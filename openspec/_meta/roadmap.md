# easypunto_parkos — System Roadmap

> Living document. Maps every change in the parking-lot management system to the
> AUDIT-FIRST data model. Authoritative source: `modelo_datos_er.mmd`.
>
> **Organization**: Foundation walking skeleton + vertical-slicing iterations.
> Each iteration is atomic, end-to-end, and crosses ALL components
> (UI admin + UI sucursal + API admin + API sucursal + sync + DB). See
> `iteration-plan.md` for per-iteration task breakdown.

## Why vertical slicing (not layers)

| | Layer-based (rejected) | Vertical slicing (adopted) |
|---|---|---|
| Time-to-first-feature | After all 6 layers | After IT-1 |
| Risk per PR | Wide (DB or API or sync alone) | Narrow (one feature, all components) |
| Review focus | "How does this layer fit?" | "Does this case work end-to-end?" |
| Feedback loop | 6-PR cycle | 1-iteration cycle |
| Rollback granularity | Layer-level | Feature-level |

## Phases

### Phase 0 — Foundation Walking Skeleton (2 PRs)

Schema + infra + Docker + minimal `parkos_core`. After this phase the system boots end-to-end (cloud + branch + DB + Alembic), serves `/health`, and applies the full schema.

| PR | Scope | Budget | Notes |
|---|---|---|---|
| F1 | infra skeleton + `Dockerfile` + compose + `0001_initial_schema.py` + `/health` + JWT three issuers stub | **`size:exception`** (~800–1500 LOC) | The schema must be one PR (single `alembic head` invariant). 49 tables + 11 REVOKE + 11 triggers + 2 session guards + 8 `pg_partman.create_parent` + hash-chain genesis + idempotent seed. |
| F2 | `dian/common,cloud,branch/` stubs + `sync/` stubs + JWT three issuers production-ready + `infra/sync_policy.yaml` + `apps/ui-kit/` | ~400 LOC | Cross-audience JWT guard active. Branch import of `dian.cloud` raises `ImportError`. |

After F2 the system is ready to deliver business features one iteration at a time.

### Phase 1 — Authentication & Tenancy (vertical)

| Iteration | Atomic case | Components touched | Budget |
|---|---|---|---|
| **IT-1** | Login end-to-end (admin + operador) | `web_admin` + `web_sucursal` login UI; `api_admin` + `api_sucursal` `POST /auth/login`; cloud `job_sync_cloud` pushes users to assigned branches via `sync_queue`; `api_admin POST /sync/push`; branch `job_sync_sucursal` upserts locally; cross-audience JWT rejection | ~400 LOC |
| **IT-2** | Sucursales CRUD + pairing branch | Admin creates branch in `web_admin`; issues 24h pairing token; `web_sucursal` `PairingWizard` consumes token; branch receives long-lived `sync_agent` JWT | ~350 LOC |

### Phase 2 — Core Operations (vertical)

| Iteration | Atomic case | Components touched | Budget |
|---|---|---|---|
| **IT-3** | Ingreso de vehículo | `web_sucursal` `IngresoForm`; `api_sucursal POST /ingresos`; enqueue in `sync_queue`; `job_sync_sucursal` pushes; `api_admin POST /sync/push` validates hash chain and inserts in cloud; `web_admin` `IngresosList` filtered by branch | ~300 LOC |
| **IT-4** | Salida de vehículo | Symmetric to IT-3 with `salidas` `[A]` (REVOKE-enforced). Audit-FIRST enforcement verified via RED test | ~250 LOC |
| **IT-5** | Facturación (cloud-first + sync back) | `web_sucursal` `FacturacionForm`; online → calls `api_admin POST /facturas/procesar` (atomic `consecutivo_actual`); offline → `numero_temporal` + enqueue; `dian_dispatcher` (cloud-only) sends to DIAN; `SyncBackEvent` flows back via pull mode every 30s; `preliminar` badge flips to real; `reimpresion_ticket` gated | ~600 LOC |

### Phase 3 — Workflows (vertical)

| Iteration | Atomic case | Components touched | Budget |
|---|---|---|---|
| **IT-6** | Anulación de ingreso | Workflow chain `solicitada → aprobada → ejecutada` on `anulaciones` `[L-W]` (3 rows chained by `uuid_anulacion_padre`); admin-only `aprobar` + `ejecutar` | ~250 LOC |
| **IT-7** | Alertas operacionales | Trigger from `arqueo` (diferencia_arqueo), from `sync_log` (branch_offline), from sync failures; workflow chain `abierta → en_revision → resuelta` on `alerta` `[L-W]` | ~300 LOC |
| **IT-8** | Reclamos | FK polimórfica (`tipo_reclamable` + `uuid_reclamable`); workflow chain `abierto → en_revision → resuelto/rechazado` on `reclamos` `[L-W]` | ~200 LOC |
| **IT-9** | Reimpresión de ticket | Workflow on `reimpresion_ticket` `[L-W]`; gated by `SyncBackEvent` (API + PWA both enforce) | ~200 LOC |

### Phase 4 — Customer Features (vertical)

| Iteration | Atomic case | Components touched | Budget |
|---|---|---|---|
| **IT-10** | Subscripciones + vehículos | Admin CRUD on `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos`; parametrization pull; branch lookup on `IngresoForm` | ~400 LOC |

### Phase 5 — Admin Ops (vertical)

| Iteration | Atomic case | Components touched | Budget |
|---|---|---|---|
| **IT-11** | Reportes admin | Read-only aggregations over `facturas`, `arqueo`, `alerta`, `log_transaccional`; cross-branch views | ~350 LOC |

### Phase 6 — Audit Hardening (vertical)

| Iteration | Atomic case | Components touched | Budget |
|---|---|---|---|
| **IT-12** | Hash-chain verifier + audit reports | `workers/hash_chain_verifier` nightly cron; tamper-detection RED test; `web_admin` `AuditDashboard` | ~300 LOC |

## Model Coverage Map

| Enforcement level | Tables | First iteration that delivers write logic |
|---|---|---|
| `[V]` projection (26 tables) | `usuarios`, `permisos`, `permisos_usuario`, `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `tipo_sucursal`, `tipo_arqueo`, `impuestos`, `otros_cobros`, `costos_servicios`, `configuracion_tolerancias`, `configuracion_seguridad`, `empresa`, `resolucion_facturacion`, `sucursal`, `usuarios_sucursal`, `documentos`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos` | F1 (schema) + IT-1 (usuarios, permisos_usuario, usuarios_sucursal), IT-2 (sucursal, tipo_sucursal, documentos), IT-10 (clientes, subscripciones, vehiculos) |
| `[L-E]` event (3 tables) | `ingreso`, `facturas`, `factura_electronica` | F1 (schema) + IT-3 (ingreso), IT-5 (facturas, factura_electronica cloud-only) |
| `[L-W]` workflow (6 tables) | `anulaciones`, `reclamos`, `alerta`, `reimpresion_ticket`, `envio_dian`, `validacion_evento` | F1 (schema) + IT-6 (anulaciones), IT-7 (alerta), IT-8 (reclamos), IT-9 (reimpresion_ticket) |
| `[L-S]` session/cycle (2 tables) | `login`, `sesion` | F1 (schema) + IT-1 (login) + future sesion for cash session lifecycle |
| `[A]` source-of-truth (12 tables) | `sync_queue`, `sync_log`, `sync_conflict`, `log_transaccional`, `revocacion_factura`, `caja`, `arqueo`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `salidas` | F1 (schema + REVOKE + triggers + partitions + hash-chain genesis) + IT-1 (sync_queue, log_transaccional), IT-3 (ingreso writes log_transaccional), IT-4 (salidas), IT-5 (factura_detalle, factura_pagos, factura_electronica), IT-7 (alerta writes log_transaccional), IT-12 (log_transaccional verifier) |

## Execution Order (recommended)

1. **Phase 0**: F1 → F2.
2. **Phase 1**: IT-1 → IT-2.
3. **Phase 2**: IT-3 → IT-4 → IT-5.
4. **Phase 3**: IT-6 → IT-7 → IT-8 → IT-9 (parallel after Phase 2).
5. **Phase 4**: IT-10.
6. **Phase 5**: IT-11.
7. **Phase 6**: IT-12.

Each iteration = one PR. Revertible in isolation. `size:exception` only for F1 (the schema PR).

## Cross-cutting Constraints (apply to every iteration)

- **AUDIT-FIRST**: every iteration touching `[A]` tables MUST include REVOKE + trigger DDL in the same migration that creates/alters the table (`config.yaml` `rules.tasks`).
- **DIAN compliance**: every iteration touching `factura_electronica`, `revocacion_factura`, `log_transaccional`, or `empresa.consecutivo_actual` MUST be cloud-only — branches never write to these.
- **Hash-chain integrity**: every iteration that produces `log_transaccional` or `revocacion_factura` rows MUST verify `hash_anterior == previous.hash_actual` per `uuid_sucursal`.
- **Sync topology**: branches use `sync_queue` (local-only, no recursion); cloud owns atomic `empresa.consecutivo_actual`; JWT three issuers (admin / operador / sync-agent).
- **Branch imports of `parkos_core.dian.cloud` MUST fail** — boundary enforced from F2 onward via RED test.
- **Vertical slicing**: each iteration crosses ALL components (UI admin + UI sucursal + API admin + API sucursal + sync + DB).

## Open Questions Surfaced So Far

- (a) **Preliminar-number UX format** → default `PRE-<8-char-uuid>`. Ratify in IT-5.
- (b) **Sync-back transport (DIAN numbers)** → pull mode every 30s. Ratify in IT-5.
- (c) **`reimpresion_ticket` blocking** → API + PWA both gate on `GET /facturas/{uuid}/numero-oficial`. Ratify in IT-9.
- (d) **DIAN provider integration** → stub for MVP; real adapter (Factus or another provider) is a separate change.
- (e) **Multi-country support** → deferred; model supports it parametrically but not implemented.
- (f) **WebSocket vs polling** → polling for all MVP iterations. WS in v2.

## Estimated Total Effort (very rough)

| Phase | Estimated LOC | PRs |
|---|---|---|
| Phase 0 (Foundation) | 1200–1900 | 2 (F1 `size:exception`, F2) |
| Phase 1 (Auth & Tenancy) | 750 | 2 (IT-1, IT-2) |
| Phase 2 (Core Operations) | 1150 | 3 (IT-3, IT-4, IT-5) |
| Phase 3 (Workflows) | 950 | 4 (IT-6, IT-7, IT-8, IT-9) |
| Phase 4 (Customer) | 400 | 1 (IT-10) |
| Phase 5 (Admin Ops) | 350 | 1 (IT-11) |
| Phase 6 (Audit) | 300 | 1 (IT-12) |

**Total**: ~5100–5800 LOC across 14 PRs. ~5× smaller than the original layer-based plan (because the layer plan duplicated setup work in each PR; vertical slicing reuses).