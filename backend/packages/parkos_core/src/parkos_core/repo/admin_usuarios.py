"""Admin user-management repo helpers (IT-1.4, IT-1.5).

This module is the write-side of the admin user-management endpoints
that pair with ``api/v1/admin_usuarios.py``. The read-side
(``GET /admin/usuarios``) lives here too because the only consumer is
the admin HTTP layer.

Layering contract
-----------------

- :func:`create_admin_usuario` writes ONE ``prod.usuarios`` row
  (close+insert via ``repo.versioned.close_and_insert``), fans out to
  write one ``prod.usuarios_sucursal`` row per assigned branch, and
  enqueues one ``prod.sync_queue`` row per branch assignment so the
  existing ``job_sync_cloud._apply_pending_loop`` drips each row to
  the branches via the normal sync transport.
- :func:`list_active_usuarios` returns the currently-open version
  of each ``prod.usuarios`` row (``vigente_hasta IS NULL``).
- :func:`list_active_asignaciones_usuario` returns the currently-open
  ``prod.usuarios_sucursal`` rows for one user.
- :func:`asignar_sucursal` opens a NEW ``prod.usuarios_sucursal``
  version (close+insert on the same ``(uuid_usuario, uuid_sucursal)``
  pair), bumping ``vigente_desde``.
- :func:`desasignar_sucursal` closes the currently-open assignment
  (``vigente_hasta = NOW()``).

All helpers are ``SELECT-only`` or ``close+insert`` -- the repo never
runs raw ``UPDATE`` or ``DELETE``. The only write column the helpers
ever touch on ``sync_queue`` is the read side; writes happen via
``repo.sync_queue.enqueue`` which goes through the canonical path.

Why bcrypt lives here, not in the handler
-----------------------------------------

The handler accepts plaintext password (per the IT-1.4 contract).
Hashing belongs in the repo layer so every consumer (HTTP now, CLI /
batch import later) gets the same hash algorithm and cost factor
without re-deriving them. ``auth.py::login`` uses the SAME bcrypt path
on read (``bcrypt.checkpw``), so the cost factor is symmetric for both
sides of the comparison.

Bcrypt cost factor is hardcoded at 12 rounds (``bcrypt.gensalt(
rounds=12)``). 12 matches ``auth.py``'s implicit default
(``bcrypt.gensalt()`` uses the ``passlib`` library's
``default_cost`` of 12 in this Python wheel); if it ever changes
in the BE the handler-side hash and the login-side verify will
disagree -- a one-line fix when that happens.
"""

from __future__ import annotations

import uuid as uuid_lib
from collections.abc import Collection
from datetime import UTC, datetime

import bcrypt
from sqlalchemy import ColumnElement, exists, false, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.permisos import Permisos
from ..models.V.permisos_usuario import PermisosUsuario
from ..models.V.sucursal import Sucursal
from ..models.V.usuarios import Usuarios
from ..models.V.usuarios_sucursal import UsuariosSucursal
from ..schemas.admin import SucursalAsignadaResumen
from .sync_queue import enqueue
from .versioned import close_and_insert, close_only

# Bcrypt cost factor -- symmetric with ``auth.py::login`` (which calls
# ``bcrypt.gensalt()`` without arguments). Keep both sides in sync if
# this ever changes.
BCRYPT_ROUNDS = 12


def _now() -> datetime:
    """Naive-UTC ``now`` -- mirrors ``repo.sync_queue._now``."""
    return datetime.now(UTC).replace(tzinfo=None)


def _bcrypt_hash(plaintext_password: str) -> str:
    """Hash a plaintext password with bcrypt at :data:`BCRYPT_ROUNDS`.

    The returned value is the bcrypt digest as ASCII (the ``bcrypt``
    library returns ``bytes``; we decode once here so the ``[V]``
    model column ``String`` accepts it directly).
    """
    return bcrypt.hashpw(
        plaintext_password.encode("utf-8"),
        bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
    ).decode("ascii")


# Admin-facing FK tables keyed by ``uuid_usuario`` whose CURRENT state
# must keep pointing at the user after a bi-temporal close+insert.
# Mirrors ``repo.sucursal._FK_TABLES`` / ``propagate_uuid_to_fks`` --
# see ``repo.versioned`` module docstring for the general "UUID
# regeneration" gotcha. ``login_historico`` / ``log_transaccional`` are
# intentionally EXCLUDED: those record "who did X at the time", so
# repointing them would rewrite audit history rather than preserve it.
_USUARIO_FK_TABLES: tuple[tuple[str, str], ...] = (
    ("prod", "usuarios_sucursal"),
    ("prod", "permisos_usuario"),
)


async def propagate_usuario_uuid_to_fks(
    session: AsyncSession,
    *,
    old_uuid: uuid_lib.UUID,
    new_uuid: uuid_lib.UUID,
) -> None:
    """Repoint ``uuid_usuario = old_uuid`` to ``new_uuid`` in the FK
    tables backing the Usuario detail page's own tabs.

    Called from ``repo.versioned.close_and_insert`` right after it
    mints the successor ``Usuarios`` row (same TX, no commit here).

    Without this, every ``update_admin_usuario`` (Datos tab save) or
    ``reset_admin_password`` call silently orphans the user's open
    ``usuarios_sucursal`` / ``permisos_usuario`` rows: those rows keep
    pointing at the now-closed OLD uuid, so the Sucursales/Permisos
    tabs read back empty for a user who still has active assignments.
    Confirmed live (qa/batch-usuarios, 2026-10-02): a user with one
    open ``usuarios_sucursal`` row showed "Sin sucursales asignadas"
    in the admin UI after two Datos-tab edits + one password reset,
    because the assignment row still carried the user's very first
    (three edits ago) closed uuid.

    Idempotent: when no FK row references ``old_uuid`` the UPDATE
    matches 0 rows and this is a no-op.
    """
    if old_uuid == new_uuid:
        return
    from sqlalchemy import text

    for schema, table in _USUARIO_FK_TABLES:
        qualified = f"{schema}.{table}"
        await session.execute(
            text(
                f"UPDATE {qualified} "
                f"SET uuid_usuario = :new_uuid "
                f"WHERE uuid_usuario = :old_uuid"
            ),
            {"new_uuid": new_uuid, "old_uuid": old_uuid},
        )


async def create_admin_usuario(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    nombre: str | None,
    apellido: str | None,
    cedula: str | None,
    email: str | None,
    password: str,
    rol: str,
    sucursales_asignadas: list[uuid_lib.UUID],
) -> Usuarios:
    """Create a new ``prod.usuarios`` row + initial branch assignments.

    The user is written via ``close_and_insert(current_uuid=None, ...)``
    so the bi-temporal versioning columns are set server-side
    (``vigente_desde = NOW()``, ``vigente_hasta = NULL``,
    ``estado = 'activo'``, ``created_at = NOW()``,
    ``created_by = actor_uuid``).

    One ``prod.usuarios_sucursal`` row is opened per
    ``sucursales_asignadas`` UUID; the row is also close+insert'd so
    its own ``vigente_desde = NOW()`` and ``vigente_hasta = NULL``.

    One ``prod.sync_queue`` row is enqueued per assignment with
    ``operacion='insert'``, ``tabla='usuarios'`` and ``datos`` carrying
    a JSONB-friendly snapshot of the user. The existing
    ``job_sync_cloud._apply_pending_loop`` will drain the queue and
    apply locally; the cloud-to-branch push is the responsibility of
    a downstream worker (deferred PR).

    Raises :class:`EmailYaRegistradoError` if an active user already
    holds ``email`` (exact match, same convention as ``auth.py::login``'s
    lookup). Without this guard two active rows could share an email --
    ``login`` would then match whichever row its ``WHERE`` clause
    returns first, silently logging the admin into an unrelated account.

    The SELECT-then-INSERT above is a fast-path UX guard only -- it is
    NOT race-free by itself: two concurrent calls with the same ``email``
    can both read "no active row" before either commits. The backstop is
    the partial UNIQUE index ``prod.usuarios_email_uk01`` (migration
    ``0068_usuarios_email_activo_uk``, ``UNIQUE (email) WHERE
    vigente_hasta IS NULL``); the ``except IntegrityError`` below catches
    the loser of that race and re-raises the same
    :class:`EmailYaRegistradoError` the pre-check raises, so the HTTP
    handler's 409 mapping covers both paths identically.
    """
    if email is not None:
        existing = await session.execute(
            select(Usuarios.uuid).where(
                Usuarios.email == email,
                Usuarios.vigente_hasta.is_(None),
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise EmailYaRegistradoError(
                f"ya existe un usuario activo con email={email}"
            )

    password_hash = _bcrypt_hash(password)

    # 1) Insert the user. ``close_and_insert`` flushes internally, so the
    #    partial-unique-index violation (concurrent duplicate email that
    #    slipped past the pre-check above) surfaces here as
    #    ``IntegrityError`` wrapping asyncpg's ``UniqueViolationError``.
    try:
        user = await close_and_insert(
            session,
            Usuarios,
            current_uuid=None,
            new_attrs={
                "nombre": nombre,
                "apellido": apellido,
                "cedula": cedula,
                "email": email,
                "password_hash": password_hash,
                "rol": rol,
            },
            actor_uuid=actor_uuid,
            log_tx=False,  # user creation isn't a bi-temporal state event
        )
    except IntegrityError as exc:
        await session.rollback()
        raise EmailYaRegistradoError(
            f"ya existe un usuario activo con email={email}"
        ) from exc
    await session.flush()  # populate user.uuid

    # 2) Fan-out to the branch assignments + queue.
    for sucursal_uuid in sucursales_asignadas:
        await _asignar_sucursal_helper(
            session,
            actor_uuid=actor_uuid,
            usuario_uuid=user.uuid,
            sucursal_uuid=sucursal_uuid,
            create_user_payload=True,
        )

    return user


def usuario_in_scope_clause(
    permitidas: Collection[uuid_lib.UUID],
) -> ColumnElement[bool]:
    """SQL predicate on ``Usuarios.uuid``: is the user manageable by an admin
    whose branch scope is ``permitidas``? (SC1)

    A user is manageable when it holds at least one OPEN ``usuarios_sucursal``
    row inside ``permitidas``, OR holds no open assignment at all (a freshly
    created user that the web_admin wizard has not assigned yet -- without
    this a scoped admin could not finish the two-step create flow).
    An empty ``permitidas`` fails closed (matches nothing).
    """
    if not permitidas:
        return false()
    open_in_scope = exists().where(
        UsuariosSucursal.uuid_usuario == Usuarios.uuid,
        UsuariosSucursal.vigente_hasta.is_(None),
        UsuariosSucursal.uuid_sucursal.in_(list(permitidas)),
    )
    any_open = exists().where(
        UsuariosSucursal.uuid_usuario == Usuarios.uuid,
        UsuariosSucursal.vigente_hasta.is_(None),
    )
    return or_(open_in_scope, ~any_open)


async def usuario_visible(
    session: AsyncSession,
    *,
    usuario_uuid: uuid_lib.UUID,
    permitidas: Collection[uuid_lib.UUID],
) -> bool:
    """True when ``usuario_uuid`` exists and is inside the admin's scope."""
    stmt = select(Usuarios.uuid).where(
        Usuarios.uuid == usuario_uuid,
        usuario_in_scope_clause(permitidas),
    )
    return (await session.execute(stmt)).first() is not None


async def list_active_usuarios(
    session: AsyncSession,
    *,
    limit: int = 100,
    permitidas: Collection[uuid_lib.UUID] | None = None,
) -> list[Usuarios]:
    """Return one page of currently-open ``prod.usuarios`` rows.

    KD-LOGIN-01-style SELECT-only helper: ``SELECT Usuarios WHERE
    vigente_hasta IS NULL ORDER BY created_at DESC LIMIT :limit``.

    No cursor yet -- IT-1.4 doesn't call for one. The ``limit``
    ceiling matches ``schemas.auth.LoginHistorico`` precedent.
    """
    stmt = select(Usuarios).where(Usuarios.vigente_hasta.is_(None))
    if permitidas is not None:
        stmt = stmt.where(usuario_in_scope_clause(permitidas))
    stmt = stmt.order_by(Usuarios.created_at.desc(), Usuarios.uuid.asc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_active_asignaciones_usuario(
    session: AsyncSession,
    *,
    usuario_uuid: uuid_lib.UUID,
) -> list[UsuariosSucursal]:
    """Return the currently-open ``prod.usuarios_sucursal`` rows for one user."""
    stmt = (
        select(UsuariosSucursal)
        .where(
            UsuariosSucursal.uuid_usuario == usuario_uuid,
            UsuariosSucursal.vigente_hasta.is_(None),
        )
        .order_by(UsuariosSucursal.vigente_desde.desc(), UsuariosSucursal.uuid.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_branch_assignments_for_users(
    session: AsyncSession,
    *,
    user_uuids: list[uuid_lib.UUID],
) -> dict[uuid_lib.UUID, list[SucursalAsignadaResumen]]:
    """Return currently-open branch assignments for a batch of users.

    Powers the embedded ``sucursales`` field on
    :class:`schemas.admin.AdminUsuarioRead`. The two-round-trip shape
    is deliberate: ONE ``SELECT`` against ``prod.usuarios_sucursal``
    with ``uuid_usuario IN (...) AND vigente_hasta IS NULL`` to grab
    every active assignment, plus ONE ``SELECT`` against
    ``prod.sucursal`` with ``uuid IN (...) AND vigente_hasta IS NULL``
    to resolve the ``nombre`` / ``prefijo_nombre`` snapshot of each
    referenced branch. The Python-side join avoids both N+1 (per-user
    round trips) and a single fat ``JOIN`` (which would emit duplicate
    user rows and complicate ordering).

    Bi-temporal semantics
    ---------------------

    - Assignment filter: ``vigente_hasta IS NULL`` on
      ``prod.usuarios_sucursal`` -- only currently-open assignments.
    - Branch filter: ``vigente_hasta IS NULL`` on ``prod.sucursal`` --
      only the currently-open version of the branch.
    - An assignment to a branch whose currently-open version does not
      exist (closed/expired branch) still appears in the output with
      ``nombre=None`` / ``prefijo_nombre=None``. We surface the row
      rather than silently dropping it: it is auditable evidence that
      this user once had access to that branch, and the admin table
      can render "(sucursal cerrada)" without a second query.

    Returns a dict keyed by ``uuid_usuario``. Users with no open
    assignments map to an empty list (not absent), so callers can do
    ``mapping[user.uuid]`` without a default. Empty ``user_uuids``
    short-circuits to ``{}`` without touching the DB.

    Why not eager-load via an ORM relationship?
    -------------------------------------------

    ``Usuarios`` already has bi-temporal close+insert semantics
    (``vigente_hasta``) that interact poorly with SQLAlchemy's
    ``selectinload`` on a relationship that has its own
    ``vigente_hasta IS NULL`` filter -- the loader wants the full
    history and the consumer wants only the open window. Keeping this
    helper as two explicit ``SELECT``s is shorter, more predictable,
    and reviewable line-by-line in ``EXPLAIN ANALYZE``.
    """
    if not user_uuids:
        return {}

    # 1) All currently-open assignments for the batch.
    stmt = (
        select(UsuariosSucursal.uuid, UsuariosSucursal.uuid_usuario, UsuariosSucursal.uuid_sucursal, UsuariosSucursal.vigente_desde)
        .where(
            UsuariosSucursal.uuid_usuario.in_(user_uuids),
            UsuariosSucursal.vigente_hasta.is_(None),
        )
        .order_by(
            UsuariosSucursal.uuid_usuario.asc(),
            UsuariosSucursal.vigente_desde.desc(),
        )
    )
    result = await session.execute(stmt)
    assignment_rows = result.all()

    if not assignment_rows:
        return {uuid: [] for uuid in user_uuids}

    # 2) Resolve the currently-open version of every referenced branch
    #    in one shot. The result set is small (max one row per branch
    #    UUID) -- a regular ``SELECT ... IN (...)`` is the right shape.
    branch_uuids = {row[2] for row in assignment_rows}
    branch_stmt = select(Sucursal.uuid, Sucursal.nombre, Sucursal.prefijo_nombre).where(
        Sucursal.uuid.in_(branch_uuids),
        Sucursal.vigente_hasta.is_(None),
    )
    branch_result = await session.execute(branch_stmt)
    branch_lookup: dict[uuid_lib.UUID, tuple[str | None, str | None]] = {
        uuid_: (nombre, prefijo) for uuid_, nombre, prefijo in branch_result.all()
    }

    # 3) Stitch the two result sets into the response shape. We keep
    #    the assignment's ``vigente_desde`` (when the user was attached
    #    to the branch) and the branch's currently-open name snapshot.
    out: dict[uuid_lib.UUID, list[SucursalAsignadaResumen]] = {
        uuid_: [] for uuid_ in user_uuids
    }
    for _asig_uuid, user_uuid, branch_uuid, vigente_desde in assignment_rows:
        nombre, prefijo = branch_lookup.get(
            branch_uuid, (None, None)
        )
        out[user_uuid].append(
            SucursalAsignadaResumen(
                uuid_sucursal=branch_uuid,
                nombre=nombre,
                prefijo_nombre=prefijo,
                vigente_desde=vigente_desde,
            )
        )
    return out


async def asignar_sucursal(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    usuario_uuid: uuid_lib.UUID,
    sucursal_uuid: uuid_lib.UUID,
) -> UsuariosSucursal:
    """Open a NEW ``prod.usuarios_sucursal`` version for the pair.

    Two cases:

    - No prior assignment ever existed -> INSERT a fresh row.
    - A prior assignment exists but ``vigente_hasta IS NOT NULL`` ->
      close+insert a new version (``vigente_desde = NOW()``,
      ``vigente_hasta = NULL``).
    - A prior assignment is still open (``vigente_hasta IS NULL``) ->
      the unique constraint
      ``(uuid_sucursal, uuid_usuario, vigente_desde)`` allows it
      (a second open row is a duplicate, not a constraint failure);
      we detect that here and raise :class:`UsuarioYaAsignadoError`
      so the handler returns 409.
    """
    existing = await list_active_asignaciones_usuario(session, usuario_uuid=usuario_uuid)
    for row in existing:
        if row.uuid_sucursal == sucursal_uuid:
            raise UsuarioYaAsignadoError(
                f"user {usuario_uuid} is already assigned to branch {sucursal_uuid}"
            )
    return await _asignar_sucursal_helper(
        session,
        actor_uuid=actor_uuid,
        usuario_uuid=usuario_uuid,
        sucursal_uuid=sucursal_uuid,
        create_user_payload=False,
    )


async def desasignar_sucursal(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    usuario_uuid: uuid_lib.UUID,
    sucursal_uuid: uuid_lib.UUID,
) -> None:
    """Close the currently-open ``prod.usuarios_sucursal`` row.

    No-op (returns ``None``) if no open assignment exists -- the
    handler maps that to a 404 so an idempotent DELETE is not silently
    accepted but a missing assignment doesn't 500.

    Unlike :func:`asignar_sucursal`, a deassignment does NOT close+insert
    a new version -- it closes the currently-open row in place with
    ``vigente_hasta = NOW()`` via :func:`close_only`. There is no "active"
    successor row; the assignment is simply gone.
    """
    from sqlalchemy import update

    # Fetch the open row's UUID first -- the (uuid_usuario, uuid_sucursal)
    # pair alone isn't enough because each pair has many history versions.
    stmt = select(UsuariosSucursal).where(
        UsuariosSucursal.uuid_usuario == usuario_uuid,
        UsuariosSucursal.uuid_sucursal == sucursal_uuid,
        UsuariosSucursal.vigente_hasta.is_(None),
    )
    result = await session.execute(stmt)
    open_row = result.scalar_one_or_none()
    if open_row is None:
        return
    # Close-only: stamp ``vigente_hasta`` and ``estado`` on the existing
    # row. No new row is created, so the user's assignment list returns
    # to empty after the DELETE.
    now = datetime.now(UTC).replace(tzinfo=None)
    await session.execute(
        update(UsuariosSucursal)
        .where(
            UsuariosSucursal.uuid == open_row.uuid,
            UsuariosSucursal.vigente_hasta.is_(None),
        )
        .values(vigente_hasta=now, estado="inactivo")
    )


async def _asignar_sucursal_helper(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    usuario_uuid: uuid_lib.UUID,
    sucursal_uuid: uuid_lib.UUID,
    create_user_payload: bool,
) -> UsuariosSucursal:
    """Insert the ``prod.usuarios_sucursal`` row + queue the sync.

    ``create_user_payload=True`` is the create-user call site: we
    embed the full user payload (name, email, role) into ``datos`` so
    the branch can build a complete INSERT without a second lookup.
    ``create_user_payload=False`` is the re-assignment call site: the
    user already exists in the branch (we hope); we queue just the
    assignment payload.
    """
    if create_user_payload:
        # Fetch the freshly-inserted user to snapshot its full payload.
        # The close+insert already flushed the row into the session.
        stmt = select(Usuarios).where(Usuarios.uuid == usuario_uuid)
        result = await session.execute(stmt)
        user_row = result.scalar_one()
        datos = {
            "uuid": str(user_row.uuid),
            "nombre": user_row.nombre,
            "apellido": user_row.apellido,
            "cedula": user_row.cedula,
            "email": user_row.email,
            "password_hash": user_row.password_hash,
            "rol": user_row.rol,
            "uuid_sucursal": str(sucursal_uuid),
        }
    else:
        datos = {
            "uuid_usuario": str(usuario_uuid),
            "uuid_sucursal": str(sucursal_uuid),
        }

    # Insert the assignment row.
    new_row = await close_and_insert(
        session,
        UsuariosSucursal,
        current_uuid=None,
        new_attrs={
            "uuid_usuario": usuario_uuid,
            "uuid_sucursal": sucursal_uuid,
        },
        actor_uuid=actor_uuid,
        log_tx=False,
    )
    await session.flush()  # populate new_row.uuid for the queue

    # Enqueue the row for the apply-pending loop. ``prioridad=10`` is
    # the default for ``insert`` -- passed explicitly for clarity.
    await enqueue(
        session,
        operacion="insert",
        tabla="usuarios_sucursal",
        uuid_registro=new_row.uuid,
        datos=datos,
        uuid_sucursal=sucursal_uuid,
        prioridad=10,
    )
    return new_row


class UsuarioYaAsignadoError(Exception):
    """Raised by :func:`asignar_sucursal` when the assignment is already open.

    The handler maps this to HTTP 409 (Conflict).
    """


class EmailYaRegistradoError(Exception):
    """Raised by :func:`create_admin_usuario` when the email is already in use
    by another active user.

    The handler maps this to HTTP 409 (Conflict).
    """


async def revocar_permiso(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    usuario_uuid: uuid_lib.UUID,
    permiso_uuid: uuid_lib.UUID,
) -> bool:
    """Close the currently-open ``prod.permisos_usuario`` row.

    Returns ``True`` if an open grant was found and closed; ``False``
    if no open grant existed (the handler maps that to 404).

    Symmetric with :func:`desasignar_sucursal`: same close-only
    semantics (no successor row), same FK-existence guard, same
    sync_queue enqueue so the revoke propagates to the branches. The
    ``_no_op_if_missing`` contract is what the AGENTS.md §3
    bi-temporal convention requires: every "destructive" operation
    against a ``[V]`` table is actually a ``close_only`` against the
    currently-open row, NOT a ``DELETE``.
    """
    from sqlalchemy import select as _select

    # Fetch the open row's UUID first -- the
    # (uuid_usuario, uuid_permiso) pair alone isn't enough because
    # each pair has many history versions (the UK includes
    # ``vigente_desde``).
    stmt = _select(PermisosUsuario).where(
        PermisosUsuario.uuid_usuario == usuario_uuid,
        PermisosUsuario.uuid_permiso == permiso_uuid,
        PermisosUsuario.vigente_hasta.is_(None),
    )
    result = await session.execute(stmt)
    open_row = result.scalar_one_or_none()
    if open_row is None:
        return False

    # Permission name lookup -- the FK to ``permisos`` is optional
    # (nullable FK) so we resolve the code via a sibling read on the
    # ``permisos`` table. Used by the "último admin" guard below.
    code_stmt = _select(Permisos.permiso).where(Permisos.uuid == permiso_uuid)
    code_result = await session.execute(code_stmt)
    permiso_codigo = code_result.scalar_one_or_none()

    # ``último admin`` guard (REQ-X-OPER-007): if the revoked
    # permission is ``admin_usuarios`` AND the user is the LAST
    # currently-granted admin, refuse the revoke with a typed
    # exception so the handler can return ``409 ultimo_admin``.
    if permiso_codigo == "admin_usuarios":
        if await _is_last_admin(session, exclude_usuario=usuario_uuid):
            raise UltimoAdminError(
                f"cannot revoke the last active admin_usuarios grant "
                f"for user {usuario_uuid}"
            )

    await close_only(
        session,
        PermisosUsuario,
        open_row.uuid,
        actor_uuid=actor_uuid,
    )

    # Enqueue the revoke for the apply-pending loop on the branches.
    # The payload mirrors ``asignar_permiso`` (not yet implemented --
    # PR-B of HU-F16 will add it), so for now we send the bare pair
    # and let the branch resolve by uuid alone.
    await enqueue(
        session,
        operacion="delete",
        tabla="permisos_usuario",
        uuid_registro=open_row.uuid,
        datos={
            "uuid_usuario": str(usuario_uuid),
            "uuid_permiso": str(permiso_uuid),
        },
        uuid_sucursal=None,
        prioridad=10,
    )
    return True


async def _is_last_admin(
    session: AsyncSession,
    *,
    exclude_usuario: uuid_lib.UUID,
) -> bool:
    """True iff ``exclude_usuario`` is the LAST admin in the system.

    The "admin" predicate is ``holds the ``admin_usuarios`` permission
    grant with ``vigente_hasta IS NULL``. We count remaining such
    grants EXCLUDING the user passed in (which is the candidate for
    revoke). If the count is zero, the candidate is the last admin.

    Used by :func:`revocar_permiso` as the gate; raised as
    :class:`UltimoAdminError` (handled as ``409 ultimo_admin``) so the
    admin surface has a typed error rather than a generic 500.

    The helper exists in the repo layer because the count is a SQL
    aggregate -- moving it to the handler would mean two round trips
    (check, then act), which is exactly the kind of TOCTOU race that
    bi-temporal close+insert was designed to avoid. Single round trip
    keeps the guard atomic with the revoke itself.
    """
    from sqlalchemy import func as _func
    from sqlalchemy import select as _select

    admin_permiso_subq = _select(Permisos.uuid).where(
        Permisos.permiso == "admin_usuarios",
        Permisos.vigente_hasta.is_(None),
    )
    admin_permiso_subq = admin_permiso_subq.subquery()

    stmt = _select(_func.count()).select_from(PermisosUsuario).where(
        PermisosUsuario.uuid_permiso == admin_permiso_subq.c.uuid,
        PermisosUsuario.vigente_hasta.is_(None),
        PermisosUsuario.uuid_usuario != exclude_usuario,
    )
    result = await session.execute(stmt)
    remaining = result.scalar_one()
    return remaining == 0


async def update_admin_usuario(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    usuario_uuid: uuid_lib.UUID,
    nombre: str | None,
    apellido: str | None,
    cedula: str | None,
    email: str | None,
    rol: str | None,
) -> Usuarios | None:
    """Bi-temporal close+insert update of a single ``prod.usuarios`` row.

    Every parameter is ``Optional``: ``None`` means "leave the
    existing value alone" (mirrors :class:`AdminUsuarioUpdateRequest`
    semantics). Caller pre-filters to only the fields it actually
    wants to change -- we do NOT touch a field whose value is ``None``.

    Returns the new open version, or ``None`` if no open row exists.

    Raises :class:`EmailYaRegistradoError` if ``email`` is being changed
    to a value another active user already holds -- same guard as
    :func:`create_admin_usuario`, so editing a user's email can't
    silently recreate the duplicate-email bug the create path already
    closes. See that function's docstring for the ``IntegrityError``
    backstop this mirrors (partial UNIQUE index ``prod.usuarios_email_uk01``).
    """
    # Fetch the open row first -- close+insert needs its current_uuid
    # so the FK history chain stays intact.
    stmt = select(Usuarios).where(
        Usuarios.uuid == usuario_uuid,
        Usuarios.vigente_hasta.is_(None),
    )
    result = await session.execute(stmt)
    current = result.scalar_one_or_none()
    if current is None:
        return None

    # Email-uniqueness pre-check -- only when the patch actually changes
    # the value (a no-op resubmit of the user's own current email must
    # not self-conflict). ``Usuarios.uuid != current.uuid`` excludes the
    # row being edited from the active-row scan.
    if email is not None and email != current.email:
        existing = await session.execute(
            select(Usuarios.uuid).where(
                Usuarios.email == email,
                Usuarios.vigente_hasta.is_(None),
                Usuarios.uuid != current.uuid,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise EmailYaRegistradoError(
                f"ya existe un usuario activo con email={email}"
            )

    # Build the new_attrs dict from non-None inputs. ``getattr`` lets
    # the caller pass a sparse payload without us having to know the
    # schema field order up-front.
    overrides: dict[str, object] = {}
    if nombre is not None:
        overrides["nombre"] = nombre
    if apellido is not None:
        overrides["apellido"] = apellido
    if cedula is not None:
        overrides["cedula"] = cedula
    if email is not None:
        overrides["email"] = email
    if rol is not None:
        overrides["rol"] = rol

    # If every field was None, the caller sent an empty patch -- we
    # return the open row unchanged rather than write a no-op version.
    if not overrides:
        return current

    try:
        new_row = await close_and_insert(
            session,
            Usuarios,
            current_uuid=current.uuid,
            new_attrs=overrides,
            actor_uuid=actor_uuid,
            log_tx=False,
        )
    except IntegrityError as exc:
        await session.rollback()
        raise EmailYaRegistradoError(
            f"ya existe un usuario activo con email={email}"
        ) from exc

    # Enqueue the patch so branches that already have a copy of the
    # user pick up the new version on their next sync drain.
    await enqueue(
        session,
        operacion="update",
        tabla="usuarios",
        uuid_registro=new_row.uuid,
        datos={
            "uuid": str(new_row.uuid),
            "nombre": new_row.nombre,
            "apellido": new_row.apellido,
            "cedula": new_row.cedula,
            "email": new_row.email,
            "rol": new_row.rol,
        },
        uuid_sucursal=None,
        prioridad=10,
    )

    return new_row


async def list_permisos(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[Permisos]:
    """Return currently-open rows of the ``prod.permisos`` catalog.

    The catalog is bi-temporal too -- the same close+insert rule
    applies if a permission code is ever revoked -- but the read here
    is restricted to ``vigente_hasta IS NULL`` so the admin UI only
    shows active codes.
    """
    stmt = (
        select(Permisos)
        .where(Permisos.vigente_hasta.is_(None))
        .order_by(Permisos.permiso.asc(), Permisos.uuid.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_active_permisos_usuario(
    session: AsyncSession,
    *,
    usuario_uuid: uuid_lib.UUID,
) -> list[tuple[PermisosUsuario, Permisos]]:
    """Return currently-open permission grants for one user.

    Joins to ``prod.permisos`` so the handler can surface the
    permission code string alongside the junction row. Returns the
    tuples to keep the join columns available for the response shape
    (the FK relation is enough; the code is what the UI shows).
    """
    stmt = (
        select(PermisosUsuario, Permisos)
        .join(Permisos, Permisos.uuid == PermisosUsuario.uuid_permiso)
        .where(
            PermisosUsuario.uuid_usuario == usuario_uuid,
            PermisosUsuario.vigente_hasta.is_(None),
        )
        .order_by(
            Permisos.permiso.asc(),
            PermisosUsuario.vigente_desde.desc(),
        )
    )
    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


class PermisoYaAsignadoError(Exception):
    """Raised by :func:`asignar_permiso` when the user already holds it."""


class PermisoNoEncontradoError(Exception):
    """Raised by :func:`asignar_permiso` when ``permiso_uuid`` is unknown.

    The handler maps this to ``404 permiso_no_encontrado`` -- distinct
    from the generic 404 we use for unknown ``usuario_uuid`` so the
    admin UI can render a targeted message.
    """


class UsuarioNoEncontradoError(Exception):
    """Raised by repo helpers when no open ``prod.usuarios`` row exists.

    Surfaces as ``404 usuario_no_encontrado``.
    """


class UltimoAdminError(Exception):
    """Raised by :func:`revocar_permiso` when revoking would leave zero
    currently-active admins in the system.

    Mapped to ``409 ultimo_admin`` so the admin UI can render a
    targeted warning instead of a generic 500. The guard is
    REQ-OPS-007 (admin_usuarios revoke protection) and fires for the
    ``admin_usuarios`` permission code only -- other permissions can
    be revoked from a user's last granted slot without this guard.
    """


async def asignar_permiso(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    usuario_uuid: uuid_lib.UUID,
    permiso_uuid: uuid_lib.UUID,
) -> PermisosUsuario:
    """Open a new ``prod.permisos_usuario`` row (close+insert).

    Returns the new open row on success. Raises
    :class:`PermisoYaAsignadoError` if the user already holds the
    permission -- the UK on ``(uuid_usuario, uuid_permiso,
    vigente_desde)`` would reject the INSERT, but we surface it as a
    typed exception so the handler can return ``409 permiso_ya_asignado``
    instead of a generic 500.
    """
    # Check the FK targets first -- a missing FK means the permission
    # uuid does not exist, which the handler maps to 404.
    perm_st = select(Permisos).where(
        Permisos.uuid == permiso_uuid,
        Permisos.vigente_hasta.is_(None),
    )
    perm_row = (await session.execute(perm_st)).scalar_one_or_none()
    if perm_row is None:
        raise PermisoNoEncontradoError(
            f"permiso {permiso_uuid} not found or not vigente"
        )

    user_st = select(Usuarios).where(
        Usuarios.uuid == usuario_uuid,
        Usuarios.vigente_hasta.is_(None),
    )
    user_row = (await session.execute(user_st)).scalar_one_or_none()
    if user_row is None:
        raise UsuarioNoEncontradoError(f"usuario {usuario_uuid} not found")

    # Check no open grant already exists for this (user, permiso) pair.
    existing_st = select(PermisosUsuario).where(
        PermisosUsuario.uuid_usuario == usuario_uuid,
        PermisosUsuario.uuid_permiso == permiso_uuid,
        PermisosUsuario.vigente_hasta.is_(None),
    )
    existing = (await session.execute(existing_st)).scalar_one_or_none()
    if existing is not None:
        raise PermisoYaAsignadoError(
            f"user {usuario_uuid} already has permission {permiso_uuid}"
        )

    new_row = await close_and_insert(
        session,
        PermisosUsuario,
        current_uuid=None,
        new_attrs={
            "uuid_usuario": usuario_uuid,
            "uuid_permiso": permiso_uuid,
        },
        actor_uuid=actor_uuid,
        log_tx=False,
    )

    await enqueue(
        session,
        operacion="insert",
        tabla="permisos_usuario",
        uuid_registro=new_row.uuid,
        datos={
            "uuid_usuario": str(usuario_uuid),
            "uuid_permiso": str(permiso_uuid),
        },
        uuid_sucursal=None,
        prioridad=10,
    )
    return new_row


async def list_sesiones_activas(
    session: AsyncSession,
    *,
    usuario_uuid: uuid_lib.UUID,
) -> list:
    """Return currently-open ``prod.sesion`` rows for one user.

    Filters on ``uuid_usuario`` and ``timestamp_cierre IS NULL``.
    Note: ``prod.sesion`` is the cash-session [L-S] table -- the
    columns the frontend expects (``ip_origen``, ``user_agent``,
    ``ultimo_activity``) do not exist on this table. The handler
    fills them with ``None`` so the wire contract is honest; if a
    future PR adds the columns the response flips to real values with
    no caller change.
    """
    # Local import to avoid a cycle: Sesion model imports from
    # ``models.base`` which imports from ``app_factory`` indirectly.
    from ..models.L_S.sesion import Sesion

    stmt = (
        select(Sesion)
        .where(
            Sesion.uuid_usuario == usuario_uuid,
            Sesion.timestamp_cierre.is_(None),
        )
        .order_by(
            Sesion.timestamp_apertura.desc().nulls_last(),
            Sesion.uuid.asc(),
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_login_historico(
    session: AsyncSession,
    *,
    usuario_uuid: uuid_lib.UUID,
    limit: int = 10,
) -> list:
    """Return the latest ``prod.login`` rows for one user.

    Reuses the cursor-pagination shape from
    :func:`api.v1.usuarios_login::list_login_attempts_paginated` -- same
    schema, same model -- so this endpoint does not invent a new
    ordering. The handler applies the limit and the cursor in
    :mod:`api.v1.usuarios_login`.
    """
    from ..models.L_S.login import Login

    stmt = (
        select(Login)
        .where(Login.uuid_usuario == usuario_uuid)
        .order_by(Login.timestamp_evento.desc().nulls_last(), Login.uuid.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def generate_temp_password() -> str:
    """12-char temporary password per IT-1.7 spec.

    Mixed charset (upper, lower, digits, two symbols). Avoids
    look-alike characters (``0`` vs ``O``, ``1`` vs ``l``) so the admin
    can read it over the phone without ambiguity.
    """
    import secrets
    import string

    alphabet = (
        "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I, O
        "abcdefghijkmnopqrstuvwxyz"  # no l
        "23456789"                   # no 0, 1
        "!@#%&*?"
    )
    # ``secrets.choice`` is cryptographically secure; the password is
    # only ever shown to the admin once so readability beats entropy
    # here (16 chars of CSPRNG alphabet = ~95 bits).
    return "".join(secrets.choice(alphabet) for _ in range(12))


async def reset_admin_password(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    usuario_uuid: uuid_lib.UUID,
    new_password: str | None = None,
) -> tuple[str, Usuarios]:
    """Bi-temporal close+insert update of ``password_hash``.

    Generates a 12-char temporary password via
    :func:`generate_temp_password` if the caller did not supply one.
    The returned tuple is ``(plaintext, updated_user)`` -- the handler
    surfaces the plaintext in the response so the admin can read it
    once. The plaintext is never persisted; only its bcrypt hash is.

    Returns ``(plaintext, new_user_row)``.
    """
    plaintext = new_password or generate_temp_password()
    password_hash = _bcrypt_hash(plaintext)

    # Reuse the bi-temporal close+insert helper: close the currently
    # open row, insert a new one with the new password_hash. Every
    # other column is preserved.
    stmt = select(Usuarios).where(
        Usuarios.uuid == usuario_uuid,
        Usuarios.vigente_hasta.is_(None),
    )
    result = await session.execute(stmt)
    current = result.scalar_one_or_none()
    if current is None:
        raise UsuarioNoEncontradoError(f"usuario {usuario_uuid} not found")

    new_row = await close_and_insert(
        session,
        Usuarios,
        current_uuid=current.uuid,
        new_attrs={
            "password_hash": password_hash,
            # HU-F16 must-change enforcement (migration 0065). The login
            # handler reads this column to decide between a normal TokenPair
            # and a 5-minute JWT with purpose="must_change" that the operator
            # must exchange at POST /auth/cambiar-password before they get a
            # regular session. Only the cambiar-password handler clears it
            # back to false, so the flag survives every close+insert cycle
            # until the operator actually exchanges the temporary credential.
            "debe_cambiar_password": True,
        },
        actor_uuid=actor_uuid,
        log_tx=False,
    )

    # Audit log: this is a destructive account action and the auditor
    # needs to see who did it without grepping the open row's history
    # chain. The close+insert already writes a log row; this is a
    # dedicated audit entry so the plaintext is never logged (only the
    # fact that a reset happened).
    from ..models.A.log_transaccional import LogTransaccional

    log_attrs = {
        "uuid_usuario": actor_uuid,
        "uuid_sucursal": None,
        "accion": "reset_password",
        "tabla_afectada": "usuarios",
        "uuid_registro_afectado": usuario_uuid,
        "timestamp_evento": _now(),
        "datos_anteriores": {"password_hash_set": True},
        "datos_nuevos": {"password_hash_reset": True},
    }
    # Route through ``repo.hash_chain.append`` so the hash chain is
    # maintained; this admin action is itself auditable.
    from . import hash_chain

    await hash_chain.append(
        session, LogTransaccional, log_attrs, actor_uuid=actor_uuid
    )
    await session.flush()

    # Return ``(plaintext, usuario_uuid)`` -- not ``new_row.uuid``.
    # ``new_row.uuid`` is a NEW version row's UUID (the post
    # close+insert successor), which the caller does NOT recognise
    # as the user they just reset. The original ``usuario_uuid`` is
    # the stable identifier across the bi-temporal rewrite -- it is
    # what the caller's UI already knows about and what the audit log
    # records as ``uuid_registro_afectado``.
    return plaintext, usuario_uuid
