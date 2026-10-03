"""Empresa + Sucursal + per-branch config HTTP routes (PR4).

REQ-OP-05 (1MB cap on documentos.b64), REQ-OP-12 (config override), REQ-X3
(DIAN boundary on resolucion_facturacion). All routers are bi-temporal
``repo_kind="versioned"`` (close+insert writes via ``repo.versioned.close_and_insert``).

NO DELETE endpoint — defense in depth (design §3, AGENTS.md §3).

T-PR4-11 extends this module with ``_SUB_ROUTERS``: a dict that maps each
resource slug to its APIRouter. The v1 package (``api/v1/__init__.py``) reads
``_SUB_ROUTERS`` and applies the DIAN boundary (REQ-X3) at router-aggregation
time — branch deploy skips cloud-only resources so they are physically absent
from ``api_sucursal/openapi.json``. The aggregated ``router`` is preserved for
direct imports (backward compat) and to keep the path layout
``/api/v1/empresa/{resource}/...`` intact for cloud.

HU-F1.4: a dedicated ``GET /tarifas-sucursal`` handler is registered BELOW
(``_mount_empresa`` is called for the same resource AFTER this dedicated
route is declared, so FastAPI's order-of-registration resolver picks the
dedicated handler for the bare ``GET`` list path and lets the factory
still own POST / PUT / GET-by-uuid / GET-history on the same resource).
The dedicated handler adds the optional ``vigente_en`` query param and
applies the canonical bi-temporal predicate
``vigente_desde <= :v AND (vigente_hasta IS NULL OR vigente_hasta > :v)
AND estado = 'activo'``. The factory (HU-F1.1) remains untouched.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.permissions import require_permission


def _to_naive_utc(value: datetime | None) -> datetime | None:
    """Normalize a (possibly tz-aware) datetime to naive UTC.

    Pydantic v2 ``datetime | None`` keeps ``tzinfo`` on the parsed value
    when the wire payload carries an offset (e.g. ``2026-12-31T01:00:00+00:00``
    from the admin ``<CupoForm>`` ``datetimeLocalToIso`` helper). All
    ``[V]`` ``vigente_desde`` columns in this project are
    ``DateTime(timezone=False)`` and asyncpg refuses to bind an aware
    datetime into a tz-naive column for the overlap guard SQL
    (``can't subtract offset-naive and offset-aware datetimes``,
    DataError 500). Centralizing here means both POST/PUT of cupos AND
    tarifas normalize the same way at the handler boundary, before any
    SQL parameter binding or ``close_and_insert`` payload build.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
from ...auth.tenancy import TenantContext, get_tenant_ctx, requires_sucursal
from ...db.tenancy import (
    extract_sucursales_permitidas,
    extract_sucursales_permitidas_fresh,
)
from ...models.V.cantidad_vehiculos_sucursal import CantidadVehiculosSucursal
from ...models.V.documentos import Documentos
from ...models.V.empresa import Empresa
from ...models.V.resolucion_facturacion import ResolucionFacturacion
from ...models.V.sucursal import Sucursal
from ...models.V.tarifas_sucursal import TarifasSucursal
from ...repo.ocupacion import get_ocupacion_puros_activos
from ...repo.overlap import (
    OverlapError,
    SucursalInmutableError,
    _Key,
    assert_no_overlap,
    assert_sucursal_inmutable,
)
from ...repo.tarifas_vigencia import bitemporal_vigente_predicate, list_tarifas_vigentes
from ...repo.versioned import close_and_insert, close_only, current_version
from ...schemas.empresa import (
    CantidadVehiculosSucursalCreate,
    CantidadVehiculosSucursalRead,
    CantidadVehiculosSucursalReadList,
    CantidadVehiculosSucursalUpdate,
    DocumentosCreate,
    DocumentosRead,
    DocumentosReadList,
    DocumentosUpdate,
    EmpresaCreate,
    EmpresaRead,
    EmpresaReadList,
    EmpresaUpdate,
    ResolucionFacturacionConsecutivoActual,
    ResolucionFacturacionCreate,
    ResolucionFacturacionRead,
    ResolucionFacturacionReadList,
    ResolucionFacturacionUpdate,
    SucursalCreate,
    SucursalRead,
    SucursalReadList,
    SucursalUpdate,
    TarifasSucursalCreate,
    TarifasSucursalFilter,
    TarifasSucursalRead,
    TarifasSucursalReadList,
    TarifasSucursalUpdate,
)
from ..deps import get_session, requires_issuer
from ..router_factory import _order_key, _parse_cursor_timestamp, make_router

router = APIRouter(prefix="/empresa", tags=["empresa"])

# Issuer-permission defaults per resource (see T-PR4-03 table).
# Cloud-only resource (DIAN root) gets strict admin- issuer.
_ROUTER_CONFIG = {
    "empresa": ("admin-,operador-", "config_empresa"),
    "sucursal": ("admin-,operador-", "config_sucursal"),
    "documentos": ("admin-,operador-", "admin_documentos"),
    "resolucion-facturacion": ("admin-", "admin_resolucion_facturacion"),
    "tarifas-sucursal": ("admin-,operador-", "config_tarifas"),
    "cantidad-vehiculos-sucursal": ("admin-,operador-", "config_cupos"),
}

# Per-resource sub-routers exposed for the v1 package's selective mounting
# (T-PR4-11, REQ-X3). Keys are the resource slugs from ``_ROUTER_CONFIG``;
# values are the APIRouters returned by ``make_router``. Populated below by
# ``_mount_empresa``.
_SUB_ROUTERS: dict[str, APIRouter] = {}


# ---------------------------------------------------------------------------
# fix/catalog-sucursal-global-reads — ``GET /empresa/sucursal`` tenant-free
# ---------------------------------------------------------------------------
#
# ``prod.sucursal`` is the BRANCH DIRECTORY: it carries ``uuid_sucursal``
# (every row IS a branch), but the table itself is conceptually global —
# admin-issued pairing tokens and the BranchSelector both need the list
# before any branch is selected. The factory sub-router at
# ``/empresa/sucursal`` injects ``get_tenant_ctx`` and therefore requires
# ``X-Sucursal-Context`` for ``admin-`` tokens — which broke the
# ``<SeleccionarSucursal>`` tab "Administrar" and the admin user-management
# assignee dropdown (``features/admin/components/AdminUsuarioSucursalesManager.tsx:8``
# and the related ``useSWR('/api/v1/empresa/sucursal?limit=200')`` calls in
# cupos / tarifas / configuracion-* pages — all reachable before branch
# selection).
#
# Carve-out: register a dedicated sub-router for the 3 read endpoints
# (list, by-uuid, history) WITHOUT ``get_tenant_ctx``, BEFORE the factory
# mount for the same resource. POST/PUT remain on the factory sub-router
# (writes stay tenant-scoped — defence in depth).
#
# What the carve-out does NOT do: drop authorization. Only the HEADER
# requirement goes away; the result set is still bounded to the caller's
# own branches by :func:`_permitted_sucursal_uuids`. "Global" here means
# "does not need a branch selected", never "sees every branch".
#
# Mirrors the HU-F1.4 dedicated-tarifas pattern: a separate APIRouter
# registered ahead of the factory sub-router so FastAPI's first-match
# resolver picks the dedicated handler for the read paths.
_sucursal_global_reads_issuer_dep = requires_issuer("admin-", "operador-")
_sucursal_global_reads_router = APIRouter(prefix="/sucursal", tags=["sucursal"])


async def _permitted_sucursal_uuids(
    session: AsyncSession,
    claims: Any,
) -> list[uuid_lib.UUID]:
    """Resolve which branches the caller may read in the directory.

    Dropping ``get_tenant_ctx`` from these handlers removes the HEADER
    requirement, NOT the authorization requirement. The directory still
    has to be bounded to the caller's own branches, otherwise any
    ``admin-`` token could enumerate every branch in the installation
    (name, NIT, address) — a cross-tenant leak. ``AGENTS.md`` lists
    "Tenant scope leak in admin JWT" as a HIGH risk whose mitigation is
    enforcing ``sucursales_permitidas`` on every call.

    - ``admin-`` → read ``prod.usuarios_sucursal`` FRESH, mirroring
      :func:`~parkos_core.api.v1.admin_views.list_sucursales`. The JWT
      claim is a login-time snapshot, so a branch created since login
      would be invisible in the picker and a revoked assignment would
      linger until the token expires.
    - ``operador-`` → the claim list, which the login handler pins to the
      operator's own single branch. A ``usuarios_sucursal`` read would
      fail closed for an operator with no admin assignment rows.

    An empty result means the caller sees nothing (fail closed, per
    ``db.tenancy.apply_admin_scope``).
    """
    if str(claims.get("iss", "")).startswith("admin-"):
        return await extract_sucursales_permitidas_fresh(
            session, actor_uuid=uuid_lib.UUID(str(claims["sub"]))
        )
    return extract_sucursales_permitidas(claims)


@_sucursal_global_reads_router.get("", response_model=SucursalReadList)
async def list_sucursal_global(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _claims: None = Depends(_sucursal_global_reads_issuer_dep),
) -> SucursalReadList:
    """Header-free directory of branches, bounded to the caller's scope.

    Reads no longer require ``X-Sucursal-Context`` (the FE branch picker
    and the assignee dropdowns run before any branch is selected), but the
    result set is still restricted to the caller's permitted branches via
    :func:`_permitted_sucursal_uuids`. Cursor pagination + limit mirror the
    factory contract so the FE ``useSWR('/api/v1/empresa/sucursal?limit=200')``
    callers (``SeleccionarSucursal``, ``Cupos``, ``Tarifas``,
    ``ConfiguracionTolerancias``, ``AdminUsuarioSucursalesManager``)
    can paginate as if it were the factory endpoint.
    """
    from ...repo.pagination import (
        Cursor as _Cursor,
    )
    from ...repo.pagination import (
        InvalidCursorError,
    )
    from ...repo.pagination import (
        decode as _cursor_decode,
    )
    from ...repo.pagination import (
        encode as _cursor_encode,
    )

    permitidas = await _permitted_sucursal_uuids(session, _claims)
    if not permitidas:
        # Fail closed: a caller with no permitted branch sees nothing.
        return SucursalReadList(items=[], next_cursor=None)

    try:
        decoded = _cursor_decode(cursor) if cursor else None
    except InvalidCursorError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_cursor", "detail": str(e)},
        )
    stmt = (
        select(Sucursal)
        .where(
            Sucursal.vigente_hasta.is_(None),
            Sucursal.uuid.in_(permitidas),
        )
        .order_by(Sucursal.vigente_desde.desc(), Sucursal.uuid.asc())
    )
    if decoded is not None:
        cursor_ts = datetime.fromisoformat(decoded.vigente_desde)
        if cursor_ts.tzinfo is not None:
            cursor_ts = cursor_ts.replace(tzinfo=None)
        stmt = stmt.where(
            (Sucursal.vigente_desde < cursor_ts)
            | (
                (Sucursal.vigente_desde == cursor_ts)
                & (Sucursal.uuid > uuid_lib.UUID(decoded.uuid))
            )
        )
    stmt = stmt.limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _cursor_encode(
            _Cursor(
                vigente_desde=last.vigente_desde.isoformat(),
                created_at=None,
                uuid=str(last.uuid),
            )
        )
    items = [SucursalRead.model_validate(r) for r in rows]
    return SucursalReadList(items=items, next_cursor=next_cursor)


@_sucursal_global_reads_router.get(
    "/{uuid}",
    response_model=SucursalRead,
    responses={404: {"description": "sucursal_no_encontrada"}},
)
async def get_sucursal_global(
    uuid: uuid_lib.UUID = Path(...),
    session: AsyncSession = Depends(get_session),
    _claims: None = Depends(_sucursal_global_reads_issuer_dep),
) -> SucursalRead:
    """Header-free read of a single branch by uuid (vigente version)."""
    permitidas = await _permitted_sucursal_uuids(session, _claims)
    if uuid not in permitidas:
        # 404, not 403: a non-permitted branch must be indistinguishable
        # from one that does not exist.
        raise HTTPException(
            status_code=404,
            detail={"error": "sucursal_no_encontrada", "uuid": str(uuid)},
        )
    row = await current_version(session, Sucursal, uuid)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "sucursal_no_encontrada", "uuid": str(uuid)},
        )
    return SucursalRead.model_validate(row)


@_sucursal_global_reads_router.get(
    "/{uuid}/history",
    response_model=list[SucursalRead],
    responses={404: {"description": "sucursal_no_encontrada"}},
)
async def get_sucursal_history_global(
    uuid: uuid_lib.UUID = Path(...),
    session: AsyncSession = Depends(get_session),
    _claims: None = Depends(_sucursal_global_reads_issuer_dep),
) -> list[SucursalRead]:
    """Header-free bi-temporal history of a branch (all versions)."""
    permitidas = await _permitted_sucursal_uuids(session, _claims)
    if uuid not in permitidas:
        raise HTTPException(
            status_code=404,
            detail={"error": "sucursal_no_encontrada", "uuid": str(uuid)},
        )
    stmt = (
        select(Sucursal)
        .where(Sucursal.uuid == uuid)
        .order_by(Sucursal.vigente_desde.desc())
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return [SucursalRead.model_validate(r) for r in rows]


# Register the dedicated reads on the aggregated ``router`` (backward-compat
# direct imports) AND in ``_SUB_ROUTERS`` so the v1 package picks them up.
# Both insertions happen BEFORE the factory mount for ``sucursal`` below so
# FastAPI's first-match resolver picks the dedicated handlers.
router.include_router(_sucursal_global_reads_router)
_SUB_ROUTERS["sucursal__dedicated_global_reads"] = _sucursal_global_reads_router


def _mount_empresa(
    *,
    resource: str,
    model_cls: type,
    read_schema: type,
    read_list_schema: type,
    create_schema: type,
    update_schema: type,
) -> APIRouter:
    """Build, stash, and mount one empresa C+Q+U router.

    The returned sub-router is:

    1. Stored in ``_SUB_ROUTERS[resource]`` so the v1 package can include
       individual resources selectively (DIAN boundary).
    2. Mounted on the aggregated ``router`` for backward-compat direct
       imports.
    """
    issuer, perm = _ROUTER_CONFIG[resource]
    sub = make_router(
        resource=resource,
        model_cls=model_cls,
        read_schema=read_schema,
        read_list_schema=read_list_schema,
        create_schema=create_schema,
        update_schema=update_schema,
        repo_kind="versioned",
        issuer_required=issuer,
        permission_required=perm,
    )
    _SUB_ROUTERS[resource] = sub
    router.include_router(sub)
    return sub


_mount_empresa(
    resource="empresa",
    model_cls=Empresa,
    read_schema=EmpresaRead,
    read_list_schema=EmpresaReadList,
    create_schema=EmpresaCreate,
    update_schema=EmpresaUpdate,
)

# ---------------------------------------------------------------------------
# Duplicate-prefix guard on ``sucursal`` POST/PUT (business key ``prefijo_nombre``)
# ---------------------------------------------------------------------------
#
# ``models/V/sucursal.py`` documents ``prefijo_nombre`` as "(UK)" but the
# only real ``UniqueConstraint`` is composite with ``vigente_desde``
# (``sucursal_uk01``), which in practice never fires between two distinct
# branches created at different instants. Confirmed live via QA (batch
# `qa/batch-sucursales`, 2026-10-02): creating a second branch with an
# already-vigente ``prefijo_nombre`` succeeds silently, no error client or
# server side. Same shadow-the-factory pattern as
# ``catalogos.py::_assert_no_vigente_duplicate`` / the tipo-persona /
# tipo-tarifa dedicated routers — GET stays on the factory / the
# tenant-free global-reads router above; POST/PUT are shadowed. UNLIKE
# ``catalogos.router`` (mounted directly by ``api/v1/__init__.py``),
# ``empresa.router``'s own include-order here has NO effect on the real
# app: the v1 aggregator rebuilds from ``_SUB_ROUTERS`` only
# (``_build_empresa_router()``). The actual precedence is set further
# down this file, where this router is registered into ``_SUB_ROUTERS``
# under a synthetic key placed before the bare ``"sucursal"`` factory key
# in the reorder block (same convention as the tarifas/cantidad/
# resolucion-facturacion dedicated routers).
_sucursal_dedicated_router = APIRouter(prefix="/sucursal", tags=["sucursal"])
_sucursal_dedicated_issuer, _sucursal_dedicated_perm = _ROUTER_CONFIG["sucursal"]
_sucursal_dedicated_issuer_dep = requires_issuer(
    *(s.strip() for s in _sucursal_dedicated_issuer.split(","))
)
_sucursal_dedicated_perm_dep = require_permission(_sucursal_dedicated_perm)


async def _assert_no_sucursal_prefijo_duplicado(
    session: AsyncSession,
    *,
    prefijo_nombre: str | None,
    exclude_uuid: uuid_lib.UUID | None = None,
) -> None:
    """Reject a write that would leave two vigente sucursales with the
    same ``prefijo_nombre``. ``None``/blank prefixes are already rejected
    client-side (``sucursalSchema.ts`` requires it) and schema-side
    (``SucursalCreate``/``Update``), so this is a defense-in-depth no-op
    for that case rather than a false-positive duplicate.
    """
    if not prefijo_nombre:
        return
    stmt = select(func.count()).select_from(Sucursal).where(
        Sucursal.vigente_hasta.is_(None),
        Sucursal.prefijo_nombre == prefijo_nombre,
    )
    if exclude_uuid is not None:
        stmt = stmt.where(Sucursal.uuid != exclude_uuid)
    result = await session.execute(stmt)
    if int(result.scalar_one()) > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "sucursal_prefijo_duplicado",
                "field": "prefijo_nombre",
                "value": prefijo_nombre,
            },
        )


@_sucursal_dedicated_router.post(
    "",
    response_model=SucursalRead,
    status_code=201,
    dependencies=[Depends(_sucursal_dedicated_perm_dep)],
)
async def create_sucursal_dedicated(
    payload: SucursalCreate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_sucursal_dedicated_issuer_dep),
) -> SucursalRead:
    """Shadow the factory's POST to enforce the ``prefijo_nombre`` guard.

    Mirrors ``make_router``'s ``create_endpoint`` (close+insert via
    ``repo.versioned.close_and_insert`` + commit + refresh + read-back,
    including the creator-assignment hook that fires for ``sucursal``).
    """
    await _assert_no_sucursal_prefijo_duplicado(
        session, prefijo_nombre=payload.prefijo_nombre
    )
    payload_dict = payload.model_dump(exclude_none=True)
    new_row = await close_and_insert(
        session,
        Sucursal,
        current_uuid=None,
        new_attrs=payload_dict,
        actor_uuid=ctx.actor_uuid,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return SucursalRead.model_validate(new_row)


@_sucursal_dedicated_router.put(
    "/{uuid}",
    response_model=SucursalRead,
    dependencies=[Depends(_sucursal_dedicated_perm_dep)],
)
async def update_sucursal_dedicated(
    payload: SucursalUpdate,
    uuid: uuid_lib.UUID = Path(...),
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_sucursal_dedicated_issuer_dep),
) -> SucursalRead:
    """Shadow the factory's PUT to enforce the ``prefijo_nombre`` guard."""
    await _assert_no_sucursal_prefijo_duplicado(
        session, prefijo_nombre=payload.prefijo_nombre, exclude_uuid=uuid
    )
    payload_dict = payload.model_dump(exclude_none=True)
    new_row = await close_and_insert(
        session,
        Sucursal,
        current_uuid=uuid,
        new_attrs=payload_dict,
        actor_uuid=ctx.actor_uuid,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return SucursalRead.model_validate(new_row)


router.include_router(_sucursal_dedicated_router)

_mount_empresa(
    resource="sucursal",
    model_cls=Sucursal,
    read_schema=SucursalRead,
    read_list_schema=SucursalReadList,
    create_schema=SucursalCreate,
    update_schema=SucursalUpdate,
)
_mount_empresa(
    resource="documentos",
    model_cls=Documentos,
    read_schema=DocumentosRead,
    read_list_schema=DocumentosReadList,
    create_schema=DocumentosCreate,
    update_schema=DocumentosUpdate,
)
_mount_empresa(
    resource="resolucion-facturacion",
    model_cls=ResolucionFacturacion,
    read_schema=ResolucionFacturacionRead,
    read_list_schema=ResolucionFacturacionReadList,
    create_schema=ResolucionFacturacionCreate,
    update_schema=ResolucionFacturacionUpdate,
)


# HU-F1.4 — dedicated handler for ``GET /empresa/tarifas-sucursal``.
# The dedicated handler is registered on its OWN sub-router (same prefix
# as the factory) and that sub-router is ``include_router``'d BEFORE the
# factory sub-router, so FastAPI's order-of-registration resolver picks
# THIS handler over the factory's ``list_endpoint`` for the bare ``GET``
# list path on this resource. POST / PUT / GET-by-uuid / GET-history
# still flow through the factory (KD-4 of the design). The dedicated
# handler delegates the SELECT to
# ``repo.tarifas_vigencia.list_tarifas_vigentes`` so the predicate, tz
# normalization, cursor and order are shared with the unit tests
# (REQ-OPS-019..020).

_tarifas_issuer_dep = requires_issuer("admin-", "operador-")


_tarifas_dedicated_router = APIRouter(prefix="/tarifas-sucursal", tags=["tarifas-sucursal"])


@_tarifas_dedicated_router.get(
    "",
    response_model=TarifasSucursalReadList,
)
async def list_tarifas_sucursal_vigente_en(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    vigente_en: datetime | None = Query(
        None,
        description=(
            "Punto en el tiempo para el predicado de vigencia. "
            "Acepta ISO-8601 con o sin tz (naive = UTC). "
            "Default: datetime.now(UTC)."
        ),
    ),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(requires_sucursal),
    _claims: None = Depends(_tarifas_issuer_dep),
) -> TarifasSucursalReadList:
    """HU-F1.4 — bi-temporal ``GET /empresa/tarifas-sucursal``.

    Same response shape as the factory's list endpoint
    (``{items: [...], next_cursor: str | None}``). ``vigente_en`` is
    evaluated per-request to ``datetime.now(UTC)`` when omitted (KD-3).
    """
    v = vigente_en if vigente_en is not None else datetime.now(UTC)
    rows, nxt = await list_tarifas_vigentes(
        session,
        vigente_en=v,
        filter=TarifasSucursalFilter(vigente_en=v),
        cursor=cursor,
        limit=limit,
    )
    items = [TarifasSucursalRead.model_validate(r) for r in rows]
    return TarifasSucursalReadList(items=items, next_cursor=nxt)


@_tarifas_dedicated_router.get(
    "/{uuid}",
    response_model=TarifasSucursalRead,
    responses={404: {"description": "tarifa_no_encontrada"}},
)
async def get_tarifa_sucursal_by_uuid(
    uuid: uuid_lib.UUID = Path(
        ...,
        description="UUIDv4 de la fila de prod.tarifas_sucursal a leer.",
    ),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(requires_sucursal),
    _claims: None = Depends(_tarifas_issuer_dep),
) -> TarifasSucursalRead:
    """HU-F1.4 / CU-02 (operador, 2026-09-22): detalle de una tarifa específica.

    El handler de listado (``list_tarifas_sucursal_vigente_en`` arriba)
    devuelve un ``TarifasSucursalReadList`` paginado para alimentar el
    hook FE ``useTarifasVigentes``. El cotizador de salida
    (``GET /operacion/cotizar``) retorna ``tarifa_uuid`` (el UUID de la
    fila aplicada) sin el detalle — el UI solo podía mostrar el UUID
    crudo. Este endpoint complementa: el FE hace un lookup
    ``getTarifaSucursalByUuid(uuid)`` para mostrar ``valor``,
    ``valor_plena``, ``vigente_desde/hasta`` y ``estado`` en el panel
    de cotizacion.

    Read-only por contrato (KD-4): sin UPDATE/DELETE, sin commit. La
    fila es ``[V]`` bi-temporal; el factory router conserva la cadena
    versionada (close+insert en escritura). El query directo via
    ``session.execute`` es read-only y consistente con la invariante
    del feature.

    Tenant scope: el handler valida via ``_tarifas_dedicated_router_
    issuer_dep`` (``admin-,operador-``) + KD-3 ``get_tenant_ctx``. El
    operador- está pinned a su sucursal, pero este endpoint NO filtra
    por ``uuid_sucursal`` porque la tarifa aplicada al cobro ya fue
    validada upstream por ``prod.calcular_cotizacion`` (FOR SHARE
    sobre la fila correcta) — el uuid que viene del cotizar es
    autoritativo. Permitir lectura cross-branch sería un leak; el cotizar
    con KD-3 ya previene eso (operador no puede cobrar en otra
    sucursal).

    404 si la fila no existe (uuid mal tipeado o fila cerrada). El FE
    muestra el UUID como fallback si 404.
    """
    row = (
        await session.execute(
            select(TarifasSucursal).where(TarifasSucursal.uuid == uuid)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "tarifa_no_encontrada", "uuid": str(uuid)},
        )
    return TarifasSucursalRead.model_validate(row)


router.include_router(_tarifas_dedicated_router)


# ---------------------------------------------------------------------------
# PR-C dedicated write routers (tarifas-sucursal + cantidad-vehiculos-sucursal)
# ---------------------------------------------------------------------------
#
# The factory ``make_router`` emits POST + PUT + GET by uuid + GET by
# uuid/history + GET list. PR-C adds three behaviours the factory does
# not cover, mounted on dedicated routers that take precedence over the
# factory's POST/PUT for the same path:
#
#   * overlap guard — the factory's POST/PUT would happily INSERT a row
#     whose ``vigente_desde`` falls inside an existing open window for
#     the same business key. UK01 prevents two rows with the SAME
#     ``vigente_desde`` but does NOT prevent a window that overlaps.
#     See ``repo.overlap.assert_no_overlap``.
#   * sucursal-inmutable guard — a PUT that changes ``uuid_sucursal``
#     silently moves the rate / capacity to a different branch and
#     invalidates every audit trail that referenced the original
#     branch. See ``repo.overlap.assert_sucursal_inmutable``.
#   * by-key / history endpoint — walks the bi-temporal version chain
#     by business identity (UK01 columns) instead of by uuid. The
#     factory's ``GET /{uuid}/history`` filters by uuid and misses the
#     close+insert fresh-UUID case. See the dedicated handler below.
#
# The factory's GET list / GET /{uuid} / GET /{uuid}/history are kept
# (registered after the dedicated router in ``_SUB_ROUTERS`` — see the
# reordering block below). The factory's POST/PUT are shadowed by the
# dedicated router for the same path; FastAPI matches the first
# registered route.


_tarifas_pr_c_perm_dep = require_permission("config_tarifas")
_cantidad_pr_c_perm_dep = require_permission("config_cupos")
_tarifas_pr_c_issuer_dep = requires_issuer("admin-", "operador-")
_cantidad_pr_c_issuer_dep = requires_issuer("admin-", "operador-")


_tarifas_pr_c_router = APIRouter(prefix="/tarifas-sucursal", tags=["tarifas-sucursal"])


@_tarifas_pr_c_router.post(
    "",
    response_model=TarifasSucursalRead,
    status_code=201,
    dependencies=[Depends(_tarifas_pr_c_perm_dep)],
)
async def create_tarifa_pr_c(
    payload: TarifasSucursalCreate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(requires_sucursal),
    _claims: None = Depends(_tarifas_pr_c_issuer_dep),
) -> TarifasSucursalRead:
    """PR-C POST: opens a new version with overlap guard.

    Rejects with 409 ``tarifa_overlap`` if the resulting window would
    intersect an existing open row for the same
    ``(uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa)`` business
    key. Adjacent windows (``new.vigente_desde == old.vigente_hasta``)
    are NOT overlaps — they are the close+insert Carril B contract.
    """
    payload_vigente_desde = _to_naive_utc(payload.vigente_desde)
    nueva_desde = payload_vigente_desde or datetime.now(UTC).replace(tzinfo=None)
    # POST opens at ``nueva_desde`` with no upper bound (open-ended).
    # We pass ``vigente_hasta = nueva_desde`` so the overlap test
    # collapses to "an open row whose vigente_desde < nueva_desde" —
    # any open row with vigente_desde == nueva_desde violates UK01
    # (DB enforces) and any open row strictly before nueva_desde is
    # by definition still active at nueva_desde (the open-ended row
    # never closes), so it overlaps the new open-ended window. The
    # second conjunct (``other.vigente_hasta > nueva_desde``) then
    # trivially passes because other.vigente_hasta is NULL (open).
    try:
        await assert_no_overlap(
            session,
            table="prod.tarifas_sucursal",
            resource="tarifas-sucursal",
            key=_Key(
                uuid_sucursal=payload.uuid_sucursal,
                uuid_tipo_vehiculo=payload.uuid_tipo_vehiculo,
                uuid_tipo_tarifa=payload.uuid_tipo_tarifa,
            ),
            nueva_vigente_desde=nueva_desde,
            nueva_vigente_hasta=nueva_desde,
            exclude_uuid=None,
        )
    except OverlapError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "tarifa_overlap",
                "conflicting_uuid": str(exc.conflicting_uuid),
                "conflicting_vigente_desde": exc.conflicting_vigente_desde.isoformat()
                if exc.conflicting_vigente_desde is not None
                else None,
                "conflicting_vigente_hasta": exc.conflicting_vigente_hasta.isoformat()
                if exc.conflicting_vigente_hasta is not None
                else None,
            },
        )
    payload_dict = payload.model_dump(exclude_none=True)
    if payload_vigente_desde is not None:
        payload_dict["vigente_desde"] = payload_vigente_desde
    new_row = await close_and_insert(
        session,
        TarifasSucursal,
        current_uuid=None,
        new_attrs=payload_dict,
        actor_uuid=ctx.actor_uuid,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return TarifasSucursalRead.model_validate(new_row)


@_tarifas_pr_c_router.put(
    "/{uuid}",
    response_model=TarifasSucursalRead,
    dependencies=[Depends(_tarifas_pr_c_perm_dep)],
)
async def update_tarifa_pr_c(
    payload: TarifasSucursalUpdate,
    uuid: uuid_lib.UUID = Path(...),
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(requires_sucursal),
    _claims: None = Depends(_tarifas_pr_c_issuer_dep),
) -> TarifasSucursalRead:
    """PR-C PUT: close+insert with overlap guard and sucursal-inmutable.

    Three rejections before the write:

    1. **sucursal_inmutable (422)** — payload's ``uuid_sucursal`` differs
       from the existing row. The tarifa belongs to the branch that
       created it; moving it across branches would invalidate audit
       trails. The operator must create a new version on the
       destination branch instead.
    2. **not_found (404)** — ``uuid`` does not match any active row.
    3. **tarifa_overlap (409)** — the resulting new window would
       intersect another open row. The current row is excluded from
       the overlap test (it is the row being closed; the helper takes
       ``exclude_uuid``).
    """
    current = await current_version(session, TarifasSucursal, uuid)
    if current is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "tarifa_no_encontrada", "uuid": str(uuid)},
        )
    try:
        assert_sucursal_inmutable(
            resource="tarifas-sucursal",
            uuid=uuid,
            existing_sucursal=current.uuid_sucursal,
            payload_sucursal=payload.uuid_sucursal,
        )
    except SucursalInmutableError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "sucursal_inmutable",
                "uuid": str(exc.uuid),
                "existing_sucursal": str(exc.existing_sucursal),
                "attempted_sucursal": str(exc.attempted_sucursal),
            },
        )
    nueva_desde = _to_naive_utc(payload.vigente_desde) or datetime.now(UTC).replace(tzinfo=None)
    # QA batch tarifas/cupos (2026-10-02): ``assert_no_overlap`` only
    # queries rows where ``vigente_hasta IS NULL`` (the single
    # currently-open row for this business key) and we pass
    # ``exclude_uuid=uuid`` below -- ``current`` IS that one open row,
    # so after excluding it there is NEVER an "other" open row left to
    # conflict with. The helper can therefore never catch a
    # backward-dated ``vigente_desde`` on PUT (confirmed live: a PUT
    # with ``vigente_desde`` inside an already-CLOSED historical window
    # returned 200, silently producing two overlapping bi-temporal
    # windows for the same key). The chain's windows are constructed
    # monotonically increasing, so comparing against the CURRENT row's
    # own ``vigente_desde`` is sufficient to block going back into any
    # prior window, open or closed -- no SQL round-trip needed.
    if nueva_desde < current.vigente_desde:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "tarifa_overlap",
                "conflicting_uuid": str(current.uuid),
                "conflicting_vigente_desde": current.vigente_desde.isoformat(),
                "conflicting_vigente_hasta": None,
            },
        )
    try:
        await assert_no_overlap(
            session,
            table="prod.tarifas_sucursal",
            resource="tarifas-sucursal",
            key=_Key(
                uuid_sucursal=current.uuid_sucursal,
                uuid_tipo_vehiculo=payload.uuid_tipo_vehiculo
                if payload.uuid_tipo_vehiculo is not None
                else current.uuid_tipo_vehiculo,
                uuid_tipo_tarifa=payload.uuid_tipo_tarifa
                if payload.uuid_tipo_tarifa is not None
                else current.uuid_tipo_tarifa,
            ),
            nueva_vigente_desde=nueva_desde,
            nueva_vigente_hasta=nueva_desde,
            exclude_uuid=uuid,
        )
    except OverlapError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "tarifa_overlap",
                "conflicting_uuid": str(exc.conflicting_uuid),
                "conflicting_vigente_desde": exc.conflicting_vigente_desde.isoformat()
                if exc.conflicting_vigente_desde is not None
                else None,
                "conflicting_vigente_hasta": exc.conflicting_vigente_hasta.isoformat()
                if exc.conflicting_vigente_hasta is not None
                else None,
            },
        )
    payload_dict = payload.model_dump(exclude_none=True)
    if payload.vigente_desde is not None:
        payload_dict["vigente_desde"] = _to_naive_utc(payload.vigente_desde)
    new_row = await close_and_insert(
        session,
        TarifasSucursal,
        current_uuid=uuid,
        new_attrs=payload_dict,
        actor_uuid=ctx.actor_uuid,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return TarifasSucursalRead.model_validate(new_row)


@_tarifas_pr_c_router.get(
    "/by-key",
    response_model=list[TarifasSucursalRead],
)
async def get_tarifa_by_key_history_pr_c(
    sucursal: uuid_lib.UUID = Query(...),
    tipo_vehiculo: uuid_lib.UUID | None = Query(None),
    tipo_tarifa: uuid_lib.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(requires_sucursal),
    _claims: None = Depends(_tarifas_pr_c_issuer_dep),
) -> list[TarifasSucursalRead]:
    """PR-C by-key / history: walk the bi-temporal version chain by business key.

    Why this endpoint exists: the factory's ``GET /{uuid}/history`` filters
    by ``uuid == :u``, so it returns only the version(s) of the SAME
    uuid (the closed original) and NOT the new version emitted by
    ``close_and_insert`` (which has a fresh UUID). The audit use-case
    "what rate did this branch apply between X and Y?" needs the full
    chain.

    Returns every version for the business key, DESC by
    ``vigente_desde`` — the operator can read the timeline top-down.
    Use the dedicated HU-F1.4 ``vigente_en`` parameter on the factory's
    GET list for the "what's vigente at instant X" view; this endpoint
    is the "every version, ever" view.
    """
    stmt = (
        select(TarifasSucursal)
        .where(
            TarifasSucursal.uuid_sucursal == sucursal,
            TarifasSucursal.uuid_tipo_vehiculo.is_not_distinct_from(tipo_vehiculo),
            TarifasSucursal.uuid_tipo_tarifa.is_not_distinct_from(tipo_tarifa),
        )
        .order_by(TarifasSucursal.vigente_desde.desc())
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return [TarifasSucursalRead.model_validate(r) for r in rows]


# Cantidad de vehiculos por sucursal: same shape.
_cantidad_pr_c_router = APIRouter(
    prefix="/cantidad-vehiculos-sucursal", tags=["cantidad-vehiculos-sucursal"]
)


@_cantidad_pr_c_router.post(
    "",
    response_model=CantidadVehiculosSucursalRead,
    status_code=201,
    dependencies=[Depends(_cantidad_pr_c_perm_dep)],
)
async def create_cantidad_pr_c(
    payload: CantidadVehiculosSucursalCreate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(requires_sucursal),
    _claims: None = Depends(_cantidad_pr_c_issuer_dep),
) -> CantidadVehiculosSucursalRead:
    """PR-C POST: opens a new cantidad version with overlap guard."""
    # Normalize the client-supplied valid-time to naive UTC so the
    # overlap guard SQL parameter and the ``vigente_desde`` column bind
    # safely (see ``_to_naive_utc`` docstring for the asyncpg DataError
    # this prevents). Same for ``payload_dict`` so ``close_and_insert``
    # does not stamp an aware datetime onto the new ``[V]`` row.
    payload_vigente_desde = _to_naive_utc(payload.vigente_desde)
    nueva_desde = payload_vigente_desde or datetime.now(UTC).replace(tzinfo=None)
    try:
        await assert_no_overlap(
            session,
            table="prod.cantidad_vehiculos_sucursal",
            resource="cantidad-vehiculos-sucursal",
            key=_Key(
                uuid_sucursal=payload.uuid_sucursal,
                uuid_tipo_vehiculo=payload.uuid_tipo_vehiculo,
                uuid_tipo_tarifa=None,
            ),
            nueva_vigente_desde=nueva_desde,
            nueva_vigente_hasta=nueva_desde,
            exclude_uuid=None,
        )
    except OverlapError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "cantidad_overlap",
                "conflicting_uuid": str(exc.conflicting_uuid),
                "conflicting_vigente_desde": exc.conflicting_vigente_desde.isoformat()
                if exc.conflicting_vigente_desde is not None
                else None,
                "conflicting_vigente_hasta": exc.conflicting_vigente_hasta.isoformat()
                if exc.conflicting_vigente_hasta is not None
                else None,
            },
        )
    payload_dict = payload.model_dump(exclude_none=True)
    if payload_vigente_desde is not None:
        payload_dict["vigente_desde"] = payload_vigente_desde
    new_row = await close_and_insert(
        session,
        CantidadVehiculosSucursal,
        current_uuid=None,
        new_attrs=payload_dict,
        actor_uuid=ctx.actor_uuid,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return CantidadVehiculosSucursalRead.model_validate(new_row)


@_cantidad_pr_c_router.put(
    "/{uuid}",
    response_model=CantidadVehiculosSucursalRead,
    dependencies=[Depends(_cantidad_pr_c_perm_dep)],
)
async def update_cantidad_pr_c(
    payload: CantidadVehiculosSucursalUpdate,
    uuid: uuid_lib.UUID = Path(...),
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(requires_sucursal),
    _claims: None = Depends(_cantidad_pr_c_issuer_dep),
) -> CantidadVehiculosSucursalRead:
    """PR-C PUT: close+insert with overlap, sucursal-inmutable, and
    capacidad-insuficiente guards.

    The third guard (BR2, HU-F14.4): the operator cannot lower
    ``cantidad`` below the count of currently-active ``ingreso`` rows
    for the same ``(uuid_sucursal, uuid_tipo_vehiculo)``. "Currently
    active" is DERIVED (never persisted) by reusing
    :func:`parkos_core.repo.ocupacion.get_ocupacion_puros_activos` --
    the same HU-F1.5 ``mv_ocupacion_diaria`` breakdown the live
    occupancy endpoint (HU-F4.3) and the ingreso V1/V2 cupo guard
    (``validar_cupo_disponible``) already use. The MV has a lag <= 10s
    accepted as live risk (KD-V8).

    A ``uuid_tipo_vehiculo`` of ``None`` (undifferentiated/blanket
    capacity -- a PR-C test convenience, not a catalog-backed cell) has
    no corresponding breakdown row (the MV join is driven by the
    ``tipos_vehiculo`` catalog), so the guard is a no-op for that cell.
    """
    current = await current_version(session, CantidadVehiculosSucursal, uuid)
    if current is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "cantidad_no_encontrada", "uuid": str(uuid)},
        )
    try:
        assert_sucursal_inmutable(
            resource="cantidad-vehiculos-sucursal",
            uuid=uuid,
            existing_sucursal=current.uuid_sucursal,
            payload_sucursal=payload.uuid_sucursal,
        )
    except SucursalInmutableError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "sucursal_inmutable",
                "uuid": str(exc.uuid),
                "existing_sucursal": str(exc.existing_sucursal),
                "attempted_sucursal": str(exc.attempted_sucursal),
            },
        )
    # Resolve the effective tipo_vehiculo: payload wins when present, else
    # carry forward from the existing row (the factory's column-merge
    # would do the same in ``close_and_insert``).
    effective_tipo_vehiculo = (
        payload.uuid_tipo_vehiculo
        if payload.uuid_tipo_vehiculo is not None
        else current.uuid_tipo_vehiculo
    )
    # The guard ONLY fires when the payload specifies a new cantidad
    # BELOW the current one. An increase is always allowed; a
    # no-cantidad-changed PUT (only vigente_desde) carries forward the
    # existing value via the factory merge — the helper would have
    # nothing to compare against, so we skip the guard in that case.
    if (
        payload.cantidad is not None
        and payload.cantidad < (current.cantidad or 0)
        and effective_tipo_vehiculo is not None
    ):
        ocupacion_rows = await get_ocupacion_puros_activos(
            session,
            uuid_sucursal=current.uuid_sucursal,  # type: ignore[arg-type]
        )
        # We match on the SAME key the cupos row is on, not the row's
        # current tipo_vehiculo, because the operator may be moving the
        # capacity to a different tipo (PUT carrying the existing
        # cantidad onto a new cell) and we want the guard to apply to
        # the destination cell's occupancy.
        ocupacion_match = next(
            (
                row
                for row in ocupacion_rows
                if row.uuid_tipo_vehiculo == effective_tipo_vehiculo
            ),
            None,
        )
        ocupado_actual = ocupacion_match.activos if ocupacion_match is not None else 0
        if payload.cantidad < ocupado_actual:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "capacidad_insuficiente",
                    "tipo": ocupacion_match.tipo if ocupacion_match is not None else None,
                    "ocupado_actual": ocupado_actual,
                    "solicitado": payload.cantidad,
                },
            )
    nueva_desde = _to_naive_utc(payload.vigente_desde) or datetime.now(UTC).replace(tzinfo=None)
    # Same retroactive-vigencia gap as tarifas (QA backlog cleanup,
    # 2026-10-02 — see the identical comment on ``update_tarifa_pr_c``
    # above): ``assert_no_overlap`` only queries the currently-open row,
    # which here IS ``current`` (excluded via ``exclude_uuid=uuid``
    # below), so it can never catch a backward-dated ``vigente_desde``.
    # The chain's windows are monotonically increasing, so comparing
    # against ``current.vigente_desde`` is sufficient to block going back
    # into any prior (open or closed) window for this business key.
    assert current.vigente_desde is not None  # current_version() guarantees an open row
    if nueva_desde < current.vigente_desde:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "cantidad_overlap",
                "conflicting_uuid": str(current.uuid),
                "conflicting_vigente_desde": current.vigente_desde.isoformat(),
                "conflicting_vigente_hasta": None,
            },
        )
    try:
        await assert_no_overlap(
            session,
            table="prod.cantidad_vehiculos_sucursal",
            resource="cantidad-vehiculos-sucursal",
            key=_Key(
                uuid_sucursal=current.uuid_sucursal,
                uuid_tipo_vehiculo=effective_tipo_vehiculo,
                uuid_tipo_tarifa=None,
            ),
            nueva_vigente_desde=nueva_desde,
            nueva_vigente_hasta=nueva_desde,
            exclude_uuid=uuid,
        )
    except OverlapError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "cantidad_overlap",
                "conflicting_uuid": str(exc.conflicting_uuid),
                "conflicting_vigente_desde": exc.conflicting_vigente_desde.isoformat()
                if exc.conflicting_vigente_desde is not None
                else None,
                "conflicting_vigente_hasta": exc.conflicting_vigente_hasta.isoformat()
                if exc.conflicting_vigente_hasta is not None
                else None,
            },
        )
    payload_dict = payload.model_dump(exclude_none=True)
    # Strip tz from any tz-aware payload carry-forward (see ``_to_naive_utc``
    # docstring). The ``close_and_insert`` helper would otherwise stamp an
    # aware datetime onto a ``DateTime(timezone=False)`` column.
    if payload.vigente_desde is not None:
        payload_dict["vigente_desde"] = _to_naive_utc(payload.vigente_desde)
    new_row = await close_and_insert(
        session,
        CantidadVehiculosSucursal,
        current_uuid=uuid,
        new_attrs=payload_dict,
        actor_uuid=ctx.actor_uuid,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return CantidadVehiculosSucursalRead.model_validate(new_row)


@_cantidad_pr_c_router.get(
    "/by-key",
    response_model=list[CantidadVehiculosSucursalRead],
)
async def get_cantidad_by_key_history_pr_c(
    sucursal: uuid_lib.UUID = Query(...),
    tipo_vehiculo: uuid_lib.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(requires_sucursal),
    _claims: None = Depends(_cantidad_pr_c_issuer_dep),
) -> list[CantidadVehiculosSucursalRead]:
    """PR-C by-key / history for cantidad."""
    stmt = (
        select(CantidadVehiculosSucursal)
        .where(
            CantidadVehiculosSucursal.uuid_sucursal == sucursal,
            CantidadVehiculosSucursal.uuid_tipo_vehiculo.is_not_distinct_from(
                tipo_vehiculo
            ),
        )
        .order_by(CantidadVehiculosSucursal.vigente_desde.desc())
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return [CantidadVehiculosSucursalRead.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# HU-F15.1 BR4 — dedicated handler for ``GET /empresa/cantidad-vehiculos-sucursal``
# ---------------------------------------------------------------------------
#
# Same ``vigente_en`` pattern as the HU-F1.4 tarifas handler above (reuses
# the SAME generic ``bitemporal_vigente_predicate`` helper — it already
# takes ``model_cls`` as a parameter, so no new repo helper is needed).
# Registered on the ALREADY-mounted ``_cantidad_pr_c_router`` (prefix
# ``/cantidad-vehiculos-sucursal``, included on ``router`` below this
# block and stored under the ``cantidad-vehiculos-sucursal__dedicated_pr_c``
# key that the reorder block already places ahead of the factory mount) —
# no new router / no new ``_SUB_ROUTERS`` key needed.
@_cantidad_pr_c_router.get(
    "",
    response_model=CantidadVehiculosSucursalReadList,
)
async def list_cantidad_vehiculos_sucursal_vigente_en(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    vigente_en: datetime | None = Query(
        None,
        description=(
            "Punto en el tiempo para el predicado de vigencia (HU-F15.1 BR4). "
            "Acepta ISO-8601 con o sin tz (naive = UTC). "
            "Default: datetime.now(UTC)."
        ),
    ),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(requires_sucursal),
    _claims: None = Depends(_cantidad_pr_c_issuer_dep),
) -> CantidadVehiculosSucursalReadList:
    """HU-F15.1 BR4 — bi-temporal ``GET /empresa/cantidad-vehiculos-sucursal``.

    Same response shape as the factory's list endpoint. ``requires_sucursal``
    (not the lenient ``get_tenant_ctx``) is deliberate: ``cantidad_vehiculos_
    sucursal`` carries ``uuid_sucursal`` and is auto-filtered by the ambient
    tenant listener (``db.tenancy.do_orm_execute``) only when a branch
    context was actually resolved -- an absent header would otherwise return
    every branch's rows combined. Mirrors
    ``list_tarifas_sucursal_vigente_en`` exactly.
    """
    v = vigente_en if vigente_en is not None else datetime.now(UTC)
    v_utc = _to_naive_utc(v) or datetime.now(UTC).replace(tzinfo=None)

    from ...repo.pagination import Cursor as _Cursor
    from ...repo.pagination import InvalidCursorError as _InvalidCursorError
    from ...repo.pagination import decode as _cursor_decode
    from ...repo.pagination import encode as _cursor_encode

    try:
        decoded = _cursor_decode(cursor) if cursor else None
    except _InvalidCursorError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_cursor", "detail": str(e)},
        ) from e

    order_col, cursor_field = _order_key(CantidadVehiculosSucursal)
    stmt = select(CantidadVehiculosSucursal).where(
        bitemporal_vigente_predicate(CantidadVehiculosSucursal, v_utc)
    )
    stmt = stmt.order_by(order_col, CantidadVehiculosSucursal.uuid.asc())
    if decoded is not None:
        cursor_ts = _parse_cursor_timestamp(getattr(decoded, cursor_field))
        stmt = stmt.where(
            (order_col.element < cursor_ts)
            | (
                (order_col.element == cursor_ts)
                & (CantidadVehiculosSucursal.uuid > uuid_lib.UUID(decoded.uuid))
            )
        )
    stmt = stmt.limit(limit + 1)

    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        last_vigente_desde: datetime | None = last.vigente_desde
        next_cursor = _cursor_encode(
            _Cursor(
                vigente_desde=(
                    last_vigente_desde.isoformat() if last_vigente_desde is not None else None
                ),
                created_at=None,
                uuid=str(last.uuid),
            )
        )
    items = [CantidadVehiculosSucursalRead.model_validate(r) for r in rows]
    return CantidadVehiculosSucursalReadList(items=items, next_cursor=next_cursor)


# ---------------------------------------------------------------------------
# HU-F15.1 BR4 — dedicated handler for ``GET /empresa/resolucion-facturacion``
# ---------------------------------------------------------------------------
#
# Unlike tarifas/cantidad there is NO existing dedicated router for this
# resource (only the factory mount below). Mirrors ``_tarifas_dedicated_
# router`` exactly: own ``APIRouter`` with the SAME ``/resolucion-facturacion``
# prefix, included on ``router`` BEFORE the factory mount for the same
# resource so FastAPI's first-match resolver answers the bare ``GET`` list
# path here. Issuer is ``admin-`` ONLY (no ``operador-``), matching
# ``_ROUTER_CONFIG["resolucion-facturacion"]`` -- this is the DIAN root
# table (REQ-X3, cloud-only writes). ``requires_sucursal`` for the same
# ambient-tenant-listener reason as the cantidad handler above
# (``resolucion_facturacion`` carries ``uuid_sucursal``).
#
# DIAN boundary note: this dedicated router is registered under its OWN
# ``_SUB_ROUTERS`` key (below), NOT the plain ``"resolucion-facturacion"``
# key the factory mount uses. ``api/v1/__init__.py``'s branch-deploy
# exclusion (``_CLOUD_ONLY_EMPRESA_RESOURCES``) matches on the exact key —
# the new key is added there too so this handler stays excluded from
# ``api_sucursal`` the same way the factory's resource already is.
_resolucion_issuer_dep = requires_issuer("admin-")
_resolucion_dedicated_router = APIRouter(
    prefix="/resolucion-facturacion", tags=["resolucion-facturacion"]
)


@_resolucion_dedicated_router.get(
    "",
    response_model=ResolucionFacturacionReadList,
)
async def list_resolucion_facturacion_vigente_en(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    vigente_en: datetime | None = Query(
        None,
        description=(
            "Punto en el tiempo para el predicado de vigencia (HU-F15.1 BR4). "
            "Acepta ISO-8601 con o sin tz (naive = UTC). "
            "Default: datetime.now(UTC)."
        ),
    ),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(requires_sucursal),
    _claims: None = Depends(_resolucion_issuer_dep),
) -> ResolucionFacturacionReadList:
    """HU-F15.1 BR4 — bi-temporal ``GET /empresa/resolucion-facturacion``.

    Same response shape and cursor contract as the factory's list endpoint;
    same bi-temporal predicate as the tarifas/cantidad siblings above.
    """
    v = vigente_en if vigente_en is not None else datetime.now(UTC)
    v_utc = _to_naive_utc(v) or datetime.now(UTC).replace(tzinfo=None)

    from ...repo.pagination import Cursor as _Cursor
    from ...repo.pagination import InvalidCursorError as _InvalidCursorError
    from ...repo.pagination import decode as _cursor_decode
    from ...repo.pagination import encode as _cursor_encode

    try:
        decoded = _cursor_decode(cursor) if cursor else None
    except _InvalidCursorError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_cursor", "detail": str(e)},
        ) from e

    order_col, cursor_field = _order_key(ResolucionFacturacion)
    stmt = select(ResolucionFacturacion).where(
        bitemporal_vigente_predicate(ResolucionFacturacion, v_utc)
    )
    stmt = stmt.order_by(order_col, ResolucionFacturacion.uuid.asc())
    if decoded is not None:
        cursor_ts = _parse_cursor_timestamp(getattr(decoded, cursor_field))
        stmt = stmt.where(
            (order_col.element < cursor_ts)
            | (
                (order_col.element == cursor_ts)
                & (ResolucionFacturacion.uuid > uuid_lib.UUID(decoded.uuid))
            )
        )
    stmt = stmt.limit(limit + 1)

    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        last_vigente_desde: datetime | None = last.vigente_desde
        next_cursor = _cursor_encode(
            _Cursor(
                vigente_desde=(
                    last_vigente_desde.isoformat() if last_vigente_desde is not None else None
                ),
                created_at=None,
                uuid=str(last.uuid),
            )
        )
    items = [ResolucionFacturacionRead.model_validate(r) for r in rows]
    return ResolucionFacturacionReadList(items=items, next_cursor=next_cursor)


@_resolucion_dedicated_router.get(
    "/{uuid}/consecutivo-actual",
    response_model=ResolucionFacturacionConsecutivoActual,
    responses={404: {"description": "resolucion_no_encontrada"}},
)
async def get_resolucion_facturacion_consecutivo_actual(
    uuid: uuid_lib.UUID = Path(
        ...,
        description="UUIDv4 de la fila de prod.resolucion_facturacion a consultar.",
    ),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(requires_sucursal),
    _claims: None = Depends(_resolucion_issuer_dep),
) -> ResolucionFacturacionConsecutivoActual:
    """HU-F15.3 BR1/BR2 — ``GET /empresa/resolucion-facturacion/{uuid}/consecutivo-actual``.

    Read-only projection of the current consecutivo + remaining-range state
    for one resolución. Mirrors ``dian.cloud.atomic_next_consecutivo
    .next_consecutivo``'s read (``COALESCE(MAX(consecutivo), rango_desde - 1)
    + 1`` scoped to the resolution) but WITHOUT ``SELECT ... FOR UPDATE``:
    this handler never allocates a consecutivo, it only reports the current
    state, so it does not need (and must not take) the write-path lock.
    Registered on the same ``_resolucion_dedicated_router`` as the BR4
    ``vigente_en`` list handler above, so it inherits the same DIAN boundary
    exclusion (``_CLOUD_ONLY_EMPRESA_RESOURCES`` in ``api/v1/__init__.py``
    matches the router's ``_SUB_ROUTERS`` key, not the individual path).
    """
    row = (
        await session.execute(
            select(ResolucionFacturacion).where(ResolucionFacturacion.uuid == uuid)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "resolucion_no_encontrada", "uuid": str(uuid)},
        )

    start = (row.rango_desde - 1) if row.rango_desde is not None else -1
    max_consecutivo = (
        await session.execute(
            text(
                "SELECT COALESCE(MAX(consecutivo), :start) "
                "FROM prod.factura_electronica "
                "WHERE uuid_resolucion_facturacion = :uuid"
            ),
            {"start": start, "uuid": str(uuid)},
        )
    ).scalar_one()
    consecutivo_actual = int(max_consecutivo) + 1
    rango_hasta = row.rango_hasta
    restantes = (rango_hasta - consecutivo_actual) if rango_hasta is not None else None
    agotandose = restantes is not None and restantes < 100
    return ResolucionFacturacionConsecutivoActual(
        consecutivo_actual=consecutivo_actual,
        rango_hasta=rango_hasta,
        restantes=restantes,
        agotandose=agotandose,
    )


# ---------------------------------------------------------------------------
# HU-F15.1 BR2/BR3 — ``POST /empresa/sucursal/{uuid}/deshabilitar``
# ---------------------------------------------------------------------------
#
# BR2: a disabled branch (``vigente_hasta`` closed, no replacement version)
# stops accepting NEW ingresos but still allows salidas -- that differential
# behaviour is enforced by ``web_sucursal`` reading ``vigente_hasta``; this
# endpoint's only job is the close itself (``repo.versioned.close_only`` --
# same close-only / no-replacement-version primitive
# ``admin_usuarios.py::revocar_permiso`` already uses for the symmetric
# "último admin" guard, mirrored here for sucursal).
#
# BR3: refuses with 409 when the branch has active ingresos (vehicles
# currently inside) OR vigente subscriptions still referencing it. Both
# checks run BEFORE the close so the row is never left half-guarded.
#
# ``get_tenant_ctx`` (NOT ``requires_sucursal``): ``Sucursal`` itself has no
# ``uuid_sucursal`` column (it IS the branch, not data scoped BY a branch),
# so there is no ambient-listener leak risk the cantidad/resolucion handlers
# above have to worry about. Mirrors the factory's OWN POST/PUT for
# ``sucursal`` (``router_factory.make_router``'s ``create_endpoint`` /
# ``update_endpoint``), which also use the lenient ``get_tenant_ctx`` so an
# admin can manage any branch from ``/sucursales/:uuid`` without first
# "selecting" it via ``X-Sucursal-Context``.
_sucursal_actions_issuer_dep = requires_issuer("admin-", "operador-")
_sucursal_actions_perm_dep = require_permission("config_sucursal")
_sucursal_actions_router = APIRouter(prefix="/sucursal", tags=["sucursal"])


async def _count_ingresos_activos_sucursal(
    session: AsyncSession, uuid_sucursal: uuid_lib.UUID
) -> int:
    """BR3 (HU-F15.1): total active ``ingreso`` rows for a branch.

    Sums ``.activos`` across every tipo from the SAME per-tipo breakdown
    helper the cantidad-vehiculos-sucursal capacity guard already relies on
    (``repo.ocupacion.get_ocupacion_puros_activos`` -- raw SQL against
    ``prod.mv_ocupacion_diaria``, same <=10s lag accepted as live risk,
    KD-V4/RIESGO-SUC-02). No new query needed: the branch's total occupancy
    is tipo-agnostic for this guard, unlike the capacity guard which checks
    one tipo at a time.
    """
    rows = await get_ocupacion_puros_activos(session, uuid_sucursal=uuid_sucursal)
    return sum(r.activos for r in rows)


async def _count_suscripciones_vigentes_sucursal(
    session: AsyncSession, uuid_sucursal: uuid_lib.UUID
) -> int:
    """BR3 (HU-F15.1): vigente ``subscripciones_cliente`` rows referencing a branch.

    Raw SQL (``text(...)``), deliberately NOT an ORM ``select(...)``:
    ``subscripciones_cliente`` carries ``uuid_sucursal`` and this endpoint
    uses the lenient ``get_tenant_ctx`` (see the module comment above), so
    an admin's ambient ``X-Sucursal-Context`` (if any, possibly a DIFFERENT
    branch than the one being disabled) must never silently narrow this
    guard's count via the ``db.tenancy.do_orm_execute`` listener. Mirrors
    ``repo.ocupacion.get_ocupacion_puros_activos``'s own use of ``text(...)``
    for the identical reason.
    """
    stmt = text(
        """
        SELECT COUNT(*) AS total
        FROM prod.subscripciones_cliente
        WHERE uuid_sucursal = :uuid_sucursal
          AND vigente_hasta IS NULL
          AND estado = 'activo'
        """
    )
    result = await session.execute(stmt, {"uuid_sucursal": str(uuid_sucursal)})
    return int(result.scalar_one())


@_sucursal_actions_router.post(
    "/{uuid}/deshabilitar",
    status_code=204,
    dependencies=[Depends(_sucursal_actions_perm_dep)],
    summary=(
        "Close a branch (admin/operador config_sucursal). POST because the "
        "underlying table is bi-temporal (AGENTS.md §3 -- [V] rows are "
        "NEVER physically deleted; the repo layer does ``close_only``, no "
        "replacement version). 404 if the branch is already closed/unknown; "
        "409 if it still has active ingresos or vigente subscriptions (BR3)."
    ),
    responses={
        204: {"description": "Sucursal deshabilitada."},
        404: {"description": "sucursal_no_encontrada"},
        409: {
            "description": (
                "sucursal_con_ocupacion (vehiculos adentro) o "
                "sucursal_con_suscripciones_vigentes"
            )
        },
    },
)
async def deshabilitar_sucursal(
    uuid: uuid_lib.UUID = Path(...),
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_sucursal_actions_issuer_dep),
) -> Response:
    current = await current_version(session, Sucursal, uuid)
    if current is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "sucursal_no_encontrada", "uuid": str(uuid)},
        )

    ocupacion_activa = await _count_ingresos_activos_sucursal(session, uuid)
    if ocupacion_activa > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "sucursal_con_ocupacion",
                "uuid": str(uuid),
                "activos": ocupacion_activa,
            },
        )

    suscripciones_vigentes = await _count_suscripciones_vigentes_sucursal(session, uuid)
    if suscripciones_vigentes > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "sucursal_con_suscripciones_vigentes",
                "uuid": str(uuid),
                "suscripciones_vigentes": suscripciones_vigentes,
            },
        )

    await close_only(session, Sucursal, uuid, actor_uuid=ctx.actor_uuid)
    await session.commit()
    return Response(status_code=204)


# Register the dedicated write routers on the same aggregated ``router``
# so the backward-compat direct-imports keep working. The v1 router in
# ``api/v1/__init__.py`` picks them up via ``_SUB_ROUTERS`` (below).
router.include_router(_tarifas_pr_c_router)
router.include_router(_cantidad_pr_c_router)
router.include_router(_resolucion_dedicated_router)
router.include_router(_sucursal_actions_router)


# Register the dedicated handlers under synthetic keys so the v1
# router picks them up BEFORE the factory sub-routers. The dedicated
# POST/PUT/by-key handlers MUST shadow the factory's POST/PUT/GET for
# the same path so the validation runs.
_SUB_ROUTERS["tarifas-sucursal__dedicated_hu_f1_4"] = _tarifas_dedicated_router
_SUB_ROUTERS["tarifas-sucursal__dedicated_pr_c"] = _tarifas_pr_c_router
_SUB_ROUTERS["cantidad-vehiculos-sucursal__dedicated_pr_c"] = _cantidad_pr_c_router
_SUB_ROUTERS["resolucion-facturacion__dedicated_vigente_en"] = _resolucion_dedicated_router
# QA backlog cleanup (2026-10-02): real defect confirmed live -- registering
# ``_sucursal_dedicated_router`` on the module-level ``router`` object
# (above, near its definition) has NO effect on the real running app.
# ``api/v1/__init__.py::_build_empresa_router()`` does NOT mount
# ``empresa.router`` directly; it rebuilds a FRESH router from
# ``empresa._SUB_ROUTERS`` only (see that function's docstring). A
# dedicated router that is never registered into ``_SUB_ROUTERS`` under
# its own key is simply invisible to the live app -- the factory's plain
# POST/PUT (registered under the bare ``"sucursal"`` key) kept answering
# every request, so the prefijo-duplicado guard silently never ran.
# Same synthetic-key + reorder pattern as every sibling dedicated router
# above.
_SUB_ROUTERS["sucursal__dedicated_prefijo_duplicado"] = _sucursal_dedicated_router
# ``/sucursal/{uuid}/deshabilitar`` is a brand-new path (no factory
# equivalent to shadow) so registration order does not matter for
# correctness, but it is tracked here for consistency with every other
# dedicated handler in this module.
_SUB_ROUTERS["sucursal__dedicated_deshabilitar"] = _sucursal_actions_router

# Reorder so the dedicated handlers come first.
_reordered: dict[str, APIRouter] = {}
for _pr_c_key in (
    # QA batch tarifas/cupos (2026-10-02): "pr_c" (owns the literal
    # ``GET /by-key``) MUST precede "hu_f1_4" (owns the catch-all
    # ``GET /{uuid}``) -- the earlier order let ``{uuid}`` swallow the
    # literal ``by-key`` path segment first, producing a permanent 422
    # ``uuid_parsing`` and making "ver histórico" unreachable. See
    # ``test_tarifas_by_key_router_ordering.py``.
    "tarifas-sucursal__dedicated_pr_c",
    "tarifas-sucursal__dedicated_hu_f1_4",
    "cantidad-vehiculos-sucursal__dedicated_pr_c",
    # HU-F15.1: new dedicated GET must precede the factory's plain
    # "resolucion-facturacion" mount the same way the tarifas/cantidad
    # dedicated handlers precede theirs.
    "resolucion-facturacion__dedicated_vigente_en",
    # QA backlog cleanup (2026-10-02): must precede the bare "sucursal"
    # factory key (POST/PUT) so the prefijo-duplicado guard actually
    # shadows it -- see the registration comment above.
    "sucursal__dedicated_prefijo_duplicado",
    "sucursal__dedicated_deshabilitar",
    # fix/catalog-sucursal-global-reads: the global-reads router was
    # added to _SUB_ROUTERS above the factory mount, but list it here
    # explicitly so the ordering stays correct if a future PR reorders
    # the insertion block. POST/PUT keep flowing through the factory
    # sub-router (tenant-scoped writes).
    "sucursal__dedicated_global_reads",
):
    if _pr_c_key in _SUB_ROUTERS:
        _reordered[_pr_c_key] = _SUB_ROUTERS[_pr_c_key]
for _k, _v in _SUB_ROUTERS.items():
    if _k not in _reordered:
        _reordered[_k] = _v
_SUB_ROUTERS.clear()
_SUB_ROUTERS.update(_reordered)


# tarifas-sucursal: factory router removed — all endpoints are provided by
# dedicated routers (_tarifas_dedicated_router for GET list/by-uuid,
# _tarifas_pr_c_router for POST/PUT/by-key). The factory router was causing
# route resolution conflicts with FastAPI's _IncludedRouter mechanism.
_mount_empresa(
    resource="cantidad-vehiculos-sucursal",
    model_cls=CantidadVehiculosSucursal,
    read_schema=CantidadVehiculosSucursalRead,
    read_list_schema=CantidadVehiculosSucursalReadList,
    create_schema=CantidadVehiculosSucursalCreate,
    update_schema=CantidadVehiculosSucursalUpdate,
)


__all__ = ["_SUB_ROUTERS", "router"]