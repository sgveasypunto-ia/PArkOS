"""test_alert_types_validate.py — T-PR8-005.

``repo.alert_types.validate`` raises :class:`UnknownAlertTypeError` for any
identifier outside ``prod.alert_types``; a seeded identifier passes.
"""
from __future__ import annotations

import pytest
from parkos_core.repo.alert_types import UnknownAlertTypeError, validate


async def test_validate_accepts_seeded_identifier(pg_session) -> None:
    await validate(pg_session, "dian_error")


@pytest.mark.parametrize(
    "tipo_alerta",
    [
        "hash_chain_anomaly",
        "dian_rechazada",
        "dian_timeout",
        "branch_offline_reauth_required",
        "orphan_workflow_chain",
        "fe_provider_error",
        "fe_numbering_exhausted",
    ],
)
async def test_validate_accepts_every_seeded_identifier(pg_session, tipo_alerta: str) -> None:
    await validate(pg_session, tipo_alerta)


async def test_validate_rejects_unknown_identifier(pg_session) -> None:
    with pytest.raises(UnknownAlertTypeError, match="not_a_real_alert_type"):
        await validate(pg_session, "not_a_real_alert_type")
