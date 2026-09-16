"""Domain exceptions raised by ``parkos_core`` repos (HU-F1.3+).

Carries typed errors re-emitted by the repo layer so HTTP handlers can
map them to stable 4xx codes WITHOUT leaking driver internals (pgcode,
raw driver messages) to the client (REQ-OPS-028).

Add a new exception class here when a repo translates a low-level
driver / DB error into a typed domain exception; keep the name
self-descriptive (``<Resource><Why>`` shape).
"""

from __future__ import annotations

import uuid as uuid_lib


class SesionAlreadyActive(Exception):
    """Raised when ``repo.session_cycle.open_session`` cannot insert a
    new ``prod.sesion`` row because the partial unique index
    ``prod.uq_prod_sesion_one_active_per_user`` already forbids it.

    Carries ``uuid_usuario`` (the actor the offending row belongs to)
    so ops triage can correlate the event without exposing the
    driver ``pgcode`` or raw Postgres error message
    (REQ-OPS-028 KD-1).
    """

    def __init__(self, uuid_usuario: uuid_lib.UUID) -> None:
        super().__init__(f"sesion already active for uuid_usuario={uuid_usuario!s}")
        self.uuid_usuario = uuid_usuario


__all__ = ["SesionAlreadyActive"]
