"""HU-F19.6 — ``ValidacionEventoCreate.estado`` validator (pure Pydantic, no DB).

REQ-25: ``POST /api/v1/validacion-evento`` previously had no way to ever
reach ``estado='rechazado'`` because ``ValidacionEventoCreate`` carried no
``estado`` field at all (``_Base`` has ``extra='forbid'``, so a client could
never pass it) — the endpoint silently forced every transition to
``'validado'``. This test file covers the new ``estado`` field + its
``model_validator(mode="after")`` in isolation, mirroring
``test_workflows_alerta_descartar.py``'s schema-level test style (no DB, no
mocks beyond plain Pydantic construction).

Rules under test:

  - ``estado`` is ONLY meaningful on a transition
    (``uuid_validacion_padre`` present). A root creation
    (``uuid_validacion_padre is None``) MUST NOT carry ``estado`` --
    sending it is rejected with a ``ValidationError`` (422 at the API
    edge) rather than silently ignored.
  - When ``estado='rechazado'``, ``observaciones`` is mandatory and
    non-blank (CU-14 E1 criterion, same rule ``AlertaDescartarEndpoint``
    already enforces for ``alerta``).
  - ``estado='validado'`` has no such ``observaciones`` requirement
    (unchanged behavior from today).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402
from parkos_core.schemas.workflows import ValidacionEventoCreate  # noqa: E402
from pydantic import ValidationError  # noqa: E402


def test_rechazado_without_observaciones_raises() -> None:
    with pytest.raises(ValidationError):
        ValidacionEventoCreate(
            uuid_validacion_padre=uuid_lib.uuid4(),
            estado="rechazado",
        )


def test_rechazado_with_whitespace_only_observaciones_raises() -> None:
    with pytest.raises(ValidationError):
        ValidacionEventoCreate(
            uuid_validacion_padre=uuid_lib.uuid4(),
            estado="rechazado",
            observaciones="   ",
        )


def test_rechazado_with_real_observaciones_is_ok() -> None:
    payload = ValidacionEventoCreate(
        uuid_validacion_padre=uuid_lib.uuid4(),
        estado="rechazado",
        observaciones="Hash no coincide con el payload auditado",
    )
    assert payload.estado == "rechazado"
    assert payload.observaciones == "Hash no coincide con el payload auditado"


def test_validado_without_observaciones_is_ok() -> None:
    """Unchanged behavior: 'validado' has no observaciones requirement."""
    payload = ValidacionEventoCreate(
        uuid_validacion_padre=uuid_lib.uuid4(),
        estado="validado",
    )
    assert payload.estado == "validado"
    assert payload.observaciones is None


def test_root_creation_with_estado_raises() -> None:
    """uuid_validacion_padre=None + estado set -> raises (root always starts pendiente)."""
    with pytest.raises(ValidationError):
        ValidacionEventoCreate(estado="validado")


def test_root_creation_without_estado_is_ok() -> None:
    payload = ValidacionEventoCreate(uuid_sucursal=uuid_lib.uuid4())
    assert payload.uuid_validacion_padre is None
    assert payload.estado is None
