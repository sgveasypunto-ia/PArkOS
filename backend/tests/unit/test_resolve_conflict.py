"""test_resolve_conflict.py — T-PR7-005/006 acceptance for
``motor/resolve_conflict.py::resolve_conflict`` (REQ-MOT-007..010, -013,
design.md §5 / §7.5).

Coverage — the per-audit-class dispatch table:

  - ``[V]`` with ``natural_key`` (``clientes``) -> delegates to
    ``spec.hook_pre_insert`` (``IdentityReconciler``, D17) -> always
    ``APPLIED``.
  - ``[V]`` without ``natural_key`` (``documentos`` — the ER model itself
    declares no UK for this table, see ``entries/sync_entries_v.py``'s own
    comment on ``_DOCUMENTOS``) -> seq comparison via ``ReadLocalSeq`` (D4)
    -> ``APPLIED`` / ``MANUAL(seq_tiebreak)`` with a ``sync_conflict`` row
    written. (``empresa`` no longer fits this precondition since 2026-09-10
    — it now declares ``natural_key=("nit",)``, see that same module.)
  - ``[L_E]``/``[L_W]``/``[A]`` (``ingreso`` / ``alerta`` / ``salidas``) ->
    delegates to ``spec.hook_validate_parent`` (``ValidateParentChain``,
    D18) -> ``APPLIED`` (no-op default today) / ``RETRY(parent_missing)``
    (test-injected hook, REQ-HOOK-015 precedent).
  - ``[L_S]`` (``login``) -> 24h grace window (REQ-MOT-013) -> ``APPLIED``
    within window, ``MANUAL`` outside it or with no ``timestamp_evento``.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

from parkos_core.models.V.documentos import Documentos
from parkos_core.sync.hooks.base import HookResult
from parkos_core.sync.motor.resolve_conflict import resolve_conflict
from sqlalchemy import select

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)


# ---------------------------------------------------------------------------
# [V] with natural_key -> IdentityReconciler delegation (D17, REQ-MOT-008)
# ---------------------------------------------------------------------------


async def test_v_with_natural_key_delegates_to_identity_reconciler(make_spec) -> None:
    """No local open_version -> ordinary first insert -> APPLIED, no reconciliation."""
    spec = make_spec("clientes")
    assert spec.natural_key  # precondition

    resolution = await resolve_conflict(
        None,  # type: ignore[arg-type]
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote={"tipo_identificador": "CC", "numero_identificacion": "123"},
        actor_uuid=ACTOR_UUID,
        open_version=None,
    )

    assert resolution.status == "APPLIED"
    assert resolution.reconciliation is None


async def test_v_with_natural_key_never_blocks_on_divergent_data(pg_session, make_spec) -> None:
    """A materially divergent arrival still resolves APPLIED (never MANUAL/RETRY).

    A real session is required here: ``IdentityReconciler`` writes an
    informational ``sync_conflict`` row for a material divergence (it holds
    ``ctx.session``), even though the apply itself always proceeds.
    """
    spec = make_spec("clientes")
    open_version = {
        "uuid": uuid_lib.uuid4(),
        "tipo_identificador": "CC",
        "numero_identificacion": "123",
        "nombre": "Ana",
        "vigente_desde": datetime(2026, 1, 1),
    }
    remote = {
        "tipo_identificador": "CC",
        "numero_identificacion": "123",
        "nombre": "Beatriz",  # material divergence
        "vigente_desde": datetime(2026, 2, 1),
    }

    resolution = await resolve_conflict(
        pg_session,
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote=remote,
        actor_uuid=ACTOR_UUID,
        open_version=open_version,
    )

    assert resolution.status == "APPLIED"
    assert resolution.reconciliation == "forward"


# ---------------------------------------------------------------------------
# [V] without natural_key -> seq comparison (D4, REQ-MOT-009)
# ---------------------------------------------------------------------------


async def test_v_without_natural_key_applies_on_first_write(pg_session, make_spec) -> None:
    """No local row exists yet -> local_seq is None -> APPLIED (no conflict possible)."""
    spec = make_spec("documentos")
    assert not spec.natural_key  # precondition

    resolution = await resolve_conflict(
        pg_session,
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote={"created_at": datetime.now(UTC).replace(tzinfo=None)},
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "APPLIED"


async def test_v_without_natural_key_applies_when_remote_seq_is_newer(
    pg_session, make_spec
) -> None:
    spec = make_spec("documentos")
    row_uuid = uuid_lib.uuid4()
    local_created = _naive(datetime(2026, 1, 1, tzinfo=UTC))
    pg_session.add(Documentos(uuid=row_uuid, created_at=local_created))
    await pg_session.flush()

    resolution = await resolve_conflict(
        pg_session,
        spec,
        uuid_registro=row_uuid,
        local=None,
        remote={"created_at": local_created + timedelta(days=1)},
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "APPLIED"


async def test_v_without_natural_key_manual_on_stale_remote_seq(pg_session, make_spec) -> None:
    """remote_seq <= local_seq -> MANUAL(seq_tiebreak) + a sync_conflict row."""
    from parkos_core.models.A.sync_conflict import SyncConflict

    spec = make_spec("documentos")
    row_uuid = uuid_lib.uuid4()
    local_created = _naive(datetime(2026, 1, 1, tzinfo=UTC))
    pg_session.add(Documentos(uuid=row_uuid, created_at=local_created))
    await pg_session.flush()

    resolution = await resolve_conflict(
        pg_session,
        spec,
        uuid_registro=row_uuid,
        local={"created_at": local_created},
        remote={"created_at": local_created},  # equal, not strictly greater
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "MANUAL"
    assert resolution.reason == "seq_tiebreak"

    rows = (
        (
            await pg_session.execute(
                select(SyncConflict).where(SyncConflict.uuid_registro == row_uuid)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].politica == "seq_tiebreak"


async def test_v_without_natural_key_manual_when_remote_seq_missing(pg_session, make_spec) -> None:
    """The remote payload has no comparable field -> can't prove newer -> MANUAL."""
    spec = make_spec("documentos")
    row_uuid = uuid_lib.uuid4()
    pg_session.add(Documentos(uuid=row_uuid, created_at=_naive(datetime(2026, 1, 1, tzinfo=UTC))))
    await pg_session.flush()

    resolution = await resolve_conflict(
        pg_session,
        spec,
        uuid_registro=row_uuid,
        local=None,
        remote={},
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "MANUAL"
    assert resolution.reason == "seq_tiebreak"


# ---------------------------------------------------------------------------
# [L_E] / [L_W] / [A] -> depends_on parent resolution (D18, REQ-MOT-010)
# ---------------------------------------------------------------------------


async def test_le_resolves_applied_when_no_hook_wired(make_spec) -> None:
    """No concrete ValidateParentChain hook yet -> registry no-op -> APPLIED.

    ``ingreso`` has a non-empty depends_on but no catalog entry sets
    hook_validate_parent today (documented gap, resolve_conflict.py's
    docstring) — passing session=None proves this branch touches no DB.
    """
    spec = make_spec("ingreso")
    assert spec.depends_on

    resolution = await resolve_conflict(
        None,  # type: ignore[arg-type]
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote={"uuid_sucursal": uuid_lib.uuid4()},
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "APPLIED"


async def test_lw_retries_when_injected_hook_rejects_parent(make_spec) -> None:
    """A test-injected hook_validate_parent (REQ-HOOK-015 precedent) proves
    the RETRY(parent_missing) branch is reachable once a real hook exists."""
    spec = make_spec(
        "alerta",
        hook_validate_parent=lambda ctx: HookResult(proceed=True, parent_valid=False),
    )

    resolution = await resolve_conflict(
        None,  # type: ignore[arg-type]
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote={"uuid_sucursal": uuid_lib.uuid4()},
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "RETRY"
    assert resolution.reason == "parent_missing"


async def test_a_resolves_applied_with_no_depends_on(make_spec) -> None:
    """depends_on=() short-circuits before any hook invocation."""
    spec = make_spec("caja")
    assert spec.depends_on == ("sucursal",)  # precondition — non-empty, still no-op today

    resolution = await resolve_conflict(
        None,  # type: ignore[arg-type]
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote={},
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "APPLIED"


# ---------------------------------------------------------------------------
# [L_S] -> 24h grace window (REQ-MOT-013)
# ---------------------------------------------------------------------------


async def test_ls_applies_within_grace_window(make_spec) -> None:
    spec = make_spec("login")
    recent = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)

    resolution = await resolve_conflict(
        None,  # type: ignore[arg-type]
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote={"timestamp_evento": recent},
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "APPLIED"


async def test_ls_manual_past_grace_window(make_spec) -> None:
    spec = make_spec("login")
    stale = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=25)

    resolution = await resolve_conflict(
        None,  # type: ignore[arg-type]
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote={"timestamp_evento": stale},
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "MANUAL"
    assert resolution.reason == "grace_window_expired"


async def test_ls_manual_when_timestamp_evento_missing(make_spec) -> None:
    spec = make_spec("login")

    resolution = await resolve_conflict(
        None,  # type: ignore[arg-type]
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote={},
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "MANUAL"
    assert resolution.reason == "missing_timestamp_evento"


async def test_ls_applies_when_timestamp_evento_is_wire_string(make_spec) -> None:
    """``remote`` is the incoming WIRE payload — over real JSON (the only
    way a row actually reaches this function outside a test), a datetime
    is always an ISO-8601 string, never a ``datetime`` instance. Every
    other test in this file passes a real ``datetime`` object, which is
    exactly why this crashed in a live Docker deployment
    (``TypeError: unsupported operand type(s) for -: 'datetime.datetime'
    and 'str'``) despite 100% green tests beforehand.
    """
    spec = make_spec("login")
    recent_iso = (datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)).isoformat()

    resolution = await resolve_conflict(
        None,  # type: ignore[arg-type]
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote={"timestamp_evento": recent_iso},
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "APPLIED"


async def test_ls_manual_when_timestamp_evento_is_malformed_string(make_spec) -> None:
    """A malformed wire timestamp resolves ``MANUAL`` (operator-reviewable)
    — never a crash that takes the whole batch down with it."""
    spec = make_spec("login")

    resolution = await resolve_conflict(
        None,  # type: ignore[arg-type]
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote={"timestamp_evento": "not-a-real-timestamp"},
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "MANUAL"
    assert resolution.reason == "invalid_timestamp_evento"


async def test_ls_custom_grace_window_override(make_spec) -> None:
    """``session_grace_hours`` override wins over the 24h default."""
    spec = make_spec("login")
    recent = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)

    resolution = await resolve_conflict(
        None,  # type: ignore[arg-type]
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote={"timestamp_evento": recent},
        actor_uuid=ACTOR_UUID,
        session_grace_hours=1,
    )

    assert resolution.status == "MANUAL"
    assert resolution.reason == "grace_window_expired"


async def test_ls_grace_window_reads_env_var_when_no_override(monkeypatch, make_spec) -> None:
    """``PARKOS_SESSION_GRACE_HOURS`` is honored when no explicit override is passed."""
    monkeypatch.setenv("PARKOS_SESSION_GRACE_HOURS", "1")
    spec = make_spec("login")
    recent = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)

    resolution = await resolve_conflict(
        None,  # type: ignore[arg-type]
        spec,
        uuid_registro=uuid_lib.uuid4(),
        local=None,
        remote={"timestamp_evento": recent},
        actor_uuid=ACTOR_UUID,
    )

    assert resolution.status == "MANUAL"
    assert resolution.reason == "grace_window_expired"
