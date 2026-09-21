"""HU-F1.7 / REQ-OPS-042..052 -- Salida lifecycle (rotacion + mensualidad).

Helpers for ``POST /operacion/salidas``:
- ``buscar_ingreso_activo_por_uuid`` (V1)
- ``cotizar_para_salida`` (V5 wrapper over F1.8 PL/pgSQL, raises typed exceptions)
- ``crear_salida_evento`` (Step 8 INSERT [A] via ORM, IntegrityError -> SalidaDuplicada)
- ``insertar_alerta_salida_forzado`` (Step 9, alerts for V2/V5 bypass)
- ``SalidaDuplicada`` (typed 409 mapping)

DEC-SAL-01: writes are append-only. NO UPDATE, NO DELETE.
DEC-SUC-21-NEW: tipo_salida is derived in the handler, NOT persisted.
KD-S7: the cotizar_para_salida call shares the caller's transaction;
       no sub-transactions or SAVEPOINT inside the repo.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.salidas import Salidas
from ..models.L_E.ingreso import Ingreso
from ..models.L_W.alerta import Alerta


class SalidaDuplicada(Exception):
    """409 -- ``fn_salidas_one_exit_per_ingreso`` trigger fired.

    Raised when ``prod.salidas`` rejects an INSERT via the
    ``fn_salidas_one_exit_per_ingreso`` BEFORE INSERT trigger
    (migration 0026). The trigger enforces EXACTLY the same
    semantics as the original partial unique index (one active
    salida per uuid_ingreso, excluding anuladas) — PG rejects
    subqueries in CREATE INDEX predicates so the constraint is
    enforced at INSERT time instead. The substring
    ``one_exit_per_ingreso`` appears in the trigger's
    RAISE EXCEPTION prefix and is what the matcher in
    ``crear_salida_evento`` keys on. Mapped to HTTP 409 by the handler.
    """


async def buscar_ingreso_activo_por_uuid(
    session: AsyncSession, *, uuid_ingreso: uuid_lib.UUID
) -> Ingreso | None:
    """V1: SELECT ingreso WHERE uuid=:p AND vigente_hasta IS NULL
    AND NOT EXISTS salidas (no anulada).

    Returns the ORM ``Ingreso`` row if found, None otherwise.
    """
    # Fast path: direct PK lookup + bi-temporal predicate.
    ingreso_row = await session.get(Ingreso, uuid_ingreso)
    if ingreso_row is None or ingreso_row.vigente_hasta is not None:
        return None

    # Existence check: NOT EXISTS salidas not anulada.
    stmt = text(
        """
        SELECT 1 FROM prod.salidas s
        WHERE s.uuid_ingreso = :uuid_ingreso
          AND NOT EXISTS (
              SELECT 1 FROM prod.anulaciones a
              WHERE a.uuid_salida = s.uuid
                AND a.tipo_anulable = 'salida'
                AND a.estado = 'ejecutada'
          )
        LIMIT 1
        """
    )
    exists = (
        await session.execute(stmt, {"uuid_ingreso": str(uuid_ingreso)})
    ).first()
    if exists is not None:
        return None  # already has a non-anulada salida
    return ingreso_row


async def cotizar_para_salida(
    session: AsyncSession, *, uuid_ingreso: uuid_lib.UUID
) -> dict[str, Any]:
    """V5: invoke ``prod.calcular_cotizacion(:uuid_ingreso)`` and return jsonb.

    Reuses F1.8's PL/pgSQL function via ``repo.cotizacion.cotizar_ingreso``.
    The difference with the GET /cotizar handler is that here the caller
    controls the exception flow (no HTTPException mapping); the handler
    decides whether to insert an alerta or raise 422.

    KD-S7: this call shares the caller's transaction. The PL/pgSQL
    ``SELECT ... FOR SHARE`` on ``tarifas_sucursal`` is held until
    ``session.commit()`` in the handler. NO sub-transactions.

    Raises:
        IngresoNoEncontrado: ``{error:ingreso_no_encontrado}`` payload (covered by V1)
        TarifaNoVigente: ``{error:tarifa_no_vigente}`` payload (KD-3, F1.8)
        IVANoConfigurado: ``{error:iva_no_configurado}`` payload (KD-IVA, F1.8)
    """
    from ..repo.cotizacion import cotizar_ingreso
    return await cotizar_ingreso(session, uuid_ingreso=uuid_ingreso)


async def crear_salida_evento(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    new_attrs: dict[str, Any],
) -> Salidas:
    """Step 8: INSERT ``prod.salidas`` [A] (append-only).

    Defense in depth: REVOKE UPDATE, DELETE (migration 0001 linea 2923)
    + ``fn_salidas_inmutable`` BEFORE UPDATE OR DELETE trigger (lineas
    1990-2003) + ``fn_salidas_one_exit_per_ingreso`` BEFORE INSERT
    trigger (migration 0026). The one-per-ingreso uniqueness replaces
    a partial unique index (PG rejects subqueries in CREATE INDEX
    predicates) — the trigger raises ERRCODE='unique_violation', which
    asyncpg surfaces as IntegrityError code 23505.

    Raises:
        SalidaDuplicada: ``IntegrityError`` with code 23505 fired by
                        the ``fn_salidas_one_exit_per_ingreso``
                        trigger. Mapped to HTTP 409 by the handler.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    new_row = Salidas(
        **new_attrs,
        created_at=now,
        created_by=actor_uuid,
    )
    session.add(new_row)
    try:
        await session.flush()
    except IntegrityError as err:
        # psycopg2/asyncpg: UniqueViolationError code 23505.
        if "one_exit_per_ingreso" in str(err.orig):
            raise SalidaDuplicada() from err
        raise
    return new_row


async def insertar_alerta_salida_forzado(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_salida: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
    motivo: str,
    tipo_alerta: str,  # 'subscripcion_vencida_forzado' | 'tarifa_vigente_forzado'
) -> Alerta:
    """Step 9: INSERT ``prod.alerta`` for V2/V5 bypass.

    Same TX as the salida INSERT (caller commits). R5 mitigation:
    FK commit ordering -- alerta only commits if salida OK.

    ``datos_nuevos`` jsonb (column added by MIGRATION 0025 in F1.6)
    carries ``{"motivo": motivo, "uuid_salida": str(uuid_salida)}``.
    """
    alerta = Alerta(
        uuid_sucursal=uuid_sucursal,
        uuid_usuario=actor_uuid,
        tipo_alerta=tipo_alerta,
        estado="abierta",
        timestamp_evento=datetime.now(UTC).replace(tzinfo=None),
        uuid_arqueo=None,
        datos_nuevos={
            "motivo": motivo,
            "uuid_salida": str(uuid_salida),
        },
    )
    session.add(alerta)
    await session.flush()
    return alerta


__all__ = [
    "SalidaDuplicada",
    "buscar_ingreso_activo_por_uuid",
    "cotizar_para_salida",
    "crear_salida_evento",
    "insertar_alerta_salida_forzado",
]
