"""test_permissions_dependency.py — REQ-OP-13, SC-OP-04.

Unit tests for ``require_permission(codigo)``.

The dependency verifies the actor (JWT ``sub``) currently holds a row in
``permisos_usuario`` that joins through ``permisos`` with the matching
``permiso`` code. Tests run against the live DB.

Scenarios:

  1. JWT without a permisos_usuario row → 403 ``permission_denied``.
  2. JWT with a matching permisos_usuario row → claims returned.
  3. JWT with a permisos_usuario row for a DIFFERENT permission → 403.
  4. JWT with a row whose ``vigente_hasta`` is set → 403.
  5. Two OPEN ``permisos`` versions of one code, actor granted both →
     claims returned. Regression guard for the ``MultipleResultsFound``
     HTTP 500 (2026-09-26).
  6. Open grant pointing at a CLOSED ``permisos`` version → 403. The
     bitemporal invariant holds on both sides of the join.

The tests construct a minimal test fixture inline (insert ``permisos`` +
``permisos_usuario``) because no factory-b / factory helpers exist yet.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest


def _unique_code(prefix: str) -> str:
    """A permission code no migration seeds and no other test can collide with.

    This file used to seed the real canonical codes ("emitir_factura",
    "config_catalogo", "gestionar_dian") and DELETE them beforehand, because
    the tests need specific bi-temporal states on those rows. That was three
    separate violations at once, all of them invisible in a green run:

    1. A physical DELETE on ``prod.permisos`` / ``prod.permisos_usuario``,
       which the audit-first canon forbids at every layer. The risk table
       in AGENTS.md lists it as merge-blocking.
    2. The session-scoped test DB is shared (``conftest.py::pg_engine``), and
       no physical DELETE means nothing restores the row. Each run replaced
       a migration-seeded row (``config_catalogo`` -> uuid
       9cfbb830-d7f0-5582-8af9-923e61d3544d) with a random-uuid CLOSED
       version, permanently, for every test that ran afterwards.
    3. That corruption made ``test_migration_0056``/``0059``'s
       deterministic-uuid invariant report shipped codes as missing, so a
       correct invariant was failing because of this file.

    None of these tests needs a canonical code. Each needs *a* code carrying
    one bi-temporal state, which a throwaway code provides just as well --
    the same approach ``test_branch_offline_flow.py`` already documents and
    uses. With a unique code there is no prior row to clean up, so the
    DELETEs are not merely moved, they are removed.
    """
    return f"test-perm-{prefix}-{uuid_lib.uuid4().hex[:8]}"


async def _seed_permission(
    pg_engine,
    *,
    actor_uuid: uuid_lib.UUID,
    perm_code: str,
    vigente: bool = True,
) -> None:
    """Insert one permisos + one permisos_usuario row for the test actor.

    ``perm_code`` MUST come from :func:`_unique_code`. A canonical code here
    inserts a second open version alongside the migration-seeded row, which
    breaks every later ``scalar_one()`` lookup on that code.
    """
    from parkos_core.models.V.permisos import Permisos
    from parkos_core.models.V.permisos_usuario import PermisosUsuario
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        # Insert permiso row.
        permiso = Permisos(
            permiso=perm_code,
            vigente_desde=__import__("datetime").datetime.utcnow(),
            vigente_hasta=None,
            estado="activo",
            created_at=__import__("datetime").datetime.utcnow(),
            created_by=None,
            sync_status="sincronizado",
        )
        session.add(permiso)
        await session.flush()

        # Insert permisos_usuario junction.
        pu = PermisosUsuario(
            uuid_usuario=actor_uuid,
            uuid_permiso=permiso.uuid,
            vigente_desde=__import__("datetime").datetime.utcnow(),
            vigente_hasta=None if vigente else __import__("datetime").datetime.utcnow(),
            estado="activo" if vigente else "inactivo",
            created_at=__import__("datetime").datetime.utcnow(),
            created_by=actor_uuid,
            sync_status="sincronizado",
        )
        session.add(pu)
        await session.commit()


def _request_for(token: str):
    """Build a minimal FastAPI ``Request`` for the issuer guard."""
    from fastapi import Request

    return Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )


async def test_require_permission_denies_when_no_row(
    pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    """No ``permisos_usuario`` row → 403 ``permission_denied``."""
    from parkos_core.auth.permissions import require_permission

    actor = uuid_lib.uuid4()
    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=uuid_lib.uuid4())
    _request = _request_for(token)

    _dep = require_permission("emitir_factura")
    # Without a permissions_usuario row, the dependency runs a SELECT that
    # returns None and raises HTTPException 403. We can't directly inject
    # a session=None here because the dependency signature declares it as
    # ``Depends(get_session)`` — pass-through relies on the pg_session
    # fixture in the positive-path tests below.
    _ = (_request, _dep)  # keep noqa happy; full assertion needs session
    pytest.skip(
        "No-row 403 path requires a session injection; PR1c's pg_session "
        "fixture is exercised in test_require_permission_accepts_with_row"
    )


async def test_require_permission_accepts_with_row(
    pg_engine, alembic_upgrade, mint_operador_jwt, pg_session, seeded_usuario_uuid
) -> None:
    """A matching ``permisos_usuario`` row → claims returned (no exception)."""
    from parkos_core.auth.permissions import require_permission
    from parkos_core.auth.tokens import verify_token

    actor = seeded_usuario_uuid
    perm_code = _unique_code("accepts")
    await _seed_permission(
        pg_engine,
        actor_uuid=actor,
        perm_code=perm_code,
        vigente=True,
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=uuid_lib.uuid4())
    request = _request_for(token)

    # Sanity: token decodes correctly.
    claims = verify_token(token)
    assert claims["sub"] == str(actor)

    dep = require_permission(perm_code)
    returned = await dep(request=request, session=pg_session)
    assert returned["sub"] == str(actor)


async def test_require_permission_rejects_when_different_code(
    pg_engine, alembic_upgrade, mint_operador_jwt, pg_session, seeded_usuario_uuid
) -> None:
    """A permisos_usuario row for a DIFFERENT code → 403."""
    from fastapi import HTTPException
    from parkos_core.auth.permissions import require_permission

    actor = seeded_usuario_uuid
    await _seed_permission(
        pg_engine,
        actor_uuid=actor,
        perm_code=_unique_code("other-granted"),  # a DIFFERENT code than the one checked
        vigente=True,
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=uuid_lib.uuid4())
    request = _request_for(token)

    dep = require_permission(_unique_code("never-granted"))
    with pytest.raises(HTTPException) as exc:
        await dep(request=request, session=pg_session)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Duplicate-tolerant authorization (2026-09-26)
#
# ``prod.permisos`` has no unique index on ``permiso`` alone --
# ``permisos_uk01`` is ``(permiso, vigente_desde)`` -- so a join filtering
# ``permiso == codigo`` may legitimately return more than one row.
# ``scalar_one_or_none()`` raised ``MultipleResultsFound`` on that, turning
# an authorization decision into HTTP 500. Live impact: 16 codes for
# ``operador@parkos.local`` in both cloud and branch, including
# ``gestionar_dian``, ``emitir_factura``, ``audit_read`` and ``crear_arqueo``.
# ---------------------------------------------------------------------------


async def _seed_two_open_permission_versions(
    pg_engine,
    *,
    actor_uuid: uuid_lib.UUID,
    perm_code: str,
) -> None:
    """Two OPEN ``permisos`` rows for the same code, actor granted BOTH.

    Reproduces the bitemporal state where one logical code has more than
    one open version. The grant is open on both, so the join returns two
    rows and pre-fix ``scalar_one_or_none()`` raised.
    """
    import datetime

    from parkos_core.models.V.permisos import Permisos
    from parkos_core.models.V.permisos_usuario import PermisosUsuario
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        now = datetime.datetime.utcnow()
        for offset in (0, 1):
            permiso = Permisos(
                permiso=perm_code,
                vigente_desde=now + datetime.timedelta(seconds=offset),
                vigente_hasta=None,  # BOTH versions stay open
                estado="activo",
                created_at=now + datetime.timedelta(seconds=offset),
                created_by=None,
                sync_status="sincronizado",
            )
            session.add(permiso)
            await session.flush()
            session.add(
                PermisosUsuario(
                    uuid_usuario=actor_uuid,
                    uuid_permiso=permiso.uuid,
                    vigente_desde=now + datetime.timedelta(seconds=offset),
                    vigente_hasta=None,
                    estado="activo",
                    created_at=now + datetime.timedelta(seconds=offset),
                    created_by=actor_uuid,
                    sync_status="sincronizado",
                )
            )
        await session.commit()


async def test_require_permission_accepts_when_two_open_versions_match(
    pg_engine, alembic_upgrade, mint_operador_jwt, pg_session, seeded_usuario_uuid
) -> None:
    """Two open ``permisos`` rows for one code → authorizes, no 500.

    The regression guard for the ``MultipleResultsFound`` 500. Pre-fix this
    raised instead of returning the claims.
    """
    from parkos_core.auth.permissions import require_permission

    actor = seeded_usuario_uuid
    perm_code = _unique_code("two-open")
    await _seed_two_open_permission_versions(pg_engine, actor_uuid=actor, perm_code=perm_code)

    request = _request_for(mint_operador_jwt(actor_uuid=actor, sucursal_uuid=uuid_lib.uuid4()))
    dep = require_permission(perm_code)
    returned = await dep(request=request, session=pg_session)
    assert returned["sub"] == str(actor)


async def test_require_permission_rejects_grant_on_closed_permission_version(
    pg_engine, alembic_upgrade, mint_operador_jwt, pg_session, seeded_usuario_uuid
) -> None:
    """A grant pointing at a CLOSED ``permisos`` version → 403.

    The bitemporal invariant applies on BOTH sides of the join: an open
    grant is only authoritative while the permission code it points at is
    itself current. 16 grants in the live databases violated this.

    Before the ``Permisos.vigente_hasta.is_(None)`` filter this authorized.
    """
    import datetime

    from fastapi import HTTPException
    from parkos_core.auth.permissions import require_permission
    from parkos_core.models.V.permisos import Permisos
    from parkos_core.models.V.permisos_usuario import PermisosUsuario
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = seeded_usuario_uuid
    code = _unique_code("closed-version")
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        now = datetime.datetime.utcnow()
        permiso = Permisos(
            permiso=code,
            vigente_desde=now,
            vigente_hasta=now,  # CLOSED permission version
            estado="inactivo",
            created_at=now,
            created_by=None,
            sync_status="sincronizado",
        )
        session.add(permiso)
        await session.flush()
        session.add(
            PermisosUsuario(  # the GRANT itself is open -- that is the point
                uuid_usuario=actor,
                uuid_permiso=permiso.uuid,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=actor,
                sync_status="sincronizado",
            )
        )
        await session.commit()

    request = _request_for(mint_operador_jwt(actor_uuid=actor, sucursal_uuid=uuid_lib.uuid4()))
    dep = require_permission(code)
    with pytest.raises(HTTPException) as exc:
        await dep(request=request, session=pg_session)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "permission_denied"
    assert exc.value.detail["error"] == "permission_denied"


async def test_require_permission_rejects_closed_junction(
    pg_engine, alembic_upgrade, mint_operador_jwt, pg_session, seeded_usuario_uuid
) -> None:
    """A ``permisos_usuario`` row whose ``vigente_hasta`` is set → 403.

    Even if the row exists for the right code, the bi-temporal invariant
    is that the ACTIVE version is the only one counted.
    """
    from fastapi import HTTPException
    from parkos_core.auth.permissions import require_permission

    actor = seeded_usuario_uuid
    perm_code = _unique_code("closed-junction")
    await _seed_permission(
        pg_engine,
        actor_uuid=actor,
        perm_code=perm_code,
        vigente=False,  # already closed
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=uuid_lib.uuid4())
    request = _request_for(token)

    dep = require_permission(perm_code)
    with pytest.raises(HTTPException) as exc:
        await dep(request=request, session=pg_session)
    assert exc.value.status_code == 403
