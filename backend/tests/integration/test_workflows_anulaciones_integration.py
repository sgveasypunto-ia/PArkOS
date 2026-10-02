"""HU-F20.3 — anulaciones workflow integration tests (real Postgres).

Exercises the handlers directly against a REAL Postgres database
(testcontainers + ``alembic upgrade head`` via the ``pg_engine`` fixture),
same "call the async handler function" style as
``test_workflows_alerta_descartar_integration.py``.

Unlike the alerta precedent, the permission check here is INLINE in the
handler body (``actor_has_permission``, not a bypassable ``Depends``
parameter — see ``workflows_anulaciones.py`` module docstring), so these
tests exercise the REAL permission-gate query against the REAL seeded
``prod.permisos`` catalogue rows (migrations 0002/0019/0059) — no permission
row is re-seeded here, only a ``prod.permisos_usuario`` GRANT referencing
the already-migrated row.

Asserts the full lifecycle end-to-end:
  1. ``solicitar_anulacion`` without the ``anular_ingreso_salida`` grant -> 403.
  2. Full happy-path chain: iniciada -> autorizada -> ejecutada, each step
     gated by its own real permission grant (``aprobar_anulacion`` /
     ``ejecutar_anulacion``).
  3. An actor holding ONLY ``aprobar_anulacion`` cannot execute the
     ``autorizada -> ejecutada`` step -> 403 (the HU's explicit example).
  4. A transition requested out of order (``iniciada -> ejecutada`` directly)
     -> 409 ``illegal_transition``, no row inserted.
  5. A transition against an already-terminal chain -> 409.
"""
from __future__ import annotations

import datetime
import uuid as uuid_lib

import pytest
from fastapi import HTTPException, Response
from parkos_core.auth.tenancy import TenantContext
from parkos_core.models.L_W.anulaciones import Anulaciones
from parkos_core.models.V.permisos import Permisos
from parkos_core.models.V.permisos_usuario import PermisosUsuario
from parkos_core.schemas.workflows import (
    AnulacionesSolicitarEndpoint,
    AnulacionesTransicionEndpoint,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


async def _grant_existing_permission(session, *, actor_uuid: uuid_lib.UUID, codigo: str) -> None:
    """Grant an ALREADY-SEEDED (migration 0002/0019/0059) permission code.

    Does NOT insert a new ``prod.permisos`` row -- only the
    ``prod.permisos_usuario`` junction, referencing the existing open
    catalogue row. Mirrors ``test_permissions_dependency.py``'s
    documented reasoning for why a canonical code must never be
    re-seeded by a test.
    """
    permiso_uuid = (
        await session.execute(
            select(Permisos.uuid).where(
                Permisos.permiso == codigo, Permisos.vigente_hasta.is_(None)
            )
        )
    ).scalar_one()
    now = datetime.datetime.utcnow()
    session.add(
        PermisosUsuario(
            uuid_usuario=actor_uuid,
            uuid_permiso=permiso_uuid,
            vigente_desde=now,
            vigente_hasta=None,
            estado="activo",
            created_at=now,
            created_by=actor_uuid,
            sync_status="sincronizado",
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_solicitar_anulacion_returns_403_without_permission(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    seeded_usuario_uuid: uuid_lib.UUID,
) -> None:
    from parkos_core.api.v1.workflows_anulaciones import solicitar_anulacion

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    ctx = TenantContext(
        actor_uuid=seeded_usuario_uuid,
        actor_rol="operador",
        issuer_prefix="operador-",
        sucursal_uuid=seeded_sucursal_uuid,
        uuid_sesion=None,
    )

    async with Session() as session:
        payload = AnulacionesSolicitarEndpoint(
            tipo_anulable="ingreso", uuid_ingreso=uuid_lib.uuid4(), motivo="Cliente desistio"
        )
        with pytest.raises(HTTPException) as exc_info:
            await solicitar_anulacion(Response(), payload, session, ctx, None)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["detail"] == "anular_ingreso_salida"


@pytest.mark.asyncio
async def test_anulacion_full_happy_path_then_terminal_409(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    seeded_usuario_uuid: uuid_lib.UUID,
) -> None:
    from parkos_core.api.v1.workflows_anulaciones import (
        solicitar_anulacion,
        transicionar_anulacion,
    )

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    actor_uuid = seeded_usuario_uuid
    ctx = TenantContext(
        actor_uuid=actor_uuid,
        actor_rol="operador",
        issuer_prefix="operador-",
        sucursal_uuid=seeded_sucursal_uuid,
        uuid_sesion=None,
    )

    async with Session() as session:
        await _grant_existing_permission(
            session, actor_uuid=actor_uuid, codigo="anular_ingreso_salida"
        )
        await _grant_existing_permission(
            session, actor_uuid=actor_uuid, codigo="aprobar_anulacion"
        )
        await _grant_existing_permission(
            session, actor_uuid=actor_uuid, codigo="ejecutar_anulacion"
        )

        # --- Step 1: solicitar (root, estado='iniciada'). ---------------
        root_payload = AnulacionesSolicitarEndpoint(
            tipo_anulable="ingreso", uuid_ingreso=uuid_lib.uuid4(), motivo="Cliente desistio"
        )
        root = await solicitar_anulacion(Response(), root_payload, session, ctx, None)
        assert root.estado == "iniciada"
        assert root.uuid_anulacion_padre is None
        root_uuid = root.uuid

        # --- Step 2: iniciada -> autorizada. -----------------------------
        aprobar_payload = AnulacionesTransicionEndpoint(
            estado="autorizada", motivo="Revisado y aprobado por admin"
        )
        aprobada = await transicionar_anulacion(
            Response(), root_uuid, aprobar_payload, session, ctx, None
        )
        assert aprobada.estado == "autorizada"
        assert aprobada.uuid_anulacion_padre == root_uuid

        # --- Step 3: autorizada -> ejecutada. -----------------------------
        ejecutar_payload = AnulacionesTransicionEndpoint(
            estado="ejecutada", motivo="Anulacion ejecutada en caja"
        )
        ejecutada = await transicionar_anulacion(
            Response(), root_uuid, ejecutar_payload, session, ctx, None
        )
        assert ejecutada.estado == "ejecutada"
        assert ejecutada.uuid_anulacion_padre == aprobada.uuid

        # --- Step 4: terminal -- any further transition -> 409. ----------
        with pytest.raises(HTTPException) as exc_info:
            await transicionar_anulacion(
                Response(),
                root_uuid,
                AnulacionesTransicionEndpoint(estado="rechazada", motivo="Intento tardio"),
                session,
                ctx,
                None,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"] == "illegal_transition"

        # Only 2 chained rows beyond the root (aprobada + ejecutada).
        count_stmt = select(Anulaciones).where(
            Anulaciones.uuid_anulacion_padre.in_([root_uuid, aprobada.uuid])
        )
        rows = (await session.execute(count_stmt)).scalars().all()
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_transicionar_anulacion_has_aprobar_but_not_ejecutar_returns_403(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    seeded_usuario_uuid: uuid_lib.UUID,
) -> None:
    """HU's explicit example, against the real permission catalogue."""
    from parkos_core.api.v1.workflows_anulaciones import (
        solicitar_anulacion,
        transicionar_anulacion,
    )

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    actor_uuid = seeded_usuario_uuid
    ctx = TenantContext(
        actor_uuid=actor_uuid,
        actor_rol="operador",
        issuer_prefix="operador-",
        sucursal_uuid=seeded_sucursal_uuid,
        uuid_sesion=None,
    )

    async with Session() as session:
        await _grant_existing_permission(
            session, actor_uuid=actor_uuid, codigo="anular_ingreso_salida"
        )
        await _grant_existing_permission(
            session, actor_uuid=actor_uuid, codigo="aprobar_anulacion"
        )
        # Deliberately NOT granted: ejecutar_anulacion.

        root = await solicitar_anulacion(
            Response(),
            AnulacionesSolicitarEndpoint(
                tipo_anulable="salida", uuid_salida=uuid_lib.uuid4(), motivo="motivo"
            ),
            session,
            ctx,
            None,
        )
        aprobada = await transicionar_anulacion(
            Response(),
            root.uuid,
            AnulacionesTransicionEndpoint(estado="autorizada", motivo="aprobado"),
            session,
            ctx,
            None,
        )
        assert aprobada.estado == "autorizada"

        with pytest.raises(HTTPException) as exc_info:
            await transicionar_anulacion(
                Response(),
                root.uuid,
                AnulacionesTransicionEndpoint(estado="ejecutada", motivo="intento sin permiso"),
                session,
                ctx,
                None,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["detail"] == "ejecutar_anulacion"


@pytest.mark.asyncio
async def test_transicionar_anulacion_out_of_order_returns_409(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    seeded_usuario_uuid: uuid_lib.UUID,
) -> None:
    """iniciada -> ejecutada directly (skipping autorizada) -> 409, no INSERT."""
    from parkos_core.api.v1.workflows_anulaciones import (
        solicitar_anulacion,
        transicionar_anulacion,
    )

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    actor_uuid = seeded_usuario_uuid
    ctx = TenantContext(
        actor_uuid=actor_uuid,
        actor_rol="operador",
        issuer_prefix="operador-",
        sucursal_uuid=seeded_sucursal_uuid,
        uuid_sesion=None,
    )

    async with Session() as session:
        await _grant_existing_permission(
            session, actor_uuid=actor_uuid, codigo="anular_ingreso_salida"
        )
        await _grant_existing_permission(
            session, actor_uuid=actor_uuid, codigo="aprobar_anulacion"
        )

        root = await solicitar_anulacion(
            Response(),
            AnulacionesSolicitarEndpoint(
                tipo_anulable="ingreso", uuid_ingreso=uuid_lib.uuid4(), motivo="motivo"
            ),
            session,
            ctx,
            None,
        )

        with pytest.raises(HTTPException) as exc_info:
            await transicionar_anulacion(
                Response(),
                root.uuid,
                AnulacionesTransicionEndpoint(estado="ejecutada", motivo="salto invalido"),
                session,
                ctx,
                None,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"] == "illegal_transition"
        assert exc_info.value.detail["estado_actual"] == "iniciada"

        rows = (
            await session.execute(
                select(Anulaciones).where(Anulaciones.uuid_anulacion_padre == root.uuid)
            )
        ).scalars().all()
        assert len(rows) == 0
