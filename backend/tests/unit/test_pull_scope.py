"""Unit tests for ``sync.motor.pull_scope`` (pull scoping pushed to SQL).

Pure compile-time coverage: each ``broadcast_policy`` is compiled against the
PostgreSQL dialect with literal binds and the resulting WHERE clause is
asserted. No database needed.
"""

from __future__ import annotations

import dataclasses
import uuid as uuid_lib
from datetime import datetime

import pytest
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.motor.pull_scope import build_scope_entry_predicate, build_scope_predicate
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

BRANCH = uuid_lib.UUID("00000000-0000-0000-0000-0000000000a1")


def _sql(table: str, branch: uuid_lib.UUID = BRANCH) -> str | None:
    spec = SYNC_CATALOG_BY_NAME[table]
    predicate = build_scope_predicate(spec, branch)
    if predicate is None:
        return None
    stmt = select(spec.model_cls.uuid).where(predicate)
    compiled = stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
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

_NK_NUMERO = "regexp_replace({t}.numero_identificacion, '[^0-9A-Za-z]', '', 'g')"
_NK_PLACA = "upper(regexp_replace({t}.placa, '[^0-9A-Za-z]', '', 'g'))"

# Any cliente version (open or closed) the branch references, by uuid.
_REFERENCED_CLIENTES = (
    "(SELECT prod.subscripciones_cliente.uuid_cliente FROM prod.subscripciones_cliente "
    f"WHERE prod.subscripciones_cliente.uuid_sucursal = '{BRANCH}' "
    "UNION SELECT prod.factura_electronica.uuid_cliente FROM prod.factura_electronica "
    f"WHERE prod.factura_electronica.uuid_sucursal = '{BRANCH}')"
)


def _cliente_keys(alias: str) -> str:
    return (
        f"(SELECT {alias}.tipo_identificador, {_NK_NUMERO.format(t=alias)} AS regexp_replace_1 "
        f"FROM prod.clientes AS {alias} WHERE {alias}.uuid IN {_REFERENCED_CLIENTES} "
        f"AND {_NK_NUMERO.format(t=alias)} != '')"
    )


def test_clientes_scope_matches_by_natural_key_of_any_referenced_version() -> None:
    spec = SYNC_CATALOG_BY_NAME["clientes"]
    assert spec.broadcast_policy == "derived"
    assert spec.direction == "bidirectional"
    assert _sql("clientes") == (
        f"prod.clientes.uuid IN {_REFERENCED_CLIENTES} OR "
        f"(prod.clientes.tipo_identificador, {_NK_NUMERO.format(t='prod.clientes')}) "
        f"IN {_cliente_keys('clientes_1')} "
        f"AND {_NK_NUMERO.format(t='prod.clientes')} != ''"
    )


def test_clientes_scope_key_includes_tipo_identificador() -> None:
    """Same number under another ``tipo_identificador`` is another client."""
    where = _sql("clientes")
    assert where is not None
    assert "(prod.clientes.tipo_identificador, regexp_replace(" in where
    assert "SELECT clientes_1.tipo_identificador, regexp_replace(" in where


def test_clientes_scope_has_no_vigencia_filter_nor_alias_branch() -> None:
    """A closed subscription still covers its cliente (a renewal inserts a new row and
    an invoice branch covers the rest); ``sync_identity_alias`` has no sucursal column
    and is local-only, so it is not a scope source."""
    where = _sql("clientes")
    assert where is not None
    assert "vigente_hasta" not in where
    assert "sync_identity_alias" not in where


def test_clientes_b2b_scope_follows_its_cliente_by_natural_key() -> None:
    spec = SYNC_CATALOG_BY_NAME["clientes_b2b"]
    assert spec.broadcast_policy == "derived"
    assert spec.direction == "bidirectional"
    assert _sql("clientes_b2b") == (
        f"prod.clientes_b2b.uuid_cliente IN {_REFERENCED_CLIENTES} OR "
        "prod.clientes_b2b.uuid_cliente IN (SELECT clientes_1.uuid "
        "FROM prod.clientes AS clientes_1 "
        f"WHERE (clientes_1.tipo_identificador, {_NK_NUMERO.format(t='clientes_1')}) "
        f"IN {_cliente_keys('clientes_2')} "
        f"AND {_NK_NUMERO.format(t='clientes_1')} != '')"
    )


# ---------------------------------------------------------------------------
# derived — vehiculos follow a subscription at the branch
# ---------------------------------------------------------------------------


_LINKED_VEHICULOS = (
    "(SELECT prod.subscripcion_vehiculos.uuid_vehiculo "
    "FROM prod.subscripcion_vehiculos JOIN prod.subscripciones_cliente "
    "ON prod.subscripciones_cliente.uuid = "
    "prod.subscripcion_vehiculos.uuid_subscripcion_cliente "
    f"WHERE prod.subscripciones_cliente.uuid_sucursal = '{BRANCH}')"
)


def test_vehiculos_scope_matches_by_normalized_placa_of_any_linked_version() -> None:
    spec = SYNC_CATALOG_BY_NAME["vehiculos"]
    assert spec.broadcast_policy == "derived"
    assert spec.direction == "bidirectional"
    assert _sql("vehiculos") == (
        f"prod.vehiculos.uuid IN {_LINKED_VEHICULOS} OR "
        f"{_NK_PLACA.format(t='prod.vehiculos')} IN "
        f"(SELECT {_NK_PLACA.format(t='vehiculos_1')} AS upper_1 "
        "FROM prod.vehiculos AS vehiculos_1 "
        f"WHERE vehiculos_1.uuid IN {_LINKED_VEHICULOS} "
        f"AND {_NK_PLACA.format(t='vehiculos_1')} != '') "
        f"AND {_NK_PLACA.format(t='prod.vehiculos')} != ''"
    )


def test_vehiculos_scope_has_no_vigencia_filter_nor_alias_branch() -> None:
    where = _sql("vehiculos")
    assert where is not None
    assert "vigente_hasta" not in where
    assert "sync_identity_alias" not in where


def test_natural_key_expressions_match_the_identity_indexes() -> None:
    """The scope SQL uses the exact expressions of ``ix_clientes_nk_open`` /
    ``ix_vehiculos_nk_open`` (migration 0008), or the planner could not use them."""
    from pathlib import Path

    migration = next(
        Path(__file__).parents[2].glob("packages/parkos_core/migrations/versions/0008_*.py")
    ).read_text(encoding="utf-8")
    assert "regexp_replace(numero_identificacion, '[^0-9A-Za-z]', '', 'g')" in migration
    assert "upper(regexp_replace(placa, '[^0-9A-Za-z]', '', 'g'))" in migration


# ---------------------------------------------------------------------------
# F3 — a natural key that normalizes to '' is not a key
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "needles"),
    [
        (
            "clientes",
            [
                f"{_NK_NUMERO.format(t='prod.clientes')} != ''",
                f"{_NK_NUMERO.format(t='clientes_1')} != ''",
            ],
        ),
        (
            "clientes_b2b",
            [
                f"{_NK_NUMERO.format(t='clientes_1')} != ''",
                f"{_NK_NUMERO.format(t='clientes_2')} != ''",
            ],
        ),
        (
            "vehiculos",
            [
                f"{_NK_PLACA.format(t='prod.vehiculos')} != ''",
                f"{_NK_PLACA.format(t='vehiculos_1')} != ''",
            ],
        ),
    ],
)
def test_empty_normalized_key_is_guarded_on_both_sides_of_the_comparison(
    table: str, needles: list[str]
) -> None:
    where = _sql(table)
    assert where is not None
    for needle in needles:
        assert needle in where


def test_key_guard_does_not_wrap_the_indexed_expression_in_nullif() -> None:
    """``nullif(expr, '')`` is a different expression: the planner would stop using
    ``ix_clientes_nk_open`` / ``ix_clientes_nk`` / ``ix_vehiculos_nk_open``."""
    for table in ("clientes", "clientes_b2b", "vehiculos"):
        assert "nullif" not in (_sql(table) or "").lower()


# ---------------------------------------------------------------------------
# F1 — scope-entry predicate: the scope rule with a window on the bridge rows
# ---------------------------------------------------------------------------

FLOOR = datetime(2026, 10, 5, 12, 0, 0)
CEILING = datetime(2026, 10, 5, 13, 0, 0)
_GE = "created_at >= '2026-10-05 12:00:00'"
_LT = "created_at < '2026-10-05 13:00:00'"


def _entry(table: str, floor: datetime | None = FLOOR, ceiling: datetime | None = None) -> str:
    spec = SYNC_CATALOG_BY_NAME[table]
    predicate = build_scope_entry_predicate(spec, BRANCH, floor, ceiling)
    assert predicate is not None
    compiled = (
        select(spec.model_cls.uuid)
        .where(predicate)
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    return " ".join(str(compiled).split("WHERE", 1)[1].split())


@pytest.mark.parametrize(
    "table",
    [
        "tipos_vehiculo",
        "resolucion_facturacion",
        "sucursal",
        "configuracion_tolerancias",
        "subscripciones_cliente",
        "subscripcion_vehiculos",
    ],
)
def test_entry_predicate_is_none_for_non_derived_policies(table: str) -> None:
    assert build_scope_entry_predicate(SYNC_CATALOG_BY_NAME[table], BRANCH, FLOOR) is None


def test_scope_predicates_carry_no_created_at_window() -> None:
    for table in (
        "usuarios",
        "permisos_usuario",
        "clientes",
        "clientes_b2b",
        "vehiculos",
        "empresa",
    ):
        assert "created_at" not in (_sql(table) or "")


def test_usuarios_entry_is_the_membership_subselect_windowed() -> None:
    assert _entry("usuarios") == (
        "prod.usuarios.uuid IN (SELECT prod.usuarios_sucursal.uuid_usuario "
        "FROM prod.usuarios_sucursal "
        f"WHERE prod.usuarios_sucursal.uuid_sucursal = '{BRANCH}' "
        "AND prod.usuarios_sucursal.vigente_hasta IS NULL "
        f"AND prod.usuarios_sucursal.{_GE})"
    )


def test_permisos_usuario_entry_follows_the_same_newly_assigned_users() -> None:
    where = _entry("permisos_usuario", ceiling=CEILING)
    assert where.startswith("prod.permisos_usuario.uuid_usuario IN (SELECT")
    assert f"prod.usuarios_sucursal.{_GE} AND prod.usuarios_sucursal.{_LT}" in where


def test_ceiling_is_optional_and_floor_only_window_has_no_upper_bound() -> None:
    assert "created_at <" not in _entry("usuarios")
    assert _LT in _entry("usuarios", ceiling=CEILING)


def test_clientes_entry_windows_both_the_subscription_and_the_invoice() -> None:
    where = _entry("clientes")
    assert f"prod.subscripciones_cliente.{_GE}" in where
    assert f"prod.factura_electronica.{_GE}" in where
    # the empty-key guard survives in the entry rule
    assert f"{_NK_NUMERO.format(t='prod.clientes')} != ''" in where


def test_clientes_b2b_entry_follows_newly_scoped_clientes_by_natural_key() -> None:
    where = _entry("clientes_b2b")
    assert where.startswith("prod.clientes_b2b.uuid_cliente IN (")
    assert where.count(f"prod.subscripciones_cliente.{_GE}") == 2
    assert where.count(f"prod.factura_electronica.{_GE}") == 2


def test_vehiculos_entry_is_new_when_either_the_subscription_or_the_link_is_new() -> None:
    where = _entry("vehiculos")
    assert f"prod.subscripciones_cliente.{_GE}" in where
    assert f"prod.subscripcion_vehiculos.{_GE}" in where
    assert " OR " in where


def test_empresa_entry_is_a_branch_row_created_in_the_window() -> None:
    assert _entry("empresa") == (
        "EXISTS (SELECT prod.sucursal.uuid FROM prod.sucursal "
        f"WHERE prod.sucursal.uuid = '{BRANCH}' AND prod.sucursal.{_GE})"
    )


def test_entry_predicate_for_derived_without_rule_raises() -> None:
    spec = dataclasses.replace(SYNC_CATALOG_BY_NAME["tipos_vehiculo"], broadcast_policy="derived")
    with pytest.raises(ValueError, match="no registered scope rule"):
        build_scope_entry_predicate(spec, BRANCH, FLOOR)
