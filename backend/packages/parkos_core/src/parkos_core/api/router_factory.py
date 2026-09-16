"""parkos_core FastAPI router factory (design §5).

Generates the uniform C+Q+U surface per table:
- ``GET    /<resource>`` — list with cursor pagination (REQ-OP-01)
- ``GET    /<resource>/{uuid}`` — current version (filters by ``vigente_hasta IS NULL``)
- ``GET    /<resource>/{uuid}/history`` — all versions (history endpoint, REQ-05)
- ``POST   /<resource>`` — insert (REQ-03 / REQ-10)
- ``PUT    /<resource>/{uuid}`` — close+insert for [V] (REQ-04)
- NO DELETE — defense in depth (SC-04), enforced at static test layer.

PR1b supports ``repo_kind="versioned"`` and ``"session_cycle"``. Other kinds
(``"append_only"``, ``"event"``, ``"workflow"``) are stubbed in PR1b and
filled in by their respective PRs.

HU-F1.1 (GAP-BE-02, plan.md Parte IV §1.2): the ``order_by`` and the
cursor comparison in ``list_endpoint`` now condition on the same
``hasattr(model_cls, "vigente_desde")`` that already protects the
``vigente_hasta IS NULL`` filter. Models without ``vigente_desde`` (the
15 ``AppendOnlyBase`` ``[A]`` tables, ``Sesion`` ``[L_S]``, and the 3
``[L_E]`` tables) order by ``created_at DESC, uuid ASC`` and carry
``created_at`` (not ``vigente_desde``) in their cursor. The two cases
share the helper :func:`_order_key` so the order-by clause, the cursor
``WHERE``, and the ``next_cursor`` construction are all driven by the
same ``(order_col, cursor_field)`` tuple.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.tenancy import TenantContext
from ..db.engine import get_session
from ..repo.pagination import Cursor, InvalidCursorError
from ..repo.pagination import decode as cursor_decode
from ..repo.pagination import encode as cursor_encode
from ..repo.versioned import close_and_insert, current_version
from .deps import get_tenant_ctx, requires_issuer

if TYPE_CHECKING:
    from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _order_key(model_cls: type) -> tuple[ColumnElement, str]:
    """Return ``(order_col_desc, cursor_field_name)`` for ``model_cls``.

    The cursor field name MUST match a field on :class:`Cursor` — the
    ``list_endpoint`` body reads it back off ``last`` via ``getattr``
    and passes the value straight into the encoded payload. Today the
    two options are:

    - ``("vigente_desde", ...)`` — when ``model_cls`` declares the
      ``vigente_desde`` column (all [V] tables + the [L-W]/[L-S]/[A]
      models that re-declare it locally).
    - ``("created_at", ...)`` — when ``model_cls`` does NOT declare
      ``vigente_desde`` (the 15 ``AppendOnlyBase`` ``[A]`` tables that
      don't re-declare it, ``Sesion`` ``[L_S]``, all 3 ``[L_E]`` tables,
      and the ``AlertTypes`` registry — though the latter is not
      currently mounted via :func:`make_router`).

    ``AuditMixin`` guarantees ``created_at`` on every base that goes
    through the standard mixin chain (VersionedBase / LifecycleEventBase
    / WorkflowBase / SessionBase / AppendOnlyBase). ``AlertTypes``
    re-declares it directly (see ``models/A/alert_types.py``); no
    router in the codebase currently lists it, but if a future HU mounts
    one, the helper resolves correctly.
    """
    if hasattr(model_cls, "vigente_desde"):
        # ``type`` here is a generic placeholder for the ORM model class
        # passed by the caller — mypy can't see the runtime mixin. The
        # runtime ``hasattr`` above guarantees the attribute exists.
        return (model_cls.vigente_desde.desc(), "vigente_desde")  # type: ignore[attr-defined]
    return (model_cls.created_at.desc(), "created_at")  # type: ignore[attr-defined]


def _parse_cursor_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp string from the cursor into a naive ``datetime``.

    The cursor stores ``vigente_desde`` / ``created_at`` as ISO-8601
    strings (REQ-OP-01: ``SC-OP-01`` round-trip via base64url(JSON)).
    SQLAlchemy with the ``asyncpg`` driver does NOT auto-cast
    ``varchar`` to ``timestamp without time zone`` in a ``WHERE``
    comparison (``operator does not exist: timestamp without time zone
    < character varying`` is the symptom — Postgres sees the string
    literal as ``varchar``, not as a timestamp). Pre-HU-F1.1 the bug
    was latent because the only call site (list_endpoint) never
    exercised the comparison against a real DB with a cursor (the
    existing ``test_pagination_cursor.py`` is a pure unit test). HU-F1.1
    is the first integration test that round-trips a cursor through
    Postgres, so the cast has to happen here.
    """
    # ``datetime.fromisoformat`` accepts the ``T`` separator since 3.7
    # and the trailing ``Z`` since 3.11 — same shape ``decode`` validates.
    # The ``.replace("Z", ...)`` is defensive: ``isoformat()`` never
    # emits ``Z`` (it emits ``+00:00`` for tz-aware), but a future HU
    # might hand-craft a cursor with ``Z`` for backward compat with the
    # pre-HU-F1.1 string shape. The ``replace`` is intentional —
    # suppress FURB162 with the noqa.
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))  # noqa: FURB162
    # The DB column is ``DateTime(timezone=False)``: we must drop any
    # tzinfo before binding, otherwise asyncpg sends ``timestamp with
    # time zone`` and Postgres refuses the implicit cast.
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def make_router(
    *,
    resource: str,
    model_cls: type,
    read_schema: type[BaseModel],
    read_list_schema: type[BaseModel],
    create_schema: type[BaseModel] | None = None,
    update_schema: type[BaseModel] | None = None,
    repo_kind: str = "versioned",
    derived_view: str | None = None,
    issuer_required: str,
    permission_required: str | None = None,
    write_enabled: bool = True,
    transition_states: list[str] | None = None,
) -> APIRouter:
    """Build the C+Q+U router for ``model_cls``.

    See design §5 for the full contract.

    Args:
        resource: URL slug (``"tipo-persona"``).
        model_cls: ORM class (e.g. ``TipoPersona``).
        read_schema: Pydantic Read schema.
        read_list_schema: Pydantic ReadList schema.
        create_schema: Pydantic Create schema (or ``None`` if writes disabled).
        update_schema: Pydantic Update schema.
        repo_kind: ``"versioned"`` (PR1b), ``"session_cycle"`` (PR1b),
            ``"append_only"``, ``"event"``, ``"workflow"`` (later PRs).
        derived_view: Optional derived view name (reserved for PR3+).
        issuer_required: Comma-separated issuer prefixes (e.g. ``"admin-,operador-"``).
        permission_required: Optional permission code (REQ-OP-13).
        write_enabled: Whether to mount POST + PUT endpoints.
        transition_states: Reserved for [L-W] tables (later PRs).
    """
    router = APIRouter(prefix=f"/{resource}", tags=[resource])

    issuers = [s.strip() for s in issuer_required.split(",")]
    issuer_dep = requires_issuer(*issuers)

    # Lazy import to avoid the dependency cycle with permissions.py at module
    # load time.
    from ..auth.permissions import require_permission

    perm_dependency = require_permission(permission_required) if permission_required else None

    # --- READ: list with cursor pagination ---
    @router.get("", response_model=read_list_schema)
    async def list_endpoint(
        cursor: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
        ctx: TenantContext = Depends(get_tenant_ctx),
        _claims: None = Depends(issuer_dep),
    ):
        try:
            decoded = cursor_decode(cursor) if cursor else None
        except InvalidCursorError as e:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_cursor", "detail": str(e)},
            )

        order_col, cursor_field = _order_key(model_cls)

        # Base query — only "current" rows for [V] tables (vigente_hasta IS NULL).
        stmt = select(model_cls)
        if hasattr(model_cls, "vigente_hasta"):
            stmt = stmt.where(model_cls.vigente_hasta.is_(None))
        stmt = stmt.order_by(order_col, model_cls.uuid.asc())
        if decoded is not None:
            # The decoded cursor carries the SAME timestamp key the order
            # was built from (the decoder enforces exactly-one), so the
            # ``where`` clause and the ``order_col`` agree on the field.
            # The cursor stores the timestamp as an ISO-8601 string; we
            # parse it back to a naive ``datetime`` so SQLAlchemy binds
            # it as a real timestamp value (see ``_parse_cursor_timestamp``
            # docstring for why the cast is necessary under asyncpg).
            cursor_ts = _parse_cursor_timestamp(getattr(decoded, cursor_field))  # type: ignore[attr-defined]
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

    # --- READ: current single row ---
    @router.get("/{uuid}", response_model=read_schema)
    async def get_endpoint(
        uuid: uuid_lib.UUID = Path(...),
        session: AsyncSession = Depends(get_session),
        _ctx: TenantContext = Depends(get_tenant_ctx),
        _claims: None = Depends(issuer_dep),
    ):
        row = await current_version(session, model_cls, uuid)
        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "uuid": str(uuid)},
            )
        return read_schema.model_validate(row)

    # --- READ: full history (all versions for the same business identity) ---
    if hasattr(model_cls, "vigente_hasta"):

        @router.get("/{uuid}/history", response_model=list[read_schema])
        async def history_endpoint(
            uuid: uuid_lib.UUID = Path(...),
            session: AsyncSession = Depends(get_session),
            _ctx: TenantContext = Depends(get_tenant_ctx),
            _claims: None = Depends(issuer_dep),
        ):
            stmt = (
                select(model_cls)
                .where(model_cls.uuid == uuid)
                .order_by(model_cls.vigente_desde.desc())
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())
            return [read_schema.model_validate(r) for r in rows]

    # --- WRITE: POST (insert) + PUT (close+insert) ---
    extra_deps = [Depends(perm_dependency)] if perm_dependency is not None else []

    if write_enabled and repo_kind == "versioned" and create_schema is not None:

        async def create_endpoint(
            payload,
            session: AsyncSession = Depends(get_session),
            ctx: TenantContext = Depends(get_tenant_ctx),
            _claims: None = Depends(issuer_dep),
        ):
            payload_dict = payload.model_dump(exclude_none=True)
            new_row = await close_and_insert(
                session,
                model_cls,
                current_uuid=None,
                new_attrs=payload_dict,
                actor_uuid=ctx.actor_uuid,
                log_tx=True,
            )
            await session.commit()
            await session.refresh(new_row)
            return read_schema.model_validate(new_row)

        # Real defect confirmed via manual QA + HTTP-level regression test
        # (test_router_factory_payload_body_binding.py): this module has
        # ``from __future__ import annotations`` (PEP 563), so a plain
        # ``payload: create_schema`` annotation would be stored as the
        # STRING "create_schema" — and ``create_schema`` is a local closure
        # variable of THIS ``make_router`` call, not a module global, so
        # FastAPI's ``typing.get_type_hints()`` could never resolve it.
        # Left unannotated (as before this fix), FastAPI fell back to
        # treating ``payload`` as a required ``str`` QUERY parameter,
        # never the JSON request body — every ``create``/``update``
        # endpoint this factory ever built was broken against a real HTTP
        # client. Setting ``__annotations__`` directly stores the REAL
        # class object (not a string), so ``get_type_hints()`` returns it
        # as-is with nothing left to resolve.
        create_endpoint.__annotations__["payload"] = create_schema
        router.post(
            "",
            response_model=read_schema,
            status_code=201,
            dependencies=extra_deps,
        )(create_endpoint)

        if update_schema is not None:

            async def update_endpoint(
                payload,
                uuid: uuid_lib.UUID = Path(...),
                session: AsyncSession = Depends(get_session),
                ctx: TenantContext = Depends(get_tenant_ctx),
                _claims: None = Depends(issuer_dep),
            ):
                payload_dict = payload.model_dump(exclude_none=True)
                new_row = await close_and_insert(
                    session,
                    model_cls,
                    current_uuid=uuid,
                    new_attrs=payload_dict,
                    actor_uuid=ctx.actor_uuid,
                    log_tx=True,
                )
                await session.commit()
                await session.refresh(new_row)
                return read_schema.model_validate(new_row)

            # Same PEP-563 fix as create_endpoint above.
            update_endpoint.__annotations__["payload"] = update_schema
            router.put(
                "/{uuid}",
                response_model=read_schema,
                dependencies=extra_deps,
            )(update_endpoint)

    elif write_enabled and repo_kind == "session_cycle" and create_schema is not None:
        # Session-cycle tables expose only POST (record event) and PUT (close).
        # PR7 fleshes out the full set.
        @router.post("", response_model=read_schema, status_code=201)
        async def create_session_endpoint(
            payload,  # FastAPI injects create_schema instance
            session: AsyncSession = Depends(get_session),
            ctx: TenantContext = Depends(get_tenant_ctx),
            _claims: None = Depends(issuer_dep),
        ):
            from ..repo.session_cycle import record_login

            row = await record_login(
                session,
                usuario_uuid=payload.uuid_usuario,
                sucursal_uuid=payload.uuid_sucursal,
                actor_uuid=ctx.actor_uuid,
            )
            await session.commit()
            await session.refresh(row)
            return read_schema.model_validate(row)

    # The derived_view argument is reserved for PR3+ (e.g. V_FACTURA_ESTADO).
    # It's accepted here so future tables can pass it without changing the
    # factory signature; PR1b emits no route for it.
    _ = derived_view
    _ = transition_states

    return router


__all__ = ["make_router"]
