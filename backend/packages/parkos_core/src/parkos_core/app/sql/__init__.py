"""``parkos_core.app.sql`` — pure-function SQL builders.

Builders in this subpackage MUST NOT touch the DB session, log, or
``datetime.now()``. Their job is to map a fixed input tuple to a
SQL string with named bind parameters; the caller (a repo helper)
provides the actual parameter values at execution time.

Adding a new builder? Keep it pure (no ``await``, no ``select()``,
no ORM types) and add a unit test that pins the string output.
"""

__all__ = []