# Spec: `operations`

## Purpose

Define the operations and CI gates that make the sync overhaul
verifiable, observable, and reversible. Encodes decision **D9**
(`strict_tdd: true` from PR1, pytest + testcontainers + 80% coverage
gate), **D10** (amended — Prometheus counters + structured logs + Grafana
alerts, plus the `sync_dependency_wait` and `catalog_backfill_complete`
gauges added by D18/R-D8), **D21** (stop enqueueing infrastructure
tables), **R-D2** (catalog drift AST guard, now asserting direction /
`broadcast_policy` / `depends_on` derivation against the ER), **R-D3**
(`sync_queue` carve-out AST check), **R-D4** (`role_guard` for cloud-only
entries, scope narrowed to `validacion_evento` only), and the mock
patterns for hook injection (R7, R15, R16).

## Requirements

### REQ-OPS-001: pytest stack and strict TDD from PR1 (D9, R-D5)
**Given** PR1 lands the testing scaffold
**When** the operator inspects `backend/pyproject.toml` `[dependency-groups].dev`
**Then** the dev dependencies MUST include: `pytest>=8`,
`pytest-asyncio>=0.24`, `pytest-cov>=5`, `httpx>=0.27`,
`factory-boy>=3`, `faker[es_CO]`, `testcontainers[postgres]>=4`
**And** `[tool.pytest.ini_options].asyncio_mode` MUST equal `"auto"`
**And** `[tool.pytest.ini_options].addopts` MUST include
`"--cov=parkos_core.sync --cov-report=term-missing --cov-fail-under=80"`
**And** the `openspec/config.yaml::testing.strict_tdd` field MUST be
updated to `true` (was `false` in the init; this change activates it)
**And** `uv lock --check` MUST pass on the resulting lockfile.

### REQ-OPS-002: Coverage gate applies to `sync/{catalog,motor,hooks}/` only (R-D5)
**Given** the pytest run executes
**When** coverage is reported
**Then** the `--cov-fail-under=80` threshold MUST be measured against
`parkos_core/sync/catalog/`, `parkos_core/sync/motor.py`, and
`parkos_core/sync/hooks/` (combined)
**And** coverage of other modules (e.g. `sync/transport.py`,
`sync/jwt_manager.py`) MUST NOT count toward or against this threshold
**And** if the threshold is missed, CI MUST fail the build.

### REQ-OPS-003: Catalog drift AST guard (`check_catalog_drift.py`) (R-D2, R1, D18, D5-rev)
**Given** the catalog files `parkos_core/sync/catalog.py` and
`parkos_core/sync/local_only_catalog.py` declare their entries
**When** `python openspec/scripts/check_catalog_drift.py` runs
**Then** the script MUST AST-walk both catalogs and verify:

1. Every `name` field resolves to an ORM class in `parkos_core/models/`
   with matching `__tablename__`.
2. Every ORM class in `parkos_core/models/{V,L_E,L_W,L_S,A}/` that is NOT
   one of the five out-of-catalog names (`sync_queue`, `sync_log`,
   `sync_conflict`, `sync_queue_lw_buffer`, `alert_types` —
   `sync-catalog.md` REQ-CAT-006) appears in **exactly one** of
   `SYNC_CATALOG` or `LOCAL_ONLY_CATALOG`. There is no `never_propagated`
   carve-out to this rule: `validacion_evento` still resolves to exactly
   one catalog (`SYNC_CATALOG`), it simply carries
   `sync_strategy="never_propagated"`.
3. The total counts match: `len(SYNC_CATALOG) == 46`,
   `len(LOCAL_ONLY_CATALOG) == 3`, and the out-of-catalog exemption list
   has exactly 5 names — `46 + 3 + 5 == 54` physical prod tables.
4. **(D5-rev)** For every `SYNC_CATALOG` entry, the script MUST re-derive
   `direction` and `broadcast_policy` from `modelo_datos_er.mmd`'s class
   tag and `uuid_sucursal` presence, per the derivation table in
   `sync-catalog.md` REQ-CAT-004, and compare the derived value against
   the declared value. Any mismatch MUST exit non-zero naming the
   offending table and the expected vs. declared value.
5. **(D18)** For every entry with a non-empty `depends_on`, the script
   MUST re-derive the expected parent set from the ER's mandatory-FK
   relationship block and compare it against the declared `depends_on`
   tuple. A hand-edited value that drifts from the ER MUST fail the
   build.
6. **(R19)** The script MUST assert that the `depends_on` graph, with the
   seven `self_chain=True` edges removed, is a DAG. A cycle MUST exit
   non-zero naming the offending cycle.

**And** any failure (missing ORM, missing entry, count mismatch, direction
mismatch, `depends_on` mismatch, cycle) MUST exit non-zero with a clear
error message naming the offending table.

> **Amended — was 2 rules with a 47/5 count.** The prior REQ-OPS-003 ran
> only rules 1-3 above with a 47/5 count and a `never_propagated`
> exception to rule 2. This amendment corrects the counts to 46/3/5/54
> (recomputed from the amended proposal's §6 enumeration, not
> hardcoded — `sync-catalog.md` REQ-CAT-002) and adds rules 4-6, which did
> not exist in the prior pass: without them, the direction/scope defect
> that motivated this whole amendment (deriving policy from installed
> triggers instead of the ER) could recur silently on a future table
> addition.

### REQ-OPS-004: `sync_queue` carve-out AST check (`check_sync_queue_carveout.py`) (R-D3, R8)
**Given** the codebase has the operational carve-out on `prod.sync_queue`
**When** `python openspec/scripts/check_sync_queue_carveout.py` runs
**Then** the script MUST AST-walk every `.py` file under
`backend/packages/parkos_core/src/`
**And** any `UPDATE` or `DELETE` statement targeting `sync_queue` /
`SyncQueue` outside `parkos_core/repo/sync_queue.py` MUST cause the
script to exit non-zero
**And** the script MUST also reject any code that imports `SyncQueue`
for mutation outside `repo/sync_queue.py` (e.g.
`session.execute(update(SyncQueue, ...))` in `sync_router.py`)
**And** the script MUST allow READS of `SyncQueue` from anywhere
(`session.execute(select(SyncQueue))` is permitted).

### REQ-OPS-005: `role_guard` scoped to `validacion_evento` only (R-D4, R6)
**Given** a module imports a spec whose `model_cls` has
`role_required="cloud"`
**When** the module is imported in a process where
`PARKOS_DEPLOY=branch`
**Then** `parkos_core/sync/role_guard.py::assert_role("branch")` MUST
raise `ImportError` with a message that includes the table name and
"cloud_only entry not allowed on branch" **only for `validacion_evento`**
**And** the guard MUST NOT raise for `envio_dian` — it has
`role_required="both"`, `originating_role="cloud"`
(`sync-catalog.md` REQ-CAT-010) — the branch legitimately holds and reads
`envio_dian` rows
**And** the integration test
`tests/integration/test_role_guard.py::test_branch_cannot_import_cloud_only`
MUST assert the `ImportError` for `validacion_evento` AND a companion test
MUST assert `envio_dian` imports and applies cleanly from the same
branch-flavored session fixture
**And** the precedent from the DIAN provider adapter module under
`dian/cloud/dian_providers/` MUST be mirrored exactly (the same
`if os.environ.get(...)` pattern that adapter already uses).

> **Amended — scope narrowed from 2 tables to 1.** The prior REQ-OPS-005
> asserted the guard for both `envio_dian` and `validacion_evento`. The
> earlier catalog would have crashed branch boot on `envio_dian`, a table
> the branch must legitimately read (R6, `sync-catalog.md` REQ-CAT-010).

### REQ-OPS-006: Prometheus counters and gauges (D10 amended)
**Given** the cloud and branch workers run `SyncMotor.apply_row` /
`apply_batch`
**When** a row completes apply (APPLIED, CONFLICT, or RETRY)
**Then** the hook `hook_post_insert` MUST emit
`prometheus_client.Counter("sync_apply_total",
    "sync row apply outcomes",
    labelnames=["status", "tabla", "uuid_sucursal", "audit_class"])`
**And** the value MUST be incremented by 1 per row, with `status` set to
the `ApplyResult.status` value
**And** the counter MUST be exposed at `GET /metrics` on the API process
(port 8000)
**And** the labels MUST NOT include PII (no payload content; only the
table name, branch UUID, and audit class).

**Given** the D18 dependency buffer and the R-D8 backfill gate
**When** the cloud and branch workers run
**Then** the worker MUST ALSO emit:
- `Gauge("sync_dependency_wait", "rows currently buffered in
  sync_queue_lw_buffer", labelnames=["tabla", "uuid_sucursal"])`
- `Gauge("catalog_backfill_complete", "1 once every cloud_to_branch entry
  has applied its initial topological backfill for this branch",
  labelnames=["uuid_sucursal"])`
- `Gauge("catalog_rows_total", "row count per catalog table per branch,
  for R18 volume monitoring", labelnames=["tabla", "uuid_sucursal"])`

**And** `catalog_backfill_complete{uuid_sucursal}` MUST transition to `1`
only after every `cloud_to_branch` `SYNC_CATALOG` entry has completed its
initial backfill with zero unresolved declared parents for that branch —
this is the gauge the R-D8 stage-4 gate reads (`cutover-migration.md`
REQ-CUT-006).

### REQ-OPS-007: Structured logs with `uuid_sucursal` + `tabla`, PII-free (D10)
**Given** the `SyncMotor` and hooks execute
**When** any log line is emitted
**Then** the log MUST be structured JSON via `structlog`
**And** every line MUST carry at minimum the keys:
`event` (e.g. `sync_apply`, `sync_chain_extend`, `sync_conflict_resolved`,
`sync_engine_flag_change`, `sync_broadcast`), `tabla`, `uuid_sucursal`,
`actor_uuid`, `correlation_id` (the `X-Request-Id` from the inbound
request), `ts` (ISO-8601 UTC), `level`
**And** the log MUST NOT carry unredacted PII — this is where
`PIIRedactor` actually runs (`hooks.md` REQ-HOOK-004): `clientes`
`email`/`telefono`/`direccion`/`nombre`/`apellido` MUST be redacted in
any log line and in `sync_conflict.datos_local`/`datos_remoto`, but the
live replicated payload itself is never redacted
**And** the log level for `chain_break` anomalies MUST be `error` so
Grafana picks them up.

### REQ-OPS-008: Grafana alerts (D10 amended)
**Given** Prometheus is scraping the `/metrics` endpoint
**When** the operator deploys the alert rules in
`infra/grafana/alerts/sync.yaml`
**Then** the rules MUST include:

| Alert | Condition | Severity |
|---|---|---|
| `SyncBacklogHigh` | `sync_queue_pending_rows > 1000 for 10m` | warning |
| `SyncConflictRateHigh` | `rate(sync_apply_total{status="conflict"}[1h]) / rate(sync_apply_total[1h]) > 0.005` | warning |
| `HashChainBreak` | `sync_chain_anomalies_total > 0 for 5m` | critical |
| `OrphanWorkflowChain` | `rate(orphan_workflow_chain_alerts_total[1h]) > 0` | warning |
| `BranchImportError` | `rate(sync_import_errors_total[5m]) > 0` | critical |
| `CatalogBackfillIncomplete` | `catalog_backfill_complete{uuid_sucursal} == 0 for 48h` after pairing | warning |
| `FEProviderError` | `rate(alerta_total{tipo_alerta="fe_provider_error"}[1h]) > 0` | critical |
| `FENumberingExhausted` | `rate(alerta_total{tipo_alerta="fe_numbering_exhausted"}[1h]) > 0` | critical |

**And** each alert MUST include a `runbook_url` annotation pointing to
`docs/runbooks/sync/<alert_name>.md`
**And** every `tipo_alerta` value referenced by an alert rule MUST be a
generic identifier — never the literal name of the third-party DIAN
provider (addendum #5, `sync-catalog.md` REQ-CAT-021).

> **Amended.** The prior REQ-OPS-008 had 5 rules and no gauge for the
> R-D8 backfill gate or the DIAN provider failure alerts. `CatalogBackfillIncomplete`,
> `FEProviderError`, and `FENumberingExhausted` are new (D10 amendment,
> D18, D1-rev/REQ-CUT-014).

### REQ-OPS-009: Mock pattern for hook injection (R7, R15)
**Given** a test exercises `SyncMotor.apply_row` for a spec with a hook
**When** the test sets up the spec
**Then** the conftest helper MUST expose
`make_spec(name: str, **overrides) -> SyncCatalogEntry`
**And** `overrides` MUST accept any of the 4 hook slots
(`hook_pre_insert`, `hook_post_insert`, `hook_chain_extend`,
`hook_validate_parent`)
**And** the default for every hook slot MUST be
`lambda ctx: HookResult(proceed=True)` so a test that does not care about
hooks does not have to set them up
**And** the `VFixtureFactory` in `tests/conftest.py` MUST default
`vigente_hasta=None` on all 26 `[V]` classes (R15) so close+insert has a
valid starting state.

### REQ-OPS-010: Parametrized tests for trivial hooks (R16)
**Given** some hooks (e.g. `BiTemporalCompensation`, `ValidateParentChain`)
are bound to multiple tables
**When** the test file declares the hook test
**Then** the test MUST use `@pytest.mark.parametrize("tabla", [...])` to
cover every bound table
**And** the parametrize list MUST be derived from
`SYNC_CATALOG.get_all_for_hook(hook_kind)` (a helper added in PR4)
**And** the test coverage report MUST show 100% line+branch coverage for
each hook across all bound tables.

### REQ-OPS-011: CI gate runs all AST checks + pytest in one job (R-D2, R-D3, R-D5)
**Given** the GitHub Actions workflow `.github/workflows/ci.yml`
**When** a PR opens or pushes
**Then** the workflow MUST run, in order:

1. `uv sync --frozen --all-extras --dev`
2. `python openspec/scripts/check_sync_queue_carveout.py`
3. `python openspec/scripts/check_catalog_drift.py` (rules 1-6,
   REQ-OPS-003)
4. `uv run ruff check .`
5. `uv run mypy src/`
6. `uv run pytest --cov --cov-report=xml`
7. Trivy scan on the built image (only on merge to `dev`)

**And** any step failure MUST fail the job
**And** long-running installs MUST use the `astral-sh/setup-uv@v3` cache.

### REQ-OPS-012: Reverse migration script is dry-runnable in CI (D12, R-D2)
**Given** `openspec/scripts/reverse_sync_overhaul.py` exists
**When** CI runs the script with `--dry-run`
**Then** the script MUST execute steps 1-3 of REQ-CUT-009 (set-legacy,
wait-for-drain, drain-the-buffer) in a mode that records the actions but
does NOT mutate any state (prints `[DRY-RUN] would set
PARKOS_SYNC_ENGINE=legacy` / `[DRY-RUN] would drain N buffered rows`
instead of touching env or data)
**And** steps 4-6 MAY be no-ops in dry-run (they are listed for
completeness; reversing the PR is the operator's job)
**And** the script MUST exit 0 on a clean dry-run and non-zero on any
detected inconsistency (e.g. the catalog drift AST fails).

### REQ-OPS-013: `openspec/scripts/check_drain.py` runs in stage-gate (R2)
**Given** the cutover advances from stage 3 to stage 4
**When** the operator runs `python openspec/scripts/check_drain.py`
**Then** the script MUST query
`SELECT count(*) FROM prod.sync_queue WHERE estado='pendiente'`
**And** if the count is 0, exit 0
**And** if the count is non-zero, exit 1 and print the count + the
elapsed seconds since the last cutover attempt
**And** the script MUST be invoked by the stage-gate automation in CI
(stage 4 gate).

### REQ-OPS-014: Stop enqueueing infrastructure tables (D21)
**Given** `sync_log` and `sync_conflict` carry the legacy
`fn_enqueue_sync` trigger today, which produces rows the cloud worker
cannot resolve to a catalog entry
**When** migration `0012_drop_infra_triggers.py` runs
**Then** the `fn_enqueue_sync` trigger MUST be dropped from both
`prod.sync_log` and `prod.sync_conflict`
**And**, independently of the trigger drop (to remain correct for any
branch still running the old trigger set during the 14-day grace
period), the cloud worker MUST **skip** — not
`mark_failed(unknown_table)` — any row whose `tabla` matches one of the
five out-of-catalog names (`sync-catalog.md` REQ-CAT-006)
**And** a skipped row MUST be logged at `info` level with
`{"event": "sync_skip_infra_table", "tabla": ...}` and MUST NOT increment
`sync_apply_total{status="failed"}` or any failure-rate metric
**And** a regression test MUST assert that a `sync_queue` row with
`tabla="sync_log"` or `tabla="sync_conflict"` is skipped cleanly instead
of marked failed.

### REQ-OPS-015: CI invariant — at most one open version per natural key (D17, R17)
**Given** `clientes`, `clientes_b2b`, and `vehiculos` — the three
natural-key identity masters (`sync-catalog.md` REQ-CAT-018)
**When** the CI invariant test runs
**Then** the test MUST assert, for each of the three tables, that no
normalized natural key has more than one row with `vigente_hasta IS NULL`
**And** the test MUST exercise the three `IdentityReconciler` outcomes
(`noop`, `forward`, `historical`) plus the divergent-data path, and MUST
assert the invariant holds after each
**And** a violation MUST fail CI — this is the direct regression guard
against the concurrent-registration hazard R17 describes.

### REQ-OPS-016: Generic alert-type identifiers enforced in CI (addendum #5)
**Given** `prod.alert_types` seed data
(`0010_add_alert_types.py`) and every `tipo_alerta` string literal in
`parkos_core/`
**When** CI runs a grep-based or AST-based check for banned vendor
identifiers
**Then** the check MUST fail the build if the literal name of the
third-party DIAN provider appears in any seed data, source file, log
format string, or `alert_types` row
**And** DIAN-provider-facing alert types MUST use the generic identifiers
`fe_provider_error` and `fe_numbering_exhausted` (or an equivalent
generic name) exclusively — this applies to `alert_types` seed data,
`sync-catalog.md`, `hooks.md`, `cutover-migration.md`, `operations.md`,
and any other artifact this change touches.

### REQ-OPS-017: Query param `vigente_en` opcional en `GET /empresa/tarifas-sucursal`

**Given** el cliente envía `GET /empresa/tarifas-sucursal` con un query param
opcional `vigente_en` en formato ISO-8601 (con o sin tz; naive se interpreta como UTC)
**When** el handler dedicado de HU-F1.4 procesa la request
**Then** el endpoint MUST aceptar el valor y propagarlo al helper
`repo/tarifas_vigencia.py::list_tarifas_vigentes` como un `datetime` UTC-normalizado
**And** MUST usar `datetime.now(UTC)` cuando `vigente_en` se omite (preservando
retrocompatibilidad con el comportamiento previo del factory para el subconjunto de
filas con `estado='activo'`)
**And** MUST aceptar ISO-8601 con sufijo `Z` (zona UTC explícita)
**And** MUST aceptar offsets ISO-8601 (`+05:00`, `-03:00`, etc.) y normalizarlos a UTC
**And** MUST devolver `422 Unprocessable Entity` cuando `vigente_en` no parsea como
ISO-8601 (Pydantic + `datetime.fromisoformat`)
**And** MUST devolver `422 Unprocessable Entity` cuando el offset está fuera del rango
válido (`±14:00` por convención IANA, validado por `datetime.fromisoformat`)
**And** MUST seguir devolviendo `400 invalid_cursor` cuando `cursor` no decodifica,
independiente del valor de `vigente_en`
**And** MUST seguir exigiendo los issuers `admin-,operador-` y el permiso
`config_tarifas` (sin cambios respecto al factory).
**And** SHALL documentar el query param en el OpenAPI generado por FastAPI con
`description=` que explique: punto en el tiempo para el predicado de vigencia, formato
ISO-8601, naive=UTC, default `now(UTC)`.

> **Amended — fue una sección del factory genérico.** Previo a HU-F1.4, el factory
> atendía este recurso con un comportamiento fijo (`vigente_hasta IS NULL`); la
> cobertura de ese comportamiento pasa a ser un subconjunto del default de HU-F1.4.
> El factory NO se modifica: el handler dedicado gana por orden de registro
> (KD-4 del `design.md`).

### REQ-OPS-018: Predicado bi-temporal canónico con `estado='activo'`

**Given** el handler dedicado invoca `list_tarifas_vigentes(session, *, vigente_en, filter, cursor, limit)`
**When** el helper construye el `SELECT`
**Then** el predicado MUST ser exactamente:
`vigente_desde <= :vigente_en AND (vigente_hasta IS NULL OR vigente_hasta > :vigente_en) AND estado = 'activo'`
**And** el predicado MUST aplicarse como filtros `WHERE` de SQLAlchemy, no como filtros
post-fetch en Python (defensa en profundidad: el índice subyacente se usa para reducir
el conjunto antes del bind)
**And** `vigente_en` MUST estar normalizado a UTC **naive** antes del bind (DB column
`DateTime(timezone=False)`; `asyncpg` rechaza `timestamptz` implícito en `WHERE`)
**And** SHALL reutilizar el patrón `_parse_cursor_timestamp` de
`backend/.../api/router_factory.py:84-113` para la normalización tz→UTC naive
**And** SHALL incluir el filtro `estado='activo'` siempre, **independiente** del valor de
`vigente_en` (incluido el default `now(UTC)`) — defensa en profundidad consistente con
`resolve_active_subscription_for_exit` (`operacion.py:215-277`)
**And** MUST persistir el orden por `vigente_desde DESC, uuid ASC` (idéntico al factory)
para que los cursors emitidos antes del deploy sigan decodificando correctamente.

### REQ-OPS-019: Handler dedicado antes del mount genérico del factory

**Given** el recurso `tarifas-sucursal` está registrado en `empresa.py` mediante
`_mount_empresa(...)` (líneas 142-149) que a su vez invoca `make_router(...)`
**When** `sdd-apply` registra el handler dedicado de HU-F1.4
**Then** el handler MUST estar declarado con `@router.get("")` (raíz del recurso)
explícitamente **antes** del bloque `_mount_empresa("tarifas-sucursal", …)` en
`backend/.../api/v1/empresa.py`
**And** FastAPI MUST preferir el handler dedicado por orden de registro sobre el
`list_endpoint` del factory para el método `GET` y path `""` (sin slug)
**And** los demás verbos del recurso (`POST`, `PUT`, `GET /{uuid}`,
`GET /{uuid}/history`) MUST seguir siendo atendidos por el factory sin cambios
**And** el factory (`make_router`) MUST permanecer intacto: HU-F1.1 GAP-BE-02
(commit `f7cb37a`) lo estabilizó y NO se modifica
**And** los demás recursos `[V]` del módulo `empresa` (`cantidad-vehiculos-sucursal`,
`resolucion-facturacion`, `documentos`, `usuarios-sucursal`) MUST seguir siendo
atendidos por el factory sin handler dedicado
**And** SHALL documentar el orden de registro con un comentario inline en `empresa.py`
explicando que el handler dedicado gana por especificidad de path.

### REQ-OPS-020: Helper puro `repo/tarifas_vigencia.py::list_tarifas_vigentes`

**Given** el handler dedicado de HU-F1.4 necesita aplicar el predicado bi-temporal sobre
`prod.tarifas_sucursal` con conversión tz→UTC, orden estable y cursor pagination
**When** `sdd-apply` crea `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py`
**Then** el módulo MUST exponer una única función async pública con signature
`async def list_tarifas_vigentes(session: AsyncSession, *, vigente_en: datetime,
filter: TarifasSucursalFilter, cursor: str | None, limit: int) -> tuple[list[TarifasSucursal], str | None]`
**And** la firma MUST ser keyword-only a partir de `vigente_en` para evitar swaps de
argumentos posicionales
**And** el orden de las filas MUST ser exactamente `(TarifasSucursal.vigente_desde.desc(),
TarifasSucursal.uuid.asc())` — idéntico al factory
**And** el cursor MUST decodificarse usando
`router_factory._parse_cursor_timestamp` y la misma `(order_col, cursor_field) =
router_factory._order_key(model_cls)` (cursor field = `vigente_desde` para esta tabla)
**And** el helper MUST ejecutar `SELECT … LIMIT limit + 1` y emitir `next_cursor` cuando
el conjunto devuelto excede `limit` (mismo patrón que el factory)
**And** el helper MUST ser SELECT puro: no `INSERT`, `UPDATE`, `DELETE`, no side-effects,
no cache, no lock
**And** SHALL encapsular el predicado en una constante constante a nivel de módulo
(`BITEMPORAL_VIGENTE_PREDICATE` o equivalente) para que los tests unit la referencien
sin reescribir el SQL
**And** el helper SHALL coexistir con `make_router` sin importar ni tocar
`router_factory.make_router` más allá de las dos funciones reusadas
(`_parse_cursor_timestamp`, `_order_key`); sin imports circulares.

### REQ-OPS-021: Campo `vigente_en` en `TarifasSucursalFilter`

> **NOTA**: este requirement se asigna REQ-OPS-021 (no REQ-OPS-018-bis) para preservar
> monotonicidad con la serie REQ-OPS-001..016 ya existente en
> `openspec/specs/operations/spec.md`. El correlativo 020 se reservó para el helper puro
> por ser la dependencia más cargada del handler dedicado. Si el lector encuentra
> inconsistente el orden numérico frente a la redacción (REQ-OPS-017..020 en proposal.md
> y design.md vs REQ-OPS-017, 018, 020, 021 acá), la divergencia es **documentada, no
> resuelta**: el agente writer no edita `proposal.md` ni `design.md` para reordenar, y
> el agente apply decide si unificar durante la implementación.

**Given** el handler dedicado construye un `TarifasSucursalFilter` para reenviar al
helper `list_tarifas_vigentes`
**When** `sdd-apply` modifica `backend/.../schemas/empresa.py`
**Then** la clase `TarifasSucursalFilter` MUST agregar el campo
`vigente_en: datetime | None = None` después del último campo existente (línea 309)
**And** el campo MUST heredar `extra='forbid'` de la `_Base` (Pydantic) para rechazar
query params desconocidos con 422
**And** el campo MUST aceptar `datetime | None` (no `str`): Pydantic con `datetime`
builtin parsea ISO-8601 directamente y rechaza lo malformado
**And** SHALL incluir `description=` que diga "Punto en el tiempo para el predicado de
vigencia. ISO-8601 con o sin tz; naive = UTC. Default en el handler: `datetime.now(UTC)`."
**And** SHALL mantener retrocompatibilidad: las instancias existentes de
`TarifasSucursalFilter` (en el factory para los demás verbos, en tests, en scripts) MUST
seguir funcionando sin cambios — el campo nuevo tiene default `None`.

### REQ-OPS-022: GET `/api/v1/operacion/cotizar?uuid_ingreso` returns the fiscal breakdown
**Given** an open `prod.ingreso` row for `uuid_ingreso=X` (i.e. without any non-anulada
`prod.salidas`), an active row in `prod.tarifas_sucursal` for the
`(uuid_sucursal, uuid_tipo_vehiculo)` combination that is vigente at `NOW()` per the
bi-temporal predicate (`vigente_desde <= NOW() AND (vigente_hasta IS NULL OR
vigente_hasta > NOW()) AND estado='activo'`), and an active row in `prod.impuestos`
with `nombre='IVA'` and `porcentaje > 0` that is also vigente at `NOW()`
**When** the handler receives the request with a valid JWT bearing an `operador-`
or `admin-` issuer (`_ingreso_issuer_dep`)
**Then** the PL/pgSQL `prod.calcular_cotizacion(p_uuid_ingreso)` MUST execute
`SELECT … FOR SHARE` against the matched `tarifas_sucursal` row, MUST compute
`subtotal`, `iva`, `total`, `tiempo_minutos`, and `vigente_hasta = NOW() + INTERVAL
'15 minutes'`, MUST apply the formula `iva = total * porcentaje_impuesto` and
`subtotal = total - iva`, and MUST return `200 OK` with body
`{cobrar: true, subtotal, iva, total, tiempo_minutos, tarifa_uuid, vigente_hasta}`
**And** the response MUST carry the header `Cache-Control: no-store` so no proxy
or intermediary can serve a stale quote (R8).

### REQ-OPS-023: Active monthly subscription by plate returns `cobrar: false`
**Given** the `prod.ingreso` row exists and is open, AND the plate joined through
`prod.subscripcion_vehiculos` → `prod.subscripciones_cliente` → `prod.vehiculos`
has an active subscription vigente at `NOW()` per the same bi-temporal predicate
**When** the handler invokes `prod.calcular_cotizacion(p_uuid_ingreso)`
**Then** the PL/pgSQL MUST delegate to the SQL port of
`resolve_active_subscription_for_exit` (precedent at
`backend/.../api/v1/operacion.py:215-277`), MUST short-circuit the pricing
pipeline, and MUST return `200 OK` with body `{cobrar: false,
motivo: "mensualidad_vigente"}`
**And** the PL/pgSQL MUST NOT acquire the `SELECT … FOR SHARE` lock on
`tarifas_sucursal` and MUST NOT invoke the pricing formula, because no cash
movement applies — the monthly fee is settled by the subscription, not the exit.

### REQ-OPS-024: Typed errors with explicit precedence
**Given** any valid request carrying a JWT signed by an allowed issuer
**When** the PL/pgSQL function evaluates its preconditions for
`p_uuid_ingreso`
**Then** the function MUST return the first applicable error in this exact
precedence order: (1) `jsonb_build_object('error', 'ingreso_no_encontrado')` →
handler maps to `404 Not Found` when the `uuid_ingreso` does not exist in
`prod.ingreso` or already has a non-anulada row in `prod.salidas`; (2)
`jsonb_build_object('error', 'tarifa_no_vigente')` → handler maps to
`404 Not Found` when the previous check passed but no `tarifas_sucursal` row
satisfies the bi-temporal predicate for the
`(uuid_sucursal, uuid_tipo_vehiculo)` combination at `NOW()` (KD-3); (3)
`jsonb_build_object('error', 'iva_no_configurado')` → handler maps to
`500 Internal Server Error` when the two previous checks passed but no
`prod.impuestos` row has `nombre='IVA'` vigente at `NOW()` with
`porcentaje > 0` (KD-IVA — seeding is out of scope of F1.8 and is owned by
HU-F14.2 Parte II)
**And** the precedence MUST be strictly
`ingreso_no_encontrado > tarifa_no_vigente > iva_no_configurado`; no other
ordering is permitted, and a single response MUST never combine two error codes.

### REQ-OPS-025: `calcular_cotizacion` declares STABLE or VOLATILE; AST walk rejects mutations

> **Note**: Originally letter-stated as `STABLE` only; reconciled 2026-09-14 to accept `VOLATILE` when `SELECT ... FOR SHARE` is required (Postgres rejects shared locks in STABLE/IMMUTABLE functions). The read-only guarantee is enforced by an AST walk over the migration body rejecting INSERT|UPDATE|DELETE|TRUNCATE|MERGE tokens, not by the volatility declaration.

**Given** the Alembic migration 0022 declares the function with `LANGUAGE plpgsql STABLE` or `LANGUAGE plpgsql VOLATILE` (either is acceptable; VOLATILE is required when using `SELECT ... FOR SHARE`)
**When** `pytest tests/static/test_no_write_in_calcular_cotizacion.py` runs
**Then** the test MUST walk the migration body, parse `op.execute("""...""")`, and reject any `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` token (case-insensitive, outside string literals and comments)
**And** the test MUST be a regular part of the pytest collection (auto-discovered in `backend/tests/static/`)
**And** the full `uv run pytest -q backend/tests/` MUST pass with this AST check included.

### REQ-OPS-026: Partial unique index on `prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL` with pre-flight abort

**Given** an Alembic migration `0023_add_sesion_unique_active.py` is
applied against a Postgres database where `prod.sesion` already exists
and may contain legacy data
**When** the migration's `upgrade()` executes
**Then** the migration MUST first run a pre-flight query of the form
`SELECT uuid_usuario, count(*) FROM prod.sesion WHERE timestamp_cierre IS
NULL GROUP BY uuid_usuario HAVING count(*) > 1`
**And** if the pre-flight returns one or more rows, the migration MUST
abort with an explicit error that names each affected `uuid_usuario` and
the orphan count, MUST NOT proceed to `CREATE INDEX`, and MUST NOT leave
the migration half-applied (Alembic records no version bump on abort)
**And** the migration MUST then execute
`CREATE UNIQUE INDEX CONCURRENTLY uq_prod_sesion_one_active_per_user
ON prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL`
**And** the index MUST be a **partial** index (the `WHERE timestamp_cierre
IS NULL` predicate is mandatory — a full unique index would forbid two
historical closed sessions for the same user, which is legitimate)
**And** the index MUST be created with `CONCURRENTLY` so the build does
not take an `AccessExclusiveLock` against `prod.sesion` while the table
is serving cashier operations
**And** the `downgrade()` MUST execute `DROP INDEX CONCURRENTLY IF EXISTS
prod.uq_prod_sesion_one_active_per_user`
**RFC 2119**: MUST (pre-flight abort, `CONCURRENTLY`, partial predicate);
SHOULD (downgrade uses `CONCURRENTLY` to match the upgrade build mode).

### REQ-OPS-027: `GET /api/v1/caja-sesion/sesion/me` returns the actor's unique active session or 404

**Given** a JWT request reaches the FastAPI router for
`GET /api/v1/caja-sesion/sesion/me` with a valid `TenantContext` carrying
`ctx.actor_uuid` (extracted from the token subject by HU-F1.2)
**When** the dedicated handler `get_my_sesion` invokes
`repo/sesion_activa.py::get_sesion_activa(session, *, actor_uuid)`
**Then** the helper MUST execute a SQLAlchemy `SELECT` against `prod.sesion`
with the predicate `Sesion.uuid_usuario == :actor_uuid AND
Sesion.timestamp_cierre.is_(None)`
**And** the helper MUST order the result by
`Sesion.timestamp_apertura.desc().nulls_last()` and MUST apply `LIMIT 1`
**And** the helper MUST return exactly one `Sesion` ORM instance if a
match exists, or `None` otherwise (the partial unique index REQ-OPS-026
guarantees at most one row satisfies the predicate)
**And** the handler MUST return `200 OK` with the `SesionRead` payload
when the helper returns a row
**And** the handler MUST raise `HTTPException(status_code=404, detail=
{"error": "sesion_no_active"})` when the helper returns `None`
**And** the handler MUST be declared with `@router.get("/sesion/me")` and
MUST be registered **before** the `include_router(make_router(resource=
"sesion", ...))` block in `caja_sesion.py` so FastAPI matches the
literal path `/me` ahead of the parametric `/sesion/{uuid}`
**And** the `make_router` (HU-F1.1 GAP-BE-02 commit `f7cb37a`) MUST
remain unmodified
**RFC 2119**: MUST (literal path, ordering, `LIMIT 1`, 404 body shape);
SHOULD (return 404 with `Cache-Control: no-store` if applicable to keep
behaviour consistent with other read endpoints, but the contract does not
require it).

### REQ-OPS-028: `UniqueViolation` from partial unique index maps to 409 `sesion_already_active`, pgcode never exposed

**Given** `repo/session_cycle.py::open_session` is invoked with a
`uuid_usuario` that already has an active row in `prod.sesion`
(`timestamp_cierre IS NULL`) — either via a TOCTOU race past the app-level
fast-path check, or because the fast-path check returned a stale view
**When** the underlying `INSERT INTO prod.sesion (...)` reaches Postgres
**Then** Postgres MUST raise a unique-constraint violation because the
partial unique index from REQ-OPS-026 forbids the row; the
`psycopg2.errors.UniqueViolation` exception is surfaced with `pgcode ==
"23505"`
**And** `repo/session_cycle.open_session` MUST catch
`psycopg2.errors.UniqueViolation` (identified by `pgcode == "23505"`, not
by Python `isinstance` alone to remain robust to driver wrapping) and
MUST re-raise a domain exception `SesionAlreadyActive(uuid_usuario=...)`
**And** the HTTP handler `POST /api/v1/caja-sesion/sesiones` MUST catch
`SesionAlreadyActive` and MUST raise `HTTPException(status_code=409,
detail={"error": "sesion_already_active"})`
**And** the response body MUST contain **only** `{"error":
"sesion_already_active"}`; the pgcode `"23505"`, the raw Postgres error
message, and any driver-level diagnostic strings MUST NOT appear in the
response body, the response headers, or any log line emitted at `info` or
higher visibility to client users
**And** the contract MUST NOT introduce a pre-check `SELECT … WHERE
uuid_usuario=:u AND timestamp_cierre IS NULL` before the `INSERT` (KD-3
BD-only): the partial index is the authoritative invariant and a
pre-check would duplicate round-trips and reopen a TOCTOU window
**RFC 2119**: MUST (catch by pgcode, re-raise typed domain exception,
409 mapping, no pgcode in body, no pre-check); SHOULD (log the
occurrence at `warning` level with `event="sesion_already_active"` and
the `uuid_usuario` for ops triage, but without the pgcode).

### REQ-OPS-029: Both `operador-` and `admin-` issuers accepted on `GET /api/v1/caja-sesion/sesion/me`

**Given** a JWT request reaches `GET /api/v1/caja-sesion/sesion/me` with
either an `operador-` prefixed issuer or an `admin-` prefixed issuer
**When** the dedicated handler `get_my_sesion` resolves its dependencies
**Then** the dependency `_sesion_issuer_dep` (defined in `caja_sesion.py`
line 35 with `requires_issuer("operador-", "admin-")`) MUST accept both
issuer prefixes and MUST reject any other issuer with 401/403 (consistent
with the rest of `caja_sesion.py`)
**And** the handler MUST follow REQ-OPS-027 for both issuer classes: it
MUST resolve `ctx.actor_uuid` from the JWT subject and MUST query
`prod.sesion WHERE uuid_usuario = ctx.actor_uuid AND timestamp_cierre
IS NULL ORDER BY timestamp_apertura DESC NULLS LAST LIMIT 1`
**And** if an `admin-` issuer has no active session (the common case —
admins rarely open a cashier shift), the response MUST be exactly the
same 404 with body `{"error": "sesion_no_active"}` as for an `operador-`
issuer; there is no special admin bypass, no synthetic "view any session"
behaviour, and no 200 with `null` payload
**And** if a future need arises to query "the active session of an
arbitrary `uuid_usuario` from an `admin-` issuer", that is a separate
endpoint with an explicit query parameter and is OUT OF SCOPE for HU-F1.3
**RFC 2119**: MUST (accept both issuers, 404 same body, no admin bypass,
no synthetic payload); SHOULD (document the issuer list in the FastAPI
OpenAPI `tags` annotation alongside the rest of `caja_sesion.py`).

### REQ-OPS-030 — `GET /api/v1/operacion/ocupacion?uuid_sucursal=X` returns per-tipo breakdown with `Cache-Control: no-store`

**Given** a JWT request reaches `GET /api/v1/operacion/ocupacion`
carrying either an `operador-` or `admin-` issuer and a valid `TenantContext`
(extracted by `get_tenant_ctx`, F1.2)
**When** the handler `get_ocupacion` resolves the target `uuid_sucursal`
via `(query_param OR ctx.sucursal_uuid)` and the `operador-/admin-`
authorization chain (KD-3) passes
**Then** the endpoint MUST return `200 OK` with a body matching
`OcupacionResponse { uuid_sucursal: UUID, items: list[OcupacionItem],
generado_en: datetime }` where each `OcupacionItem` carries
`{ uuid_tipo_vehiculo: UUID, tipo: str, cupo_maximo: int, activos: int,
disponible: int }` ordered `ORDER BY tv.tipo` (KD-4 deterministic order)
**And** the response MUST include the header `Cache-Control: no-store`
(consistent with F1.3 R8 / F1.8 R8) on every `2xx`/`4xx`/`5xx` response
emitted by the handler
**And** the endpoint MUST NOT mutate state: `INSERT|UPDATE|DELETE|TRUNCATE|MERGE`
tokens MUST NOT appear in the handler body, enforced by the AST walk
in `tests/static/test_no_write_in_ocupacion.py`
**And** the SQL MUST use bind params (`:uuid_sucursal`) — NO string
interpolation — enforced by the helper signature
`get_ocupacion_puros_activos(session, *, uuid_sucursal: UUID)`.
**RFC 2119**: MUST (response shape, header, ordering, bind params,
no write verbs); SHALL (the JSON response use ISO-8601 with `Z` suffix
for `generado_en`).

#### Scenario: operador queries own branch returns 200 with breakdown
**Given** an `operador-` JWT carrying `ctx.sucursal_uuid = X` and the
branch has 1 active `ingreso(X, Auto)` with `cantidad_vehiculos_sucursal(X, Auto) = 50`
and 0 active `ingreso(X, Moto)`
**When** the operator calls
`GET /operacion/ocupacion?uuid_sucursal=X`
**Then** the response MUST be `200 OK` with
`{ uuid_sucursal: X, items: [{ uuid_tipo_vehiculo: T_auto, tipo: "Auto",
cupo_maximo: 50, activos: 1, disponible: 49 }, { uuid_tipo_vehiculo:
T_moto, tipo: "Moto", cupo_maximo: 0, activos: 0, disponible: 0 }],
generado_en: "2026-09-14T...Z" }`
**And** the `Cache-Control: no-store` header MUST be present.

#### Scenario: admin queries branch within permitted set returns 200
**Given** an `admin-` JWT carrying `claims["sucursales_permitidas"] = [X, Y]`
and the request includes `X-Sucursal-Context: X`
**When** the admin calls
`GET /operacion/ocupacion?uuid_sucursal=X`
**Then** the response MUST be `200 OK` with the breakdown for branch X.
**And** the `Cache-Control: no-store` header MUST be present.

#### Scenario: cupo not configured surfaces `disponible < 0`, response remains 200
**Given** branch X has `tipos_vehiculo(Auto, Moto)` vigente but no
`cantidad_vehiculos_sucursal` row for `(X, Auto)` (admin has not
configured capacity) and 3 active `ingreso(X, Auto)`
**When** an operator calls `GET /operacion/ocupacion?uuid_sucursal=X`
**Then** the response MUST be `200 OK` (NEVER `404` / `503`) with the
Auto item carrying `{ cupo_maximo: 0, activos: 3, disponible: -3 }`
**And** the `Cache-Control: no-store` header MUST be present.
**And** the client is the authority on UX (`-3` is interpreted as
"configuration missing, contact admin" — KD-6 invariant).

### REQ-OPS-031 — Per-sucursal authorization with typed errors (KD-3 chain)

**Given** a JWT request reaches `GET /api/v1/operacion/ocupacion` with
either an `operador-` or `admin-` issuer prefix
**When** the handler `get_ocupacion` resolves the target `uuid_sucursal`
**Then** the dependency chain MUST be `_ingreso_issuer_dep =
requires_issuer("operador-", "admin-")` (already defined at
`api/v1/operacion.py:64`) followed by `get_tenant_ctx` and `get_session`
**And** if `uuid_sucursal` query param is absent AND
`ctx.sucursal_uuid is None` (e.g. `admin-` issuer without
`X-Sucursal-Context` header and without `claims["sucursales_permitidas"]`),
the handler MUST raise `HTTPException(status_code=400, detail={"error":
"missing_sucursal_context"})`
**And** if the issuer is `operador-` AND `target != ctx.sucursal_uuid`
(cross-tenant), the handler MUST raise
`TenantScopeViolation(actor_uuid=ctx.actor_uuid)` (existing typed error
in `auth/tenancy.py:60-65`) which the global exception handler maps to
`403 {"error": "tenant_scope_violation"}`
**And** if the issuer is `admin-` AND `target not in
ctx.claims["sucursales_permitidas"]`, the handler MUST raise
`SucursalNotPermitted(target_sucursal=target)` (existing typed error in
`auth/tenancy.py:115-131`) which maps to
`403 {"error": "sucursal_not_permitted"}`
**And** the response body MUST contain **only** the typed error
discriminator (`tenant_scope_violation`, `sucursal_not_permitted`,
`missing_sucursal_context`); the pgcode `"23505"`, the raw Postgres
error message, the `uuid_sucursal` value, and any driver-level diagnostic
strings MUST NOT appear in the body, headers, or any log line emitted
at `info` or higher visibility
**And** the precedence MUST be strictly
`400 missing_sucursal_context > 403 tenant_scope_violation > 403 sucursal_not_permitted`;
no other ordering is permitted.
**RFC 2119**: MUST (issuer acceptance, 400, 403 mappings, no pgcode in
body, precedence); SHALL (log the rejection at `warning` level with
`event="ocupacion_authz_rejected"` and `actor_uuid`/`issuer_prefix` for
ops triage, but without the pgcode and without the target value).

#### Scenario: operador cross-tenant returns 403 `tenant_scope_violation`
**Given** an `operador-` JWT with `ctx.sucursal_uuid = X`
**When** the operator calls
`GET /operacion/ocupacion?uuid_sucursal=Y` (different branch)
**Then** the response MUST be `403 Forbidden` with body
`{"error": "tenant_scope_violation"}`
**And** the body MUST NOT contain `uuid_sucursal=Y`, no pgcode, no
driver string.

#### Scenario: admin without context returns 400 `missing_sucursal_context`
**Given** an `admin-` JWT without `X-Sucursal-Context` header AND without
`claims["sucursales_permitidas"]`
**When** the admin calls `GET /operacion/ocupacion` (no query param)
**Then** the response MUST be `400 Bad Request` with body
`{"error": "missing_sucursal_context"}`
**And** the body MUST NOT contain the `uuid_sucursal` value.

#### Scenario: admin outside permitted set returns 403 `sucursal_not_permitted`
**Given** an `admin-` JWT with `claims["sucursales_permitidas"] = [X]`
**When** the admin calls
`GET /operacion/ocupacion?uuid_sucursal=Z` (Z not in permits)
**Then** the response MUST be `403 Forbidden` with body
`{"error": "sucursal_not_permitted"}`
**And** the body MUST NOT contain `uuid_sucursal=Z`.

### REQ-OPS-032 — `prod.mv_ocupacion_diaria` materialized view with `CREATE UNIQUE INDEX CONCURRENTLY` + pre-flight `DO $$` (KD-7 10M NOTICE / 50M ABORT)

**Given** an Alembic migration `0024_add_mv_ocupacion_diaria.py` is
applied against a Postgres database where `prod.ingreso`,
`prod.salidas`, `prod.anulaciones`, `prod.tipos_vehiculo`,
`prod.cantidad_vehiculos_sucursal` already exist
**When** the migration's `upgrade()` executes
**Then** the migration MUST first execute a pre-flight `DO $$` block
that runs `SELECT count(*) INTO _n_ingreso FROM prod.ingreso`,
`SELECT count(*) INTO _n_anul FROM prod.anulaciones`, `SELECT count(*)
INTO _n_salidas FROM prod.salidas`, and emits
`RAISE NOTICE 'mv_ocupacion_diaria_preflight: prod.ingreso=% filas,
prod.salidas=% filas, prod.anulaciones=% filas. El primer REFRESH puede
tardar segundos a minutos.'`
**And** if `_n_ingreso > 50_000_000` (KD-7 hard limit), the block MUST
emit `RAISE EXCEPTION 'mv_ocupacion_diaria_preflight_abort: prod.ingreso
tiene % filas (umbral 50M). Aplique índice (uuid_sucursal,
uuid_tipo_vehiculo) en prod.ingreso antes de continuar.'` which aborts
the migration with a typed message; Alembic MUST record no version
bump on abort (rollback automatic)
**And** the migration MUST then execute `CREATE MATERIALIZED VIEW
prod.mv_ocupacion_diaria AS SELECT i.uuid_sucursal, i.uuid_tipo_vehiculo,
count(*) AS activos FROM prod.ingreso i WHERE i.uuid_tipo_vehiculo IS
NOT NULL AND NOT EXISTS (SELECT 1 FROM prod.salidas s WHERE
s.uuid_ingreso = i.uuid AND s.uuid_sucursal = i.uuid_sucursal) AND NOT
EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_ingreso = i.uuid
AND a.estado = 'ejecutada' AND a.tipo_anulable IN ('ingreso', 'salida'))
GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo`
**And** the migration MUST then execute `CREATE UNIQUE INDEX CONCURRENTLY
IF NOT EXISTS prod.uq_mv_ocupacion_diaria_sucursal_tipo ON
prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo)` —
mandatory for `REFRESH MATERIALIZED VIEW CONCURRENTLY` (KD-2); the
natural composite is unique by the view's `GROUP BY`, NO synthetic
column is added
**And** the migration MUST then execute `GRANT SELECT ON
prod.mv_ocupacion_diaria TO parkos_app`
**And** `revision` MUST equal `"0024_mv_ocupacion_diaria"` and
`down_revision` MUST equal `"0023_unique_active_sesion_per_user"` (F1.3
chain head, commit `ca3f9bf`)
**And** `downgrade()` MUST execute `DROP MATERIALIZED VIEW IF EXISTS
prod.mv_ocupacion_diaria` (drops the view + its indexes).
**RFC 2119**: MUST (pre-flight, threshold constants, MV definition,
CONCURRENTLY, GRANT, downgrade symmetry, chain head); SHALL (constants
`_PREFLIGHT_THRESHOLD_INFO = 10_000_000` and
`_PREFLIGHT_THRESHOLD_ABORT = 50_000_000` extracted at module level for
traceability); SHOULD (operator schedules rollback off-peak because
`DROP MATERIALIZED VIEW` acquires `AccessExclusiveLock` regardless of
`CONCURRENTLY`).

#### Scenario: pre-flight NOTICE at 10M rows, no abort
**Given** the `prod.ingreso` table holds between `10_000_001` and
`50_000_000` rows
**When** migration `0024_add_mv_ocupacion_diaria` applies
**Then** the pre-flight MUST emit a `RAISE NOTICE` carrying the exact
prefix `mv_ocupacion_diaria_preflight: prod.ingreso=` with the row count
**And** the migration MUST NOT abort (10M is informational only).
**And** the view MUST be created, the UNIQUE INDEX applied, and the
GRANT issued.

#### Scenario: pre-flight EXCEPTION at 50M+ rows aborts the migration
**Given** the `prod.ingreso` table holds `50_000_001` rows (or more)
**When** migration `0024_add_mv_ocupacion_diaria` applies
**Then** the pre-flight MUST emit `RAISE EXCEPTION` carrying the exact
prefix `mv_ocupacion_diaria_preflight_abort:` with the offending count
**And** Alembic MUST record no version bump (no half-applied state)
**And** the view MUST NOT exist after rollback (`prod.mv_ocupacion_diaria`
absent from `pg_class`).

#### Scenario: UNIQUE INDEX CONCURRENTLY is created outside transaction
**Given** a clean Postgres database where the migration is being applied
**When** the upgrade function reaches the UNIQUE INDEX statement
**Then** Postgres MUST execute `CREATE UNIQUE INDEX CONCURRENTLY IF NOT
EXISTS prod.uq_mv_ocupacion_diaria_sucursal_tipo ON
prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo)` without
acquiring `AccessExclusiveLock` on the underlying table
**And** `pg_index.indisunique` MUST equal `True` for the new index.
**And** the migration MUST be idempotent against `alembic upgrade` retries
(IF NOT EXISTS avoids `42P07` `duplicate_object`).

### REQ-OPS-033 — `RefreshMvOcupacionWorker` executes `REFRESH CONCURRENTLY` + KD-5 fallback + `asyncio.sleep(refresh_interval_s=10)` post-cycle

**Given** a dedicated NSSM service runs
`python -m parkos_core.jobs.refresh_mv_ocupacion` against the branch
database with `PARKOS_BRANCH_DB_DSN` configured
**When** `RefreshMvOcupacionWorker(WorkerRunner)` enters its
`async def cycle()` body
**Then** the worker MUST first attempt
`await self._session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY
prod.mv_ocupacion_diaria"))` + `await self._session.commit()` (KD-5
happy path)
**And** if the CONCURRENTLY branch raises any exception (typically
because the UNIQUE INDEX was dropped, or because Postgres is under
load), the worker MUST log at `warning` level with structured
`extra={"event": "refresh_mv_concurrently_failed_fallback",
"exception_class": type(exc).__name__}` (NO pgcode, NO repr of the
exception, NO DSN fragment — R6 mitigation), MUST
`await self._session.rollback()`, and MUST fall back to
`await self._session.execute(text("REFRESH MATERIALIZED VIEW
prod.mv_ocupacion_diaria"))` + `await self._session.commit()` (KD-5
fallback, plain REFRESH, brief `AccessExclusiveLock`)
**And** if the fallback also raises, the worker MUST log at `error`
level with `extra={"event": "refresh_mv_ocupacion_both_branches_failed",
"exception_class": type(inner_exc).__name__}` and MUST
`await self._session.rollback()` — the worker MUST NOT crash the loop;
the next cycle retries fresh (NO circuit breaker)
**And** after the refresh — successful or fallback — the worker MUST
`await asyncio.sleep(self.refresh_interval_s)` (default `10s`, floored
to `max(5, ...)` in `__init__`) before the next cycle (R1 startup
resilience: refresh runs immediately after worker restart, not after
sleep)
**And** the CLI MUST be invokable as
`python -m parkos_core.jobs.refresh_mv_ocupacion --refresh-interval-s 10
--database-url $PARKOS_BRANCH_DB_DSN` with exit codes inherited from
`WorkerRunner` (0 success / 1 application error / 2 SIGTERM)
**And** the `WorkerRunner` base (`backend/packages/parkos_core/src/
parkos_core/jobs/runner.py`) MUST remain unmodified — verified by the
`worker_base_intact` CI gate (`git diff jobs/runner.py` returns empty).
**RFC 2119**: MUST (cycle shape, KD-5 fallback, inner-resilience, log
shape with `exception_class` only, post-cycle sleep, CLI, base intact);
SHALL (the structured log keys `event` and `exception_class` be present
in every warning/error line emitted by the worker cycle); SHOULD
(deploy ONE service per branch DB — documented in the NSSM install guide,
not in code).

#### Scenario: normal cycle executes REFRESH CONCURRENTLY then sleeps
**Given** a `RefreshMvOcupacionWorker(session=mock, refresh_interval_s=10)`
with the UNIQUE INDEX present
**When** `cycle()` is awaited once
**Then** the worker MUST call `session.execute` with exactly
`text("REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria")`
**And** the worker MUST call `session.commit()`
**And** the worker MUST call `asyncio.sleep(10)` AFTER the refresh
(post-cycle sleep, R1 resilience).

#### Scenario: KD-5 fallback when CONCURRENTLY fails
**Given** a `RefreshMvOcupacionWorker(session=mock_with_concurrently_failure,
refresh_interval_s=10)` whose first `session.execute` raises
`psycopg2.errors.FeatureNotSupported` (simulating missing UNIQUE INDEX)
**When** `cycle()` is awaited
**Then** the worker MUST log a `warning` line with structured
`event="refresh_mv_concurrently_failed_fallback"` and
`exception_class="FeatureNotSupported"`
**And** the worker MUST call `session.rollback()`
**And** the worker MUST call `session.execute` again with exactly
`text("REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria")` (plain,
no `CONCURRENTLY`)
**And** the worker MUST call `session.commit()`
**And** the worker MUST NOT raise (the cycle completes — KD-5 acceptance).
**And** the captured log MUST NOT contain the substring `pgcode` or the
literal `"23505"` (R6 mitigation).

#### Scenario: both branches fail does not crash the loop
**Given** a `RefreshMvOcupacionWorker(session=mock_double_failure)` whose
both REFRESH attempts raise exceptions
**When** `cycle()` is awaited
**Then** the worker MUST log an `error` line with structured
`event="refresh_mv_ocupacion_both_branches_failed"` and
`exception_class=...` (matching the inner exception class)
**And** the worker MUST call `session.rollback()` (twice)
**And** the worker MUST return normally without raising (next cycle
retries fresh — no crash, no circuit breaker).

## ADDED Requirements

### REQ-OPS-034 — V1: `cupo_no_configurado` returns 422 with `forzado_permitido: true`

**Given** branch `X` has `prod.tipos_vehiculo(Auto)` vigente
(`vigente_hasta IS NULL AND estado='activo'`) but NO row in
`prod.cantidad_vehiculos_sucursal(X, Auto)` (admin has not configured
capacity) and a JWT request reaches `POST /api/v1/operacion/ingresos`
with valid KD-3 tenant context resolved for `X`
**When** the dedicated handler `create_ingreso` invokes
`repo/ocupacion.py::validar_cupo_disponible(session, *, uuid_sucursal=X,
uuid_tipo_vehiculo=T_auto, forzado=false)` after V5 regex has derived
`T_auto` from the placa
**Then** the helper MUST return a result indicating
`cupo_no_configurado=true` (no `cantidad_vehiculos_sucursal` row for
`(X, T_auto)`)
**And** the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"cupo_no_configurado", "forzado_permitido": True})`
**And** no INSERT into `prod.ingreso` MUST occur
**And** the response MUST include the header `Cache-Control: no-store`
(consistent with F1.3 / F1.5 / F1.8 R8).
**RFC 2119**: MUST (422 shape, `forzado_permitido: true` literal,
no INSERT, header).

#### Scenario: operador posts valid placa on unconfigured branch without forzado returns 422

**Given** an `operador-` JWT with `ctx.sucursal_uuid = X`, branch X has
`tipos_vehiculo(Auto)` vigente and 0 `cantidad_vehiculos_sucursal` rows
**When** the operator POSTs `{"placa": "ABC123"}` (no `forzado`,
no `observaciones`)
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "cupo_no_configurado", "forzado_permitido": true}`
**And** `prod.ingreso` MUST have no new rows.

#### Scenario: admin posts valid placa on unconfigured branch with forzado bypass returns 201 (no alerta, V1 alone)

**Given** the same unconfigured branch state
**When** the admin POSTs `{"placa": "ABC123", "forzado": true,
"observaciones": "[FORZADO: branch sin cupo configurado por admin nuevo]"}`
**Then** the response MUST be `201 Created` with the happy-path body
**And** `prod.alerta` MUST NOT receive a new `capacidad_agotada_forzado`
row (R2 mitigation: alerta only when V2 was bypassed, not V1 — V1 bypass
is "cupo missing", not "cupo full").

### REQ-OPS-035 — V2: `motivo_forzado_requerido` returns 422 with `cupo_maximo` / `activos`; forzado bypass INSERTs + emits alerta

**Given** branch `X` has `prod.cantidad_vehiculos_sucursal(X, Auto)` with
`cantidad = 50` and `prod.mv_ocupacion_diaria` (refreshed within the
last `2 × refresh_interval_s = 20s`, F1.5) reports `activos = 50` for
`(X, Auto)` (cupo agotado) and a JWT request reaches
`POST /api/v1/operacion/ingresos` with KD-3 chain resolved for `X`
**When** the handler invokes
`repo/ocupacion.py::validar_cupo_disponible(session, *, uuid_sucursal=X,
uuid_tipo_vehiculo=T_auto, forzado=false)`
**Then** the helper MUST return `cupo_no_configurado=false,
cupo_agotado=true, cupo_maximo=50, activos=50`
**And** the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"motivo_forzado_requerido", "cupo_maximo": 50, "activos": 50})`
**And** no INSERT into `prod.ingreso` MUST occur
**And** no `prod.alerta` row MUST be inserted (R2 — V2 was not bypassed).
**RFC 2119**: MUST (422 shape with literal keys, `cupo_agotado` detection,
no INSERT, no alerta on rejection).

#### Scenario: cupo agotado sin forzado returns 422 with cupo_maximo + activos

**Given** the cupo-agotado state above
**When** the operator POSTs `{"placa": "ABC123"}` (no `forzado`)
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "motivo_forzado_requerido", "cupo_maximo": 50, "activos": 50}`
**And** `prod.ingreso` MUST have no new rows.

#### Scenario: cupo agotado con forzado válido returns 201 and emits `capacidad_agotada_forzado` alerta same TX

**Given** the cupo-agotado state above
**When** the operator POSTs `{"placa": "ABC123", "forzado": true,
"observaciones": "[FORZADO: cliente con cita medica urgente 2026-09-14]"}`
**Then** the handler MUST pass V2 (`cupo_result.cupo_agotado=true AND
forzado=true` ⇒ bypass, `bypass_reason="cupo_agotado"`) and proceed to
the INSERT path
**And** the handler MUST INSERT a row into `prod.ingreso` (`[L-E]`)
**And** the handler MUST INSERT a row into `prod.alerta` with
`tipo_alerta='capacidad_agotada_forzado'`, `estado='abierta'`,
`datos_nuevos` carrying the motivo string (jsonb)
**And** both INSERTs MUST commit in the SAME `await session.commit()`
call (R5 — no huérfanas)
**And** the response MUST be `201 Created` with `IngresoReadForzado`
**And** `Cache-Control: no-store` MUST be present.

### REQ-OPS-036 — V3: `tarifa_vigente_no_encontrada` returns 422 unless `forzado=true` (bi-temporal canónico from F1.4)

**Given** no row in `prod.tarifas_sucursal(X, T_auto)` satisfies the
bi-temporal canónico predicate
`vigente_desde <= NOW() AND (vigente_hasta IS NULL OR vigente_hasta >
NOW()) AND estado='activo'` (F1.4 `bitemporal_vigente_predicate`,
`repo/tarifas_vigencia.py` constant) at `datetime.now(UTC)`
**When** the handler invokes
`repo/tarifas_vigencia.py::validar_tarifa_vigente(session, *,
uuid_sucursal=X, uuid_tipo_vehiculo=T_auto, at=now(UTC),
forzado=bypass_reason)`
**Then** the helper MUST return `vigente=false`
**And** the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"tarifa_vigente_no_encontrada"})`
**And** no INSERT into `prod.ingreso` MUST occur.
**RFC 2119**: MUST (bi-temporal predicate reuse from F1.4, 422 shape,
no INSERT).

#### Scenario: tarifa no vigente sin forzado returns 422

**Given** `prod.tarifas_sucursal(X, Auto)` has only one row with
`vigente_hasta = '2025-01-01'` (already expired) and the request has
`forzado=false`
**When** the operator POSTs `{"placa": "ABC123"}`
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "tarifa_vigente_no_encontrada"}`.

#### Scenario: tarifa no vigente con forzado válido bypasses V3

**Given** the same expired-tarifa state
**When** the operator POSTs `{"placa": "ABC123", "forzado": true,
"observaciones": "[FORZADO: tarifa en renegociacion con operador X]"}`
**Then** the handler MUST pass V3 (forzado bypass) and proceed; no alerta
is emitted for V3 bypass (R2 — alerta only for V2 bypass).

### REQ-OPS-037 — V4: `tipo_vehiculo_invalido` returns 422; no bypass (catalog bug, not operational)

**Given** the `uuid_tipo_vehiculo` derived by V5 regex resolution maps
to either (a) no row in `prod.tipos_vehiculo` with that UUID, or (b) a
row with `vigente_hasta IS NOT NULL` (tipo dado de baja) or
`estado='inactivo'`
**When** the handler invokes
`repo/ingreso.py::validar_tipo_vehiculo_vigente(session, *,
uuid_tipo_vehiculo=T)`
**Then** the helper MUST return `False`
**And** the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"tipo_vehiculo_invalido"})`
**And** the handler MUST NOT honor `forzado=true` for V4 — V4 is a
catalog integrity defect (R-KD-V3): the operator cannot force a catalog
fix by stamping `forzado`
**And** no INSERT into `prod.ingreso` MUST occur.
**RFC 2119**: MUST (422 shape, `False` detection on missing OR
`vigente_hasta IS NOT NULL` OR `estado='inactivo'`, no bypass on
`forzado=true`).

#### Scenario: catalog missing the regex-derived tipo returns 422

**Given** `prod.tipos_vehiculo` has NO row with `tipo='Auto'` even
though `FORMATO_AUTO` regex matches the placa `ABC123`
**When** the handler invokes `validar_tipo_vehiculo_vigente(...)`
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "tipo_vehiculo_invalido"}`
**And** the handler MUST NOT proceed even with `forzado=true`.

#### Scenario: tipo dado de baja (`vigente_hasta IS NOT NULL`) returns 422

**Given** `prod.tipos_vehiculo` has `tipo='Auto'` with
`vigente_hasta = '2026-01-01'`
**When** the operator POSTs `{"placa": "ABC123"}`
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "tipo_vehiculo_invalido"}`.

### REQ-OPS-038 — V5: regex placa Colombia server-side + `placa_formato_invalido` 422 + `uuid_tipo_vehiculo` derivado y sobreescrito (BR2 CU-01)

**Given** the request body contains `placa` as a string (after V5
sequence begins; this is V5's input)
**When** the handler invokes
`repo/placa.py::detectar_tipo_vehiculo(placa)` with the regex constants
`FORMATO_AUTO = r"^[A-Z]{3}[0-9]{3}$"` (Auto) and
`FORMATO_MOTO = r"^[A-Z]{3}[0-9]{2}[A-Z]$"` (Moto), lazy lookup against
`prod.tipos_vehiculo(tipo)` vigente
**Then** if the regex matches `FORMATO_AUTO`, the helper MUST return the
UUID of `tipos_vehiculo` where `tipo='Auto'` AND
`vigente_hasta IS NULL AND estado='activo'`
**And** if the regex matches `FORMATO_MOTO`, the helper MUST return the
UUID of `tipos_vehiculo` where `tipo='Moto'` AND vigente
**And** if neither regex matches, the helper MUST return `None`
**And** if the helper returns `None`, the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"placa_formato_invalido", "formatos_aceptados": ["ABC123", "ABC12D"]})`
**And** the handler MUST overwrite the client-supplied
`uuid_tipo_vehiculo` with the regex-derived UUID before passing to V4
(BR2 CU-01, D-HU-F1.6-6 — defense in depth against stale client).
**RFC 2119**: MUST (regex constants at module level, lazy UUID lookup,
422 shape with literal `formatos_aceptados`, server-side overwrite);
SHALL (the regex constants live in `repo/placa.py` as module-level
constants so a future HU can swap them in one place).

#### Scenario: placa Auto `ABC123` deriva `tipo='Auto'` UUID y sobreescribe cliente

**Given** a valid JWT, `tipos_vehiculo(Auto)` vigente, and the request
carries `{"placa": "ABC123", "uuid_tipo_vehiculo":
"<uuid_moto_incorrecto>"}` (client bug)
**When** the operator POSTs the payload
**Then** the handler MUST use the `Auto` UUID (regex-derived) and
overwrite the Moto UUID before V4 — the operator sees 201, not 422.

#### Scenario: placa `abc123` (lowercase) returns 422 `placa_formato_invalido`

**Given** the lowercase string does not match `FORMATO_AUTO`
**When** the operator POSTs `{"placa": "abc123"}`
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "placa_formato_invalido", "formatos_aceptados":
["ABC123", "ABC12D"]}`.

#### Scenario: placa `AB12C` (4 chars / mixed) returns 422

**Given** neither regex matches `AB12C`
**When** the operator POSTs `{"placa": "AB12C"}`
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "placa_formato_invalido", "formatos_aceptados":
["ABC123", "ABC12D"]}`.

### REQ-OPS-039 — V6: `subscripcion_inactiva_o_vencida` returns 422 unless `forzado=true` (walk-in auditado)

**Given** the request body contains
`uuid_subscripcion_cliente = S` (non-None)
**When** the handler invokes
`repo/subscripcion_activa.py::validar_subscripcion_vigente(session, *,
uuid_subscripcion_cliente=S, forzado=bypass_reason)` which checks
`vigente_hasta IS NULL AND estado='activo' AND fecha_vencimiento >=
NOW()` against `prod.subscripciones_cliente`
**Then** if all three predicates hold, the helper MUST return
`vigente=true`
**And** if any predicate fails, the helper MUST return `vigente=false`
**And** when `vigente=false` AND `forzado=false`, the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"subscripcion_inactiva_o_vencia"})`
**And** when `vigente=false` AND `forzado=true`, the handler MUST accept
the request as a walk-in auditado (D-HU-F1.6-2 + KD-V3 — vencida is
operational, not catalog) and proceed; no alerta is emitted for V6
bypass (R2).
**RFC 2119**: MUST (three predicates AND-ed, 422 shape, no alerta on
V6 bypass).

#### Scenario: subscripcion vigente procede sin forzado

**Given** `prod.subscripciones_cliente(S)` has
`vigente_hasta IS NULL`, `estado='activo'`,
`fecha_vencimiento = '2026-12-31'` (future)
**When** the operator POSTs `{"placa": "ABC123",
"uuid_subscripcion_cliente": "S"}` (no `forzado`)
**Then** the handler MUST pass V6 and proceed to V8 / INSERT.

#### Scenario: subscripcion vencida sin forzado returns 422

**Given** `prod.subscripciones_cliente(S)` has
`fecha_vencimiento = '2026-01-01'` (past)
**When** the operator POSTs `{"placa": "ABC123",
"uuid_subscripcion_cliente": "S"}` (no `forzado`)
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "subscripcion_inactiva_o_vencida"}`.

#### Scenario: subscripcion inactiva (`estado='inactivo'`) sin forzado returns 422

**Given** `prod.subscripciones_cliente(S)` has `estado='inactivo'`
**When** the operator POSTs `{"placa": "ABC123",
"uuid_subscripcion_cliente": "S"}` (no `forzado`)
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "subscripcion_inactiva_o_vencida"}`.

#### Scenario: subscripcion vencida con forzado válido walks-in

**Given** the past-vencimiento state above
**When** the operator POSTs `{"placa": "ABC123",
"uuid_subscripcion_cliente": "S", "forzado": true,
"observaciones": "[FORZADO: cliente pago en efectivo tras vencer 2026-01-15]"}`
**Then** the handler MUST pass V6 (walk-in auditado) and proceed to V8 /
INSERT — the resulting ingreso is `MENSUALIDAD` (V9 derivation,
REQ-OPS-041) for ops reconciliation in F7.

### REQ-OPS-040 — V8: `ingreso_activo_existente` returns 409 with `uuid_ingreso_existente`; `EXISTS` directo a tablas (no MV, no lock)

**Given** the request body has reached V8 (all prior validations passed)
**When** the handler invokes
`repo/ingreso.py::existe_ingreso_activo(session, *, uuid_sucursal=X,
placa=P)` which executes `EXISTS (SELECT 1 FROM prod.ingreso i WHERE
i.uuid_sucursal=X AND i.placa=P AND NOT EXISTS (SELECT 1 FROM
prod.salidas s WHERE s.uuid_ingreso=i.uuid AND
s.uuid_sucursal=i.uuid_sucursal) AND NOT EXISTS (SELECT 1 FROM
prod.anulaciones a WHERE a.uuid_ingreso=i.uuid AND a.estado='ejecutada'
AND a.tipo_anulable IN ('ingreso','salida')))`
**Then** if the predicate returns a row, the helper MUST return the
`uuid` of the existing active ingreso
**And** the handler MUST raise
`HTTPException(status_code=409, detail={"error":
"ingreso_activo_existente", "uuid_ingreso_existente": "<uuid>"})`
**And** the handler MUST NOT acquire any `SELECT … FOR UPDATE/SHARE`
lock — KD-V4 eventual consistency via `mv_ocupacion_diaria` is
acceptable for V2 (R8); V8 goes directly to the authoritative tables
(< 50ms p99 expected; EXPLAIN ANALYZE confirmed in design.md).
**RFC 2119**: MUST (predicate shape with two `NOT EXISTS` clauses, 409
with literal `uuid_ingreso_existente` key, no pessimistic lock).

#### Scenario: placa activa sin salida ni anulación returns 409

**Given** `prod.ingreso` already contains `(uuid_sucursal=X,
placa=ABC123)` with no row in `prod.salidas` and no row in
`prod.anulaciones` with `estado='ejecutada'`
**When** the operator POSTs `{"placa": "ABC123"}` (all prior V
validations pass)
**Then** the response MUST be `409 Conflict` with body
`{"error": "ingreso_activo_existente", "uuid_ingreso_existente":
"<existing_uuid>"}`
**And** `prod.ingreso` MUST have no new rows.

#### Scenario: placa con salida previa no anulada permite nuevo ingreso

**Given** the existing `(X, ABC123)` ingreso has a non-anulada row in
`prod.salidas` (the previous ciclo closed)
**When** the operator POSTs `{"placa": "ABC123"}`
**Then** `existe_ingreso_activo` MUST return `None` (the previous activo
was eliminated by the salida) and the handler MUST proceed to INSERT a
new `prod.ingreso` row.

#### Scenario: placa con anulación ejecutada permite nuevo ingreso

**Given** the existing `(X, ABC123)` ingreso has a row in
`prod.anulaciones` with `estado='ejecutada' AND
tipo_anulable='ingreso'`
**When** the operator POSTs `{"placa": "ABC123"}`
**Then** `existe_ingreso_activo` MUST return `None` and the handler
MUST proceed to INSERT.

### REQ-OPS-041 — V9 + KD-FORZADO-01: `tipo_entrada` derivado server-side (nunca persistido) + bypass contract + alerta `capacidad_agotada_forzado`

This requirement bundles three related contracts that share the same
INVOCATION path through the handler:

**(A) V9 — `tipo_entrada` derivación server-side (DEC-SUC-21)**:
**Given** the INSERT path has reached the response-build step (all V
validations passed)
**When** the handler derives `tipo_entrada`
**Then** the handler MUST set `tipo_entrada = "MENSUALIDAD"` if and only
if `payload.uuid_subscripcion_cliente is not None` (the `forzado` flag
is irrelevant — a walk-in with `forzado=true` still resolves to
`MENSUALIDAD` if a `uuid_subscripcion_cliente` was provided), else
`"ROTACION"`
**And** the handler MUST include `tipo_entrada` in the
`IngresoReadForzado` response body
**And** the handler MUST NOT persist `tipo_entrada` in any column of
`prod.ingreso` (DEC-SUC-21 — derived value, not a column).

**(B) KD-FORZADO-01 — bypass contract (A-04)**:
**Given** the request body carries `observaciones` (possibly None) and
`forzado` (bool)
**When** the handler invokes
`repo/ingreso.py::validar_kd_forzado(observaciones, forzado)` (the
prefix constant `FORZADO_PREFIX = "[FORZADO: "` and
`FORZADO_MIN_MOTIVO_CHARS = 10` live at module level)
**Then** the helper MUST enforce exactly three discriminators:

1. If `forzado=false` AND `observaciones` starts with `FORZADO_PREFIX`,
   the helper MUST raise `HTTPException(status_code=422, detail={"error":
   "forzado_contradiccion"})` — D-HU-F1.6-5 defense in depth (the
   prefix is the source of truth, not the bool flag).
2. If `forzado=true` AND `observaciones` is None OR does not start with
   `FORZADO_PREFIX`, the helper MUST raise `HTTPException(status_code=422,
   detail={"error": "motivo_forzado_requerido"})`.
3. If `forzado=true` AND `observaciones` starts with `FORZADO_PREFIX` AND
   the motivo (substring after `FORZADO_PREFIX`, `rstrip("]")`) has
   `len(motivo.strip()) < FORZADO_MIN_MOTIVO_CHARS = 10`, the helper MUST
   raise `HTTPException(status_code=422, detail={"error":
   "motivo_forzado_insuficiente", "min_chars": 10})`.

**And** on a valid `forzado=true` + valid prefix + motivo ≥10 chars, the
helper MUST return the stripped motivo string (and the handler records
`forzado_en_creacion=true` + `motivo_forzado=<motivo>` in the response).

**(C) Alerta `capacidad_agotada_forzado` same-TX INSERT (R2 + R5)**:
**Given** the INSERT step for `prod.ingreso` is reached AND
`bypass_reason == "cupo_agotado"` (V2 was bypassed)
**When** the handler invokes `repo/event.record_event` for the `[L-E]`
insert
**Then** the handler MUST immediately afterwards (in the same
transaction) invoke
`repo/alerta.py::insertar_alerta_forzado(session, *, uuid_sucursal=X,
uuid_ingreso=new_row.uuid, actor_uuid=ctx.actor_uuid, motivo=<motivo>)`
which INSERTs into `prod.alerta` with
`tipo_alerta='capacidad_agotada_forzado'`, `estado='abierta'`, and the
motivo in `datos_nuevos` (jsonb)
**And** both INSERTs MUST commit in ONE `await session.commit()` call —
no `INSERT` for alerta without a corresponding `INSERT` for ingreso
(no huérfanas, R5 mitigation)
**And** if `bypass_reason != "cupo_agotado"` (for example, V1, V3, or V6
bypassed), the handler MUST NOT INSERT a `capacidad_agotada_forzado`
alerta — R2 mitigation (alerta only on V2 bypass, not other bypasses).
**RFC 2119**: MUST (V9 derivation rule, prefix constants, three
discriminators with literal key names, alerta only on V2 bypass, single
commit for ingreso + alerta).

#### Scenario: V9 happy path MENSUALIDAD con subscripcion vigente

**Given** the request carries `{"placa": "ABC123",
"uuid_subscripcion_cliente": "S"}` and V6 passed
**When** the handler builds the response
**Then** the response MUST be `201 Created` with
`IngresoReadForzado` carrying
`{"tipo_entrada": "MENSUALIDAD", "forzado_en_creacion": false,
"motivo_forzado": null, …}`
**And** a `SELECT tipo_entrada FROM prod.ingreso WHERE uuid=<new>`
MUST error with "column does not exist" (DEC-SUC-21 — never persisted).

#### Scenario: V9 happy path ROTACION sin subscripcion

**Given** the request carries `{"placa": "ABC123"}` (no
`uuid_subscripcion_cliente`)
**When** the handler builds the response
**Then** the response MUST be `201 Created` with
`{"tipo_entrada": "ROTACION", "forzado_en_creacion": false,
"motivo_forzado": null, …}`.

#### Scenario: KD-FORZADO-01 `forzado_contradiccion` when forzado=false with prefix

**Given** the request carries `{"placa": "ABC123", "forzado": false,
"observaciones": "[FORZADO: prueba cliente]"}`
**When** the handler invokes `validar_kd_forzado(observaciones, forzado)`
**Then** the helper MUST raise `HTTPException(422, {"error":
"forzado_contradiccion"})` (the bool flag contradicts the prefix).

#### Scenario: KD-FORZADO-01 `motivo_forzado_requerido` when forzado=true without prefix

**Given** the request carries `{"placa": "ABC123", "forzado": true,
"observaciones": "cliente sin placa"}` (no prefix)
**When** the handler invokes `validar_kd_forzado(observaciones, forzado)`
**Then** the helper MUST raise `HTTPException(422, {"error":
"motivo_forzado_requerido"})`.

#### Scenario: KD-FORZADO-01 `motivo_forzado_insuficiente` when motivo <10 chars

**Given** the request carries `{"placa": "ABC123", "forzado": true,
"observaciones": "[FORZADO: a b]"}` (motivo "a b" = 3 chars after
prefix + rstrip)
**When** the handler invokes `validar_kd_forzado(observaciones, forzado)`
**Then** the helper MUST raise `HTTPException(422, {"error":
"motivo_forzado_insuficiente", "min_chars": 10})`.

#### Scenario: KD-FORZADO-01 valid bypass on cupo agotado emits alerta same TX as ingreso

**Given** cupo agotado for `(X, Auto)` (REQ-OPS-035 scenario)
**When** the operator POSTs `{"placa": "ABC123", "forzado": true,
"observaciones": "[FORZADO: cliente con cita medica urgente 2026-09-14]"}`
**Then** `validar_kd_forzado` returns the stripped motivo
**And** V2 is bypassed with `bypass_reason="cupo_agotado"`
**And** the `prod.ingreso` INSERT and the `prod.alerta` INSERT both commit
in ONE `await session.commit()` (verified by integration test
`test_ingreso_create_db.py::T1`)
**And** the response carries `{"tipo_entrada": "ROTACION",
"forzado_en_creacion": true, "motivo_forzado": "cliente con cita
medica urgente 2026-09-14", …}`.

#### Scenario: KD-FORZADO-01 valid bypass on V1 (cupo no configurado) does NOT emit alerta

**Given** branch X has no `cantidad_vehiculos_sucursal` for Auto
(REQ-OPS-034 scenario)
**When** the operator POSTs `{"placa": "ABC123", "forzado": true,
"observaciones": "[FORZADO: branch sin cupo configurado por admin nuevo]"}`
**Then** the handler MUST proceed (V1 bypassed) and commit the ingreso
INSERT
**And** the handler MUST NOT call `insertar_alerta_forzado` — R2
mitigation (alerta only on V2 bypass)
**And** `prod.alerta` MUST have no new rows for this UUID.

#### Scenario: V9 `tipo_entrada=MENSUALIDAD` is derived even when forzado=true

**Given** the request carries `{"placa": "ABC123",
"uuid_subscripcion_cliente": "S", "forzado": true,
"observaciones": "[FORZADO: cliente pago en efectivo tras vencer 2026-01-15]"}`
(REQ-OPS-039 walk-in auditado scenario)
**When** the handler builds the response
**Then** the response MUST carry `{"tipo_entrada": "MENSUALIDAD",
"forzado_en_creacion": true, "motivo_forzado": "cliente pago en
efectivo tras vencer 2026-01-15", …}` — `tipo_entrada` is keyed on
`uuid_subscripcion_cliente`, NOT on `forzado` (V9 invariant).

### REQ-OPS-042 — POST /operacion/salidas contract: handler `create_salida` with `SalidaCreateForzado` / `SalidaReadForzado`, KD-3 tenant scope, `Cache-Control: no-store`, Idempotency-Key header

**Given** the FastAPI router `api/v1/operacion.py` already hosts
`@router.post("/ingresos", ...)` (F1.6, lines 132-294) and `api/v1/__init__.py`
mounts `r.include_router(operacion.router)` at line 143 (no changes to
`__init__.py`)
**When** the new handler `@router.post("/salidas", response_model=SalidaReadForzado, status_code=201)` is registered on the same custom `APIRouter`
(line 52) with the signature `async def create_salida(response: Response,
payload: SalidaCreateForzado, session: AsyncSession = Depends(get_session),
ctx: TenantContext = Depends(get_tenant_ctx), _claims: None = Depends(_ingreso_issuer_dep)) -> SalidaReadForzado`
**Then** the handler MUST accept a JSON body `SalidaCreateForzado` with
`extra='forbid'` (inherited from `_Base`) carrying the required field
`uuid_ingreso: uuid_lib.UUID` and the optional fields `placa: str | None`,
`observaciones: str | None`, `forzado: bool = False` — rejecting any extra
field (defense-in-depth against `tipo_salida` injection, DEC-SUC-21-NEW)
**And** MUST resolve the target `uuid_sucursal` **server-side** from the
ingreso located in V1 (the client does not send `uuid_sucursal`; this is a
behavioral delta from F1.6 where the client supplied the sucursal in the
payload)
**And** MUST respond `201 Created` with `SalidaReadForzado` carrying the
fields `uuid`, `created_at`, `created_by`, `sync_status`, `sync_timestamp`,
`sync_attempts`, `uuid_sucursal`, `uuid_ingreso`, `fecha_salida`, plus the
NEW F1.7 fields `tipo_salida: Literal["MENSUALIDAD", "ROTACION"]`,
`forzado_en_creacion: bool = False`, `motivo_forzado: str | None = None`,
and `cotizacion_snapshot: CotizarFacturacion | None = None`
**And** MUST set the header `Cache-Control: no-store` on every 2xx, 4xx,
and 5xx response (aligned with F1.3 / F1.5 / F1.6 / F1.8 precedents)
**And** MUST be guarded by `_ingreso_issuer_dep = requires_issuer("operador-",
"admin-")` so only those JWT roles can POST (KD-3 chain reuso)
**And** MUST rely on the PR2 `Idempotency-Key` HTTP header for retry
deduplication (DEC-IDEM-01) — the payload MUST NOT carry a `correlacion_id`
field (rejected by `extra='forbid'`).
**RFC 2119**: MUST (response shape, `extra='forbid'`, `Cache-Control: no-store`,
issuer dep, Idempotency-Key delegation).

#### Scenario: rotación exitosa with full payload returns 201 ROTACION snapshot

**Given** an existing `prod.ingreso` with `uuid_ingreso=:p` and
`uuid_sucursal=:s`, no `prod.salidas` linked to it, and a vigente
`prod.tarifas_sucursal` row for `(s, tipo_vehiculo)` at `datetime.now(UTC)`
**And** an `operador-:s` JWT (or `admin-` with :s in `sucursales_permitidas`)
**And** a vigente `prod.impuestos` row with `codigo='IVA'` and `porcentaje > 0`
(post-MIGRATION 0026 deploy)
**When** the client sends `POST /api/v1/operacion/salidas` with
`{"uuid_ingreso":":p","placa":"ABC123","observaciones":null,"forzado":false}`
and header `Idempotency-Key: <uuid>`
**Then** the server MUST insert one row in `prod.salidas` with
`uuid_ingreso=:p`, `uuid_sucursal=:s`, `fecha_salida=NOW()`,
`fecha_retencion_hasta=fecha_salida + 2 years`
**And** MUST respond `201 Created` with `SalidaReadForzado{tipo_salida:"ROTACION",
forzado_en_creacion:false, motivo_forzado:null, cotizacion_snapshot:{...}}`
**And** MUST set `Cache-Control: no-store` on the response.

#### Scenario: mensualidad exitosa returns 201 MENSUALIDAD with `cotizacion_snapshot: None`

**Given** an existing `prod.ingreso` with `uuid_ingreso=:p` and
`uuid_subscripcion_cliente=:sub` where `:sub` is vigente at `NOW()` (per
`validar_subscripcion_vigente` predicate `vigente_hasta IS NULL AND
estado='activo' AND fecha_vencimiento >= NOW()`)
**When** the client sends `POST /api/v1/operacion/salidas` with
`{"uuid_ingreso":":p"}` (no `placa`, no `forzado`, no `observaciones`)
**Then** the server MUST respond `201 Created` with `SalidaReadForzado{
`tipo_salida:"MENSUALIDAD"`, `forzado_en_creacion:false`,
`motivo_forzado:null`, `cotizacion_snapshot:null}`
**And** MUST set `Cache-Control: no-store` on the response
**And** MUST NOT insert any row in `prod.alerta` (no bypass was used).

### REQ-OPS-043 — V1 ingreso activo exists: `404 ingreso_no_encontrado` unified discriminator

**Given** the request body carries `uuid_ingreso=:p` and the handler has
resolved KD-3 issuer claims via `_ingreso_issuer_dep`
**When** the handler invokes
`repo/salida.py::buscar_ingreso_activo_por_uuid(session,
*, uuid_ingreso=:p)` which executes
`SELECT i.* FROM prod.ingreso i WHERE i.uuid = :p AND i.vigente_hasta IS
NULL AND NOT EXISTS (SELECT 1 FROM prod.salidas s WHERE s.uuid_ingreso = i.uuid
AND NOT EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_salida = s.uuid
AND a.tipo_anulable = 'salida' AND a.estado = 'ejecutada'))`
**Then** the helper MUST return `None` if any of the following hold:
the `uuid_ingreso` does not exist in `prod.ingreso`; the ingreso already
has a non-anulada row in `prod.salidas`; or the ingreso was anulado (DEC-SUC-21,
analogous "no hay nada que cerrar")
**And** if `None`, the handler MUST raise
`HTTPException(status_code=404, detail={"error":
"ingreso_no_encontrado", "uuid_ingreso": str(:p)}, headers={"Cache-Control":
"no-store"})`
**And** MUST NOT honor `forzado=true` for V1 — V1 is a correctness
invariant (D-HU-F1.7-6; without an ingreso, there is nothing to close)
**And** MUST NOT insert any row in `prod.ingreso`, `prod.salidas`, or
`prod.alerta`.
**RFC 2119**: MUST (single 404 discriminator for the three unified cases,
no bypass on `forzado=true`, `Cache-Control: no-store` header).

#### Scenario: uuid_ingreso inexistente returns 404

**Given** no row in `prod.ingreso` with `uuid=:p`
**When** the client sends `POST /operacion/salidas` with `{"uuid_ingreso":":p"}`
**Then** the response MUST be `404 Not Found` with body
`{"error":"ingreso_no_encontrado","uuid_ingreso":":p"}`
**And** the response MUST carry `Cache-Control: no-store`
**And** `prod.salidas` MUST have no new rows.

#### Scenario: ingreso ya con salida no anulada returns 404 (KD-S1 unified)

**Given** `prod.ingreso` with `uuid=:p` exists with `vigente_hasta IS NULL`
**And** `prod.salidas` contains a row with `uuid_ingreso=:p` and no row in
`prod.anulaciones` references that salida with `tipo_anulable='salida' AND
estado='ejecutada'`
**When** the client sends `POST /operacion/salidas` with `{"uuid_ingreso":":p"}`
**Then** the response MUST be `404 Not Found` with body
`{"error":"ingreso_no_encontrado","uuid_ingreso":":p"}` (operationally
equivalent to "no existe" — there is nothing to close).

#### Scenario: ingreso anulado returns 404 (KD-S1 unified)

**Given** `prod.ingreso` with `uuid=:p` was anulado (a row in
`prod.anulaciones` with `tipo_anulable='ingreso' AND estado='ejecutada'`
references `:p`)
**When** the client sends `POST /operacion/salidas` with `{"uuid_ingreso":":p"}`
**Then** the response MUST be `404 Not Found` with body
`{"error":"ingreso_no_encontrado","uuid_ingreso":":p"}` (KD-S1 — same
unified discriminator).

### REQ-OPS-044 — V2 subscripción vigente al momento salida: reuso verbatim F1.6 `validar_subscripcion_vigente`; 422 sin forzado; alerta `subscripcion_vencida_forzado` con forzado

**Given** V1 passed (REQ-OPS-043) and the located `ingreso` has
`uuid_subscripcion_cliente=:sub` (non-None)
**When** the handler invokes
`repo/subscripcion_activa.py::validar_subscripcion_vigente(session, *,
uuid_subscripcion_cliente=:sub, forzado=bool(bypass_reason))` (the F1.6
helper reused verbatim, no modification)
**Then** the helper MUST apply the three-predicate AND:
`vigente_hasta IS NULL AND estado='activo' AND fecha_vencimiento >= NOW()`
against `prod.subscripciones_cliente`
**And** MUST return `vigente=true` only if all three predicates hold;
otherwise `vigente=false`
**And** when `vigente=false AND forzado=false`, the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"subscripcion_inactiva_o_vencida"}, headers={"Cache-Control":"no-store"})`
and MUST NOT insert any row in `prod.salidas` or `prod.alerta`
**And** when `vigente=false AND forzado=true` (a valid KD-FORZADO-01
bypass from V4), the handler MUST accept the request as a "walk-in
auditado" (F1.6 D-HU-F1.6-2) and proceed with `bypass_reason =
"subscripcion_vencida"` so the Step 9 alerta (REQ-OPS-050) inserts
`subscripcion_vencida_forzado` same-TX as the salida INSERT
**And** MUST re-validate at the moment of salida (not trust the snapshot
of the ingreso) — the subscripción may have expired since ingreso
(estacionamiento prolongado, monthly subscription that expired during
the stay).
**RFC 2119**: MUST (three-predicate AND, verbatim F1.6 reuse, 422 shape,
no bypass on `forzado=false`, alerta path on `forzado=true`, re-validate
at `NOW()`).

#### Scenario: subscripcion vigente al momento salida proceeds without forzado

**Given** `prod.subscripciones_cliente(:sub)` has `vigente_hasta IS NULL`,
`estado='activo'`, `fecha_vencimiento = '2026-12-31'` (future)
**And** V1 passed with `ingreso.uuid_subscripcion_cliente = :sub`
**When** the operator POSTs `{"uuid_ingreso":":p"}` (no `forzado`,
no `observaciones`)
**Then** the handler MUST pass V2 with `vigente=true` and proceed to V3,
V4, V5, INSERT (REQ-OPS-048), and 201 response
**And** MUST NOT insert any row in `prod.alerta` (no bypass was used).

#### Scenario: subscripcion vencida al momento salida sin forzado returns 422

**Given** `prod.subscripciones_cliente(:sub)` has `fecha_vencimiento =
'2026-01-01'` (past)
**And** V1 passed with `ingreso.uuid_subscripcion_cliente = :sub`
**When** the operator POSTs `{"uuid_ingreso":":p"}` (no `forzado`)
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error":"subscripcion_inactiva_o_vencida"}`
**And** MUST carry `Cache-Control: no-store`
**And** `prod.salidas` MUST have no new rows
**And** `prod.alerta` MUST have no new rows.

#### Scenario: subscripcion vencida al momento salida con forzado válido proceeds + alerta `subscripcion_vencida_forzado`

**Given** the past-`fecha_vencimiento` state above
**And** V1 passed
**When** the operator POSTs `{"uuid_ingreso":":p","forzado":true,
"observaciones":"[FORZADO: cliente pago en efectivo tras vencer 2026-01-15]"}`
**Then** V4 (REQ-OPS-046) MUST return the stripped motivo and set
`bypass_reason="forzado"`
**And** V2 MUST mark `bypass_reason="subscripcion_vencida"` for the alerta
discriminator
**And** V3 (if `placa` provided) MUST pass, V5 MUST compute
`cobrar=true` from `prod.calcular_cotizacion(:p)` (F1.8 PL/pgSQL returns
`cobrar:true` when no active subscription is found at the branch — the
subscription expired, so it falls through to rotación pricing)
**And** the INSERT in REQ-OPS-048 MUST commit with
`tipo_salida="ROTACION"`
**And** the alerta (REQ-OPS-050) MUST commit same-TX with
`tipo_alerta='subscripcion_vencida_forzado'`, `estado='abierta'`,
`datos_nuevos={motivo: "cliente pago en efectivo tras vencer 2026-01-15",
uuid_salida: <new>}`
**And** the response MUST be `201 Created` with `SalidaReadForzado{
tipo_salida:"ROTACION", forzado_en_creacion:true, motivo_forzado:"cliente
pago en efectivo tras vencer 2026-01-15", cotizacion_snapshot:{...}}`.

### REQ-OPS-045 — V3 placa matches ingreso: reuso verbatim F1.6 `detectar_tipo_vehiculo`; 422 sin bypass; placa opcional

**Given** V1 (REQ-OPS-043) and V2 (REQ-OPS-044, if applicable) passed,
and `payload.placa` is non-None (the placa field is optional per KD-S3 —
client may know `uuid_ingreso` from a QR scan but not remember the placa)
**When** the handler invokes
`repo/placa.py::detectar_tipo_vehiculo(payload.placa)` (F1.6 helper
reused verbatim) to derive the regex-based tipo `T_req`, and
`repo/placa.py::detectar_tipo_vehiculo(ingreso.placa)` to derive `T_ing`
**Then** if `T_req != T_ing` (mismatch in regex-derived vehicle type —
Auto vs Moto, or None vs tipo), the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"placa_no_coincide_con_ingreso", "placa_request": payload.placa,
"placa_ingreso": ingreso.placa}, headers={"Cache-Control":"no-store"})`
**And** if `payload.placa is None`, the server MUST skip V3 entirely
(trust the `uuid_ingreso` mapping)
**And** MUST NOT honor `forzado=true` for V3 — placa mismatch is a
correctness invariant (D-HU-F1.7-6: bug del operador or fraud attempt,
not operational state)
**And** MUST NOT insert any row in `prod.salidas` or `prod.alerta`.
**RFC 2119**: MUST (regex reuse verbatim F1.6, optional placa, 422 shape
with both placa values, no bypass on `forzado=true`).

#### Scenario: placa Auto matches ingreso Auto proceeds

**Given** V1 and V2 passed, `ingreso.placa = "ABC123"` (matches `FORMATO_AUTO`)
**When** the operator POSTs `{"uuid_ingreso":":p","placa":"ABC123"}`
**Then** V3 MUST pass (`T_req = T_ing = uuid_tipo_vehiculo(Auto)`)
**And** the handler MUST proceed to V4, V5, INSERT, and 201 response.

#### Scenario: placa Moto mismatches ingreso Auto returns 422

**Given** `ingreso.placa = "ABC123"` (Auto) and the request carries
`placa = "ABC12D"` (Moto)
**When** the operator POSTs `{"uuid_ingreso":":p","placa":"ABC12D"}`
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error":"placa_no_coincide_con_ingreso","placa_request":"ABC12D",
"placa_ingreso":"ABC123"}`
**And** MUST carry `Cache-Control: no-store`
**And** `prod.salidas` MUST have no new rows.

#### Scenario: placa omitida proceeds (KD-S3 trust uuid_ingreso)

**Given** V1 and V2 passed, `ingreso.placa = "ABC123"`
**When** the operator POSTs `{"uuid_ingreso":":p"}` (no `placa` field)
**Then** the handler MUST skip V3 and proceed to V4, V5, INSERT, and 201
response (the server trusts the uuid→placa mapping).

### REQ-OPS-046 — V4 KD-FORZADO-01 prefix contract: reusado verbatim de F1.6 (`repo/ingreso.py::validar_kd_forzado`); mismo set 422

**Given** the request body carries `observaciones` (possibly `None`) and
`forzado: bool` (default `False`), and V1, V2 (if applicable), V3 (if
applicable) passed
**When** the handler invokes
`repo/ingreso.py::validar_kd_forzado(payload.observaciones, payload.forzado)`
(F1.6 helper reused verbatim — single implementation, single test suite,
single audit; no modification)
**Then** the helper MUST enforce exactly three discriminators using the
module-level constants `FORZADO_PREFIX = "[FORZADO: "` and
`FORZADO_MIN_MOTIVO_CHARS = 10`:

1. If `forzado=false` AND `observaciones` starts with `FORZADO_PREFIX`,
   the helper MUST raise
   `HTTPException(status_code=422, detail={"error":"forzado_contradiccion"},
   headers={"Cache-Control":"no-store"})` — D-HU-F1.6-5 defense in
   depth (the prefix is the source of truth, not the bool flag).
2. If `forzado=true` AND (`observaciones is None` OR does not start with
   `FORZADO_PREFIX`), the helper MUST raise
   `HTTPException(status_code=422, detail={"error":
   "motivo_forzado_requerido"}, headers={"Cache-Control":"no-store"})`.
3. If `forzado=true` AND `observaciones` starts with `FORZADO_PREFIX` AND
   the motivo (substring after `FORZADO_PREFIX`, `rstrip("]")`) has
   `len(motivo.strip()) < FORZADO_MIN_MOTIVO_CHARS = 10`, the helper MUST
   raise `HTTPException(status_code=422, detail={"error":
   "motivo_forzado_insuficiente", "min_chars": 10}, headers={"Cache-Control":
   "no-store"})`.

**And** on a valid `forzado=true` + valid prefix + motivo ≥10 chars, the
helper MUST return the stripped motivo string (the handler records
`forzado_en_creacion=true` and `motivo_forzado=<motivo>` in the response)
**And** MUST set `bypass_reason = "forzado"` only after the helper returns
a valid stripped motivo (not on the bool flag alone — defense in depth).
**RFC 2119**: MUST (prefix constants verbatim F1.6, three discriminators
with literal key names, helper reused verbatim, `bypass_reason` set on
returned motivo only).

#### Scenario: KD-FORZADO-01 valid prefix + motivo ≥10 chars bypasses V2/V5

**Given** V1 passed and `ingreso.uuid_subscripcion_cliente = :sub` is
expired, and `prod.tarifas_sucursal` has no vigente row at `NOW()` for
the `(uuid_sucursal, uuid_tipo_vehiculo)` combination
**When** the operator POSTs `{"uuid_ingreso":":p","forzado":true,
"observaciones":"[FORZADO: cliente pago en efectivo tras vencer 2026-01-15]"}`
**Then** `validar_kd_forzado` MUST return the stripped motivo
`"cliente pago en efectivo tras vencer 2026-01-15"` (len ≥ 10)
**And** the handler MUST set `bypass_reason = "forzado"` initially
**And** the response MUST carry `forzado_en_creacion:true` and
`motivo_forzado:"cliente pago en efectivo tras vencer 2026-01-15"`.

#### Scenario: KD-FORZADO-01 `forzado_contradiccion` when `forzado=false` with prefix

**Given** the request carries `{"uuid_ingreso":":p","forzado":false,
"observaciones":"[FORZADO: prueba cliente]"}`
**When** the handler invokes `validar_kd_forzado(observaciones, forzado)`
**Then** the helper MUST raise `HTTPException(422, {"error":
"forzado_contradiccion"})` (the bool flag contradicts the prefix — the
prefix is the source of truth per D-HU-F1.6-5)
**And** MUST NOT insert any row in `prod.salidas` or `prod.alerta`.

#### Scenario: KD-FORZADO-01 `motivo_forzado_requerido` when `forzado=true` without prefix

**Given** the request carries `{"uuid_ingreso":":p","forzado":true,
"observaciones":"cliente sin placa"}` (no `[FORZADO: ` prefix)
**When** the handler invokes `validar_kd_forzado(observaciones, forzado)`
**Then** the helper MUST raise `HTTPException(422, {"error":
"motivo_forzado_requerido"})`.

#### Scenario: KD-FORZADO-01 `motivo_forzado_insuficiente` when motivo <10 chars

**Given** the request carries `{"uuid_ingreso":":p","forzado":true,
"observaciones":"[FORZADO: a b]"}` (motivo `"a b"` = 3 chars after prefix
+ `rstrip("]")`)
**When** the handler invokes `validar_kd_forzado(observaciones, forzado)`
**Then** the helper MUST raise `HTTPException(422, {"error":
"motivo_forzado_insuficiente", "min_chars": 10})`.

### REQ-OPS-047 — V5 tarifa vigente via `prod.calcular_cotizacion(:uuid_ingreso)` (F1.8 PL/pgSQL VOLATILE, KD-S7 lock continuity); 422 sin forzado; alerta `tarifa_vigente_forzado` con forzado; 500 post-0026: never

**Given** V1, V2 (if applicable), V3 (if applicable), V4 passed, and the
`bypass_reason` is determined
**When** the handler invokes
`repo/salida.py::cotizar_para_salida(session, *, uuid_ingreso=:p)` which
delegates to `repo/cotizacion.py::cotizar_ingreso(session, uuid_ingreso=:p)`
(F1.8 thin wrapper) and that wrapper executes
`SELECT prod.calcular_cotizacion(:p)` — the F1.8 PL/pgSQL function with
`LANGUAGE plpgsql VOLATILE` (REQ-OPS-025 deviation letter, user approved
2026-09-14) which acquires `SELECT … FOR SHARE` on the matching
`prod.tarifas_sucursal` row at the bi-temporal predicate
`vigente_desde <= NOW() AND (vigente_hasta IS NULL OR vigente_hasta > NOW())
AND estado='activo'` (F1.4 `bitemporal_vigente_predicate` reused verbatim)
**Then** the F1.8 function MUST return one of these JSONB payloads, in
strict precedence order:

- `{"cobrar": true, subtotal, iva, total, tiempo_minutos, tarifa_uuid,
  vigente_hasta}` → the handler MUST derive `tipo_salida = "ROTACION"` (per
  REQ-OPS-049) and `cotizacion_snapshot` MUST be populated in the response.
- `{"cobrar": false, motivo: "mensualidad_vigente"}` → the handler MUST
  derive `tipo_salida = "MENSUALIDAD"` (per REQ-OPS-049) and
  `cotizacion_snapshot` MUST be `None` (KD-S4).
- `{"error": "ingreso_no_encontrado"}` → covered by V1 (REQ-OPS-043).
- `{"error": "tarifa_no_vigente"}` → if `bypass_reason` is None, the
  handler MUST raise `HTTPException(status_code=422, detail={"error":
  "tarifa_vigente_no_encontrada"}, headers={"Cache-Control":"no-store"})`
  and MUST NOT insert any row in `prod.salidas` or `prod.alerta`; if
  `bypass_reason` is set, the handler MUST set
  `bypass_reason = "tarifa_no_vigente"` for the alerta discriminator in
  REQ-OPS-050 and proceed with INSERT.
- `{"error": "iva_no_configurado"}` → the handler MUST raise
  `HTTPException(status_code=500, detail={"error":"iva_no_configurado"},
  headers={"Cache-Control":"no-store"})`. Post-MIGRATION 0026 deploy
  (REQ-OPS-052), this MUST never occur because the IVA row is seeded.

**And** the `prod.calcular_cotizacion` invoke MUST execute **inside the
same transaction** as the INSERT into `prod.salidas` (Step 8, REQ-OPS-048)
and the alerta INSERT (Step 9, REQ-OPS-050) — the `FOR SHARE` lock
acquired on `prod.tarifas_sucursal` is held through `session.commit()`
(KD-S7 lock continuity invariant). The handler MUST NOT use
sub-transactions, `SAVEPOINT`, or multiple `session.commit()` calls
**And** the precedence MUST be strictly
`ingreso_no_encontrado > tarifa_no_vigente > iva_no_configurado`; a
single response MUST never combine two error codes.
**RFC 2119**: MUST (F1.8 verbatim reuse, FOR SHARE continuity in same TX,
422 shape for `tarifa_no_vigente`, 500 shape for `iva_no_configurado`,
precedence, single commit).

#### Scenario: tarifa vigente returns 201 ROTACION with full fiscal breakdown

**Given** V1, V2, V3, V4 passed (no `forzado`)
**And** `prod.tarifas_sucursal(s, tipo_vehiculo)` has a vigente row at
`datetime.now(UTC)`
**When** the handler invokes `cotizar_para_salida(session, uuid_ingreso=:p)`
**Then** `prod.calcular_cotizacion(:p)` MUST return
`{"cobrar":true,"subtotal":X,"iva":Y,"total":Z,"tiempo_minutos":N,"tarifa_uuid":...,
"vigente_hasta":"..."}`
**And** the handler MUST derive `tipo_salida="ROTACION"` and the INSERT in
REQ-OPS-048 MUST commit
**And** the response MUST be `201 Created` with `SalidaReadForzado{
tipo_salida:"ROTACION", forzado_en_creacion:false, motivo_forzado:null,
cotizacion_snapshot:{...}}` (KD-S4 snapshot populated for ROTACION).

#### Scenario: tarifa no vigente sin forzado returns 422

**Given** V1, V2, V3, V4 passed (no `forzado`)
**And** `prod.tarifas_sucursal(s, tipo_vehiculo)` has NO row satisfying the
bi-temporal predicate at `NOW()`
**When** the handler invokes `cotizar_para_salida(session, uuid_ingreso=:p)`
**Then** `prod.calcular_cotizacion(:p)` MUST return `{"error":
"tarifa_no_vigente"}`
**And** the handler MUST raise `HTTPException(422, {"error":
"tarifa_vigente_no_encontrada"})`
**And** MUST carry `Cache-Control: no-store`
**And** `prod.salidas` MUST have no new rows
**And** `prod.alerta` MUST have no new rows.

#### Scenario: tarifa no vigente con forzado válido proceeds + alerta `tarifa_vigente_forzado`

**Given** the same expired-tarifa state and a valid KD-FORZADO-01 bypass
from V4 with motivo ≥10 chars
**When** the handler invokes `cotizar_para_salida(session, uuid_ingreso=:p)`
**Then** `prod.calcular_cotizacion(:p)` MUST return `{"error":
"tarifa_no_vigente"}`
**And** the handler MUST set `bypass_reason = "tarifa_no_vigente"`
**And** the INSERT in REQ-OPS-048 MUST commit with `tipo_salida="ROTACION"`
**And** the alerta (REQ-OPS-050) MUST commit same-TX with
`tipo_alerta='tarifa_vigente_forzado'`, `estado='abierta'`,
`datos_nuevos={motivo: <stripped motivo>, uuid_salida: <new>}`
**And** the response MUST be `201 Created` with `SalidaReadForzado{
tipo_salida:"ROTACION", forzado_en_creacion:true, motivo_forzado:<motivo>,
cotizacion_snapshot:{...}}`.

#### Scenario: iva_no_configurado (KD-IVA pre-0026) returns 500

**Given** MIGRATION 0026 has NOT been applied (pre-deploy state, or
post-deploy with the IVA row deleted for testing)
**And** V1, V2, V3, V4 passed
**And** `prod.tarifas_sucursal` has a vigente row
**When** the handler invokes `cotizar_para_salida(session, uuid_ingreso=:p)`
**Then** `prod.calcular_cotizacion(:p)` MUST return `{"error":
"iva_no_configurado"}`
**And** the handler MUST raise `HTTPException(500, {"error":
"iva_no_configurado"})` (this error MUST never occur post-MIGRATION 0026
deploy per REQ-OPS-052).

### REQ-OPS-048 — INSERT `prod.salidas` `[A]` append-only via `repo/salida.py::crear_salida_evento`; defense in depth (REVOKE + trigger + partial unique index); NUNCA UPDATE (DEC-SAL-01)

**Given** V1, V2 (if applicable), V3 (if applicable), V4, V5 passed (all
prior validations passed; either `bypass_reason` is set or no bypass was
needed)
**When** the handler invokes
`repo/salida.py::crear_salida_evento(session, *, actor_uuid=ctx.actor_uuid,
new_attrs={"uuid_sucursal": target_sucursal, "uuid_ingreso": payload.uuid_ingreso,
"fecha_salida": datetime.now(UTC).replace(tzinfo=None),
"fecha_retencion_hasta": date.today() + relativedelta(years=2)})` (KD-S6
retention 2 years from `fecha_salida`)
**Then** the helper MUST INSERT one row in `prod.salidas` via the
`models/L_S/salida.py::Salida(LifecycleEventBase)` ORM model with the
audit + sync mixins inherited from the base class
**And** MUST NOT acquire a `FOR UPDATE` or `FOR SHARE` lock on `prod.ingreso`
(KD-V4: read-mostly; the partial unique index `one_exit_per_ingreso` from
REQ-OPS-051 closes the TOCTOU race)
**And** MUST map any `IntegrityError` whose `err.orig` (psycopg2/asyncpg)
contains the string `"one_exit_per_ingreso"` to the typed exception
`SalidaDuplicada`, which the handler MUST translate to
`HTTPException(status_code=409, detail={"error":"salida_duplicada",
"uuid_ingreso": str(payload.uuid_ingreso)}, headers={"Cache-Control":
"no-store"})`
**And** MUST NOT persist any of the following in `prod.salidas` columns
(DEC-SUC-21-NEW + DEC-SUC-23): `tipo_salida`, `valor`, `subtotal`, `iva`,
`total`, `cobrar`, `forzado`, `motivo_forzado` — these belong in the
response (`SalidaReadForzado`) and/or in `prod.alerta.datos_nuevos` (when
bypassed), never in the `[A]` event row
**And** MUST respect the defense-in-depth at DB layer:
- `REVOKE UPDATE, DELETE ON prod.salidas FROM parkos_app` (migration 0001
  línea 2923) — already applied
- `CREATE TRIGGER fn_salidas_inmutable BEFORE UPDATE OR DELETE ON
  prod.salidas` (migration 0001 líneas 1990-2003) — already applied
- `CREATE UNIQUE INDEX one_exit_per_ingreso ON prod.salidas (uuid_ingreso)
  WHERE NOT EXISTS (anulaciones ejecutadas)` (MIGRATION 0026 Op 4, REQ-OPS-051)
  — applied in F1.7 apply phase
**And** the INSERT MUST commit in the SAME `await session.commit()` call as
the alerta INSERT in REQ-OPS-050 (R5 mitigation — no orphan alerts, no
orphan salidas without alerts when bypassed).
**RFC 2119**: MUST (single INSERT via `Salida` ORM, `IntegrityError` →
`SalidaDuplicada` → 409, no monto/tipo in columns, REVOKE + trigger +
index all respected, same TX as alerta).

#### Scenario: INSERT exitosa sin bypass commits in same TX

**Given** V1, V2, V3, V4, V5 passed, no `forzado` flag, no bypass used
**When** the handler invokes `crear_salida_evento(session, ...)`
**Then** one row MUST be INSERTed in `prod.salidas` with the computed
`uuid_sucursal`, `uuid_ingreso`, `fecha_salida`, `fecha_retencion_hasta`
**And** the response MUST be `201 Created` with `SalidaReadForzado{...}`
carrying `forzado_en_creacion:false` and `motivo_forzado:null`
**And** NO row in `prod.alerta` MUST be inserted (no bypass).

#### Scenario: INSERT conflictiva por partial unique index returns 409 `salida_duplicada`

**Given** V1 passed and `prod.salidas` already has a row with
`uuid_ingreso=:p` (no anulación ejecutada referencing that salida's UUID)
**When** the handler invokes `crear_salida_evento(session, ...)`
**Then** Postgres MUST raise `UniqueViolationError` (sqlstate `23505`)
violating the `one_exit_per_ingreso` index
**And** `crear_salida_evento` MUST catch the `IntegrityError` and raise
`SalidaDuplicada`
**And** the handler MUST translate to
`HTTPException(409, {"error":"salida_duplicada","uuid_ingreso":":p"})`
**And** MUST carry `Cache-Control: no-store`.

#### Scenario: type_salida NO persisted in prod.salidas (DEC-SUC-21-NEW AST guard)

**Given** the INSERT committed
**When** a direct query `SELECT tipo_salida FROM prod.salidas WHERE
uuid=<new>` is executed against the DB
**Then** the query MUST error with `column "tipo_salida" does not exist`
(DEC-SUC-21-NEW — `prod.salidas` has no `tipo_salida` column by 4FN
design, and the AST walk `tests/static/test_no_write_after_salida_insert.py`
verifies that `repo/salida.py::crear_salida_evento` does not introduce
one in the future).

### REQ-OPS-049 — `tipo_salida = MENSUALIDAD | ROTACION` derivado server-side (DEC-SUC-21-NEW, DEC-FORZADO-01 irrelevante); retornado en `SalidaReadForzado`; NUNCA persistido

**Given** V5 (REQ-OPS-047) returned `cotizacion` from
`prod.calcular_cotizacion(:p)`, and the INSERT in REQ-OPS-048 committed
(or is about to commit in the same TX)
**When** the handler derives `tipo_salida` from `cotizacion`
**Then** the handler MUST set `tipo_salida = "MENSUALIDAD"` if and only
if `cotizacion.get("cobrar") is False` (the F1.8 PL/pgSQL short-circuit on
`resolve_active_subscription_for_exit` returned `cobrar:false,
motivo:"mensualidad_vigente"` because the plate has an active subscription
vigente at `NOW()` at this branch)
**And** MUST set `tipo_salida = "ROTACION"` otherwise (any of: `cobrar:true`
with a vigente tarifa, OR `error:tarifa_no_vigente` bypassed with
`forzado=true`)
**And** MUST include `tipo_salida` in the `SalidaReadForzado` response body
**And** MUST NOT persist `tipo_salida` in any column of `prod.salidas`
(DEC-SUC-21-NEW — derived value, not a column, by 4FN design); the
analogous `tipo_entrada` for ingreso (F1.6 DEC-SUC-21) shares the same
invariant
**And** MUST derive `tipo_salida` keyed on the `cobrar` flag, NOT on
`forzado` (D-HU-F1.7-11: KD-FORZADO-01 is irrelevant to the derivation —
a monthly subscriber who is forced to walk-in because their subscription
expired during the stay still gets `tipo_salida="ROTACION"` because F1.8
returns `cobrar:true` for "no subscription at branch" — see REQ-OPS-044
Scenario "subscripcion vencida con forzado válido").
**RFC 2119**: MUST (literal `cobrar` flag rule, NEVER persisted, returned
in response, keyed on F1.8 output).

#### Scenario: mensualidad derivation returns 201 MENSUALIDAD

**Given** V1, V2, V3, V4, V5 passed
**And** `prod.calcular_cotizacion(:p)` returned
`{"cobrar":false,"motivo":"mensualidad_vigente"}` (F1.8 short-circuit per
REQ-OPS-023)
**When** the handler derives `tipo_salida` and builds the response
**Then** `tipo_salida` MUST be `"MENSUALIDAD"`
**And** `cotizacion_snapshot` MUST be `None` (KD-S4 — mensualidad
subscribers do not get billed for the exit; no fiscal breakdown)
**And** the response MUST be `201 Created` with `SalidaReadForzado{
tipo_salida:"MENSUALIDAD", forzado_en_creacion:false, motivo_forzado:null,
cotizacion_snapshot:null}`
**And** a direct query `SELECT tipo_salida FROM prod.salidas WHERE
uuid=<new>` MUST error with "column does not exist" (DEC-SUC-21-NEW).

#### Scenario: rotación derivation returns 201 ROTACION

**Given** V1, V2, V3, V4, V5 passed
**And** `prod.calcular_cotizacion(:p)` returned
`{"cobrar":true,"subtotal":X,"iva":Y,"total":Z,"tiempo_minutos":N,
"tarifa_uuid":...,"vigente_hasta":"..."}` (REQ-OPS-047)
**When** the handler derives `tipo_salida` and builds the response
**Then** `tipo_salida` MUST be `"ROTACION"`
**And** `cotizacion_snapshot` MUST be populated with the full fiscal
breakdown (KD-S4 — snapshot populated for ROTACION)
**And** the response MUST be `201 Created` with `SalidaReadForzado{
tipo_salida:"ROTACION", ..., cotizacion_snapshot:{...}}`.

#### Scenario: walk-in mensualidad (sub vencida + forzado) sigue siendo ROTACION

**Given** `ingreso.uuid_subscripcion_cliente = :sub` is expired at salida
time, and `forzado=true` with motivo ≥10 chars
**When** the handler runs V2 (sets `bypass_reason="subscripcion_vencida"`),
V5 (F1.8 finds no active subscription at branch → `cobrar:true`)
**Then** `tipo_salida` MUST be `"ROTACION"` (keyed on `cobrar=true`, NOT
on the original `uuid_subscripcion_cliente`)
**And** the response MUST carry `forzado_en_creacion:true` and
`motivo_forzado:<motivo>` (KD-FORZADO-01 marker preserved independently).

### REQ-OPS-050 — alerta same-TX for V2/V5 bypass (`subscripcion_vencida_forzado` or `tarifa_vigente_forzado`); one alerta per bypassed validation; DEF-INDEX no orphan alerts (R5)

**Given** the INSERT in REQ-OPS-048 reached Step 9 (alertas), and
`bypass_reason` is one of `"subscripcion_vencida"`, `"tarifa_no_vigente"`,
or unset/no bypass
**When** the handler invokes the alerta path
**Then** if `bypass_reason is None` (no bypass), the handler MUST NOT
insert any row in `prod.alerta` (R2 mitigation — alerta only on V2/V5
bypass, not other bypasses)
**And** if `bypass_reason == "subscripcion_vencida"`, the handler MUST
invoke `repo/salida.py::insertar_alerta_salida_forzado(session, *,
uuid_sucursal=target_sucursal, uuid_salida=new_row.uuid,
actor_uuid=ctx.actor_uuid, motivo=<stripped motivo>,
tipo_alerta="subscripcion_vencida_forzado")`
**And** if `bypass_reason == "tarifa_no_vigente"`, the handler MUST
invoke `repo/salida.py::insertar_alerta_salida_forzado(session, *,
uuid_sucursal=target_sucursal, uuid_salida=new_row.uuid,
actor_uuid=ctx.actor_uuid, motivo=<stripped motivo>,
tipo_alerta="tarifa_vigente_forzado")`
**And** each invocation MUST INSERT one row in `prod.alerta` with
`tipo_alerta=<above>`, `estado='abierta'`, `timestamp_evento=NOW()`,
`datos_nuevos={"motivo": <motivo>, "uuid_salida": <new_row.uuid>}`
(jsonb, F1.6 R-A2 audit), `uuid_sucursal=<target>`,
`uuid_usuario=<actor_uuid>`
**And** the alerta INSERT MUST commit in the SAME
`await session.commit()` call as the salida INSERT (REQ-OPS-048) — no
`session.commit()` between the two INSERTs (R5 mitigation against orphan
alerts)
**And** if the alerta INSERT fails (FK violation, etc.), the salida INSERT
MUST rollback atomically — no huérfanas (R5 verification via
integration test `test_insert_salida_con_alerta_forzado_atomico`)
**And** the `alert_types_inmutable` trigger (migration 0013) MUST be
respected — the handler MUST NOT attempt UPDATE/DELETE on
`prod.alert_types` (the alert_type rows are inserted by MIGRATION 0026
Op 3 with INSERT-only privileges for `rol_app`).
**RFC 2119**: MUST (one alerta per bypassed validation, `datos_nuevos`
jsonb shape, same TX as salida INSERT, atomic rollback, alert_type trigger
respected).

#### Scenario: V2 bypass (sub vencida) emits `subscripcion_vencida_forzado` same TX

**Given** V2 was bypassed (`bypass_reason="subscripcion_vencida"`) and
Step 8 INSERT in REQ-OPS-048 reached Step 9
**When** the handler invokes `insertar_alerta_salida_forzado(session, ...,
tipo_alerta="subscripcion_vencida_forzado")`
**Then** `prod.alerta` MUST receive one new row with
`tipo_alerta='subscripcion_vencida_forzado'`, `estado='abierta'`,
`datos_nuevos={"motivo":<motivo>,"uuid_salida":<new>}`,
`uuid_sucursal=<target>`, `uuid_usuario=<actor>`
**And** both the salida INSERT and the alerta INSERT MUST commit in ONE
`await session.commit()` call.

#### Scenario: V5 bypass (tarifa no vigente) emits `tarifa_vigente_forzado` same TX

**Given** V5 was bypassed (`bypass_reason="tarifa_no_vigente"`) and
Step 8 INSERT in REQ-OPS-048 reached Step 9
**When** the handler invokes `insertar_alerta_salida_forzado(session, ...,
tipo_alerta="tarifa_vigente_forzado")`
**Then** `prod.alerta` MUST receive one new row with
`tipo_alerta='tarifa_vigente_forzado'`, `estado='abierta'`,
`datos_nuevos={"motivo":<motivo>,"uuid_salida":<new>}`,
`uuid_sucursal=<target>`, `uuid_usuario=<actor>`
**And** both the salida INSERT and the alerta INSERT MUST commit in ONE
`await session.commit()` call.

#### Scenario: no bypass used — no alerta emitted (R2)

**Given** V1, V2, V3, V4, V5 all passed without `forzado=true`
(`bypass_reason is None`)
**When** Step 9 executes
**Then** the handler MUST NOT insert any row in `prod.alerta` (R2
mitigation — alerta only on V2/V5 bypass)
**And** only the salida INSERT commits.

#### Scenario: alerta INSERT falla — salida INSERT rollback (R5 atomic)

**Given** the alerta INSERT in Step 9 fails (FK violation simulated in
integration test, e.g. `uuid_usuario` references a non-existent user)
**When** the single `await session.commit()` call is reached
**Then** both the salida INSERT and the alerta INSERT MUST rollback
together — `prod.salidas` MUST have no new rows for this attempt, and
`prod.alerta` MUST have no new rows (verified by
`test_insert_salida_con_alerta_forzado_atomico` in
`tests/integration/test_salida_create_db.py`).

### REQ-OPS-051 — partial unique index `one_exit_per_ingreso` on `prod.salidas` (MIGRATION 0026 Op 4); `UniqueViolationError` → 409 `salida_duplicada`; cierra TOCTOU race en V1 EXISTS subquery (R4)

**Given** MIGRATION 0026 Op 4 has been applied:
`CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_exit_per_ingreso
ON prod.salidas (uuid_ingreso)
WHERE NOT EXISTS (
    SELECT 1 FROM prod.anulaciones a
    WHERE a.uuid_salida = prod.salidas.uuid
      AND a.tipo_anulable = 'salida'
      AND a.estado = 'ejecutada'
);`
**When** the handler in Step 8 (REQ-OPS-048) calls
`repo/salida.py::crear_salida_evento(session, ...)` and Postgres raises
`UniqueViolationError` (sqlstate `23505`) because a non-anulada row in
`prod.salidas` already has the same `uuid_ingreso=:p`
**Then** `crear_salida_evento` MUST catch the `IntegrityError` whose
`err.orig` (psycopg2/asyncpg) contains the substring `"one_exit_per_ingreso"`,
and MUST re-raise as the typed exception `SalidaDuplicada`
**And** the handler MUST translate `SalidaDuplicada` to
`HTTPException(status_code=409, detail={"error":"salida_duplicada",
"uuid_ingreso": str(payload.uuid_ingreso)}, headers={"Cache-Control":
"no-store"})`
**And** MUST NOT retry the INSERT (defense in depth — the partial unique
index is the authoritative closure of the TOCTOU race in V1 EXISTS
subquery per R4; retries would mask concurrent requests)
**And** the partial predicate MUST allow a new `prod.salidas` row for the
same `uuid_ingreso` if the previous one was anulada — the `NOT EXISTS`
subquery on `prod.anulaciones WHERE tipo_anulable='salida' AND
estado='ejecutada'` excludes the anulada case, so a new INSERT succeeds
after anulación ejecutada (DEC-SAL-01 + R4 mitigation — defense in depth
without violating the original append-only semantics for non-anuladas).
**RFC 2119**: MUST (substring detection on `err.orig`, 409 shape with
literal `uuid_ingreso`, no retry, `NOT EXISTS` partial predicate
respecting anulación ejecutada).

#### Scenario: second POST same uuid_ingreso returns 409

**Given** `prod.salidas` already has a row with `uuid_ingreso=:p` and no
anulación ejecutada references that salida's UUID
**When** the client sends a second `POST /operacion/salidas` with
`{"uuid_ingreso":":p"}`
**Then** the response MUST be `409 Conflict` with body
`{"error":"salida_duplicada","uuid_ingreso":":p"}`
**And** MUST carry `Cache-Control: no-store`
**And** `prod.salidas` MUST have no new rows for this second request.

#### Scenario: salida anulada allows a new salida for same uuid_ingreso

**Given** `prod.salidas` has a row with `uuid_ingreso=:p` and
`uuid=<old_salida>`
**And** `prod.anulaciones` has a row with `uuid_salida=<old_salida>`,
`tipo_anulable='salida'`, `estado='ejecutada'`
**When** the client sends `POST /operacion/salidas` with `{"uuid_ingreso":":p"}`
**Then** the partial unique index predicate MUST evaluate `NOT EXISTS` as
`true` (the anulación ejecutada excludes the old salida)
**And** the INSERT MUST succeed, committing a new `prod.salidas` row with
a new `uuid=<new_salida>`
**And** the response MUST be `201 Created` with `SalidaReadForzado{...}`.

### REQ-OPS-052 — inline-seed `impuestos.IVA` en MIGRATION 0026 Op 2 (`codigo='IVA'`, `porcentaje=0.19`); KD-IVA blocker de F1.8 resuelto; pre-flight abort si `prod.impuestos` no existe

**Given** MIGRATION 0026 Op 1 (pre-flight `DO $$` block) has verified that
`prod.impuestos`, `prod.salidas`, and `prod.alert_types` tables exist in
the DB schema (KD-7 pattern from F1.6 migration 0024):
- If `_n_impuestos IS NULL OR _n_impuestos = 0` → RAISE EXCEPTION
  `'0026_preflight_abort: tabla prod.impuestos no existe. Aplique
  migrations 0001-0025 antes.'`
- If `_n_salidas IS NULL OR _n_salidas = 0` → RAISE EXCEPTION
  `'0026_preflight_abort: tabla prod.salidas no existe.'`
- If `_n_alert_types IS NULL OR _n_alert_types = 0` → RAISE EXCEPTION
  `'0026_preflight_abort: tabla prod.alert_types no existe.'`

**Then** MIGRATION 0026 Op 2 MUST execute the following inline-seed:
```sql
INSERT INTO prod.impuestos (
    uuid, codigo, nombre, porcentaje,
    valid_desde, vigente_hasta, estado, created_at
) VALUES (
    gen_random_uuid(), 'IVA', 'IVA', 0.19,
    NOW() AT TIME ZONE 'UTC', NULL, 'activo', NOW()
)
ON CONFLICT (codigo, vigente_desde) DO NOTHING;
```

**And** `porcentaje=0.19` MUST be the regulatory constant for IVA Colombia
2026 (locked in F1.8 design.md §4 KD-IVA; F1.7 respects the same value)
**And** the UK constraint `(codigo, vigente_desde)` MUST be the
idempotency key — running MIGRATION 0026 a second time MUST be a no-op
(verified by `tests/integration/test_migration_0026_idempotent.py`)
**And** after MIGRATION 0026 deploy, the F1.8 PL/pgSQL function
`prod.calcular_cotizacion` MUST NOT return `iva_no_configurado` for any
valid `(uuid_sucursal, uuid_tipo_vehiculo)` combination with a vigente
tarifa — the KD-IVA blocker is resolved
**And** the row MUST be insertable by `rol_app` (the `impuestos`
permissions MUST allow INSERT for the alembic migration context; the
handler reads via `prod.calcular_cotizacion` which bypasses rol_app
directly via PL/pgSQL execution)
**And** the MIGRATION 0026 Op 2 insert MUST commit before any F1.7 test
runs (DEC-IMP-01: ownership of the catalog scope remains HU-F14.2
Parte II; F1.7 apply advances the dependency as a side effect, mirroring
F1.6's `INSERT … ON CONFLICT (tipo_alerta) DO NOTHING` in MIGRATION
0025).
**RFC 2119**: MUST (pre-flight on 3 tables, `porcentaje=0.19` constant,
UK `(codigo, vigente_desde)` for idempotency, no `iva_no_configurado`
post-deploy).

#### Scenario: MIGRATION 0026 first apply seeds IVA successfully

**Given** MIGRATION 0025 (`alerta_datos_nuevos`) is the current `head` and
`prod.impuestos`, `prod.salidas`, `prod.alert_types` tables exist
**When** `alembic upgrade head` runs MIGRATION 0026
**Then** Op 1 (pre-flight) MUST NOT raise (all 3 tables exist)
**And** Op 2 MUST insert one row in `prod.impuestos` with `codigo='IVA'`,
`nombre='IVA'`, `porcentaje=0.19`, `vigente_desde=NOW() AT TIME ZONE
'UTC'`, `vigente_hasta=NULL`, `estado='activo'`, `created_at=NOW()`
**And** Op 3 MUST insert two rows in `prod.alert_types`
(`subscripcion_vencida_forzado`, `tarifa_vigente_forzado`) — see REQ-OPS-050
for the alerta contract
**And** Op 4 MUST create the partial unique index `one_exit_per_ingreso`
— see REQ-OPS-051.

#### Scenario: MIGRATION 0026 second apply is idempotent (no-op)

**Given** MIGRATION 0026 was applied successfully and is the current `head`
**When** `alembic upgrade head` runs again
**Then** Op 2 MUST be a no-op (`ON CONFLICT (codigo, vigente_desde) DO
NOTHING` matches the existing IVA row)
**And** Op 3 MUST be a no-op (`ON CONFLICT (tipo_alerta) DO NOTHING` for
both alert_types)
**And** Op 4 MUST be a no-op (`IF NOT EXISTS` on the partial unique
index)
**And** the migration MUST NOT produce duplicate rows.

#### Scenario: pre-flight aborts when `prod.impuestos` missing (regression test)

**Given** a test environment where `prod.impuestos` has been dropped (or
MIGRATION 0001-0025 have not run) — simulated in
`tests/integration/test_migration_0026_preflight.py`
**When** `alembic upgrade head` runs MIGRATION 0026
**Then** Op 1 (pre-flight `DO $$` block) MUST raise
`0026_preflight_abort: tabla prod.impuestos no existe. Aplique migrations
0001-0025 antes.`
**And** Op 2, Op 3, Op 4 MUST NOT execute.

#### Scenario: post-0026 deploy, F1.8 `iva_no_configurado` no longer occurs

**Given** MIGRATION 0026 has been applied and `prod.impuestos` has the
IVA row with `porcentaje=0.19`, `vigente_desde <= NOW()`, `vigente_hasta
IS NULL`, `estado='activo'`
**When** any valid `POST /operacion/salidas` reaches V5 (REQ-OPS-047) and
invokes `prod.calcular_cotizacion(:p)`
**Then** the F1.8 PL/pgSQL MUST find the IVA row, compute `iva = total *
0.19`, `subtotal = total - iva`, and return `{"cobrar":true,"subtotal":...,
"iva":...,"total":...}` (or `{"cobrar":false,...}` for mensualidad)
**And** MUST NOT return `{"error":"iva_no_configurado"}` — the KD-IVA
blocker is resolved (verified by F1.8 regression test
`pytest backend/tests/integration/test_cotizar_db.py`).

### REQ-OPS-053 — POST /api/v1/facturacion/factura contract: 12-step handler with KD-3 tenant scope, `Cache-Control: no-store`, Idempotency-Key header

**Given** the FastAPI router `api/v1/facturacion.py` is newly mounted via `r.include_router(facturacion.router)` in `api/v1/__init__.py`
**When** the handler `create_factura` is invoked with `payload: FacturaCreate`, `session: AsyncSession`, `ctx: TenantContext`, and `_claims: None = Depends(_facturacion_issuer_dep)` where `_facturacion_issuer_dep = requires_issuer("admin-", "cajero-")`
**Then** the handler MUST execute the strict 12-step order: (1) KD-3 issuer claims + `no_store_headers`; (2) V1 salida facturable SELECT; (3) tenant scope post-V1; (4) V2 cliente SELECT cuando `fe_con_datos=true`; (5) V3 IVA configurado; (6) V4 detalle items coherentes; (7) KD-FACT-02 `SELECT … FOR SHARE` per-row sobre `prod.tarifas_sucursal`; (8) V6 total recompute server-side (±0.01 COP); (9) INSERT `prod.facturas` [L-E]; (10) INSERT `prod.factura_detalle` (N rows) + `prod.factura_impuestos` (1 row) + `prod.factura_pagos` (1 row); (11) single `await session.commit()`; (12) response shape `FacturaRead`.
**And** the handler MUST respond `201 Created` with `FacturaRead` carrying `uuid`, `created_at`, `uuid_sucursal`, `uuid_ingreso`, `uuid_salida`, `subtotal`, `descuento`, `total`, `uuid_cliente` (server-derived, DEC-FACT-06), `items: list[FacturaItemRead]`, `estado: Literal["emitida","pagada","anulada"]` (derived from `V_FACTURA_ESTADO`).
**And** the handler MUST set the header `Cache-Control: no-store` on every 2xx, 4xx, and 5xx response.
**And** the handler MUST rely on the PR2 `Idempotency-Key` HTTP header for retry deduplication (DEC-IDEM-01 reuse from F1.6); the payload MUST NOT carry `correlacion_id` (rejected by `extra='forbid'`).
**RFC 2119**: MUST (12-step order, response shape, `Cache-Control: no-store`, issuer dep, Idempotency-Key delegation).

#### Scenario: T1 happy path ROTACION returns 201 with `estado="emitida"` and 4 tables populated atomically

**Given** an existing `prod.salidas` row with `uuid_salida=:p`, `uuid_ingreso=:i`, `uuid_sucursal=:s`, and no prior `prod.facturas` row referencing `:p`
**And** a vigente `prod.impuestos` row with `nombre='IVA'` and `porcentaje=0.19` (post-MIGRATION 0026 deploy)
**And** a `cajero-:s` JWT (or `admin-` with `:s` in `sucursales_permitidas`)
**When** the client sends `POST /api/v1/facturacion/factura` with `{"uuid_salida":":p","items":[{"tipo":"servicio","concepto":"parqueo","cantidad":1,"valor_unitario":5000}],"subtotal":5000,"total":5950,"medio_pago":"efectivo","fe_con_datos":false}`
**Then** the server MUST insert one row in `prod.facturas`, one row in `prod.factura_detalle`, one row in `prod.factura_impuestos` (IVA snapshot), one row in `prod.factura_pagos`, all in a single `await session.commit()`.
**And** MUST respond `201 Created` with `FacturaRead{estado:"emitida", uuid_cliente:null, ...}` and `Cache-Control: no-store`.

#### Scenario: T2 happy path CONSUMIDOR_FINAL with `fe_con_datos=false` returns 201 sin cliente

**Given** an existing `prod.salidas` row with `uuid_salida=:p`
**When** the client sends `POST /facturacion/factura` with `fe_con_datos=false` (no `fe_datos_cliente`)
**Then** the server MUST respond `201 Created` with `FacturaRead{uuid_cliente:null, ...}`
**And** MUST NOT insert any row in `prod.clientes`.

#### Scenario: T8 atomicidad — INSERT `factura_detalle` FK violation rolls back `facturas` row

**Given** an existing `prod.salidas` row with `uuid_salida=:p`
**And** the payload contains an item with `uuid_tarifa_sucursal=:fake` referencing a non-existent `prod.tarifas_sucursal` row
**When** the handler reaches Step 10 `crear_factura_detalle_bulk`
**Then** PostgreSQL MUST raise a FK constraint violation (pgcode `23503`)
**And** the handler MUST NOT call `await session.commit()` (single-commit invariant, KD-FACT-01)
**And** on exit, `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos` MUST have zero new rows for `:p` (single TX rollback, no orphans).

### REQ-OPS-054 — V1: salida existe y es facturable

**Given** `FacturaCreate.uuid_salida` referencing a non-existent salida OR an already-facturada salida (a row in `prod.facturas` exists with `uuid_salida=:p` and estado derivado in `{emitida, pagada}`)
**When** `POST /facturacion/factura` is called
**Then** the handler MUST raise `HTTPException(status_code=404, detail={"error":"salida_no_encontrada", "uuid_salida":str(payload.uuid_salida)}, headers={"Cache-Control":"no-store"})`.
**And** the response body MUST NOT leak PostgreSQL error codes (pgcode `23505`, `23503`, etc.) or internal error codes.
**And** the handler MUST exit before Step 9; NO row MUST be inserted in any of the 4 tables.
**RFC 2119**: MUST (single 404 discriminator for "not found" and "already facturada", no pgcode leak, no INSERT on failure).

#### Scenario: salida inexistente returns 404 sin pgcode leak

**Given** no row in `prod.salidas` with `uuid=:p`
**When** the client sends `POST /facturacion/factura` with `{"uuid_salida":":p",...}`
**Then** the response MUST be `404 Not Found` with body `{"error":"salida_no_encontrada","uuid_salida":":p"}` and `Cache-Control: no-store`.
**And** the response body MUST NOT contain `"23503"`, `"23505"`, `"FOREIGN KEY"`, or any pgcode string.
**And** `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos` MUST have zero new rows.

#### Scenario: salida ya facturada returns 404 (DEC-FACT-01 unified discriminator)

**Given** `prod.salidas` with `uuid=:p` exists
**And** `prod.facturas` contains a row with `uuid_salida=:p` and `estado` derivado in `{emitida, pagada}`
**When** the client sends `POST /facturacion/factura` with `{"uuid_salida":":p",...}`
**Then** the response MUST be `404 Not Found` with body `{"error":"salida_no_encontrada","uuid_salida":":p"}` (operationally equivalent to "no existe").

### REQ-OPS-055 — V2: cliente existe cuando `fe_con_datos=true`

**Given** `FacturaCreate.fe_con_datos=true` AND `FacturaItemConDatosPropios.numero_identificacion` does not match any active row in `prod.clientes` (`estado='activo'` AND `vigente_hasta IS NULL`)
**When** `POST /facturacion/factura` is called
**Then** the handler MUST raise `HTTPException(status_code=404, detail={"error":"cliente_no_encontrado", "numero_identificacion":"..."}, headers={"Cache-Control":"no-store"})`.
**And** the handler MUST exit before Step 9; NO row MUST be inserted in any of the 4 tables.
**And** the handler MUST NOT auto-create the cliente — V2 returns 404 to caller; caller decides whether to POST `/clientes` first.
**RFC 2119**: MUST (V2 lookup miss → 404, no auto-create, no INSERT on failure).

#### Scenario: cliente no existe con `fe_con_datos=true` returns 404

**Given** no active row in `prod.clientes` with `numero_identificacion=:n` (any `tipo_identificador`)
**When** the client sends `POST /facturacion/factura` with `fe_con_datos=true` and `fe_datos_cliente.numero_identificacion=":n"`
**Then** the response MUST be `404 Not Found` with body `{"error":"cliente_no_encontrado","numero_identificacion":":n"}` and `Cache-Control: no-store`.
**And** `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos`, `prod.clientes` MUST have zero new rows.

#### Scenario: V2 SKIPPED cuando `fe_con_datos=false` (consumidor final)

**Given** `payload.fe_con_datos=false` (no `fe_datos_cliente`)
**When** the client sends `POST /facturacion/factura`
**Then** the handler MUST skip V2 entirely; MUST NOT query `prod.clientes`.
**And** MUST respond `201 Created` with `FacturaRead{uuid_cliente:null, ...}` (DEC-FACT-08 consumidor final).

### REQ-OPS-056 — V3: IVA configurado (defense-in-depth guard)

**Given** `prod.impuestos` does NOT contain a row with `nombre='IVA'` AND `estado='activo'` AND `porcentaje > 0` (KD-IVA blocker pre-MIGRATION 0026)
**When** `POST /facturacion/factura` is called
**Then** the handler MUST raise `HTTPException(status_code=500, detail={"error":"iva_no_configurado"}, headers={"Cache-Control":"no-store"})`.
**And** the handler MUST exit before Step 9; NO row MUST be inserted in any of the 4 tables.
**RFC 2119**: After MIGRATION 0026 (F1.7) is deployed, this 500 path **MUST NEVER** fire. This REQ serves as a defense-in-depth guard; the post-0026 runtime contract is `validar_iva_configurado() -> True` always.

#### Scenario: iva_no_configurado pre-MIGRATION 0026 deploy returns 500 (defense only)

**Given** `prod.impuestos` has NO row with `nombre='IVA'`
**When** the client sends `POST /facturacion/factura`
**Then** the response MUST be `500 Internal Server Error` with body `{"error":"iva_no_configurado"}` and `Cache-Control: no-store`.

#### Scenario: IVA configurado post-MIGRATION 0026 returns 201 (happy path proceeds)

**Given** `prod.impuestos` has a row with `nombre='IVA'`, `porcentaje=0.19`, `estado='activo'`, `vigente_desde <= NOW() < vigente_hasta` (post-MIGRATION 0026 deploy)
**When** the client sends `POST /facturacion/factura` (happy path)
**Then** V3 MUST return `True`; the handler MUST proceed to V4 and beyond.
**And** MUST respond `201 Created` (assuming all other validations pass).

### REQ-OPS-057 — V4: detalle items coherentes

**Given** `FacturaCreate.items=[]` OR any item with `cantidad <= 0` OR `valor_unitario < 0` OR `tipo not in {"servicio", "producto"}` OR `concepto` is empty
**When** `POST /facturacion/factura` is called
**Then** the handler MUST raise `HTTPException(status_code=422, detail={"error":"detalle_invalido", "min_items":1}, headers={"Cache-Control":"no-store"})` for the empty-items case, OR a per-item index error for granular cases.
**And** the handler MUST exit before Step 7 (no lock acquired); NO row MUST be inserted in any of the 4 tables.
**RFC 2119**: MUST (`items` MUST have `min_length=1` enforced at Pydantic schema level; `cantidad` MUST be `> 0`; `valor_unitario` MUST be `>= 0`; `tipo` MUST be one of `{servicio, producto}`).

#### Scenario: T5 items vacío returns 422 detalle_invalido

**Given** a valid `FacturaCreate` payload with `items=[]`
**When** the client sends `POST /facturacion/factura`
**Then** Pydantic MUST reject with `422 Unprocessable Entity` and body `{"error":"detalle_invalido","min_items":1}`.
**And** NO INSERT in any of the 4 tables.

#### Scenario: item con cantidad negativa returns 422 con item index

**Given** a valid payload where `items[0].cantidad=-1`
**When** the client sends `POST /facturacion/factura`
**Then** the response MUST be `422 Unprocessable Entity` with body referencing `items[0].cantidad`.

### REQ-OPS-058 — V5: NIT módulo 11 DIAN Resolución 000175 de 2021

**Given** `FacturaItemConDatosPropios.tipo_identificador="NIT"` AND `dv` mismatches the algorithm-computed DV per DIAN spec
**When** the Pydantic v2 `@field_validator("numero_identificacion")` runs (either via `FacturaItemConDatosPropios` in `/facturacion/factura` payload OR via `ClientesCreate` in any `/clientes` POST payload)
**Then** validation MUST raise a Pydantic validation error mapped to `HTTPException(status_code=422, detail={"error":"nit_invalido", "dv_esperado":<int>, "dv_recibido":"<string>"}, headers={"Cache-Control":"no-store"})`.
**And** the validator MUST NOT proceed to insert any row in `prod.clientes` or `prod.facturas`.
**RFC 2119**: MUST (Variant A canónica per DIAN Resolución 000175 de 2021; `dv_calculado = sum_ponderada % 11`; NO alternative algorithms; weights `[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]` applied **right-to-left** over NIT digits without DV; NIT normalized: strip non-digits, strip leading zeros, minimum 5 digits).

**Algorithm** (canonical reference for `repo/nit_modulo11.py::validar_nit_modulo11`):

1. Strip non-digits from NIT (`"800.123.456-7"` → `"800123456"`).
2. Strip leading zeros (`"000123"` → `"123"`).
3. Compute weighted sum: `sum = Σ(d_i × w_i)` for `i=0..len-1`, where `d_i` is the i-th digit from RIGHT to LEFT, and `w_i` cycles through `[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]`.
4. Compute `mod = sum % 11`.
5. `dv_calculado = mod` (Variant A canónica per DIAN, NOT `11 - mod` Variant B).
6. If `dv_calculado != int(dv_input)` → reject with `dv_esperado=dv_calculado`, `dv_recibido=dv_input`.

#### Scenario: T3 NIT válido `800.123.456-7` (DV=7) MUST pass

**Given** a `FacturaItemConDatosPropios` block with `tipo_identificador="NIT"`, `numero_identificacion="800.123.456-7"`, `dv="7"`
**When** Pydantic v2 validation runs
**Then** `validar_nit_modulo11("800.123.456-7", "7")` MUST return `True` (Variant A canónica).
**And** the request MUST proceed (assuming other validations pass).

#### Scenario: T4 NIT inválido `800.123.456-5` (DV=5) MUST fail con dv_esperado=7

**Given** a `FacturaItemConDatosPropios` block with `tipo_identificador="NIT"`, `numero_identificacion="800.123.456-5"`, `dv="5"`
**When** Pydantic v2 validation runs
**Then** validation MUST fail with body `{"error":"nit_invalido","dv_esperado":7,"dv_recibido":"5"}` and HTTP `422 Unprocessable Entity`.
**And** NO INSERT en `prod.clientes` o `prod.facturas`.

#### Scenario: edge — NIT con ceros a la izquierda normaliza

**Given** `numero_identificacion="000123-1"` (`tipo_identificador="NIT"`)
**When** validation runs
**Then** the helper MUST normalize to `"123"`, compute `dv_esperado("123")=1`, and `dv="1"` MUST pass.

#### Scenario: edge — NIT con guión y puntos normaliza

**Given** `numero_identificacion="800.123.456-7"`, `dv="7"`
**When** validation runs
**Then** the helper MUST strip non-digits to `"800123456"`, compute `dv_esperado("800123456")=7`, and `dv="7"` MUST pass.

#### Scenario: edge — DV no-dígito MUST reject

**Given** `numero_identificacion="800.123.456"`, `dv="X"` (non-digit)
**When** validation runs
**Then** validation MUST fail with `dv_recibido="X"` and HTTP `422`.

#### Scenario: V5 SKIPPED cuando `tipo_identificador="CC"` (no NIT)

**Given** a `FacturaItemConDatosPropios` block with `tipo_identificador="CC"` (no NIT)
**When** Pydantic v2 validation runs
**Then** the módulo 11 validator MUST NOT run; `dv` is optional for `CC`.
**And** the request MUST proceed (assuming other validations pass).

### REQ-OPS-059 — V6: total coherente ±0.01 COP

**Given** `FacturaCreate.total` differs from server-computed `total_server = subtotal_items + iva - retencion` by more than `Decimal("0.01")` COP
**When** `POST /facturacion/factura` is called (after V4 items validated, before Step 9 INSERT)
**Then** the handler MUST raise `HTTPException(status_code=422, detail={"error":"total_no_coherente", "total_recibido":"<decimal>", "total_calculado":"<decimal>", "diferencia":"<decimal>"}, headers={"Cache-Control":"no-store"})`.
**And** the handler MUST exit before Step 9; NO row MUST be inserted in any of the 4 tables.
**RFC 2119**: MUST (tolerance ±0.01 COP, i.e. 1 centavo colombiano; `iva = subtotal * porcentaje_iva` where `porcentaje_iva` comes from `prod.impuestos.IVA.porcentaje`; `retencion = Decimal("0")` per DEC-FACT-04 MVP).

#### Scenario: T6 total differs by >0.01 COP returns 422 total_no_coherente

**Given** items totaling `subtotal=5000`, IVA `= 950` (5000 × 0.19), so `total_server=5950`
**And** payload `total=6000` (differs by `Decimal("50")` from server-computed `5950`)
**When** the client sends `POST /facturacion/factura`
**Then** the response MUST be `422 Unprocessable Entity` with body `{"error":"total_no_coherente","total_recibido":"6000","total_calculado":"5950","diferencia":"50"}`.
**And** NO INSERT en cualquier de las 4 tablas.

#### Scenario: total exacto (diff=0) MUST pass V6

**Given** items totaling `subtotal=5000`, `total_server=5950`
**And** payload `total=5950` (differs by `Decimal("0")` from server-computed)
**When** the client sends `POST /facturacion/factura`
**Then** V6 MUST return `True`; handler proceeds to Step 9 (assuming all other validations pass).

#### Scenario: total differs by exactly 0.01 COP MUST pass V6 (tolerance boundary)

**Given** `total_server=5950`, payload `total=5950.01` (differs by `Decimal("0.01")`)
**When** the client sends `POST /facturacion/factura`
**Then** V6 MUST return `True` (boundary inclusive).

### REQ-OPS-060 — KD-FACT-01: single `await session.commit()` invariant

**RFC 2119**: The `create_factura` handler body in `api/v1/facturacion.py` MUST contain **EXACTLY ONE** `await session.commit()` call. Multiple `commit()` calls, `session.begin_nested()`, or `SAVEPOINT` statements **MUST NOT** appear anywhere in the handler body or its callees (KD-FACT-01 + DEC-FACT-01).

**Defense**: AST walk `tests/static/test_factura_handler_single_commit.py` parses the `create_factura` function body using `ast.walk` BFS via `iter_child_nodes` recursion (per F1.7 pattern) and asserts:

- `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and getattr(n.value.func, "attr", "") == "commit"]) == 1`.
- `len([n for n in ast.walk(body) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "begin_nested"]) == 0`.
- No `SAVEPOINT` or `RELEASE SAVEPOINT` string literals in the body.

#### Scenario: T10 AST walk enforces exactly 1 commit call

**Given** the source file `api/v1/facturacion.py` containing `create_factura`
**When** `tests/static/test_factura_handler_single_commit.py` runs
**Then** the AST walk MUST assert `commit_count == 1`; if multiple commits OR any `begin_nested` OR any `SAVEPOINT` is detected, the test MUST fail with a typed error referencing the offending AST node line number.

#### Scenario: handler with two `commit()` calls MUST fail AST walk

**Given** a hypothetical handler with `await session.commit()` at line 50 and `await session.commit()` at line 80
**When** the AST walk runs
**Then** `commit_count == 2` MUST trigger test failure with message `"KD-FACT-01 violation: expected 1 commit, found 2 at lines [50, 80]"`.

### REQ-OPS-061 — KD-FACT-02: `SELECT … FOR SHARE` per-row sobre `prod.tarifas_sucursal`

**Given** any `FacturaItemCreate.uuid_tarifa_sucursal IS NOT NULL` in `payload.items`
**When** `POST /facturacion/factura` is called (after V4 items validated, before Step 9 INSERT)
**Then** the handler MUST execute `SELECT … FOR SHARE` per-row on `prod.tarifas_sucursal` for each unique `uuid_tarifa_sucursal` referenced.
**And** the lock MUST be held until the single `await session.commit()` (KD-FACT-01) at Step 11.
**And** the lock MUST be per-row (NOT per-table) — only the referenced rows are locked, not all `tarifas_sucursal` rows.
**And** the handler MUST NOT acquire locks on `prod.salidas` (V1 read by PK) or `prod.clientes` (V2 read by UK).
**RFC 2119**: MUST (per-row `FOR SHARE` on every `uuid_tarifa_sucursal` referenced; lock held until `session.commit()`; per-row scope prevents global serialization).

#### Scenario: T9 concurrent TX cannot UPDATE locked `tarifas_sucursal` row

**Given** a `create_factura` handler holding `FOR SHARE` on `prod.tarifas_sucursal.uuid=:t` (locked by TX 1)
**When** a concurrent TX 2 attempts `UPDATE prod.tarifas_sucursal SET valor=999 WHERE uuid=:t`
**Then** TX 2 MUST block (FOR SHARE conflicts with FOR UPDATE / UPDATE).
**And** TX 2 MUST unblock only after TX 1 commits or rolls back.

#### Scenario: items sin `uuid_tarifa_sucursal` MUST skip lock acquisition

**Given** `payload.items=[]` is rejected by V4 (so this scenario starts post-V4 with valid items)
**And** items have `uuid_tarifa_sucursal=null` (no tarifa referenced)
**When** Step 7 executes
**Then** the handler MUST NOT execute any `SELECT … FOR SHARE` (no lock to acquire).
**And** MUST proceed to Step 8 (V6 recompute).

### REQ-OPS-062 — POST /api/v1/facturacion/factura-pagos: voucher_requerido

**Given** `FacturaPagoAdicionalCreate.medio_pago="datafono"` AND `referencia` is empty (length 0) OR missing (`None`)
**When** `POST /api/v1/facturacion/factura-pagos` is called
**Then** the handler MUST raise `HTTPException(status_code=400, detail={"error":"voucher_requerido"}, headers={"Cache-Control":"no-store"})`.
**And** the handler MUST NOT insert any row in `prod.factura_pagos`.
**RFC 2119**: MUST (`medio_pago="datafono"` REQUIRES non-empty `referencia`; `medio_pago in {"efectivo","tarjeta","transferencia","mixto"}` accepts `referencia=null`).

#### Scenario: T7 `medio_pago="datafono"` sin `referencia` returns 400 voucher_requerido

**Given** `FacturaPagoAdicionalCreate{medio_pago:"datafono", referencia:null, valor:5000, uuid_factura:":f"}`
**When** the client sends `POST /facturacion/factura-pagos`
**Then** the response MUST be `400 Bad Request` with body `{"error":"voucher_requerido"}` and `Cache-Control: no-store`.
**And** `prod.factura_pagos` MUST have zero new rows for `:f`.

#### Scenario: T7b `medio_pago="datafono"` con `referencia` returns 201

**Given** `FacturaPagoAdicionalCreate{medio_pago:"datafono", referencia:"VCHR-12345", valor:5000, uuid_factura:":f"}` and `prod.facturas` row `:f` exists with `estado="emitida"`
**When** the client sends `POST /facturacion/factura-pagos`
**Then** the response MUST be `201 Created` with `FacturaPagoRead`.

#### Scenario: T7c `medio_pago="efectivo"` sin `referencia` returns 201 (no voucher required)

**Given** `FacturaPagoAdicionalCreate{medio_pago:"efectivo", referencia:null, valor:5000, uuid_factura:":f"}`
**When** the client sends `POST /facturacion/factura-pagos`
**Then** the response MUST be `201 Created` (no voucher required for cash).

#### Scenario: T7d `medio_pago="datafono"` con `referencia=""` (empty string) returns 400

**Given** `FacturaPagoAdicionalCreate{medio_pago:"datafono", referencia:"", valor:5000, uuid_factura:":f"}`
**When** the client sends `POST /facturacion/factura-pagos`
**Then** the response MUST be `400 Bad Request` with body `{"error":"voucher_requerido"}` (empty string treated as missing).

### REQ-OPS-063 — DEC-FACT-06: `uuid_cliente` derivado server-side

**RFC 2119**: The `FacturaRead.uuid_cliente` field MUST be server-derived via lookup against `prod.clientes` by `numero_identificacion` provided in `fe_datos_cliente` when `fe_con_datos=true`. It MUST NOT be persisted as a column in `prod.facturas` (the table column does not exist in migration 0001 lines 607-654; 4FN design).

**Behavior**:

- When `fe_con_datos=true`: server resolves `cliente_uuid` via V2 lookup; `FacturaRead.uuid_cliente` MUST equal the resolved `cliente.uuid`.
- When `fe_con_datos=false`: `FacturaRead.uuid_cliente` MUST be `null`; the response MUST NOT include cliente data.
- The response MUST NEVER echo a client-supplied `uuid_cliente` field (rejected by `extra='forbid'`).
- Future HUs MAY add `prod.facturas.uuid_cliente` FK column and backfill; F1.9 does NOT create the FK.

#### Scenario: T1 cliente derivado server-side cuando `fe_con_datos=true`

**Given** `payload.fe_con_datos=true` AND `prod.clientes` has an active row with `numero_identificacion=":n"` and `uuid=:c`
**When** the client sends `POST /facturacion/factura` and V2 resolves `cliente_uuid=:c`
**Then** the response MUST be `201 Created` with `FacturaRead{uuid_cliente=":c", ...}`.

#### Scenario: T2 `uuid_cliente=null` cuando `fe_con_datos=false` (consumidor final)

**Given** `payload.fe_con_datos=false`
**When** the client sends `POST /facturacion/factura`
**Then** the response MUST be `201 Created` with `FacturaRead{uuid_cliente:null, ...}`.
**And** the response body MUST NOT include any `cliente` object.

#### Scenario: payload con `uuid_cliente` client-supplied MUST be rejected by `extra='forbid'`

**Given** a payload that includes `"uuid_cliente":":c"` (client attempts to inject)
**When** Pydantic v2 validation runs
**Then** validation MUST fail with HTTP `422 Unprocessable Entity` and message referencing `extra_forbidden`.

### REQ-OPS-064 — Server-assigns `prefijo`+`consecutivo` via `assign_consecutivo` (SELECT FOR UPDATE on `prod.resolucion_facturacion`)

**Level**: SHALL. **Statement**: The branch MUST assign `prefijo`+`consecutivo` to a new `prod.factura_electronica` row by calling `repo/resolucion_facturacion.py::assign_consecutivo(session, *, resolucion_uuid, source_event_uuid) -> int` (verified signature, lines 97-149) with the vigente `prod.resolucion_facturacion` row's `uuid` for the factura's sucursal. The helper MUST take `SELECT ... FOR UPDATE` on the resolution row (lines 114-120) and increment the next consecutive value atomically within the request's TX. The prefijo is snapshotted separately from the vigente resolution row at INSERT time (REQ-OPS-074).

**Rationale**: plan.md línea 953 mandates `assign_consecutivo` (real numeración, NOT fallback `SIM-YYYY-MM-DD-NNNNNN` per línea 951). DIAN Resolución 000175 de 2021 + Decreto 2242 de 2015 require contiguous numbering inside the authorized `rango_desde`..`rango_hasta` range. The SELECT FOR UPDATE closes the concurrent assignment race at the row level.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py` lines 97-149 (helper verified 2026-09-14); `plan.md` línea 953.

#### Scenario 1: Happy path — `assign_consecutivo` returns next consecutivo and INSERT proceeds

**Given** a paid `prod.facturas.uuid=:f` with `uuid_sucursal=:s` and `estado` derivado `in {emitida, pagada}`
**And** a vigente `prod.resolucion_facturacion` row with `uuid=:r`, `prefijo='FE'`, `rango_desde=1`, `rango_hasta=5000`, `vigente_hasta IS NULL`, `estado='activo'`
**And** `COALESCE(MAX(consecutivo), 0)` over `prod.factura_electronica` WHERE `uuid_resolucion_facturacion=:r` returns `41`
**When** the handler reaches Step 6 of `create_factura_electronica` and invokes `await assign_consecutivo(session, resolucion_uuid=:r, source_event_uuid=:f)`
**Then** the helper MUST take `SELECT ... FOR UPDATE` on `prod.resolucion_facturacion WHERE uuid=:r` (lock held until `await session.commit()` at Step 11)
**And** MUST return `int(41 + 1) = 42` (`next_value=42`).
**And** MUST NOT raise `ConsecutivoRangeExhaustedError` (since `42 <= rango_hasta=5000`).
**And** Step 7 of the handler MUST INSERT a `prod.factura_electronica` row with `prefijo='FE'` (from `:r`) and `consecutivo=42`.
**And** the handler MUST respond `201 Created` with `FacturaElectronicaRead{prefijo:'FE', consecutivo:42, ...}` and `Cache-Control: no-store`.

#### Scenario 2: Idempotency on retry of same `(resolucion_uuid, source_event_uuid)`

**Given** a prior successful POST that INSERTed `prod.factura_electronica(consecutivo=42)` for `(resolucion_uuid=:r, uuid_factura=:f)`
**When** the same client POSTs `/api/v1/facturacion/factura-electronica` with `{"uuid_factura":":f"}` again (same `Idempotency-Key` or natural retry)
**Then** `assign_consecutivo` MUST execute the idempotency check at lines 99-108 FIRST and MUST return `int(42)` directly without taking any lock or running `MAX(consecutivo)+1`.
**And** the handler MUST NOT INSERT a NEW `prod.factura_electronica` row (the SELECT-by-`uuid_factura` in V2 catches it before INSERT and returns 409 `factura_electronica_ya_existe`).
**And** no NEW `prod.resolucion_facturacion` consecutivo MUST be consumed (idempotency invariant).

#### Scenario 3: Concurrent POSTs on the same resolution serialize cleanly

**Given** two concurrent TXs both POSTing `/api/v1/facturacion/factura-electronica` for the same `:f` with the same resolution `:r`
**When** both TXs invoke `assign_consecutivo(session, resolucion_uuid=:r, source_event_uuid=:f)` simultaneously
**Then** the FIRST TX MUST acquire `SELECT ... FOR UPDATE` on `:r` and proceed to compute `consecutivo=42`.
**And** the SECOND TX MUST block at the SELECT FOR UPDATE until the FIRST TX commits.
**And** after the FIRST TX commits, the SECOND TX MUST acquire the lock and proceed to compute `consecutivo=43` (atomic MAX()+1 over the now-committed state).
**And** NO gap in the consecutivo sequence MUST be introduced (DIAN numbering contiguity invariant).

#### Scenario 4: 4NF snapshot pattern — `prefijo` snapshot is independent of later resolution changes

**Given** a vigente resolution `:r` with `prefijo='FE'` at INSERT time
**When** the FE row is INSERTed with `prefijo='FE'` and `consecutivo=42`
**Then** `prod.factura_electronica.prefijo='FE'` is a denormalized snapshot.
**And** a later `UPDATE prod.resolucion_facturacion SET prefijo='FX' WHERE uuid=:r` MUST NOT retroactively alter `prod.factura_electronica.prefijo` (4NF — the FE's prefijo is the historical truth at INSERT time).
**And** a later bi-temporal versioning of `:r` (close + new row with new `prefijo='FX'`) MUST also NOT alter `prod.factura_electronica.prefijo`.

#### Definition of Done for REQ-OPS-064

- MIGRATION 0028 (or earlier) does NOT modify `assign_consecutivo`; the helper is reused verbatim from F1.9 / T-PR9-002 / D1-rev.
- The handler Step 6 of `create_factura_electronica` calls `await assign_consecutivo(session, resolucion_uuid=:r, source_event_uuid=uuid_factura)` with the resuelción's `uuid` from V3 (REQ-OPS-073).
- Unit test `tests/unit/test_factura_electronica_repo.py::test_assign_consecutivo_for_fe_returns_next_value` PASSES (returns 42 for MAX=41, range=1..5000).
- Integration test `tests/integration/test_factura_electronica_atomicidad_db.py::test_concurrent_post_serializes_consecutivos` PASSES (two concurrent TXs commit with consecutivos 42 and 43, no gap).
- `Cache-Control: no-store` header verified on 201 / 409 / 500 responses (REQ-OPS-XR2 from F1.9).

### REQ-OPS-065 — Initial `prod.envio_dian` row with `estado='pendiente'` is INSERTed in the SAME `await session.commit()` as the `prod.factura_electronica` INSERT (KD-FE-01 single-commit)

**Level**: SHALL. **Statement**: The branch MUST INSERT a `prod.envio_dian` row with `estado='pendiente'`, `uuid_envio_padre=NULL`, `cufe=NULL`, `respuesta_proveedor=NULL`, `payload={prefijo, consecutivo, uuid_factura}` (JSONB snapshot) in the SAME `await session.commit()` as the `prod.factura_electronica` INSERT. KD-FE-01 single-commit invariant is the mirror of F1.9 KD-FACT-01.

**Rationale**: An `envio_dian` chain without its parent FE is an audit orphan; an FE without its initial envio is a fiscal breach (DIAN requires the submission trail to exist from the moment of numbering). Single-commit atomicity closes both risks.

**Source**: plan.md línea 953; F1.9 KD-FACT-01 (REQ-OPS-060).

#### Scenario 1: Atomic insert — both rows visible together to subsequent SELECTs

**Given** a paid `prod.facturas.uuid=:f` and a vigente resolution `:r` with `prefijo='FE'` and `rango_hasta=5000`
**When** the handler reaches Step 11 of `create_factura_electronica` and calls `await session.commit()` after Steps 7 (INSERT FE) and Step 10 (INSERT envio_dian)
**Then** exactly one `prod.factura_electronica` row MUST exist for `:f` (UK01 on `(uuid_resolucion_facturacion, consecutivo)` enforces uniqueness).
**And** exactly one `prod.envio_dian` row MUST exist with `uuid_factura_electronica = <fe.uuid>` AND `uuid_envio_padre IS NULL` AND `estado='pendiente'` AND `cufe IS NULL`.
**And** both rows MUST be visible to subsequent SELECTs in the same session (no isolation drift).

#### Scenario 2: Atomic rollback on FK violation — neither row persisted

**Given** the handler Step 7 (INSERT FE) succeeds but Step 10 (INSERT envio_dian) raises a FK violation (e.g. `uuid_resolucion_facturacion=:fake` not found)
**When** the request returns 5xx
**Then** `await session.commit()` MUST NOT be called (single-commit invariant, KD-FE-01).
**And** NEITHER the FE row NOR the envio_dian row MUST be persisted (single TX rollback).
**And** the partial unique index `one_fe_per_factura` MUST NOT have a pending entry (no half-applied state).

#### Scenario 3: Prefijo+consecutivo denormalized onto `envio_dian.payload`

**Given** `prod.factura_electronica` has `prefijo='FE'` and `consecutivo=42`
**When** the initial `prod.envio_dian` row is INSERTed
**Then** `envio_dian.payload` MUST include `prefijo='FE'` AND `consecutivo=42` AND `uuid_factura=:f` (JSONB denormalized snapshot for the cloud dispatcher to consume).
**And** the handler MUST NOT include any PII in `payload` (no `cliente.email`, no `cliente.telefono`, no `direccion`); the cloud dispatcher reconstructs the full payload from the sync replication.

#### Scenario 4: Initial row has `uuid_envio_padre IS NULL`

**Given** a fresh POST request (not a retry)
**When** the initial `prod.envio_dian` row is INSERTed
**Then** `envio_dian.uuid_envio_padre IS NULL` MUST hold (first row in the chain; the chain tip is the row itself).
**And** `envio_dian.uuid_factura_electronica = <fe.uuid>` MUST hold (NOT NULL FK).
**And** `envio_dian.estado='pendiente'` MUST hold (cloud dispatcher hasn't picked it up yet).

#### Definition of Done for REQ-OPS-065

- Handler Step 10 INSERTs the initial `envio_dian` row in the same `await session.commit()` as Step 7's FE INSERT (no intermediate commit).
- AST walk `tests/static/test_fe_handler_single_commit.py` PASSES (asserts `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(n.value.func, 'attr', '') == 'commit']) == 1`).
- Integration test `tests/integration/test_factura_electronica_atomicidad_db.py::test_rollback_no_orphan_fe_or_envio` PASSES.
- Unit test `tests/unit/test_factura_electronica_repo.py::test_crear_envio_dian_reintento_initial_no_padre` PASSES (initial row has `uuid_envio_padre IS NULL`).

### REQ-OPS-066 — Range exhaustion → HTTP 409 `numeracion_agotada` + alerta `fe_numbering_exhausted` fired in same TX (DEC-FE-03)

**Level**: MUST. **Statement**: When `assign_consecutivo` raises `ConsecutivoRangeExhaustedError` (verified, helper source lines 143-147 — `next_value > rango_hasta`), the handler MUST catch the typed exception, fire the already-seeded alerta `fe_numbering_exhausted` via `repo/alert_types.py::AlertaFactory(session, ctx).fire(...)` in the SAME TX, and return HTTP `409 Conflict` with body `{"error":"numeracion_agotada", "uuid_resolucion_facturacion":"<uuid>", "rango_hasta":<int>, "prefijo":"<str>"}`. The pgcode MUST NEVER appear in the response body, headers, or info+ logs.

**Rationale**: plan.md línea 949 mandates the alerta; línea 951 explicitly forbids the `SIM-YYYY-MM-DD-NNNNNN` fallback; the typed 409 body gives the operator enough context to request a new resolution from DIAN.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py` lines 143-147 (verified); `plan.md` líneas 949-951; `backend/packages/parkos_core/src/parkos_core/repo/alert_types.py::AlertaFactory` (F1.8 T-PR8-002).

#### Scenario 1: Range exhausted — handler catches, fires alerta, returns 409

**Given** a resolution `:r` with `prefijo='FE'`, `rango_desde=1`, `rango_hasta=5000`, vigente
**And** `COALESCE(MAX(consecutivo), 0)` over `prod.factura_electronica` for `:r` returns `5000` (range fully consumed)
**When** the handler invokes `await assign_consecutivo(session, resolucion_uuid=:r, source_event_uuid=:f)`
**Then** the helper MUST raise `ConsecutivoRangeExhaustedError("resolucion_facturacion :r range exhausted: next consecutivo 5001 exceeds rango_hasta=5000")`.
**And** the handler MUST catch the exception in Step 6 of `create_factura_electronica`, MUST fire `AlertaFactory(session, ctx).fire("fe_numbering_exhausted", motivo=str(exc))` BEFORE raising the HTTP 409.
**And** MUST return `409 Conflict` with body `{"error":"numeracion_agotada","uuid_resolucion_facturacion":":r","rango_hasta":5000,"prefijo":"FE"}` and `Cache-Control: no-store`.
**And** the response body MUST NOT contain `"22000"`, the literal text `"range exhausted"`, or any pgcode.

#### Scenario 2: No FE row, no envio_dian row on exhaustion

**Given** the range-exhausted state above
**When** POST `/api/v1/facturacion/factura-electronica` returns 409 `numeracion_agotada`
**Then** `prod.factura_electronica` MUST have zero new rows for `:f`.
**And** `prod.envio_dian` MUST have zero new rows for `:f` (Step 7 INSERT is gated by successful `assign_consecutivo`).
**And** `prod.alertas` MUST have exactly one NEW row with `tipo_alerta='fe_numbering_exhausted'`, `estado='abierta'`, and `datos_nuevos` carrying `{uuid_resolucion_facturacion, rango_hasta, prefijo, uuid_factura}` for operator diagnostics.

#### Scenario 3: Alerta payload includes range context for operator triage

**Given** the range-exhausted state and a successful alerta INSERT
**When** the operator queries `prod.alertas WHERE tipo_alerta='fe_numbering_exhausted' ORDER BY created_at DESC LIMIT 1`
**Then** the alerta row MUST include `datos_nuevos.uuid_resolucion_facturacion = :r` AND `datos_nuevos.rango_hasta = 5000` AND `datos_nuevos.prefijo = 'FE'` AND `datos_nuevos.uuid_factura = :f` (jsonb).
**And** the alerta MUST be fired with `actor_uuid = ctx.actor_uuid` and `uuid_sucursal = :s` (F1.8 `AlertaFactory` API).

#### Definition of Done for REQ-OPS-066

- MIGRATION 0028 does NOT add the alerta seed (already seeded in `0010_add_alert_types.py` per `plan.md` línea 949 + `repo/alert_types.py::AlertaFactory`).
- Handler Step 6 catch block fires `AlertaFactory(...).fire('fe_numbering_exhausted', motivo=str(exc))` and maps to `409 numeracion_agotada`.
- Unit test `tests/unit/test_factura_electronica_create_handler.py::test_create_fe_returns_409_numeracion_agotada_alerta_fired` PASSES (range=5000 with MAX=5000 → 409 + alerta row).
- Integration test verifies `prod.alertas` row created with the expected `tipo_alerta='fe_numbering_exhausted'` and JSONB payload.

### REQ-OPS-067 — At most one vigente `prod.factura_electronica` row per `prod.facturas.uuid` (V2 + DB partial UK `one_fe_per_factura`)

**Level**: MUST. **Statement**: The system MUST enforce at most one `prod.factura_electronica` row per `prod.facturas.uuid`. The application-layer V2 SELECT-before-INSERT (Step 4 of `create_factura_electronica`) is the primary guard; the DB-layer partial unique index `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_fe_per_factura ON prod.factura_electronica (uuid_factura) WHERE uuid_factura IS NOT NULL` (MIGRATION 0028 Op 2) is the defense-in-depth layer that closes the TOCTOU race between two concurrent POSTs that both pass V2. A `psycopg2.errors.UniqueViolation` (pgcode `23505`) MUST be caught by the handler and mapped to `409 Conflict` with body `{"error":"factura_electronica_ya_existe", "uuid_factura":"<uuid>"}`. The pgcode MUST NEVER appear in the response body, headers, or info+ logs.

**Rationale**: plan.md línea 953 mandates one FE per internal factura; the F1.9 `one_factura_per_salida` partial UK (migration 0027) transitively enforces this when `uuid_factura` is NOT NULL, but the partial UK on FE is the direct invariant. Defense in depth against concurrent cajeros or operator mis-clicks.

**Source**: `plan.md` línea 953; `backend/packages/parkos_core/migrations/versions/0027_*` precedent (`one_factura_per_salida`); F1.7 `one_exit_per_ingreso` precedent (migration 0026 Op 4).

#### Scenario 1: First POST creates the FE row

**Given** a paid `prod.facturas.uuid=:f` with no existing `prod.factura_electronica` row
**When** the client POSTs `/api/v1/facturacion/factura-electronica` with `{"uuid_factura":":f"}`
**Then** the V2 SELECT-by-`uuid_factura` MUST return `None`.
**And** the handler MUST proceed to Step 5 (V3 resuelve resolution) and Step 6 (`assign_consecutivo`).
**And** exactly one `prod.factura_electronica` row MUST exist for `uuid_factura=:f` after the successful commit.

#### Scenario 2: Second POST returns 409 `factura_electronica_ya_existe`

**Given** an existing `prod.factura_electronica` row with `uuid_factura=:f` (created by the first POST in Scenario 1)
**When** the client POSTs `/api/v1/facturacion/factura-electronica` with `{"uuid_factura":":f"}` again (different `Idempotency-Key` or natural retry)
**Then** V2 MUST return the existing FE row (non-None).
**And** the handler MUST return `409 Conflict` with body `{"error":"factura_electronica_ya_existe", "uuid_factura":":f"}` and `Cache-Control: no-store`.
**And** NO second `prod.factura_electronica` row MUST be INSERTed (Step 5 onward is unreachable on V2 hit).
**And** the original FE row MUST remain unchanged.

#### Scenario 3: TOCTOU race past V2 — partial UK forces UniqueViolation

**Given** two concurrent TXs both POSTing `/factura-electronica` with `{"uuid_factura":":f}` simultaneously
**And** both pass V2 SELECT (both see `None` for `:f`)
**When** both TXs reach Step 7 INSERT `prod.factura_electronica(uuid_factura=:f, ...)`
**Then** the partial UK `one_fe_per_factura ON prod.factura_electronica (uuid_factura) WHERE uuid_factura IS NOT NULL` MUST reject the second INSERT with `psycopg2.errors.UniqueViolation` (pgcode `23505`).
**And** the handler MUST catch the exception by pgcode (`pgcode == '23505'`), MUST NOT rely on Python `isinstance` alone.
**And** MUST translate to `HTTPException(status_code=409, detail={"error":"factura_electronica_ya_existe", "uuid_factura":":f"})`.
**And** the response body MUST NOT contain the substring `"23505"` or any pgcode reference.

#### Definition of Done for REQ-OPS-067

- MIGRATION 0028 Op 2 creates the partial UK `one_fe_per_factura` with `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`.
- Handler Step 4 performs the V2 SELECT-by-`uuid_factura` and returns 409 on hit.
- Handler catches `psycopg2.errors.UniqueViolation` (pgcode `23505`) on the INSERT path and maps to 409.
- Unit test `tests/unit/test_factura_electronica_create_handler.py::test_create_fe_returns_409_factura_electronica_ya_existe` PASSES.
- Integration test `tests/integration/test_factura_electronica_atomicidad_db.py::test_concurrent_post_uk_race` PASSES (two concurrent TXs → exactly one succeeds, the other returns 409).
- Downgrade of MIGRATION 0028 drops the partial UK.

### REQ-OPS-068 — GET endpoint JOINs `prod.v_factura_electronica_acuse` view (NEVER direct SELECT on `prod.envio_dian` for `envio_actual`)

**Level**: SHALL. **Statement**: The `GET /api/v1/facturacion/factura-electronica/{uuid}` endpoint MUST return a response shape `FacturaElectronicaRead` with `envio_actual: EnvioDianRead` whose `estado`, `cufe`, `timestamp_evento` are SERVER-DERIVED via JOIN against the existing `prod.v_factura_electronica_acuse` view (`backend/packages/parkos_core/migrations/versions/0009_add_derived_read_views.py` lines 96-109, `DISTINCT ON (uuid_factura_electronica) ORDER BY timestamp_evento DESC NULLS LAST, uuid DESC`). The handler MUST NEVER execute a direct SELECT against `prod.envio_dian` when computing `envio_actual` (the view is the single source of truth for the latest chain tip).

**Rationale**: The view already encodes the `DISTINCT ON … ORDER BY timestamp_evento DESC` semantic; querying `prod.envio_dian` directly would duplicate the logic and risk inconsistency between read paths. Centralizing on the view simplifies future ER changes (e.g. `envio_dian` partitioning) and enforces the "view is the canonical read path" convention (F1.7 + F1.9 precedent).

**Source**: `backend/packages/parkos_core/migrations/versions/0009_add_derived_read_views.py` lines 96-109 (verified).

#### Scenario 1: Happy path — view returns the latest envio row

**Given** a `prod.factura_electronica` row with `uuid=:fe_uuid` and `consecutivo=42`
**And** one `prod.envio_dian` row with `uuid_factura_electronica=:fe_uuid`, `estado='aceptado'`, `cufe='abc123'`, `timestamp_evento='2026-09-14T10:00:00Z'`
**When** the client GETs `/api/v1/facturacion/factura-electronica/:fe_uuid`
**Then** the handler MUST JOIN `prod.v_factura_electronica_acuse WHERE uuid_factura_electronica=:fe_uuid`.
**And** MUST return `200 OK` with `FacturaElectronicaRead{envio_actual: EnvioDianRead{estado:'aceptado', cufe:'abc123', timestamp_evento:'2026-09-14T10:00:00Z', ...}}` and `Cache-Control: no-store`.

#### Scenario 2: No envio rows (defensive null mapping)

**Given** an FE row with `uuid=:fe_uuid` and zero `prod.envio_dian` rows (shouldn't happen after REQ-OPS-065 atomic insert, but defensive)
**When** the client GETs `/api/v1/facturacion/factura-electronica/:fe_uuid`
**Then** the view JOIN returns no row.
**And** the handler MUST return `200 OK` with `FacturaElectronicaRead{envio_actual: null, ...}` (defensive null mapping; the FE exists but the chain is empty).
**And** MUST NOT raise 404 or 5xx (this is a defensive read for legacy data, not an error).

#### Scenario 3: Multiple envio rows — view picks the latest by `timestamp_evento DESC`

**Given** an FE with 3 `prod.envio_dian` rows: `e1` with `estado='rechazado'`, `timestamp_evento='2026-09-14T08:00:00Z'`; `e2` with `estado='pendiente'`, `timestamp_evento='2026-09-14T09:00:00Z'`; `e3` with `estado='aceptado'`, `cufe='abc123'`, `timestamp_evento='2026-09-14T10:00:00Z'`
**When** the client GETs `/api/v1/facturacion/factura-electronica/:fe_uuid`
**Then** the view MUST return the LATEST row by `timestamp_evento DESC NULLS LAST, uuid DESC` (per `DISTINCT ON`).
**And** `envio_actual.estado='aceptado'` AND `envio_actual.cufe='abc123'` MUST be returned.

#### Definition of Done for REQ-OPS-068

- Handler Step 3 of `get_factura_electronica` SELECTs from `prod.v_factura_electronica_acuse` via `session.execute(text("SELECT estado, cufe, timestamp_evento, uuid FROM prod.v_factura_electronica_acuse WHERE uuid_factura_electronica = :uuid"))`.
- Handler MUST NOT query `prod.envio_dian` directly for `envio_actual` (enforced by code review + handler 3-step chain).
- MIGRATION 0028 Op 3 adds covering index `idx_envio_dian_chain_tip (uuid_factura_electronica, timestamp_evento DESC)` for the JOIN performance.
- Unit test `tests/unit/test_factura_electronica_get_handler.py::test_get_fe_returns_estado_aceptado_with_cufe` PASSES.
- Unit test `tests/unit/test_factura_electronica_get_handler.py::test_get_fe_returns_latest_envio_via_view` PASSES (3-row chain → latest by timestamp_evento DESC).

### REQ-OPS-069 — GET response `envio_actual` exposes `estado` (Literal) + `cufe` (nullable) + `timestamp_evento`; server NEVER fabricates `reportado_dian` boolean

**Level**: SHALL. **Statement**: The GET response `envio_actual: EnvioDianRead` MUST carry `estado` as `Literal["pendiente", "enviado", "aceptado", "rechazado"]`, `cufe` as `Annotated[str, StringConstraints(min_length=1, max_length=255)] | None`, and `timestamp_evento` as ISO-8601 UTC datetime. The server MUST NEVER fabricate a `reportado_dian` boolean (plan.md línea 947 FORBIDDEN); state is derived purely from `envio_dian.estado` via the view. `motivo_rechazo` MUST be exposed when present on the latest envio.

**Rationale**: 4NF compliance — state lives on `envio_dian`, not duplicated on `factura_electronica`. A fabricated `reportado_dian` boolean would create a denormalization that drifts from the source of truth. The `Literal` type forces the client to handle all four states explicitly.

**Source**: plan.md línea 947 (forbidden `reportado_dian`); ER `modelo_datos_er.mmd` línea 700 (`cufe y reportado_dian eliminados (4FN)`); migration 0001 lines 976-993 (`envio_dian.estado` enum).

#### Scenario 1: Aceptado with CUFE — both fields populated

**Given** an envio with `estado='aceptado'`, `cufe='abc123'`, `timestamp_evento='2026-09-14T10:00:00Z'`
**When** the client GETs `/api/v1/facturacion/factura-electronica/:fe_uuid`
**Then** `envio_actual.estado='aceptado'` AND `envio_actual.cufe='abc123'` AND `envio_actual.timestamp_evento='2026-09-14T10:00:00Z'` MUST be returned.
**And** the response MUST NOT include any `reportado_dian` field (server never fabricates it).

#### Scenario 2: Pendiente without CUFE — null mapping

**Given** an envio with `estado='pendiente'`, `cufe=NULL`, `timestamp_evento='2026-09-14T10:00:00Z'` (initial envio, cloud dispatcher hasn't picked it up yet)
**When** the client GETs `/api/v1/facturacion/factura-electronica/:fe_uuid`
**Then** `envio_actual.estado='pendiente'` AND `envio_actual.cufe=null` AND `envio_actual.timestamp_evento='2026-09-14T10:00:00Z'` MUST be returned.

#### Scenario 3: Rechazado with motivo_rechazo — full context exposed

**Given** an envio with `estado='rechazado'`, `cufe=NULL`, `motivo_rechazo='Error X: CUFE signature mismatch'`, `timestamp_evento='2026-09-14T10:00:00Z'`
**When** the client GETs `/api/v1/facturacion/factura-electronica/:fe_uuid`
**Then** `envio_actual.estado='rechazado'` AND `envio_actual.motivo_rechazo='Error X: CUFE signature mismatch'` MUST be returned.
**And** the response MUST allow `motivo_rechazo` to be `null` when the field is absent (e.g. `aceptado` envios have no motivo_rechazo).

#### Definition of Done for REQ-OPS-069

- Pydantic v2 schema `EnvioDianRead` with `estado: Literal["pendiente", "enviado", "aceptado", "rechazado"]`, `cufe: str | None`, `timestamp_evento: datetime`, `motivo_rechazo: str | None = None` (no `reportado_dian` field).
- `ER modelo_datos_er.mmd` línea 700 comment (`cufe y reportado_dian eliminados (4FN)`) preserved as-is.
- Unit tests `test_get_aceptado_with_cufe` + `test_get_pendiente_without_cufe` + `test_get_rechazado_with_motivo` PASS.

### REQ-OPS-070 — Retry INSERTs NEW `prod.envio_dian` row with `uuid_envio_padre` pointing at previous chain tip (NEVER UPDATE — DEC-FE-02)

**Level**: SHALL. **Statement**: The `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar` endpoint MUST INSERT a NEW `prod.envio_dian` row with `uuid_envio_padre` pointing at the previous chain tip (the latest existing envio_dian row for the FE, identified via `repo/workflow.read_chain_tip` — F1.5 PR5-016). The endpoint MUST NEVER UPDATE existing envio rows (DEC-FE-02: the chain IS the audit trail). The `[L-W]` WorkflowBase MAY UPDATE `vigente_hasta` on the closed version for bi-temporal versioning, but user-meaningful fields (`estado`, `cufe`, `uuid_envio_padre`, `motivo_rechazo`) MUST be insert-only.

**Rationale**: 4NF compliance (state lives on `envio_dian.estado`, not duplicated on `factura_electronica`). Audit trail completeness (every transition is a row with `created_at`, `created_by`, `timestamp_evento`). Cloud-dispatcher-outage tolerance (the chain grows locally; cloud catches up via sync replication). DIAN audit requires immutable transitions per Resolución 000175 de 2021.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/workflow.py::read_chain_tip` (F1.5 PR5-016); `modelo_datos_er.mmd` lines 891-914; plan.md línea 953.

#### Scenario 1: First retry — chain grows by 1, original row unchanged

**Given** a `prod.factura_electronica` row `:fe` with one `prod.envio_dian` row `:e1` (the original, with `estado='rechazado'`, `uuid_envio_padre=NULL`)
**When** the client POSTs `/api/v1/facturacion/factura-electronica/:fe/reintentar`
**Then** `repo_factura_electronica.buscar_envio_dian_chain_tip(session, uuid_factura_electronica=:fe)` MUST return `:e1` (the latest by `timestamp_evento DESC`).
**And** the handler MUST INSERT a NEW `prod.envio_dian` row `:e2` with `uuid_factura_electronica=:fe`, `uuid_envio_padre=:e1`, `estado='pendiente'`, `cufe=NULL`, `payload=<snapshot>`.
**And** the original row `:e1` MUST remain unchanged (no UPDATE).
**And** the response MUST be `201 Created` with `EnvioDianRetryRead{uuid=:e2, uuid_factura_electronica=:fe, estado:'pendiente', uuid_envio_padre=:e1, timestamp_evento:<now>}`.

#### Scenario 2: Second retry — chain grows by 1, previous tip becomes non-tip

**Given** the state after Scenario 1 (`:fe` with `:e1` rechazo and `:e2` pendiente)
**And** `:e2` has `estado='rechazado'` (cloud dispatcher processed and rejected)
**When** the client POSTs `/api/v1/facturacion/factura-electronica/:fe/reintentar` again
**Then** `read_chain_tip` MUST return `:e2` (latest by timestamp_evento DESC).
**And** a NEW `:e3` MUST be INSERTed with `uuid_envio_padre=:e2` (chain tip moves to `:e3`).
**And** `:e1` and `:e2` MUST remain unchanged.

#### Scenario 3: Chain reconstruction via recursive SELECT on `uuid_envio_padre`

**Given** an FE `:fe` with 5 envio_dian rows `:e1`, `:e2`, `:e3`, `:e4`, `:e5` forming a chain (each row's `uuid_envio_padre` = previous row's `uuid`, except `:e1` which is `NULL`)
**When** a recursive WITH query `WITH RECURSIVE chain AS (SELECT * FROM prod.envio_dian WHERE uuid_factura_electronica=:fe AND uuid_envio_padre IS NULL UNION ALL SELECT e.* FROM prod.envio_dian e JOIN chain c ON e.uuid_envio_padre = c.uuid) SELECT uuid, uuid_envio_padre, estado, timestamp_evento FROM chain ORDER BY timestamp_evento ASC` executes
**Then** the chain MUST be reconstructed in order: `:e1` (root, `uuid_envio_padre=NULL`) → `:e2` → `:e3` → `:e4` → `:e5` (tip).
**And** each row's `estado` MUST be preserved (`:e1`='pendiente' initial, `:e2`='rechazado', `:e3`='pendiente' retry, `:e4`='aceptado', `:e5`='pendiente' retry).
**And** the chain integrity MUST be verifiable end-to-end (no orphans, no cycles, every row references the previous via `uuid_envio_padre`).

#### Scenario 4: AST walk — handler emits ONLY INSERT on `prod.envio_dian` for the chain (no UPDATE)

**Given** the source file `api/v1/facturacion.py` containing `retry_factura_electronica`
**When** `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` runs
**Then** the AST walk MUST assert that no `UPDATE prod.envio_dian ...` statement or `update(EnvioDian)` SQLAlchemy core call appears in the handler body.
**And** MUST assert that exactly one `INSERT INTO prod.envio_dian` (or equivalent `crear_envio_dian_reintento` helper call) appears.
**And** MUST assert `len(commits) == 1` (single-commit invariant).

#### Definition of Done for REQ-OPS-070

- Handler `/reintentar` Step 5 INSERTs a NEW `envio_dian` row via `repo_factura_electronica.crear_envio_dian_reintento(session, ..., uuid_envio_padre=tip_envio.uuid)`.
- Handler MUST NOT call any UPDATE on `prod.envio_dian` for user-meaningful fields.
- AST walk `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` PASSES (no UPDATE statements, exactly 1 INSERT, exactly 1 commit).
- Unit tests `test_first_retry` + `test_second_retry` + `test_chain_reconstruction` PASS.

### REQ-OPS-071 — Retry NOT allowed on chain tip `estado='aceptado'` (409 `reintento_no_permitido`); NOT allowed on `pendiente` (409 `envio_dian_already_pending`) (DEC-FE-04)

**Level**: MUST. **Statement**: When the latest `prod.envio_dian` chain tip's `estado='aceptado'`, the `/reintentar` endpoint MUST return HTTP `409 Conflict` with body `{"error":"reintento_no_permitido", "uuid_factura_electronica":"<uuid>", "estado_actual":"aceptado"}` (DEC-FE-04). Only `rechazado` (and `enviado` for completeness, though cloud dispatcher should normally advance it) chain tips may be retried. When the chain tip is `pendiente`, the endpoint MUST return `409 {"error":"envio_dian_already_pending", "uuid_factura_electronica":"<uuid>", "uuid_envio_pendiente":"<tip.uuid>"}` (rapid-retry guard).

**Rationale**: plan.md línea 969. `aceptado` is the terminal success state — retrying creates a phantom chain that misleads DIAN audits. `pendiente` means the cloud dispatcher is still working — the client just needs to wait. The 409 prevents accidental retry storms.

**Source**: plan.md línea 969; DEC-FE-04 in `HU-F1.10-proposal.md` §6.4.

#### Scenario 1: Retry blocked on `aceptado` chain tip

**Given** an FE `:fe` with the latest envio `:e_tip` having `estado='aceptado'`, `cufe='abc123'`
**When** the client POSTs `/api/v1/facturacion/factura-electronica/:fe/reintentar`
**Then** `read_chain_tip` MUST return `:e_tip` with `estado='aceptado'`.
**And** the handler MUST return `409 Conflict` with body `{"error":"reintento_no_permitido", "uuid_factura_electronica":":fe", "estado_actual":"aceptado"}` and `Cache-Control: no-store`.
**And** NO new `prod.envio_dian` row MUST be INSERTed.

#### Scenario 2: Retry allowed on `rechazado` chain tip

**Given** an FE `:fe` with the latest envio `:e_tip` having `estado='rechazado'`, `motivo_rechazo='...'`
**When** the client POSTs `/api/v1/facturacion/factura-electronica/:fe/reintentar`
**Then** `read_chain_tip` MUST return `:e_tip` with `estado='rechazado'`.
**And** the handler MUST INSERT a NEW envio row `:e_new` with `uuid_envio_padre=:e_tip`, `estado='pendiente'`.
**And** MUST return `201 Created` with `EnvioDianRetryRead{uuid=:e_new, ...}`.

#### Scenario 3: Retry blocked on `pendiente` chain tip (cloud dispatcher working)

**Given** an FE `:fe` with the latest envio `:e_tip` having `estado='pendiente'` (initial envio from REQ-OPS-065, cloud dispatcher hasn't picked it up yet)
**When** the client POSTs `/api/v1/facturacion/factura-electronica/:fe/reintentar`
**Then** `read_chain_tip` MUST return `:e_tip` with `estado='pendiente'`.
**And** the handler MUST return `409 Conflict` with body `{"error":"envio_dian_already_pending", "uuid_factura_electronica":":fe", "uuid_envio_pendiente":":e_tip"}` and `Cache-Control: no-store`.
**And** NO new `prod.envio_dian` row MUST be INSERTed (rapid-retry guard).

#### Scenario 4: Retry allowed on `enviado` chain tip (defensive)

**Given** an FE `:fe` with the latest envio `:e_tip` having `estado='enviado'` (cloud dispatcher has POSTed to DIAN but not received response yet)
**When** the client POSTs `/api/v1/facturacion/factura-electronica/:fe/reintentar`
**Then** the handler MAY return `409 envio_dian_already_pending` (defensive: cloud is still working; rapid-retry creates noise)
**Or** the handler MAY proceed to INSERT a new envio row (operator has explicit knowledge the cloud is stuck).
**And** whichever behavior is implemented MUST be consistent across the codebase and MUST be unit-tested.

#### Definition of Done for REQ-OPS-071

- Handler Step 4 of `retry_factura_electronica` calls `repo_factura_electronica.buscar_envio_dian_chain_tip(session, uuid_factura_electronica=:fe)` and inspects `tip.estado`.
- Handler returns `409 reintento_no_permitido` on `estado='aceptado'`, `409 envio_dian_already_pending` on `estado='pendiente'`, and proceeds to INSERT on `estado='rechazado'` (or `enviado`, per Scenario 4 decision).
- Unit tests `test_retry_blocked_on_aceptado` + `test_retry_allowed_on_rechazado` + `test_retry_blocked_on_pendiente` PASS.

### REQ-OPS-072 — `prod.envio_dian` writes are branch-initiated; sync catalog direction flipped to `branch_to_cloud` in MIGRATION 0028 Op 1 (DEC-FE-01)

**Level**: SHALL. **Statement**: `prod.envio_dian` INSERTs MUST be branch-initiated for the initial state and every retry transition. The sync catalog entry for `envio_dian` MUST be flipped from `direction='cloud_to_branch'` to `direction='branch_to_cloud'` in MIGRATION 0028 Op 1 (DEC-FE-01, plan.md línea 953 canonical). The cloud dispatcher consumes the chain via sync replication in `branch_to_cloud` direction for state-machine advancement (`pendiente → enviado → aceptado | rechazado`). The downgrade MUST reverse the flip.

**Rationale**: plan.md línea 953 is canonical (per user mandate "siempre remitete al plan.md"). The cloud-only assumption from PR2 (ER `modelo_datos_er.mmd` línea 892 "CLOUD-ONLY") is aspirational and incompatible with retry semantics (UUID v4 generation must be offline-safe; UPDATE would break the audit trail). The `[L-W]` WorkflowBase mandate of INSERT-only per transition is preserved. The ER diagram comment is updated post-archive from "CLOUD-ONLY" to "BRANCH-INITIATED, cloud consumer via sync" (separate PR for traceability).

**Source**: plan.md línea 953; `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 112-136; `modelo_datos_er.mmd` línea 892 (post-archive update).

#### Scenario 1: Sync catalog flip applied by MIGRATION 0028 Op 1

**Given** MIGRATION 0028 Op 1 SQL `UPDATE sync_catalog SET direction='branch_to_cloud' WHERE table_name='envio_dian' AND direction='cloud_to_branch';` is applied
**When** the operator queries `SELECT direction FROM sync_catalog WHERE table_name='envio_dian';`
**Then** the result MUST be `branch_to_cloud`.
**And** the migration MUST be idempotent: a second application MUST NOT change the direction (the WHERE clause filters on the old value).

#### Scenario 2: Branch INSERTs replicate to cloud via flipped direction

**Given** a branch TX INSERTs a NEW `prod.envio_dian` row via the `/reintentar` endpoint (REQ-OPS-070)
**When** the sync dispatcher runs (per F1.5 PR5-016 sync infrastructure, R-D8 stage-4 cutover)
**Then** the row MUST be replicated to the cloud (direction=`branch_to_cloud` per MIGRATION 0028 Op 1).
**And** the cloud dispatcher MUST consume the chain via the `branch_to_cloud` sync channel, POST to DIAN provider, and write transition rows (`enviado → aceptado | rechazado`) via the SAME sync channel (bidirectional sync on the same row, mediated by the version row).

#### Scenario 3: Downgrade reverses the flip

**Given** MIGRATION 0028 is downgraded
**When** the downgrade's `UPDATE sync_catalog SET direction='cloud_to_branch' WHERE table_name='envio_dian' AND direction='branch_to_cloud';` executes
**Then** the direction MUST revert to `cloud_to_branch` (pre-F1.10 state).
**And** the downgrade MUST execute AFTER the `DROP INDEX CONCURRENTLY` statements in the downgrade block (reverse order).

#### Definition of Done for REQ-OPS-072

- MIGRATION 0028 Op 1 SQL body `UPDATE sync_catalog SET direction='branch_to_cloud' WHERE table_name='envio_dian' AND direction='cloud_to_branch';` is present.
- MIGRATION 0028 downgrade reverses the flip in reverse order.
- Unit test `tests/integration/test_migration_0028_idempotent.py::test_sync_catalog_envio_dian_direction_flipped_to_branch_to_cloud` PASSES.
- Integration test `tests/integration/test_branch_insert_replicates_to_cloud.py::test_branch_envio_dian_replicates_to_cloud` PASSES (mock cloud dispatcher receives the row).
- ER `modelo_datos_er.mmd` línea 892 comment update is tracked as a separate post-archive PR (not in F1.10 archive).

### REQ-OPS-073 — Vigente resolution lookup at `NOW()` with defensive `ORDER BY vigente_desde DESC LIMIT 1` (V3)

**Level**: SHALL. **Statement**: The handler MUST look up the vigente `prod.resolucion_facturacion` row for the factura's sucursal using a new helper `repo/resolucion_facturacion.py::buscar_resolucion_vigente_por_sucursal(session, *, uuid_sucursal: UUID) -> ResolucionFacturacion | None` with the defensive query `SELECT * FROM prod.resolucion_facturacion WHERE uuid_sucursal = :uuid_sucursal AND vigente_hasta IS NULL AND estado = 'activo' ORDER BY vigente_desde DESC LIMIT 1`. A corrupt DB with multiple vigente rows MUST deterministically pick the most recent by `vigente_desde DESC`.

**Rationale**: The bi-temporal VersionedBase model (migration 0001 line 332) keeps all historical version rows; the vigente predicate (`vigente_hasta IS NULL`) is the natural filter, but a corrupt DB with multiple vigentes must still resolve deterministically. R2 MEDIUM mitigation per `HU-F1.10-proposal.md` §7.

**Source**: `backend/packages/parkos_core/src/parkos_core/models/V/resolucion_facturacion.py` (VersionedBase); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 332 (bi-temporal index).

#### Scenario 1: Single vigente — handler picks that row

**Given** `prod.resolucion_facturacion` has exactly one row for `uuid_sucursal=:s` with `vigente_hasta IS NULL`, `estado='activo'`, `prefijo='FE'`, `rango_hasta=5000`, `vigente_desde='2026-01-01'`
**When** `create_factura_electronica` Step 5 invokes `await buscar_resolucion_vigente_por_sucursal(session, uuid_sucursal=:s)`
**Then** the helper MUST return the single row.
**And** MUST NOT raise (V3 happy path).

#### Scenario 2: Multiple vigentes (corrupt DB) — handler picks latest by `vigente_desde DESC`

**Given** `prod.resolucion_facturacion` has two rows for `uuid_sucursal=:s` with `vigente_hasta IS NULL`, `estado='activo'` (a corrupt state that should never occur, but defensive):
- row `r1`: `vigente_desde='2026-01-01'`, `prefijo='FE'`, `rango_hasta=5000`
- row `r2`: `vigente_desde='2026-09-01'`, `prefijo='FX'`, `rango_hasta=9999`
**When** `create_factura_electronica` Step 5 invokes `buscar_resolucion_vigente_por_sucursal(session, uuid_sucursal=:s)`
**Then** the helper MUST return `r2` (latest by `vigente_desde DESC`).
**And** MUST NOT raise (defensive, NOT an error).

#### Scenario 3: No vigente — handler returns 409 `resolucion_no_vigente`

**Given** `prod.resolucion_facturacion` has zero rows for `uuid_sucursal=:s` with `vigente_hasta IS NULL`, `estado='activo'` (all resolutions are expired or inactivas)
**When** `create_factura_electronica` Step 5 invokes `buscar_resolucion_vigente_por_sucursal(session, uuid_sucursal=:s)`
**Then** the helper MUST return `None`.
**And** the handler MUST return `409 Conflict` with body `{"error":"resolucion_no_vigente", "uuid_sucursal":":s"}` and `Cache-Control: no-store`.
**And** NO `prod.factura_electronica` row MUST be INSERTed.

#### Definition of Done for REQ-OPS-073

- New helper `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::buscar_resolucion_vigente_por_sucursal` with signature `async def buscar_resolucion_vigente_por_sucursal(session, *, uuid_sucursal: UUID) -> ResolucionFacturacion | None`.
- Handler Step 5 calls the helper and maps `None` → 409 `resolucion_no_vigente`.
- Unit test `tests/unit/test_factura_electronica_repo.py::test_buscar_resolucion_vigente_por_sucursal_returns_latest` PASSES (single vigente + multi-vigente corrupt cases).
- Unit test `tests/unit/test_factura_electronica_create_handler.py::test_create_fe_returns_409_resolucion_no_vigente` PASSES.

### REQ-OPS-074 — Prefijo snapshot on `prod.factura_electronica.prefijo` at INSERT time (denormalized from vigente resolution; 4NF snapshot pattern)

**Level**: SHALL. **Statement**: The handler MUST denormalize the vigente `prod.resolucion_facturacion.prefijo` onto the new `prod.factura_electronica.prefijo` at INSERT time. The FE's `prefijo` is the historical truth — subsequent changes to the resolution's `prefijo` (e.g. a new resolution with `prefijo='FX'` supersedes the old `prefijo='FE'`) MUST NOT retroactively alter the FE's `prefijo` (4NF snapshot pattern per plan.md línea 697 and `modelo_datos_er.mmd` línea 700).

**Rationale**: 4NF — the FE's prefijo is the snapshot at the moment of numbering. DIAN audits require that historical documents reference the prefijo they were issued under, not the current prefijo of the resolution.

**Source**: plan.md línea 697; ER `modelo_datos_er.mmd` línea 700; `backend/packages/parkos_core/src/parkos_core/models/L_E/factura_electronica.py`.

#### Scenario 1: Prefijo snapshotted at INSERT, immutable thereafter

**Given** a vigente resolution `:r` with `prefijo='FE'`
**When** the FE row is INSERTed with `prefijo='FE'` and `consecutivo=42`
**Then** `prod.factura_electronica.prefijo='FE'` MUST be persisted.
**And** a later `UPDATE prod.resolucion_facturacion SET prefijo='FX' WHERE uuid=:r` MUST NOT change `prod.factura_electronica.prefijo` (still `'FE'`).
**And** a later bi-temporal versioning of `:r` (close + new row with `prefijo='FX'`) MUST also NOT change `prod.factura_electronica.prefijo` (still `'FE'`).

#### Scenario 2: Two FE rows from different resolution eras show independent prefijos

**Given** two FE rows:
- FE1: inserted under resolution A with `prefijo='FE'`, `consecutivo=42`
- FE2: inserted under resolution B with `prefijo='FX'`, `consecutivo=1`
**When** both rows are queried via `GET /api/v1/facturacion/factura-electronica/{uuid}` for FE1 and FE2
**Then** FE1's response MUST carry `prefijo='FE'` (snapshot from resolution A era).
**And** FE2's response MUST carry `prefijo='FX'` (snapshot from resolution B era).
**And** no cross-contamination MUST occur (FE2's `prefijo='FX'` MUST NOT bleed into FE1's response).

#### Definition of Done for REQ-OPS-074

- Handler Step 7 reads `resolucion.prefijo` from the vigente row returned by V3 and uses it as the `prefijo` argument to `crear_factura_electronica_inicial`.
- Unit test `tests/unit/test_factura_electronica_repo.py::test_prefijo_snapshot_independent_of_resolution_change` PASSES.
- Integration test `tests/integration/test_factura_electronica_atomicidad_db.py::test_two_fe_rows_different_prefijo_eras` PASSES.


### REQ-OPS-075 — POST endpoint INSERTs new `prod.reimpresion_ticket` row with `workflow_estado='autorizada'`

**Level**: SHALL. **Statement**: The branch MUST INSERT a new `prod.reimpresion_ticket` row with `workflow_estado='autorizada'`, `uuid_reimpresion_padre=NULL`, `uuid_ingreso=<ingreso.uuid>`, optional `uuid_factura`, `motivo` captured from request, `bi-temporal_estado='activo'`. The handler MUST resolve GAP-BE-04 by using permission name `reimprimir_ticket` (DEC-TKT-01), and MUST NOT use the typo'd `emitir_reimpresion` permission string.

**Rationale**: plan.md lines 989-991 mandate the create endpoint; the `reimprimir_ticket` permission is already seeded in `prod.permisos` (migration 0001 line 3292). GAP-BE-04 reconciliation (plan.md line 7342) is the precondition for the resource being reachable at all. The `[L-W]` WorkflowBase insert-only invariant keeps every create as a new chain root.

**Source**: `plan.md` lines 989-991 (acceptance criteria for crear); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 3292 (`reimprimir_ticket` permission seed); `backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py` line 74 (GAP-BE-04 site); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 66-72 (state machine); `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py` lines 50-132 (`ReimpresionTicketCreate` / `ReimpresionTicketRead`); `backend/packages/parkos_core/src/parkos_core/models/L_W/reimpresion_ticket.py` lines 29-90.

#### Scenario 1: Happy path with `uuid_ingreso` only — INSERT `workflow_estado='autorizada'`, no `uuid_factura`

**Given** an operador with role granted `reimprimir_ticket` permission (NOT `emitir_reimpresion` per GAP-BE-04)
**And** an existing `prod.ingreso.uuid=:i` with `uuid_sucursal=:s`
**And** no existing `prod.reimpresion_ticket` row for `uuid_ingreso=:i`
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket` with body `{"motivo":"Cliente solicita reimpresión por deterioro del original", "uuid_ingreso":":i", "uuid_factura":null}`
**Then** the handler MUST INSERT a new `prod.reimpresion_ticket` row with `workflow_estado='autorizada'`, `uuid_reimpresion_padre=NULL`, `uuid_ingreso=:i`, `uuid_factura=NULL`, `motivo=<payload.motivo>`, `bi-temporal_estado='activo'`, `timestamp_evento=NOW()`.
**And** MUST return `201 Created` with body `ReimpresionTicketRead{uuid:<new.uuid>, workflow_estado:'autorizada', uuid_reimpresion_padre:null, ...}` and `Cache-Control: no-store`.

#### Scenario 2: Happy path with `uuid_factura` populated — optional FK accepted

**Given** an operador with `reimprimir_ticket` permission
**And** an existing `prod.ingreso.uuid=:i` AND an existing `prod.facturas.uuid=:f`
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket` with body `{"motivo":"...", "uuid_ingreso":":i", "uuid_factura":":f"}`
**Then** the handler MUST validate `prod.facturas.uuid=:f` exists (V1 SELECT).
**And** MUST INSERT a new `prod.reimpresion_ticket` row with `uuid_factura=:f` populated (DEC-TKT-04 OPTIONAL).
**And** MUST return `201 Created` with `ReimpresionTicketRead{uuid_factura:":f", workflow_estado:'autorizada', ...}`.

#### Scenario 3: GAP-BE-04 fix verified — `reimprimir_ticket` permission accepted, `emitir_reimpresion` rejected

**Given** the handler dependency at `api/v1/workflows.py:74` was changed from `emitir_reimpresion` to `reimprimir_ticket` (DEC-TKT-01)
**When** an operador with role granted `reimprimir_ticket` POSTs to the endpoint
**Then** the request MUST succeed (201 Created) and the prior 403 caused by GAP-BE-04 MUST be gone.
**And** conversely, an operador with role granted ONLY the legacy `emitir_reimpresion` (no `reimprimir_ticket`) MUST receive `403` — proving the typo'd permission is no longer in the dependency check.

#### Scenario 4: `422` on missing `uuid_ingreso` (Pydantic validation rejects before DB hit)

**Given** a request body that omits the required `uuid_ingreso` field
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket` with `{"motivo":"...texto suficientemente largo...", "uuid_factura":null}`
**Then** Pydantic v2 schema validation MUST reject the request before any handler body code runs.
**And** MUST return `422 Unprocessable Entity` with body `{"error":"missing_field", "field":"uuid_ingreso"}` and `Cache-Control: no-store`.
**And** NO `prod.reimpresion_ticket` row MUST be INSERTed.

#### Definition of Done for REQ-OPS-075

- Handler `_create_reimpresion_ticket` wired in new module `api/v1/workflows_reimpresion.py` with `POST /api/v1/workflows/reimpresion-ticket`.
- KD-3 issuer chain `_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")` applied via FastAPI dependency.
- Handler calls `repo.workflow.append_transition(...)` with `parent_uuid=None, parent_fk_column="uuid_reimpresion_padre"`.
- GAP-BE-04 fix applied at `api/v1/workflows.py:74` (single-line; DEC-TKT-01).
- Unit tests `test_happy_path_uuid_ingreso_only` + `test_happy_path_uuid_factura_populated` + `test_gap_be_04_reimpresion_resource_unblocked` + `test_422_missing_uuid_ingreso` PASS.
- `Cache-Control: no-store` header verified on 201 / 422 / 500 responses.

---

### REQ-OPS-076 — GAP-BE-04 fix: permission name `emitir_reimpresion` → `reimprimir_ticket` (single-line)

**Level**: MUST. **Statement**: The handler dependency MUST use permission name `reimprimir_ticket` (NOT the typo `emitir_reimpresion` from GAP-BE-04). The fix is a single-line change at `api/v1/workflows.py:74`. This unblocks the entire `reimpresion-ticket` resource (currently returns 403 to all callers because no operador has the typo'd permission in `prod.permisos`).

**Rationale**: plan.md line 7342 mandates the reconciliation as GAP-BE-04 (highest blast radius — affects the entire `reimpresion-ticket` resource, not just the new POST endpoints). `reimprimir_ticket` is ALREADY seeded in `prod.permisos` (migration 0001 line 3292); no migration needed, no re-seed required. The existing `prod.permisos_usuario` grants already cover the canonical permission name.

**Source**: `plan.md` line 7342 (GAP-BE-04 reconciliation mandate); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 3292 (`reimprimir_ticket` permission seed); `backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py` line 74 (GAP-BE-04 site, current stale value `"emitir_reimpresion"`).

#### Scenario 1: Permission check uses correct name `reimprimir_ticket`

**Given** the handler dependency at `api/v1/workflows.py:74`
**When** the dependency module is loaded by the FastAPI router
**Then** the required permission string MUST equal `"reimprimir_ticket"` (NOT `"emitir_reimpresion"`).
**And** a code-level regression test MUST assert `permission_required == "reimprimir_ticket"`.

#### Scenario 2: Operator granted `reimprimir_ticket` succeeds

**Given** an operador role with the canonical permission `reimprimir_ticket` granted via `prod.permisos_usuario`
**When** the operador POSTs to `/api/v1/workflows/reimpresion-ticket`
**Then** the request MUST pass the dependency check and reach the handler body (201 Created on happy path).

#### Scenario 3: Operator granted only the typo'd `emitir_reimpresion` is rejected

**Given** an operador role with only the legacy typo'd permission `emitir_reimpresion` granted (and NOT `reimprimir_ticket`)
**When** the operador POSTs to `/api/v1/workflows/reimpresion-ticket`
**Then** the request MUST fail with `403 Forbidden` (the dependency check no longer recognizes `emitir_reimpresion`).
**And** the test MUST verify the rejection to prove the typo'd permission is no longer in the dependency check.

#### Definition of Done for REQ-OPS-076

- `api/v1/workflows.py:74` changed from `"emitir_reimpresion"` to `"reimprimir_ticket"`.
- No migration; no permission re-seed; no role grants re-issued.
- Integration test `tests/integration/test_workflows_router_wiring.py::test_workflows_router_config_uses_reimprimir_ticket_not_emitir_reimpresion` PASSES.
- Integration test `tests/integration/test_workflows_router_wiring.py::test_anular_reimpresion_endpoint_requires_anular_reimpresion_permission` PASSES.

---

### REQ-OPS-077 — Anulación endpoint INSERTs NEW row with `workflow_estado='rechazada'` + `motivo_anulacion`

**Level**: SHALL. **Statement**: The branch MUST INSERT a NEW `prod.reimpresion_ticket` row with `workflow_estado='rechazada'`, `motivo_anulacion` captured from request, `uuid_reimpresion_padre=<tip.uuid>` (the current chain tip). The handler MUST use permission `anular_reimpresion` (separate from `reimprimir_ticket`, seeded in MIGRATION 0029 Op 2 and granted to roles in Op 3). The original chain tip row MUST NEVER be UPDATEd (DEC-TKT-03 + `[L-W]` insert-only invariant).

**Rationale**: plan.md line 993 explicitly flags the anulación as **"gap huérfano detectado"**. The `[L-W]` WorkflowBase pattern mirrors `anulaciones` / `alerta` / `envio_dian`: anulación is a NEW row that captures the audit trail of why a prior transición is being rejected. Closing this gap is the regulatory minimum for operator-correction flows (admin cancels a prior reimpresión that had a charging typo).

**Source**: `plan.md` line 993 (orphan anulación gap); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 110-237 (`append_transition`); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 240-348 (`read_chain_tip`); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 1638-1692 (FK constraint on `uuid_reimpresion_padre`).

#### Scenario 1: Happy path anulación — INSERT NEW row with `workflow_estado='rechazada'`, `uuid_reimpresion_padre=<tip.uuid>`

**Given** an existing reimpresion_ticket chain with tip `<tip>` at `workflow_estado='autorizada' | 'ejecutada' | 'solicitada'`
**And** an operador with role granted `anular_reimpresion` permission
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket/{uuid}/anular` with body `{"motivo_anulacion":"Error operativo: reimprimir solicitada por error administrativo"}`
**Then** `repo.workflow.read_chain_tip(session, ReimpresionTicket, root_uuid=uuid, parent_fk_column="uuid_reimpresion_padre")` MUST return `<tip>`.
**And** the handler MUST INSERT a NEW `prod.reimpresion_ticket` row with `workflow_estado='rechazada'`, `uuid_reimpresion_padre=<tip.uuid>`, `motivo_anulacion=<payload.motivo_anulacion>`, `bi-temporal_estado='activo'`.
**And** the original `<tip>` row MUST remain unchanged (NEVER UPDATE on user-meaningful fields).
**And** MUST return `201 Created` with `ReimpresionTicketRead{uuid:<new.uuid>, workflow_estado:'rechazada', uuid_reimpresion_padre:"<tip.uuid>", motivo_anulacion:"...", ...}` and `Cache-Control: no-store`.

#### Scenario 2: Anulación blocked when chain tip already `rechazada` (terminal state)

**Given** an existing reimpresion_ticket chain with tip `<tip>` at `workflow_estado='rechazada'` (terminal — already anulada)
**And** an operador with `anular_reimpresion` permission
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket/{uuid}/anular` again
**Then** `read_chain_tip` MUST return `<tip>` with `workflow_estado='rechazada'`.
**And** the handler MUST return `409 Conflict` with body `{"error":"anulacion_no_permitida", "uuid_reimpresion":"<uuid>", "estado_actual":"rechazada"}` and `Cache-Control: no-store`.
**And** NO NEW `prod.reimpresion_ticket` row MUST be INSERTed (terminal state guard).

#### Scenario 3: Permission check — `anular_reimpresion` gate enforced

**Given** the handler dependency at the new module requires permission `anular_reimpresion`
**When** an operador role is granted `anular_reimpresion` via MIGRATION 0029 Op 3 + `prod.permisos_usuario`
**Then** the endpoint MUST accept the request (handler body reachable).
**And** an operador without `anular_reimpresion` MUST receive `403 Forbidden`.

#### Definition of Done for REQ-OPS-077

- Handler `_anular_reimpresion_ticket` wired in `api/v1/workflows_reimpresion.py` with `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular`.
- KD-3 issuer chain `_anular_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")` applied via FastAPI dependency with `permission_required="anular_reimpresion"`.
- Handler calls `repo.workflow.append_transition(...)` with `parent_uuid=tip.uuid, parent_fk_column="uuid_reimpresion_padre"` and `workflow_estado='rechazada'`.
- Single-commit invariant preserved (KD-TKT-01 — exactly one `await session.commit()`).
- Unit tests `test_happy_path_anulacion` + `test_anulacion_blocked_when_already_rechazada` + `test_403_without_anular_reimpresion_permission` PASS.
- `Cache-Control: no-store` header verified on 201 / 409 / 500 responses.

---

### REQ-OPS-078 — Chain integrity via `uuid_reimpresion_padre` FK + `read_chain_tip` helper

**Level**: SHALL. **Statement**: The handler MUST use `repo/workflow.py::read_chain_tip` to find the current chain tip (latest row by `timestamp_evento DESC LIMIT 1`, with the REQ-X9 tie-break `(max(timestamp_evento), longest chain, lex(uuid))`). The NEW row's `uuid_reimpresion_padre` MUST reference the chain tip's `uuid`. The chain MUST be reconstructable by recursive SELECT on `uuid_reimpresion_padre`. The FK constraint on `prod.reimpresion_ticket.uuid_reimpresion_padre` (migration 0001 lines 1690-1692) MUST be enforced at the DB layer.

**Rationale**: plan.md línea 953 + the F1.5 PR5-016 precedent establish the chain IS the audit trail. FK enforces referential integrity at the DB layer; `read_chain_tip` encodes the canonical tie-break. Without this contract the anulación chain can fork unpredictably and produce orphans that block regulatory audits.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 240-348 (`read_chain_tip`); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 1690-1692 (FK `fk_reimpresion_ticket_uuid_reimpresion_padre`); plan.md línea 953.

#### Scenario 1: `read_chain_tip` returns the latest row by `timestamp_evento DESC`

**Given** 3 `prod.reimpresion_ticket` rows in a chain: `:r1` (root, `uuid_reimpresion_padre=NULL`, `timestamp_evento='2026-09-15T10:00:00Z'`), `:r2` (`uuid_reimpresion_padre=:r1.uuid`, `timestamp_evento='2026-09-15T11:00:00Z'`), `:r3` (`uuid_reimpresion_padre=:r2.uuid`, `timestamp_evento='2026-09-15T12:00:00Z'`)
**When** the handler invokes `read_chain_tip(session, ReimpresionTicket, root_uuid=:r1.uuid, parent_fk_column="uuid_reimpresion_padre")`
**Then** the helper MUST return `:r3` (latest by `timestamp_evento DESC`, applying the REQ-X9 tie-break on equal timestamps).
**And** the returned object MUST expose `uuid_actual=:r3.uuid` AND `estado=:r3.workflow_estado`.

#### Scenario 2: Chain reconstruction via recursive CTE on `uuid_reimpresion_padre`

**Given** 5 `prod.reimpresion_ticket` rows `:e1`, `:e2`, `:e3`, `:e4`, `:e5` forming a chain (each row's `uuid_reimpresion_padre` = previous row's `uuid`, except `:e1` which is `NULL`)
**When** a recursive WITH query `WITH RECURSIVE chain AS (SELECT * FROM prod.reimpresion_ticket WHERE uuid=:e1.uuid AND uuid_reimpresion_padre IS NULL UNION ALL SELECT e.* FROM prod.reimpresion_ticket e JOIN chain c ON e.uuid_reimpresion_padre = c.uuid) SELECT uuid, uuid_reimpresion_padre, workflow_estado, timestamp_evento FROM chain ORDER BY timestamp_evento ASC` executes
**Then** the chain MUST be reconstructed in order: `:e1` (root, `uuid_reimpresion_padre=NULL`) → `:e2` → `:e3` → `:e4` → `:e5` (tip).
**And** each row's `workflow_estado` MUST be preserved.

#### Scenario 3: FK constraint enforces referential integrity on `uuid_reimpresion_padre`

**Given** a NEW `prod.reimpresion_ticket` row INSERT with `uuid_reimpresion_padre=<fake.uuid>` (UUID that does NOT exist in the table)
**When** the INSERT is executed
**Then** PostgreSQL MUST raise `psycopg2.errors.ForeignKeyViolation` (pgcode `23503`) at the DB layer.
**And** the handler MUST translate this exception to a typed 5xx (NEVER expose the pgcode in response body, headers, or info+ logs).

#### Definition of Done for REQ-OPS-078

- `repo/workflow.py::read_chain_tip` reused from F1.5 PR5-016 (no modification).
- Handler anulación uses `read_chain_tip(session, ReimpresionTicket, root_uuid=uuid_reimpresion, parent_fk_column="uuid_reimpresion_padre")`.
- Unit tests `test_read_chain_tip_returns_latest` + `test_chain_reconstruction_recursive_cte` + `test_fk_constraint_violation_raises_typed_exception` PASS.
- FK constraint verification via raw SQL `INSERT INTO prod.reimpresion_ticket (uuid, uuid_reimpresion_padre, ...) VALUES (gen_random_uuid(), gen_random_uuid(), ...)` raises `23503`.

---

### REQ-OPS-079 — CONDITIONAL MIGRATION 0029 siembra `costos_servicios.concepto='reimpresion'` if absent

**Level**: MUST. **Statement**: MIGRATION 0029 Op 1 MUST pre-flight `prod.costos_servicios WHERE concepto='reimpresion' AND vigente_hasta IS NULL AND estado='activo'`. If row absent (count == 0), INSERT a new row with `concepto='reimpresion', costo=0, tipo_calculo='fijo', vigente_desde=NOW(), vigente_hasta=NULL, estado='activo'`. If row present (count >= 1), no-op (idempotent). This is defensive: F1.11 ships regardless of whether siembra was already done by another HU.

**Rationale**: Mirrors F1.7's `impuestos.IVA` inline siembra (MIGRATION 0026 pattern + pending list). Idempotent on re-apply. Operator-configurable cost avoids hardcoded values — the cost is informational for F1.11 (the issuance flow is decoupled from cost charging; see DEC-TKT-04). The migration MUST ship even when siembra is already present because we cannot know in advance whether it exists at deployment time.

**Source**: `plan.md` lines 989-1006 (F1.11 mandate); `modelo_datos_er.mmd` lines 230-244 (`costos_servicios` [V]); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 297-309 (`costos_servicios` create_table).

#### Scenario 1: Siembra absent → INSERT

**Given** no vigente `prod.costos_servicios` row with `concepto='reimpresion'` (count == 0 from the pre-flight SELECT)
**When** MIGRATION 0029 Op 1 is applied
**Then** the `DO $$` block MUST INSERT a new `prod.costos_servicios` row with `uuid=gen_random_uuid(), concepto='reimpresion', costo=0, tipo_calculo='fijo', vigente_desde=NOW(), vigente_hasta=NULL, estado='activo', created_at=NOW(), created_by=NULL, sync_status='sincronizado', sync_attempts=0`.
**And** the `ON CONFLICT (concepto, vigente_desde) DO NOTHING` clause MUST prevent duplicate key violations if a concurrent TX inserts first.

#### Scenario 2: Siembra present → no-op (idempotent)

**Given** an existing vigente `prod.costos_servicios` row with `concepto='reimpresion'` (count >= 1 from the pre-flight SELECT, possibly inserted by a manual siembra or prior migration run)
**When** MIGRATION 0029 Op 1 is applied
**Then** the `DO $$` block MUST NOT INSERT a new row (the `IF siembra_count = 0` guard skips the INSERT branch).
**And** the existing row MUST remain unchanged (no UPDATE).
**And** the migration MUST be idempotent: a second application MUST NOT change the state.

#### Definition of Done for REQ-OPS-079

- MIGRATION 0029 Op 1 `DO $$` block with pre-flight `ASSERT prod.costos_servicios exists` + count check + conditional INSERT.
- MIGRATION 0029 Op 2 seeds `anular_reimpresion` permission (`INSERT INTO prod.permisos VALUES (..., 'anular_reimpresion', ...)` if NOT EXISTS).
- MIGRATION 0029 Op 3 grants `anular_reimpresion` to `operador` and `admin` roles via `prod.permisos_usuario` (idempotent via NOT EXISTS subquery).
- Integration test `tests/integration/test_migration_0029_idempotent.py::test_siembra_costos_servicios_reimpresion_pre_flight` PASSES (covers both absent and present cases).
- Integration test `tests/integration/test_migration_0029_idempotent.py::test_migration_0029_idempotent_upgrade_downgrade_upgrade` PASSES.

---

### REQ-OPS-080 — `uuid_factura` OPTIONAL (DEC-TKT-04) — nullable FK

**Level**: SHALL. **Statement**: The `prod.reimpresion_ticket.uuid_factura` column is OPTIONAL (nullable FK to `prod.facturas.uuid`). F1.11 does NOT require a `prod.facturas` row to exist for reimpresión. The full create-factura-then-reimprimir flow is deferred to HU-F8.3 (frontend Fase 8). If `uuid_factura` IS provided, the handler validates existence via V1 SELECT but does NOT snapshot the cost (the issuance flow is decoupled from cost charging per DEC-TKT-04).

**Rationale**: 170 LOC budget (plan.md line 1001) is tight for a full F1.9-style atomic factura creation + reimpresion_ticket INSERT in one TX. Splitting concerns keeps F1.11 focused on workflow chain + permission reconciliation. The admin-correction use case (anular a reimpresion that had a charging typo) is served by leaving `uuid_factura` nullable.

**Source**: `plan.md` line 1001 (170 LOC budget); `backend/packages/parkos_core/src/parkos_core/models/L_W/reimpresion_ticket.py` lines 29-90 (`uuid_factura` nullable column); `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py` lines 50-132 (`ReimpresionTicketCreate` schema).

#### Scenario 1: `uuid_factura: null` accepted — reimpresión recorded without factura

**Given** a request body `{"motivo":"...", "uuid_ingreso":":i", "uuid_factura":null}`
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket`
**Then** Pydantic v2 schema validation MUST accept `uuid_factura: null` as valid input.
**And** the handler MUST skip the V1 SELECT-by-`uuid_factura` (the `if payload.uuid_factura is not None` guard).
**And** MUST INSERT a new `prod.reimpresion_ticket` row with `uuid_factura=NULL`.
**And** MUST return `201 Created` with `ReimpresionTicketRead{uuid_factura:null, workflow_estado:'autorizada', ...}`.

#### Scenario 2: `uuid_factura` populated accepted — FK validated, not snapshotted

**Given** an existing `prod.facturas.uuid=:f`
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket` with body `{"motivo":"...", "uuid_ingreso":":i", "uuid_factura":":f"}`
**Then** the handler MUST execute the V1 SELECT `SELECT uuid FROM prod.facturas WHERE uuid=:f` and find the row.
**And** MUST INSERT a new `prod.reimpresion_ticket` row with `uuid_factura=:f` populated.
**And** MUST return `201 Created` with `ReimpresionTicketRead{uuid_factura:":f", workflow_estado:'autorizada', ...}`.
**And** the handler MUST NOT read or copy `prod.facturas.costo` to the reimpresion row (issuance flow decoupled from cost charging).

#### Definition of Done for REQ-OPS-080

- Pydantic v2 `ReimpresionTicketCreateEndpoint` schema with `uuid_factura: uuid_lib.UUID | None = None` and `extra='forbid'` (inherited from `_Base`).
- Handler `_create_reimpresion_ticket` Step 4 conditionally validates `uuid_factura` only if not None.
- Unit tests `test_uuid_factura_null_accepted` + `test_uuid_factura_populated_validates_fk` + `test_404_uuid_factura_not_found` PASS.
- Schema `ReimpresionTicketRead` exposes `uuid_factura: uuid_lib.UUID | None` (nullable).

## Cross-Cutting Requirements

### REQ-OPS-XR1 — Defense in depth: 5 layers

**Given** the 4-table atomic insert + NIT validation + immutability invariants are critical to billing correctness
**When** any layer of the defense fails
**Then** the remaining 4 layers MUST contain the failure:

1. **(a) DB layer — partial unique index `one_factura_per_salida`**: `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_factura_per_salida ON prod.facturas (uuid_salida) WHERE uuid_salida IS NOT NULL` (closes TOCTOU between concurrent cajeros attempting the same `uuid_salida`; `prod.facturas` is NOT partitioned per migration 0001 lines 607-626, so the partial unique index is feasible). UniqueViolationError (pgcode `23505`) maps to 409 `factura_duplicada`.
2. **(b) DB layer — BEFORE INSERT trigger `fn_factura_pagos_init_pago_uniqueness`**: analogía `fn_factura_pagos_reverso_uniqueness` (migration 0004 lines 35-66). Closes TOCTOU on `prod.factura_pagos` rows where `tipo_movimiento='pago'`. `prod.factura_pagos` IS partitioned by `RANGE (fecha_retencion_hasta)` (migration 0001 line 716), so partial unique index is infeasible — BEFORE INSERT trigger is the only DB-layer defense.
3. **(c) Repo layer — typed exceptions**: `SalidaNoFacturableError(uuid_salida)`, `ClienteNoEncontradoFacturaError(numero_identificacion)`, `NitInvalidoError(dv_esperado, dv_recibido)`, `TotalNoCoherenteError(total_recibido, total_calculado, diferencia)`, `VoucherRequeridoError(medio_pago)`. Each exception maps to a typed HTTP error response; pgcode NEVER appears in response body, headers, or info+ logs.
4. **(d) Handler layer — 12-step chain + single `await session.commit()`**: `create_factura` enforces strict 12-step order (locked by AST walk `test_factura_handler_step_order.py`); single commit (KD-FACT-01, locked by AST walk `test_factura_handler_single_commit.py`); tenant scope check post-V1 (KD-S2 analog from F1.7); V6 total coherence ±0.01 COP before INSERT; KD-FACT-02 `FOR SHARE` lock acquired before bulk INSERT; `Cache-Control: no-store` on all 2xx/4xx/5xx responses.
5. **(e) AST walk layer — invariant enforcement**: `tests/static/test_factura_handler_single_commit.py` (~80 LOC) and `tests/static/test_factura_handler_step_order.py` (~80 LOC) enforce KD-FACT-01 + literal step order.

**RFC 2119**: MUST (each layer independently tested; failure of any one layer MUST be contained by the other 4).

#### Scenario: layer (a) — concurrent INSERT same `uuid_salida` raises `UniqueViolationError` → 409

**Given** `prod.facturas` row with `uuid_salida=:p` already exists
**When** concurrent TX attempts `INSERT INTO prod.facturas (uuid_salida, ...) VALUES (:p, ...)`
**Then** PostgreSQL MUST raise `UniqueViolationError` (pgcode `23505`).
**And** the handler MUST translate to `HTTPException(status_code=409, detail={"error":"factura_duplicada", "uuid_salida":":p"})`.

#### Scenario: layer (b) — BEFORE INSERT trigger rejects second `pago` for same `uuid_factura`

**Given** `prod.factura_pagos` already has a row with `uuid_factura=:f` and `tipo_movimiento='pago'`
**When** concurrent INSERT attempts a second `pago` row for `:f`
**Then** the BEFORE INSERT trigger MUST `RAISE EXCEPTION` with message `fn_factura_pagos_init_pago_uniqueness: pago duplicado para uuid_factura=:f`.
**And** the handler MUST translate to `HTTPException(status_code=409, detail={"error":"pago_duplicado", "uuid_factura":":f"})`.

### REQ-OPS-XR2 — `Cache-Control: no-store` header on all responses

**Given** billing responses must never be cached (defense in depth against cache poisoning)
**When** any handler under `/api/v1/facturacion/` responds (2xx, 4xx, or 5xx)
**Then** the response MUST carry `Cache-Control: no-store` header.

#### Scenario: 201 Created carries `Cache-Control: no-store`

**When** `POST /facturacion/factura` returns `201 Created`
**Then** the response MUST carry `Cache-Control: no-store`.

#### Scenario: 422 nit_invalido carries `Cache-Control: no-store`

**When** `POST /facturacion/factura` returns `422 nit_invalido`
**Then** the response MUST carry `Cache-Control: no-store`.

### REQ-OPS-XR3 — DEC-FACT-01 amended: F1.9 itself never UPDATEs rows in `prod.facturas`

**RFC 2119**: The F1.9 handler `create_factura` MUST perform only INSERT operations on `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, and `prod.factura_pagos`. State transitions on a `prod.facturas` row (e.g., `emitida → pagada`) MUST happen via NEW rows with the bi-temporal composite PK `(uuid, fecha_retencion_hasta)` — NOT via UPDATE.

**Behavior**:

- `prod.facturas` is `[L-E]` (bi-temporal versioning, migration 0001 lines 607-626); immutability is provided by the composite PK, NOT by an `fn_facturas_inmutable` DB trigger.
- `fn_factura_detalle_inmutable`, `fn_factura_impuestos_inmutable`, `fn_factura_pagos_inmutable` triggers (migration 0001 lines 2024-2088) still apply to the `[A]`-class detail/impuestos/pagos tables.
- Anulación (state `emitida → anulada`) is OUT OF F1.9 scope (deferred to HU-F1.13 via `prod.anulaciones` workflow — Fase 7+).
- F1.9 does NOT modify the `fn_*_inmutable` triggers and does NOT introduce `fn_facturas_inmutable` (R2 RESOLVED — bi-temporal PK handles immutability).

#### Scenario: state transitions happen via new rows con composite PK

**Given** a `prod.facturas` row with `uuid=:f, fecha_retencion_hasta=2028-01-01T00:00:00Z, estado=emitida`
**When** a future HU creates a state transition (e.g., `emitida → pagada`)
**Then** the future HU MUST INSERT a new row with `uuid=:f, fecha_retencion_hasta=2028-01-02T00:00:00Z` (different composite PK timestamp) and MUST NOT UPDATE the original row.

### REQ-OPS-XR1 — Defense in depth: 5 layers (mirror of F1.9 REQ-OPS-XR1, F1.10-specific)

**Given** the FE + envio chain is critical to DIAN regulatory compliance (numbering contiguity, audit trail integrity, cloud-dispatcher-outage tolerance)
**When** any layer of the defense fails
**Then** the remaining 4 layers MUST contain the failure:

1. **(a) KD-3 issuer chain**: `_fe_issuer_dep = requires_issuer("operador-", "admin-")` (F1.9 pattern verbatim). Branch operator with `emitir_factura` permission emits; admin cross-branch. Applied at handler entry as a FastAPI dependency; runs BEFORE any handler body code.
2. **(b) Tenant scope post-V1**: After resolving `target_sucursal` from `prod.facturas.uuid_sucursal` (V1 in `POST /factura-electronica`) or from `prod.factura_electronica.uuid_sucursal` (V1 in `GET` and `/reintentar`), if `ctx.issuer_prefix == "operador-"` AND `(ctx.sucursal_uuid is None OR target_sucursal != ctx.sucursal_uuid)`, return `403 {"error":"tenant_scope_violation"}`. Admin (`admin-`) bypasses. KD-S2 analog from F1.7.
3. **(c) DB-layer partial unique index `one_fe_per_factura`**: MIGRATION 0028 Op 2 `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_fe_per_factura ON prod.factura_electronica (uuid_factura) WHERE uuid_factura IS NOT NULL`. Defense in depth: closes the V2 SELECT-before-INSERT TOCTOU race window between two concurrent cajeros attempting the same `prod.facturas.uuid`. `psycopg2.errors.UniqueViolation` (pgcode `23505`) maps to `409 factura_electronica_ya_existe` (REQ-OPS-067 Scenario 3).
4. **(d) `assign_consecutivo` SELECT FOR UPDATE**: `repo/resolucion_facturacion.py::assign_consecutivo` already takes `SELECT ... FOR UPDATE` on `prod.resolucion_facturacion` (verified, source lines 114-120). Lock held until `await session.commit()`. Concurrent calls on the SAME resolution serialize cleanly. NO modification in F1.10 (DEC-FE-05).
5. **(e) Handler 409 mapping + typed exceptions**: 8 typed exceptions mapped to HTTP responses per `HU-F1.10-proposal.md` §8 Layer 5 table. The pgcode NEVER appears in the response body, headers, or info+ logs.

**RFC 2119**: MUST (each layer independently tested; failure of any one layer MUST be contained by the other 4).

#### Scenario: layer (c) — concurrent INSERT same `uuid_factura` raises `UniqueViolationError` → 409

**Given** `prod.factura_electronica` row with `uuid_factura=:f` already exists
**When** concurrent TX attempts `INSERT INTO prod.factura_electronica (uuid_factura, ...) VALUES (:f, ...)`
**Then** PostgreSQL MUST raise `psycopg2.errors.UniqueViolation` (pgcode `23505`).
**And** the handler MUST translate to `HTTPException(status_code=409, detail={"error":"factura_electronica_ya_existe", "uuid_factura":":f"})`.

### REQ-OPS-XR2 — `Cache-Control: no-store` header on all responses (mirror of F1.9 REQ-OPS-XR2)

**Given** FE responses must never be cached (defense in depth against cache poisoning of `cufe`, `estado`, `timestamp_evento`)
**When** any handler under `/api/v1/facturacion/factura-electronica` responds (2xx, 4xx, or 5xx)
**Then** the response MUST carry `Cache-Control: no-store` header.

#### Scenario: 201 Created carries `Cache-Control: no-store`

**When** `POST /factura-electronica` returns `201 Created`
**Then** the response MUST carry `Cache-Control: no-store`.

#### Scenario: 409 `numeracion_agotada` carries `Cache-Control: no-store`

**When** `POST /factura-electronica` returns `409 numeracion_agotada`
**Then** the response MUST carry `Cache-Control: no-store`.

### REQ-OPS-XR3 — KD-FE-01 single `await session.commit()` invariant (mirror of F1.9 REQ-OPS-XR3 / KD-FACT-01)

**RFC 2119**: The `create_factura_electronica` and `retry_factura_electronica` handler bodies in `api/v1/facturacion.py` MUST each contain **EXACTLY ONE** `await session.commit()` call. Multiple `commit()` calls, `session.begin_nested()`, or `SAVEPOINT` statements **MUST NOT** appear anywhere in the handler body or its callees (KD-FE-01 + DEC-FE-01).

**Defense**: AST walks enforce the invariant:

- `tests/static/test_fe_handler_single_commit.py` parses `create_factura_electronica` body using `ast.walk` BFS and asserts:
  - `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and getattr(n.value.func, 'attr', '') == 'commit']) == 1`
  - `len([n for n in ast.walk(body) if isinstance(n, ast.Call) and getattr(n.func, 'attr', '') == 'begin_nested']) == 0`
  - No `SAVEPOINT` or `RELEASE SAVEPOINT` string literals in the body.
- `tests/static/test_fe_retry_handler_single_commit.py` enforces the same invariant for `retry_factura_electronica`.
- `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` enforces that no UPDATE on user-meaningful fields appears in the retry handler.

#### Scenario: T10 AST walk enforces exactly 1 commit call in `create_factura_electronica`

**Given** the source file `api/v1/facturacion.py` containing `create_factura_electronica`
**When** `tests/static/test_fe_handler_single_commit.py` runs
**Then** the AST walk MUST assert `commit_count == 1`; if multiple commits OR any `begin_nested` OR any `SAVEPOINT` is detected, the test MUST fail with a typed error referencing the offending AST node line number.

#### Scenario: handler with two `commit()` calls MUST fail AST walk

**Given** a hypothetical handler with `await session.commit()` at line 50 and `await session.commit()` at line 80
**When** the AST walk runs
**Then** `commit_count == 2` MUST trigger test failure with message `"KD-FE-01 violation: expected 1 commit, found 2 at lines [50, 80]"`.


### REQ-OPS-XR4 — Defense in depth: 5 layers + AST walk for `[L-W]` insert-only invariant (mirror F1.9 XR1..XR3 + F1.10 XR1..XR3)

**Level**: SHALL. **Statement**: F1.11 MUST apply the F1.10 defense-in-depth pattern: (1) KD-3 issuer chain `_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")` + `_anular_reimpresion_issuer_dep`; (2) permission check (`reimprimir_ticket` for create + `anular_reimpresion` for anular — Layer 1 + 2 combined per F1.10 pattern, with GAP-BE-04 reconciled via DEC-TKT-01); (3) tenant scope post-V1 (KD-S2 analog from F1.7) — `operador-` issuer forbidden from cross-branch `uuid_sucursal != ctx.sucursal_uuid`; (4) FK chain integrity via `uuid_reimpresion_padre` (REQ-OPS-078); (5) handler 422/409 mapping (REQ-OPS-077 + REQ-OPS-075 Scenario 4). Additionally, an AST walk MUST enforce the `[L-W]` insert-only invariant: NO UPDATE statements on `prod.reimpresion_ticket` user-meaningful fields (`workflow_estado`, `motivo`, `motivo_anulacion`, `uuid_reimpresion_padre`) from the F1.11 handler bodies. Only `vigente_hasta` MAY be UPDATEd for bi-temporal versioning (WorkflowBase contract).

**Rationale**: 4NF compliance (state lives on the chain, not duplicated on the original row). Audit trail completeness (every transition is a row with `created_at`, `created_by`, `timestamp_evento`). Defense in depth against accidental UPDATE in future HUs that touch the reimpresion handler.

**Source**: `tests/static/test_no_raw_dml_on_lw_tables.py` (F1.5 PR5-016 precedent); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 110-237 (`append_transition`); F1.10 REQ-OPS-XR1..XR3 mirror.

#### Scenario 1: AST walk — no UPDATE on user-meaningful fields

**Given** the source files `api/v1/workflows_reimpresion.py` containing `create_reimpresion_ticket` and `anular_reimpresion_ticket`
**When** `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` runs
**Then** the AST walk MUST assert that no `UPDATE prod.reimpresion_ticket ...` statement or `update(ReimpresionTicket)` SQLAlchemy core call appears in either handler body.
**And** MUST assert that no UPDATE on `workflow_estado`, `motivo`, `motivo_anulacion`, `uuid_reimpresion_padre`, `uuid_ingreso`, `uuid_factura` appears.
**And** MUST assert that exactly one `INSERT INTO prod.reimpresion_ticket` (or equivalent `repo.workflow.append_transition(...)` helper call) appears per handler.
**And** MUST assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(n.value.func, 'attr', '') == 'commit']) == 1` per handler (KD-TKT-01 single-commit invariant).

#### Scenario 2: `vigente_hasta` MAY be UPDATEd (bi-temporal versioning)

**Given** the bi-temporal WorkflowBase pattern from F1.5 PR5-016
**When** the WorkflowBase closes a version (sets `vigente_hasta=NOW()` for the previous active row)
**Then** this UPDATE MUST be allowed (the ONLY UPDATE allowed by WorkflowBase on the L-W tables).
**And** the AST walk MUST permit `update(...).where(...).values(vigente_hasta=...)` patterns originating from the `WorkflowBase` superclass.

#### Definition of Done for REQ-OPS-XR4

- AST walk `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` PASSES for both `create_reimpresion_ticket` and `anular_reimpresion_ticket`.

## ADDED Requirements

### REQ-OPS-083 — Single-commit atomicity across 9 tables (KD-VENTA-01)

**Source**: HU-F1.12 (DEC-VENTA-01) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
The handler MUST issue exactly one `await session.commit()` at the END of the request body (Step 10 of the 10-step chain), covering all 5 `[V]` writes (`prod.clientes`, `prod.vehiculos`, `prod.subscripciones_cliente`, `prod.subscripcion_vehiculos`, `prod.tipo_subscripciones` lock-only) + the 4 optional `[A]`/`[L-E]` cobro writes (`prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos`) when `cobrar_ahora=true` + the 2 optional `[L-W]`/`[L-E]` FE writes (`prod.factura_electronica`, `prod.envio_dian`) when `emitir_factura_electronica=true` + N `prod.log_transaccional` co-INSERTs. The handler MUST NOT use `session.begin_nested()` or `SAVEPOINT`. All helper functions (`crear_*`) MUST stay commit-free — they `session.add()` + `await session.flush()` only.

**Rationale**: Cross-domain atomicity is the entire business requirement (plan.md line 1014: "sin que un fallo a mitad de camino deje datos inconsistentes"). F1.10 KD-FE-01 + F1.11 KD-TKT-01 establish the single-commit invariant as the canonical pattern for multi-table writes. The 9-table single commit is well within PostgreSQL's capabilities — `[V]` tables have minimal locking (UK checks), `[A]`/`[L-E]`/`[L-W]` writes are INSERT-only, no long-held locks.

**Source**: `plan.md` line 1014 (atomicity mandate); `backend/packages/parkos_core/src/parkos_core/repo/versioned.py::close_and_insert` (commit-free contract); F1.10 REQ-OPS-065 (KD-FE-01 precedent); F1.11 REQ-OPS-XR3 (KD-TKT-01 single-commit precedent).

**Scenario 1: Happy path — all writes succeed in 1 commit, all rows visible post-response**
- **Given** a `VentaSuscripcionCreate` payload with valid `cliente` (new), 1 placa `ABC123`, a vigente `uuid_tipo_subscripcion`, `fecha_inicio_cobertura='2026-09-12'`, `cobrar_ahora=true`, `emitir_factura_electronica=true`
- **When** the handler reaches Step 10 and calls `await session.commit()` exactly once
- **Then** exactly one `prod.clientes` row MUST be visible (uuid matches response)
- **And** exactly one `prod.vehiculos` row MUST be visible (placa=`ABC123`)
- **And** exactly one `prod.subscripciones_cliente` row MUST be visible
- **And** exactly one `prod.subscripcion_vehiculos` row MUST be visible (junctions the subscription to the vehiculo)
- **And** exactly one `prod.facturas` row + 1 `prod.factura_detalle` row + 1 `prod.factura_impuestos` row + 1 `prod.factura_pagos` row MUST be visible
- **And** exactly one `prod.factura_electronica` row + 1 `prod.envio_dian` row MUST be visible
- **And** the response MUST be `201 Created` with `VentaSuscripcionResponse` carrying all nested UUIDs + `Cache-Control: no-store`.

**Scenario 2: Mid-flight failure — any helper raise rolls back the entire TX**
- **Given** the same valid payload but Step 8a (`_factura_sub_chain` when `cobrar_ahora=true`) raises `IvaNoConfiguradoError` because `prod.impuestos.IVA` row is missing
- **When** the handler catches the exception and returns `500 iva_no_configurado`
- **Then** `await session.commit()` MUST NOT be called (KD-VENTA-01)
- **And** the entire TX MUST be rolled back — ZERO `prod.clientes`, `prod.vehiculos`, `prod.subscripciones_cliente`, `prod.subscripcion_vehiculos`, `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos` rows MUST exist after the rollback (no orphan clientes / vehiculos / subscripciones if cobro failed)
- **And** NO `prod.factura_electronica` / `prod.envio_dian` rows MUST exist.

**Scenario 3: AST walk — handler source contains EXACTLY ONE `await session.commit()` call**
- **Given** the source file `api/v1/clientes_venta.py` containing `venta_suscripcion` handler
- **When** `tests/static/test_venta_handler_single_commit.py` runs an `ast.walk()` over the handler body
- **Then** the AST walk MUST assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(n.value.func, 'attr', '') == 'commit']) == 1` (exactly one `await session.commit()` call)
- **And** MUST assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(getattr(n.value, 'func', None), 'attr', '') == 'begin_nested']) == 0` (no SAVEPOINT)
- **And** MUST assert NO occurrence of the literal string `"SAVEPOINT"` in the handler body (defense in depth).

---

### REQ-OPS-084 — Plan lock `SELECT FOR UPDATE` on `prod.tipo_subscripciones` (KD-VENTA-02 + DEC-VENTA-04)

**Source**: HU-F1.12 (DEC-VENTA-02 + DEC-VENTA-04) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
The handler MUST take `SELECT ... FOR UPDATE` (exclusive, NOT `FOR SHARE`) on the vigente `prod.tipo_subscripciones` row identified by `payload.uuid_tipo_subscripcion` BEFORE any other lock is acquired (Step 2 of the 10-step chain). The lock MUST be held until `await session.commit()` at Step 10. If the lookup returns no vigente row, the handler MUST raise `HTTPException(404, {"error": "tipo_subscripcion_no_encontrado", "uuid_tipo_subscripcion": str(payload.uuid_tipo_subscripcion)}, headers=no_store_headers())`. If multiple vigentes exist (corrupt DB), the handler MUST deterministically pick the latest by `vigente_desde DESC LIMIT 1`.

**Rationale**: The plan read mutates the sale semantics — `fecha_inicio_cobertura` is captured, and concurrent ventas on the SAME plan with different `fecha_inicio_cobertura` would produce different A-09 prorrateo amounts. `FOR SHARE` (F1.9 KD-FACT-02 pattern) is insufficient because two concurrent ventas could compute prorrateo on a stale snapshot. `FOR UPDATE` serializes the calc.

**Source**: `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 195-210 (`tipo_subscripciones` schema + bi-temporal VersionedBase); F1.9 KD-FACT-02 (`FOR SHARE` precedent, intentionally diverged); F1.10 REQ-OPS-064 (`assign_consecutivo` `FOR UPDATE` precedent); `plan.md` lines 1010-1054 (KD-VENTA-02).

**Scenario 1: Single venta on plan — lock acquired, sold, released on commit**
- **Given** a vigente `prod.tipo_subscripciones` row with `uuid=:p`, `valor=50000`, `duracion_dias=30`, `cantidad_maxima_vehiculos=2`, `mismo_tipo_vehiculo=true`
- **When** the handler invokes `SELECT * FROM prod.tipo_subscripciones WHERE uuid=:p AND vigente_hasta IS NULL ORDER BY vigente_desde DESC LIMIT 1 FOR UPDATE`
- **Then** the row lock MUST be acquired (the TX owns the lock until commit)
- **And** the handler MUST proceed to Step 3 (cliente lookup-or-create)
- **And** after `await session.commit()` at Step 10, the lock MUST be released (other TXs can now lock the same row).

**Scenario 2: Concurrent ventas on SAME plan — second venta waits, then succeeds with fresh `fecha_inicio_cobertura` capture**
- **Given** two concurrent TXs both POST `/api/v1/clientes/venta-suscripcion` with the SAME `uuid_tipo_subscripcion=:p` but DIFFERENT `fecha_inicio_cobertura` (TX-A: `'2026-09-10'`, TX-B: `'2026-09-25'`)
- **When** both TXs reach Step 2 simultaneously
- **Then** TX-A MUST acquire `SELECT FOR UPDATE` on `:p` first
- **And** TX-B MUST block at the `SELECT FOR UPDATE` until TX-A commits
- **And** TX-B MUST re-read `:p` (no read snapshot taken before the lock release) and compute prorrateo on its OWN `fecha_inicio_cobertura='2026-09-25'` (after-day-15 prorrateo path)
- **And** TX-A MUST compute prorrateo on its OWN `fecha_inicio_cobertura='2026-09-10'` (no prorrateo, full `plan.valor`)
- **And** both ventas MUST succeed atomically with DIFFERENT prorrateo amounts persisted in each `prod.factura_detalle` row (no cross-contamination).

**Scenario 3: Concurrent ventas on DIFFERENT plans — NOT serialized, both succeed**
- **Given** two vigentes `prod.tipo_subscripciones` rows `:p1` (plan "mensualidad") and `:p2` (plan "trimestral")
- **When** two concurrent TXs POST with `uuid_tipo_subscripcion=:p1` and `uuid_tipo_subscripcion=:p2` respectively
- **Then** both TXs MUST acquire their respective plan locks independently (no mutual blocking)
- **And** both ventas MUST succeed atomically in their own TXs without serialization on the plan row.

---

### REQ-OPS-085 — Lock ordering: plan lock before cliente lock (deadlock prevention)

**Source**: HU-F1.12 (DEC-VENTA-02) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
When `payload.uuid_cliente` is provided (existing cliente), the handler MUST acquire the plan lock (`SELECT FOR UPDATE` on `prod.tipo_subscripciones`) FIRST (Step 2), then the cliente lock (`SELECT FOR UPDATE` on `prod.clientes`) AFTER (Step 3a). When `payload.cliente` is provided (new cliente, no existing row), the cliente lock is not acquired because `close_and_insert(current_uuid=None, ...)` INSERTs a new row without a prior lock. The handler MUST NOT reverse the ordering (cliente first, then plan).

**Rationale**: A consistent global lock ordering prevents deadlocks under concurrent ventas. Without it, Plan A could hold the cliente lock waiting for the plan lock while Plan B holds the plan lock waiting for the cliente lock — a classic AB-BA deadlock that PostgreSQL would resolve by killing one TX with `deadlock_detected`. F1.10 KD-FE-01 established the "external lock (resolution row) before internal write" pattern; F1.12 mirrors it for plan-before-cliente.

**Source**: F1.10 REQ-OPS-064 (external-lock-first pattern); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 66-72 (state machine lock ordering precedent).

**Scenario 1: Plan A + existing cliente X, Plan B + existing cliente X — no deadlock**
- **Given** two concurrent ventas, both for the same existing cliente `:c` (uuid_cliente=:c):
  - TX-A: `uuid_tipo_subscripcion=:p1` (plan A), `uuid_cliente=:c`
  - TX-B: `uuid_tipo_subscripcion=:p2` (plan B), `uuid_cliente=:c`
- **When** both TXs reach Step 2 simultaneously
- **Then** TX-A MUST acquire the plan lock on `:p1` first
- **And** TX-B MUST acquire the plan lock on `:p2` (independent plan lock, no contention with TX-A)
- **And** TX-A MUST then acquire the cliente lock on `:c` (Step 3a) — no other TX holds `:c` yet
- **And** TX-B MUST wait at the cliente lock on `:c` until TX-A commits
- **And** after TX-A commits, TX-B MUST acquire `:c`, read the now-committed cliente state, and proceed to Step 4+ — no deadlock, no abort.

**Scenario 2: Reversed ordering — cliente first, then plan — REJECTED, would deadlock**
- **Given** a hypothetical handler that acquires `SELECT FOR UPDATE` on `prod.clientes` BEFORE `prod.tipo_subscripciones`
- **When** the two TXs from Scenario 1 run
- **Then** TX-A MUST acquire cliente lock `:c` first
- **And** TX-B MUST block at cliente lock `:c`
- **And** TX-A MUST then attempt to acquire plan lock `:p1` — succeeds independently
- **And** TX-A MUST commit and release `:c` and `:p1`
- **And** TX-B MUST acquire `:c`, then attempt to acquire `:p2` — also independent, no deadlock here
- **But** a third scenario (TX-A: plan A + cliente X; TX-B: plan B + cliente Y, where X and Y have a pending FK relationship via another join path) could exhibit a deadlock — the reversed ordering is REJECTED in DEC-VENTA-02 §6.2.

---

### REQ-OPS-086 — Placa format validation (V3 — `FORMATO_AUTO` / `FORMATO_MOTO`)

**Source**: HU-F1.12 (V3) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
Each placa string in `payload.placas` MUST match one of two regex patterns: `FORMATO_AUTO = re.compile(r"^[A-Z]{3}[0-9]{3}$")` for automobiles (e.g. `ABC123`) OR `FORMATO_MOTO = re.compile(r"^[A-Z]{3}[0-9]{2}[A-Z]$")` for motorcycles (e.g. `ABC12D`). Both patterns are defined in `backend/packages/parkos_core/src/parkos_core/repo/placa.py`. If any placa in the list fails both regexes, the handler MUST raise `HTTPException(422, {"error": "placa_formato_invalido", "placa": <offending_placa>}, headers=no_store_headers())`. The Pydantic schema MUST also enforce `Annotated[list[str], Field(min_length=1, max_length=2)]` on `placas` AND `Annotated[str, StringConstraints(min_length=1, max_length=16)]` on each placa string. Layered defense: Pydantic rejects at parse time (Layer 4) AND `repo.placa` rejects at handler time (Layer 3 via KD-VENTA-02 plan lock ordering).

**Rationale**: F1.6 introduced `FORMATO_AUTO` + `FORMATO_MOTO` as the canonical placa validators. The 422 mapping ensures the operator gets a typed error pointing at the offending placa. The `min_length=1, max_length=2` on the list enforces the plan's `cantidad_maxima_vehiculos` upper bound at the schema layer (defense in depth against V6).

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/placa.py` lines 12-25 (regex constants); `plan.md` lines 1010-1054 (V3 mandate); F1.6 REQ-OPS-038 (placa validators precedent).

**Scenario 1: `ABC123` matches AUTO format — OK**
- **Given** a payload with `placas: ["ABC123"]`
- **When** the handler Step 4 invokes `repo.placa.validar_formato_placa("ABC123")`
- **Then** the validator MUST return `True` (matches `FORMATO_AUTO`)
- **And** the handler MUST proceed to `repo.placa.detectar_tipo_vehiculo("ABC123")` for V5.

**Scenario 2: `ABC12D` matches MOTO format — OK**
- **Given** a payload with `placas: ["ABC12D"]`
- **When** the handler Step 4 invokes `repo.placa.validar_formato_placa("ABC12D")`
- **Then** the validator MUST return `True` (matches `FORMATO_MOTO`)
- **And** the handler MUST proceed to lookup-or-create the vehiculo with `uuid_tipo_vehiculo` corresponding to "moto".

**Scenario 3: `abc123` (lowercase) — 422 `placa_formato_invalido`**
- **Given** a payload with `placas: ["abc123"]`
- **When** the handler Step 4 invokes `repo.placa.validar_formato_placa("abc123")`
- **Then** the validator MUST return `False` (lowercase `a` fails both `[A-Z]{3}` patterns)
- **And** the handler MUST raise `HTTPException(422, {"error": "placa_formato_invalido", "placa": "abc123"}, headers=no_store_headers())`
- **And** NO `prod.vehiculos` row MUST be INSERTed (validation failure short-circuits before Step 4 INSERT).

---

### REQ-OPS-087 — Tipo vehículo compatible constraint (V5 — `mismo_tipo_vehiculo`)

**Source**: HU-F1.12 (V5) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
When the resolved `prod.tipo_subscripciones.mismo_tipo_vehiculo=true`, the handler MUST verify that ALL placas in `payload.placas` derive the SAME `uuid_tipo_vehiculo` via `repo.placa.detectar_tipo_vehiculo(session, placa)`. If the derived tipos differ (e.g. one placa matches AUTO format and another matches MOTO format, OR two placas match AUTO format but one resolves to a catalog variant like "taxi" while the other resolves to "particular"), the handler MUST raise `HTTPException(422, {"error": "tipo_vehiculo_incompatible", "tipos_encontrados": [<list of distinct tipos>]}, headers=no_store_headers())`. When `mismo_tipo_vehiculo=false`, mixed tipos are accepted and no V5 check applies.

**Rationale**: Some plans are tipo-restricted (e.g. "plan solo para automóviles"). A plan with `mismo_tipo_vehiculo=true` means ALL subscribed vehicles must share the same tipo. The 422 mapping gives the operator a typed error listing the distinct tipos found.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/placa.py` lines 27-65 (`detectar_tipo_vehiculo`); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 207 (`mismo_tipo_vehiculo` column); F1.6 REQ-OPS-038 (placa-to-tipo mapping precedent).

**Scenario 1: Plan with `mismo_tipo_vehiculo=true` + 2 placas of tipo "auto" — OK**
- **Given** a plan `:p` with `mismo_tipo_vehiculo=true`, `cantidad_maxima_vehiculos=2`
- **And** a payload with `placas: ["ABC123", "DEF456"]` (both match `FORMATO_AUTO`)
- **And** `repo.placa.detectar_tipo_vehiculo` returns the SAME `uuid_tipo_vehiculo` for both placas (catalog lookup against `prod.tipos_vehiculo`)
- **When** the handler Step 5 invokes `repo_venta.validar_placas_mismo_tipo_vehiculo(session, plan=:p, vehiculos=[<v1>, <v2>])`
- **Then** the validator MUST return without raising
- **And** the handler MUST proceed to Step 6 (V6 cantidad maxima check).

**Scenario 2: Plan with `mismo_tipo_vehiculo=true` + 1 auto + 1 moto — 422 `tipo_vehiculo_incompatible`**
- **Given** a plan `:p` with `mismo_tipo_vehiculo=true`, `cantidad_maxima_vehiculos=2`
- **And** a payload with `placas: ["ABC123", "XYZ12A"]` (AUTO + MOTO format)
- **When** the handler Step 5 invokes `validar_placas_mismo_tipo_vehiculo`
- **Then** the validator MUST detect that `detectar_tipo_vehiculo("ABC123")` returns `uuid_tipo_vehiculo=:t_auto` AND `detectar_tipo_vehiculo("XYZ12A")` returns `uuid_tipo_vehiculo=:t_moto` AND `:t_auto != :t_moto`
- **And** MUST raise `HTTPException(422, {"error": "tipo_vehiculo_incompatible", "tipos_encontrados": [":t_auto", ":t_moto"]}, headers=no_store_headers())`
- **And** NO `prod.subscripciones_cliente` row MUST be INSERTed (V5 failure short-circuits before Step 9).

**Scenario 3: Plan with `mismo_tipo_vehiculo=false` + mixed tipos — OK**
- **Given** a plan `:p` with `mismo_tipo_vehiculo=false`, `cantidad_maxima_vehiculos=2`
- **And** a payload with `placas: ["ABC123", "XYZ12A"]` (AUTO + MOTO format, distinct tipos)
- **When** the handler Step 5 invokes `validar_placas_mismo_tipo_vehiculo`
- **Then** the validator MUST return without raising (V5 check is SKIPPED because `mismo_tipo_vehiculo=false`)
- **And** the handler MUST proceed to Step 6.

---

### REQ-OPS-088 — Cantidad máxima vehículos constraint (V6 — `cantidad_maxima_vehiculos`)

**Source**: HU-F1.12 (V6) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
The handler MUST verify that `len(payload.placas) <= plan.cantidad_maxima_vehiculos`. If `len(payload.placas) > plan.cantidad_maxima_vehiculos`, the handler MUST raise `HTTPException(422, {"error": "cantidad_maxima_excedida", "cantidad_maxima_vehiculos": <plan.cantidad_maxima_vehiculos>, "placas_proporcionadas": <len(payload.placas)>}, headers=no_store_headers())`. The Pydantic schema MUST also enforce `Field(min_length=1, max_length=2)` on `placas` (Layer 4 defense in depth), so any payload with `len(placas) > 2` is rejected before reaching the handler body.

**Rationale**: Plans have a hard cap on how many vehicles a single subscription can cover (e.g. "plan mensual para 1 vehiculo" vs "plan familiar para 2 vehiculos"). The V6 check enforces the business contract. The Pydantic `max_length=2` is the hard upper bound across all plans (no plan in the catalog allows > 2 vehicles); the V6 helper adds the per-plan check.

**Source**: `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 206 (`cantidad_maxima_vehiculos` column); `plan.md` lines 1010-1054 (V6 mandate, 1-2 placas per plan).

**Scenario 1: Plan allows 1 vehiculo + 1 placa — OK**
- **Given** a plan `:p` with `cantidad_maxima_vehiculos=1`
- **And** a payload with `placas: ["ABC123"]`
- **When** the handler Step 6 invokes `validar_cantidad_maxima_vehiculos(session, plan=:p, n_placas=1)`
- **Then** the validator MUST return without raising (`1 <= 1`).

**Scenario 2: Plan allows 1 vehiculo + 2 placas — 422 `cantidad_maxima_excedida`**
- **Given** a plan `:p` with `cantidad_maxima_vehiculos=1`
- **And** a payload with `placas: ["ABC123", "DEF456"]`
- **When** the handler Step 6 invokes `validar_cantidad_maxima_vehiculos(session, plan=:p, n_placas=2)`
- **Then** the validator MUST detect that `2 > 1`
- **And** MUST raise `HTTPException(422, {"error": "cantidad_maxima_excedida", "cantidad_maxima_vehiculos": 1, "placas_proporcionadas": 2}, headers=no_store_headers())`
- **And** NO `prod.subscripcion_vehiculos` rows MUST be INSERTed (V6 failure short-circuits before Step 9b).

---

### REQ-OPS-089 — Placa duplicate detection (V4 — `suscripcion_duplicada_placa`)

**Source**: HU-F1.12 (V4) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
For each placa in `payload.placas`, the handler MUST call `repo.subscripcion_activa.resolve_active_subscription_for_exit(session, placa=<p>, uuid_sucursal=ctx.sucursal_uuid, fecha_salida=payload.fecha_inicio_cobertura)` (F1.7 reuse, return-truthy semantics — `found=True` when ANY active subscription exists at this branch for this placa). If the helper returns `found=True` for ANY placa, the handler MUST raise `HTTPException(422, {"error": "suscripcion_duplicada_placa", "placa": <offending_placa>, "uuid_sucursal": str(ctx.sucursal_uuid)}, headers=no_store_headers())`. The branch-pinned `WHERE uuid_sucursal == :this_branch` predicate (R22 defense-in-depth from F1.7) MUST be enforced — placas with active subscriptions at a DIFFERENT branch are accepted (cross-branch check NOT enforced in F1.12, deferred to a future cross-branch consistency HU).

**Rationale**: A placa cannot be subscribed twice at the same branch simultaneously (operator mis-clicks, fraudulent resubscription attempts). The reverse-direction reuse of `resolve_active_subscription_for_exit` is semantically equivalent to the F1.7 exit-check: "is there ANY active subscription for placa?" — F1.12 asks the same question before INSERTing the new subscription.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py` lines 93-141 (`resolve_active_subscription_for_exit`); F1.7 REQ-OPS-039 (R22 branch-pinned predicate precedent); `plan.md` lines 1010-1054 (V4 mandate).

**Scenario 1: Placa new to branch — OK**
- **Given** a placa `ABC123` with NO active `prod.subscripciones_cliente` row at `ctx.sucursal_uuid=:s`
- **And** a payload with `placas: ["ABC123"]`
- **When** the handler Step 7 invokes `resolve_active_subscription_for_exit(session, placa="ABC123", uuid_sucursal=:s, fecha_salida=<fecha_inicio_cobertura>)`
- **Then** the helper MUST return `found=False` (no active subscription at this branch)
- **And** the handler MUST proceed to Step 8 (A-09 prorrateo calc).

**Scenario 2: Placa has active subscription at SAME branch — 422 `suscripcion_duplicada_placa`**
- **Given** an existing `prod.subscripciones_cliente` row `:sc1` with `uuid_cliente=:c1`, `uuid_sucursal=:s`, `uuid_tipo_subscripcion=:p`, `fecha_vencimiento='2026-12-31'` (active)
- **And** a `prod.vehiculos` row `:v` with `placa='ABC123'`
- **And** a `prod.subscripcion_vehiculos` row linking `:sc1` to `:v`
- **And** a new payload with `placas: ["ABC123"]`, `uuid_tipo_subscripcion=:p_new`, `uuid_cliente=:c2` (different cliente, same placa)
- **When** the handler Step 7 invokes `resolve_active_subscription_for_exit(session, placa="ABC123", uuid_sucursal=:s, fecha_salida=<new.fecha_inicio_cobertura>)`
- **Then** the helper MUST return `found=True` with `uuid_subscripcion=:sc1`
- **And** the handler MUST raise `HTTPException(422, {"error": "suscripcion_duplicada_placa", "placa": "ABC123", "uuid_sucursal": ":s"}, headers=no_store_headers())`
- **And** NO NEW `prod.subscripciones_cliente` row MUST be INSERTed (V4 failure short-circuits before Step 9).

**Scenario 3: Placa has active subscription at DIFFERENT branch — OK (cross-branch check not enforced in F1.12)**
- **Given** an existing `prod.subscripciones_cliente` row `:sc1` with `uuid_sucursal=:s_other` (different from `ctx.sucursal_uuid=:s_this`)
- **And** a `prod.vehiculos` row `:v` with `placa='ABC123'`
- **And** a new payload with `placas: ["ABC123"]`, `uuid_tipo_subscripcion=:p_new`
- **When** the handler Step 7 invokes `resolve_active_subscription_for_exit(session, placa="ABC123", uuid_sucursal=:s_this, fecha_salida=<new.fecha_inicio_cobertura>)`
- **Then** the helper MUST return `found=False` (the `:s_other` subscription is filtered out by the `WHERE uuid_sucursal == :this_branch` predicate)
- **And** the handler MUST proceed to Step 8 (cross-branch check is out of F1.12 scope; the new subscription is recorded at `:s_this` independently).

---

### REQ-OPS-090 — A-09 prorrateo calc and persistence (DEC-VENTA-03)

**Source**: HU-F1.12 (DEC-VENTA-03) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
The handler MUST compute the A-09 prorrateo at Step 8 via `repo_venta.calcular_prorrateo(plan=plan, fecha_inicio_cobertura=payload.fecha_inicio_cobertura)`. The formula: `valor_dia = plan.valor / plan.duracion_dias` (when `plan.duracion_dias > 0`, else `PlanDuracionDiasInvalidoError`); `dias_restantes_mes = (<last day of fecha_inicio_cobertura.month> - fecha_inicio_cobertura.day)` (calendar month after `fecha_inicio_cobertura`); `monto_proporcional = valor_dia * dias_restantes_mes` IF `fecha_inicio_cobertura.day > 15` ELSE `None` (no prorrateo before day 16). When `cobrar_ahora=true`, the handler MUST persist `monto_proporcional` in `prod.factura_detalle.valor_unitario` AND `prod.factura_detalle.subtotal` of the SINGLE detail row with `concepto='subscripcion_mensual_prorrateada'`, `cantidad=1`. When `cobrar_ahora=false`, the handler MUST NOT persist prorrateo anywhere — the prorrateo amount is returned in the response body's `monto_prorrateado` field only when `monto_proporcional is not None`, else `null`.

**Rationale**: plan.md line 460 explicitly: "no hay columna para el monto prorrateado en `subscripciones_cliente`. Se calcula al momento de la venta y el resultado sí queda persistido, pero en `factura_detalle.valor_unitario`/`subtotal` — no en la tabla de suscripción misma, que no necesita columna nueva." The decay rule (`day > 15`) is the plan.md trigger condition (line 1053 T2).

**Source**: `plan.md` line 460 (A-09 spec), line 1053 (T2 day > 15 trigger); `backend/packages/parkos_core/src/parkos_core/repo/factura.py::crear_factura_detalle_bulk` (F1.9 helper, reused with `concepto='subscripcion_mensual_prorrateada'`); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 483-496 (`subscripciones_cliente` has NO prorrateo column by design).

**Scenario 1: `fecha_inicio_cobertura.day = 20` + `cobrar_ahora=true` — prorrateo persisted in `factura_detalle`**
- **Given** a plan `:p` with `valor=30000`, `duracion_dias=30`
- **And** a payload with `fecha_inicio_cobertura='2026-09-20'`, `cobrar_ahora=true`
- **When** the handler Step 8 invokes `calcular_prorrateo(plan=:p, fecha_inicio_cobertura='2026-09-20')`
- **Then** the helper MUST compute `valor_dia = 30000 / 30 = 1000.0` AND `dias_restantes_mes = (30 - 20) = 10` (September has 30 days)
- **And** MUST return `monto_proporcional = 1000.0 * 10 = 10000.0`
- **And** Step 8a (`_factura_sub_chain`) MUST persist `prod.factura_detalle` row with `concepto='subscripcion_mensual_prorrateada'`, `valor_unitario=10000.0`, `cantidad=1`, `subtotal=10000.0`
- **And** the response MUST include `monto_prorrateado=10000.0`.

**Scenario 2: `fecha_inicio_cobertura.day = 10` — no prorrateo, full `plan.valor` charged**
- **Given** a plan `:p` with `valor=30000`, `duracion_dias=30`
- **And** a payload with `fecha_inicio_cobertura='2026-09-10'`, `cobrar_ahora=true`
- **When** the handler Step 8 invokes `calcular_prorrateo(plan=:p, fecha_inicio_cobertura='2026-09-10')`
- **Then** the helper MUST detect `day=10` is NOT `> 15` and MUST return `monto_proporcional = None`
- **And** Step 8a MUST persist `prod.factura_detalle` row with `concepto='subscripcion_mensual'`, `valor_unitario=30000.0`, `cantidad=1`, `subtotal=30000.0` (full `plan.valor`, no prorrateo)
- **And** the response MUST include `monto_prorrateado=null` (no prorrateo applied).

**Scenario 3: `fecha_inicio_cobertura.day = 20` + `cobrar_ahora=false` — `monto_prorrateado` in response body only, no persistence**
- **Given** a plan `:p` with `valor=30000`, `duracion_dias=30`
- **And** a payload with `fecha_inicio_cobertura='2026-09-20'`, `cobrar_ahora=false` (deferred billing)
- **When** the handler Step 8 invokes `calcular_prorrateo(plan=:p, fecha_inicio_cobertura='2026-09-20')`
- **Then** the helper MUST return `monto_proporcional = 10000.0` (same calc as Scenario 1)
- **And** Step 8a MUST be SKIPPED (no `_factura_sub_chain` call because `cobrar_ahora=false`)
- **And** NO `prod.factura_detalle` row MUST be INSERTed with prorrateo (the prorrateo is NOT persisted when not charging)
- **And** the response MUST include `monto_prorrateado=10000.0` (informational, returned for the operator's records but NOT in the DB)
- **And** `uuid_factura` MUST be `null` in the response (no factura was created).

---

### REQ-OPS-XR5 — Defense in depth: 5 layers + single-commit AST walk

**Source**: HU-F1.12 (KD-VENTA-01 + KD-VENTA-02 + DEC-VENTA-05 + DEC-VENTA-06) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
F1.12 MUST apply the F1.10 + F1.11 defense-in-depth pattern (5 layers), each independently testable, with failure of any one layer contained by the other four:
- **Layer 1 — KD-3 issuer chain + permission gate**: `_venta_suscripcion_issuer_dep = requires_issuer("operador-", "admin-")` (FastAPI dependency) + permission `gestionar_clientes` inherited from the existing `clientes.py` factory mount via `router.include_router(...)` (DEC-VENTA-05).
- **Layer 2 — Tenant scope post-V1**: After resolving the target sucursal from `ctx.issuer_prefix`, if `ctx.issuer_prefix == "operador-"` and `ctx.sucursal_uuid != target_sucursal`, the handler MUST return `403 tenant_scope_violation` with `Cache-Control: no-store`. Admin (`admin-` prefix) bypasses.
- **Layer 3 — KD-VENTA-01 single-commit + KD-VENTA-02 plan lock**: AST walk `tests/static/test_venta_handler_single_commit.py` enforces EXACTLY ONE `await session.commit()` in the handler body. `SELECT FOR UPDATE` on `prod.tipo_subscripciones` (Step 2) precedes all other locks (REQ-OPS-084).
- **Layer 4 — Pydantic `extra='forbid'` + placa constraints + NIT DV validator**: `VentaSuscripcionCreate(_Base)` inherits `extra='forbid'` from `schemas/common.py` (blocks client smuggling of `uuid_sucursal`, `vigente_desde`, `estado`, `created_at`, `created_by`, `monto_prorrateado`, `valor_dia`, `dias_restantes_mes` — all server-derived). `placas: Annotated[list[str], Field(min_length=1, max_length=2)]` + per-placa `StringConstraints(min_length=1, max_length=16)` (REQ-OPS-086). NIT DV validator via `ClientesCreate._validar_nit_dv` (F1.9 REQ-OPS-058 reuse, DEC-VENTA-07 — `dv` is validated by Pydantic then discarded before INSERT).
- **Layer 5 — Handler 422/409/404 mapping + `Cache-Control: no-store`**: Every response (201 + 4xx + 5xx) carries `Cache-Control: no-store`. Success: `apply_no_store_header(response)`. Error: `HTTPException(headers=no_store_headers())`. Typed exceptions (`TipoSubscripcionNoVigenteError` 409, `TipoSubscripcionNoEncontradoError` 404, `SubscripcionDuplicadaPlacaError` 422, `TipoVehiculoIncompatibleError` 422, `CantidadMaximaExcedidaError` 422, `PlanDuracionDiasInvalidoError` 422, `PlacaFormatoInvalidoError` 422, `TipoVehiculoInvalidoError` 422, `NitInvalidoError` 422, `ClienteNoEncontradoError` 404, `TenantScopeViolationError` 403, `PermissionDeniedError` 403, `IdempotencyKeyRequiredError` 400, `IdempotencyConflictError` 409) map to the typed bodies documented in `schemas/clientes.py` §9.2. The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

**Rationale**: Defense in depth against accidental drift in any single layer. The AST walk is the F1.10 XR1 + F1.11 XR4 mirror for F1.12. The 5-layer pattern is the canonical backend invariant for multi-table atomic writes (F1.9 KD-FACT-01, F1.10 KD-FE-01, F1.11 KD-TKT-01).

**Source**: F1.9 REQ-OPS-058 (NIT DV validator precedent); F1.10 REQ-OPS-XR1 (single-commit AST walk precedent); F1.11 REQ-OPS-XR4 (insert-only AST walk precedent); `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header`); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'`).

**Scenario 1: operador with `gestionar_clientes` + own branch — OK**
- **Given** an operador role granted `gestionar_clientes` permission via `prod.permisos_usuario`
- **And** `ctx.sucursal_uuid=:s` matching the operator's branch
- **And** a valid `VentaSuscripcionCreate` payload
- **When** the operador POSTs `/api/v1/clientes/venta-suscripcion`
- **Then** the request MUST pass Layer 1 (KD-3 issuer chain + permission gate) AND Layer 2 (tenant scope) AND reach the handler body
- **And** MUST return `201 Created` on the happy path.

**Scenario 2: operador with `gestionar_clientes` + DIFFERENT branch — 403 `tenant_scope_violation`**
- **Given** an operador role granted `gestionar_clientes` permission
- **And** `ctx.sucursal_uuid=:s_other` (operator's branch is `:s_other`, but the request's target sucursal is `:s_target != :s_other`)
- **When** the operador POSTs `/api/v1/clientes/venta-suscripcion`
- **Then** Layer 2 MUST reject with `403 Forbidden` and body `{"error": "tenant_scope_violation"}` and `Cache-Control: no-store`
- **And** NO DB writes MUST occur (handler body unreachable).

**Scenario 3: operador WITHOUT `gestionar_clientes` — 403 `permission_denied`**
- **Given** an operador role WITHOUT `gestionar_clientes` permission (e.g. role "operador-lectura")
- **When** the operador POSTs `/api/v1/clientes/venta-suscripcion`
- **Then** Layer 1 MUST reject with `403 Forbidden` and body `{"error": "permission_denied"}` and `Cache-Control: no-store`
- **And** Layer 2 (tenant scope) MUST NOT be evaluated (Layer 1 short-circuits first).

**Scenario 4: All responses (201 + 4xx + 5xx) carry `Cache-Control: no-store`**
- **Given** any response from `POST /api/v1/clientes/venta-suscripcion` (success or failure)
- **When** the response is emitted
- **Then** the `Cache-Control: no-store` header MUST be present on `201 Created`
- **And** MUST be present on `400 idempotency_key_required` / `403 tenant_scope_violation` / `403 permission_denied` / `404 tipo_subscripcion_no_encontrado` / `404 cliente_no_encontrado` / `409 tipo_subscripcion_no_vigente` / `409 idempotency_conflict` / `422 placa_formato_invalido` / `422 tipo_vehiculo_incompatible` / `422 cantidad_maxima_excedida` / `422 plan_duracion_dias_invalido` / `422 nit_dv_invalido` / `422 suscripcion_duplicada_placa` / `500 iva_no_configurado`
- **And** MUST be present on any uncaught 5xx (defense-in-depth).

### REQ-OPS-091 — POST `/api/v1/caja/arqueo` single-commit atomicity (KD-ARQUEO-01 + DEC-ARQUEO-01)

**Source**: HU-F1.13 (KD-ARQUEO-01 + DEC-ARQUEO-01) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
The handler `post_arqueo` in `api/v1/caja_arqueo.py` MUST execute exactly ONE `await session.commit()` at the END of the request body (Step 12 of the 12-step chain), covering all 4 table families in a single TX: (1) one `prod.arqueo` [A] INSERT via `repo/append_only.append_event` (KD-ARQUEO-02), (2) N `prod.sesion` [L-S] UPDATEs when `tipo_arqueo.codigo == 'cierre_dia'` via `repo/session_cycle.close_session_with_log` per row (KD-ARQUEO-03 + `ls_session_guard` trigger), (3) one conditional `prod.alerta` [L-W] INSERT initial via `repo/workflow.append_transition` when `|diferencia_efectivo| > tolerancia_efectivo OR |diferencia_datafono| > tolerancia_datafono` (KD-ARQUEO-04 + KD-ARQUEO-05), (4) N+1 `prod.log_transaccional` [A] co-INSERTs auto-emitted by the helpers. The handler MUST NOT use `session.begin_nested()` or `SAVEPOINT`. All helper functions (`insertar_arqueo`, `cerrar_sesiones_del_dia_bulk`, `insertar_alerta_descuadre_critico`) MUST stay commit-free — they `session.add()` + `await session.flush()` only. On any helper raise, the entire TX MUST roll back (no SAVEPOINT partial commits). The response MUST return `201 Created` with `Cache-Control: no-store`.

**Rationale**: Cross-domain atomicity for the `arqueo + alerta` pair is the entire business requirement — no arqueo without its alerta when `descuadre_critico` is true. A SAVEPOINT strategy would partially commit, leaving orphan arqueos without the matched alerta. The `ls_session_guard` per-row DB trigger mandates log-first ordering for every sesion UPDATE — the per-row `(log INSERT + flush + UPDATE)` pattern in `close_session_with_log` is the only allowed path inside the outer TX. The single-commit invariant becomes the AST walk contract `tests/static/test_arqueo_handler_single_commit.py` (mirror of `tests/static/test_venta_handler_single_commit.py`).

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/append_only.py` lines 64-124 (`append_event` commit-free contract); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 110-237 (`append_transition` commit-free); `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py` lines 274-349 (`close_session_with_log` + `ls_session_guard` trigger lines 286-289); F1.11 KD-TKT-01 + F1.12 KD-VENTA-01 (single-commit precedents).

**Scenario 1: Happy path — all writes succeed in 1 commit, all rows visible post-response**
- **Given** an `operador-` issuer with `realizar_arqueo` permission and `ctx.sucursal_uuid=:s`
- **And** a vigente `prod.tipo_arqueo` row with `codigo='cierre_turno'`, `vigente_hasta IS NULL`
- **And** a vigente `prod.sesion` row `:ses` with `uuid_sucursal=:s`, `estado='abierta'`, `timestamp_cierre IS NULL`
- **And** a vigente `prod.configuracion_tolerancias` row with `uuid_sucursal=:s`, `tolerancia_efectivo=100`, `tolerancia_datafono=200`
- **And** an `ArqueoCreateV2` payload with `uuid_tipo_arqueo=<uuid for cierre_turno>`, `uuid_sesion=<:ses>`, `valor_efectivo_reportado=148000`, `valor_datafono_reportado=320000`, `justificacion=null` (sin diferencia)
- **When** the handler reaches Step 12 and calls `await session.commit()` exactly once
- **Then** exactly one `prod.arqueo` row MUST be visible (uuid matches response)
- **And** exactly one `prod.log_transaccional` row MUST be visible (auto-co-inserted by `append_event`)
- **And** `prod.sesion` MUST be UNCHANGED (UPDATE not required for `cierre_turno` without descuadre; Step 9 only runs on `cierre_dia`)
- **And** NO `prod.alerta` row MUST be visible (descuadre_critico did NOT trigger — diferencia == 0)
- **And** the response MUST be `201 Created` with `ArqueoReadForHandler` carrying `alerta_generada=false`, `alerta_uuid=null` + `Cache-Control: no-store`.

**Scenario 2: Mid-flight failure — any helper raise rolls back the entire TX**
- **Given** the same valid payload but Step 9 (cierre_dia path) raises `SesionNoEncontradaError` because the sesion was deleted mid-flight by a concurrent TX
- **When** the handler catches the exception and returns `404 sesion_no_encontrada`
- **Then** `await session.commit()` MUST NOT be called (KD-ARQUEO-01)
- **And** the entire TX MUST be rolled back — ZERO `prod.arqueo`, ZERO `prod.log_transaccional` rows MUST exist after the rollback
- **And** the response MUST carry `Cache-Control: no-store`.

**Scenario 3: AST walk — handler source contains EXACTLY ONE `await session.commit()` call**
- **Given** the source file `api/v1/caja_arqueo.py` containing `post_arqueo` handler
- **When** `tests/static/test_arqueo_handler_single_commit.py` runs an `ast.walk()` over the handler body
- **Then** the AST walk MUST assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(n.value.func, 'attr', '') == 'commit']) == 1` (exactly one `await session.commit()` call)
- **And** MUST assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(getattr(n.value, 'func', None), 'attr', '') == 'begin_nested']) == 0` (no SAVEPOINT)
- **And** MUST assert NO occurrence of the literal string `"SAVEPOINT"` in the handler body (defense in depth).

---

### REQ-OPS-092 — `cierre_dia` mass sesion UPDATE through `session_cycle` helper only (KD-ARQUEO-03 + DEC-ARQUEO-03)

**Source**: HU-F1.13 (KD-ARQUEO-03 + DEC-ARQUEO-03) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
For `tipo_arqueo.codigo == 'cierre_dia'` with `uuid_sesion=null` and N open sesiones at `ctx.sucursal_uuid`, the handler MUST execute Step 9 by iterating per open sesion and calling `repo.session_cycle.close_session_with_log(session, uuid_sesion=<uuid>, log_tx=True)` for each one. The handler MUST NOT execute raw `session.execute(update(Sesion))` or `session.execute(text("UPDATE prod.sesion ..."))` — the `ls_session_guard` DB trigger (per `repo/session_cycle.py:286-289`) REJECTS direct UPDATE without co-transactional `log_transaccional` row. Each `close_session_with_log` iteration MUST perform `(log_transaccional INSERT + flush + sesion UPDATE estado='cerrada', timestamp_cierre=...)` inside the outer TX. The `ls_session_guard` DB trigger MUST NOT reject any iteration. The AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` MUST PASS (NEW walk — no precedent; mirrors `test_venta_handler_no_raw_dml.py` shape).

**Rationale**: `ls_session_guard` per-row DB trigger mandates log-first ordering for every sesion UPDATE — bulk UPDATE without per-row log would trigger the rejection. The `close_session_with_log` helper is the only allowed path. The new AST walk locks the contract at static-parse time (defense in depth against accidental drift).

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py` lines 274-349 (`close_session_with_log` + `ls_session_guard` reference lines 286-289); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (trigger definition); `tests/static/test_no_raw_dml_on_ls_tables.py` (F1.5 PR5-016 precedent for [L-S] AST walks).

**Scenario 1: `cierre_dia` + 3 open sesiones — all 3 closed via `close_session_with_log`**
- **Given** a `cierre_dia` `ArqueoCreateV2` payload with `uuid_tipo_arqueo=<uuid for cierre_dia>`, `uuid_sesion=null`
- **And** 3 open `prod.sesion` rows `:ses1`, `:ses2`, `:ses3` at `ctx.sucursal_uuid=:s` with `estado='abierta'`, `timestamp_cierre IS NULL`
- **When** the handler Step 9 invokes `repo_arqueo.cerrar_sesiones_del_dia_bulk(session, target_sucursal=:s, fecha=<today>)`
- **Then** the helper MUST iterate per open sesion and call `close_session_with_log(session, uuid_sesion=<each>, log_tx=True)` exactly 3 times
- **And** each iteration MUST emit one `prod.log_transaccional` row + one `prod.sesion` UPDATE inside the outer TX
- **And** the final state MUST be `prod.sesion[ses1].estado='cerrada'`, `prod.sesion[ses2].estado='cerrada'`, `prod.sesion[ses3].estado='cerrada'` with `timestamp_cierre` set to NOW()
- **And** NO `prod.sesion` row MUST remain in `estado='abierta'` at `ctx.sucursal_uuid=:s` for the day after the commit.

**Scenario 2: `cierre_dia` + 2 cerradas + 1 abierta — only the open sesion is closed**
- **Given** 3 `prod.sesion` rows where `:ses1` and `:ses2` already have `estado='cerrada'`, `timestamp_cierre=<yesterday>`, and `:ses3` has `estado='abierta'`, `timestamp_cierre IS NULL`
- **And** a `cierre_dia` payload
- **When** the handler Step 9 invokes `cerrar_sesiones_del_dia_bulk`
- **Then** the helper MUST iterate over the single open sesion `:ses3` only
- **And** MUST call `close_session_with_log(session, uuid_sesion=<:ses3>, log_tx=True)` exactly 1 time (NOT 3)
- **And** `:ses1` and `:ses2` MUST remain UNCHANGED (no UPDATE applied, no log row emitted).

**Scenario 3: AST walk — `post_arqueo` for `cierre_dia` calls `close_session_with_log`, NOT raw UPDATE**
- **Given** the source file `api/v1/caja_arqueo.py` containing `post_arqueo` handler
- **When** `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` runs
- **Then** the AST walk MUST detect at least one call to `close_session_with_log(...)` inside the `if tipo_arqueo.codigo == 'cierre_dia':` branch (KD-ARQUEO-03)
- **And** MUST assert NO occurrence of `update(Sesion)` or `text("UPDATE prod.sesion ...")` or `session.execute(update(Sesion))` anywhere in the handler body
- **And** MUST assert that within the `cierre_dia` branch the literal string `"UPDATE prod.sesion"` does NOT appear.

---

### REQ-OPS-093 — Tolerancia evaluated as ABSOLUTE monto (KD-ARQUEO-04 + DEC-ARQUEO-04)

**Source**: HU-F1.13 (KD-ARQUEO-04 + DEC-ARQUEO-04) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
The handler MUST evaluate `es_descuadre_critico(diferencia_efectivo, diferencia_datafono, tolerancia_efectivo, tolerancia_datafono)` by computing `abs(diferencia_efectivo) > tolerancia_efectivo OR abs(diferencia_datafono) > tolerancia_datafono`. The comparison MUST use the **absolute monto**, NOT a percentage. The `descuadre_pct` field (computed as `((diferencia_efectivo + diferencia_datafono) / (esperado_efectivo + esperado_datafono)) * 100` when esperado > 0, else `None`) MUST be returned in the response body as **informational only** and MUST NOT participate in the alerta decision. plan.md line 1065 mandates: "tolerancia = monto absoluto (no porcentaje)". The Fase 10 reconciliation may revise to percentage — out of F1.13 scope.

**Rationale**: plan.md line 1065 + line 1093 explicit mandate. Fase 10 owns the percentage reconciliation. Mixing the two would silently accept descuadres > tolerance (R5). The `descuadre_pct` field is informational for the operator's UX (visualization) but the alerta decision uses absolute monto per the F1.13 contract.

**Source**: `plan.md` line 1065 (tolerancia = monto absoluto), line 1093 (4 mandated unit tests); `backend/packages/parkos_core/src/parkos_core/repo/arqueo.py::es_descuadre_critico` (NEW helper, pure function); `backend/packages/parkos_core/src/parkos_core/schemas/caja.py::ArqueoReadForHandler.descuadre_pct` (informational marker).

**Scenario 1: `|diferencia| < tolerancia` — NO descuadre alerta**
- **Given** a sesion with `valor_efectivo_esperado=100000` and `valor_efectivo_reportado=100050`
- **And** `tolerancia_efectivo=100`, `tolerancia_datafono=200`
- **When** the handler Step 7 invokes `es_descuadre_critico(diferencia_efectivo=50, diferencia_datafono=0, tolerancia_efectivo=100, tolerancia_datafono=200)`
- **Then** the helper MUST compute `abs(50)=50 > 100 → False` AND `abs(0)=0 > 200 → False` → return `False`
- **And** the handler MUST NOT call `insertar_alerta_descuadre_critico` (Step 10 SKIPPED)
- **And** the response MUST include `alerta_generada=false`, `alerta_uuid=null` AND `descuadre_pct=0.05` (informational only).

**Scenario 2: `|diferencia| > tolerancia` — alerta generated**
- **Given** the same sesion but `valor_efectivo_reportado=100150`
- **And** `tolerancia_efectivo=100`
- **When** the handler Step 7 invokes `es_descuadre_critico(diferencia_efectivo=150, diferencia_datafono=0, tolerancia_efectivo=100, tolerancia_datafono=200)`
- **Then** the helper MUST compute `abs(150)=150 > 100 → True` → return `True`
- **And** Step 10 MUST call `insertar_alerta_descuadre_critico` via `append_transition` (REQ-OPS-095)
- **And** the response MUST include `alerta_generada=true`, `alerta_uuid=<uuid>`.

**Scenario 3: `|diferencia| == tolerancia` — boundary, NO alerta**
- **Given** `valor_efectivo_reportado=100100`, `tolerancia_efectivo=100` → `|diferencia_efectivo|=100`
- **When** the handler Step 7 invokes `es_descuadre_critico(diferencia_efectivo=100, diferencia_datafono=0, tolerancia_efectivo=100, tolerancia_datafono=200)`
- **Then** the helper MUST compute `abs(100)=100 > 100 → False` (strict inequality)
- **And** the handler MUST NOT generate alerta (`>` not `>=`)
- **And** `descuadre_pct` MUST appear in response body (informational, not decision-driving).

---

### REQ-OPS-094 — `justificacion` REQUIRED on `cierre_turno`/`cierre_dia` when diferencia != 0 (DEC-ARQUEO-07)

**Source**: HU-F1.13 (DEC-ARQUEO-07) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
The handler MUST validate the request body at Step 6: when `tipo_arqueo.codigo in ('cierre_turno', 'cierre_dia')` AND (`diferencia_efectivo != 0` OR `diferencia_datafono != 0`) AND `payload.justificacion is None` (or empty string), the handler MUST raise `HTTPException(400, {"error": "justificacion_requerida"}, headers=no_store_headers())`. When `tipo_arqueo.codigo == 'auditoria'` with diferencia != 0, the handler MUST accept the request without `justificacion` (advertencia only — not bloqueante per plan.md lines 1086-1091 + line 2476 mandate).

**Rationale**: plan.md line 2476 asymmetry. `auditoria` is an internal control step (advertencia only); `cierre_turno`/`cierre_dia` are operational commitments (justification required when there is a delta). The 400 mapping gives the operator a typed error so the UI can prompt for the missing field.

**Source**: `plan.md` lines 1086-1091 + line 2476 (justification asymmetry mandate); `backend/packages/parkos_core/src/parkos_core/schemas/caja.py::ArqueoCreateV2.justificacion` (`str | None = None`); `backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py::post_arqueo` Step 6.

**Scenario 1: `cierre_turno` + diferencia != 0 + justificacion=null → 400 `justificacion_requerida`**
- **Given** a `cierre_turno` `ArqueoCreateV2` with `valor_efectivo_reportado=148050` (esperado=148000, diferencia_efectivo=50, != 0)
- **And** `justificacion=null` (omitted from payload)
- **When** the handler Step 6 validates the body
- **Then** it MUST raise `HTTPException(400, {"error": "justificacion_requerida"}, headers=no_store_headers())`
- **And** the response MUST carry `Cache-Control: no-store`
- **And** NO `prod.arqueo` row MUST be INSERTed (Step 6 short-circuits before Step 8)
- **And** NO `prod.alerta` row MUST be INSERTed.

**Scenario 2: `auditoria` + diferencia != 0 + justificacion=null → ACCEPTED (advertencia)**
- **Given** an `auditoria` `ArqueoCreateV2` with `valor_efectivo_reportado=148050` (diferencia_efectivo=50)
- **And** `justificacion=null`
- **When** the handler Step 6 validates the body
- **Then** it MUST NOT raise (DEC-ARQUEO-07 asymmetry — auditoria is advertencia only)
- **And** the handler MUST proceed to Step 7 (es_descuadre_critico) → Step 8 (INSERT arqueo)
- **And** the response MUST be `201 Created` with `ArqueoReadForHandler` carrying `alerta_generada` per the tolerance check.

**Scenario 3: `cierre_dia` + diferencia != 0 + justificacion=null → 400 `justificacion_requerida`**
- **Given** a `cierre_dia` `ArqueoCreateV2` with the aggregated day having diferencia != 0
- **And** `justificacion=null`
- **When** the handler Step 6 validates the body
- **Then** it MUST raise `HTTPException(400, {"error": "justificacion_requerida"}, headers=no_store_headers())`
- **And** NO `prod.sesion` row MUST be UPDATEd (Step 6 short-circuits before Step 9).

---

### REQ-OPS-095 — `alerta 'descuadre_critico'` INSERTed conditionally via `append_transition` (KD-ARQUEO-05 + DEC-ARQUEO-05)

**Source**: HU-F1.13 (KD-ARQUEO-05 + DEC-ARQUEO-05) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
When Step 7 evaluates `es_descuadre_critico == True`, the handler MUST call `repo_arqueo.insertar_alerta_descuadre_critico(session, actor_uuid=ctx.actor_uuid, uuid_arqueo=<uuid_arqueo>, uuid_sucursal=target_sucursal, diferencia_efectivo=<diff_e>, diferencia_datafono=<diff_d>, payload_json={...})` at Step 10. The helper MUST internally call `repo.workflow.append_transition(session, tabla='alerta', tipo_alerta='descuadre_critico', estado_inicial='activa', ...)` — NOT raw `session.execute(insert(Alerta))`. The `append_transition` helper MUST validate `tipo_alerta='descuadre_critico'` against `prod.alert_types` (MIGRATION 0031 Op 2 seeded this entry idempotently). The `alerta_generada=true` + `alerta_uuid=<uuid>` MUST appear in the `201 Created` response body. The AST walk `tests/static/test_arqueo_handler_no_raw_dml.py` MUST NOT detect raw INSERT/UPDATE on `prod.alerta`.

**Rationale**: `WorkflowBase` provides DB-layer state machine integrity (initial state `{activa -> descartada | resuelta}` only). `append_transition` centralizes the audit/sync columns. Raw INSERT bypasses the state machine guard and the audit/sync column computation. MIGRATION 0031 Op 2 seeds `descuadre_critico` into `prod.alert_types` with `ON CONFLICT DO NOTHING` (idempotent — F1.14's planned seed becomes no-op).

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 110-237 (`append_transition` + `STATE_MACHINES['alerta']` lines 85-90); `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` (registry + `alert_types_inmutable` trigger lines 21-22); `backend/packages/parkos_core/migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` (NEW, MIGRATION 0031 Op 2 seeds `descuadre_critico`).

**Scenario 1: `|diferencia_efectivo| > tolerancia_efectivo` → alerta INSERTed via `append_transition`**
- **Given** Step 7 evaluated `es_descuadre_critico == True` (REQ-OPS-093 Scenario 2)
- **And** `prod.alert_types` has the row `('descuadre_critico', 'critical')` seeded by MIGRATION 0031 Op 2
- **When** the handler Step 10 invokes `insertar_alerta_descuadre_critico(...)`
- **Then** the helper MUST call `repo.workflow.append_transition(session, tabla='alerta', tipo_alerta='descuadre_critico', estado_inicial='activa', severity='critical', uuid_recurso_origen=<uuid_arqueo>, tipo_recurso_origen='arqueo', payload_json={...})`
- **And** exactly one `prod.alerta` row MUST be visible after the commit (uuid matches response `alerta_uuid`)
- **And** the response MUST include `alerta_generada=true` + `alerta_uuid=<uuid>`.

**Scenario 2: `|diferencia| <= tolerancia` → NO alerta INSERTed**
- **Given** Step 7 evaluated `es_descuadre_critico == False` (REQ-OPS-093 Scenario 1)
- **When** the handler Step 10 checks `if es_critico:`
- **Then** the handler MUST NOT call `insertar_alerta_descuadre_critico` (the if-branch is SKIPPED)
- **And** ZERO `prod.alerta` rows MUST exist after the commit
- **And** the response MUST include `alerta_generada=false` + `alerta_uuid=null`.

**Scenario 3: AST walk — no raw INSERT/UPDATE on `prod.alerta` in handler body**
- **Given** the source file `api/v1/caja_arqueo.py` containing `post_arqueo`
- **When** `tests/static/test_arqueo_handler_no_raw_dml.py` runs
- **Then** the AST walk MUST assert NO occurrence of `session.execute(insert(Alerta))` or `session.execute(text("INSERT INTO prod.alerta ..."))` or `update(Alerta)` in the handler body
- **And** MUST assert that `append_transition` (or a helper wrapping it) is the ONLY path that inserts into `prod.alerta`.

---

### REQ-OPS-096 — Sesion MUST be abierta for `cierre_turno` (KD-ARQUEO-06)

**Source**: HU-F1.13 (KD-ARQUEO-06) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
When `tipo_arqueo.codigo == 'cierre_turno'` (or `'auditoria'`) AND `payload.uuid_sesion is not None`, the handler MUST validate at Step 4 that the referenced `prod.sesion` row has `estado='abierta'` AND `timestamp_cierre IS NULL`. The handler MUST call `repo_arqueo.validar_sesion_abierta_para_arqueo(session, uuid_sesion=<uuid>, target_sucursal=ctx.sucursal_uuid)` which returns the sesion object when open OR raises `SesionYaCerradaError` when `timestamp_cierre IS NOT NULL`. The handler MUST map `SesionYaCerradaError` to `HTTPException(409, {"error": "sesion_ya_cerrada", "uuid_sesion": str(payload.uuid_sesion)}, headers=no_store_headers())`. For `cierre_dia`, the sesion validation is SKIPPED (the request carries `uuid_sesion=null` per DEC-ARQUEO-03 — the helper iterates ALL open sesiones for the day). The AST walk MUST enforce that `validar_sesion_abierta_para_arqueo` is called BEFORE any INSERT into `prod.arqueo`.

**Rationale**: A sesion that has already been closed (`timestamp_cierre IS NOT NULL`) cannot be closed or audited again — the arqueo would create a duplicate or contradictory record. The 409 mapping gives the operator a typed error pointing at the offending sesion.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py::validar_sesion_abierta` (F1.3/F1.5 precedent, reused); `backend/packages/parkos_core/src/parkos_core/repo/arqueo.py::validar_sesion_abierta_para_arqueo` (NEW wrapper, raises `SesionYaCerradaError`).

**Scenario 1: `cierre_turno` + sesion abierta → OK**
- **Given** a `cierre_turno` `ArqueoCreateV2` with `uuid_sesion=<:ses>`
- **And** `prod.sesion[:ses]` has `estado='abierta'`, `timestamp_cierre IS NULL`
- **When** the handler Step 4 invokes `validar_sesion_abierta_para_arqueo(session, uuid_sesion=<:ses>, target_sucursal=:s)`
- **Then** the helper MUST return the sesion object (not raise)
- **And** the handler MUST proceed to Step 5 (compute esperado + diferencia).

**Scenario 2: `cierre_turno` + sesion already cerrada → 409 `sesion_ya_cerrada`**
- **Given** `prod.sesion[:ses]` has `estado='cerrada'`, `timestamp_cierre='2026-09-14T18:30:00Z'`
- **And** a `cierre_turno` `ArqueoCreateV2` with `uuid_sesion=<:ses>`
- **When** the handler Step 4 invokes `validar_sesion_abierta_para_arqueo`
- **Then** the helper MUST raise `SesionYaCerradaError(uuid_sesion=<:ses>)`
- **And** the handler MUST translate to `HTTPException(409, {"error": "sesion_ya_cerrada", "uuid_sesion": "<:ses>"}, headers=no_store_headers())`
- **And** NO `prod.arqueo` row MUST be INSERTed (Step 4 short-circuits before Step 8).

**Scenario 3: `auditoria` + sesion abierta → OK (auditoria also requires sesion validate)**
- **Given** an `auditoria` `ArqueoCreateV2` with `uuid_sesion=<:ses>`
- **And** `prod.sesion[:ses]` has `estado='abierta'`
- **When** the handler Step 4 invokes `validar_sesion_abierta_para_arqueo`
- **Then** the helper MUST return the sesion object (auditoria is an internal control — applies to the open sesion too)
- **And** the handler MUST proceed to Step 5.

---

### REQ-OPS-097 — GET `/api/v1/caja/arqueo/resumen` JOIN sesion + `factura_pagos` SUM (KD-ARQUEO-07 + DEC-ARQUEO-10)

**Source**: HU-F1.13 (KD-ARQUEO-07 + DEC-ARQUEO-10) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
The handler `get_arqueo_resumen` in `api/v1/caja_arqueo.py` MUST execute a read query (Step 3 + Step 4) that returns one row per `prod.sesion` of the day at `params.uuid_sucursal` with `timestamp_apertura::date = params.fecha`. For each sesion, the row MUST compute `valor_efectivo_esperado = sesion.valor_inicial_efectivo + COALESCE((SELECT SUM(valor) FROM prod.factura_pagos WHERE uuid_sesion=sesion.uuid AND medio_pago='efectivo' AND tipo_movimiento='pago'), 0)` and `valor_datafono_esperado = sesion.valor_inicial_datafono + COALESCE((SELECT SUM(valor) FROM prod.factura_pagos WHERE uuid_sesion=sesion.uuid AND medio_pago IN ('tarjeta', 'datafono') AND tipo_movimiento='pago'), 0)`. The query MUST NOT execute any UPDATE/INSERT/DELETE on `prod.factura_pagos` (F1.9 immutability, KD-ARQUEO-08 read-only). If a `cierre_dia` arqueo exists for `(uuid_sucursal, fecha)`, it MUST appear in the `cierre_dia` aggregate field at the bottom of the response. The response MUST be `200 OK` with `Cache-Control: no-store` (DEC-ARQUEO-06).

**Rationale**: F1.9 `prod.factura_pagos` is immutable (F1.9 REQ-OPS-058 + `fn_factura_pagos_inmutable` trigger migration 0001 lines 2024-2088). F1.13 reads only via the direct FK `prod.factura_pagos.uuid_sesion` (migration 0001 line 716). The grouping matches the arqueo contract (plan.md lines 1062-1065).

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/arqueo.py::listar_sesiones_del_dia`, `repo/arqueo.py::construir_resumen_sesion`, `repo/arqueo.py::obtener_cierre_dia_del_dia` (NEW helpers); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 716 (`factura_pagos.uuid_sesion` FK), lines 2024-2088 (`fn_factura_pagos_inmutable` trigger); F1.9 REQ-OPS-058 (`factura_pagos` immutability precedent).

**Scenario 1: Resumen con 1 sesion + 1 arqueo → 1 item con totales calculados**
- **Given** a GET `?uuid_sucursal=<:s>&fecha=2026-09-15`
- **And** 1 `prod.sesion` row `:ses` at `:s` with `timestamp_apertura::date='2026-09-15'`, `valor_inicial_efectivo=50000`, `valor_inicial_datafono=0`
- **And** 2 `prod.factura_pagos` rows for `:ses`: `(medio_pago='efectivo', valor=30000, tipo_movimiento='pago')` and `(medio_pago='tarjeta', valor=20000, tipo_movimiento='pago')`
- **And** 1 `prod.arqueo` row for `:ses` (cierre_turno or auditoria)
- **When** the handler Step 3 + Step 4 execute the read query
- **Then** the response MUST include exactly 1 `ArqueoResumenItem` for `:ses`
- **And** the item MUST have `valor_efectivo_esperado = 50000 + 30000 = 80000` AND `valor_datafono_esperado = 0 + 20000 = 20000`
- **And** `cierre_dia` MUST be `null` (no cierre_dia arqueo for this date).

**Scenario 2: Resumen con cierre_dia existente → aggregate al fondo**
- **Given** 3 sesiones at `:s` for `fecha='2026-09-15'`
- **And** 1 `cierre_dia` arqueo row with `uuid_sucursal=:s`, `uuid_sesion=null`, `fecha_retencion_hasta IN ('2026-09-15', ...)`
- **When** the handler Step 4 invokes `obtener_cierre_dia_del_dia(session, uuid_sucursal=:s, fecha='2026-09-15')`
- **Then** the response MUST include 3 items in `sesiones[]` AND 1 item in `cierre_dia` (the aggregate arqueo row)
- **And** the `cierre_dia` item MUST have `uuid_sesion=null` (because `cierre_dia` carries `uuid_sesion=null` per DEC-ARQUEO-03).

**Scenario 3: Resumen con día vacío → 200 con `sesiones=[]`, `cierre_dia=null`**
- **Given** a GET `?uuid_sucursal=<:s>&fecha=2026-09-15`
- **And** ZERO `prod.sesion` rows at `:s` for that date AND ZERO `cierre_dia` arqueos
- **When** the handler Step 3 invokes `listar_sesiones_del_dia`
- **Then** the helper MUST return `[]` (empty list, NOT 404)
- **And** the response MUST be `200 OK` with `{"fecha": "2026-09-15", "uuid_sucursal": "<:s>", "sesiones": [], "cierre_dia": null}` + `Cache-Control: no-store`.

---

### REQ-OPS-XR6 — Defense in depth: 5 layers + AST walks (mirror XR1..XR5)

**Source**: HU-F1.13 (KD-ARQUEO-01 + KD-ARQUEO-08 + DEC-ARQUEO-05 + DEC-ARQUEO-06 + DEC-ARQUEO-08) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
F1.13 MUST apply the F1.10 + F1.11 + F1.12 defense-in-depth pattern (5 layers), each independently testable, with failure of any one layer contained by the other four:
- **Layer 1 — KD-3 issuer chain + permission gate**: `_caja_arqueo_issuer_dep = requires_issuer("operador-", "admin-")` (FastAPI dependency) + permission `realizar_arqueo` (after GAP-BE-05 fix at `api/v1/caja.py:53` — DEC-ARQUEO-08). For `caja_sesion.py:257` permission `abrir_cerrar_caja` (after GAP-BE-05 fix at site #2). Branch operator with `realizar_arqueo` performs arqueo; admin cross-branch.
- **Layer 2 — Tenant scope post-V1**: After resolving `target_sucursal` from `ctx.sucursal_uuid` (V1 in POST) or from `params.uuid_sucursal` (in GET), if `ctx.issuer_prefix == "operador-"` AND `(ctx.sucursal_uuid is None OR target_sucursal != ctx.sucursal_uuid)`, return `403 tenant_scope_violation` with `Cache-Control: no-store`. Admin (`admin-`) bypasses. KD-S2 analog from F1.7.
- **Layer 3 — KD-ARQUEO-01 single-commit + KD-ARQUEO-08 lock ordering**: AST walk `tests/static/test_arqueo_handler_single_commit.py` enforces EXACTLY ONE `await session.commit()` in the `post_arqueo` body. `SELECT FOR UPDATE` on `prod.tipo_arqueo` (Step 1) precedes all other locks (REQ-OPS-091 Scenario 1, KD-ARQUEO-08 deadlock prevention). AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` enforces `close_session_with_log` usage on the `cierre_dia` path (REQ-OPS-092 Scenario 3). AST walk `tests/static/test_arqueo_handler_no_raw_dml.py` enforces no raw INSERT/UPDATE/DELETE on `[A]`/`[V]` tables outside the `repo/arqueo.py` helpers.
- **Layer 4 — Pydantic `extra='forbid'` + numeric Decimal + UUID required**: `ArqueoCreateV2(_Base)` + `ArqueoReadForHandler` + `ArqueoResumenItem` + `ArqueoResumenRead` + `CierreDiarioQueryParams` inherit `extra='forbid'` from `schemas/common.py::_Base` (blocks client smuggling of `uuid_usuario`, `fecha_retencion_hasta`, `alerta_generada`, `alerta_uuid`, `descuadre_pct`, `created_at`, `created_by` — all server-derived). Numeric `valor_efectivo_reportado`/`valor_datafono_reportado` use `Decimal` with `ge=0`. UUID fields required where mandated (REQ-OPS-096 sesion validate).
- **Layer 5 — Handler 422/409/404/403/400 mapping + `Cache-Control: no-store`**: Every response (201 + 4xx + 5xx) on BOTH endpoints carries `Cache-Control: no-store`. Success: `apply_no_store_header(response)`. Error: `HTTPException(headers=no_store_headers())`. Typed exceptions (`TipoArqueoNoEncontradoError` 404, `SesionNoEncontradaError` 404, `ToleranciaNoConfiguradaError` 404, `SesionYaCerradaError` 409, `CierreDiaNoAceptaSesionError` 400, `JustificacionRequeridaError` 400, `TenantScopeViolationError` 403, `PermissionDeniedError` 403, `IdempotencyKeyRequiredError` 400, `IdempotencyConflictError` 409) map to the typed bodies documented in `schemas/caja.py` §9.3. The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

**Rationale**: Defense in depth against accidental drift in any single layer. The AST walk is the F1.10 XR1 + F1.11 XR4 + F1.12 XR5 mirror for F1.13. The 5-layer pattern is the canonical backend invariant for multi-table atomic writes (F1.9 KD-FACT-01, F1.10 KD-FE-01, F1.11 KD-TKT-01, F1.12 KD-VENTA-01, F1.13 KD-ARQUEO-01).

**Source**: F1.9 REQ-OPS-058 (factura_pagos immutability precedent); F1.10 REQ-OPS-XR1 (single-commit AST walk precedent); F1.11 REQ-OPS-XR4 (insert-only AST walk precedent); F1.12 REQ-OPS-XR5 (5-layer defense precedent); `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header`); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'`); `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` line 53 (GAP-BE-05 site #1) + `api/v1/caja_sesion.py` line 257 (GAP-BE-05 site #2).

**Scenario 1: operador with `realizar_arqueo` + own branch — OK**
- **Given** an operador role granted `realizar_arqueo` permission via `prod.permisos_usuario`
- **And** `ctx.sucursal_uuid=:s` matching the operator's branch
- **And** a valid `ArqueoCreateV2` payload (sin diferencia, justificacion optional for auditoria)
- **When** the operador POSTs `/api/v1/caja/arqueo`
- **Then** the request MUST pass Layer 1 (KD-3 issuer chain + permission gate) AND Layer 2 (tenant scope) AND reach the handler body
- **And** MUST return `201 Created` on the happy path with `Cache-Control: no-store`.

**Scenario 2: operador with `emitir_factura` only (pre-GAP-BE-05 behavior) — 403 `permission_denied`**
- **Given** an operador role granted `emitir_factura` permission (NOT `realizar_arqueo`)
- **When** the operador POSTs `/api/v1/caja/arqueo` (after GAP-BE-05 fix applied to `caja.py:53`)
- **Then** Layer 1 MUST reject with `403 Forbidden` and body `{"error": "permission_denied"}` and `Cache-Control: no-store`
- **And** Layer 2 (tenant scope) MUST NOT be evaluated (Layer 1 short-circuits first)
- **And** NO DB writes MUST occur (handler body unreachable).

**Scenario 3: operador with `realizar_arqueo` + DIFFERENT branch — 403 `tenant_scope_violation`**
- **Given** an operador role granted `realizar_arqueo` permission
- **And** `ctx.sucursal_uuid=:s_other` (operator's branch is `:s_other`, but the request's resolved target sucursal is `:s_target != :s_other`)
- **When** the operador POSTs `/api/v1/caja/arqueo`
- **Then** Layer 2 MUST reject with `403 Forbidden` and body `{"error": "tenant_scope_violation"}` and `Cache-Control: no-store`
- **And** NO DB writes MUST occur (handler body unreachable).

**Scenario 4: All responses (201 + 4xx + 5xx) carry `Cache-Control: no-store`**
- **Given** any response from `POST /api/v1/caja/arqueo` or `GET /api/v1/caja/arqueo/resumen` (success or failure)
- **When** the response is emitted
- **Then** the `Cache-Control: no-store` header MUST be present on `201 Created`
- **And** MUST be present on `400 idempotency_key_required` / `400 cierre_dia_no_acepta_uuid_sesion` / `400 justificacion_requerida` / `403 tenant_scope_violation` / `403 permission_denied` / `404 tipo_arqueo_no_encontrado` / `404 sesion_no_encontrada` / `404 tolerancia_no_configurada` / `409 sesion_ya_cerrada` / `409 idempotency_conflict` / `422 missing_query_params`
- **And** MUST be present on any uncaught 5xx (defense-in-depth).

**Scenario 5: GAP-BE-05 unit test — `caja_arqueo` endpoint requires `realizar_arqueo` not `emitir_factura`**
- **Given** the source file `api/v1/caja.py` at line 53
- **When** `tests/unit/test_gap_be_05.py::test_caja_arqueo_endpoint_requires_realizar_arqueo_not_emitir_factura` runs
- **Then** the test MUST assert `permission_required="realizar_arqueo"` is the bound permission
- **And** a role granted `emitir_factura` only MUST receive `403 permission_denied` on POST `/api/v1/caja/arqueo`
- **And** a role granted `realizar_arqueo` only MUST receive `201 Created` on the happy path.

**Scenario 6: GAP-BE-05 unit test — `caja_sesion` mount requires `abrir_cerrar_caja` not `emitir_factura`**
- **Given** the source file `api/v1/caja_sesion.py` at line 257
- **When** `tests/unit/test_gap_be_05.py::test_caja_sesion_endpoint_requires_abrir_cerrar_caja_not_emitir_factura` runs
- **Then** the test MUST assert `permission_required="abrir_cerrar_caja"` is the bound permission
- **And** a role granted `emitir_factura` only MUST receive `403 permission_denied` on `GET /api/v1/caja/sesion/...`
- **And** a role granted `abrir_cerrar_caja` only MUST pass through.

---
### REQ-OPS-098 — `GET /api/v1/sync/estado` SELECT-only contract (KD-SYNC-01 + KD-SYNC-02)

**Source**: HU-F1.14 (DEC-SYNC-01 + DEC-SYNC-02 + KD-SYNC-01 + KD-SYNC-02) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
The handler `get_sync_estado` in the NEW dedicated router `api/v1/sync_estado.py` (mounted under `/sync` prefix via `router.include_router(sync_estado_router)` in `api/v1/caja.py` per DEC-SYNC-02 — F1.13 mount precedent at `caja.py:86`) MUST be a READ-ONLY endpoint that returns HTTP 200 with body `SyncEstadoRead(uuid_sucursal, ultima_sync_at, lag_seg, pendientes)`. The handler MUST execute exactly **2 SELECT queries**: one against `prod.sync_log` (computing `MAX(timestamp_evento) WHERE uuid_sucursal=X` via `repo_sync_estado.get_ultima_sync_at(session, uuid_sucursal)`) and one against `prod.sync_queue` (computing `count(*) WHERE uuid_sucursal=X AND estado='pendiente'` via `repo_sync_estado.count_pendientes_sync_queue(session, uuid_sucursal)`). The handler MUST NOT execute any `UPDATE`, `INSERT`, or `DELETE` statements on `sync_log` or `sync_queue` (KD-SYNC-01). The handler MUST NOT call `await session.commit()` (GET is naturally idempotent). The handler MUST NOT append any row in `prod.log_operaciones` or any `[A]` audit table. The response MUST include `Cache-Control: no-store` (DEC-SYNC-04).

**Rationale**: HU-F11.1 `SyncBanner` polls every 30 seconds with `operador-` JWT. A read-only path preserves the `[A]` invariant on `sync_log` (append-only via AppendOnlyBase + `fn_sync_log_inmutable` trigger) and the REQ-OPS-004 carve-out on `sync_queue`. KD-SYNC-02 AST walk `tests/static/test_sync_estado_read_only.py` enforces the read-only invariant at static-parse time — defense in depth against accidental drift to a write path. The dedicated router with `requires_issuer("operador-", "admin-")` resolves the issuer-chain conflict on `/sync` prefix (DEC-SYNC-01 — `sync_router.py:358` rejects non-`sync-agent-` issuers, so the new endpoint MUST live in a separate router file to reach operador JWTs).

**Source**: `backend/packages/parkos_core/src/parkos_core/api/v1/sync_router.py` lines 9-49 (docstring listing 7 endpoints — `/estado` NOT in list, no collision), line 95 (`APIRouter(prefix="/sync")`), line 358 (`sync-agent-` issuer guard); `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` line 86 (F1.13 mount precedent); `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header`); `backend/packages/parkos_core/src/parkos_core/models/A/{sync_log, sync_queue}.py` (verbatim ORM models); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (`fn_sync_log_inmutable` trigger); F1.10 REQ-OPS-XR1 + F1.11 REQ-OPS-XR4 + F1.12 REQ-OPS-XR5 + F1.13 REQ-OPS-XR6 (AST walk precedents).

**Scenario 1: Happy path — populated branch returns 200 with exact lag + count**
- **Given** an `operador-` JWT with `audit_read` permission (DEC-SYNC-03.B) and `ctx.sucursal_uuid=:s` matching the request target
- **And** `prod.sync_log` contains 5 rows for `uuid_sucursal=:s` with `timestamp_evento` spanning 60-300 seconds before NOW()
- **And** `prod.sync_queue` contains 12 rows for `uuid_sucursal=:s` with `estado='pendiente'`
- **And** `MAX(timestamp_evento)` over those 5 rows resolves to a single value `t_max`
- **When** the operator invokes `GET /api/v1/sync/estado?uuid_sucursal=:s`
- **Then** the handler MUST execute exactly 2 SELECT queries against `prod.sync_log` and `prod.sync_queue`
- **And** MUST NOT execute any UPDATE, INSERT, or DELETE on either table
- **And** MUST NOT call `await session.commit()`
- **And** the response MUST be `200 OK` with `SyncEstadoRead{uuid_sucursal=:s, ultima_sync_at=t_max, lag_seg=NOW_seconds - t_max_seconds (±1s tolerance), pendientes=12}`
- **And** the response MUST carry `Cache-Control: no-store`.

**Scenario 2: Empty branch — no sync_log rows returns 200 with null lag, NOT 404**
- **Given** an `operador-` JWT with `audit_read` permission and `ctx.sucursal_uuid=:s`
- **And** `prod.sync_log` contains **ZERO** rows for `uuid_sucursal=:s` (branch has never synced)
- **And** `prod.sync_queue` contains ZERO rows for `uuid_sucursal=:s`
- **When** the operator invokes `GET /api/v1/sync/estado?uuid_sucursal=:s`
- **Then** the handler MUST return `200 OK` (NOT 404 — branch exists, just no sync activity, DEC-SYNC-08)
- **And** the response body MUST be `SyncEstadoRead{uuid_sucursal=:s, ultima_sync_at=null, lag_seg=null, pendientes=0}` (NOT lag_seg=0, NOT lag_seg=infinity)
- **And** the response MUST carry `Cache-Control: no-store`.

**Scenario 3: Empty sync_queue only — populated sync_log, zero pendientes**
- **Given** an `operador-` JWT with `audit_read` permission and `ctx.sucursal_uuid=:s`
- **And** `prod.sync_log` contains 3 rows for `uuid_sucursal=:s`
- **And** `prod.sync_queue` contains **ZERO** rows for `uuid_sucursal=:s`
- **When** the operator invokes `GET /api/v1/sync/estado?uuid_sucursal=:s`
- **Then** the response MUST be `200 OK` with `lag_seg` computed from `t_max` AND `pendientes=0` (integer, NOT null, NOT negative — DEC-SYNC-09)
- **And** the response MUST carry `Cache-Control: no-store`.

**Scenario 4: AST walk — handler source contains NO `update`/`delete` on SyncLog/SyncQueue and NO `commit`**
- **Given** the source file `api/v1/sync_estado.py` containing `get_sync_estado` handler
- **When** `tests/static/test_sync_estado_read_only.py` runs an `ast.walk()` over the handler body
- **Then** the AST walk MUST assert ZERO occurrences of `update(SyncLog)` or `update(SyncQueue)` or `delete(SyncLog)` or `delete(SyncQueue)` or `session.execute(text("UPDATE prod.sync_log"))` or `session.execute(text("DELETE FROM prod.sync_queue"))` in the handler body (KD-SYNC-01 + KD-SYNC-02)
- **And** MUST assert ZERO occurrences of `await session.commit()` in the handler body (GET is naturally commit-free).

---

### REQ-OPS-099 — MIGRATION 0032 siembra 11 alert_types de negocio (idempotent, 10 net new) (DEC-SYNC-05 + DEC-SYNC-06 + DEC-SYNC-07)

**Source**: HU-F1.14 (DEC-SYNC-05 + DEC-SYNC-06 + DEC-SYNC-07 + DEC-SYNC-10) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
MIGRATION 0032 (`0032_seed_alert_types_operativos.py`, `down_revision='0031_arqueo_cierre_dia_and_gap_be_05'`) MUST apply an idempotent siembra of the 11 business alert_types codes per plan.md line 1131 against `prod.alert_types` ([A] registry, migration 0013 lines 1-169). The seed MUST use `ON CONFLICT (tipo_alerta) DO NOTHING` for idempotency — `alert_types_inmutable` trigger (migration 0013:21-22) MUST remain enabled throughout the INSERT path (it only blocks BEFORE UPDATE OR DELETE, not INSERT — DEC-SYNC-07). The pre-F1.14 state MUST be preserved: 8 técnicos from migration 0013 (`hash_chain_anomaly`, `dian_rechazada`, `dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`, `fe_provider_error`, `fe_numbering_exhausted`) + 1 from F1.13 MIGRATION 0031 Op 2 (`descuadre_critico`, lines 169-175 of `0031_arqueo_cierre_dia_and_gap_be_05.py`) = 9 pre-existing rows. The F1.14 re-seed of `descuadre_critico` MUST become a no-op via `ON CONFLICT DO NOTHING` (DEC-SYNC-05). Net new rows MUST be **10** (NOT 11). Final total: **19** (8 técnicos + 1 F1.13 + 10 F1.14 — DEC-SUC-14).

Severity mapping MUST follow plan.md line 1131 verbatim, mapped to the DB CHECK constraint values (DEC-SYNC-06): `alta` → `critical` (applied to `descuadre_critico`, `sync_fallida`, `evento_no_procesado`, `impresora_caida`, `fe_error_toppoint`, `numeracion_toppoint_agotada`), `media` → `warning` (applied to `capacidad_agotada`, `capacidad_agotada_forzado`, `arqueo_pendiente_24h`, `suscripcion_proxima_vencer`), `baja` → `info` (applied to `cache_desactualizado`). Each row MUST include a `descripcion` field per plan.md lines 2311-2323 (DEC-SYNC-10).

**Rationale**: Fase 11 (HU-F11.2 AlertasPanel) JOINs `alerta.tipo_alerta = alert_types.tipo_alerta` to surface severity (A-08). Without the siembra, the JOIN returns null for these 11 codes and the operator UI shows "—" placeholder. `alert_types_inmutable` is the immutability contract — disabling it for re-seed would violate KD-3 (no migration may bypass DB-layer immutability). The `ON CONFLICT DO NOTHING` clause is atomic (no SELECT-then-INSERT race) and respects the trigger (it operates on INSERT, not UPDATE/DELETE).

**Source**: `backend/packages/parkos_core/migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` lines 169-175 (F1.13 head, Op 2 `descuadre_critico` siembra precedent — DEC-ARQUEO-09b); `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` lines 21-22 (`alert_types_inmutable` trigger), lines 67-108 (idempotent INSERT precedent), lines 119 (severity CHECK constraint), lines 129-130 (REVOKE/GRANT); `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` lines 134-188 (conditional siembra pattern); `plan.md` line 429 (DEC-SUC-14: 19 totales), line 459 (A-08 severity JOIN), lines 2311-2323 (canonical descriptions per code); `modelo_datos_er.mmd` lines 1101-1114 (`alert_types` [A]).

**Scenario 1: Upgrade applied on fresh DB after F1.13 head — net 10 rows added, total 19**
- **Given** the DB at migration head `0031_arqueo_cierre_dia_and_gap_be_05` with `prod.alert_types` containing exactly **9** rows (8 técnicos + `descuadre_critico`)
- **When** `alembic upgrade head` applies MIGRATION 0032
- **Then** the pre-flight `DO $$` Op MUST verify `prod.alert_types` exists with PK `tipo_alerta` AND the `alert_types_inmutable` trigger is active AND the `severity` column has CHECK constraint accepting `('info', 'warning', 'critical')`
- **And** the siembra MUST INSERT all 11 codes per plan.md line 1131 (including the `descuadre_critico` re-attempt)
- **And** the `descuadre_critico` re-attempt MUST be silently absorbed by `ON CONFLICT DO NOTHING` (zero error, zero new row)
- **And** exactly **10** net new rows MUST be visible (1+1+1+1+1+1+1+1+1+1 for `sync_fallida`, `capacidad_agotada`, `capacidad_agotada_forzado`, `evento_no_procesado`, `impresora_caida`, `fe_error_toppoint`, `numeracion_toppoint_agotada`, `cache_desactualizado`, `arqueo_pendiente_24h`, `suscripcion_proxima_vencer`)
- **And** the final total MUST be **19** rows (`SELECT COUNT(*) FROM prod.alert_types` = 19)
- **And** the `alert_types_inmutable` trigger MUST remain ENABLED after the upgrade (the `DISABLE TRIGGER`/`ENABLE TRIGGER` pair only appears in `downgrade()`).

**Scenario 2: Upgrade idempotency — re-running on already-migrated DB is a clean no-op**
- **Given** the DB already at migration head `0032_seed_alert_types_operativos` with `prod.alert_types` containing **19** rows
- **When** `alembic upgrade head` is invoked again (idempotency check)
- **Then** the siembra MUST execute `INSERT ... ON CONFLICT (tipo_alerta) DO NOTHING` for all 11 codes
- **And** ZERO new rows MUST be added (count remains 19)
- **And** the trigger MUST NOT raise (the conflict path is silent)
- **And** NO error MUST be emitted.

**Scenario 3: Severity exact match per plan.md line 1131**
- **Given** MIGRATION 0032 has just been applied to a fresh DB
- **When** `SELECT tipo_alerta, severity FROM prod.alert_types WHERE tipo_alerta IN (...)` runs against the 11 business codes
- **Then** the mapping MUST be exact per DEC-SYNC-06:
  - `descuadre_critico` → `critical`
  - `sync_fallida` → `critical`
  - `evento_no_procesado` → `critical`
  - `impresora_caida` → `critical`
  - `fe_error_toppoint` → `critical`
  - `numeracion_toppoint_agotada` → `critical`
  - `capacidad_agotada` → `warning`
  - `capacidad_agotada_forzado` → `warning`
  - `arqueo_pendiente_24h` → `warning`
  - `suscripcion_proxima_vencer` → `warning`
  - `cache_desactualizado` → `info`
- **And** the `severity` column MUST satisfy the CHECK constraint for every row (no `alta`/`media`/`baja` neutral-Spanish values).

**Scenario 4: Downgrade removes only the 10 F1.14 net new rows (NOT `descuadre_critico`)**
- **Given** the DB at head `0032_seed_alert_types_operativos` with 19 rows
- **When** `alembic downgrade -1` executes MIGRATION 0032's `downgrade()`
- **Then** the `ALTER TABLE prod.alert_types DISABLE TRIGGER alert_types_inmutable` MUST precede the DELETE (trigger blocks DELETE by default — migration 0013:21-22)
- **And** the DELETE MUST target only the 10 F1.14 net new codes (`sync_fallida`, `capacidad_agotada`, `capacidad_agotada_forzado`, `evento_no_procesado`, `impresora_caida`, `fe_error_toppoint`, `numeracion_toppoint_agotada`, `cache_desactualizado`, `arqueo_pendiente_24h`, `suscripcion_proxima_vencer`)
- **And** the DELETE MUST NOT touch `descuadre_critico` (owned by F1.13 MIGRATION 0031 Op 2 lines 169-175)
- **And** the DELETE MUST NOT touch any of the 8 técnicos (owned by MIGRATION 0013)
- **And** after the DELETE + `ENABLE TRIGGER`, `prod.alert_types` MUST contain exactly **9** rows (8 técnicos + `descuadre_critico`).
- **And** after `alembic upgrade head` is invoked again, `prod.alert_types` MUST contain **19** rows again (the cycle round-trips cleanly).

---

### REQ-OPS-100 — `lag_seg = null` semantics + `pendientes >= 0` invariant + UI rendering contract (DEC-SYNC-08 + DEC-SYNC-09)

**Source**: HU-F1.14 (DEC-SYNC-08 + DEC-SYNC-09 + DEC-SYNC-04) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
Given a successful `GET /api/v1/sync/estado` response, the response shape MUST enforce the following invariants:
- `ultima_sync_at: datetime | None` — nullable ISO-8601 naive UTC datetime. `None` semantically means "branch has never synced" (NOT 0, NOT a sentinel date).
- `lag_seg: int | None` — nullable integer. `None` when `ultima_sync_at IS NULL` (DEC-SYNC-08). When non-null, MUST equal `int((NOW() - ultima_sync_at).total_seconds())` (positive integer >= 0).
- `pendientes: int` — non-nullable integer >= 0 (DEC-SYNC-09). `SELECT count(*)` ALWAYS returns 0 for empty result set; the handler MUST NOT return `null`.

The HU-F11.1 `SyncBanner` operator UI MUST render the response per the following contract:
- `lag_seg = null` → "NEVER SYNCED" banner state (NOT "freshly synced", NOT error, NOT 404).
- `lag_seg = 0..30` → VERDE (green, fresh sync).
- `lag_seg = 31..300` → AMARILLO (yellow, degraded).
- `lag_seg > 300` → ROJO (red, stale).
- `pendientes >= 100` → inline alert badge rendered (DEC-SYNC-09 high-pile indicator).

The response body MUST NEVER include `pgcode`, `pgerror`, `pgmessage`, or any PostgreSQL error internals. The response MUST ALWAYS include `Cache-Control: no-store` header (DEC-SYNC-04).

**Rationale**: Returning `lag_seg = 0` for an empty branch would falsely reassure the operator that the sync is fresh — semantically wrong. Returning `None` forces the UI to handle the "never synced" state explicitly via the NEVER SYNCED banner. `count(*)` is by definition `>= 0`; returning `null` would force the client to special-case the empty result, which the SQL aggregate already handles. The pgcode/pgerror redaction is XR6 Layer 5 (defense in depth — prevents leaking schema internals via error responses).

**Source**: `backend/packages/parkos_core/src/parkos_core/schemas/sync_infra.py` (NEW `SyncEstadoRead(_Base)` with `lag_seg: int | None`, `ultima_sync_at: datetime | None`, `pendientes: int`); `backend/packages/parkos_core/src/parkos_core/repo/sync_estado.py` (NEW `calcular_lag_seg(ultima_sync_at, now)` helper returns `None` when `ultima_sync_at IS None`); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` base class); `plan.md` lines 2275-2291 (HU-F11.1 SyncBanner consumer — 30s polling, verde/amarillo/rojo umbrales from CU-14 BR1); `plan.md` lines 2305-2325 (HU-F11.2 AlertasPanel consumer); DEC-FE-06 / DEC-TKT-06 / DEC-VENTA-06 / DEC-ARQUEO-06 (XR6 `Cache-Control: no-store` precedent).

**Scenario 1: `lag_seg = None` renders as NEVER SYNCED banner (NOT verde, NOT 0)**
- **Given** the operator UI receives `SyncEstadoRead{uuid_sucursal=:s, ultima_sync_at=null, lag_seg=null, pendientes=0}`
- **When** the SyncBanner renders the state
- **Then** the banner MUST display "NEVER SYNCED" (or equivalent localized label — DEC-SYNC-08)
- **And** MUST NOT display VERDE (green) state (lag_seg=null ≠ lag_seg=0)
- **And** MUST NOT display an error indicator (the response is 200, not 4xx/5xx).

**Scenario 2: `lag_seg = 120` renders as AMARILLO, `lag_seg = 600` as ROJO, `lag_seg = 5` as VERDE**
- **Given** three successive poll responses: `lag_seg=5`, `lag_seg=120`, `lag_seg=600`
- **When** the SyncBanner renders each state
- **Then** the `lag_seg=5` banner MUST display VERDE (green — within 0-30s threshold)
- **And** the `lag_seg=120` banner MUST display AMARILLO (yellow — within 31-300s threshold)
- **And** the `lag_seg=600` banner MUST display ROJO (red — > 300s threshold).

**Scenario 3: `pendientes = 0` MUST NOT be null; `pendientes >= 100` MUST render badge**
- **Given** `SyncEstadoRead{pendientes=0}` (empty sync_queue) and `SyncEstadoRead{pendientes=247}` (large pile)
- **When** the SyncBanner + AlertasPanel render the state
- **Then** the `pendientes=0` case MUST render with no badge and no error
- **And** the `pendientes=247` case MUST render an inline alert badge (DEC-SYNC-09 high-pile indicator)
- **And** `pendientes` MUST NEVER be `null` in the response body (count(*) invariant — DEC-SYNC-09).

**Scenario 4: Response NEVER includes pgcode/pgerror/pgmessage; ALWAYS includes `Cache-Control: no-store`**
- **Given** any response from `GET /api/v1/sync/estado` (200 or 4xx, success or failure)
- **When** the response is emitted
- **Then** the response body MUST NOT contain the keys `pgcode`, `pgerror`, or `pgmessage` (XR6 Layer 5 redaction)
- **And** the response MUST include the `Cache-Control: no-store` header on every status code (200, 403, 422 — DEC-SYNC-04).

---

### REQ-OPS-101 — XR6 cross-cutting defense in depth (REFERENCE to existing REQ-OPS-XR6)

**Source**: HU-F1.14 (DEC-SYNC-01 + DEC-SYNC-03.B + DEC-SYNC-04 + KD-SYNC-02) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
Given that REQ-OPS-XR6 already exists at `openspec/specs/operations/spec.md:3951` from F1.13, F1.14's `GET /api/v1/sync/estado` endpoint MUST satisfy all 5 defense-in-depth layers defined in REQ-OPS-XR6, applied as follows:

- **Layer 1 (KD-3 issuer chain + permission gate)** — NEW dedicated router `api/v1/sync_estado.py` declares `_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")`. Permission gate is `audit_read` (DEC-SYNC-03.B, pre-seeded per `0002_seed_permisos_canonicos.py:48`). Branch operator with `audit_read` reads sync status; admin cross-branch.
- **Layer 2 (Tenant scope post-V1)** — After resolving `target_sucursal` from `params.uuid_sucursal`, if `ctx.issuer_prefix == "operador-"` AND `(ctx.sucursal_uuid is None OR target_sucursal != ctx.sucursal_uuid)`, return `403 tenant_scope_violation` with `Cache-Control: no-store`. Admin (`admin-`) bypasses. KD-S2 analog from F1.7.
- **Layer 3 (KD-SYNC-01 SELECT-only + KD-SYNC-02 read-only AST walk)** — The handler invokes ONLY the 3 typed SELECT helpers from `repo/sync_estado.py` (read-only path). The AST walk `tests/static/test_sync_estado_read_only.py` enforces NO `session.execute(update(SyncLog))`, `session.execute(update(SyncQueue))`, `session.execute(delete(SyncLog))`, `session.execute(delete(SyncQueue))`, and NO `await session.commit()` in the handler body. Mirrors F1.10 REQ-OPS-XR1 + F1.11 REQ-OPS-XR4 + F1.12 REQ-OPS-XR5 + F1.13 REQ-OPS-XR6.
- **Layer 4 (Pydantic `extra='forbid'` + UUID required + nullable `lag_seg`)** — `SyncEstadoQueryParams(_Base)` + `SyncEstadoRead(_Base)` inherit `extra='forbid'` from `schemas/common.py::_Base` (blocks client smuggling of `actor_uuid`, `computed_at`, `cache_key`). `uuid_sucursal: UUID` is required. `lag_seg: int | None` (nullable, DEC-SYNC-08). `ultima_sync_at: datetime | None` (nullable). `pendientes: int` (non-nullable, DEC-SYNC-09).
- **Layer 5 (Handler 200/422/403 mapping + `Cache-Control: no-store`)** — Every response (200 + 4xx + 5xx) on `GET /api/v1/sync/estado` carries `Cache-Control: no-store`. Typed exceptions map as follows: `UuidSucursalInvalidError` → 422 `uuid_sucursal_invalid` (Pydantic validator, Layer 4); `TenantScopeViolationError` → 403 `tenant_scope_violation` (handler Layer 2); `PermissionDeniedError` → 403 `permission_denied` (`require_permission` Layer 1). The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

F1.14 MUST NOT create a new cross-cutting requirement (XR). REQ-OPS-XR6 is canonical and applies to F1.14 by reference. `openspec/changes/hu-f1-14-sync-estado/design.md` §13 (Cross-Cutting Requirements) MUST reference REQ-OPS-XR6 and the 5 layer mapping above. `openspec/changes/hu-f1-14-sync-estado/tasks.md` §10 (Test Plan) MUST include the `test_sync_estado_read_only.py` AST walk as a Layer 3 verification step.

**Rationale**: XR6 is the canonical defense-in-depth contract for cross-cutting concerns. Creating a new XR (XR7) for F1.14 would duplicate the 5-layer contract and fragment the review surface. By referencing XR6, F1.14 inherits the testable invariants (AST walks, `extra='forbid'`, `Cache-Control: no-store`) without redefining them. Each layer is independently testable; failure of any one layer is contained by the other four (defense in depth principle).

**Source**: `openspec/specs/operations/spec.md` line 3951 (REQ-OPS-XR6 canonical from F1.13); `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header` — Layer 5 helper); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` — Layer 4 base); `backend/packages/parkos_core/src/parkos_core/auth/jwt_issuer_guard.py` (`requires_issuer` factory — Layer 1 dep); `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` (`get_tenant_ctx` — Layer 2 dep); F1.9 REQ-OPS-058 (factura_pagos immutability); F1.10 REQ-OPS-XR1 (single-commit AST walk precedent); F1.11 REQ-OPS-XR4 (insert-only AST walk precedent); F1.12 REQ-OPS-XR5 (5-layer defense precedent); F1.13 REQ-OPS-XR6 (caja-specific 5-layer defense precedent at `operations/spec.md:3951`).

**Scenario 1: operador with `audit_read` + own branch — 200 OK (Layer 1 + Layer 2 PASS)**
- **Given** an operador role granted `audit_read` permission via `prod.permisos_usuario`
- **And** `ctx.sucursal_uuid=:s` matching the request's `params.uuid_sucursal`
- **When** the operador invokes `GET /api/v1/sync/estado?uuid_sucursal=:s`
- **Then** Layer 1 MUST pass (KD-3 issuer `operador-` accepted + `audit_read` permission granted)
- **And** Layer 2 MUST pass (own-branch tenant scope)
- **And** Layer 3 MUST execute exactly 2 SELECT queries (KD-SYNC-01)
- **And** Layer 4 MUST validate the Pydantic schema (`uuid_sucursal` is a valid UUID, no extra fields)
- **And** Layer 5 MUST return `200 OK` with `Cache-Control: no-store`.

**Scenario 2: operador with `audit_read` + DIFFERENT branch — 403 `tenant_scope_violation` (Layer 2 short-circuits)**
- **Given** an operador role granted `audit_read` permission
- **And** `ctx.sucursal_uuid=:s_other` (operator's branch is `:s_other`, but the request target is `:s_target != :s_other`)
- **When** the operador invokes `GET /api/v1/sync/estado?uuid_sucursal=:s_target`
- **Then** Layer 1 MUST pass (issuer + permission OK)
- **And** Layer 2 MUST reject with `403 Forbidden` and body `{"error": "tenant_scope_violation"}` and `Cache-Control: no-store`
- **And** NO SELECT queries MUST execute against `prod.sync_log` / `prod.sync_queue` (Layer 2 short-circuits before Layer 3).

**Scenario 3: operador with `audit_read` DENIED (no permission grant) — 403 `permission_denied` (Layer 1 short-circuits)**
- **Given** an operador role WITHOUT `audit_read` permission (only `emitir_factura` granted)
- **When** the operador invokes `GET /api/v1/sync/estado?uuid_sucursal=:s`
- **Then** Layer 1 MUST reject with `403 Forbidden` and body `{"error": "permission_denied"}` and `Cache-Control: no-store`
- **And** Layer 2 (tenant scope) MUST NOT be evaluated (Layer 1 short-circuits first)
- **And** NO DB queries MUST execute (handler body unreachable).

**Scenario 4: All responses (200 + 4xx + 5xx) carry `Cache-Control: no-store`**
- **Given** any response from `GET /api/v1/sync/estado` (success or failure)
- **When** the response is emitted
- **Then** the `Cache-Control: no-store` header MUST be present on `200 OK`
- **And** MUST be present on `403 tenant_scope_violation` / `403 permission_denied` / `422 uuid_sucursal_invalid`
- **And** MUST be present on any uncaught 5xx (defense in depth).
- **And** the response body MUST NOT contain `pgcode`, `pgerror`, or `pgmessage` keys.

**Scenario 5: Read-only AST walk — handler source contains ZERO UPDATE/DELETE on SyncLog/SyncQueue and ZERO `commit`**
- **Given** the source file `api/v1/sync_estado.py` containing `get_sync_estado`
- **When** `tests/static/test_sync_estado_read_only.py` runs
- **Then** the AST walk MUST assert ZERO occurrences of `update(SyncLog)` or `update(SyncQueue)` or `delete(SyncLog)` or `delete(SyncQueue)` or `session.execute(text("UPDATE prod.sync_log"))` or `session.execute(text("DELETE FROM prod.sync_queue"))` in the handler body (KD-SYNC-01 + KD-SYNC-02)
- **And** MUST assert ZERO occurrences of `await session.commit()` in the handler body.
### REQ-OPS-102 — `GET /api/v1/usuarios/{uuid}/login` SELECT-only contract (KD-LOGIN-01 + KD-LOGIN-02)

**Source**: HU-F1.15 (DEC-LOGIN-01 + DEC-LOGIN-02 + DEC-LOGIN-09.B + KD-LOGIN-01 + KD-LOGIN-02) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
The handler `get_login_historico` in the NEW dedicated router `api/v1/usuarios_login.py` (mounted at FastAPI app-level under `/usuarios` prefix — sibling of `auth.py`, NOT nested in `caja.py` per DEC-LOGIN-01.A separation-of-concerns rationale: `auth.py:69` is POST-mutating-only and adding a GET for login history there would couple read-of-history with the login write path; Parte 2's `api/v1/usuarios.py` will EXTEND this router without collision) MUST be a READ-ONLY endpoint that returns HTTP 200 with body `LoginHistoricoListResponse(items, next_cursor)` per the canonical `{items, next_cursor}` envelope (`api/router_factory.py:227`). The handler MUST execute exactly **1 SELECT query** against `prod.login` via `repo/login_historico.listar_intentos_paginado(session, uuid_usuario, cursor, limit, tenant_ctx)`. The handler MUST NOT execute any `UPDATE`, `INSERT`, or `DELETE` statements on `prod.login` (KD-LOGIN-01 — preserves the `_NARROW_UPDATE_LS_TABLES["login"] = ("timestamp_cierre", "estado")` whitelist at `0021_least_privilege_and_immutability_contract.py:206` and the [L-S] immutability invariant). The handler MUST NOT call `await session.commit()` (GET is naturally idempotent). The handler MUST NOT append any row in `prod.log_operaciones` or any `[A]` audit table. The response MUST include `Cache-Control: no-store` (DEC-LOGIN-05, XR6 mirror).

KD-3 issuer chain `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")` (DEC-LOGIN-02 — operador needs own-branch lockout diagnostic; admin needs cross-branch security audit). Permission gate `audit_read` (DEC-LOGIN-09.B, pre-seeded per `0002_seed_permisos_canonicos.py:48` — same audit domain as F1.14's `GET /sync/estado` per F1.14 DEC-SYNC-03.B precedent). Path param `uuid: UUID` (Pydantic validator; required). Query params `limit: int = 10` (ge=1, le=100 validators per DEC-LOGIN-04) + `cursor: str | None = None`. Response items MUST be ordered by `timestamp_evento DESC, uuid ASC` (most recent first per `plan.md` line 1143 verbatim). Each item MUST have exactly 5 fields: `uuid` (UUID), `timestamp_evento` (ISO 8601 naive UTC datetime), `timestamp_cierre` (ISO 8601 naive UTC datetime or null), `estado` (`Literal["exitoso", "fallido", "cerrado"]` — the REAL [L-S] lifecycle value per DEC-LOGIN-10; NEVER a synthetic boolean `activo`), `uuid_sucursal` (UUID or null).

**Rationale**: Operator/admin diagnostic on "why is user X locked out" or "did user Y just authenticate" is the gap huérfano per `plan.md` line 1139 + `pending.md` row 15. F1.15 surfaces this without adding a UI surface (UI deferred to Fase 11+). The dedicated router resolves the Parte 1 vs Parte 2 endpoint-ownership conflict (DEC-LOGIN-01 — both F1.15 and HU-F16.1/F16.5 propose the same URL per `plan.md` lines 7571-7574; F1.15 ships the minimal slice, Parte 2 extends). KD-LOGIN-02 AST walk `tests/static/test_login_historico_read_only.py` enforces the read-only invariant at static-parse time — defense in depth against accidental drift to a write path. Mirrors the F1.10 REQ-OPS-XR1 + F1.11 REQ-OPS-XR4 + F1.12 REQ-OPS-XR5 + F1.13 REQ-OPS-XR6 + F1.14 KD-SYNC-02 pattern.

**Source**: `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:69` (POST-mutating-only rationale for DEC-LOGIN-01.A — dedicated router); `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header` — DEC-LOGIN-05); `backend/packages/parkos_core/src/parkos_core/models/L_S/login.py:33-74` (verbatim ORM model — 5 business columns + FK + audit mixin); `backend/packages/parkos_core/src/parkos_core/models/V/usuarios.py` (Usuarios ORM — F1.15 reads `uuid` only for optional existence check); `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py:49-146` (`record_login` write helper — F1.15 NEVER calls it; only references the table it writes to); `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py:79-162` (cursor pagination precedent — `list_tarifas_vigentes`); `backend/packages/parkos_core/src/parkos_core/api/router_factory.py:127-227` (cursor pagination + `{items, next_cursor}` envelope pattern — DEC-LOGIN-04 + DEC-LOGIN-07); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` — Layer 4 base); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 511-523 (login table), 2203-2214 (`login_ls_session_guard` trigger), 2533-2541 (audit+set_vigente_inicial triggers), 2777-2788 (`login_enqueue_sync` trigger — none fire on F1.15's read path); `backend/packages/parkos_core/migrations/versions/0021_least_privilege_and_immutability_contract.py:206` (`_NARROW_UPDATE_LS_TABLES["login"]` whitelist — KD-LOGIN-02 enforces); `backend/packages/parkos_core/migrations/versions/0002_seed_permisos_canonicos.py:48` (`audit_read` pre-seeded — DEC-LOGIN-09.B); `tests/static/{test_sync_estado_read_only,test_arqueo_handler_single_commit,test_no_raw_dml_on_ls_tables}.py` (AST walk precedents); F1.10 REQ-OPS-XR1 + F1.11 REQ-OPS-XR4 + F1.12 REQ-OPS-XR5 + F1.13 REQ-OPS-XR6 + F1.14 KD-SYNC-02 (AST walk precedents for KD-LOGIN-02).

**Scenario 1: Happy path — populated user returns 200 with exact DESC ordering**
- **Given** a KD-3 issuer session (`operador-` or `admin-` JWT) with `audit_read` permission granted via `prod.permisos_usuario`
- **And** a path `uuid` (valid Pydantic UUID format) that has 5 rows in `prod.login` with `timestamp_evento` spanning 60-300 seconds before NOW() and mixed `estado ∈ {exitoso, fallido, cerrado}`
- **When** the handler `GET /api/v1/usuarios/{uuid}/login` is invoked with `limit=10` and no cursor
- **Then** the handler MUST execute exactly **1 SELECT query** against `prod.login` via `repo/login_historico.listar_intentos_paginado`
- **And** MUST NOT execute any `UPDATE`, `INSERT`, or `DELETE` on `prod.login` (KD-LOGIN-01)
- **And** MUST NOT call `await session.commit()`
- **And** the response MUST be `200 OK` with `Cache-Control: no-store` and body `LoginHistoricoListResponse{items: [5 LoginIntentoItem], next_cursor: <base64-encoded JSON of last item's (timestamp_evento, uuid) pair>}`
- **And** the 5 items MUST be ordered by `(timestamp_evento DESC, uuid ASC)` (most recent first per `plan.md` line 1143 verbatim).

**Scenario 2: Empty user (zero rows) — 200 with `items=[]`, NEVER 404**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` (valid Pydantic UUID) that has **ZERO** rows in `prod.login` (either the user does not exist OR exists but never authenticated)
- **When** the handler `GET /api/v1/usuarios/{uuid}/login` is invoked
- **Then** the response MUST be `200 OK` (NOT 404 — anti-enumeration per DEC-LOGIN-08, mirroring F1.2 R-F1.2-10 / R-F1.2-11 rationale)
- **And** the body MUST be `LoginHistoricoListResponse{items: [], next_cursor: null}`
- **And** the response MUST carry `Cache-Control: no-store`.

**Scenario 3: Cursor pagination — second page resumes EXACTLY at the next boundary**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` with 12 rows in `prod.login` ordered by `(timestamp_evento DESC, uuid ASC)`
- **And** the first page (no cursor) returned 10 items + a non-null `next_cursor` (the base64-encoded JSON of item #10's `(timestamp_evento, uuid)` pair per `router_factory.py:185-200`)
- **When** the client invokes `GET /api/v1/usuarios/{uuid}/login?limit=10&cursor=<that next_cursor>`
- **Then** the handler MUST execute the `WHERE` clause `(timestamp_evento < cursor_ts) OR (timestamp_evento = cursor_ts AND uuid > cursor_uuid)` (DEC-LOGIN-04 mirror of `api/router_factory.py:185-200`)
- **And** MUST return EXACTLY the remaining 2 items in DESC order — no row repeated, no row skipped
- **And** `next_cursor` MUST be `null` (last page).

**Scenario 4: AST walk — handler source contains NO `update`/`delete` on `Login` and NO `commit`**
- **Given** the source file `api/v1/usuarios_login.py` containing `get_login_historico` handler
- **When** `tests/static/test_login_historico_read_only.py` runs an `ast.walk()` over the handler body
- **Then** the AST walk MUST assert ZERO occurrences of `update(Login)` or `delete(Login)` or `session.execute(text("UPDATE prod.login"))` or `session.execute(text("DELETE FROM prod.login"))` in the handler body (KD-LOGIN-01 + KD-LOGIN-02)
- **And** MUST assert ZERO occurrences of `await session.commit()` in the handler body (GET is naturally commit-free).

---

### REQ-OPS-103 — Cursor pagination invariants + empty-user contract (DEC-LOGIN-04 + DEC-LOGIN-07 + DEC-LOGIN-08 + DEC-LOGIN-10)

**Source**: HU-F1.15 (DEC-LOGIN-04 + DEC-LOGIN-07 + DEC-LOGIN-08 + DEC-LOGIN-10) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
Given a successful or empty-user response from `GET /api/v1/usuarios/{uuid}/login`, the response shape MUST enforce the following invariants:

- **Ordering**: Items MUST be ordered by `(timestamp_evento DESC, uuid ASC)`. The `DESC` matches `plan.md` line 1143 verbatim ("los intentos más recientes primero"); the `uuid ASC` secondary key is the canonical tie-breaker for same-second INSERTs (e.g., F1.2 lockout writes batch multiple failed attempts at the same instant — pagination correctness requires the tie-breaker).
- **Cursor encoding**: `next_cursor` MUST encode the LAST item's `(timestamp_evento_iso, uuid_str)` pair as base64-encoded JSON (mirrors `api/router_factory.py:127-140` verbatim — `cursor_encode`/`cursor_decode` helpers reused). The `next_cursor` field MUST be `null` iff there are NO more rows after the current page (handler uses `LIMIT N+1` then slices to N to detect presence — DEC-LOGIN-04 mirror of `router_factory.py:185-200`).
- **Limit bounds**: `limit: int = 10` (default per `plan.md` line 1143 verbatim) with Pydantic validators `ge=1, le=100`. Out-of-range values MUST raise 422 before the handler body runs.
- **Item shape**: Each `LoginIntentoItem` MUST have exactly 5 fields, with no extras: `uuid` (UUID, required), `timestamp_evento` (ISO 8601 naive UTC datetime, required), `timestamp_cierre` (ISO 8601 naive UTC datetime or `null`, nullable for open sessions), `estado` (`Literal["exitoso", "fallido", "cerrado"]` — DEC-LOGIN-10 — the REAL [L-S] lifecycle value, NEVER a synthetic boolean `activo`), `uuid_sucursal` (UUID or `null`, nullable FK to `prod.sucursal`).
- **Envelope**: `LoginHistoricoListResponse{items: list[LoginIntentoItem], next_cursor: str | None}`. NO `activo`, NO `count`, NO `total`, NO `has_more` in F1.15 — the canonical `{items, next_cursor}` shape per `router_factory.py:227` is forward-compatible with Parte 2's HU-F16.1/F16.5 added filtros (`?activo=`) and closure action (`POST /usuarios/{uuid}/login/{login_uuid}/cerrar`) without breaking F1.15's response (DEC-LOGIN-07).
- **Empty-user contract**: ZERO `prod.login` rows for the requested `uuid` MUST return `200 OK` with `items=[]` and `next_cursor=null` — NEVER `404` (DEC-LOGIN-08 anti-enumeration). Mirrors F1.2 R-F1.2-10 / R-F1.2-11 rationale: returning `404` for an unknown `uuid_usuario` would let an attacker enumerate valid user UUIDs by comparing `404` vs `200`. F1.15 returns `200` with empty items regardless of whether the user exists, has zero login rows, or has only cross-branch rows (operador Layer 2 filter — DEC-LOGIN-03.A returns no rows → `items=[]`).
- **Malformed cursor**: A `cursor` value that fails base64 decode or fails JSON parse or is missing the `timestamp_evento` / `uuid` keys or has invalid types MUST return `400 Bad Request` with body `{"error": "cursor_invalid"}` and `Cache-Control: no-store`. NEVER `500` (typed exception handler converts decode errors to `CursorInvalidError`).
- **Cache-Control**: EVERY response (200, 400, 403, 422) MUST carry `Cache-Control: no-store` (DEC-LOGIN-05). XR6 Layer 5 mirror from F1.10..F1.14.
- **Pydantic redaction**: Response body MUST NEVER include `pgcode`, `pgerror`, `pgmessage`, or any PostgreSQL error internals. `extra='forbid'` (inherited from `schemas/common.py::_Base`) blocks client smuggling of `actor_uuid`, `computed_at`, `cache_key`, `activo`.

**Rationale**: Stable cursor pagination under concurrent INSERTs (F1.2 lockout writes from `record_login` may add rows during pagination — cursor pagination tolerates this; offset pagination would shift rows). The 3-value `estado` domain is the canonical truth per `plan.md` line 1143 verbatim; introducing a synthetic `activo` boolean would create a derived field that requires UI to interpret (`activo=True` → `cerrado OR exitoso`?). The anti-enumeration `200 + items=[]` contract prevents user UUID discovery via response code differential analysis.

**Source**: `backend/packages/parkos_core/src/parkos_core/api/router_factory.py:127-140` (`cursor_encode` / `cursor_decode` / `Cursor` dataclass — DEC-LOGIN-04 reuse); `api/router_factory.py:185-200` (LIMIT N+1 + slice-to-N next_cursor detection — DEC-LOGIN-04 mirror); `api/router_factory.py:227` (`{items, next_cursor}` envelope — DEC-LOGIN-07); `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py:79-162` (cursor pagination helper precedent — `ORDER BY vigente_desde DESC, uuid ASC`); `backend/packages/parkos_core/src/parkos_core/models/L_S/login.py:33-74` (verbatim ORM model — 5 business columns + state enum); `backend/packages/parkos_core/src/parkos_core/auth.py:239-246` (`fallido`), `:260-266` (`exitoso`), `:352-393` (`cerrado`) — `estado` lifecycle sources; `plan.md` line 1143 verbatim ("cada uno con su `estado` real (`exitoso|fallido|cerrado`) — nunca un campo booleano `activo`, que no existe en el dominio real de `login.estado`"); `plan.md` lines 7571-7574 (Parte 2 forward-compatibility — DEC-LOGIN-07); DEC-LOGIN-08 (anti-enumeration rationale mirrors F1.2 R-F1.2-10 / R-F1.2-11); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` — Layer 4 base).

**Scenario 1: `limit + cursor` pagination — `next_cursor` non-null iff more rows exist**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` with EXACTLY 15 rows in `prod.login` ordered by `(timestamp_evento DESC, uuid ASC)`
- **When** the client invokes `GET /api/v1/usuarios/{uuid}/login?limit=10`
- **Then** the response MUST contain AT MOST 10 items
- **And** MUST include a non-null `next_cursor` (base64 JSON of the 10th item's `(timestamp_evento, uuid)` pair — DEC-LOGIN-04 LIMIT N+1 detection)
- **And** MUST include `Cache-Control: no-store`.

**Scenario 2: Cursor resume — subsequent page resumes EXACTLY at the next `(timestamp_evento, uuid)` boundary**
- **Given** the response from Scenario 1: 10 items + `next_cursor=C1`
- **When** the client invokes `GET /api/v1/usuarios/{uuid}/login?limit=10&cursor=C1`
- **Then** the handler MUST execute the `WHERE` clause `(timestamp_evento < cursor_ts) OR (timestamp_evento = cursor_ts AND uuid > cursor_uuid)`
- **And** MUST return EXACTLY 5 items (the remaining rows)
- **And** MUST include `next_cursor=null` (last page)
- **And** NO row from the first page MUST be repeated; NO row from the 15 total MUST be skipped.

**Scenario 3: Empty user (zero rows) — 200 with `items=[]`, NEVER 404**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` (valid Pydantic UUID) that has ZERO `prod.login` rows
- **When** the handler is invoked (with or without `limit`/`cursor`)
- **Then** the response MUST be `200 OK` with `items=[]` and `next_cursor=null`
- **And** MUST NEVER be `404 Not Found` (anti-enumeration per DEC-LOGIN-08)
- **And** MUST carry `Cache-Control: no-store`.

**Scenario 4: Malformed cursor — 400 with `cursor_invalid`, NEVER 500**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` with rows in `prod.login`
- **When** the client invokes `GET /api/v1/usuarios/{uuid}/login?cursor=<malformed>` (e.g., not base64, base64 of `{}`, base64 of `{"timestamp_evento": "garbage"}`)
- **Then** the response MUST be `400 Bad Request` with body `{"error": "cursor_invalid"}`
- **And** MUST carry `Cache-Control: no-store`
- **And** MUST NEVER be `500 Internal Server Error` (typed exception handler converts decode errors to `CursorInvalidError`).

---

### REQ-OPS-104 — Empty-user 200 response + response-time parity + anti-enumeration (DEC-LOGIN-08)

**Source**: HU-F1.15 (DEC-LOGIN-08) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
When `prod.login` contains ZERO rows for the requested path `uuid` (regardless of whether the user exists in `prod.usuarios`, has zero login rows, or has only rows from branches the operador cannot see via the Layer 2 filter per DEC-LOGIN-03.A), the handler `get_login_historico` MUST return `200 OK` with body `LoginHistoricoListResponse{items: [], next_cursor: null}` and `Cache-Control: no-store` — NEVER `404 Not Found`. The response time MUST be identical (within ±5%) to a populated-user query on the same `uuid` (no extra DB roundtrip for a separate `prod.usuarios` existence check; the FK existence of zero `prod.login` rows IS the existence check).

The audit log MUST record the attempt (KD-LOGIN-02 SELECT-only still permits structured log emission for security audit; the handler MUST NOT log `prod.login` rows themselves — only the request metadata: actor UUID, target UUID, timestamp, response size). The pgcode / internal error code MUST NEVER appear in the response body, headers, or info+ logs (XR6 Layer 5 redaction).

**Rationale**: Same rationale as F1.2 `GET /auth/me` R-F1.2-10 + R-F1.2-11 (anti-enumeration by response code differential). Returning `404` for an unknown `uuid_usuario` would let an attacker enumerate valid user UUIDs by comparing `404` vs `200`. The response-time parity constraint prevents a SECOND enumeration vector: an attacker who measures response time could distinguish "user exists but zero rows" from "user does not exist" if the handler issued an extra DB roundtrip for an existence check. By relying on the FK existence of zero `prod.login` rows as the implicit existence check, the handler runs exactly the same query (1 SELECT) for both cases, and the response time is identical. KD-LOGIN-02 AST walk still applies to the empty path (no UPDATE/DELETE/COMMIT).

**Source**: F1.2 R-F1.2-10 / R-F1.2-11 (anti-enumeration rationale — `openspec/specs/operations/spec.md` REQ-OPS-029 mirror); `openspec/specs/operations/spec.md` line 4034-4041 (REQ-OPS-100 empty-branch precedent at F1.14 — DEC-LOGIN-08 mirror); `backend/packages/parkos_core/src/parkos_core/models/L_S/login.py:33-74` (Login ORM FK to `prod.usuarios`); `backend/packages/parkos_core/src/parkos_core/models/V/usuarios.py` (Usuarios ORM — F1.15 reads `uuid` only for optional existence check; SKIPPED per DEC-LOGIN-08); KD-LOGIN-02 AST walk `tests/static/test_login_historico_read_only.py` (extends to the empty path).

**Scenario 1: Zero rows for an EXISTING user (user exists but never authenticated) — 200 with `items=[]`**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` that EXISTS in `prod.usuarios` (FK row present) but has ZERO rows in `prod.login`
- **When** the handler `GET /api/v1/usuarios/{uuid}/login` is invoked
- **Then** the response MUST be `200 OK` with `LoginHistoricoListResponse{items: [], next_cursor: null}`
- **And** MUST carry `Cache-Control: no-store`
- **And** MUST NOT be `404 Not Found` (the user exists; this is a zero-data response, not a missing-resource response).

**Scenario 2: Zero rows for an UNKNOWN user (anti-enumeration) — 200 indistinguishable from Scenario 1**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` that does NOT exist in `prod.usuarios` (FK row absent) AND has ZERO rows in `prod.login`
- **When** the handler `GET /api/v1/usuarios/{uuid}/login` is invoked
- **Then** the response MUST be `200 OK` with `LoginHistoricoListResponse{items: [], next_cursor: null}`
- **And** MUST carry `Cache-Control: no-store`
- **And** MUST NOT be `404 Not Found` (anti-enumeration — same response shape as Scenario 1 prevents UUID discovery).

**Scenario 3: Response time parity — zero-row response time within ±5% of populated-row response time**
- **Given** two identical KD-3 issuer sessions with `audit_read` permission
- **And** path `uuid_a` with ZERO `prod.login` rows
- **And** path `uuid_b` with 100 `prod.login` rows
- **When** both handlers are invoked with the same `limit=10` query
- **Then** the wall-clock response time for `uuid_a` MUST be within ±5% of the response time for `uuid_b` (no extra DB roundtrip for `prod.usuarios` existence check — DEC-LOGIN-08 evidence-of-no-distinguishable-side-channel)
- **And** the audit log MUST record the attempt for BOTH requests (actor UUID, target UUID, timestamp, response size)
- **And** the audit log MUST NOT include the `prod.login` row contents themselves (KD-LOGIN-02 SELECT-only invariant extends to log emission).

---

### REQ-OPS-105 — XR6 cross-cutting defense in depth (REFERENCE to existing REQ-OPS-XR6)

**Source**: HU-F1.15 (DEC-LOGIN-01 + DEC-LOGIN-02 + DEC-LOGIN-03 + DEC-LOGIN-05 + DEC-LOGIN-09.B + KD-LOGIN-02) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
Given that REQ-OPS-XR6 already exists at `openspec/specs/operations/spec.md:3951` from F1.13, F1.15's `GET /api/v1/usuarios/{uuid}/login` endpoint MUST satisfy all 5 defense-in-depth layers defined in REQ-OPS-XR6, applied as follows:

- **Layer 1 (KD-3 issuer chain + permission gate)** — NEW dedicated router `api/v1/usuarios_login.py` declares `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")` (DEC-LOGIN-02 — same KD-3 chain as F1.14 `sync_estado.py`). Permission gate is `audit_read` (DEC-LOGIN-09.B, pre-seeded per `0002_seed_permisos_canonicos.py:48`). Operador with `audit_read` reads own-branch login history (DEC-LOGIN-03.A); admin cross-branch.
- **Layer 2 (Tenant scope post-V1)** — After resolving `ctx.sucursal_uuid` from the JWT, if `ctx.issuer_prefix == "operador-"` AND `tenant_ctx.sucursal_uuid is not None`, the SQL query MUST be filtered by `login.uuid_sucursal = ctx.sucursal_uuid` at the SQL layer (DEC-LOGIN-03.A — own-branch audit history only). Cross-branch login history is implicitly NOT returned to operador (no rows match the filter → `items=[]`). Admin (`admin-`) bypasses Layer 2 and sees ALL branches. KD-S2 analog from F1.7. The filter is applied at SQL layer via `repo/login_historico.listar_intentos_paginado` — NOT a Python-side post-filter (which would leak row metadata).
- **Layer 3 (KD-LOGIN-01 SELECT-only + KD-LOGIN-02 read-only AST walk)** — The handler invokes ONLY the 1 typed SELECT helper from `repo/login_historico.py` (read-only path). The AST walk `tests/static/test_login_historico_read_only.py` enforces NO `session.execute(update(Login))`, `session.execute(delete(Login))`, `session.execute(text("UPDATE prod.login"))`, `session.execute(text("DELETE FROM prod.login"))`, and NO `await session.commit()` in the handler body. Mirrors F1.10 REQ-OPS-XR1 + F1.11 REQ-OPS-XR4 + F1.12 REQ-OPS-XR5 + F1.13 REQ-OPS-XR6 + F1.14 KD-SYNC-02.
- **Layer 4 (Pydantic `extra='forbid'` + UUID required + `Literal[estado]` + limit validators)** — `LoginHistoricoQueryParams(_Base)` + `LoginIntentoItem(_Base)` + `LoginHistoricoListResponse(_Base)` inherit `extra='forbid'` from `schemas/common.py::_Base` (blocks client smuggling of `actor_uuid`, `computed_at`, `cache_key`, `activo`). `uuid: UUID` is required (Pydantic validator, 422 on malformed). `estado: Literal["exitoso", "fallido", "cerrado"]` enforces the 3-value domain at the type level (DEC-LOGIN-10). `limit: int = 10` with `ge=1, le=100` validators (DEC-LOGIN-04). `cursor: str | None = None` (base64-encoded JSON from previous page's next_cursor).
- **Layer 5 (Handler 200/422/403/400 mapping + `Cache-Control: no-store`)** — Every response (200 + 4xx + 5xx) on `GET /api/v1/usuarios/{uuid}/login` carries `Cache-Control: no-store`. Success: `apply_no_store_header(response)`. Error: `HTTPException(headers=no_store_headers())`. Typed exceptions map as follows: `UuidUsuarioInvalidError` → 422 `uuid_usuario_invalid` (Pydantic validator, Layer 4); `CursorInvalidError` → 400 `cursor_invalid` (base64 decode failure, Layer 4); `TenantScopeViolationError` → 403 `tenant_scope_violation` (handler Layer 2, enforced via SQL filter — DEC-LOGIN-03.A); `PermissionDeniedError` → 403 `permission_denied` (`require_permission` Layer 1). The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

F1.15 MUST NOT create a new cross-cutting requirement (XR). REQ-OPS-XR6 is canonical and applies to F1.15 by reference. `openspec/changes/hu-f1-15-login-historico/design.md` §13 (Cross-Cutting Requirements) MUST reference REQ-OPS-XR6 and the 5 layer mapping above. `openspec/changes/hu-f1-15-login-historico/tasks.md` §10 (Test Plan) MUST include the `test_login_historico_read_only.py` AST walk as a Layer 3 verification step.

**Rationale**: XR6 is the canonical defense-in-depth contract for cross-cutting concerns. Creating a new XR (XR7) for F1.15 would duplicate the 5-layer contract and fragment the review surface. By referencing XR6, F1.15 inherits the testable invariants (AST walks, `extra='forbid'`, `Cache-Control: no-store`, KD-3 issuer chain, permission gate) without redefining them. Each layer is independently testable; failure of any one layer is contained by the other four (defense in depth principle). The Layer 2 SQL-side filter (DEC-LOGIN-03.A) prevents operator cross-branch data leaks while preserving the same canonical response shape as admin — no client-side discriminator needed.

**Source**: `openspec/specs/operations/spec.md` line 3951 (REQ-OPS-XR6 canonical from F1.13); `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header` — Layer 5 helper); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` — Layer 4 base); `backend/packages/parkos_core/src/parkos_core/auth/jwt_issuer_guard.py` (`requires_issuer` factory — Layer 1 dep); `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` (`get_tenant_ctx` — Layer 2 dep); F1.7 KD-S2 (Layer 2 precedent); F1.9 REQ-OPS-058 (factura_pagos immutability); F1.10 REQ-OPS-XR1 (single-commit AST walk precedent); F1.11 REQ-OPS-XR4 (insert-only AST walk precedent); F1.12 REQ-OPS-XR5 (5-layer defense precedent); F1.13 REQ-OPS-XR6 (caja-specific 5-layer defense precedent at `operations/spec.md:3951`); F1.14 KD-SYNC-02 (read-only AST walk precedent for `sync_estado`); `backend/packages/parkos_core/migrations/versions/0002_seed_permisos_canonicos.py:48` (`audit_read` pre-seeded — DEC-LOGIN-09.B Layer 1 anchor).

**Scenario 1: operador with `audit_read` + own branch — 200 OK (Layer 1 + Layer 2 PASS)**
- **Given** an operador role granted `audit_read` permission via `prod.permisos_usuario`
- **And** `ctx.sucursal_uuid=:s` matching at least one `prod.login.uuid_sucursal` for the requested `uuid`
- **When** the operador invokes `GET /api/v1/usuarios/{uuid}/login?limit=10`
- **Then** Layer 1 MUST pass (KD-3 issuer `operador-` accepted + `audit_read` permission granted)
- **And** Layer 2 MUST pass (own-branch SQL filter `login.uuid_sucursal = ctx.sucursal_uuid` — DEC-LOGIN-03.A)
- **And** Layer 3 MUST execute exactly 1 SELECT query against `prod.login` (KD-LOGIN-01)
- **And** Layer 4 MUST validate the Pydantic schema (`uuid` is a valid UUID, no extra fields)
- **And** Layer 5 MUST return `200 OK` with `Cache-Control: no-store`.

**Scenario 2: operador with `audit_read` + NO own-branch rows (cross-branch only) — 200 with `items=[]` (Layer 2 filter applied at SQL layer)**
- **Given** an operador role granted `audit_read` permission
- **And** `ctx.sucursal_uuid=:s_other` (operator's branch is `:s_other`)
- **And** the requested `uuid` has `prod.login` rows ONLY in branches DIFFERENT from `:s_other` (no `uuid_sucursal = :s_other` matches)
- **When** the operador invokes `GET /api/v1/usuarios/{uuid}/login`
- **Then** Layer 1 MUST pass (issuer + permission OK)
- **And** Layer 2 MUST apply the SQL filter `login.uuid_sucursal = :s_other` — NO cross-branch rows returned
- **And** the response MUST be `200 OK` with `LoginHistoricoListResponse{items: [], next_cursor: null}` (anti-enumeration, DEC-LOGIN-08)
- **And** MUST carry `Cache-Control: no-store`
- **And** MUST NOT be `403 tenant_scope_violation` (the user exists; only the branch filter excludes the rows — same as the empty-user contract).

**Scenario 3: operador with `audit_read` DENIED (no permission grant) — 403 `permission_denied` (Layer 1 short-circuits)**
- **Given** an operador role WITHOUT `audit_read` permission (only `emitir_factura` granted)
- **When** the operador invokes `GET /api/v1/usuarios/{uuid}/login`
- **Then** Layer 1 MUST reject with `403 Forbidden` and body `{"error": "permission_denied"}` and `Cache-Control: no-store`
- **And** Layer 2 (tenant scope) MUST NOT be evaluated (Layer 1 short-circuits first)
- **And** NO DB queries MUST execute (handler body unreachable).

**Scenario 4: admin with `audit_read` — 200 OK with cross-branch rows (Layer 2 bypassed)**
- **Given** an admin role granted `audit_read` permission via `prod.permisos_usuario`
- **And** the requested `uuid` has `prod.login` rows across MULTIPLE branches
- **When** the admin invokes `GET /api/v1/usuarios/{uuid}/login`
- **Then** Layer 1 MUST pass (KD-3 issuer `admin-` accepted + `audit_read` permission granted)
- **And** Layer 2 MUST be bypassed (admin bypasses the `uuid_sucursal` filter per DEC-LOGIN-03.A — sees ALL branches)
- **And** the response MUST be `200 OK` with all rows from all branches in `(timestamp_evento DESC, uuid ASC)` order
- **And** MUST carry `Cache-Control: no-store`.

**Scenario 5: All responses (200 + 4xx + 5xx) carry `Cache-Control: no-store`**
- **Given** any response from `GET /api/v1/usuarios/{uuid}/login` (success or failure)
- **When** the response is emitted
- **Then** the `Cache-Control: no-store` header MUST be present on `200 OK`
- **And** MUST be present on `400 cursor_invalid` / `403 tenant_scope_violation` / `403 permission_denied` / `422 uuid_usuario_invalid`
- **And** MUST be present on any uncaught 5xx (defense in depth)
- **And** the response body MUST NOT contain `pgcode`, `pgerror`, or `pgmessage` keys (XR6 Layer 5 redaction).

**Scenario 6: Read-only AST walk — handler source contains ZERO UPDATE/DELETE on `Login` and ZERO `commit`**
- **Given** the source file `api/v1/usuarios_login.py` containing `get_login_historico`
- **When** `tests/static/test_login_historico_read_only.py` runs
- **Then** the AST walk MUST assert ZERO occurrences of `update(Login)` or `delete(Login)` or `session.execute(text("UPDATE prod.login"))` or `session.execute(text("DELETE FROM prod.login"))` in the handler body (KD-LOGIN-01 + KD-LOGIN-02)
- **And** MUST assert ZERO occurrences of `await session.commit()` in the handler body (GET is naturally commit-free).

---
### REQ-OPS-106 — LoginForm con validación RHF+Zod inline (DEC-F3.1-02 + DEC-F3.1-06)

**Source**: HU-F3.1 (`plan.md:1278, 1289, 1291` + `DEC-F3.1-02` Container/Presentational split + `DEC-F3.1-06` Zod local) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<LoginForm>` MUST renderizar dos campos de formulario (`email` + `password`) con validación inline React Hook Form + Zod (`@hookform/resolvers/zod`) usando el schema `z.object({ email: z.string().email(), password: z.string().min(8) })`. Los mensajes de validación (`validation.email.invalid`, `validation.password.minLength`, `validation.required`) MUST mostrarse inline en cada `FormField` vía `<FormMessage />` con `role="alert"` (atributo semántico del componente shadcn `Form`). El botón submit MUST estar deshabilitado (`disabled={!form.formState.isValid || isSubmitting}`) hasta que ambos campos pasen la validación Zod. El componente MUST cumplir WCAG 2.1 AA — `FormField` con `aria-invalid={!!error}`, label asociado via `htmlFor` (componente `FormLabel` shadcn), tab order secuencial.

**Rationale**: El operador necesita feedback inmediato sobre la validez de sus credenciales antes de tocar el backend. RHF + Zod evita renders innecesarios (re-render solo en `onChange` blur/submit) y mantiene la lógica de validación declarativa (vs imperativa). La validación local es UX — la validación final la hace el backend via Pydantic (`schemas/auth.py::LoginRequest` `EmailStr + StringConstraints min_length:8`); si hay mismatch (R6 risk), el cliente recibe 422 con detalle.

**Source**: `apps/electron-sucursal/package.json:23, 45, 51` (`react-hook-form@^7.53.0` + `zod@^3.23.8` + `@hookform/resolvers@^3.9.0` — F2.1 baseline); `apps/electron-sucursal/src/renderer/components/ui/{form,input,button}.tsx` (F2.1 shadcn primitives); `backend/packages/parkos_core/src/parkos_core/schemas/auth.py::LoginRequest` (Pydantic anchor).

**Scenario 1: Happy path — form válido habilita submit**
- **Given** el operador accede a `/login` sin sesión activa (`useAuthStore.getState().accessToken === null`)
- **And** los dos campos están vacíos (`email: ''`, `password: ''`)
- **When** el operador tipea `email = "operador@sucursal-1.parkos.local"` (formato válido) y `password = "Pass1234word"` (8+ chars)
- **Then** el `<Button type="submit">` MUST estar habilitado (`disabled === false`)
- **And** NO MUST haber mensajes de validación visibles
- **And** el form MUST pasar `formState.isValid === true` (RHF + Zod resolver).

**Scenario 2: Email formato inválido — `validation.email.invalid` inline + submit deshabilitado**
- **Given** el operador tipea `email = "no-es-email"` y `password = "Pass1234word"`
- **When** el operador hace blur en `email` (RHF dispara validación)
- **Then** `<FormMessage name="email">` MUST mostrar el texto exacto de la key i18n `validation.email.invalid` (`auth.json` — pre-F3.1 NO existe; F3.1 T1 agrega las 5 keys de validation)
- **And** el FormField MUST setear `aria-invalid="true"` en el `<Input>`
- **And** el `<Button type="submit">` MUST estar deshabilitado (`disabled === true`).

**Scenario 3: Password < 8 caracteres — `validation.password.minLength` inline**
- **Given** el operador tipea `email = "operador@sucursal-1.parkos.local"` y `password = "123"` (3 chars)
- **When** el operador hace blur en `password`
- **Then** `<FormMessage name="password">` MUST mostrar `validation.password.minLength`
- **And** el FormField MUST setear `aria-invalid="true"`
- **And** el submit MUST estar deshabilitado.

**Scenario 4: Submit con campos vacíos — `validation.required` inline + form NO submitea**
- **Given** el operador accede a `/login` y submita el form sin tipear nada (click submit con campos vacíos)
- **When** `onSubmit` se dispara
- **Then** RHF MUST abortar submit (resolver detecta campos vacíos)
- **And** ambos FormMessages MUST show `validation.required`
- **And** NO MUST haber network request al backend.

---

### REQ-OPS-107 — POST /auth/login con `credentials:'include'` + cookie httpOnly round-trip (DEC-F3.1-03 + DEC-F3.1-04 + DEC-F3.1-05)

**Source**: HU-F3.1 (`plan.md:1279, 1284` + `DEC-F3.1-03` credentials include + `DEC-F3.1-04` HTTP no IPC + `DEC-F3.1-05` fetch raw no parkosFetch) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El cliente MUST enviar `POST /api/v1/auth/login` con `credentials: 'include'` explícito en el `fetch` para que el navegador ACEPTE la cookie `parkos_session` (httponly+secure+samesite=lax) y la ENVÍE en requests subsiguientes (`GET /auth/me`). El `fetch` MUST ser raw (no `parkosFetch`) porque (a) NO queremos `Authorization: Bearer` pre-login (no existe token), (b) queremos leer `Retry-After` header en 429, (c) queremos `credentials:'include'` explícito sin que parkosFetch intercepte. La request MUST llevar `Content-Type: application/json` y body `{"email": "...", "password": "..."}` (password min 8 chars, validado Zod localmente en REQ-OPS-106). El cliente MUST aceptar la response 200 con body `TokenPair{access_token, refresh_token, token_type, expires_in}` (backend `auth.py:303-307` + `schemas/auth.py::TokenPair`).

**Rationale**: La cookie httpOnly es el canal primario de autenticación cross-request (no el access_token en memoria, que se usa para header `Authorization: Bearer`). `credentials:'include'` es mandatory — sin esto, el navegador setea la cookie en la response pero NO la persiste en el cookie jar, y el siguiente `/auth/me` viaja sin auth y el backend responde 404 (`auth.py:454-458`). El raw fetch (no parkosFetch) preserva la semántica "login es anónimo, todo lo demás es autenticado" (DEC-F3.1-05).

**Source**: `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-307` (POST /auth/login endpoint); `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:291-299` (cookie set_cookie call con httponly+secure+samesite=lax); `backend/packages/parkos_core/src/parkos_core/schemas/auth.py::LoginRequest` + `TokenPair`; `apps/ui-kit/src/fetch/parkosFetch.ts:105-109` (`isLoginEndpoint = url.includes('/auth/login')` — Idempotency-Key skip); `apps/electron-sucursal/src/features/auth/api/loginApi.ts` (T2 nuevo, fetch raw).

**Scenario 1: Login OK con credenciales válidas — 200 + cookie persistida + TokenPair body**
- **Given** el operador submita `email = "operador@sucursal-1.parkos.local"` + `password = "Pass1234word"` (válido)
- **When** `loginApi.postLogin(email, password)` ejecuta `fetch('/api/v1/auth/login', {method:'POST', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email, password})})`
- **Then** el backend MUST responder `200 OK` con `Content-Type: application/json` + `Set-Cookie: parkos_session=<jwt>; HttpOnly; Secure; SameSite=Lax; Max-Age=3600; Path=/`
- **And** el body MUST ser `TokenPair{access_token, refresh_token, token_type: "Bearer", expires_in: 3600}`
- **And** el navegador MUST persistir la cookie `parkos_session` (httponly bloquea JS lectura; cookie jar la mantiene hasta Max-Age).
- **And** el cliente MUST retornar el `TokenPair` parseado al caller (Login.tsx → REQ-OPS-110 setTokens).

**Scenario 2: Request sin `credentials:'include'` — cookie se setea pero NO se persiste (anti-regression test)**
- **Given** un hipotético cliente que envía `fetch('/api/v1/auth/login', {method:'POST'})` SIN `credentials:'include'`
- **When** el backend responde 200 con `Set-Cookie parkos_session`
- **Then** el navegador MUST NO persistir la cookie (Fetch spec: omit credentials = no cookie jar write)
- **And** el siguiente `GET /auth/me` MUST NO llevar la cookie
- **And** el backend MUST responder 404 (`auth.py:454-458`)
- **And** el test e2e MUST validar que `loginApi.postLogin` SIEMPRE incluye `credentials:'include'` (no se omite accidentalmente).

---

### REQ-OPS-108 — 401 → `errors.invalidCredentials` único anti-enumeración (DEC-F3.1-08)

**Source**: HU-F3.1 (`plan.md:1281` + `DEC-F3.1-08` anti-enumeration UI message) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
Cuando el backend responde `401 Unauthorized` con body `{"error": "invalid_credentials", ...}` (causa: email desconocido O password incorrecta — indistinguibles por anti-enumeration backend en `auth.py:159-191, 248-251`), el frontend MUST mostrar un único mensaje `<p role="alert">{t('invalidCredentials')}</p>` con texto exacto de `auth.json:9` (`invalidCredentials`). MUST NO haber distinción visible entre "email no existe" / "password incorrecta" / "cuenta deshabilitada" — esto previene enumeración de usuarios válidos por differential analysis. El componente `<LoginForm>` MUST renderizar el mensaje en `<FormMessage>` o `<p role="alert">` arriba del submit button, con `aria-live="polite"` o `role="alert"` para screen readers.

**Rationale**: Anti-enumeración es cross-layer (backend + frontend). El backend ya colapsa 401 a `errors.invalid_credentials` único (`auth.py:159-191, 248-251`). El frontend matchea — no debe filtrar información que el backend colapsó. Esto evita el vector de ataque "POST /auth/login con emails conocidos vs aleatorios → comparar respuestas para inferir emails válidos".

**Source**: `apps/electron-sucursal/src/renderer/i18n/locales/auth.json:9` (`invalidCredentials` key — pre-F3.1 existe per `exploration.md §2.9`); `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:159-191, 248-251` (anti-enumeration backend); R1..R5 risks en `exploration.md §7` (timing attacks mitigados por bcrypt cost).

**Scenario 1: 401 con email desconocido — mensaje único `invalidCredentials`**
- **Given** el operador tipea `email = "fantasma@sucursal.local"` (no existe en `prod.usuarios`) + `password = "Pass1234word"`
- **And** el backend responde 401 con `{"error": "invalid_credentials", ...}` (auth.py:188-191)
- **When** `loginApi.postLogin` parsea la response y `Login.tsx` setea `error = t('invalidCredentials')`
- **Then** el componente MUST renderizar `<p role="alert">{t('invalidCredentials')}</p>` ("Credenciales inválidas" en español neutro)
- **And** el componente MUST NO renderizar "Email no encontrado" ni "Usuario inexistente" (anti-enumeration).

**Scenario 2: 401 con email válido + password incorrecta — MISMO mensaje `invalidCredentials`**
- **Given** el operador tipea `email = "operador@sucursal-1.parkos.local"` (existe) + `password = "wrong-pass"` (incorrecta)
- **And** el backend responde 401 con `{"error": "invalid_credentials", ...}` (auth.py:248-251)
- **When** `loginApi.postLogin` parsea la response
- **Then** el componente MUST renderizar el MISMO texto que Scenario 1 (`t('invalidCredentials')`)
- **And** el componente MUST NO renderizar "Password incorrecta" ni "Credenciales erróneas — verifique su contraseña" (mismo shape, indistinguible).

---

### REQ-OPS-109 — 429 → `errors.lockout` con `Retry-After` header parseado (DEC-F3.1-08)

**Source**: HU-F3.1 (`plan.md:1283` + `DEC-F3.1-05` fetch raw para Retry-After + `DEC-F3.1-08` lockout forward hook) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
Cuando el backend responde `429 Too Many Requests` con `Retry-After: <segundos>` header (cuando `count(fallido in window) >= max_intentos_login` per `configuracion_seguridad` configurable per-branch, `auth.py:219-228`), el cliente MUST emitir `AccountLockedError(retryAfterSeconds)` donde `retryAfterSeconds = Number(response.headers.get('Retry-After') ?? '0')`. El frontend MUST mostrar `<p role="alert">{t('lockout')}</p>` con texto de `auth.json:8` (`lockout` — "Cuenta bloqueada. Intenta de nuevo en N minutos." donde N = `Math.ceil(retryAfterSeconds / 60)`). F3.1 MUST NO implementar countdown UI (forward hook a F3.2 — `useCountdown` hook + 429 disable form + countdown visual). El componente MUST mantener el form deshabilitado hasta que `retryAfterSeconds` expire, pero SIN countdown visual en F3.1 (texto estático "Intenta de nuevo en N minutos.").

**Rationale**: F3.1 entrega el catch + surface del 429 (REQ-OPS-109). F3.2 (HU-F3.2) entrega el countdown UI (forward hook declarado en `proposal.md §14` + `exploration.md §15`). El split es por atomicidad: F3.1 NO depende de F3.2 para shippear; F3.2 consume `AccountLockedError` que F3.1 emite.

**Source**: `apps/electron-sucursal/src/renderer/i18n/locales/auth.json:8` (`lockout` key); `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:219-228` (429 + Retry-After); `backend/packages/parkos_core/src/parkos_core/models/V/configuracion_seguridad.py` (max_intentos_login + minutos_bloqueo_login — modelo_datos_er.mmd:270-289); `apps/electron-sucursal/src/features/auth/api/loginApi.ts` (T2 — error mapping custom).

**Scenario 1: 429 + Retry-After: 600 — lockout estático "10 minutos"**
- **Given** el operador agotó `max_intentos_login` en `configuracion_seguridad` (default 5 intentos)
- **And** el operador tipea credenciales (válidas o inválidas — el backend bloquea cualquiera)
- **When** el backend responde `429 Too Many Requests` con `Retry-After: 600` header (10 minutos)
- **Then** `loginApi.postLogin` MUST parsear `Number(response.headers.get('Retry-After') ?? '0')` = 600
- **And** MUST throw `AccountLockedError(retryAfterSeconds: 600)`
- **And** el componente MUST mostrar `<p role="alert">{t('lockout')}</p>` ("Cuenta bloqueada. Intenta de nuevo en 10 minutos.")
- **And** MUST NO mostrar countdown visual (forward hook F3.2).

**Scenario 2: 429 sin `Retry-After` header — fallback `retryAfterSeconds: 0` + mensaje genérico**
- **Given** una response 429 hipotética SIN `Retry-After` header (anomaly del backend)
- **When** `loginApi.postLogin` parsea la response
- **Then** `retryAfterSeconds` MUST ser 0 (fallback `?? '0'`)
- **And** `AccountLockedError(0)` MUST emitirse
- **And** el componente MUST mostrar `t('lockout')` SIN "N minutos" (texto fallback).

---

### REQ-OPS-110 — `useAuthStore.setTokens(access, refresh, expires_in)` atómico post 200 OK (DEC-F3.1-07)

**Source**: HU-F3.1 (`plan.md:1280, 1292` + `DEC-F3.1-07` hidratación transaccional) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
Cuando `loginApi.postLogin` retorna el `TokenPair` parseado de 200 OK, el componente `<LoginPage>` MUST llamar `useAuthStore.getState().setTokens(access_token, refresh_token, expires_in)` ANTES de cualquier otra acción (incluyendo redirect o re-render). El state de `useAuthStore` MUST pasar de `{accessToken: null, refreshToken: null, expiresAt: null}` a `{accessToken: <jwt>, refreshToken: <jwt>, expiresAt: <ISO 8601>}` atómicamente (Zustand `setState` es síncrono). El estado MUST persistir vía `bridge.authStore.{set}` IPC a `electron-store` (F2.2 `DEC-FETCH-08` — `partialize` whitelist persiste SOLO `{accessToken, refreshToken, expiresAt}`). Tras `setTokens`, `useAuth()` SWR hook MUST detectar el key change (`null` → `'/auth/me'`) y disparar `parkosFetch('/auth/me')` con `Authorization: Bearer <new_access>` (header automático per `parkosFetch.ts:92-96`) + cookie `parkos_session` auto-enviada (browser cookie jar).

**Rationale**: Hidratación atómica garantiza que el operador nunca llega a `/` con `accessToken: null` mientras `useAuth()` está hidratando. Zustand `setState` síncrono elimina la race condition entre setTokens y SWR key change (R4 risk en `exploration.md §7`).

**Source**: `apps/ui-kit/src/store/authStore.ts:1-129` (F2.2 — `setTokens` + `clear` + `partialize`); `apps/ui-kit/src/hooks/useAuth.ts:1-87` (F2.2 — SWR key `accessToken ? '/auth/me' : null`); `apps/ui-kit/src/fetch/parkosFetch.ts:92-96` (Authorization Bearer injection).

**Scenario 1: 200 OK → setTokens atómico + persist electron-store**
- **Given** `loginApi.postLogin` retorna `TokenPair{access_token: "<jwt>", refresh_token: "<jwt>", token_type: "Bearer", expires_in: 3600}`
- **When** `<LoginPage>` ejecuta `useAuthStore.getState().setTokens("<access>", "<refresh>", 3600)`
- **Then** `useAuthStore.getState().accessToken` MUST ser `<access>` (no null, no previous value)
- **And** `useAuthStore.getState().refreshToken` MUST ser `<refresh>`
- **And** `useAuthStore.getState().expiresAt` MUST ser `<now + 3600s>` en ISO 8601 UTC
- **And** `bridge.authStore.set({accessToken, refreshToken, expiresAt})` MUST invocarse vía IPC (F2.2 wireado)
- **And** `electron-store` MUST persistir el state (visible post Electron app restart).

**Scenario 2: SWR key change → useAuth() re-fetcha `/auth/me` con Bearer + cookie**
- **Given** `setTokens` se ejecutó (state actualizado)
- **When** React re-renderiza `<LoginPage>` con el nuevo `useAuth()` state
- **Then** SWR MUST detectar `accessToken !== null` y disparar `parkosFetch('/auth/me')` con:
  - `Authorization: Bearer <access>` (header automático)
  - `Cookie: parkos_session=<jwt>` (browser cookie jar auto-envía)
- **And** `useAuth()` MUST retornar `{user, sucursal, sucursalesPermitidas, permisos, expiresAt, isAuthenticated: true, isLoading: true}` (loading durante el fetch).

---

### REQ-OPS-111 — Redirect a `/` post-`useAuth().isAuthenticated && data?.user && !isLoading` (DEC-F3.1-07)

**Source**: HU-F3.1 (`plan.md:1302` + `DEC-F3.1-07` hidratación transaccional + `DEC-F3.1-09` AuthGuard deferred) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<LoginPage>` MUST ejecutar `navigate('/')` SOLO cuando `useAuth()` retorna `{isAuthenticated: true, isLoading: false, data: {user: <UserItem>, sucursal: <SucursalItem>, sucursalesPermitidas: <SucursalItem[]>, permisos: <string[]>, expiresAt: <ISO 8601>}}`. El `useEffect` MUST tener deps `[isAuthenticated, data?.user, isLoading]` (R4 race mitigation). MUST NO navegar si `data?.user === undefined` (in-flight SWR) ni si `isLoading === true` (transición). Esto previene el flash de "sesión no iniciada" en el destino — F3.3+ dashboards dependen de `useAuth().user.sucursal` y renderizarían con `user: null` durante el primer render. El componente MUST NO implementar AuthGuard (forward hook F3.3+ — `parkos:auth:cleared` event listener que dispara `navigate('/login?next=...')`); F3.1 Login page es standalone (entry point, no requiere auth-guard).

**Rationale**: Hidratación transaccional es critical para UX profesional. El operador llega a `/` con sesión + user + sucursal + permisos TODOS resueltos (F3.3+ lee `user.sucursal` para abrir turno).

**Source**: `apps/ui-kit/src/hooks/useAuth.ts:67-69` (`parkos:auth:cleared` event emission); `apps/electron-sucursal/src/renderer/App.tsx:1-37` (F2.1 router + F2.3 StatusBar mount — F3.1 T3 MODIFY +5 LOC para agregar `<Route path="/login">`); react-router-dom@^6.27.0 `useNavigate`.

**Scenario 1: Hidratación completa → navigate('/') atómico**
- **Given** el operador completó `setTokens` (REQ-OPS-110) + `useAuth()` SWR resolvió `/auth/me` con 200 OK
- **And** `useAuth()` retorna `{isAuthenticated: true, isLoading: false, data: {user: {uuid, email, nombre, apellido, rol}, sucursal: {uuid, nombre, prefijo_nombre}, sucursalesPermitidas: [...], permisos: [...], expiresAt: <ISO>}}`
- **When** el `useEffect` en `<LoginPage>` dispara con deps `[isAuthenticated, data?.user, isLoading]`
- **Then** el componente MUST llamar `navigate('/')`
- **And** el operador MUST llegar a `/` con `useAuth()` ya hidratado (sin flash de "sesión no iniciada").

**Scenario 2: Hidratación en curso — useEffect NO navega**
- **Given** el operador completó `setTokens` (REQ-OPS-110) pero `/auth/me` AÚN no resolvió
- **And** `useAuth()` retorna `{isAuthenticated: true, isLoading: true, data: undefined}`
- **When** el `useEffect` dispara con deps `[isAuthenticated, data?.user, isLoading]`
- **Then** el componente MUST NO llamar `navigate('/')` (falta `data?.user`)
- **And** el operador MUST permanecer en `/login` viendo un spinner o estado de loading.

---

### REQ-OPS-112 — WCAG 2.1 AA compliance via axe-core 0 violaciones (RNF-022)

**Source**: HU-F3.1 (`plan.md:1295` + `RNF-022` WCAG 2.1 AA — `docs/01-requisitos/no-funcionales.md:126` + `DEC-F3.1-01` feature folder + `DEC-F3.1-02` Container/Presentational con a11y) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<LoginForm>` MUST pasar el scan `axe-core` (vía `@axe-core/playwright` extension) con 0 violaciones de WCAG 2.1 AA. Cobertura mandatory: (1) labels asociados via `htmlFor` (componente shadcn `FormLabel` resuelve automáticamente), (2) `aria-invalid="true"` en `<Input>` cuando hay error de validación (`formState.errors.email` o `.password`), (3) `aria-describedby` apuntando a `FormMessage` (componente shadcn `FormControl` + `FormMessage` linked via `useFormField`), (4) `role="alert"` en mensajes de error (`FormMessage` shadcn), (5) tab order secuencial (email → password → submit), (6) contraste de color mínimo 4.5:1 (CSS tokens de `apps/ui-kit/src/tokens.ts` — F2.1 baseline), (7) focus visible en inputs (CSS `focus-visible` ring). El e2e test `e2e/auth/login.spec.ts` MUST incluir un test `axe-core scan on /login` que ejecute el analyzer post-render del form.

**Rationale**: RNF-022 (`docs/01-requisitos/no-funcionales.md:126`) exige WCAG 2.1 AA compliance para todas las pantallas transaccionales. Login es la primera pantalla post-Fase 2 — setea el patrón a11y para Fase 3 entera (F3.2, F3.3, etc.).

**Source**: `apps/electron-sucursal/package.json:55-56` (`@playwright/test@^1.48.0` + `@axe-core/playwright@^4.10.0` — F2.1 baseline); `docs/01-requisitos/no-funcionales.md:126` (RNF-022 anchor); `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` (F2.1 axe-core pattern precedent — F3.1 replica el patrón en `e2e/auth/login.spec.ts`).

**Scenario 1: axe-core scan en `<LoginForm>` — 0 violaciones**
- **Given** el operador accede a `/login` y `<LoginForm>` renderiza completamente
- **When** `e2e/auth/login.spec.ts::test_axe_core_login` ejecuta `new AxeBuilder({page}).analyze()` con tags `wcag2a, wcag2aa, wcag21a, wcag21aa`
- **Then** el array `result.violations` MUST estar vacío (length === 0)
- **And** el test MUST pasar verde (no skip en CI).

**Scenario 2: Form con error — aria-invalid + role="alert" + axe-core 0 violaciones**
- **Given** el operador tipea `email = "no-es-email"` y dispara blur (REQ-OPS-106 Scenario 2)
- **And** `<FormMessage>` renderiza `validation.email.invalid` con `role="alert"`
- **And** el `<Input>` tiene `aria-invalid="true"`
- **When** el scan axe-core re-ejecuta post-error
- **Then** MUST haber 0 violaciones adicionales (axe-core valida que aria-invalid + role="alert" juntos pasan WCAG 2.1 AA).

**Scenario 3: Tab order secuencial email → password → submit**
- **Given** el operador accede a `/login`
- **When** el operador presiona Tab 3 veces desde el body
- **Then** el foco MUST pasar por: (1) `<Input name="email">`, (2) `<Input name="password">`, (3) `<Button type="submit">`
- **And** el orden MUST ser el document order (no `tabindex` overrides).

---

## Modified Capabilities

- `backend/pyproject.toml` — adds the pytest stack and coverage
  configuration (REQ-OPS-001, REQ-OPS-002).
- `openspec/config.yaml::testing.strict_tdd` — flipped from `false` to
  `true` (D9).
- `.github/workflows/ci.yml` — adds the AST checks + coverage gate
  (REQ-OPS-011).
- `tests/conftest.py` — adds `make_spec`, `VFixtureFactory`, the
  branch-flavored session fixture, and the natural-key invariant fixture
  (REQ-OPS-005, REQ-OPS-009, REQ-OPS-015).
- `openspec/scripts/check_catalog_drift.py` — gains rules 4-6 (direction
  derivation, `depends_on` derivation, DAG assertion) and the corrected
  46/3/5/54 counts (REQ-OPS-003).
- `parkos_core/jobs/sync_cloud.py` — the apply loop gains the
  skip-not-fail branch for out-of-catalog tables (REQ-OPS-014).
- `backend/packages/parkos_core/src/parkos_core/api/v1/empresa.py` — handler dedicado
  `@router.get("")` registrado **antes** del bloque `_mount_empresa("tarifas-sucursal", …)`
  (líneas 142-149). Factory `make_router` intacto (REQ-OPS-019).
- `backend/packages/parkos_core/src/parkos_core/schemas/empresa.py` — `TarifasSucursalFilter`
  agrega `vigente_en: datetime | None = None` después del último campo existente (línea 309).
  `extra='forbid'` heredado preservado (REQ-OPS-021).
- `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (NUEVO) —
  helper puro `list_tarifas_vigentes` con predicado bi-temporal extraído como constante
  reutilizable `bitemporal_vigente_predicate` (REQ-OPS-018, REQ-OPS-020).
- `backend/tests/unit/test_tarifas_vigente_en.py` (NUEVO) — 4 RED-then-GREEN tests
  cubriendo las 4 ramas del OR bi-temporal (default `now(UTC)`, pasado, futuro,
  fuera-de-ventana) + tests de tz normalization + cursor compat + coexistencia factory
  (REQ-OPS-017, REQ-OPS-018, REQ-OPS-019).
- `backend/tests/integration/test_tarifas_vigente_en_db.py` (NUEVO) — DB-backed contra
  `pg_engine` real (`parkos-postgres:16-pgpartman`).
- `backend/packages/parkos_core/migrations/versions/0023_unique_active_sesion_per_user.py` (NUEVO) — pre-flight `DO $$` que aborta con `RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation'` si hay `prod.sesion` con `timestamp_cierre IS NULL` agrupados por `uuid_usuario` con `count(*) > 1`, seguido de `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS prod.uq_prod_sesion_one_active_per_user ON prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL`. `down_revision = "0022_create_calcular_cotizacion"` (REQ-OPS-026).
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` (MODIFICAR) — handler dedicado `@router.get("/sesion/me")` registrado **antes** del bloque `include_router(make_router(resource="sesion", write_enabled=False, ...))`; filtros `uuid_usuario == ctx.actor_uuid AND timestamp_cierre.is_(None)`; ORDER BY `timestamp_apertura DESC NULLS LAST LIMIT 1`; 404 `{"error":"sesion_no_active"}`; mapping `SesionAlreadyActive → HTTPException(409, {"error":"sesion_already_active"})` en `open_sesion`; `_sesion_issuer_dep = requires_issuer("operador-", "admin-")` (REQ-OPS-027, REQ-OPS-028, REQ-OPS-029).
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py` (MODIFICAR) — `open_session` captura `IntegrityError` por `pgcode == "23505"` (no `isinstance`, robusto a driver wrapping) y re-emite `raise SesionAlreadyActive(uuid_usuario=...) from exc`. KD-3 BD-only: NO pre-check (REQ-OPS-028).
- `backend/packages/parkos_core/src/parkos_core/repo/sesion_activa.py` (NUEVO) — helper puro async `get_sesion_activa(session, *, actor_uuid) -> Sesion | None` con `ORDER BY timestamp_apertura DESC NULLS LAST LIMIT 1`. Reusable desde tests sin acoplar a HTTP (REQ-OPS-027).
- `backend/packages/parkos_core/src/parkos_core/exceptions.py` (MODIFICAR) — nueva excepción de dominio `SesionAlreadyActive(uuid_usuario: UUID)`. NO contiene pgcode ni mensaje del driver (REQ-OPS-028).
- `backend/tests/unit/test_caja_sesion_me.py` (NUEVO) — 4 tests HTTP (operador con sesión activa → 200; operador sin → 404 `sesion_no_active`; `cliente-` issuer → 403; dos cerradas + una abierta → 200 con la abierta).
- `backend/tests/unit/test_open_session_unique.py` (NUEVO) — 1 test unit con `MagicMock(orig.pgcode="23505")` verifica que `repo/session_cycle.open_session` re-emite `SesionAlreadyActive` y el handler mapea a 409 sin pgcode en body ni headers.
- `backend/tests/static/test_no_write_in_caja_sesion_me.py` (NUEVO) — AST walk (`ast.walk()` case-insensitive) sobre `caja_sesion.get_my_sesion` AND `repo/session_cycle.open_session` rechaza `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` fuera de strings/comentarios. Mismo patrón que F1.8.
- `backend/tests/integration/test_migration_0023_preflight.py` (NUEVO) — 1 test contra `parkos-branch-db` con `PARKOS_DOCKER_TEST=1`; assert que el pre-flight `DO $$` aborta con `integrity_constraint_violation` cuando hay huérfanos.
- `backend/tests/integration/test_caja_sesion_unique_constraint_db.py` (NUEVO) — 2 tests DB: T1 doble INSERT activo mismo `uuid_usuario` → `UniqueViolation` sqlstate `23505`; T2 close + reopen OK (partial predicate excluye la cerrada).
- `backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py` (NUEVO, ~142 LOC) — pre-flight `DO $$` con `_n_ingreso/_n_anul/_n_salidas` + `RAISE NOTICE` 10M informativo / `RAISE EXCEPTION` 50M abort + `CREATE MATERIALIZED VIEW prod.mv_ocupacion_diaria` (NOT EXISTS salidas + NOT EXISTS anulaciones, GROUP BY `uuid_sucursal, uuid_tipo_vehiculo`) + `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS prod.uq_mv_ocupacion_diaria_sucursal_tipo ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo)` (KD-2 mandatory for `REFRESH CONCURRENTLY`) + `GRANT SELECT ON prod.mv_ocupacion_diaria TO parkos_app` + `DROP MATERIALIZED VIEW` downgrade. `revision = "0024_mv_ocupacion_diaria"`, `down_revision = "0023_unique_active_sesion_per_user"`. KD-7 thresholds extraídas como constantes a nivel de módulo `_PREFLIGHT_THRESHOLD_INFO = 10_000_000` + `_PREFLIGHT_THRESHOLD_ABORT = 50_000_000`. (REQ-OPS-032).
- `backend/packages/parkos_core/src/parkos_core/jobs/refresh_mv_ocupacion.py` (NUEVO, ~177 LOC) — `class RefreshMvOcupacionWorker(WorkerRunner)` con `DEFAULT_REFRESH_INTERVAL_S = 10`; `__init__(self, *, session: AsyncSession, refresh_interval_s: int = 10)` con floor `max(5, ...)`; `async def cycle()` ejecuta `REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria` + `commit()` (KD-5 happy path); on `Exception` cae a `REFRESH MATERIALIZED VIEW` plain + `commit()` con log estructurado `refresh_mv_concurrently_failed_fallback` (`exception_class=type(exc).__name__`, NO pgcode, NO repr); inner `refresh_mv_ocupacion_both_branches_failed` log en second failure (no crash, no circuit breaker); post-cycle `await asyncio.sleep(self.refresh_interval_s)` (R1 startup resilience); CLI `main(argv)` con `--refresh-interval-s` y `--database-url`; `python -m parkos_core.jobs.refresh_mv_ocupacion`. Zero modificaciones a `jobs/runner.py` — `worker_base_intact` CI gate. (REQ-OPS-033).
- `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py` (NUEVO, ~128 LOC) — `@dataclass(frozen=True) class OcupacionItemRow` con `@property def disponible(self) -> int: return self.cupo_maximo - self.activos`; `async def get_ocupacion_puros_activos(session: AsyncSession, *, uuid_sucursal: uuid_lib.UUID) -> list[OcupacionItemRow]` con bind-param `text("SELECT … FROM prod.tipos_vehiculo tv LEFT JOIN prod.cantidad_vehiculos_sucursal cvs … LEFT JOIN prod.mv_ocupacion_diaria mv … WHERE tv.vigente_hasta IS NULL ORDER BY tv.tipo")`. **D-F1.5-1** KD-6-respecting: `tipos_vehiculo` drives (LEFT JOIN MV), no MV LEFT JOIN `tipos_vehiculo` — surface every configured tipo even when `activos == 0` (F4.3 `OcupacionStrip` empty-state UX); documentado en source docstring. KD-4 ordering preserved. (REQ-OPS-030).
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (MODIFICAR, +106/-1 LOC) — handler `get_ocupacion` registrado via `@router.get("/ocupacion", response_model=OcupacionResponse, responses={400, 403, 503})`; KD-3 chain: target resolution → `400 missing_sucursal_context` → `403 tenant_scope_violation` (`operador-` cross-tenant) / `403 sucursal_not_permitted` (`admin-` fuera de `claims["sucursales_permitidas"]`); delega SQL a `repo/ocupacion.py::get_ocupacion_puros_activos`; set `response.headers["Cache-Control"] = "no-store"` en respuestas 200. `api/v1/__init__.py` intacto (router montado en línea 143). NO modificaciones a `make_router` (`factory_intact` CI gate). (REQ-OPS-030, REQ-OPS-031).
- `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (MODIFICAR, +38 LOC) — `OcupacionItem(uuid_tipo_vehiculo, tipo, cupo_maximo, activos, disponible)` y `OcupacionResponse(uuid_sucursal, items: list[OcupacionItem], generado_en: datetime)` append tras el bloque F1.8 `CotizarResponse`; ambos heredan `extra='forbid'` de `_Base`; `disponible` puede ser negativo (KD-6 documented inline). (REQ-OPS-030).
- `backend/tests/unit/test_operacion_ocupacion.py` (NUEVO, ~510 LOC, 4 parametrized HTTP-level tests) — T1 operador self 200 con breakdown, T2 operador cross-tenant 403 `tenant_scope_violation`, T3 admin allowed branch 200, T4 admin no-context 400 `missing_sucursal_context`. `httpx.AsyncClient + ASGITransport` + JWT fixtures. (REQ-OPS-030, REQ-OPS-031).
- `backend/tests/integration/test_mv_ocupacion_diaria_db.py` (NUEVO, ~380 LOC, 2 DB integration tests) — T1 `insert_ingreso + REFRESH → activos=1, cupo_maximo=0, disponible=-1` (KD-6 valid negative); T2 `insert_ingreso + insert_salida + REFRESH → empty` (NOT EXISTS predicate verified). Requiere `PARKOS_DOCKER_TEST=1`. (REQ-OPS-030, REQ-OPS-032).
- `backend/tests/integration/test_migration_0024_mv.py` (NUEVO, ~462 LOC, 2 migration pre-flight tests) — T1 `apply with dirty data (5 ingresos, 2 con salidas, 1 anulada) → view + UNIQUE INDEX OK`; T2 `preflight_aborts_on_simulated_50m_rows` via mocked `count(*)`. (REQ-OPS-032).
- `backend/tests/integration/test_refresh_mv_job.py` (NUEVO, ~221 LOC, 2 worker cycle tests) — T1 normal `cycle()` con `AsyncMock(spec=AsyncSession)`; T2 `FeatureNotSupported` on CONCURRENTLY → KD-5 fallback to plain REFRESH + `refresh_mv_concurrently_failed_fallback` log (no pgcode, no `repr(exc)`). (REQ-OPS-033).
- `backend/tests/static/test_no_write_in_ocupacion.py` (NUEVO, ~127 LOC, 1 AST walk test) — `ast.walk()` sobre `api/v1/operacion.py::get_ocupacion` rechazando `INSERT|UPDATE|DELETE|TRUNCATE|MERGE|FOR UPDATE|FOR SHARE` tokens fuera de strings/comentarios. Lockea el read-only contract. (REQ-OPS-030).

- `backend/packages/parkos_core/src/parkos_core/repo/placa.py` (NUEVO, ~30 LOC) — module-level constants `FORMATO_AUTO = r"^[A-Z]{3}[0-9]{3}$"` y `FORMATO_MOTO = r"^[A-Z]{3}[0-9]{2}[A-Z]$"`; `detectar_tipo_vehiculo(placa)` con lazy lookup contra `prod.tipos_vehiculo` (vigente). Server overwrites client `uuid_tipo_vehiculo` (D-HU-F1.6-6). (REQ-OPS-038)
- `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py` (NUEVO, ~180 LOC) — 8 helpers de validación V1..V9 (V1+V2 re-export via `repo/ocupacion.py`; V3 re-export via `repo/tarifas_vigencia.py`; V4 + V6 + V8 + V9 propias) + `validar_kd_forzado` (3 discriminadores KD-FORZADO-01) + `crear_ingreso_evento` thin wrapper de `record_event` + `insertar_alerta_forzado` re-export via `repo/alerta.py`. M1 inline fix (archive): prefix detection alineada con spec `startswith`. M2 inline fix (archive): EXISTS predicate con `s.uuid_sucursal`, `a.estado='ejecutada'`, `a.tipo_anulable IN ('ingreso','salida')`. L1 inline fix (archive): `forzado` kwarg removido de V4 signature. (REQ-OPS-034..041)
- `backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py` (NUEVO, ~50 LOC) — `validar_subscripcion_vigente` con bi-temporal `vigente_hasta IS NULL AND estado='activo' AND fecha_vencimiento >= NOW()`; `resolve_active_subscription_for_exit` extraído verbatim de `api/v1/operacion.py` (F1.5 `bb99e18`); R22 defense-in-depth `WHERE uuid_sucursal == :this_branch`. (REQ-OPS-039)
- `backend/packages/parkos_core/src/parkos_core/repo/alerta.py` (NUEVO, ~60 LOC) — `insertar_alerta_forzado` puro; INSERT `Alerta(tipo_alerta='capacidad_agotada_forzado', estado='abierta', datos_nuevos={motivo, uuid_ingreso})` + `session.add` + `await session.flush()` (R-A2 jsonb audit). (REQ-OPS-041.C)
- `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py` (MODIFICAR, +40 LOC) — `CupoValidationResult(cupo_no_configurado, cupo_agotado, cupo_maximo, activos)` + `validar_cupo_disponible` reusando `get_ocupacion_puros_activos` (F1.5); KD-V4 eventual consistency via `mv_ocupacion_diaria`. (REQ-OPS-034, REQ-OPS-035)
- `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (MODIFICAR, +30 LOC) — `TarifaValidationResult(vigente, tarifa)` + `validar_tarifa_vigente` reusando `bitemporal_vigente_predicate` (F1.4); bi-temporal canónico. (REQ-OPS-036)
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (MODIFICAR, replace `create_ingreso` líneas 92-114 → ~232 LOC) — handler dedicado con 9 validaciones V1..V9 + KD-FORZADO-01 chain + derivación `tipo_entrada`. KD-3 chain (`_ingreso_issuer_dep`, `get_tenant_ctx`) preservado; `response_model=IngresoReadForzado`, `status_code=201`, `Cache-Control: no-store` en 2xx/4xx/5xx. `api/v1/__init__.py` y `router_factory.py` intactos. Precedencia 11-step per D-HU-F1.6-11 (AST walk verificado). (REQ-OPS-034..041)
- `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (MODIFICAR, +116 LOC) — `IngresoCreateForzado(forzado: bool=False)` + `IngresoReadForzado(tipo_entrada: Literal["MENSUALIDAD","ROTACION"], forzado_en_creacion: bool=False, motivo_forzado: str|None=None)` + 7 clases de error tipadas (`CupoNoConfiguradoError`, `MotivoForzadoRequeridoError`, `TarifaVigenteNoEncontradaError`, `PlacaFormatoInvalidoError`, `SubscripcionInactivaOVencidaError`, `IngresoActivoExistenteError`, `TipoVehiculoInvalidoError`). `IngresoCreate`/`IngresoRead` preservados como alias deprecated (backward compat F1.5). `extra='forbid'` heredado de `_Base`. (REQ-OPS-034..041)
- `backend/packages/parkos_core/migrations/versions/0025_add_alerta_datos_nuevos_and_alert_type.py` (NUEVO, ~141 LOC) — pre-flight `DO $$` sobre `prod.alerta` (KD-7) + `ALTER TABLE prod.alerta ADD COLUMN IF NOT EXISTS datos_nuevos JSONB` + `INSERT INTO prod.alert_types (..., 'capacidad_agotada_forzado', ...) ON CONFLICT (tipo_alerta) DO NOTHING` (idempotente; respeta `alert_types_inmutable` trigger). `revision = "0025_alerta_datos_nuevos"`, `down_revision = "0024_mv_ocupacion_diaria"`. (REQ-OPS-041.C)
- `backend/tests/unit/test_operacion_ingresos_kd_forzado.py` (NUEVO + archive M1 regression) — 4 KD-FORZADO contract tests + 2 T-aux + 2 M1 regression tests (`prefix_mid_string_no_startswith_returns_none`, `prefix_sin_cierre_raises_contradiccion`) cubriendo el alineamiento con spec `startswith`. Pure helper, sin HTTP/DB. (REQ-OPS-041.B)
- `backend/tests/integration/test_ingreso_create_db.py` (NUEVO + archive M2 regression) — 3 DB integration tests (T1 alerta same-TX, T2 duplicado, T3 sub vencida) + 1 M2 regression (`anulacion_pendiente_no_bloquea_nuevo_ingreso`) cubriendo el filtro `a.estado='ejecutada' AND a.tipo_anulable IN ('ingreso','salida')`. Requiere `PARKOS_DOCKER_TEST=1`. (REQ-OPS-040)
- **`operational` (F1.7 — HU-F1.7 archive)** — the canonical capability adds REQ-OPS-042..052 (11 requirements): POST /operacion/salidas contract (V1..V5 validations + KD-FORZADO-01 prefix contract verbatim F1.6 reuse + server-side `tipo_salida` derivation DEC-SUC-21-NEW + alerta same-TX contract for V2/V5 bypass + partial unique index `one_exit_per_ingreso` with 409 mapping + inline-seed `impuestos.IVA` via MIGRATION 0026). The merged main spec (`openspec/specs/operations/spec.md`) gains 11 new requirements and no existing requirement is modified (REQ-OPS-001..041 remain unchanged). The new `prod.salidas` table inserts are coordinated with the existing `prod.anulaciones` workflow (Fase 7+) via the partial unique index's `NOT EXISTS` predicate (REQ-OPS-051). The handler reuses the pre-existing `models/A/salidas.py::Salidas(AppendOnlyBase)` ORM (composite PK `uuid+fecha_retencion_hasta`, monthly RANGE partition, `__write_only__` marker enabling AST-level DML rejection — D-HU-F1.7-14 supersession; the originally-proposed `models/L_S/salida.py` based on `LifecycleEventBase` was rejected at apply in favor of reusing the pre-existing `[A]`-class ORM, which is superior for defense-in-depth).

## Out of Scope

- **Application Performance Monitoring (APM)** — OpenTelemetry is added
  in `bootstrap-monorepo-foundation`; this change relies on the
  structured logs + Prometheus surface only.
- **Log shipping** — Grafana Loki / similar is added in the bootstrap
  change; this change assumes the operator can already view structured
  JSON logs.
- **Synthetic monitoring** — blackbox probes against `/sync/hello` are
  added by `bootstrap-monorepo-foundation`.
- **Chaos engineering** — fault injection against the catalog path is
  deferred to v2.
- **DIAN-specific runbooks** — the `runbook_url` for `HashChainBreak`,
  `FEProviderError`, and `FENumberingExhausted` points to a generic sync
  runbook; the DIAN-specific recovery procedure is documented in
  `docs/runbooks/dian/` using the same generic identifiers.
