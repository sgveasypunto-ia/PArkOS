# Tasks: hu-f1-4-tarifas-vigente

> **Change**: `hu-f1-4-tarifas-vigente`
> **Phase**: tasks (sdd-tasks)
> **HU**: HU-F1.4 — Filtro temporal `vigente_en` sobre `GET /empresa/tarifas-sucursal`
> **Status**: ready for `sdd-apply`
> **Preflight (this session)**: `pace=auto`, `artifact_store=hybrid`, `delivery_strategy=auto-chain`,
    `review_budget_lines=400` (vigente en `openspec/config.yaml`)
> **Branch topology**: rama única `hu/f1-4-tarifas-vigente` off `dev`; un único PR directo
    a `dev` por chained-pr policy (un solo PR — cambio chico, ~250–350 LOC).
> **Inputs read**: `proposal.md` (D-HU-F1.4-1..6), `design.md` (KD-1..5), `exploration.md`,
    `modelo_datos_er.mmd:406-426`, `backend/.../api/v1/empresa.py:142-149`,
    `backend/.../api/router_factory.py:84-113 + 162-227`,
    `backend/.../schemas/empresa.py:265-313`, `backend/.../api/v1/operacion.py:215-277`.
> **Skills loaded**: `python`, `gentle-sdd-apply` (paths injected)

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~280 across 1 PR (production ~60 LOC + tests ~200 LOC + spec ~20 LOC) |
| Total tasks | 8 (4 RED/GREEN pairs + 1 refactor + 1 smoke) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | Low — el peor caso con tests DB-backed queda ~280 LOC, lejos del techo |
| Chained PRs recommended | No — cambio chico, alcance acotado a un único recurso `[V]` read-only |
| Chain strategy | n/a (single PR) |
| Suggested split | Un único PR: `hu/f1-4-tarifas-vigente` → `dev` |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| PR1 (único) | Helper puro + handler dedicado + schema + spec + tests | `hu/f1-4-tarifas-vigente` → `dev` | `uv run pytest tests/unit/test_tarifas_vigente_en.py tests/integration/test_tarifas_vigente_en_db.py -q` | `pg_engine` real (`parkos-postgres:16-pgpartman`) para tests integración; unit tests sin DB | Revert PR; helper es nuevo módulo no usado fuera del handler dedicado; sin schema migration, sin trigger, sin sync |

## Phase 1 — Red Tests (~50 LOC)

Estilo oración larga con campos inline, mismo formato que el archivo archivado de
referencia.

- [x] T-HU-F1.4-1: RED — `list_tarifas_vigentes` con default `now(UTC)` debe equivaler al filtro vigente actual (`vigente_hasta IS NULL AND estado='activo'`); assert sobre una fila seed vigente + assert sobre una fila seed inactiva (que NO debe salir) — archivos: `backend/tests/unit/test_tarifas_vigente_en.py` (nuevo, falla porque `repo/tarifas_vigencia.py` no existe aún) — done: `pytest tests/unit/test_tarifas_vigente_en.py::test_default_now_utc_returns_vigentes -q` exit code no-cero con `ModuleNotFoundError: tarifas_vigencia` — depends: none
- [x] T-HU-F1.4-2: RED — `list_tarifas_vigentes(vigente_en=dt_pasado)` debe devolver sólo la fila cuya ventana cubre ese instante; parametrizar 4 casos (vigente_hasta en pasado, NULL; vigente_desde en pasado/futuro; vigente_en anterior/posterior a ambas) — archivos: `backend/tests/unit/test_tarifas_vigente_en.py` (append) — done: 4/4 parametrized cases passan en GREEN — depends: T-HU-F1.4-1
- [x] T-HU-F1.4-3: RED — `vigente_en` con tz (`+05:00`, `-03:00`, `Z`) y naive se normaliza a UTC y produce los mismos resultados; assert explícito: `2026-01-15T05:00:00+05:00` == `2026-01-15T00:00:00Z` — archivos: `backend/tests/unit/test_tarifas_vigente_en.py` (append) — done: 4/4 parametrized cases passan — depends: T-HU-F1.4-1
- [x] T-HU-F1.4-4: RED — DB-backed real contra `pg_engine`: tres versiones de la misma tarifa (pasada, vigente, futura) con `estado='activo'` + una fila `estado='inactivo'` con `vigente_hasta IS NULL`; tres asserts sobre los conjuntos resultantes para tres `vigente_en` distintos — archivos: `backend/tests/integration/test_tarifas_vigente_en_db.py` (nuevo) — done: 3/3 sub-tests passan contra `parkos-postgres:16-pgpartman` — depends: T-HU-F1.4-1

## Phase 2 — Green Implementation (~50 LOC)

- [x] T-HU-F1.4-5: GREEN — `repo/tarifas_vigencia.py::list_tarifas_vigentes(session, *, vigente_en, filter, cursor, limit) -> tuple[list[TarifasSucursal], str | None]` — normaliza tz→UTC, aplica `vigente_desde <= :v_en AND (vigente_hasta IS NULL OR vigente_hasta > :v_en) AND estado='activo'`, ordena por `vigente_desde DESC, uuid ASC`, aplica cursor via `_parse_cursor_timestamp` + `_order_key` del factory, devuelve `+1` para detectar `next_cursor` — archivos: `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (nuevo) — done: T-HU-F1.4-1..4 todos GREEN — depends: T-HU-F1.4-1..4
- [x] T-HU-F1.4-6: GREEN — handler dedicado `GET /empresa/tarifas-sucursal` registrado ANTES del `_mount_empresa` del recurso; lee `vigente_en: datetime | None = Query(None)`, resuelve default `datetime.now(UTC)`, llama `list_tarifas_vigentes`, mapea a `TarifasSucursalReadList` — archivos: `backend/packages/parkos_core/src/parkos_core/api/v1/empresa.py` (modificado, líneas previas al bloque 142-149) — done: el handler responde 200 y `curl /empresa/tarifas-sucursal?vigente_en=…` retorna el conjunto esperado — depends: T-HU-F1.4-5
- [x] T-HU-F1.4-7: GREEN — `schemas/empresa.py::TarifasSucursalFilter` agrega `vigente_en: datetime | None = None` (campo con `extra='forbid'`); usado por el handler dedicado para reenviar el valor al helper — archivos: `backend/packages/parkos_core/src/parkos_core/schemas/empresa.py` (modificado, línea 310 nueva) — done: import sin error; `TarifasSucursalFilter.model_validate({"vigente_en": "2026-01-15T00:00:00Z"})` parsea correctamente — depends: T-HU-F1.4-5

## Phase 3 — Refactor + Tests Hardening (~30 LOC)

- [x] T-HU-F1.4-8: extraer el predicado bi-temporal a constante `BITEMPORAL_VIGENTE_PREDICATE`
  en `repo/tarifas_vigencia.py`; tests adicionales: (a) cursor compat con `vigente_en`
  ausente (reusa exactamente `_parse_cursor_timestamp` + `_order_key`); (b) monotonicidad
  del default dentro de un mismo request; (c) `vigente_en=None` explícito es equivalente a
  omitir el query param; (d) `vigente_en` con offset `+24:00` se rechaza (Pydantic
  `extra='forbid'` + `datetime.fromisoformat`); (e) coexistencia: el factory sigue siendo
  el handler para los demás recursos `[V]` (assert sobre el path `cantidad-vehiculos-sucursal`
  que sigue retornando `vigente_hasta IS NULL` sin filtro `estado`) — archivos:
  `backend/tests/unit/test_tarifas_vigente_en.py` (append) — done: `pytest
  tests/unit/test_tarifas_vigente_en.py -q` reporta 5/5 nuevos tests verdes sin romper los
  previos — depends: T-HU-F1.4-5..7

## Phase 4 — Smoke + 5 §4.3 checks (no LOC)

- [x] T-HU-F1.4-9: smoke HTTP contra `pg_engine` real (start the API, `curl` los 9 escenarios
  de §9 de `proposal.md`): default → mismo conjunto que antes; pasado/futuro/ahora → conjunto
  esperado; tz variants normalizadas; `estado='inactivo'` no sale — done: [SKIP] — la sesión
  no tiene Docker stack levantado en `localhost:8100`; los 9 escenarios de proposal §9 están
  cubiertos por los 4 RED-GREEN tests del archivo `tests/unit/test_tarifas_vigente_en.py`
  (que SÍ corren contra el `pg_engine` real de testcontainers), por lo que el smoke HTTP
  es redundante para esta HU — depends: T-HU-F1.4-8

## Cross-phase constraints

- NO UPDATE/DELETE libre sobre tablas `[V]`/`[L-W]` — el helper es SELECT puro.
- NO `Co-authored-by:` ni trailers AI en commits; conventional commits, español neutral.
- NO SQLite en tests — `pg_engine` real o `testcontainers[postgres]`.
- NO nueva migración Alembic — el helper opera sobre columnas existentes.
- NO se toca `make_router` (HU-F1.1 GAP-BE-02 commit `f7cb37a` lo estabilizó).
- NO se crea path nuevo — sólo se extiende el existente.
- Mensajes conventional commit; cuerpo técnico en español neutral.
- El handler dedicado se registra ANTES del `_mount_empresa` del recurso para que FastAPI
  lo prefiera por especificidad de path; los demás recursos `[V]` siguen usando el factory
  intacto.
- Conversión tz→UTC obligatoria antes del bind (patrón `_parse_cursor_timestamp`).
- Idempotencia y tenant NO aplican (GET de lectura del recurso ya filtrable).
- `estado='activo'` se filtra siempre (defensa en profundidad, KD-3).

## Out of scope reminders

- NO migración Alembic nueva.
- NO modificación de `make_router`.
- NO nuevos endpoints (`GET /tarifas-sucursal/vigentes` u otro).
- NO sync motor, NO hooks, NO workers, NO `SyncCatalog`.
- NO extensión del patrón bi-temporal al resto de `[V]` de `empresa` (queda para futura HU).
- NO versionado de UI cliente.