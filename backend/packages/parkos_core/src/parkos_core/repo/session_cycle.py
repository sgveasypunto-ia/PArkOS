"""Session lifecycle helpers for [L-S] tables (design §4.3).

PR1b shipped the auth-domain helpers (``record_login`` /
``close_login_with_log`` for ``prod.login``). PR7 EXTENDS this module
with the cash-session helpers (``open_session`` /
``close_session_with_log`` for ``prod.sesion``) and the login-failure
lockout skeleton (``record_login_failure`` / ``clear_login_failures``
for ``prod.usuarios`` — best-effort until the ``intentos_fallo`` column
lands). Every helper writes a co-transactional ``log_transaccional`` row
to satisfy the DB-layer session-guard trigger on UPDATE.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timezone
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..exceptions import SesionAlreadyActive
from ..models.L_S.login import Login
from ..models.L_S.sesion import Sesion
from ..models.V.usuarios import Usuarios

# SQLSTATE for unique-constraint violation in Postgres. Used to
# detect the partial unique index violation from migration 0023
# (RE ``prod.uq_prod_sesion_one_active_per_user``) inside
# ``open_session`` and translate it to the typed domain exception
# ``SesionAlreadyActive`` (KD-2 / REQ-OPS-028).
_UNIQUE_VIOLATION_SQLSTATE = "23505"


class SessionGuardError(Exception):
    """Raised when the DB-layer session guard trigger fires (LOG_TRANSACCIONAL_REQUIRED)."""


class SessionNotFoundError(SessionGuardError):
    """Raised when a Sesion row doesn't exist, is already closed, or violates
    an open-state invariant on close."""


def _now_naive() -> datetime:
    """Naive UTC ``datetime`` matching the DB ``DateTime(timezone=False)`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


async def record_login(
    session: AsyncSession,
    *,
    usuario_uuid: uuid_lib.UUID,
    sucursal_uuid: uuid_lib.UUID | None = None,
    actor_uuid: uuid_lib.UUID | None = None,
    success: bool = True,
    motivo: str | None = None,
    uuid: uuid_lib.UUID | None = None,
) -> Login:
    """REQ-42-S-LOGIN / REQ-43-S-LOGIN-FAILURE: INSERT a new ``login`` row.

    Args:
        session: Active ``AsyncSession`` (caller commits).
        usuario_uuid: The user attempting login.
        sucursal_uuid: The branch the login is against. ``None`` is valid
            — the column is nullable; the bad-password path in
            ``api/v1/auth.py::login`` records the failure BEFORE the
            first branch assignment is resolved (R-F1.2-1), so this
            helper accepts ``None`` to satisfy the audit invariant.
        actor_uuid: The audit actor. Defaults to ``usuario_uuid`` for self-service.
        success: ``True`` → ``estado='exitoso'``, ``False`` → ``estado='fallido'``.
        motivo: Optional failure reason (carried in the log row).
        uuid: Optional explicit primary key (``None`` — the default —
            keeps the original behavior: the DB's own
            ``gen_random_uuid()`` server default mints it). Set by
            ``motor/apply_row.py``'s catalog-driven ``session_cycle``
            dispatch for ``login`` when applying an already-arrived
            remote row, so the destination's copy carries the SAME
            identity as the origin's — same reasoning as
            ``open_session``'s own ``uuid`` parameter (see its
            docstring); found alongside it wiring the post-PR14
            full-catalog-sync closing exercise.

    Returns:
        The newly created :class:`Login` row (not yet committed).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: UP017
    estado = "exitoso" if success else "fallido"

    login_row = Login(
        uuid_usuario=usuario_uuid,
        uuid_sucursal=sucursal_uuid,
        timestamp_evento=now,
        timestamp_cierre=None,
        vigente_desde=now,
        vigente_hasta=None,
        estado=estado,
        created_at=now,
        created_by=actor_uuid or usuario_uuid,
        sync_status="pendiente",
        **({"uuid": uuid} if uuid is not None else {}),
    )
    session.add(login_row)

    # Co-transactional log row — required by the DB-layer session guard
    # trigger. Routed through ``repo.hash_chain.append`` (PR6, REQ-16 +
    # REQ-X4) rather than a raw ``LogTransaccional(...)`` + ``session.add()``
    # — the latter leaves ``hash_anterior``/``hash_actual`` NULL client-side
    # and relies entirely on the DB trigger to compute them, which has no
    # genesis-row bootstrap of its own and rejects the first login for any
    # ``uuid_sucursal`` never seen before with ``HASH_CHAIN_INTEGRITY_
    # VIOLATION: no genesis row``. ``hash_chain.append`` both computes the
    # chain in Python and transparently bootstraps that genesis row.
    from ..models.A.log_transaccional import LogTransaccional
    from . import hash_chain

    log_attrs = {
        "uuid_usuario": actor_uuid or usuario_uuid,
        "uuid_sucursal": sucursal_uuid,
        "accion": "login",
        "tabla_afectada": "login",
        "timestamp_evento": now,
    }
    await hash_chain.append(
        session, LogTransaccional, log_attrs, actor_uuid=actor_uuid or usuario_uuid
    )
    return login_row


async def close_login_with_log(
    session: AsyncSession,
    *,
    login_uuid: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
) -> Login:
    """REQ-45-S-LOGOUT skeleton: log row FIRST, then UPDATE ``login``.

    The full implementation lands in PR7 (with the timestamp_cierre +
    state-machine validation). PR1b ships this as a skeleton so the auth
    router's ``POST /auth/logout`` endpoint compiles.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: UP017

    # 1. Read current row (for datos_anteriores snapshot)
    from sqlalchemy import select

    result = await session.execute(select(Login).where(Login.uuid == login_uuid))
    row = result.scalar_one_or_none()
    if row is None:
        raise SessionGuardError(f"login {login_uuid} not found")

    # 2. Log row FIRST (so the DB-layer session-guard trigger accepts the
    #    UPDATE). Routed through ``repo.hash_chain.append`` — see
    #    ``record_login``'s docstring note above for why the raw-insert
    #    stub this replaces broke on a ``uuid_sucursal`` never seen before.
    from ..models.A.log_transaccional import LogTransaccional
    from . import hash_chain

    log_attrs = {
        "uuid_usuario": actor_uuid,
        "uuid_sucursal": row.uuid_sucursal,
        "accion": "logout",
        "tabla_afectada": "login",
        "uuid_registro_afectado": login_uuid,
        "timestamp_evento": now,
    }
    await hash_chain.append(session, LogTransaccional, log_attrs, actor_uuid=actor_uuid)
    await session.flush()  # ensure log row is visible to the trigger

    # 3. UPDATE the login row
    from sqlalchemy import update

    await session.execute(
        update(Login).where(Login.uuid == login_uuid).values(timestamp_cierre=now, estado="cerrado")
    )

    # Refresh the row so the caller sees the updated state
    await session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# PR7 — Cash session helpers (REQ-40-S-OPEN, REQ-41-S-CLOSE, SC-40, SC-42)
# ---------------------------------------------------------------------------


async def open_session(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    valor_inicial_efectivo: float,
    valor_inicial_datafono: float,
    uuid_usuario: uuid_lib.UUID,
    log_tx: bool = True,
    uuid: uuid_lib.UUID | None = None,
    observaciones: str | None = None,
) -> Sesion:
    """Open a cash session — REQ-40-S-OPEN.

    Inserts a new ``Sesion`` row + co-transactional ``log_transaccional``
    row in the same TX. The session-guard trigger validates the log row
    on the subsequent UPDATE (close) — but the INSERT itself doesn't
    require a log row first (the trigger only fires on UPDATE/DELETE).

    Args:
        uuid: Optional explicit primary key (``None`` — the default —
            keeps the original behavior: the DB's own
            ``gen_random_uuid()`` server default mints it). Set by
            ``motor/apply_row.py``'s catalog-driven ``session_cycle``
            dispatch for ``sesion`` when applying an already-arrived
            remote row, so the destination's copy carries the SAME
            identity as the origin's — found wiring the post-PR14
            full-catalog-sync closing exercise: without this, ANY table
            with a real ``ForeignKey`` to ``sesion.uuid`` (``arqueo``,
            ``factura_pagos``) raises ``ForeignKeyViolationError`` the
            moment it is synced alongside its ``sesion`` parent, because
            the destination's own freshly-generated ``uuid`` never
            matches the value the child row's FK still carries from the
            origin. Every OTHER ``apply_strategy`` (``close_and_insert``
            excepted, by design — see D17/D18 note elsewhere) already
            preserves ``uuid`` this way since ``model_cls(**payload)``
            naturally passes it through; ``open_session``'s fully-named
            constructor call was the one place that did not.
        observaciones: REQ-OPS-135 (Bug 5 of qa-2026-09-17) free-text
            notes supplied at open time by the F3.3 frontend (capped at
            500 chars by ``SesionCreate``). Persisted into the new
            ``prod.sesion.observaciones`` column added by migration
            0035 (PG11+ instant, no rewrite). When non-NULL, the value
            is mirrored into ``prod.log_transaccional.datos_nuevos``
            for audit (REQ-OPS-021 AUDIT-FIRST canon). When None or
            empty string, neither the column nor the audit payload
            carries the field — no empty-key noise.
    """
    from ..models.A.log_transaccional import LogTransaccional

    now = _now_naive()

    new_row = Sesion(
        valor_inicial_efectivo=valor_inicial_efectivo,
        valor_inicial_datafono=valor_inicial_datafono,
        uuid_sucursal=uuid_sucursal,
        uuid_usuario=uuid_usuario,
        timestamp_apertura=now,
        timestamp_cierre=None,
        uuid_usuario_cierre=None,
        created_at=now,
        created_by=actor_uuid,
        observaciones=observaciones,
        **({"uuid": uuid} if uuid is not None else {}),
    )
    session.add(new_row)

    if log_tx:
        # REQ-OPS-135: when observaciones is provided, mirror it into
        # datos_nuevos for audit. Strip empty strings to NULL-shaped
        # JSON (``None``) so the log row does not carry an empty key.
        datos_nuevos: dict[str, str | None] = {
            "valor_inicial_efectivo": str(valor_inicial_efectivo),
            "valor_inicial_datafono": str(valor_inicial_datafono),
        }
        if observaciones:
            datos_nuevos["observaciones"] = observaciones

        log_row = LogTransaccional(
            uuid_usuario=actor_uuid,
            uuid_sucursal=uuid_sucursal,
            accion="crear",
            tabla_afectada="sesion",
            uuid_registro_afectado=getattr(new_row, "uuid", None),
            timestamp_evento=now,
            datos_nuevos=datos_nuevos,
        )
        session.add(log_row)

    # KD-2 / REQ-OPS-028: the partial unique index from migration 0023
    # (``prod.uq_prod_sesion_one_active_per_user``) rejects a second
    # open sesion for the same ``uuid_usuario``. ``flush()`` forces the
    # INSERTs through so the SA ``IntegrityError`` is inspectable in
    # this frame rather than only at the implicit commit (the previous
    # behaviour left the 500 surface to FastAPI without typed-mapping).
    try:
        await session.flush()
    except IntegrityError as exc:
        pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
        if pgcode == _UNIQUE_VIOLATION_SQLSTATE:
            raise SesionAlreadyActive(uuid_usuario=uuid_usuario) from exc
        raise

    return new_row


async def close_session_with_log(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    sesion_uuid: uuid_lib.UUID,
    valor_final_efectivo: float | None = None,
    valor_final_datafono: float | None = None,
    observaciones: str | None = None,
    log_tx: bool = True,
) -> Sesion:
    """Close a cash session — REQ-41, SC-42.

    UPDATEs the ``Sesion`` row with ``timestamp_cierre`` +
    ``uuid_usuario_cierre``. The DB trigger ``ls_session_guard`` validates
    a ``log_transaccional`` row exists in the same TX — that row is added
    FIRST (then ``flush()``) so the trigger can see it on the subsequent
    UPDATE.

    Final cash counts (``valor_final_*``) are recorded in the log row's
    ``datos_nuevos`` JSONB — the Sesion table only carries
    ``valor_inicial_*`` columns, so the initial values are preserved and
    the deltas live in the audit log. The optional ``observaciones``
    free-text operator note is also stamped into the log row
    (caller-supplied via the PUT ``/caja-sesion/sesion/{uuid}/cerrar``
    payload, mirroring REQ-OPS-119/135 for the open path).
    """
    from ..models.A.log_transaccional import LogTransaccional

    now = _now_naive()

    # 1. Read the current Sesion row (for uuid_sucursal + initial values
    #    to snapshot into datos_nuevos).
    result = await session.execute(select(Sesion).where(Sesion.uuid == sesion_uuid))
    row = result.scalar_one_or_none()
    if row is None:
        raise SessionNotFoundError(f"sesion {sesion_uuid} not found")

    # 2. Log row FIRST (so the DB-layer session-guard trigger accepts the UPDATE)
    if log_tx:
        datos_nuevos: dict[str, object] = {
            "valor_inicial_efectivo": (
                str(row.valor_inicial_efectivo)
                if row.valor_inicial_efectivo is not None
                else None
            ),
            "valor_inicial_datafono": (
                str(row.valor_inicial_datafono)
                if row.valor_inicial_datafono is not None
                else None
            ),
            "valor_final_efectivo": (
                str(valor_final_efectivo) if valor_final_efectivo is not None else None
            ),
            "valor_final_datafono": (
                str(valor_final_datafono) if valor_final_datafono is not None else None
            ),
        }
        if observaciones is not None:
            datos_nuevos["observaciones"] = observaciones
        log_row = LogTransaccional(
            uuid_usuario=actor_uuid,
            uuid_sucursal=row.uuid_sucursal,
            accion="cerrar",
            tabla_afectada="sesion",
            uuid_registro_afectado=sesion_uuid,
            timestamp_evento=now,
            datos_nuevos=datos_nuevos,
        )
        session.add(log_row)
        await session.flush()  # ensure log row is visible to the trigger

    # 3. UPDATE the Sesion row (the trigger fires here and validates the log row)
    update_result_raw = await session.execute(
        update(Sesion)
        .where(Sesion.uuid == sesion_uuid, Sesion.timestamp_cierre.is_(None))
        .values(timestamp_cierre=now, uuid_usuario_cierre=actor_uuid, estado="cerrado")
    )
    # mypy --strict sees ``Result[Any]`` from ``session.execute``;
    # ``rowcount`` is only on ``CursorResult``. The UPDATE statement
    # always returns a ``CursorResult`` at runtime (no RETURNING
    # clause, no scalar projection), so the cast is safe.
    update_result = cast(CursorResult[Any], update_result_raw)
    if update_result.rowcount == 0:
        raise SessionNotFoundError(f"sesion {sesion_uuid} already closed or not found")

    # 4. Refresh and return so the caller sees the updated state
    await session.refresh(row)
    return row


async def record_login_failure(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_usuario: uuid_lib.UUID,
    ip_origen: str | None = None,
) -> None:
    """Increment the ``usuarios.intentos_fallo`` counter (REQ-OP-11).

    Best-effort: if the ``Usuarios`` model has no ``intentos_fallo`` column
    (PR1b didn't add it), this function silently no-ops. Future PR adds
    the column + the lockout enforcement: 3 failures within 15 min locks
    the user out for 30 min (REQ-43, SC-41).

    Args:
        session: Active ``AsyncSession`` (caller commits).
        actor_uuid: JWT subject (audit actor).
        uuid_usuario: User whose failure counter should increment.
        ip_origen: Optional IP for the audit log (currently unused —
            the column will land with the lockout PR).
    """
    # Column doesn't exist yet on the ORM — no-op (documented limitation).
    if not hasattr(Usuarios, "intentos_fallo"):
        return

    # Future PR: read current_version(), increment counter, close+insert
    # via repo.versioned.close_and_insert. For now: nothing to do.
    return


async def clear_login_failures(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_usuario: uuid_lib.UUID,
) -> None:
    """Reset ``usuarios.intentos_fallo`` on successful login (REQ-OP-11).

    Best-effort no-op when the column doesn't exist on the model yet.
    When the column lands, this will read the current version, reset the
    counter to 0, and close+insert via ``repo.versioned.close_and_insert``.
    """
    if not hasattr(Usuarios, "intentos_fallo"):
        return

    # Future PR: close+insert with ``intentos_fallo=0``.
    return


__all__ = [
    "SesionAlreadyActive",
    "SessionGuardError",
    "SessionNotFoundError",
    "clear_login_failures",
    "close_login_with_log",
    "open_session",
    "record_login",
    "record_login_failure",
]
