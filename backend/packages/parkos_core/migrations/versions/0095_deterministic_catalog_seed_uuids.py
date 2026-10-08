"""MIGRATION 0095 -- deterministic uuid for the catalog rows still seeded at random.

Revision ID: 0095_deterministic_catalog_seed_uuids
Revises: 0094_cotizar_iva_incluido

WHY THIS MIGRATION EXISTS
-------------------------
``0001``/``0026``/``0031``/``0040``/``0041``/``0062`` seed catalog rows with
``gen_random_uuid()``, so cloud and every branch mint a DIFFERENT identifier for
the same logical row (``impuestos.IVA``, the four ``tipo_arqueo`` codes, the
``tipos_vehiculo`` ``otro`` row and the global ``configuracion_*`` defaults). ``0019``/``0020``/``0056``/``0093`` already fixed permisos,
tipo_persona, empresa and costos_servicios; this closes the remaining tables.
Applied migrations are immutable, so the fix is a convergence step at the head
of the chain (same scheme and namespace as ``0093``): every node, present and
future, ends up with ``uuid5(NAMESPACE, '<tabla>:<clave natural>')``, hardcoded
(computed offline, no ``uuid_generate_v5`` / pgcrypto dependency).

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It must not disturb a node that already depends on its random uuid (those keep
relying on ``prod.sync_identity_alias``). Per seed, a node converges ONLY when
all of these hold; otherwise the seed is skipped untouched:

* the deterministic uuid is not already part of the node's history;
* the natural key has exactly ONE version, and it is open (a history with edits
  is node-specific);
* no other table references the row (declared dependents plus every real FK
  found in ``pg_constraint``).

On a fresh node (the case this targets) all three hold, so it converges. Where
it converges it inserts the deterministic row as the new open version copying
the business columns, then closes the superseded one (``vigente_hasta`` +
``estado='inactivo'``) at the SAME instant (no gap/overlap). No UPDATE of a
uuid, no physical DELETE. Idempotent.

The statements are plain SQL (``DO`` blocks), so ``alembic upgrade --sql`` works
for the pre-flight check.
"""
from __future__ import annotations

import uuid as uuid_lib
from typing import NamedTuple

from alembic import op

revision = "0095_deterministic_catalog_seed_uuids"
down_revision = "0094_cotizar_iva_incluido"
branch_labels = None
depends_on = None

_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"
_NAMESPACE = uuid_lib.UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60")
_GLOBAL_DEFAULT_UUID_SUCURSAL = "2049f2cd-b2a8-4e45-9d19-31fa87eb67c6"  # see 0041


class Seed(NamedTuple):
    """One seeded catalog row and its deterministic identity.

    ``NamedTuple`` (not ``dataclass``): Alembic loads revision files without
    registering them in ``sys.modules``, which ``dataclass`` needs.
    """

    table: str
    key: str  # natural key label; uuid = uuid5(NAMESPACE, f"{table}:{key}")
    predicate: str  # SQL selecting every version of the natural key
    columns: tuple[str, ...]  # business columns copied onto the new version
    uuid: str


# table -> (table, column) pairs that reference it WITHOUT a declared DB FK.
# Real FKs are discovered at runtime from pg_constraint on top of these.
_DECLARED_DEPENDENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "impuestos": (("factura_impuestos", "uuid_impuesto"),),
    "tipo_arqueo": (("arqueo", "uuid_tipo_arqueo"),),
    "tipos_vehiculo": (
        ("ingreso", "uuid_tipo_vehiculo"),
        ("tarifas_sucursal", "uuid_tipo_vehiculo"),
        ("cantidad_vehiculos_sucursal", "uuid_tipo_vehiculo"),
        ("vehiculos", "uuid_tipo_vehiculo"),
        ("tipo_subscripciones", "uuid_tipo_vehiculo"),
    ),
}


def _seed(table: str, key: str, predicate: str, columns: tuple[str, ...], det_uuid: str) -> Seed:
    return Seed(table=table, key=key, predicate=predicate, columns=columns, uuid=det_uuid)


# uuid5(UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60"), "<tabla>:<clave>"), computed
# offline and hardcoded (verified against uuid5 by the regression test).
SEEDS: tuple[Seed, ...] = (
    _seed(
        "impuestos", "IVA", "codigo = 'IVA'",
        ("codigo", "nombre", "porcentaje", "tipo_calculo", "base_calculo"),
        "38766f08-f0ae-5fb3-8960-b9a3019acf99",
    ),
    _seed(
        "tipo_arqueo", "auditoria", "codigo = 'auditoria'",
        ("codigo", "nombre", "descripcion"), "184a2d44-267b-535a-932c-bd6e8b2b554e",
    ),
    _seed(
        "tipo_arqueo", "cierre_turno", "codigo = 'cierre_turno'",
        ("codigo", "nombre", "descripcion"), "acccb596-1e71-581e-81b8-bf530a842e94",
    ),
    _seed(
        "tipo_arqueo", "cierre_sesion", "codigo = 'cierre_sesion'",
        ("codigo", "nombre", "descripcion"), "0367b3e6-0f16-5979-8327-94321bf32ad3",
    ),
    _seed(
        "tipo_arqueo", "cierre_dia", "codigo = 'cierre_dia'",
        ("codigo", "nombre", "descripcion"), "7d522b56-d8f6-50b4-a399-ae591ee15f92",
    ),
    # 'moto' is NOT listed on purpose: 0087 already points the seeded
    # MENSUAL_MOTO plan at the random 'moto' uuid, so on every node (fresh
    # included) it has a dependent and converging it would mean re-versioning
    # tipo_subscripciones. It stays covered by sync_identity_alias.
    _seed("tipos_vehiculo", "otro", "tipo = 'otro'", ("tipo",), "dc3bdd19-7d7f-5831-8b28-b150ec21cf5b"),
    _seed(
        "configuracion_tolerancias", "global", "uuid_sucursal IS NULL",
        ("uuid_sucursal", "tolerancia_efectivo", "tolerancia_datafono"),
        "98d67b31-2e93-5b30-948f-d0880434705f",
    ),
    _seed(
        "configuracion_tolerancias",
        f"sucursal:{_GLOBAL_DEFAULT_UUID_SUCURSAL}",
        f"uuid_sucursal = '{_GLOBAL_DEFAULT_UUID_SUCURSAL}'",
        ("uuid_sucursal", "tolerancia_efectivo", "tolerancia_datafono"),
        "96f979e9-f483-5d09-8e40-b3ef8a01accd",
    ),
    _seed(
        "configuracion_seguridad", "global", "uuid_sucursal IS NULL",
        ("uuid_sucursal", "dias_expiracion_password", "max_intentos_login", "minutos_bloqueo_login"),
        "22491c5c-98f9-5f4e-a4c8-db9d11c72496",
    ),
)


def _declared_dependents_sql(table: str) -> str:
    pairs = _DECLARED_DEPENDENTS.get(table, ())
    if not pairs:
        return ""
    checks = "\n".join(
        f"""
        IF to_regclass('prod.{rel}') IS NOT NULL THEN
            EXECUTE 'SELECT EXISTS (SELECT 1 FROM prod.{rel} WHERE {col} = $1)'
                INTO _ref USING _old_uuid;
            IF _ref THEN RETURN; END IF;
        END IF;"""
        for rel, col in pairs
    )
    return checks


def build_statement(seed: Seed) -> str:
    """Plain-SQL ``DO`` block converging ONE seed (see the module docstring)."""
    cols = ", ".join(seed.columns)
    return f"""
DO $conv$
DECLARE
    _n integer;
    _old_uuid uuid;
    _now timestamp := clock_timestamp();
    _ref boolean;
    _fk record;
BEGIN
    IF EXISTS (SELECT 1 FROM prod.{seed.table} WHERE uuid = '{seed.uuid}') THEN
        RETURN;  -- already converged (or part of this node's history)
    END IF;

    SELECT count(*) INTO _n FROM prod.{seed.table} WHERE {seed.predicate};
    IF _n <> 1 THEN
        RETURN;  -- nothing seeded, or an edited history: node-specific, aliases cover it
    END IF;

    SELECT uuid INTO _old_uuid FROM prod.{seed.table}
     WHERE {seed.predicate} AND vigente_hasta IS NULL;
    IF NOT FOUND THEN
        RETURN;
    END IF;
{_declared_dependents_sql(seed.table)}
    FOR _fk IN
        SELECT c.conrelid::regclass AS rel, a.attname AS col
          FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
         WHERE c.contype = 'f' AND c.confrelid = 'prod.{seed.table}'::regclass
    LOOP
        EXECUTE format('SELECT EXISTS (SELECT 1 FROM %s WHERE %I = $1)', _fk.rel, _fk.col)
            INTO _ref USING _old_uuid;
        IF _ref THEN
            RETURN;  -- the row already has dependents: keep it, aliases cover the divergence
        END IF;
    END LOOP;

    INSERT INTO prod.{seed.table}
        (uuid, {cols}, vigente_desde, vigente_hasta, estado,
         created_at, created_by, sync_status, sync_attempts)
    SELECT '{seed.uuid}', {cols}, _now, NULL, 'activo',
           _now, NULL, 'sincronizado', 0
      FROM prod.{seed.table} WHERE uuid = _old_uuid;

    UPDATE prod.{seed.table}
       SET vigente_hasta = _now, estado = 'inactivo'
     WHERE uuid = _old_uuid AND vigente_hasta IS NULL;
END
$conv$;
"""


def build_statements(seeds: tuple[Seed, ...] = SEEDS) -> list[str]:
    return [build_statement(seed) for seed in seeds]


def converge(bind, seeds: tuple[Seed, ...] = SEEDS) -> None:  # noqa: ANN001 - sync Connection
    """Run the convergence on ``bind`` (used by tests; ``upgrade`` uses ``op.execute``)."""
    from sqlalchemy import text

    for sql in build_statements(seeds):
        bind.execute(text(sql))


def upgrade() -> None:
    op.execute(_LOCK_TIMEOUT_SQL)
    for sql in build_statements():
        op.execute(sql)


def downgrade() -> None:
    """No-op by design (the random uuids were never recorded; see 0056/0093)."""
    return


__all__ = ["SEEDS", "Seed", "build_statement", "build_statements", "converge", "downgrade", "upgrade"]
