"""HU-F1.14 / T2.2 -- ``schemas/sync_infra.py`` extension tests.

* ``SyncEstadoQueryParams(_Base)`` -- query params with required
  ``uuid_sucursal: UUID`` (Layer 4 defense via ``extra='forbid'``).
* ``SyncEstadoRead(_Base)`` -- response shape with ``ultima_sync_at:
  datetime | None``, ``lag_seg: int | None``, ``pendientes: int``
  (ge=0).

Both inherit from :class:`_Base` (``extra='forbid'``) so client
smuggling of unknown fields (e.g. ``actor_uuid``, ``computed_at``,
``cache_key``) raises ``ValidationError``.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


# ---------------------------------------------------------------------------
# T2.2 -- SyncEstadoQueryParams
# ---------------------------------------------------------------------------


def test_sync_estado_query_params_uuid_required() -> None:
    """SyncEstadoQueryParams MUST require ``uuid_sucursal``."""
    from parkos_core.schemas.sync_infra import SyncEstadoQueryParams
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SyncEstadoQueryParams()  # type: ignore[call-arg]


def test_sync_estado_query_params_extra_forbid() -> None:
    """Layer 4 defense: ``extra='forbid'`` blocks unknown query fields."""
    from parkos_core.schemas.sync_infra import SyncEstadoQueryParams
    from pydantic import ValidationError

    uuid_sucursal = uuid_lib.uuid4()
    with pytest.raises(ValidationError):
        SyncEstadoQueryParams(
            uuid_sucursal=uuid_sucursal,
            actor_uuid="x",  # type: ignore[call-arg]
        )


def test_sync_estado_query_params_uuid_validator() -> None:
    """Layer 4: malformed uuid_sucursal raises ValidationError (422 on API)."""
    from parkos_core.schemas.sync_infra import SyncEstadoQueryParams
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SyncEstadoQueryParams(uuid_sucursal="not-a-uuid")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# T2.2 -- SyncEstadoRead
# ---------------------------------------------------------------------------


def test_sync_estado_read_lag_seg_nullable() -> None:
    """DEC-SYNC-08: ``lag_seg: int | None`` accepts None (empty branch)."""
    from parkos_core.schemas.sync_infra import SyncEstadoRead

    uuid_sucursal = uuid_lib.uuid4()
    read = SyncEstadoRead(
        uuid_sucursal=uuid_sucursal,
        ultima_sync_at=None,
        lag_seg=None,
        pendientes=0,
    )
    assert read.lag_seg is None
    assert read.ultima_sync_at is None
    assert read.pendientes == 0


def test_sync_estado_read_pendientes_ge_zero() -> None:
    """DEC-SYNC-09: ``pendientes`` MUST be ``int >= 0`` (never null, never negative)."""
    from parkos_core.schemas.sync_infra import SyncEstadoRead
    from pydantic import ValidationError

    uuid_sucursal = uuid_lib.uuid4()
    # pending=0 OK (boundary)
    SyncEstadoRead(uuid_sucursal=uuid_sucursal, ultima_sync_at=None, lag_seg=None, pendientes=0)
    # negative -> ValidationError
    with pytest.raises(ValidationError):
        SyncEstadoRead(
            uuid_sucursal=uuid_sucursal,
            ultima_sync_at=None,
            lag_seg=None,
            pendientes=-1,
        )
