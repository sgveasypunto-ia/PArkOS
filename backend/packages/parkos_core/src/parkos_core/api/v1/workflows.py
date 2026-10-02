"""Operations HTTP routes — workflows (PR6, T-PR6-10, REQ-21, REQ-22, REQ-23).

4 branch-originated ``[L-W]`` workflow tables mounted via
:func:`make_router`:

- ``reimpresion-ticket`` — ``[L-W]`` ticket-reprint chain (operator
  write, admin read). Available as soon as the invoice is emitted at the
  branch — never gated on a cloud round-trip (D1-rev).
- ``anulaciones`` — ``[L-W]`` annulment chain against ``ingreso`` or
  ``salida`` (polymorphic FK, REQ-22). Terminal states: ``ejecutada`` /
  ``rechazada``.
- ``reclamos`` — ``[L-W]`` claim against ``ingreso`` / ``salida`` /
  ``factura`` (polymorphic FK, REQ-OP-08, REQ-23-W-POLYMORPHIC-FK).
  The fast-fail discriminator is enforced at the Pydantic layer
  (:class:`ReclamosCreate`); the DB-existence check via
  :func:`repo.workflow.polymorphic_row_exists` runs from a future
  custom endpoint (PR7).
``alerta`` is NOT mounted here (HU-F19.5): it shares the same ``[L-W]``
shape as the 3 resources above, but its ``GET /workflows/alerta`` list
needs a ``LEFT JOIN prod.alert_types`` (``severity``, BR4 null-safe) plus
``uuid_sucursal``/``tipo_alerta``/``estado``/``severidad``/``desde``/
``hasta`` filters and admin cross-branch resolution via
``extract_sucursales_permitidas_fresh`` (HU-F19.1 pattern) -- none of
which :func:`make_router` supports (no per-resource query-extension
hook; its ``list_endpoint`` is single-branch-or-global via
``get_tenant_ctx``, the wrong dependency for a cross-branch admin list --
see ``auth.tenancy.BranchScope``'s own docstring on that gap). Mounting
``alerta`` here and bolting the extra filters on afterward would require
changing the SHARED ``make_router``/``list_endpoint`` body that
``reimpresion-ticket``/``anulaciones``/``reclamos`` also depend on.
``api/v1/workflows_alerta.py`` (already home to the ``descartar``
transition endpoint, HU-F19.4) owns ALL THREE of ``alerta``'s GET routes
instead -- list (extended), single (``current_version``), and history --
under its own ``APIRouter(prefix="/workflows/alerta")``, so the
``/workflows/alerta`` URL surface is unchanged for clients even though
the mount moved.

Cloud-only ``[L-W]`` (``envio-dian``, ``validacion-evento``) live ONLY
in :mod:`parkos_core.dian.cloud_router` (T-PR6-09, REQ-X3). This module
MUST NOT mount them.

READ-ONLY mounts (PR6):

Same rationale as :mod:`parkos_core.api.v1.facturacion` — these tables
are ``[L-W]`` with their own write helpers
(:func:`repo.workflow.append_transition`) that the generic factory's
``"versioned"`` branch does not call. Custom transition endpoints ship
in PR7. PR6 only exposes reads so the operations console can browse
chains, including the chain-tip
(:func:`repo.workflow.read_chain_tip`) that the admin UI consumes.

The standard :func:`make_router` reads obey the cursor-paginated list
contract (REQ-OP-01) and the per-resource issuer + permission guard
(REQ-OP-13).

NO DELETE endpoint — defense in depth (design §3, AGENTS.md §3).
"""
from __future__ import annotations

from fastapi import APIRouter

from ...models.L_W.anulaciones import Anulaciones
from ...models.L_W.reclamos import Reclamos
from ...models.L_W.reimpresion_ticket import ReimpresionTicket
from ...schemas.workflows import (
    AnulacionesCreate,
    AnulacionesRead,
    AnulacionesReadList,
    AnulacionesUpdate,
    ReclamosCreate,
    ReclamosRead,
    ReclamosReadList,
    ReclamosUpdate,
    ReimpresionTicketCreate,
    ReimpresionTicketRead,
    ReimpresionTicketReadList,
    ReimpresionTicketUpdate,
)
from ..router_factory import make_router

router = APIRouter(prefix="/workflows", tags=["workflows"])

# Issuer-permission defaults per resource (T-PR6-10). ``alerta`` is
# deliberately absent -- see module docstring (HU-F19.5: its reads live
# in ``workflows_alerta.py``, not this factory mount).
_ROUTER_CONFIG = {
    "reimpresion-ticket": ("operador-,admin-", "reimprimir_ticket"),
    "anulaciones": ("operador-,admin-", "anular_ingreso_salida"),
    "reclamos": ("operador-,admin-", "registrar_reclamo"),
}


def _mount_workflow(
    *,
    resource: str,
    model_cls: type,
    read_schema: type,
    read_list_schema: type,
    create_schema: type,
    update_schema: type,
) -> None:
    """Mount one workflow C+Q+U router under ``/workflows/{resource}``.

    ``write_enabled=False`` per PR6 rationale (see module docstring).
    """
    issuer, perm = _ROUTER_CONFIG[resource]
    router.include_router(
        make_router(
            resource=resource,
            model_cls=model_cls,
            read_schema=read_schema,
            read_list_schema=read_list_schema,
            create_schema=create_schema,
            update_schema=update_schema,
            repo_kind="versioned",
            issuer_required=issuer,
            permission_required=perm,
            write_enabled=False,
        )
    )


_mount_workflow(
    resource="reimpresion-ticket",
    model_cls=ReimpresionTicket,
    read_schema=ReimpresionTicketRead,
    read_list_schema=ReimpresionTicketReadList,
    create_schema=ReimpresionTicketCreate,
    update_schema=ReimpresionTicketUpdate,
)
_mount_workflow(
    resource="anulaciones",
    model_cls=Anulaciones,
    read_schema=AnulacionesRead,
    read_list_schema=AnulacionesReadList,
    create_schema=AnulacionesCreate,
    update_schema=AnulacionesUpdate,
)
_mount_workflow(
    resource="reclamos",
    model_cls=Reclamos,
    read_schema=ReclamosRead,
    read_list_schema=ReclamosReadList,
    create_schema=ReclamosCreate,
    update_schema=ReclamosUpdate,
)
# alerta: NOT mounted here (HU-F19.5) -- see module docstring.
# ``workflows_alerta.router`` carries its full GET surface
# (list/single/history) plus the HU-F19.4 ``descartar`` POST.


__all__ = ["router"]
