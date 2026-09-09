"""Unit tests for ``sync.motor.broadcast_resolver`` (T-PR12-003).

Req: REQ-MOT-014, REQ-MOT-016 · Design: §3, D5-rev, D19, §16 Q1.

Pure unit coverage — no real Postgres. ``all_branches``/``all_branches_with_
override`` enumeration is monkeypatched (``discover_active_branches``); the
``subscription`` transitive fallback uses a fake ``AsyncSession`` with a
query-call counter so the "never a second query" contract is asserted
behaviorally, not just by reading the source.
"""
from __future__ import annotations

import uuid as uuid_lib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.sync.auto_discovery import BranchEndpoint
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.motor import broadcast_resolver as resolver_module
from parkos_core.sync.motor.broadcast_resolver import (
    BroadcastPolicyError,
    resolve_broadcast_targets,
)

BRANCH_A = uuid_lib.UUID("00000000-0000-0000-0000-0000000000a1")
BRANCH_B = uuid_lib.UUID("00000000-0000-0000-0000-0000000000b2")


def _fake_session() -> MagicMock:
    session = MagicMock(name="AsyncSession")
    session.execute = AsyncMock()
    return session


def _endpoint(uuid_sucursal: uuid_lib.UUID, *, nombre: str = "b") -> BranchEndpoint:
    return BranchEndpoint(
        uuid_sucursal=uuid_sucursal, nombre=nombre, endpoint_url="", last_heartbeat_at=None
    )


# ---------------------------------------------------------------------------
# broadcast_policy=None — never call this resolver for it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_none_policy_raises() -> None:
    spec = SYNC_CATALOG_BY_NAME["ingreso"]
    assert spec.broadcast_policy is None
    with pytest.raises(BroadcastPolicyError):
        await resolve_broadcast_targets(_fake_session(), spec, {})


# ---------------------------------------------------------------------------
# single_branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_branch_uses_payload_uuid_sucursal() -> None:
    spec = SYNC_CATALOG_BY_NAME["resolucion_facturacion"]
    assert spec.broadcast_policy == "single_branch"
    assert spec.has_uuid_sucursal is True

    targets = await resolve_broadcast_targets(
        _fake_session(), spec, {"uuid_sucursal": BRANCH_A}
    )
    assert targets.all_branches is False
    assert targets.branch_uuids == (BRANCH_A,)


@pytest.mark.asyncio
async def test_single_branch_without_uuid_sucursal_column_uses_row_uuid() -> None:
    """``sucursal`` itself: has_uuid_sucursal=False, the row IS the branch."""
    spec = SYNC_CATALOG_BY_NAME["sucursal"]
    assert spec.broadcast_policy == "single_branch"
    assert spec.has_uuid_sucursal is False

    targets = await resolve_broadcast_targets(_fake_session(), spec, {"uuid": BRANCH_A})
    assert targets.all_branches is False
    assert targets.branch_uuids == (BRANCH_A,)


@pytest.mark.asyncio
async def test_single_branch_missing_target_raises() -> None:
    spec = SYNC_CATALOG_BY_NAME["resolucion_facturacion"]
    with pytest.raises(BroadcastPolicyError):
        await resolve_broadcast_targets(_fake_session(), spec, {})


# ---------------------------------------------------------------------------
# all_branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_branches_enumerates_active_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = SYNC_CATALOG_BY_NAME["tipos_vehiculo"]
    assert spec.broadcast_policy == "all_branches"

    async def _fake_discover(session: Any, **kwargs: Any) -> list[BranchEndpoint]:
        return [_endpoint(BRANCH_A, nombre="a"), _endpoint(BRANCH_B, nombre="b")]

    monkeypatch.setattr(resolver_module, "discover_active_branches", _fake_discover)

    targets = await resolve_broadcast_targets(_fake_session(), spec, {"tipo": "carro"})
    assert targets.all_branches is True
    assert set(targets.branch_uuids) == {BRANCH_A, BRANCH_B}


# ---------------------------------------------------------------------------
# all_branches_with_override (D19)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_branches_with_override_null_row_targets_every_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = SYNC_CATALOG_BY_NAME["configuracion_tolerancias"]
    assert spec.broadcast_policy == "all_branches_with_override"

    async def _fake_discover(session: Any, **kwargs: Any) -> list[BranchEndpoint]:
        return [_endpoint(BRANCH_A, nombre="a")]

    monkeypatch.setattr(resolver_module, "discover_active_branches", _fake_discover)

    targets = await resolve_broadcast_targets(
        _fake_session(), spec, {"uuid_sucursal": None}
    )
    assert targets.all_branches is True
    assert targets.branch_uuids == (BRANCH_A,)


@pytest.mark.asyncio
async def test_all_branches_with_override_non_null_row_targets_only_that_branch() -> None:
    spec = SYNC_CATALOG_BY_NAME["configuracion_tolerancias"]

    targets = await resolve_broadcast_targets(
        _fake_session(), spec, {"uuid_sucursal": BRANCH_B}
    )
    assert targets.all_branches is False
    assert targets.branch_uuids == (BRANCH_B,)


# ---------------------------------------------------------------------------
# subscription (§16 Q1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscription_direct_uses_own_uuid_sucursal() -> None:
    spec = SYNC_CATALOG_BY_NAME["subscripciones_cliente"]
    assert spec.broadcast_policy == "subscription"
    assert spec.has_uuid_sucursal is True

    targets = await resolve_broadcast_targets(
        _fake_session(), spec, {"uuid_sucursal": BRANCH_A}
    )
    assert targets.all_branches is False
    assert targets.branch_uuids == (BRANCH_A,)


@pytest.mark.asyncio
async def test_subscription_transitive_reuses_parent_local_zero_queries() -> None:
    """subscripcion_vehiculos + an already-validated parent_local — 0 queries."""
    spec = SYNC_CATALOG_BY_NAME["subscripcion_vehiculos"]
    assert spec.broadcast_policy == "subscription"
    assert spec.has_uuid_sucursal is False

    session = _fake_session()
    parent_cliente_uuid = uuid_lib.uuid4()
    targets = await resolve_broadcast_targets(
        session,
        spec,
        {"uuid_subscripcion_cliente": parent_cliente_uuid, "uuid_vehiculo": uuid_lib.uuid4()},
        parent_local={"uuid": parent_cliente_uuid, "uuid_sucursal": BRANCH_A},
    )
    assert targets.all_branches is False
    assert targets.branch_uuids == (BRANCH_A,)
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscription_transitive_fallback_uses_exactly_one_query() -> None:
    """No parent_local supplied — exactly ONE query, never two."""
    spec = SYNC_CATALOG_BY_NAME["subscripcion_vehiculos"]
    parent_cliente_uuid = uuid_lib.uuid4()

    session = _fake_session()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=BRANCH_B))
    )

    targets = await resolve_broadcast_targets(
        session,
        spec,
        {"uuid_subscripcion_cliente": parent_cliente_uuid, "uuid_vehiculo": uuid_lib.uuid4()},
    )
    assert targets.all_branches is False
    assert targets.branch_uuids == (BRANCH_B,)
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_subscription_transitive_missing_fk_raises() -> None:
    spec = SYNC_CATALOG_BY_NAME["subscripcion_vehiculos"]
    with pytest.raises(BroadcastPolicyError):
        await resolve_broadcast_targets(_fake_session(), spec, {"uuid_vehiculo": uuid_lib.uuid4()})


@pytest.mark.asyncio
async def test_subscription_transitive_never_falls_back_to_all_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A parent with no resolvable uuid_sucursal raises — never all_branches."""
    spec = SYNC_CATALOG_BY_NAME["subscripcion_vehiculos"]
    parent_cliente_uuid = uuid_lib.uuid4()

    session = _fake_session()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    async def _fail_if_called(*args: Any, **kwargs: Any) -> list[BranchEndpoint]:
        raise AssertionError("must never fall back to discover_active_branches")

    monkeypatch.setattr(resolver_module, "discover_active_branches", _fail_if_called)

    with pytest.raises(BroadcastPolicyError):
        await resolve_broadcast_targets(
            session,
            spec,
            {"uuid_subscripcion_cliente": parent_cliente_uuid, "uuid_vehiculo": uuid_lib.uuid4()},
        )
