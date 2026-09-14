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
