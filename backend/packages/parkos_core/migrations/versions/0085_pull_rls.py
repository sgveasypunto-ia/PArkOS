"""MIGRATION 0085 -- database-level safety net for ``POST /sync/pull`` (ADR-005).

Revision ID: 0085_pull_rls
Revises: 0084_clientes_nk_all_index
Create Date: 2026-10-06 00:00:00.000000

**Why.** The pull scope is decided in SQL by ``sync/motor/pull_scope.py``. That is
an application-layer control: a future query that forgets the predicate would hand
the database to a branch. This migration adds a second barrier inside PostgreSQL.

**Design.**

* ``rol_sync_pull`` -- ``NOLOGIN NOBYPASSRLS``, granted ``SELECT`` ONLY on the 26
  tables the pull reads plus ``USAGE`` on schema ``prod``. The API (``parkos_app``,
  member of ``rol_app``) does ``SET LOCAL ROLE rol_sync_pull`` inside the pull
  transaction (``GRANT rol_sync_pull TO rol_app``), so a mistaken query can only
  *read*, and only what the policies below allow.
* The branch comes from the transaction-local setting ``parkos.pull_sucursal``
  (``prod.fn_pull_branch()``); unset / empty => NULL => scoped tables return NO rows
  (fail closed). Reference catalogs (``ALL_BRANCHES_ALLOWLIST``: no personal data)
  get ``SELECT`` only and no RLS: they are meant for every branch.
* The 16 scoped tables (plus the ``factura_electronica`` bridge, read by the pull
  predicate of ``clientes``, restricted to the branch's own invoices) get ``ENABLE ROW LEVEL SECURITY`` (NOT ``FORCE``: the table
  owner and ``rol_admin_auditor`` -- ``BYPASSRLS`` -- are unaffected) and two kinds of
  policy:

  - ``pull_rls_app_<t>``  ``FOR ALL TO rol_app USING (true) WITH CHECK (true)``.
    PostgreSQL denies everything when RLS is on and no policy matches the role, so
    without it ``parkos_app`` (API, ``job_sync_cloud``, admin, login) would lose the
    tables. It is the regression guard: behaviour for ``rol_app`` is unchanged.
  - ``pull_rls_<t>``      ``FOR SELECT TO rol_sync_pull USING (<scope rule>)``,
    mirroring ``pull_scope.build_scope_predicate`` (never narrower; the pull query
    still ANDs its own predicate, so a policy may be coarser but not tighter).

* Rules that must read tables whose own policy would recurse (``clientes`` ->
  ``clientes``) or that the role must not read at all (``factura_electronica``)
  go through ``SECURITY DEFINER`` helpers ``prod.fn_pull_*``. Security reasoning:
  they are owned by the migration owner (table owner => bypasses RLS), pin
  ``search_path = pg_catalog, prod, pg_temp`` (no hijack by a caller-created object),
  are read-only ``STABLE`` SQL, take no caller-controlled text (the branch comes from
  the GUC), ``EXECUTE`` is revoked from ``PUBLIC`` and granted to ``rol_sync_pull``
  only. They expose only uuids / normalized keys of the caller's OWN branch scope.
  The GUC itself is settable by whoever holds ``rol_sync_pull``; that is the same
  trust the JWT-derived ``uuid_sucursal`` already carries in the application, and
  the role is read-only.

**[A] tables.** ``factura_electronica`` is ``[L-E]``/append-only; ``rol_sync_pull`` only
READS it (own branch rows). No REVOKE / trigger / privilege of ``rol_app`` is touched; no table is
created. ``ENABLE ROW LEVEL SECURITY`` adds a read filter and cannot weaken
``REVOKE UPDATE, DELETE`` or the ``BEFORE UPDATE OR DELETE`` triggers.

**Idempotent.** Role creation is guarded; policies are ``DROP ... IF EXISTS`` +
``CREATE``; functions are ``CREATE OR REPLACE``. Downgrade disables RLS, drops
policies and functions, revokes grants and drops the role if nothing else uses it.
No row is ever modified or deleted.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0085_pull_rls"
down_revision = "0084_clientes_nk_all_index"
branch_labels = None
depends_on = None

ROLE = "rol_sync_pull"

# Reference catalogs: every branch receives them, no personal data. SELECT only.
GLOBAL_TABLES: tuple[str, ...] = (
    "permisos",
    "tipo_persona",
    "tipos_vehiculo",
    "tipo_subscripciones",
    "tipo_tarifa",
    "tipo_sucursal",
    "tipo_arqueo",
    "impuestos",
    "otros_cobros",
    "costos_servicios",
)

_BRANCH = "prod.fn_pull_branch()"
_NK_NUM = "regexp_replace({c}, '[^0-9A-Za-z]', '', 'g')"
_NK_PLACA = "upper(regexp_replace({c}, '[^0-9A-Za-z]', '', 'g'))"

# table -> policy USING expression (rol_sync_pull). Mirrors pull_scope.py.
SCOPED_POLICIES: dict[str, str] = {
    # owned by one branch
    "sucursal": f"uuid = {_BRANCH}",
    "resolucion_facturacion": f"uuid_sucursal = {_BRANCH}",
    "usuarios_sucursal": f"uuid_sucursal = {_BRANCH}",
    "documentos": f"uuid_sucursal = {_BRANCH}",
    "tarifas_sucursal": f"uuid_sucursal = {_BRANCH}",
    "cantidad_vehiculos_sucursal": f"uuid_sucursal = {_BRANCH}",
    # global default + per-branch override (fail closed when the branch is unset)
    "configuracion_tolerancias": (
        f"{_BRANCH} IS NOT NULL AND (uuid_sucursal IS NULL OR uuid_sucursal = {_BRANCH})"
    ),
    "configuracion_seguridad": (
        f"{_BRANCH} IS NOT NULL AND (uuid_sucursal IS NULL OR uuid_sucursal = {_BRANCH})"
    ),
    # sold by one branch (the parent policy applies to the sub-select too: same rule)
    "subscripciones_cliente": f"uuid_sucursal = {_BRANCH}",
    "subscripcion_vehiculos": (
        "uuid_subscripcion_cliente IN ("
        f"SELECT sc.uuid FROM prod.subscripciones_cliente sc WHERE sc.uuid_sucursal = {_BRANCH})"
    ),
    # derived through bridge tables
    "usuarios": (
        "uuid IN (SELECT us.uuid_usuario FROM prod.usuarios_sucursal us "
        f"WHERE us.uuid_sucursal = {_BRANCH} AND us.vigente_hasta IS NULL)"
    ),
    "permisos_usuario": (
        "uuid_usuario IN (SELECT us.uuid_usuario FROM prod.usuarios_sucursal us "
        f"WHERE us.uuid_sucursal = {_BRANCH} AND us.vigente_hasta IS NULL)"
    ),
    "clientes": (
        "uuid IN (SELECT r.v FROM prod.fn_pull_cliente_refs() r) OR ("
        f"(tipo_identificador, {_NK_NUM.format(c='numero_identificacion')}) IN "
        "(SELECT k.tipo, k.numero FROM prod.fn_pull_cliente_keys() k) "
        f"AND {_NK_NUM.format(c='numero_identificacion')} <> '')"
    ),
    "clientes_b2b": (
        "uuid_cliente IN (SELECT r.v FROM prod.fn_pull_cliente_refs() r) "
        "OR uuid_cliente IN (SELECT n.v FROM prod.fn_pull_cliente_versions() n)"
    ),
    "vehiculos": (
        "uuid IN (SELECT l.v FROM prod.fn_pull_vehiculo_linked() l) OR ("
        f"{_NK_PLACA.format(c='placa')} IN (SELECT k.k FROM prod.fn_pull_vehiculo_keys() k) "
        f"AND {_NK_PLACA.format(c='placa')} <> '')"
    ),
    "empresa": "prod.fn_pull_empresa_visible(uuid, nit)",
    # BRIDGE table (not pulled): the pull's own scope predicate for clientes reads
    # ``factura_electronica.uuid_cliente`` directly, so the role needs SELECT, but only
    # on the pulling branch's own invoices.
    "factura_electronica": f"uuid_sucursal = {_BRANCH}",
}

_FUNCTIONS: tuple[str, ...] = (
    "prod.fn_pull_branch()",
    "prod.fn_pull_cliente_refs()",
    "prod.fn_pull_cliente_keys()",
    "prod.fn_pull_cliente_versions()",
    "prod.fn_pull_vehiculo_linked()",
    "prod.fn_pull_vehiculo_keys()",
    "prod.fn_pull_empresa_visible(uuid, varchar)",
)

_DEFINER = "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, prod, pg_temp"

_FUNCTION_DDL: tuple[str, ...] = (
    # Branch of the current pull transaction; NULL => fail closed.
    """
    CREATE OR REPLACE FUNCTION prod.fn_pull_branch() RETURNS uuid
    LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp
    AS $fn$ SELECT NULLIF(current_setting('parkos.pull_sucursal', true), '')::uuid $fn$
    """,
    # uuid of every cliente VERSION the branch references (subscription or invoice).
    f"""
    CREATE OR REPLACE FUNCTION prod.fn_pull_cliente_refs() RETURNS TABLE (v uuid)
    {_DEFINER}
    AS $fn$
        SELECT sc.uuid_cliente FROM prod.subscripciones_cliente sc
        WHERE sc.uuid_sucursal = prod.fn_pull_branch()
        UNION
        SELECT fe.uuid_cliente FROM prod.factura_electronica fe
        WHERE fe.uuid_sucursal = prod.fn_pull_branch()
    $fn$
    """,
    # natural keys (tipo, normalized numero) of those clientes; empty keys excluded.
    f"""
    CREATE OR REPLACE FUNCTION prod.fn_pull_cliente_keys()
    RETURNS TABLE (tipo varchar, numero text)
    {_DEFINER}
    AS $fn$
        SELECT c.tipo_identificador, {_NK_NUM.format(c="c.numero_identificacion")}
        FROM prod.clientes c
        WHERE c.uuid IN (SELECT r.v FROM prod.fn_pull_cliente_refs() r)
          AND {_NK_NUM.format(c="c.numero_identificacion")} <> ''
    $fn$
    """,
    # every cliente version carrying one of those keys (open or closed).
    f"""
    CREATE OR REPLACE FUNCTION prod.fn_pull_cliente_versions() RETURNS TABLE (v uuid)
    {_DEFINER}
    AS $fn$
        SELECT c.uuid FROM prod.clientes c
        WHERE (c.tipo_identificador, {_NK_NUM.format(c="c.numero_identificacion")}) IN
              (SELECT k.tipo, k.numero FROM prod.fn_pull_cliente_keys() k)
          AND {_NK_NUM.format(c="c.numero_identificacion")} <> ''
    $fn$
    """,
    # vehiculo versions linked to a subscription sold at the branch.
    f"""
    CREATE OR REPLACE FUNCTION prod.fn_pull_vehiculo_linked() RETURNS TABLE (v uuid)
    {_DEFINER}
    AS $fn$
        SELECT sv.uuid_vehiculo
        FROM prod.subscripcion_vehiculos sv
        JOIN prod.subscripciones_cliente sc ON sc.uuid = sv.uuid_subscripcion_cliente
        WHERE sc.uuid_sucursal = prod.fn_pull_branch()
    $fn$
    """,
    # normalized placas of the linked vehiculos; empty keys excluded.
    f"""
    CREATE OR REPLACE FUNCTION prod.fn_pull_vehiculo_keys() RETURNS TABLE (k text)
    {_DEFINER}
    AS $fn$
        SELECT {_NK_PLACA.format(c="ve.placa")}
        FROM prod.vehiculos ve
        WHERE ve.uuid IN (SELECT l.v FROM prod.fn_pull_vehiculo_linked() l)
          AND {_NK_PLACA.format(c="ve.placa")} <> ''
    $fn$
    """,
    # empresa of the pulling branch by NIT across versions, with the pull_scope
    # fallbacks (NULL / unknown reference, orphaned closed reference => open rows).
    f"""
    CREATE OR REPLACE FUNCTION prod.fn_pull_empresa_visible(p_uuid uuid, p_nit varchar)
    RETURNS boolean
    {_DEFINER}
    AS $fn$
        WITH b AS (SELECT prod.fn_pull_branch() AS s),
        ref AS (
            SELECT su.uuid_empresa AS r FROM prod.sucursal su, b
            WHERE su.uuid = b.s AND su.uuid_empresa IS NOT NULL
        ),
        nits AS (
            SELECT e.nit FROM prod.empresa e WHERE e.uuid IN (SELECT r FROM ref) AND e.nit <> ''
        )
        SELECT (SELECT s FROM b) IS NOT NULL AND (
            NOT EXISTS (SELECT 1 FROM ref)
            OR p_uuid IN (SELECT r FROM ref)
            OR (p_nit IN (SELECT nit FROM nits) AND p_nit <> '')
            OR NOT EXISTS (
                SELECT 1 FROM prod.empresa o
                WHERE o.vigente_hasta IS NULL AND o.nit IN (SELECT nit FROM nits) AND o.nit <> ''
            )
        )
    $fn$
    """,
)


def _grant_functions() -> None:
    for fn in _FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {ROLE}")


def upgrade() -> None:
    """Create the role, helper functions, grants, RLS and policies (idempotent)."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        f"""
        DO $do$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
            END IF;
        END
        $do$
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA prod TO {ROLE}")
    for ddl in _FUNCTION_DDL:
        op.execute(ddl)
    _grant_functions()

    for table in GLOBAL_TABLES:
        op.execute(f"GRANT SELECT ON prod.{table} TO {ROLE}")

    for table, using in SCOPED_POLICIES.items():
        op.execute(f"GRANT SELECT ON prod.{table} TO {ROLE}")
        op.execute(f"ALTER TABLE prod.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS pull_rls_app_{table} ON prod.{table}")
        op.execute(
            f"CREATE POLICY pull_rls_app_{table} ON prod.{table} "
            "FOR ALL TO rol_app USING (true) WITH CHECK (true)"
        )
        op.execute(f"DROP POLICY IF EXISTS pull_rls_{table} ON prod.{table}")
        op.execute(
            f"CREATE POLICY pull_rls_{table} ON prod.{table} FOR SELECT TO {ROLE} USING ({using})"
        )

    # rol_app (parkos_app) switches into the read-only role inside the pull.
    op.execute(f"GRANT {ROLE} TO rol_app")


def downgrade() -> None:
    """Disable RLS, drop policies / functions, revoke grants, drop the role if unused."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    for table in SCOPED_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS pull_rls_{table} ON prod.{table}")
        op.execute(f"DROP POLICY IF EXISTS pull_rls_app_{table} ON prod.{table}")
        op.execute(f"ALTER TABLE prod.{table} DISABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        DO $do$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                REVOKE {ROLE} FROM rol_app;
            END IF;
        END
        $do$
        """
    )
    for fn in reversed(_FUNCTIONS):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    # Revoking from the role only when it exists (it may already be gone).
    op.execute(
        f"""
        DO $do$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA prod FROM {ROLE};
                REVOKE USAGE ON SCHEMA prod FROM {ROLE};
                BEGIN
                    DROP ROLE {ROLE};
                EXCEPTION WHEN dependent_objects_still_exist THEN
                    RAISE NOTICE '{ROLE} still has dependent objects; role kept';
                END;
            END IF;
        END
        $do$
        """
    )
