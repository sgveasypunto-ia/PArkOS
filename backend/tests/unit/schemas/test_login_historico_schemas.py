"""HU-F1.15 / T2.2 -- ``schemas/usuarios.py`` Pydantic v2 unit tests.

Pure Pydantic validation tests (no HTTP, no DB). 4 tests pinning the
canonical validators:

* ``extra='forbid'`` Layer 4 defense (blocks smuggling of unknown
  fields like ``actor_uuid``, ``computed_at``, ``cache_key``,
  ``activo``).
* ``limit`` validator (ge=1, le=100 per DEC-LOGIN-04).
* ``estado`` Literal (DEC-LOGIN-10 -- only ``exitoso|fallido|cerrado``
  accepted; NEVER synthetic boolean ``activo``).
* ``estado`` NOT nullable (DEC-LOGIN-10 + ``models/L_S/login.py:64-67``).
"""
from __future__ import annotations

import importlib
import sys
import uuid as uuid_lib
from pathlib import Path

import pytest
from pydantic import ValidationError

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


# ---------------------------------------------------------------------------
# T2.2.1 -- extra='forbid' Layer 4 defense
# ---------------------------------------------------------------------------


def test_login_historico_query_params_extra_forbid() -> None:
    """T2.2: ``LoginHistoricoQueryParams`` rejects unknown fields with ``ValidationError``.

    Layer 4 (REQ-OPS-102): ``extra='forbid'`` blocks client smuggling
    of unknown query fields (e.g. ``actor_uuid``, ``computed_at``,
    ``cache_key``, ``activo``). FastAPI returns 422.
    """
    schemas = importlib.import_module("parkos_core.schemas.usuarios")
    with pytest.raises(ValidationError) as exc_info:
        schemas.LoginHistoricoQueryParams(
            limit=10,
            actor_uuid="x",  # smuggled field, MUST be rejected
        )
    assert "actor_uuid" in str(exc_info.value), (
        f"unknown field actor_uuid must be reported in ValidationError; got {exc_info.value!r}"
    )


# ---------------------------------------------------------------------------
# T2.2.2 -- limit bounds (ge=1, le=100)
# ---------------------------------------------------------------------------


def test_login_historico_query_params_limit_zero_raises() -> None:
    """T2.2: ``limit=0`` raises ``ValidationError`` (ge=1 invariant).

    DEC-LOGIN-04: limit MUST be in [1, 100]. Zero is meaningless
    (empty page) and rejected at the Pydantic edge.
    """
    schemas = importlib.import_module("parkos_core.schemas.usuarios")
    with pytest.raises(ValidationError):
        schemas.LoginHistoricoQueryParams(limit=0)


def test_login_historico_query_params_limit_too_large_raises() -> None:
    """T2.2: ``limit=101`` raises ``ValidationError`` (le=100 invariant).

    DEC-LOGIN-04: limit MUST be in [1, 100]. Values > 100 are
    rejected to bound DB query cost + memory footprint.
    """
    schemas = importlib.import_module("parkos_core.schemas.usuarios")
    with pytest.raises(ValidationError):
        schemas.LoginHistoricoQueryParams(limit=101)


# ---------------------------------------------------------------------------
# T2.2.3 -- estado Literal (DEC-LOGIN-10)
# ---------------------------------------------------------------------------


def test_login_intento_item_estado_literal_rejects_activoboolean() -> None:
    """T2.2: ``estado='activo'`` raises ``ValidationError`` (DEC-LOGIN-10).

    ``prod.login.estado`` carries the REAL [L-S] lifecycle value
    ``exitoso|fallido|cerrado`` -- NEVER a synthetic boolean ``activo``.
    The response shape MUST enforce the Literal at Pydantic edge
    (Layer 4 defense -- the ORM column is ``String(16)``, so any
    string would otherwise slip through).
    """
    schemas = importlib.import_module("parkos_core.schemas.usuarios")
    from datetime import datetime, UTC

    with pytest.raises(ValidationError):
        schemas.LoginIntentoItem(
            uuid=uuid_lib.uuid4(),
            timestamp_evento=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            timestamp_cierre=None,
            estado="activo",  # synthetic boolean -- MUST be rejected
            uuid_sucursal=None,
        )


def test_login_intento_item_estado_null_raises() -> None:
    """T2.2: ``estado=None`` raises ``ValidationError`` (NOT nullable).

    DEC-LOGIN-10 + ``models/L_S/login.py:64-67``: the ORM declares
    ``estado: Mapped[str | None]``, but at the API edge the lifecycle
    ALWAYS stamps a value (exitoso|fallido|cerrado). The response
    shape rejects ``None`` so the client cannot infer a "missing"
    state from the wire payload.
    """
    schemas = importlib.import_module("parkos_core.schemas.usuarios")
    from datetime import datetime, UTC

    with pytest.raises(ValidationError):
        schemas.LoginIntentoItem(
            uuid=uuid_lib.uuid4(),
            timestamp_evento=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            timestamp_cierre=None,
            estado=None,  # NOT nullable at API edge
            uuid_sucursal=None,
        )


def test_login_intento_item_estado_literal_accepts_three_values() -> None:
    """T2.2: ``estado`` accepts the 3 canonical lifecycle values.

    Pin: ``exitoso`` + ``fallido`` + ``cerrado`` round-trip through
    the Pydantic validator (DEC-LOGIN-10).
    """
    schemas = importlib.import_module("parkos_core.schemas.usuarios")
    from datetime import datetime, UTC

    for value in ("exitoso", "fallido", "cerrado"):
        item = schemas.LoginIntentoItem(
            uuid=uuid_lib.uuid4(),
            timestamp_evento=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            timestamp_cierre=None,
            estado=value,
            uuid_sucursal=None,
        )
        assert item.estado == value, f"estado round-trip mismatch for {value!r}"


# ---------------------------------------------------------------------------
# T2.2.4 -- envelope shape (DEC-LOGIN-07)
# ---------------------------------------------------------------------------


def test_login_historico_list_response_envelope_shape() -> None:
    """T2.2: ``LoginHistoricoListResponse`` carries ``{items, next_cursor}``.

    DEC-LOGIN-07: forward-compatible with Parte 2 -- NO ``activo``,
    NO ``count``, NO ``total``, NO ``has_more``. Parte 2 may extend
    the dedicated router without breaking this contract.
    """
    schemas = importlib.import_module("parkos_core.schemas.usuarios")
    from datetime import datetime, UTC

    items = [
        schemas.LoginIntentoItem(
            uuid=uuid_lib.uuid4(),
            timestamp_evento=datetime(2026, 1, 1, 12, 0, i, tzinfo=UTC),
            timestamp_cierre=None,
            estado="exitoso",
            uuid_sucursal=None,
        )
        for i in range(3)
    ]
    resp = schemas.LoginHistoricoListResponse(items=items, next_cursor=None)
    assert len(resp.items) == 3
    assert resp.next_cursor is None

    resp2 = schemas.LoginHistoricoListResponse(items=[], next_cursor=None)
    assert resp2.items == []
    assert resp2.next_cursor is None  # DEC-LOGIN-08: empty -> next_cursor=None
