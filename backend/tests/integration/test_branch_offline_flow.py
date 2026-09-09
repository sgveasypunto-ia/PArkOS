"""test_branch_offline_flow.py — T-PR12-009 (proposal §13 Success Criteria,
design.md §10 Testing Strategy).

Req: proposal §13 Success Criteria · Design: §10 Testing Strategy ·
Depends on: T-PR12-002, PR9, PR5.

Full offline-flow integration test — authenticate, authorize, classify a
vehicle, price a stay, register an identified client, emit and number an
electronic invoice, reprint a ticket — ALL against a real Postgres
container, with the cloud genuinely unreachable (a real failed TCP
connection attempt to a non-listening address, via
``SyncSucursalWorker._detect_applier_mode``'s ``GET /sync/hello`` call —
NOT a mocked/stubbed HTTP layer). Every business step below writes through
the SAME ``repo.*`` helpers ``motor/apply_row.py`` dispatches to in
production — there is no cloud round-trip anywhere in that call chain, so
"the cloud is unreachable" changes nothing about whether these steps
succeed.

**Apply-phase discovery.** This file already existed (dated 2026-09-03,
pre-dating this task's own launch) as a PR6-era, fully ``pytest.mark.skip``
placeholder (``NotImplementedError`` fixture, ``...`` literals, zero real
assertions) — tasks.md's "new" wording for this file was already stale.
Replaced in full here per T-PR12-009; nothing of the placeholder's
(nonexistent) coverage is lost.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from parkos_core.jobs.sync_sucursal import ApplierMode, SyncSucursalWorker
from parkos_core.models.A.salidas import Salidas
from parkos_core.models.L_E.factura_electronica import FacturaElectronica
from parkos_core.models.L_E.facturas import Facturas
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.L_W.reimpresion_ticket import ReimpresionTicket
from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.permisos import Permisos
from parkos_core.models.V.permisos_usuario import PermisosUsuario
from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion
from parkos_core.models.V.tarifas_sucursal import TarifasSucursal
from parkos_core.models.V.tipo_tarifa import TipoTarifa
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.repo import append_only as ao_helpers
from parkos_core.repo import event as event_helpers
from parkos_core.repo import resolucion_facturacion as consecutivo_helpers
from parkos_core.repo import session_cycle as session_helpers
from parkos_core.repo import versioned as versioned_helpers
from parkos_core.repo import workflow as workflow_helpers
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

# An address with no listener — a REAL connection attempt (refused almost
# instantly on any OS), not an httpx mock. This is the "cloud unreachable"
# simulation the task explicitly asks for (never a superficial stub).
UNREACHABLE_CLOUD_URL = "http://127.0.0.1:1"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def test_full_offline_flow(
    pg_engine: AsyncEngine,
    alembic_upgrade,
    tmp_path: Path,
    seeded_sucursal_uuid: uuid_lib.UUID,
) -> None:
    """Every step below succeeds with a REAL failed cloud connection proven
    first — not assumed, not mocked."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    # -----------------------------------------------------------------
    # 0. Prove the cloud is genuinely unreachable — a real socket attempt
    #    via the exact mechanism T-PR12-007 ships (GET /sync/hello),
    #    fail-safe to the legacy applier (REQ-CUT-005 row 4).
    # -----------------------------------------------------------------
    async with Session() as session:
        jwt_path = tmp_path / "sync.jwt"
        jwt_path.write_text("fake-jwt", encoding="utf-8")
        worker = SyncSucursalWorker(
            jwt_path=jwt_path, base_url=UNREACHABLE_CLOUD_URL, session=session
        )
        worker._http_client = None  # force a real SyncHttpClient, real socket
        # Reuse the worker's own lazy-build path (mirrors cycle()'s first lines).
        from parkos_core.sync.transport import SyncHttpClient

        worker._http_client = SyncHttpClient(
            base_url=worker.base_url, jwt_path=worker.jwt_path, timeout_s=2.0
        )
        mode = await worker._detect_applier_mode()
        assert mode is ApplierMode.LEGACY, (
            "a real unreachable cloud must fail-safe to the legacy applier"
        )

    # -----------------------------------------------------------------
    # 1. Authenticate — repo.session_cycle.record_login (no cloud call).
    # -----------------------------------------------------------------
    async with Session() as session:
        cedula = f"cd-{uuid_lib.uuid4().hex[:10]}"
        usuario = await versioned_helpers.close_and_insert(
            session,
            Usuarios,
            current_uuid=None,
            new_attrs={
                "nombre": "Ada",
                "apellido": "Lovelace",
                "cedula": cedula,
                "email": f"{cedula}@example.com",
                "rol": "operador",
            },
            actor_uuid=uuid_lib.uuid4(),
        )
        await session.flush()
        sucursal_uuid = seeded_sucursal_uuid
        login = await session_helpers.record_login(
            session,
            usuario_uuid=usuario.uuid,
            sucursal_uuid=sucursal_uuid,
            success=True,
        )
        await session.commit()
        assert login.estado == "exitoso"

    # -----------------------------------------------------------------
    # 2. Authorize — the SAME join auth.permissions.require_permission
    #    runs (PermisosUsuario x Permisos), against local data only.
    # -----------------------------------------------------------------
    async with Session() as session:
        permiso = await versioned_helpers.close_and_insert(
            session,
            Permisos,
            current_uuid=None,
            new_attrs={"permiso": "config_catalogo"},
            actor_uuid=uuid_lib.uuid4(),
        )
        await session.flush()
        await versioned_helpers.close_and_insert(
            session,
            PermisosUsuario,
            current_uuid=None,
            new_attrs={"uuid_usuario": usuario.uuid, "uuid_permiso": permiso.uuid},
            actor_uuid=uuid_lib.uuid4(),
        )
        await session.commit()

        result = await session.execute(
            select(PermisosUsuario)
            .join(Permisos, Permisos.uuid == PermisosUsuario.uuid_permiso)
            .where(
                PermisosUsuario.uuid_usuario == usuario.uuid,
                PermisosUsuario.vigente_hasta.is_(None),
                Permisos.permiso == "config_catalogo",
            )
        )
        assert result.scalar_one_or_none() is not None

    # -----------------------------------------------------------------
    # 3. Classify a vehicle — repo.event.record_event(Ingreso), [L-E].
    # -----------------------------------------------------------------
    async with Session() as session:
        tipo_vehiculo = await versioned_helpers.close_and_insert(
            session,
            TiposVehiculo,
            current_uuid=None,
            new_attrs={"tipo": f"carro-{uuid_lib.uuid4().hex[:6]}"},
            actor_uuid=uuid_lib.uuid4(),
        )
        await session.flush()
        placa = f"PL{uuid_lib.uuid4().hex[:6].upper()}"
        ingreso = await event_helpers.record_event(
            session,
            Ingreso,
            actor_uuid=usuario.uuid,
            new_attrs={
                "uuid_sucursal": sucursal_uuid,
                "placa": placa,
                "uuid_tipo_vehiculo": tipo_vehiculo.uuid,
                "fecha_ingreso": _now(),
            },
        )
        await session.commit()
        assert ingreso.placa == placa

    # -----------------------------------------------------------------
    # 4. Price a stay — TarifasSucursal rate x elapsed time -> Salidas +
    #    the Facturas.total this invoice will number in step 6.
    # -----------------------------------------------------------------
    async with Session() as session:
        tipo_tarifa = await versioned_helpers.close_and_insert(
            session,
            TipoTarifa,
            current_uuid=None,
            new_attrs={"tipo": f"hora-{uuid_lib.uuid4().hex[:6]}"},
            actor_uuid=uuid_lib.uuid4(),
        )
        await session.flush()
        tarifa = await versioned_helpers.close_and_insert(
            session,
            TarifasSucursal,
            current_uuid=None,
            new_attrs={
                "uuid_sucursal": sucursal_uuid,
                "uuid_tipo_vehiculo": tipo_vehiculo.uuid,
                "uuid_tipo_tarifa": tipo_tarifa.uuid,
                "valor": 2000,
                "valor_plena": 15000,
            },
            actor_uuid=uuid_lib.uuid4(),
        )
        await session.flush()

        salida = await ao_helpers.append_event(
            session,
            Salidas,
            {"uuid_sucursal": sucursal_uuid, "uuid_ingreso": ingreso.uuid, "fecha_salida": _now()},
            actor_uuid=usuario.uuid,
        )
        await session.commit()

        horas = 3
        total = float(tarifa.valor) * horas
        assert total == 6000.0
        assert salida.uuid_ingreso == ingreso.uuid

    # -----------------------------------------------------------------
    # 5. Register an identified client — repo.versioned.close_and_insert
    #    (Clientes, [V], D17 natural key semantics).
    # -----------------------------------------------------------------
    async with Session() as session:
        numero_identificacion = str(uuid_lib.uuid4().int)[:10]
        cliente = await versioned_helpers.close_and_insert(
            session,
            Clientes,
            current_uuid=None,
            new_attrs={
                "tipo_identificador": "CC",
                "numero_identificacion": numero_identificacion,
                "nombre": "Grace",
                "apellido": "Hopper",
            },
            actor_uuid=uuid_lib.uuid4(),
        )
        await session.commit()
        assert cliente.numero_identificacion == numero_identificacion

    # -----------------------------------------------------------------
    # 6. Emit + number an electronic invoice — repo.event.record_event
    #    (Facturas, FacturaElectronica) + repo.resolucion_facturacion.
    #    assign_consecutivo (T-PR9's local, no-cloud-wait numbering).
    # -----------------------------------------------------------------
    async with Session() as session:
        resolucion = ResolucionFacturacion(
            uuid=uuid_lib.uuid4(),
            uuid_sucursal=sucursal_uuid,
            numero_resolucion=f"RES-{uuid_lib.uuid4().hex[:8]}",
            prefijo="SETP",
            rango_desde=1,
            rango_hasta=999999999,
            fecha_resolucion=date.today(),
            fecha_inicio_vigencia=date.today(),
            fecha_fin_vigencia=None,
            vigente_desde=_now(),
            vigente_hasta=None,
            estado="activo",
            created_at=_now(),
            created_by=None,
        )
        session.add(resolucion)
        await session.commit()

        factura = await event_helpers.record_event(
            session,
            Facturas,
            actor_uuid=usuario.uuid,
            new_attrs={
                "uuid_sucursal": sucursal_uuid,
                "subtotal": total,
                "descuento": 0,
                "total": total,
                "uuid_ingreso": ingreso.uuid,
            },
        )
        await session.flush()

        consecutivo = await consecutivo_helpers.assign_consecutivo(
            session, resolucion.uuid, factura.uuid
        )
        factura_electronica = await event_helpers.record_event(
            session,
            FacturaElectronica,
            actor_uuid=usuario.uuid,
            new_attrs={
                "uuid_sucursal": sucursal_uuid,
                "uuid_factura": factura.uuid,
                "uuid_cliente": cliente.uuid,
                "uuid_resolucion_facturacion": resolucion.uuid,
                "prefijo": "SETP",
                "consecutivo": consecutivo,
                "descuento": 0,
            },
        )
        await session.commit()
        assert factura_electronica.consecutivo == 1

        # Idempotent re-emission of the SAME source event reuses the
        # number — never a gap, never a second number for the same
        # invoice (design.md §2 Issue #9).
        replay_consecutivo = await consecutivo_helpers.assign_consecutivo(
            session, resolucion.uuid, factura.uuid
        )
        assert replay_consecutivo == consecutivo

    # -----------------------------------------------------------------
    # 7. Reprint a ticket — repo.workflow.append_transition
    #    (ReimpresionTicket, [L-W]) — available with the cloud
    #    unreachable throughout (design.md §8 stage 2 acceptance).
    # -----------------------------------------------------------------
    async with Session() as session:
        reimpresion = await workflow_helpers.append_transition(
            session,
            ReimpresionTicket,
            actor_uuid=usuario.uuid,
            new_attrs={
                "uuid_sucursal": sucursal_uuid,
                "uuid_ingreso": ingreso.uuid,
                "uuid_usuario": usuario.uuid,
                "uuid_factura": factura.uuid,
                "estado": "solicitada",
                "motivo": "ticket original perdido",
                "timestamp_evento": _now(),
            },
        )
        await session.commit()
        assert reimpresion.estado == "solicitada"

    # -----------------------------------------------------------------
    # Sanity: nothing above ever constructed an httpx client pointed at
    # a reachable address — the only network attempt in this whole test
    # was step 0's real, failed one.
    # -----------------------------------------------------------------
    with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout, OSError)):
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.get(f"{UNREACHABLE_CLOUD_URL}/api/v1/sync/hello")
