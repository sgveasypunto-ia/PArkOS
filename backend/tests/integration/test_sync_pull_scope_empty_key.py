"""test_sync_pull_scope_empty_key.py — an empty natural key is not a key.

``'---'`` normalizes to ``''`` (separators stripped). Matching clientes / vehiculos
by natural key must not treat ``''`` as a key: a keyless row referenced by the
branch (by uuid) must not drag in every OTHER row whose key also normalizes to ``''``.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime


def _model(table: str):
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME

    return SYNC_CATALOG_BY_NAME[table].model_cls


async def test_rows_with_an_empty_natural_key_do_not_match_each_other(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    from parkos_core.api.v1.sync_router import _fetch_pull_rows
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    since_seq = int(datetime.now(UTC).timestamp() * 1000) - 2
    tag = uuid_lib.uuid4().hex[:8]
    ids: dict[str, uuid_lib.UUID] = {}

    def build(table: str, who: str, **kw):
        row = v_fixture_factory.build(_model(table), **kw)
        ids[f"{table}:{who}"] = row.uuid
        return row

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all(
            [
                build("sucursal", "a", nombre=f"A-{tag}"),
                build("tipo_subscripciones", "x"),
                # known to A by uuid, numero normalizes to ''
                build("clientes", "known", tipo_identificador="CC", numero_identificacion="---"),
                # unrelated, numero ALSO normalizes to ''
                build("clientes", "other", tipo_identificador="CC", numero_identificacion="..."),
                build("vehiculos", "known", placa="--"),
                build("vehiculos", "other", placa=".."),
            ]
        )
        await s.commit()
        s.add_all(
            [
                build("clientes_b2b", "other", uuid_cliente=ids["clientes:other"]),
                build(
                    "subscripciones_cliente",
                    "a",
                    uuid_sucursal=ids["sucursal:a"],
                    uuid_cliente=ids["clientes:known"],
                    uuid_tipo_subscripcion=ids["tipo_subscripciones:x"],
                ),
            ]
        )
        await s.commit()
        s.add(
            build(
                "subscripcion_vehiculos",
                "a",
                uuid_subscripcion_cliente=ids["subscripciones_cliente:a"],
                uuid_vehiculo=ids["vehiculos:known"],
            )
        )
        await s.commit()

    try:
        async with Session() as s:
            rows, _ = await _fetch_pull_rows(
                s, uuid_sucursal=ids["sucursal:a"], since_seq=since_seq
            )
        pulled = {(r.tabla, r.uuid_registro) for r in rows}
        # control: the rows A references by uuid still arrive
        assert ("clientes", ids["clientes:known"]) in pulled
        assert ("vehiculos", ids["vehiculos:known"]) in pulled
        # an empty key must not match anything else
        assert ("clientes", ids["clientes:other"]) not in pulled
        assert ("clientes_b2b", ids["clientes_b2b:other"]) not in pulled
        assert ("vehiculos", ids["vehiculos:other"]) not in pulled
    finally:
        now = datetime.now(UTC).replace(tzinfo=None)
        async with Session() as s:
            for table in (
                "sucursal",
                "clientes",
                "clientes_b2b",
                "vehiculos",
                "tipo_subscripciones",
                "subscripciones_cliente",
                "subscripcion_vehiculos",
            ):
                model = _model(table)
                mine = [v for k, v in ids.items() if k.startswith(f"{table}:")]
                await s.execute(
                    update(model)
                    .where(model.uuid.in_(mine), model.vigente_hasta.is_(None))
                    .values(vigente_hasta=now, estado="inactivo")
                )
            await s.commit()

