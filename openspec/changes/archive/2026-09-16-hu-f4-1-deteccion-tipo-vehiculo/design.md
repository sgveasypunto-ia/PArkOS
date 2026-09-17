# Design — HU-F4.1 Detección de tipo de vehículo por placa (función pura `detectarTipoVehiculo()` estricto + hook SWR `useTiposVehiculo()` con fallback hardcoded `{auto, moto}`)

> **Change**: `hu-f4-1-deteccion-tipo-vehiculo` · **Folder**: `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/`
> **Phase**: design (sdd-design) · **Status**: ready for `sdd-tasks`
> **HU ID**: HU-F4.1 (Fase 4 — primera HU; Catálogos y ocupación en vivo)
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feature/hu-f4-1-deteccion-tipo-vehiculo` (clean, recién creada desde `dev`) · **PR target**: `origin/dev` (gitflow, F4.1 = primera PR de Fase 4)
> **Inputs**: `proposal.md` (~758 LOC, 11 secciones, 11 DEC-F4.1-01..11 ratified, DEC-F4.1-07 + DEC-F4.1-11 verdict DELTA, 6 new REQ-OPS-125..130 user-facing), `exploration.md` (input explore phase — ~512 LOC, 16 secciones, 10 DEC-F4.1-01..10, 5 riesgos R1..R5, 7 acceptance gates G1..G7, pre-flight 10/10 PASS + 0 KNOWN-MISSING), `openspec/changes/archive/2026-09-15-hu-f3-3-abrir-cerrar-turno/design.md` (precedente verbatim ~1394 LOC — layout canónico clonado 1:1 con adaptación al scope función pura + hook SWR, sin UI containers), `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts:1-89` (SWR token-gated hook pattern precedent — `accessToken ? key : null` + `dedupingInterval: 10s` + `shouldRetryOnError` excluye 404 + `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event), `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.test.ts:1-211` (verbatim test pattern: vi.mock módulos + captura swrOptions para inspeccionar config), `apps/ui-kit/src/fetch/parkosFetch.ts:1-212` (F2.2+F3.2 primitive — retry + refresh-once 401 via Mutex + Idempotency-Key; PRE_FLIGHT_PATHS sin cambios F4.1 porque `/catalogos/*` GET read idempotente NO requiere pre-flight gate DEC-SUC-03 + F3.2 verbatim), `apps/ui-kit/src/store/authStore.ts:71-128` (F2.2 primitive — `setTokens` atómico + `clear()` borra tokens vía IPC `bridge.authStore.delete` + dispatch `parkos:auth:cleared`), `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py:215-277` (READ ONLY — `detectar_tipo_vehiculo()` server-side shipped HU-F1.x, defense in depth XR6 layer 4, regex hardcoded idéntica cliente/backend), `backend/packages/parkos_core/src/parkos_core/api/v1/catalogos.py:140-147` (READ ONLY — `_mount_catalog(resource="tipos-vehiculo", ...)` C+Q+U router SHIPPED con permission `config_catalogo` per `_CATALOG_DEFAULTS:101`), `backend/packages/parkos_core/src/parkos_core/schemas/tipos_vehiculo.py:13-23` (`TiposVehiculoRead` shape cliente consume), `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json:1-12` (10 keys pre-existentes F2.1 baseline; F4.1 +1 key `placa_formato_invalido`), `apps/electron-sucursal/vitest.config.ts:1-23` (F2.1 baseline vitest jsdom + globals + alias `@/` → `src/renderer`; F4.1 NO requiere changes estructurales, solo agrega thresholds), `plan.md:1355-1388` (HU-F4.1 verbatim, ~250 LOC, 3 tareas atómicas T1..T3), `plan.md:437` (DEC-SUC-22 stricta sin tolerancia), `plan.md:454` (A-03 regex hardcoded en `src/lib/validation/placa.ts` cliente), `plan.md:1369` (BR2 CU-01 literal), `docs/01-requisitos/no-funcionales.md:126` (RNF-022 WCAG 2.1 AA), `pending.md §5` (F6.x ingreso vehicular CU-01 consume F3.3 turno activo + F4.x catálogos), `pending.md §1 row F4.1` (~250 LOC).
> **Language**: español neutro profesional · **Conventional commits**: `feat(operacion)` / `feat(catalogos)` / `test(electron)` — sin Co-authored-by.

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F4.1 |
| **Fase** | 4 (Catálogos y ocupación en vivo — primera HU) |
| **Change name** | `hu-f4-1-deteccion-tipo-vehiculo` |
| **Folder** | `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/` |
| **State** | design ready |
| **Branch** | `feature/hu-f4-1-deteccion-tipo-vehiculo` (clean) |
| **PR target** | `origin/dev` |
| **Author** | Parkos Dev |
| **Date** | 2026-09-16 |
| **Phase precedente** | sdd-explore + sdd-propose + sdd-spec (paralelo) |
| **Próximo phase** | sdd-tasks |
| **DEC ratified** | 11 DEC-F4.1-01..11 (DEC-F4.1-07 + DEC-F4.1-11 verdict DELTA — F4.1 ES user-facing) |
| **REQ-OPS range** | REQ-OPS-125..130 (6 new requirements, continuación monotónica post F3.3 REQ-OPS-124) |
| **LOC target** | ~163 producción + ~130 tests + ~3 i18n = **~296 LOC total** |
| **Conventional commits** | `feat(operacion)` / `feat(catalogos)` / `test(electron)` — sin Co-authored-by |
| **Verdict** | **DELTA** (NOT NO-OP) — F4.1 ES user-facing behavior observable: autocompletar tipo + error inline i18n + catálogo con fallback degradado |

---

## 1. Contexto técnico

### 1.1 AS-IS verificado (estado actual F3.1 + F3.2 + F3.3 archivados)

F3.1 archivado 2026-09-15 entrega `POST /auth/login` + `useAuth` SWR + `LoginForm` container/presentational + RHF+Zod + i18n namespace `auth.json` (15 keys) + 7 REQ-OPS-106..112. F3.2 archivado 2026-09-15 entrega `useCountdown` hook reusable + lockout visible + refresh transparente 50min (`REFRESH_INTERVAL_MS = 50 * 60 * 1000` heredado de DEC-SUC-03 plan.md:418) + pre-flight gate en `parkosFetch.ts` (`PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/`) + 6 REQ-OPS-113..118. F3.3 archivado 2026-09-15 entrega `useSesionActiva()` SWR hook + `AbrirTurno`/`CerrarTurno` pages + `Dashboard` + `TurnoActivoPanel` + Login `?closed=true` detection + 6 REQ-OPS-119..124 + 4 atomic commits + 4 e2e scenarios. **El flujo crítico de la operación de parqueadero (ingreso vehicular CU-01) sigue sin la pieza cliente que autocompleta el tipo de vehículo**: el operador debe seleccionar Auto / Moto manualmente en dos pasos separados. Esto choca con BR2 de CU-01 verbatim ("autodetección por regex es la ÚNICA fuente válida; NO hay override manual del cajero; si falla, se corrige como bug", plan.md:1369).

F4.1 entrega la pieza fundamental: función pura `detectarTipoVehiculo()` (sin UI, sin red, sin store) + hook SWR `useTiposVehiculo()` con fallback hardcoded `{auto, moto}` + i18n key `operacion.placa_formato_invalido` para consumo forward F6.1 `<PlacaInput>`. NO toca backend (ya shipped `detectar_tipo_vehiculo()` server-side en `operacion.py:215-277` defense in depth XR6 layer 4). NO entrega componente UI (forward F6.1).

**Inputs verificados**:

- `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts:1-89` — F3.3 SWR hook shipped (`accessToken ? key : null` + `refreshInterval: REFRESH_INTERVAL_MS = 50min` + `dedupingInterval: 10s` + `shouldRetryOnError` excl 404 + `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event). F4.1 replica el pattern con deduping 5min (no 50min refresh — catálogos reference data).
- `apps/ui-kit/src/fetch/parkosFetch.ts:1-212` — F2.2+F3.2 primitive (`Idempotency-Key` SHA-256 auto para POST, skip `/auth/login` only + `handle401` Mutex refresh-once + `PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/`). F4.1 consume; **NO modifica** `PRE_FLIGHT_PATHS` — `/catalogos/*` GET read idempotente NO requiere pre-flight gate (DEC-SUC-03 + F3.2 verbatim precedent).
- `apps/ui-kit/src/store/authStore.ts` — F2.2 primitive (`accessToken` + `refreshToken` + `expiresAt` + `setTokens` atómico + `clear()` borra tokens vía IPC `bridge.authStore.delete`). F4.1 consume `accessToken` para SWR key + `clear()` post-401 (precedent F3.3 verbatim).
- `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json:1-12` — 10 keys pre-existentes (F2.1 baseline). F4.1 agrega 1 key `placa_formato_invalido` (DEC-F4.1-11 namespace pre-existente).
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py:215-277` — READ ONLY: `detectar_tipo_vehiculo()` server-side shipped HU-F1.x (defense in depth XR6 layer 4, regex idéntica cliente/backend, server overwrites via V5 "regex-derived UUID wins over client value", operacion.py:261 verbatim).
- `backend/packages/parkos_core/src/parkos_core/api/v1/catalogos.py:140-147` — READ ONLY: `_mount_catalog(resource="tipos-vehiculo", ...)` C+Q+U router SHIPPED con permission `config_catalogo` per `_CATALOG_DEFAULTS:101`. Verificación I2 resuelta en `proposal.md` §6.
- `backend/packages/parkos_core/src/parkos_core/schemas/tipos_vehiculo.py:13-23` — READ ONLY: `TiposVehiculoRead` con `uuid: UUID, tipo: str | None, vigente_desde: datetime, vigente_hasta: datetime | None, estado: str`. Cliente mapea `tipo: string | null`.
- `apps/electron-sucursal/vitest.config.ts:1-23` — F2.1 baseline (`environment: 'jsdom'` + `globals: true` + alias `@/` → `src/renderer`). F4.1 agrega coverage thresholds para nuevos archivos.

### 1.2 Gap UX que F4.1 cierra

Tres pain points UX rompen la promesa BR2 + DEC-SUC-22 + kiosko desatendido del `plan.md:418`:

1. **Pain #1 — Operador selecciona tipo manualmente (fraude potencial)**: cuando el operador llega al flujo de ingreso vehicular (HU-F6.1 forward, sin F4.1), debe tipear placa + seleccionar manualmente tipo en un `<Select>` o `<RadioGroup>`. Viola BR2 literal + abre puerta a fraude (marcar "Auto" cuando es Moto = tarifa menor). F4.1 entrega la función pura + i18n key que F6.1 `<PlacaInput>` consume para llenar `uuid_tipo_vehiculo` automáticamente — operador NO elige.
2. **Pain #2 — Catálogo `tipos_vehiculo` sin hook cliente = fetch repetido**: múltiples componentes futuros (F4.3 `<OcupacionStrip>` + F6.1 `<PlacaInput>` + F7.x `<SalidaFlow>`) van a necesitar la lista. Sin hook compartido, cada componente hace su propio fetch. F4.1 entrega `useTiposVehiculo()` con `dedupingInterval: 5min` — único fetch cada 5min compartido vía SWR cache (precedent F3.3 `useSesionActiva` con deduping 10s).
3. **Pain #3 — Catálogo API down = pantalla rota**: si la API está down (sync atrasado, db offline, server restart), componentes que consumen el catálogo quedan en loading permanente o crash. F4.1 implementa `fallbackData: HARDCODED_CATALOG` con `{auto, moto}` + UUIDs sentinels — degradación explícita (nunca pantalla rota, plan.md:1375 verbatim). `isFromFallback: boolean` permite consumers futuros mostrar indicador visual.

### 1.3 TO-BE resumido (entregables end-to-end verificables)

1. **`detectarTipoVehiculo()` función pura** (T1 ~50 LOC production + ~80 LOC tests). Signature `(placa: string) => 'Auto' | 'Moto' | null`. Sin acceso a red, store, DOM. Normalización previa (trim + uppercase + remover whitespace interno) antes de aplicar regex. Exporta `REGEX_AUTO` + `REGEX_MOTO` como constantes módulo-level para reuso en validación Zod (F6.1 forward). JSDoc verbatim DEC-SUC-22 + A-03 + BR2 + `operacion.py:215-277` backend counterpart.
2. **`useTiposVehiculo()` hook SWR** (T2 ~80 LOC production + ~40 LOC tests). SWR key `accessToken ? '/catalogos/tipos-vehiculo' : null` (precedent F3.3 verbatim). `dedupingInterval: 5 * 60 * 1000` (plan.md:1375 verbatim — 5min para catálogos). `fallbackData: HARDCODED_CATALOG` con `{auto, moto}` + UUIDs sentinels. `shouldRetryOnError` excluye 404. `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event. Retorna `{tipos, isLoading, error, refresh, isFromFallback}`.
3. **`tiposVehiculoApi` typed wrapper** (T2 ~30 LOC production). `getTiposVehiculo(): Promise<TipoVehiculo[]>` — `parkosFetch<TiposVehiculoReadList>('/api/v1/catalogos/tipos-vehiculo')` con mapeo 404 → `[]` + filtro defensivo de filas con `tipo: null`. Interface `TipoVehiculo` matching backend `TiposVehiculoRead` (schemas/tipos_vehiculo.py:13-23).
4. **i18n key `operacion.placa_formato_invalido`** (T3 +1 key JSON, ~3 LOC). Namespace pre-existente (F2.1 DEC-ELEC-06). String literal verbatim plan.md:1366 ("Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)") consumido por F6.1 `<PlacaInput>` `<p role="alert">{t('operacion.placa_formato_invalido')}</p>` forward.
5. **11 unit tests verde** (6 placa U1..U6 + 5 useTiposVehiculo U7..U11). Cobertura ≥90% líneas / 80% branches per D9 F2.1 + F3.x precedent.
6. **2 atomic commits** (work-unit-commits skill F2.x + F3.x precedent): C1 `feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido (HU-F4.1-T1+T3)`. C2 `feat(catalogos): adicionar useTiposVehiculo() SWR + fallback hardcoded {auto,moto} + 5 unit tests (HU-F4.1-T2)`. Tests incluidos con código.

### 1.4 Hard constraints (mirrored from `plan.md:1363-1377` verbatim)

- Placa `ABC123` → detecta `Auto` (regex `^[A-Z]{3}[0-9]{3}$`).
- Placa `ABC12D` → detecta `Moto` (regex `^[A-Z]{3}[0-9]{2}[A-Z]$`).
- Placa que no matchea ningún regex → error inline "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)" (consumido por F6.1 forward).
- **DEC-SUC-22 — estricta sin tolerancia**: NUNCA aplica `O↔0`/`I↔1`/`B↔8` en detección de ingreso. Esa tolerancia es exclusiva de `buscarIngresoTolerante()` (Fase 7).
- **A-03 — regex hardcoded en `src/lib/validation/placa.ts` del cliente**: NO columna del ER `tipos_vehiculo` (4NF canon).
- **BR2 de CU-01 literal**: autodetección por regex es la ÚNICA fuente válida; NO hay override manual del cajero; si falla, se corrige como bug.
- Tamaño: ~250 LOC production + tests + configs.
- 3 tareas atómicas T1..T3 → 2 commits C1+C2 per DEC-F4.1-08.
- Pruebas: 6 casos unitarios placa (`Auto`, `Moto`, formato inválido, placa vacía, minúsculas normalizadas, placa con espacios).

### 1.5 No-objetivos (cross-ref proposal §3.2 / exploration §2.2)

- Backend cambios — `detectar_tipo_vehiculo()` server-side ya shipped HU-F1.x (`operacion.py:215-277`). `GET /api/v1/catalogos/tipos-vehiculo` C+Q+U router ya shipped (catalogos.py:140-147 F1.x + F3.0 precedent). F4.1 NO modifica backend.
- UI componente `<PlacaInput>` — HU-F6.1 entrega el componente que consume `detectarTipoVehiculo()` + `useTiposVehiculo()` + renderiza el mensaje de error. F4.1 entrega SOLO la función pura + el hook del catálogo + la i18n key.
- Selector manual de tipo de vehículo — corpus categórico (BR2 + DEC-SUC-22). NO existe `<Select>` ni `<RadioGroup>` para tipo. Operador kiosko NUNCA selecciona manualmente.
- Tolerancia de tipeo `O↔0`/`I↔1`/`B↔8` — pertenece a `buscarIngresoTolerante()` Fase 7. F4.1 entrega función estricta sin tolerancia.
- Migraciones Alembic — ninguna tabla nueva ni columna nueva (regex vive en código cliente).
- `electron-store` fallback persistente — plan.md menciona fallback hardcoded `{auto, moto}`, NO persistente entre sesiones (a diferencia de HU-F4.2 tarifas que usa electron-store). Catálogos reference data — fallback hardcoded suficiente.
- `refreshInterval` periódico — SWR usa solo `dedupingInterval`. NO `refreshInterval` (catálogos cambian muy raramente — operador no espera actualización en tiempo real).
- e2e test (Playwright) — F4.1 es lógica pura. Los 11 unit tests cubren la lógica. e2e (Playwright) testeará la integración cuando F6.1 consuma la función en `<PlacaInput>`. Sandbox F.6 SKIPPED-env (npm 11.16.0 limit) — D-env en verify-report futuro.
- WCAG axe-core scan runtime — 11 unit tests cubren lógica. axe-core A1 scan es para HU-F6.1 (`<PlacaInput>` componente visible). F4.1 NO entrega componente UI, NO aplica axe-core scan runtime.
- i18n plurals — mensaje de error es string único (no plural). NO requiere `i18next-resources-types`.
- `crypto.randomUUID()` para fallback uuids — fallback hardcoded usa UUIDs sentinels literales (`'00000000-0000-0000-0000-000000000001'` y `...0002`). NO generados dinámicamente — son sentinels de FALLBACK, no IDs reales para sync.
- Tipos de vehículo adicionales (`Bicicleta`, `Camión`, `Moto eléctrica`) — A-03 explícito: "no hay respaldo en el corpus de CU para un tercer patrón". Si el negocio lo requiere, se agrega como decisión de producto explícita (DEC-F4.1-NN futura), no como dato asumido.
- Decoradores TypeScript / runtime guards — la función es pura; no requiere validador runtime externo. F6.x Zod usa las constantes `REGEX_AUTO` + `REGEX_MOTO` exportadas (no la función).
- Permisos granulares por acción — backend ya emite 403 si `permisos[]` no incluye `config_catalogo` (per `_CATALOG_DEFAULTS:101`). F4.1 NO agrega client-side permission gating — backend source of truth (Defense in depth XR6).

---

## 2. Arquitectura propuesta

### 2.1 Tree delta (target)

```
apps/electron-sucursal/
├── src/
│   ├── lib/
│   │   └── validation/                                ← NEW feature folder T1
│   │       ├── placa.ts                               ← NEW (~50 LOC — función pura + JSDoc + REGEX_AUTO + REGEX_MOTO)
│   │       └── placa.test.ts                          ← NEW (~80 LOC — U1..U6 verbatim plan.md:1381)
│   └── features/
│       └── catalogos/                                 ← NEW feature folder T2 (pre-existente carpeta vacía)
│           ├── api/
│           │   ├── tiposVehiculoApi.ts                ← NEW (~30 LOC — getTiposVehiculo() wrapper + 404 → [] + filtro tipo null)
│           │   └── tiposVehiculoApi.test.ts           ← NEW (~20 LOC — U5a..U5b api coverage)
│           └── hooks/
│               ├── useTiposVehiculo.ts                ← NEW (~80 LOC — SWR key null + deduping 5min + fallback hardcoded + 401 clear)
│               └── useTiposVehiculo.test.ts           ← NEW (~50 LOC — U7..U11)
└── src/renderer/i18n/locales/operacion.json           ← MODIFY (+1 key placa_formato_invalido)
```

**NEW total**: 5 archivos (~290 LOC production + ~150 LOC tests = ~440 LOC). Sin e2e (F4.1 lógica pura).
**MODIFY total**: 1 archivo (i18n operacion.json) = +3 LOC.
**Total impact**: 6 archivos = ~293 LOC total.

### 2.2 Data flow + SWR/Zustand boundaries

```
┌────────────────────── Renderer (React 18 + SWR + Zustand + TypeScript strict) ────────────────────┐
│                                                                                                  │
│   <PlacaInput>  (HU-F6.1 forward — consume F4.1)                                                 │
│   ├── useForm<{placa}>() with zodResolver(...)                                                    │
│   │     + z.string().regex(REGEX_AUTO) o .regex(REGEX_MOTO)                                      │
│   ├── detectarTipoVehiculo(form.placa) → 'Auto'|'Moto'|null                                       │
│   │     → si null: <p role="alert">                                                              │
│   │              {t('operacion.placa_formato_invalido')}</p>                                      │
│   │     → si 'Auto'|'Moto': setea uuid_tipo_vehiculo via                                          │
│   │       useTiposVehiculo().tipos.find(t => t.tipo === ...)                                      │
│                                                                                                  │
│   detectarTipoVehiculo  (NEW ~50 LOC, T1)                                                         │
│   ├── detectarTipoVehiculo(placa: string): 'Auto'|'Moto'|null                                    │
│   │   internals:                                                                                  │
│   │     1. const normalizada = placa.trim().toUpperCase().replace(/\s+/g, '')                    │
│   │     2. if (REGEX_AUTO.test(normalizada)) return 'Auto'                                       │
│   │     3. if (REGEX_MOTO.test(normalizada)) return 'Moto'                                       │
│   │     4. return null                                                                           │
│   └── exports:                                                                                    │
│         REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/                                                         │
│         REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/                                                    │
│                                                                                                  │
│   useTiposVehiculo  (NEW ~80 LOC, T2)                                                             │
│   ├── useTiposVehiculo(): { tipos, isLoading, error, refresh, isFromFallback }                   │
│   │   internals:                                                                                  │
│   │     accessToken = useAuthStore(s => s.accessToken)                                           │
│   │     HARDCODED_CATALOG: TipoVehiculo[] = [                                                     │
│   │       { uuid: '...0001', tipo: 'Auto', vigente_desde:                                         │
│   │         '2026-01-01T00:00:00Z', vigente_hasta: null, estado: 'activo' },                     │
│   │       { uuid: '...0002', tipo: 'Moto', vigente_desde:                                         │
│   │         '2026-01-01T00:00:00Z', vigente_hasta: null, estado: 'activo' }                       │
│   │     ]                                                                                          │
│   │     useSWR(                                                                                   │
│   │       key: accessToken ? '/catalogos/tipos-vehiculo' : null,                                 │
│   │       fetcher: () => tiposVehiculoApi.getTiposVehiculo(),                                     │
│   │       fallbackData: HARDCODED_CATALOG,                                                        │
│   │       dedupingInterval: 5 * 60 * 1000,                                                        │
│   │       shouldRetryOnError: (err) => err?.status !== 404,                                       │
│   │       onError: (err) => if (err?.status === 401) {                                            │
│   │                          useAuthStore.getState().clear()                                      │
│   │                          window.dispatchEvent(                                                │
│   │                            new Event('parkos:auth:cleared'))                                  │
│   │                        }                                                                       │
│   │     )                                                                                          │
│   │     isFromFallback = data === HARDCODED_CATALOG                                              │
│                                                                                                  │
│   tiposVehiculoApi  (NEW ~30 LOC, T2)                                                             │
│   └── getTiposVehiculo(): Promise<TipoVehiculo[]>                                                  │
│         → parkosFetch<TiposVehiculoReadList>('/api/v1/catalogos/tipos-vehiculo')                  │
│         → if status 404: return []                                                                │
│         → filter rows where tipo !== null                                                          │
│         → return items.map(toTipoVehiculo)                                                         │
│                                                                                                  │
└────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                     │ parkosFetch (F2.2 + F3.2 Idempotency-Key auto + handle401 Mutex)
                                     │ GET /api/v1/catalogos/tipos-vehiculo  (SWR key '/catalogos/tipos-vehiculo')
                                     ▼
┌────────────────────────── Backend FastAPI (HU-F1.x + F3.0 catalogos precedent READ ONLY) ─────────┐
│                                                                                                  │
│   GET /api/v1/catalogos/tipos-vehiculo                                                            │
│   ├── permission_required='config_catalogo' (admin-, operador-)                                   │
│   ├── 200 OK → TiposVehiculoReadList (lista de {uuid, tipo, vigente_desde,                       │
│   │             vigente_hasta, estado, created_at, ...})                                         │
│   ├── 404 → catálogo no encontrado (sucursal sin tipos) → cliente mapea a []                    │
│   └── 403 → permission denied                                                                    │
│                                                                                                  │
│   backend detectar_tipo_vehiculo() (HU-F1.x READ ONLY)                                            │
│   ├── Defense in depth XR6 layer 4 (operacion.py:215-277)                                          │
│   ├── Server overwrites via V5: "regex-derived UUID wins over client value" (operacion.py:261)    │
│   └── Same regex cliente + backend:                                                                │
│        Auto: ^[A-Z]{3}[0-9]{3}$                                                                   │
│        Moto: ^[A-Z]{3}[0-9]{2}[A-Z]$                                                              │
│                                                                                                  │
└────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                     │ consume via useTiposVehiculo + detectarTipoVehiculo
                                     ▼
┌──────────────────────────── ui-kit (apps/ui-kit/src/) ──────────────────────────────────────────────┐
│                                                                                                  │
│   parkosFetch.ts  (F2.2+F3.2 READ-ONLY, F4.1 consume)                                             │
│   ├── Idempotency-Key auto SHA-256 (skip /auth/login only)                                        │
│   ├── handle401 Mutex refresh-once (DEC-FETCH-03 invariant preserved)                              │
│   └── PRE_FLIGHT_PATHS sin cambios (DEC-F4.1: /catalogos/* GET read idempotente NO requiere gate) │
│                                                                                                  │
│   useAuth.ts  (F2.2+F3.2 READ-ONLY, F4.1 NO consume REFRESH_INTERVAL_MS — catálogos no refresh) │
│                                                                                                  │
│   authStore.ts  (F2.2 READ-ONLY, F4.1 consume useAuthStore para SWR key + onError clear)         │
│   ├── accessToken / refreshToken / expiresAt (ISO 8601)                                           │
│   ├── setTokens(access, refresh, expiresIn) → atomic update                                        │
│   ├── clear() → all 3 → null                                                                       │
│   └── refreshAccessToken() ──► Mutex singleton (F2.2 DEC-FETCH-03)                                │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Principios arquitectónicos

1. **Pureza absoluta de la función detector** (DEC-F4.1-01): `detectarTipoVehiculo(placa: string): 'Auto' | 'Moto' | null` es determinista, sin acceso a red/store/DOM. Testeable sin mocks (6 tests). Consumida por F6.1 `<PlacaInput>` (forward).
2. **Normalización trivial antes del regex** (DEC-F4.1-02): `(a) trim inicio/fin; (b) uppercase; (c) replace(/\s+/g, '')` para remover TODOS los whitespace internos. Cubre tests U5 (minúsculas) + U6 (espacios) sin regex tolerantes. NO extiende DEC-SUC-22 (esa es OTRO nivel de tolerancia).
3. **Regex como constantes exportadas** (DEC-F4.1-03): `REGEX_AUTO` + `REGEX_MOTO` exportadas módulo-level para que F6.1 las importe y use en validación Zod (`z.string().regex(REGEX_AUTO)`). DRY + UN solo punto de cambio si negocio evoluciona el patrón.
4. **SWR deduping 5min, sin refresh activo** (DEC-F4.1-04): `dedupingInterval: 5 * 60 * 1000` evita refetch entre consumers concurrentes (`<PlacaInput>` F6.1 + `<OcupacionStrip>` F4.3 + futuras pantallas). Catálogo reference data — operador no espera actualización en tiempo real. Si admin cambia `tipos_vehiculo`, próximo refresh SWR (5min) o al cerrar/abrir turno.
5. **Fallback hardcoded con UUIDs sentinels literales** (DEC-F4.1-05): `HARDCODED_CATALOG` inline en el hook. UUIDs literales `'00000000-...-0001'` y `...0002` — NO `crypto.randomUUID()` (sería bug latente). Cubre Auto+Moto (los 2 tipos que la regex puede detectar).
6. **`isFromFallback` flag en return del hook** (DEC-F4.1-06): comparación por referencia `data === HARDCODED_CATALOG`. Consumers futuros (F6.x tooltip "usando datos locales") pueden mostrar indicador visual sutil. Cheap de agregar upfront.
7. **`useTiposVehiculo` SWR key null-when-no-token** (precedent F3.3 verbatim): `accessToken ? '/catalogos/tipos-vehiculo' : null`. Sin fetch cuando operador no autenticado. Gate crítico contra 401 noise pre-login.
8. **`shouldRetryOnError` excluye 404** (precedent F3.3 verbatim): catálogo vacío es estado válido (sucursal nueva sin tipos configurados). NO reintentar 404.
9. **`onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event** (precedent F3.3 verbatim): logout defensivo si token expira mid-fetch. Forward F6.x+ AuthGuard consume el event.
10. **Función pura sin tolerancia de tipeo** (DEC-SUC-22 verbatim): NUNCA aplica `O↔0`/`I↔1`/`B↔8`. Esa tolerancia es exclusiva de `buscarIngresoTolerante()` (Fase 7). F4.1 sienta el precedent de separación clara entre las dos funciones.
11. **Tipo de retorno explícito union literals** (DEC-F4.1-01): `'Auto' | 'Moto' | null` (NO enum TypeScript). Mejor tree-shaking + mejor type narrowing con `if (tipo === 'Auto')`.
12. **Interface `TipoVehiculo` matching backend + filtro defensivo** (DEC-F4.1-09): `tipo: string | null` con filtro en `tiposVehiculoApi.getTiposVehiculo()` descarta filas con `tipo: null` (backend Pydantic permite null).
13. **i18n namespace pre-existente** (DEC-F4.1-11): `operacion.json` con 10 keys pre-existentes F2.1. F4.1 +1 key. NO nuevo namespace (F2.1 DEC-ELEC-06 un namespace por bounded context).
14. **No extensión de `PRE_FLIGHT_PATHS`** (DEC-F4.1 verbatim, mismo precedent F3.3 DEC-F3.3-10): `/catalogos/*` GET read idempotente NO requiere pre-flight gate. `handle401` cubre expiración mid-fetch. YAGNI — F4.1 NO modifica `parkosFetch.ts`.
15. **Defense in depth XR6 layer 4** (operations/spec.md:3951): cliente detecta (F4.1, feedback inmediato) + backend re-valida con `detectar_tipo_vehiculo()` server-side (HU-F1.x, server overwrites via V5). Backend SIEMPRE wins.
16. **`parkosFetch` siempre via typed wrapper** (precedent F2.2 verbatim): `tiposVehiculoApi.getTiposVehiculo()` usa `parkosFetch` con auth + refresh-once + Idempotency-Key automático. NO `fetch` directo.
17. **Tests con vitest + mock SWR** (F2.1 baseline + F3.3 test pattern verbatim): vi.mock módulos + captura swrOptions para inspeccionar config (`dedupingInterval`, `shouldRetryOnError`, `onError`).

---

## 3. Atomic tasks — diseño detallado (T1..T3)

### T1 — `detectarTipoVehiculo` función pura + constantes regex + i18n key + 6 unit tests (~83 prod + 80 tests = ~163 LOC)

**Propósito**: Proveer la función pura reutilizable que detecta tipo de vehículo (Auto/Moto/null) vía regex estricto hardcoded, con normalización trivial previa. Exportar `REGEX_AUTO` + `REGEX_MOTO` para reuso en validación Zod (F6.1 forward). Sentar el precedent de separación clara entre detección estricta (F4.1) y búsqueda tolerante (F7.x).

**Files**:
- `apps/electron-sucursal/src/lib/validation/placa.ts` (NEW ~50 LOC — función pura + JSDoc verbatim DEC-SUC-22 + A-03 + BR2 + `operacion.py:215-277` backend counterpart + constantes regex exportadas).
- `apps/electron-sucursal/src/lib/validation/placa.test.ts` (NEW ~80 LOC — U1..U6 verbatim plan.md:1381).
- `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (MODIFY +1 key `placa_formato_invalido`, ~3 LOC).

**Acceptance criteria**:
- U1: `detectarTipoVehiculo('ABC123')` → `'Auto'`.
- U2: `detectarTipoVehiculo('ABC12D')` → `'Moto'`.
- U3: `detectarTipoVehiculo('ABCD12')` → `null` (formato inválido).
- U4: `detectarTipoVehiculo('')` → `null` (placa vacía).
- U5: `detectarTipoVehiculo('abc123')` → `'Auto'` (minúsculas normalizadas).
- U6: `detectarTipoVehiculo('  ABC123  ')` → `'Auto'` (con espacios).
- G1: TypeScript strict sin errores (`tsc -b` exit 0).
- G2: ESLint sin errores (`--max-warnings 0` exit 0).

**Decisiones clave**: Función pura determinista — sin acceso a red/store/DOM. Sin side effects (logging, métricas se agregan en F6.1 capa que consume la función). Normalización previa (trim + uppercase + remove whitespace interno) ANTES de regex. Regex exportadas como constantes módulo-level. Tests incluido en mismo commit (work-unit-commits hard rule: "Tests belong in the same commit as the behavior they verify").

**Precedentes**: F2.1 `formatCOP` (helper puro en `features/caja/lib/format.ts`) + F4.2 `formatCOP` reuse + F7.x forward `buscarIngresoTolerante` (función NUEVA en archivo NUEVO, nunca se reusa con F4.1 — DEC-SUC-22 categórico).

### T2 — `useTiposVehiculo` hook SWR + `tiposVehiculoApi` wrapper + 5 unit tests (~110 prod + 70 tests = ~180 LOC)

**Propósito**: Proveer el hook SWR reusable para consultar el catálogo `tipos_vehiculo` con fallback hardcoded `{auto, moto}` (degradación explícita, nunca pantalla rota). F4.1 primer consumer; F4.3 `<OcupacionStrip>` + F6.1 `<PlacaInput>` + F11.x sync UI consumen forward.

**Files**:
- `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` (NEW ~30 LOC — `getTiposVehiculo()` wrapper con `parkosFetch` + mapeo 404 → `[]` + filtro defensivo `tipo: null`).
- `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.test.ts` (NEW ~20 LOC — U5a 200 OK + U5b 404 mapeo).
- `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (NEW ~80 LOC — SWR hook + `HARDCODED_CATALOG` constante inline + `isFromFallback` flag).
- `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.test.ts` (NEW ~50 LOC — U7..U11).

**Acceptance criteria**:
- U5a: `getTiposVehiculo()` 200 OK → `TipoVehiculo[]` poblado.
- U5b: `getTiposVehiculo()` 404 → `[]` (NO lanza error, mapeo explícito).
- U7: SWR key null sin token (mock `useAuthStore` retornando `null`) → `tipos: HARDCODED_CATALOG, isLoading: false, error: undefined`, NO fetcher call.
- U8: SWR fetch OK con catálogo poblado (mock 200 OK) → `tipos: TipoVehiculo[]` del backend, `isFromFallback: false`.
- U9: SWR fetch error 500 → `data === HARDCODED_CATALOG` (fallback activo), `isFromFallback: true`, `error: ParkosHttpError`.
- U10: `dedupingInterval: 5 * 60 * 1000` configurado (inspect `swrOptions.dedupingInterval === 300000`).
- U11: `onError` con `status === 401` dispara `useAuthStore.getState().clear()` + `window.dispatchEvent(new Event('parkos:auth:cleared'))` (precedent F3.3 verbatim).
- G1 + G2 + G3 (vitest run exit 0) + G5 (SWR config).

**Decisiones clave**: SWR key `accessToken ? '/catalogos/tipos-vehiculo' : null` (precedent F3.3 useSesionActiva). `dedupingInterval: 5 * 60 * 1000` (plan.md:1375 verbatim 5min). `fallbackData: HARDCODED_CATALOG` (NUNCA pantalla rota). `shouldRetryOnError: (err) => err?.status !== 404` (catálogo vacío válido). `onError` con `status===401` → `useAuthStore.getState().clear()` + `dispatchEvent('parkos:auth:cleared')`. Comparación `isFromFallback = data === HARDCODED_CATALOG` (referencia, no deep-equal). API wrapper filtra filas con `tipo: null` antes de retornar al hook.

**Precedentes**: F3.3 `useSesionActiva.ts:1-89` verbatim SWR config (key null-when-no-token + deduping + 404 skip + 401 clear) + F3.3 `useSesionActiva.test.ts:1-211` verbatim test pattern (vi.mock módulos + captura swrOptions) + F2.2 `parkosFetch` typed wrapper precedent (F2.2 `auth.ts` + F2.2 `catalogos.ts` patterns).

### T3 — i18n key `placa_formato_invalido` (~3 LOC, agrupado en C1)

**Propósito**: Proveer el string literal del mensaje de error "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)" para que F6.1 `<PlacaInput>` lo consuma vía `<p role="alert">{t('operacion.placa_formato_invalido')}</p>`.

**Files**:
- `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (MODIFY +1 key).

**Acceptance criteria**:
- G1: TypeScript estricto verifica que `t('operacion.placa_formato_invalido')` retorna string (i18next typing). Sin errores lint.
- Snapshot test verifica string literal verbatim plan.md:1366.

**Decisiones clave**: Namespace pre-existente `operacion.json` (F2.1 DEC-ELEC-06 — un namespace por bounded context). NO nuevo namespace. String literal sin variables. Mensaje en español neutro profesional.

**Precedentes**: F2.1 `operacion.json` 10 keys baseline + F3.x `caja.json` precedent (namespace pre-existente, +N keys por HU). F4.1 replica exactamente.

---

## 4. Componentes nuevos (atomic design placement)

### 4.1 Mapeo atomic design

| Componente | Tipo | Capa | Atomic placement | Path |
|---|---|---|---|---|
| `detectarTipoVehiculo` | Pure function (logic) | Logic | Utility puro (F2.1 `formatCOP` precedent) | `lib/validation/placa.ts` |
| `REGEX_AUTO` + `REGEX_MOTO` | Constantes módulo-level | Logic | Utility constants (DRY export) | `lib/validation/placa.ts` |
| `tiposVehiculoApi` | Service (data) | Data | API wrapper (F2.2 + F3.3 verbatim pattern) | `features/catalogos/api/tiposVehiculoApi.ts` |
| `useTiposVehiculo` | Hook (logic) | Logic | SWR hook reusable (F3.3 `useSesionActiva` precedent) | `features/catalogos/hooks/useTiposVehiculo.ts` |
| `HARDCODED_CATALOG` | Constante módulo-level | Logic | Inline en useTiposVehiculo (DEC-F4.1-05 cohesión) | `features/catalogos/hooks/useTiposVehiculo.ts` |
| `operacion.json` (i18n) | Resource (i18n) | i18n | Namespace pre-existente (F2.1 DEC-ELEC-06) | `renderer/i18n/locales/operacion.json` |

### 4.2 `detectarTipoVehiculo` signature + JSDoc

```typescript
// apps/electron-sucursal/src/lib/validation/placa.ts (NEW T1)

/**
 * Constantes regex exportadas — reusables por F6.x <PlacaInput> Zod validation.
 * Sincronizadas manualmente con backend `operacion.py:215-277`
 * (defense in depth XR6 layer 4 — regex idéntica cliente/backend).
 *
 * Auto:  ^[A-Z]{3}[0-9]{3}$    (ej. ABC123)
 * Moto:  ^[A-Z]{3}[0-9]{2}[A-Z]$ (ej. ABC12D)
 */
export const REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/;
export const REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/;

/**
 * Detecta tipo de vehículo (Auto / Moto) a partir de la placa digitada.
 *
 * DEC-SUC-22 verbatim: detección estricta, SIN tolerancia de tipeo.
 * La tolerancia O↔0/I↔1/B↔8 pertenece a `buscarIngresoTolerante()` (Fase 7).
 *
 * A-03 verbatim: regex hardcoded en cliente, NO columna del ER (4NF canon).
 * Backend tiene `detectar_tipo_vehiculo()` server-side idéntica
 * (operacion.py:215-277) — defense in depth XR6 layer 4.
 *
 * BR2 de CU-01 literal: autodetección por regex es la ÚNICA fuente válida;
 * NO hay override manual del cajero; si falla, se corrige como bug.
 *
 * @param placa Placa digitada por el operador (puede tener espacios o minúsculas).
 * @returns 'Auto' | 'Moto' | null. `null` indica formato no reconocido.
 */
export function detectarTipoVehiculo(placa: string): 'Auto' | 'Moto' | null;
```

### 4.3 `TipoVehiculo` interface + `tiposVehiculoApi` signatures

```typescript
// apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts (NEW T2)

export interface TipoVehiculo {
  uuid: string;
  tipo: string | null;        // backend Pydantic permite null; api wrapper filtra
  vigente_desde: string;       // ISO 8601
  vigente_hasta: string | null;
  estado: string;
}

/**
 * GET /api/v1/catalogos/tipos-vehiculo
 * Retorna [] si 404 (sucursal sin tipos configurados — estado válido).
 * Filtra filas con tipo === null (defensiva contra backend corrupto).
 */
export function getTiposVehiculo(): Promise<TipoVehiculo[]>;
```

### 4.4 `useTiposVehiculo` hook signature

```typescript
// apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts (NEW T2)

export interface UseTiposVehiculoReturn {
  tipos: TipoVehiculo[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<TipoVehiculo[] | undefined>;
  isFromFallback: boolean;
}

/**
 * Hook SWR para consultar catálogo de tipos de vehículo.
 *
 * DEC-F4.1-04: dedupingInterval 5min, sin refreshInterval (catálogos reference data).
 * DEC-F4.1-05: fallback hardcoded HARDCODED_CATALOG con {auto, moto} + UUIDs sentinels.
 * DEC-F4.1-06: isFromFallback flag (data === HARDCODED_CATALOG por referencia).
 *
 * Precedente: F3.3 useSesionActiva (mismo pattern: key null-when-no-token +
 * dedupingInterval + shouldRetryOnError excl 404 + onError 401 clear).
 *
 * Forward extensibilidad: F4.3 <OcupacionStrip> + F6.1 <PlacaInput> +
 * F11.x sync UI consumen este hook para scoped queries per sucursal.
 */
export function useTiposVehiculo(): UseTiposVehiculoReturn;
```

---

## 5. i18n keys (namespace `operacion`)

### 5.1 Namespace `operacion.json` (F2.1 baseline + F4.1 delta = 11 keys total)

**Pre-existente (F2.1, 10 keys)**: `ingreso`, `salida`, `placa`, `tipo`, `tarifa`, `total`, `registrar`, `imprimir`, `anular`, `confirmar`.

**Nueva F4.1 (1 key)**: `placa_formato_invalido` con string literal verbatim plan.md:1366: "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)".

```diff
  // apps/electron-sucursal/src/renderer/i18n/locales/operacion.json (F4.1 MODIFY, +1 key)
  {
    "ingreso": "Ingreso",
    "salida": "Salida",
    "placa": "Placa",
    "tipo": "Tipo de vehículo",
    "tarifa": "Tarifa",
    "total": "Total",
    "registrar": "Registrar",
    "imprimir": "Imprimir ticket",
    "anular": "Anular",
    "confirmar": "Confirmar",
+   "placa_formato_invalido": "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)"
  }
```

### 5.2 Convenciones (DEC-F4.1-11 + F2.1 DEC-ELEC-06)

- **Un namespace por bounded context** (F2.1 DEC-ELEC-06): operación = `operacion`. NO `operacion.placa` (namespace plano).
- **Keys en `camelCase`**. Mensajes en español neutro profesional.
- **String literal sin variables** (`placa_formato_invalido`): el mensaje indica ejemplos estáticos (ABC123, ABC12D), no necesita interpolación i18next.
- **No crear `auth.json` o `caja.json` keys nuevas**: la detección de tipo de vehículo es bounded context `operacion` (ingreso vehicular), no auth ni caja.
- **Forward consumer F6.1** consume `t('operacion.placa_formato_invalido')` con prefijo namespace explícito.

---

## 6. Error handling & edge cases

### 6.1 Matriz de errores F4.1

| Origen | Status / Tipo | Comportamiento | Anchor |
|---|---|---|---|
| Input | `placa === ''` | `detectarTipoVehiculo('')` → `null` (regex testea contra string vacío, NO matchea) | DEC-F4.1-01 |
| Input | `placa === 'ABC123'` (happy path Auto) | `detectarTipoVehiculo('ABC123')` → `'Auto'` | DEC-F4.1-01 |
| Input | `placa === 'ABC12D'` (happy path Moto) | `detectarTipoVehiculo('ABC12D')` → `'Moto'` | DEC-F4.1-01 |
| Input | `placa === 'ABCD12'` (formato inválido) | `detectarTipoVehiculo('ABCD12')` → `null` | DEC-F4.1-01 |
| Input | `placa === 'abc123'` (minúsculas) | normalización `toUpperCase()` → `'ABC123'` → `'Auto'` | DEC-F4.1-02 |
| Input | `placa === '  ABC123  '` (con espacios) | normalización `trim().replace(/\s+/g, '')` → `'ABC123'` → `'Auto'` | DEC-F4.1-02 |
| Input | `placa === null` cast a `''` | `null` test contra string vacío → `null` (TypeScript strict NO permite pasar `null` sin cast) | DEC-F4.1-01 |
| Input | `placa === 'ABC@12'` (caracteres especiales) | normalización NO remueve `@` → regex NO matchea → `null` | DEC-F4.1-02 |
| Input | `placa === 'ABC1234D'` (8 caracteres Moto extendida) | regex Moto `^[A-Z]{3}[0-9]{2}[A-Z]$` requiere 6 caracteres → `null` | DEC-F4.1-03 |
| Red | `GET /catalogos/tipos-vehiculo` 200 OK | SWR cachea `TipoVehiculo[]`, `isFromFallback: false` | REQ-OPS-127, DEC-F4.1-04 |
| Red | `GET /catalogos/tipos-vehiculo` 404 | api wrapper mapea a `[]`, hook retorna `tipos: []`, `error: undefined` (catálogo vacío válido) | REQ-OPS-127, DEC-F4.1-04 |
| Red | `GET /catalogos/tipos-vehiculo` 500 | SWR `fallbackData: HARDCODED_CATALOG` → `tipos: HARDCODED_CATALOG`, `isFromFallback: true`, `error: ParkosHttpError` | REQ-OPS-127, DEC-F4.1-05 |
| Red | `GET /catalogos/tipos-vehiculo` 401 | SWR `onError` dispara `useAuthStore.getState().clear()` + `dispatchEvent('parkos:auth:cleared')` | REQ-OPS-127, DEC-F4.1-04, F2.2 invariant |
| Red | `GET /catalogos/tipos-vehiculo` 403 | SWR retorna `error: ParkosHttpError(403)`, hook NO muestra fallback (403 NO es transient) | REQ-OPS-127, DEC-F4.1-04 |
| Red | Network failure (offline) | SWR `fallbackData: HARDCODED_CATALOG` → `tipos: HARDCODED_CATALOG`, `isFromFallback: true` (cached in SWR via fallbackData — siempre disponible) | DEC-F4.1-05 |
| Auth | `accessToken === null` | SWR key `null` → NO fetch → `tipos: HARDCODED_CATALOG`, `isLoading: false` | DEC-F4.1-04 |
| Auth | `accessToken` expira mid-fetch | `parkosFetch.handle401` Mutex refresh-once (F2.2+F3.2 invariant preserved) | F2.2 invariant |

### 6.2 Edge cases cubiertos

- **Operador kiosko tipea ` abc123 ` (con espacios y minúsculas)**: normalización `trim + uppercase + remove whitespace` → `'ABC123'` → `'Auto'`. UX eficiente (operador puede tipear rápido sin corregir formato).
- **Operador tipea placa con caracteres especiales (`ABC@12`, `ABC.123`, `ABC-123`)**: normalización NO remueve caracteres no-whitespace → regex NO matchea → `null`. F6.1 muestra `<p role="alert">{t('operacion.placa_formato_invalido')}</p>`. Operador corrige manualmente.
- **Backend down al boot**: SWR `fallbackData: HARDCODED_CATALOG` → operador ve catálogo hardcoded `{auto, moto}` con `isFromFallback: true`. F6.x+ consumers pueden mostrar `<Tooltip>` "usando datos locales". Si backend vuelve, SWR revalida automáticamente (refresh on focus / on reconnect per SWR default behavior).
- **Backend retorna `tipo: null` en una fila corrupta**: `tiposVehiculoApi.getTiposVehiculo()` filtra la fila (`return items.filter(t => t.tipo !== null)`). Hook nunca ve fila corrupta.
- **SWR cache stale entre sesiones**: SWR key `'catalogos/tipos-vehiculo'` NO incluye uuid_sucursal (catálogo branch-local — branch NO tiene catálogos distintos). F11.x sync UI invalida cache con `mutate('/catalogos/tipos-vehiculo')` post-sync event (forward hook).
- **`accessToken` expira durante `useTiposVehiculo` polling**: SWR `onError` 401 → `useAuthStore.getState().clear()` + `dispatchEvent('parkos:auth:cleared')` (precedent F3.3 verbatim). Forward hook AuthGuard F3.x+ intercepta event y redirige a `/login?next=...`.
- **Operador sin `useAuth().user`**: SWR key `null` (sin token) → `tipos: HARDCODED_CATALOG`, `isLoading: false`. No fetch, no error.
- **Multi-tab open**: F2.3 single-instance lock (DEC-UPD-07) previene multi-tab kiosko. Cross-tab sync NO es scope F4.1.

### 6.3 Defense in depth XR6 layer 4 (F4.1 cliente + backend `detectar_tipo_vehiculo`)

```typescript
// F6.1 <PlacaInput> forward — usa detectarTipoVehiculo() cliente + backend SIEMPRE wins

// Cliente (F4.1):
const tipoDetectado = detectarTipoVehiculo(placa);          // 'Auto' | 'Moto' | null
if (tipoDetectado === null) {
  // mostrar <p role="alert">{t('operacion.placa_formato_invalido')}</p>
  return;
}
const tipoVehiculo = tipos.find(t => t.tipo === tipoDetectado);
const uuid_tipo_vehiculo = tipoVehiculo?.uuid;              // puede ser undefined si catálogo incompleto

// Backend (HU-F1.x, operacion.py:215-277 — READ ONLY):
// POST /operacion/ingresos con body {uuid_tipo_vehiculo}
// → server overwrites via V5: "regex-derived UUID wins over client value"
// → si cliente envía uuid incorrecto, backend reemplaza con regex-derived UUID
// → defense in depth XR6 layer 4: cliente propone, backend dispone
```

---

## 7. Testing strategy (unit + sandbox F.6 caveat)

### 7.1 Vitest unit (mockeando SWR + parkosFetch + useAuthStore)

**`placa.test.ts`** (NEW F4.1 T1, ~80 LOC, 6 tests verbatim plan.md:1381):

| # | Escenario | Aserción clave |
|---|---|---|
| U1 | Placa `ABC123` → `Auto` | `expect(detectarTipoVehiculo('ABC123')).toBe('Auto')` |
| U2 | Placa `ABC12D` → `Moto` | `expect(detectarTipoVehiculo('ABC12D')).toBe('Moto')` |
| U3 | Placa `ABCD12` formato inválido → `null` | `expect(detectarTipoVehiculo('ABCD12')).toBeNull()` |
| U4 | Placa vacía `''` → `null` | `expect(detectarTipoVehiculo('')).toBeNull()` |
| U5 | Placa minúsculas `abc123` → `Auto` (normalizada) | `expect(detectarTipoVehiculo('abc123')).toBe('Auto')` |
| U6 | Placa con espacios `'  ABC123  '` → `Auto` (normalizada) | `expect(detectarTipoVehiculo('  ABC123  ')).toBe('Auto')` |

**`tiposVehiculoApi.test.ts`** (NEW F4.1 T2, ~20 LOC, 2 tests):

| # | Escenario | Aserción clave |
|---|---|---|
| U5a | `getTiposVehiculo()` 200 OK → `TipoVehiculo[]` poblado | `mock200('/api/v1/catalogos/tipos-vehiculo', tiposMock) + await getTiposVehiculo() → expect(result).toEqual(tiposMock)` |
| U5b | `getTiposVehiculo()` 404 → `[]` (NO lanza error) | `mock404('/api/v1/catalogos/tipos-vehiculo') + await getTiposVehiculo() → expect(result).toEqual([])` |

**`useTiposVehiculo.test.ts`** (NEW F4.1 T2, ~50 LOC, 5 tests — precedent F3.3 verbatim):

| # | Escenario | Aserción clave |
|---|---|---|
| U7 | SWR key null sin token → `tipos: HARDCODED_CATALOG`, NO fetcher call | `mockUseAuthStoreToken(null) + renderHook(useTiposVehiculo) → waitFor(() => expect(tipos).toEqual(HARDCODED_CATALOG)); expect(fetchMock).not.toHaveBeenCalled()` |
| U8 | SWR fetch OK con catálogo poblado | `mock200('/api/v1/catalogos/tipos-vehiculo', tiposMock) + renderHook(useTiposVehiculo) → waitFor(() => expect(tipos).toEqual(tiposMock)); expect(isFromFallback).toBe(false)` |
| U9 | SWR fetch error 500 → fallback hardcoded | `mock500('/api/v1/catalogos/tipos-vehiculo') + renderHook(useTiposVehiculo) → waitFor(() => expect(tipos).toBe(HARDCODED_CATALOG)); expect(isFromFallback).toBe(true); expect(error).toBeInstanceOf(ParkosHttpError)` |
| U10 | `dedupingInterval: 5 * 60 * 1000` configurado | `renderHook(useTiposVehiculo) + inspect(swrOptions.dedupingInterval) → expect(swrOptions.dedupingInterval).toBe(300000)` |
| U11 | `onError` con `status === 401` dispara `useAuthStore.clear()` + event | `mock401('/api/v1/catalogos/tipos-vehiculo') + spyOn(useAuthStore.getState(), 'clear') + spyOn(window, 'dispatchEvent') + renderHook(useTiposVehiculo) → waitFor(() => expect(clearSpy).toHaveBeenCalledOnce()); expect(dispatchEventSpy).toHaveBeenCalledWith('parkos:auth:cleared')` |

### 7.2 Sandbox F.6 caveat (e2e SKIPPED-env)

F4.1 **NO entrega e2e** — los 11 unit tests (6 placa + 2 api + 5 hook = 13 totales) cubren la lógica. e2e (Playwright) testeará la integración cuando F6.1 consuma `detectarTipoVehiculo()` + `useTiposVehiculo()` en `<PlacaInput>`. Sandbox F.6 SKIPPED-env (npm 11.16.0 refuses `workspace:*` resolution, F.6 precedent) — D-env documentado en verify-report futuro, NO project defect.

### 7.3 Cobertura thresholds

```typescript
// apps/electron-sucursal/vitest.config.ts (extracto — F2.1+F3.x baseline, F4.1 agrega thresholds)

coverage: {
  provider: 'v8',
  thresholds: {
    // ... existing F2.1+F3.1+F3.2+F3.3 thresholds ...
    'src/lib/validation/placa.ts':                          { lines: 95, functions: 95, branches: 90 },
    'src/features/catalogos/api/tiposVehiculoApi.ts':        { lines: 90, functions: 90, branches: 85 },
    'src/features/catalogos/hooks/useTiposVehiculo.ts':       { lines: 90, functions: 90, branches: 85 },
  }
}
```

---

## 8. Accessibility (WCAG 2.1 AA — forward F6.1)

### 8.1 Cobertura WCAG F4.1 (forward a F6.1 `<PlacaInput>`)

F4.1 **NO entrega componente UI** — la cobertura WCAG aplica al forward consumer F6.1. Lo que F4.1 entrega son las primitives accesibles que F6.1 consume:

| Criterio WCAG 2.1 AA | Implementación F4.1 | Forward F6.1 |
|---|---|---|
| 1.3.1 Info and Relationships | `detectarTipoVehiculo` retorna tipo discriminado (`'Auto' \| 'Moto' \| null`) — type narrowing permite a F6.1 renderizar label correcto | `<FormLabel>` para input placa + `<FormDescription>` con formato esperado |
| 1.4.3 Contrast (Minimum) | N/A (no UI) | shadcn tokens + Card shadcn primitives (F2.1 baseline ≥4.5:1) |
| 3.3.1 Error Identification | `t('operacion.placa_formato_invalido')` i18n key pre-poblada con mensaje UX explícito | `<FormMessage role="alert">` muestra mensaje cuando `detectarTipoVehiculo(placa) === null` |
| 3.3.2 Labels or Instructions | N/A | F6.1 `<FormLabel>` para input placa con texto i18n |
| 4.1.2 Name, Role, Value | N/A | F6.1 `aria-invalid={!!error}` + `aria-describedby` referenciando mensaje |
| 4.1.3 Status Messages | N/A | F6.1 `<p role="status" aria-live="polite">` para anuncio automático |

### 8.2 i18n key `operacion.placa_formato_invalido` como foundation WCAG

```typescript
// F6.1 <PlacaInput> forward — usa F4.1 i18n key con WCAG role="alert"
<Input
  type="text"
  aria-required="true"
  aria-invalid={detectarTipoVehiculo(placa) === null}
  aria-describedby={detectarTipoVehiculo(placa) === null ? 'placa-error' : undefined}
  value={placa}
  onChange={(e) => setPlaca(e.target.value.toUpperCase())}
/>
{detectarTipoVehiculo(placa) === null && (
  <p id="placa-error" role="alert">
    {t('operacion.placa_formato_invalido')}
  </p>
)}
```

- `role="alert"` anuncia error inmediatamente al screen reader (NO polite).
- `aria-describedby` asocia mensaje al input para screen readers.
- WCAG 2.1 AA compliant: pattern idéntico a F3.1 Login error precedent.

### 8.3 axe-core e2e test (forward F6.1 — SKIPPED-env)

axe-core A1 scan para `<PlacaInput>` (F6.1) con tags `wcag2a, wcag2aa, wcag21a, wcag21aa`. **NO es F4.1 scope** — F4.1 sienta primitives accesibles, F6.1 verifica con axe-core.

---

## 9. Performance budget

### 9.1 Función pura `detectarTipoVehiculo` overhead

- Regex test contra string ≤7 caracteres: ~0.01ms CPU.
- Normalización previa (trim + uppercase + replace whitespace): ~0.005ms.
- **Total**: ~0.015ms por llamada. Insignificante. F6.1 puede llamar en cada keystroke sin debounce.

### 9.2 SWR dedupingInterval 5min vs F3.3 deduping 10s

- F3.3 `useSesionActiva`: 6 deduplications/minuto potencial si múltiples componentes consumen en paralelo.
- F4.1 `useTiposVehiculo`: 0.033 deduplications/minuto (1 cada 30min promedio). Catálogo reference data cambia raramente.
- **Ahorro**: ~99% menos requests a `/catalogos/tipos-vehiculo` comparado con F3.3 ratio.

### 9.3 SWR fallback hardcoded sin red

- Si backend down: SWR retorna `HARDCODED_CATALOG` instantáneamente (cached en `fallbackData`). Cero latencia de red.
- Si backend OK: 1 fetch cada 5min = ~12 fetches/hora = ~30KB/hora bandwidth.

### 9.4 Network requests per operación (forward F6.1 + F4.3 + F11.x)

- `<PlacaInput>` (F6.1) consume `useTiposVehiculo()`: 0 requests adicionales (SWR cache compartido).
- `<OcupacionStrip>` (F4.3) consume `useTiposVehiculo()`: 0 requests adicionales.
- `useTiposVehiculo` polling: 1 request cada 5min (no refresh activo, solo dedup).
- **Total F4.1**: 12 requests/hora máximo en operación normal. Insignificante.

### 9.5 Memory footprint

- `detectarTipoVehiculo`: 0 bytes (función pura sin closure).
- `HARDCODED_CATALOG`: ~500B constante módulo-level (2 objetos).
- `useTiposVehiculo` SWR cache: ~500B por catálogo en memoria.
- `TipoVehiculo[]` del backend: ~200B por entrada × N tipos (típicamente 2-5) = ~1KB.
- **Total**: ~2KB adicional en memoria. Insignificante.

### 9.6 Comparación con naive approach (sin SWR)

- **Naive**: cada componente (F4.3 + F6.1 + F7.x + ...) hace su propio `fetch` → N requests cada vez que un componente monta.
- **F4.1 SWR**: 1 request cada 5min compartido por TODOS los consumers → 99% reducción bandwidth.
- **Trade-off**: cache stale hasta 5min. Aceptable para catálogos (no transaccional).

---

## 10. Security (Defense in depth, idempotency, XSS)

### 10.1 Defense in depth (5 capas, F4.1 contribution)

| Layer | Mechanism | Source | F4.1 contribution |
|---|---|---|---|
| 1 auth | JWT Bearer (F2.2) + cookie httpOnly SameSite=Lax (F1.2) + bcrypt (F1.2) | `useAuth.ts` + `authStore.ts` + backend `auth.py` | NO custom auth (heredado); SWR key null-when-no-token preserva invariant |
| 2 engineering | TS strict + noUncheckedIndexedAccess + ESLint flat (F2.1) | tsconfig.* + eslint.config.js | `placa.ts` + `useTiposVehiculo.ts` + `tiposVehiculoApi.ts` heredan; `tipo: string \| null` defensivo |
| 3 a11y | axe-core WCAG 2.1 AA (RNF-022) + i18n key pre-poblada para `<p role="alert">` | `@axe-core/playwright` + shadcn `form.tsx` + F4.1 i18n key | ADD i18n key `placa_formato_invalido` + foundation WCAG para F6.1 `<PlacaInput>` |
| 4 contract | Regex cliente (F4.1) + regex backend (HU-F1.x) + 6 new REQ-OPS-125..130 (DEC-F4.1-11) | `lib/validation/placa.ts` + `operacion.py:215-277` + `operations/spec.md` delta | ADD 6 new REQ-OPS-125..130 al spec canónico (sdd-archive phase commit) |
| 5 retry-budget | parkosFetch retry 5xx + 401 refresh-once (F2.2) + pre-flight gate (F3.2 — NO extension F4.1) | parkosFetch.ts + DEC-FETCH-02/03 | NO extension (`/catalogos/*` GET read idempotente NO requiere gate) |

### 10.2 CSRF mitigation (F2.2 + F3.1 invariant preserved)

- Cookie httpOnly `parkos_session` con `SameSite=Lax` (F1.2 backend) bloquea cross-site form submissions.
- Bearer JWT en `Authorization` header para requests `parkosFetch` (F2.2).
- F4.1 NO agrega endpoints públicos — `GET /api/v1/catalogos/tipos-vehiculo` requiere `accessToken` válido (backend `config_catalogo` permission per `_CATALOG_DEFAULTS:101`).
- Atacante sin sesión válida no puede CSRF fetch catálogo.

### 10.3 XSS mitigation (F3.x invariant preserved)

- `React 18` JSX escapa automáticamente interpolaciones (forward F6.1 — `{t('operacion.placa_formato_invalido')}` → HTML-safe).
- `detectarTipoVehiculo` retorna union literal `'Auto' | 'Moto' | null` (NO user input directo en output). Forward F6.1 renderiza con shadcn primitives — sin `dangerouslySetInnerHTML`.
- `formatCOP` no aplica a F4.1 (forward F4.2 sí).
- `HARDCODED_CATALOG` UUIDs sentinels literales — sin user input.

### 10.4 Idempotency-Key automático (F2.2 invariant preserved — no aplica F4.1)

- `parkosFetch.ts` genera SHA-256 de `method|path|body` como `Idempotency-Key` header para POST `/caja-sesion/*` (skip `/auth/login` only).
- F4.1 es READ-ONLY (`GET /api/v1/catalogos/tipos-vehiculo`) — Idempotency-Key NO aplica a GET per RFC 7231 §4.2.1.
- Si admin publica cambio en `tipos_vehiculo`, F4.1 consume via re-fetch normal (SWR revalidateOnFocus + dedupingInterval expiry).

### 10.5 Permission gating (Defense in depth XR6)

- Backend ya emite 403 si `permisos[]` no incluye `config_catalogo` (per `_CATALOG_DEFAULTS:101` catalogos.py).
- F4.1 NO agrega client-side permission gating — backend es source of truth.
- Forward hook: si F4.x+ requiere client-side permission check, exportar `usePermisos()` desde `useAuth()` y agregar `<ProtectedRoute perm="config_catalogo">` wrapping.

### 10.6 Atomic state updates (F2.2 invariant preserved)

- `useAuthStore.setTokens` (F2.2) actualiza 3 keys simultáneamente en Zustand `set` síncrono. NO race condition con `useTiposVehiculo` SWR que lee `accessToken`.
- `useAuthStore.clear()` post-401 dispara logout defensivo (forward AuthGuard F3.x+ intercepta `parkos:auth:cleared`).

---

## 11. Observability

### 11.1 Structured logging (F2.1 baseline, F4.1 consume)

- `parkosFetch` emite `console.info` con `[parkosFetch]` prefix per request (F2.1 baseline).
- F4.1 NO agrega logging custom — consume el baseline.
- Forward hook: si F11.x requiere structured logging para analytics, agregar `Sentry.captureException(err)` en `tiposVehiculoApi` catches.

### 11.2 Error tracking (forward hook F11.x)

- `ParkosHttpError(401)` post-fetch se loggea automáticamente por `parkosFetch` baseline.
- F4.1 NO captura errors con Sentry — F11.x sync UI + reportería es responsable.

### 11.3 Métricas de uso (forward hook F12.x reportería)

- F4.1 modelo de datos `prod.tipos_vehiculo` [V] provee métricas nativas en backend (vigente_desde, vigente_hasta, estado).
- F12.x consume via queries a `prod.tipos_vehiculo_v_resumen` (forward view).
- F4.1 NO consume analytics — solo emite eventos via `parkosFetch` (F2.1 baseline).

### 11.4 Window events (F2.2 invariant preserved)

- F4.1 dispatch `new Event('parkos:auth:cleared')` post-401 mid-fetch (forward hook AuthGuard F3.x+).
- F4.1 NO consume `parkos:auth:cleared` events (eso es responsabilidad de `<AuthGuard>` forward).
- `parkos:auth:cleared` event listener count = 0 en F4.1 — forward extensibility.

### 11.5 i18n locale switching (F2.1 DEC-ELEC-06)

- F4.1 keys en namespace `operacion.json` (es-CO default + en-US + pt-BR forward).
- F4.1 NO implementa locale switcher — F4.x+ UI feature.
- Tests asumen `es-CO` default; en-US + pt-BR son stubs F2.1 baseline.

---

## 12. Migration / rollback plan

### 12.1 F4.1 entrega

**Cluster C1** (3 atomic tasks T1..T3) en orden mandatory con 2 commits atómicos per DEC-F4.1-08 (work-unit-commits skill):

```
T1 — detectarTipoVehiculo() función pura + placa.test.ts 6 unit tests
   ↓ (T1 entrega función base + cobertura branches críticos)
T3 — i18n key placa_formato_invalido  (agrupado en C1 per DEC-F4.1-08 — cohesivo con T1)
   ↓ (T3 entrega string UX consumible por F6.1 forward)
[C1 COMMIT] feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido (HU-F4.1-T1+T3)
   ↓
T2 — useTiposVehiculo() hook SWR + tiposVehiculoApi wrapper + useTiposVehiculo.test.ts 5 unit tests
   ↓ (T2 entrega hook reusable + api typed + fallback hardcoded)
[C2 COMMIT] feat(catalogos): adicionar useTiposVehiculo() SWR + fallback hardcoded {auto,moto} + 5 unit tests (HU-F4.1-T2)
   ↓
archive — mover change folder a archive/, actualizar pending.md §1 row F4.1 → ✅
```

C1 antes que C2 porque la i18n key + función pura son la base (forward F6.1 las necesita). C2 después porque el hook SWR es independiente (forward F4.3 podría consumirlo antes de F6.1 exista, peer con F4.2 hook independiente).

### 12.2 Forward hooks (Fase 4+)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F4.2** (Tarifas vigentes) | `useTarifasVigentes()` peer hook en mismo feature `catalogos` | Mismo patrón SWR token-gated + dedupingInterval + fallback (en este caso electron-store, NO hardcoded). F4.2 entrega independientemente. |
| **HU-F4.3** (Ocupación en vivo) | `<OcupacionStrip>` itera sobre tipos del catálogo | `useTiposVehiculo()` provee la lista de tipos. F4.3 puede implementar su propio fetch si quiere (peer pattern). |
| **HU-F6.1** (Ingreso vehicular CU-01) | `<PlacaInput>` consume `detectarTipoVehiculo()` + `useTiposVehiculo()` + `t('operacion.placa_formato_invalido')` | Llama `detectarTipoVehiculo(placa)` → si `null` muestra `<p role="alert">{t('operacion.placa_formato_invalido')}</p>` con `aria-describedby`; si `'Auto' | 'Moto'` setea `uuid_tipo_vehiculo` via `useTiposVehiculo().tipos.find()`. También importa `REGEX_AUTO` + `REGEX_MOTO` para validación Zod local. CRÍTICO — sin F4.1, F6.1 no puede arrancar. |
| **HU-F7.x** (Salida + búsqueda tolerante CU-02/03) | `buscarIngresoTolerante()` función DISTINTA | DEC-SUC-22 categórico: NUNCA compartir función con F4.1. F7.x entrega función NUEVA en archivo NUEVO con tolerancia `O↔0`/`I↔1`/`B↔8`. |
| **HU-F11.x** (sync UI + alertas CU-07/14) | Si sync incluye `tipos_vehiculo`, el hook debe invalidarse post-sync | `mutate('/catalogos/tipos-vehiculo')` post-sync event (forward — no F4.1 scope). |

### 12.3 Rollout strategy

- **Branch**: `feature/hu-f4-1-deteccion-tipo-vehiculo` (clean, recién creada desde `dev`).
- **PR target**: `origin/dev`.
- **Merge order**: F4.1 merge a `dev` post-F3.3 (archivado 2026-09-15). F6.x+ depende de F4.1 function + hook + i18n key.
- **Feature flag**: NO. F4.1 es consumer directo de infra shipped F2.1+F2.2+F3.1+F3.2+F3.3. Cero toggle runtime.
- **Sandbox**: F4.1 e2e puede SKIP en sandbox F.6 (npm 11.16.0 refuses workspace:*) — pero F4.1 NO entrega e2e (lógica pura). Unit tests cubren el camino crítico.
- **Local dev**: unit tests verdes en Windows native con npm 11.16+ (per F2.x + F3.x archive precedent).

### 12.4 Rollback plan

Si F4.1 merge causa regresión en F3.x (auth, lockout, turno):

1. **Revert PR en `dev`** — `git revert <merge-commit-sha>`. Cero impacto en F1.x + F2.x + F3.x (F4.1 es ADDITIVE: 4 NEW archivos + 1 MODIFY pequeño + 1 i18n key).
2. **Selective rollback** — si solo un commit rompe:
   - `git revert <C1-commit>` revierte `detectarTipoVehiculo` + tests + i18n key. F6.1 forward bloqueado — sin función pura, F6.1 no puede arrancar.
   - `git revert <C2-commit>` revierte `useTiposVehiculo` + `tiposVehiculoApi`. F4.3 + F6.1 (forward consumers) bloqueados — sin hook, no pueden resolver `uuid_tipo_vehiculo`.
3. **Forward compatibility** — F4.1 NO es prerequisite de F3.1/F3.2/F3.3 (F3.x archivadas independientemente). Rollback F4.1 NO afecta login + lockout + turno.

### 12.5 Pendiente post-archive

- `pending.md` §1 row F4.1 → marcar ✅ cerrado.
- `docs/02-arquitectura/decisiones-tecnicas.md` → agregar DEC-F4.1-01..11 resumen (cross-ref `proposal.md` §4).
- `openspec/CHANGELOG.md` → entrada "2026-09-16 — HU-F4.1 detección tipo vehículo archived (6 new REQ-OPS-125..130 user-facing)".
- `openspec/specs/operations/spec.md` post-archive → REQ-OPS vigente = 001..130 (130 total).

### 12.6 Resoluciones de open questions (verificación cruzada)

Las 4 inconsistencias detectadas en `exploration.md` §1 están cerradas en `proposal.md` §4 + `exploration.md` §7:

- **Q1** (LOC budget 100 vs 250): DEC-F4.1-08 — budget total real ~293 LOC (T1 ~130 + T2 ~160 + T3 3). El "100 LOC" del plan.md:1383 cubre T1 sola.
- **Q2** (endpoint verification): catalogos.py:140-147 confirma `_mount_catalog(resource="tipos-vehiculo", ...)` SHIPPED con permission `config_catalogo`. F4.1 hook SI tiene endpoint; fallback hardcoded sigue siendo degradación explícita si API down.
- **Q3** (dedupingInterval 5min): DEC-F4.1-04 — `dedupingInterval: 5 * 60 * 1000` (plan.md:1375 verbatim). Catálogos reference data.
- **Q4** (i18n literal string): DEC-F4.1-11 — `operacion.placa_formato_invalido` con string literal verbatim plan.md:1366, sin variables.

0 KNOWN-MISSING. F4.1 ready for `sdd-tasks`.

---

## 13. Open questions

Cero open questions en esta fase. Las 4 inconsistencias (Q1..Q4) están cerradas en `proposal.md` §4 con DEC-F4.1-04 + DEC-F4.1-05 + DEC-F4.1-08 + DEC-F4.1-11. Forward extensibility documented en §12.2.

---

## Apéndice A — TS mockups (KEEP COMPACT: 6 archivos, 5-30 LOC cada uno)

### A.1 `placa.ts` (~30 LOC target — T1)

```typescript
/**
 * Detección de tipo de vehículo por placa — función pura.
 * DEC-SUC-22 estricta sin tolerancia. A-03 regex hardcoded cliente.
 * BR2 CU-01: ÚNICA fuente válida; NO override manual del cajero.
 * Backend sincronizado: operacion.py:215-277 (defense in depth XR6 layer 4).
 */

export const REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/;
export const REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/;

export function detectarTipoVehiculo(placa: string): 'Auto' | 'Moto' | null {
  const normalizada = placa.trim().toUpperCase().replace(/\s+/g, '');
  if (REGEX_AUTO.test(normalizada)) return 'Auto';
  if (REGEX_MOTO.test(normalizada)) return 'Moto';
  return null;
}
```

### A.2 `tiposVehiculoApi.ts` (~25 LOC target — T2)

```typescript
import { parkosFetch, ParkosHttpError } from '@parkos/ui-kit/fetch';

export interface TipoVehiculo {
  uuid: string;
  tipo: string | null;
  vigente_desde: string;
  vigente_hasta: string | null;
  estado: string;
}

export async function getTiposVehiculo(): Promise<TipoVehiculo[]> {
  try {
    const items = await parkosFetch<TipoVehiculo[]>('/api/v1/catalogos/tipos-vehiculo');
    return items.filter((t) => t.tipo !== null);          // DEC-F4.1-09 filtro defensivo
  } catch (err) {
    if ((err as ParkosHttpError)?.status === 404) return [];  // catálogo vacío válido
    throw err;
  }
}
```

### A.3 `useTiposVehiculo.ts` (~30 LOC target — T2)

```typescript
import useSWR from 'swr';
import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { getTiposVehiculo, type TipoVehiculo } from '../api/tiposVehiculoApi';

const HARDCODED_CATALOG: TipoVehiculo[] = [
  { uuid: '00000000-0000-0000-0000-000000000001', tipo: 'Auto', vigente_desde: '2026-01-01T00:00:00Z', vigente_hasta: null, estado: 'activo' },
  { uuid: '00000000-0000-0000-0000-000000000002', tipo: 'Moto', vigente_desde: '2026-01-01T00:00:00Z', vigente_hasta: null, estado: 'activo' },
];

export function useTiposVehiculo() {
  const accessToken = useAuthStore((s) => s.accessToken);
  const { data, error, isLoading, mutate } = useSWR<TipoVehiculo[]>(
    accessToken ? '/catalogos/tipos-vehiculo' : null,
    () => getTiposVehiculo(),
    {
      fallbackData: HARDCODED_CATALOG,                   // DEC-F4.1-05 NUNCA pantalla rota
      dedupingInterval: 5 * 60 * 1000,                   // plan.md:1375 verbatim 5min
      shouldRetryOnError: (err) => (err as ParkosHttpError)?.status !== 404,
      onError: (err) => {
        if ((err as ParkosHttpError)?.status === 401) {
          useAuthStore.getState().clear();
          window.dispatchEvent(new Event('parkos:auth:cleared'));
        }
      },
    },
  );
  return { tipos: data ?? HARDCODED_CATALOG, isLoading, error, refresh: mutate,
           isFromFallback: data === HARDCODED_CATALOG };
}
```

### A.4 `placa.test.ts` (6 tests verbatim plan.md:1381 — T1)

```typescript
import { describe, it, expect } from 'vitest';
import { detectarTipoVehiculo, REGEX_AUTO, REGEX_MOTO } from './placa';

describe('detectarTipoVehiculo', () => {
  it('U1: ABC123 → Auto', () => expect(detectarTipoVehiculo('ABC123')).toBe('Auto'));
  it('U2: ABC12D → Moto', () => expect(detectarTipoVehiculo('ABC12D')).toBe('Moto'));
  it('U3: ABCD12 → null', () => expect(detectarTipoVehiculo('ABCD12')).toBeNull());
  it('U4: "" → null', () => expect(detectarTipoVehiculo('')).toBeNull());
  it('U5: abc123 → Auto (normalizado)', () => expect(detectarTipoVehiculo('abc123')).toBe('Auto'));
  it('U6: "  ABC123  " → Auto (con espacios)', () => expect(detectarTipoVehiculo('  ABC123  ')).toBe('Auto'));
});

describe('regex constants exported', () => {
  it('REGEX_AUTO matches ABC123', () => expect(REGEX_AUTO.test('ABC123')).toBe(true));
  it('REGEX_MOTO matches ABC12D', () => expect(REGEX_MOTO.test('ABC12D')).toBe(true));
});
```

### A.5 `tiposVehiculoApi.test.ts` (2 tests — T2)

```typescript
import { describe, it, expect, vi } from 'vitest';
import { getTiposVehiculo } from './tiposVehiculoApi';
import { parkosFetch } from '@parkos/ui-kit/fetch';

vi.mock('@parkos/ui-kit/fetch', () => ({ parkosFetch: vi.fn(), ParkosHttpError: class {} }));

describe('getTiposVehiculo', () => {
  it('U5a: 200 OK → TipoVehiculo[] poblado', async () => {
    vi.mocked(parkosFetch).mockResolvedValueOnce([{ uuid: 'a', tipo: 'Auto', vigente_desde: '2026-01-01', vigente_hasta: null, estado: 'activo' }]);
    const result = await getTiposVehiculo();
    expect(result).toHaveLength(1);
    expect(result[0]?.tipo).toBe('Auto');
  });
  it('U5b: 404 → [] (NO lanza error)', async () => {
    vi.mocked(parkosFetch).mockRejectedValueOnce({ status: 404 });
    const result = await getTiposVehiculo();
    expect(result).toEqual([]);
  });
});
```

### A.6 `useTiposVehiculo.test.ts` (5 tests — T2, precedent F3.3 verbatim)

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useTiposVehiculo } from './useTiposVehiculo';
import { useAuthStore } from '@parkos/ui-kit/store';

vi.mock('@parkos/ui-kit/store', () => ({ useAuthStore: vi.fn() }));
vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: vi.fn(),
  ParkosHttpError: class { status: number; constructor(s: number) { this.status = s; } },
}));

describe('useTiposVehiculo', () => {
  beforeEach(() => vi.clearAllMocks());

  it('U7: SWR key null sin token → HARDCODED_CATALOG sin fetch', async () => {
    vi.mocked(useAuthStore).mockImplementation((sel: any) => sel({ accessToken: null }));
    const { result } = renderHook(() => useTiposVehiculo());
    await waitFor(() => expect(result.current.tipos).toHaveLength(2));
  });

  it('U8: fetch OK con catálogo poblado → isFromFallback false', async () => {
    vi.mocked(useAuthStore).mockImplementation((sel: any) => sel({ accessToken: 'tok' }));
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: true, status: 200,
      json: async () => [{ uuid: 'a', tipo: 'Auto', vigente_desde: '2026-01-01', vigente_hasta: null, estado: 'activo' }] });
    const { result } = renderHook(() => useTiposVehiculo());
    await waitFor(() => expect(result.current.isFromFallback).toBe(false));
  });

  it('U9: fetch error 500 → fallback hardcoded', async () => {
    vi.mocked(useAuthStore).mockImplementation((sel: any) => sel({ accessToken: 'tok' }));
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: false, status: 500 });
    const { result } = renderHook(() => useTiposVehiculo());
    await waitFor(() => expect(result.current.isFromFallback).toBe(true));
  });

  it('U10: dedupingInterval = 5min (300000ms)', () => {
    vi.mocked(useAuthStore).mockImplementation((sel: any) => sel({ accessToken: 'tok' }));
    const swrSpy = vi.spyOn(require('swr'), 'default');
    renderHook(() => useTiposVehiculo());
    expect(swrSpy).toHaveBeenCalledWith(expect.anything(), expect.anything(), expect.objectContaining({ dedupingInterval: 300000 }));
  });

  it('U11: onError con status=401 dispara clear + event', async () => {
    const clearSpy = vi.fn();
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    vi.mocked(useAuthStore).mockImplementation((sel: any) => sel({ accessToken: 'tok', clear: clearSpy }));
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: false, status: 401 });
    renderHook(() => useTiposVehiculo());
    await waitFor(() => expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'parkos:auth:cleared' })));
  });
});
```

---

## Apéndice B — config deltas (3 configs)

### B.1 `vitest.config.ts` (apps/electron-sucursal)

F4.1 agrega coverage thresholds para los nuevos archivos `placa.ts` + `tiposVehiculoApi.ts` + `useTiposVehiculo.ts`. Sin cambios estructurales.

```diff
   // apps/electron-sucursal/vitest.config.ts
   coverage: {
     provider: 'v8',
     thresholds: {
       // ... existing F2.1+F3.1+F3.2+F3.3 thresholds ...
+      'src/lib/validation/placa.ts':                          { lines: 95, functions: 95, branches: 90 },
+      'src/features/catalogos/api/tiposVehiculoApi.ts':        { lines: 90, functions: 90, branches: 85 },
+      'src/features/catalogos/hooks/useTiposVehiculo.ts':       { lines: 90, functions: 90, branches: 85 },
     }
   }
```

### B.2 `package.json` (apps/electron-sucursal)

F4.1 **NO requiere nuevas dependencias**. Todo el stack ya está en `package.json` per F2.1+F2.2+F3.1+F3.2+F3.3 baseline (`react@^18.3.1` + `react-router-dom@^6.27.0` + `react-hook-form@^7.53.0` + `zod@^3.23.0` + `swr` + `vitest` + `@testing-library/react` + `i18next` + `react-i18next`).

```diff
   "dependencies": {
-    // F2.1 + F2.2 + F3.1 + F3.2 + F3.3 stack (sin cambios)
+    // F2.1 + F2.2 + F3.1 + F3.2 + F3.3 stack + F4.1 detectarTipoVehiculo + useTiposVehiculo (NO requiere nuevas deps)
   }
```

### B.3 `tsconfig.renderer.json`

F4.1 **NO requiere cambios**. `placa.ts` + `tiposVehiculoApi.ts` + `useTiposVehiculo.ts` usan imports existentes (`react`, `swr`, `@parkos/ui-kit/*`). Strict mode + `noUncheckedIndexedAccess` + `noImplicitOverride` heredados de F2.1+F3.x.

```diff
   // Sin cambios — F4.1 hereda paths y strict mode de F2.1+F2.2+F3.x
```

---

## CHANGELOG

- (2026-09-16) F4.1 design phase complete — 13 secciones + 2 apéndices verbatim clonando layout F3.3 1:1 con adaptación a scope función pura + hook SWR (sin UI containers, ~880 LOC target — actual ~[XXX] LOC). 11 DEC-F4.1-01..11 documentados (cross-ref `proposal.md` §4 + `exploration.md` §7). DEC-F4.1-07 + DEC-F4.1-11 verdict **DELTA** (F4.1 ES user-facing: detectarTipoVehiculo función pura + useTiposVehiculo SWR con fallback hardcoded + i18n key placa_formato_invalido + defense in depth XR6 layer 4 + WCAG forward F6.1). 7 acceptance gates G1..G7 mapeados a tests (G1 typecheck placa+hook, G2 lint, G3 vitest 11 tests verde, G4 atomic commits C1+C2, G5 SWR config deduping 5min, G6 axe-core forward F6.1, G7 e2e SKIPPED-env D-env documentado). 6 REQ-OPS-125..130 coverage (REQ-OPS-125 detectarTipoVehiculo función pura, REQ-OPS-126 i18n key placa_formato_invalido, REQ-OPS-127 useTiposVehiculo SWR token-gated + deduping 5min + fallback, REQ-OPS-128 tiposVehiculoApi typed wrapper, REQ-OPS-129 defense in depth XR6 layer 4, REQ-OPS-130 WCAG 2.1 AA forward F6.1). Arquitectura: `detectarTipoVehiculo` función pura NEW (T1 normalización trim+uppercase+remove-whitespace + REGEX_AUTO + REGEX_MOTO exportadas + JSDoc DEC-SUC-22/A-03/BR2 verbatim) + `useTiposVehiculo` hook SWR NEW (T2 key null-when-no-token + dedupingInterval 5min + fallbackData HARDCODED_CATALOG + shouldRetryOnError 404 + onError 401 clear + isFromFallback flag) + `tiposVehiculoApi` typed wrapper NEW (T2 parkosFetch GET + 404 → [] + filtro tipo null defensivo) + `operacion.json` i18n MODIFY (+1 key placa_formato_invalido verbatim plan.md:1366, namespace pre-existente F2.1 DEC-ELEC-06) + `vitest.config.ts` MODIFY (+3 coverage thresholds) + 6 unit tests placa (U1..U6 verbatim plan.md:1381) + 2 unit tests api (U5a 200 OK + U5b 404 → []) + 5 unit tests hook (U7 SWR null sin token + U8 fetch OK + U9 fallback cuando error + U10 dedupingInterval 5min + U11 401 clear + event dispatch precedent F3.3). 2 atomic commits per DEC-F4.1-08 work-unit-commits skill (C1 feat(operacion) T1+T3 agrupados cohesivos + C2 feat(catalogos) T2 independiente). 0 KNOWN-MISSING. F4.1 ready for `sdd-tasks`.

---

**End of design — HU-F4.1.**
