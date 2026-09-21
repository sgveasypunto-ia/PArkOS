"""``parkos_core.app`` — application-level helpers (SQL builders, etc.).

Subpackage ``sql`` holds pure-function SQL string builders that are
exercised by repo helpers without an active DB session. The builders
are pure (same input -> same SQL) so they can be unit-tested without
testcontainers / Docker.
"""

__all__ = []