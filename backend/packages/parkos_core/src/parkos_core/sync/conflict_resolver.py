"""conflict_resolver.py — thin shim over ``SyncMotor.resolve_conflict`` (T-PR7-004).

``ConflictResolver.apply_pushed_row`` decides what happens when a row
arrives from the cloud-side ``/sync/push`` (or the branch-side
``/sync/pull``). Existing callers (``jobs/sync_cloud.py``,
``jobs/sync_sucursal.py``, and ``motor/sync_motor.py``'s own
``EngineMode.LEGACY`` dispatch — see that module's ``_apply_row_legacy``)
see **no API change**: ``apply_pushed_row(session, row) -> ApplyOutcome``
is unchanged, but the actual per-audit-class DECISION now lives in
``motor/resolve_conflict.py`` (D4, D17, D18), reached via
``SyncMotor.resolve_conflict`` (T-PR7-006).

**What moved out of this module (PR9a -> PR7).** The 4 hardcoded
``frozenset`` constants (``APPEND_ONLY_TABLES``, ``LIFECYCLE_EVENT_TABLES``,
``WORKFLOW_TABLES``, ``SESSION_TABLES``) duplicated the catalog's own
``audit_class`` field — this shim now reads ``SYNC_CATALOG_BY_NAME`` instead.
The ``_read_local_seq`` stub (permanently ``None``) is replaced by
``motor/read_local_seq.py::ReadLocalSeq`` (D4) — every ``[V]`` conflict
without a natural key now produces a concrete seq instead of trivially
admitting every row.

**Behavior change this shim necessarily carries (documented, not hidden).**
The PR9a policy treated ``[L-E]``/``[A]`` as unconditionally ``APPLIED`` and
never checked ``depends_on`` at all; REQ-MOT-007's amendment (D18) gates
those classes on parent resolution instead (``RETRY`` on a missing parent).
Under the current catalog wiring (no concrete ``ValidateParentChain`` hook
yet — see ``motor/resolve_conflict.py``'s docstring), that branch still
resolves ``APPLIED`` in practice, so no existing caller observes a different
outcome today. The ``seq``-format pre-validation the PR9a stub performed
before class dispatch (missing/non-int/negative ``datos.seq`` -> ``ERROR``,
even for classes that never consulted ``seq`` at all) is also gone: ``seq``
is only meaningful for the ``[V]``-without-``natural_key`` branch now, and an
invalid seq there is bounded by the SQL query itself (a non-numeric
``datos->>'seq'`` in ``prod.sync_queue``'s own history — not the incoming
row — would raise at the DB layer, surfacing as the pre-existing
``SQLAlchemyError`` -> ``ERROR`` path below).

Cites design §5 (API Contracts), §7.5 (sequence diagram), REQ-MOT-007..010.
"""
from __future__ import annotations

import enum
import uuid as uuid_lib

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .catalog.sync_catalog import SYNC_CATALOG_BY_NAME


class ApplyOutcome(enum.StrEnum):
    """Result of applying a single pushed row."""

    APPLIED = "applied"
    CONFLICT_V = "conflict_v"
    CONFLICT_LS = "conflict_ls"
    ERROR = "error"


# ConflictResolution.status -> ApplyOutcome for classes that never carry a
# [L-S]-specific conflict (RETRY always means "caller retries the batch",
# matching motor/sync_motor.py's own _LEGACY_OUTCOME_TO_STATUS reverse map).
_STATUS_TO_OUTCOME: dict[str, ApplyOutcome] = {
    "APPLIED": ApplyOutcome.APPLIED,
    "RETRY": ApplyOutcome.ERROR,
}


class ConflictResolver:
    """Apply pushed rows from a branch sync to the local DB (shim, T-PR7-004).

    Args:
        jwt_overlap_hours: Length of the ``[L-S]`` grace window during
            which both sides may legitimately write a session close.
            Default 24h per REQ-MOT-013. Forwarded verbatim as
            ``SyncMotor(session_grace_hours=...)``.
    """

    def __init__(self, *, jwt_overlap_hours: int = 24) -> None:
        if jwt_overlap_hours < 0:
            raise ValueError("jwt_overlap_hours must be >= 0")
        self.jwt_overlap_hours = jwt_overlap_hours

    async def apply_pushed_row(
        self, session: AsyncSession, row: dict
    ) -> ApplyOutcome:
        """Apply a pushed row from the branch to the local DB.

        Args:
            session: Active ``AsyncSession`` (caller commits).
            row: Pushed row with shape ``{tabla, uuid_registro, datos,
                uuid_sucursal, timestamp_evento, actor_uuid}``.

        Returns:
            :class:`ApplyOutcome` — one of ``APPLIED``, ``CONFLICT_V``,
            ``CONFLICT_LS``, ``ERROR``. The caller is responsible for
            translating outcomes into repo writes and into the next-batch
            decision (``ERROR`` -> retry the whole batch).
        """
        tabla = row.get("tabla")
        uuid_registro = row.get("uuid_registro")
        datos = row.get("datos") or {}
        # `datos` doubles as the resolve_conflict "remote" payload — the
        # [L-S] branch reads `remote["timestamp_evento"]`, so surface the
        # row-level field into it when the row itself carries one and the
        # payload does not (mirrors what a real wire push assembles).
        remote = dict(datos)
        remote.setdefault("timestamp_evento", row.get("timestamp_evento"))

        if not isinstance(tabla, str) or not tabla:
            return ApplyOutcome.ERROR
        if not isinstance(uuid_registro, (str, uuid_lib.UUID)):
            return ApplyOutcome.ERROR
        if isinstance(uuid_registro, str):
            try:
                uuid_registro = uuid_lib.UUID(uuid_registro)
            except ValueError:
                return ApplyOutcome.ERROR

        spec = SYNC_CATALOG_BY_NAME.get(tabla)
        if spec is None:
            # Out-of-catalog table (e.g. `sync_queue` itself, an
            # infrastructure table never pushed as a business row) — no
            # conflict is possible; accept unconditionally, matching the
            # pre-PR7 append-only default for anything outside the catalog.
            return ApplyOutcome.APPLIED

        actor_uuid = row.get("actor_uuid") or uuid_lib.uuid4()
        if isinstance(actor_uuid, str):
            try:
                actor_uuid = uuid_lib.UUID(actor_uuid)
            except ValueError:
                actor_uuid = uuid_lib.uuid4()

        branch_uuid = row.get("uuid_sucursal")
        if isinstance(branch_uuid, str):
            try:
                branch_uuid = uuid_lib.UUID(branch_uuid)
            except ValueError:
                branch_uuid = None

        # Lazy import — avoids a module-load-time circular import:
        # motor/sync_motor.py already imports THIS module (for the
        # EngineMode.LEGACY dispatch, see that module's _apply_row_legacy),
        # so importing SyncMotor at this module's top level would cycle.
        from .motor.sync_motor import SyncMotor

        motor = SyncMotor(session_grace_hours=self.jwt_overlap_hours)

        try:
            resolution = await motor.resolve_conflict(
                session,
                spec,
                uuid_registro=uuid_registro,
                local=None,
                remote=remote,
                actor_uuid=actor_uuid,
                branch_uuid=branch_uuid,
            )
        except SQLAlchemyError:
            # Driver / connection failure — caller retries the batch.
            return ApplyOutcome.ERROR

        if resolution.status in _STATUS_TO_OUTCOME:
            return _STATUS_TO_OUTCOME[resolution.status]
        # MANUAL — which flavor of conflict depends on the audit class.
        return ApplyOutcome.CONFLICT_LS if spec.audit_class == "L_S" else ApplyOutcome.CONFLICT_V


__all__ = [
    "ApplyOutcome",
    "ConflictResolver",
]
