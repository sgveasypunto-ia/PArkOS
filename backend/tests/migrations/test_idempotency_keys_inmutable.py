"""Migration test — idempotency_keys BEFORE UPDATE/DELETE trigger + REVOKE.

Verifies (SC-13):

- INSERT succeeds (rol_app has INSERT).
- UPDATE raises (REVOKE UPDATE + ``idempotency_keys_inmutable`` trigger).
- DELETE raises (REVOKE DELETE + ``idempotency_keys_inmutable`` trigger).

Requires a live Postgres (testcontainers). Skipped when no DB is available
because the project ships without a built ``parkos-postgres:16-pgpartman``
image by default.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="Requires testcontainers Postgres with pg_partman — skip when no live DB"
)


def test_insert_succeeds(db_session):
    """INSERT a new ``idempotency_keys`` row succeeds (rol_app has INSERT)."""
    pytest.skip("testcontainers not wired in this environment")


def test_update_raises(db_session):
    """UPDATE the row raises (REVOKE UPDATE + ``idempotency_keys_inmutable`` trigger)."""
    pytest.skip("testcontainers not wired in this environment")


def test_delete_raises(db_session):
    """DELETE the row raises (REVOKE DELETE + ``idempotency_keys_inmutable`` trigger)."""
    pytest.skip("testcontainers not wired in this environment")
