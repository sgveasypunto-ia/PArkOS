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
