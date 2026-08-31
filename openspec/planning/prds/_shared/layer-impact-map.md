# Layer Impact Map — canonical layer list

> Each PRD's `## Layer-by-Layer Impact` section addresses the layers that this
> specific table actually touches. This doc is the canonical reference of all
> possible layers.

## Layers

| # | Layer | Path | Owner |
|---|---|---|---|
| 1 | DB schema | `backend/packages/parkos_core/migrations/` | SQLAlchemy + Alembic |
| 2 | DB triggers | `0001_initial_schema.py` + per-iteration migrations | Alembic + PL/pgSQL |
| 3 | DB partitioning | `pg_partman` setup in `infra/postgres/init/` | DBA |
| 4 | DB hash-chain | per-iteration verifier + genesis rows | backend |
| 5 | DB audit constraints | REVOKE statements + session guards | backend |
| 6 | API admin router | `backend/packages/api_admin/.../routers/` | FastAPI |
| 7 | API sucursal router | `backend/packages/api_sucursal/.../routers/` | FastAPI |
| 8 | API Pydantic schemas | `backend/packages/parkos_core/schemas/` | Pydantic v2 |
| 9 | API auth/tenancy | `backend/packages/parkos_core/auth/`, `parkos_core/db/tenancy.py` | JWT three issuers |
| 10 | Sync cloud→branch | `backend/packages/job_sync_cloud/...` | sync worker |
| 11 | Sync branch→cloud | `backend/packages/job_sync_sucursal/...` | sync worker |
| 12 | Sync queue/conflict | `backend/packages/parkos_core/sync/` | queue_processor + conflict_policy |
| 13 | web_admin UI | `apps/web_admin/src/` | React 18 + shadcn |
| 14 | web_sucursal UI | `apps/web_sucursal/src/` | React 18 + shadcn |
| 15 | UI design system | `apps/ui-kit/src/` | shadcn + Tailwind |
| 16 | UI state | Zustand stores per domain | frontend |
| 17 | UI i18n | `apps/{web_admin,web_sucursal}/src/locales/es-CO/` | i18next |
| 18 | UI a11y | axe-core CI + WCAG 2.1 AA checks | frontend + CI |
| 19 | PWA offline | `vite-plugin-pwa` + IndexedDB shell | frontend |
| 20 | Observability/logs | structlog (Python), pino (TS) | observability |
| 21 | Observability/metrics | Prometheus counters per table | observability |
| 22 | Observability/traces | OpenTelemetry spans per request | observability |
| 23 | Observability/alerts | Prometheus alert rules + `alerta` table rows | observability |
| 24 | CI/test | `pytest` + `@axe-core/playwright` | testing |
| 25 | CI/lint | ruff + mypy + eslint | linting |
| 26 | CI/typecheck | mypy strict (Python) + `tsc --noEmit` (TS) | type-checking |
| 27 | CI/migration pre-flight | `alembic upgrade --sql` per `config.yaml` `rules.tasks` | CI |
| 28 | Docker/compose | `Dockerfile`, `docker-compose.{cloud,branch}.yml` | docker |
| 29 | DIAN provider | `parkos_core/dian/cloud/dispatcher.py` (cloud-only) | DIAN |
| 30 | Workers (cron) | `workers/{hash_chain_verifier,dian_dispatcher}/entrypoint.sh` | cloud-only |
| 31 | Docs/API | OpenAPI auto-generated from FastAPI | docs |
| 32 | Docs/architecture | `docs/architecture.md` | docs |
| 33 | Docs/DIAN compliance | `docs/dian-compliance.md` | docs |
| 34 | Docs/sync flow | `docs/sync-flow.md` | docs |
| 35 | Docs/branch setup | `docs/branch-setup.md` | docs |
| 36 | Security/JWT | three issuers (admin, operador, sync-agent) | auth |
| 37 | Security/RBAC | `permisos` + `permisos_usuario` | auth |
| 38 | Security/tenancy | `sucursales_permitidas` in admin JWT, single | tenancy |
| 39 | Security/encryption | TLS for sync; bcrypt for passwords | security |
| 40 | Migration/seed | `infra/postgres/init/*.sql` + Alembic seeds | infra |

## Per-table layer selection

A table's PRD specifies which of these 40 layers are impacted. Common patterns:

- **`[V]` parametrization** tables: layers 1, 6, 7, 8, 10, 12, 13, 15, 16, 17, 20, 24, 25, 26, 28, 31, 36, 37, 38.
- **`[V]` user-facing** tables (clientes, vehiculos, etc.): same + 14.
- **`[L-E]` event** tables: layers 1, 6, 7, 10, 11, 12, 13, 14, 15, 16, 17, 20, 24, 28, 31.
- **`[L-W]` workflow** tables: layers 1, 6, 7, 10, 11, 12, 13, 14, 15, 16, 17, 20, 24, 28, 31.
- **`[L-S]` session** tables: layers 1, 6, 7, 8, 9, 10, 11, 20, 24, 28, 36.
- **`[A]` source-of-truth** tables: layers 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 16, 17, 20, 21, 22, 23, 24, 28, 31.
- **`[A]` hash-chain** tables (log_transaccional, revocacion_factura): all `[A]` layers + dedicated verifier (worker + cron).