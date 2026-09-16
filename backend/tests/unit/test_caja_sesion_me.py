"""test_caja_sesion_me.py — HU-F1.3 / REQ-OPS-027, REQ-OPS-029.

TDD RED-then-GREEN coverage for the new ``GET /api/v1/caja-sesion/sesion/me``
handler introduced by HU-F1.3. The endpoint returns the actor's active
cash session (one row per ``uuid_usuario`` thanks to the partial unique
index from HU-F1.3's migration 0023) or 404 ``sesion_no_active``.

Pattern mirrors ``tests/unit/test_calcular_cotizacion.py``: real
``pg_engine`` (the partial unique index is a Postgres-only invariant)
plus an ``httpx.AsyncClient`` bound to the FastAPI app via
``ASGITransport`` + the JWT issuer fixture.

Four scenarios from ``openspec/changes/hu-f1-3-sesion-unica/design.md
§7 T1-T4``:

  - T1 — operador with an active sesion → 200 + ``SesionRead`` JSON.
  - T2 — operador without an active sesion → 404 + ``{"error":
    "sesion_no_active"}``.
  - T3 — ``cliente-`` JWT → 401/403 (issuer_dep rejects the path).
  - T4 — operador with two closed sesiones + one open → 200 with the
    OPEN one (``ORDER BY timestamp_apertura DESC NULLS LAST`` picks it
    from the historical rows).

Issuer: ``operador-`` (KD-4 also accepts ``admin-``, but the T4
ordering test specifically seeds 2 cerradas + 1 abierta for the same
actor — easier to assert the open one comes back, not the most recent
closed).
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

import pytest
from parkos_core.models.L_S.sesion import Sesion
from parkos_core.schemas.caja import SesionRead
from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.parametrize("app", ["sucursal"], indirect=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_naive() -> datetime:
    """Naive ``datetime`` matching ``DateTime(timezone=False)`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _truncate_sesion(pg_dsn: str) -> None:
    """Truncate ``prod.sesion`` so each scenario starts clean."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        # FK follows into ``log_transaccional.uuid_registro_afectado``? No,
        # the FK is the other direction — sesion is the parent. We do
        # CASCADE anyway to be safe against future FKs.
        cur.execute("TRUNCATE prod.sesion CASCADE")
        conn.commit()


async def _seed_one_sesion(
    pg_engine,
    *,
    uuid_usuario: uuid_lib.UUID,
    timestamp_cierre: datetime | None = None,
    timestamp_apertura: datetime | None = None,
) -> uuid_lib.UUID:
    """Insert one ``Sesion`` row for ``uuid_usuario``.

    Returns the inserted ``uuid``. By default the sesion is open
    (``timestamp_cierre=None``); pass a non-None ``timestamp_cierre``
    to seed a closed one. ``timestamp_apertura`` defaults to ``now()``
    so ORDER BY DESC puts this row last.
    """
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sesion_uuid = uuid_lib.uuid4()
        apertura = timestamp_apertura or _now_naive()
        session.add(
            Sesion(
                uuid=sesion_uuid,
                valor_inicial_efectivo=100000.0,
                valor_inicial_datafono=0.0,
                uuid_sucursal=None,
                uuid_usuario=uuid_usuario,
                timestamp_apertura=apertura,
                timestamp_cierre=timestamp_cierre,
                uuid_usuario_cierre=None,
                created_at=apertura,
                created_by=uuid_usuario,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return sesion_uuid


# ---------------------------------------------------------------------------
# T1 — operador con sesion activa → 200 + SesionRead
# ---------------------------------------------------------------------------


async def test_operador_con_sesion_activa_devuelve_200_y_sesion_read(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """T1: ``operador-`` actor with one OPEN sesion (``timestamp_cierre=
    NULL``) hits ``GET /api/v1/caja-sesion/sesion/me`` and gets back a
    200 with a ``SesionRead`` payload whose ``timestamp_cierre`` is
    ``None``.

    RED: handler not registered → 404 (the read-only
    ``GET /caja-sesion/sesion/{uuid}`` mount catches the path and
    treats ``me`` as a uuid). GREEN: 200 with the seeded row.
    """
    await _truncate_sesion(pg_dsn)

    actor_uuid = uuid_lib.uuid4()
    sucursal_uuid = uuid_lib.uuid4()
    seeded_uuid = await _seed_one_sesion(pg_engine, uuid_usuario=actor_uuid)

    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=sucursal_uuid)

    resp = await client.get(
        "/api/v1/caja-sesion/sesion/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(sucursal_uuid),
        },
    )

    assert resp.status_code == 200, (
        f"open sesion MUST surface as 200; got {resp.status_code}: {resp.text}"
    )
    assert resp.headers.get("Cache-Control") == "no-store", (
        f"Cache-Control: no-store MUST be set on /sesion/me responses "
        f"(R8); got {resp.headers.get('Cache-Control')!r}"
    )
    body = resp.json()
    assert body["uuid"] == str(seeded_uuid), (
        f"handler MUST return exactly the seeded open sesion; got {body['uuid']!r}"
    )
    assert body["uuid_usuario"] == str(actor_uuid)
    assert body["timestamp_cierre"] is None, (
        f"open sesion MUST carry timestamp_cierre=None; got {body['timestamp_cierre']!r}"
    )
    # Pydantic validation roundtrip — same shape as ``SesionRead``.
    parsed = SesionRead.model_validate(body)
    assert parsed.uuid == uuid_lib.UUID(body["uuid"])


# ---------------------------------------------------------------------------
# T2 — operador sin sesion activa → 404 sesion_no_active
# ---------------------------------------------------------------------------


async def test_operador_sin_sesion_activa_devuelve_404_sesion_no_active(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """T2: ``operador-`` actor with NO open sesion in ``prod.sesion``
    hits the endpoint and gets back 404 with body ``{"error":
    "sesion_no_active"}``.

    RED: handler not registered → 404 with a different body shape (the
    parametric ``GET /sesion/{uuid}`` mount). GREEN: 404 with the
    typed body.
    """
    await _truncate_sesion(pg_dsn)

    actor_uuid = uuid_lib.uuid4()
    sucursal_uuid = uuid_lib.uuid4()
    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=sucursal_uuid)

    resp = await client.get(
        "/api/v1/caja-sesion/sesion/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(sucursal_uuid),
        },
    )

    assert resp.status_code == 404, (
        f"missing-sesion MUST surface as 404; got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    # FastAPI wraps ``HTTPException(detail=...)`` under ``{"detail": ...}``
    # (Starlette convention).
    assert body.get("detail", {}).get("error") == "sesion_no_active", (
        f"404 body MUST be exactly {{'detail': {{'error': 'sesion_no_active'}}}}; got {body!r}"
    )
    # KD-1 MUST: no pgcode leak in body or headers.
    pgcode_str = "23505"
    assert pgcode_str not in str(body), (
        f"pgcode MUST NOT appear in the response body (KD-1); found {pgcode_str!r} in {body!r}"
    )
    assert all(pgcode_str not in str(v) for v in resp.headers.values()), (
        f"pgcode MUST NOT appear in any response header (KD-1); headers: {dict(resp.headers)!r}"
    )


# ---------------------------------------------------------------------------
# T3 — issuer ``cliente-`` is rejected
# ---------------------------------------------------------------------------


async def test_issuer_cliente_rechazado_en_sesion_me(pg_engine, alembic_upgrade, client) -> None:
    """T3: a request with an issuer that is NOT ``operador-`` or
    ``admin-`` (here ``cliente-``) MUST be rejected BEFORE the handler
    body runs — by ``_sesion_issuer_dep``. FastAPI's
    ``HTTPException(401/403)`` short-circuits the call.

    RED: handler not registered yet → path 404. GREEN:
    401/403 (issuer rejected by ``requires_issuer``).
    """
    # Mint a token with an unknown issuer prefix. The
    # ``requires_issuer("operador-", "admin-")`` check MUST reject it.
    from parkos_core.auth.tokens import issue_token

    actor_uuid = uuid_lib.uuid4()
    sucursal_uuid = uuid_lib.uuid4()
    token = issue_token(
        subject_uuid=actor_uuid,
        issuer="cliente-test",
        claims={
            "rol": "cliente",
            "sucursal": str(sucursal_uuid),
        },
    )

    resp = await client.get(
        "/api/v1/caja-sesion/sesion/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(sucursal_uuid),
        },
    )

    assert resp.status_code in (401, 403), (
        f"cliente- issuer MUST be rejected with 401/403; got {resp.status_code}: {resp.text}"
    )
    # Issuer rejection means the handler body NEVER ran — no
    # sesion_no_active leak.
    body_text = resp.text
    assert "sesion_no_active" not in body_text, (
        f"issuer rejection MUST NOT surface typed-error body; got {body_text!r}"
    )


# ---------------------------------------------------------------------------
# T4 — operador con 2 cerradas + 1 abierta → la abierta
# ---------------------------------------------------------------------------


async def test_dos_sesiones_cerradas_y_una_abierta_devuelve_la_abierta(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """T4: ``operador-`` actor with TWO closed sesiones + ONE open
    sesion. Defense in depth: ``ORDER BY timestamp_apertura DESC NULLS
    LAST LIMIT 1`` MUST return the OPEN sesion (the closed ones have
    an earlier ``timestamp_apertura`` and a non-NULL
    ``timestamp_cierre``; the WHERE timestamp_cierre IS NULL filter is
    what disqualifies them).

    RED: handler not registered → 404 ``me`` is not a valid uuid.
    GREEN: 200 with the open sesion's uuid.
    """
    await _truncate_sesion(pg_dsn)

    actor_uuid = uuid_lib.uuid4()
    sucursal_uuid = uuid_lib.uuid4()

    # Two closed sesiones (older), one open (newest). The open sesion
    # has the LATEST timestamp_apertura so ORDER BY DESC NULLS LAST would
    # return it anyway, but the IS NULL filter on timestamp_cierre is
    # what really disqualifies the closed ones.
    older_ts = _now_naive() - timedelta(hours=2)
    older_ts_2 = _now_naive() - timedelta(hours=1)
    open_ts = _now_naive()

    old_uuid_1 = await _seed_one_sesion(
        pg_engine,
        uuid_usuario=actor_uuid,
        timestamp_cierre=older_ts + timedelta(minutes=30),
        timestamp_apertura=older_ts,
    )
    old_uuid_2 = await _seed_one_sesion(
        pg_engine,
        uuid_usuario=actor_uuid,
        timestamp_cierre=older_ts_2 + timedelta(minutes=30),
        timestamp_apertura=older_ts_2,
    )
    open_uuid = await _seed_one_sesion(
        pg_engine,
        uuid_usuario=actor_uuid,
        timestamp_cierre=None,
        timestamp_apertura=open_ts,
    )

    assert open_uuid not in {old_uuid_1, old_uuid_2}

    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=sucursal_uuid)

    resp = await client.get(
        "/api/v1/caja-sesion/sesion/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(sucursal_uuid),
        },
    )

    assert resp.status_code == 200, (
        f"open sesion MUST surface as 200; got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body["uuid"] == str(open_uuid), (
        f"MUST return the OPEN sesion, not a closed one; "
        f"got {body['uuid']!r} but expected the open sesion {open_uuid!r}"
    )
    assert body["timestamp_cierre"] is None, (
        f"the returned sesion MUST be the open one "
        f"(timestamp_cierre=None); got {body['timestamp_cierre']!r}"
    )


__all__ = [
    "test_dos_sesiones_cerradas_y_una_abierta_devuelve_la_abierta",
    "test_issuer_cliente_rechazado_en_sesion_me",
    "test_operador_con_sesion_activa_devuelve_200_y_sesion_read",
    "test_operador_sin_sesion_activa_devuelve_404_sesion_no_active",
]
