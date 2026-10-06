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
                                    (membership / subscription / invoice); see
                                    ``_DERIVED_RULES``.

An unsupported policy raises :class:`ValueError`; it never degrades to an
unscoped (leaking) query.
"""
from __future__ import annotations

import uuid as uuid_lib
from collections.abc import Callable
from typing import Any

from sqlalchemy import ColumnElement, Select, or_, select

from ...models.L_E.factura_electronica import FacturaElectronica
from ...models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ...models.V.subscripciones_cliente import SubscripcionesCliente
from ...models.V.usuarios_sucursal import UsuariosSucursal
from ..catalog.schema import SyncCatalogEntry
from .broadcast_resolver import _TRANSITIVE_SUBSCRIPTION_PARENT

# ``derived`` scope rules, registered per catalog entry name. A rule receives the
# entry's ORM model and the pulling branch and returns the WHERE clause. An entry
# declared ``derived`` with no rule here is refused, never pulled unscoped.
_DerivedRule = Callable[[Any, uuid_lib.UUID], ColumnElement[bool]]
_DERIVED_RULES: dict[str, _DerivedRule] = {}


def _branch_member_usuarios(uuid_sucursal: uuid_lib.UUID) -> Select[tuple[uuid_lib.UUID | None]]:
    """Users with a vigente ``usuarios_sucursal`` row at ``uuid_sucursal``.

    Defined once: both ``usuarios`` and ``permisos_usuario`` follow it. The
    branch login validates against this same vigente membership. Served by the
    UK ``(uuid_sucursal, uuid_usuario, vigente_desde)`` and ``ix_usuarios_sucursal_*``.
    """
    return select(UsuariosSucursal.uuid_usuario).where(
        UsuariosSucursal.uuid_sucursal == uuid_sucursal,
        UsuariosSucursal.vigente_hasta.is_(None),
    )


def _usuarios_rule(model: Any, uuid_sucursal: uuid_lib.UUID) -> ColumnElement[bool]:
    return model.uuid.in_(_branch_member_usuarios(uuid_sucursal))


def _permisos_usuario_rule(model: Any, uuid_sucursal: uuid_lib.UUID) -> ColumnElement[bool]:
    return model.uuid_usuario.in_(_branch_member_usuarios(uuid_sucursal))


def _cliente_in_branch_scope(cliente_column: Any, uuid_sucursal: uuid_lib.UUID) -> ColumnElement[bool]:
    """``cliente_column`` references a cliente known to ``uuid_sucursal``.

    A cliente is known to a branch when it holds a ``subscripciones_cliente`` row
    there OR an emitted ``factura_electronica`` there. Defined once: ``clientes``
    (own ``uuid``) and ``clientes_b2b`` (``uuid_cliente``) share it.

    Subscriptions are NOT filtered by ``vigente_hasta``: a renewal inserts a new
    row, and a client whose subscription closed but who was invoiced at the branch
    stays covered by the invoice branch, so a vigencia filter would add no rows
    and would make the rule depend on subscription lifecycle. There is no
    ``sync_identity_alias`` branch: that table has no sucursal column, is
    local-only and has no writer. Indexes: ``ix_subscripciones_cliente_sucursal_cliente``
    and ``ix_factura_electronica_sucursal_cliente`` (migration 0083).
    """
    from_subscription = select(SubscripcionesCliente.uuid_cliente).where(
        SubscripcionesCliente.uuid_sucursal == uuid_sucursal
    )
    from_invoice = select(FacturaElectronica.uuid_cliente).where(
        FacturaElectronica.uuid_sucursal == uuid_sucursal
    )
    return or_(cliente_column.in_(from_subscription), cliente_column.in_(from_invoice))


def _clientes_rule(model: Any, uuid_sucursal: uuid_lib.UUID) -> ColumnElement[bool]:
    return _cliente_in_branch_scope(model.uuid, uuid_sucursal)


def _clientes_b2b_rule(model: Any, uuid_sucursal: uuid_lib.UUID) -> ColumnElement[bool]:
    return _cliente_in_branch_scope(model.uuid_cliente, uuid_sucursal)


def _vehiculos_rule(model: Any, uuid_sucursal: uuid_lib.UUID) -> ColumnElement[bool]:
    """Vehicles linked, through ``subscripcion_vehiculos``, to a subscription sold
    at ``uuid_sucursal``. No vigencia filter on the subscription (a renewal inserts
    a new row) and no ``sync_identity_alias`` branch (no sucursal column, local-only).
    Served by the UK of ``subscripcion_vehiculos`` plus the
    ``subscripciones_cliente (uuid_sucursal, ...)`` indexes of migration 0083.
    """
    from_subscription = (
        select(SubscripcionVehiculos.uuid_vehiculo)
        .join(
            SubscripcionesCliente,
            SubscripcionesCliente.uuid == SubscripcionVehiculos.uuid_subscripcion_cliente,
        )
        .where(SubscripcionesCliente.uuid_sucursal == uuid_sucursal)
    )
    return model.uuid.in_(from_subscription)


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


__all__ = ["build_scope_predicate"]
