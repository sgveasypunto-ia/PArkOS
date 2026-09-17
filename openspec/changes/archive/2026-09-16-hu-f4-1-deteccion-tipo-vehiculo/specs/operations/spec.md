# Delta Spec — HU-F4.1 Detección de tipo de vehículo por placa (función pura `detectarTipoVehiculo()` estricto + hook SWR `useTiposVehiculo()` con fallback hardcoded `{auto, moto}`)

> **Phase**: spec (sdd-spec) · **Status**: ready for sdd-design (parallel) + sdd-tasks
> **HU ID**: HU-F4.1 (Fase 4 — primera HU; Catálogos y ocupación en vivo)
> **Change**: `hu-f4-1-deteccion-tipo-vehiculo`
> **Spec canonical**: `openspec/specs/operations/spec.md` (v: post-F3.3 archive, 124 REQ-OPS-001..124)
> **Delta type**: MATERIALIZED con 6 new REQ-OPS-125..130 (user-facing behavior per F1.15 + F3.1 + F3.2 + F3.3 precedent)
> **DEC-F4.1-07 + DEC-F4.1-11 verdict**: DELTA (NOT NO-OP) — F4.1 ES user-facing behavior observable (autodetectar tipo al digitar placa + error inline "formato inválido" + catálogo con fallback degradado + SWR token-gated + defense in depth XR6 + WCAG 2.1 AA forward).

---

## 0. Metadata

- **HU**: HU-F4.1
- **Fase**: 4 (Catálogos y ocupación en vivo — primera HU)
- **Spec delta type**: MATERIALIZED DELTA (NOT NO-OP stub)
- **New REQ-OPS**: 6 (REQ-OPS-125..130)
- **Author**: Parkos Dev <dev@parkos.local>
- **Date**: 2026-09-16
- **Branch**: `feature/hu-f4-1-deteccion-tipo-vehiculo` (clean, recién creada desde `dev`)
- **PR target**: `origin/dev`
- **Precedente directo**: F3.3 archivado 2026-09-15 con 6 new REQ-OPS-119..124 (`openspec/changes/archive/2026-09-15-hu-f3-3-abrir-cerrar-turno/specs/operations/spec.md`). Cadena: F1.15 (login histórico, REQ-OPS-102..105) + F3.1 (Login email+password, REQ-OPS-106..112) + F3.2 (lockout countdown, REQ-OPS-113..118) + F3.3 (abrir/cerrar turno, REQ-OPS-119..124).
- **Spec canonical vigente**: 124 REQ-OPS (REQ-OPS-001..124) post-F3.3 archive.
- **Numeración monotónica verificada**: 124 → 125 → 126 → 127 → 128 → 129 → 130 (0 gaps, sin duplicados). Materialization al canonical `operations/spec.md` ocurre en `sdd-archive` phase, NO en spec phase.

---

## 1. Contexto y motivación

F4.1 cierra el **gap UX crítico** que F1.x + F3.x archivados dejaron abierto en el flujo de ingreso vehicular CU-01 (forward HU-F6.1): aunque el backend ya shipped `detectar_tipo_vehiculo()` server-side en `operacion.py:215-277` (defense in depth XR6 layer 4) y `GET /api/v1/catalogos/tipos-vehiculo` en `catalogos.py:140-147`, **el cliente NO tiene la pieza que autocompleta el tipo de vehículo al digitar la placa** — el operador debe tipear la placa Y seleccionar manualmente el tipo (Auto / Moto) en dos pasos separados. Esto viola la regla de negocio BR2 de CU-01, literal: "autodetección por regex es la ÚNICA fuente válida; NO hay override manual del cajero; si falla, se corrige como bug" (plan.md:1369). F4.1 entrega la pieza cliente end-to-end, anclando el comportamiento observable al operador en 6 new REQ-OPS-125..130.

A diferencia de F2.1/F2.2/F2.3 (infra-only con NO-OP stub per `DEC-ELEC-10`, `DEC-FETCH-10`, `DEC-UPD-13`), F4.1 ES user-facing behavior observable en cuatro dimensiones: (a) **autocompletar tipo al digitar placa** — operador NO selecciona manualmente; (b) **mensaje inline "Placa no coincide con ningún formato conocido"** si regex no matchea (forward WCAG `role="alert"` F6.1); (c) **catálogo cargado desde API con fallback hardcoded `{auto, moto}`** si la API está down (degradación observable, nunca pantalla rota — plan.md:1375 verbatim); (d) **defense in depth bidireccional** cliente (`detectarTipoVehiculo()` UX rápido) + backend (`detectar_tipo_vehiculo()` server-side ya shipped — operacion.py:261 verbatim "Server overwrites via V5 (regex-derived UUID wins over client value)"). Esta behavior visible al usuario NO puede vivir solo en `DEC-F4.1-NN` dentro de `proposal.md` — debe anclarse en `REQ-OPS-NNN` dentro del spec canónico.

`DEC-F4.1-07 + DEC-F4.1-11` (introducidos en `proposal.md §4.7 + §4.11`) **rompen** el precedent NO-OP de F2.x y adoptan precedent F1.15 + F3.x. Las 6 new REQ-OPS-125..130 documentan el comportamiento observable en formato Given/When/Then/And RFC 2119, con anchor links explícitos a `DEC-F4.1-NN` ratificados en `proposal.md §4`.

Adicionalmente, F4.1 entrega **`useTiposVehiculo()`** como hook genuinely reusable del feature `catalogos` — se exporta desde `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` para forward consumption F4.2 (tarifas) + F4.3 (ocupación en vivo) + F6.1 (ingreso vehicular `<PlacaInput>`) + F7.x (salida). El pattern SWR con `dedupingInterval: 5 * 60 * 1000` + `shouldRetryOnError` excl 404 + `onError` con status=401 dispara `useAuthStore.clear()` + `parkos:auth:cleared` event es **idéntico** al precedent F3.3 `useSesionActiva` (REQ-OPS-120).

---

## 2. Goals y no-goals

### 2.1 Goals in-scope (6 new REQ-OPS)

| REQ-OPS | Comportamiento observable al operador |
|---|---|
| **REQ-OPS-125** | `detectarTipoVehiculo(placa: string): 'Auto' \| 'Moto' \| null` función pura con regex estricto hardcoded (`^[A-Z]{3}[0-9]{3}$` Auto, `^[A-Z]{3}[0-9]{2}[A-Z]$` Moto), normalización previa (trim + uppercase + remover whitespace interno), exports `REGEX_AUTO` + `REGEX_MOTO` para reuso F6.1 Zod validation |
| **REQ-OPS-126** | i18n key `operacion.placa_formato_invalido` con literal verbatim "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)" para consumo forward F6.1 `<PlacaInput>` `<p role="alert" aria-describedby>` |
| **REQ-OPS-127** | `useTiposVehiculo()` hook SWR con key `accessToken ? '/catalogos/tipos-vehiculo' : null`, `dedupingInterval: 5 * 60 * 1000` (plan.md:1375 verbatim), `fallbackData: HARDCODED_CATALOG` con `{auto, moto}` UUIDs sentinels literales, `shouldRetryOnError` excl 404, `onError` con status=401 dispara `useAuthStore.clear()` + `parkos:auth:cleared` event. Retorna `{tipos, isLoading, error, refresh, isFromFallback}` |
| **REQ-OPS-128** | `tiposVehiculoApi.getTiposVehiculo()` typed wrapper `parkosFetch<TiposVehiculoReadList>('/api/v1/catalogos/tipos-vehiculo')` con mapeo 404 → `[]` (catálogo vacío es estado válido) + filtro defensivo de filas con `tipo: null` |
| **REQ-OPS-129** | Defense in depth XR6 layer 4: cliente detecta (F4.1) + backend re-valida con `detectar_tipo_vehiculo()` server-side (shipped HU-F1.x — `operacion.py:215-277`); backend SIEMPRE wins (overwrites via V5 "regex-derived UUID wins over client value", operacion.py:261 verbatim) |
| **REQ-OPS-130** | WCAG 2.1 AA compliance (forward F6.1) — la i18n key + el detector sientan las bases para que `<PlacaInput>` use `aria-describedby` + `<p role="alert">` con 0 violaciones axe-core (verificación en F6.1 forward, RNF-022) |

### 2.2 Out of scope (deferred a Fase 4+)

- **Backend cambios** — `detectar_tipo_vehiculo()` server-side ya shipped (`operacion.py:215-277`, HU-F1.x) + `GET /api/v1/catalogos/tipos-vehiculo` C+Q+U router ya shipped (`catalogos.py:140-147`). F4.1 NO modifica backend.
- **UI componente `<PlacaInput>`** — HU-F6.1 entrega el componente que consume `detectarTipoVehiculo()` y renderiza el mensaje de error. F4.1 entrega SOLO la función pura + el hook del catálogo + la i18n key.
- **Selector manual de tipo de vehículo** — el corpus es categórico (BR2 + DEC-SUC-22). NO existe `<Select>` ni `<RadioGroup>` para tipo. F4.1 NO entrega UI de override.
- **Tolerancia de tipeo `O↔0`/`I↔1`/`B↔8`** — pertenece a `buscarIngresoTolerante()` Fase 7 (DEC-SUC-22 verbatim). F4.1 entrega función estricta sin tolerancia. Funciones DISTINTAS en archivos DISTINTOS.
- **Migraciones Alembic** — ninguna tabla nueva ni columna nueva (regex vive en código cliente, NO en BD — A-03 explícito, 4NF canon).
- **`electron-store` fallback persistente** — fallback hardcoded `{auto, moto}`, NO persistente entre sesiones (HU-F4.2 sí usa electron-store; F4.1 catálogos reference data suficiente).
- **`refreshInterval` periódico** — SWR solo `dedupingInterval`. Si admin cambia `tipos_vehiculo`, operador verá al próximo refresh SWR (5min) o al cerrar/abrir turno.
- **e2e test (Playwright)** — F4.1 es lógica pura. Los 11 unit tests cubren la lógica. e2e testeará `<PlacaInput>` (F6.1) que consume F4.1. Documentado como forward coverage.
- **WCAG axe-core scan runtime** — 6 unit tests + 5 hook tests cubren lógica. axe-core A1 scan es para HU-F6.1 (`<PlacaInput>` visible). F4.1 sienta las bases (i18n key + detector).
- **i18n plurals** — mensaje de error es string único. NO requiere `i18next-resources-types`.
- **`crypto.randomUUID()` para fallback uuids** — fallback hardcoded usa UUIDs sentinels literales (`'00000000-0000-0000-0000-000000000001'` Auto, `'...0002'` Moto), NO generados dinámicamente.
- **Tipos de vehículo adicionales** (`Bicicleta`, `Camión`, `Moto eléctrica`) — A-03 explícito: "no hay respaldo en el corpus de CU para un tercer patrón". Si negocio lo requiere, DEC-F4.1-NN futura.
- **Extensión de `PRE_FLIGHT_PATHS`** — F4.1 NO modifica `parkosFetch.ts`. Las rutas `/catalogos/*` (GET) son read idempotente — NO requieren pre-flight gate (DEC-SUC-03 + F3.2 verbatim).

---

## 3. Requirements (REQ-OPS-125..130)

### REQ-OPS-125 — `detectarTipoVehiculo()` función pura estricta con regex hardcoded (DEC-F4.1-01 + DEC-F4.1-02 + DEC-F4.1-03 + DEC-SUC-22 + A-03 + BR2)

**Source**: `plan.md:1355-1388` + `plan.md:437` DEC-SUC-22 + `plan.md:454` A-03 + `plan.md:1369` BR2 · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
La función `export function detectarTipoVehiculo(placa: string): 'Auto' | 'Moto' | null` exportada desde `apps/electron-sucursal/src/lib/validation/placa.ts` MUST ser pura determinista — sin acceso a red, store, DOM. La función MUST aplicar normalización previa al regex en este orden exacto: (1) `placa.trim()`; (2) `placa.toUpperCase()`; (3) `placa.replace(/\s+/g, '')` para remover TODO whitespace interno. Posterior MUST aplicar las constantes exportadas `export const REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/` y `export const REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/`. La función MUST retornar `'Auto'` si `REGEX_AUTO.test(placaNormalizada)` retorna `true`; MUST retornar `'Moto'` si `REGEX_MOTO.test(placaNormalizada)` retorna `true`; MUST retornar `null` si ninguna regex matchea. La función MUST NO aplicar tolerancia de tipeo `O↔0`/`I↔1`/`B↔8` (DEC-SUC-22 verbatim) — esa tolerancia es exclusiva de `buscarIngresoTolerante()` Fase 7. La función MUST NO tener un parámetro override de tipo — UNA sola firma, BR2 literal. La JSDoc MUST referenciar explícitamente `operacion.py:215-277` (backend counterpart) + DEC-SUC-22 + A-03 + BR2.

**Rationale**: La función pura permite testing determinista sin mocks; la normalización previa cubre minúsculas + espacios sin regex tolerantes (que introducirían matches falsos). DEC-SUC-22 es categórico: tolerancia `O↔0`/`I↔1`/`B↔8` pertenece a Fase 7, NO Fase 4. Exportar las regex constantes permite DRY con F6.1 sin acoplar F4.1 a F6.1.

#### Scenario 1: `detectarTipoVehiculo('ABC123')` → `'Auto'` (happy path Auto)
- **Given** la función pura `detectarTipoVehiculo` exportada desde `lib/validation/placa.ts`
- **When** el operador (o F6.1 `<PlacaInput>`) invoca `detectarTipoVehiculo('ABC123')`
- **Then** la función MUST normalizar (trim + uppercase — sin cambio) y MUST retornar `'Auto'`
- **And** MUST NO invocar red, store, ni DOM (función pura).

#### Scenario 2: `detectarTipoVehiculo('ABC12D')` → `'Moto'` (happy path Moto)
- **Given** la función pura exportada
- **When** el operador invoca `detectarTipoVehiculo('ABC12D')`
- **Then** MUST retornar `'Moto'`.

#### Scenario 3: `detectarTipoVehiculo('ABCD12')` → `null` (formato inválido)
- **Given** la función pura exportada
- **When** el operador invoca `detectarTipoVehiculo('ABCD12')` (4 letras + 2 dígitos — no calza Auto ni Moto)
- **Then** MUST retornar `null` (NO aplica tolerancia — DEC-SUC-22 verbatim).

#### Scenario 4: `detectarTipoVehiculo('')` → `null` (placa vacía)
- **Given** la función pura exportada
- **When** el operador invoca `detectarTipoVehiculo('')`
- **Then** MUST retornar `null` (string vacío no matchea ninguna regex).

#### Scenario 5: `detectarTipoVehiculo('abc123')` → `'Auto'` (minúsculas normalizadas)
- **Given** la función pura exportada
- **When** el operador invoca `detectarTipoVehiculo('abc123')`
- **Then** MUST aplicar `toUpperCase()` → `'ABC123'` y MUST retornar `'Auto'`.

#### Scenario 6: `detectarTipoVehiculo('  ABC123  ')` → `'Auto'` (espacios)
- **Given** la función pura exportada
- **When** el operador invoca `detectarTipoVehiculo('  ABC123  ')`
- **Then** MUST aplicar trim + uppercase + remove whitespace → `'ABC123'` y MUST retornar `'Auto'`.

---

### REQ-OPS-126 — i18n key `operacion.placa_formato_invalido` con mensaje literal (DEC-F4.1-07 forward hook + F2.1 DEC-ELEC-06 namespace)

**Source**: `plan.md:1366` verbatim string + F2.1 DEC-ELEC-06 · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
El namespace pre-existente `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` MUST agregar UNA nueva key top-level `placa_formato_invalido` con el string literal verbatim "`Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)`" (plan.md:1366 verbatim — incluye placeholders `ABC123` y `ABC12D` como ejemplos literales). La key MUST NO tener variables de interpolación (`{{tipo}}` NO permitido). El namespace `operacion.json` MUST seguir registrado en `i18n/index.ts` sin cambios (F2.1 DEC-ELEC-06 verbatim). La key MUST ser consumible forward por F6.1 `<PlacaInput>` con `<p role="alert" data-testid="placa-formato-invalido">{t('operacion.placa_formato_invalido')}</p>` y MUST propagarse al `aria-describedby` del `<Input>` para que screen readers anuncien el error (WCAG 2.1 AA — forward F6.1). El snapshot test del JSON MUST verificar la key con el string literal exacto (defense contra typo silencioso).

**Rationale**: La key pre-poblada evita que F6.1 agregue key nueva al implementar el componente. Namespace pre-existente respeta DEC-ELEC-06 (un namespace por bounded context). String literal sin interpolación garantiza traducción atómica y verificable.

#### Scenario 1: i18n key existe en operacion.json con string literal verbatim
- **Given** el namespace `operacion.json` con 10 keys pre-F4.1 (`ingreso`, `salida`, `placa`, `tipo`, `tarifa`, `total`, `registrar`, `imprimir`, `anular`, `confirmar`)
- **When** F4.1 ship T3
- **Then** `operacion.json` MUST contener la key top-level `placa_formato_invalido`
- **And** el valor MUST ser exactamente `"Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)"`
- **And** MUST NO tener variables de interpolación.

#### Scenario 2: Snapshot test del JSON verifica la key + string verbatim
- **Given** el snapshot test del JSON `operacion.json`
- **When** `vitest run` ejecuta el snapshot
- **Then** el snapshot MUST contener la key con string verbatim
- **And** MUST fallar si la key se borra o el string cambia (defense contra typo).

#### Scenario 3: F6.1 `<PlacaInput>` consume la key vía `t('operacion.placa_formato_invalido')` (forward)
- **Given** la key registrada en `operacion.json` post-F4.1
- **When** F6.1 HU futura implementa `<PlacaInput>` y renderiza error inline cuando `detectarTipoVehiculo() === null`
- **Then** `<p role="alert" aria-describedby="placa-input-error">{t('operacion.placa_formato_invalido')}</p>` MUST renderizar el string i18n
- **And** WCAG axe-core MUST validar `aria-describedby` apuntando al `<p role="alert">` (RNF-022 forward).

---

### REQ-OPS-127 — `useTiposVehiculo()` SWR hook con deduping 5min + fallback hardcoded `{auto, moto}` (DEC-F4.1-04 + DEC-F4.1-05 + DEC-F4.1-06 + F3.3 REQ-OPS-120 precedent)

**Source**: `plan.md:1375` verbatim + F3.3 REQ-OPS-120 SWR precedent · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El hook `useTiposVehiculo(): { tipos: TipoVehiculo[]; isLoading: boolean; error: Error | undefined; refresh: () => Promise<TipoVehiculo[] | undefined>; isFromFallback: boolean }` exportado desde `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` MUST consumir `useAuthStore(s => s.accessToken)` y MUST configurar `useSWR` con: (1) `key: accessToken ? '/catalogos/tipos-vehiculo' : null` (key null sin token, idéntico pattern F3.3 `useSesionActiva`); (2) `fetcher: () => tiposVehiculoApi.getTiposVehiculo()`; (3) `dedupingInterval: 5 * 60 * 1000` (plan.md:1375 verbatim — 5min para catálogos reference data); (4) `fallbackData: HARDCODED_CATALOG` constante módulo-level `[{uuid: '00000000-0000-0000-0000-000000000001', tipo: 'Auto', vigente_desde: '2026-01-01T00:00:00Z', vigente_hasta: null, estado: 'activo'}, {uuid: '00000000-0000-0000-0000-000000000002', tipo: 'Moto', ...}]` (UUIDs sentinels literales, NO `crypto.randomUUID()`); (5) `shouldRetryOnError: (err) => err?.status !== 404` (catálogo vacío es estado válido — NO retry spam); (6) `onError: (err) => { if (err?.status === 401) { useAuthStore.getState().clear(); window.dispatchEvent(new Event('parkos:auth:cleared')) } }` (precedent F3.3 verbatim — 401 dispara logout defensivo + forward hook AuthGuard F4.x+). El hook MUST retornar `{tipos: data ?? HARDCODED_CATALOG, isLoading, error: error?.status === 404 ? undefined : error, refresh: mutate, isFromFallback: data === undefined || data === HARDCODED_CATALOG}` — cuando la API no responde o retorna 5xx, SWR muestra `HARDCODED_CATALOG` y `isFromFallback === true` permite a consumers futuros (F4.3 + F6.x) mostrar `<Tooltip>` "usando datos locales" (DEC-F4.1-06).

**Rationale**: DedupingInterval 5min (vs 10s de `useSesionActiva`) refleja que catálogos NO son transaccionales — son reference data. F4.2 + F4.3 + F6.1 comparten el dedup SWR — un solo fetch cada 5min. Fallback hardcoded garantiza "nunca pantalla rota" (plan.md:1375 verbatim) si la API está down.

#### Scenario 1: SWR key null sin token → hook retorna HARDCODED_CATALOG fallback sin fetch
- **Given** el operador no está autenticado (`useAuthStore.accessToken === null`)
- **When** un componente invoca `useTiposVehiculo()`
- **Then** la SWR key MUST ser `null` (ternaria convierte string vacío a `null`)
- **And** SWR MUST NO ejecutar el fetcher
- **And** el hook MUST retornar `{tipos: HARDCODED_CATALOG, isLoading: false, error: undefined, refresh: <fn>, isFromFallback: true}`
- **And** ningún `parkosFetch('/catalogos/tipos-vehiculo')` MUST ejecutarse.

#### Scenario 2: SWR fetch OK con catálogo poblado → hook retorna tipos + `isFromFallback: false`
- **Given** el operador autenticado (`useAuthStore.accessToken !== null`)
- **And** MSW mockea `GET /catalogos/tipos-vehiculo` retornando `200 OK` con `[{uuid: 'real-uuid-auto', tipo: 'Auto'}, {uuid: 'real-uuid-moto', tipo: 'Moto'}]`
- **When** un componente invoca `useTiposVehiculo()` por primera vez
- **Then** SWR MUST ejecutar `parkosFetch('/catalogos/tipos-vehiculo')` con la SWR key
- **And** el hook MUST retornar `{tipos: [...], isLoading: false, error: undefined, refresh: <fn>, isFromFallback: false}`.

#### Scenario 3: Fallback hardcoded cuando API retorna 500
- **Given** el operador autenticado pero la API responde `500 Internal Server Error`
- **When** SWR ejecuta el fetcher y la respuesta falla
- **Then** `tiposVehiculoApi.getTiposVehiculo()` MUST rechazar con error
- **And** SWR MUST usar `fallbackData: HARDCODED_CATALOG` como data
- **And** el hook MUST retornar `{tipos: HARDCODED_CATALOG, isLoading: false, error: <error500>, refresh: <fn>, isFromFallback: true}` (degradación explícita).

#### Scenario 4: dedupingInterval = 5 * 60 * 1000 verificado en swrOptions (plan.md:1375 verbatim)
- **Given** el hook exportado
- **When** `useTiposVehiculo.test.ts` captura `swrOptions` del mock y verifica `swrOptions.dedupingInterval`
- **Then** el valor MUST ser exactamente `5 * 60 * 1000` = `300_000ms`.

#### Scenario 5: onError con status=401 → `useAuthStore.clear()` + `parkos:auth:cleared` event
- **Given** el operador autenticado pero token expirado (backend responde 401)
- **When** SWR ejecuta el fetcher y `onError` captura el error
- **Then** `onError` MUST detectar `err?.status === 401`
- **And** MUST invocar `useAuthStore.getState().clear()` (borra tokens vía IPC bridge per F2.2)
- **And** MUST despachar `new Event('parkos:auth:cleared')` en `window` (forward hook AuthGuard F4.x+).

---

### REQ-OPS-128 — `tiposVehiculoApi.getTiposVehiculo()` typed wrapper con 404→[] + filtro defensivo `tipo: null` (DEC-F4.1-09 + F2.2 `parkosFetch` precedent + backend `catalogos.py:140-147`)

**Source**: `DEC-F4.1-09` + F2.2 `parkosFetch` + `catalogos.py:140-147` · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
El módulo `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` MUST exportar `async function getTiposVehiculo(): Promise<TipoVehiculo[]>` que internamente ejecuta `parkosFetch<TiposVehiculoReadList>('/api/v1/catalogos/tipos-vehiculo')` (per F2.2 — NO `fetch` directo, heredando retry + refresh-once 401 via Mutex + Idempotency-Key auto). La interface `interface TipoVehiculo { uuid: string; tipo: string | null; vigente_desde: string; vigente_hasta: string | null; estado: string }` MUST exportar desde el módulo matching backend `TiposVehiculoRead` (`schemas/tipos_vehiculo.py:13-23`). La función MUST capturar respuestas `404 Not Found` (catálogo vacío es estado válido) y retornar `[]`. La función MUST filtrar defensivamente cualquier fila con `tipo: null` ANTES de retornar al hook (`data.filter(row => row.tipo !== null)`). La función MUST NO usar `fetch` directo — TODO acceso a red vía `parkosFetch`.

**Rationale**: TypeScript strict (F2.1 baseline) requiere tipos explícitos. Backend Pydantic permite `tipo: str | None`; mentir al cliente sería bug latente. Filtro defensivo garantiza que F4.3 + F6.1 reciban solo filas con `tipo` truthy. 404 → `[]` evita contaminar SWR con error cuando sucursal nueva no tiene tipos configurados.

#### Scenario 1: GET 200 OK con catálogo poblado → retorna `TipoVehiculo[]` filtrado
- **Given** el operador autenticado
- **And** MSW mockea `GET /api/v1/catalogos/tipos-vehiculo` retornando `200 OK` con body `[{uuid: 'real-uuid-auto', tipo: 'Auto', vigente_desde: '2026-01-01T...', vigente_hasta: null, estado: 'activo'}, {uuid: 'real-uuid-moto', tipo: 'Moto', ...}]`
- **When** el hook invoca `tiposVehiculoApi.getTiposVehiculo()`
- **Then** MUST ejecutar `parkosFetch('/api/v1/catalogos/tipos-vehiculo')`
- **And** MUST retornar el array poblado después del filtro `tipo !== null`.

#### Scenario 2: GET 404 Not Found → retorna `[]` (catálogo vacío es válido)
- **Given** el operador autenticado pero el catálogo está vacío (sucursal nueva sin tipos configurados)
- **And** MSW mockea `GET /api/v1/catalogos/tipos-vehiculo` retornando `404 Not Found`
- **When** el hook invoca `tiposVehiculoApi.getTiposVehiculo()`
- **Then** MUST capturar el 404 (NO rechazar) y MUST retornar `[]`.

#### Scenario 3: Filtro defensivo descarta fila con `tipo: null` (backend legacy/corrupto)
- **Given** el operador autenticado
- **And** MSW mockea `GET /api/v1/catalogos/tipos-vehiculo` retornando `200 OK` con body `[{uuid: 'real-uuid-auto', tipo: 'Auto', ...}, {uuid: 'legacy-bad-row', tipo: null, ...}]`
- **When** el hook invoca `tiposVehiculoApi.getTiposVehiculo()`
- **Then** MUST filtrar la fila con `tipo: null` y MUST retornar solo `[{uuid: 'real-uuid-auto', tipo: 'Auto', ...}]` al hook.

---

### REQ-OPS-129 — Defense in depth XR6 layer 4: cliente detecta (F4.1) + backend re-valida (`detectar_tipo_vehiculo()` server-side, operacion.py:215-277) (DEC-F4.1-01 defense layer + XR6 + operacion.py:261 verbatim)

**Source**: `operacion.py:215-277` + `operacion.py:261` V5 verbatim + `operations/spec.md:3951` XR6 · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El sistema MUST aplicar defense in depth XR6 layer 4 contract sobre el tipo de vehículo detectado: (a) **Cliente (F4.1)** — `detectarTipoVehiculo(placa)` corre ANTES del round-trip API para dar feedback inmediato al operador (UX rápido, <1ms); (b) **Backend (F1.x ya shipped)** — `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py:215-277` `detectar_tipo_vehiculo()` server-side re-valida con las MISMAS regex (`^[A-Z]{3}[0-9]{3}$` y `^[A-Z]{3}[0-9]{2}[A-Z]$`) en cada POST `/operacion/ingresos` (V5 verification — el cliente envía `uuid_tipo_vehiculo`, pero el backend OVERWRITE via V5 con el UUID derivado de su propia regex; operacion.py:261 verbatim: "Server overwrites via V5 (regex-derived UUID wins over client value)"). F4.1 MUST garantizar que el cliente NUNCA confía en sí mismo como source of truth — el backend SIEMPRE wins. La JSDoc de `detectarTipoVehiculo` MUST referenciar explícitamente `operacion.py:215-277` para que el lector entienda que divergencia entre regex cliente y regex backend es bug a corregir (R2 risk exploration.md mitigated). F4.1 MUST NO agregar validación backend nueva — la regex defense in depth ya shipped F1.x.

**Rationale**: Defense in depth bidireccional — cliente rápido (<1ms, sin red) para UX inmediata, backend authoritative (truth DB) rechaza lógica corrupta del cliente. Si divergen (R2 risk), es bug a corregir; NUNCA el cliente es source of truth. Pattern XR6 anclada en `operations/spec.md:3951` — F4.1 cumple layer 4 (contract: regex bidireccional cliente+backend).

#### Scenario 1: Cliente detecta Auto para placa `ABC123` → backend confirma server-side en POST
- **Given** F6.1 `<PlacaInput>` consume `detectarTipoVehiculo('ABC123')` → retorna `'Auto'`
- **And** F6.1 envía POST `/operacion/ingresos` con body `{placa: 'ABC123', uuid_tipo_vehiculo: '<uuid-auto>', ...}` (uuid del catálogo API)
- **When** el backend `operacion.py:215-277` `detectar_tipo_vehiculo()` ejecuta V5 server-side
- **Then** MUST detectar `'Auto'` server-side (regex idéntica a cliente)
- **And** MUST overwrite `uuid_tipo_vehiculo` con el UUID derivado del server-side regex (operacion.py:261 verbatim "Server overwrites via V5 (regex-derived UUID wins over client value)")
- **And** MUST NO confiar solo en el uuid enviado por el cliente (defense in depth).

#### Scenario 2: Cliente detecta `'Auto'` per regex, pero backend divergente rechaza (R2 risk)
- **Given** (hipotético) un bug futuro donde cliente regex acepta `ABC1234` pero backend no
- **When** F6.1 envía POST con placa `ABC1234` que cliente detectó como Auto (post-bug hypothético)
- **Then** el backend MUST detectar formato inválido per su regex server-side
- **And** MUST retornar `422 Unprocessable Entity` con `{"error": "placa_formato_invalido"}` (forward V5 contract)
- **And** F4.1 cliente MUST NO prevenir este rejection — defensa es del backend (XR6 layer 4).

#### Scenario 3: JSDoc cross-link garantiza sincronización manual cliente↔backend
- **Given** `apps/electron-sucursal/src/lib/validation/placa.ts` con JSDoc que referencia `operacion.py:215-277`
- **When** un developer futuro modifica `REGEX_AUTO` o `REGEX_MOTO` en el cliente
- **Then** el JSDoc MUST alertar (vía grep `backend/.../operacion.py:215-277`) que también debe actualizar el backend
- **And** la R2 risk mitigation MUST estar documentada en la JSDoc (defense in depth bidireccional).

---

### REQ-OPS-130 — WCAG 2.1 AA compliance forward F6.1 (DEC-F4.1-11 forward coverage + RNF-022 + F3.3 REQ-OPS-124 precedent)

**Source**: `DEC-F4.1-11` forward coverage + RNF-022 + F3.3 REQ-OPS-124 axe-core precedent · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
F4.1 MUST sentar las bases WCAG 2.1 AA que F6.1 `<PlacaInput>` consumirá, sin entregar componente UI propia. La i18n key `operacion.placa_formato_invalido` (REQ-OPS-126) MUST ser consumible en F6.1 con `<p role="alert" data-testid="placa-formato-invalido" id="placa-input-error">{t('operacion.placa_formato_invalido')}</p>` (atributo `id` para que `aria-describedby` lo apunte). El detector `detectarTipoVehiculo` MUST ser determinista para que screen readers anuncien cambios de estado predecibles (input → null → error visible → Auto detectado). F6.1 forward MUST pasar `axe-core` con 0 violaciones WCAG 2.1 AA en los 4 estados: input vacío + input con placa inválida (error visible) + input con placa Auto válida + input con placa Moto válida. F4.1 MUST NO crear componente UI visible — la verificación axe-core aplica al forward consumer F6.1 (forward coverage). Las 11 unit tests de F4.1 (6 placa + 5 hook) MUST verificar la lógica determinista que F6.1 usará para los 4 estados WCAG.

**Rationale**: Operador kiosko con discapacidad visual necesita feedback predecible. La i18n key + el detector determinista + el hook con `isFromFallback` son los building blocks que F6.1 usa para WCAG. F4.1 sienta las bases sin entregar UI — la verificación axe-core vive en F6.1 forward (no project defect — sandbox F.6 SKIPPED-env precedent F2.x + F3.x).

#### Scenario 1: i18n key pre-poblada permite `<p role="alert">` con contenido textual
- **Given** la key `operacion.placa_formato_invalido` registrada en `operacion.json` (REQ-OPS-126)
- **When** F6.1 forward implementa `<p role="alert" id="placa-input-error">{t('operacion.placa_formato_invalido')}</p>`
- **Then** el `<p>` MUST contener contenido textual no vacío (axe-core rechaza `aria-live` regions vacías — RNF-022 compliance)
- **And** F6.1 MUST agregar el atributo `id` para que `<Input aria-describedby="placa-input-error">` apunte correctamente.

#### Scenario 2: detector determinista → 6 unit tests verde cubren los 4 estados WCAG (forward F6.1 axe-core inputs)
- **Given** los 6 tests placa.ts verde (U1..U6 verbatim plan.md:1381)
- **When** F6.1 forward usa los resultados del detector para gestionar 4 estados WCAG (vacío, inválido, Auto, Moto)
- **Then** el detector MUST ser determinista: misma input → misma output (forward F6.1 axe-core predictability)
- **And** los 6 tests MUST cubrir al menos: estado vacío (U4), estado inválido (U3), estado Auto válido (U1), estado Moto válido (U2).

#### Scenario 3: hook `useTiposVehiculo` retorna `isFromFallback` → permite UI accesible "usando datos locales" (forward F4.3 + F6.1)
- **Given** el hook retorna `{tipos, isLoading, error, refresh, isFromFallback}` (REQ-OPS-127)
- **When** F6.1 forward (o F4.3) quiere anunciar a screen readers que está usando datos locales
- **Then** el componente puede renderizar `<p role="status" aria-live="polite">{t('catalogos.usandoDatosLocales', { fuente: 'fallback' })}</p>` cuando `isFromFallback === true`
- **And** el `role="status"` + `aria-live="polite"` pattern MUST seguir precedent F3.3 REQ-OPS-124 Scenario 1.

---

## 4. Cross-reference table + acceptance scenarios

### 4.1 Cross-reference table

| REQ-OPS | DEC-F4.1 anchor | plan.md line | Precedent directo |
|---|---|---|---|
| REQ-OPS-125 | DEC-F4.1-01 + DEC-F4.1-02 + DEC-F4.1-03 + DEC-SUC-22 + A-03 + BR2 | 1355-1388 + 437 (DEC-SUC-22) + 454 (A-03) + 1369 (BR2) | `formatCOP` F4.2 plan.md:1416 (función pura) + `buscarIngresoTolerante()` F7.x (forward función distinta) + F1.x `detectar_tipo_vehiculo()` server-side `operacion.py:215-277` |
| REQ-OPS-126 | DEC-F4.1-07 (forward hook) + F2.1 DEC-ELEC-06 | 1366 (string literal verbatim) | F3.1 REQ-OPS-108 i18n key verbatim + F3.3 REQ-OPS-124 `?closed=true` feedback i18n + F3.2 REQ-OPS-118 `aria-live` countdown pattern |
| REQ-OPS-127 | DEC-F4.1-04 + DEC-F4.1-05 + DEC-F4.1-06 + DEC-SUC-03 | 1375 (5min verbatim) + 418 (REFRESH_INTERVAL_MS) | F3.3 REQ-OPS-120 `useSesionActiva` SWR (key null + dedup + 401 clear verbatim) + F3.1 REQ-OPS-110 `useAuth` SWR pattern |
| REQ-OPS-128 | DEC-F4.1-09 | F1.x `catalogos.py:140-147` (`_mount_catalog`) + `schemas/tipos_vehiculo.py:13-23` (`TiposVehiculoRead`) | F2.2 `parkosFetch` (retry + refresh-once 401) + F3.3 REQ-OPS-120 `sesionActivaApi.getSesionActiva()` 404 → null mapping |
| REQ-OPS-129 | DEC-F4.1-01 defense layer + XR6 | `operations/spec.md:3951` (XR6) + `operacion.py:261` (V5 verbatim) | `REQ-OPS-XR6` cross-cutting precedent + F1.x `detectar_tipo_vehiculo()` server-side ship |
| REQ-OPS-130 | DEC-F4.1-11 forward coverage + RNF-022 | RNF-022 `docs/01-requisitos/no-funcionales.md:126` | F3.3 REQ-OPS-124 (axe-core + `aria-live="polite"`) + F3.2 REQ-OPS-118 (axe-core lockout) + F3.1 REQ-OPS-112 (axe-core LoginForm) |

**Nota**: F4.1 NO crea un nuevo REQ-OPS-XR. Las 6 new REQ-OPS-125..130 son SPECIFIC al flujo de detección de placa + catálogo de tipos. REQ-OPS-XR6 de F1.13 (5-layer defense in depth) sigue siendo el canonical cross-cutting contract; F4.1 contribuye a las capas `contract` (regex bidireccional cliente+backend) + `a11y` (i18n key pre-poblada + función determinista) sin formalizar XR-NN (precedent F1.15 + F3.1 + F3.2 + F3.3 — NINGUNO crea XR nuevo en spec).

### 4.2 Acceptance scenarios for sdd-verify

| # | Criterion | Test source | Type |
|---|---|---|---|
| AC-1 | `detectarTipoVehiculo()` función pura con regex estricto + normalización + 6 cases verbatim plan.md:1381 (REQ-OPS-125) | `placa.test.ts` (T1, ~80 LOC, 6 tests: U1 Auto válido, U2 Moto válido, U3 formato inválido, U4 placa vacía, U5 minúsculas normalizadas, U6 placa con espacios) | Unit (vitest) |
| AC-2 | `useTiposVehiculo()` SWR con key null + deduping 5min + fallback hardcoded + 401 clear (REQ-OPS-127) | `useTiposVehiculo.test.ts` (T2, ~50 LOC, 5 tests: U7 SWR key null, U8 fetch OK, U9 fallback cuando API 500, U10 dedupingInterval = 5min, U11 onError 401 dispara clear + event) | Unit (vitest + MSW) |
| AC-3 | `tiposVehiculoApi` typed wrappers con 404 → [] + filtro defensivo `tipo: null` (REQ-OPS-128) | cobertura indirecta vía `useTiposVehiculo.test.ts` U8/U9 con MSW | Unit (vitest + MSW) |
| AC-4 | `operacion.json` agrega key `placa_formato_invalido` con string literal verbatim (REQ-OPS-126) | snapshot test del JSON (F2.1 baseline `i18n.test.ts` precedent) | Unit (vitest snapshot) |
| AC-5 | `REGEX_AUTO` + `REGEX_MOTO` exportadas + matching backend `operacion.py:215-277` (REQ-OPS-125 + REQ-OPS-129) | `placa.test.ts` U1 + U2 + grep cross-check `operacion.py:215-277` en CI | Unit (vitest + grep CI) |
| AC-6 | i18n key + detector + hook sientan bases WCAG 2.1 AA forward F6.1 (REQ-OPS-130) | F4.1 NO entrega componente UI — aplica al forward consumer F6.1 `<PlacaInput>`. Documentado como forward coverage per F2.x + F3.x precedent. | Forward (F6.1 axe-core) |
| AC-7 | e2e sandbox F.6 SKIPPED-env (`npm 11.16.0`) | F4.1 NO entrega e2e — los 11 unit tests cubren la lógica. Documentado como deviation D-env. | Forward (no F4.1 scope) |

**Sandbox F.6 caveat**: AC-6 + AC-7 documentados como deviation D-env en `verify-report.md` futuro (precedent F2.x + F3.x archive). NO project defect.

---

## 5. Out of scope (deferred a Fase 4+)

F4.1 NO incluye (explícitamente deferido):

- **Backend cambios** — `detectar_tipo_vehiculo()` server-side ya shipped (`operacion.py:215-277`, HU-F1.x) + `GET /api/v1/catalogos/tipos-vehiculo` C+Q+U router ya shipped (`catalogos.py:140-147`) + permission `config_catalogo`. F4.1 NO modifica backend.
- **UI componente `<PlacaInput>`** — HU-F6.1 entrega el componente que consume `detectarTipoVehiculo()` + renderiza el error. F4.1 entrega SOLO función pura + hook + i18n key. F6.1 los compone.
- **Selector manual de tipo de vehículo** — corpus categórico (BR2 + DEC-SUC-22). NO `<Select>`/`<RadioGroup>`. F4.1 NO entrega UI override.
- **Tolerancia de tipeo `O↔0`/`I↔1`/`B↔8`** — pertenece a `buscarIngresoTolerante()` Fase 7 (DEC-SUC-22 verbatim). F4.1 entrega función estricta sin tolerancia.
- **Migraciones Alembic** — ninguna tabla nueva ni columna nueva (regex vive en código cliente — A-03 explícito: 4NF canon).
- **`electron-store` fallback persistente** — fallback hardcoded `{auto, moto}`, NO persistente (HU-F4.2 sí usa electron-store). Catálogos reference data.
- **`refreshInterval` periódico** — SWR solo `dedupingInterval` (5min). Catálogos cambian muy raramente.
- **`crypto.randomUUID()` para fallback uuids** — UUIDs sentinels literales (`'00000000-0000-0000-0000-000000000001'` Auto, `'...0002'` Moto), NO generados dinámicamente.
- **Tipos de vehículo adicionales** (`Bicicleta`, `Camión`, `Moto eléctrica`) — A-03 explícito: "no hay respaldo en el corpus de CU para un tercer patrón". Si negocio lo requiere, DEC-F4.1-NN futura.
- **e2e test (Playwright)** — F4.1 es lógica pura. Los 11 unit tests cubren la lógica. e2e testeará `<PlacaInput>` (F6.1) que consume F4.1. Forward coverage.
- **WCAG axe-core scan runtime** — 6 unit + 5 hook tests cubren lógica. axe-core A1 scan es para HU-F6.1 (`<PlacaInput>` visible). F4.1 sienta las bases.
- **i18n plurals** — string único. NO requiere `i18next-resources-types`.
- **Decoradores TypeScript / runtime guards** — función pura. F6.1 Zod usa `REGEX_AUTO` + `REGEX_MOTO` exportadas.
- **Permisos granulares por acción** — backend ya emite 403 si `permisos[]` no incluye `config_catalogo`. F4.1 NO agrega client-side gating (XR6 — backend source of truth).
- **Extensión de `PRE_FLIGHT_PATHS`** — F4.1 NO modifica `parkosFetch.ts`. `/catalogos/*` (GET) son read idempotente (DEC-SUC-03 + F3.2 verbatim).
- **Tabla `tipos_vehiculo` con columna `regex_pattern`** — A-03 explícito: NO columna al ER. Regex vive exclusivamente en cliente + `backend/.../operacion.py:215-277` (sincronizados manualmente vía JSDoc).
- **`useCountdown` o countdown visual** — F4.1 es lógica pura determinista, NO involucra tiempo.
- **AuthGuard component** — F4.1 emite `parkos:auth:cleared` event (forward hook) pero NO crea `<AuthGuard>`.

---

## 6. Dependencies + forward hooks

### 6.1 Shipped prerequisites (F1.x + F2.x + F3.x)

- **HU-F1.x** ✅ Fase 1: `detectar_tipo_vehiculo()` server-side en `operacion.py:215-277` (XR6 layer 4) + `GET /api/v1/catalogos/tipos-vehiculo` en `catalogos.py:140-147` con permission `config_catalogo`.
- **HU-F2.1** ✅ Fase 2: Electron 30 skeleton + shadcn Form/Input/Button + i18n 7 namespaces (`operacion.json` con 10 keys) + axe-core + playwright e2e.
- **HU-F2.2** ✅ Fase 2: `parkosFetch` (retry + refresh-once 401 via Mutex + Idempotency-Key) + bridge IPC + `authStore` Zustand + `useAuth` SWR.
- **HU-F2.3** ✅ Fase 2: kiosko mode + electron-updater + StatusBar + single-instance lock.
- **HU-F3.1** ✅ 2026-09-15: Login page + LoginForm + loginApi + loginSchema + ruta `/login` + 7 REQ-OPS-106..112.
- **HU-F3.2** ✅ 2026-09-15: `useCountdown` + `REFRESH_INTERVAL_MS = 50min` + `PRE_FLIGHT_PATHS` regex + 6 REQ-OPS-113..118.
- **HU-F3.3** ✅ 2026-09-15: Abrir/Cerrar turno + `useSesionActiva()` SWR precedent (key null + deduping + 401 clear + event) + 6 REQ-OPS-119..124.

### 6.2 Forward hooks (Fase 4+ consumer map)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F4.2** (Tarifas) | `useTarifasVigentes` peer hook | F4.2 entrega independientemente; replica pattern de `useTiposVehiculo` con `electronStore` persistente (F4.1 NO usa electron-store) |
| **HU-F4.3** (Ocupación) | `<OcupacionStrip>` itera sobre tipos | `useTiposVehiculo()` provee lista; peer pattern posible |
| **HU-F6.1** (Ingreso CU-01 — **CRÍTICO**) | `<PlacaInput>` consume `detectarTipoVehiculo()` + `useTiposVehiculo()` + i18n key | HU crítica — sin F4.1, F6.1 no puede arrancar. `pending.md §5` forward hook explícito |
| **HU-F7.x** (Salida) | depende F6.x → consume transitivo | F7.x consume para resolver uuid tipo en POST `/operacion/salidas` |
| **HU-F8.x** (Cobro + FE) | depende F7.x → consume transitivo | F8.x consume `uuid_tipo_vehiculo` en `<Factura>` |
| **HU-F11.x** (Sync UI) | si sync incluye `tipos_vehiculo`, hook debe invalidarse | F11.x dispara `mutate()` post-sync via SWR cache invalidation |
| **HU-F6.x+ AuthGuard** | `parkos:auth:cleared` event emitido por 401 path | AuthGuard intercepta → `navigate('/login?next=...')` |
| **HU-F13.x** (Reportería) | `<ReporteOcupacion>` itera sobre tipos | F13.x consume via SWR shared cache |

---

## 7. DoD checklist

- [ ] 6 REQ-OPS-125..130 materializadas en este archivo
- [ ] Given/When/Then/And format RFC 2119 per F3.3 precedent verbatim
- [ ] Anchor links explícitos a `DEC-F4.1-NN` ratificados en `proposal.md §4`
- [ ] Cross-reference table completa (§4.1) — 6 rows con precedent column
- [ ] Acceptance criteria verificables para `sdd-verify` (§4.2) — 7 criterios
- [ ] Forward hooks documentados para F4.2 + F4.3 + F6.1 + F7.x + F8.x + F11.x + F13.x + AuthGuard (§6.2)
- [ ] Out of scope verbatim de `proposal.md §3.2 + §5.2` (§5)
- [ ] NO-OP stub NO aplicado — DELTA con 6 new REQ-OPS confirmado (per `DEC-F4.1-07` + `DEC-F4.1-11`)
- [ ] Numeración monotónica verificada (REQ-OPS-124 vigente post-F3.3; F4.1 ocupa REQ-OPS-125..130)
- [ ] Spanish neutro profesional per F3.3 precedent
- [ ] Author: `Parkos Dev <dev@parkos.local>` (verbatim precedent)
- [ ] No "Co-authored-by" attribution per `AGENTS.md` global rules
- [ ] RFC 2119 MUST/SHOULD/MAY consistentes en las 6 REQ-OPS
- [ ] DEC-SUC-22 honrada — `detectarTipoVehiculo()` NEVER aplica `O↔0`/`I↔1`/`B↔8`
- [ ] A-03 honrada — regex hardcoded en cliente, NO columna ER
- [ ] BR2 CU-01 honrada — UNA función pura, sin override manual

---

## CHANGELOG

- **(2026-09-16)** F4.1 spec delta complete — 6 REQ-OPS-125..130 materializadas en Given/When/Then/And format RFC 2119. DELTA (NOT NO-OP) per critical re-evaluación en `proposal.md §4.7 + §4.11` (DEC-F4.1-07 + DEC-F4.1-11). F4.1 ES user-facing behavior observable: función pura `detectarTipoVehiculo(placa)` con regex estricto hardcoded `^[A-Z]{3}[0-9]{3}$` (Auto) + `^[A-Z]{3}[0-9]{2}[A-Z]$` (Moto) + normalización previa (trim + uppercase + remover whitespace interno) + exports `REGEX_AUTO` + `REGEX_MOTO` (REQ-OPS-125) + i18n key `operacion.placa_formato_invalido` con string literal verbatim "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)" forward F6.1 `<PlacaInput>` `aria-describedby` (REQ-OPS-126) + `useTiposVehiculo()` SWR hook con `dedupingInterval: 5 * 60 * 1000` + `fallbackData: HARDCODED_CATALOG` con `{auto, moto}` UUIDs sentinels literales + `shouldRetryOnError` excl 404 + `onError` con status=401 dispara `useAuthStore.clear()` + `parkos:auth:cleared` event + `isFromFallback` flag para forward UI accesible (REQ-OPS-127) + `tiposVehiculoApi.getTiposVehiculo()` typed wrapper con 404 → `[]` + filtro defensivo `tipo: null` (REQ-OPS-128) + Defense in depth XR6 layer 4 bidireccional cliente (F4.1) + backend ya shipped F1.x `operacion.py:215-277` con "Server overwrites via V5 (regex-derived UUID wins over client value)" operacion.py:261 verbatim (REQ-OPS-129) + WCAG 2.1 AA compliance forward F6.1 — i18n key pre-poblada + detector determinista + `isFromFallback` flag sientan bases para axe-core 0 violaciones forward (REQ-OPS-130). Precedente directo: F3.3 archivado 2026-09-15 con 6 new REQ-OPS-119..124 + F3.2 archivado 2026-09-15 con 6 new REQ-OPS-113..118 + F3.1 archivado 2026-09-15 con 7 new REQ-OPS-106..112 + F1.15 archivado 2026-09-15 con 4 new REQ-OPS-102..105. Numeración monotónica: REQ-OPS-124 vigente post-F3.3 archive; F4.1 ocupa REQ-OPS-125..130 (continuación, 0 gaps). Ready for `sdd-design` (parallel) + `sdd-tasks`.

---

**End of delta spec — HU-F4.1.**
