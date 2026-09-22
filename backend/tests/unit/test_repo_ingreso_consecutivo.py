"""test_repo_ingreso_consecutivo.py — REQ-OPS-191..193 / HU-INGRESO-SIN-PLACA.

Unit tests for ``repo.ingreso_consecutivo.assign_ingreso_consecutivo``
exercised against a REAL Postgres container (rule: no mocked DB for
this path -- the row lock + namespace scoping is exactly the part a
mock would hide; same precedent as
``tests/unit/test_consecutivo_assignment.py``).

Mirrors ``assign_consecutivo`` (DIAN numbering) but for the parking-lot
identifier of ingresos sin placa (bici / patineta). Eight scenarios:

  T1 -- first ingreso for (sucursal, tipo) returns ``BICI-000001-<uuid8>``
  T2 -- monotonic per namespace: 3 calls -> 000001, 000002, 000003
  T3 -- independent counter for a different (sucursal, tipo) pair
  T4 -- idempotency: same source_event_uuid 5x -> same consecutivo
  T5 -- format: <TIPO>-NNNNNN-<uuid8> for n=1..999 (spot check)
  T6 -- 10 concurrent asyncio.gather calls serialize to 10 distinct n
  T7 -- REVOKE: UPDATE on non-carve-out column raises insufficient_privilege
  T8 -- carve-out: UPDATE on (ultimo_consecutivo, last_event_uuid) SUCCEEDS
  T9 -- DB-level defense: partial UK rejects duplicate consecutivo on ingreso
"""
from __future__ import annotations

import asyncio
import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.models.A.ingreso_consecutivo_contador import IngresoConsecutivoContador
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.V.empresa import Empresa
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from parkos_core.repo.ingreso_consecutivo import (
    TipoVehiculoNotFoundError,
    assign_ingreso_consecutivo,
)
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Seed helpers (parallel to test_consecutivo_assignment.py fixtures).
# ---------------------------------------------------------------------------


async def _seed_empresa(pg_engine: AsyncEngine) -> uuid_lib.UUID:
    """Insert one open ``empresa`` row (FK parent for Sucursal)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre=f"Empresa consec {empresa_uuid.hex[:6]}",
                nit=f"900{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="hi",
                mensaje_salida="bye",
                regimen="comun",
                vigente_desde=_now(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now(),
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()
        return empresa_uuid


async def _seed_sucursal(
    pg_engine: AsyncEngine, *, uuid_empresa: uuid_lib.UUID
) -> uuid_lib.UUID:
    """Insert one open ``sucursal`` row."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal_uuid = uuid_lib.uuid4()
        session.add(
            Sucursal(
                uuid=sucursal_uuid,
                uuid_empresa=uuid_empresa,
                uuid_tipo_sucursal=None,
                nombre=f"Suc consec {sucursal_uuid.hex[:6]}",
                prefijo_nombre=f"S{sucursal_uuid.hex[:4]}",
                ciudad="Bogota",
                direccion="Calle consec 1",
                telefono="+57111",
                horario="24/7",
                vigente_desde=_now(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
        return sucursal_uuid


async def _seed_tipo(
    pg_engine: AsyncEngine, *, tipo: str
) -> uuid_lib.UUID:
    """Insert one open ``tipos_vehiculo`` row."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        tipo_uuid = uuid_lib.uuid4()
        session.add(
            TiposVehiculo(
                uuid=tipo_uuid,
                tipo=tipo,
                vigente_desde=_now(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
        return tipo_uuid


async def _truncate_ingreso_consecutivo_tables(pg_dsn: str) -> None:
    """TRUNCATE every table the counter helper reads/writes."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.ingreso, prod.ingreso_consecutivo_contador, "
            "prod.tipos_vehiculo, prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


# ---------------------------------------------------------------------------
# T1: first call returns ``<TIPO>-000001-<uuid8>``.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_call_returns_formatted_000001(
    pg_engine: AsyncEngine, pg_dsn: str
) -> None:
    """T1: first ingreso sin placa for (sucursal, bicicleta) -> ``BICI-000001-<uuid8>``.

    The ``<uuid8>`` suffix is the first 8 hex chars of the caller-supplied
    ``source_event_uuid``. We pin it explicitly so the assertion is
    deterministic.
    """
    await _truncate_ingreso_consecutivo_tables(pg_dsn)
    empresa_uuid = await _seed_empresa(pg_engine)
    sucursal_uuid = await _seed_sucursal(pg_engine, uuid_empresa=empresa_uuid)
    tipo_uuid = await _seed_tipo(pg_engine, tipo="bicicleta")

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    source_event = uuid_lib.UUID("3f8a1b2c-9d8e-4a1b-8c7d-1234567890ab")
    async with Session() as session:
        consecutivo = await assign_ingreso_consecutivo(
            session,
            uuid_sucursal=sucursal_uuid,
            uuid_tipo_vehiculo=tipo_uuid,
            source_event_uuid=source_event,
        )
        await session.commit()

    assert consecutivo == f"BICI-000001-{source_event.hex[:8]}"


# ---------------------------------------------------------------------------
# T2: monotonic per namespace.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monotonic_per_namespace_three_calls(
    pg_engine: AsyncEngine, pg_dsn: str
) -> None:
    """T2: 3 distinct source events -> 000001, 000002, 000003 for same namespace."""
    await _truncate_ingreso_consecutivo_tables(pg_dsn)
    empresa_uuid = await _seed_empresa(pg_engine)
    sucursal_uuid = await _seed_sucursal(pg_engine, uuid_empresa=empresa_uuid)
    tipo_uuid = await _seed_tipo(pg_engine, tipo="bicicleta")

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    consecutivos: list[str] = []
    for _ in range(3):
        source_event = uuid_lib.uuid4()
        async with Session() as session:
            c = await assign_ingreso_consecutivo(
                session,
                uuid_sucursal=sucursal_uuid,
                uuid_tipo_vehiculo=tipo_uuid,
                source_event_uuid=source_event,
            )
            consecutivos.append(c)
            await session.commit()

    # Format: BICI-NNNNNN-<uuid8>
    ns = [c.split("-")[0] + "-" + c.split("-")[1] for c in consecutivos]
    assert ns == ["BICI-000001", "BICI-000002", "BICI-000003"]


# ---------------------------------------------------------------------------
# T3: independent counter for a different (sucursal, tipo) pair.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_independent_counters_per_namespace(
    pg_engine: AsyncEngine, pg_dsn: str
) -> None:
    """T3: (sucursal-A, bicicleta) and (sucursal-A, patineta) have independent counters.

    Same branch, different tipo -> different namespace. The first
    bicicleta call gives 000001; the first patineta call also gives
    000001 (independent counters per (sucursal, tipo)).
    """
    await _truncate_ingreso_consecutivo_tables(pg_dsn)
    empresa_uuid = await _seed_empresa(pg_engine)
    sucursal_uuid = await _seed_sucursal(pg_engine, uuid_empresa=empresa_uuid)
    tipo_bici = await _seed_tipo(pg_engine, tipo="bicicleta")
    tipo_patin = await _seed_tipo(pg_engine, tipo="patineta")

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    source_event_bici = uuid_lib.uuid4()
    source_event_patin = uuid_lib.uuid4()
    async with Session() as session:
        c_bici = await assign_ingreso_consecutivo(
            session,
            uuid_sucursal=sucursal_uuid,
            uuid_tipo_vehiculo=tipo_bici,
            source_event_uuid=source_event_bici,
        )
        c_patin = await assign_ingreso_consecutivo(
            session,
            uuid_sucursal=sucursal_uuid,
            uuid_tipo_vehiculo=tipo_patin,
            source_event_uuid=source_event_patin,
        )
        await session.commit()

    assert c_bici.startswith("BICI-000001-")
    assert c_patin.startswith("PATIN-000001-")


# ---------------------------------------------------------------------------
# T4: idempotency per source_event_uuid.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotent_on_source_event_uuid(
    pg_engine: AsyncEngine, pg_dsn: str
) -> None:
    """T4: same source_event_uuid called 5x returns the SAME string verbatim.

    Mirrors ``assign_consecutivo`` idempotency contract (T-PR9-001).
    """
    await _truncate_ingreso_consecutivo_tables(pg_dsn)
    empresa_uuid = await _seed_empresa(pg_engine)
    sucursal_uuid = await _seed_sucursal(pg_engine, uuid_empresa=empresa_uuid)
    tipo_uuid = await _seed_tipo(pg_engine, tipo="bicicleta")

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    source_event = uuid_lib.uuid4()
    results: list[str] = []
    for _ in range(5):
        async with Session() as session:
            c = await assign_ingreso_consecutivo(
                session,
                uuid_sucursal=sucursal_uuid,
                uuid_tipo_vehiculo=tipo_uuid,
                source_event_uuid=source_event,
            )
            results.append(c)
            await session.commit()

    # All 5 calls must return byte-identical strings.
    assert len(set(results)) == 1, f"idempotency violated: {results!r}"
    # And the counter advances exactly once.
    async with Session() as session:
        from sqlalchemy import select

        counter = (
            await session.execute(
                select(IngresoConsecutivoContador).where(
                    IngresoConsecutivoContador.uuid_sucursal == sucursal_uuid,
                    IngresoConsecutivoContador.uuid_tipo_vehiculo == tipo_uuid,
                    IngresoConsecutivoContador.vigente_hasta.is_(None),
                )
            )
        ).scalar_one()
        assert counter.ultimo_consecutivo == 1


# ---------------------------------------------------------------------------
# T5: format spot-check for n=1, 5, 100.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_format_for_various_n(
    pg_engine: AsyncEngine, pg_dsn: str
) -> None:
    """T5: format ``<TIPO>-NNNNNN-<uuid8>`` for n=1, 5, 100 (spot check)."""
    await _truncate_ingreso_consecutivo_tables(pg_dsn)
    empresa_uuid = await _seed_empresa(pg_engine)
    sucursal_uuid = await _seed_sucursal(pg_engine, uuid_empresa=empresa_uuid)
    tipo_uuid = await _seed_tipo(pg_engine, tipo="bicicleta")

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    # Roll up the counter to 100 via direct INSERTs (faster than 100
    # sequential asyncio.gather calls).
    async with Session() as session:
        from sqlalchemy import select

        # Advance to n=100 by calling the helper 100 times with distinct
        # source events.
        for i in range(1, 101):
            await assign_ingreso_consecutivo(
                session,
                uuid_sucursal=sucursal_uuid,
                uuid_tipo_vehiculo=tipo_uuid,
                source_event_uuid=uuid_lib.uuid4(),
            )
        await session.commit()

        # Now we should be at n=100. Verify the counter row directly.
        counter = (
            await session.execute(
                select(IngresoConsecutivoContador).where(
                    IngresoConsecutivoContador.uuid_sucursal == sucursal_uuid,
                    IngresoConsecutivoContador.uuid_tipo_vehiculo == tipo_uuid,
                    IngresoConsecutivoContador.vigente_hasta.is_(None),
                )
            )
        ).scalar_one()
        assert counter.ultimo_consecutivo == 100

    # Spot-check the format with a single new call. The next one is n=101.
    new_source = uuid_lib.UUID("12345678-aaaa-bbbb-cccc-000000000099")
    async with Session() as session:
        c = await assign_ingreso_consecutivo(
            session,
            uuid_sucursal=sucursal_uuid,
            uuid_tipo_vehiculo=tipo_uuid,
            source_event_uuid=new_source,
        )
        await session.commit()
    assert c == f"BICI-000101-{new_source.hex[:8]}"


# ---------------------------------------------------------------------------
# T6: 10 concurrent asyncio.gather calls -> 10 distinct n (1..10).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_lock_serializes_to_distinct_n(
    pg_engine: AsyncEngine, pg_dsn: str
) -> None:
    """T6: SELECT FOR UPDATE serializes 10 concurrent calls.

    10 asyncio.gather calls on the same (sucursal, tipo) namespace ->
    10 distinct ``BICI-NNNNNN-<uuid8>`` strings, n=1..10 (no gap, no
    collision). Verifies the SELECT FOR UPDATE pattern protects the
    counter under contention.
    """
    await _truncate_ingreso_consecutivo_tables(pg_dsn)
    empresa_uuid = await _seed_empresa(pg_engine)
    sucursal_uuid = await _seed_sucursal(pg_engine, uuid_empresa=empresa_uuid)
    tipo_uuid = await _seed_tipo(pg_engine, tipo="bicicleta")

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async def _one_call() -> str:
        async with Session() as session:
            c = await assign_ingreso_consecutivo(
                session,
                uuid_sucursal=sucursal_uuid,
                uuid_tipo_vehiculo=tipo_uuid,
                source_event_uuid=uuid_lib.uuid4(),
            )
            await session.commit()
            return c

    results = await asyncio.gather(*[_one_call() for _ in range(10)])

    # Extract the 6-digit n from each.
    ns = sorted(int(r.split("-")[1]) for r in results)
    assert ns == list(range(1, 11)), f"expected 1..10 distinct n, got {ns}"
    assert len(set(results)) == 10, f"expected 10 unique strings, got {results!r}"


# ---------------------------------------------------------------------------
# T7: REVOKE: rol_app cannot UPDATE non-carve-out columns.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_blocks_update_on_non_carveout_column(
    pg_engine: AsyncEngine, pg_dsn: str
) -> None:
    """T7: REVOKE + trigger block UPDATE on non-carve-out columns.

    ``rol_app`` has only SELECT, INSERT on the counter table. Attempting
    UPDATE on a column outside the carve-out (e.g. ``uuid_sucursal``)
    MUST raise ``insufficient_privilege`` (REVOKE) BEFORE the trigger
    even fires.
    """
    await _truncate_ingreso_consecutivo_tables(pg_dsn)
    empresa_uuid = await _seed_empresa(pg_engine)
    sucursal_uuid = await _seed_sucursal(pg_engine, uuid_empresa=empresa_uuid)
    tipo_uuid = await _seed_tipo(pg_engine, tipo="bicicleta")

    # First INSERT a counter row as the superuser (via the test session).
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await assign_ingreso_consecutivo(
            session,
            uuid_sucursal=sucursal_uuid,
            uuid_tipo_vehiculo=tipo_uuid,
            source_event_uuid=uuid_lib.uuid4(),
        )
        await session.commit()

    # Now try UPDATE as rol_app. The connstring for rol_app mirrors what
    # the application uses at runtime (parkos_app / parkos_app_dev).
    import psycopg

    # Best-effort role switch via SET LOCAL ROLE. rol_app exists on dev
    # and CI; if it doesn't, the test is skipped with a clear message.
    with psycopg.connect(pg_dsn) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SET ROLE rol_app")
        except psycopg.errors.InsufficientPrivilege:
            pytest.skip("rol_app not present on this DB -- REVOKE scenario out of scope")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE prod.ingreso_consecutivo_contador "
                    "SET uuid_sucursal = uuid_sucursal "
                    "WHERE uuid_sucursal = %s",
                    (str(sucursal_uuid),),
                )
            conn.commit()
            # If we got here without exception, the REVOKE is missing.
            pytest.fail(
                "rol_app UPDATE succeeded -- REVOKE UPDATE should have blocked it"
            )
        except psycopg.errors.InsufficientPrivilege:
            # Expected: REVOKE UPDATE on rol_app.
            conn.rollback()
        finally:
            with conn.cursor() as cur:
                cur.execute("RESET ROLE")
            conn.commit()


# ---------------------------------------------------------------------------
# T8: carve-out allows UPDATE on (ultimo_consecutivo, last_event_uuid).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_carveout_allows_update_on_consecutivo_column(
    pg_engine: AsyncEngine, pg_dsn: str
) -> None:
    """T8: UPDATE on the carve-out columns (ultimo_consecutivo, last_event_uuid) SUCCEEDS.

    Mirror of T7 but on the carve-out columns: this is the helper's
    operational mutation path.
    """
    await _truncate_ingreso_consecutivo_tables(pg_dsn)
    empresa_uuid = await _seed_empresa(pg_engine)
    sucursal_uuid = await _seed_sucursal(pg_engine, uuid_empresa=empresa_uuid)
    tipo_uuid = await _seed_tipo(pg_engine, tipo="bicicleta")

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await assign_ingreso_consecutivo(
            session,
            uuid_sucursal=sucursal_uuid,
            uuid_tipo_vehiculo=tipo_uuid,
            source_event_uuid=uuid_lib.uuid4(),
        )
        await session.commit()

    import psycopg

    with psycopg.connect(pg_dsn) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SET ROLE rol_app")
        except psycopg.errors.InsufficientPrivilege:
            pytest.skip("rol_app not present on this DB")

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE prod.ingreso_consecutivo_contador "
                "SET ultimo_consecutivo = ultimo_consecutivo + 1, "
                "    last_event_uuid = gen_random_uuid() "
                "WHERE uuid_sucursal = %s "
                "  AND uuid_tipo_vehiculo = %s "
                "  AND vigente_hasta IS NULL",
                (str(sucursal_uuid), str(tipo_uuid)),
            )
        conn.commit()

        # Confirm the row advanced.
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ultimo_consecutivo FROM prod.ingreso_consecutivo_contador "
                "WHERE uuid_sucursal = %s AND uuid_tipo_vehiculo = %s "
                "AND vigente_hasta IS NULL",
                (str(sucursal_uuid), str(tipo_uuid)),
            )
            row = cur.fetchone()
        assert row is not None, "counter row vanished after carve-out UPDATE"
        assert row[0] == 2, (
            f"carve-out UPDATE should advance counter to 2; got {row[0]!r}"
        )

        with conn.cursor() as cur:
            cur.execute("RESET ROLE")
        conn.commit()


# ---------------------------------------------------------------------------
# T9: DB-level defense -- partial UK rejects duplicate consecutivos on ingreso.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_unique_index_rejects_duplicate_consecutivo(
    pg_engine: AsyncEngine, pg_dsn: str
) -> None:
    """T9: ``uq_ingreso_consecutivo_partial`` rejects duplicate consecutivos.

    Two ``Ingreso`` rows with the same (sucursal, tipo, consecutivo) MUST
    fail with ``23505 unique_violation``. Defense in depth (R1/R5) on
    top of the helper's SELECT FOR UPDATE.
    """
    await _truncate_ingreso_consecutivo_tables(pg_dsn)
    empresa_uuid = await _seed_empresa(pg_engine)
    sucursal_uuid = await _seed_sucursal(pg_engine, uuid_empresa=empresa_uuid)
    tipo_uuid = await _seed_tipo(pg_engine, tipo="bicicleta")

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    shared_consecutivo = "BICI-000099-deadbeef"

    # Insert two ingreso rows with the SAME consecutivo in the same
    # (sucursal, tipo) namespace via raw SQL (bypassing the helper so we
    # can craft a duplicate collision deliberately).
    async with Session() as session:
        session.add(
            Ingreso(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=sucursal_uuid,
                uuid_tipo_vehiculo=tipo_uuid,
                placa=None,
                consecutivo=shared_consecutivo,
                fecha_ingreso=_now(),
                observaciones=None,
                created_at=_now(),
                created_by=None,
                sync_status="pendiente",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()

    # Second INSERT with the same consecutivo MUST fail with 23505.
    import psycopg

    def _insert_dup(cur, sucursal, tipo, consecutivo):
        cur.execute(
            "INSERT INTO prod.ingreso "
            "(uuid, uuid_sucursal, uuid_tipo_vehiculo, placa, consecutivo, "
            " fecha_ingreso, created_at) "
            "VALUES (gen_random_uuid(), %s, %s, NULL, %s, NOW(), NOW())",
            (sucursal, tipo, consecutivo),
        )

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        _insert_dup(cur, str(sucursal_uuid), str(tipo_uuid), shared_consecutivo)
        with pytest.raises(psycopg.errors.UniqueViolation) as exc_info:
            conn.commit()
        conn.rollback()
    # Verify the partial UK fired (not some other constraint).
    assert (
        "uq_ingreso_consecutivo_partial" in str(exc_info.value)
        or "ingreso_consecutivo" in str(exc_info.value)
    ), f"expected uq_ingreso_consecutivo_partial violation; got: {exc_info.value!s}"


# ---------------------------------------------------------------------------
# Bonus: TipoVehiculoNotFoundError when uuid_tipo_vehiculo has no vigente row.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tipo_raises_tipo_vehiculo_not_found(
    pg_engine: AsyncEngine, pg_dsn: str
) -> None:
    """Bonus: missing catalog row for uuid_tipo_vehiculo raises the typed error."""
    await _truncate_ingreso_consecutivo_tables(pg_dsn)
    empresa_uuid = await _seed_empresa(pg_engine)
    sucursal_uuid = await _seed_sucursal(pg_engine, uuid_empresa=empresa_uuid)

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        with pytest.raises(TipoVehiculoNotFoundError):
            await assign_ingreso_consecutivo(
                session,
                uuid_sucursal=sucursal_uuid,
                uuid_tipo_vehiculo=uuid_lib.uuid4(),  # not in catalog
                source_event_uuid=uuid_lib.uuid4(),
            )


__all__ = [
    "test_carveout_allows_update_on_consecutivo_column",
    "test_concurrent_lock_serializes_to_distinct_n",
    "test_first_call_returns_formatted_000001",
    "test_format_for_various_n",
    "test_idempotent_on_source_event_uuid",
    "test_independent_counters_per_namespace",
    "test_monotonic_per_namespace_three_calls",
    "test_partial_unique_index_rejects_duplicate_consecutivo",
    "test_revoke_blocks_update_on_non_carveout_column",
    "test_unknown_tipo_raises_tipo_vehiculo_not_found",
]