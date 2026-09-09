"""test_observability_logs.py — T-PR13-002.

Verifies ``parkos_core.sync.observability.logs`` configures ``structlog``
to emit JSON log lines carrying the 7 required observability keys
(design.md §9): ``event``, ``tabla``, ``uuid_sucursal``, ``actor_uuid``,
``correlation_id``, ``ts``, ``level``. A ``chain_break`` event always logs
at ``error``, regardless of the caller-requested level.
"""
from __future__ import annotations

import json

from parkos_core.sync.observability import logs as observability_logs

REQUIRED_KEYS = observability_logs.REQUIRED_KEYS


def _parse_last_json_line(captured: str) -> dict:
    lines = [ln for ln in captured.strip().splitlines() if ln.strip()]
    assert lines, "expected at least one logged JSON line"
    return json.loads(lines[-1])


def test_required_keys_constant_matches_design_doc() -> None:
    assert set(REQUIRED_KEYS) == {
        "event",
        "tabla",
        "uuid_sucursal",
        "actor_uuid",
        "correlation_id",
        "ts",
        "level",
    }


def test_sample_sync_apply_event_carries_all_7_required_keys(capsys) -> None:
    logger = observability_logs.get_logger("test.sync_apply")
    observability_logs.log_sync_event(
        logger,
        "sync_apply",
        tabla="clientes",
        uuid_sucursal="00000000-0000-0000-0000-000000000000",
        actor_uuid="11111111-1111-1111-1111-111111111111",
        correlation_id="corr-1",
    )
    captured = capsys.readouterr().out
    record = _parse_last_json_line(captured)
    for key in REQUIRED_KEYS:
        assert key in record, f"missing required key {key!r} in {record!r}"
    assert record["event"] == "sync_apply"
    assert record["level"] == "info"
    assert record["tabla"] == "clientes"


def test_chain_break_event_forces_error_level_even_if_caller_says_info(capsys) -> None:
    logger = observability_logs.get_logger("test.chain_break")
    observability_logs.log_sync_event(
        logger,
        "chain_break",
        tabla="log_transaccional",
        uuid_sucursal=None,
        actor_uuid="22222222-2222-2222-2222-222222222222",
        correlation_id="corr-2",
        level="info",  # deliberately wrong — must be forced to error
    )
    captured = capsys.readouterr().out
    record = _parse_last_json_line(captured)
    assert record["level"] == "error"
    assert record["event"] == "chain_break"


def test_uuid_sucursal_none_is_serialized_as_null_not_stringified(capsys) -> None:
    logger = observability_logs.get_logger("test.no_branch")
    observability_logs.log_sync_event(
        logger,
        "sync_skip_infra_table",
        tabla="alert_types",
        uuid_sucursal=None,
        actor_uuid=None,
        correlation_id="corr-3",
    )
    captured = capsys.readouterr().out
    record = _parse_last_json_line(captured)
    assert record["uuid_sucursal"] is None
    assert record["actor_uuid"] is None


def test_payload_is_redacted_when_tabla_is_clientes(capsys) -> None:
    logger = observability_logs.get_logger("test.payload_redaction")
    observability_logs.log_sync_event(
        logger,
        "sync_apply",
        tabla="clientes",
        uuid_sucursal="00000000-0000-0000-0000-000000000000",
        actor_uuid="11111111-1111-1111-1111-111111111111",
        correlation_id="corr-4",
        payload={"email": "alice@example.com", "numero_identificacion": "123"},
    )
    captured = capsys.readouterr().out
    record = _parse_last_json_line(captured)
    assert record["payload"]["email"] != "alice@example.com"
    assert record["payload"]["numero_identificacion"] == "123"
