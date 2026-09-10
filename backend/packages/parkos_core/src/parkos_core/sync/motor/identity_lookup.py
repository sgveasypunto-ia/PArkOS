"""motor/identity_lookup.py — resolves ``HookContext.open_version`` for
real (T-PR5-005 follow-up, real defect confirmed via manual QA + real HTTP
identity-divergence exercise, 2026-09-10).

**The defect this closes.** ``identity_reconciler`` (``hooks/impls/
identity_reconciler.py``) classifies an arriving row into ``noop`` /
``forward`` / ``historical`` entirely from ``HookContext.open_version`` —
"the currently-open local version for the SAME normalized natural key,
resolved by the caller" (that module's own docstring). ``motor/apply_row.py
::apply_row`` only ever FORWARDS whatever ``open_version`` it is given —
it never resolves it. ``SyncMotor.apply_row`` (``motor/sync_motor.py`` —
the ONLY caller reachable from the three real production paths:
``api/v1/sync_router.py::sync_events``, ``jobs/sync_cloud.py::
_apply_pending_batch_once``, ``jobs/sync_sucursal.py::
_pull_and_apply_catalog``) never passed it either, so ``open_version`` was
``None`` on every real call ever made — the reconciler always saw an
arriving row as brand new, never closed the prior open version, and TWO
(observed: THREE, across cloud + branch) simultaneously-open rows for the
same natural key resulted from a real HTTP push+pull cycle.

``tests/integration/test_identity_invariant.py`` never caught this because
it calls ``apply_row.apply_row`` directly, resolving ``open_version``
itself (its own ``_row_dict(open_row)``, from a query IT constructs) and
passing it explicitly — it never exercises ``SyncMotor.apply_row``'s real
wiring.

**The fix.** This module resolves the SAME "currently open version for
this normalized natural key" query ``test_identity_invariant.py`` was
doing by hand, generically enough to wire into ``SyncMotor.apply_row``
itself — so every real caller gets it automatically, with no per-call-site
opt-in. Dispatches by table name using the EXACT functional-index
expressions migration ``0008_add_identity_nk_indexes.py`` already created
for the 3 original identity masters (``ix_clientes_nk_open``,
``ix_clientes_b2b_nk_open``, ``ix_vehiculos_nk_open``) — a per-table
dispatch, not a fragile "build SQL from an arbitrary Python normalizer"
generalization, mirroring the same per-table-registry style already used by
``motor/broadcast_resolver.py``'s ``_TRANSITIVE_SUBSCRIPTION_PARENT``.

**2026-09-10 extension — every ``[V]`` table, not just the 3 identity
masters.** Auditing every ``SYNC_CATALOG`` ``[V]`` entry against
``modelo_datos_er.mmd``'s own UK01 markers found 20 more tables
(``usuarios``, ``permisos``, every ``tipo_*``/``tipos_vehiculo`` catalog,
``impuestos``, ``otros_cobros``, ``costos_servicios``, ``empresa``,
``permisos_usuario``, ``configuracion_tolerancias``,
``configuracion_seguridad``, ``sucursal``, ``resolucion_facturacion``,
``usuarios_sucursal``, ``tarifas_sucursal``,
``cantidad_vehiculos_sucursal``, ``subscripcion_vehiculos``) with a real,
ER-declared natural key and NO reconciliation at all — a rename/update on
any of them (``cloud_to_branch`` single-authority tables included: only one
side ever WRITES them, but that write still mints a fresh uuid via
``close_and_insert``, and no sync trigger anywhere is ``AFTER UPDATE``, see
``sync_motor.py``'s own comment) left the receiving node with a
permanently-stale open row forever — the exact "(a) two simultaneously-open
versions" / "(b) a node that never learns a version closed" hazard the
original identity-reconciliation fix only closed for 3 tables.

None of these 20 need the 3 originals' SQL-functional-index normalization
(their natural keys are plain codes/UUIDs already stored in canonical
form, per the ER model — no ``regexp_replace``/``upper`` needed). They are
served by ``_resolve_generic`` below, built directly from ``spec.
natural_key`` — no per-table SQL required, unlike the 3 originals.
``configuracion_tolerancias``/``configuracion_seguridad`` are the one
exception needing their own tiny resolver: their single natural-key column
(``uuid_sucursal``) is NULLABLE, and NULL is itself a meaningful identity
(the global-default row) rather than "value unknown" — ``_resolve_generic``
deliberately refuses to resolve when ANY natural-key value is ``None``
(the same "return None -> ordinary insert, nothing to reconcile" safety
the 3 original resolvers use for a missing key value), which is the WRONG
default for exactly these two tables.

A table that declares ``natural_key`` with NO registered resolver here (a
future catalog entry someone adds a natural key to without reading this
module) is no longer possible to get wrong silently: ``_resolve_generic``
is now the universal fallback for anything not in ``_RESOLVERS``, so a new
``[V]`` natural-key entry is reconciled correctly out of the box unless its
key needs special normalization (functional-index or NULL-is-meaningful) —
in which case it belongs in ``_RESOLVERS`` explicitly, same as the 5
entries already there.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from ..catalog.schema import SyncCatalogEntry


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Every column of an ORM instance as a plain dict — mirrors
    ``test_identity_invariant.py``'s own ``_row_dict`` helper exactly, since
    that is the shape ``identity_reconciler`` already expects."""
    mapper = sa_inspect(type(row))
    return {column.name: getattr(row, column.name) for column in mapper.columns}


async def _resolve_clientes(session: AsyncSession, payload: dict[str, Any]) -> Any | None:
    from ...models.V.clientes import Clientes

    tipo_identificador = payload.get("tipo_identificador")
    numero_identificacion = payload.get("numero_identificacion")
    if tipo_identificador is None or numero_identificacion is None:
        return None
    stmt = (
        select(Clientes)
        .where(
            Clientes.tipo_identificador == tipo_identificador,
            func.regexp_replace(Clientes.numero_identificacion, "[^0-9A-Za-z]", "", "g")
            == func.regexp_replace(numero_identificacion, "[^0-9A-Za-z]", "", "g"),
            Clientes.vigente_hasta.is_(None),
        )
        # Defensive against pre-existing data that already violates the R17
        # "at most one open version" invariant (e.g. rows created before
        # this fix existed) — picks the most recently created open row
        # rather than crashing with MultipleResultsFound; the invariant
        # itself is enforced going forward by this very resolution.
        .order_by(Clientes.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def _resolve_clientes_b2b(session: AsyncSession, payload: dict[str, Any]) -> Any | None:
    from ...models.V.clientes_b2b import ClientesB2B

    uuid_cliente = payload.get("uuid_cliente")
    if uuid_cliente is None:
        return None
    stmt = (
        select(ClientesB2B)
        .where(
            ClientesB2B.uuid_cliente == uuid_cliente,
            ClientesB2B.vigente_hasta.is_(None),
        )
        .order_by(ClientesB2B.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def _resolve_vehiculos(session: AsyncSession, payload: dict[str, Any]) -> Any | None:
    from ...models.V.vehiculos import Vehiculos

    placa = payload.get("placa")
    if placa is None:
        return None
    stmt = (
        select(Vehiculos)
        .where(
            func.upper(func.regexp_replace(Vehiculos.placa, "[^0-9A-Za-z]", "", "g"))
            == func.upper(func.regexp_replace(placa, "[^0-9A-Za-z]", "", "g")),
            Vehiculos.vigente_hasta.is_(None),
        )
        .order_by(Vehiculos.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def _resolve_nullable_uuid_sucursal_scope(
    model_cls: type, session: AsyncSession, payload: dict[str, Any]
) -> Any | None:
    """Shared body for ``configuracion_tolerancias``/``configuracion_seguridad``
    — natural key is ``(uuid_sucursal,)`` where NULL means "the global
    default row", a real identity, not a missing value.
    """
    value = payload.get("uuid_sucursal")
    column = model_cls.uuid_sucursal
    stmt = (
        select(model_cls)
        .where(
            column.is_(None) if value is None else column == value,
            model_cls.vigente_hasta.is_(None),
        )
        .order_by(model_cls.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def _resolve_configuracion_tolerancias(
    session: AsyncSession, payload: dict[str, Any]
) -> Any | None:
    from ...models.V.configuracion_tolerancias import ConfiguracionTolerancias

    return await _resolve_nullable_uuid_sucursal_scope(ConfiguracionTolerancias, session, payload)


async def _resolve_configuracion_seguridad(
    session: AsyncSession, payload: dict[str, Any]
) -> Any | None:
    from ...models.V.configuracion_seguridad import ConfiguracionSeguridad

    return await _resolve_nullable_uuid_sucursal_scope(ConfiguracionSeguridad, session, payload)


async def _resolve_generic(
    session: AsyncSession, spec: SyncCatalogEntry, payload: dict[str, Any]
) -> Any | None:
    """Universal natural-key resolver for any ``[V]`` table whose
    ``natural_key`` columns need no special normalization — built directly
    from ``spec.natural_key``/``spec.model_cls``, no per-table SQL.

    Mirrors the 3 hand-written resolvers' own safety default: if ANY
    natural-key column is missing from ``payload`` (``None``), this refuses
    to resolve (returns ``None`` -> ordinary insert, nothing to reconcile)
    rather than risk matching an unrelated row that also happens to have a
    NULL value in that column. Tables where NULL is itself a meaningful
    identity (``configuracion_tolerancias``/``configuracion_seguridad``) are
    registered in ``_RESOLVERS`` instead and never reach this function.
    """
    model_cls = spec.model_cls
    conditions = []
    for column_name in spec.natural_key:
        value = payload.get(column_name)
        if value is None:
            return None
        conditions.append(getattr(model_cls, column_name) == value)
    stmt = (
        select(model_cls)
        .where(*conditions, model_cls.vigente_hasta.is_(None))
        .order_by(model_cls.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


#: table name -> resolver, for the entries needing SPECIAL handling (SQL
#: functional-index normalization, or a NULL natural-key value that is
#: itself a meaningful identity). Every other ``natural_key``-declaring
#: entry falls through to ``_resolve_generic`` in ``resolve_open_version``
#: below — see this module's docstring for why that is now safe as a
#: universal default.
_RESOLVERS: dict[str, Any] = {
    "clientes": _resolve_clientes,
    "clientes_b2b": _resolve_clientes_b2b,
    "vehiculos": _resolve_vehiculos,
    "configuracion_tolerancias": _resolve_configuracion_tolerancias,
    "configuracion_seguridad": _resolve_configuracion_seguridad,
}


async def resolve_open_version(
    session: AsyncSession, spec: SyncCatalogEntry, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Return the currently-open row (as a plain dict) matching ``payload``'s
    normalized natural key for ``spec``, or ``None`` when ``spec`` declares
    no natural key (nothing to reconcile) or no open row matches (the
    arriving row is genuinely new).
    """
    if not spec.natural_key:
        return None
    resolver = _RESOLVERS.get(spec.name)
    row = (
        await resolver(session, payload)
        if resolver is not None
        else await _resolve_generic(session, spec, payload)
    )
    if row is None:
        return None
    return _row_to_dict(row)


__all__ = ["resolve_open_version"]
