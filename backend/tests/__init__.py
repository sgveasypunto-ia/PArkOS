"""parkos backend tests (PR1c+).

Test layout (per ``openspec/changes/create-49-table-apis/design.md`` §15):

  - ``tests/conftest.py``           — session-scope testcontainers Postgres +
                                     pytest fixtures + JWT mint helpers
  - ``tests/migrations/``           — DB-level enforcement tests (PR1a schema
                                     invariants, PR2 sync outbox, hash chain)
  - ``tests/static/``               — AST scans: no DELETE routes, no raw DML
                                     outside the repo helpers, OpenAPI scope
  - ``tests/unit/``                 — unit tests for ORM helpers, JWT,
                                     pagination, permissions, session cycle
  - ``tests/repo/``                 — PR2+ repo helper tests (placeholder)
  - ``tests/api/``                  — PR2+ router integration tests (placeholder)
"""