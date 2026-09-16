"""HU-F1.10 / T3.1 + T3.2 — MIGRATION 0028 idempotency + DEC-FE-01 flip.

T3.1 — pre-flight ``DO $$`` aborts on missing tables +
DEC-FE-01 sync catalog flip verification.
T3.2 — Op 2 partial UK + Op 3 covering index + Op 4 GRANT.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest
from parkos_core.sync.catalog import SYNC_CATALOG_BY_NAME
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


def test_envio_dian_direction_flipped_to_branch_to_cloud() -> None:
    """DEC-FE-01: envio_dian is now branch_to_cloud (was cloud_to_branch)."""
    envio_dian = SYNC_CATALOG_BY_NAME.get("envio_dian")
    assert envio_dian is not None
    assert envio_dian.direction == "branch_to_cloud", (
        f"DEC-FE-01 violated: envio_dian direction is "
        f"{envio_dian.direction!r}, expected 'branch_to_cloud'"
    )


@pytest.mark.asyncio
async def test_one_fe_per_factura_partial_uk_blocks_duplicate_fe(
    pg_engine: AsyncEngine,
) -> None:
    """Op 2: partial UK ``one_fe_per_factura`` blocks a 2nd FE row for same uuid_factura.

    Inserts one ``prod.factura_electronica`` row, then attempts a
    second INSERT with the same ``uuid_factura``; the second must
    raise ``IntegrityError`` (pgcode 23505) carrying the index name
    ``one_fe_per_factura``.
    """
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from parkos_core.models.L_E.factura_electronica import FacturaElectronica

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    uuid_factura = None

    async with Session() as session:
        fe1 = FacturaElectronica(
            uuid=None,  # server default
            fecha_retencion_hasta=None,
            uuid_sucursal=None,
            uuid_factura=None,
            uuid_resolucion_facturacion=None,
            prefijo="SETP",
            consecutivo=1,
            descuento=0,
        )
        # Set uuid_factura separately to share between rows
        from datetime import date, timedelta
        uuid_factura = __import__("uuid").uuid4()
        fe1.uuid_factura = uuid_factura
        session.add(fe1)
        await session.commit()

    async with Session() as session:
        fe2 = FacturaElectronica(
            uuid=None,
            fecha_retencion_hasta=date.today() + timedelta(days=5 * 365),
            uuid_sucursal=None,
            uuid_factura=uuid_factura,  # SAME uuid_factura → blocked by partial UK
            uuid_resolucion_facturacion=None,
            prefijo="SETP",
            consecutivo=2,
            descuento=0,
        )
        with pytest.raises(IntegrityError) as exc_info:
            await session.commit()
        msg = str(exc_info.value).lower()
        assert "one_fe_per_factura" in msg or "23505" in msg


@pytest.mark.asyncio
async def test_idx_envio_dian_chain_tip_covering_index_exists(
    pg_engine: AsyncEngine,
) -> None:
    """Op 3: covering index ``idx_envio_dian_chain_tip`` is present."""
    async with pg_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'prod' AND indexname = 'idx_envio_dian_chain_tip'"
            )
        )
        rows = result.fetchall()
    assert len(rows) == 1, (
        f"Op 3 covering index missing: pg_indexes returned {len(rows)} rows "
        f"for idx_envio_dian_chain_tip; expected exactly 1."
    )


@pytest.mark.asyncio
async def test_grant_reassertion_post_migration(pg_engine: AsyncEngine) -> None:
    """Op 4: rol_app has SELECT+INSERT on the 3 tables."""
    async with pg_engine.connect() as conn:
        for table in ("factura_electronica", "envio_dian", "resolucion_facturacion"):
            result = await conn.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'rol_app' AND table_schema = 'prod' "
                    "AND table_name = :table"
                ),
                {"table": table},
            )
            grants = {row[0] for row in result.fetchall()}
            assert "SELECT" in grants, f"Op 4: rol_app missing SELECT on {table}"
            assert "INSERT" in grants, f"Op 4: rol_app missing INSERT on {table}"
