"""Helpers to put exception detail in logs without leaking secrets."""
from __future__ import annotations

import re

_URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/@\s]+@", re.IGNORECASE)
MAX_ERROR_CHARS = 300


def sanitize_error(exc: BaseException) -> str:
    """``str(exc)`` with URL credentials masked, truncated for log aggregation."""
    return _URL_CREDENTIALS.sub(r"\g<scheme>***@", str(exc))[:MAX_ERROR_CHARS]
