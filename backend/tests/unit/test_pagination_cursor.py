"""test_pagination_cursor.py — REQ-OP-01, SC-OP-01.

Unit tests for the opaque cursor encode/decode helper
(``repo.pagination.encode`` / ``decode``).

The cursor is a base64url-encoded JSON object with the keys
``vigente_desde`` (ISO 8601 string) and ``uuid`` (string). It is
opaque to clients — server constructs, server parses.

Tests verify:

  1. Round-trip preserves both fields exactly.
  2. Malformed payloads (bad base64, bad JSON, missing keys, wrong types)
     raise ``InvalidCursorError``.
  3. Non-ISO-8601 timestamps are rejected.
  4. Invalid UUIDs are rejected.
"""
from __future__ import annotations

import base64
import json
import uuid as uuid_lib

import pytest
from parkos_core.repo.pagination import (
    Cursor,
    InvalidCursorError,
    decode,
    encode,
)


def test_encode_decode_roundtrip() -> None:
    """encode → decode returns the same fields."""
    cursor = Cursor(
        vigente_desde="2026-09-03T12:00:00",
        uuid=str(uuid_lib.uuid4()),
    )
    opaque = encode(cursor)
    decoded = decode(opaque)
    assert decoded.vigente_desde == cursor.vigente_desde
    assert decoded.uuid == cursor.uuid


def test_encode_produces_url_safe_opaque() -> None:
    """The encoded cursor is valid URL-safe base64 (decode succeeds cleanly).

    Some implementations include trailing ``=`` padding and some don't;
    both are valid URL-safe base64. We assert the round-trip decode
    works (regardless of padding choice) and that no ``+`` or ``/`` from
    standard base64 slipped through.
    """
    cursor = Cursor(
        vigente_desde="2026-09-03T12:00:00",
        uuid=str(uuid_lib.uuid4()),
    )
    opaque = encode(cursor)
    # URL-safe base64 uses '-' and '_' instead of '+' and '/'.
    assert "+" not in opaque, f"standard-base64 '+' in output: {opaque!r}"
    assert "/" not in opaque, f"standard-base64 '/' in output: {opaque!r}"
    # Round-trip: decode MUST work whether the implementation includes
    # '=' padding or not (urlsafe_b64decode is tolerant of either).
    padded = opaque + "=" * (-len(opaque) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    assert json.loads(raw)["vigente_desde"] == cursor.vigente_desde


def test_decode_rejects_empty_string() -> None:
    """An empty cursor raises ``InvalidCursorError``."""
    with pytest.raises(InvalidCursorError):
        decode("")


def test_decode_rejects_non_string() -> None:
    """Non-string inputs raise ``InvalidCursorError``."""
    with pytest.raises(InvalidCursorError):
        decode(None)  # type: ignore[arg-type]


def test_decode_rejects_bad_base64() -> None:
    """Random non-base64 content raises ``InvalidCursorError``."""
    with pytest.raises(InvalidCursorError):
        decode("!!!not base64!!!")


def test_decode_rejects_bad_json() -> None:
    """Valid base64 but invalid JSON raises ``InvalidCursorError``."""
    # base64url of "not json" (padded to multiple of 4)
    bad = base64.urlsafe_b64encode(b"not json").rstrip(b"=").decode("ascii")
    with pytest.raises(InvalidCursorError):
        decode(bad)


def test_decode_rejects_non_dict_payload() -> None:
    """A JSON array (not object) is rejected."""
    bad = base64.urlsafe_b64encode(json.dumps([1, 2, 3]).encode()).rstrip(b"=").decode("ascii")
    with pytest.raises(InvalidCursorError):
        decode(bad)


def test_decode_rejects_missing_vigente_desde() -> None:
    """Payload without ``vigente_desde`` is rejected."""
    bad = base64.urlsafe_b64encode(
        json.dumps({"uuid": str(uuid_lib.uuid4())}).encode()
    ).rstrip(b"=").decode("ascii")
    with pytest.raises(InvalidCursorError) as exc:
        decode(bad)
    assert "vigente_desde" in str(exc.value)


def test_decode_rejects_missing_uuid() -> None:
    """Payload without ``uuid`` is rejected."""
    bad = base64.urlsafe_b64encode(
        json.dumps({"vigente_desde": "2026-09-03T12:00:00"}).encode()
    ).rstrip(b"=").decode("ascii")
    with pytest.raises(InvalidCursorError) as exc:
        decode(bad)
    assert "uuid" in str(exc.value)


def test_decode_rejects_non_iso_timestamp() -> None:
    """A free-form string in ``vigente_desde`` is rejected."""
    bad = base64.urlsafe_b64encode(
        json.dumps({"vigente_desde": "yesterday", "uuid": str(uuid_lib.uuid4())}).encode()
    ).rstrip(b"=").decode("ascii")
    with pytest.raises(InvalidCursorError):
        decode(bad)


def test_decode_rejects_invalid_uuid() -> None:
    """A malformed UUID is rejected."""
    bad = base64.urlsafe_b64encode(
        json.dumps({"vigente_desde": "2026-09-03T12:00:00", "uuid": "not-a-uuid"}).encode()
    ).rstrip(b"=").decode("ascii")
    with pytest.raises(InvalidCursorError):
        decode(bad)


def test_decode_accepts_iso_with_z_suffix() -> None:
    """``datetime.fromisoformat`` accepts the ``Z`` UTC suffix in Python 3.11+."""
    cursor = Cursor(
        vigente_desde="2026-09-03T12:00:00Z",
        uuid=str(uuid_lib.uuid4()),
    )
    decoded = decode(encode(cursor))
    assert decoded.vigente_desde == "2026-09-03T12:00:00Z"


def test_cursor_is_frozen_dataclass() -> None:
    """``Cursor`` is frozen — assignment to a field raises ``FrozenInstanceError``."""
    import dataclasses

    cursor = Cursor(vigente_desde="2026-09-03T12:00:00", uuid=str(uuid_lib.uuid4()))
    with pytest.raises(dataclasses.FrozenInstanceError):
        cursor.uuid = "00000000-0000-0000-0000-000000000000"  # type: ignore[misc]