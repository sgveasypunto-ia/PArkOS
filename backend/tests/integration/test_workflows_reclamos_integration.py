"""HU-F20.3 — reclamos workflow integration tests (real Postgres).

Same style as ``test_workflows_anulaciones_integration.py``: exercises the
handlers directly against a REAL Postgres database, granting ALREADY-SEEDED
permission codes (``registrar_reclamo`` / ``resolver_reclamo``) rather than
re-seeding them.

Asserts:
  1. ``solicitar_reclamo`` without ``registrar_reclamo`` -> 403.
  2. Full happy-path chain: recibido -> en_investigacion -> resuelto, both
     transition steps gated by the SAME ``resolver_reclamo`` grant (unlike
     anulaciones' per-step split).
  3. ``transicionar_reclamo`` without ``resolver_reclamo`` -> 403.
  4. A transition requested out of order (``recibido -> resuelto`` directly,
     skipping ``en_investigacion``) -> 409 ``illegal_transition``, no row
     inserted.
  5. A transition against an already-terminal chain -> 409.
"""
from __future__ import annotations

import datetime
import uuid as uuid_lib

import pytest
from fastapi import HTTPException, Response
from parkos_core.auth.tenancy import TenantContext
from parkos_core.models.L_W.reclamos import Reclamos
from parkos_core.models.V.permisos import Permisos
from parkos_core.models.V.permisos_usuario import PermisosUsuario
from parkos_core.schemas.workflows import ReclamosSolicitarEndpoint, ReclamosTransicionEndpoint
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


async def _grant_existing_permission(session, *, actor_uuid: uuid_lib.UUID, codigo: str) -> None:
    """Grant an ALREADY-SEEDED permission code (see sibling anulaciones test)."""
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
async def test_solicitar_reclamo_returns_403_without_permission(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    seeded_usuario_uuid: uuid_lib.UUID,
) -> None:
    from parkos_core.api.v1.workflows_reclamos import solicitar_reclamo

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    ctx = TenantContext(
        actor_uuid=seeded_usuario_uuid,
        actor_rol="operador",
        issuer_prefix="operador-",
        sucursal_uuid=seeded_sucursal_uuid,
        uuid_sesion=None,
    )

    async with Session() as session:
        payload = ReclamosSolicitarEndpoint(
            tipo_reclamable="ingreso", uuid_reclamable=uuid_lib.uuid4(), motivo="Cobro doble"
        )
        with pytest.raises(HTTPException) as exc_info:
            await solicitar_reclamo(Response(), payload, session, ctx, None)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["detail"] == "registrar_reclamo"


@pytest.mark.asyncio
async def test_reclamo_full_happy_path_then_terminal_409(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    seeded_usuario_uuid: uuid_lib.UUID,
) -> None:
    from parkos_core.api.v1.workflows_reclamos import solicitar_reclamo, transicionar_reclamo

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
        await _grant_existing_permission(session, actor_uuid=actor_uuid, codigo="registrar_reclamo")
        await _grant_existing_permission(session, actor_uuid=actor_uuid, codigo="resolver_reclamo")

        # --- Step 1: solicitar (root, estado='recibido'). ---------------
        root = await solicitar_reclamo(
            Response(),
            ReclamosSolicitarEndpoint(
                tipo_reclamable="factura",
                uuid_reclamable=uuid_lib.uuid4(),
                motivo="Factura duplicada",
            ),
            session,
            ctx,
            None,
        )
        assert root.estado == "recibido"
        assert root.uuid_reclamo_padre is None

        # --- Step 2: recibido -> en_investigacion. -----------------------
        en_investigacion = await transicionar_reclamo(
            Response(),
            root.uuid,
            ReclamosTransicionEndpoint(estado="en_investigacion", motivo="Tomado en revision"),
            session,
            ctx,
            None,
        )
        assert en_investigacion.estado == "en_investigacion"
        assert en_investigacion.uuid_reclamo_padre == root.uuid

        # --- Step 3: en_investigacion -> resuelto. -----------------------
        resuelto = await transicionar_reclamo(
            Response(),
            root.uuid,
            ReclamosTransicionEndpoint(estado="resuelto", motivo="Reembolso aplicado"),
            session,
            ctx,
            None,
        )
        assert resuelto.estado == "resuelto"
        assert resuelto.uuid_reclamo_padre == en_investigacion.uuid

        # --- Step 4: terminal -- any further transition -> 409. ----------
        with pytest.raises(HTTPException) as exc_info:
            await transicionar_reclamo(
                Response(),
                root.uuid,
                ReclamosTransicionEndpoint(estado="rechazado", motivo="Intento tardio"),
                session,
                ctx,
                None,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"] == "illegal_transition"


@pytest.mark.asyncio
async def test_transicionar_reclamo_without_resolver_reclamo_returns_403(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    seeded_usuario_uuid: uuid_lib.UUID,
) -> None:
    from parkos_core.api.v1.workflows_reclamos import solicitar_reclamo, transicionar_reclamo

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
        await _grant_existing_permission(session, actor_uuid=actor_uuid, codigo="registrar_reclamo")
        # Deliberately NOT granted: resolver_reclamo.

        root = await solicitar_reclamo(
            Response(),
            ReclamosSolicitarEndpoint(
                tipo_reclamable="salida", uuid_reclamable=uuid_lib.uuid4(), motivo="motivo"
            ),
            session,
            ctx,
            None,
        )

        with pytest.raises(HTTPException) as exc_info:
            await transicionar_reclamo(
                Response(),
                root.uuid,
                ReclamosTransicionEndpoint(estado="en_investigacion", motivo="sin permiso"),
                session,
                ctx,
                None,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["detail"] == "resolver_reclamo"


@pytest.mark.asyncio
async def test_transicionar_reclamo_out_of_order_returns_409(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    seeded_usuario_uuid: uuid_lib.UUID,
) -> None:
    """recibido -> resuelto directly (skipping en_investigacion) -> 409, no INSERT."""
    from parkos_core.api.v1.workflows_reclamos import solicitar_reclamo, transicionar_reclamo

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
        await _grant_existing_permission(session, actor_uuid=actor_uuid, codigo="registrar_reclamo")
        await _grant_existing_permission(session, actor_uuid=actor_uuid, codigo="resolver_reclamo")

        root = await solicitar_reclamo(
            Response(),
            ReclamosSolicitarEndpoint(
                tipo_reclamable="ingreso", uuid_reclamable=uuid_lib.uuid4(), motivo="motivo"
            ),
            session,
            ctx,
            None,
        )

        with pytest.raises(HTTPException) as exc_info:
            await transicionar_reclamo(
                Response(),
                root.uuid,
                ReclamosTransicionEndpoint(estado="resuelto", motivo="salto invalido"),
                session,
                ctx,
                None,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"] == "illegal_transition"
        assert exc_info.value.detail["estado_actual"] == "recibido"

        rows = (
            await session.execute(
                select(Reclamos).where(Reclamos.uuid_reclamo_padre == root.uuid)
            )
        ).scalars().all()
        assert len(rows) == 0
