"""hooks/impls/bi_temporal_compensation.py — ``BiTemporalCompensation`` (T-PR5-015).

REQ-HOOK-007: ``hook_post_insert`` bound to ``factura_pagos``. For an
arriving row whose ``tipo_movimiento == "reverso"``, emits a compensating
``log_transaccional`` row in the SAME transaction — the original
``factura_pagos`` row (an ``[A]`` append-only row) is NEVER modified; the
reverso is itself a brand-new, independent row (``repo.append_only.
compensate``, PR2/PR6), and this hook's job is only the AUDIT trail for
that reversal, not the reversal mechanics themselves.

The compensating row extends the per-``uuid_sucursal`` SHA-256 hash chain
via ``repo.append_only.append_event(chain_hash=True)`` — the SAME
primitive ``hook_chain_extend``'s eventual registry binding
(``LogTransaccionalChain``, PR6, REQ-HOOK-008) wraps, so no separate
top-level ``apply_row`` call is needed: the chain extends as part of THIS
``apply_row(factura_pagos, ...)`` invocation, inside the ``hook_post_insert``
phase, before the caller commits.

``factura_pagos.uuid_pago_revertido`` is a self-chain FK
(``self_chain=True``, ``parent_fk_column="uuid_pago_revertido"``) resolved
by ``ValidateParentChain`` like every other self-chain — unrelated to this
hook, which only reads it to point the compensating log row back at the
original payment.
"""
from __future__ import annotations

from datetime import UTC, datetime

from .. import registry
from ..base import HookContext, HookResult


async def bi_temporal_compensation(ctx: HookContext) -> HookResult:
    """``hook_post_insert`` — REQ-HOOK-007 reverso compensation logging."""
    payload = ctx.payload
    if payload.get("tipo_movimiento") != "reverso":
        return HookResult(proceed=True)

    from ....models.A.log_transaccional import LogTransaccional
    from ....repo import append_only

    original_uuid = payload.get("uuid_pago_revertido")
    now = datetime.now(UTC).replace(tzinfo=None)

    compensation_attrs = {
        "uuid_usuario": ctx.actor_uuid,
        "uuid_sucursal": payload.get("uuid_sucursal"),
        "accion": "compensar",
        "tabla_afectada": "factura_pagos",
        "uuid_registro_afectado": original_uuid,
        "datos_nuevos": {
            "compensacion_para": str(original_uuid) if original_uuid is not None else None,
        },
        "timestamp_evento": now,
    }

    await append_only.append_event(
        ctx.session,
        LogTransaccional,
        compensation_attrs,
        actor_uuid=ctx.actor_uuid,
        chain_hash=True,
    )

    return HookResult(proceed=True)


registry.register("bi_temporal_compensation", bi_temporal_compensation)

__all__ = ["bi_temporal_compensation"]
