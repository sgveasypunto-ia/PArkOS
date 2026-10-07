"""Shared actor seeding for the integration suite.

``permisos_usuario``, ``alerta`` and the other actor-bearing tables carry a real
FK to ``prod.usuarios`` (``fk_permisos_usuario_uuid_usuario``,
``fk_alerta_uuid_usuario`` ...). Tests that mint a JWT for ``uuid4()`` and then
grant permissions or file rows on its behalf must therefore have a real
``usuarios`` row first. ``ensure_usuario`` is the single, idempotent place that
creates it, so the per-file ``_grant_permission`` helpers stay one call away
from a valid actor instead of each re-inventing the seed.
"""
from __future__ import annotations

import contextlib
import os
import sys
import uuid as uuid_lib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


async def ensure_usuario(
    pg_engine, actor_uuid: uuid_lib.UUID, *, rol: str = "operador"
) -> uuid_lib.UUID:
    """Insert an open ``usuarios`` row for ``actor_uuid`` unless one exists."""
    from parkos_core.models.V.usuarios import Usuarios

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        existing = (
            await session.execute(
                select(Usuarios.uuid).where(
                    Usuarios.uuid == actor_uuid, Usuarios.vigente_hasta.is_(None)
                )
            )
        ).first()
        if existing is None:
            session.add(
                Usuarios(
                    uuid=actor_uuid,
                    nombre="Test",
                    apellido=rol.capitalize(),
                    email=f"{actor_uuid}@example.com",
                    password_hash="test-hash",
                    rol=rol,
                )
            )
            await session.commit()
    return actor_uuid


async def grant_admin_scope(
    pg_engine,
    actor_uuid: uuid_lib.UUID,
    sucursales: list[uuid_lib.UUID] | tuple[uuid_lib.UUID, ...],
) -> None:
    """Give an ``admin-`` actor an open ``usuarios_sucursal`` row per branch.

    The admin's branch scope is read FRESH from ``usuarios_sucursal``
    (``auth.tenancy.get_tenant_ctx``), not from the JWT's
    ``sucursales_permitidas`` claim, so a token minted for a branch the actor is
    not assigned to is rejected with ``403 unauthorized_sucursal_context``.
    Seeds, idempotently: the actor (``rol='admin'``), any branch that does not
    exist yet (``usuarios_sucursal.uuid_sucursal`` is a real FK) and the
    assignment itself.
    """
    from parkos_core.models.V.sucursal import Sucursal
    from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal

    from tests.conftest import VFixtureFactory

    await ensure_usuario(pg_engine, actor_uuid, rol="admin")
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        for suc in sucursales:
            if (
                await session.execute(select(Sucursal.uuid).where(Sucursal.uuid == suc))
            ).first() is None:
                session.add(VFixtureFactory.build(Sucursal, uuid=suc))
                await session.flush()
            if (
                await session.execute(
                    select(UsuariosSucursal.uuid).where(
                        UsuariosSucursal.uuid_usuario == actor_uuid,
                        UsuariosSucursal.uuid_sucursal == suc,
                        UsuariosSucursal.vigente_hasta.is_(None),
                    )
                )
            ).first() is None:
                session.add(
                    VFixtureFactory.build(
                        UsuariosSucursal, uuid_usuario=actor_uuid, uuid_sucursal=suc
                    )
                )
        await session.commit()


async def close_open_tipos_vehiculo(pg_engine) -> None:
    """Close (logical delete) every open ``tipos_vehiculo`` row.

    The catalog is capped at 5 open rows and the migrations seed that many, so a
    test that creates a tipo must first free the slots. Closing is the
    bi-temporal way to do it (no physical DELETE anywhere); pair it with the
    ``tipos_vehiculo_restaurados`` fixture so the seeded catalog is reopened
    afterwards instead of leaking into later tests.
    """
    from sqlalchemy import text

    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE prod.tipos_vehiculo SET vigente_hasta = NOW(), estado = 'inactivo' "
                "WHERE vigente_hasta IS NULL"
            )
        )


async def grant_permission(pg_engine, actor_uuid: uuid_lib.UUID, perm_code: str) -> None:
    """Idempotently grant ``perm_code`` to ``actor_uuid`` (actor created if needed).

    ``require_permission`` reads ``permisos_usuario`` from the DB, never the JWT.
    The ``permisos`` row is created when the code is not one the migrations seed.
    """
    from datetime import UTC, datetime

    from parkos_core.models.V.permisos import Permisos
    from parkos_core.models.V.permisos_usuario import PermisosUsuario

    await ensure_usuario(pg_engine, actor_uuid)
    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        permiso = (
            await session.execute(
                select(Permisos).where(
                    Permisos.permiso == perm_code, Permisos.vigente_hasta.is_(None)
                )
            )
        ).scalar_one_or_none()
        if permiso is None:
            permiso = Permisos(
                uuid=uuid_lib.uuid4(),
                permiso=perm_code,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
            )
            session.add(permiso)
            await session.flush()
        already = (
            await session.execute(
                select(PermisosUsuario.uuid).where(
                    PermisosUsuario.uuid_usuario == actor_uuid,
                    PermisosUsuario.uuid_permiso == permiso.uuid,
                    PermisosUsuario.vigente_hasta.is_(None),
                )
            )
        ).first()
        if already is None:
            session.add(PermisosUsuario(uuid_usuario=actor_uuid, uuid_permiso=permiso.uuid))
        await session.commit()


async def seed_sucursales(pg_engine, *sucursales: uuid_lib.UUID) -> None:
    """Insert a plain ``sucursal`` row for each uuid that does not exist yet.

    ``envio_dian``, ``validacion_evento``, ``usuarios_sucursal``, ... carry a real
    FK to ``prod.sucursal``, so a bare ``uuid4()`` is no longer a valid branch.
    """
    from parkos_core.models.V.sucursal import Sucursal

    from tests.conftest import VFixtureFactory

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        for suc in sucursales:
            if (
                await session.execute(select(Sucursal.uuid).where(Sucursal.uuid == suc))
            ).first() is None:
                session.add(VFixtureFactory.build(Sucursal, uuid=suc))
        await session.commit()


async def seed_ingreso(pg_engine, uuid_sucursal: uuid_lib.UUID) -> uuid_lib.UUID:
    """Insert a minimal open ``ingreso`` on ``uuid_sucursal`` and return its uuid.

    ``anulaciones.uuid_ingreso`` (and every other ingreso reference) is a real FK.
    """
    from datetime import UTC, datetime

    from parkos_core.models.L_E.ingreso import Ingreso

    ingreso_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Ingreso(
                uuid=ingreso_uuid,
                uuid_sucursal=uuid_sucursal,
                placa=f"SEED{ingreso_uuid.hex[:3].upper()}",
                fecha_ingreso=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        await session.commit()
    return ingreso_uuid


async def ensure_cliente(pg_engine, uuid_cliente: uuid_lib.UUID | None) -> uuid_lib.UUID | None:
    """Idempotently insert a ``clientes`` row with this uuid (``None`` passes through).

    ``factura_electronica.uuid_cliente`` and ``subscripciones_cliente.uuid_cliente``
    are real FKs.
    """
    if uuid_cliente is None:
        return None
    from parkos_core.models.V.clientes import Clientes

    from tests.conftest import VFixtureFactory

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        if (
            await session.execute(select(Clientes.uuid).where(Clientes.uuid == uuid_cliente))
        ).first() is None:
            session.add(VFixtureFactory.build(Clientes, uuid=uuid_cliente))
            await session.commit()
    return uuid_cliente


@contextlib.contextmanager
def cloud_node_env():
    """Run the cloud side of this two-node, one-process simulation as a cloud deploy.

    Applying a ``factura_electronica`` on the cloud lazily imports
    ``parkos_core.dian.cloud.*``, whose import-time guard (REQ-X3, design section
    10 layer 2) refuses to load under ``PARKOS_DEPLOY=branch`` -- the default the
    root conftest pins for the whole session. Switch the env for the cloud-side
    steps and drop the cloud-only modules afterwards so no other test sees a
    branch process that has them loaded.
    """
    previous = os.environ.get("PARKOS_DEPLOY")
    os.environ["PARKOS_DEPLOY"] = "cloud"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PARKOS_DEPLOY", None)
        else:
            os.environ["PARKOS_DEPLOY"] = previous
        for name in [m for m in sys.modules if m.startswith("parkos_core.dian.cloud")]:
            sys.modules.pop(name, None)
            parent, _, attr = name.rpartition(".")
            parent_mod = sys.modules.get(parent)
            if parent_mod is not None and attr in vars(parent_mod):
                delattr(parent_mod, attr)
