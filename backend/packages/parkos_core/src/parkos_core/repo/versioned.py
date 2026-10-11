"""Bi-temporal close+insert helper for [V] tables (design §4.1).

REQ-04, REQ-05:
1. UPDATE current SET vigente_hasta = NOW(), estado = 'inactivo' WHERE uuid = :cu
2. INSERT new row with vigente_desde = NOW(), vigente_hasta = NULL, estado = 'activo'
3. (PR2) Write a ``log_transaccional`` row in the same TX

Both operations happen in the same transaction. The caller is responsible for
``session.commit()``.

UUID REGENERATION (BIO-TEMPORAL GOTCHA)
----------------------------------------
The PK of every ``[V]`` table is single-column ``uuid``; step 2 INSERTs
without specifying ``uuid`` so the server-default ``gen_random_uuid()``
mints a NEW one. **The business UUID of a branch does NOT survive
across edits.** This is consistent with the sync path
(``sync.motor.apply_row``) but it has a sharp edge: every FK column
pointing at the [V] row carries the OLD ``uuid``. After the first edit,
those FKs reference a closed (``vigente_hasta IS NOT NULL``) row.

Two callers suffer immediately:

1. The picker (``admin_views.list_sucursales`` filters by
   ``sucursales_permitidas`` which the JWT built from the OLD UUID).
   The admin sees the branch disappear after editing it.
2. Operational JOINs on the closed UUID that filter
   ``s.vigente_hasta IS NULL`` silently drop rows.

For ``Sucursal`` the helper repoints the admin-facing FK columns
in the same TX right after the INSERT flush -- see the post-flush hook
below. Migration 0061 (``0061_repair_sucursal_fk_chain.py``) repairs
the pre-existing gap on already-edited branches. Other ``[V]`` tables
are intentionally NOT propagated today because the user-facing cost
hasn't surfaced; the hook is opt-in via ``model_cls.__tablename__`` so
adding more tables is one line of work when needed.

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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base import VersionedBase

T = TypeVar("T", bound=VersionedBase)

# Columns close_and_insert always recomputes itself (step 2) — never carried
# forward from the row being closed, even when present on the model.
_RESERVED_COLUMNS = frozenset(
    {"uuid", "vigente_desde", "vigente_hasta", "estado", "created_at", "created_by"}
)


def _extract_constraint_name(exc: IntegrityError) -> str | None:
    """Best-effort constraint name extraction from a SQLAlchemy IntegrityError.

    Driver-specific ``exc.orig`` shape varies across SQLAlchemy 2.0 +
    asyncpg + psycopg2 + aiosqlite. We try the cheap structured paths
    first, then fall back to a regex over the rendered error string --
    the last resort, but it's the only path that works on the live
    SQLAlchemy 2.0 + asyncpg stack used by the project's testcontainers
    tests (where the chain is
    ``asyncpg.UniqueViolationError`` → ``sqlalchemy.exc.IntegrityError``
    → another ``sqlalchemy.exc.IntegrityError`` -- the inner orig is
    NOT the asyncpg exception, so neither ``exc.orig.constraint_name``
    nor ``exc.orig.diag.constraint_name`` is populated).

    We never raise here -- the caller still gets the typed
    ``VersioningConflictError`` even if extraction fails.
    """
    import re

    orig = getattr(exc, "orig", None)
    if orig is not None:
        # 1) asyncpg / psycopg2: top-level attribute on the orig itself.
        name = getattr(orig, "constraint_name", None)
        if isinstance(name, str) and name:
            return name
        # 2) psycopg2 fallback: ``orig.diag.constraint_name`` (DBAPI DiagStruct).
        diag = getattr(orig, "diag", None)
        if diag is not None:
            diag_name = getattr(diag, "constraint_name", None)
            if isinstance(diag_name, str) and diag_name:
                return diag_name
    # 3) Last-resort regex over the rendered message. Postgres wires the
    # constraint name into the SQLSTATE error string verbatim:
    # ``duplicate key value violates unique constraint "usuarios_uk01"``
    # or ``insert or update on table ... violates foreign key
    # constraint "fk_tarifas_sucursal_uuid_tipo_vehiculo"``. Both carry
    # the constraint name between double quotes -- the project does
    # NOT use double-quoted identifiers in DDL, so the regex won't
    # false-positive on user data.
    match = re.search(r'(?:unique|foreign key|check|exclude) constraint "([^"]+)"', str(exc))
    if match is not None:
        return match.group(1)
    return None


class VersioningError(Exception):
    """Base class for versioned-table operation failures."""


class RowNotFoundError(VersioningError):
    """Raised when ``current_uuid`` does not match any row."""


class VersioningConflictError(VersioningError):
    """Raised when the DB rejects the new version with an ``IntegrityError``.

    The canonical case is a UK violation (e.g. two rows trying to share the
    same business key + ``vigente_desde``). ``close_and_insert`` flushes
    inside the same transaction the helper owns, so an upstream
    ``assert_no_overlap`` check that misses the edge (e.g. two POSTs racing
    on the same ``vigente_desde``) surfaces here as a typed exception
    instead of leaking an opaque 500 from FastAPI.

    Carries ``constraint_name`` when the underlying driver exposes it
    (asyncpg's ``exc.orig.diag.constraint_name``); ``None`` on drivers
    that don't (e.g. SQLite in unit tests, where the test mocks the
    ``IntegrityError`` directly).
    """

    def __init__(
        self,
        message: str,
        *,
        constraint_name: str | None = None,
        original: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.constraint_name = constraint_name
        self.original = original


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

    # Carril B fix: when the caller supplies an origin ``vigente_desde``
    # (remote sync apply of a [V] row — see ``identity_reconciler.forward``),
    # the new version opens at that valid time, so the row being closed must
    # end at the SAME boundary (no gap/overlap: closed row's
    # ``vigente_hasta`` == new row's ``vigente_desde``). Local writes (no
    # origin valid time) keep the historical ``now`` semantics unchanged.
    origin_valid_time = new_attrs.get("vigente_desde")
    close_boundary = origin_valid_time if origin_valid_time is not None else now

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
                vigente_hasta=close_boundary,
                estado="inactivo",
            )
        )

    # Drop validation-only schema fields that have no column on the model.
    # A Pydantic create/update schema may carry fields that exist purely for
    # cross-field validation and are never persisted (``ClientesCreate.dv``
    # for the NIT modulo-11 check is the canonical case -- ``prod.clientes``
    # has no ``dv`` column, and ``schemas/clientes.py`` says so explicitly).
    # Passing them straight into the declarative constructor raises
    # ``TypeError: '<field>' is an invalid keyword argument for <Model>``
    # from SQLAlchemy's ``_declarative_constructor``, which surfaced as a
    # bare 500 on ``POST /api/v1/clientes/clientes``. Filtering centrally
    # here protects every ``make_router``-mounted resource, not just the
    # ones whose repo already strips the field by hand
    # (``venta_suscripcion.py`` does ``{k: v for k, v in ... if k != "dv"}``).
    model_column_names = frozenset(
        column.name for column in sa_inspect(model_cls).columns
    )
    new_attrs = {k: v for k, v in new_attrs.items() if k in model_column_names}
    carried_forward = {k: v for k, v in carried_forward.items() if k in model_column_names}

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
    # branch's own query (``hash_chain.append`` -> ``_read_head``)
    # does not have to rely on SQLAlchemy's autoflush to persist this row
    # first — autoflush-triggered-by-SELECT does not reliably postfetch a
    # server-generated PK for every model in this codebase (observed with
    # ``Usuarios``, whose ``uuid`` column re-declaration leaves no
    # ORM-visible default; discovered while wiring PR6's genesis bootstrap).
    #
    # Centralized ``IntegrityError`` → ``VersioningConflictError`` mapping
    # (defense in depth, REQ-OPS canon). The upstream ``assert_no_overlap``
    # check in tarifa / cupos handlers is the FIRST line of defense; this
    # is the SECOND. Two POSTs racing on the same ``vigente_desde`` slip
    # past ``assert_no_overlap`` because the open-row check happens before
    # either INSERT, and the DB UK01 catches the loser. Without this
    # mapping, the loser surfaces as a bare 500 from FastAPI (raw
    # ``Internal Server Error`` body, no JSON). With it, the handler can
    # translate the typed exception into a 409 with the canonical
    # ``tarifa_overlap`` / ``cupo_overlap`` shape the FE already parses.
    try:
        await session.flush()
    except IntegrityError as exc:
        constraint_name = _extract_constraint_name(exc)
        raise VersioningConflictError(
            f"integrity error inserting new version into {model_cls.__tablename__}: {exc.orig}",
            constraint_name=constraint_name,
            original=exc,
        ) from exc

    # FK propagation hook. The PK of every ``[V]`` table is single-column
    # ``uuid``; bi-temporal close+insert regenerates it, leaving the 48
    # FKs to that table pointing at the OLD closed version. The admin
    # notices this as the picker dropping the branch (because
    # ``sucursales_permitidas`` was built from the OLD UUID), and as
    # JOIN queries on operational data silently missing rows.
    # ``close_and_insert`` regenerates ``uuid`` by design (see the
    # docstring at the top of this module); the FK propagation lives here
    # so the symptom doesn't leak to the user. See migration 0061 for
    # the data-repair counterpart and ``repo.sucursal`` for the rationale.
    # The hook fires only for ``Sucursal`` -- the one ``[V]`` table where
    # the PK regeneration is user-visible today. Other tables can opt in
    # by registering here as their FK surface grows.
    if current_uuid is not None and model_cls.__tablename__ == "sucursal":
        # Lazy import: ``repo.sucursal`` itself depends on nothing
        # model-side, but the dispatch table lives there to avoid growing
        # the versioned module's surface.
        from .sucursal import propagate_uuid_to_fks

        await propagate_uuid_to_fks(
            session,
            old_uuid=current_uuid,
            new_uuid=new_row.uuid,
        )

    # Same gotcha, ``usuarios`` side: the admin Usuario detail page's
    # Sucursales/Permisos tabs filter ``usuarios_sucursal`` /
    # ``permisos_usuario`` by ``uuid_usuario``, so those rows must
    # follow the user across every close+insert (Datos tab save,
    # password reset). See ``repo.admin_usuarios.
    # propagate_usuario_uuid_to_fks`` for the live defect this fixes.
    if current_uuid is not None and model_cls.__tablename__ == "usuarios":
        from .admin_usuarios import propagate_usuario_uuid_to_fks

        await propagate_usuario_uuid_to_fks(
            session,
            old_uuid=current_uuid,
            new_uuid=new_row.uuid,
        )

    # CREATE-side auto-assignment. Companion to the FK-propagation
    # hook above: when an admin POSTs a brand-new Sucursal (the
    # ``current_uuid is None`` branch), nothing repoints the creator's
    # ``sucursales_permitidas`` because nothing pointed at the row before
    # it existed. Without this, the picker drops the just-created branch
    # for the admin who created it -- exactly the "invisible branch"
    # reported 2026-09-29 on ``testTTTTTTTT``. The hook inserts an open
    # ``usuarios_sucursal`` row in the same TX so the next login rebuilds
    # ``sucursales_permitidas`` with the new UUID present. Idempotent on
    # UK violation (see ``repo.sucursal.assign_creator_to_new_sucursal``).
    # ``operador-`` issuers never reach here -- ``config_sucursal``
    # permission check at the endpoint rejects them with 403 first.
    if current_uuid is None and model_cls.__tablename__ == "sucursal":
        from .sucursal import assign_creator_to_new_sucursal

        await assign_creator_to_new_sucursal(
            session,
            admin_user_uuid=actor_uuid,
            sucursal_uuid=new_row.uuid,
            actor_uuid=actor_uuid,
        )

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
    "VersioningConflictError",
    "close_and_insert",
    "close_only",
    "current_version",
]
