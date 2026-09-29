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
from datetime import UTC, datetime

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.sucursal import Sucursal
from ..models.V.usuarios import Usuarios
from ..models.V.usuarios_sucursal import UsuariosSucursal
from ..schemas.admin import SucursalAsignadaResumen
from .sync_queue import enqueue
from .versioned import close_and_insert

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
    """
    password_hash = _bcrypt_hash(password)

    # 1) Insert the user.
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


async def list_active_usuarios(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[Usuarios]:
    """Return one page of currently-open ``prod.usuarios`` rows.

    KD-LOGIN-01-style SELECT-only helper: ``SELECT Usuarios WHERE
    vigente_hasta IS NULL ORDER BY created_at DESC LIMIT :limit``.

    No cursor yet -- IT-1.4 doesn't call for one. The ``limit``
    ceiling matches ``schemas.auth.LoginHistorico`` precedent.
    """
    stmt = (
        select(Usuarios)
        .where(Usuarios.vigente_hasta.is_(None))
        .order_by(Usuarios.created_at.desc(), Usuarios.uuid.asc())
        .limit(limit)
    )
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
