"""test_workflows_alert_types.py — HU-F11.2 fix (2026-09-24).

TDD RED -> GREEN for ``GET /api/v1/workflows/alert-types``, previously
404 in production (never mounted — see ``api/v1/workflows_alert_types.py``
module docstring for the full root-cause writeup).

Contract under test: the response MUST match the FE's ``.strict()`` Zod
schema (``apps/electron-sucursal/src/lib/api/schemas/alertas.ts::
AlertTypeSchema``) exactly — a bare JSON array of
``{codigo, severidad, descripcion, mensaje}``, NOT the cursor-paginated
``{items, next_cursor}`` envelope the generic catalog factory uses.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.models.A.alert_types import AlertTypes
from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.parametrize("app", ["sucursal"], indirect=True)


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _truncate_alert_types(pg_dsn: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.alert_types")
        conn.commit()


async def _seed_alert_type(
    pg_engine, *, tipo_alerta: str, descripcion: str, severity: str
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            AlertTypes(
                tipo_alerta=tipo_alerta,
                descripcion=descripcion,
                severity=severity,
                created_at=_now_naive(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()


async def test_alert_types_devuelve_array_plano_con_severidad_mapeada(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """REGRESSION: 200 con array plano (no envelope), severity traducida.

    Antes del fix este path devolvía 404 (endpoint nunca montado). Este
    test también fija la traducción de vocabulario
    critical/warning/info -> alta/media/baja (repo/alert_types.py::
    severity_to_severidad) y el mapeo tipo_alerta -> codigo.
    """
    await _truncate_alert_types(pg_dsn)
    await _seed_alert_type(
        pg_engine,
        tipo_alerta="descuadre_critico",
        descripcion="Descuadre critico en arqueo",
        severity="critical",
    )
    await _seed_alert_type(
        pg_engine,
        tipo_alerta="capacidad_agotada",
        descripcion="Capacidad de la sucursal agotada",
        severity="warning",
    )
    await _seed_alert_type(
        pg_engine,
        tipo_alerta="cache_desactualizado",
        descripcion="Cache local desactualizado",
        severity="info",
    )

    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    resp = await client.get(
        "/api/v1/workflows/alert-types",
        params={"uuid_sucursal": str(branch_uuid)},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert isinstance(body, list), (
        f"response MUST be a bare JSON array (FE Zod z.array(...)), "
        f"not a paginated envelope; got {type(body).__name__}: {body!r}"
    )
    by_codigo = {row["codigo"]: row for row in body}
    assert set(by_codigo.keys()) == {
        "descuadre_critico",
        "capacidad_agotada",
        "cache_desactualizado",
    }
    assert by_codigo["descuadre_critico"] == {
        "codigo": "descuadre_critico",
        "severidad": "alta",
        "descripcion": "Descuadre critico en arqueo",
        "mensaje": "Descuadre critico en arqueo",
    }
    assert by_codigo["capacidad_agotada"]["severidad"] == "media"
    assert by_codigo["cache_desactualizado"]["severidad"] == "baja"
    for row in body:
        assert set(row.keys()) == {"codigo", "severidad", "descripcion", "mensaje"}, (
            f"row must carry exactly the 4 FE-contract fields (strict() "
            f"Zod schema); got {sorted(row.keys())}"
        )


__all__ = ["test_alert_types_devuelve_array_plano_con_severidad_mapeada"]
