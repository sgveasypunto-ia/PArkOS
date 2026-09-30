"""Branch-scope enforcement on the ``GET /operacion`` read paths (PR-A).

Why this file exists
--------------------
``get_tenant_ctx`` was treated as if it authorized every branch-scoped read.
It does not, for three independent reasons, all of which this suite pins:

1. **The header is optional for ``admin-``.** ``auth/tenancy.py`` returns
   ``sucursal_uuid=None`` when ``X-Sucursal-Context`` is absent and, crucially,
   never calls ``set_tenant_context``. The ``do_orm_execute`` listener in
   ``db/tenancy.py`` short-circuits on ``ctx_uuid is None``, so **no** tenant
   filter is applied. A query param ``?uuid_sucursal=B`` then reaches the
   database verbatim.
2. **The listener only sees the header, not the query param.** Even with a
   validated header the param wins in the handlers, so ``?uuid_sucursal=<other>``
   selected a branch the header check never inspected.
3. **Raw SQL is invisible to the listener.** ``/operacion/ocupacion`` reads
   ``text(...)``. ``_iter_tenant_columns`` resolves zero tenant columns for a
   ``TextClause`` (``column_descriptions`` and ``get_final_froms`` are both
   absent), so the listener never fires for it — even with a valid header. Its
   only guard was an ``operador-``-specific check in the handler, which an
   ``admin-`` issuer skips.

The scope is resolved FRESH from ``prod.usuarios_sucursal`` (not the JWT claim
snapshot), so these tests seed that table. Minting a claim and seeding no row
is not equivalent, and testing only the claim would let a revoked assignment
keep reading for a full token lifetime.

Coverage per endpoint, mirroring the six read routes
----------------------------------------------------
- ``/operacion/ingresos``, ``/operacion/salidas`` — omitted filter must mean
  "every permitted branch", never "every branch"; an out-of-scope explicit
  filter is 403, not a silently widened read.
- ``/operacion/ingresos?placa=`` as ``operador-`` — this was a GLOBAL lookup.
  It must be pinned to the operator's branch while still finding that
  operator's own row.
- single-row reads — 404 (not 403) for an out-of-scope uuid, so the response
  does not confirm the row exists somewhere the caller cannot see.
- ``/operacion/ocupacion`` — 403 for an out-of-scope branch, 400 when the caller
  has no permitted branch at all, and still 200 for an in-scope one.

Two invariants that must survive the fix, because both are occupancy lies:
- the LEFT JOIN in ``list_salidas`` keeps orphan exits (``uuid_ingreso IS NULL``)
  visible. Filtering on the JOINED side instead of the owning side would degrade
  it to an INNER JOIN and silently drop them.
- an ``operador-`` whose JWT branch is A can still read A's rows with no
  ``uuid_sucursal`` param at all, which is what ``web_sucursal`` sends.

Pattern: ``test_operacion_salidas_list.py`` (same seeding helpers and
``_auth`` convention).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.models.A.salidas import Salidas
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.V.cantidad_vehiculos_sucursal import (
    CantidadVehiculosSucursal,
)
from parkos_core.models.V.empresa import Empresa
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal
from sqlalchemy.ext.asyncio import async_sessionmaker


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _truncate(pg_dsn: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.alerta, prod.ingreso, prod.salidas, "
            "prod.anulaciones, prod.cantidad_vehiculos_sucursal, "
            "prod.usuarios_sucursal, prod.usuarios, prod.tipos_vehiculo, "
            "prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


def _auth(token: str, sucursal: uuid_lib.UUID | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if sucursal is not None:
        headers["X-Sucursal-Context"] = str(sucursal)
    return headers


async def _seed_branch(pg_engine, *, uuid_sucursal: uuid_lib.UUID) -> uuid_lib.UUID:
    """Seed empresa/sucursal/tipo_vehiculo/cupo. Returns uuid_tipo_vehiculo."""
    now = _now_naive()
    tipo_auto = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Scope Test SA",
                nit=f"902{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="hi",
                mensaje_salida="bye",
                regimen="comun",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
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
                nombre=f"Suc Scope {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"S{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle Scope",
                telefono="+57222222",
                horario="24/7",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        session.add(
            TiposVehiculo(
                uuid=tipo_auto,
                tipo="carro",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    async with Session() as session:
        session.add(
            CantidadVehiculosSucursal(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=tipo_auto,
                cantidad=50,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return tipo_auto


async def _assign_admin(
    pg_engine, *, actor_uuid: uuid_lib.UUID, sucursales: list[uuid_lib.UUID]
) -> None:
    """Open ``usuarios_sucursal`` rows — the FRESH source of admin scope.

    The parent ``prod.usuarios`` row is mandatory, not optional politeness:
    ``uuid_usuario`` carries an enforced FK (``fk_usuarios_sucursal_uuid_usuario``)
    even though the ORM marks the column nullable, so seeding the junction alone
    fails with ``ForeignKeyViolationError``. Password material is irrelevant
    here — this test authenticates with a minted JWT, never a login.
    """
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=actor_uuid,
                nombre="Scope",
                apellido="Admin",
                cedula=f"C{actor_uuid.hex[:10]}",
                email=f"scope-{actor_uuid.hex[:8]}@parkos.local",
                password_hash="$2b$12$not-a-real-hash-for-jwt-only-tests",
                rol="admin",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        for sucursal in sucursales:
            session.add(
                UsuariosSucursal(
                    uuid_sucursal=sucursal,
                    uuid_usuario=actor_uuid,
                    vigente_desde=now,
                    vigente_hasta=None,
                    estado="activo",
                    created_at=now,
                    created_by=None,
                    sync_status="sincronizado",
                    sync_timestamp=None,
                    sync_attempts=0,
                )
            )
        await session.commit()


async def _seed_ingreso(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    placa: str,
    uuid_ingreso: uuid_lib.UUID | None = None,
) -> uuid_lib.UUID:
    now = _now_naive()
    uuid_ingreso = uuid_ingreso or uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Ingreso(
                uuid=uuid_ingreso,
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
                placa=placa,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now,
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return uuid_ingreso


async def _seed_salida(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID | None,
    fecha_salida: datetime | None,
) -> uuid_lib.UUID:
    now = _now_naive()
    uuid_salida = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Salidas(
                uuid=uuid_salida,
                fecha_retencion_hasta=now.date(),
                uuid_sucursal=uuid_sucursal,
                uuid_ingreso=uuid_ingreso,
                fecha_salida=fecha_salida,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return uuid_salida


async def _seed_two_branches(
    pg_engine,
) -> tuple[uuid_lib.UUID, uuid_lib.UUID, uuid_lib.UUID, uuid_lib.UUID]:
    """Branches A and B, each with one ingreso. Returns (a, b, tipo_a, tipo_b).

    Returning the per-branch tipo_vehiculo lets callers add ingresos/salidas
    to an existing branch without re-seeding it (sucursal_pkey is unique,
    so a second _seed_branch against the same uuid would 23505).
    """
    a = uuid_lib.uuid4()
    b = uuid_lib.uuid4()
    tipo_a = await _seed_branch(pg_engine, uuid_sucursal=a)
    tipo_b = await _seed_branch(pg_engine, uuid_sucursal=b)
    await _seed_ingreso(
        pg_engine, uuid_sucursal=a, uuid_tipo_vehiculo=tipo_a, placa="AAA111"
    )
    await _seed_ingreso(
        pg_engine, uuid_sucursal=b, uuid_tipo_vehiculo=tipo_b, placa="BBB222"
    )
    return a, b, tipo_a, tipo_b


# ---------------------------------------------------------------------------
# /operacion/ingresos
# ---------------------------------------------------------------------------


async def test_lista_sin_param_ve_solo_sucursales_permitidas(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """No ``uuid_sucursal`` + no header must NOT mean every branch.

    This is the shape that leaked: with no header ``set_tenant_context`` is never
    called, so the ORM listener applies nothing and the unfiltered
    ``select(Ingreso)`` returned every branch. Expectation: A only.
    """
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a])
    resp = await client.get("/api/v1/operacion/ingresos", headers=_auth(token))
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    placas = {row["placa"] for row in resp.json()}
    assert placas == {"AAA111"}, f"leaked across branches: {placas}"
    assert b not in {uuid_lib.UUID(r["uuid_sucursal"]) for r in resp.json()}


async def test_admin_permitido_en_ambas_ve_ambas(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """The multi-branch admin is the real ``web_admin`` case — must still work.

    Pinning this prevents a "fix" that hardcodes one branch and breaks the
    selector. This is the multi-tenant screen's entire reason to exist.
    """
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a, b])

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a, b])
    resp = await client.get("/api/v1/operacion/ingresos", headers=_auth(token))
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    assert {row["placa"] for row in resp.json()} == {"AAA111", "BBB222"}


async def test_admin_recibe_403_por_uuid_sucursal_fuera_de_scope(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """Naming an out-of-scope branch is 403, never a widened read.

    403 rather than an empty list: the caller sent a filter the server cannot
    honour, and silently returning ``[]`` would look like "that branch has no
    rows" — a wrong operational answer, not a safe one.
    """
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a])
    resp = await client.get(
        f"/api/v1/operacion/ingresos?uuid_sucursal={b}", headers=_auth(token)
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "tenant_scope_violation"


async def test_header_permitido_no_habilita_otro_param(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """A validated header does not authorize a DIFFERENT branch in the param.

    The param takes precedence in the handler, so the header check never saw it.
    This is the case the previous "already validated by get_tenant_ctx"
    reasoning in ``get_ocupacion`` got wrong.
    """
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a])
    resp = await client.get(
        f"/api/v1/operacion/ingresos?uuid_sucursal={b}", headers=_auth(token, a)
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"


async def test_scope_se_lee_fresco_no_del_claim(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """A stale ``sucursales_permitidas`` claim grants nothing.

    The claim is a login-time snapshot. If it were the authority, revoking a
    branch would leave the admin reading it until the token expired — up to an
    hour for ``admin-``. Here the claim says A+B but the DB says A only, so the
    answer must be A.
    """
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a, b])
    resp = await client.get(
        f"/api/v1/operacion/ingresos?uuid_sucursal={b}", headers=_auth(token)
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"


async def test_placa_de_operador_esta_pinned_a_su_sucursal(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """``?placa=X`` as ``operador-`` was a GLOBAL lookup; now it is branch-pinned.

    Both halves matter. The operator's OWN row must still be found — that is the
    feature ``web_sucursal`` depends on. And another branch's row with the same
    plate must be invisible, otherwise a plate that exists in two branches
    returns whichever row the DB happened to order first.
    """
    await _truncate(pg_dsn)
    a, b, _tipo_a, tipo_b = await _seed_two_branches(pg_engine)
    await _seed_ingreso(
        pg_engine, uuid_sucursal=b, uuid_tipo_vehiculo=tipo_b, placa="AAA111"
    )
    actor = uuid_lib.uuid4()

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=a)
    resp = await client.get(
        "/api/v1/operacion/ingresos?placa=AAA111", headers=_auth(token, a)
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert len(body) == 1, f"expected exactly the operator's own row, got {body}"
    assert body[0]["uuid_sucursal"] == str(a), "matched a row from another branch"


async def test_operador_ve_su_sucursal_sin_param(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """Regression: no param + pinned operator must keep working.

    ``web_sucursal`` sends no ``uuid_sucursal``. If the fix ever turned an
    omitted filter into "nothing", the operator screen would silently show an
    empty list — the most likely way to break this endpoint.
    """
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    actor = uuid_lib.uuid4()

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=a)
    resp = await client.get("/api/v1/operacion/ingresos", headers=_auth(token, a))
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    assert {row["placa"] for row in resp.json()} == {"AAA111"}


@pytest.mark.parametrize(
    ("path_template", "status"),
    [
        ("ingresos/{uuid}", 404),
        ("ingresos/{uuid}/estado", 404),
    ],
)
async def test_detalle_fuera_de_scope_es_404(
    pg_engine, mint_admin_jwt, client, pg_dsn, path_template: str, status: int
) -> None:
    """A guessed row uuid from another branch is 404, not 403.

    403 would confirm the row EXISTS, which is itself a leak — it turns the
    endpoint into an existence oracle for the other branches' uuids.
    """
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])
    # Mint the victim uuid here so the test never depends on a read-back
    # helper that the ORM listener might re-scope under a stale context.
    victim_uuid = uuid_lib.uuid4()
    await _seed_ingreso(
        pg_engine,
        uuid_sucursal=b,
        uuid_tipo_vehiculo=_tipo_b,
        placa="VICT01",
        uuid_ingreso=victim_uuid,
    )

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a])
    resp = await client.get(
        f"/api/v1/operacion/{path_template.format(uuid=victim_uuid)}",
        headers=_auth(token),
    )
    assert resp.status_code == status, f"got {resp.status_code}: {resp.text}"


async def test_detalle_en_scope_sigue_200(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """The permitted branch's own row is still readable — the fix is not a wall."""
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])
    # Same defensive uuid minting as the 404 test — see comment there.
    own_uuid = uuid_lib.uuid4()
    await _seed_ingreso(
        pg_engine,
        uuid_sucursal=a,
        uuid_tipo_vehiculo=_tipo_a,
        placa="OWN01",
        uuid_ingreso=own_uuid,
    )

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a])
    resp = await client.get(
        f"/api/v1/operacion/ingresos/{own_uuid}", headers=_auth(token)
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["uuid_sucursal"] == str(a)


# ---------------------------------------------------------------------------
# /operacion/salidas
# ---------------------------------------------------------------------------


async def test_salidas_lista_sin_param_ve_solo_permitidas(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """Same closed shape as ingresos, on the joined read path."""
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])
    await _seed_salida(
        pg_engine, uuid_sucursal=a, uuid_ingreso=None, fecha_salida=_now_naive()
    )
    await _seed_salida(
        pg_engine, uuid_sucursal=b, uuid_ingreso=None, fecha_salida=_now_naive()
    )

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a])
    resp = await client.get("/api/v1/operacion/salidas", headers=_auth(token))
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    assert {row["uuid_sucursal"] for row in resp.json()} == {str(a)}


async def test_salidas_fuera_de_scope_es_403(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a])
    resp = await client.get(
        f"/api/v1/operacion/salidas?uuid_sucursal={b}", headers=_auth(token)
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"


async def test_salidas_scope_no_degrada_el_left_join(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """An orphan exit stays listable once scope is applied.

    The regression this guards is subtle and silent: scoping on the JOINED
    ``Ingreso.uuid_sucursal`` instead of the OWNING ``Salidas.uuid_sucursal``
    turns the LEFT JOIN into an effective INNER JOIN, so exits whose ingreso
    row is absent vanish and the UI under-reports occupancy. Nothing errors —
    the number is just quietly wrong, which is the dangerous kind.
    """
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])
    orphan = await _seed_salida(
        pg_engine, uuid_sucursal=a, uuid_ingreso=None, fecha_salida=_now_naive()
    )

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a])
    resp = await client.get("/api/v1/operacion/salidas", headers=_auth(token))
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    uuids = [row["uuid"] for row in resp.json()]
    assert str(orphan) in uuids, "LEFT JOIN degraded to INNER under branch scope"


async def test_salida_detalle_fuera_de_scope_es_404(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """The detail endpoint returns the joined plate, so it must be scoped too.

    Left unscoped it was the cheapest probe available: guess an exit uuid, get
    back the vehicle plate attached to it.
    """
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])
    victim = await _seed_salida(
        pg_engine, uuid_sucursal=b, uuid_ingreso=None, fecha_salida=_now_naive()
    )

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a])
    resp = await client.get(
        f"/api/v1/operacion/salidas/{victim}", headers=_auth(token)
    )
    assert resp.status_code == 404, f"got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# /operacion/ocupacion
# ---------------------------------------------------------------------------


async def test_ocupacion_fuera_de_scope_es_403(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """Raw-SQL endpoint: the ORM listener never fired, so this was open.

    Also pins the WITH-header case, which is why the previous in-handler
    ``operador-``-only check was not a guard: the header was validated, then the
    param selected a different branch anyway.
    """
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a])
    resp = await client.get(
        f"/api/v1/operacion/ocupacion?uuid_sucursal={b}", headers=_auth(token)
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"


async def test_ocupacion_con_header_no_habilita_otro_param(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a])
    resp = await client.get(
        f"/api/v1/operacion/ocupacion?uuid_sucursal={b}", headers=_auth(token, a)
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"


async def test_ocupacion_admin_sin_sucursales_permitidas_es_400(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """An admin with no permitted branch gets 400, never every branch's data.

    Fail-closed with the pre-existing ``missing_sucursal_context`` error, so the
    shape of the response is unchanged for a client that already handles it.
    """
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[])

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[])
    resp = await client.get(
        f"/api/v1/operacion/ocupacion?uuid_sucursal={a}", headers=_auth(token)
    )
    assert resp.status_code == 400, f"got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"]["error"] == "missing_sucursal_context"


async def test_ocupacion_en_scope_sigue_200(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """The permitted branch still answers — including with no param at all."""
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    admin = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin, sucursales=[a])

    token = mint_admin_jwt(actor_uuid=admin, sucursales_permitidas=[a])
    for suffix in (f"?uuid_sucursal={a}", ""):
        resp = await client.get(
            f"/api/v1/operacion/ocupacion{suffix}", headers=_auth(token)
        )
        assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"


async def test_ocupacion_operador_no_puede_cambiar_de_sucursal(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """Operator pinned to A cannot read B's occupancy by passing the param."""
    await _truncate(pg_dsn)
    a, b, _tipo_a, _tipo_b = await _seed_two_branches(pg_engine)
    actor = uuid_lib.uuid4()

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=a)
    resp = await client.get(
        f"/api/v1/operacion/ocupacion?uuid_sucursal={b}", headers=_auth(token, a)
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"
