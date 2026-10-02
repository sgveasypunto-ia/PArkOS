"""HU-F19.4 / REQ-26-W-ALERTA-DESCARTADA — alerta "descartar" transition.

One POST endpoint on a dedicated ``APIRouter`` — mirrors the DEC-TKT-06
precedent set by ``workflows_reimpresion.py`` (HU-F1.11): the
factory-mounted router at ``api/v1/workflows.py`` stays reserved for the
C+Q GET mount (``write_enabled=False`` for ``alerta`` — see that module's
docstring, "Custom transition endpoints ship in PR7"; this HU IS that
custom transition). Any write on an ``[L-W]`` workflow table ships as a
dedicated custom endpoint reusing ``repo.workflow.append_transition`` /
``STATE_MACHINES`` directly — same pattern ``dian.cloud_router`` uses for
``envio_dian`` / ``validacion_evento``, and the same pattern
``workflows_reimpresion.anular_reimpresion_ticket`` uses for the sibling
``reimpresion-ticket`` resource.

**Design note — ``write_enabled`` was intentionally NOT flipped on the
generic factory mount.** plan.md's HU-F19.4 BR3 literal wording says
"``write_enabled`` pasa de ``False`` a ``True``"; flipping that kwarg on
``_mount_workflow(resource="alerta", ...)`` in ``api/v1/workflows.py``
would instead wire up the GENERIC ``POST``/``PUT`` endpoints built by
``router_factory.make_router`` for ``repo_kind="versioned"``, which call
``repo.versioned.close_and_insert`` — the WRONG write helper for an
``[L-W]`` workflow chain (no ``STATE_MACHINES`` validation, no
``append_transition`` semantics). ``api/v1/workflows.py``'s own module
docstring already warns about this exact trap. The HU's own "ARCHIVOS DE
REFERENCIA" section additionally says to reuse
``append_transition``/``STATE_MACHINES`` "mismo patrón que
``envio_dian``/``validacion_evento``" — i.e. a bespoke endpoint, not the
factory flag. This module is that bespoke endpoint; ``workflows.py`` is
left untouched.

``STATE_MACHINES['alerta']`` (``repo/workflow.py``) already allows
``abierta|en_revision -> resuelta``; ``resuelta`` is terminal (``[]``), so
re-discarding an already-resolved alert is rejected with 409.

Permission: ``descartar_alerta`` — already seeded (canonical permission
set, migration ``0002_seed_permisos_canonicos.py``; deterministic UUID
assigned in ``0019_deterministic_permisos_uuids.py``). Enforced here via
an explicit ``require_permission`` dependency, per BR3's explicit mention
of ``permission_required="descartar_alerta"`` — stricter than the
``workflows_reimpresion`` precedent (which relies on issuer-only +
role-grant enforcement without an explicit ``require_permission`` call).

HU-F19.5 / T1 — ``alerta``'s entire GET surface also lives here now.

**Design note — why the GET list is hand-built, not factory-mounted.**
``router_factory.make_router`` has no per-resource query-extension hook:
its ``list_endpoint`` is one fixed closure shared verbatim by every
``repo_kind="versioned"`` mount (``reimpresion-ticket``/``anulaciones``/
``reclamos`` all go through it today). HU-F19.5 needs ``GET
/workflows/alerta`` to (a) ``LEFT JOIN prod.alert_types`` for
``severity`` (BR4: ``null`` when ``tipo_alerta`` has no catalog row,
never an ``INNER JOIN`` that would silently drop the alert), (b) accept
``uuid_sucursal``/``tipo_alerta``/``estado``/``severidad``/``desde``/
``hasta`` filters the factory's ``list_endpoint`` doesn't parse at all,
and (c) resolve ``admin-`` cross-branch (every branch the admin is
currently assigned to, not one-branch-or-global). None of that is
expressible by passing more kwargs into :func:`make_router` -- doing it
there would mean carving resource-specific branches into the ONE
``list_endpoint`` closure the other 3 resources also call, i.e. touching
shared code for an ``alerta``-only requirement. So instead: ``alerta`` is
no longer passed to ``_mount_workflow`` in ``api/v1/workflows.py`` at
all (see that module's docstring), and its full GET surface --
list (extended), ``GET /{uuid}`` (``current_version``, unchanged shape),
``GET /{uuid}/history`` (unchanged shape) -- is reimplemented here by
hand, reusing ``repo.pagination``'s ``Cursor``/``encode``/``decode`` so
the ``{items, next_cursor}`` wire contract matches every other list
endpoint in the codebase byte-for-byte. The ``/workflows/alerta`` URL
surface itself does not change for clients; only which module owns it
does.

**Design note — authorization is NOT ``get_tenant_ctx``/``BranchScope``
for the list endpoint.** ``get_tenant_ctx`` resolves to exactly ONE
``sucursal_uuid`` (``operador-``: JWT-pinned; ``admin-``: the
``X-Sucursal-Context`` header, or ``None`` = "global", i.e. NO tenant
filter at all -- see ``auth.tenancy.BranchScope``'s own docstring on why
that "global mode" is unsafe to rely on for an unfiltered cross-branch
read). Neither shape fits "every branch THIS admin is currently assigned
to, cursor-paginated, optionally narrowed by ``uuid_sucursal``". This
endpoint instead follows the HU-F19.1 ``admin_views.py`` precedent
(``sync_log_list``/``sync_conflict_list``/``dashboard_resumen``): read
the issuer claims directly off ``requires_issuer``, and for ``admin-``
resolve the permitted-branch set fresh via
``db.tenancy.extract_sucursales_permitidas_fresh`` on every request (not
the JWT's login-time ``sucursales_permitidas`` snapshot). ``operador-``
stays pinned to its own JWT ``sucursal`` claim, mirroring the tenant
check ``descartar_alerta`` already does below. ``GET /{uuid}`` and
``GET /{uuid}/history`` keep the OLD factory behavior unchanged (still
``get_tenant_ctx``, unused beyond the issuer-gate side effect) --
HU-F19.5 only asked for the list endpoint's filters/severity/cross-branch
read; changing the single-row routes' scoping is out of scope here.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.permissions import require_permission
from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...db.tenancy import extract_sucursales_permitidas_fresh
from ...models.A.alert_types import AlertTypes
from ...models.L_W.alerta import Alerta
from ...repo import workflow as repo_workflow
from ...repo.pagination import Cursor, InvalidCursorError
from ...repo.pagination import decode as cursor_decode
from ...repo.pagination import encode as cursor_encode
from ...repo.versioned import current_version
from ...repo.workflow import _now_naive
from ...schemas.workflows import (
    AlertaDescartarEndpoint,
    AlertaListItem,
    AlertaListResponse,
    AlertaRead,
)
from ..deps import requires_issuer
from . import _helpers

_descartar_alerta_issuer_dep = requires_issuer("operador-", "admin-")
_descartar_alerta_perm_dep = require_permission("descartar_alerta")

# Same issuer pair as the old factory mount's ``_ROUTER_CONFIG["alerta"]``
# (T-PR6-10) -- reads are issuer-gated only, no permission dependency
# (make_router's list/get/history endpoints never depended on one either).
_alerta_read_issuer_dep = requires_issuer("operador-", "admin-")

# New dedicated router (mirrors DEC-TKT-06). HU-F19.5: now carries
# ``alerta``'s ENTIRE route surface (GET list/single/history + the
# HU-F19.4 ``descartar`` POST) -- see module docstring.
router = APIRouter(prefix="/workflows/alerta", tags=["workflows"])

_ESTADO_VALUES = Literal["abierta", "en_revision", "resuelta"]
_SEVERIDAD_VALUES = Literal["info", "warning", "critical"]


@router.get(
    "",
    response_model=AlertaListResponse,
    summary=(
        "HU-F19.5 / T1: cursor-paginated alerta inbox, LEFT JOIN "
        "prod.alert_types for severity (BR4), with uuid_sucursal/"
        "tipo_alerta/estado/severidad/desde/hasta filters."
    ),
    responses={
        400: {"description": "missing_sucursal_context (admin- with no assigned branches)"},
        403: {
            "description": (
                "unauthorized_sucursal_context (admin- names a branch outside "
                "scope) | tenant_scope_violation (operador- names another branch)"
            )
        },
        422: {"description": "rango_fecha_invalido (desde > hasta)"},
    },
)
async def list_alertas(
    claims: Annotated[dict[str, Any], Depends(_alerta_read_issuer_dep)],
    session: AsyncSession = Depends(get_session),  # noqa: B008
    uuid_sucursal: Annotated[
        uuid_lib.UUID | None,
        Query(description="Branch filter. Defaults to every branch in scope."),
    ] = None,
    tipo_alerta: Annotated[str | None, Query()] = None,
    estado: Annotated[_ESTADO_VALUES | None, Query()] = None,
    severidad: Annotated[
        _SEVERIDAD_VALUES | None,
        Query(description="Filters on prod.alert_types.severity."),
    ] = None,
    desde: Annotated[
        date | None,
        Query(description="Inclusive UTC start date, filtered on timestamp_evento."),
    ] = None,
    hasta: Annotated[
        date | None,
        Query(description="Inclusive UTC end date, filtered on timestamp_evento."),
    ] = None,
    cursor: Annotated[str | None, Query(description="Opaque cursor, vigente_desde-keyed.")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AlertaListResponse:
    """``GET /workflows/alerta`` -- see module docstring for the two design notes.

    Current-row only (``vigente_hasta IS NULL``), ordered
    ``vigente_desde DESC, uuid ASC`` -- same order the old factory mount
    used (``router_factory._order_key`` picks ``vigente_desde`` for
    ``Alerta`` since the model re-declares that column).
    """
    iss = claims.get("iss", "")
    # Same prefix-derivation as ``auth.tenancy.get_tenant_ctx`` -- deliberately
    # NOT calling that dependency here (see module docstring).
    issuer_prefix = iss.split("-")[0] + "-" if "-" in iss else ""
    actor_uuid = uuid_lib.UUID(claims["sub"])

    target_sucursales: set[uuid_lib.UUID] | None
    if issuer_prefix == "operador-":
        sucursal_str = claims.get("sucursal")
        if not sucursal_str:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "missing_sucursal_in_jwt",
                    "detail": "operador tokens require 'sucursal' claim",
                },
            )
        try:
            own_sucursal = uuid_lib.UUID(sucursal_str)
        except (ValueError, TypeError) as e:
            raise HTTPException(
                status_code=401,
                detail={"error": "malformed_sucursal_in_jwt", "detail": str(e)},
            ) from e
        if uuid_sucursal is not None and uuid_sucursal != own_sucursal:
            raise HTTPException(
                status_code=403,
                detail={"error": "tenant_scope_violation", "uuid_sucursal": str(uuid_sucursal)},
            )
        target_sucursales = {own_sucursal}
    else:
        # admin- (the only other issuer ``_alerta_read_issuer_dep`` allows).
        permitidas = set(
            await extract_sucursales_permitidas_fresh(session, actor_uuid=actor_uuid)
        )
        if not permitidas:
            raise HTTPException(
                status_code=400,
                detail={"error": "missing_sucursal_context"},
            )
        if uuid_sucursal is not None:
            if uuid_sucursal not in permitidas:
                raise HTTPException(
                    status_code=403,
                    detail={"error": "unauthorized_sucursal_context"},
                )
            target_sucursales = {uuid_sucursal}
        else:
            target_sucursales = permitidas

    if desde is not None and hasta is not None and desde > hasta:
        raise HTTPException(
            status_code=422,
            detail={"error": "rango_fecha_invalido"},
        )

    try:
        decoded_cursor = cursor_decode(cursor) if cursor else None
    except InvalidCursorError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_cursor", "detail": str(exc)},
        ) from exc

    # BR4: LEFT JOIN -- never INNER. A tipo_alerta with no catalog row
    # (out-of-catalog, or a seed drift) must still list, with severity=null.
    stmt = (
        select(Alerta, AlertTypes.severity)
        .outerjoin(AlertTypes, AlertTypes.tipo_alerta == Alerta.tipo_alerta)
        .where(Alerta.vigente_hasta.is_(None))
        .where(Alerta.uuid_sucursal.in_(target_sucursales))
    )
    if tipo_alerta is not None:
        stmt = stmt.where(Alerta.tipo_alerta == tipo_alerta)
    if estado is not None:
        stmt = stmt.where(Alerta.estado == estado)
    if severidad is not None:
        stmt = stmt.where(AlertTypes.severity == severidad)
    if desde is not None:
        stmt = stmt.where(func.date(Alerta.timestamp_evento) >= desde)
    if hasta is not None:
        stmt = stmt.where(func.date(Alerta.timestamp_evento) <= hasta)

    stmt = stmt.order_by(Alerta.vigente_desde.desc(), Alerta.uuid.asc())
    if decoded_cursor is not None:
        if decoded_cursor.vigente_desde is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_cursor",
                    "detail": "cursor missing vigente_desde (required for alerta listing)",
                },
            )
        cursor_ts = datetime.fromisoformat(
            decoded_cursor.vigente_desde.replace("Z", "+00:00")  # noqa: FURB162
        ).replace(tzinfo=None)
        cursor_uuid = uuid_lib.UUID(decoded_cursor.uuid)
        stmt = stmt.where(
            (Alerta.vigente_desde < cursor_ts)
            | ((Alerta.vigente_desde == cursor_ts) & (Alerta.uuid > cursor_uuid))
        )
    stmt = stmt.limit(limit + 1)

    rows = (await session.execute(stmt)).all()
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last_alerta, _last_severity = rows[-1]
        next_cursor = cursor_encode(
            Cursor(vigente_desde=last_alerta.vigente_desde.isoformat(), uuid=str(last_alerta.uuid))
        )

    items = [
        AlertaListItem(**AlertaRead.model_validate(alerta_row).model_dump(), severity=severity)
        for alerta_row, severity in rows
    ]
    return AlertaListResponse(items=items, next_cursor=next_cursor)


@router.get(
    "/{uuid}",
    response_model=AlertaRead,
    summary="Current version of one prod.alerta chain row (unchanged from the old factory mount).",
)
async def get_alerta(
    uuid: uuid_lib.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_alerta_read_issuer_dep),
) -> AlertaRead:
    # current_version's T is bound to VersionedBase; Alerta is a
    # WorkflowBase that re-declares vigente_hasta/vigente_desde/estado by
    # hand (see models/L_W/alerta.py docstring) rather than inheriting
    # VersionedMixin, so it is structurally but not nominally compatible.
    # The old factory `get_endpoint` never hit this because it received
    # `model_cls: type` (erased, so T unified with Any); calling with the
    # concrete class here makes mypy check the bound for real.
    row = await current_version(session, Alerta, uuid)  # type: ignore[type-var]
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "uuid": str(uuid)},
        )
    return AlertaRead.model_validate(row)


@router.get(
    "/{uuid}/history",
    response_model=list[AlertaRead],
    summary="Full version history of one prod.alerta chain row (unchanged from the old factory mount).",
)
async def get_alerta_history(
    uuid: uuid_lib.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_alerta_read_issuer_dep),
) -> list[AlertaRead]:
    stmt = (
        select(Alerta)
        .where(Alerta.uuid == uuid)
        .order_by(Alerta.vigente_desde.desc())
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    return [AlertaRead.model_validate(r) for r in rows]


@router.post(
    "/{uuid}/descartar",
    response_model=AlertaRead,
    status_code=201,
    summary=(
        "HU-F19.4 / REQ-26-W-ALERTA-DESCARTADA: INSERT NEW prod.alerta row "
        "with estado='resuelta', uuid_alerta_padre=<tip.uuid>. NEVER UPDATE "
        "the existing chain tip."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {"description": "alerta_not_found (V1)"},
        409: {"description": "alerta_ya_resuelta (V2 terminal)"},
        422: {"description": "Pydantic validation (observaciones vacía | missing_field)"},
    },
)
async def descartar_alerta(
    response: Response,
    uuid: uuid_lib.UUID,
    payload: AlertaDescartarEndpoint,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_descartar_alerta_issuer_dep),
    _perm: None = Depends(_descartar_alerta_perm_dep),  # requires 'descartar_alerta'
) -> AlertaRead:
    """REQ-26-W-ALERTA-DESCARTADA: discard/resolve an alerta via a NEW chain row.

    Sequence (mirrors ``workflows_reimpresion.anular_reimpresion_ticket``):
        1. issuer + permission claims (DI)
        2. V1 chain tip via ``read_chain_tip``; ``ChainNotFoundError`` -> 404
        3. tenant scope post-V1 (403 if operador- cross-branch)
        4. V2 terminal-state guard (409 if the tip is already 'resuelta')
        5. V3 INSERT NEW ``prod.alerta`` row via ``append_transition``
           (NEVER UPDATE the tip) — ``observaciones`` is stashed in
           ``datos_nuevos`` (no dedicated column; see module docstring)
        6. single ``await session.commit()`` + no-store header + response
    """
    no_store = _helpers.no_store_headers()

    # --- Step 2: V1 chain tip via read_chain_tip. ----------------------
    try:
        tip = await repo_workflow.read_chain_tip(
            session,
            Alerta,
            root_uuid=uuid,
            parent_fk_column="uuid_alerta_padre",
        )
    except repo_workflow.ChainNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"error": "alerta_not_found", "uuid": str(uuid)},
            headers=no_store,
        ) from None

    tip_row = (
        await session.execute(select(Alerta).where(Alerta.uuid == tip["uuid_actual"]))
    ).scalar_one_or_none()
    if tip_row is None:
        # Defensive: read_chain_tip returned a uuid that no longer exists.
        raise HTTPException(
            status_code=404,
            detail={"error": "alerta_not_found", "uuid": str(uuid)},
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1). -------------------------------
    if ctx.issuer_prefix == "operador-" and (
        ctx.sucursal_uuid is None or tip_row.uuid_sucursal != ctx.sucursal_uuid
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation", "uuid": str(uuid)},
            headers=no_store,
        )

    # --- Step 4: V2 terminal-state guard. -------------------------------
    if tip["estado"] == "resuelta":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "alerta_ya_resuelta",
                "uuid": str(uuid),
                "estado_actual": "resuelta",
            },
            headers=no_store,
        )

    # --- Step 5: V3 INSERT NEW prod.alerta row (NEVER UPDATE the tip). -
    new_row = await repo_workflow.append_transition(
        session,
        Alerta,
        actor_uuid=ctx.actor_uuid,
        new_attrs={
            "uuid_sucursal": tip_row.uuid_sucursal,
            # The actor performing THIS transition, not the alert's
            # original reporter (mirrors
            # workflows_reimpresion.anular_reimpresion_ticket).
            "uuid_usuario": ctx.actor_uuid,
            "uuid_arqueo": tip_row.uuid_arqueo,
            "tipo_alerta": tip_row.tipo_alerta,
            "valor_diferencia_efectivo": tip_row.valor_diferencia_efectivo,
            "valor_diferencia_datafono": tip_row.valor_diferencia_datafono,
            "timestamp_evento": _now_naive(),
            # No dedicated `observaciones` column on prod.alerta (unlike
            # validacion_evento) — reuse the existing free-form JSONB
            # payload column (module docstring).
            "datos_nuevos": {"observaciones": payload.observaciones},
            "estado": "resuelta",
        },
        parent_uuid=tip["uuid_actual"],
        parent_fk_column="uuid_alerta_padre",
        log_tx=True,
    )

    # --- Step 6: single commit + response shape. ------------------------
    await session.commit()  # single commit

    _helpers.apply_no_store_header(response)
    return AlertaRead.model_validate(new_row)


__all__ = ["router"]
