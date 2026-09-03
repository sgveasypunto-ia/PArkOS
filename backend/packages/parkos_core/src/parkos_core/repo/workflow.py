"""Workflow state-machine helpers for ``[L-W]`` tables (REQ-21, REQ-X9, REQ-OP-08).

Each ``[L-W]`` table has its own state machine (see :data:`STATE_MACHINES`).
The transition writer :func:`append_transition` is the ONLY legal write
path on ``[L-W]`` classes outside :mod:`repo.versioned`. Direct
``UPDATE``/``DELETE`` on ``[L-W]`` rows is forbidden by the AST test
``tests/static/test_no_raw_dml_on_lw_tables.py`` (T-PR6-14).

Defense in depth (AGENTS.md §3, design §4):

  - API layer: ``make_router`` exposes only ``POST`` (transition) and
    ``GET`` (read chain tip); no UPDATE/DELETE endpoint.
  - ORM layer: this module is the single mutation surface; the AST
    marker ``__workflow_only__`` on :class:`WorkflowBase` is read by
    the static test.
  - DB layer: not enforced here \u2014 the [L-W] tables do not carry
    REVOKE on UPDATE because legitimate business operations write
    them via this helper; the AST + ORM layer is the gate.

Three public surfaces:

  - :data:`STATE_MACHINES` \u2014 per-table ``{from_estado: [allowed_to_estados]}``.
  - :func:`append_transition` \u2014 append a new chain row linked to the parent.
  - :func:`read_chain_tip` \u2014 walk the ``uuid_xxx_padre`` chain from a
    root and return the tip per the REQ-X9 tie-break:
    ``(max(timestamp_evento), max(chain_length), lex(uuid))``.
  - :func:`polymorphic_row_exists` \u2014 REQ-OP-08, REQ-23-W-POLYMORPHIC-FK.
    Validates ``(tipo_reclamable, uuid_reclamable)`` against the right
    polymorphic target table.
"""

from __future__ import annotations

import importlib
import uuid as uuid_lib
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base import WorkflowBase

T = TypeVar("T", bound=WorkflowBase)


class WorkflowError(Exception):
    """Base class for workflow operation failures."""


class IllegalTransitionError(WorkflowError):
    """Raised when ``append_transition`` would violate :data:`STATE_MACHINES`."""


class ChainNotFoundError(WorkflowError):
    """Raised when ``read_chain_tip`` cannot resolve a root or parent row."""


class UnknownPolymorphicTypeError(WorkflowError):
    """Raised when ``polymorphic_row_exists`` gets an unknown ``tipo_reclamable``."""


# Per-table state machines (REQ-21).
# Each entry: {from_estado: [allowed_to_estados]} \u2014 terminal states map to [].
# Keys MUST match ``__tablename__`` on the corresponding ORM class.
STATE_MACHINES: dict[str, dict[str, list[str]]] = {
    "reimpresion_ticket": {
        "solicitada": ["autorizada", "rechazada"],
        "autorizada": ["ejecutada", "rechazada"],
        "ejecutada": [],  # terminal
        "rechazada": [],  # terminal
    },
    "anulaciones": {
        "iniciada": ["autorizada", "rechazada"],
        "autorizada": ["ejecutada", "rechazada"],
        "ejecutada": [],  # terminal
        "rechazada": [],  # terminal
    },
    "reclamos": {
        "recibido": ["en_investigacion", "rechazado"],
        "en_investigacion": ["resuelto", "rechazado"],
        "resuelto": [],  # terminal
        "rechazado": [],  # terminal
    },
    "alerta": {
        "activa": ["descartada", "resuelta"],
        # ``descartada`` is admin-only (T-PR6-08 enforces via JWT role).
        "descartada": [],  # terminal
        "resuelta": [],  # terminal (operator path)
    },
    "envio_dian": {
        "pendiente": ["enviado"],
        "enviado": ["ack", "error"],
        "ack": [],  # terminal
        "error": [],  # terminal (retry-to-pendiente out of scope)
    },
    "validacion_evento": {
        "pendiente": ["validado", "rechazado"],
        "validado": [],  # terminal
        "rechazado": [],  # terminal
    },
}


def _now_naive() -> datetime:
    """Naive UTC ``datetime`` — matches ``repo/versioned.py`` style."""
    return datetime.now(UTC).replace(tzinfo=None)


async def append_transition(  # noqa: UP047 (TypeVar style — matches repo/versioned.py)
    session: AsyncSession,
    model_cls: type[T],
    *,
    actor_uuid: uuid_lib.UUID,
    new_attrs: dict[str, Any],
    parent_uuid: uuid_lib.UUID | None = None,
    parent_fk_column: str | None = None,
    log_tx: bool = True,
) -> T:
    """Append a workflow transition row.

    Each ``[L-W]`` table carries a self-FK column (``uuid_xxx_padre``)
    linking sequential transitions in a chain. This helper:

    1. Validates ``model_cls`` is a :class:`WorkflowBase` subclass and
       has a :data:`STATE_MACHINES` entry.
    2. If ``parent_uuid`` is provided, fetches the parent row, looks
       up the parent's ``estado``, and validates the transition
       ``parent.estado -> new_attrs['estado']`` is legal. Raises
       :class:`IllegalTransitionError` otherwise; raises
       :class:`ChainNotFoundError` if the parent row is missing.
    3. Inserts a new row with ``new_attrs`` (plus ``parent_fk_column``=
       ``parent_uuid`` when both are provided) plus server-set
       ``created_at``/``created_by``.
    4. Optionally appends a ``log_transaccional`` row in the same TX.

    The caller is responsible for committing the session. The new row's
    ``uuid`` is server-generated by :class:`IdMixin`.

    Args:
        session: Active :class:`AsyncSession` (caller commits).
        model_cls: The ``[L-W]`` ORM class (e.g. ``Anulaciones``).
        actor_uuid: JWT subject.
        new_attrs: Business attributes for the new transition. MUST
            include ``estado`` (the new state machine value).
        parent_uuid: UUID of the previous row in the chain. ``None``
            only for the root row (first transition).
        parent_fk_column: The self-FK column name on this table
            (e.g. ``uuid_reimpresion_padre``, ``uuid_anulacion_padre``,
            ``uuid_reclamo_padre``, ``uuid_alerta_padre``,
            ``uuid_envio_padre``, ``uuid_validacion_padre``).
            Required when ``parent_uuid`` is provided.
        log_tx: Whether to also append a ``log_transaccional`` row in
            the same TX (default ``True``).

    Returns:
        The newly inserted workflow row. ``session.refresh()`` is the
        caller's responsibility.

    Raises:
        IllegalTransitionError: The transition is not allowed by
            :data:`STATE_MACHINES` for the table.
        ChainNotFoundError: ``parent_uuid`` does not match any row.
        WorkflowError: ``model_cls`` is not a :class:`WorkflowBase`
            subclass, has no :data:`STATE_MACHINES` entry, is missing
            ``estado`` in ``new_attrs``, or is invoked with
            ``parent_uuid`` but no ``parent_fk_column``.
    """
    if not (isinstance(model_cls, type) and issubclass(model_cls, WorkflowBase)):
        raise WorkflowError(
            f"append_transition requires a WorkflowBase subclass; got {model_cls!r}"
        )

    table = model_cls.__tablename__
    state_machine = STATE_MACHINES.get(table)
    if state_machine is None:
        raise WorkflowError(f"No STATE_MACHINES entry for table {table!r}")

    new_estado = new_attrs.get("estado")
    if new_estado is None:
        raise WorkflowError(f"new_attrs MUST include 'estado' for [{table}]")

    if parent_uuid is not None:
        if not parent_fk_column:
            raise WorkflowError(
                f"parent_fk_column is required when parent_uuid is given (table {table!r})"
            )

        # 1. Look up the parent row and read its estado.
        parent = (
            await session.execute(select(model_cls).where(model_cls.uuid == parent_uuid))
        ).scalar_one_or_none()
        if parent is None:
            raise ChainNotFoundError(f"parent row {parent_uuid} not found in {table}")
        # ``estado`` is re-declared on each [L-W] concrete subclass; LSP can't
        # see it through the generic WorkflowBase bound, so silence attr-defined.
        parent_estado = parent.estado  # type: ignore[attr-defined]

        # 2. Validate the transition is legal.
        allowed = state_machine.get(parent_estado, [])
        if new_estado not in allowed:
            raise IllegalTransitionError(
                f"Illegal transition for {table}: "
                f"{parent_estado!r} -> {new_estado!r}. "
                f"Allowed from {parent_estado!r}: {allowed}"
            )

    # 3. Build the new row. Wire the parent FK if provided; do not let
    #    the caller's ``new_attrs`` override it (parent FK is server-set
    #    by this helper, not the API client).
    insert_attrs = dict(new_attrs)
    if parent_uuid is not None and parent_fk_column:
        insert_attrs[parent_fk_column] = parent_uuid

    new_row = model_cls(
        **insert_attrs,
        created_at=_now_naive(),
        created_by=actor_uuid,
    )
    session.add(new_row)

    # 4. Co-transactional audit log row (PR2 stub; full hash chain in PR3+).
    if log_tx:
        # Lazy import: avoids module-load-time circulars.
        from ..models.A.log_transaccional import LogTransaccional

        log_row = LogTransaccional(
            uuid_usuario=actor_uuid,
            uuid_sucursal=new_attrs.get("uuid_sucursal"),
            accion="crear",
            tabla_afectada=table,
            uuid_registro_afectado=getattr(new_row, "uuid", None),
            timestamp_evento=_now_naive(),
        )
        session.add(log_row)

    return new_row


async def read_chain_tip(  # noqa: UP047 (TypeVar style — matches repo/versioned.py)
    session: AsyncSession,
    model_cls: type[T],
    *,
    root_uuid: uuid_lib.UUID,
    parent_fk_column: str,
) -> dict[str, Any]:
    """Return the chain tip for ``root_uuid`` per REQ-X9 tie-break.

    The chain forms a tree (a root can have multiple children via the
    ``parent_fk_column`` self-FK). The "tip" is the row selected by:

    1. Latest ``timestamp_evento``.
    2. If multiple rows share the latest timestamp, the one with the
       longest chain (deepest descendant).
    3. If still tied, lexicographically largest ``uuid``.

    Implementation: BFS from ``root_uuid`` collecting every reachable
    row, then sort by the three-key tie-break.

    Args:
        session: Active :class:`AsyncSession`.
        model_cls: The ``[L-W]`` ORM class.
        root_uuid: The root uuid of the chain (the first row; its
            ``parent_fk_column`` is NULL).
        parent_fk_column: The self-FK column name on this table
            (e.g. ``uuid_reimpresion_padre``).

    Returns:
        ``{uuid_root, uuid_actual, estado, timestamp_evento, chain_length}``.

    Raises:
        ChainNotFoundError: No row exists for ``root_uuid``.
        WorkflowError: ``model_cls`` is not a :class:`WorkflowBase`
            subclass.
    """
    if not (isinstance(model_cls, type) and issubclass(model_cls, WorkflowBase)):
        raise WorkflowError(f"read_chain_tip requires a WorkflowBase subclass; got {model_cls!r}")

    # Validate root exists, then BFS to collect the whole reachable tree.
    root_row = (
        await session.execute(select(model_cls).where(model_cls.uuid == root_uuid))
    ).scalar_one_or_none()
    if root_row is None:
        raise ChainNotFoundError(f"root row {root_uuid} not found in {model_cls.__tablename__!r}")

    parent_col = getattr(model_cls, parent_fk_column)

    visited: set[uuid_lib.UUID] = set()
    queue: list[uuid_lib.UUID] = [root_uuid]
    rows_by_uuid: dict[uuid_lib.UUID, Any] = {}

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        row = (
            await session.execute(select(model_cls).where(model_cls.uuid == current))
        ).scalar_one_or_none()
        if row is None:
            continue
        rows_by_uuid[row.uuid] = row

        children = (
            (await session.execute(select(model_cls).where(parent_col == row.uuid))).scalars().all()
        )
        for child in children:
            if child.uuid not in visited:
                queue.append(child.uuid)

    # Chain length = number of ancestors + 1 (count the row itself).
    def chain_length(target: Any) -> int:
        depth = 0
        current = target
        seen: set[uuid_lib.UUID] = set()
        while True:
            parent_uuid_val = getattr(current, parent_fk_column)
            if parent_uuid_val is None or parent_uuid_val in seen:
                return depth + 1
            seen.add(current.uuid)
            parent = rows_by_uuid.get(parent_uuid_val)
            if parent is None or parent == current:
                return depth + 1
            current = parent
            depth += 1

    all_rows = list(rows_by_uuid.values())
    # Naive sentinel matches the column type ``DateTime(timezone=False)``.
    # We compare naive-to-naive only; a tz-aware sentinel would TypeError
    # against the naive column values.
    _NAIVE_SENTINEL = datetime(1, 1, 1)  # noqa: DTZ001 (sentinel must be naive)
    sorted_rows = sorted(
        all_rows,
        key=lambda r: (
            r.timestamp_evento or _NAIVE_SENTINEL,
            -chain_length(r),  # longest first -> negate for ascending sort
            str(r.uuid),
        ),
        reverse=True,
    )
    tip = sorted_rows[0]
    return {
        "uuid_root": root_uuid,
        "uuid_actual": tip.uuid,
        "estado": tip.estado,  # type: ignore[attr-defined]
        "timestamp_evento": tip.timestamp_evento,  # type: ignore[attr-defined]
        "chain_length": chain_length(tip),
    }


# Polymorphic FK target registry (REQ-OP-08, REQ-23-W-POLYMORPHIC-FK).
# Resolves ``tipo_reclamable`` to an ORM class. We use lazy import via
# importlib so the module stays importable even when one of the target
# models (notably ``Salidas``) has not yet shipped \u2014 the validator
# fails with a clear ``ImportError`` at call-time, not at module-load.
_POLYMORPHIC_TARGETS: dict[str, str] = {
    "ingreso": "parkos_core.models.L_E.ingreso.Ingreso",
    "factura": "parkos_core.models.L_E.facturas.Facturas",
    "salida": "parkos_core.models.A.salidas.Salidas",
}


def _resolve_polymorphic_target(tipo_reclamable: str) -> type:
    """Lazy import the polymorphic FK target class.

    Args:
        tipo_reclamable: One of ``'ingreso'``, ``'factura'``, ``'salida'``.

    Returns:
        The ORM class for the requested target.

    Raises:
        UnknownPolymorphicTypeError: ``tipo_reclamable`` not in the registry.
        ImportError: The target class has not been shipped yet (propagated
            from the deferred import).
    """
    fq_name = _POLYMORPHIC_TARGETS.get(tipo_reclamable)
    if fq_name is None:
        raise UnknownPolymorphicTypeError(
            f"Unknown tipo_reclamable: {tipo_reclamable!r}. "
            f"Allowed: {sorted(_POLYMORPHIC_TARGETS.keys())}"
        )
    module_path, _, class_name = fq_name.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


async def polymorphic_row_exists(
    session: AsyncSession,
    *,
    tipo_reclamable: str,
    uuid_reclamable: uuid_lib.UUID,
) -> bool:
    """Validate that ``(tipo_reclamable, uuid_reclamable)`` references a real row.

    REQ-OP-08 + REQ-23-W-POLYMORPHIC-FK. Used by the ``ReclamoCreate``
    Pydantic validator (T-PR6-08) to refuse claims that point at a
    non-existent ``ingreso``/``salida``/``factura`` row.

    Args:
        session: Active :class:`AsyncSession`.
        tipo_reclamable: One of ``'ingreso'``, ``'factura'``, ``'salida'``.
        uuid_reclamable: The uuid of the target row.

    Returns:
        ``True`` if a row with ``uuid == uuid_reclamable`` exists in the
        target table, ``False`` otherwise.

    Raises:
        UnknownPolymorphicTypeError: ``tipo_reclamable`` is not in
            :data:`_POLYMORPHIC_TARGETS`.
        ImportError: The target ORM class has not yet shipped.
    """
    target_cls = _resolve_polymorphic_target(tipo_reclamable)
    row = (
        await session.execute(select(target_cls).where(target_cls.uuid == uuid_reclamable))
    ).scalar_one_or_none()
    return row is not None


__all__ = [
    "STATE_MACHINES",
    "ChainNotFoundError",
    "IllegalTransitionError",
    "UnknownPolymorphicTypeError",
    "WorkflowError",
    "append_transition",
    "polymorphic_row_exists",
    "read_chain_tip",
]
