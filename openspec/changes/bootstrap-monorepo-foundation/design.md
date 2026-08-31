# Design: Bootstrap Monorepo Foundation

## Technical Approach

Two workspaces, one image, one migration. `backend/` declares `[tool.uv.workspace] members=["packages/*"]`; `apps/` declares npm workspaces. One multi-stage `Dockerfile` (`BUILD_TARGET` + `SERVICE_NAME`) deploys as any of four Python roles. `infra/docker/entrypoint.sh`: `rol_app precheck → alembic upgrade head → REVOKE/trigger verifier → exec CMD`. **DIAN processing is cloud-only**: branches import `parkos_core.dian` for shape parity but never invoke the dispatcher.

## Architecture Decisions

| # | Choice | Why |
|---|---|---|
| 1 | uv workspace at `backend/` | One lockfile. |
| 2 | Alembic at `parkos_core/migrations/` | `env.py` imports plain. |
| 3 | `init/` = roles + extensions ONLY | Pre-Alembic. |
| 4 | One `Dockerfile` w/ `BUILD_TARGET`+`SERVICE_NAME` | Same image. |
| 5 | Skip BFF for MVP | Revisit at ≥50 branches. |
| 6 | Isolated `workers/{hash_chain_verifier,dian_dispatcher}` | Three cadences. |
| 7 | HTTP polling only | <100 branches. |
| 8 | `docker pull` + `compose up -d` | Git-clone fallback. |
| 9 | 6 chained PRs; PR2 `size:exception` | 2500–4000+ LOC. |
| 10 | REVOKE on 11 `[A]` + trigger | Defense in depth. |
| 11 | Three JWT key sets | Sync lifetime differs. |
| 12 | Cloud preserves branch chain | DIAN evidence. |
| 13 | **DIAN centralized in cloud** | Branches never contact DIAN; `empresa.consecutivo_actual` atomic in cloud; `dian_dispatcher` cloud-only; `factura_electronica`+`revocacion_factura` rows written ONLY in cloud. |
| 14 | **DIAN numeration = cloud-first w/ sync back** | Online: `api_sucursal` POSTs `/facturas/procesar` → real `numero_oficial`. Offline: branch prints `preliminar`, enqueues `factura`; cloud assigns real number, `SyncBackEvent` flows back; `reimpresion_ticket` enabled post-sync-back. |

## Data Flow

```
Cloud:  initdb -> 01_roles -> 02_extensions -> precheck
        -> alembic -> verifier -> exec
Branch: initdb -> precheck -> alembic -> verifier
        -> POST /sync/pair -> JWT -> exec uvicorn
Sync:   sync_queue -> job_sync_sucursal -> POST /push
        -> job_sync_cloud: hash_anterior==prev.hash_actual
        -> INSERT log_transaccional + sync_log

Factura -> DIAN (TWO PATHS; cloud-only writes):
  Online:  api_sucursal POST /facturas/procesar
           -> consecutivo_actual++ -> INSERT
           factura_electronica -> 200 {numero_oficial}
           -> branch prints REAL.
  Offline: ProvisionalNumber(prefix,uuid) -> enqueue factura
           -> job_sync_cloud -> dian_dispatcher -> DIAN
           -> SyncBackEvent -> parametrization pull fills
           uuid_factura_electronica + numero_oficial
           -> reimpresion_ticket enabled.
```

## File Changes

- **PR1**: `Dockerfile`, `.dockerignore`, `docker-compose.{cloud,branch}.yml`, `.env.{cloud,branch}.example`, `backend/pyproject.toml`+`uv.lock`.
- **PR2** (`size:exception`): `infra/postgres/init/{01_roles,02_extensions}.sql`, `parkos_core/migrations/{env.py,script.py.mako,versions/0001_initial_schema.py}`, `infra/docker/entrypoint.sh`.
- **PR3** (`parkos_core`): `models/{V,L_E,L_W,L_S,A}`, `schemas`, `db`, `auth`. **`dian/` splits: `common/` (shared), `cloud/` (`FacturaElectronicaBuilder`, `dian_dispatcher`, `atomic_next_consecutivo`), `branch/` (`ProvisionalNumber` consumer).**
- **PR4** (`api_*`): `api_{admin,sucursal}/...`, `parkos_core/auth/jwt_three_issuers.py`, `routers/{auth,health}.py`. **`api_admin/routers/facturas.py` adds `POST /facturas/procesar`; `api_sucursal/routers/facturas.py` adds `POST /facturas` + `GET /facturas/{uuid}/numero-oficial`.**
- **PR5** (sync+dispatcher): `job_sync_{cloud,sucursal}/...`, `parkos_core/sync/{queue_processor,conflict_policy,pairing,sync_back}.py`, `workers/{hash_chain_verifier,dian_dispatcher}/entrypoint.sh`, `infra/sync_policy.yaml`. **Cloud-only `dian_dispatcher` drains DIAN queue; `job_sync_cloud` writes `SyncBackEvent`.**
- **PR6** (PWA): `apps/{...}`, `apps/ui-kit/{...}`, `apps/{web_admin,web_sucursal}/{...}`. **`web_sucursal`: `preliminar` badge + disabled `reimpresion_ticket`.**

## Interfaces / Contracts

**`parkos_core`**: `models/[V|L_E|L_W|L_S|A]/` per `config.yaml`. `db.get_session()` async. `auth.issue_token(scope, claims)` w/ `scope ∈ {admin,operador,sync_agent}`.

**`dian/` split** (#13, #14):
- `dian/common/`: `NumerationMode = Literal["online","offline-preliminar","sync-back-pending"]`; `ProvisionalNumber(prefix, uuid) -> str` (deterministic); `SyncBackEvent(uuid_factura, numero_oficial, dian_response_at)`.
- `dian/cloud/`: `FacturaElectronicaBuilder`, `dian_dispatcher`, `atomic_next_consecutivo(empresa_id)`.
- `dian/branch/`: emits business `factura` w/ `numero_temporal` only.

**JWT**: `kid` prefix `admin-|operador-|sync-agent-`; grace `JWT_OVERLAP_HOURS=24`. `.env.branch`: `BRANCH_UUID`, `PAIRING_TOKEN`, `CLOUD_API_URL`; missing → exit 1. DIAN retention / Hash-chain genesis / Verifier: see specs; ratified in Open Questions.

## Testing Strategy

`config.yaml testing.strict_tdd: false`; `reconfigure_when` fires after PR1.

- **Schema**: `alembic check`; `\dt prod.*` = 45; 11 `_inmutable` + 2 `_ls_session_update_guard` triggers.
- **Container**: `compose -f docker-compose.branch.yml up -d --wait`; `/health` → 200; verifier exit 0.
- **Auth**: `admin`→`api_sucursal /auth/login`→401; `operador`→`api_admin`→401; `sync_agent`→any `api_*`→401.
- **DIAN**: branch import of `dian.cloud.dian_dispatcher` fails; container ONLY in `docker-compose.cloud.yml`. mock cloud 200 → `POST /facturas` returns `numero_oficial`; unreachable → `numero_temporal` until `GET /facturas/{uuid}/numero-oficial` syncs.
- **PWA**: `tsc --noEmit` clean; `playwright --grep WCAG` exit 0. pytest/vitest deferred.

## Threat Matrix

| Boundary | Response | RED test |
|---|---|---|
| Shell commands | `set -euo pipefail`, `${VAR:?}` | `PAIRING_TOKEN=""` → exit 1 |
| Executable-file classification | `chmod +x`; `shellcheck` | POSIX |
| Routing (DIAN) | `api_sucursal /facturas`: online→cloud, offline→`dian.branch` | Mocked 500 → fallback; 200 → real |
| Subprocesses / VCS / Process | N/A | — |

## Migration / Rollout

| PR | Scope | Budget |
|---|---|---|
| PR1 | Infra skeleton | ~300 LOC |
| PR2 | `init/*.sql` + `0001_initial_schema.py` + `entrypoint.sh` | **`size:exception`** (~800–1500) |
| PR3 | `parkos_core` + `dian/{common,cloud,branch}/` | ~350 |
| PR4 | `api_admin`+`api_sucursal` + JWT + `/facturas{,/procesar,/uuid/numero-oficial}` | ~350 |
| PR5 | `job_sync_*` + `dian_dispatcher` + `infra/sync_policy.yaml` | ~400 |
| PR6 | PWA + axe-core CI + preliminar badge | ~400 |

Branch rollout: `docker pull` + `docker compose -f docker-compose.branch.yml up -d`. **Constraint: PR5 cloud `dian_dispatcher` MUST be up BEFORE branches — else `/facturas/procesar` hangs.**

## Open Questions

**Resolved**: GHCR → `ghcr.io/easypunto/parkos:vX.Y.Z`. Hash-chain genesis → `encode(sha256(concat(uuid_sucursal, ts_evento, 'GENESIS')), 'hex')`. DIAN retention → per-row `fecha_retencion_hasta`. Workers `HEALTHCHECK start_period` → `60s`.

**Remaining**: (a) Preliminar-number UX format — defer `web_sucursal`. (b) Sync-back transport: pull vs `/sync/dian-numbers`? Default pull — confirm PR5. (c) `reimpresion_ticket` blocking: PWA/API? Default both — confirm PR6.