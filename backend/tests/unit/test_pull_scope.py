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
    assert spec.broadcast_policy == "single_branch" and spec.has_uuid_sucursal
    where = _sql("resolucion_facturacion")
    assert where == f"prod.resolucion_facturacion.uuid_sucursal = '{BRANCH}'"


def test_single_branch_without_uuid_sucursal_filters_on_own_uuid() -> None:
    spec = SYNC_CATALOG_BY_NAME["sucursal"]
    assert spec.broadcast_policy == "single_branch" and not spec.has_uuid_sucursal
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
    assert spec.broadcast_policy == "subscription" and spec.has_uuid_sucursal
    assert _sql("subscripciones_cliente") == (
        f"prod.subscripciones_cliente.uuid_sucursal = '{BRANCH}'"
    )


def test_subscription_transitive_uses_parent_subselect_without_vigencia() -> None:
    spec = SYNC_CATALOG_BY_NAME["subscripcion_vehiculos"]
    assert spec.broadcast_policy == "subscription" and not spec.has_uuid_sucursal
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
