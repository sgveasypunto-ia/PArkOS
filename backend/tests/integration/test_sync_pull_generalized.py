"""test_sync_pull_generalized.py — regression coverage for a real, large gap
confirmed while doing manual QA against the live Docker cloud+branch stack
(2026-09-10): ``POST /api/v1/sync/pull`` was a confirmed stub — its own
docstring said "PR8c returns an empty batch", and it always returned
``{"rows": [], "next_seq": since_seq}`` regardless of what a branch actually
needed. ``SyncSucursalWorker._pull_and_apply_catalog`` (the REAL, live
worker loop — not a test) calls exactly this endpoint every cycle, so NO
``cloud_to_branch``/``bidirectional`` catalog row could ever reach a branch
through the currently-wired path, for ANY sucursal.

This test proves the real fix: ``/sync/pull`` now resolves the CALLING
branch from its own JWT (``claims["sucursal"]``, never a caller-supplied or
hardcoded uuid) and returns exactly the rows that branch's per-table
``broadcast_policy`` (T-PR12-003, ``resolve_broadcast_targets``) actually
owns — proven generic with TWO distinct simulated branches, not just the
one this QA session happened to create in Docker.

Scenarios:
  1. ``single_branch`` policy (``sucursal`` itself, ``has_uuid_sucursal=
     False`` — the row's own uuid IS the branch identity): branch A pulls
     and gets ONLY sucursal A's row; branch B pulls and gets ONLY B's.
  2. ``all_branches`` policy (``tipos_vehiculo``): BOTH branches receive
     the SAME row.
  3. ``since_seq`` filtering: a second pull with ``since_seq=next_seq`` from
     the first response returns no rows already delivered.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_sync_pull_is_generic_across_two_distinct_branches(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, v_fixture_factory
) -> None:
    from parkos_core.models.V.sucursal import Sucursal
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        sucursal_a = v_fixture_factory.build(Sucursal, nombre="Sucursal A pull-test")
        sucursal_b = v_fixture_factory.build(Sucursal, nombre="Sucursal B pull-test")
        shared_tipo = v_fixture_factory.build(
            TiposVehiculo, tipo=f"tipo-{uuid_lib.uuid4().hex[:8]}"
        )
        session.add_all([sucursal_a, sucursal_b, shared_tipo])
        await session.commit()
        await session.refresh(sucursal_a)
        await session.refresh(sucursal_b)
        await session.refresh(shared_tipo)

    token_a = mint_sync_agent_jwt(scope="branch", sucursal_uuid=sucursal_a.uuid)
    token_b = mint_sync_agent_jwt(scope="branch", sucursal_uuid=sucursal_b.uuid)

    resp_a = await client.post(
        "/api/v1/sync/pull",
        json={"since_seq": 0},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a.status_code == 200, resp_a.text
    body_a = resp_a.json()
    tablas_a = {(r["tabla"], r["uuid_registro"]) for r in body_a["rows"]}

    resp_b = await client.post(
        "/api/v1/sync/pull",
        json={"since_seq": 0},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b.status_code == 200, resp_b.text
    body_b = resp_b.json()
    tablas_b = {(r["tabla"], r["uuid_registro"]) for r in body_b["rows"]}

    # single_branch: each branch gets ONLY its own sucursal row, never the
    # other's — proves the endpoint is identity-scoped, not hardcoded.
    assert ("sucursal", str(sucursal_a.uuid)) in tablas_a
    assert ("sucursal", str(sucursal_b.uuid)) not in tablas_a
    assert ("sucursal", str(sucursal_b.uuid)) in tablas_b
    assert ("sucursal", str(sucursal_a.uuid)) not in tablas_b

    # all_branches: the SAME tipos_vehiculo row reaches BOTH branches.
    assert ("tipos_vehiculo", str(shared_tipo.uuid)) in tablas_a
    assert ("tipos_vehiculo", str(shared_tipo.uuid)) in tablas_b

    # The delivered sucursal row's business data really is on the wire.
    sucursal_a_row = next(r for r in body_a["rows"] if r["tabla"] == "sucursal")
    assert sucursal_a_row["datos"]["nombre"] == "Sucursal A pull-test"


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_sync_pull_since_seq_excludes_already_delivered_rows(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, v_fixture_factory
) -> None:
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        tipo = v_fixture_factory.build(TiposVehiculo, tipo=f"tipo-{uuid_lib.uuid4().hex[:8]}")
        session.add(tipo)
        await session.commit()
        await session.refresh(tipo)

    token = mint_sync_agent_jwt(scope="branch")

    # Explicit, distinct X-Request-Id per call: the ``client`` fixture
    # attaches a FIXED default ("test") to every request, which would
    # otherwise make the second call hit this endpoint's own idempotency
    # cache (keyed on issuer+subject+X-Request-Id) and replay the FIRST
    # response verbatim — a test-harness artifact, not a real duplicate
    # pull from an actual branch (which never repeats a request id).
    first = await client.post(
        "/api/v1/sync/pull",
        json={"since_seq": 0},
        headers={"Authorization": f"Bearer {token}", "X-Request-Id": "pull-1"},
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert any(r["uuid_registro"] == str(tipo.uuid) for r in first_body["rows"])
    next_seq = first_body["next_seq"]
    assert next_seq > 0

    second = await client.post(
        "/api/v1/sync/pull",
        json={"since_seq": next_seq},
        headers={"Authorization": f"Bearer {token}", "X-Request-Id": "pull-2"},
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert not any(r["uuid_registro"] == str(tipo.uuid) for r in second_body["rows"]), (
        "a row already delivered up to next_seq must not be re-sent"
    )


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_sync_pull_rejects_cloud_scope_token(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt
) -> None:
    """A ``scope=cloud`` sync-agent token names no single target branch —
    pull must reject it rather than guess."""
    token = mint_sync_agent_jwt(scope="cloud")
    resp = await client.post(
        "/api/v1/sync/pull",
        json={"since_seq": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "pull_requires_branch_scope"
