"""Unit pins: JSON-safe conflict snapshots and the apply-failure log detail."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from parkos_core.sync.hooks.impls.identity_reconciler import _json_safe
from parkos_core.sync.motor.sync_motor import describe_apply_error_detail


def test_json_safe_serializes_plain_dates() -> None:
    out = _json_safe(
        {
            "d": date(2026, 10, 4),
            "ts": datetime(2026, 10, 7, 1, 2, 3),
            "n": Decimal("1.5"),
            "u": uuid4(),
        }
    )
    assert out is not None
    assert out["d"] == "2026-10-04"
    json.dumps(out)  # must not raise


class _Orig(Exception):
    pass


class _Wrapper(Exception):
    def __init__(self, orig: Exception) -> None:
        super().__init__("full message with bound parameters: {'secret': 1}")
        self.orig = orig


def test_detail_uses_original_message_not_wrapper_parameters() -> None:
    detail = describe_apply_error_detail(_Wrapper(_Orig("boom\nlines")))
    assert detail == "_Orig: boom lines"
    assert "secret" not in detail


def test_json_safe_is_recursive_and_covers_more_types() -> None:
    from datetime import time, timedelta

    out = _json_safe({"l": [date(2026, 1, 2), {"u": uuid4()}], "t": time(1, 2), "d": timedelta(seconds=3)})
    assert out is not None
    json.dumps(out)


class _PgOrig(Exception):
    sqlstate = "23505"

    def __init__(self) -> None:
        super().__init__("Key (cedula)=(12345) already exists.")


def test_detail_for_server_error_omits_row_values() -> None:
    detail = describe_apply_error_detail(_Wrapper(_PgOrig()))
    assert detail == "_PgOrig:23505"
    assert "12345" not in detail


def test_detail_without_cause_does_not_use_wrapper_text() -> None:
    class _NoOrig(Exception):
        params = {"x": 1}  # SQLAlchemy wrappers expose the bound parameters

    assert describe_apply_error_detail(_NoOrig("params {'x': 1}")) == "_NoOrig"


def test_detail_is_truncated() -> None:
    assert len(describe_apply_error_detail(ValueError("x" * 5000))) < 300
