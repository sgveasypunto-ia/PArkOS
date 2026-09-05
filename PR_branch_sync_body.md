## What

Closes the 3 gaps discovered during the local cloud + branch end-to-end
deployment:

1. **JWT issuer prefix detection (auth/jwt_issuer_guard.py)** — the
   previous ``prefix = iss.split("-")[0] + "-"`` only kept the FIRST
   dash-separated segment, so a valid ``sync-agent-cloud`` token was
   always rejected as ``wrong_issuer: unknown_issuer_prefix=sync-``.
   Replaced with the LONGEST matching prefix from ISSUER_PREFIXES
   (the existing canonical list ``admin-``, ``operador-``,
   ``sync-agent-`` is now matched correctly).

2. **Redundant issuer check (api/v1/sync_router.py:264)** — same bug
   as above but in the sync router's local prefix assertion (after
   ``verify_jwt`` already accepted the token). Removed the redundant
   duplicate check; rely on the canonical guard in ``verify_jwt``.

3. **End-to-end pairing bootstrap (infra/scripts/bootstrap_pairing.py)** —
   adds a single-script bootstrap that:
     - Creates DEFAULT partitions on every pg_partman-managed parent
       in ``prod.*`` (cloud-db ships without pg_partman installed so
       migrations create the parent but not the children).
     - Idempotent INSERT of an admin user in ``prod.usuarios`` with all
       permissions needed by ``/admin/pairing-tokens``
       (``gestionar_dian`` + 6 others).
     - Idempotent INSERT of the branch in ``prod.sucursal`` (FK to
       ``pairing_tokens``).
     - Inserts the ``log_transaccional`` genesis row for the branch
       (the hash-chain trigger rejects any INSERT without a prior
       genesis row per ``uuid_sucursal``).
     - Mints an admin JWT signed with the SAME secret bytes the cloud
       container mounts at ``/var/run/parkos/jwt_private.pem``.
     - POST /admin/pairing-tokens → pairing plaintext.
     - POST /sync/pair → long-lived sync-agent JWT.
     - Persists the sync JWT to disk at ``infra/deploy/secrets/sync.jwt``
       (the branch worker's ``PARKOS_SYNC_JWT_PATH``).

4. **Local combined stack (infra/deploy/docker-compose.local.yml)** —
   adds a third compose file that runs cloud + one branch on the same
   docker network so ``api-admin`` resolves as a hostname (the
   branch's ``PARKOS_CLOUD_API_URL=http://api-admin:8000``).

5. **Secrets docs (infra/deploy/secrets/README.md)** — documents the
   dev-only secret layout and ``openssl`` commands to regenerate.
   ``.gitignore`` excludes the actual ``*.pem`` / ``*.jwt`` / token
   files so devs never commit real keys.

## Verification (end-to-end)

- ``docker compose -f infra/deploy/docker-compose.cloud.yml --env-file infra/deploy/.env.cloud up -d --build``
  → 3 services HEALTHY (cloud-db, api-admin, job-sync-cloud)
- ``docker compose -f infra/deploy/docker-compose.local.yml --env-file infra/deploy/.env.local up -d --build``
  → 6 services HEALTHY (cloud stack + branch stack on shared
  ``parkos-cloud_parkos-cloud-net`` network)
- ``python infra/scripts/bootstrap_pairing.py --branch-uuid 360357ea-3564-4843-a680-7e821dd26383``:
  - admin user uuid = 332ab66f-c33c-4cae-8e57-a20923508315
  - pairing token uuid = d1d43202-85d5-4b0d-80bf-c574cb1b4012
  - sync JWT length = 440 (saved to ``infra/deploy/secrets/sync.jwt``)
- Branch worker logs (after the fix):
  - ``worker_started name=sync_sucursal``
  - ``pull_applied applied=0 conflicts=0 errors=0 next_seq=0 pulled=0``
  - JWT 401 errors are GONE (was failing every poll before this PR)
- ``POST /api/v1/sync/push`` with the bootstrap JWT returns 207 (was
  401 before this PR)

📍 Closes the sync transport wiring for the local combined stack.
