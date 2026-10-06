"""Standard customer: constants stay in sync with migration 0088 (offline uuid5)."""
from __future__ import annotations

import importlib.util
import uuid as uuid_lib
from pathlib import Path

from parkos_core import constants

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "packages/parkos_core/migrations/versions/0088_seed_cliente_estandar.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m0088", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_uuid_is_the_documented_uuid5() -> None:
    assert constants.CLIENTE_ESTANDAR_UUID == uuid_lib.uuid5(
        constants.UUID_NAMESPACE, "cliente_estandar_consumidor_final"
    )


def test_tipo_persona_natural_matches_migration_0020() -> None:
    assert constants.TIPO_PERSONA_NATURAL_UUID == uuid_lib.UUID(
        "9ff893fd-e771-5b6a-8b18-6648e47c69d9"
    )


def test_migration_literals_match_constants() -> None:
    m = _load_migration()
    assert uuid_lib.UUID(m._UUID) == constants.CLIENTE_ESTANDAR_UUID
    assert uuid_lib.UUID(m._TIPO_PERSONA_NATURAL) == constants.TIPO_PERSONA_NATURAL_UUID
    assert m._TIPO_IDENTIFICADOR == constants.CLIENTE_ESTANDAR_TIPO_IDENTIFICADOR
    assert m._NUMERO == constants.CLIENTE_ESTANDAR_NUMERO_IDENTIFICACION
    assert m._NOMBRE == constants.CLIENTE_ESTANDAR_NOMBRE
    assert m._VIGENTE_DESDE == constants.CLIENTE_ESTANDAR_VIGENTE_DESDE.isoformat(sep=" ")
    assert m.down_revision == "0087_add_tipo_subscripciones_tipo_vehiculo"
