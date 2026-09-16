"""test_open_session_unique.py — HU-F1.3 / REQ-OPS-028.

TDD RED-then-GREEN coverage for the ``UniqueViolation``
(pgcode ``23505``) → ``SesionAlreadyActive(uuid_usuario=...)``
mapping inside ``repo/session_cycle.open_session``.

One test scenario:

  - T1 — mock the ``AsyncSession.flush`` to raise
    ``sqlalchemy.exc.IntegrityError`` whose ``orig.pgcode == "23505"``;
    invoking ``open_session(...)`` MUST re-raise the typed domain
    exception ``SesionAlreadyActive(uuid_usuario=...)`` rather than
    letting ``IntegrityError`` bubble up.

Pattern mirrors the HU-F1.2 precedent (``MagicMock(exc)`` with
``orig.pgcode == "23505"``). The mock keeps the test isolated from
Postgres — no real DB roundtrip, no ``PARKOS_DOCKER_TEST`` dependency.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.exceptions import SesionAlreadyActive
from parkos_core.repo import session_cycle as session_cycle_mod
from sqlalchemy.exc import IntegrityError


def _now_naive() -> datetime:
    """Naive ``datetime`` matching the DB column ``DateTime(timezone=False)``."""
    return datetime.now(UTC).replace(tzinfo=None)


def _make_integrity_error_pgcode(pgcode: str) -> IntegrityError:
    """Build an ``IntegrityError`` whose ``orig.pgcode == pgcode``.

    Mirrors the F1.2 mapping-test pattern: psycopg2-style
    ``orig.pgcode`` is the discriminator, NOT ``isinstance`` (the driver
    may wrap ``UniqueViolation``).
    """
    orig = MagicMock()
    orig.pgcode = pgcode
    return IntegrityError("mocked statement", {}, orig)


async def test_open_session_con_unique_violation_re_emite_sesion_already_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``open_session()`` MUST catch ``IntegrityError`` whose
    ``orig.pgcode == "23505"`` and re-raise
    ``SesionAlreadyActive(uuid_usuario=...)`` with the offending
    actor on the exception body (KD-2, REQ-OPS-028).

    RED: the typed exception does NOT exist yet → ``ImportError` at
    the import line. GREEN: re-raised with the right attribute.
    """
    actor_uuid = uuid_lib.uuid4()
    target_uuid = uuid_lib.uuid4()
    sucursal_uuid = uuid_lib.uuid4()

    # Build a fake ``AsyncSession`` whose ``flush()`` raises the
    # pgcode-23505 ``IntegrityError``.
    fake_session = MagicMock()
    fake_session.add = MagicMock()  # sync, no side-effects
    fake_session.flush = AsyncMock(side_effect=_make_integrity_error_pgcode("23505"))

    # We DO NOT want ``session.commit`` to bubble the IntegrityError
    # again — keep it a no-op so the test only observes
    # ``open_session``'s behaviour.
    fake_session.commit = AsyncMock(return_value=None)

    with pytest.raises(SesionAlreadyActive) as exc_info:
        await session_cycle_mod.open_session(
            fake_session,
            actor_uuid=actor_uuid,
            uuid_sucursal=sucursal_uuid,
            valor_inicial_efectivo=100000.0,
            valor_inicial_datafono=0.0,
            uuid_usuario=target_uuid,
            log_tx=False,  # skip the LogTransaccional row for this test
        )

    raised: SesionAlreadyActive = exc_info.value
    assert raised.uuid_usuario == target_uuid, (
        f"SesionAlreadyActive MUST carry the offending uuid_usuario "
        f"(REPO contract); got {raised.uuid_usuario!r} expected "
        f"{target_uuid!r}"
    )


__all__ = [
    "test_open_session_con_unique_violation_re_emite_sesion_already_active",
]
