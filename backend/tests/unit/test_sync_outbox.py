"""test_sync_outbox.py - REQ-X6 + SC-X5 design fence.

The repo.sync_outbox.enqueue_sync_row() facade is a no-op by design -
it always raises RuntimeError. The DB trigger prod.fn_enqueue_sync() is
the canonical outbox path; this Python function exists to keep callers
honest. This test pins that contract.

Defense in depth (AGENTS.md §1 + §3): the [A] canon forbids any Python
path that bypasses the DB-side trigger. The facade is the design-enforced
fence that makes the contract visible at the import site; if any
contributor ever reaches for it, the test catches the regression
immediately.
"""
from __future__ import annotations

import re

import pytest
from parkos_core.repo.sync_outbox import enqueue_sync_row


def test_enqueue_sync_row_always_raises():
    """The facade raises RuntimeError even with no arguments.

    The message must mention the "no-op by design" contract - that's
    the signal callers grep for when they accidentally reach for the
    facade.
    """
    with pytest.raises(RuntimeError, match="no-op by design"):
        enqueue_sync_row()


def test_enqueue_sync_row_raises_with_arbitrary_args():
    """Even with valid-looking args, the facade raises unconditionally.

    The contract is "any call raises" - not "valid args proceed". The
    function body is one line (`raise RuntimeError(...)`); no arg
    validation happens because none should.
    """
    with pytest.raises(RuntimeError, match=re.escape("parkos_core.repo.sync_outbox")):
        enqueue_sync_row(
            session=None,  # type: ignore[arg-type]
            tabla="factura_pagos",
            uuid_registro="00000000-0000-0000-0000-000000000000",
        )


def test_enqueue_sync_row_raises_with_only_kwargs():
    """Keyword-only call also raises - the contract is symmetric."""
    with pytest.raises(RuntimeError):
        enqueue_sync_row(tabla="factura_pagos")


def test_enqueue_sync_row_error_message_names_legitimate_alternative():
    """The error message must point callers at repo.sync_queue.enqueue.

    Without that hint, a future contributor might just delete the
    facade and accidentally introduce a Python-side outbox that
    bypasses the DB trigger (the exact failure mode the facade
    exists to prevent).
    """
    with pytest.raises(RuntimeError) as excinfo:
        enqueue_sync_row()
    msg = str(excinfo.value)
    # Must mention the legitimate programmatic escape hatch.
    assert "repo.sync_queue.enqueue" in msg
    # Must mention the canonical DB path.
    assert "fn_enqueue_sync" in msg
