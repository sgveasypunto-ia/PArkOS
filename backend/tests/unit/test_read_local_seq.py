"""test_read_local_seq.py — T-PR7-001/002 acceptance for
``motor/read_local_seq.py::ReadLocalSeq`` (D4, design.md §2 Issue #4).

Coverage — the 4-strategy dispatch table:

  - ``seq_via_datos``: reads ``prod.sync_queue.datos->>'seq'``, 5s TTL cache,
    ``force_refresh`` bypass.
  - ``max_timestamp_evento`` / ``max_created_at``: read the destination
    table's own column directly, never cached.
  - ``none``: returns ``None`` immediately, no DB access at all (proven by
    passing ``session=None``).

All DB-backed cases use the real testcontainers Postgres
(``pg_engine``/``pg_session``/``alembic_upgrade``) — replaces the PR9a-era
stub this module supersedes (T-PR7-004 removes
``conflict_resolver.py::_read_local_seq``).
"""
from __future__ import annotations

import asyncio
import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.models.A.sync_queue import SyncQueue
from parkos_core.models.L_S.login import Login
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.sync.motor.read_local_seq import ReadLocalSeq, ReadLocalSeqError


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _insert_sync_queue_seq(
    pg_session, *, tabla: str, uuid_registro, uuid_sucursal, seq: int, estado: str = "exitoso"
) -> None:
    row = SyncQueue(
        uuid_sucursal=uuid_sucursal,
        operacion="update",
        tabla=tabla,
        uuid_registro=uuid_registro,
        datos={"seq": seq},
        prioridad=0,
        estado=estado,
        intentos=0,
    )
    pg_session.add(row)
    await pg_session.flush()


# ---------------------------------------------------------------------------
# seq_via_datos
# ---------------------------------------------------------------------------


async def test_seq_via_datos_returns_max_seq(pg_session, make_spec, seeded_sucursal_uuid) -> None:
    """Multiple sync_queue rows for the same key -> MAX(seq) wins."""
    spec = make_spec("alerta", seq_strategy="seq_via_datos")
    uuid_registro = uuid_lib.uuid4()
    branch_uuid = seeded_sucursal_uuid
    await _insert_sync_queue_seq(
        pg_session, tabla="alerta", uuid_registro=uuid_registro, uuid_sucursal=branch_uuid, seq=3
    )
    await _insert_sync_queue_seq(
        pg_session, tabla="alerta", uuid_registro=uuid_registro, uuid_sucursal=branch_uuid, seq=7
    )

    reader = ReadLocalSeq()
    result = await reader(pg_session, spec, uuid_registro, branch_uuid=branch_uuid)

    assert result == 7


async def test_seq_via_datos_returns_none_when_no_rows(pg_session, make_spec) -> None:
    spec = make_spec("alerta", seq_strategy="seq_via_datos")
    result = await ReadLocalSeq()(pg_session, spec, uuid_lib.uuid4(), branch_uuid=uuid_lib.uuid4())
    assert result is None


async def test_seq_via_datos_ignores_fallido_rows(
    pg_session, make_spec, seeded_sucursal_uuid
) -> None:
    """A ``'fallido'`` row is superseded by a fresh re-enqueue, never counted."""
    spec = make_spec("alerta", seq_strategy="seq_via_datos")
    uuid_registro = uuid_lib.uuid4()
    branch_uuid = seeded_sucursal_uuid
    await _insert_sync_queue_seq(
        pg_session,
        tabla="alerta",
        uuid_registro=uuid_registro,
        uuid_sucursal=branch_uuid,
        seq=99,
        estado="fallido",
    )

    result = await ReadLocalSeq()(pg_session, spec, uuid_registro, branch_uuid=branch_uuid)

    assert result is None


async def test_seq_via_datos_caches_within_ttl(
    pg_session, make_spec, seeded_sucursal_uuid
) -> None:
    """A second call within the TTL returns the cached value, not a fresh read."""
    spec = make_spec("alerta", seq_strategy="seq_via_datos")
    uuid_registro = uuid_lib.uuid4()
    branch_uuid = seeded_sucursal_uuid
    await _insert_sync_queue_seq(
        pg_session, tabla="alerta", uuid_registro=uuid_registro, uuid_sucursal=branch_uuid, seq=1
    )

    reader = ReadLocalSeq(cache_ttl_seconds=5.0)
    first = await reader(pg_session, spec, uuid_registro, branch_uuid=branch_uuid)
    assert first == 1

    # A second row lands locally (a fresh conflict) but the cache is still
    # warm — the reader must not see it yet.
    await _insert_sync_queue_seq(
        pg_session, tabla="alerta", uuid_registro=uuid_registro, uuid_sucursal=branch_uuid, seq=42
    )
    second = await reader(pg_session, spec, uuid_registro, branch_uuid=branch_uuid)
    assert second == 1


async def test_seq_via_datos_expires_after_ttl(
    pg_session, make_spec, seeded_sucursal_uuid
) -> None:
    """Past the TTL, the reader re-queries and observes the fresh value."""
    spec = make_spec("alerta", seq_strategy="seq_via_datos")
    uuid_registro = uuid_lib.uuid4()
    branch_uuid = seeded_sucursal_uuid
    await _insert_sync_queue_seq(
        pg_session, tabla="alerta", uuid_registro=uuid_registro, uuid_sucursal=branch_uuid, seq=1
    )

    reader = ReadLocalSeq(cache_ttl_seconds=0.05)
    first = await reader(pg_session, spec, uuid_registro, branch_uuid=branch_uuid)
    assert first == 1

    await _insert_sync_queue_seq(
        pg_session, tabla="alerta", uuid_registro=uuid_registro, uuid_sucursal=branch_uuid, seq=42
    )
    await asyncio.sleep(0.1)
    second = await reader(pg_session, spec, uuid_registro, branch_uuid=branch_uuid)
    assert second == 42


async def test_seq_via_datos_force_refresh_bypasses_cache(
    pg_session, make_spec, seeded_sucursal_uuid
) -> None:
    """``force_refresh=True`` re-queries even within a warm TTL window."""
    spec = make_spec("alerta", seq_strategy="seq_via_datos")
    uuid_registro = uuid_lib.uuid4()
    branch_uuid = seeded_sucursal_uuid
    await _insert_sync_queue_seq(
        pg_session, tabla="alerta", uuid_registro=uuid_registro, uuid_sucursal=branch_uuid, seq=1
    )

    reader = ReadLocalSeq(cache_ttl_seconds=30.0)
    first = await reader(pg_session, spec, uuid_registro, branch_uuid=branch_uuid)
    assert first == 1

    await _insert_sync_queue_seq(
        pg_session, tabla="alerta", uuid_registro=uuid_registro, uuid_sucursal=branch_uuid, seq=42
    )
    forced = await reader(
        pg_session, spec, uuid_registro, branch_uuid=branch_uuid, force_refresh=True
    )
    assert forced == 42


# ---------------------------------------------------------------------------
# max_timestamp_evento / max_created_at — read the destination column
# ---------------------------------------------------------------------------


async def test_max_timestamp_evento_reads_destination_column(pg_session, make_spec) -> None:
    spec = make_spec("login", seq_strategy="max_timestamp_evento")
    when = _now()
    row = Login(uuid=uuid_lib.uuid4(), timestamp_evento=when)
    pg_session.add(row)
    await pg_session.flush()

    result = await ReadLocalSeq()(pg_session, spec, row.uuid)

    assert result == when


async def test_max_created_at_reads_destination_column(pg_session, make_spec) -> None:
    spec = make_spec("usuarios", seq_strategy="max_created_at")
    row_uuid = uuid_lib.uuid4()
    row = Usuarios(uuid=row_uuid)
    pg_session.add(row)
    await pg_session.flush()
    await pg_session.refresh(row)

    result = await ReadLocalSeq()(pg_session, spec, row_uuid)

    assert result == row.created_at


async def test_time_based_strategy_returns_none_when_row_absent(pg_session, make_spec) -> None:
    spec = make_spec("usuarios", seq_strategy="max_created_at")
    result = await ReadLocalSeq()(pg_session, spec, uuid_lib.uuid4())
    assert result is None


# ---------------------------------------------------------------------------
# none — short-circuits before touching the session
# ---------------------------------------------------------------------------


async def test_none_strategy_returns_none_without_db_access(make_spec) -> None:
    spec = make_spec("validacion_evento")
    assert spec.seq_strategy == "none"  # precondition — the sole real "none" entry

    result = await ReadLocalSeq()(None, spec, uuid_lib.uuid4())  # type: ignore[arg-type]

    assert result is None


# ---------------------------------------------------------------------------
# Unknown strategy
# ---------------------------------------------------------------------------


async def test_unknown_seq_strategy_raises(make_spec) -> None:
    spec = make_spec("usuarios", seq_strategy="bogus")

    with pytest.raises(ReadLocalSeqError, match="bogus"):
        await ReadLocalSeq()(None, spec, uuid_lib.uuid4())  # type: ignore[arg-type]
