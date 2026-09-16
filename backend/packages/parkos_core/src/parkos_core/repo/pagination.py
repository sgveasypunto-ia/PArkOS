"""Opaque cursor encode/decode (REQ-OP-01, SC-OP-01).

Format: ``base64url(json({"vigente_desde"|"created_at": iso8601,
                          "uuid": "<uuid>"}))``.

Why opaque: callers never construct cursors themselves — they're round-trip
artefacts of paginated list responses. A future migration (e.g. adding a
third key for tie-break) is a one-place change here, with no client impact.

Why base64url: URL-safe (no padding issues), compact, supports query strings.

HU-F1.1 (GAP-BE-02): the schema gained a second optional timestamp key,
``created_at``, alongside ``vigente_desde``. The router_factory now orders
``[A]``/``[L-E]``/``[L_S]``-Sesion tables (which have no ``vigente_desde``
column) by ``created_at DESC, uuid ASC``; the cursor carries whichever
timestamp was used to build it. Existing cursors that only have
``vigente_desde`` still decode cleanly — the JSON shape is backward-
compatible (clients see a base64url blob; the only difference is the
internal key for the non-[V] cases).
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

    Exactly ONE of ``vigente_desde`` / ``created_at`` is set:

    - ``vigente_desde`` — for [V] tables and any [L-W]/[L-S] model that
      re-declares the column locally (e.g. ``Login``, ``Alerta``).
      Sort key: ``(vigente_desde DESC, uuid ASC)``.
    - ``created_at`` — for [A] tables, ``Sesion`` ([L-S]), and [L-E]
      tables (``Facturas``, ``FacturaElectronica``, ``Ingreso``). Sort
      key: ``(created_at DESC, uuid ASC)``.

    The dataclass exposes both fields as ``str | None`` so callers always
    read the field they expect and ``None`` if it's the other one. The
    dataclass is frozen so a cursor cannot be mutated after construction
    (the ``test_cursor_is_frozen_dataclass`` test in
    ``tests/unit/test_pagination_cursor.py`` pins this).
    """

    vigente_desde: str | None = None  # ISO 8601 (set for [V] + re-declaring [L-W]/[L-S])
    created_at: str | None = None  # ISO 8601 (set for [A], [L-S]-Sesion, [L-E])
    uuid: str = ""  # uuid string (always present after decode/encode round-trip)


def _validate_iso8601(value: str, *, field: str) -> None:
    """Raise ``InvalidCursorError`` if ``value`` is not a valid ISO-8601 timestamp."""
    from datetime import datetime

    try:
        # ``datetime.fromisoformat`` accepts the ``T`` separator and the
        # ``Z`` UTC suffix since Python 3.11. ``isoformat()`` never emits
        # ``Z`` itself (it emits ``+00:00``) — but external callers might
        # hand-craft a cursor with ``Z`` for compatibility. The
        # ``.replace("Z", ...)`` is defensive; suppress FURB162.
        datetime.fromisoformat(value.replace("Z", "+00:00"))  # noqa: FURB162
    except ValueError as e:
        raise InvalidCursorError(f"{field} not ISO 8601: {e}") from e


def _validate_uuid(value: str) -> None:
    """Raise ``InvalidCursorError`` if ``value`` is not a valid UUID string."""
    try:
        uuid_lib.UUID(value)
    except ValueError as e:
        raise InvalidCursorError(f"uuid not valid: {e}") from e


def encode(cursor: Cursor) -> str:
    """Encode a Cursor into a URL-safe opaque string.

    Only non-None timestamp fields are written to JSON. Validation
    enforces the "exactly one timestamp" invariant so a malformed
    Cursor raises immediately rather than producing a cursor that
    decodes to a different shape.
    """
    # Defensive: refuse to encode an invalid cursor (exactly one of the
    # two timestamp keys must be set, and uuid must be non-empty).
    ts_set = sum(v is not None for v in (cursor.vigente_desde, cursor.created_at))
    if ts_set != 1:
        raise InvalidCursorError(
            f"cursor must carry exactly one of vigente_desde/created_at, got {ts_set}"
        )
    if not cursor.uuid:
        raise InvalidCursorError("cursor missing uuid")

    payload: dict[str, str] = {"uuid": cursor.uuid}
    if cursor.vigente_desde is not None:
        payload["vigente_desde"] = cursor.vigente_desde
    if cursor.created_at is not None:
        payload["created_at"] = cursor.created_at

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode(opaque: str) -> Cursor:
    """Decode an opaque cursor string. Raises :class:`InvalidCursorError` on
    malformed JSON, missing fields, or invalid types.

    Accepts cursors carrying EITHER ``vigente_desde`` OR ``created_at`` as
    the timestamp key (exactly one of the two must be present).
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
    cat = data.get("created_at")
    uuid_str = data.get("uuid")

    ts_present = sum(v is not None for v in (vig, cat))
    if ts_present == 0:
        raise InvalidCursorError(
            "cursor missing both vigente_desde and created_at "
            "(exactly one is required)"
        )
    if ts_present > 1:
        raise InvalidCursorError(
            "cursor carries both vigente_desde and created_at "
            "(exactly one is allowed)"
        )

    if not isinstance(uuid_str, str) or not uuid_str:
        raise InvalidCursorError("cursor missing uuid")

    # Validate whichever timestamp is present, then validate uuid.
    # We always validate uuid regardless of which timestamp branch we
    # take — that keeps the contract identical to the pre-HU-F1.1 form
    # (the existing ``test_decode_rejects_invalid_uuid`` test pins
    # uuid rejection on the vigente_desde path).
    if vig is not None:
        if not isinstance(vig, str) or not vig:
            raise InvalidCursorError("cursor missing vigente_desde")
        _validate_iso8601(vig, field="vigente_desde")
        _validate_uuid(uuid_str)
        return Cursor(vigente_desde=vig, uuid=uuid_str)
    # cat is not None here (ts_present == 1).
    if not isinstance(cat, str) or not cat:
        raise InvalidCursorError("cursor missing created_at")
    _validate_iso8601(cat, field="created_at")
    _validate_uuid(uuid_str)
    return Cursor(created_at=cat, uuid=uuid_str)


__all__ = ["Cursor", "InvalidCursorError", "decode", "encode"]