"""test_tarifas_sucursal_e2e.py — PR-C end-to-end coverage of the four
write/read paths that ``make_router`` mounts for ``tarifas_sucursal``
(POST, PUT /{uuid}, GET /{uuid}, GET /{uuid}/history). The listing path
is the dedicated HU-F1.4 handler and is already covered by
``tests/unit/test_tarifas_vigente_en.py``.

The factory's ``close_and_insert`` issues a fresh UUID on PUT (the new
version is a distinct row in the [V] table). The factory's ``GET /{uuid}
/history`` filters by ``uuid == :u``, so it returns ONLY the version(s)
of the SAME uuid — the closed original — and NOT the new version. The
full version chain across the close+insert is NOT queryable through the
factory's endpoints today (no by-business-key history endpoint). PR-C
ships the close+insert contract; the missing history endpoint is logged
as a follow-up so PR-D scope stays clean.

Cases:

* T1 POST 201 creates a row with ``vigente_hasta=NULL``, ``estado='activo'``.
* T2 POST without ``Authorization`` → 401; POST without ``config_tarifas``
  → 403 (lock-in of the 0059 fix; pre-0059 this was 403 for everyone).
* T3 PUT closes the POST'd row and inserts a new version with a fresh
  UUID; ``GET /{old_uuid}`` → 404; ``GET /{new_uuid}`` → 200; ``GET
  /{old_uuid}/history`` → list of one closed version.
* T4 Schema UK01 invariant: two INSERTs with identical UK01 columns
  raise ``UniqueViolation`` (DB-level enforcement; factory is
  safe-by-coincidence because ``clock_timestamp()`` separates
  consecutive POSTs).
* T5 Cross-check with the downstream cotizador: after PUT, the new
  ``valor`` is the one ``prod.calcular_cotizacion`` would apply on the
  next salida. The bi-temporal list (HU-F1.4) at ``vigente_en=now``
  returns only the open version, mirroring the cotizador's predicate.

See ``tests/unit/test_tarifas_vigente_en.py``'s docstring for the
rationale on integration vs unit tests.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from decimal import Decimal

import pytest

# Module-level parametrize would force every test (including the UK01 ones
# that don't touch the HTTP client) to depend on the ``app`` fixture.
# Only the five HTTP-driven cases pin the ``sucursal`` app — apply the
# parametrize on each of those individually.
_HTTP_PYTESTMARK = pytest.mark.parametrize("app", ["sucursal"], indirect=True)


# ---------------------------------------------------------------------------
# Local helpers (mirror the ones in test_tarifas_vigente_en.py — kept local
# to avoid coupling two test modules through conftest mutation).
# ---------------------------------------------------------------------------


def _now_naive() -> datetime:
    """Naive ``datetime`` matching the DB column ``DateTime(timezone=False)``."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _ensure_permiso(pg_engine, *, perm_code: str) -> uuid_lib.UUID:
    """Look up (or insert) one ``permisos`` row for ``perm_code``.

    Idempotent — 0059 already seeds ``config_tarifas`` for every node, so
    on a fresh DB this is a no-op SELECT; on a pre-0059 DB it inserts a
    fresh row (mirroring ``test_tarifas_vigente_en.py``'s helper so the
    test passes against either schema state).
    """
    from parkos_core.models.V.permisos import Permisos
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        existing = (
            await session.execute(
                select(Permisos).where(
                    Permisos.permiso == perm_code, Permisos.vigente_hasta.is_(None)
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.uuid
        row = Permisos(
            uuid=uuid_lib.uuid4(),
            permiso=perm_code,
            vigente_desde=_now_naive(),
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


async def _grant_permission(pg_engine, *, actor_uuid: uuid_lib.UUID, perm_code: str) -> None:
    from parkos_core.models.V.permisos_usuario import PermisosUsuario
    from sqlalchemy.ext.asyncio import async_sessionmaker

    permiso_uuid = await _ensure_permiso(pg_engine, perm_code=perm_code)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        # Idempotent: skip when an open grant already exists.
        from parkos_core.models.V.permisos_usuario import PermisosUsuario as _PU
        from sqlalchemy import select

        already = (
            await session.execute(
                select(_PU).where(
                    _PU.uuid_usuario == actor_uuid,
                    _PU.uuid_permiso == permiso_uuid,
                    _PU.vigente_hasta.is_(None),
                )
            )
        ).scalar_one_or_none()
        if already is not None:
            return
        session.add(PermisosUsuario(uuid_usuario=actor_uuid, uuid_permiso=permiso_uuid))
        await session.commit()


async def _seed_sucursal(pg_engine, uuid_sucursal: uuid_lib.UUID) -> None:
    """Insert one real ``sucursal`` row.

    ``tarifas_sucursal.uuid_sucursal`` carries a real FK to
    ``prod.sucursal.uuid`` — tests that POST tarifas need a parent Sucursal
    first. Mirrors ``test_tarifas_vigente_en.py::_seed_sucursal`` so the
    contract is identical to what HU-F1.4 verified.
    """
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Empresa Test PR-C",
                nit=f"901{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="Hola",
                mensaje_salida="Adios",
                regimen="comun",
                vigente_desde=_now_naive(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now_naive(),
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.flush()
        session.add(
            Sucursal(
                uuid=uuid_sucursal,
                uuid_empresa=empresa_uuid,
                uuid_tipo_sucursal=None,
                nombre=f"Sucursal PR-C {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"C{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle Test 1",
                telefono="+571234567",
                horario="24/7",
                vigente_desde=_now_naive(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now_naive(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()


async def _truncate_tarifas(pg_dsn: str) -> None:
    """Truncate ``prod.tarifas_sucursal`` so each test sees a clean slate."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.tarifas_sucursal")
        conn.commit()


def _payload(*, uuid_sucursal: uuid_lib.UUID) -> dict[str, object]:
    """Minimal valid POST payload.

    ``uuid_tipo_vehiculo`` and ``uuid_tipo_tarifa`` are nullable in the
    schema and the FK check is skipped when NULL — the test does not need
    to seed catalog parents (mirrors HU-F1.4's choice).
    """
    return {
        "uuid_sucursal": str(uuid_sucursal),
        "uuid_tipo_vehiculo": None,
        "uuid_tipo_tarifa": None,
        "valor": "1500.00",
        "valor_plena": "2000.00",
    }


# ---------------------------------------------------------------------------
# T1 — POST 201 creates a row, vigente_hasta IS NULL, estado='activo'
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_post_tarifa_crea_fila_vigente(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json=_payload(uuid_sucursal=branch_uuid),
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["vigente_hasta"] is None, "POST must open a row (vigente_hasta IS NULL)"
    assert body["estado"] == "activo"
    assert body["uuid_sucursal"] == str(branch_uuid)
    assert body["valor"] == "1500.0000" or body["valor"] == "1500.00"
    assert body["valor_plena"] == "2000.0000" or body["valor_plena"] == "2000.00"

    # GET current must return the same row by the UUID the POST returned.
    get_resp = await client.get(
        f"/api/v1/empresa/tarifas-sucursal/{body['uuid']}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert get_resp.status_code == 200, f"got {get_resp.status_code}: {get_resp.text}"
    assert get_resp.json()["uuid"] == body["uuid"]


# ---------------------------------------------------------------------------
# T2 — auth gates: 401 without a token, 403 with admin but no permission
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_post_tarifa_sin_token_devuelve_401(
    pg_engine, alembic_upgrade, client, pg_dsn
) -> None:
    """No Authorization header → 401 (JWT guard fails before the route runs)."""
    await _truncate_tarifas(pg_dsn)
    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json={"uuid_sucursal": str(uuid_lib.uuid4()), "valor": "1.00"},
    )
    assert resp.status_code == 401, f"got {resp.status_code}: {resp.text}"


@_HTTP_PYTESTMARK
async def test_post_tarifa_sin_permiso_devuelve_403(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """Admin token without ``config_tarifas`` → 403 (the 0059 lock-in).

    Pre-0059 this was ALSO 403, but the failure mode was indistinguishable
    from a missing permission code in the catalogue — POSTs always 403'd
    for every admin. After 0059 the catalogue holds the code and the
    permission gate becomes the discriminator: an admin WITHOUT the grant
    is 403, an admin WITH the grant is 201 (T1). This test pins the
    "without" half of that discriminator.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    # Deliberately NO _grant_permission call.
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json=_payload(uuid_sucursal=branch_uuid),
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# T3 — PUT closes the current row and inserts a new version
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_put_tarifa_cierra_version_y_abre_nueva(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    post = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json=_payload(uuid_sucursal=branch_uuid),
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert post.status_code == 201
    original_uuid = post.json()["uuid"]

    # PUT changes the valor — the factory writes ``payload_dict`` through
    # ``close_and_insert``, so the new version carries the new valor and
    # the original row is closed at ``vigente_hasta = NOW``.
    new_payload = _payload(uuid_sucursal=branch_uuid)
    new_payload["valor"] = "3000.00"
    new_payload["valor_plena"] = "4000.00"

    put = await client.put(
        f"/api/v1/empresa/tarifas-sucursal/{original_uuid}",
        json=new_payload,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert put.status_code == 200, f"got {put.status_code}: {put.text}"
    new_body = put.json()
    new_uuid = new_body["uuid"]

    # New row carries a different UUID (close+insert, NOT in-place update).
    assert new_uuid != original_uuid, "PUT must close+insert, NOT mutate the row in place"

    # GET /{old_uuid} — the original row is now CLOSED, so the
    # ``current_version`` helper (uuid == :u AND vigente_hasta IS NULL)
    # returns None → 404. This is the bi-temporal contract: closed rows
    # are not visible through the single-row GET.
    closed_get = await client.get(
        f"/api/v1/empresa/tarifas-sucursal/{original_uuid}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert closed_get.status_code == 404, (
        f"GET on a closed uuid must return 404; got {closed_get.status_code}: {closed_get.text}"
    )

    # GET /{new_uuid} — the open version resolves to 200.
    open_get = await client.get(
        f"/api/v1/empresa/tarifas-sucursal/{new_uuid}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert open_get.status_code == 200, f"got {open_get.status_code}: {open_get.text}"
    assert open_get.json()["uuid"] == new_uuid
    assert Decimal(str(open_get.json()["valor"])) == Decimal("3000.00"), (
        f"open version must carry the PUT'd valor 3000.00; got {open_get.json()['valor']}"
    )

    # GET /{old_uuid}/history lists ONLY the closed version — the history
    # endpoint filters by uuid, not by business key. The full version chain
    # across the close+insert would need a separate "by business key"
    # endpoint (gap surfaced during PR-C — see docstring of this file).
    history = await client.get(
        f"/api/v1/empresa/tarifas-sucursal/{original_uuid}/history",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert history.status_code == 200, f"got {history.status_code}: {history.text}"
    old_versions = history.json()
    assert len(old_versions) == 1, (
        f"history of the closed uuid must list 1 version (itself); got {len(old_versions)}"
    )
    assert old_versions[0]["vigente_hasta"] is not None
    assert old_versions[0]["estado"] == "inactivo"
    assert Decimal(str(old_versions[0]["valor"])) == Decimal("1500.00")


# ---------------------------------------------------------------------------
# T4 — UK01 invariant: the schema rejects two open rows with the same
#      (uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, vigente_desde).
#
# The factory's POST path mints ``vigente_desde = clock_timestamp()``
# internally (the Create schema blocks client-supplied timestamps via
# ``extra='forbid'``), so two consecutive POSTs land on different
# microsecond ticks and do NOT collide on UK01 — there is no real
# concurrent-write code path to exercise here that the factory exposes.
# The load-bearing invariant is the SCHEMA's UK01, not the factory's
# behaviour, so this case seeds two rows with the SAME ``vigente_desde``
# directly via psycopg and asserts the second raises IntegrityError.
#
# This pins the contract the factory inherits: any future code path that
# attempts to write a row violating UK01 will fail at the DB layer. The
# factory today is safe-by-coincidence (clock_timestamp() makes collisions
# unlikely); the schema enforces the invariant unconditionally.
# ---------------------------------------------------------------------------


async def test_uk01_rechaza_dos_filas_con_mismo_vigente_desde(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """Two INSERTs with identical UK01 columns must violate the constraint."""
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    fixed_vigente_desde = _now_naive()

    with _psycopg_conn(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO prod.tarifas_sucursal "
            "(uuid, uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, "
            " valor, valor_plena, vigente_desde, vigente_hasta, estado, "
            " created_at, created_by, sync_status, sync_attempts) "
            "VALUES (gen_random_uuid(), %s, NULL, NULL, 100, 100, "
            "        %s, NULL, 'activo', %s, NULL, 'sincronizado', 0)",
            (branch_uuid, fixed_vigente_desde, _now_naive()),
        )
        conn.commit()

        # Same UUIDv4 column tuple EXCEPT a different uuid PK (the PK is
        # the row's identity — UK01 is on the business key). The DB must
        # reject because uuid_sucursal + uuid_tipo_vehiculo (NULL) +
        # uuid_tipo_tarifa (NULL) + vigente_desde is identical.
        import psycopg

        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO prod.tarifas_sucursal "
                "(uuid, uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, "
                " valor, valor_plena, vigente_desde, vigente_hasta, estado, "
                " created_at, created_by, sync_status, sync_attempts) "
                "VALUES (gen_random_uuid(), %s, NULL, NULL, 200, 200, "
                "        %s, NULL, 'activo', %s, NULL, 'sincronizado', 0)",
                (branch_uuid, fixed_vigente_desde, _now_naive()),
            )
        conn.rollback()


def _psycopg_conn(pg_dsn: str):
    """Plain psycopg v3 connection context manager.

    Mirrors ``test_tarifas_vigente_en.py::_truncate_tarifas``'s shape but
    yields a connection (not a cursor) so each case can run multi-statement
    sequences inside the same TX.
    """
    import contextlib

    import psycopg

    @contextlib.contextmanager
    def _ctx():
        with psycopg.connect(pg_dsn) as conn:
            yield conn

    return _ctx()


# ---------------------------------------------------------------------------
# T5 — Cross-check with the downstream cotizador: after PUT, the new
#      vigente row is the one ``prod.calcular_cotizacion`` would pick.
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_put_tarifa_se_refleja_en_cotizacion_vigente(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """PUT a new ``valor`` and verify the bi-temporal list (HU-F1.4) returns
    only the new row at ``vigente_en=now``.

    ``prod.calcular_cotizacion`` uses the same predicate
    (``vigente_desde <= :v AND (vigente_hasta IS NULL OR vigente_hasta >
    :v) AND estado = 'activo'``) — the bi-temporal list endpoint is the
    read-side mirror of what the cotizador applies. If the list returns
    the new row at ``vigente_en=now``, the cotizador will charge the new
    rate on the next salida. This is the load-bearing end-to-end link.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    post = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json=_payload(uuid_sucursal=branch_uuid),
        headers=headers,
    )
    assert post.status_code == 201
    original_uuid = post.json()["uuid"]

    new_payload = _payload(uuid_sucursal=branch_uuid)
    new_payload["valor"] = "7777.77"
    put = await client.put(
        f"/api/v1/empresa/tarifas-sucursal/{original_uuid}",
        json=new_payload,
        headers=headers,
    )
    assert put.status_code == 200

    # At ``vigente_en=now`` the dedicated HU-F1.4 list must return the
    # OPEN version (the PUT'd one). The closed version's vigente_hasta
    # is <= now, so it is excluded by the bi-temporal predicate.
    list_now = await client.get(
        "/api/v1/empresa/tarifas-sucursal",
        headers=headers,
    )
    assert list_now.status_code == 200, f"got {list_now.status_code}: {list_now.text}"
    items = list_now.json()["items"]
    assert len(items) == 1, (
        f"only the open version must be vigente at now; got {len(items)} items: "
        f"{[it['uuid'] for it in items]}"
    )
    assert Decimal(str(items[0]["valor"])) == Decimal("7777.77"), (
        f"the vigente version must carry the new valor 7777.77; got {items[0]['valor']}"
    )
    assert items[0]["vigente_hasta"] is None
    assert items[0]["estado"] == "activo"
