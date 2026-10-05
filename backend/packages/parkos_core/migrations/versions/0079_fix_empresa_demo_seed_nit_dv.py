"""0079_fix_empresa_demo_seed_nit_dv -- correct the invalid check digit
(DV) on the demo ``prod.empresa`` seed.

Revision ID: 0079_fix_empresa_demo_seed_nit_dv
Revises: 0078_empresa_singleton_uk
Create Date: 2026-10-04

THE PROBLEM THIS PINS
----------------------
``0001_initial_schema.py`` seeds the ``prod.empresa`` singleton with
``nit='900000000-0'``. ``900000000-0`` has an INVALID check digit: the
DIAN modulo-11 algorithm (DV weights ``[3, 7, 13, 17, 19, 23, 29, 37, 41,
43, 47, 53, 59, 67, 71]`` applied right-to-left, ``mod = sum % 11``, then
``DV = mod`` if ``mod < 2`` else ``DV = 11 - mod`` -- see
``apps/web_admin/src/lib/validation/nit.ts::calcularDvModulo11``, the
exact function gating the Empresa form) expects DV ``5`` for body
``900000000``, not ``0``. Confirmed independently by hand-computing the
algorithm and by evaluating ``calcularDvModulo11('900000000') === 5``.

Live impact (confirmed via chrome-devtools on a genuinely fresh
``-FreshVolumes`` reset, QA ``integracion-admin-sucursal``): the admin
frontend's ``EmpresaDatosTab``
(``apps/web_admin/src/features/empresa/components/EmpresaDatosTab.tsx``)
calls this same validator (``validarNitModulo11``) directly on page load
and rejects the seeded NIT with ``DV inválido: el esperado para
900000000 es 5, recibiste 0.``. The "Guardar datos" submit button is
gated on that NIT validation result (``disabled={isSubmitting ||
nitShowError}``), so it stays PERMANENTLY DISABLED the instant the page
loads with this seed -- even after editing an unrelated field
(``nombre``, ``regimen``, welcome messages). A fresh install cannot save
ANY edit to the Empresa singleton until an admin happens to know to also
fix the NIT first. This blocks the documented Fase 2 "create a sucursal
from the admin UI" golden path at its very first screen.

Note: ``backend/packages/parkos_core/src/parkos_core/schemas/empresa.py``
(``EmpresaCreate``/``EmpresaUpdate``) does NOT run any DV validation
today -- unlike its sibling ``schemas/clientes.py`` (``_validar_nit_dv``).
The backend never rejected this seed; only the frontend Zod copy (which
documents itself as "idéntico al backend" -- a claim that is currently
false for ``empresa``, see the finding in this migration's test file).
That gap is a separate, pre-existing issue and is NOT fixed here.

WHY A NEW MIGRATION, NOT AN EDIT TO 0001
-----------------------------------------
``0001`` is NOT safely editable in place for this value.
``0020_deterministic_tipo_persona_empresa_uuids.py`` keys its
``_EMPRESA_DETERMINISTIC_UUIDS`` reconciliation dict by the EXACT literal
``"900000000-0"`` and matches live rows with
``WHERE nit = :key_value AND vigente_hasta IS NULL`` to redirect the
seeded row onto the fixed ``uuid5`` every node must converge on
(``11de9b03-8be3-5688-93e1-d283b6557f70``). If ``0001``'s seed literal
were changed in place, a FRESH install replaying the full migration
chain would seed a DIFFERENT ``nit``, ``0020``'s dict key would no
longer match, its reconciliation would silently no-op, and the row
would keep a random ``gen_random_uuid()`` instead of the deterministic
uuid -- reintroducing the exact cross-node identity defect ``0020`` (and
its sibling ``0019``) exist to prevent. Editing historical seed history
here would be strictly worse than leaving it alone and fixing the data
forward.

WHY THE PREDICATE DOES NOT ALSO MATCH ``nombre = 'Parkos Demo'``
-------------------------------------------------------------------
On a database that has run ``0020``, the OPEN ``prod.empresa`` row no
longer carries ``nombre='Parkos Demo'``: ``0020``'s reconciliation INSERT
only copies ``uuid``/``nit``/versioning/audit/sync columns onto the new
deterministic-uuid row -- ``nombre``, ``mensaje_bienvenida``,
``mensaje_salida`` and ``regimen`` are deliberately NOT carried over (see
``0020``'s ``_reconcile_table`` INSERT column list). The original
``nombre='Parkos Demo'`` row from ``0001`` is the one ``0020`` closes
(``vigente_hasta`` set, ``estado='inactivo'``); it must stay untouched as
historical audit trail. So the only predicate that is both tight (never
touches a real admin-edited row -- no real company plausibly has this
exact invalid demo NIT) and correct on every already-migrated database
(regardless of whether ``nombre`` happens to be NULL or still
``'Parkos Demo'``, e.g. a database paused between ``0001`` and ``0020``)
is the NIT value itself, scoped to the currently-open row.

THE FIX
-------
One idempotent, tightly-scoped ``UPDATE``: only the row whose
``nit = '900000000-0'`` AND ``vigente_hasta IS NULL`` (the live, current
version of the row) gets its ``nit`` corrected to ``'900000000-5'``. A
second run matches zero rows and is a no-op. No bi-temporal close+insert
is used -- like ``0073``/``0074``, this is a correction of seed data that
was simply wrong, not a business-level edit that must preserve the prior
value as a historical version. ``prod.empresa`` has no immutability
trigger (unlike ``prod.factura_pagos``/``prod.bitacora``): its only
``BEFORE INSERT`` triggers are ``empresa_audit_columns`` and
``empresa_set_vigente_inicial``, neither of which fires on ``UPDATE``, so
no trigger disable/enable bracket is needed.

DOWNGRADE
---------
No-op by design (same reasoning as ``0073``): restoring a known-invalid
check digit is not a correct prior state to roll back to, and a blind
"set nit back to 900000000-0" could just as easily stomp a different,
legitimately-edited row that happens to now hold the corrected value.
"""

from __future__ import annotations

from alembic import op

revision = "0079_fix_empresa_demo_seed_nit_dv"
down_revision = "0078_empresa_singleton_uk"
branch_labels = None
depends_on = None

_INVALID_DEMO_NIT = "900000000-0"
_CORRECTED_DEMO_NIT = "900000000-5"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE prod.empresa
        SET nit = '{_CORRECTED_DEMO_NIT}'
        WHERE nit = '{_INVALID_DEMO_NIT}'
          AND vigente_hasta IS NULL
        """
    )


def downgrade() -> None:
    """No-op by design -- see the module docstring's DOWNGRADE section."""


__all__ = [
    "down_revision",
    "downgrade",
    "revision",
    "upgrade",
]
