"""Sucursal-specific repository helpers.

The FK propagation logic lives here so ``repo.versioned.close_and_insert``
does not need to import Sucursal directly (would be a circular import).

WHY THIS MODULE EXISTS
----------------------
``prod.sucursal`` is the only ``[V]`` table in the project whose PK
regeneration on bi-temporal close+insert creates user-visible breakage.
See migration 0061 docstring for the full defect description.

When the admin PUTs a Sucursal, ``close_and_insert`` produces a new
``uuid`` for the row that replaces the closed one. The 48 FK columns
pointing to ``prod.sucursal`` continue to hold the OLD ``uuid``. After
the migration runs once to repair existing data, this helper propagates
the new ``uuid`` to the 8 FK tables the admin explicitly interacts with
(``usuarios_sucursal`` drives the picker's ``sucursales_permitidas``
filter; the others drive other admin CRUD screens). The 40+ operational
FKs (``ingreso``, ``salidas``, ``facturas``, etc.) are out of scope here --
their closed-version ``prod.sucursal`` row still exists, so the FK is
satisfied; only the JOIN-vs-``vigente_hasta IS NULL`` semantics need the
separate fix.

CALL SITE
---------
Invoked from ``repo.versioned.close_and_insert`` immediately after the
``session.flush()`` that populates ``new_row.uuid``. Both branches
(local admin edit AND sync apply of a cloud Sucursal change) get
correct propagation because they share the same code path.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Same 7 tables as the one-shot data migration; same rationale.
# Keep this list in sync with ``0061_repair_sucursal_fk_chain.py::_FK_TABLES``.
# ``pairing_tokens`` is intentionally EXCLUDED: it is ``[A]`` (append-only)
# per AGENTS.md §1 audit-first canon, and UPDATE is blocked at the DB
# level. Pairing tokens are a forward-pinned issue, not a fix-on-edit
# one -- see the migration docstring for the full reasoning.
_FK_TABLES: tuple[tuple[str, str], ...] = (
    ("prod", "usuarios_sucursal"),
    ("prod", "tarifas_sucursal"),
    ("prod", "cantidad_vehiculos_sucursal"),
    ("prod", "configuracion_tolerancias"),
    ("prod", "configuracion_seguridad"),
    ("prod", "resolucion_facturacion"),
    ("prod", "subscripciones_cliente"),
)


async def propagate_uuid_to_fks(
    session: AsyncSession,
    old_uuid: uuid_lib.UUID,
    new_uuid: uuid_lib.UUID,
) -> None:
    """Repoint ``uuid_sucursal = old_uuid`` to ``new_uuid`` in the 7
    admin-facing FK tables.

    Runs inside the same TX as the Sucursal close+insert (no commit here).
    Idempotent: when no FK row references ``old_uuid`` (the typical case
    after the very first edit of a branch), the UPDATE matches 0 rows
    and we exit cleanly.

    ``prod.sucursal`` is NOT in the FK table list -- it has the
    ``uuid_tipo_sucursal`` FK to ``prod.tipo_sucursal`` (different column),
    and ``uuid_empresa`` FK to ``prod.empresa`` (different column),
    neither of which is impacted by a Sucursal UUID regeneration.
    """
    if old_uuid == new_uuid:
        return
    for schema, table in _FK_TABLES:
        qualified = f"{schema}.{table}"
        await session.execute(
            text(
                f"UPDATE {qualified} "
                f"SET uuid_sucursal = :new_uuid "
                f"WHERE uuid_sucursal = :old_uuid"
            ),
            {"new_uuid": new_uuid, "old_uuid": old_uuid},
        )


__all__ = ["propagate_uuid_to_fks"]
