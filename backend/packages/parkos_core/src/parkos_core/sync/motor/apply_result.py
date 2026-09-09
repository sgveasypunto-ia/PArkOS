"""motor/apply_result.py — ``ApplyResult`` dataclass (T-PR4-002).

REQ-MOT-005: the return type of ``motor.apply_row.apply_row`` /
``SyncMotor.apply_row``. ``metrics`` always carries all 4 hook-invocation
booleans (T-PR4-002's acceptance wording) so an operator can audit, per row,
which of the 4 lifecycle hook phases actually ran (design.md §5/§6,
``specs/sync-motor.md`` REQ-MOT-005). ``bool`` is a subtype of ``int`` in
Python, so this also satisfies the spec's ``dict[str, int]`` (``0|1``)
wording verbatim.
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass, field
from typing import Literal

ApplyStatus = Literal["APPLIED", "CONFLICT", "RETRY"]

# The 4 hook lifecycle phases apply_row.py accounts for in ApplyResult.metrics
# (REQ-HOOK-003's lifecycle order minus the repo call itself).
HOOK_METRIC_KEYS: tuple[str, ...] = (
    "hook_validate_parent",
    "hook_pre_insert",
    "hook_post_insert",
    "hook_chain_extend",
)


def _default_metrics() -> dict[str, bool]:
    return dict.fromkeys(HOOK_METRIC_KEYS, False)


@dataclass
class ApplyResult:
    """Outcome of one ``apply_row`` call (REQ-MOT-005).

    ``status``: ``APPLIED`` | ``CONFLICT`` | ``RETRY``.
    ``row_uuid``: the applied row's uuid, or ``None`` when nothing was
    persisted (e.g. ``RETRY``).
    ``reason``: ``None`` on ``APPLIED``; e.g. ``"parent_missing"`` on
    ``RETRY``, ``"hash_chain_break"`` on a chain-verification ``CONFLICT``.
    ``metrics``: which of the 4 hook lifecycle phases actually ran.
    """

    status: ApplyStatus
    row_uuid: uuid_lib.UUID | None = None
    reason: str | None = None
    metrics: dict[str, bool] = field(default_factory=_default_metrics)


__all__ = ["HOOK_METRIC_KEYS", "ApplyResult", "ApplyStatus"]
