"""Unit tests for ``schemas/admin.py`` (IT-1.4, IT-1.5).

Schema-level only -- no DB, no HTTP. Pydantic's ``extra='forbid'`` from
:class:`_Base` is what makes smuggling hard (C-3 in bi-temporal-crud.md).
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.schemas.admin import (
    AdminAsignarSucursalRequest,
    AdminUsuarioCreateRequest,
    AdminUsuarioRead,
)
from pydantic import ValidationError


def _valid_payload() -> dict:
    return {
        "nombre": "Ana",
        "apellido": "Pérez",
        "cedula": "1234567",
        "email": "ana@parkos.local",
        "password": "Pass1234word",
        "rol": "operador",
        "sucursales_asignadas": [],
    }


class TestAdminUsuarioCreateRequest:
    def test_accepts_a_minimal_payload(self) -> None:
        p = AdminUsuarioCreateRequest(**_valid_payload())
        assert p.email == "ana@parkos.local"
        assert p.rol == "operador"
        assert p.sucursales_asignadas == []

    def test_rejects_short_password(self) -> None:
        with pytest.raises(ValidationError):
            AdminUsuarioCreateRequest(**{**_valid_payload(), "password": "short"})

    def test_rejects_invalid_email(self) -> None:
        with pytest.raises(ValidationError):
            AdminUsuarioCreateRequest(**{**_valid_payload(), "email": "not-an-email"})

    def test_rejects_empty_rol(self) -> None:
        with pytest.raises(ValidationError):
            AdminUsuarioCreateRequest(**{**_valid_payload(), "rol": ""})

    def test_rejects_smuggling_vigente_desde(self) -> None:
        # Defense-in-depth: ``extra='forbid'`` blocks versioning columns
        # at the edge so close+insert is the only writer.
        with pytest.raises(ValidationError):
            AdminUsuarioCreateRequest(
                **{
                    **_valid_payload(),
                    "vigente_desde": "2026-01-01T00:00:00",
                }
            )

    def test_rejects_smuggling_password_hash(self) -> None:
        # The client MUST NOT supply a pre-computed bcrypt hash; the
        # server hashes plaintext. ``extra='forbid'`` enforces this.
        with pytest.raises(ValidationError):
            AdminUsuarioCreateRequest(
                **{
                    **_valid_payload(),
                    "password_hash": "$2b$12$" + "x" * 53,
                }
            )

    def test_accepts_sucursales_asignadas_with_multiple_uuids(self) -> None:
        uuids = [uuid_lib.uuid4(), uuid_lib.uuid4()]
        p = AdminUsuarioCreateRequest(**{**_valid_payload(), "sucursales_asignadas": uuids})
        assert p.sucursales_asignadas == uuids


class TestAdminAsignarSucursalRequest:
    def test_accepts_a_uuid(self) -> None:
        u = uuid_lib.uuid4()
        r = AdminAsignarSucursalRequest(uuid_sucursal=u)
        assert r.uuid_sucursal == u

    def test_rejects_missing_field(self) -> None:
        with pytest.raises(ValidationError):
            AdminAsignarSucursalRequest()  # type: ignore[call-arg]


class TestAdminUsuarioRead:
    def test_drops_password_hash_field(self) -> None:
        # The handler never carries password_hash back to the client.
        # ``model_validate`` on a row WITH password_hash does NOT
        # expose it (no field declared) -- a stray field is silently
        # ignored (Pydantic default), so we test the OPPOSITE: the
        # schema cannot be CONSTRUCTED with password_hash even if a
        # caller tried.
        with pytest.raises(ValidationError):
            AdminUsuarioRead(  # type: ignore[call-arg]
                uuid=uuid_lib.uuid4(),
                password_hash="$2b$12$" + "x" * 53,
                vigente_desde="2026-01-01T00:00:00",
                estado="activo",
                created_at="2026-01-01T00:00:00",
            )
