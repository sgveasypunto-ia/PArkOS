# infra/deploy/secrets/

This directory holds local-dev secrets used by `docker compose up -d`.

**DO NOT commit the actual files** — `.gitignore` excludes `*.pem`,
`*.jwt`, and `factus_token`.

## Required files

| File                       | What                                          | How to create |
|----------------------------|-----------------------------------------------|---------------|
| `jwt_private.pem`          | HS256 secret used by the project's JWT auth.   | `openssl genrsa -out jwt_private.pem 2048` |
| `jwt_public.pem`           | (Currently unused in HS256 dev mode.)         | `openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem` |
| `factus_token`             | Mock DIAN provider token (dev only).          | `echo "mock-factus-token" > factus_token` |
| `sync.jwt`                 | Per-branch sync-agent JWT (written by the     | `infra/scripts/bootstrap_pairing.py` |
|                            | pairing bootstrap).                            | |

Production deployments use Kubernetes secrets or Vault — these files are
local-dev only and never reach production. The compose files mount
`./secrets` into `/var/run/parkos:ro` so the containers can read them.
