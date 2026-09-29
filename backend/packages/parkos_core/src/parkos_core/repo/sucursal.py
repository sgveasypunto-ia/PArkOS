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

A second helper, ``assign_creator_to_new_sucursal``, covers the
complementary CREATE-side defect: when an admin POSTs a brand-new
Sucursal, the hook in ``close_and_insert`` inserts a ``usuarios_sucursal``
row granting the creator access -- otherwise the new branch is invisible
to the picker until the creator manually assigns themselves via the
``/admin/usuarios/{uuid}/sucursales`` endpoint.

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

# Model import is lazy (see the call site in ``close_and_insert`` and
# the module docstring) to avoid pulling the [V] model registry at
# module load time -- the helper runs in a post-flush hook where
# ``session`` is already bound. Importing here would be a no-op at
# call time, but keeps the lazy-import boilerplate in one place.
from ..models.V.usuarios_sucursal import UsuariosSucursal
from .versioned import close_and_insert

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


async def assign_creator_to_new_sucursal(
    session: AsyncSession,
    *,
    admin_user_uuid: uuid_lib.UUID,
    sucursal_uuid: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
) -> None:
    """Auto-grant the creating admin access to a just-created Sucursal.

    The creator of a branch is implicitly its first admin: their JWT
    ``sucursales_permitidas`` claim must include the new branch or the
    picker drops it (``admin_views.list_sucursales`` filters by
    ``claims.sucursales_permitidas``, which is built from the open
    ``usuarios_sucursal`` rows at login time). Without this auto-assign,
    the admin who just created the branch can see it in
    ``GET /empresa/sucursal`` (factory endpoint) but NOT in
    ``GET /sucursales`` (admin_views picker) -- exactly the
    "invisible branch" symptom reported 2026-09-29 on a freshly
    created Sucursal.

    Uses the same bi-temporal write pattern as
    ``admin_usuarios.asignar_sucursal`` (``UsuariosSucursal`` close+insert
    with ``current_uuid=None``), but invoked automatically from the
    POST /empresa/sucursal hook. ``operador-`` issuers never reach
    here -- the ``config_sucursal`` permission check at the endpoint
    rejects them with 403 first -- so ``actor_uuid`` is always the
    admin's user UUID in practice.

    Idempotent: a UK violation (the same admin already has an open
    assignment to this branch in the same TX) is swallowed so the
    call site does not have to guard against double-inserts.
    """
    import contextlib

    from sqlalchemy.exc import IntegrityError

    with contextlib.suppress(IntegrityError):
        await close_and_insert(
            session,
            UsuariosSucursal,
            current_uuid=None,
            new_attrs={
                "uuid_usuario": admin_user_uuid,
                "uuid_sucursal": sucursal_uuid,
            },
            actor_uuid=actor_uuid,
            log_tx=False,
        )


__all__ = ["assign_creator_to_new_sucursal", "propagate_uuid_to_fks"]
