"""Unit tests for ``sync.motor.pull_scope`` (pull scoping pushed to SQL).

Pure compile-time coverage: each ``broadcast_policy`` is compiled against the
PostgreSQL dialect with literal binds and the resulting WHERE clause is
asserted. No database needed.
"""
from __future__ import annotations

import dataclasses
import uuid as uuid_lib

import pytest
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.motor.pull_scope import build_scope_predicate
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

BRANCH = uuid_lib.UUID("00000000-0000-0000-0000-0000000000a1")


def _sql(table: str, branch: uuid_lib.UUID = BRANCH) -> str | None:
    spec = SYNC_CATALOG_BY_NAME[table]
    predicate = build_scope_predicate(spec, branch)
    if predicate is None:
        return None
    stmt = select(spec.model_cls.uuid).where(predicate)
    compiled = stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    # Keep only the WHERE clause so assertions don't depend on the SELECT list.
    return " ".join(str(compiled).split("WHERE", 1)[1].split())


def test_all_branches_has_no_predicate() -> None:
    spec = SYNC_CATALOG_BY_NAME["tipos_vehiculo"]
    assert spec.broadcast_policy == "all_branches"
    assert build_scope_predicate(spec, BRANCH) is None


def test_single_branch_filters_on_uuid_sucursal() -> None:
    spec = SYNC_CATALOG_BY_NAME["resolucion_facturacion"]
    assert spec.broadcast_policy == "single_branch"
    assert spec.has_uuid_sucursal
    where = _sql("resolucion_facturacion")
    assert where == f"prod.resolucion_facturacion.uuid_sucursal = '{BRANCH}'"


def test_single_branch_without_uuid_sucursal_filters_on_own_uuid() -> None:
    spec = SYNC_CATALOG_BY_NAME["sucursal"]
    assert spec.broadcast_policy == "single_branch"
    assert not spec.has_uuid_sucursal
    assert _sql("sucursal") == f"prod.sucursal.uuid = '{BRANCH}'"


def test_override_accepts_global_default_or_own_row() -> None:
    spec = SYNC_CATALOG_BY_NAME["configuracion_tolerancias"]
    assert spec.broadcast_policy == "all_branches_with_override"
    where = _sql("configuracion_tolerancias")
    assert where == (
        "prod.configuracion_tolerancias.uuid_sucursal IS NULL OR "
        f"prod.configuracion_tolerancias.uuid_sucursal = '{BRANCH}'"
    )


def test_subscription_direct_filters_on_uuid_sucursal() -> None:
    spec = SYNC_CATALOG_BY_NAME["subscripciones_cliente"]
    assert spec.broadcast_policy == "subscription"
    assert spec.has_uuid_sucursal
    assert _sql("subscripciones_cliente") == (
        f"prod.subscripciones_cliente.uuid_sucursal = '{BRANCH}'"
    )


def test_subscription_transitive_uses_parent_subselect_without_vigencia() -> None:
    spec = SYNC_CATALOG_BY_NAME["subscripcion_vehiculos"]
    assert spec.broadcast_policy == "subscription"
    assert not spec.has_uuid_sucursal
    where = _sql("subscripcion_vehiculos")
    assert where is not None
    assert where.startswith("prod.subscripcion_vehiculos.uuid_subscripcion_cliente IN (SELECT")
    assert "FROM prod.subscripciones_cliente" in where
    assert f"prod.subscripciones_cliente.uuid_sucursal = '{BRANCH}'" in where
    # A renewal creates a new parent row: the parent must not be vigencia-filtered.
    assert "vigente_hasta" not in where


def test_predicate_binds_the_given_branch() -> None:
    other = uuid_lib.UUID("00000000-0000-0000-0000-0000000000b2")
    assert str(other) in (_sql("resolucion_facturacion", other) or "")
    assert str(BRANCH) not in (_sql("resolucion_facturacion", other) or "")


def test_unsupported_policy_raises_instead_of_going_unscoped() -> None:
    spec = dataclasses.replace(SYNC_CATALOG_BY_NAME["resolucion_facturacion"])
    object.__setattr__(spec, "broadcast_policy", "bogus")
    with pytest.raises(ValueError, match="bogus"):
        build_scope_predicate(spec, BRANCH)


def test_none_policy_raises() -> None:
    spec = SYNC_CATALOG_BY_NAME["ingreso"]
    assert spec.broadcast_policy is None
    with pytest.raises(ValueError):
        build_scope_predicate(spec, BRANCH)


def test_transitive_subscription_without_mapping_raises() -> None:
    spec = dataclasses.replace(SYNC_CATALOG_BY_NAME["subscripcion_vehiculos"])
    object.__setattr__(spec, "name", "unmapped_subscription")
    with pytest.raises(ValueError, match="transitive"):
        build_scope_predicate(spec, BRANCH)


def test_derived_without_registered_rule_raises_instead_of_going_unscoped() -> None:
    spec = dataclasses.replace(SYNC_CATALOG_BY_NAME["tipos_vehiculo"], broadcast_policy="derived")
    with pytest.raises(ValueError, match="no registered scope rule"):
        build_scope_predicate(spec, BRANCH)


# ---------------------------------------------------------------------------
# derived — usuarios / permisos_usuario follow a vigente usuarios_sucursal row
# ---------------------------------------------------------------------------

_MEMBERS_SUBSELECT = (
    "(SELECT prod.usuarios_sucursal.uuid_usuario FROM prod.usuarios_sucursal "
    f"WHERE prod.usuarios_sucursal.uuid_sucursal = '{BRANCH}' "
    "AND prod.usuarios_sucursal.vigente_hasta IS NULL)"
)


def test_usuarios_scope_is_vigente_branch_membership() -> None:
    spec = SYNC_CATALOG_BY_NAME["usuarios"]
    assert spec.broadcast_policy == "derived"
    assert _sql("usuarios") == f"prod.usuarios.uuid IN {_MEMBERS_SUBSELECT}"


def test_permisos_usuario_scope_reuses_the_membership_subselect() -> None:
    spec = SYNC_CATALOG_BY_NAME["permisos_usuario"]
    assert spec.broadcast_policy == "derived"
    assert _sql("permisos_usuario") == f"prod.permisos_usuario.uuid_usuario IN {_MEMBERS_SUBSELECT}"


# ---------------------------------------------------------------------------
# derived — clientes / clientes_b2b follow a subscription or an invoice
# ---------------------------------------------------------------------------

_CLIENTES_FROM_SUBSCRIPTION = (
    "(SELECT prod.subscripciones_cliente.uuid_cliente FROM prod.subscripciones_cliente "
    f"WHERE prod.subscripciones_cliente.uuid_sucursal = '{BRANCH}')"
)
_CLIENTES_FROM_INVOICE = (
    "(SELECT prod.factura_electronica.uuid_cliente FROM prod.factura_electronica "
    f"WHERE prod.factura_electronica.uuid_sucursal = '{BRANCH}')"
)


def test_clientes_scope_is_subscription_or_invoice_at_the_branch() -> None:
    spec = SYNC_CATALOG_BY_NAME["clientes"]
    assert spec.broadcast_policy == "derived"
    assert spec.direction == "bidirectional"
    assert _sql("clientes") == (
        f"prod.clientes.uuid IN {_CLIENTES_FROM_SUBSCRIPTION} "
        f"OR prod.clientes.uuid IN {_CLIENTES_FROM_INVOICE}"
    )


def test_clientes_scope_has_no_vigencia_filter_nor_alias_branch() -> None:
    """A closed subscription still covers its cliente (a renewal inserts a new row and
    an invoice branch covers the rest); ``sync_identity_alias`` has no sucursal column
    and is local-only, so it is not a scope source."""
    where = _sql("clientes")
    assert where is not None
    assert "vigente_hasta" not in where
    assert "sync_identity_alias" not in where


def test_clientes_b2b_scope_follows_its_cliente() -> None:
    spec = SYNC_CATALOG_BY_NAME["clientes_b2b"]
    assert spec.broadcast_policy == "derived"
    assert spec.direction == "bidirectional"
    assert _sql("clientes_b2b") == (
        f"prod.clientes_b2b.uuid_cliente IN {_CLIENTES_FROM_SUBSCRIPTION} "
        f"OR prod.clientes_b2b.uuid_cliente IN {_CLIENTES_FROM_INVOICE}"
    )


# ---------------------------------------------------------------------------
# derived — vehiculos follow a subscription at the branch
# ---------------------------------------------------------------------------


def test_vehiculos_scope_is_subscription_at_the_branch() -> None:
    spec = SYNC_CATALOG_BY_NAME["vehiculos"]
    assert spec.broadcast_policy == "derived"
    assert spec.direction == "bidirectional"
    assert _sql("vehiculos") == (
        "prod.vehiculos.uuid IN (SELECT prod.subscripcion_vehiculos.uuid_vehiculo "
        "FROM prod.subscripcion_vehiculos JOIN prod.subscripciones_cliente "
        "ON prod.subscripciones_cliente.uuid = "
        "prod.subscripcion_vehiculos.uuid_subscripcion_cliente "
        f"WHERE prod.subscripciones_cliente.uuid_sucursal = '{BRANCH}')"
    )


def test_vehiculos_scope_has_no_vigencia_filter_nor_alias_branch() -> None:
    where = _sql("vehiculos")
    assert where is not None
    assert "vigente_hasta" not in where
    assert "sync_identity_alias" not in where
