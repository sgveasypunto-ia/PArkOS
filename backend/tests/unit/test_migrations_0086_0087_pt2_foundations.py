"""Static checks for migrations 0086 (permission + alert types) and 0087 (plan vehicle type).

No database needed: asserts the deterministic permission uuid, the revision chain,
the no-physical-DELETE canon and the ORM/catalog wiring. DB-level behaviour is
covered by ``tests/migrations/test_pt2_foundations_schema.py``.
"""
from __future__ import annotations

import importlib
import uuid
from pathlib import Path

import pytest
from parkos_core.models.V.tipo_subscripciones import TipoSubscripciones
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.motor.identity_fk_map import IDENTITY_FK_COLUMNS

_VERSIONS = (
    Path(__file__).resolve().parents[2]
    / "packages" / "parkos_core" / "migrations" / "versions"
)


@pytest.fixture(scope="module")
def m0086():
    import sys

    sys.path.insert(0, str(_VERSIONS))
    return importlib.import_module("0086_seed_permiso_placas_y_alertas")


@pytest.fixture(scope="module")
def m0087():
    import sys

    sys.path.insert(0, str(_VERSIONS))
    return importlib.import_module("0087_add_tipo_subscripciones_tipo_vehiculo")


def test_permission_uuid_is_deterministic_uuid5(m0086) -> None:
    expected = uuid.uuid5(uuid.UUID(m0086._PERMISSION_NAMESPACE), m0086._PERMISSION_CODE)
    assert m0086._PERMISSION_UUID == str(expected)
    assert m0086._PERMISSION_CODE == "gestionar_placas_suscripcion"


def test_alert_types_are_info(m0086) -> None:
    assert {(t, s) for t, _d, s in m0086._ALERT_TYPES} == {
        ("suscripcion_placa_agregada", "info"),
        ("suscripcion_placa_quitada", "info"),
    }


def test_granted_roles_exclude_operators(m0086) -> None:
    assert set(m0086._GRANTED_ROLES) == {"admin", "Administrador", "Supervisor"}


def test_revision_chain(m0086, m0087) -> None:
    assert m0086.down_revision == "0085_pull_rls"
    assert m0087.down_revision == m0086.revision


@pytest.mark.parametrize("name", [
    "0086_seed_permiso_placas_y_alertas.py",
    "0087_add_tipo_subscripciones_tipo_vehiculo.py",
])
def test_no_physical_delete(name: str) -> None:
    src = (_VERSIONS / name).read_text(encoding="utf-8").upper()
    assert "DELETE FROM" not in src


def test_backfill_map_matches_plan_names(m0087) -> None:
    assert m0087._BACKFILL == {
        "MENSUAL_MOTO": "moto",
        "MENSUAL_AUTO": "carro",
        "BIMESTRAL_AUTO": "carro",
        "TRIMESTRAL_AUTO": "carro",
    }
    assert "MENSUAL_EMPRESA" not in m0087._BACKFILL  # stays NULL = any type


def test_orm_and_identity_map_know_the_new_column() -> None:
    assert "uuid_tipo_vehiculo" in TipoSubscripciones.__table__.columns
    assert TipoSubscripciones.__table__.columns["uuid_tipo_vehiculo"].nullable is True
    assert IDENTITY_FK_COLUMNS["tipo_subscripciones"] == frozenset({"uuid_tipo_vehiculo"})
    assert "tipo_subscripciones" in SYNC_CATALOG_BY_NAME
