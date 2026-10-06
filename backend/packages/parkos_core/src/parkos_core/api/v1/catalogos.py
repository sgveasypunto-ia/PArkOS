"""Catalog-domain HTTP routes (REQ-OP-13, REQ-02-V-CONSULTA, SC-01-V-CATALOG-CRUD).

PR3 mounts all 9 catalog tables — see ``tasks.md`` T-PR3-01..T-PR3-09. Each
router is built by ``make_router`` with:

- ``repo_kind="versioned"`` — bi-temporal close+insert writes (REQ-04, REQ-05)
- ``issuer_required="admin-,operador-"`` — admin writes, operador reads the
  replicated catalogs (catalogs are cloud-authored + replicated down)
- ``permission_required="config_catalogo"`` — write-side guard (REQ-OP-13)

The 9 catalogs (all ``[V]`` per design §2):

1. ``tipo-persona``         — natural | juridica
2. ``tipos-vehiculo``       — carro | moto | bicicleta
3. ``tipo-subscripciones``  — commercial plans
4. ``tipo-tarifa``          — hora | fraccion | plena | nocturna
5. ``tipo-sucursal``        — branch operating model (with JSONB ``caracteristicas``)
6. ``tipo-arqueo``          — cierre_turno | auditoria | cierre_sesion
7. ``impuestos``            — tax catalog (IVA, INC); invoice snapshots to
                              ``factura_impuestos`` (design §10)
8. ``otros-cobros``         — additional billable charges; invoice snapshots to
                              ``factura_otros_cobros``
9. ``costos-servicios``     — internal services (ticket reprint, etc.)

NO DELETE endpoint at any layer — defense in depth (design §3, AGENTS.md §3).

**Global reads carve-out (fix/catalog-sucursal-global-reads)** — none of the
9 catalog tables carries a ``uuid_sucursal`` column; they are tenant-global
reference data replicated cloud→branch. The frontend mounts ``CatalogPage``
and ``TipoSucursal`` picker OUTSIDE ``<RequireSucursal>`` because reading
or editing a catalog does not require a branch to be selected
(``features/catalogos/CatalogPage.tsx:2-7``). To honour that invariant
without touching ``make_router`` (CI gate ``factory_intact``), the 3 read
routes (``GET /catalogos/{resource}``, ``GET /catalogos/{resource}/{uuid}``,
``GET /catalogos/{resource}/{uuid}/history``) are registered FIRST on the
main ``router`` via :func:`_register_global_catalog_reads`. FastAPI's
order-of-registration resolver picks the global-reads handler over the
factory sub-router for those paths; POST/PUT continue to flow through the
factory sub-router and therefore still require ``X-Sucursal-Context`` for
``admin-`` tokens (defense in depth on writes).
"""
from __future__ import annotations

import uuid as uuid_lib

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.permissions import require_permission
from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...models.V.costos_servicios import CostosServicios
from ...models.V.impuestos import Impuestos
from ...models.V.otros_cobros import OtrosCobros
from ...models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ...models.V.subscripciones_cliente import SubscripcionesCliente
from ...models.V.tipo_arqueo import TipoArqueo
from ...models.V.tipo_persona import TipoPersona
from ...models.V.tipo_subscripciones import TipoSubscripciones
from ...models.V.tipo_sucursal import TipoSucursal
from ...models.V.tipo_tarifa import TipoTarifa
from ...models.V.tipos_vehiculo import TiposVehiculo
from ...models.V.vehiculos import Vehiculos
from ...repo.pagination import Cursor, InvalidCursorError
from ...repo.pagination import decode as cursor_decode
from ...repo.pagination import encode as cursor_encode
from ...repo.tipos_vehiculo_subscripcion import get_tipos_vehiculo_con_subscripcion
from ...repo.versioned import close_and_insert, current_version
from ...schemas.costos_servicios import (
    CostosServiciosCreate,
    CostosServiciosRead,
    CostosServiciosReadList,
    CostosServiciosUpdate,
)
from ...schemas.impuestos import (
    ImpuestosCreate,
    ImpuestosRead,
    ImpuestosReadList,
    ImpuestosUpdate,
)
from ...schemas.otros_cobros import (
    OtrosCobrosCreate,
    OtrosCobrosRead,
    OtrosCobrosReadList,
    OtrosCobrosUpdate,
)
from ...schemas.tipo_arqueo import (
    TipoArqueoCreate,
    TipoArqueoRead,
    TipoArqueoReadList,
    TipoArqueoUpdate,
)
from ...schemas.tipo_persona import (
    TipoPersonaCreate,
    TipoPersonaRead,
    TipoPersonaReadList,
    TipoPersonaUpdate,
)
from ...schemas.tipo_subscripciones import (
    TipoSubscripcionesCreate,
    TipoSubscripcionesRead,
    TipoSubscripcionesReadList,
    TipoSubscripcionesUpdate,
)
from ...schemas.tipo_sucursal import (
    TipoSucursalCreate,
    TipoSucursalRead,
    TipoSucursalReadList,
    TipoSucursalUpdate,
)
from ...schemas.tipo_tarifa import (
    TipoTarifaCreate,
    TipoTarifaRead,
    TipoTarifaReadList,
    TipoTarifaUpdate,
)
from ...schemas.tipos_vehiculo import (
    TiposVehiculoCreate,
    TiposVehiculoRead,
    TiposVehiculoReadList,
    TiposVehiculoUpdate,
)
from ..deps import requires_issuer
from ..router_factory import make_router

router = APIRouter(prefix="/catalogos", tags=["catalogos"])

_CATALOG_DEFAULTS = {
    "repo_kind": "versioned",
    "issuer_required": "admin-,operador-",
    "permission_required": "config_catalogo",
}

# Issuer for the global-reads endpoints. Same surface as the factory
# (``admin-,operador-``) but NO ``get_tenant_ctx`` dependency — catalogs
# are tenant-global reference data, so reading them does not require an
# ``X-Sucursal-Context`` header. ``admin-`` JWTs without the header now
# succeed; ``operador-`` JWTs are unaffected (header is already optional
# for them; the JWT ``sucursal`` claim drives query scoping which is a
# no-op for tables without a ``uuid_sucursal`` column).
_catalog_reads_issuer_dep = requires_issuer("admin-", "operador-")


def _order_key(model_cls: type) -> tuple:
    """Mirror of ``api/router_factory.py::_order_key`` — duplicated here
    intentionally to avoid touching ``router_factory.py`` (CI gate
    ``factory_intact``). Returns ``(order_col_desc, cursor_field_name)``.

    The 9 catalog tables all declare ``vigente_desde`` (they are ``[V]``),
    so the order-by branch with ``vigente_desde.desc()`` is the live one.
    The ``created_at`` fallback is a defense-in-depth copy of the
    factory's helper for any future catalog that omits ``vigente_desde``.
    """
    if hasattr(model_cls, "vigente_desde"):
        return (model_cls.vigente_desde.desc(), "vigente_desde")
    return (model_cls.created_at.desc(), "created_at")


def _register_global_catalog_reads(
    *,
    resource: str,
    model_cls: type,
    read_schema: type,
    read_list_schema: type,
) -> None:
    """Register the 3 tenant-free read handlers on the main ``router``.

    Mounted BEFORE the factory sub-router for the same resource so
    FastAPI's order-of-registration resolver picks these handlers over
    the factory's ``GET /{resource}`` / ``GET /{resource}/{uuid}`` /
    ``GET /{resource}/{uuid}/history``. POST/PUT remain on the factory
    sub-router (tenant-scoped — see module docstring).

    The cursor pagination logic mirrors ``api/router_factory.py``
    verbatim; only the dependencies differ (no ``get_tenant_ctx``).
    """
    order_col, cursor_field = _order_key(model_cls)

    @router.get(
        f"/{resource}",
        response_model=read_list_schema,
        tags=["catalogos"],
    )
    async def _catalog_list(
        cursor: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        uuid_tipo_vehiculo: uuid_lib.UUID | None = Query(
            None,
            description=(
                "Solo ``tipo-subscripciones`` (PT-2): devuelve los planes de ese "
                "tipo de vehiculo MAS los planes sin tipo (NULL = cualquier tipo)."
            ),
        ),
        session: AsyncSession = Depends(get_session),
        _claims: None = Depends(_catalog_reads_issuer_dep),
    ):
        try:
            decoded = cursor_decode(cursor) if cursor else None
        except InvalidCursorError as e:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_cursor", "detail": str(e)},
            )
        stmt = select(model_cls)
        if hasattr(model_cls, "vigente_hasta"):
            stmt = stmt.where(model_cls.vigente_hasta.is_(None))
        if uuid_tipo_vehiculo is not None:
            if model_cls is not TipoSubscripciones:
                raise HTTPException(
                    status_code=422,
                    detail={"error": "filter_not_supported", "detail": "uuid_tipo_vehiculo"},
                )
            stmt = stmt.where(
                (TipoSubscripciones.uuid_tipo_vehiculo == uuid_tipo_vehiculo)
                | TipoSubscripciones.uuid_tipo_vehiculo.is_(None)
            )
        stmt = stmt.order_by(order_col, model_cls.uuid.asc())
        if decoded is not None:
            from datetime import datetime

            cursor_ts = datetime.fromisoformat(decoded.vigente_desde)
            if cursor_ts.tzinfo is not None:
                cursor_ts = cursor_ts.replace(tzinfo=None)
            stmt = stmt.where(
                (order_col.element < cursor_ts)
                | (
                    (order_col.element == cursor_ts)
                    & (model_cls.uuid > uuid_lib.UUID(decoded.uuid))
                )
            )
        stmt = stmt.limit(limit + 1)

        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = cursor_encode(
                Cursor(
                    vigente_desde=(
                        last.vigente_desde.isoformat()
                        if cursor_field == "vigente_desde"
                        else None
                    ),
                    created_at=(
                        last.created_at.isoformat()
                        if cursor_field == "created_at"
                        else None
                    ),
                    uuid=str(last.uuid),
                )
            )
        items = [read_schema.model_validate(row) for row in rows]
        return read_list_schema(items=items, next_cursor=next_cursor)

    @router.get(
        f"/{resource}/{{uuid}}",
        response_model=read_schema,
        tags=["catalogos"],
    )
    async def _catalog_get(
        uuid: uuid_lib.UUID = Path(...),
        session: AsyncSession = Depends(get_session),
        _claims: None = Depends(_catalog_reads_issuer_dep),
    ):
        row = await current_version(session, model_cls, uuid)
        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "uuid": str(uuid)},
            )
        return read_schema.model_validate(row)

    if hasattr(model_cls, "vigente_hasta"):

        @router.get(
            f"/{resource}/{{uuid}}/history",
            response_model=list[read_schema],
            tags=["catalogos"],
        )
        async def _catalog_history(
            uuid: uuid_lib.UUID = Path(...),
            session: AsyncSession = Depends(get_session),
            _claims: None = Depends(_catalog_reads_issuer_dep),
        ):
            stmt = (
                select(model_cls)
                .where(model_cls.uuid == uuid)
                .order_by(model_cls.vigente_desde.desc())
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())
            return [read_schema.model_validate(r) for r in rows]


def _mount_catalog(
    *,
    resource: str,
    model_cls: type,
    read_schema: type,
    read_list_schema: type,
    create_schema: type,
    update_schema: type,
    tenant_free_reads: bool = False,
) -> None:
    """Mount one catalog C+Q+U router under ``/catalogos/{resource}``.

    Centralises the ``make_router`` defaults so all 9 catalogs share the same
    issuer/permission/repo policy (REQ-OP-13, SC-01-V-CATALOG-CRUD).

    When ``tenant_free_reads=True`` the 3 read endpoints
    (``GET /{resource}``, ``GET /{resource}/{uuid}``,
    ``GET /{resource}/{uuid}/history``) are registered FIRST on the main
    ``router`` WITHOUT ``get_tenant_ctx``, so ``admin-`` tokens without
    ``X-Sucursal-Context`` can read catalogs before a branch is selected.
    The factory sub-router is then ``include_router``'d for the same
    resource — FastAPI's first-match resolver keeps the global-reads
    handlers in front; only POST/PUT fall through to the factory
    (tenant-scoped writes preserved).
    """
    if tenant_free_reads:
        _register_global_catalog_reads(
            resource=resource,
            model_cls=model_cls,
            read_schema=read_schema,
            read_list_schema=read_list_schema,
        )
    router.include_router(
        make_router(
            resource=resource,
            model_cls=model_cls,
            read_schema=read_schema,
            read_list_schema=read_list_schema,
            create_schema=create_schema,
            update_schema=update_schema,
            **_CATALOG_DEFAULTS,
        )
    )


async def _assert_no_vigente_duplicate(
    session: AsyncSession,
    model_cls: type,
    *,
    field_name: str,
    value: str,
    exclude_uuid: uuid_lib.UUID | None = None,
) -> None:
    """Reject a write that would leave two vigente rows with the same
    business-key value on a ``[V]`` catalog table.

    Discovered live via manual QA (2026-10-02, batch ``qa/batch-catalogos``):
    ``router_factory.make_router``'s generic POST (``current_uuid=None``)
    never checks for an existing vigente row before inserting — the only
    DB-level guard is ``UniqueConstraint(tipo, vigente_desde)``, which never
    fires because ``vigente_desde`` is a fresh ``NOW()`` on every insert.
    Submitting "natural" via "Nueva versión" while a "natural" row was
    already vigente silently produced TWO vigente rows with the same
    ``tipo`` — both rendered as "Vigente" in the UI with no way to tell
    which one is authoritative. Each catalog config already documents its
    own business-key field (see ``configs/*.config.ts`` comments); this
    helper is the server-side guard for it.

    Mirrors the style of the ``tipos_vehiculo`` 409 guards below —
    check-before-write, typed detail, no change to ``router_factory.py``
    (CI gate ``factory_intact``). ``exclude_uuid`` lets PUT exclude the row
    being edited itself (renaming a row to its own current value is not a
    duplicate).
    """
    column = getattr(model_cls, field_name)
    stmt = select(func.count()).select_from(model_cls).where(
        model_cls.vigente_hasta.is_(None),
        column == value,
    )
    if exclude_uuid is not None:
        stmt = stmt.where(model_cls.uuid != exclude_uuid)
    result = await session.execute(stmt)
    if int(result.scalar_one()) > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "catalogo_duplicado_vigente",
                "field": field_name,
                "value": value,
            },
        )


# ---------------------------------------------------------------------------
# Duplicate-vigente guard on ``tipo-persona`` POST/PUT (business key ``tipo``)
# ---------------------------------------------------------------------------
#
# Same shadow-the-factory pattern as the ``tipos_vehiculo`` dedicated router
# below: the dedicated router is mounted FIRST on ``catalogos.router`` so
# FastAPI's order-of-registration resolver routes POST/PUT here instead of
# to the factory. GET stays on the factory / ``_register_global_catalog_reads``.
_tipo_persona_dedicated_router = APIRouter(prefix="/tipo-persona", tags=["tipo-persona"])
_tipo_persona_dedicated_perm_dep = require_permission("config_catalogo")
_tipo_persona_dedicated_issuer_dep = requires_issuer("admin-", "operador-")


@_tipo_persona_dedicated_router.post(
    "",
    response_model=TipoPersonaRead,
    status_code=201,
    dependencies=[Depends(_tipo_persona_dedicated_perm_dep)],
)
async def create_tipo_persona_dedicated(
    payload: TipoPersonaCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_tipo_persona_dedicated_issuer_dep),
) -> TipoPersonaRead:
    await _assert_no_vigente_duplicate(
        session, TipoPersona, field_name="tipo", value=payload.tipo
    )
    new_row = await close_and_insert(
        session,
        TipoPersona,
        current_uuid=None,
        new_attrs={"tipo": payload.tipo},
        actor_uuid=ctx.actor_uuid,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return TipoPersonaRead.model_validate(new_row)


@_tipo_persona_dedicated_router.put(
    "/{uuid}",
    response_model=TipoPersonaRead,
    dependencies=[Depends(_tipo_persona_dedicated_perm_dep)],
)
async def update_tipo_persona_dedicated(
    payload: TipoPersonaUpdate,
    uuid: uuid_lib.UUID = Path(...),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_tipo_persona_dedicated_issuer_dep),
) -> TipoPersonaRead:
    await _assert_no_vigente_duplicate(
        session, TipoPersona, field_name="tipo", value=payload.tipo, exclude_uuid=uuid
    )
    new_row = await close_and_insert(
        session,
        TipoPersona,
        current_uuid=uuid,
        new_attrs={"tipo": payload.tipo},
        actor_uuid=ctx.actor_uuid,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return TipoPersonaRead.model_validate(new_row)


router.include_router(_tipo_persona_dedicated_router)

_mount_catalog(
    resource="tipo-persona",
    model_cls=TipoPersona,
    read_schema=TipoPersonaRead,
    read_list_schema=TipoPersonaReadList,
    create_schema=TipoPersonaCreate,
    update_schema=TipoPersonaUpdate,
    tenant_free_reads=True,
)


# ---------------------------------------------------------------------------
# 5-type cap on ``tipos-vehiculo`` POST
# ---------------------------------------------------------------------------
#
# The canonical vehicle-type catalog is exactly 5 entries: ``carro``,
# ``moto``, ``bicicleta``, ``patineta``, ``otro`` (seeded by migration
# 0062_canonical_tipos_vehiculo). Without a server-side cap, anyone
# with ``config_catalogo`` could POST arbitrary strings (``"barco"``,
# ``"motoo"`` typo, etc.) and the catalog would grow unbounded — and
# since ``tipos_vehiculo`` is a level-0 sync catalog
# (``sync_entries_v.py:118``), every garbage row replicates to every
# branch. The placa detector hardcodes
# ``["carro", "moto", "bicicleta", "patineta"]`` so typos silently
# bypass it.
#
# Pattern mirrors ``empresa.py:_cantidad_pr_c_router`` (PR-C dedicated
# POST with overlap guard) and the tarifas dedicated router — both
# shadow the factory's POST with a more specialized handler. The
# dedicated POST is mounted FIRST on ``catalogos.router`` so FastAPI's
# order-of-registration resolver routes ``POST /tipos-vehiculo`` here.
# The factory's GET is NOT shadowed (reads stay on the factory /
# ``_register_global_catalog_reads``). The factory's POST and PUT are
# BOTH shadowed at the router registration layer (FastAPI first-match
# wins) — PUT also needs a dedicated handler as of HU-F14.1-T5 (BR3,
# see below).
_TIPOS_VEHICULO_MAX_ACTIVE = 5
_tipos_vehiculo_dedicated_perm_dep = require_permission("config_catalogo")
_tipos_vehiculo_dedicated_issuer_dep = requires_issuer("admin-", "operador-")


async def _count_active_tipos_vehiculo(session: AsyncSession) -> int:
    """Return the count of currently-open tipos_vehiculo rows.

    Mirrors the factory GET filter ``vigente_hasta IS NULL`` (line 199
    of this file). Used by the dedicated POST to enforce the 5-type
    cap before opening a new version.
    """
    stmt = select(func.count(TiposVehiculo.uuid)).where(
        TiposVehiculo.vigente_hasta.is_(None)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


_tipos_vehiculo_dedicated_router = APIRouter(
    prefix="/tipos-vehiculo", tags=["tipos-vehiculo"]
)


@_tipos_vehiculo_dedicated_router.post(
    "",
    response_model=TiposVehiculoRead,
    status_code=201,
    dependencies=[
        Depends(_tipos_vehiculo_dedicated_perm_dep),
    ],
)
async def create_tipo_vehiculo_dedicated(
    payload: TiposVehiculoCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_tipos_vehiculo_dedicated_issuer_dep),
) -> TiposVehiculoRead:
    """Shadow the factory's POST to enforce the canonical 5-type cap.

    Mirrors ``make_router``'s create_endpoint at
    ``api/router_factory.py:269-308`` (close+insert via
    ``repo.versioned.close_and_insert`` + commit + refresh + read-back).
    Two additions: the **5-type cap** (409 ``tipos_vehiculo_max_reached``)
    — if the count of currently-open tipos_vehiculo rows is already
    ``_TIPOS_VEHICULO_MAX_ACTIVE``, reject the POST with the current
    count in the detail so the UI can render an actionable message — and
    the same **duplicate-vigente guard** (409 ``catalogo_duplicado_vigente``)
    already applied to ``tipo-persona``/``tipo-tarifa`` above: without it,
    creating "carro" while a "carro" row is already vigente silently opens
    a second vigente row with the same ``tipo`` (QA backlog cleanup,
    2026-10-02).

    ``log_tx=True`` matches the factory so the audit chain (log_transaccional
    + SHA-256 hash) keeps treating catalog writes uniformly with every
    other versioned write.
    """
    current_count = await _count_active_tipos_vehiculo(session)
    if current_count >= _TIPOS_VEHICULO_MAX_ACTIVE:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "tipos_vehiculo_max_reached",
                "limit": _TIPOS_VEHICULO_MAX_ACTIVE,
                "current": current_count,
            },
        )
    await _assert_no_vigente_duplicate(
        session, TiposVehiculo, field_name="tipo", value=payload.tipo
    )
    new_row = await close_and_insert(
        session,
        TiposVehiculo,
        current_uuid=None,
        new_attrs={"tipo": payload.tipo},
        actor_uuid=ctx.actor_uuid,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return TiposVehiculoRead.model_validate(new_row)


# ---------------------------------------------------------------------------
# BR3 (HU-F14.1-T5, plan.md CU-12 E3) — block PUT when the current version
# has dependent vigente subscriptions
# ---------------------------------------------------------------------------
#
# ``PUT /tipos-vehiculo/{uuid}`` always closes the current open row as step 1
# of ``repo.versioned.close_and_insert`` (``vigente_hasta = NOW()``,
# ``estado = "inactivo"``) and opens a REPLACEMENT row under a brand-new
# ``uuid`` — the business uuid never survives an edit (see that module's
# docstring, "UUID REGENERATION"). No FK-propagation hook is registered for
# ``tipos_vehiculo`` there (only ``Sucursal`` opted in), so every FK still
# pointing at the OLD uuid silently starts referencing a closed
# (``vigente_hasta IS NOT NULL``) row the moment the PUT commits.
#
# ``vehiculos.uuid_tipo_vehiculo`` is exactly such an FK. If a vehicle of
# this type is covered by a currently open ``subscripciones_cliente`` (via
# the ``subscripcion_vehiculos`` junction — there is no direct FK between
# ``subscripciones_cliente`` and ``vehiculos``), closing the current
# ``tipos_vehiculo`` version would orphan that subscriber's vehicle-type
# reference. Mirrors the style of ``admin_usuarios.py``'s "último admin"
# guard (check-before-close, then a typed 409) but inline here since this
# check only guards this one dedicated endpoint.
async def _count_subscripciones_vigentes_dependientes(
    session: AsyncSession, tipo_vehiculo_uuid: uuid_lib.UUID
) -> int:
    """Count vigente ``subscripciones_cliente`` rows covering a vehicle of
    ``tipo_vehiculo_uuid`` (vigente ``vehiculos`` row, joined through the
    vigente ``subscripcion_vehiculos`` junction row)."""
    stmt = (
        select(func.count())
        .select_from(Vehiculos)
        .join(
            SubscripcionVehiculos,
            SubscripcionVehiculos.uuid_vehiculo == Vehiculos.uuid,
        )
        .join(
            SubscripcionesCliente,
            SubscripcionesCliente.uuid == SubscripcionVehiculos.uuid_subscripcion_cliente,
        )
        .where(
            Vehiculos.uuid_tipo_vehiculo == tipo_vehiculo_uuid,
            Vehiculos.vigente_hasta.is_(None),
            SubscripcionVehiculos.vigente_hasta.is_(None),
            SubscripcionesCliente.vigente_hasta.is_(None),
        )
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


@_tipos_vehiculo_dedicated_router.put(
    "/{uuid}",
    response_model=TiposVehiculoRead,
    dependencies=[
        Depends(_tipos_vehiculo_dedicated_perm_dep),
    ],
)
async def update_tipo_vehiculo_dedicated(
    payload: TiposVehiculoUpdate,
    uuid: uuid_lib.UUID = Path(...),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_tipos_vehiculo_dedicated_issuer_dep),
) -> TiposVehiculoRead:
    """Shadow the factory's PUT to enforce BR3 (HU-F14.1-T5).

    Mirrors ``make_router``'s update_endpoint at
    ``api/router_factory.py:312-338`` (close+insert via
    ``repo.versioned.close_and_insert`` + commit + refresh + read-back).
    Two additions: a 409 ``tipo_vehiculo_con_subscripciones_vigentes`` guard
    — see the module comment above — runs BEFORE ``close_and_insert`` so
    the current version is never closed when the dependency exists; and the
    same duplicate-vigente guard (409 ``catalogo_duplicado_vigente``) as
    ``tipo-persona``/``tipo-tarifa`` (QA backlog cleanup, 2026-10-02).
    """
    dependientes = await _count_subscripciones_vigentes_dependientes(session, uuid)
    if dependientes > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "tipo_vehiculo_con_subscripciones_vigentes",
                "uuid": str(uuid),
                "subscripciones_vigentes": dependientes,
            },
        )
    await _assert_no_vigente_duplicate(
        session, TiposVehiculo, field_name="tipo", value=payload.tipo, exclude_uuid=uuid
    )
    new_row = await close_and_insert(
        session,
        TiposVehiculo,
        current_uuid=uuid,
        new_attrs={"tipo": payload.tipo},
        actor_uuid=ctx.actor_uuid,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return TiposVehiculoRead.model_validate(new_row)


# Mount the dedicated router BEFORE the factory mount for ``tipos-vehiculo``
# so FastAPI's first-match resolver routes ``POST``/``PUT /tipos-vehiculo``
# to the cap-enforcing / dependency-guarding handlers above. GET keeps
# flowing through the factory.
router.include_router(_tipos_vehiculo_dedicated_router)


_mount_catalog(
    resource="tipos-vehiculo",
    model_cls=TiposVehiculo,
    read_schema=TiposVehiculoRead,
    read_list_schema=TiposVehiculoReadList,
    create_schema=TiposVehiculoCreate,
    update_schema=TiposVehiculoUpdate,
    tenant_free_reads=True,
)
_mount_catalog(
    resource="tipo-subscripciones",
    model_cls=TipoSubscripciones,
    read_schema=TipoSubscripcionesRead,
    read_list_schema=TipoSubscripcionesReadList,
    create_schema=TipoSubscripcionesCreate,
    update_schema=TipoSubscripcionesUpdate,
    tenant_free_reads=True,
)
# ---------------------------------------------------------------------------
# Duplicate-vigente guard on ``tipo-tarifa`` POST/PUT (business key ``tipo``)
# ---------------------------------------------------------------------------
# Same rationale/pattern as the ``tipo-persona`` dedicated router above.
_tipo_tarifa_dedicated_router = APIRouter(prefix="/tipo-tarifa", tags=["tipo-tarifa"])
_tipo_tarifa_dedicated_perm_dep = require_permission("config_catalogo")
_tipo_tarifa_dedicated_issuer_dep = requires_issuer("admin-", "operador-")


@_tipo_tarifa_dedicated_router.post(
    "",
    response_model=TipoTarifaRead,
    status_code=201,
    dependencies=[Depends(_tipo_tarifa_dedicated_perm_dep)],
)
async def create_tipo_tarifa_dedicated(
    payload: TipoTarifaCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_tipo_tarifa_dedicated_issuer_dep),
) -> TipoTarifaRead:
    await _assert_no_vigente_duplicate(
        session, TipoTarifa, field_name="tipo", value=payload.tipo
    )
    new_row = await close_and_insert(
        session,
        TipoTarifa,
        current_uuid=None,
        new_attrs={"tipo": payload.tipo},
        actor_uuid=ctx.actor_uuid,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return TipoTarifaRead.model_validate(new_row)


@_tipo_tarifa_dedicated_router.put(
    "/{uuid}",
    response_model=TipoTarifaRead,
    dependencies=[Depends(_tipo_tarifa_dedicated_perm_dep)],
)
async def update_tipo_tarifa_dedicated(
    payload: TipoTarifaUpdate,
    uuid: uuid_lib.UUID = Path(...),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_tipo_tarifa_dedicated_issuer_dep),
) -> TipoTarifaRead:
    await _assert_no_vigente_duplicate(
        session, TipoTarifa, field_name="tipo", value=payload.tipo, exclude_uuid=uuid
    )
    new_row = await close_and_insert(
        session,
        TipoTarifa,
        current_uuid=uuid,
        new_attrs={"tipo": payload.tipo},
        actor_uuid=ctx.actor_uuid,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return TipoTarifaRead.model_validate(new_row)


router.include_router(_tipo_tarifa_dedicated_router)

_mount_catalog(
    resource="tipo-tarifa",
    model_cls=TipoTarifa,
    read_schema=TipoTarifaRead,
    read_list_schema=TipoTarifaReadList,
    create_schema=TipoTarifaCreate,
    update_schema=TipoTarifaUpdate,
    tenant_free_reads=True,
)
_mount_catalog(
    resource="tipo-sucursal",
    model_cls=TipoSucursal,
    read_schema=TipoSucursalRead,
    read_list_schema=TipoSucursalReadList,
    create_schema=TipoSucursalCreate,
    update_schema=TipoSucursalUpdate,
    tenant_free_reads=True,
)
_mount_catalog(
    resource="tipo-arqueo",
    model_cls=TipoArqueo,
    read_schema=TipoArqueoRead,
    read_list_schema=TipoArqueoReadList,
    create_schema=TipoArqueoCreate,
    update_schema=TipoArqueoUpdate,
    tenant_free_reads=True,
)
_mount_catalog(
    resource="impuestos",
    model_cls=Impuestos,
    read_schema=ImpuestosRead,
    read_list_schema=ImpuestosReadList,
    create_schema=ImpuestosCreate,
    update_schema=ImpuestosUpdate,
    tenant_free_reads=True,
)
_mount_catalog(
    resource="otros-cobros",
    model_cls=OtrosCobros,
    read_schema=OtrosCobrosRead,
    read_list_schema=OtrosCobrosReadList,
    create_schema=OtrosCobrosCreate,
    update_schema=OtrosCobrosUpdate,
    tenant_free_reads=True,
)
_mount_catalog(
    resource="costos-servicios",
    model_cls=CostosServicios,
    read_schema=CostosServiciosRead,
    read_list_schema=CostosServiciosReadList,
    create_schema=CostosServiciosCreate,
    update_schema=CostosServiciosUpdate,
    tenant_free_reads=True,
)


# ---------------------------------------------------------------------------
# HU-F11.x (REQ-OPS-200) — tipos_vehiculo subset para ingreso con override
# ---------------------------------------------------------------------------


@router.get(
    "/tipos-vehiculo-con-subscripcion",
    response_model=list[TiposVehiculoRead],
    response_model_by_alias=False,
    summary=(
        "HU-F11.x: vigentes ``prod.tipos_vehiculo`` cuyo ``tipo`` aparece "
        "como sufijo de al menos un ``prod.tipo_subscripciones`` vigente. "
        "Usado por ``<IngresoPanel />`` para el dropdown de override del "
        "tipo detectado por regex. Caching 5min (DEC-F4.1-04)."
    ),
    responses={
        200: {"description": "Lista de ``TiposVehiculoRead`` filtrada por subscripcion."},
    },
)
async def list_tipos_vehiculo_con_subscripcion(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[TiposVehiculoRead]:
    """Tipos de vehículo cubiertos por al menos un plan de subscripción
    vigente. La selección se hace por convención del string
    ``tipo_subscripciones.tipo`` (último segmento después de ``_``).

    Operador-issuer: el dropdown es parte del flujo de ingreso. Mismas
    reglas de caché que ``GET /catalogos/tipos-vehiculo`` (catalog reference
    data, no realtime).
    """
    rows = await get_tipos_vehiculo_con_subscripcion(session)
    return [TiposVehiculoRead.model_validate(r) for r in rows]


__all__ = ["router"]