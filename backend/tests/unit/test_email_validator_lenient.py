"""Regression tests for ``schemas._email.ParkosEmail`` (custom validator).

These tests lock in the fix for the issue where ``pydantic.EmailStr`` rejects
RFC 6762 reserved TLDs (``.local``, ``.localhost``) and RFC 2606
reserved-for-testing TLDs (``.test``, ``.example``), breaking the
end-to-end login flow with HTTP 422 BEFORE bcrypt could run.

The fix is in ``schemas/_email.py``: a Pydantic ``BeforeValidator`` wrapper
around ``email_validator.validate_email(..., test_environment=True)`` which
accepts reserved TLDs while still rejecting malformed addresses.

These tests skip when ``PARKOS_EMAIL_VALIDATION=strict`` because that env
var switches the validator back to strict mode (production-only path; see
``schemas/_email.py`` docstring).
"""
from __future__ import annotations

import os

import pytest
from pydantic import BaseModel, ValidationError

from parkos_core.schemas._email import ParkosEmail


pytestmark = pytest.mark.skipif(
    os.environ.get("PARKOS_EMAIL_VALIDATION", "").strip().lower() == "strict",
    reason=(
        "Test verifies lenient mode (default). Skipped when "
        "PARKOS_EMAIL_VALIDATION=strict (production-only path; reserved "
        "TLDs must reject)."
    ),
)


class _Probe(BaseModel):
    """Tiny probe schema that uses ParkosEmail for the email field."""

    email: ParkosEmail


@pytest.mark.parametrize(
    "addr",
    [
        # RFC 6762 reserved .local TLD (the bootstrap_pairing.py dev admin).
        "admin@parkos.local",
        # RFC 6761 special-use localhost host.
        "user@localhost",
        # RFC 2606 reserved-for-testing TLD (used in unit tests).
        "test@parkos.test",
        # RFC 2606 reserved-for-examples TLD.
        "demo@service.example",
        # RFC 2606 reserved-for-invalid TLD.
        "noreply@invalid",
        # Real-world TLDs still work.
        "operator@parkos.com",
        "user.name+tag@subdomain.parkos.local",
        "uppercase@PARKOS.LOCAL",
        # IDN-like multi-label (not full IDN but plausibly common).
        "user@multi.level.subdomain.example.test",
    ],
)
def test_parkos_email_accepts_reserved_and_real_tlds(addr: str) -> None:
    """All reserved-TLD and real-TLD addresses must validate."""
    probe = _Probe(email=addr)
    # email-validator may normalize the case of the domain part; that's
    # the desired production behavior (avoid duplicate-key races on
    # users.email in the versioned projection).
    assert probe.email.lower() == addr.lower()


@pytest.mark.parametrize(
    "addr",
    [
        # No @-sign.
        "no-at-sign",
        # Empty local-part.
        "@missing-local.com",
        # Empty domain.
        "missing-local@",
        # Spaces in local-part.
        "spaces in@local.com",
        # Spaces in domain.
        "user@local domain.com",
        # Two consecutive @-signs.
        "double@@at.com",
        # No local-part.
        "@",
        # Trailing dot in domain with no TLD.
        "user@.",
    ],
)
def test_parkos_email_rejects_malformed_addresses(addr: str) -> None:
    """Malformed addresses must raise — even in lenient mode, the syntax check is strict."""
    with pytest.raises(ValidationError):
        _Probe(email=addr)
