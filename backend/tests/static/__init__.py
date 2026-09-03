"""Static AST-scan tests (PR1c).

These tests run WITHOUT a database — they parse the source tree with
``ast`` and reject code patterns that violate project invariants:

  - No DELETE routes anywhere under ``parkos_core/api/`` (SC-04)
  - No raw UPDATE on [V] tables outside ``repo/versioned.py`` (C-2)
  - No raw DML on [A] tables outside the future ``repo/append_only.py``
  - No raw DML on [L-S] tables outside ``repo/session_cycle.py``
  - ``api_sucursal_main`` OpenAPI excludes cloud-only paths (REQ-X3)

Each scanner is parameterized so adding a new [A] / [L-S] / [V] class
automatically extends the rejection set without code edits.
"""