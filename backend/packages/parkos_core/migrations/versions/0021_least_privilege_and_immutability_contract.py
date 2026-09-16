"""enforce the least-privilege contract for every real table via the missing
login role + per-class REVOKE/column-scoped GRANT (SELECT/INSERT always
allowed, UPDATE never free-form, DELETE forbidden except one documented,
pre-existing, tested carve-out)

Revision ID: 0021_least_privilege_and_immutability_contract
Revises: 0020_deterministic_tipo_persona_empresa_uuids
Create Date: 2026-09-10 18:00:00.000000

**The root-cause finding.** ``rol_app`` (created in ``0001_initial_schema.py``)
is ``NOLOGIN`` — it was always meant to be INHERITED by a real connection
role. No such role has ever existed: the ONLY login-capable role in either
node's database is ``parkos``, which is also the Postgres SUPERUSER
(``POSTGRES_USER=parkos``, used verbatim as ``DATABASE_URL``/``PARKOS_DB_URL``
by every container — confirmed live via ``pg_roles``/``pg_stat_activity``).
Every ``REVOKE`` any prior migration ever wrote has been **inert** since the
day it was written: a superuser bypasses every GRANT/REVOKE check by
definition. This migration creates the missing login role
(``docker-compose.cloud.yml``/``docker-compose.local.yml`` updated in the
same change to actually connect as it) and closes the per-class privilege
gaps that were invisible until ``rol_app`` was a real, used identity.

**New login role.** ``CREATE ROLE parkos_app LOGIN INHERIT IN ROLE rol_app``,
dev-only password (matches this repo's existing plaintext-in-compose
``POSTGRES_PASSWORD=parkos`` convention — a real deployment MUST source this
from secrets management, flagged as a residual finding, not solved here).
``rol_app`` itself stays NOLOGIN — a pure privilege-group role.

**Design correction made DURING this same work session (documented here
because the first draft of this migration genuinely broke 30 existing
tests — corrected before commit, not silently patched):**

The first draft added a NEW generic ``BEFORE UPDATE OR DELETE`` trigger,
unconditionally blocking even the superuser, to every table this migration
touches — copying the *shape* of the existing per-table ``fn_<table>_
inmutable()`` triggers (``0001``) without first confirming which tables
already had exactly that. Running the full test suite immediately exposed
five real problems with that first draft, each fixed by reading the
ALREADY-EXISTING contract more carefully rather than assuming a gap existed:

1. The 11 ``[A]`` tables ``0001`` REVOKE's were NOT missing a trigger — they
   already have one, per-table, since ``0001`` (``fn_<table>_inmutable()``,
   tag ``<TABLE>_INMUTABLE``, ``ERRCODE 42501``). Adding a second, generic
   trigger duplicated existing protection and broke
   ``test_a_inmutable.py`` (asserts the specific ``<TABLE>_INMUTABLE`` tag,
   which the newer, alphabetically-earlier generic trigger pre-empted).
   **Fix: touch none of these 11 tables at all.**
2. ``sync_queue`` intentionally KEEPS DELETE granted —
   ``test_revokes_active.py::test_sync_queue_has_update_delete`` is an
   existing, deliberate regression test for a documented purge-worker
   carve-out (not yet implemented, but already an accepted design decision,
   independent of whether ``sync_queue_lw_buffer``'s own docstring describes
   a stricter carve-out for its sibling table). Per this task's own
   instruction to never resolve a finding by weakening an existing
   criterion: **this migration does not touch ``sync_queue``'s DELETE
   grant.** Flagged in the audit report as a disclosed, pre-existing
   exception to the "DELETE never, anywhere" rule — a real deviation, not a
   silently-assumed one.
3. ``sesion``'s legitimate narrow-update set is NOT just
   ``(timestamp_cierre, uuid_usuario_cierre)`` (``repo/session_cycle.py``'s
   ``close_sesion`` only shows one call site) — ``estado`` is ALSO
   legitimately updatable, guarded by the pre-existing
   ``fn_sesion_ls_session_guard()`` trigger (requires a co-transactional
   ``log_transaccional`` row), per ``test_ls_session_guard.py``. **Fix:
   ``estado`` added to ``sesion``'s allowed column set.**
4. ``envio_dian`` is NOT a zero-update ``[L-W]`` table like its siblings —
   ``dian/cloud/dispatcher.py`` legitimately does
   ``envio.payload = {**envio.payload, "track_id": ...}`` then commits,
   a real mid-lifecycle UPDATE of exactly the ``payload`` column while the
   DIAN round-trip is in flight (confirmed by the actual failing SQL in
   ``test_dian_round_trip.py``: ``UPDATE prod.envio_dian SET payload=...``).
   **Fix: ``envio_dian`` moved out of the blanket-forbid class into a
   column-scoped-update class, narrowed to exactly ``payload``.**
5. Blocking DELETE unconditionally (even for the superuser) on ``[V]``
   tables broke ``test_permissions_dependency.py``'s own fixture teardown,
   which hard-deletes its ``permisos``/``permisos_usuario`` test rows
   between runs — a testing-infrastructure pattern, unrelated to the
   production contract this migration exists to enforce. **Fix: every
   NEWLY-added restriction in this migration uses GRANT/REVOKE only, never
   a blocking trigger** — REVOKE is naturally superuser-exempt (matching
   Postgres semantics), so it cannot collide with a superuser-run fixture
   teardown or a future data-fix migration, while still being a REAL,
   meaningful restriction for ``rol_app`` — which is the actual production
   application identity as of this same migration. The pre-existing
   triggers this migration does NOT touch (the 11 ``[A]`` tables,
   ``idempotency_keys``/``pairing_tokens``/``revoked_sync_jwts``,
   ``sync_queue_lw_buffer``'s DELETE guard) keep their stricter
   "blocks-even-superuser" behavior unchanged — this migration does not
   weaken them, it simply doesn't extend that specific stricter mechanism
   to new tables without proof no existing test depends on superuser-level
   DML there.

**Net asymmetry this leaves, disclosed rather than hidden:** for the tables
covered by a PRE-EXISTING trigger (see above), DELETE fails even for
``parkos`` the superuser. For every table this migration newly restricts —
26 ``[V]``, ``login``/``sesion``, 8 ``[L-W]``/``[L-E]`` tables (all but
``envio_dian``), ``envio_dian`` itself, ``alert_types`` — the restriction is
GRANT/REVOKE only: ``rol_app`` (the real application identity) cannot
violate the contract, but a session connecting directly as the Postgres
superuser still technically can. Closing that gap the same way the older
tables do would require auditing every test and worker that might run a
direct DML statement against these specific tables as a superuser-equivalent
role first (this session's budget did not allow re-deriving that
exhaustively for 36 more tables after finding it broke 3 for the 5 tables
above) — recommended as explicit follow-up work, not assumed solved.

**Column-scoped UPDATE, not a trigger, for narrow-update classes.** Postgres
column-level ``GRANT UPDATE (col_a, col_b) ON t TO role`` restricts exactly
which columns a role's ``UPDATE ... SET`` may name — attempting to set any
other column raises ``InsufficientPrivilege`` natively, no PL/pgSQL needed,
and (like all GRANT/REVOKE) it's naturally inert for a superuser session,
consistent with point 5 above.

**Why GRANT/REVOKE on the partitioned PARENT is enough.** Every partitioned
table's privileges (``salidas``, ``caja``, ... — untouched by this migration,
verified only) are inherited by all its partitions automatically since
Postgres 11; none of the tables this migration DOES touch are partitioned,
so this is a documentation note, not something this migration relies on.

**Not covered by this migration (explicit residual findings):**
- The dev-only login password — a real deployment must inject this from
  secrets management.
- The superuser-DML asymmetry described above for the 36 newly-restricted
  tables.
- ``sync_queue``'s DELETE grant — pre-existing, intentional, documented, not
  touched.
- ``config.yaml``'s own DIAN audit-first rule text names only ``[A]``
  tables for the "REVOKE + trigger" requirement — a spec-completeness gap
  against the broader ``[L-W]``/``[L-E]`` audit-first contract, separate
  from this migration's job of fixing the running database's actual grants.
- Exhaustive live SQL testing of all 54 tables individually was done by
  representative sample per mechanism class plus this migration's own
  narrower, corrected scope — see the companion audit report in
  ``.agent-generated/2026-09-10-contrato-crud-tablas/``.
"""

from __future__ import annotations

import os

from alembic import op

# revision identifiers, used by Alembic.
revision = "0021_least_privilege_and_immutability_contract"
down_revision = "0020_deterministic_tipo_persona_empresa_uuids"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

# Dev/test-only default — same convention as this repo's existing
# POSTGRES_PASSWORD=parkos plaintext-in-compose. A real deployment MUST
# override via PARKOS_APP_DB_PASSWORD from secrets management.
_APP_LOGIN_PASSWORD = os.environ.get("PARKOS_APP_DB_PASSWORD", "parkos_app_dev")

# [L-W]/[L-E] tables with NO legitimate UPDATE at all (envio_dian excluded —
# see class below). REVOKE UPDATE, DELETE only; no trigger (point 5 above).
_ZERO_UPDATE_TABLES: tuple[str, ...] = (
    "alerta",
    "anulaciones",
    "reclamos",
    "reimpresion_ticket",
    "validacion_evento",
    "facturas",
    "ingreso",
    "factura_electronica",
)

# envio_dian: legitimate narrow UPDATE on exactly `payload` (dian/cloud/
# dispatcher.py's mid-round-trip track_id merge). Column-scoped GRANT, no
# blanket UPDATE, DELETE fully revoked.
_ENVIO_DIAN_NARROW_COLUMNS = ("payload",)

# [V] tables + [L-S]: column-scoped UPDATE, DELETE revoked (GRANT/REVOKE
# only — see point 5 above for why no trigger).
_NARROW_UPDATE_V_TABLES: tuple[str, ...] = (
    "cantidad_vehiculos_sucursal",
    "clientes",
    "clientes_b2b",
    "configuracion_seguridad",
    "configuracion_tolerancias",
    "costos_servicios",
    "documentos",
    "empresa",
    "impuestos",
    "otros_cobros",
    "permisos",
    "permisos_usuario",
    "resolucion_facturacion",
    "subscripcion_vehiculos",
    "subscripciones_cliente",
    "sucursal",
    "tarifas_sucursal",
    "tipo_arqueo",
    "tipo_persona",
    "tipo_subscripciones",
    "tipo_sucursal",
    "tipo_tarifa",
    "tipos_vehiculo",
    "usuarios",
    "usuarios_sucursal",
    "vehiculos",
)
_V_NARROW_COLUMNS = ("vigente_hasta", "estado")
_NARROW_UPDATE_LS_TABLES: dict[str, tuple[str, ...]] = {
    "login": ("timestamp_cierre", "estado"),
    # `estado` confirmed legitimate here too — fn_sesion_ls_session_guard()
    # (0001) already guards estado changes with a co-transactional
    # log_transaccional requirement; test_ls_session_guard.py exercises it
    # directly with a raw `UPDATE ... SET estado = 'cerrado'`.
    "sesion": ("timestamp_cierre", "uuid_usuario_cierre", "estado"),
}

# Seeded reference catalog — SELECT-only for rol_app, re-seeding is a
# migration-time (superuser) idempotent INSERT, never an app-runtime op.
_SEED_ONLY_TABLE = "alert_types"


def upgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)

    # ---- 1. The missing login role (root cause) ----
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'parkos_app') THEN
                CREATE ROLE parkos_app LOGIN INHERIT PASSWORD '{_APP_LOGIN_PASSWORD}';
            END IF;
        END
        $$;
    """)
    op.execute("GRANT rol_app TO parkos_app;")

    # ---- 2. [L-W]/[L-E] zero-update tables (envio_dian excluded) ----
    for table in _ZERO_UPDATE_TABLES:
        op.execute(f"REVOKE UPDATE, DELETE ON prod.{table} FROM rol_app;")
        op.execute(f"GRANT SELECT, INSERT ON prod.{table} TO rol_app;")

    # ---- 3. envio_dian: narrow UPDATE(payload), DELETE forbidden ----
    op.execute("REVOKE UPDATE, DELETE ON prod.envio_dian FROM rol_app;")
    cols_sql = ", ".join(_ENVIO_DIAN_NARROW_COLUMNS)
    op.execute(f"GRANT UPDATE ({cols_sql}) ON prod.envio_dian TO rol_app;")

    # ---- 4. [V] narrow update + forbid delete (GRANT/REVOKE only) ----
    for table in _NARROW_UPDATE_V_TABLES:
        op.execute(f"REVOKE UPDATE, DELETE ON prod.{table} FROM rol_app;")
        cols_sql = ", ".join(_V_NARROW_COLUMNS)
        op.execute(f"GRANT UPDATE ({cols_sql}) ON prod.{table} TO rol_app;")

    # ---- 5. [L-S] narrow update + forbid delete ----
    for table, cols in _NARROW_UPDATE_LS_TABLES.items():
        op.execute(f"REVOKE UPDATE, DELETE ON prod.{table} FROM rol_app;")
        cols_sql = ", ".join(cols)
        op.execute(f"GRANT UPDATE ({cols_sql}) ON prod.{table} TO rol_app;")

    # ---- 6. alert_types: seeded reference catalog — SELECT-only ----
    op.execute(f"REVOKE INSERT, UPDATE, DELETE ON prod.{_SEED_ONLY_TABLE} FROM rol_app;")
    op.execute(f"GRANT SELECT ON prod.{_SEED_ONLY_TABLE} TO rol_app;")

    # sync_queue is deliberately NOT touched — see module docstring point 2.


def downgrade() -> None:
    """Restore blanket grants on every table this migration touched.

    Does NOT drop ``parkos_app`` or revoke ``rol_app`` from it — see the
    identical note in the first-draft migration's history; yanking
    credentials out from under a possibly-still-configured connection
    string is a worse failure mode than leaving an unused role behind.
    """
    op.execute(_LOCK_TIMEOUT_SQL)

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON prod.{_SEED_ONLY_TABLE} TO rol_app;")

    for table in _NARROW_UPDATE_LS_TABLES:
        op.execute(f"GRANT UPDATE, DELETE ON prod.{table} TO rol_app;")
    for table in reversed(_NARROW_UPDATE_V_TABLES):
        op.execute(f"GRANT UPDATE, DELETE ON prod.{table} TO rol_app;")

    op.execute("GRANT UPDATE, DELETE ON prod.envio_dian TO rol_app;")

    for table in reversed(_ZERO_UPDATE_TABLES):
        op.execute(f"GRANT UPDATE, DELETE ON prod.{table} TO rol_app;")
