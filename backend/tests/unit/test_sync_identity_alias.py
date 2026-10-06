"""Unit tests for the identity-alias writer and the FK-column-filtered remap.

No database: the session is a mock that records the statements it receives.
The catalog-derived column lists are pinned as golden sets so a model/catalog
change that widens or narrows the remap surface is a conscious edit.
"""

from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.motor.identity_fk_map import IDENTITY_FK_COLUMNS
from parkos_core.sync.motor.sync_motor import (
    identity_fk_columns,
    record_identity_alias,
    remap_foreign_keys,
    remap_payload_with_aliases,
)

ACTOR = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")
U_B = uuid_lib.uuid4()
U_A = uuid_lib.uuid4()


def _session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    return session


async def test_record_identity_alias_inserts_idempotently() -> None:
    session = _session()
    assert await record_identity_alias(session, "clientes", U_B, U_A, ACTOR) is True
    stmt = str(session.execute.await_args.args[0])
    params = session.execute.await_args.args[1]
    assert "INSERT INTO prod.sync_identity_alias" in stmt
    assert "ON CONFLICT (uuid_origen) DO NOTHING" in stmt
    assert params["origen"] == U_B
    assert params["resuelto"] == U_A
    assert params["tabla"] == "clientes"


@pytest.mark.parametrize(
    ("origen", "resuelto"),
    [(U_A, U_A), (None, U_A), (U_B, None), ("not-a-uuid", U_A)],
)
async def test_record_identity_alias_skips_equal_or_missing(origen, resuelto) -> None:
    session = _session()
    assert await record_identity_alias(session, "clientes", origen, resuelto, ACTOR) is False
    session.execute.assert_not_awaited()


async def test_record_identity_alias_accepts_string_uuids() -> None:
    session = _session()
    assert await record_identity_alias(session, "clientes", str(U_B), str(U_A), ACTOR) is True
    assert session.execute.await_args.args[1]["origen"] == U_B


def test_fk_columns_golden_lists() -> None:
    """Columns that point at an identity-reconciled master, per dependent."""
    cols = {n: identity_fk_columns(SYNC_CATALOG_BY_NAME[n]) for n in IDENTITY_FK_COLUMNS}
    # clientes dependents
    assert cols["subscripciones_cliente"] == {"uuid_cliente", "uuid_tipo_subscripcion"}
    assert cols["clientes_b2b"] == {"uuid_cliente"}
    assert cols["factura_electronica"] == {"uuid_cliente", "uuid_resolucion_facturacion"}
    # vehiculos dependents
    assert cols["subscripcion_vehiculos"] == {"uuid_vehiculo"}
    # usuarios dependents
    assert cols["usuarios_sucursal"] == {"uuid_usuario"}
    assert cols["permisos_usuario"] == {"uuid_permiso", "uuid_usuario"}
    assert cols["sesion"] == {"uuid_usuario", "uuid_usuario_cierre"}
    # a table with no FK onto a reconciled master has nothing to remap
    assert identity_fk_columns(SYNC_CATALOG_BY_NAME["tipo_subscripciones"]) == frozenset()


def test_fk_columns_never_include_identity_audit_or_sucursal_columns() -> None:
    for name, cols in IDENTITY_FK_COLUMNS.items():
        assert not cols & {"uuid", "created_by", "current_uuid", "uuid_sucursal"}, name
        assert name != "sucursal"


def test_fk_map_entries_are_catalog_tables_with_real_columns() -> None:
    for name, cols in IDENTITY_FK_COLUMNS.items():
        spec = SYNC_CATALOG_BY_NAME[name]
        assert cols <= set(spec.model_cls.__table__.c.keys()), name


def test_remap_foreign_keys_only_touches_alias_matching_fk_columns() -> None:
    spec = SYNC_CATALOG_BY_NAME["subscripciones_cliente"]
    other = uuid_lib.uuid4()
    payload = {
        "uuid": str(U_B),  # same value as the alias key: identity must not be rewritten
        "created_by": str(U_B),
        "current_uuid": str(U_B),
        "uuid_cliente": str(U_B),
        "uuid_tipo_subscripcion": str(other),
    }
    out = remap_foreign_keys(spec, payload, {U_B: U_A})
    assert out["uuid_cliente"] == U_A
    assert out["uuid"] == str(U_B)
    assert out["created_by"] == str(U_B)
    assert out["current_uuid"] == str(U_B)
    assert out["uuid_tipo_subscripcion"] == str(other)
    assert payload["uuid_cliente"] == str(U_B), "input is never mutated"


async def test_remap_payload_skips_the_lookup_without_candidates() -> None:
    session = _session()
    # a spec with no FK to a reconciled master: no query at all
    spec = SYNC_CATALOG_BY_NAME["tipo_subscripciones"]
    payload = {"uuid": str(U_B)}
    assert await remap_payload_with_aliases(session, spec, payload) is payload
    # a spec with FK columns but no value in them: no query either
    spec = SYNC_CATALOG_BY_NAME["subscripciones_cliente"]
    payload = {"uuid": str(U_B), "uuid_cliente": None}
    assert await remap_payload_with_aliases(session, spec, payload) is payload
    session.execute.assert_not_awaited()


async def test_remap_payload_runs_one_lookup_and_rewrites() -> None:
    session = _session()
    result = MagicMock()
    result.all.return_value = [MagicMock(uuid_origen=U_B, uuid_resuelto=U_A)]
    session.execute.return_value = result
    spec = SYNC_CATALOG_BY_NAME["subscripciones_cliente"]
    out = await remap_payload_with_aliases(
        session, spec, {"uuid": str(uuid_lib.uuid4()), "uuid_cliente": str(U_B)}
    )
    assert out["uuid_cliente"] == U_A
    assert session.execute.await_count == 1


async def test_remap_payload_leaves_payload_untouched_without_alias() -> None:
    session = _session()
    result = MagicMock()
    result.all.return_value = []
    session.execute.return_value = result
    spec = SYNC_CATALOG_BY_NAME["subscripciones_cliente"]
    payload = {"uuid": str(uuid_lib.uuid4()), "uuid_cliente": str(U_B)}
    assert await remap_payload_with_aliases(session, spec, payload) == payload
