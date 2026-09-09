"""role_guard.py — boot-import role guard (T-PR1-010, R-D4, R6, REQ-OPS-005, REQ-MOT-012).

Mirrors the existing ``dian/cloud/dian_providers/factus.py`` precedent
(module-level ``if os.environ.get("PARKOS_DEPLOY", "cloud").lower() ==
"branch": raise ImportError(...)``), generalized into a reusable helper so
every role-scoped catalog entry module (PR2+, ``role_required="cloud"`` or
``role_required="branch"``) can call one function instead of repeating the
env-var check.

``role_required="both"`` entries (e.g. ``envio_dian``) never call
:func:`assert_role` at all — the guard's ``role`` parameter only accepts
``"cloud"``/``"branch"`` by design, so a "both" entry structurally cannot
be blocked by this guard.
"""

from __future__ import annotations

import os
from typing import Literal

Role = Literal["cloud", "branch"]


def assert_role(role: Role, *, table: str | None = None) -> None:
    """Raise ``ImportError`` when the current deploy does not match ``role``.

    Args:
        role: The deploy role this module/entry is scoped to
            (``"cloud"`` or ``"branch"``). Never ``"both"`` — entries with
            ``role_required="both"`` do not call this guard at all.
        table: Optional table/entry name, included in the error message so
            an operator can immediately identify the offending entry from
            a boot-time traceback.

    Raises:
        ImportError: when ``PARKOS_DEPLOY`` (default ``"cloud"``, matching
            the ``factus.py`` precedent) does not equal ``role``.
    """
    deploy = os.environ.get("PARKOS_DEPLOY", "cloud").lower()
    if deploy != role:
        label = f"{table}: " if table else ""
        raise ImportError(
            f"{label}{role}_only entry not allowed on {deploy} (PARKOS_DEPLOY={deploy!r})"
        )


__all__ = ["Role", "assert_role"]
