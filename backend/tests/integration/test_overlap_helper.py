"""test_overlap_helper.py — PR-C unit/integration coverage for the
bi-temporal overlap guard in :mod:`parkos_core.repo.overlap`.

Why a dedicated file (not rolled into test_tarifas_sucursal_e2e.py):
the helper is shared by the tarifas and cantidad POST/PUT handlers and
has its own matrix of overlapping scenarios that need to be pinned
independent of the resource. The matrix lives here so a future
contributor adding a third [V] resource (cuotas, planes, etc.) can
read the contract once and trust it.

What the five cases pin
-----------------------
* O1 Adjacent windows do NOT overlap: ``new.vigente_desde == old.vigente_hasta``
  is the close+insert Carril B contract — the helper must NOT raise.
* O2 Strict overlap (new opens INSIDE an existing open window) raises.
* O3 Strict overlap (new contains an existing open window) raises.
* O4 Same ``vigente_desde`` raises (UK01 territory) — but that's
  enforced at the DB layer, not by the helper. The helper does NOT
  raise; the INSERT will fail with UniqueViolation.
* O5 Excluding the current row's own uuid (PUT scenario) lets a row
  close+insert against itself without spurious overlap.

The tests use psycopg directly to seed fixtures and bypass the
factory, so they pin the helper independent of any URL handler
behaviour. The handler-level rejection (409 ``tarifa_overlap``) is
covered by the tarifa e2e file.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

# Note: no module-level ``pytestmark = parametrize(app=...)`` here.
# These tests bypass the HTTP client (they call the helper directly
# against a psycopg + SQLAlchemy session), so the ``app`` fixture is
# not needed. A module-level parametrize would force every test to
# depend on ``app`` and the collection would fail with "function
# uses no fixture 'app'" — same lesson as the tarifa/cantidad e2e
# files in PR-C.


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _truncate_tarifas(pg_dsn: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.tarifas_sucursal")
        conn.commit()


async def _seed_one_open_tarifa(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    vigente_desde: datetime,
) -> uuid_lib.UUID:
    """Insert one open tarifa (vigente_hasta=NULL, estado='activo')."""
    from parkos_core.models.V.tarifas_sucursal import TarifasSucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = TarifasSucursal(
            uuid=uuid_lib.uuid4(),
            uuid_sucursal=uuid_sucursal,
            uuid_tipo_vehiculo=None,
            uuid_tipo_tarifa=None,
            valor=100,
            valor_plena=100,
            vigente_desde=vigente_desde,
            vigente_hasta=None,
            estado="activo",
            created_at=_now_naive(),
            created_by=None,
            sync_status="sincronizado",
            sync_timestamp=_now_naive(),
            sync_attempts=0,
        )
        session.add(row)
        await session.commit()
        return row.uuid


async def _assert_no_overlap_call(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    nueva_desde: datetime,
    exclude_uuid: uuid_lib.UUID | None,
):
    """Invoke :func:`assert_no_overlap` against the tarifas table for a
    generic business key (all FK columns NULL) and return the exception
    or ``None``."""
    from parkos_core.repo.overlap import OverlapError, _Key, assert_no_overlap

    try:
        await assert_no_overlap(
            pg_engine,
            table="prod.tarifas_sucursal",
            resource="tarifas-sucursal",
            key=_Key(
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=None,
                uuid_tipo_tarifa=None,
            ),
            nueva_vigente_desde=nueva_desde,
            nueva_vigente_hasta=nueva_desde,
            exclude_uuid=exclude_uuid,
        )
        return None
    except OverlapError as exc:
        return exc


# ---------------------------------------------------------------------------
# O1 — Adjacent windows do NOT overlap (Carril B contract)
# ---------------------------------------------------------------------------


async def test_o1_strictly_after_existing_open_no_overlap(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """An open row whose ``vigente_desde`` is BEFORE the new candidate's
    ``nueva_desde`` does NOT overlap — the existing row ends at
    ``nueva_desde`` (Carril B close boundary) and the new row opens at
    the same boundary, so they are adjacent, not overlapping.

    The helper's predicate is strict-overlap (``<`` and ``>``, not
    ``<=`` / ``>=``), so equal boundaries do not trigger overlap.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    seed_vigente_desde = _now_naive() - timedelta(days=10)
    seed_uuid = await _seed_one_open_tarifa(
        pg_engine,
        uuid_sucursal=branch_uuid,
        vigente_desde=seed_vigente_desde,
    )

    # The PUT handler closes the seed at ``nueva_desde`` (Carril B)
    # and opens the new row there; the helper excludes the seed's own
    # uuid from the overlap search so it does not see itself.
    nueva_desde = _now_naive()
    result = await _assert_no_overlap_call(
        pg_engine,
        uuid_sucursal=branch_uuid,
        nueva_desde=nueva_desde,
        exclude_uuid=seed_uuid,
    )
    assert result is None, (
        f"with the seed excluded (Carril B close), no other open row exists; "
        f"the helper must NOT raise; got {result!r}"
    )


# `timedelta` import is needed for the strict-overlap arithmetic in O2/O3.
from datetime import timedelta  # noqa: E402


# ---------------------------------------------------------------------------
# O2 — Strict overlap (new opens INSIDE an existing open window)
# ---------------------------------------------------------------------------


async def test_o2_strict_overlap_inside_open_raises(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """An existing open row whose vigente_desde is before the new one and
    whose vigente_hasta is NULL (open-ended) overlaps any new open row.

    The seed fixture is open-ended; the new candidate at any time later
    than the seed's vigente_desde overlaps (because the seed never
    closes). The helper MUST raise.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    seed_vigente_desde = _now_naive() - timedelta(days=10)
    await _seed_one_open_tarifa(
        pg_engine,
        uuid_sucursal=branch_uuid,
        vigente_desde=seed_vigente_desde,
    )

    nueva_desde = _now_naive()  # strictly after the seed's vigente_desde
    result = await _assert_no_overlap_call(
        pg_engine,
        uuid_sucursal=branch_uuid,
        nueva_desde=nueva_desde,
        exclude_uuid=None,
    )
    assert result is not None, "strict overlap inside an open window must raise"
    assert result.conflicting_vigente_desde == seed_vigente_desde


# ---------------------------------------------------------------------------
# O3 — Strict overlap (new contains an existing open window)
# ---------------------------------------------------------------------------


async def test_o3_strict_overlap_contains_open_raises(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """The new candidate's ``nueva_desde`` is BEFORE the seed's
    vigente_desde (seed is in the future relative to the new). The
    helper's predicate is strict — ``other.vigente_desde < nueva_hasta``
    (i.e. seed.vigente_desde < nueva_desde, since they are equal in
    this test) AND ``(other.vigente_hasta IS NULL OR ...)``. With seed
    open-ended, the second conjunct is TRUE. The first conjunct
    evaluates ``seed.vigente_desde < nueva_desde``; if nueva_desde is
    AFTER seed.vigente_desde, this is TRUE and the helper raises.

    This is the dual of O2 and the helper must raise.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    seed_vigente_desde = _now_naive() + timedelta(days=5)  # future
    await _seed_one_open_tarifa(
        pg_engine,
        uuid_sucursal=branch_uuid,
        vigente_desde=seed_vigente_desde,
    )

    nueva_desde = _now_naive() + timedelta(days=10)  # even later
    result = await _assert_no_overlap_call(
        pg_engine,
        uuid_sucursal=branch_uuid,
        nueva_desde=nueva_desde,
        exclude_uuid=None,
    )
    assert result is not None, (
        "strict overlap that contains an open window must raise; the seed "
        "is open-ended, so any nueva_desde strictly after the seed overlaps it"
    )


# ---------------------------------------------------------------------------
# O4 — Same vigente_desde is NOT raised by the helper (UK01 territory)
# ---------------------------------------------------------------------------


async def test_o4_same_vigente_desde_does_not_raise_in_helper(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """The overlap helper uses ``other.vigente_desde < nueva_desde`` as
    the first conjunct. When the two are equal, the conjunct is FALSE
    and the helper does NOT raise — even though the row IS a duplicate
    per UK01. The DB-level UK01 (``permisos_uk01`` analogue:
    ``tarifas_sucursal_uk01``) catches that case on INSERT. The helper
    is NOT a substitute for UK01; the two are complementary.

    This pins that contract: tests of the handler must not rely on the
    helper to catch the same-vigente_desde case (the handler would
    surface it as a 500 from the DB UniqueViolation). A future refactor
    that folds UK01 into the helper would need to update this test.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    same_desde = _now_naive()
    await _seed_one_open_tarifa(
        pg_engine,
        uuid_sucursal=branch_uuid,
        vigente_desde=same_desde,
    )

    result = await _assert_no_overlap_call(
        pg_engine,
        uuid_sucursal=branch_uuid,
        nueva_desde=same_desde,
        exclude_uuid=None,
    )
    assert result is None, (
        "equal vigente_desde is NOT caught by the helper (DB-level UK01 is); "
        "if a future change makes the helper catch this, update this test"
    )


# ---------------------------------------------------------------------------
# O5 — Excluding the current row's own uuid lets close+insert work
# ---------------------------------------------------------------------------


async def test_o5_exclude_uuid_skips_self_overlap(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """The PUT scenario: an open row is being closed+inserted. The new
    version opens at the same boundary the old closes at. The helper
    MUST ignore the row being closed (via ``exclude_uuid``); otherwise
    the row would always overlap itself.

    We seed one open row at ``t0`` and propose a new row at
    ``t0 + 1 day`` with ``exclude_uuid`` set to the seed's uuid. The
    helper sees no other open rows and does NOT raise.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    seed_vigente_desde = _now_naive() - timedelta(days=1)
    seed_uuid = await _seed_one_open_tarifa(
        pg_engine,
        uuid_sucursal=branch_uuid,
        vigente_desde=seed_vigente_desde,
    )

    # WITHOUT exclude_uuid: must raise (the seed is open and overlaps).
    result_without = await _assert_no_overlap_call(
        pg_engine,
        uuid_sucursal=branch_uuid,
        nueva_desde=_now_naive(),
        exclude_uuid=None,
    )
    assert result_without is not None, (
        "without exclude_uuid, the open seed must trigger overlap"
    )

    # WITH exclude_uuid=seed_uuid: must NOT raise.
    result_with = await _assert_no_overlap_call(
        pg_engine,
        uuid_sucursal=branch_uuid,
        nueva_desde=_now_naive(),
        exclude_uuid=seed_uuid,
    )
    assert result_with is None, (
        f"with exclude_uuid={seed_uuid}, the helper must skip the seed; "
        f"got {result_with!r}"
    )
