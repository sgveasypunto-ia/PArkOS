"""Unit tests for the project-wide UTC datetime serializer on
:class:`parkos_core.schemas.common._Base`.

The serializer is the single source of truth for the "every datetime
leaves the API with a ``Z`` (or ``±HH:MM``) suffix" wire contract.
Any regression here breaks ``/cupos`` and ``/tarifas`` because the
``<input type="datetime-local">`` round-trip on the web_admin side
expects every backend value to parse unambiguously as UTC — see
:file:`apps/web_admin/src/lib/datetimeTz.ts` for the consumer side.

The serializer must:

  - Append ``Z`` to naive datetimes (the legacy ``DateTime(timezone=False)``
    case, the dominant shape in our schema).
  - Leave aware datetimes alone (Pydantic's own JSON encoder already
    emits them with their offset, including the canonical ``Z`` for
    UTC).
  - Preserve ``@computed_field`` and every other Pydantic-driven
    serialization — we only post-process the result of the default
    serializer, never replace it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import computed_field

from parkos_core.schemas.common import _Base


class _CupoReadShape(_Base):
    """Mirrors the canonical read-model shape used in
    :file:`backend/.../schemas/empresa.py::CantidadVehiculosSucursalRead`
    — three datetime fields, two of them nullable, the rest plain
    scalars. Lets the test exercise the full mix of "naive + aware +
    computed + nullable" in one model.
    """

    uuid: str
    cantidad: Optional[int]
    vigente_desde: datetime
    vigente_hasta: Optional[datetime]
    estado: str
    created_at: datetime
    sync_status: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def esta_vigente(self) -> bool:
        return self.estado == "activo" and self.vigente_hasta is None


def test_naive_datetime_gets_z_suffix_on_model_dump_json() -> None:
    """Legacy ``DateTime(timezone=False)`` columns serialize as
    ``2026-10-11T19:30:00Z``. Pre-Commit-3 they serialized as
    ``2026-10-11T19:30:00`` and the web_admin's
    ``new Date(naiveString).getTime()`` mis-parsed them as local
    time. Pin the new behavior so a future Pydantic upgrade can't
    silently regress it.
    """
    row = _CupoReadShape(
        uuid="aaaaaaaa-1111-1111-1111-111111111111",
        cantidad=10,
        vigente_desde=datetime(2026, 10, 11, 19, 30),
        vigente_hasta=None,
        estado="activo",
        created_at=datetime(2026, 10, 11, 19, 30),
    )
    dumped = row.model_dump(mode="json")
    assert dumped["vigente_desde"] == "2026-10-11T19:30:00Z"
    assert dumped["created_at"] == "2026-10-11T19:30:00Z"
    # Computed fields must STILL be present (regression: an
    # earlier ``mode='plain'`` implementation walked ``self.__dict__``
    # which excludes ``@computed_field`` and silently dropped
    # ``esta_vigente`` from the output).
    assert dumped["esta_vigente"] is True


def test_aware_utc_datetime_stays_at_z() -> None:
    """An aware datetime at UTC offset 0 must land on the wire as
    ``Z`` (Pydantic's default JSON encoder collapses ``+00:00`` to
    ``Z`` for us; the serializer must not double-suffix).
    """
    row = _CupoReadShape(
        uuid="11111111-1111-1111-1111-111111111111",
        cantidad=20,
        vigente_desde=datetime(2026, 10, 11, 19, 30, tzinfo=timezone.utc),
        vigente_hasta=None,
        estado="activo",
        created_at=datetime(2026, 10, 11, 19, 30, tzinfo=timezone.utc),
    )
    dumped = row.model_dump(mode="json")
    assert dumped["vigente_desde"] == "2026-10-11T19:30:00Z"
    assert dumped["created_at"] == "2026-10-11T19:30:00Z"


def test_null_datetime_stays_null() -> None:
    """The nullable fields must remain ``None`` on the wire, not
    be turned into the empty string or ``"Z"``.
    """
    row = _CupoReadShape(
        uuid="22222222-1111-1111-1111-111111111111",
        cantidad=None,
        vigente_desde=datetime(2026, 10, 11, 19, 30),
        vigente_hasta=None,
        estado="inactivo",
        created_at=datetime(2026, 10, 11, 19, 30),
        sync_status=None,
    )
    dumped = row.model_dump(mode="json")
    assert dumped["vigente_hasta"] is None
    assert dumped["sync_status"] is None
    assert dumped["cantidad"] is None


def test_default_model_dump_preserves_python_types() -> None:
    """The Python-mode (``mode='python'``) ``model_dump`` must NOT
    alter datetime objects — it should still return ``datetime``
    instances so downstream SQLAlchemy / ORM code that introspects
    the dict can keep using the typed values. Only the JSON wire
    format gets the Z suffix.
    """
    row = _CupoReadShape(
        uuid="33333333-1111-1111-1111-111111111111",
        cantidad=10,
        vigente_desde=datetime(2026, 10, 11, 19, 30),
        vigente_hasta=None,
        estado="activo",
        created_at=datetime(2026, 10, 11, 19, 30),
    )
    dumped = row.model_dump()  # default mode is "python"
    assert isinstance(dumped["vigente_desde"], datetime)
    assert dumped["vigente_desde"].tzinfo is None  # round-trips Python
    assert isinstance(dumped["created_at"], datetime)
