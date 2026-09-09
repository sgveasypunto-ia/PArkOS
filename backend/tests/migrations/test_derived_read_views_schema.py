"""test_derived_read_views_schema.py — T-PR5-008 acceptance for migration
``0009_add_derived_read_views.py`` (D17 step 5 + ADR-001 §2 Issue #1).

Verifies the 3 derived read views exist as VIEWS (not tables — the 51/54
physical-table canon is unaffected, ``check_table_counts.py`` untouched)
and resolve "the current identity" correctly by normalized natural key /
latest DIAN acknowledgement.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.tipo_persona import TipoPersona
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from parkos_core.models.V.vehiculos import Vehiculos
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker


async def test_three_views_exist_as_views_not_tables(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT viewname FROM pg_views WHERE schemaname = 'prod' "
                    "AND viewname IN ("
                    "'v_clientes_actual', 'v_vehiculos_actual', "
                    "'v_factura_electronica_acuse')"
                )
            )
        ).scalars().all()

    assert set(rows) == {
        "v_clientes_actual",
        "v_vehiculos_actual",
        "v_factura_electronica_acuse",
    }

    # Views add no table — the 51/54 physical canon is unaffected.
    async with pg_engine.connect() as conn:
        table_exists = (
            await conn.execute(
                text(
                    "SELECT 1 FROM pg_tables WHERE schemaname = 'prod' "
                    "AND tablename IN ("
                    "'v_clientes_actual', 'v_vehiculos_actual', "
                    "'v_factura_electronica_acuse')"
                )
            )
        ).first()
    assert table_exists is None


async def test_v_clientes_actual_resolves_latest_open_version_per_natural_key(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        tipo = v_fixture_factory.build(TipoPersona, tipo="natural")
        session.add(tipo)
        await session.commit()

        now = datetime.now(UTC).replace(tzinfo=None)
        # Two independently-open rows sharing the SAME normalized natural
        # key (an artificial D17-style duplicate — no DB constraint
        # prevents this by design, see migration 0008's docstring) — the
        # view must resolve to exactly the LATEST one by vigente_desde.
        older = v_fixture_factory.build(
            Clientes,
            tipo_identificador="CC",
            numero_identificacion="55-55",
            nombre="Older",
            uuid_tipo_persona=tipo.uuid,
            vigente_desde=now - timedelta(days=1),
            vigente_hasta=None,
        )
        newer = v_fixture_factory.build(
            Clientes,
            tipo_identificador="CC",
            numero_identificacion="5555",
            nombre="Newer",
            uuid_tipo_persona=tipo.uuid,
            vigente_desde=now,
            vigente_hasta=None,
        )
        session.add_all([older, newer])
        await session.commit()

        result = (
            await session.execute(
                text(
                    "SELECT uuid, nombre FROM prod.v_clientes_actual "
                    "WHERE tipo_identificador = 'CC' AND "
                    "regexp_replace(numero_identificacion, '[^0-9A-Za-z]', '', 'g') = '5555'"
                )
            )
        ).all()

    assert len(result) == 1
    assert result[0].uuid == newer.uuid
    assert result[0].nombre == "Newer"


async def test_v_vehiculos_actual_resolves_latest_open_version_per_placa(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        tipo_vehiculo = v_fixture_factory.build(TiposVehiculo, tipo="carro")
        session.add(tipo_vehiculo)
        await session.commit()

        now = datetime.now(UTC).replace(tzinfo=None)
        older = v_fixture_factory.build(
            Vehiculos,
            placa="ABC-123",
            uuid_tipo_vehiculo=tipo_vehiculo.uuid,
            vigente_desde=now - timedelta(days=1),
            vigente_hasta=None,
        )
        newer = v_fixture_factory.build(
            Vehiculos,
            placa="abc123",
            uuid_tipo_vehiculo=tipo_vehiculo.uuid,
            vigente_desde=now,
            vigente_hasta=None,
        )
        session.add_all([older, newer])
        await session.commit()

        result = (
            await session.execute(
                text(
                    "SELECT uuid FROM prod.v_vehiculos_actual WHERE "
                    "upper(regexp_replace(placa, '[^0-9A-Za-z]', '', 'g')) = 'ABC123'"
                )
            )
        ).all()

    assert len(result) == 1
    assert result[0].uuid == newer.uuid


async def test_v_factura_electronica_acuse_resolves_latest_envio_dian_row(
    pg_engine, alembic_upgrade
) -> None:
    factura_uuid = uuid_lib.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)

    # Pre-existing bug discovered here (out of PR5 scope — see the PR5 apply
    # report's "Issues Found" section): migration 0001 attaches the
    # ``fn_set_vigente_inicial`` trigger (BEFORE INSERT) to
    # ``prod.factura_electronica``, but that table is ``[L-E]``
    # (``LifecycleEventBase`` — NO ``vigente_desde``/``estado`` columns at
    # all). The trigger unconditionally references ``NEW.vigente_desde`` /
    # ``NEW.estado``, so ANY insert into this table raises
    # ``UndefinedColumnError: record "new" has no field "vigente_desde"``
    # regardless of insertion method (ORM or raw SQL). ``session_
    # replication_role=replica`` disables triggers for this one seed insert
    # (test-only workaround — this view test only needs a real FK-valid
    # ``factura_electronica`` row to exist, not to exercise that table's own
    # triggers).
    async with pg_engine.begin() as conn:
        await conn.execute(text("SET session_replication_role = replica"))
        await conn.execute(
            text(
                "INSERT INTO prod.factura_electronica (uuid, prefijo, consecutivo) "
                "VALUES (:fe, 'FE', 1)"
            ),
            {"fe": factura_uuid},
        )
        await conn.execute(text("SET session_replication_role = origin"))
        await conn.execute(
            text(
                "INSERT INTO prod.envio_dian "
                "(uuid, uuid_factura_electronica, cufe, estado, timestamp_evento) "
                "VALUES (gen_random_uuid(), :fe, 'CUFE-OLD', 'enviado', :ts_old)"
            ),
            {"fe": factura_uuid, "ts_old": now - timedelta(hours=1)},
        )
        await conn.execute(
            text(
                "INSERT INTO prod.envio_dian "
                "(uuid, uuid_factura_electronica, cufe, estado, timestamp_evento) "
                "VALUES (gen_random_uuid(), :fe, 'CUFE-NEW', 'aceptado', :ts_new)"
            ),
            {"fe": factura_uuid, "ts_new": now},
        )

    async with pg_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT cufe, estado FROM prod.v_factura_electronica_acuse "
                    "WHERE uuid_factura_electronica = :fe"
                ),
                {"fe": factura_uuid},
            )
        ).one()

    assert row.cufe == "CUFE-NEW"
    assert row.estado == "aceptado"
