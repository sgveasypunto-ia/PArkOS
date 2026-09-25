"""Operations HTTP routes — caja + arqueo (PR7, REQ-10-A-INSERCION).

``caja`` and ``arqueo`` are ``[A]`` (append-only) tables — NO UPDATE/DELETE
via the router. Write endpoints land in a follow-up PR that calls
``repo.append_only.append_event``.
"""
from __future__ import annotations

from fastapi import APIRouter

from ...models.A.arqueo import Arqueo
from ...models.A.caja import Caja
from ...schemas.caja import (
    ArqueoCreate,
    ArqueoRead,
    ArqueoReadList,
    ArqueoUpdate,
    CajaCreate,
    CajaRead,
    CajaReadList,
    CajaUpdate,
)
from ..router_factory import make_router

router = APIRouter(prefix="/caja", tags=["caja"])


def _mount_caja(
    *,
    resource: str,
    model_cls: type,
    read_schema: type,
    read_list_schema: type,
    create_schema: type,
    update_schema: type,
) -> None:
    """Mount one caja C+Q+U router under ``/caja/{resource}``.

    ``write_enabled=False`` per PR7 rationale (above). Corrections on
    ``[A]`` tables are expressed as compensating rows via the
    ``repo.append_only.append_event`` helper (REQ-10-A-INSERCION).
    """
    router.include_router(
        make_router(
            resource=resource,
            model_cls=model_cls,
            read_schema=read_schema,
            read_list_schema=read_list_schema,
            create_schema=create_schema,
            update_schema=update_schema,
            repo_kind="versioned",
            issuer_required="operador-,admin-",
            permission_required="realizar_arqueo",  # GAP-BE-05 -- was emitir_factura
            write_enabled=False,  # PR7 is read-only; writes via custom endpoints (PR11)
        )
    )


_mount_caja(
    resource="caja",
    model_cls=Caja,
    read_schema=CajaRead,
    read_list_schema=CajaReadList,
    create_schema=CajaCreate,
    update_schema=CajaUpdate,
)


# ---------------------------------------------------------------------------
# HU-F1.13 / DEC-ARQUEO-05: dedicated router mount for the atomic
# ``POST /api/v1/caja/arqueo`` + ``GET /api/v1/caja/arqueo/resumen`` pair.
# The factory mount below stays read-only; the dedicated router carries
# the cross-table atomic write (1 [A] Arqueo + N [L-S] sesion + 1 [L-W]
# alerta + N+1 log_transaccional in a single commit -- KD-ARQUEO-01).
#
# BUGFIX (2026-09-25, reproducido en vivo con un fetch autenticado real):
# este ``include_router`` DEBE quedar registrado ANTES que
# ``_mount_caja(resource="arqueo", ...)`` de abajo. Starlette matchea
# rutas en orden de registro; el mount factory genérico registra
# ``GET /caja/arqueo/{uuid}`` (read-by-id, C+Q read-only), y con el
# orden viejo (factory primero) ese ``{uuid}`` capturaba CUALQUIER
# segundo segmento bajo ``/caja/arqueo/...`` -- incluida la ruta
# literal ``/caja/arqueo/resumen`` de este router (T4, más abajo).
# Pydantic rechazaba "resumen" como UUID inválido -> 422 permanente,
# el endpoint de resumen de arqueo (consumido por `useArqueoResumen` /
# `useArqueoResumenPorSesion` en el front, y por el propio cierre de
# turno para calcular lo esperado) nunca fue alcanzable. Registrar
# este router primero hace que la ruta literal ``/arqueo/resumen`` se
# resuelva antes de que el ``{uuid}`` genérico tenga chance de
# matchear.
# ---------------------------------------------------------------------------
from .caja_arqueo import router as caja_arqueo_router

router.include_router(caja_arqueo_router)

_mount_caja(
    resource="arqueo",
    model_cls=Arqueo,
    read_schema=ArqueoRead,
    read_list_schema=ArqueoReadList,
    create_schema=ArqueoCreate,
    update_schema=ArqueoUpdate,
)


# NOTE (fix 2026-09-24, bug reproducido en vivo): ``sync_estado`` NO se monta
# aquí. Este router declara ``prefix="/caja"`` (línea 25); anidar
# ``sync_estado.router`` (que declara su propio ``prefix="/sync"``) adentro
# de este router concatenaba ambos prefijos y publicaba el endpoint en
# ``/api/v1/caja/sync/estado`` en vez de ``/api/v1/sync/estado`` (el path
# que documentan plan.md HU-F1.14, el frontend `useSyncEstado.ts`, y el
# propio docstring de `sync_estado.py`). El montaje correcto vive en
# ``api/v1/__init__.py::_build_router``, al mismo nivel que
# ``sync_router.router`` (que sí es responsable de ``/api/v1/sync/*``).


__all__ = ["router"]