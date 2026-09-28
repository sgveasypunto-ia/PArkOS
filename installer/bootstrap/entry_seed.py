"""PyInstaller entry point for the frozen `seed.exe` (HU-F23.2).

Seeds `tipos_vehiculo` via the REAL api-sucursal HTTP API (never raw SQL
for business-governed catalog rows) - the one exception is the seed admin
user + its `config_catalogo` permission grant, which is infrastructure
bootstrapping, not a business rule the catalog write path enforces. That
exception is not invented here: it is the exact same pattern already
proven in `infra/scripts/bootstrap_pairing.py`'s `ensure_admin_user()` /
`mint_admin_jwt()` (reused, not reimplemented - `issue_token()` is the
real function `jwt_issuer_guard.py` verifies against).

Scope note (verified against the real migrations, not assumed from
plan.md's own text): `tipo_arqueo` is already seeded by migration
`0040_seed_tipo_arqueo_codigos.py`, and `impuestos` (IVA) is already
seeded by migration `0026_seed_impuestos_iva_and_one_exit_per_ingreso.py`.
`config_caja` does not exist anywhere in the real backend (no model, no
schema, no migration) - plan.md's HU-F23.3 describes a feature that was
never built, not a seed step this installer can perform. This entry point
therefore seeds ONLY `tipos_vehiculo`, which genuinely has no seed
anywhere in the migrations.

Usage: seed.exe --database-url <migration DSN> --api-base-url <http://127.0.0.1:8000>
               --jwt-key-path <path> --sucursal-uuid <uuid>
"""
from __future__ import annotations

import argparse
import sys
import uuid as uuid_lib

import httpx


ADMIN_EMAIL = "installer-seed@parkos.local"
REQUIRED_PERMISSIONS = ("config_catalogo",)

# plan.md's HU-F23.2 describes a per-tipo `formato_placa_regex` field
# (CU-01 BR5) - verified against the real schema/model/ORM: that field
# does not exist anywhere in the backend (TiposVehiculoCreate has only
# `tipo`). Plate-format validation, if it exists, lives elsewhere (not
# this installer's concern) - seeding a field the schema would reject
# with 422 (`extra='forbid'`) is not an option.
TIPOS_VEHICULO = ["carro", "moto", "bicicleta", "patineta"]


def ensure_seed_admin(database_url: str) -> uuid_lib.UUID:
    """Idempotent INSERT of the installer's seed admin user + permission grant.

    Adapted from `infra/scripts/bootstrap_pairing.py::ensure_admin_user` -
    same INSERT shape, scoped down to just the one permission this seed
    step needs (`config_catalogo`).
    """
    import psycopg

    with psycopg.connect(database_url) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO prod.usuarios (
                    uuid, vigente_desde, vigente_hasta, estado,
                    created_at, created_by,
                    nombre, apellido, cedula, email, password_hash, rol,
                    fecha_cambio_password
                )
                VALUES (
                    gen_random_uuid(), NOW(), NULL, 'activo',
                    NOW(), NULL,
                    'Installer', 'Seed', 'installer-seed', %s, NULL, 'admin',
                    NULL
                )
                ON CONFLICT (cedula, vigente_desde) DO NOTHING
                RETURNING uuid
                """,
                (ADMIN_EMAIL,),
            )
            row = cur.fetchone()
            if row is not None:
                user_uuid = row[0]
            else:
                cur.execute(
                    "SELECT uuid FROM prod.usuarios WHERE email = %s LIMIT 1",
                    (ADMIN_EMAIL,),
                )
                row = cur.fetchone()
                assert row is not None, "seed admin user lookup failed"
                user_uuid = row[0]

            for code in REQUIRED_PERMISSIONS:
                cur.execute(
                    "SELECT uuid FROM prod.permisos WHERE permiso = %s LIMIT 1",
                    (code,),
                )
                prow = cur.fetchone()
                if prow is None:
                    print(f"WARNING: permission code {code!r} not in seed data; skipping")
                    continue
                permiso_uuid = prow[0]
                cur.execute(
                    """
                    INSERT INTO prod.permisos_usuario (
                        uuid, vigente_desde, vigente_hasta, estado,
                        created_at, created_by,
                        uuid_usuario, uuid_permiso
                    )
                    VALUES (
                        gen_random_uuid(), NOW(), NULL, 'activo',
                        NOW(), NULL,
                        %s, %s
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    (user_uuid, permiso_uuid),
                )
    return user_uuid


def mint_seed_jwt(user_uuid: uuid_lib.UUID, jwt_key_path: str, sucursal_uuid: uuid_lib.UUID) -> str:
    """Mint an `admin-` JWT - same `issue_token()` the backend itself uses
    to verify tokens (auth/tokens.py), not a hand-rolled implementation."""
    import os

    os.environ["PARKOS_JWT_KEY_PATH"] = jwt_key_path
    from parkos_core.auth.tokens import issue_token

    return issue_token(
        subject_uuid=user_uuid,
        issuer="admin-seed",
        claims={"rol": "admin", "sucursales_permitidas": [str(sucursal_uuid)]},
        expires_in=300,
    )


def seed_tipos_vehiculo(client: httpx.Client, sucursal_uuid: str) -> None:
    """Idempotent by our own check, not the API's: `create_endpoint` (router_
    factory.py) calls `close_and_insert(current_uuid=None, ...)`, a pure
    INSERT with no natural-key conflict handling - `vigente_desde` is
    freshly generated per call, so the `(tipo, vigente_desde)` UNIQUE
    constraint never fires on a re-run and a second POST would silently
    create a duplicate active row for the same `tipo`. GET first, skip
    what already exists (mirrors HU-F23.2's own re-run requirement)."""
    headers = {"X-Sucursal-Context": sucursal_uuid}
    existing = client.get("/api/v1/catalogos/tipos-vehiculo", params={"limit": 200}, headers=headers)
    existing_tipos = {item["tipo"] for item in existing.json().get("items", [])} if existing.status_code == 200 else set()

    created = 0
    for tipo in TIPOS_VEHICULO:
        if tipo in existing_tipos:
            continue
        resp = client.post("/api/v1/catalogos/tipos-vehiculo", json={"tipo": tipo}, headers=headers)
        if resp.status_code != 201:
            raise RuntimeError(f"tipos-vehiculo seed failed for {tipo!r}: {resp.status_code} {resp.text}")
        created += 1
    print(f"catalog.seed.ok tipos_vehiculo_created={created} tipos_vehiculo_already_present={len(existing_tipos)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--jwt-key-path", required=True)
    parser.add_argument("--sucursal-uuid", required=True)
    args = parser.parse_args()

    user_uuid = ensure_seed_admin(args.database_url)
    token = mint_seed_jwt(user_uuid, args.jwt_key_path, uuid_lib.UUID(args.sucursal_uuid))

    with httpx.Client(base_url=args.api_base_url, headers={"Authorization": f"Bearer {token}"}, timeout=10.0) as client:
        seed_tipos_vehiculo(client, args.sucursal_uuid)

    return 0


if __name__ == "__main__":
    sys.exit(main())
