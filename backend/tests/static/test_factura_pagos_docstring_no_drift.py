"""HU-F1.9 / T8.1 -- Docstring drift check on ``models/A/factura_pagos.py``.

The ORM docstring on ``prod.factura_pagos`` MUST stay in sync with the
DB-layer defenses. Specifically:

- It MUST NOT reference ``0004_add_factura_pagos_reverso_index.py``
  (a filename that does NOT exist; the actual reverso migration is
  ``0004_add_factura_pagos_reverso_trigger.py`` -- a BEFORE INSERT
  trigger, not an index).
- It MUST mention ``fn_factura_pagos_init_pago_uniqueness`` (F1.9's
  MIGRATION 0027 Op 3 BEFORE INSERT trigger on the same table --
  closes the 2nd-init-pago race that the partial UK cannot enforce
  across partitions).

Pattern: F1.7 ``test_*.py`` precedent for static docstring checks.
Pure regex on source, no DB.
"""
from __future__ import annotations

import re
from pathlib import Path

FACTURA_PAGOS_PATH = Path(
    "packages/parkos_core/src/parkos_core/models/A/factura_pagos.py"
)


def test_factura_pagos_docstring_no_references_nonexistent_migration() -> None:
    """T1: docstring MUST NOT reference the broken filename.

    The filename ``0004_add_factura_pagos_reverso_index.py`` is stale
    (the actual migration 0004 is a BEFORE INSERT TRIGGER, not an
    INDEX). If this test fails, a future-dev has reintroduced the
    drift.
    """
    src = FACTURA_PAGOS_PATH.read_text(encoding="utf-8")
    assert re.search(r"0004_add_factura_pagos_reverso_index\.py", src) is None, (
        "Docstring drift detected: references non-existent migration "
        "'0004_add_factura_pagos_reverso_index.py'. The actual migration "
        "is '0004_add_factura_pagos_reverso_trigger.py' (a BEFORE INSERT "
        "trigger, not an index)."
    )


def test_factura_pagos_docstring_documents_init_pago_trigger() -> None:
    """T2: docstring MUST mention ``fn_factura_pagos_init_pago_uniqueness``.

    F1.9 / MIGRATION 0027 Op 3 added a NEW BEFORE INSERT trigger on
    ``prod.factura_pagos`` that rejects a 2nd ``pago``/``ajuste`` row
    for the same ``uuid_factura``. The ORM docstring MUST document
    this so future maintainers know the trigger exists.
    """
    src = FACTURA_PAGOS_PATH.read_text(encoding="utf-8")
    assert "fn_factura_pagos_init_pago_uniqueness" in src, (
        "Docstring drift: models/A/factura_pagos.py MUST document "
        "fn_factura_pagos_init_pago_uniqueness (F1.9 MIGRATION 0027 "
        "Op 3 BEFORE INSERT trigger). The trigger is the only "
        "DB-layer defense against duplicate init-pago rows because "
        "prod.factura_pagos is range-partitioned (partial UK infeasible)."
    )
