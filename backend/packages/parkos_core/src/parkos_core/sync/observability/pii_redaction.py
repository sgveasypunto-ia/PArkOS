"""sync/observability/pii_redaction.py — ``PIIRedactor``, sink-side only
(T-PR13-003).

REQ-HOOK-004, REQ-OPS-007, design.md §6, §9. ``PIIRedactor`` masks
``clientes``' PII fields (``email``, ``telefono``, ``direccion``,
``nombre``, ``apellido``) ONLY at observability sinks: structured logs
(``logs.py``), the structured-log stream conventionally called "sync log"
in ops docs (``prod.sync_log`` itself carries no payload columns — see
note below), and ``sync_conflict``'s data snapshot columns.

**The replicated payload is NEVER touched by this module.** Nothing in
``parkos_core``'s write path (``repo.versioned.close_and_insert``,
``repo.append_only.append_event``, ``repo.workflow.append_transition``)
imports or calls ``PIIRedactor`` — the full, unredacted payload is what
reaches the DB and what gets replicated over the wire (protected in
transit by TLS 1.3 + the ``sync-agent-`` JWT, R20).

**Why re-scoped from a payload hook to a sink-only utility (design.md §6).**
The original hook contract was "redact email, phone, address before push".
Once ``clientes`` is ``bidirectional``, that destroys data the DIAN flow
requires: the ER states ``clientes.email`` receives the graphical
representation of the electronic invoice, and ``telefono``/``nombre``/
``apellido`` are the acquirer identity on the document. A hook that strips
them makes every replicated client unusable as an invoice acquirer.
Redaction therefore lives only at sinks where PII is not required for the
business function.

**``prod.sync_log`` has no PII columns.** Its schema
(``models/A/sync_log.py``) is diagnostic counters (sent/succeeded/failed/
conflicts/duration) — there is nothing to redact in the DB table itself.
"Redaction applies to sync_log" (design.md §9) refers to the structured
LOG STREAM ``logs.py`` emits alongside those diagnostic writes, not to
this DB table's columns.

**``sync_conflict.datos_local``/``datos_remoto``.** The task-level wording
mirrors design.md §6's original hook-contract text ("datos_local" /
"datos_remoto"). The actual ORM columns (``models/A/sync_conflict.py``,
PR8) are ``datos_local`` and ``datos_cloud`` — ``datos_remoto`` does not
exist as a column name in this schema. ``PIIRedactor.redact`` operates on
a plain ``dict`` snapshot regardless of which column it is about to be
stored under, so this naming discrepancy does not affect its behavior;
flagging it here because a caller wiring this into
``sync_conflict``-writing call sites should use the real column name
(``datos_cloud``).

**``direccion`` is not a ``clientes`` column.** ``models/V/clientes.py``
(PR5) declares 8 business columns — ``tipo_identificador``,
``numero_identificacion``, ``nombre``, ``apellido``, ``telefono``,
``email``, ``uuid_tipo_persona``, ``registro`` (a JSONB catch-all) — none
named ``direccion``. This redactor masks ``direccion`` defensively
whenever it appears as a top-level payload key (e.g. if a future migration
adds the column, or if it is nested under ``registro`` by an as-yet-unbuilt
caller) rather than gating on the current ORM schema. No schema change is
made by this PR to introduce the column (see repo rule against changing
schema as a test shortcut).
"""
from __future__ import annotations

from typing import Any, Final

#: Placeholder written in place of a redacted field's value. Deliberately
#: NOT the string "REDACTED" alone (too easy to collide with real data);
#: the asterisks make it visually unambiguous in log output.
MASK: Final[str] = "***REDACTED***"

#: tabla -> PII field names to mask at observability sinks (T-PR13-003).
#: Only ``clientes`` carries PII fields in this schema today.
_REDACTED_FIELDS_BY_TABLE: Final[dict[str, frozenset[str]]] = {
    "clientes": frozenset({"email", "telefono", "direccion", "nombre", "apellido"}),
}


class PIIRedactor:
    """Redacts PII fields from observability-sink payloads only.

    Never mutates its input — callers that also hand the same ``payload``
    dict to a repo write path (``close_and_insert`` and friends) keep
    receiving the full, unredacted data because ``redact`` always returns a
    NEW dict.
    """

    def redact(self, tabla: str, payload: dict[str, Any] | None) -> dict[str, Any] | None:
        """Return a new dict with ``tabla``'s PII fields masked.

        Args:
            tabla: The catalog table name the payload belongs to (e.g.
                ``"clientes"``). Tables with no registered PII fields are
                returned as a shallow copy, unchanged.
            payload: Column-name -> value mapping to redact. ``None``
                passes through as ``None`` (a log call with no payload
                attached).

        Returns:
            A new dict (or ``None``) — the input ``payload`` is never
            mutated in place.
        """
        if payload is None:
            return None

        fields = _REDACTED_FIELDS_BY_TABLE.get(tabla)
        if not fields:
            return dict(payload)

        return {
            key: (MASK if key in fields and value is not None else value)
            for key, value in payload.items()
        }


__all__ = ["MASK", "PIIRedactor"]
