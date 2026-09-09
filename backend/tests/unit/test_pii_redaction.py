"""test_pii_redaction.py — T-PR13-003.

Verifies ``PIIRedactor`` redacts ``clientes`` PII fields ONLY at the
observability sink (structured logs) — the SAME payload that reaches
``repo.versioned.close_and_insert`` is NEVER touched (design.md §6, §9).

design.md's hook-contract note explains why: once ``clientes`` is
``bidirectional``, ``email``/``telefono``/``nombre``/``apellido`` are the
DIAN invoice's graphical-representation target and acquirer identity —
stripping them from the replicated payload would make the client unusable
as an invoice acquirer. Redaction is scoped to sinks that don't need PII
for their business function.

NOTE — ``direccion``: the task-level PII field list (T-PR13-003) names
``email``/``telefono``/``direccion``/``nombre``/``apellido``, mirroring
design.md §6's "email, phone, address" wording. ``models/V/clientes.py``
(PR5) has no ``direccion`` column — the 8 business columns are
``tipo_identificador``, ``numero_identificacion``, ``nombre``,
``apellido``, ``telefono``, ``email``, ``uuid_tipo_persona``, ``registro``
(a JSONB catch-all). ``PIIRedactor`` masks ``direccion`` defensively
wherever it appears as a top-level payload key so a future column
addition needs no redactor change; this PR does not add the column (repo
rule: never change schema as a test shortcut).
"""
from __future__ import annotations

import json
import uuid as uuid_lib


async def test_clientes_payload_reaches_repo_unredacted_but_log_line_is_masked(
    pg_engine, alembic_upgrade, capsys
) -> None:
    """The single scenario T-PR13-003 requires: one event, two sinks, one rule.

    1. ``close_and_insert`` receives (and persists) the FULL, unredacted
       ``clientes`` payload.
    2. The observability log line for that same conceptual event has the
       PII fields masked.
    3. The caller's own payload dict is never mutated by the log call.
    """
    from parkos_core.models.V.clientes import Clientes
    from parkos_core.repo.versioned import close_and_insert, current_version
    from parkos_core.sync.observability import logs as observability_logs
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    payload = {
        "tipo_identificador": "CC",
        "numero_identificacion": f"test-{uuid_lib.uuid4().hex[:8]}",
        "nombre": "Alice",
        "apellido": "Doe",
        "telefono": "3001234567",
        "email": "alice.doe@example.com",
    }

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        new_row = await close_and_insert(
            session,
            Clientes,
            current_uuid=None,
            new_attrs=dict(payload),
            actor_uuid=actor,
            log_tx=True,
        )
        await session.commit()
        await session.refresh(new_row)
        new_row_uuid = new_row.uuid

        # 1. The payload landed in the DB completely unredacted.
        stored = await current_version(session, Clientes, new_row_uuid)
        assert stored is not None
        assert stored.nombre == "Alice"
        assert stored.apellido == "Doe"
        assert stored.telefono == "3001234567"
        assert stored.email == "alice.doe@example.com"

    # 2. The SAME event's log line has the PII fields masked.
    logger = observability_logs.get_logger("test.pii_redaction")
    observability_logs.log_sync_event(
        logger,
        "sync_apply",
        tabla="clientes",
        uuid_sucursal=None,
        actor_uuid=actor,
        correlation_id="corr-pii-1",
        payload=payload,
    )
    captured = capsys.readouterr().out
    lines = [ln for ln in captured.strip().splitlines() if ln.strip()]
    record = json.loads(lines[-1])
    logged_payload = record["payload"]
    assert logged_payload["nombre"] != "Alice"
    assert logged_payload["apellido"] != "Doe"
    assert logged_payload["telefono"] != "3001234567"
    assert logged_payload["email"] != "alice.doe@example.com"
    # Non-PII fields are NOT touched by the redactor.
    assert logged_payload["tipo_identificador"] == "CC"

    # 3. The caller's own payload dict was never mutated by the log call.
    assert payload["nombre"] == "Alice"
    assert payload["apellido"] == "Doe"
    assert payload["telefono"] == "3001234567"
    assert payload["email"] == "alice.doe@example.com"


def test_redactor_masks_only_the_5_documented_clientes_fields() -> None:
    from parkos_core.sync.observability.pii_redaction import PIIRedactor

    redactor = PIIRedactor()
    payload = {
        "email": "a@b.com",
        "telefono": "123",
        "direccion": "Calle 1",
        "nombre": "A",
        "apellido": "B",
        "tipo_identificador": "CC",
        "numero_identificacion": "999",
    }
    redacted = redactor.redact("clientes", payload)

    assert redacted is not payload, "redact() must return a new dict, never mutate the input"
    for field in ("email", "telefono", "direccion", "nombre", "apellido"):
        assert redacted[field] != payload[field]
    # Non-PII fields pass through unchanged.
    assert redacted["tipo_identificador"] == "CC"
    assert redacted["numero_identificacion"] == "999"
    # The original dict is untouched.
    assert payload["email"] == "a@b.com"
    assert payload["direccion"] == "Calle 1"


def test_redactor_passthrough_for_non_clientes_tables() -> None:
    from parkos_core.sync.observability.pii_redaction import PIIRedactor

    redactor = PIIRedactor()
    payload = {"email": "should-not-be-touched@example.com", "monto": 100}
    redacted = redactor.redact("factura_pagos", payload)

    assert redacted == payload
    assert redacted is not payload


def test_redactor_handles_none_payload() -> None:
    from parkos_core.sync.observability.pii_redaction import PIIRedactor

    assert PIIRedactor().redact("clientes", None) is None


def test_redactor_does_not_mask_none_valued_pii_fields() -> None:
    """A PII field that is simply absent/None stays None, not a mask string."""
    from parkos_core.sync.observability.pii_redaction import PIIRedactor

    redactor = PIIRedactor()
    redacted = redactor.redact("clientes", {"email": None, "nombre": "A"})
    assert redacted["email"] is None
    assert redacted["nombre"] != "A"
