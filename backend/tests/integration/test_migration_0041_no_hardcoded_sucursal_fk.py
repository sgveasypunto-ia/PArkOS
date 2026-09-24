"""test_migration_0041_no_hardcoded_sucursal_fk.py — REGRESSION (2026-09-24).

Bug reproducido en vivo: ``uv run pytest ... TEST_PG_IMAGE=parkos-postgres:
16-pgpartman`` fallaba con la cadena de migraciones abortada en
``0041_seed_configuracion_tolerancias`` — diagnosticado inicialmente (mal)
como "imagen pg_partman desactualizada", pero el error real es otro y no
tiene nada que ver con pg_partman ni con la imagen:

    psycopg2.errors.ForeignKeyViolation: insert or update on table
    "configuracion_tolerancias" violates foreign key constraint
    "fk_configuracion_tolerancias_uuid_sucursal"
    DETAIL: Key (uuid_sucursal)=(2049f2cd-b2a8-4e45-9d19-31fa87eb67c6)
    is not present in table "sucursal".

Causa raíz real: la migración 0041 (Op 2) hardcodea el ``uuid_sucursal``
de la sucursal de ESTE dev local (``BOG-CEN``) como un INSERT
incondicional que corre en TODA base de datos (cloud, cualquier
sucursal nueva, cualquier test aislado) — el propio docstring de la
migración lo admite: "Branch override for the LOCAL DEV BRANCH...
A future PR can either drop this row... or replace it". En cualquier
entorno donde esa sucursal específica no exista (una instalación
nueva de verdad, CI, o un Postgres de test aislado via testcontainers)
la FK revienta y ABORTA TODA la cadena de migraciones desde 0041 en
adelante — ningún migration 0042+ llega a aplicarse.

Este test corre ``alembic upgrade head`` de forma independiente del
fixture ``alembic_upgrade`` (que hace SKIP silencioso ante cualquier
fallo, asumiendo que siempre es por falta de ``pg_partman`` — eso es
lo que ocultó este bug real hasta ahora) para que la regresión sea un
FAIL duro, no un skip.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
_MIGRATIONS_PKG = _PARKOS_CORE_SRC.parent / "migrations"

_TIMEOUT_S = 120


def test_alembic_upgrade_head_succeeds_on_fresh_db(pg_dsn: str, _wait_for_pg: None) -> None:
    """``alembic upgrade head`` MUST reach head on a genuinely fresh DB.

    Antes del fix, esto fallaba en ``0041_seed_configuracion_tolerancias``
    (Op 2) con ``ForeignKeyViolation`` porque ``prod.sucursal`` está
    vacía en cualquier DB recién creada — exactamente la situación de
    una instalación nueva o de un test aislado. Corre el subprocess
    directamente (no vía el fixture ``alembic_upgrade``, que absorbe
    cualquier fallo como SKIP) para que la regresión sea un FAIL, no
    un skip silencioso.
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = pg_dsn

    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_MIGRATIONS_PKG.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
    )

    assert proc.returncode == 0, (
        f"alembic upgrade head debe llegar a head en una DB fresca "
        f"(sin filas en prod.sucursal); REGRESSION si falla en 0041 "
        f"con ForeignKeyViolation sobre uuid_sucursal hardcodeado.\n"
        f"stdout:\n{proc.stdout[-3000:]}\n"
        f"stderr:\n{proc.stderr[-3000:]}"
    )


__all__ = ["test_alembic_upgrade_head_succeeds_on_fresh_db"]
