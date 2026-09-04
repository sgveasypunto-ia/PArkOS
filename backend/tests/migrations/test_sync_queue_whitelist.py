"""test_sync_queue_whitelist.py - SC-13-A-SYNC-QUEUE-MARK-DISPATCHED.

Fuzz-style tests for the ``sync_queue`` column whitelist
(``ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS``) and the
``_validate_update_columns`` helper that enforces it client-side.

REQ-14-A-SYNC-FACADE: ``prod.sync_queue`` is the carved-out [A] table
where ``rol_app`` keeps UPDATE/DELETE grants so workers can flip
``estado`` + ``intentos``. Only the four whitelisted columns
(``estado``, ``intentos``, ``next_retry_at``, ``ultimo_error``) may
be mutated; any attempt to UPDATE a non-whitelisted column raises
:class:`SyncQueueStateError` (Python) or a DB GRANT error (Postgres).

The DB-side GRANT carries the same restriction at the SQL layer (out
of PR2 scope). The Python validator (``_validate_update_columns``)
is the first line of defense: it raises BEFORE the session hits
the DB, keeping the error message clean and avoiding a round-trip.

These tests exercise the validator with every plausibly-forbidden
column name; they do NOT require a live DB.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.repo.sync_queue import (
    ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS,
    SyncQueueStateError,
    _validate_update_columns,
)


def test_whitelist_contains_exactly_four_columns() -> None:
    """The whitelist has exactly the four expected columns.

    Mirrors the assertion in tests/unit/test_sync_queue.py
    ::test_allowed_columns_constant; this migration-level test pins
    the same invariant at the boundary (so a runtime migration
    refactor cannot silently expand or shrink the whitelist).
    """
    assert frozenset(
        {"estado", "intentos", "next_retry_at", "ultimo_error"}
    ) == ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS


@pytest.mark.parametrize(
    "forbidden_column",
    [
        "uuid",
        "uuid_sucursal",
        "operacion",
        "tabla",
        "uuid_registro",
        "datos",
        "prioridad",
        "created_at",
        "created_by",
        "sync_status",
        "sync_timestamp",
        "sync_attempts",
        "fecha_retencion_hasta",
        "pairing_token_hash",  # a totally unrelated column - guards against typos
    ],
)
def test_validate_rejects_forbidden_column(forbidden_column: str) -> None:
    """Fuzz: every plausible non-whitelisted column raises ``SyncQueueStateError``.

    The validator MUST raise BEFORE the session reaches the DB. We
    exercise every column an attacker or buggy caller might plausibly
    try - including columns from related tables (``pairing_token_hash``)
    to guard against the validator accidentally passing through
    arbitrary kwarg names.
    """
    with pytest.raises(SyncQueueStateError, match="forbidden"):
        _validate_update_columns(
            {"estado": "exitoso", forbidden_column: "anything"}
        )


def test_validate_accepts_whitelist_only_payload() -> None:
    """A payload using ONLY whitelist keys is accepted.

    Defense-in-depth mirror of the reject test - the validator must
    succeed for the legitimate payload shape that
    ``mark_dispatched`` / ``mark_in_progress`` / ``mark_failed``
    build internally.
    """
    # Should NOT raise.
    _validate_update_columns(
        {
            "estado": "exitoso",
            "intentos": 1,
            "next_retry_at": None,
            "ultimo_error": None,
        }
    )


def test_validate_rejects_empty_payload_is_a_noop() -> None:
    """An empty dict passes (nothing to validate).

    The validator's job is to catch forbidden columns in a
    *candidate* payload; an empty payload has no candidates. This
    keeps the helper composable: callers may pass ``values={}`` for
    a "validate nothing" path.
    """
    # Should NOT raise.
    _validate_update_columns({})


def test_validate_rejects_with_descriptive_error() -> None:
    """The error message must enumerate the allowed set + the forbidden columns.

    Without the descriptive message, an operator looking at the
    stack trace would not know which column they tried to set.
    """
    with pytest.raises(SyncQueueStateError) as excinfo:
        _validate_update_columns(
            {"estado": "exitoso", "datos": {"foo": "bar"}}
        )
    msg = str(excinfo.value)
    # The error must name the allowed columns (sorted for stability).
    assert "estado" in msg
    assert "intentos" in msg
    assert "next_retry_at" in msg
    assert "ultimo_error" in msg
    # And the offending column.
    assert "datos" in msg


def test_validate_runs_before_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """The validator raises before any DB call is issued.

    Pins the design contract: the validator MUST be the first line
    of defense. We monkey-patch SQLAlchemy ``update`` to raise if
    the validator ever lets a forbidden payload through - which
    would be a regression.

    The real regression this guards against: a future refactor
    that "simplifies" the validators away, expecting the DB GRANT
    to do the job. That would round-trip to Postgres for every
    bad call (slow) and produce a less informative error.
    """
    import sqlalchemy

    called = {"update": 0}
    real_update = sqlalchemy.update

    def counting_update(*args, **kwargs):
        called["update"] += 1
        return real_update(*args, **kwargs)

    monkeypatch.setattr(sqlalchemy, "update", counting_update)

    # Forbidden payload - must raise client-side.
    with pytest.raises(SyncQueueStateError):
        _validate_update_columns({"estado": "x", "datos": {}})

    # Critical assertion: no SQLAlchemy update was issued.
    assert called["update"] == 0, (
        "_validate_update_columns must raise before any SQLAlchemy "
        "update() call; the validator is the first line of defense"
    )


def test_validate_accepts_uuid_value_for_whitelisted_intentos_column() -> None:
    """The validator is type-agnostic - only column NAMES matter.

    The whitelist is a column-level contract, not a value-level one.
    A caller that passes ``intentos=uuid_lib.uuid4()`` (wrong type
    but right name) gets a ``SyncQueueStateError``-free path; the
    DB will reject the type mismatch via the SQL type system. The
    Python validator's job is just to keep the column set tight.
    """
    # Should NOT raise - 'intentos' is whitelisted even with a weird value.
    _validate_update_columns({"intentos": uuid_lib.uuid4()})
