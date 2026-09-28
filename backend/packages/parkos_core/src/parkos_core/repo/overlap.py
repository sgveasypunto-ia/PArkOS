"""repo/overlap.py — bi-temporal overlap guard for [V] resources.

PR-C business invariant: when opening a new version of a [V] row
(``tarifas_sucursal``, ``cantidad_vehiculos_sucursal``, etc.), the
resulting bi-temporal window MUST NOT overlap any other open window for
the same business identity. UK01 in the schema is on
``(uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, vigente_desde)``
for tarifas and ``(uuid_sucursal, uuid_tipo_vehiculo, vigente_desde)``
for cantidad — UK01 prevents two rows with the SAME ``vigente_desde``
but does NOT prevent a window that starts before the old one ends.

This helper closes that gap at the API layer. It is NOT a substitute
for UK01; the two are complementary:

  * UK01 (schema): prevents duplicate ``vigente_desde`` (deterministic
    INSERT collision).
  * overlap guard (here): prevents ``vigente_desde < viejo.vigente_hasta``
    windows on the same business key.

Defence in depth: a migration could add a CHECK constraint
``vigente_desde >= COALESCE(vigente_hasta, vigente_desde)`` to back
this at the DB layer, but the application-layer check is the canonical
source of truth — the error message is operator-readable and the
business reason is logged via ``log_transaccional``.

NULL semantics: every business column (``uuid_sucursal``,
``uuid_tipo_vehiculo``, ``uuid_tipo_tarifa``) is nullable. We compare
each with ``IS NOT DISTINCT FROM`` semantics (NULL = NULL). The SQL is
written with explicit ``(c = :v OR (c IS NULL AND :v IS NULL))`` rather
than the SQL ``IS NOT DISTINCT FROM`` operator because asyncpg returns
a cleaner parameter mapping for the former and tests assert on the
bound params.
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class OverlapError(Exception):
    """Raised when a new bi-temporal window would overlap an existing one.

    Carries enough context for the handler to build a 409 with the
    offending row's ``uuid``, ``vigente_desde``, and ``vigente_hasta``
    so the operator can pick a non-overlapping window.
    """

    def __init__(
        self,
        *,
        resource: str,
        conflicting_uuid: uuid_lib.UUID,
        conflicting_vigente_desde,
        conflicting_vigente_hasta,
    ) -> None:
        self.resource = resource
        self.conflicting_uuid = conflicting_uuid
        self.conflicting_vigente_desde = conflicting_vigente_desde
        self.conflicting_vigente_hasta = conflicting_vigente_hasta
        super().__init__(
            f"{resource}: new version overlaps open row "
            f"uuid={conflicting_uuid} vigente_desde={conflicting_vigente_desde} "
            f"vigente_hasta={conflicting_vigente_hasta}"
        )


class SucursalInmutableError(Exception):
    """Raised when a PUT payload tries to change the row's sucursal.

    The tarifa / cupo belongs to the branch that created it. Moving a
    rate or capacity to a different branch would invalidate every
    audit trail that already references the original branch. The
    operator should create a new version on the destination branch
    instead — explicitly, never implicitly.
    """

    def __init__(
        self,
        *,
        resource: str,
        uuid: uuid_lib.UUID,
        existing_sucursal: uuid_lib.UUID,
        attempted_sucursal: uuid_lib.UUID,
    ) -> None:
        self.resource = resource
        self.uuid = uuid
        self.existing_sucursal = existing_sucursal
        self.attempted_sucursal = attempted_sucursal
        super().__init__(
            f"{resource} uuid={uuid}: cannot change uuid_sucursal from "
            f"{existing_sucursal} to {attempted_sucursal}"
        )


@dataclass(frozen=True)
class _Key:
    """Business-identity columns for the overlap guard.

    All three are nullable in the schema; ``None`` is treated as
    ``NULL`` (matching rows where the column is also NULL).
    """

    uuid_sucursal: uuid_lib.UUID | None
    uuid_tipo_vehiculo: uuid_lib.UUID | None
    uuid_tipo_tarifa: uuid_lib.UUID | None  # tarifas only; pass None for cupos


# ---------------------------------------------------------------------------
# SQL builders
# ---------------------------------------------------------------------------
#
# The overlap predicate has two variants because the tarifas table has
# three business keys and the cantidad table has two. We pass them as a
# single SQL with a NULL-aware equality test on each column. The
# ``exclude_uuid`` lets the caller exclude the row being PUT'd (whose
# own current version is still open during the transaction and would
# otherwise always self-overlap).

_OVERLAP_SQL = """
SELECT uuid, vigente_desde, vigente_hasta
FROM {table}
WHERE vigente_hasta IS NULL
  AND (uuid_sucursal = :sucursal OR (uuid_sucursal IS NULL AND :sucursal IS NULL))
  AND (uuid_tipo_vehiculo = :tipo_vehiculo
       OR (uuid_tipo_vehiculo IS NULL AND :tipo_vehiculo IS NULL))
  AND (:tipo_tarifa_check = 0
       OR (uuid_tipo_tarifa = :tipo_tarifa
           OR (uuid_tipo_tarifa IS NULL AND :tipo_tarifa IS NULL)))
  AND uuid <> COALESCE(:exclude_uuid, '00000000-0000-0000-0000-000000000000'::uuid)
  AND vigente_desde < :nueva_hasta
  AND (vigente_hasta IS NULL OR vigente_hasta > :nueva_desde)
LIMIT 1
"""


async def assert_no_overlap(
    session: AsyncSession,
    *,
    table: str,
    resource: str,
    key: _Key,
    nueva_vigente_desde,
    nueva_vigente_hasta,
    exclude_uuid: uuid_lib.UUID | None = None,
) -> None:
    """Raise :class:`OverlapError` if any open row on ``table`` overlaps.

    Args:
        session: Async SQLAlchemy session. Must NOT have an uncommitted
            new row yet (the caller invokes this BEFORE ``close_and_insert``
            opens the new version, so the only open rows in the table
            for this business key are the pre-existing ones).
        table: Schema-qualified table name (``"prod.tarifas_sucursal"``,
            ``"prod.cantidad_vehiculos_sucursal"``).
        resource: Human-readable resource name for the error message
            (``"tarifas-sucursal"``, ``"cantidad-vehiculos-sucursal"``).
        key: Business-identity columns. All nullable.
        nueva_vigente_desde: When the new version opens. Typically
            ``datetime.now(UTC)`` or a future-dated client request.
        nueva_vigente_hasta: When the new version closes (``None`` for
            open-ended; pass a sentinel if your caller requires it).
        exclude_uuid: UUID of the row whose own current version we want
            to ignore (the PUT target). ``None`` for POST.

    The open-window overlap definition:
        other.vigente_desde < nueva_hasta AND (other.vigente_hasta IS NULL OR other.vigente_hasta > nueva_desde)

    That is strict-overlap (the two intervals share at least one
    instant). Adjacent windows (``other.vigente_hasta == nueva_desde``)
    are NOT overlaps — the new version opens exactly when the old one
    closes, which is the close+insert Carril B contract.
    """
    # The SQL uses a flag (``tipo_tarifa_check``) so the SAME statement
    # can serve both tablas — tarifas with the tipo_tarifa column and
    # cupos without it (``tipo_tarifa_check=1`` vs ``0``). SQLAlchemy's
    # parameter binding does not support dynamic table / column lists
    # safely; a single static statement is the right shape.
    sql = _OVERLAP_SQL.format(table=table)
    params: dict[str, object] = {
        "sucursal": key.uuid_sucursal,
        "tipo_vehiculo": key.uuid_tipo_vehiculo,
        "tipo_tarifa": key.uuid_tipo_tarifa,
        "tipo_tarifa_check": 1 if key.uuid_tipo_tarifa is not None else 0,
        "nueva_desde": nueva_vigente_desde,
        "nueva_hasta": nueva_vigente_hasta,
        "exclude_uuid": exclude_uuid,
    }
    row = (await session.execute(text(sql), params)).first()
    if row is not None:
        raise OverlapError(
            resource=resource,
            conflicting_uuid=row.uuid,
            conflicting_vigente_desde=row.vigente_desde,
            conflicting_vigente_hasta=row.vigente_hasta,
        )


def assert_sucursal_inmutable(
    *,
    resource: str,
    uuid: uuid_lib.UUID,
    existing_sucursal: uuid_lib.UUID | None,
    payload_sucursal: uuid_lib.UUID | None,
) -> None:
    """Raise :class:`SucursalInmutableError` if the payload tries to
    change the row's ``uuid_sucursal``.

    The check is permissive on ``None`` payload (carry-forward from the
    existing row is allowed via the factory's column-merge) but strict
    on a real value that does not match the existing one.

    A ``None`` existing sucursal is rare (schema allows it but the
    factory never produces it because POST always sets it) — handle it
    as "any payload is allowed" since there is no constraint to violate.
    """
    if existing_sucursal is None:
        return
    if payload_sucursal is None:
        return
    if payload_sucursal != existing_sucursal:
        raise SucursalInmutableError(
            resource=resource,
            uuid=uuid,
            existing_sucursal=existing_sucursal,
            attempted_sucursal=payload_sucursal,
        )


__all__ = [
    "OverlapError",
    "SucursalInmutableError",
    "assert_no_overlap",
    "assert_sucursal_inmutable",
]
