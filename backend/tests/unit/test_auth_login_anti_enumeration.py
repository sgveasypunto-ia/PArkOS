"""test_auth_login_anti_enumeration.py — R-F1.2-11.

An unknown email MUST return ``401 invalid_credentials`` (NOT 429) and
MUST NOT insert any row into ``prod.login``. The lockout count only
applies to real ``uuid_usuario`` rows — there is nothing to count when
the email doesn't exist.

This preserves the anti-enumeration property: an attacker iterating
emails can't tell apart "email exists" from "email doesn't exist" by
the response code or by any audit footprint.
"""
from __future__ import annotations

import uuid as uuid_lib

from parkos_core.models.L_S.login import Login
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

LOGIN_URL = "/api/v1/auth/login"


async def _count_recent_login_rows_without_user(
    pg_engine: AsyncEngine, *, seconds: int = 60
) -> int:
    """Count ``prod.login`` rows with ``uuid_usuario IS NULL`` inserted in
    the last ``seconds``. Used as the sentinel: a bad-password request
    must NOT produce such a row (R-F1.2-1 inserts with the user's uuid,
    not NULL).
    """
    from datetime import UTC, datetime, timedelta

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=seconds)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        stmt = select(Login).where(
            Login.uuid_usuario.is_(None),
            Login.timestamp_evento >= cutoff,
        )
        rows = (await session.execute(stmt)).scalars().all()
        return len(rows)


async def test_unknown_email_returns_401_without_login_row_insert(
    client, pg_engine: AsyncEngine
) -> None:
    """S-F1.2-3: unknown email → 401 (NOT 429) → no audit footprint.

    Antienumeración. The response shape is identical to a bad-password
    401 on a known email; the only difference is internal (no ``fallido``
    row inserted because there's no real user to attribute it to).
    """
    before = await _count_recent_login_rows_without_user(pg_engine, seconds=60)

    resp = await client.post(
        LOGIN_URL,
        json={
            "email": f"fantasma-{uuid_lib.uuid4().hex[:10]}@example.com",
            "password": "CualquieraX1!",
        },
    )

    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"]["error"] == "invalid_credentials"

    # Crucially: NO new ``prod.login`` row was created (uuid_usuario IS NULL
    # count must stay flat).
    after = await _count_recent_login_rows_without_user(pg_engine, seconds=60)
    assert after == before, (
        f"unknown email MUST NOT insert a login row; before={before} after={after}"
    )

    # The response was NOT 429 (no lockout for nonexistent emails).
    assert resp.status_code != 429
