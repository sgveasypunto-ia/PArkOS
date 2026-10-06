"""motor/pull_scope.py — SQL scoping predicates for ``POST /sync/pull``.

Pushes the per-branch row filter of the cloud→branch pull into the database.
It is the SQL counterpart of :mod:`~parkos_core.sync.motor.broadcast_resolver`
(which decides the same scope in Python, one row at a time): for each
``broadcast_policy`` :func:`build_scope_predicate` returns the WHERE clause
that keeps exactly the rows the resolver would deliver to ``uuid_sucursal``.

  - ``all_branches``              — ``None`` (no filter: every branch gets it).
  - ``single_branch``             — ``uuid_sucursal = :s`` (or ``uuid = :s`` for
                                    an entry that IS the branch identity).
  - ``all_branches_with_override`` — ``uuid_sucursal IS NULL OR = :s``.
  - ``subscription``              — ``uuid_sucursal = :s``; transitively
                                    (``subscripcion_vehiculos``) via
                                    ``uuid_subscripcion_cliente IN (SELECT uuid
                                    FROM subscripciones_cliente WHERE
                                    uuid_sucursal = :s)``. The parent is NOT
                                    filtered by ``vigente_hasta``: a renewal
                                    inserts a new parent row and the link must
                                    survive it.

  - ``derived``                   — a per-entry rule over bridge tables
                                    (membership / subscription / invoice /
                                    ``sucursal.uuid_empresa``); see
                                    ``_DERIVED_RULES``.

Scope ENTRY (``derived`` only). A derived row's own ``created_at`` says nothing
about WHEN it entered the branch's scope: a user created long ago and assigned
to the branch today has an old ``created_at`` but a fresh ``usuarios_sucursal``
bridge row. :func:`build_scope_entry_predicate` returns the same rule restricted
to bridge rows created inside a ``created_at`` window, i.e. "rows brought into
scope by a bridge row the pull cursor is now crossing". The pull delivers those
rows in addition to the ones whose own ``created_at`` crossed the cursor.

An unsupported policy raises :class:`ValueError`; it never degrades to an
unscoped (leaking) query.
"""
from __future__ import annotations

import uuid as uuid_lib
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ColumnElement,
    CompoundSelect,
    Select,
    and_,
    exists,
    func,
    or_,
    select,
    tuple_,
)
from sqlalchemy.orm import aliased

from ...models.L_E.factura_electronica import FacturaElectronica
from ...models.V.clientes import Clientes
from ...models.V.empresa import Empresa
from ...models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ...models.V.subscripciones_cliente import SubscripcionesCliente
from ...models.V.sucursal import Sucursal
from ...models.V.usuarios_sucursal import UsuariosSucursal
from ...models.V.vehiculos import Vehiculos
from ..catalog.schema import SyncCatalogEntry
from .broadcast_resolver import _TRANSITIVE_SUBSCRIPTION_PARENT

# ``derived`` scope rules, registered per catalog entry name. A rule receives the
# entry's ORM model, the pulling branch and an optional bridge-row window, and
# returns the WHERE clause. Without a window it is the SCOPE; with one it is the
# scope ENTRY (see the module docstring): the same rule, but every bridge row it
# follows must have been created inside the window. Defining it once guarantees
# the two can never drift. An entry declared ``derived`` with no rule here is
# refused, never pulled unscoped.
_DerivedRule = Callable[..., ColumnElement[bool]]
_DERIVED_RULES: dict[str, _DerivedRule] = {}


def _window(
    column: Any, since_floor: datetime | None, until_ceiling: datetime | None
) -> list[ColumnElement[bool]]:
    """``created_at`` conditions restricting a bridge table to the pull window."""
    conditions: list[ColumnElement[bool]] = []
    if since_floor is not None:
        conditions.append(column >= since_floor)
    if until_ceiling is not None:
        conditions.append(column < until_ceiling)
    return conditions


def _branch_member_usuarios(
    uuid_sucursal: uuid_lib.UUID,
    since_floor: datetime | None = None,
    until_ceiling: datetime | None = None,
) -> Select[tuple[uuid_lib.UUID | None]]:
    """Users with a vigente ``usuarios_sucursal`` row at ``uuid_sucursal``.

    Defined once: both ``usuarios`` and ``permisos_usuario`` follow it. The
    branch login validates against this same vigente membership. Served by the
    UK ``(uuid_sucursal, uuid_usuario, vigente_desde)`` and ``ix_usuarios_sucursal_*``.
    With a window, only memberships created inside it (users NEWLY assigned).
    """
    return select(UsuariosSucursal.uuid_usuario).where(
        UsuariosSucursal.uuid_sucursal == uuid_sucursal,
        UsuariosSucursal.vigente_hasta.is_(None),
        *_window(UsuariosSucursal.created_at, since_floor, until_ceiling),
    )


def _usuarios_rule(
    model: Any,
    uuid_sucursal: uuid_lib.UUID,
    since_floor: datetime | None = None,
    until_ceiling: datetime | None = None,
) -> ColumnElement[bool]:
    return model.uuid.in_(_branch_member_usuarios(uuid_sucursal, since_floor, until_ceiling))


def _permisos_usuario_rule(
    model: Any,
    uuid_sucursal: uuid_lib.UUID,
    since_floor: datetime | None = None,
    until_ceiling: datetime | None = None,
) -> ColumnElement[bool]:
    """With a window: ALL open permisos of a newly assigned user."""
    return model.uuid_usuario.in_(
        _branch_member_usuarios(uuid_sucursal, since_floor, until_ceiling)
    )


def _nk_numero(column: Any) -> ColumnElement[str]:
    """Natural-key form of ``numero_identificacion``: separators stripped.

    Must stay identical to the expression of ``ix_clientes_nk_open`` (migration
    0008) and to ``identity_lookup._resolve_clientes``.
    """
    return func.regexp_replace(column, "[^0-9A-Za-z]", "", "g")


def _nk_placa(column: Any) -> ColumnElement[str]:
    """Natural-key form of ``placa``: separators stripped, upper-cased.

    Must stay identical to the expression of ``ix_vehiculos_nk_open`` (migration
    0008) and to ``identity_lookup._resolve_vehiculos``.
    """
    return func.upper(func.regexp_replace(column, "[^0-9A-Za-z]", "", "g"))


def _has_nk(normalized: Any) -> ColumnElement[bool]:
    """``normalized <> ''``: an explicit guard, not ``nullif(normalized, '')``.

    A natural key that normalizes to the empty string (``'---'``) is not a key: left
    unguarded it would match every other row whose key is also empty. Wrapping the
    expression in ``nullif`` would change it and the planner could no longer use
    ``ix_clientes_nk_open`` / ``ix_clientes_nk`` / ``ix_vehiculos_nk_open``, which
    index the bare normalizer, so the guard is a separate predicate applied on both
    sides of the key comparison. ``NULL <> ''`` is NULL, i.e. also no match.
    """
    return normalized != ""


def _branch_referenced_clientes(
    uuid_sucursal: uuid_lib.UUID,
    since_floor: datetime | None = None,
    until_ceiling: datetime | None = None,
) -> CompoundSelect[Any]:
    """``uuid`` of every cliente VERSION the branch references.

    A cliente is known to a branch when it holds a ``subscripciones_cliente`` row
    there OR an emitted ``factura_electronica`` there. Subscriptions are NOT
    filtered by ``vigente_hasta`` (a renewal inserts a new row; a client invoiced
    at the branch stays covered). There is no ``sync_identity_alias`` branch: that
    table has no sucursal column, is local-only and has no writer. Indexes:
    ``ix_subscripciones_cliente_sucursal_cliente`` and
    ``ix_factura_electronica_sucursal_cliente`` (migration 0083). With a window,
    only subscriptions / invoices created inside it (clientes NEWLY referenced).
    """
    return select(SubscripcionesCliente.uuid_cliente).where(
        SubscripcionesCliente.uuid_sucursal == uuid_sucursal,
        *_window(SubscripcionesCliente.created_at, since_floor, until_ceiling),
    ).union(
        select(FacturaElectronica.uuid_cliente).where(
            FacturaElectronica.uuid_sucursal == uuid_sucursal,
            *_window(FacturaElectronica.created_at, since_floor, until_ceiling),
        )
    )


def _branch_cliente_keys(
    uuid_sucursal: uuid_lib.UUID,
    since_floor: datetime | None = None,
    until_ceiling: datetime | None = None,
) -> Select[Any]:
    """Natural keys ``(tipo_identificador, numero)`` of the clientes the branch knows.

    The references above point at a cliente by ``uuid``, and a [V] version bump
    (``close_and_insert``) mints a NEW uuid while the references keep the OLD,
    closed one (the invoice table is append-only and nothing repoints them). So
    scope is resolved by NATURAL KEY: the key of ANY version (open or closed) the
    branch references is in scope and every open version carrying it is delivered.
    Defined once: ``clientes`` and ``clientes_b2b`` share it. A key that normalizes
    to '' is excluded (see :func:`_has_nk`).
    """
    known = aliased(Clientes)
    return select(known.tipo_identificador, _nk_numero(known.numero_identificacion)).where(
        known.uuid.in_(_branch_referenced_clientes(uuid_sucursal, since_floor, until_ceiling)),
        _has_nk(_nk_numero(known.numero_identificacion)),
    )


def _clientes_rule(
    model: Any,
    uuid_sucursal: uuid_lib.UUID,
    since_floor: datetime | None = None,
    until_ceiling: datetime | None = None,
) -> ColumnElement[bool]:
    # The uuid branch keeps rows WITHOUT a natural key (NULL tipo/numero, which
    # ``identity_lookup`` cannot resolve either) delivered, as before.
    return or_(
        model.uuid.in_(_branch_referenced_clientes(uuid_sucursal, since_floor, until_ceiling)),
        and_(
            tuple_(model.tipo_identificador, _nk_numero(model.numero_identificacion)).in_(
                _branch_cliente_keys(uuid_sucursal, since_floor, until_ceiling)
            ),
            _has_nk(_nk_numero(model.numero_identificacion)),
        ),
    )


def _clientes_b2b_rule(
    model: Any,
    uuid_sucursal: uuid_lib.UUID,
    since_floor: datetime | None = None,
    until_ceiling: datetime | None = None,
) -> ColumnElement[bool]:
    """A b2b row follows its cliente by natural key: ``uuid_cliente`` may point at a
    closed version of a cliente whose key the branch knows. Resolving those versions
    by key needs the full (non-partial) ``ix_clientes_nk`` of migration 0084; the
    partial ``ix_clientes_nk_open`` does not cover closed versions."""
    version = aliased(Clientes)
    versions_in_scope = select(version.uuid).where(
        tuple_(version.tipo_identificador, _nk_numero(version.numero_identificacion)).in_(
            _branch_cliente_keys(uuid_sucursal, since_floor, until_ceiling)
        ),
        _has_nk(_nk_numero(version.numero_identificacion)),
    )
    return or_(
        model.uuid_cliente.in_(
            _branch_referenced_clientes(uuid_sucursal, since_floor, until_ceiling)
        ),
        model.uuid_cliente.in_(versions_in_scope),
    )


def _branch_linked_vehiculos(
    uuid_sucursal: uuid_lib.UUID,
    since_floor: datetime | None = None,
    until_ceiling: datetime | None = None,
) -> Select[Any]:
    """``uuid`` of every vehiculo VERSION linked, through ``subscripcion_vehiculos``,
    to a subscription sold at ``uuid_sucursal``. No vigencia filter on the
    subscription (a renewal inserts a new row) and no ``sync_identity_alias`` branch
    (no sucursal column, local-only). Served by the UK of ``subscripcion_vehiculos``
    plus the ``subscripciones_cliente (uuid_sucursal, ...)`` indexes of migration 0083.
    With a window, a vehicle is NEWLY linked when EITHER the subscription or the link
    row was created inside it (a vehicle added to an old subscription, or an old
    vehicle on a new subscription).
    """
    query = (
        select(SubscripcionVehiculos.uuid_vehiculo)
        .join(
            SubscripcionesCliente,
            SubscripcionesCliente.uuid == SubscripcionVehiculos.uuid_subscripcion_cliente,
        )
        .where(SubscripcionesCliente.uuid_sucursal == uuid_sucursal)
    )
    if since_floor is None and until_ceiling is None:
        return query
    return query.where(
        or_(
            and_(*_window(SubscripcionesCliente.created_at, since_floor, until_ceiling)),
            and_(*_window(SubscripcionVehiculos.created_at, since_floor, until_ceiling)),
        )
    )


def _vehiculos_rule(
    model: Any,
    uuid_sucursal: uuid_lib.UUID,
    since_floor: datetime | None = None,
    until_ceiling: datetime | None = None,
) -> ColumnElement[bool]:
    """Vehicles linked to the branch, matched by the normalized ``placa`` of ANY
    linked version: the link references a vehiculo by uuid, which a version bump
    replaces. The uuid branch keeps keyless (NULL ``placa``) rows delivered."""
    known = aliased(Vehiculos)
    linked = _branch_linked_vehiculos(uuid_sucursal, since_floor, until_ceiling)
    keys = select(_nk_placa(known.placa)).where(
        known.uuid.in_(linked), _has_nk(_nk_placa(known.placa))
    )
    return or_(
        model.uuid.in_(linked),
        and_(_nk_placa(model.placa).in_(keys), _has_nk(_nk_placa(model.placa))),
    )


def _empresa_rule(
    model: Any,
    uuid_sucursal: uuid_lib.UUID,
    since_floor: datetime | None = None,
    until_ceiling: datetime | None = None,
) -> ColumnElement[bool]:
    """The empresa of the pulling branch, matched by NIT across versions.

    ``sucursal.uuid_empresa`` (nullable, FK ``fk_sucursal_uuid_empresa``) names the
    operator, but an empresa [V] bump (``close_and_insert``) mints a NEW uuid while
    the sucursal keeps pointing at the old, closed one. So the NIT of the
    referenced version is in scope and every open version carrying it is
    delivered (the same natural-key approach as ``clientes``). A branch with NULL
    ``uuid_empresa`` (a real case) -- or an unknown one -- falls back to the open
    empresa row(s): returning zero rows would strip it of NIT, regimen and ticket
    messages. The open-version filter lives in the caller. An empty NIT is not a
    key (see :func:`_has_nk`).

    Scope entry (window given): the branch's own ``sucursal`` row created inside
    the window brings its empresa into scope (a branch created after its empresa;
    the NULL-fallback case follows the same trigger). An in-place UPDATE of
    ``sucursal.uuid_empresa`` leaves ``created_at`` untouched and is NOT
    detectable by a ``created_at`` cursor -- a known limitation.
    """
    if since_floor is not None or until_ceiling is not None:
        return exists(
            select(Sucursal.uuid).where(
                Sucursal.uuid == uuid_sucursal,
                *_window(Sucursal.created_at, since_floor, until_ceiling),
            )
        )
    referenced = (
        select(Sucursal.uuid_empresa)
        .where(Sucursal.uuid == uuid_sucursal, Sucursal.uuid_empresa.is_not(None))
        .scalar_subquery()
    )
    known = aliased(Empresa)
    nits = select(known.nit).where(known.uuid == referenced, _has_nk(known.nit))
    has_reference = exists(
        select(Sucursal.uuid).where(
            Sucursal.uuid == uuid_sucursal, Sucursal.uuid_empresa.is_not(None)
        )
    )
    return or_(~has_reference, model.uuid == referenced, and_(model.nit.in_(nits), _has_nk(model.nit)))


_DERIVED_RULES["empresa"] = _empresa_rule
_DERIVED_RULES["usuarios"] = _usuarios_rule
_DERIVED_RULES["permisos_usuario"] = _permisos_usuario_rule
_DERIVED_RULES["clientes"] = _clientes_rule
_DERIVED_RULES["clientes_b2b"] = _clientes_b2b_rule
_DERIVED_RULES["vehiculos"] = _vehiculos_rule


def build_scope_predicate(
    spec: SyncCatalogEntry, uuid_sucursal: uuid_lib.UUID
) -> ColumnElement[bool] | None:
    """The WHERE clause that scopes ``spec``'s table to ``uuid_sucursal``.

    Returns ``None`` when the policy delivers every row to every branch
    (``all_branches``). Raises :class:`ValueError` for ``broadcast_policy=None``,
    an unrecognized policy, or a transitive ``subscription`` entry with no
    registered parent mapping.
    """
    policy = spec.broadcast_policy
    model: Any = spec.model_cls

    if policy is None:
        raise ValueError(
            f"{spec.name}: broadcast_policy=None has no pull scope — it is not pullable"
        )

    if policy == "all_branches":
        return None

    if policy == "single_branch":
        column = model.uuid_sucursal if spec.has_uuid_sucursal else model.uuid
        return column == uuid_sucursal

    if policy == "all_branches_with_override":
        return or_(model.uuid_sucursal.is_(None), model.uuid_sucursal == uuid_sucursal)

    if policy == "subscription":
        if spec.has_uuid_sucursal:
            return model.uuid_sucursal == uuid_sucursal

        mapping = _TRANSITIVE_SUBSCRIPTION_PARENT.get(spec.name)
        if mapping is None:
            raise ValueError(
                f"{spec.name}: subscription policy with has_uuid_sucursal=False has no "
                "registered transitive-parent mapping — refusing to pull unscoped"
            )
        fk_column, parent_table = mapping
        # Lazy import — same circularity reasoning as broadcast_resolver.
        from ..catalog.sync_catalog import SYNC_CATALOG_BY_NAME

        parent_model: Any = SYNC_CATALOG_BY_NAME[parent_table].model_cls
        parent_uuids = select(parent_model.uuid).where(
            parent_model.uuid_sucursal == uuid_sucursal
        )
        return getattr(model, fk_column).in_(parent_uuids)

    if policy == "derived":
        rule = _DERIVED_RULES.get(spec.name)
        if rule is None:
            raise ValueError(
                f"{spec.name}: derived broadcast_policy has no registered scope rule — "
                "refusing to pull unscoped"
            )
        return rule(model, uuid_sucursal)

    raise ValueError(f"{spec.name}: unsupported broadcast_policy {policy!r} for pull scoping")


def build_scope_entry_predicate(
    spec: SyncCatalogEntry,
    uuid_sucursal: uuid_lib.UUID,
    since_floor: datetime | None,
    until_ceiling: datetime | None = None,
) -> ColumnElement[bool] | None:
    """Rows of a ``derived`` entry BROUGHT INTO SCOPE by a bridge row created in
    ``[since_floor, until_ceiling)``; ``None`` for every other policy.

    A derived row's own ``created_at`` does not say when it entered the branch's
    scope, so the pull also delivers the rows whose bridge row (membership,
    subscription, invoice, link, sucursal) is the one crossing the cursor. It is the
    registered scope rule evaluated with a window on the bridge tables, hence a
    subset of the scope by construction; callers still AND it with
    :func:`build_scope_predicate`.
    """
    if spec.broadcast_policy != "derived":
        return None
    rule = _DERIVED_RULES.get(spec.name)
    if rule is None:
        raise ValueError(
            f"{spec.name}: derived broadcast_policy has no registered scope rule — "
            "refusing to pull unscoped"
        )
    return rule(spec.model_cls, uuid_sucursal, since_floor, until_ceiling)


__all__ = ["build_scope_entry_predicate", "build_scope_predicate"]
