"""test_dependency_orderer.py — T-PR3-004/005 acceptance for motor/dependency_orderer.py.

Given an already-selected batch of queue rows, when ``order_batch`` sorts
it, then:

  - ``test_parents_before_children``: ``facturas`` precedes
    ``factura_pagos`` despite the legacy ``priority`` values
    (``factura_pagos=5``, ``facturas=1`` — R12, ADR-003 Validation).
  - ``test_batch_selection_unchanged``: the selection query
    ``repo/sync_queue.py::list_pending`` builds is byte-identical to
    ``prioridad DESC, intentos ASC, created_at ASC``, default ``LIMIT 100``
    (ADR-003 Validation, addendum #4) — proving PR3 did not touch it.

Both tests are pure Python / no DB (design's "Runtime harness: N/A — pure
graph algorithm, no DB").
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field

from parkos_core.repo.sync_queue import list_pending
from parkos_core.sync.motor.dependency_orderer import order_batch


@dataclass
class _FakeRow:
    """Minimal stand-in for a ``SyncQueue`` row — only ``tabla`` is read.

    ``prioridad`` is carried for test readability only (documenting the
    legacy value that must NOT win); ``order_batch`` never reads it (rule 7
    — see ``test_check_catalog_drift.py``'s AST-check tests).
    """

    tabla: str
    prioridad: int = field(default=0)


def test_parents_before_children() -> None:
    """facturas precedes factura_pagos despite the legacy priority values.

    The batch arrives in the order the legacy (wrong) ``prioridad DESC``
    cross-table read would rank them — ``factura_pagos`` (priority 5)
    ahead of ``facturas`` (priority 1) — proving the fix is real: without
    topological ordering, this input would already be in the "wrong" order.
    """
    batch = [
        _FakeRow(tabla="factura_pagos", prioridad=5),
        _FakeRow(tabla="facturas", prioridad=1),
    ]

    ordered = order_batch(batch)

    ordered_tables = [row.tabla for row in ordered]
    assert ordered_tables.index("facturas") < ordered_tables.index("factura_pagos"), ordered_tables


def test_order_batch_is_stable_within_a_level() -> None:
    """Rows at the same topological level keep their incoming relative order.

    ``usuarios``, ``permisos``, and ``tipo_persona`` are all root entries
    (empty ``depends_on``) — same level, unrelated to each other — so a
    stable sort must preserve whatever order ``list_pending`` already
    established between them (the FIFO tie-break, R12) — this is how
    ``priority`` "survives" without ``order_batch`` ever reading it.
    """
    batch = [_FakeRow(tabla="usuarios"), _FakeRow(tabla="permisos"), _FakeRow(tabla="tipo_persona")]

    ordered = order_batch(batch)

    assert [row.tabla for row in ordered] == ["usuarios", "permisos", "tipo_persona"]


async def test_batch_selection_unchanged() -> None:
    """list_pending's selection query is byte-identical to prioridad DESC,
    intentos ASC, created_at ASC, LIMIT <default 100> — PR3 does not touch it.
    """
    # Default limit is still 100 (design.md Issue #7 / ADR-003 Validation:
    # "prioridad DESC, intentos ASC, created_at ASC LIMIT 100").
    assert inspect.signature(list_pending).parameters["limit"].default == 100

    captured: dict[str, object] = {}

    class _CaptureResult:
        def scalars(self):
            class _Scalars:
                def all(self_inner):
                    return []

            return _Scalars()

    class _CaptureSession:
        async def execute(self, stmt):
            captured["stmt"] = stmt
            return _CaptureResult()

    await list_pending(_CaptureSession(), limit=100)

    compiled = str(captured["stmt"].compile(compile_kwargs={"literal_binds": True}))
    assert (
        "ORDER BY prod.sync_queue.prioridad DESC, prod.sync_queue.intentos ASC, "
        "prod.sync_queue.created_at ASC" in compiled
    ), compiled
    assert "LIMIT 100" in compiled, compiled
