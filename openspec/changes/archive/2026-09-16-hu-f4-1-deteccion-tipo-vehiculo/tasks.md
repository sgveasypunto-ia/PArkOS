# Tasks — HU-F4.1 Detección automática de tipo de vehículo por placa (función pura `detectarTipoVehiculo()` estricto + hook SWR `useTiposVehiculo()` con fallback hardcoded `{auto, moto}`)

> **Phase**: tasks (sdd-tasks) · **Status**: ready for sdd-apply
> **HU ID**: HU-F4.1 (Fase 4 — primera HU; Catálogos y ocupación en vivo)
> **Working dir**: `E:\easypunto_parkos` · **Branch**: `feature/hu-f4-1-deteccion-tipo-vehiculo` (clean, recién creada desde `dev`)
> **PR target**: `origin/dev`
> **Cross-refs**: `exploration.md` (~512 LOC, 16 secciones, 10 DEC-F4.1-01..10, 5 riesgos R1..R5) · `proposal.md` (~758 LOC, 11 DEC-F4.1-01..11 ratified, DEC-F4.1-07 + DEC-F4.1-11 verdict DELTA, 6 new REQ-OPS-125..130 user-facing) · `specs/operations/spec.md` (DELTA con 6 new REQ-OPS-125..130 en formato Given/When/Then/And RFC 2119) · `design.md` (13 secciones + 2 apéndices, 6 TS mockups + 3 configs delta + 7 acceptance gates G1..G7)
> **Prereq change**: `hu-f3-3-abrir-cerrar-turno` archived 2026-09-15 (F3.3 sentado hooks SWR pattern + i18n namespace pre-existente + vitest setup)
> **Author**: Parkos Dev <dev@parkos.local> · **Language**: español neutro profesional · **Conventional commits**: `feat(operacion)` / `feat(catalogos)` / `test(electron)` — sin Co-authored-by AI

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **Change** | `hu-f4-1-deteccion-tipo-vehiculo` |
| **HU** | F4.1 — Función pura `detectarTipoVehiculo(placa: string): 'Auto' \| 'Moto' \| null` con regex estricto hardcoded (Auto `^[A-Z]{3}[0-9]{3}$`, Moto `^[A-Z]{3}[0-9]{2}[A-Z]$`), normalización previa (trim + uppercase + remover whitespace interno), exports `REGEX_AUTO` + `REGEX_MOTO` para reuso F6.1 Zod + hook SWR `useTiposVehiculo()` con `dedupingInterval: 5 * 60 * 1000` (plan.md:1375 verbatim — 5min para catálogos reference data) + `fallbackData: HARDCODED_CATALOG` con `{auto, moto}` + UUIDs sentinels literales (degradación explícita, NUNCA pantalla rota) + `shouldRetryOnError` excl 404 + `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event (precedent F3.3 verbatim) + `tiposVehiculoApi` typed wrapper `parkosFetch<TiposVehiculoReadList>('/api/v1/catalogos/tipos-vehiculo')` con mapeo 404 → `[]` + filtro defensivo `tipo: null` + i18n key `operacion.placa_formato_invalido` con literal verbatim plan.md:1366 ("Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)") para consumo forward F6.1 `<PlacaInput>` `<p role="alert" aria-describedby>` + defense in depth XR6 layer 4 (cliente F4.1 + backend `detectar_tipo_vehiculo()` ya shipped HU-F1.x — operacion.py:215-277, regex idéntica cliente/backend, "Server overwrites via V5" operacion.py:261 verbatim) + WCAG 2.1 AA foundation forward F6.1 (i18n key pre-poblada + detector determinista + `isFromFallback` flag). |
| **Owner** | Parkos Dev <dev@parkos.local> |
| **Working tree** | `E:\easypunto_parkos` |
| **Branch base** | `feature/hu-f4-1-deteccion-tipo-vehiculo` (F2.1 + F2.2 + F2.3 + F3.1 + F3.2 + F3.3 archivados) |
| **PR target** | `origin/dev` |
| **Total tasks** | 3 atomic (T1..T3) |
| **Total clusters** | 2 (C1 — detección + i18n; C2 — hook SWR + catálogo) |
| **Production LOC budget** | ~163 LOC (T1 ~50 + T2 ~110 + T3 ~3) |
| **Test LOC budget** | ~150 LOC unit (T1 6 tests ~80 + T2 5 tests ~70) |
| **Total LOC budget** | **~313 LOC** (production 163 + unit 150) — bien debajo del budget 800 per `config.yaml rules.tasks` |
| **Atomic commits** | 2 (C1 — T1+T3 agrupados cohesivos "detección de placa funciona en cliente"; C2 — T2 independiente "catálogo de tipos se carga con degradación") |
| **Review actor** | `sdd-verify` post-apply |
| **Archive actor** | orchestrator (post-verify PASS) |
| **Related artifacts** | `exploration.md` (16 secciones, 10 DEC-F4.1-01..10, 5 riesgos R1..R5) · `proposal.md` (11 secciones, 11 DEC-F4.1-01..11 ratified) · `specs/operations/spec.md` (DELTA con 6 new REQ-OPS-125..130) · `design.md` (13 secciones + 2 apéndices, 6 TS mockups + 3 configs delta) |
| **Scope** | Frontend-only: `detectarTipoVehiculo()` función pura en `lib/validation/placa.ts` + `REGEX_AUTO` + `REGEX_MOTO` constantes módulo-level exportadas + `useTiposVehiculo()` hook SWR reusable (primer hook genuinely reusable del feature `catalogos` — forward F4.2 + F4.3 + F6.1 + F7.x + F11.x consumers) + `tiposVehiculoApi` typed wrappers con `parkosFetch` + 404 → `[]` + filtro defensivo + `HARDCODED_CATALOG` constante inline con `{auto, moto}` + UUIDs sentinels literales + i18n key `operacion.placa_formato_invalido` agregada a namespace pre-existente F2.1 + `vitest.config.ts` MODIFY (+3 coverage thresholds). NO incluye backend cambios (`detectar_tipo_vehiculo()` server-side shipped HU-F1.x operacion.py:215-277 + `GET /api/v1/catalogos/tipos-vehiculo` C+Q+U router shipped catalogos.py:140-147 F1.x con permission `config_catalogo` per `_CATALOG_DEFAULTS:101`), UI componente `<PlacaInput>` (forward HU-F6.1), selector manual de tipo (corpus categórico BR2 + DEC-SUC-22 — NO override manual), tolerancia de tipeo `O↔0`/`I↔1`/`B↔8` (pertenece a `buscarIngresoTolerante()` Fase 7 — funciones DISTINTAS en archivos DISTINTOS), migraciones Alembic (A-03 verbatim: regex hardcoded cliente, NO columna ER `tipos_vehiculo`), `electron-store` persistente (fallback hardcoded suficiente para catálogos reference data), `refreshInterval` periódico (solo `dedupingInterval`), e2e test Playwright (F4.1 lógica pura — 11 unit tests cubren el camino crítico, e2e aplica al forward consumer F6.1), WCAG axe-core scan runtime (sienta primitives — F6.1 verifica), `crypto.randomUUID()` para fallback UUIDs (literales sentinels), tipos de vehículo adicionales (`Bicicleta`/`Camión`/`Moto eléctrica` — A-03 explícito), extensión `PRE_FLIGHT_PATHS` (`/catalogos/*` GET read idempotente NO requiere pre-flight gate DEC-SUC-03 + F3.2 verbatim). |
| **Dependencies** | F2.1 archivado (Electron 30 scaffold + shadcn Form/Input/Button + i18n 7 namespaces con `operacion.json` 10 keys baseline + axe-core + playwright e2e setup) · F2.2 archivado (`parkosFetch` con retry + refresh-once 401 via Mutex + Idempotency-Key auto + bridge IPC + `authStore` Zustand + `useAuth` SWR) · F2.3 archivado (kiosko mode + electron-updater + StatusBar + single-instance lock) · F3.1 archivado (Login page + LoginForm + loginApi + ruta `/login` + 7 REQ-OPS-106..112) · F3.2 archivado (`useCountdown` + `REFRESH_INTERVAL_MS = 50min` + `PRE_FLIGHT_PATHS` regex + 6 REQ-OPS-113..118) · F3.3 archivado (`useSesionActiva()` SWR precedent — key null-when-no-token + deduping + 401 clear + event + `useAuthStore.clear()` + `parkos:auth:cleared` event dispatch verbatim + 6 REQ-OPS-119..124) · HU-F1.x shipped Fase 1 (backend `detectar_tipo_vehiculo()` server-side en `operacion.py:215-277` defense in depth XR6 layer 4 + `GET /api/v1/catalogos/tipos-vehiculo` C+Q+U router en `catalogos.py:140-147` con permission `config_catalogo`) · npm 11.16.0 local Windows + npm sandbox F.6 caveat documentado (NO aplica a F4.1 — sin e2e, solo unit tests). |

---

## 1. Atomic task clusters (C1 + C2)

F4.1 entrega 3 atomic tasks en orden mandatory con paralelismo donde aplica, organizados en **2 clusters C1 + C2** que reflejan la decisión arquitectónica de work-unit-commits (deliverable cohesivo por commit, NO por tarea):

```
T1 — detectarTipoVehiculo() función pura + placa.test.ts 6 unit tests
   ↓ (T1 entrega función pura reutilizable + cobertura branches críticos)
T3 — i18n key placa_formato_invalido  (agrupado en C1 per DEC-F4.1-08)
   ↓ (T3 entrega string UX consumible por F6.1 forward)
[C1 COMMIT] feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido
   ↓
T2 — useTiposVehiculo() hook SWR + tiposVehiculoApi typed wrapper + useTiposVehiculo.test.ts 5 unit tests + HARDCODED_CATALOG fallback
   ↓ (T2 entrega hook reusable + api typed + fallback hardcoded)
[C2 COMMIT] feat(catalogos): adicionar useTiposVehiculo() SWR + tiposVehiculoApi typed wrapper + 5 unit tests + fallback hardcoded {auto,moto}
   ↓
archive — mover change folder a archive/, actualizar pending.md §1 row F4.1 → ✅
```

### §1.1 Justificación del split 2 clusters (C1 + C2)

Work-unit-commits skill (F2.x + F3.x precedent verbatim, `AGENTS.md` canon): commits agrupan por **DELIVERABLE cohesivo**, NO por tarea atómica. F4.1 emite 2 commits porque la función pura (T1) sin la i18n key (T3) es incompleta para el caller que quiera mostrar el error en F6.1, mientras que el hook SWR (T2) es deliverable independiente consumible por F4.3 antes que F6.1 exista (peer con F4.2 hook independiente). Esta es la decisión ratificada en `proposal.md §4.8 DEC-F4.1-08` con 3 alternativas consideradas (3 commits separados por tarea RECHAZADA, 1 commit monolítico RECHAZADA por >400 LOC, 2 commits DECIDIDA).

### §1.2 Dependency graph (ASCII)

```
              ┌──────────────────────────────────────────────────────────┐
              │ FUNCIÓN PURA REUSABLE (NEW — DEC-F4.1-01..03)            │
              │ apps/electron-sucursal/src/lib/validation/               │
              └──────────────────────────────────────────────────────────┘
                                          │
                                          ▼
              ┌──────────────────────────────────────────────────────────┐
              │ T1 detectarTipoVehiculo.ts + placa.test.ts               │
              │ + REGEX_AUTO + REGEX_MOTO constants                     │
              │ ~50 LOC prod + ~80 LOC tests = ~130 LOC                 │
              │ Función pura determinista (sin red/store/DOM) +          │
              │ normalización trim+uppercase+remove-whitespace +        │
              │ exports REGEX_AUTO + REGEX_MOTO para F6.1 Zod            │
              └──────────────────────────────────────────────────────────┘
                                          │
                                          ▼
              ┌──────────────────────────────────────────────────────────┐
              │ T3 i18n key placa_formato_invalido                       │
              │ operacion.json MODIFY (+1 key, ~3 LOC)                   │
              │ Namespace pre-existente F2.1 DEC-ELEC-06 verbatim        │
              └──────────────────────────────────────────────────────────┘
                                          │
                          ┌───────────────┴───────────────┐
                          ▼                               ▼
              ┌─────────────────────────┐    ┌─────────────────────────────────────┐
              │ [C1 COMMIT]             │    │ HOOK SWR REUSABLE (NEW — DEC-F4.1-04..06) │
              │ feat(operacion)         │    │ apps/electron-sucursal/src/         │
              │ T1 + T3 agrupados       │    │ features/catalogos/                  │
              │ cohesivos               │    └─────────────────────────────────────┘
              └─────────────────────────┘                  │
                                          ▼
              ┌──────────────────────────────────────────────────────────┐
              │ T2 tiposVehiculoApi.ts + useTiposVehiculo.ts             │
              │ + useTiposVehiculo.test.ts (5 tests)                     │
              │ + HARDCODED_CATALOG constante inline                      │
              │ ~110 LOC prod + ~70 LOC tests = ~180 LOC                 │
              │ SWR key null + deduping 5min + fallback hardcoded        │
              │ + 401 clear + event dispatch + isFromFallback            │
              └──────────────────────────────────────────────────────────┘
                                          │
                                          ▼
              ┌──────────────────────────────────────────────────────────┐
              │ [C2 COMMIT]                                             │
              │ feat(catalogos)                                         │
              │ T2 solo                                                 │
              └──────────────────────────────────────────────────────────┘
                                          │
                                          ▼
              ┌──────────────────────────────────────────────────────────┐
              │ archive — mover change folder, update pending.md §1 F4.1│
              └──────────────────────────────────────────────────────────┘
```

### §1.3 Tabla de orden estricto

| Step | Cluster | Task | Cuándo | Acción | Razón orden |
|---|---|---|---|---|---|
| 1 | C1 | **T1** | primera | NEW `placa.ts` + `placa.test.ts` (~130 LOC — 50 prod + 80 tests) | DEC-F4.1-01/02/03: función pura reusable con regex estricto + normalización + exports `REGEX_AUTO` + `REGEX_MOTO`. Es la pieza fundamental del flujo de ingreso CU-01 (forward F6.1). |
| 2 | C1 | **T3** | después T1 (mismo C1) | MODIFY `operacion.json` (+1 key `placa_formato_invalido`, ~3 LOC) | DEC-F4.1-11: namespace pre-existente F2.1 DEC-ELEC-06. La i18n key + la función pura son cohesivas — la función SIN i18n key es incompleta para el caller. |
| 3 | C1 | **[C1 COMMIT]** | después T1 + T3 | Commit `feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido (HU-F4.1-T1+T3)` | Work-unit cohesivo: detección de placa funciona en cliente (función + i18n + tests). Reviewable standalone. Rollback: `git revert <C1-commit>` elimina función pura — F6.1 forward bloqueado (sin función, F6.1 no puede arrancar). |
| 4 | C2 | **T2** | después C1 (independiente — F4.3 podría consumir antes que F6.1 exista, peer con F4.2 hook) | NEW `tiposVehiculoApi.ts` + `useTiposVehiculo.ts` + `useTiposVehiculo.test.ts` (~180 LOC — 110 prod + 70 tests) + MODIFY `vitest.config.ts` (+3 coverage thresholds, ~3 LOC) | DEC-F4.1-04/05/06/09: hook SWR reusable con key null + deduping 5min + fallback hardcoded + 401 clear + event dispatch + `isFromFallback` flag + tiposVehiculoApi typed wrapper. Forward extensibility F4.2 + F4.3 + F6.1 + F11.x. |
| 5 | C2 | **[C2 COMMIT]** | después T2 | Commit `feat(catalogos): adicionar useTiposVehiculo() SWR + tiposVehiculoApi typed wrapper + 5 unit tests + fallback hardcoded {auto,moto} (HU-F4.1-T2)` | Work-unit cohesivo: catálogo de tipos se carga con degradación. Reviewable standalone. Rollback: `git revert <C2-commit>` revierte hook — F4.3 + F6.1 forward consumers bloqueados (sin hook, no pueden resolver `uuid_tipo_vehiculo`). |
| 6 | (archive) | **archive** | post-verify PASS | Mover change folder `hu-f4-1-deteccion-tipo-vehiculo/` → `archive/2026-09-16-hu-f4-1-deteccion-tipo-vehiculo/` + actualizar `pending.md §1` row F4.1 → ✅ + mergear 6 new REQ-OPS-125..130 a `openspec/specs/operations/spec.md` canónico (sdd-archive phase per F3.3 verbatim precedent) | Numeración monotónica verificada: REQ-OPS-124 vigente post-F3.3 archive; F4.1 ocupa REQ-OPS-125..130 (0 gaps, sin duplicados). |

### §1.4 Justificación de orden

- **T1 antes que T3**: la i18n key T3 describe el mensaje de error que se muestra cuando `detectarTipoVehiculo()` retorna `null` (T1). Sin T1, la i18n key queda huérfana (string sin función consumidora). Orden T1 → T3 mantiene cohesión funcional.
- **T1+T3 agrupados en C1**: per `DEC-F4.1-08` ratified en `proposal.md §4.8`. La función pura + la i18n key son el mismo deliverable "detección de placa funciona en cliente". Tests incluidos en mismo commit (work-unit-commits hard rule: "Tests belong in the same commit as the behavior they verify").
- **C1 antes que C2**: C1 sienta las primitives (función pura + mensaje i18n) que F6.1 consume forward. C2 entrega el hook del catálogo (consumible por F4.3 antes que F6.1 exista — peer pattern). Sin embargo, C1 NO es prerequisito técnico de C2 — son deliverables independientes en features distintas (`lib/validation/` vs `features/catalogos/`). El orden C1 → C2 es por **delivery semantics** (primero la pieza fundamental de la operación, después el hook reusable que múltiples consumers comparten).
- **C2 después de C1**: el hook SWR `useTiposVehiculo()` es independiente de la función pura — vive en feature `catalogos/` distinto. F4.3 `<OcupacionStrip>` puede consumirlo antes que F6.1 exista (peer pattern con F4.2 `useTarifasVigentes`). El orden de commits sigue el flujo narrativo: "primero la detección (C1), después el catálogo que la complementa (C2)".
- **2 clusters vs 1 monolítico**: ~313 LOC total está bien debajo del budget 800 LOC per `config.yaml rules.tasks`. Sin embargo, el split C1+C2 permite rollback granular (C1 rollback no toca C2 hook reusable y viceversa) — defense in depth a nivel de delivery.
- **2 clusters vs 3 commits por tarea**: work-unit-commits skill categórico: commits agrupan por DELIVERABLE cohesivo, NO por tarea atómica. T1 sin T3 = función sin mensaje de error (incompleta). T3 sin T1 = i18n key huérfana sin función consumidora. T2 es deliverable independiente pero NO requiere T1+T3 como prerequisito técnico.

**Precedente inmediato**: F3.3 archivado (`archive/2026-09-15-hu-f3-3-abrir-cerrar-turno/tasks.md`) — 5 atomic tasks T1..T5 con single-cluster C1 end-to-end (~650 LOC). F4.1 adapta el layout 1:1 con 3 tasks T1..T3 y 2 clusters C1+C2 (~313 LOC) — el split refleja la decisión `DEC-F4.1-08` de work-unit cohesivo (función+i18n cohesivos vs hook independiente). F2.2 archivado (`archive/2026-09-15-hu-f2-2-parkos-fetch-auth-store/`) — precedente verbatim de work-unit commits para hooks SWR (T2 replica el pattern `useAuth` precedent).

---

## 2. Atomic task inventory

### T1 — `detectarTipoVehiculo()` función pura + `REGEX_AUTO` + `REGEX_MOTO` constantes + 6 unit tests (~50 prod + ~80 tests = ~130 LOC)

**Descripción**: Entrega la función pura reusable que detecta el tipo de vehículo (Auto / Moto / null) vía regex estricto hardcoded, con normalización trivial previa (trim + uppercase + remover whitespace interno). Exporta `REGEX_AUTO` + `REGEX_MOTO` como constantes módulo-level para reuso en validación Zod (F6.1 forward consumer). Sienta el precedent de separación clara entre detección estricta (F4.1) y búsqueda tolerante (F7.x — `buscarIngresoTolerante()` con `O↔0`/`I↔1`/`B↔8`). JSDoc verbatim DEC-SUC-22 + A-03 + BR2 + `operacion.py:215-277` backend counterpart (defense in depth XR6 layer 4). Función determinista sin acceso a red, store, DOM — testeable sin mocks (6 unit tests verbatim `plan.md:1381`).

**Archivos a crear**:
- `apps/electron-sucursal/src/lib/validation/placa.ts` (~50 LOC — `export const REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/` + `export const REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/` + `export function detectarTipoVehiculo(placa: string): 'Auto' | 'Moto' | null` con normalización `(a) trim; (b) toUpperCase; (c) replace(/\s+/g, '')` + JSDoc verbatim DEC-SUC-22/A-03/BR2 + cross-link `operacion.py:215-277`).
- `apps/electron-sucursal/src/lib/validation/placa.test.ts` (~80 LOC — U1 ABC123 → 'Auto', U2 ABC12D → 'Moto', U3 ABCD12 → null, U4 '' → null, U5 abc123 → 'Auto' normalizado, U6 '  ABC123  ' → 'Auto' con espacios, todos verbatim `plan.md:1381`).

**Archivos a modificar**: (ninguno — T1 es additive puro, consume primitives F2.1+F2.2+F3.x READ ONLY).

**Criterio de done**:
- U1..U6 verde en `pnpm vitest run src/lib/validation/placa.test.ts --coverage` (≥95% lines, ≥95% functions, ≥90% branches per design §7.3 coverage thresholds).
- `pnpm tsc --noEmit -p tsconfig.renderer.json` clean (zero TS errors en archivo nuevo).
- ESLint `--max-warnings 0` clean en `placa.ts` + `placa.test.ts`.
- JSDoc referencia explícita a `operacion.py:215-277` + DEC-SUC-22 + A-03 + BR2 (defense in depth XR6 layer 4 documentado).
- Working tree clean (`git status --short` vacío) post-commit.

**Commit message esperado** (per DEC-F4.1-08 C1 agrupado con T3): `feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido (HU-F4.1-T1+T3)`.

---

### T2 — `useTiposVehiculo()` hook SWR + `tiposVehiculoApi` typed wrapper + `HARDCODED_CATALOG` fallback + 5 unit tests (~110 prod + ~70 tests = ~180 LOC)

**Descripción**: Entrega el hook SWR reusable para consultar el catálogo `tipos_vehiculo` con fallback hardcoded `{auto, moto}` (degradación explícita, NUNCA pantalla rota) + el typed wrapper `tiposVehiculoApi.getTiposVehiculo()` con `parkosFetch` + mapeo 404 → `[]` + filtro defensivo de filas con `tipo: null`. Primer consumer F4.1; forward consumers F4.3 `<OcupacionStrip>` + F6.1 `<PlacaInput>` + F11.x sync UI consumen el hook compartido. SWR config verbatim F3.3 `useSesionActiva` precedent con adaptaciones: (a) `key: accessToken ? '/catalogos/tipos-vehiculo' : null` (key null-when-no-token); (b) `fetcher: () => tiposVehiculoApi.getTiposVehiculo()`; (c) `dedupingInterval: 5 * 60 * 1000` (plan.md:1375 verbatim — 5min para catálogos reference data, vs F3.3 10s para sesión activa); (d) `fallbackData: HARDCODED_CATALOG` con shape `[{uuid: '...0001', tipo: 'Auto', ...}, {uuid: '...0002', tipo: 'Moto', ...}]` + UUIDs sentinels literales (NO `crypto.randomUUID()` — son sentinels de FALLBACK, no IDs reales para sync); (e) `shouldRetryOnError: (err) => err?.status !== 404` (catálogo vacío es estado válido, NO retry spam); (f) `onError: (err) => { if (err?.status === 401) { useAuthStore.getState().clear(); window.dispatchEvent(new Event('parkos:auth:cleared')) } }` (precedent F3.3 verbatim — 401 dispara logout defensivo + forward hook AuthGuard F4.x+). Retorna `{tipos: TipoVehiculo[], isLoading, error: ParkosHttpError | undefined, refresh: () => Promise<TipoVehiculo[] | undefined>, isFromFallback: boolean}` — `isFromFallback = data === HARDCODED_CATALOG` (comparación por referencia, NO deep-equal). `HARDCODED_CATALOG` constante inline módulo-level (DEC-F4.1-05 cohesión con el hook que la usa).

**Archivos a crear**:
- `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` (~30 LOC — `export interface TipoVehiculo { uuid: string; tipo: string | null; vigente_desde: string; vigente_hasta: string | null; estado: string }` matching backend `schemas/tipos_vehiculo.py:13-23` + `export async function getTiposVehiculo(): Promise<TipoVehiculo[]>` con `parkosFetch<TipoVehiculo[]>('/api/v1/catalogos/tipos-vehiculo')` + catch `ParkosHttpError(404)` → `return []` + filtro `items.filter(t => t.tipo !== null)` defensivo).
- `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (~80 LOC — `const HARDCODED_CATALOG: TipoVehiculo[] = [...]` constante inline módulo-level + `export function useTiposVehiculo(): UseTiposVehiculoReturn` con `useAuthStore(s => s.accessToken)` selector + `useSWR<TipoVehiculo[]>(accessToken ? '/catalogos/tipos-vehiculo' : null, () => getTiposVehiculo(), { fallbackData: HARDCODED_CATALOG, dedupingInterval: 5 * 60 * 1000, shouldRetryOnError: (err) => (err as ParkosHttpError)?.status !== 404, onError: (err) => { if (status === 401) { useAuthStore.getState().clear(); window.dispatchEvent(new Event('parkos:auth:cleared')) } } })` + `return { tipos: data ?? HARDCODED_CATALOG, isLoading, error: error?.status === 404 ? undefined : error, refresh: mutate, isFromFallback: data === HARDCODED_CATALOG }`).
- `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.test.ts` (~70 LOC — U7 SWR key null sin token (mock `useAuthStore` retornando `null` → `tipos: HARDCODED_CATALOG`, NO fetcher call), U8 SWR fetch OK con catálogo poblado (mock 200 OK), U9 fallback hardcoded cuando API 500 (mock 500 → `data === HARDCODED_CATALOG`, `isFromFallback: true`), U10 dedupingInterval = 5min (inspeccionar `swrOptions.dedupingInterval === 300000`), U11 onError con `status === 401` dispara `useAuthStore.getState().clear()` + `dispatchEvent('parkos:auth:cleared')` — precedent F3.3 `useSesionActiva.test.ts:1-211` verbatim).

**Archivos a modificar**:
- `apps/electron-sucursal/vitest.config.ts` (+3 LOC — coverage thresholds `'src/lib/validation/placa.ts': { lines: 95, functions: 95, branches: 90 }, 'src/features/catalogos/api/tiposVehiculoApi.ts': { lines: 90, functions: 90, branches: 85 }, 'src/features/catalogos/hooks/useTiposVehiculo.ts': { lines: 90, functions: 90, branches: 85 }` per design §7.3).

**Criterio de done**:
- U7..U11 verde en `pnpm vitest run src/features/catalogos/hooks/useTiposVehiculo.test.ts --coverage` (≥90% lines, ≥90% functions, ≥85% branches).
- `pnpm tsc --noEmit -p tsconfig.renderer.json` clean (zero TS errors en archivos nuevos).
- ESLint `--max-warnings 0` clean en `tiposVehiculoApi.ts` + `useTiposVehiculo.ts` + `useTiposVehiculo.test.ts`.
- SWR config verified: `dedupingInterval === 300000` + `fallbackData === HARDCODED_CATALOG` + `shouldRetryOnError(404) === false` (capture swrOptions pattern F3.3 verbatim).
- `onError` con 401 dispara `useAuthStore.getState().clear()` + `window.dispatchEvent(new Event('parkos:auth:cleared'))` — spy verification con `vi.spyOn(window, 'dispatchEvent')` (precedent F3.3 U4 verbatim).
- Working tree clean post-commit.

**Commit message esperado** (per DEC-F4.1-08 C2 independiente): `feat(catalogos): adicionar useTiposVehiculo() SWR + tiposVehiculoApi typed wrapper + 5 unit tests + fallback hardcoded {auto,moto} (HU-F4.1-T2)`.

---

### T3 — i18n key `operacion.placa_formato_invalido` (~3 LOC, agrupado en C1)

**Descripción**: Agrega 1 key top-level `placa_formato_invalido` al namespace pre-existente `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` con string literal verbatim `plan.md:1366` ("Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)"). Namespace pre-existente respeta F2.1 DEC-ELEC-06 verbatim (un namespace por bounded context — `operacion` para flujo de ingreso vehicular). NO requiere nuevo namespace. String literal sin variables de interpolación (`{{tipo}}` NO permitido). Consumida forward por F6.1 `<PlacaInput>` con `<p role="alert" aria-describedby="placa-input-error">{t('operacion.placa_formato_invalido')}</p>` para WCAG 2.1 AA compliance (REQ-OPS-130). Agrupado en C1 per DEC-F4.1-08 (cohesivo con T1 — la función SIN i18n key es incompleta para el caller que quiera mostrar el error).

**Archivos a modificar**:
- `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (+3 LOC — `"placa_formato_invalido": "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)"`). Namespace pasa de 10 keys F2.1 baseline a 11 keys post-F4.1.

**Archivos a crear**: (ninguno — T3 es additive key sobre namespace pre-existente. Snapshot test del JSON verifica la key + string verbatim — defense contra typo silencioso, F2.1 baseline precedent).

**Criterio de done**:
- `pnpm tsc --noEmit -p tsconfig.renderer.json` clean (i18next typing verifica que `t('operacion.placa_formato_invalido')` retorna string).
- ESLint `--max-warnings 0` clean.
- Snapshot test del JSON `operacion.json` estable con +1 key (sin regresión de las 10 keys pre-existentes F2.1).
- String literal verbatim `plan.md:1366` — sin variables de interpolación.
- Working tree clean post-commit.

**Commit message esperado**: T3 NO es commit independiente — se commitea agrupado con T1 en C1 per `DEC-F4.1-08` (`feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido (HU-F4.1-T1+T3)`).

---

## 3. Acceptance gates (G1..G7)

Cross-ref `proposal.md §6` + `design.md §13` + `exploration.md §9` + `specs/operations/spec.md §4.2` verbatim. Mapeo de gates a tests verificables:

| Gate | Task | Mechanism | File | Verification command |
|---|---|---|---|---|
| **G1** | T1 + T2 | TypeScript strict sin errores (`tsc -b` exit 0) | `placa.ts` + `placa.test.ts` + `tiposVehiculoApi.ts` + `useTiposVehiculo.ts` + `useTiposVehiculo.test.ts` | `pnpm tsc --noEmit -p tsconfig.renderer.json` |
| **G2** | T1 + T2 | ESLint sin errores (`--max-warnings 0`) | `placa.ts` + `placa.test.ts` + `tiposVehiculoApi.ts` + `useTiposVehiculo.ts` + `useTiposVehiculo.test.ts` | `pnpm lint` exit 0 |
| **G3** | T1 + T2 + T3 | 11 unit tests verde (`vitest run`) con cobertura ≥90% líneas / 80% branches per D9 F2.1 + F3.1 precedent | `placa.test.ts` U1..U6 + `useTiposVehiculo.test.ts` U7..U11 | `pnpm vitest run src/lib/validation/placa.test.ts src/features/catalogos/hooks/useTiposVehiculo.test.ts --coverage` |
| **G4** | T1 + T2 + T3 | Atomic commits (2 commits C1 + C2 con tests incluidos) | `git log --oneline` muestra los 2 commits siguiendo Conventional Commits sin Co-authored-by AI | `git log --format='%(trailers)' --grep='Co-authored-by'` debe retornar vacío |
| **G5** | T2 (hook SWR) | **Hard requirement** — `useTiposVehiculo()` SWR key MUST ser `null` cuando `useAuthStore.accessToken === null` (gate NO 401 noise on cold boot pre-login, precedent F3.3 `useSesionActiva` U1 verbatim) + `dedupingInterval === 300000` + `fallbackData === HARDCODED_CATALOG` + `shouldRetryOnError(404) === false` | `useTiposVehiculo.test.ts` U7 + U10 | `pnpm vitest run src/features/catalogos/hooks/useTiposVehiculo.test.ts` |
| **G6** | T2 (i18n key + detector forward) | WCAG 2.1 AA compliance forward F6.1 — la i18n key `operacion.placa_formato_invalido` + el detector determinista + `isFromFallback` flag sientan las bases para que `<PlacaInput>` use `aria-describedby` + `<p role="alert">` con 0 violaciones axe-core (REQ-OPS-130 forward coverage, RNF-022) | F4.1 NO entrega componente UI — G6 aplica al forward consumer F6.1 `<PlacaInput>`. Documentado como forward coverage per F2.x + F3.x precedent. | Forward (F6.1 axe-core scan — NOT F4.1 scope) |
| **G7** | T1 + T2 (e2e) | e2e sandbox F.6 SKIPPED-env (`npm 11.16.0` refuses `workspace:*`) | F4.1 NO entrega e2e — los 11 unit tests cubren la lógica pura. Documentado como deviation D-env per F2.x + F3.x precedent (verify-report future D-env). | Forward (no F4.1 scope — F6.1 entrega e2e `<PlacaInput>`) |

**Estado pre-flight target**: 0/7 PASS al inicio; **5/7 PASS** post-implementación (G1, G2, G3, G4, G5 PASS; G6 + G7 forward coverage / SKIPPED-env documentado). Cobertura de tests ≥90% líneas / 80% branches per D9 F2.1 + F3.x precedent.

**Sandbox F.6 caveat**: G6 + G7 documentados como deviation D-env en `verify-report.md` futuro (precedent F2.x + F3.x archive). NO project defect — F4.1 sienta primitives accesibles + lógica pura, F6.1 verifica con axe-core + e2e.

---

## 4. Review Workload Forecast

**LOC budget breakdown** (suma de T1..T3 per task specs, adaptado al scope `lib/validation/` + `features/catalogos/`):

| Task | Prod LOC | Unit tests LOC | i18n LOC | Total |
|---|---|---|---|---|
| T1 (`detectarTipoVehiculo` + `REGEX_AUTO` + `REGEX_MOTO` + `placa.test.ts`) | ~50 | ~80 | 0 | ~130 |
| T2 (`tiposVehiculoApi` + `useTiposVehiculo` + `useTiposVehiculo.test.ts` + `vitest.config.ts` MODIFY) | ~110 | ~70 | 0 | ~183 |
| T3 (`operacion.json` MODIFY +1 key) | 0 | 0 | ~3 | ~3 |
| **TOTAL** | **~160** | **~150** | **~3** | **~313** |

**Verdict**: **~313 LOC total** (production 160 + unit tests 150 + i18n 3 ≈ 313 LOC delta total). **BIEN DEBAJO del budget 800 LOC per `config.yaml rules.tasks`**. ~39% del budget total (ratio saludable para cambio atomizable).

**Comparación con presupuesto plan.md**: `plan.md:1383` verbatim "Tamaño estimado: 100 LOC" — F4.1 sobreexcede ese presupuesto en ~3x porque incluye tests + i18n + coverage thresholds configs. Sin embargo, `config.yaml rules.tasks` establece budget 800 LOC por HU/change (cross-ref `pending.md §4`), y **F4.1 está cómodamente debajo** (~313 LOC = 39% del budget).

**¿Split required?**: **NO**. ~313 LOC está bien dentro del budget 800. Cero necesidad de chained PR slice per `work-unit-commits` skill ("Low risk: keep work-unit commits inside one PR"). Single PR con 2 atomic commits C1+C2 es la estrategia óptima.

**¿Por qué 2 commits y no 1 monolítico?**: work-unit-commits skill categórico (F2.x + F3.x precedent verbatim): commits agrupan por **DELIVERABLE cohesivo**, NO por tarea atómica. F4.1 emite 2 commits porque:
- **C1 (T1+T3)**: la función pura + la i18n key son el mismo deliverable "detección de placa funciona en cliente". Cohesivos. Tests incluidos en mismo commit (work-unit hard rule).
- **C2 (T2)**: el hook SWR es deliverable independiente "catálogo de tipos se carga con degradación". Forward F4.3 podría consumir antes que F6.1 exista (peer con F4.2 hook).

2 commits permiten rollback granular (C1 rollback no toca C2 hook reusable y viceversa) — defense in depth a nivel de delivery. Ambos commits caben en single PR (suma ~313 LOC < 800 budget).

**Nota sobre cálculo**: el prompt inicial del orchestrator mencionó "~313 LOC (163 production + 150 tests)" — coincide con mi suma aritmética de los LOC per-task. La diferencia con la cifra "~293 LOC" del design §12.6 (`design.md:786`) se debe a que el design incluye el `vitest.config.ts` MODIFY (+3 LOC coverage thresholds) que el orchestrator agrupó en el total de "163 production". Mantengo el número honesto (~313 LOC) para reflejar el delta completo incluyendo configs.

---

## 5. Delivery strategy alignment

Cross-ref `work-unit-commits` skill + `sdd-apply` SDD workflow + `plan.md:1355-1388` + precedent F3.3 archivado verbatim.

**Delivery strategy**: **Single PR con 2 atomic commits** (chained PR slice NO requerida — bien dentro del budget 800 LOC, ~313 LOC = 39%).

**Work-unit commit strategy** (per work-unit-commits skill "Tell a story — a reviewer should understand why each commit exists from its diff and message"):

1. **Commit C1** (`feat(operacion)`) — `detectarTipoVehiculo()` función pura + `REGEX_AUTO` + `REGEX_MOTO` constantes exportadas + 6 unit tests + i18n key `operacion.placa_formato_invalido`. **Work unit**: detección de placa funciona en cliente (función + i18n + tests cohesivos per `DEC-F4.1-08`). Reviewable standalone. Rollback: `git revert <C1-commit>` elimina función pura — F6.1 forward bloqueado (sin función, F6.1 no puede arrancar; i18n key queda huérfana).
2. **Commit C2** (`feat(catalogos)`) — `useTiposVehiculo()` SWR hook + `tiposVehiculoApi` typed wrapper + `HARDCODED_CATALOG` constante inline + 5 unit tests + `vitest.config.ts` MODIFY (+3 coverage thresholds). **Work unit**: catálogo de tipos se carga con degradación explícita. Reviewable standalone. Rollback: `git revert <C2-commit>` revierte hook — F4.3 + F6.1 forward consumers bloqueados (sin hook, no pueden resolver `uuid_tipo_vehiculo`).

**Conventional commits** (per F2.1 + F3.1 + F3.2 + F3.3 precedent verbatim):

| Commit | Type | Scope | Mensaje |
|---|---|---|---|
| C1 (T1+T3) | `feat` | `operacion` | `feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido (HU-F4.1-T1+T3)` |
| C2 (T2) | `feat` | `catalogos` | `feat(catalogos): adicionar useTiposVehiculo() SWR + tiposVehiculoApi typed wrapper + 5 unit tests + fallback hardcoded {auto,moto} (HU-F4.1-T2)` |

**NO** `Co-authored-by` trailer (F2.1 canon — `git log --format='%(trailers)' --grep='Co-authored-by'` debe retornar vacío post-apply). **NO** AI attribution (per persona rules + canon de la organización `AGENTS.md`).

**PR target**: `origin/dev` per `AGENTS.md` gitflow authorization model (F4.1 = primera PR de Fase 4). PRs mergean a `dev` (nunca directo a `main`); cada rama certificada se mergea a `dev`, y de `dev` a `main` solo via release branch con certificación.

**Author identity** (per `AGENTS.md` §Git identity for sub-agent work): sub-agent runs set `user.name=gentle-ai-sub-agent, user.email=sub-agent@local`. Para evitar `Co-authored-by: gentle-ai-sub-agent <sub-agent@local>` trailer automático en squash merge, set neutral identity BEFORE merging: `git config user.name "Parkos Dev"` + `git config user.email "dev@parkos.local"`.

**Test commands focused por commit** (work-unit-commits skill hard rule: "Focused test command and exact result are recorded"):

| Commit | Focused test command | Expected result |
|---|---|---|
| C1 | `pnpm vitest run src/lib/validation/placa.test.ts --coverage` | 6 tests verde, ≥95% lines / ≥95% functions / ≥90% branches |
| C2 | `pnpm vitest run src/features/catalogos/hooks/useTiposVehiculo.test.ts --coverage` | 5 tests verde, ≥90% lines / ≥90% functions / ≥85% branches |

**Rollback boundaries** (work-unit-commits skill hard rule: "Rollback boundary names the exact files/behavior removable without unrelated work"):

| Commit | Rollback command | Files removed | Independent of |
|---|---|---|---|
| C1 | `git revert <C1-sha>` | `lib/validation/placa.ts` + `lib/validation/placa.test.ts` + `operacion.json` (1 key removed) | C2 hook + F2.x + F3.x intactos |
| C2 | `git revert <C2-sha>` | `features/catalogos/api/tiposVehiculoApi.ts` + `features/catalogos/hooks/useTiposVehiculo.ts` + `features/catalogos/hooks/useTiposVehiculo.test.ts` + `vitest.config.ts` (3 thresholds removed) | C1 función pura + F2.x + F3.x intactos |

---

## 6. DoD checklist

Cross-ref `proposal.md §16.4` + `design.md §11.5` + `exploration.md §13` + F3.3 precedent verbatim.

- [ ] **2 atomic commits C1 + C2** con author `Parkos Dev <dev@parkos.local>` (verificado via `git log --format='%an <%ae>'`).
- [ ] **NO Co-authored-by, NO AI trailers** en los 2 commits (verificado via `git log --format='%(trailers)'`).
- [ ] **Conventional commits** neutrales español: `feat(operacion)` × 1 (C1) + `feat(catalogos)` × 1 (C2).
- [ ] **`pnpm vitest --run` verde** en archivos nuevos: `placa.test.ts` (U1..U6) + `useTiposVehiculo.test.ts` (U7..U11) = **11 tests verde**.
- [ ] **`pnpm tsc --noEmit -p tsconfig.renderer.json` clean** en archivos nuevos (zero TS errors — G1).
- [ ] **ESLint `--max-warnings 0` clean** en archivos nuevos (G2).
- [ ] **Coverage thresholds** cumplidos per design §7.3: `placa.ts` ≥95% lines / ≥95% functions / ≥90% branches + `tiposVehiculoApi.ts` ≥90% lines / ≥90% functions / ≥85% branches + `useTiposVehiculo.ts` ≥90% lines / ≥90% functions / ≥85% branches.
- [ ] **SWR config verified**: `dedupingInterval === 300000` (5min) + `fallbackData === HARDCODED_CATALOG` + `shouldRetryOnError(404) === false` + `onError(401)` dispara `useAuthStore.getState().clear()` + `dispatchEvent('parkos:auth:cleared')` (G5 hard requirement).
- [ ] **`detectarTipoVehiculo` función pura** sin acceso a red/store/DOM, JSDoc referencia explícita `operacion.py:215-277` + DEC-SUC-22 + A-03 + BR2 (defense in depth XR6 layer 4 documentado).
- [ ] **`REGEX_AUTO` + `REGEX_MOTO` exportadas** como constantes módulo-level para reuso F6.1 Zod validation.
- [ ] **`HARDCODED_CATALOG` constante inline** con shape `[{uuid: '...0001', tipo: 'Auto'}, {uuid: '...0002', tipo: 'Moto'}]` + UUIDs sentinels literales (NO `crypto.randomUUID()` — DEC-F4.1-05 verbatim).
- [ ] **`operacion.json` snapshot estable** con +1 key `placa_formato_invalido` (string literal verbatim `plan.md:1366`, sin regresión de las 10 keys pre-existentes F2.1).
- [ ] **`isFromFallback: boolean` flag** en return del hook `useTiposVehiculo()` (DEC-F4.1-06 forward extensibility F4.3 + F6.x `<Tooltip>` "usando datos locales").
- [ ] **WCAG 2.1 AA foundation forward F6.1**: i18n key pre-poblada + detector determinista + `isFromFallback` flag sientan bases para axe-core 0 violaciones en `<PlacaInput>` (G6 forward coverage documentado, RNF-022).
- [ ] **e2e G7 SKIPPED-env** documentado (verify-report.md D-env — sandbox F.6 npm 11.16.0 refuses workspace:*; F4.1 NO entrega e2e per scope explícito).
- [ ] **No regresiones en suite Fase 1 + Fase 2 + Fase 3** (F1.x backend + F2.1+F2.2+F2.3+F3.1+F3.2+F3.3 frontend e2e siguen verdes post-merge F4.1).
- [ ] **CERO `any`** introducido en código nuevo (TS strict + lint).
- [ ] **Working tree clean post-apply** (`git status --short` retorna vacío post-archive).
- [ ] **`pending.md` §1 row F4.1 → ✅ cerrado** (archive phase post-verify).
- [ ] **`openspec/specs/operations/spec.md` REQ-OPS-125..130 mergeados** (post-archive byte count incrementado, numeración monotónica verificada 124 → 125..130).
- [ ] **i18n namespaces consistentes** — 0 nuevos namespaces; la nueva key vive en `operacion.json` namespace pre-existente (F2.1 DEC-ELEC-06 verbatim — un namespace por bounded context).
- [ ] **No `fetch` directo en código nuevo** — todo acceso a red vía `parkosFetch` (F2.2 invariant preserved).
- [ ] **No extensión de `PRE_FLIGHT_PATHS`** — `/catalogos/*` GET read idempotente NO requiere pre-flight gate (DEC-SUC-03 + F3.2 verbatim, F4.1 NO modifica `parkosFetch.ts`).

---

## 7. Forward hooks (qué consumer Fase 4+ va a leer)

Cross-ref `proposal.md §14` + `design.md §12.2 + §15.2` + `exploration.md §6.4` verbatim.

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F4.2** (Tarifas vigentes) | `useTarifasVigentes()` peer hook en mismo feature `catalogos` | Mismo patrón SWR token-gated + `dedupingInterval` + fallback. F4.2 usa `electron-store` persistente (NO hardcoded) — F4.1 sienta el pattern. F4.2 entrega independientemente. |
| **HU-F4.3** (Ocupación en vivo) | `<OcupacionStrip>` itera sobre tipos del catálogo para renderizar `Auto: 23/50` por tipo | `useTiposVehiculo()` provee la lista de tipos. F4.3 puede implementar su propio fetch si quiere (peer pattern). F4.1 exporta hook desde `features/catalogos/hooks/useTiposVehiculo.ts`. |
| **HU-F6.1** (Ingreso vehicular CU-01 — **CRÍTICO**) | `<PlacaInput>` consume `detectarTipoVehiculo()` + `useTiposVehiculo()` + `t('operacion.placa_formato_invalido')` | Llama `detectarTipoVehiculo(placa)` → si `null` muestra `<p role="alert" aria-describedby="placa-input-error">{t('operacion.placa_formato_invalido')}</p>` con WCAG 2.1 AA compliant; si `'Auto' | 'Moto'` setea `uuid_tipo_vehiculo` via `useTiposVehiculo().tipos.find(t => t.tipo === tipoDetectado)`. También importa `REGEX_AUTO` + `REGEX_MOTO` para validación Zod local (`z.string().regex(REGEX_AUTO) | z.string().regex(REGEX_MOTO)`). HU crítica — sin F4.1, F6.1 no puede arrancar. `pending.md §5` forward hook explícito. |
| **HU-F7.x** (Salida + búsqueda tolerante CU-02/03) | `buscarIngresoTolerante()` función DISTINTA en archivo NUEVO | DEC-SUC-22 categórico: NUNCA compartir función con F4.1. F7.x entrega función NUEVA con tolerancia `O↔0`/`I↔1`/`B↔8` que vive en archivo distinto (`lib/validation/placaTolerante.ts` forward — nombre tentativo). F4.1 sienta el precedent de separación clara. |
| **HU-F8.x** (Cobro + FE) | Depende F7.x → consume transitivo | F8.x consume `uuid_tipo_vehiculo` en `<Factura>` via hook F4.1 + F6.1. |
| **HU-F11.x** (Sync UI + alertas CU-07/14) | Si sync incluye `tipos_vehiculo`, el hook debe invalidarse post-sync | `mutate('/catalogos/tipos-vehiculo')` post-sync event (forward hook — no F4.1 scope). F4.1 exporta `refresh: () => Promise<TipoVehiculo[]>` que F11.x puede invocar post-sync. |
| **HU-F13.x** (Reportería) | `<ReporteOcupacion>` itera sobre tipos | F13.x consume vía SWR shared cache (mismo `useTiposVehiculo()` hook, dedupingInterval compartido). |
| **HU-F6.x+ AuthGuard** | `parkos:auth:cleared` event emitido por 401 path | AuthGuard intercepta → `navigate('/login?next=...')`. F4.1 emite el evento verbatim (T2 `onError` 401). |

**Gating transversal confirmado**: F4.1 es prerequisite para **HU-F6.1** (ingreso vehicular CU-01, flujo crítico de la operación) y opcionalmente para **F4.2** (peer pattern) + **F4.3** (consumer directo) + **F7.x** (peer pattern función tolerante). Sin F4.1, F6.1 no puede arrancar — `pending.md §5` forward hook explícito: "F6.x (ingreso vehicular CU-01) consume F3.3 turno activo + F4.x catálogos". Función `detectarTipoVehiculo()` + hook `useTiposVehiculo()` + i18n key `operacion.placa_formato_invalido` son los single source of truth para "tipo de vehículo detectado" a través de toda la Fase 4+.

---

## CHANGELOG

- (2026-09-16) **F4.1 tasks phase complete** — 3 atomic tasks T1..T3 across 2 clusters C1+C2 (orden interno T1 → T3 → C1 COMMIT → T2 → C2 COMMIT). **~313 LOC total** (production 160 + unit tests 150 + i18n 3 ≈ 313 LOC delta total, ~39% del budget 800 per `config.yaml rules.tasks`). 7 acceptance gates G1..G7 (G1 typecheck 5 archivos, G2 lint 5 archivos, G3 vitest 11 tests verde U1..U11, G4 atomic commits 2 commits C1+C2 con tests incluidos, G5 SWR key null + deduping 5min + fallback hardcoded + 401 clear hard requirements, G6 WCAG 2.1 AA forward F6.1, G7 e2e SKIPPED-env D-env documentado). 11 DEC-F4.1-01..11 ratified (cross-ref proposal §4 + exploration §7 + design §5). 6 new REQ-OPS-125..130 user-facing (DEC-F4.1-07 + DEC-F4.1-11 DELTA verdict — F4.1 ES user-facing precedent F1.15 + F3.1 + F3.2 + F3.3 verbatim). T1 entrega `detectarTipoVehiculo()` función pura reusable con regex estricto hardcoded + normalización trivial + exports `REGEX_AUTO` + `REGEX_MOTO` para F6.1 Zod (forward consumer crítico). T2 entrega `useTiposVehiculo()` primer hook genuinely reusable del feature `catalogos` + `tiposVehiculoApi` typed wrapper + `HARDCODED_CATALOG` fallback `{auto, moto}` con UUIDs sentinels literales + SWR config verbatim F3.3 `useSesionActiva` precedent con `dedupingInterval: 5 * 60 * 1000` (plan.md:1375 verbatim 5min catálogos). T3 entrega i18n key `operacion.placa_formato_invalido` con string literal verbatim `plan.md:1366` agrupada en C1 (cohesiva con T1). 2 atomic commits per `DEC-F4.1-08` (C1: T1+T3 agrupados cohesivos "detección de placa funciona en cliente"; C2: T2 independiente "catálogo de tipos se carga con degradación"). Single-PR strategy (NO chained slice needed — ~313 LOC bien debajo del budget 800). Precedente directo: F3.3 archivado 2026-09-15 (5 tasks T1..T5 single-cluster C1 end-to-end ~650 LOC) — F4.1 adapta el layout 1:1 con split 2 clusters para reflejar el work-unit cohesivo de DEC-F4.1-08. Sandbox F.6 caveat documentado (e2e G7 SKIPPED-env local, F4.1 NO entrega e2e per scope — lógica pura cubierta por 11 unit tests). Ready for `sdd-apply`.

---

**End of tasks — HU-F4.1.**
