"""sync/observability/logs.py — ``structlog`` sink config (T-PR13-002).

REQ-OPS-007, design.md §9. Configures ``structlog`` to emit JSON log lines
carrying the 7 keys design.md §9 requires: ``event``, ``tabla``,
``uuid_sucursal``, ``actor_uuid``, ``correlation_id``, ``ts``, ``level``. A
``chain_break`` event always logs at ``error``, regardless of the
caller-requested level.

``structlog`` is already a runtime dependency (``pyproject.toml``) and
already used across the sync workers (``jobs/sync_cloud.py``,
``jobs/sync_sucursal.py``, ``jobs/runner.py``, ``sync/jwt_manager.py``,
``sync/transport.py``) via ``structlog.get_logger(name)`` — but none of
those call sites, nor anywhere else in the codebase, ever called
``structlog.configure(...)``, so every logger up to this PR ran under
``structlog``'s interactive default (``ConsoleRenderer`` + no forced
``ts``/``level`` keys). This module is the FIRST place that configures the
process-wide processor chain; ``configure_logging()`` is idempotent (safe
to call from multiple worker entrypoints) and does nothing until a caller
actually asks for a logger through this module.

**PII redaction happens at THIS sink**, via
:class:`parkos_core.sync.observability.pii_redaction.PIIRedactor` — never
on the replicated payload itself (design.md §6). :func:`log_sync_event`'s
optional ``payload`` argument is redacted before being attached to the log
line; the caller's own dict (e.g. what is about to reach
``repo.versioned.close_and_insert``) is never mutated.
"""
from __future__ import annotations

from typing import Any, Final

import structlog

from .pii_redaction import PIIRedactor

#: The 7 keys every sync observability log line MUST carry (design.md §9).
REQUIRED_KEYS: Final[tuple[str, ...]] = (
    "event",
    "tabla",
    "uuid_sucursal",
    "actor_uuid",
    "correlation_id",
    "ts",
    "level",
)

#: Event names that always force ``level="error"``, regardless of what the
#: caller requested (design.md §9: "chain_break at error").
_FORCED_ERROR_EVENTS: Final[frozenset[str]] = frozenset({"chain_break"})

_configured = False


def configure_logging() -> None:
    """Idempotently configure ``structlog`` for JSON sink output.

    Safe to call from multiple worker entrypoints (``job_sync_cloud``,
    ``job_sync_sucursal``, ...) — the underlying ``structlog.configure()``
    call is only issued once per process.
    """
    global _configured
    if _configured:
        return
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="ts"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    _configured = True


def get_logger(name: str = "parkos.sync") -> Any:
    """Return a ``structlog`` logger bound to the sink JSON config.

    Calls :func:`configure_logging` first so any caller of this function
    gets JSON output without needing to configure ``structlog`` itself.
    """
    configure_logging()
    return structlog.get_logger(name)


def log_sync_event(
    logger: Any,
    event: str,
    *,
    tabla: str,
    uuid_sucursal: Any,
    actor_uuid: Any,
    correlation_id: Any,
    level: str = "info",
    payload: dict[str, Any] | None = None,
    **extra: Any,
) -> None:
    """Emit one sync observability log line carrying all 7 required keys.

    Args:
        logger: A logger returned by :func:`get_logger`.
        event: The event name (becomes the ``event`` key). Forced to
            ``level="error"`` when it is ``"chain_break"``
            (design.md §9), overriding whatever ``level`` was passed.
        tabla: The affected table name.
        uuid_sucursal: The branch this event belongs to, or ``None`` for a
            cloud-global event. Coerced to ``str`` (or left ``None``) so
            the JSON line never carries a raw UUID object.
        actor_uuid: The actor (JWT subject) that caused this event.
        correlation_id: Cross-request/cross-worker correlation id.
        level: ``structlog`` method name to call (``info``/``warning``/
            ``error``/``debug``/...). Ignored for forced-error events.
        payload: Optional row payload. Redacted via
            :class:`~parkos_core.sync.observability.pii_redaction.PIIRedactor`
            before being attached — the caller's own dict is never mutated
            and is NOT what this function returns (it returns nothing; the
            caller keeps using its own unredacted dict for the repo call).
        **extra: Any additional structured fields to attach verbatim.
    """
    effective_level = "error" if event in _FORCED_ERROR_EVENTS else level
    log_fn = getattr(logger, effective_level)

    fields: dict[str, Any] = {
        "tabla": tabla,
        "uuid_sucursal": str(uuid_sucursal) if uuid_sucursal is not None else None,
        "actor_uuid": str(actor_uuid) if actor_uuid is not None else None,
        "correlation_id": str(correlation_id) if correlation_id is not None else None,
        **extra,
    }
    if payload is not None:
        fields["payload"] = PIIRedactor().redact(tabla, payload)

    log_fn(event, **fields)


__all__ = ["REQUIRED_KEYS", "configure_logging", "get_logger", "log_sync_event"]
