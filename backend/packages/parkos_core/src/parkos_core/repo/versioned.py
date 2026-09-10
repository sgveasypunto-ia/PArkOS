"""Bi-temporal close+insert helper for [V] tables (design §4.1).

REQ-04, REQ-05:
1. UPDATE current SET vigente_hasta = NOW(), estado = 'inactivo' WHERE uuid = :cu
2. INSERT new row with vigente_desde = NOW(), vigente_hasta = NULL, estado = 'activo'
3. (PR2) Write a ``log_transaccional`` row in the same TX

Both operations happen in the same transaction. The caller is responsible for
``session.commit()``.

NOTE: This module is the ONLY allowed UPDATE writer on [V] tables. The AST
test ``tests/static/test_no_raw_upsert_on_v_tables.py`` rejects
``session.execute(update(...))`` against [V] classes outside this module.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Any, TypeVar

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base import VersionedBase

T = TypeVar("T", bound=VersionedBase)

# Columns close_and_insert always recomputes itself (step 2) — never carried
# forward from the row being closed, even when present on the model.
_RESERVED_COLUMNS = frozenset(
    {"uuid", "vigente_desde", "vigente_hasta", "estado", "created_at", "created_by"}
)


class VersioningError(Exception):
    """Base class for versioned-table operation failures."""


class RowNotFoundError(VersioningError):
    """Raised when ``current_uuid`` does not match any row."""


async def close_and_insert(
    session: AsyncSession,
    model_cls: type[T],
    *,
    current_uuid: uuid_lib.UUID | None,
    new_attrs: dict[str, Any],
    actor_uuid: uuid_lib.UUID,
    log_tx: bool = True,
) -> T:
    """Bi-temporal Actualización: close current version, insert new version.

    Args:
        session: Active ``AsyncSession`` (caller commits).
        model_cls: The [V] ORM class to operate on (e.g. ``Usuarios``).
        current_uuid: UUID of the row to close. If ``None``, performs INSERT
            only (no close step) — used for the POST ``/<resource>`` path.
        new_attrs: Column-name → value mapping for the new row. The caller
            supplies business attributes (e.g. ``nombre``, ``email``);
            ``vigente_desde``, ``vigente_hasta``, ``estado``, ``created_at``,
            ``created_by`` are set server-side here. When ``current_uuid`` is
            given, any business column NOT present in ``new_attrs`` is
            carried forward from the row being closed (see the real-defect
            note below) — ``new_attrs`` only needs to name what changed.
        actor_uuid: JWT subject (the writer of the change).
        log_tx: Whether to write a ``log_transaccional`` row in the same TX
            (default ``True``). PR2 ships the helper; PR1b accepts the
            parameter but the actual log row is a no-op stub.

    Returns:
        The newly inserted row instance. ``session.refresh()`` is the
        caller's responsibility (we don't refresh here to keep the helper
        composable inside larger TX).

    Raises:
        RowNotFoundError: ``current_uuid`` doesn't match any row.
        VersioningError: On any other invariant violation (e.g. attempting
            to close a row whose ``vigente_hasta`` is already set — the
            UPDATE returns 0 rows and we raise).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1. Close the current version (if any), and carry forward any business
    #    column not present in `new_attrs` from the row being closed.
    #
    #    Real defect confirmed via live HTTP against router_factory's
    #    generic PUT /{uuid} (qa-e2e audit session, 2026-09-10): every
    #    *Update schema derives its fields from the matching *Create schema
    #    made Optional, and the endpoint sends `payload.model_dump(
    #    exclude_none=True)` as `new_attrs` — a partial diff by construction
    #    (renaming just `nombre` must not require resending `email`,
    #    `telefono`, etc.). Before this fix, this function used `new_attrs`
    #    as the COMPLETE new row verbatim, silently NULLing every business
    #    column the caller omitted — confirmed live on `clientes`: a
    #    PUT {"nombre": "..."} nulled `numero_identificacion` and
    #    `tipo_identificador` on the new open version. Beyond plain data
    #    loss, a NULLed natural-key column breaks `identity_reconciler`
    #    (D17) for every subsequent cloud_to_branch/bidirectional sync of
    #    that row, and the corruption then replicates to every other node.
    #
    #    The remote-replication caller (`sync.motor.apply_row`, via
    #    `SyncMotor` push/pull) is unaffected: its `new_attrs` always
    #    originates from the origin node's own `to_jsonb(NEW)` trigger
    #    payload, which already carries every business column — merging
    #    with the destination's current row there is a no-op (every key
    #    `new_attrs` needs is already present and wins the merge).
    carried_forward: dict[str, Any] = {}
    if current_uuid is not None:
        result = await session.execute(
            select(model_cls).where(
                model_cls.uuid == current_uuid,
                model_cls.vigente_hasta.is_(None),
            )
        )
        current_row = result.scalar_one_or_none()
        if current_row is None:
            raise RowNotFoundError(
                f"no active row in {model_cls.__tablename__} for uuid={current_uuid}"
            )
        carried_forward = {
            column.name: getattr(current_row, column.name)
            for column in sa_inspect(model_cls).columns
            if column.name not in _RESERVED_COLUMNS
        }
        await session.execute(
            update(model_cls)
            .where(
                model_cls.uuid == current_uuid,
                model_cls.vigente_hasta.is_(None),
            )
            .values(
                vigente_hasta=now,
                estado="inactivo",
            )
        )

    merged_attrs: dict[str, Any] = {**carried_forward, **new_attrs}

    # 2. Build the new row
    payload: dict[str, Any] = {
        "vigente_desde": now,
        "vigente_hasta": None,
        "estado": "activo",
        "created_at": now,
        "created_by": actor_uuid,
        **merged_attrs,
    }
    new_row = model_cls(**payload)
    session.add(new_row)
    # Flush NOW (still same TX, nothing committed) so ``new_row.uuid`` is
    # populated before the log-row branch below reads it, and so that
    # branch's own query (``hash_chain.append`` -> ``_read_prior_hash``)
    # does not have to rely on SQLAlchemy's autoflush to persist this row
    # first — autoflush-triggered-by-SELECT does not reliably postfetch a
    # server-generated PK for every model in this codebase (observed with
    # ``Usuarios``, whose ``uuid`` column re-declaration leaves no
    # ORM-visible default; discovered while wiring PR6's genesis bootstrap).
    await session.flush()

    # 3. Log row — extends the SHA-256 hash chain (PR6, REQ-16 + REQ-X4).
    #    A plain ``LogTransaccional(...)`` + ``session.add()`` (the PR2-era
    #    stub this replaces) leaves ``hash_anterior``/``hash_actual`` NULL
    #    client-side, relying entirely on the DB trigger
    #    ``fn_extend_hash_chain()`` to compute them — which has NO genesis
    #    -row bootstrap of its own (see ``repo/hash_chain.py``), so the
    #    very first ``log_transaccional`` row for any ``uuid_sucursal`` this
    #    helper had never seen before raised ``HASH_CHAIN_INTEGRITY_
    #    VIOLATION: no genesis row``. Routing through ``repo.hash_chain.
    #    append`` (the SAME primitive ``repo.event.record_event`` already
    #    uses for its own log row) both extends the chain in Python and
    #    transparently bootstraps that genesis row on first use.
    if log_tx:
        # Lazily import to avoid module-load-time circulars.
        from ..models.A.log_transaccional import LogTransaccional
        from . import hash_chain

        log_attrs: dict[str, Any] = {
            "uuid_usuario": actor_uuid,
            "uuid_sucursal": merged_attrs.get("uuid_sucursal"),
            "accion": "actualizar" if current_uuid is not None else "crear",
            "tabla_afectada": model_cls.__tablename__,
            "uuid_registro_afectado": getattr(new_row, "uuid", None),
            "timestamp_evento": now,
        }

        await hash_chain.append(
            session,
            LogTransaccional,
            log_attrs,
            actor_uuid=actor_uuid,
        )

    return new_row


async def close_only(
    session: AsyncSession,
    model_cls: type[T],
    uuid: uuid_lib.UUID,
    *,
    actor_uuid: uuid_lib.UUID,
) -> None:
    """Close an active ``[V]`` row with NO replacement version.

    Same guarded ``UPDATE`` as :func:`close_and_insert`'s step 1, exposed on
    its own for a corrective/administrative deactivation (e.g. collapsing an
    erroneous duplicate) where a paired new version would be wrong — unlike
    a real business update, there is no new state to insert.

    Args:
        session: Active ``AsyncSession`` (caller commits).
        model_cls: The ``[V]`` ORM class to operate on.
        uuid: The active row to close.
        actor_uuid: JWT subject (the writer of the change) — unused today
            (no ``[V]`` table carries a "closed_by" column) but required for
            signature symmetry with :func:`close_and_insert` and to keep the
            call site auditable if that column is ever added.

    Raises:
        RowNotFoundError: ``uuid`` doesn't match any currently-active row.
    """
    _ = actor_uuid
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await session.execute(
        update(model_cls)
        .where(
            model_cls.uuid == uuid,
            model_cls.vigente_hasta.is_(None),
        )
        .values(
            vigente_hasta=now,
            estado="inactivo",
        )
    )
    if result.rowcount == 0:
        raise RowNotFoundError(f"no active row in {model_cls.__tablename__} for uuid={uuid}")


async def current_version(
    session: AsyncSession,
    model_cls: type[T],
    uuid: uuid_lib.UUID,
) -> T | None:
    """Return the active row for ``uuid`` (vigente_hasta IS NULL), or None."""
    result = await session.execute(
        select(model_cls).where(
            model_cls.uuid == uuid,
            model_cls.vigente_hasta.is_(None),
        )
    )
    return result.scalar_one_or_none()


__all__ = [
    "VersioningError",
    "RowNotFoundError",
    "close_and_insert",
    "close_only",
    "current_version",
]
