"""HU-F19.4 — POST /api/v1/workflows/alerta/{uuid}/descartar integration test.

Exercises the handler directly (no HTTP layer / JWT middleware — same
"call the async handler function" style as
``test_envio_dian_reaches_branch.py``) against a REAL Postgres database
(testcontainers + ``alembic upgrade head`` via the ``pg_engine`` fixture).

Asserts the full transition end-to-end:
  1. A root ``prod.alerta`` row (``estado='abierta'``) transitions to a
     NEW ``estado='resuelta'`` row chained via ``uuid_alerta_padre``.
  2. ``observaciones`` lands in the new row's ``datos_nuevos`` JSONB
     column (no dedicated ``observaciones`` column on ``prod.alerta``).
  3. A second ``descartar`` call against the same root now resolves (via
     ``read_chain_tip``) to the already-``resuelta`` row and is rejected
     with 409 ``alerta_ya_resuelta`` — no further row is inserted.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from _seeds import ensure_usuario
from fastapi import HTTPException, Response
from parkos_core.auth.tenancy import TenantContext
from parkos_core.models.L_W.alerta import Alerta
from parkos_core.repo.workflow import append_transition
from parkos_core.schemas.workflows import AlertaDescartarEndpoint
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


@pytest.mark.asyncio
async def test_descartar_alerta_full_transition_then_409_on_retry(
    pg_engine: AsyncEngine, seeded_sucursal_uuid: uuid_lib.UUID
) -> None:
    from parkos_core.api.v1.workflows_alerta import descartar_alerta

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    actor_uuid = uuid_lib.uuid4()
    await ensure_usuario(pg_engine, actor_uuid)  # alerta.uuid_usuario is a real FK
    ctx = TenantContext(
        actor_uuid=actor_uuid,
        actor_rol="operador",
        issuer_prefix="operador-",
        sucursal_uuid=seeded_sucursal_uuid,
        uuid_sesion=None,
    )

    async with Session() as session:
        root = await append_transition(
            session,
            Alerta,
            actor_uuid=actor_uuid,
            new_attrs={
                "uuid_sucursal": seeded_sucursal_uuid,
                "uuid_usuario": actor_uuid,
                "tipo_alerta": "descuadre_critico",
                "estado": "abierta",
            },
            parent_uuid=None,
            parent_fk_column="uuid_alerta_padre",
            log_tx=True,
        )
        await session.commit()
        await session.refresh(root)
        root_uuid = root.uuid

        observaciones = "Conteo verificado manualmente, diferencia justificada"
        result = await descartar_alerta(
            Response(),
            root_uuid,
            AlertaDescartarEndpoint(observaciones=observaciones),
            session,
            ctx,
            None,
            None,
        )

        assert result.estado == "resuelta"
        assert result.uuid_alerta_padre == root_uuid
        assert result.uuid_sucursal == seeded_sucursal_uuid

        # Readback: observaciones persisted into datos_nuevos (no
        # dedicated column on prod.alerta).
        new_row = (
            await session.execute(select(Alerta).where(Alerta.uuid == result.uuid))
        ).scalar_one()
        assert new_row.datos_nuevos == {"observaciones": observaciones}

        # Second call against the SAME root: read_chain_tip now resolves
        # to the 'resuelta' row -> 409, no third row inserted.
        with pytest.raises(HTTPException) as exc_info:
            await descartar_alerta(
                Response(),
                root_uuid,
                AlertaDescartarEndpoint(observaciones="Segundo intento"),
                session,
                ctx,
                None,
                None,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"] == "alerta_ya_resuelta"

        count_stmt = select(Alerta).where(Alerta.uuid_alerta_padre == root_uuid)
        rows = (await session.execute(count_stmt)).scalars().all()
        assert len(rows) == 1  # only the first descartar's row chains off root
