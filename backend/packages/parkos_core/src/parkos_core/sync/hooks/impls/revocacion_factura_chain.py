"""hooks/impls/revocacion_factura_chain.py — ``RevocacionFacturaChain`` (T-PR6-003/004).

REQ-HOOK-009: ``hook_chain_extend`` bound to ``revocacion_factura``. A
DIAN-accepted revocation extends the SAME kind of per-``uuid_sucursal``
SHA-256 chain as ``log_transaccional`` (design.md §6) — same primitive
(:func:`repo.hash_chain.append`), same pattern as
:mod:`log_transaccional_chain`, mirrored for the second (and only other)
hash-chain carrier (REQ-CAT-009: exactly ONE catalog entry for
``revocacion_factura`` — D6-rev — is what keeps this a single chain per
``(tabla, uuid_sucursal)`` rather than the superseded dual-catalog design's
guaranteed interleaved-chain hazard).

**Replaces the manual dispatcher call (T-PR6-005).** Before PR6,
``dian/cloud/dispatcher.py::_finalize_revocacion`` called
``repo.hash_chain.append`` directly, hardcoding the model class and bypassing
the catalog entirely. It now looks up ``revocacion_factura``'s catalog spec
and invokes ITS ``hook_chain_extend`` slot (this function) — the extension
logic itself is unchanged, but it is now reached via the catalog's hook
contract instead of a private, unregistered call site, so the DIAN
dispatcher and any future caller share the exact same, single, tested
implementation.
"""
from __future__ import annotations

from .. import registry
from ..base import HookContext, HookResult


async def revocacion_factura_chain(ctx: HookContext) -> HookResult:
    """``hook_chain_extend`` — REQ-HOOK-009 chain extension for ``revocacion_factura``."""
    from ....models.A.revocacion_factura import RevocacionFactura
    from ....repo import hash_chain

    new_row = await hash_chain.append(
        ctx.session,
        RevocacionFactura,
        ctx.payload,
        actor_uuid=ctx.actor_uuid,
    )

    return HookResult(
        proceed=True,
        chain_extension=(
            new_row.hash_anterior.encode("ascii"),
            new_row.hash_actual.encode("ascii"),
        ),
    )


registry.register("revocacion_factura_chain", revocacion_factura_chain)

__all__ = ["revocacion_factura_chain"]
