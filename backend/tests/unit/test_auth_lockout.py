"""test_auth_lockout.py — HU-F1.2 lockout enforcement (R-F1.2-2, R-F1.2-3).

The lockout counts ``prod.login`` rows with ``estado='fallido'`` inside
the ``minutos_bloqueo_login`` window against ``max_intentos_login``. Once
the threshold is reached, the next ``POST /api/v1/auth/login`` returns
``429 account_locked`` with a ``Retry-After`` header equal to
``minutos_bloqueo_login * 60`` (integer seconds).

These tests verify the 4 acceptance scenarios from the spec:

1. ``test_five_failures_returns_429_with_retry_after`` (S-F1.2-2): the
   sixth attempt with a known email is rejected before bcrypt runs.
2. ``test_old_failures_outside_window_do_not_count``: a ``fallido`` row
   older than the window does NOT count (ventana deslizante).
3. ``test_successful_login_does_not_clear_counter``: an ``exitoso`` row
   does not retroactively delete prior ``fallido`` rows; the window
   slides naturally as time advances.
4. ``test_override_por_sede_manda_sobre_global``: a per-branch
   ``configuracion_seguridad`` override wins over the global default
   (S-F1.2-7).

All tests count rows BEFORE asserting the 429 — if R1 of the explore
re-emerges (lockout decorativo por omisión), the count would be 0 and
the test would fail loudly.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

import bcrypt
from parkos_core.models.V.configuracion_seguridad import ConfiguracionSeguridad
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from tests.conftest import VFixtureFactory

LOGIN_URL = "/api/v1/auth/login"


async def _seed_user_with_branch(
    pg_engine: AsyncEngine, *, email: str, plaintext: str = "Correcta123!"
) -> tuple[uuid_lib.UUID, uuid_lib.UUID]:
    """Insert one ``usuarios`` + one ``usuarios_sucursal`` + one ``sucursal``.

    Returns ``(user_uuid, sucursal_uuid)``. The user gets a real bcrypt
    hash so bad-password attempts can be distinguished from
    unknown-email attempts.
    """
    password_hash = bcrypt.hashpw(
        plaintext.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal = VFixtureFactory.build(Sucursal, nombre="Lockout Norte")
        session.add(sucursal)
        await session.flush()

        user = VFixtureFactory.build(
            Usuarios, email=email, password_hash=password_hash, rol="operador"
        )
        session.add(user)
        await session.flush()

        session.add(
            VFixtureFactory.build(
                UsuariosSucursal, uuid_sucursal=sucursal.uuid, uuid_usuario=user.uuid
            )
        )
        await session.commit()
        return (user.uuid, sucursal.uuid)


async def _insert_failed_login_row(
    pg_engine: AsyncEngine,
    *,
    user_uuid: uuid_lib.UUID,
    minutos_atras: int,
) -> None:
    """Insert one ``prod.login`` row with ``estado='fallido'`` at
    ``timestamp_evento = now() - minutos_atras minutes``.

    Bypasses ``record_login`` (which would also write a
    ``log_transaccional`` and add a ``motivo`` row that pollutes the
    count assertion). Direct SQL keeps the test focused on the lockout
    counter.
    """
    from parkos_core.models.L_S.login import Login

    when = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=minutos_atras)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = VFixtureFactory.build(
            Login,
            uuid_usuario=user_uuid,
            uuid_sucursal=None,
            timestamp_evento=when,
            timestamp_cierre=None,
            vigente_desde=when,
            vigente_hasta=None,
            estado="fallido",
        )
        session.add(row)
        await session.commit()


async def _count_failed_logins(
    pg_engine: AsyncEngine, *, user_uuid: uuid_lib.UUID
) -> int:
    from parkos_core.models.L_S.login import Login

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        stmt = select(Login).where(
            Login.uuid_usuario == user_uuid, Login.estado == "fallido"
        )
        rows = (await session.execute(stmt)).scalars().all()
        return len(rows)


async def test_five_failures_returns_429_with_retry_after(
    client, pg_engine: AsyncEngine, auth_seguridad_global: uuid_lib.UUID
) -> None:
    """S-F1.2-2: 5 ``fallido`` rows within window → 6th request is 429.

    The retry-after must be ``15 * 60 = 900`` seconds (defaults from
    ``plan.md:609`` as defined by the seeded global ``configuracion_seguridad``).
    """
    email = f"lockout-{uuid_lib.uuid4().hex[:10]}@example.com"
    user_uuid, _ = await _seed_user_with_branch(pg_engine, email=email)

    # Seed 5 ``fallido`` rows within the 15-minute window.
    for minutos_atras in (1, 3, 5, 8, 12):
        await _insert_failed_login_row(
            pg_engine, user_uuid=user_uuid, minutos_atras=minutos_atras
        )

    # Defense against R1 (lockout decorativo): assert the seed actually
    # produced 5 rows before claiming the 6th triggers the 429.
    assert await _count_failed_logins(pg_engine, user_uuid=user_uuid) == 5

    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": "Correcta123!"}
    )

    assert resp.status_code == 429, resp.text
    assert resp.headers.get("Retry-After") == "900"
    body = resp.json()
    assert body["detail"]["error"] == "account_locked"
    assert body["detail"]["retry_after_seconds"] == 900


async def test_old_failures_outside_window_do_not_count(
    client, pg_engine: AsyncEngine, auth_seguridad_global: uuid_lib.UUID
) -> None:
    """A ``fallido`` row older than ``minutos_bloqueo_login`` does NOT count.

    Ventana deslizante (sliding window). 5 rows at 16 minutes ago → 6th
    request is NOT a 429.
    """
    email = f"old-{uuid_lib.uuid4().hex[:10]}@example.com"
    user_uuid, _ = await _seed_user_with_branch(pg_engine, email=email)

    for _ in range(5):
        await _insert_failed_login_row(
            pg_engine, user_uuid=user_uuid, minutos_atras=16
        )

    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": "WrongPwd9!"}
    )

    # Window slid past: lockout must NOT fire. The 6th attempt must run
    # the bcrypt path — bad-password → 401 (NOT 429).
    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"]["error"] == "invalid_credentials"


async def test_successful_login_does_not_clear_counter(
    client, pg_engine: AsyncEngine, auth_seguridad_global: uuid_lib.UUID
) -> None:
    """A successful login does NOT delete prior ``fallido`` rows.

    The counter is the COUNT of rows in the window — it cannot be
    "cleared" by an ``exitoso``. Only the sliding window naturally
    evicts them as time advances. This is by design (KD-1, R-F1.2-2).
    """
    email = f"counter-{uuid_lib.uuid4().hex[:10]}@example.com"
    user_uuid, _ = await _seed_user_with_branch(pg_engine, email=email)

    # Seed 4 ``fallido`` rows (one short of the threshold).
    for minutos_atras in (1, 3, 5, 8):
        await _insert_failed_login_row(
            pg_engine, user_uuid=user_uuid, minutos_atras=minutos_atras
        )

    # A SUCCESSFUL login in between — inserts a new ``exitoso`` row, does
    # NOT delete the 4 ``fallido`` ones.
    resp_ok = await client.post(
        LOGIN_URL, json={"email": email, "password": "Correcta123!"}
    )
    assert resp_ok.status_code == 200, resp_ok.text

    # Confirm the 4 ``fallido`` rows are still there.
    assert await _count_failed_logins(pg_engine, user_uuid=user_uuid) == 4

    # Seed one more ``fallido`` (5 total, within window).
    await _insert_failed_login_row(
        pg_engine, user_uuid=user_uuid, minutos_atras=2
    )

    # The next request must be 429 — proves the counter is purely
    # window-based, not "cleared" by the prior ``exitoso``.
    resp_429 = await client.post(
        LOGIN_URL, json={"email": email, "password": "Correcta123!"}
    )
    assert resp_429.status_code == 429, resp_429.text
    assert resp_429.headers.get("Retry-After") == "900"


async def test_override_por_sede_manda_sobre_global(
    client, pg_engine: AsyncEngine, auth_seguridad_override: uuid_lib.UUID
) -> None:
    """S-F1.2-7: the per-branch override (max=3, min=2) wins over the
    global default (max=5, min=15).

    After 3 ``fallido`` rows inside the 2-minute window, the 4th request
    must return 429 with ``Retry-After: 120`` (2 * 60).

    The fixture returns the override branch's uuid (not the config row
    uuid). The test seeds the user with that branch as the FIRST
    ``usuarios_sucursal`` so the login handler picks it up before the
    lockout pre-check.
    """
    from parkos_core.repo.config_override import resolve_efectiva_seguridad

    override_branch_uuid = auth_seguridad_override

    # Sanity check — the override row resolves to (3, 2) for the
    # override branch.
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        cfg = await resolve_efectiva_seguridad(session, override_branch_uuid)
    assert cfg is not None
    assert cfg.max_intentos_login == 3
    assert cfg.minutos_bloqueo_login == 2

    # Seed a user whose FIRST active branch is the override branch, so
    # the login handler picks that branch (and thus the override policy)
    # BEFORE bcrypt runs.
    email = f"override-{uuid_lib.uuid4().hex[:10]}@example.com"
    password_hash = bcrypt.hashpw(
        b"Correcta123!", bcrypt.gensalt()
    ).decode("utf-8")
    async with Session() as session:
        user = VFixtureFactory.build(
            Usuarios, email=email, password_hash=password_hash, rol="operador"
        )
        session.add(user)
        await session.flush()
        session.add(
            VFixtureFactory.build(
                UsuariosSucursal,
                uuid_sucursal=override_branch_uuid,
                uuid_usuario=user.uuid,
            )
        )
        await session.commit()
        user_uuid = user.uuid

    # Seed 3 ``fallido`` rows within the 2-minute window.
    for minutos_atras in (1, 1, 1):
        await _insert_failed_login_row(
            pg_engine, user_uuid=user_uuid, minutos_atras=minutos_atras
        )

    assert await _count_failed_logins(pg_engine, user_uuid=user_uuid) == 3

    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": "Correcta123!"}
    )
    assert resp.status_code == 429, resp.text
    assert resp.headers.get("Retry-After") == "120"
    body = resp.json()
    assert body["detail"]["error"] == "account_locked"
    assert body["detail"]["retry_after_seconds"] == 120
