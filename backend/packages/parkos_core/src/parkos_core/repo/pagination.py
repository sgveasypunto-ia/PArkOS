"""Opaque cursor encode/decode (REQ-OP-01, SC-OP-01).

Format: ``base64url(json({"vigente_desde": iso8601, "uuid": "<uuid>"}))``.

Why opaque: callers never construct cursors themselves — they're round-trip
artefacts of paginated list responses. A future migration (e.g. adding a
third key for tie-break) is a one-place change here, with no client impact.

Why base64url: URL-safe (no padding issues), compact, supports query strings.
"""
from __future__ import annotations

import base64
import json
import uuid as uuid_lib
from dataclasses import dataclass


class InvalidCursorError(ValueError):
    """Raised when a cursor cannot be decoded or fails validation."""


@dataclass(frozen=True)
class Cursor:
    """Opaque pagination cursor.

    Sort key is ``(vigente_desde DESC, uuid ASC)`` for [V] history;
    ``(timestamp_evento DESC, uuid ASC)`` for [L-E] and [L-S] event streams;
    ``(created_at DESC, uuid ASC)`` for [A] logs.
    """

    vigente_desde: str  # ISO 8601
    uuid: str  # uuid string


def encode(cursor: Cursor) -> str:
    """Encode a Cursor into a URL-safe opaque string."""
    payload = {
        "vigente_desde": cursor.vigente_desde,
        "uuid": cursor.uuid,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode(opaque: str) -> Cursor:
    """Decode an opaque cursor string. Raises :class:`InvalidCursorError` on
    malformed JSON, missing fields, or invalid types.
    """
    if not isinstance(opaque, str) or not opaque:
        raise InvalidCursorError("cursor must be a non-empty string")
    try:
        padded = opaque + "=" * (-len(opaque) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise InvalidCursorError(f"cursor not decodable: {e}") from e

    if not isinstance(data, dict):
        raise InvalidCursorError("cursor payload must be an object")
    vig = data.get("vigente_desde")
    uuid_str = data.get("uuid")
    if not isinstance(vig, str) or not vig:
        raise InvalidCursorError("cursor missing vigente_desde")
    if not isinstance(uuid_str, str) or not uuid_str:
        raise InvalidCursorError("cursor missing uuid")

    # Validate ISO 8601 timestamp
    from datetime import datetime

    try:
        datetime.fromisoformat(vig.replace("Z", "+00:00"))
    except ValueError as e:
        raise InvalidCursorError(f"vigente_desde not ISO 8601: {e}") from e

    # Validate UUID
    try:
        uuid_lib.UUID(uuid_str)
    except ValueError as e:
        raise InvalidCursorError(f"uuid not valid: {e}") from e

    return Cursor(vigente_desde=vig, uuid=uuid_str)


__all__ = ["Cursor", "InvalidCursorError", "encode", "decode"]