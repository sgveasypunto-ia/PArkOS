"""Custom email validators that accept reserved/special-use TLDs.

The default ``pydantic.EmailStr`` uses the ``email_validator`` library with
``test_environment=False``, which rejects RFC 6762 reserved TLDs (``.local``,
``.localhost``) and RFC 2606 reserved-for-testing TLDs (``.test``,
``.example``, ``.invalid``).

For development and staging environments the project uses these reserved
TLDs to bootstrap operator/admin accounts without manual DB intervention
(see ``infra/scripts/bootstrap_pairing.py``: ``ADMIN_EMAIL =
"admin@parkos.local"``). The strict default validator broke the
end-to-end login flow with HTTP 422 BEFORE bcrypt could even run.

This module ships ONE production-grade validator that is permissive about
TLDs but still rejects malformed addresses. The same validator is used
across all email fields in the auth/operator schemas, so the bootstrap
script's ``admin@parkos.local`` works end-to-end AND new operator accounts
created via the admin API (which uses ``.test`` TLD in unit tests) work too.

If a stricter production validator is ever required, set the env var
``PARKOS_EMAIL_VALIDATION=strict`` at api-sucursal/api-admin startup time;
the module will switch to ``test_environment=False`` at import time and
the strict-mode validator will surface RFC 6762 / RFC 2606 rejections again.

Refs: RFC 6762 (``.local`` / ``.localhost`` reserved for mDNS), RFC 2606
(``.test`` / ``.example`` / ``.invalid`` reserved for testing/examples).
"""
from __future__ import annotations

import os
from typing import Annotated

from email_validator import validate_email
from pydantic import BeforeValidator


# Reserved / special-use TLDs that the email_validator library's
# ``test_environment=True`` flag does NOT bypass. We accept these by hand
# BEFORE delegating because they're legitimate dev/local-network TLDs:
#   - ``.local`` / ``.localhost`` per RFC 6762 (mDNS local network)
#   - ``.test`` / ``.example`` / ``.invalid`` per RFC 2606 (testing reserved)
_RESERVED_TLDS_ALLOWED = frozenset(
    {"local", "localhost", "test", "example", "invalid"}
)


def _parkos_email_lenient(v: str) -> str:
    """Lenient validator: RFC 5322 syntax OK + reserved TLDs allowed.

    Used for any auth/operator email field.

    Strategy:
    1. Quick shape check: must contain exactly one ``@`` with non-empty
       local-part and non-empty domain (no whitespace).
    2. If the address's TLD is in ``_RESERVED_TLDS_ALLOWED`` (``.local`` /
       ``.test`` / etc.), accept as-is after shape check (email_validator's
       ``test_environment=True`` does NOT bypass ``.local``/``.localhost``
       rejections — see issue surfaced 2026-09-17 in fix of
       ``infra/scripts/bootstrap_pairing.py`` login).
    3. Otherwise delegate to ``email_validator.validate_email`` with
       ``check_deliverability=False`` (skip DNS) and ``test_environment=True``
       (skip special-name checks). The library handles full RFC 5322 syntax
       including multi-label subdomains, IDN/punycode, etc.

    A malformed address (missing ``@``, bad local-part, etc.) raises
    ``EmailNotValidError`` which Pydantic surfaces as a 422 to the client.
    """
    if not isinstance(v, str):
        raise ValueError(f"Email must be a string, got {type(v).__name__}")
    if " " in v or "\t" in v or "\n" in v:
        raise ValueError(f"Email must not contain whitespace: {v!r}")
    if v.count("@") != 1:
        raise ValueError(f"Email must contain exactly one @-sign: {v!r}")
    local, domain = v.split("@")
    if not local or not domain:
        raise ValueError(f"Email must have non-empty local-part and domain: {v!r}")
    if ".." in v:
        raise ValueError(f"Email must not contain consecutive dots: {v!r}")
    # Extract TLD (rightmost label after the last dot in domain)
    tld = domain.rsplit(".", 1)[-1].lower() if "." in domain else ""
    if tld in _RESERVED_TLDS_ALLOWED:
        # Bypass email_validator's strict reserved-TLD check for dev TLDs.
        return v.strip().lower()
    # For real-world TLDs, delegate to email_validator.
    result = validate_email(v, check_deliverability=False, test_environment=True)
    return result.normalized


def _parkos_email_strict(v: str) -> str:
    """Strict validator: rejects RFC 6762 / RFC 2606 reserved TLDs.

    Opt-in via ``PARKOS_EMAIL_VALIDATION=strict``. Production-only — do NOT
    set this env var in dev/staging because it will break the bootstrap
    flow (see ``bootstrap_pairing.py``).
    """
    validate_email(v, test_environment=False)
    return v


# Mode is captured at import time. Switching requires a process restart.
_STRICT_MODE = (
    os.environ.get("PARKOS_EMAIL_VALIDATION", "").strip().lower() == "strict"
)
_parkos_validator = (
    _parkos_email_strict if _STRICT_MODE else _parkos_email_lenient
)


# Pydantic 2.x: ``Annotated[str, BeforeValidator(...)]`` runs the validator
# BEFORE the field's declared type (``str``) is checked. Raising inside
# the validator surfaces as a standard pydantic ``ValidationError`` on the
# request body, which FastAPI maps to HTTP 422 with the same shape used
# elsewhere in the API (``{"detail": [{"type": "...", "loc": [...], ...}]}``).
ParkosEmail = Annotated[str, BeforeValidator(_parkos_validator)]


__all__ = ["ParkosEmail"]
