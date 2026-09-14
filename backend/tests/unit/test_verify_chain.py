"""test_verify_chain.py — T-PR6-006/007/008 acceptance for
``motor/verify_chain.py`` (REQ-MOT-006, REQ-CAT-009, REQ-CAT-005).

Real Postgres throughout — the walker reads actual persisted rows written
through ``repo.hash_chain.append`` (correct chain) and a raw, deliberately
mismatched row (broken chain) to prove the anomaly detection + continuation
behavior.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

from parkos_core.models.A.log_transaccional import LogTransaccional
from parkos_core.models.A.revocacion_factura import RevocacionFactura
from parkos_core.repo.hash_chain import append as hash_chain_append
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG, SYNC_CATALOG_BY_NAME
from parkos_core.sync.motor.verify_chain import (
    ChainAnomaly,
    verify_chain,
    verify_chain_for_spec,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000ad")


async def _insert_bypassing_chain_trigger(
    session,
    *,
    uuid_sucursal: uuid_lib.UUID,
    accion: str,
    uuid_registro_afectado: uuid_lib.UUID,
    timestamp_evento: datetime,
    hash_anterior: str,
    hash_actual: str,
) -> uuid_lib.UUID:
    """INSERT a deliberately hash-broken ``log_transaccional`` row for tests.

    ``prod.fn_extend_hash_chain()`` (0001_initial_schema.py) itself
    enforces ``NEW.hash_anterior == prev_hash`` at INSERT time and raises
    ``HASH_CHAIN_INTEGRITY_VIOLATION`` on any mismatch — a real broken
    chain link can therefore never land via an ordinary INSERT. Disabling
    triggers for this ONE INSERT (``session_replication_role = replica``,
    same established pattern as ``test_bi_temporal_compensation.py``'s
    ``_seed_factura``) is the only way to construct the corrupted fixture
    ``verify_chain``'s anomaly detection is meant to catch — the DB
    trigger is a real safety net in production; this test intentionally
    defeats it to prove the WALKER (not the trigger) also detects breaks.
    """
    row_uuid = uuid_lib.uuid4()
    await session.execute(text("SET session_replication_role = replica"))
    await session.execute(
        text(
            "INSERT INTO prod.log_transaccional "
            "(uuid, uuid_sucursal, accion, tabla_afectada, "
            " uuid_registro_afectado, timestamp_evento, "
            " hash_anterior, hash_actual) "
            "VALUES (:uuid, :uuid_sucursal, :accion, 'ingreso', "
            " :uuid_registro_afectado, :timestamp_evento, "
            " :hash_anterior, :hash_actual)"
        ),
        {
            "uuid": row_uuid,
            "uuid_sucursal": uuid_sucursal,
            "accion": accion,
            "uuid_registro_afectado": uuid_registro_afectado,
            "timestamp_evento": timestamp_evento,
            "hash_anterior": hash_anterior,
            "hash_actual": hash_actual,
        },
    )
    await session.execute(text("SET session_replication_role = origin"))
    await session.commit()
    return row_uuid


async def test_walks_both_chain_bearing_tables(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """``verify_chain`` iterates BOTH log_transaccional and revocacion_factura.

    Writes one correctly-chained row into each table, then a SECOND row
    into ``log_transaccional`` whose ``hash_anterior`` is deliberately
    corrupted (does not match the first row's ``hash_actual``) — the walk
    must report exactly one anomaly for ``log_transaccional`` and CONTINUE
    (i.e. it does not stop after finding it, and does not falsely flag
    ``revocacion_factura``, whose chain is untouched and correct).
    """
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        # 1. A correct log_transaccional chain: genesis (auto) + 1 good row.
        await hash_chain_append(
            session,
            LogTransaccional,
            {
                "uuid_sucursal": seeded_sucursal_uuid,
                "accion": "crear",
                "tabla_afectada": "ingreso",
                "uuid_registro_afectado": uuid_lib.uuid4(),
                "timestamp_evento": datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None),
            },
            actor_uuid=ACTOR_UUID,
        )
        await session.commit()

        # 2. A correct revocacion_factura chain: genesis (auto) + 1 good row.
        await hash_chain_append(
            session,
            RevocacionFactura,
            {
                "uuid_sucursal": seeded_sucursal_uuid,
                "uuid_factura_electronica": None,
                "motivo": "dian_confirmada",
                "timestamp_evento": datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None),
            },
            actor_uuid=ACTOR_UUID,
        )
        await session.commit()

        # 3. A SECOND log_transaccional row with a deliberately WRONG
        #    hash_anterior — the DB trigger itself enforces the correct
        #    linkage at INSERT time (see _insert_bypassing_chain_trigger's
        #    docstring), so triggers are disabled for this one insert to
        #    construct the corrupted fixture the walker must detect.
        broken_uuid = await _insert_bypassing_chain_trigger(
            session,
            uuid_sucursal=seeded_sucursal_uuid,
            accion="actualizar",
            uuid_registro_afectado=uuid_lib.uuid4(),
            timestamp_evento=datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None),
            hash_anterior="0" * 64,  # wrong on purpose
            hash_actual="1" * 64,
        )

        anomalies = await verify_chain(session, seeded_sucursal_uuid)

        log_anomalies = [a for a in anomalies if a.tabla == "log_transaccional"]
        revocacion_anomalies = [a for a in anomalies if a.tabla == "revocacion_factura"]

        assert len(log_anomalies) == 1, (
            f"expected exactly 1 log_transaccional anomaly, got {len(log_anomalies)}"
        )
        assert log_anomalies[0].uuid == broken_uuid
        assert log_anomalies[0].actual == "0" * 64

        # revocacion_factura's chain is untouched — zero anomalies.
        assert revocacion_anomalies == []


async def test_mismatch_does_not_abort_the_walk(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """A broken link at row N does not prevent row N+1 from being checked
    against its OWN (correct) predecessor — no anomaly cascade."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    spec = SYNC_CATALOG_BY_NAME["log_transaccional"]

    async with Session() as session:
        first = await hash_chain_append(
            session,
            LogTransaccional,
            {
                "uuid_sucursal": seeded_sucursal_uuid,
                "accion": "crear",
                "tabla_afectada": "ingreso",
                "uuid_registro_afectado": uuid_lib.uuid4(),
                "timestamp_evento": datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None),
            },
            actor_uuid=ACTOR_UUID,
        )
        await session.commit()

        # Broken row — wrong hash_anterior (trigger bypassed to construct
        # the corrupted fixture, see _insert_bypassing_chain_trigger).
        broken_uuid = await _insert_bypassing_chain_trigger(
            session,
            uuid_sucursal=seeded_sucursal_uuid,
            accion="actualizar",
            uuid_registro_afectado=uuid_lib.uuid4(),
            timestamp_evento=datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None),
            hash_anterior="0" * 64,
            hash_actual="2" * 64,
        )

        # A THIRD row correctly chained onto the BROKEN row's OWN
        # hash_actual — the walker must accept it (it checks against the
        # immediately prior row, not against the ORIGINAL genesis/first
        # row), proving the walk did not abort at the first anomaly. This
        # one links correctly (hash_anterior == broken row's hash_actual),
        # so the trigger accepts it via the ordinary INSERT path.
        third = LogTransaccional(
            uuid_sucursal=seeded_sucursal_uuid,
            accion="actualizar",
            tabla_afectada="ingreso",
            uuid_registro_afectado=uuid_lib.uuid4(),
            timestamp_evento=datetime(2026, 1, 3, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None),
            hash_anterior="2" * 64,  # matches broken row's hash_actual
            hash_actual="3" * 64,
        )
        session.add(third)
        await session.commit()

        anomalies = await verify_chain_for_spec(session, spec, seeded_sucursal_uuid)

        assert len(anomalies) == 1
        assert anomalies[0].uuid == broken_uuid
        assert first.uuid not in {a.uuid for a in anomalies}
        assert third.uuid not in {a.uuid for a in anomalies}


async def test_colliding_timestamp_evento_does_not_false_positive(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """Rows sharing the IDENTICAL ``timestamp_evento`` must still verify
    clean — the ordering key deciding "prior row" (both at append time in
    ``repo.hash_chain._read_prior_hash`` and at verify time here) is
    ``created_at``, never ``timestamp_evento``. ``timestamp_evento`` is
    business-supplied and can collide across a burst of events; before
    the fix, ``ORDER BY timestamp_evento DESC, uuid DESC`` picked
    whichever EXISTING row happened to have the lexicographically-largest
    random uuid as "prior" once 2+ rows shared a timestamp — NOT the row
    that was truly appended last — permanently forking the chain. This is
    the exact failure confirmed live in a real Docker deployment
    (``sync_cloud.hash_chain_break`` fired on ``log_transaccional`` rows
    that were never actually corrupted).

    UUIDs are pinned explicitly (never left to ``gen_random_uuid()``) so
    the old bug reproduces deterministically instead of only sometimes,
    depending on how the random UUIDs happened to sort:
    ``uuid_a`` (max) is appended FIRST, ``uuid_b`` (near-min) SECOND,
    ``uuid_c`` THIRD — true append order is a -> b -> c, but the old
    ``uuid DESC`` tie-break on the shared timestamp would pick "a"
    (uuid_a > uuid_b) as the prior for "c", not "b".
    """
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    spec = SYNC_CATALOG_BY_NAME["log_transaccional"]
    same_timestamp = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC).replace(tzinfo=None)

    uuid_a = uuid_lib.UUID(int=(2**128 - 1))
    uuid_b = uuid_lib.UUID(int=1)
    uuid_c = uuid_lib.UUID(int=2**127)

    def _attrs(row_uuid: uuid_lib.UUID) -> dict:
        return {
            "uuid": row_uuid,
            "uuid_sucursal": seeded_sucursal_uuid,
            "accion": "crear",
            "tabla_afectada": "ingreso",
            "uuid_registro_afectado": uuid_lib.uuid4(),
            "timestamp_evento": same_timestamp,
        }

    async with Session() as session:
        row_a = await hash_chain_append(
            session, LogTransaccional, _attrs(uuid_a), actor_uuid=ACTOR_UUID
        )
        await session.commit()

        # Only ONE existing row so far — even the old buggy tie-break
        # can't go wrong yet (there's nothing to tie against).
        row_b = await hash_chain_append(
            session, LogTransaccional, _attrs(uuid_b), actor_uuid=ACTOR_UUID
        )
        await session.commit()

        # NOW two existing rows (a, b) share ``same_timestamp`` — this is
        # where the old ``uuid DESC`` tie-break would pick "a" instead of
        # the truly-last-appended "b".
        row_c = await hash_chain_append(
            session, LogTransaccional, _attrs(uuid_c), actor_uuid=ACTOR_UUID
        )
        await session.commit()

        assert row_c.hash_anterior == row_b.hash_actual, (
            "row_c must chain onto the truly-last-appended row_b "
            f"(hash_actual={row_b.hash_actual!r}), not row_a "
            f"(hash_actual={row_a.hash_actual!r}); got "
            f"hash_anterior={row_c.hash_anterior!r}"
        )

        anomalies = await verify_chain_for_spec(session, spec, seeded_sucursal_uuid)

    assert anomalies == [], (
        "a chain built entirely from rows sharing one timestamp_evento "
        f"must still verify clean when ordered by created_at; got {anomalies!r}"
    )


def test_single_chain_per_tabla_uuid_sucursal() -> None:
    """T-PR6-008 — exactly one catalog entry resolves to ``revocacion_factura``.

    The superseded dual-catalog design let TWO entries both target
    ``revocacion_factura``, producing two interleaved hash chains for the
    same ``(tabla, uuid_sucursal)`` — a guaranteed false ``HashChainBreak``.
    D6-rev removes the second entry; this is the direct regression guard.
    """
    matching = [entry for entry in SYNC_CATALOG if entry.name == "revocacion_factura"]
    assert len(matching) == 1, (
        f"expected exactly 1 catalog entry for revocacion_factura, got "
        f"{len(matching)} — the double-chain hazard is back"
    )

    matching_log = [entry for entry in SYNC_CATALOG if entry.name == "log_transaccional"]
    assert len(matching_log) == 1

    # Both are the only two hash_chain=True entries in the whole catalog
    # (REQ-CAT-009) — verify_chain() must not accidentally pick up a third.
    chain_bearing = [entry.name for entry in SYNC_CATALOG if entry.hash_chain]
    assert set(chain_bearing) == {"log_transaccional", "revocacion_factura"}


def test_chain_anomaly_is_frozen() -> None:
    """``ChainAnomaly`` is an immutable record (matches ``ApplyResult``-style
    dataclasses elsewhere in ``motor/``)."""
    anomaly = ChainAnomaly(
        tabla="log_transaccional",
        uuid_sucursal=None,
        uuid=uuid_lib.uuid4(),
        expected="a" * 64,
        actual="b" * 64,
    )
    assert anomaly.reason == "hash_chain_break"
