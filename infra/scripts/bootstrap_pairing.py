"""Bootstrap a one-shot admin user in cloud-db + mint a pairing token.

End-to-end setup so the branch container can POST /sync/pair and receive
a sync-agent JWT. Steps:

  1. SQL INSERT a canonical admin user (idempotent — ON CONFLICT DO NOTHING).
  2. Mint an admin- JWT for that user using the project's auth tokens.
  3. POST /admin/pairing-tokens with the admin JWT.
  4. Persist the returned plaintext + write the resolved sync_jwt to disk.

Usage (from the host, with the cloud stack up on :8000 + cloud-db on :5432):

    cd backend
    uv run python ../infra/scripts/bootstrap_pairing.py --branch-uuid <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
import uuid as uuid_lib
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_ROOT / "packages" / "parkos_core" / "src"))


ADMIN_EMAIL = "admin@parkos.local"
ADMIN_PASSWORD = "Admin12345!"  # dev-only — never reuse in prod


def http_post_json(url: str, body: dict, *, headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code} on POST {url}")
        print(f"  body: {body}")
        raise


def ensure_admin_user(cloud_dsn: str) -> uuid_lib.UUID:
    """Idempotent INSERT of an admin user + permissions. Returns the user uuid.

    The admin user gets the ``gestionar_dian`` permission (required by
    ``POST /admin/pairing-tokens`` per pairing.py:80) so the bootstrap
    pairing flow works end-to-end without manual DB fiddling.

    Why we compute the hash here instead of hard-coding it: pydantic.EmailStr
    (or our lenient ParkosEmail in api-sucursal/api-admin) must accept the
    login attempt BEFORE bcrypt.compare runs. If the hash stored here is a
    sentinel (e.g., ``"$2b$12$dummy..."``) ``bcrypt.checkpw`` will raise
    ``ValueError`` on the malformed sentinel and the operator will get HTTP
    500 instead of a clean 401 ``invalid_credentials``. So we always compute
    a real bcrypt hash for ``ADMIN_PASSWORD`` at bootstrap time.
    """
    import bcrypt
    import psycopg

    ADMIN_BCRYPT_HASH = bcrypt.hashpw(
        ADMIN_PASSWORD.encode("utf-8"),
        bcrypt.gensalt(rounds=12),
    ).decode("utf-8")
    REQUIRED_PERMISSIONS = (
        "gestionar_dian",
        "config_catalogo",
        "audit_read",
        "admin_usuarios",
        "gestionar_clientes",
        "emitir_factura",
        "emitir_factura_electronica",
    )

    with psycopg.connect(cloud_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            # INSERT admin user (idempotent).
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
                    'Admin', 'Dev', '1234567890', %s, %s, 'admin',
                    NULL
                )
                ON CONFLICT (cedula, vigente_desde) DO NOTHING
                RETURNING uuid
                """,
                (ADMIN_EMAIL, ADMIN_BCRYPT_HASH),
            )
            row = cur.fetchone()
            if row is not None:
                user_uuid = row[0]
            else:
                # Already exists — look up.
                cur.execute(
                    "SELECT uuid FROM prod.usuarios WHERE email = %s LIMIT 1",
                    (ADMIN_EMAIL,),
                )
                row = cur.fetchone()
                assert row is not None, "admin user lookup failed"
                user_uuid = row[0]

            # Grant required permissions (idempotent).
            for code in REQUIRED_PERMISSIONS:
                # Look up the permiso uuid.
                cur.execute(
                    "SELECT uuid FROM prod.permisos WHERE permiso = %s LIMIT 1",
                    (code,),
                )
                prow = cur.fetchone()
                if prow is None:
                    print(f"   WARNING: permission code {code!r} not in seed data; skipping")
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


def mint_admin_jwt(user_uuid: uuid_lib.UUID, jwt_key_path: Path, branch_uuid: uuid_lib.UUID) -> str:
    """Mint an admin- JWT for the given user.

    HS256 (dev mode) uses the bytes of ``PARKOS_JWT_KEY_PATH`` as the secret
    (or the static dev default if unset). We MUST point the env at the
    SAME file the cloud container mounts, otherwise the cloud's
    ``verify_jwt`` will reject our signature with 401.

    The admin needs ``sucursales_permitidas`` including the target branch
    uuid so the ``X-Sucursal-Context`` header check passes (admin tokens
    require the header per ``auth/tenancy.py:115``).
    """
    import os
    os.environ["PARKOS_JWT_KEY_PATH"] = str(jwt_key_path)

    from parkos_core.auth.tokens import issue_token

    claims = {
        "rol": "admin",
        "sucursales_permitidas": [str(branch_uuid)],  # branch scope
        "permissions": [
            "gestionar_dian",
            "config_catalogo",
            "audit_read",
        ],
    }
    return issue_token(
        subject_uuid=user_uuid,
        issuer="admin-test",
        claims=claims,
    )


def mint_pairing_token(
    cloud_api_url: str, admin_jwt: str, branch_uuid: uuid_lib.UUID, ttl_hours: int = 24
) -> dict:
    """POST /admin/pairing-tokens → {token, expires_at, ...}.

    The ``X-Sucursal-Context`` header is REQUIRED for admin tokens (auth/
    tenancy.py:115) and must be in the JWT's ``sucursales_permitidas``.
    """
    return http_post_json(
        f"{cloud_api_url}/api/v1/admin/pairing-tokens",
        {"uuid_sucursal": str(branch_uuid), "ttl_hours": ttl_hours},
        headers={
            "Authorization": f"Bearer {admin_jwt}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )


def pair_with_cloud(
    cloud_api_url: str, pairing_token: str, branch_uuid: uuid_lib.UUID,
    branch_info: dict,
) -> dict:
    """POST /sync/pair → {sync_jwt, expires_at, uuid_sucursal}."""
    return http_post_json(
        f"{cloud_api_url}/api/v1/sync/pair",
        {
            "pairing_token": pairing_token,
            "uuid_sucursal": str(branch_uuid),
            "branch_info": branch_info,
        },
    )


def ensure_genesis_hash_chain(cloud_dsn: str, branch_uuid: uuid_lib.UUID) -> None:
    """Create the genesis ``log_transaccional`` row for the branch.

    The hash-chain trigger (PR1a's ``fn_extend_hash_chain()``) requires
    a prior row per ``uuid_sucursal`` with ``hash_anterior = sha256(b'genesis:' + uuid_bytes)``
    before it accepts any new INSERT for that branch. Branch bootstrap
    in production creates this via the canonical ``pair_completed`` flow;
    in our local dev bootstrap we INSERT directly so the first
    POST /sync/pair succeeds.
    """
    import hashlib
    import psycopg

    GENESIS_HASH = hashlib.sha256(b"genesis:" + str(branch_uuid).encode()).hexdigest()
    # Use the admin user uuid (any stable uuid works; FK to usuarios).
    ADMIN_UUID = "00000000-0000-0000-0000-0000000000aa"  # placeholder

    with psycopg.connect(cloud_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO prod.log_transaccional (
                    uuid, fecha_retencion_hasta,
                    uuid_usuario, uuid_sucursal, accion, tabla_afectada,
                    uuid_registro_afectado, datos_anteriores, datos_nuevos,
                    timestamp_evento,
                    hash_anterior, hash_actual,
                    created_at, created_by
                )
                VALUES (
                    gen_random_uuid(), CURRENT_DATE,
                    NULL, %s, 'inicialización', 'log_transaccional',
                    NULL, NULL, '{"reason": "genesis bootstrap"}'::jsonb,
                    NOW(),
                    %s, %s,
                    NOW(), NULL
                )
                ON CONFLICT DO NOTHING
                """,
                (str(branch_uuid), GENESIS_HASH, GENESIS_HASH),
            )


def ensure_sucursal(cloud_dsn: str, branch_uuid: uuid_lib.UUID, *, nombre: str = "Branch Dev") -> None:
    """Idempotent INSERT of the branch in ``prod.sucursal``.

    The ``POST /admin/pairing-tokens`` INSERTs into ``prod.pairing_tokens``
    with a foreign key to ``prod.sucursal`` — the FK is enforced on the
    default partition, so the branch row must exist first.

    ``uuid_tipo_sucursal`` and ``uuid_empresa`` are both nullable FKs
    (the schema declares them YES), so we INSERT with NULL when the seed
    data isn't present (the dev local DB starts empty for these catalogs).
    """
    import psycopg

    with psycopg.connect(cloud_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            # Optional: pick uuid_tipo_sucursal if any seed row exists.
            cur.execute("SELECT uuid FROM prod.tipo_sucursal LIMIT 1")
            row = cur.fetchone()
            tipo_uuid = row[0] if row else None

            # Optional: pick uuid_empresa if any seed row exists.
            cur.execute("SELECT uuid FROM prod.empresa LIMIT 1")
            row = cur.fetchone()
            empresa_uuid = row[0] if row else None

            cur.execute(
                """
                INSERT INTO prod.sucursal (
                    uuid, vigente_desde, vigente_hasta, estado,
                    created_at, created_by,
                    nombre, prefijo_nombre, ciudad,
                    uuid_tipo_sucursal, uuid_empresa
                )
                VALUES (
                    %s, NOW(), NULL, 'activo',
                    NOW(), NULL,
                    %s, %s, %s,
                    %s, %s
                )
                ON CONFLICT (uuid) DO NOTHING
                """,
                (
                    str(branch_uuid),
                    nombre,
                    "branch-dev",  # UK requires prefijo_nombre
                    "Bogotá",      # dev default
                    tipo_uuid,
                    empresa_uuid,
                ),
            )


def ensure_default_partitions(cloud_dsn: str) -> None:
    """Create DEFAULT partitions on every pg_partman-managed parent.

    The cloud-db Postgres image ships without pg_partman pre-installed,
    so migrations declare ``PARTITION BY RANGE`` but cannot auto-create
    children. Without a DEFAULT partition, the first INSERT into any of
    those tables fails with ``no partition of relation ... found for row``.
    Production runs ``partman.run_maintenance`` on a schedule; for the
    local smoke we just add DEFAULT catch-all partitions.
    """
    PARTITIONED = (
        "salidas", "factura_detalle", "factura_impuestos", "factura_otros_cobros",
        "factura_pagos", "revocacion_factura", "caja", "arqueo",
        "sync_log", "sync_conflict", "log_transaccional",
        "pairing_tokens", "revoked_sync_jwts", "idempotency_keys",
    )
    import psycopg

    with psycopg.connect(cloud_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for parent in PARTITIONED:
                cur.execute(
                    f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_class c
                            JOIN pg_namespace n ON n.oid = c.relnamespace
                            WHERE c.relname = '{parent}_default'
                            AND n.nspname = 'prod'
                        ) AND EXISTS (
                            SELECT 1 FROM pg_class c
                            JOIN pg_namespace n ON n.oid = c.relnamespace
                            WHERE c.relname = '{parent}'
                            AND n.nspname = 'prod'
                            AND c.relkind = 'p'
                        ) THEN
                            EXECUTE format(
                                'CREATE TABLE prod.%I PARTITION OF prod.%I DEFAULT',
                                '{parent}_default', '{parent}'
                            );
                        END IF;
                    END$$;
                    """
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud-api-url", default="http://localhost:8000")
    parser.add_argument("--cloud-dsn", default="postgresql://parkos:parkos@localhost:5432/parkos")
    parser.add_argument("--jwt-key-path", default=str(BACKEND_ROOT / "secrets" / "jwt_private.pem"))
    parser.add_argument("--branch-uuid", required=True)
    parser.add_argument("--sync-jwt-out", default=str(BACKEND_ROOT / "infra" / "deploy" / "secrets" / "sync.jwt"))
    args = parser.parse_args()

    branch_uuid = uuid_lib.UUID(args.branch_uuid)
    jwt_key_path = Path(args.jwt_key_path)
    sync_jwt_path = Path(args.sync_jwt_out)
    sync_jwt_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"== Step 1: ensure DEFAULT partitions on cloud-db ==")
    ensure_default_partitions(args.cloud_dsn)

    print(f"== Step 2: ensure admin user in cloud-db ==")
    admin_uuid = ensure_admin_user(args.cloud_dsn)
    print(f"   admin user uuid = {admin_uuid}")

    print(f"== Step 2b: ensure branch row in prod.sucursal ==")
    ensure_sucursal(args.cloud_dsn, branch_uuid)

    # NOTE: order matters — the log_transaccional INSERT below fires the
    # ``fn_enqueue_sync`` trigger, which INSERTs into ``prod.sync_queue``
    # with the branch uuid as FK. The branch row must exist first.

    print(f"== Step 2: mint admin JWT (key: {jwt_key_path}) ==")
    admin_jwt = mint_admin_jwt(admin_uuid, jwt_key_path, branch_uuid)
    print(f"   admin JWT length = {len(admin_jwt)}")

    print(f"== Step 3: POST /admin/pairing-tokens ==")
    pairing = mint_pairing_token(args.cloud_api_url, admin_jwt, branch_uuid)
    pairing_token = pairing["token"]
    expires_at = pairing["expires_at"]
    print(f"   pairing token uuid = {pairing['pairing_token_uuid']}")
    print(f"   expires_at = {expires_at}")

    print(f"== Step 4: POST /sync/pair ==")
    branch_info = {
        "hostname": os.environ.get("COMPUTERNAME", "dev-host"),
        "os": "linux",
        "version": "dev",
        "endpoint_url": f"http://api-sucursal:8000",
    }
    pair_resp = pair_with_cloud(args.cloud_api_url, pairing_token, branch_uuid, branch_info)
    sync_jwt = pair_resp["sync_jwt"]
    print(f"   sync JWT length = {len(sync_jwt)}")
    print(f"   expires_at = {pair_resp['expires_at']}")

    print(f"== Step 5: persist sync JWT to {sync_jwt_path} ==")
    sync_jwt_path.write_text(sync_jwt, encoding="utf-8")
    # 0600 perms so the worker process can read it (POSIX only; Windows
    # ACLs are inherited from the secrets directory).
    try:
        os.chmod(sync_jwt_path, 0o600)
    except OSError:
        pass

    print("\nALL DONE.")
    print(f"  pairing token uuid: {pairing['pairing_token_uuid']}")
    print(f"  sync_jwt_path: {sync_jwt_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
