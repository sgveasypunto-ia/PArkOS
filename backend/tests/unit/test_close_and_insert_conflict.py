"""Unit test -- ``close_and_insert`` propagates ``IntegrityError`` as
``VersioningConflictError`` (defense-in-depth, HU-tarifas-batch).

Pins the new typed exception added to ``parkos_core.repo.versioned``.
The canonical case is a UK01 violation on ``prod.tarifas_sucursal``
during the ``session.flush()`` step; without this mapping the
``IntegrityError`` leaks out of the helper as an opaque 500 from
FastAPI (the bug found 2026-10-10 in
``apps/web_admin/src/features/tarifas/pages/Tarifas.tsx`` where two
sequential POSTs to ``/tarifas-sucursal`` produced one 201 and
six 500s -- the second POST hit the UK01 race because
``assert_no_overlap`` was the only defense and the two requests
raced the open-row check).

The mock session simulates the asyncpg ``diag.constraint_name``
shape. The real driver exposes the same attribute, so the test
pins the integration too. SQLite (used in some other unit tests)
does not expose ``diag``; the helper's ``_extract_constraint_name``
returns ``None`` for that case, which is also correct (we just
can't name the violated constraint in the typed error).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

from parkos_core.repo.versioned import (  # noqa: E402
    VersioningConflictError,
    VersioningError,
    close_and_insert,
)

# Monkey-patch ``sa_inspect`` in the versioned module to return our
# stub columns (the real TarifasSucursal class would work but it would
# also trigger the post-flush FK hook which we don't want here --
# IntegrityError fires before flush completes, so the hook never runs).
import parkos_core.repo.versioned as _versioned_module  # noqa: E402
_original_sa_inspect = _versioned_module.sa_inspect


def _patched_sa_inspect(cls):  # noqa: ANN001, ANN201
    if getattr(cls, "__name__", "") == "TarifasSucursal_stub_class":
        return cls._sa_inspect_proxy
    return _original_sa_inspect(cls)


_versioned_module.sa_inspect = _patched_sa_inspect


# Stub model class -- close_and_insert uses ``sa_inspect(model_cls).columns``
# to drop validation-only fields and the FK propagation hook reads
# ``model_cls.__tablename__``. We don't need the real TarifasSucursal
# because the only call we exercise is ``session.flush()`` which raises
# BEFORE any post-flush code runs.
class _StubColumn:
    def __init__(self, name: str) -> None:
        self.name = name


_STUB_COLUMN_NAMES = (
    "uuid",
    "uuid_sucursal",
    "uuid_tipo_vehiculo",
    "uuid_tipo_tarifa",
    "valor",
    "valor_plena",
    "vigente_desde",
    "vigente_hasta",
    "estado",
    "created_at",
    "created_by",
)


def _make_stub_model():
    """Build a MagicMock that looks like a SQLAlchemy ``[V]`` model class
    for the parts ``close_and_insert`` introspects (``sa_inspect(...).columns``
    and ``__tablename__``). The constructor returns a row with a
    generated uuid so the helper's ``session.add`` accepts it.
    """
    import uuid as _uuid

    cls = MagicMock(name="TarifasSucursal_stub_class")
    cls.__tablename__ = "tarifas_sucursal"
    # ``sa_inspect(cls).columns`` returns objects with a ``.name`` attr.
    inspect_mock = MagicMock(name="sa_inspect")
    inspect_mock.columns = [_StubColumn(n) for n in _STUB_COLUMN_NAMES]
    cls._sa_inspect_proxy = inspect_mock

    def _factory(**_kw):
        row = MagicMock(name="row")
        row.uuid = _uuid.uuid4()
        return row

    cls.side_effect = _factory
    return cls


_StubTarifas = _make_stub_model()


def _make_integrity_error(*, constraint_name: str | None) -> IntegrityError:
    """Build an ``IntegrityError`` whose ``.orig`` mimics the asyncpg shape.

    asyncpg exposes ``DiagStruct`` with a ``constraint_name`` attribute;
    SQLAlchemy wraps the asyncpg exception in ``IntegrityError`` and
    attaches the original via ``.orig``. We build the same shape so the
    extraction helper ``_extract_constraint_name`` can be unit-tested
    without spinning up Postgres.
    """
    diag = MagicMock(name="asyncpg_diag")
    diag.constraint_name = constraint_name
    orig = MagicMock(name="asyncpg_orig")
    orig.diag = diag
    # SQLAlchemy expects ``orig`` to be a real exception-like for traceback
    # handling. MagicMock duck-types well enough here.
    return IntegrityError("INSERT", {}, orig)


def _make_session_mocks(
    *,
    flush_raises: IntegrityError | None = None,
) -> tuple[MagicMock, AsyncMock]:
    """Build a session mock whose ``flush`` is the only behavior exercised.

    ``session.add`` is a sync MagicMock (close_and_insert calls it
    synchronously, and we don't care about the result -- the helper
    only needs the row's ``.uuid`` after flush, which the IntegrityError
    prevents from happening anyway).
    """
    session = MagicMock(name="AsyncSession")
    session.add = MagicMock(name="session.add")
    if flush_raises is not None:
        session.flush = AsyncMock(side_effect=flush_raises)
    else:
        session.flush = AsyncMock(name="session.flush")
    return session, session.flush


@pytest.mark.asyncio
async def test_close_and_insert_raises_versioning_conflict_on_uk01() -> None:
    """UK01 on ``prod.tarifas_sucursal`` surfaces as
    ``VersioningConflictError(constraint_name='tarifas_sucursal_uk01')``,
    not as a bare 500 from FastAPI."""
    integrity_error = _make_integrity_error(constraint_name="tarifas_sucursal_uk01")
    session, _ = _make_session_mocks(flush_raises=integrity_error)

    with pytest.raises(VersioningConflictError) as exc_info:
        await close_and_insert(
            session,
            _StubTarifas,
            current_uuid=None,
            new_attrs={
                "uuid_sucursal": uuid_lib.uuid4(),
                "uuid_tipo_vehiculo": uuid_lib.uuid4(),
                "uuid_tipo_tarifa": uuid_lib.uuid4(),
                "valor": 1000,
            },
            actor_uuid=uuid_lib.uuid4(),
            log_tx=False,
        )

    assert exc_info.value.constraint_name == "tarifas_sucursal_uk01"
    # The typed exception is a VersioningError subclass so any caller
    # that already catches VersioningError (the historic pattern) keeps
    # working -- this is the defense-in-depth promise.
    assert isinstance(exc_info.value, VersioningError)
    # The original IntegrityError is preserved on .original for
    # diagnostics and ``raise ... from exc`` chains.
    assert exc_info.value.original is integrity_error


@pytest.mark.asyncio
async def test_close_and_insert_raises_versioning_conflict_on_fk_violation() -> None:
    """FK violation (e.g. unknown ``uuid_tipo_vehiculo``) also surfaces
    as ``VersioningConflictError`` with the right constraint name
    (Postgres: ``fk_tarifas_sucursal_uuid_tipo_vehiculo``)."""
    integrity_error = _make_integrity_error(
        constraint_name="fk_tarifas_sucursal_uuid_tipo_vehiculo"
    )
    session, _ = _make_session_mocks(flush_raises=integrity_error)

    with pytest.raises(VersioningConflictError) as exc_info:
        await close_and_insert(
            session,
            _StubTarifas,
            current_uuid=None,
            new_attrs={
                "uuid_sucursal": uuid_lib.uuid4(),
                "uuid_tipo_vehiculo": uuid_lib.uuid4(),
                "uuid_tipo_tarifa": uuid_lib.uuid4(),
                "valor": 1000,
            },
            actor_uuid=uuid_lib.uuid4(),
            log_tx=False,
        )

    assert exc_info.value.constraint_name == "fk_tarifas_sucursal_uuid_tipo_vehiculo"


@pytest.mark.asyncio
async def test_close_and_insert_handles_integrity_error_without_constraint() -> None:
    """When the driver does not expose ``constraint_name`` (SQLite, some
    edge cases), the typed exception still surfaces -- with
    ``constraint_name=None``. The FE then sees a 409 without the
    constraint hint but still correctly maps to ``TarifaConflictError``."""
    # SQLite-style IntegrityError: ``.orig`` is a string, no ``diag``.
    sqlite_like = IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: foo"))
    session, _ = _make_session_mocks(flush_raises=sqlite_like)

    with pytest.raises(VersioningConflictError) as exc_info:
        await close_and_insert(
            session,
            _StubTarifas,
            current_uuid=None,
            new_attrs={
                "uuid_sucursal": uuid_lib.uuid4(),
                "uuid_tipo_vehiculo": uuid_lib.uuid4(),
                "uuid_tipo_tarifa": uuid_lib.uuid4(),
                "valor": 1000,
            },
            actor_uuid=uuid_lib.uuid4(),
            log_tx=False,
        )

    assert exc_info.value.constraint_name is None
    # The original IntegrityError is still chained for debugging.
    assert exc_info.value.original is sqlite_like
