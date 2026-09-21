"""HU-F12.1 / T-B1-1 -- Pydantic schemas for ``GET /operacion/mi-turno``.

Pure Pydantic v2 validation tests, no HTTP, no DB. Codifies the 7-field
``MiTurnoRead`` shape (REQ-OPS-184, DA-F12.1-1 / DA-F12.1-9 drift gates):

  uuid_sesion:                   UUID
  uuid_sucursal:                 UUID
  timestamp_calculo:             datetime
  ingresos_count:                int       (default 0)
  salidas_count:                 int       (default 0)
  total_cobrado_efectivo_cop:    Decimal   (default 0)
  total_cobrado_datafono_cop:    Decimal   (default 0)

``extra='forbid'`` (inherited from :class:`_Base`) rejects any extra
field the BE might smuggle in (defense in depth).

S1: 7-field Pydantic parses + each count/decimal carries the documented
    default ``0``.
S2: ``extra='forbid'`` rejects a hypothetical 8th field (``cufe``
    injection or similar BE drift) — defense against BE field drift.
S3: Key-set equality with FE Zod ``MiTurnoSchema`` — the BE / FE schema
    lock (DA-F12.1-1 / DA-F12.1-9 GATING).
S4: ``uuid_sesion`` is REQUIRED (REJECT if absent).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from decimal import Decimal
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


# The 7-field BE / FE contract (REQ-OPS-184 + REQ-OPS-189). Must remain
# identical to the FE Zod shape. Both ends of the wire MUST be locked
# here; drift = broken integration test in CI.
EXPECTED_KEYS = frozenset(
    {
        "uuid_sesion",
        "uuid_sucursal",
        "timestamp_calculo",
        "ingresos_count",
        "salidas_count",
        "total_cobrado_efectivo_cop",
        "total_cobrado_datafono_cop",
    },
)


def _make_minimal_payload() -> dict[str, object]:
    return {
        "uuid_sesion": str(uuid_lib.uuid4()),
        "uuid_sucursal": str(uuid_lib.uuid4()),
        "timestamp_calculo": "2026-09-21T08:00:00",
    }


def test_mi_turno_read_parses_minimal_payload_with_zero_defaults() -> None:
    """S1 (REQ-OPS-184): minimal payload parses + count/decimal fields default to 0."""
    from parkos_core.schemas.operacion import MiTurnoRead

    payload = _make_minimal_payload()
    parsed = MiTurnoRead.model_validate(payload)

    # The 4 count/decimal fields MUST default to 0 (per spec: BE always
    # returns 200 with zeros, never 404). Decimal, not int — Pydantic
    # serializes JSON numbers to Decimal by spec.
    assert parsed.ingresos_count == 0
    assert parsed.salidas_count == 0
    assert parsed.total_cobrado_efectivo_cop == Decimal("0")
    assert parsed.total_cobrado_datafono_cop == Decimal("0")
    # UUID round-trips.
    assert isinstance(parsed.uuid_sesion, uuid_lib.UUID)
    assert isinstance(parsed.uuid_sucursal, uuid_lib.UUID)


def test_mi_turno_read_parses_full_payload_preserving_values() -> None:
    """S1b: full payload parses with the supplied counts + decimals preserved."""
    from parkos_core.schemas.operacion import MiTurnoRead

    payload = {
        **_make_minimal_payload(),
        "ingresos_count": 3,
        "salidas_count": 2,
        "total_cobrado_efectivo_cop": Decimal("50000"),
        "total_cobrado_datafono_cop": Decimal("30000"),
    }
    parsed = MiTurnoRead.model_validate(payload)

    assert parsed.ingresos_count == 3
    assert parsed.salidas_count == 2
    assert parsed.total_cobrado_efectivo_cop == Decimal("50000")
    assert parsed.total_cobrado_datafono_cop == Decimal("30000")


def test_mi_turno_read_rejects_extra_field_drift() -> None:
    """S2 (DA-F12.1-9): ``extra='forbid'`` rejects hypothetical 8th field."""
    from pydantic import ValidationError

    from parkos_core.schemas.operacion import MiTurnoRead

    payload = {**_make_minimal_payload(), "phantom_field": "drift from a future BE"}
    try:
        MiTurnoRead.model_validate(payload)
    except ValidationError as exc:
        # The error message MUST mention the smuggled field — that's how
        # downstream monitors will spot drift.
        assert "phantom_field" in str(exc) or "extra" in str(exc).lower()
    else:  # pragma: no cover — test fails if no exception raised
        raise AssertionError("MiTurnoRead must reject extra fields per extra='forbid'")


def test_mi_turno_read_field_set_matches_fe_zod_contract() -> None:
    """S3 (DA-F12.1-1 GATING): BE key set === FE Zod key set.

    Drift between BE Pydantic and FE Zod breaks the wire contract. Both
    schemas MUST share the exact same 7-field key set; CI fails on any
    divergence. The FE Zod test (``apps/electron-sucursal/src/lib/api/
    schemas/__tests__/mi-turno.test.ts``) reads the same fixture from
    a derived source; this BE test mirrors the fixture.
    """
    from parkos_core.schemas.operacion import MiTurnoRead

    # Pydantic v2 exposes field names via ``model_fields``.
    actual_keys = frozenset(MiTurnoRead.model_fields.keys())
    assert actual_keys == EXPECTED_KEYS, (
        f"BE / FE schema drift: MiTurnoRead has {sorted(actual_keys)} "
        f"but contract is {sorted(EXPECTED_KEYS)}"
    )


def test_mi_turno_read_requires_uuid_sesion() -> None:
    """S4 (REQ-OPS-184): uuid_sesion is REQUIRED."""
    from pydantic import ValidationError

    from parkos_core.schemas.operacion import MiTurnoRead

    payload = _make_minimal_payload()
    payload.pop("uuid_sesion")
    try:
        MiTurnoRead.model_validate(payload)
    except ValidationError as exc:
        assert "uuid_sesion" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("uuid_sesion is REQUIRED per REQ-OPS-184")