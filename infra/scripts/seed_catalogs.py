"""Seed catalog rows via the admin API.

Used for local smoke tests of the sync transport. The admin JWT must
be signed with the SAME secret bytes the cloud container mounts at
``/var/run/parkos/jwt_private.pem`` (set by the docker-compose secrets
volume).

Usage:
    cd backend
    PARKOS_JWT_KEY_PATH=../infra/deploy/secrets/jwt_private.pem \
    uv run python ../infra/scripts/seed_catalogs.py --cloud-api-url http://localhost:8000 \
        --table tipos-vehiculo --rows 'carro,moto,bicicleta,patineta'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid as uuid_lib
from pathlib import Path


def mint_admin_jwt(jwt_key_path: Path, branch_uuid: uuid_lib.UUID, cloud_dsn: str | None = None) -> str:
    """Mint an admin- JWT signed with the bytes of ``jwt_key_path``.

    If ``cloud_dsn`` is provided, looks up an existing admin user from
    ``prod.usuarios`` so the JWT subject matches a row with the
    required permissions. The permission check is performed live against
    the DB, so a JWT signed with a random uuid has zero permissions.
    """
    os.environ["PARKOS_JWT_KEY_PATH"] = str(jwt_key_path)

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "packages" / "parkos_core" / "src"))

    subject_uuid = uuid_lib.uuid4()
    if cloud_dsn:
        import psycopg
        with psycopg.connect(cloud_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (pu.vigente_hasta IS NULL) u.uuid
                    FROM prod.usuarios u
                    JOIN prod.permisos_usuario pu ON pu.uuid_usuario = u.uuid
                    JOIN prod.permisos p ON p.uuid = pu.uuid_permiso
                    WHERE u.email = 'admin@parkos.local' AND p.permiso = 'config_catalogo'
                    AND pu.vigente_hasta IS NULL
                    ORDER BY pu.vigente_hasta IS NULL
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if row:
                    subject_uuid = row[0]

    from parkos_core.auth.tokens import issue_token

    claims = {
        "rol": "admin",
        "sucursales_permitidas": [str(branch_uuid)],
        "permissions": ["config_catalogo"],
    }
    return issue_token(
        subject_uuid=subject_uuid,
        issuer="admin-test",
        claims=claims,
    )


def post_row(cloud_api_url: str, jwt: str, table: str, body: dict, branch_uuid: uuid_lib.UUID) -> dict:
    """POST a catalog row to the admin endpoint."""
    url = f"{cloud_api_url}/api/v1/catalogos/{table}"
    headers = {
        "Authorization": f"Bearer {jwt}",
        "X-Sucursal-Context": str(branch_uuid),
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body_text}") from e


def get_rows(cloud_api_url: str, jwt: str, table: str) -> list:
    """GET all rows for a catalog table."""
    url = f"{cloud_api_url}/api/v1/catalogos/{table}?limit=200"
    headers = {"Authorization": f"Bearer {jwt}"}
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("items", [])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud-api-url", default="http://localhost:8000")
    parser.add_argument("--cloud-dsn", default="postgresql://parkos:parkos@localhost:5432/parkos")
    parser.add_argument("--jwt-key-path", required=True)
    parser.add_argument("--branch-uuid", required=True)
    parser.add_argument("--table", default="tipos-vehiculo")
    parser.add_argument("--rows", required=True, help="Comma-separated values to insert")
    args = parser.parse_args()

    branch_uuid = uuid_lib.UUID(args.branch_uuid)
    jwt = mint_admin_jwt(Path(args.jwt_key_path), branch_uuid, cloud_dsn=args.cloud_dsn)

    rows = [r.strip() for r in args.rows.split(",") if r.strip()]
    print(f"== POSTing {len(rows)} rows to /catalogos/{args.table} ==")
    created = []
    for row_value in rows:
        body = {"tipo": row_value}
        try:
            resp = post_row(args.cloud_api_url, jwt, args.table, body, branch_uuid)
            print(f"  OK: {row_value} -> uuid={resp.get('uuid')}")
            created.append(resp)
        except RuntimeError as e:
            print(f"  FAIL: {row_value} -> {e}")

    print(f"\n== GETting current rows from /catalogos/{args.table} ==")
    current = get_rows(args.cloud_api_url, jwt, args.table)
    for row in current:
        print(f"  - {row.get('tipo')}  uuid={row.get('uuid')[:8]}...  estado={row.get('estado')}")
    print(f"\nTotal rows in cloud: {len(current)}")

    return 0 if len(created) == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
