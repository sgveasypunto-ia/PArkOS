"""Unit tests for parkos_core helpers (PR1c).

Modules here test single units (no router integration). DB-touching tests
go through the ``pg_session`` fixture from ``tests/conftest.py``. Pure-Python
tests (JWT, cursor encode/decode) need no fixture.
"""