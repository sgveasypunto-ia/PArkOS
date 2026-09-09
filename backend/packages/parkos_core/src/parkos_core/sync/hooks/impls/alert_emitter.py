"""hooks/impls/alert_emitter.py — ``AlertEmitter`` (T-PR8-005, T-PR8-009).

Registry-validated ``tipo_alerta`` writer (design.md §6 hook table:
"``AlertEmitter`` | dependency-buffer sweep, dispatcher, verifier |
Registry-validated ``tipo_alerta`` from ``prod.alert_types``"). PR8 wires
the dependency-buffer TTL sweep's escalation alert
(``motor/dependency_buffer.py::_lw_buffer_sweep``) through here — the ONE
production call site this PR adds.

**Not `HookContext`-shaped.** Unlike the other 7 registry callables,
``AlertEmitter`` is never bound to one of ``SyncCatalogEntry``'s four
``hook_*`` slots — design.md's hook table lists its callers as
"dependency-buffer sweep, dispatcher, verifier", none of which run inside
``apply_row``'s per-row lifecycle. It still self-registers via
``hooks.registry.register()`` at import time (matching every other
``hooks/impls/*`` module's convention, and ``registry.py``'s own docstring
naming ``AlertEmitter`` among the modules that do this) so callers can
discover it by name (``registry.get_hook("alert_emitter")``) without a hard
import, even though its call signature is its own (``session`` + explicit
kwargs), not ``Callable[[HookContext], HookResult]``.

**Write path.** Reuses the SAME canonical writer
``jobs/sync_cloud.py::_handle_chain_break`` already established for
``alerta`` chain-root rows — ``repo.workflow.append_transition`` (the
``[L-W]`` canonical write path; ``STATE_MACHINES["alerta"]`` requires
``estado='activa'`` for the root transition, no ``parent_uuid``). This is
NOT the same path ``dian/cloud/dispatcher.py::_write_alerta`` uses (a bare
``repo.append_only.append_event`` call, bypassing the state machine) — that
pre-existing inconsistency predates ``prod.alert_types`` and is a
documented, out-of-scope follow-up (see this PR's apply report).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ....repo import alert_types
from ....repo import workflow as wf_helpers
from .. import registry


async def alert_emitter(
    session: AsyncSession,
    *,
    tipo_alerta: str,
    uuid_sucursal: uuid_lib.UUID | None = None,
    actor_uuid: uuid_lib.UUID | None = None,
) -> None:
    """Validate ``tipo_alerta`` then write the ``alerta`` chain-root row.

    Args:
        session: Active ``AsyncSession`` (caller commits).
        tipo_alerta: Must be a registered ``prod.alert_types`` identifier.
        uuid_sucursal: Tenant scope for the alert (``None`` for a
            cloud-global condition).
        actor_uuid: JWT subject / system actor. Defaults to a fresh
            ``uuid4()`` for system-originated alerts (no human actor) —
            mirrors ``jobs/sync_cloud.py::_handle_chain_break``'s own
            ``actor = uuid_lib.uuid4()`` for the same reason.

    Raises:
        UnknownAlertTypeError: ``tipo_alerta`` is not seeded.
    """
    await alert_types.validate(session, tipo_alerta)

    from ....models.L_W.alerta import Alerta

    await wf_helpers.append_transition(
        session,
        Alerta,
        actor_uuid=actor_uuid or uuid_lib.uuid4(),
        new_attrs={
            "uuid_sucursal": uuid_sucursal,
            "tipo_alerta": tipo_alerta,
            "estado": "activa",
            "timestamp_evento": datetime.now(UTC).replace(tzinfo=None),
        },
        log_tx=False,
    )


registry.register("alert_emitter", alert_emitter)

__all__ = ["alert_emitter"]
