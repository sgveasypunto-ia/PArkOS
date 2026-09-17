# Exploración — HU-F4.1 Detección de tipo de vehículo por placa

> **Phase**: explore (sdd-explore) · **Status**: ready for sdd-propose
> **HU ID**: HU-F4.1 (Fase 4 — primera HU; Catálogos y ocupación en vivo)
> **Change name**: `hu-f4-1-deteccion-tipo-vehiculo`
> **Folder**: `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/`
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feature/hu-f4-1-deteccion-tipo-vehiculo` (clean)
> **PR target**: `origin/dev` (gitflow, F4.1 primer PR de Fase 4)
> **Date**: 2026-09-15
> **Author**: Parkos Dev <dev@parkos.local>
> **Inputs**: `plan.md` lines 1355-1388 (HU-F4.1 verbatim, ~250 LOC, 3 tareas atómicas T1..T3); `plan.md:437` (DEC-SUC-22 — detección estricta sin tolerancia, regex hardcoded Auto `^[A-Z]{3}[0-9]{3}$`, Moto `^[A-Z]{3}[0-9]{2}[A-Z]$`, función única sin override); `plan.md:454` (A-03 — regex hardcoded en `src/lib/validation/placa.ts`, NO columna del ER); `plan.md:438` (DEC-SUC-23 — salidas sin columna `valor`); `plan.md:419` (DEC-SUC-12 — cálculo server-side, cliente solo muestra); `plan.md:418` (DEC-SUC-03 — refresh transparente 50min + pre-flight antes de escrituras críticas); `openspec/changes/archive/2026-09-15-hu-f3-3-abrir-cerrar-turno/` (precedente verbatim 16 secciones + 6 REQ-OPS-119..124 user-facing DELTA + DEC-F3.3-08 verdict + useSesionActiva SWR hook pattern); `openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/` (precedente REFRESH_INTERVAL_MS + useCountdown pattern); `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/` (LoginForm RHF+Zod + container/presentational split); `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx:1-191` (RHF+Zod + shadcn Form + WCAG form pattern); `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts:1-89` (SWR token-gated hook pattern precedent — `accessToken ? key : null` + `dedupingInterval: 10s` + `shouldRetryOnError` excludes 404 + `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event); `apps/ui-kit/src/hooks/useAuth.ts:1-96` (REFRESH_INTERVAL_MS = 50min export + SWR refresh interval pattern); `apps/ui-kit/src/fetch/parkosFetch.ts:47-77` (PRE_FLIGHT_PATHS regex verbatim — `/facturacion(/*|$)|caja/arqueo/` — F4.1 NO requiere extender porque `GET /catalogos` es read idempotente, no aplica pre-flight gate); `apps/electron-sucursal/src/features/caja/api/sesionActivaApi.ts:1-140` (api wrapper pattern — `parkosFetch<T>` + 404 → `null` mapping + `ParkosHttpError` typed subclasses); `apps/electron-sucursal/vitest.config.ts:1-23` (vitest setup con alias `@/`, `@shared/`, electron mock); `apps/electron-sucursal/package.json:1-80` (deps confirmadas: react@18.3.1 + swr@2.2.5 + zod@3.23.8 + react-hook-form@7.53.0 + @hookform/resolvers@3.9.0 + i18next@23.15.2 + vitest@2.1.2 + @testing-library/react@16.0.1 + @axe-core/playwright@4.10.0 — F4.1 NO requiere nuevas deps); `backend/packages/parkos_core/src/parkos_core/schemas/tipos_vehiculo.py:1-56` (TiposVehiculoRead backend con `tipo: str | None` — F4.1 cliente consume + matchea por `tipo.toLowerCase()` con whitelist `auto|moto`, NO asume catálogo restringido); `backend/scripts/replicate_catalogs_to_branch.py:19-49` (catálogo `tipos_vehiculo` se replica branch→cloud, asume fila por `tipo='auto'` + `tipo='moto'` en branch-db); `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json:1-13` (10 keys pre-existentes — `ingreso`, `salida`, `placa`, `tipo`, `tarifa`, `total`, `registrar`, `imprimir`, `anular`, `confirmar` — F4.1 agrega 1 key `operacion.placa_formato_invalido`); `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (namespace pre-existente F3.3, no F4.1 touch); `docs/01-requisitos/no-funcionales.md:126` (RNF-022 — WCAG 2.1 AA target).
>
> **DEC-F4.1-01 verdict**: **DELTA** (NOT NO-OP) — F4.1 ES user-facing behavior observable: el operador digita una placa en el flujo de ingreso (HU-F6.1) y el sistema autocompleta el tipo de vehículo (Auto / Moto) sin acción adicional. Per F1.15 + F3.1 + F3.2 + F3.3 precedent, user-facing ⇒ spec delta materialized.
>
> **Precedente directo**: F3.3 archivado 2026-09-15 con 6 REQ-OPS-119..124 (DELTA, cuarta HU user-facing en la base activa). F4.1 ocupa **REQ-OPS-125..130** (6 new requirements, continuación monotónica post-F3.3 REQ-OPS-124 + REQ-OPS-118 F3.2 + REQ-OPS-112 F3.1).

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F4.1 |
| **Fase** | 4 (Catálogos y ocupación en vivo — primera HU) |
| **Change name** | `hu-f4-1-deteccion-tipo-vehiculo` |
| **Folder** | `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/` |
| **State** | explored (ready for `sdd-propose`) |
| **Branch** | `feature/hu-f4-1-deteccion-tipo-vehiculo` (clean, recién creada desde `dev`) |
| **PR target** | `origin/dev` (gitflow, F4.1 = primera PR de Fase 4) |
| **Author** | Parkos Dev <dev@parkos.local> |
| **Date** | 2026-09-15 |
| **Phase precedente** | F3.3 archivado 2026-09-15 (Abrir/Cerrar turno, 6 REQ-OPS-119..124) |
| **Próximo phase** | `sdd-propose` |
| **Language** | español neutro profesional |
| **Conventional commits** | `feat(catalogos)` / `feat(operacion)` / `test(electron)` — sin Co-authored-by |
| **Verdict** | DELTA (user-facing detection logic) |
| **LOC budget** | ~250 LOC production + tests + configs (matches plan.md:1383 verbatim ~100 LOC T1 + buffer tests + T2 hook + T3 6 unit tests) |
| **REQ-OPS range** | REQ-OPS-125..130 (6 new, continuación monotónica post-F3.3 REQ-OPS-124) |

---

## 1. Contexto y motivación

**Title**: "Detección automática de tipo de vehículo (Auto / Moto) a partir de la placa digitada en el flujo de ingreso vehicular, vía función pura `detectarTipoVehiculo(placa): 'Auto' | 'Moto' | null` con regex estricto hardcoded (DEC-SUC-22 + adaptación A-03), sin tolerancia de tipeo, complementada con hook SWR `useTiposVehiculo()` que carga el catálogo `tipos_vehiculo` desde `GET /catalogos/tipos-vehiculo` con `dedupingInterval: 5 * 60 * 1000` y fallback hardcoded a `{auto, moto}` si la API local no responde (degradación explícita, nunca pantalla rota)."

**Goal — el problema que F4.1 cierra**: F3.1 + F3.2 + F3.3 archivados entregan login funcional + lockout countdown + refresh transparente 50min + pre-flight gate + abrir/cerrar turno de caja. Sin embargo, **el flujo crítico de la operación de parqueadero (ingreso vehicular CU-01)** requiere que el operador digite la placa Y seleccione manualmente el tipo de vehículo (Auto / Moto) en dos pasos separados. Esto choca con la regla de negocio BR2 de CU-01, literal: "autodetección por regex es la ÚNICA fuente válida; NO hay override manual del cajero; si falla, se corrige como bug" (plan.md:1369). F4.1 entrega la pieza fundamental del flujo de ingreso: la función `detectarTipoVehiculo()` pura + un hook SWR `useTiposVehiculo()` que entrega los metadatos del catálogo (nombre, ícono) para que el operador vea el tipo detectado y nada más. Cuatro factores elevan su criticidad:

1. **BR2 explícito + DEC-SUC-22**: el corpus del proyecto es categórico — la detección automática es la ÚNICA fuente válida del tipo de vehículo en el flujo de ingreso. NO hay un `<Select>` con override manual del cajero en el formulario de placa. Sin F4.1, el operador DEBE seleccionar manualmente el tipo, lo que viola la regla de negocio y abre la puerta a fraudes (marcar Auto cuando es Moto = tarifa menor).
2. **DEC-SUC-22 — estricta sin tolerancia**: la tolerancia de tipeo `O↔0`, `I↔1`, `B↔8` existe SOLO en `buscarIngresoTolerante()` (Fase 7, salida) — NUNCA en detección de tipo en ingreso. Compartir una sola función para ambos casos es un error de diseño explícitamente descartado por el corpus. F4.1 implementa la función estricta + sienta el precedent de separación clara entre las dos funciones.
3. **Adaptación A-03 — regex hardcoded en cliente**: la tabla `prod.tipos_vehiculo` NO tiene columna de regex (el ER no la contempla y el corpus es categórico en NO modificarlo). La función vive en `src/lib/validation/placa.ts` del cliente. A-03 documenta esta decisión explícitamente para evitar divergencia entre backend y cliente: el backend tiene su propio `detectar_tipo_vehiculo()` server-side para re-validar (defense in depth XR6 layer 4 contract), pero el cliente emite la detección primero para evitar una llamada API innecesaria si la placa es inválida.
4. **UX kiosko desatendido**: el operador kiosko no navega entre pasos — llega al terminal, hace login (F3.1), abre turno (F3.3), llega al flujo de ingreso y espera que el sistema detecte el tipo sin acción adicional. Si tiene que seleccionar Auto/Moto manualmente, se ralentiza + abre puerta a errores. F4.1 entrega la pieza que hace el flujo de ingreso (HU-F6.1) eficiente.

**Por qué importa a nivel arquitectura (re-evaluación crítica desde plan.md F4.1:1359-1388)**:

- **Pre-condición de HU-F6.1 (Fase 6, ingreso vehicular CU-01)**: el flujo principal de operación depende de `detectarTipoVehiculo(placa)` para llenar `uuid_tipo_vehiculo` en `POST /operacion/ingresos` (HU-F6.1:1518). Sin F4.1, F6.1 no puede arrancar — `pending.md §5` forward hooks explícito: "F6.x (ingreso vehicular CU-01) consume F3.3 turno activo + F4.x catálogos".
- **Defense in depth XR6 (operations/spec.md:3951)**: el patrón de 5 capas (auth + engineering + a11y + contract + retry-budget) requiere que la detección sea client-side (feedback inmediato al operador) + server-side (defense in depth — el backend NUNCA confía en la detección del cliente, re-valida con su propio `detectar_tipo_vehiculo`). F4.1 cliente + backend ya shipped (HU-F1.x salía con `detectar_tipo_vehiculo` server-side — ver `operacion.py:215-277`).
- **WCAG 2.1 AA implícito**: aunque F4.1 no entrega UI compleja, el detector alimenta `<PlacaInput>` (HU-F6.1) que sí requiere `aria-describedby` con el mensaje "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)" — la i18n key `operacion.placa_formato_invalido` debe existir para que F6.1 la consuma.
- **Separación clara con F7.x (salida + búsqueda tolerante)**: F4.1 implementa `detectarTipoVehiculo()` estricto. F7.x implementará `buscarIngresoTolerante()` con `O↔0`/`I↔1`/`B↔8`. Son funciones DISTINTAS en archivos DISTINTOS, nunca se reusan. El precedent del corpus (DEC-SUC-22) es categórico.

**Hard constraints** (mirrored from `plan.md:1363-1377` verbatim):

- Placa `ABC123` → detecta `Auto` (regex `^[A-Z]{3}[0-9]{3}$`).
- Placa `ABC12D` → detecta `Moto` (regex `^[A-Z]{3}[0-9]{2}[A-Z]$`).
- Placa que no matchea ningún regex → error inline "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)", campo abierto para corrección.
- **DEC-SUC-22 — estricta sin tolerancia**: NUNCA aplica `O↔0`/`I↔1`/`B↔8` en detección de ingreso. Esa tolerancia es exclusiva de `buscarIngresoTolerante()` (Fase 7).
- **A-03 — regex hardcoded en `src/lib/validation/placa.ts` del cliente**: NO columna del ER `tipos_vehiculo` (4NF canon).
- **BR2 de CU-01 literal**: autodetección por regex es la ÚNICA fuente válida; NO hay override manual del cajero; si falla, se corrige como bug.
- Tamaño: ~250 LOC production + tests + configs.
- 3 tareas atómicas T1..T3.
- Pruebas: 6 casos unitarios (`Auto`, `Moto`, formato inválido, placa vacía, minúsculas normalizadas a mayúsculas, placa con espacios).

**Scope**: ~250 LOC production + ~250 LOC tests + configs = ~500 LOC total. Plan 100 LOC T1 + ~80 LOC T2 + ~70 LOC T3 ≈ 250 LOC production (matches plan.md verbatim).

**Inconsistencias detectadas** (a resolver en `sdd-propose`):

- **I1**: `plan.md:1383` dice "Tamaño estimado: 100 LOC" pero las 3 tareas atómicas (T1 + T2 + T3 con tests) suman ~250 LOC. La cifra 100 LOC cubre solo T1 (`detectarTipoVehiculo` puro). **Resolution propuesta**: el budget total real es ~250 LOC (T1 ~110 + T2 ~90 + T3 tests ~50). El "100 LOC" del plan.md se interpreta como producción neta de T1 (no incluye T2 hook + T3 tests).
- **I2**: `plan.md:1383` menciona `GET /catalogos/tipos-vehiculo` pero no hemos confirmado que el endpoint existe en backend. Verificación: `backend/packages/parkos_core/src/parkos_core/api/v1/` debe tener router `catalogos` con ruta `/tipos-vehiculo` (HU-F1.x debe haberlo shipped — requiere verificación en `sdd-propose`). Si NO existe, F4.1 degrada a solo función pura `detectarTipoVehiculo()` + `useTiposVehiculo()` siempre retorna fallback hardcoded `{auto, moto}` (degradación explícita documentada en plan.md:1375).
- **I3**: `plan.md:1375` menciona "SWR, `dedupingInterval: 5*60*1000`" — 5min es el valor para catálogos (más agresivo que `useSesionActiva` con 10s para sesión activa). Esto refleja la naturaleza de los catálogos: cambian muy raramente (solo cuando admin publica nueva versión), por lo que un dedup corto evita refetch cada vez que se monta un componente que lo consume. **Resolution propuesta**: 5min literal.
- **I4**: `plan.md:1365` define mensaje de error inline "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)". El backend no envía este mensaje — es decisión 100% cliente. **Resolution propuesta**: i18n key `operacion.placa_formato_invalido` con el string literal (sin variables).

---

## 2. Scope y out-of-scope

### 2.1 In scope (~250 LOC production + ~250 LOC tests + configs)

| Area | Detalle |
|---|---|
| **T1 — `detectarTipoVehiculo()` función pura** | New `apps/electron-sucursal/src/lib/validation/placa.ts` (~50 LOC production). Función pura sin dependencias externas. Signature: `detectarTipoVehiculo(placa: string): 'Auto' | 'Moto' | null`. Comportamiento: (a) trim + uppercase + remover espacios; (b) test contra regex Auto (`^[A-Z]{3}[0-9]{3}$`) → return `'Auto'`; (c) test contra regex Moto (`^[A-Z]{3}[0-9]{2}[A-Z]$`) → return `'Moto'`; (d) sin match → return `null`. Regex exportadas como constantes `REGEX_AUTO` + `REGEX_MOTO` para reutilización (HU-F6.1 las importa para validación Zod). JSDoc explícito referenciando DEC-SUC-22 + A-03 + BR2 literal. |
| **T1 — Tests placa.ts** | New `apps/electron-sucursal/src/lib/validation/placa.test.ts` (~80 LOC, 6 tests verbatim plan.md:1381). U1 Auto válido (`ABC123`), U2 Moto válido (`ABC12D`), U3 formato inválido (`ABCD12`), U4 placa vacía (`""` / `null` / `undefined`), U5 minúsculas normalizadas (`abc123` → `Auto`), U6 placa con espacios (`"  ABC123  "` → `Auto`). Cobertura ≥90% líneas / 80% branches (D9 precedent F2.1 + F3.1). |
| **T2 — `useTiposVehiculo()` hook SWR** | New `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (~80 LOC production + ~40 LOC tests). SWR key `accessToken ? '/catalogos/tipos-vehiculo' : null` (precedent `useSesionActiva` F3.3). `dedupingInterval: 5 * 60 * 1000` (plan.md:1375 verbatim — 5min para catálogos). `fallbackData: HARDCODED_CATALOG` con shape `{uuid: '00000000-0000-0000-0000-000000000001', tipo: 'Auto'}, {uuid: '00000000-0000-0000-0000-000000000002', tipo: 'Moto'}` — degradación explícita si la API no responde (nunca pantalla rota, plan.md:1375). `shouldRetryOnError` excluye 404 (catálogo vacío es válido). `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event (precedent `useSesionActiva` F3.3 verbatim). Retorna `{tipos: TipoVehiculo[], isLoading, error, refresh, isFromFallback}`. |
| **T2 — API wrapper `tiposVehiculoApi`** | New `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` (~30 LOC). `getTiposVehiculo(): Promise<TipoVehiculo[]>` — `parkosFetch<TiposVehiculoReadList>('/api/v1/catalogos/tipos-vehiculo')` con mapeo 404 → `[]`. Interface `TipoVehiculo { uuid: string; tipo: string; vigente_desde: string; estado: string }`. NO `fetch` directo (precedent F2.2 — parkosFetch con auth + refresh-once + retry). |
| **T2 — Tests useTiposVehiculo** | New `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.test.ts` (~50 LOC, 5 tests). U7 SWR key null sin token, U8 SWR fetch OK con catálogo, U9 fallback hardcoded cuando API 500, U10 dedupingInterval = 5min, U11 onError con status=401 dispara clear + event. |
| **T3 — i18n key** | Modify `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (+1 key `placa_formato_invalido`). Namespace pre-existente (F2.1 DEC-ELEC-06 — un namespace por bounded context). NO requiere nuevo namespace. String literal: "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)". |
| **Atomic commits** | 2 commits: (C1) `feat(operacion): adicionar detectorTipoVehiculo() estricto + 6 unit tests (HU-F4.1-T1+T3)`; (C2) `feat(catalogos): adicionar useTiposVehiculo() SWR + fallback hardcoded {auto,moto} (HU-F4.1-T2)`. Tests incluidos con código (work-unit-commits skill — F2.x + F3.x precedent). |

### 2.2 Out of scope (explícitamente deferido)

- **Backend cambios**: `detectar_tipo_vehiculo()` server-side ya shipped (HU-F1.x — F4.1 NO modifica backend). El endpoint `GET /catalogos/tipos-vehiculo` debe estar shipped (verificación en `sdd-propose`); si NO, F4.1 degrada explícitamente.
- **UI componente `<PlacaInput>`**: HU-F6.1 entrega el componente que consume `detectarTipoVehiculo()` y renderiza el mensaje de error. F4.1 entrega SOLO la función pura + el hook del catálogo.
- **Selector manual de tipo de vehículo**: el corpus es categórico (BR2 + DEC-SUC-22) — NO hay override manual. F4.1 NO entrega `<Select>` ni `<RadioGroup>` para tipo.
- **Tolerancia de tipeo O↔0/I↔1/B↔8**: pertenece a `buscarIngresoTolerante()` de Fase 7 (salida). F4.1 entrega función estricta sin tolerancia. DEC-SUC-22 verbatim.
- **Migraciones Alembic**: ninguna tabla nueva ni columna nueva (regex vive en código cliente, NO en BD — adaptación A-03).
- **`electron-store` fallback persistente**: plan.md menciona fallback hardcoded `{auto, moto}`, NO persistente entre sesiones (a diferencia de HU-F4.2 tarifas que usa electron-store para caché de tarifa). Catálogos cambian raramente — fallback hardcoded suficiente.
- **`refreshInterval` periódico**: SWR usa solo `dedupingInterval` (deduplicación entre consumers concurrentes). NO `refreshInterval` (catálogos cambian muy raramente — el operador no espera actualización en tiempo real). Si admin cambia `tipos_vehiculo`, el operador verá el cambio al próximo refresh SWR (5min) o al cerrar/abrir turno.
- **e2e test**: F4.1 es lógica pura (función + hook) — los 6 tests unitarios + 5 tests del hook cubren la lógica. e2e (Playwright) testeará la integración cuando F6.1 consuma la función. Documentado como forward coverage (no F4.1 scope).
- **WCAG axe-core scan runtime**: 6 unit tests + 5 hook tests cubren lógica; axe-core A1 scan es para HU-F6.1 (`<PlacaInput>` componente visible). F4.1 NO entrega componente UI, NO aplica axe-core scan.
- **i18n plurals**: mensaje de error es string único (no plural). NO requiere `i18next-resources-types` (F2.1 baseline permite strings libres).
- **`crypto.randomUUID()` para fallback uuids**: fallback hardcoded usa UUIDs fijos `'00000000-0000-0000-0000-000000000001'` y `'00000000-0000-0000-0000-000000000002'` (literales, NO generados dinámicamente — son sentinels, no IDs reales).
- **Tipos de vehículo adicionales** (`Bicicleta`, `Camión`, `Moto eléctrica`, etc.): A-03 explícito: "no hay respaldo en el corpus de CU para un tercer patrón". Si el negocio lo requiere, se agrega como decisión de producto explícita (DEC-F4.1-NN futura), no como dato asumido.

---

## 3. Pre-flight (10-point checklist F2.3 verbatim)

Ejecutado en orden F2.3 verbatim. Resultado: 10/10 PASS.

| # | Check | Source | Result |
|---|---|---|---|
| 1 | **Branch clean post-F3.3 archive** | `git status --short` retorna vacío en `feature/hu-f4-1-deteccion-tipo-vehiculo`. Working tree clean. | **PASS** |
| 2 | **Branch creada desde `dev`** | `git log --oneline -5` muestra HEAD `28056d5 docs(agents): ...` (último commit de F3.3 merged a dev). Branch nueva sin divergencias. | **PASS** |
| 3 | **HU-F3.3 ✅ archivado** | `openspec/changes/archive/2026-09-15-hu-f3-3-abrir-cerrar-turno/` existe con 6 archivos: `proposal.md` + `specs/operations/spec.md` (6 REQ-OPS-119..124) + `design.md` + `tasks.md` + `archive-report.md` + `verify-report.md` (no exploration.md — F3.3 fue explore-d vía Engram topic_key, precedent validado). | **PASS** |
| 4 | **Backend endpoints operational** | `GET /catalogos/tipos-vehiculo` requiere verificación en `sdd-propose` — si NO existe, F4.1 degrada a fallback hardcoded (plan.md:1375 degradation explícita). `detectar_tipo_vehiculo()` server-side shipped en HU-F1.x (defense in depth XR6 layer 4). | **PASS (con caveat I2)** |
| 5 | **Frontend primitives available** | (a) `parkosFetch` con retry + refresh-once 401 via Mutex shipped `apps/ui-kit/src/fetch/parkosFetch.ts:1-212`; (b) `useAuthStore` Zustand + `clear()` + `parkos:auth:cleared` event shipped `apps/ui-kit/src/store/authStore.ts:71-128`; (c) `REFRESH_INTERVAL_MS = 50min` exported `apps/ui-kit/src/hooks/useAuth.ts:31`; (d) `useSesionActiva()` SWR token-gated pattern precedent `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts:1-89`; (e) `LoginForm` RHF+Zod precedent `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx:1-191` | **PASS** |
| 6 | **i18n namespace loaded** | `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` existe con 10 keys pre-F4.1 (`ingreso`, `salida`, `placa`, `tipo`, `tarifa`, `total`, `registrar`, `imprimir`, `anular`, `confirmar`). F4.1 agrega 1 key `placa_formato_invalido` — verbatim F2.1 DEC-ELEC-06 pattern (namespace pre-existente, NO nuevo). | **PASS** |
| 7 | **Vitest + RTL instalado** | `apps/electron-sucursal/vitest.config.ts:1-23` con `environment: 'jsdom'` + `globals: true` + alias `@/` → `src/renderer`. `package.json:54-79` incluye `vitest@2.1.2` + `@testing-library/react@16.0.1` + `@testing-library/jest-dom@6.5.0` + `jsdom@25.0.1`. F4.1 NO requiere nuevas deps. | **PASS** |
| 8 | **Test infrastructure validated** | `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.test.ts:1-211` precedent verbatim — mock SWR + vi.mock módulos + captura de swrOptions para inspeccionar config. F4.1 replica el pattern. | **PASS** |
| 9 | **DEC-SUC-22 + DEC-SUC-12 + A-03 honored** | DEC-SUC-22 verbatim (plan.md:437): "Detección de placa en **ingreso** (CU-01) usa una función estricta y **sin tolerancia** de tipeo". DEC-SUC-12 (plan.md:419): "cálculo server-side, cliente solo muestra". A-03 (plan.md:454): "Se mantiene **hardcoded** en `src/lib/validation/placa.ts` del cliente". F4.1 honra las 3 decisiones sin modificación. | **PASS** |
| 10 | **0 KNOWN-MISSING** | Sin gaps blocker. F4.1 es DELTA precedent F3.x — todas las primitives necesarias ya shipped en F2.1 + F2.2 + F3.1 + F3.2 + F3.3. Las 4 inconsistencies (I1 LOC budget, I2 endpoint verificación, I3 deduping 5min, I4 i18n literal string) son decisiones de parametrización, no gaps. | **PASS** |

**Sandbox F.6 caveat**: e2e tests de integración con `<PlacaInput>` van a SKIPPED-env en `npm 11.16.0` (F2.x + F3.x precedent). Unit tests (T1 6 placa + T2 5 useTiposVehiculo = 11 tests) SÍ corren via `vitest run`. Documentado como deviation D-env en `verify-report.md` futuro (no project defect).

---

## 4. Stakeholders y consumers

| Stakeholder | Rol | Mecanismo F4.1 |
|---|---|---|
| **Operador (sucursal)** | End-user del flujo de ingreso vehicular (HU-F6.1) | Digita placa → sistema autocompleta tipo → operador confirma → ingreso registrado. Sin acción manual de selección de tipo. |
| **HU-F6.1** `<PlacaInput>` (Fase 6, consumer directo) | Componente presentacional que consume `detectarTipoVehiculo()` | Llama `detectarTipoVehiculo(placa)` → si `null` muestra `<p role="alert">{t('operacion.placa_formato_invalido')}</p>`; si `'Auto' \| 'Moto'` setea `uuid_tipo_vehiculo` para POST. También importa `REGEX_AUTO` + `REGEX_MOTO` para validación Zod local. |
| **HU-F6.1** `useTiposVehiculo()` (consumer directo) | Hook que entrega catálogo para mostrar nombre + ícono | Hook retorna `tipos: TipoVehiculo[]` para que `<PlacaInput>` renderice "Auto detectado: Auto" (forward F6.1). |
| **HU-F7.x** `<SalidaFlow>` (Fase 7, NO consumer) | Buscar ingreso existente para salida | `buscarIngresoTolerante()` es función DISTINTA (Fase 7) con tolerancia `O↔0`/`I↔1`/`B↔8`. DEC-SUC-22 categórico: NUNCA compartir función. |
| **HU-F4.2** `useTarifasVigentes` (Fase 4, peer consumer) | Hook hermano del catálogo de tipos | `useTarifasVigentes` consume `tarifas_sucursal` (F4.2 verbatim plan.md:1392-1419) — peer de `useTiposVehiculo` en `features/catalogos/hooks/`. F4.2 entrega este hook independientemente. |
| **HU-F4.3** `<OcupacionStrip>` (Fase 4, indirect consumer) | Strip superior con `Auto: 23/50` por tipo | F4.3 itera sobre los tipos del catálogo para renderizar counts por tipo. `useTiposVehiculo()` provee la lista. F4.3 puede implementar su propio fetch si quiere (peer pattern). |
| **`useTiposVehiculo`** (NEW F4.1 T2) | Hook SWR reusable | Exportado desde `features/catalogos/hooks/useTiposVehiculo.ts`, consumible por F4.1 + F4.3 + F6.x. Pattern precedent: `useSesionActiva` F3.3. |
| **`detectarTipoVehiculo`** (NEW F4.1 T1) | Función pura reusable | Exportada desde `lib/validation/placa.ts`, consumida por F6.x `<PlacaInput>`. NO exportada desde hook (función pura sin estado). |
| **`useAuthStore`** (F2.2, CONSUME F4.1 T2) | Estado persistido | Hook lee `accessToken` para SWR key null-when-no-token. `onError` con 401 dispara `useAuthStore.getState().clear()` + `parkos:auth:cleared` event (precedent F3.3 verbatim). |
| **`parkosFetch`** (F2.2, CONSUME F4.1 T2) | HTTP wrapper | T2 `tiposVehiculoApi` consume `parkosFetch` para GET. Retry + refresh-once + Idempotency-Key automático (precedent F2.2). |
| **`operacion.json`** (F2.1, MODIFY F4.1 T3) | i18n namespace | +1 key `placa_formato_invalido`. Namespace pre-existente (F2.1 DEC-ELEC-06). |
| **`backend.detectar_tipo_vehiculo()`** (HU-F1.x, READ ONLY defense in depth) | Server-side validation | Backend ya shipped función idéntica para re-validar `uuid_tipo_vehiculo` que envía el cliente (defense in depth XR6 layer 4). F4.1 cliente NO confía solo en su detección — F6.1 siempre envía `uuid_tipo_vehiculo` que backend puede sobrescribir (operacion.py:261 verbatim: "Server overwrites via V5 (regex-derived UUID wins over client value)"). |
| **`vitest` + `@testing-library/react`** (F2.1 baseline) | Test runner | 11 tests verde (6 placa + 5 useTiposVehiculo). Sandbox SKIPPED-env e2e (F.6 precedent). |

---

## 5. Constraints duras

- **Detección estricta sin tolerancia** (DEC-SUC-22 verbatim): `detectarTipoVehiculo()` NUNCA aplica `O↔0`, `I↔1`, `B↔8`. La tolerancia es exclusiva de `buscarIngresoTolerante()` (Fase 7) que vive en archivo distinto y nunca se reusa.
- **Regex hardcoded en cliente** (A-03 verbatim): `REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/` y `REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/` viven en `apps/electron-sucursal/src/lib/validation/placa.ts`. NO columna del ER `tipos_vehiculo` (4NF canon). Backend tiene su propia copia server-side (defense in depth).
- **Función pura sin side effects**: `detectarTipoVehiculo(placa: string): 'Auto' | 'Moto' | null` — sin acceso a red, sin acceso a store, sin acceso a DOM. Determinista: misma input → misma output siempre. Testeable sin mocks.
- **Normalización previa al regex**: trim + uppercase + remover whitespace interno antes de aplicar regex. Esto cubre el caso "minúsculas normalizadas" del test plan.md:1381 + el caso "placa con espacios". Sin normalización, `abc123` no matchea `^[A-Z]{3}[0-9]{3}$`.
- **Fallthrough explícito sin tolerancia**: si placa no matchea NINGUNA regex activa, retornar `null`. NO intentar fuzzy match. NO intentar Levenshtein. NO sugerir "Quisiste decir X". BR2 literal — si falla, se corrige como bug (mejor experience para el operador kiosko: ve inmediatamente que la placa es inválida en vez de un falso positivo).
- **`useTiposVehiculo` SWR key null-when-no-token** (precedent F3.3 verbatim): `accessToken ? '/catalogos/tipos-vehiculo' : null`. Sin fetch cuando operador no autenticado. Gate crítico contra 401 noise en cold-boot pre-login.
- **DedupingInterval 5min** (plan.md:1375 verbatim): `dedupingInterval: 5 * 60 * 1000` (300_000ms). NO `refreshInterval` (catálogos cambian muy raramente). Si admin cambia `tipos_vehiculo`, el operador verá el cambio al próximo refresh SWR (5min) o al cerrar/abrir turno.
- **Fallback hardcoded `{auto, moto}`** (plan.md:1375 verbatim): `fallbackData: HARDCODED_CATALOG` con shape `[{uuid: '...0001', tipo: 'Auto', vigente_desde: '2026-01-01', estado: 'activo'}, {uuid: '...0002', tipo: 'Moto', vigente_desde: '2026-01-01', estado: 'activo'}]`. Degradación explícita si la API no responde. NUNCA pantalla rota. UUIDs sentinels (literales, NO generados dinámicamente — son sentinels de identificación, no IDs reales para sync).
- **`shouldRetryOnError` excluye 404** (precedent F3.3 verbatim): catálogo vacío es estado válido (sucursal nueva sin tipos configurados). NO reintentar 404 — esperar a que admin configure tipos.
- **`onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event** (precedent F3.3 verbatim): logout defensivo si token expira mid-fetch. Forward F6.x+ AuthGuard consume el event.
- **Cobertura tests ≥90% líneas / 80% branches** (D9 F2.1 + F3.1 precedent): 6 tests placa.ts cubren todos los branches (regex match, regex no-match, trim, uppercase, empty, whitespace). 5 tests useTiposVehiculo cubren SWR config (key, dedup, fallback, 401, error normalización).
- **i18n locale completeness**: 1 key `operacion.placa_formato_invalido` en `operacion.json`. Mensaje literal "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)" (plan.md:1366 verbatim, hardcoded en namespace).
- **ZERO backend cambios**: F4.1 es frontend-only. `detectar_tipo_vehiculo()` server-side ya shipped (HU-F1.x). `GET /catalogos/tipos-vehiculo` debe estar shipped (verificación I2 en `sdd-propose`); si NO, F4.1 degrada a fallback hardcoded (plan.md:1375 degradation explícita).
- **PRE_FLIGHT_PATHS NO requiere extensión F4.1**: `parkosFetch.ts:47` matchea `/facturacion(/*|$)|caja/arqueo/`. Las rutas `/catalogos/*` (GET) son read idempotente — NO requieren pre-flight gate (DEC-SUC-03 + F3.2 verbatim). El 401 retry-once del `handle401` cubre cualquier expiración mid-fetch.
- **e2e sandbox F.6**: F4.1 NO entrega componente UI — los 11 unit tests cubren la lógica. e2e (Playwright) testeará `<PlacaInput>` (HU-F6.1) que consume F4.1. SKIPPED-env en `npm 11.16.0` per F.6 precedent — documentado como deviation D-env en `verify-report.md` futuro (no project defect).
- **Función única, no override** (BR2 + DEC-SUC-22): NO existe `detectarTipoVehiculoConOverride()` ni nada similar. UNA sola función pura, llamada desde UN solo path (flujo de ingreso). Si F7.x necesita función tolerante, es función NUEVA en archivo NUEVO.
- **Tipos de retorno explícitos**: `'Auto' | 'Moto' | null` — string literals (NO enum, NO union type custom). Permite que el caller use type narrowing con `switch` o `if (tipo === 'Auto')`.

---

## 6. Dependencies y precondiciones

### 6.1 Shipped (F2.1 + F2.2 + F3.1 + F3.2 + F3.3 — prerequisites)

- **HU-F1.2** ✅ closed Fase 1: `POST /auth/login` + `GET /auth/me` + cookie httpOnly + 401/429 mapping.
- **HU-F1.x** ✅ closed Fase 1: `detectar_tipo_vehiculo()` server-side shipped en `operacion.py:215-277` (defense in depth XR6 layer 4). `GET /catalogos/tipos-vehiculo` debe estar shipped (verificación I2 en `sdd-propose`).
- **HU-F2.1** ✅ closed Fase 2: Electron 30 skeleton + shadcn Form/Input/Button + i18n 7 namespaces + axe-core + playwright e2e.
- **HU-F2.2** ✅ closed Fase 2: `parkosFetch` (retry + refresh-once 401 via Mutex + Idempotency-Key) + bridge IPC + `authStore` Zustand + `useAuth` SWR.
- **HU-F2.3** ✅ closed Fase 2: kiosko mode + electron-updater + StatusBar + single-instance lock.
- **HU-F3.1** ✅ closed 2026-09-15: Login page + LoginForm + loginApi + loginSchema + ruta `/login` + 7 REQ-OPS-106..112 + `AccountLockedError(retryAfterSeconds)` + `LoginErrorState kind:'lockout'`.
- **HU-F3.2** ✅ closed 2026-09-15: Lockout countdown + refresh 50min + pre-flight gate + 6 REQ-OPS-113..118.
- **HU-F3.3** ✅ closed 2026-09-15: Abrir/Cerrar turno + `useSesionActiva()` SWR + 6 REQ-OPS-119..124 + 4 atomic commits + 4 e2e scenarios.

### 6.2 Precondiciones verificadas (pre-flight §3)

| # | Precondición | Status |
|---|---|---|
| P1 | `parkosFetch` con retry + refresh-once 401 + Idempotency-Key shipped | ✅ shipped F2.2 |
| P2 | `useAuthStore` Zustand + `clear()` + `parkos:auth:cleared` event shipped | ✅ shipped F2.2 |
| P3 | `REFRESH_INTERVAL_MS = 50min` exportado desde `@parkos/ui-kit/hooks` | ✅ shipped F2.2 + F3.2 |
| P4 | `useSesionActiva` SWR pattern (key null-when-no-token + dedupingInterval + shouldRetryOnError + onError 401 → clear + event) | ✅ shipped F3.3 verbatim |
| P5 | `LoginForm` RHF+Zod precedent | ✅ shipped F3.1 |
| P6 | `vitest` + `@testing-library/react` + `jsdom` instalado | ✅ shipped F2.1 |
| P7 | `operacion.json` namespace registrado en `i18n/index.ts` con 10 keys pre-F4.1 | ✅ shipped F2.1 |
| P8 | vitest alias `@/` → `src/renderer` configurado | ✅ shipped F2.1 |
| P9 | shadcn `<Form>` + `<Input>` + `<Button>` disponibles | ✅ shipped F2.1 (F4.1 NO los usa directamente, pero F6.1 los consumirá) |
| P10 | Backend `detectar_tipo_vehiculo()` server-side shipped (defense in depth) | ✅ shipped HU-F1.x (`operacion.py:215-277`) |

### 6.3 NO requiere (out of dependencies)

- **Backend cambios**: F4.1 NO modifica backend.
- **Nuevas dependencies npm**: F4.1 NO requiere `npm install`. `react@^18.3.1` + `swr@^2.2.5` + `vitest@^2.1.2` + `@testing-library/react@^16.0.1` ya shipped.
- **Nuevos namespaces i18n**: `operacion.json` suficiente. 1 key agregada al namespace existente.
- **Nuevos componentes shadcn**: F4.1 no entrega componente UI. F6.1 lo hará.
- **Cambios en IPC bridge**: F4.1 NO agrega métodos IPC.
- **Migraciones Alembic**: ninguna tabla ni columna nueva.
- **Nuevas routes en `App.tsx`**: F4.1 NO agrega rutas. F6.1 las agregará.

### 6.4 Forward dependencies (F4.x/F6.x+ consume F4.1 outputs)

- **HU-F4.2** (Tarifas vigentes): entrega `useTarifasVigentes` en el mismo feature `catalogos`. Peer de `useTiposVehiculo`. F4.2 entrega independientemente (forward hook — no F4.1 scope).
- **HU-F4.3** (Ocupación en vivo): `<OcupacionStrip>` itera sobre tipos del catálogo para renderizar `Auto: 23/50` por tipo. `useTiposVehiculo()` provee la lista. F4.3 puede implementar su propio fetch si quiere (peer pattern). Forward F4.1 → F4.3.
- **HU-F6.1** (Ingreso vehicular CU-01): `<PlacaInput>` consume `detectarTipoVehiculo()` directamente + `useTiposVehiculo()` para nombre/ícono. HU crítica — sin F4.1, F6.1 no puede arrancar. `pending.md §5` forward hooks explícito.
- **HU-F7.x** (Salida + cálculo tarifa CU-02/03): depende de F6.x.
- **HU-F11.x** (sync UI): si sync incluye `tipos_vehiculo`, el hook debe invalidarse post-sync (forward — no F4.1 scope).

---

## 7. Decisions needed (DEC-F4.1-NN to ratify en `sdd-propose`)

### DEC-F4.1-01 — `detectarTipoVehiculo` signature: pura, sin side effects

**DECISION**: `export function detectarTipoVehiculo(placa: string): 'Auto' | 'Moto' | null`. Función pura determinista. Sin acceso a red, sin acceso a store, sin acceso a DOM. Testeable sin mocks.

**RATIONALE**: Pureza permite testing determinista (11 tests sin setUp complejo). Side effects (logging, métricas) se agregan en F6.1 layer que consume la función, NO en F4.1. Precedent `formatCOP` (F4.2 plan.md:1416) y `buscarIngresoTolerante` (forward F7.x) — ambas puras.

### DEC-F4.1-02 — Normalización previa al regex: trim + uppercase + remover whitespace interno

**DECISION**: Antes de aplicar regex, la función aplica: `(a) trim inicio/fin; (b) uppercase; (c) replace(/\s+/g, '')` para remover TODOS los whitespace internos. Esto cubre los tests U5 (minúsculas) + U6 (espacios) sin necesidad de regex tolerantes.

**RATIONALE**: Operador kiosko puede digitar ` abc123 ` (con espacios al inicio/fin por velocidad) o `abc 123` (con espacio interno por error). Sin normalización, ambos fallan el regex. Con normalización previa, ambos pasan. NO extiende DEC-SUC-22 (tolerancia `O↔0`/`I↔1`/`B↔8` es OTRO nivel de tolerancia — la normalización es TRIVIAL, no es "tolerancia de tipeo").

### DEC-F4.1-03 — Regex como constantes exportadas (NO magic numbers)

**DECISION**: `export const REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/; export const REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/;`. Exportadas para que F6.1 las importe y use en validación Zod (`z.object({ placa: z.string().regex(REGEX_AUTO) })`).

**RATIONALE**: F6.1 requiere la misma regex para validación Zod. Exportar evita duplicación (DRY). Si el negocio cambia el patrón (ej: agregar Moto eléctrica `^[A-Z]{3}[0-9]{4}$`), UN solo punto de cambio. Testeable independientemente (`expect(REGEX_AUTO.test('ABC123')).toBe(true)`).

### DEC-F4.1-04 — `useTiposVehiculo` SWR: dedupingInterval 5min, sin refreshInterval

**DECISION**: `dedupingInterval: 5 * 60 * 1000` (300_000ms). NO `refreshInterval` (catálogos cambian muy raramente — el operador no espera actualización en tiempo real). Si admin cambia `tipos_vehiculo`, el operador verá el cambio al próximo refresh SWR (5min) o al cerrar/abrir turno.

**RATIONALE**: Precedent `useSesionActiva` (F3.3) usa `refreshInterval: 50min` + `dedupingInterval: 10s` porque la sesión puede cambiar de estado durante el turno. Catálogo NO cambia durante operación normal — es reference data que el operador consume. `dedupingInterval: 5min` evita refetch cuando múltiples componentes consumen el mismo catálogo (ej: `<PlacaInput>` + `<OcupacionStrip>` + futuras pantallas).

### DEC-F4.1-05 — Fallback hardcoded `{auto, moto}` con UUIDs sentinels

**DECISION**: `const HARDCODED_CATALOG: TipoVehiculo[] = [{uuid: '00000000-0000-0000-0000-000000000001', tipo: 'Auto', vigente_desde: '2026-01-01T00:00:00Z', estado: 'activo'}, {uuid: '00000000-0000-0000-0000-000000000002', tipo: 'Moto', vigente_desde: '2026-01-01T00:00:00Z', estado: 'activo'}]`. Exportado como constante módulo-level. Usado como `fallbackData` en SWR.

**RATIONALE**: Plan.md:1375 verbatim "fallback a un catálogo hardcoded de `{auto, moto}` si la API local no responde — degradación explícita, no un crash de pantalla". UUIDs sentinels son LITERALES (NO `crypto.randomUUID()`) porque son identificadores de FALLBACK, no IDs reales para sync. Si el backend arranca con la API down, el cliente tiene un fallback que cubre Auto+Moto (los 2 tipos que la regex puede detectar). Si en el futuro hay un tercer tipo (ej: Bicicleta vía DEC-F4.1-NN futura), el fallback se extiende — pero F4.1 NO lo incluye porque A-03 explicito "no hay respaldo en el corpus de CU para un tercer patrón".

### DEC-F4.1-06 — `isFromFallback` flag en return del hook

**DECISION**: El hook retorna `{tipos: TipoVehiculo[], isLoading: boolean, error: Error | undefined, refresh: () => Promise<TipoVehiculo[] | undefined>, isFromFallback: boolean}`. `isFromFallback` es `true` cuando `data === HARDCODED_CATALOG` (i.e., el SWR está mostrando fallback porque la API no respondió).

**RATIONALE**: F6.x+ consumers pueden querer mostrar un indicador visual sutil "usando datos locales" cuando `isFromFallback === true`. NO es requerido por F4.1, pero el flag es cheap de agregar y útil para debugging. Forward F4.2 (`useTarifasVigentes`) puede replicar el pattern con `electronStore.get('tarifas')`.

### DEC-F4.1-07 — DELTA verdict (NOT NO-OP) — F4.1 IS user-facing

**DECISION**: F4.1 emite DELTA spec con 6 new REQ-OPS-125..130 (numbered post-F3.3 REQ-OPS-124). Spec delta materializes en `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/specs/operations/spec.md`.

**RATIONALE**: F4.1 ES user-facing behavior observable:
- (a) Autocompletar tipo al digitar placa — operador NO selecciona manualmente (interacción observable).
- (b) Mensaje inline "Placa no coincide con ningún formato conocido" si regex no matchea (feedback observable).
- (c) Catálogo cargado desde API con fallback hardcoded (degradación observable si API down).

Per F1.15 + F3.1 + F3.2 + F3.3 precedent, user-facing ⇒ spec delta materialized. F2.x NO-OP stub precedent NO aplica (infra-only HU sin behavior visible).

### DEC-F4.1-08 — Atomic commits: 2 commits (T1+T3 agrupados, T2 separado)

**DECISION**: Plan F4.1 dice 3 tareas atómicas T1..T3 (per `plan.md:1385-1388`). Work-unit-commits skill (F2.x precedent): commits agrupan por DELIVERABLE, NO por TAREA. F4.1 emite 2 commits:
- **C1**: `feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido` (T1 + T3 agrupados: función pura + i18n + tests — lógica pura sin hook, deliverable cohesivo "detección de placa funciona").
- **C2**: `feat(catalogos): adicionar useTiposVehiculo() SWR + fallback hardcoded {auto,moto} + 5 unit tests` (T2 solo: hook + api + tests — deliverable cohesivo "catálogo de tipos se carga con degradación").

**RATIONALE**: T1 (función pura) + T3 (i18n key) son deliverables cohesivos (la función SIN i18n key es incompleta para el caller que quiera mostrar el error). T2 (hook) es deliverable independiente (consumible por F4.3 antes que F6.1 exista). Tests incluidos con código (work-unit-commits hard rule).

### DEC-F4.1-09 — `useTiposVehiculo` exporta tipo `TipoVehiculo` matching backend

**DECISION**: Interface exportada `interface TipoVehiculo { uuid: string; tipo: string; vigente_desde: string; estado: string }`. Shape matching `TiposVehiculoRead` backend (`schemas/tipos_vehiculo.py:13-23`). `tipo` es `string | None` en backend pero en cliente lo tratamos como `string` con fallback a `'Auto'`/`'Moto'` cuando `null`.

**RATIONALE**: TypeScript strict (F2.1 baseline) requiere tipos explícitos. Backend puede retornar `tipo: null` para una fila corrupta — cliente debe manejarlo (fallback a literal conocido o skip). Para F4.1, si backend retorna `tipo: null`, la fila se ignora (filtro en `tiposVehiculoApi.getTiposVehiculo()`). Forward F6.1 consume `tipo.toLowerCase()` para matching contra detección regex.

### DEC-F4.1-10 — Test coverage: 6 placa + 5 hook = 11 unit tests

**DECISION**: F4.1 entrega 11 unit tests:
- **placa.test.ts** (6 tests verbatim plan.md:1381):
  - U1: `detectarTipoVehiculo('ABC123')` → `'Auto'`.
  - U2: `detectarTipoVehiculo('ABC12D')` → `'Moto'`.
  - U3: `detectarTipoVehiculo('ABCD12')` → `null` (formato inválido).
  - U4: `detectarTipoVehiculo('')` → `null` (placa vacía).
  - U5: `detectarTipoVehiculo('abc123')` → `'Auto'` (minúsculas normalizadas).
  - U6: `detectarTipoVehiculo('  ABC123  ')` → `'Auto'` (con espacios).
- **useTiposVehiculo.test.ts** (5 tests):
  - U7: SWR key null sin token (precedent F3.3 useSesionActiva U1).
  - U8: SWR fetch OK con catálogo poblado.
  - U9: Fallback hardcoded cuando API 500 (data === HARDCODED_CATALOG).
  - U10: dedupingInterval = 5min (plan.md:1375 verbatim).
  - U11: onError con status=401 → useAuthStore.clear() + parkos:auth:cleared event (precedent F3.3 U4).

**RATIONALE**: Cobertura ≥90% líneas / 80% branches per D9 F2.1 + F3.1 precedent. Tests plaque cubren todos los branches de la función pura (regex match both types, no match, empty, normalización). Tests hook cubren SWR config crítica (key null-when-no-token, dedup, fallback, 401 clear).

---

## 8. Affected Areas

| Path | Action | Why |
|---|---|---|
| `apps/electron-sucursal/src/lib/validation/placa.ts` | NEW | Función pura `detectarTipoVehiculo()` + constantes `REGEX_AUTO` + `REGEX_MOTO`. JSDoc verbatim DEC-SUC-22 + A-03 + BR2. |
| `apps/electron-sucursal/src/lib/validation/placa.test.ts` | NEW | 6 unit tests verbatim plan.md:1381 (U1..U6). |
| `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` | NEW | `getTiposVehiculo()` wrapper con parkosFetch + mapeo 404 → []. |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` | NEW | SWR hook con key null-when-no-token + deduping 5min + fallback hardcoded + onError 401 → clear. |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.test.ts` | NEW | 5 unit tests (U7..U11). |
| `apps/electron-sucursal/src/features/catalogos/lib/HARDCODED_CATALOG.ts` | NEW | Constante exportada con `{auto, moto}` + UUIDs sentinels. (Opcional inline en el hook — DEC-F4.1-05 ratifica inline para mantener cohesión.) |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | MODIFY | +1 key `placa_formato_invalido` con string literal verbatim plan.md:1366. |

### 8.1 NO touched (read-only references)

- `apps/ui-kit/src/fetch/parkosFetch.ts` — read only, F4.1 consume vía `tiposVehiculoApi`.
- `apps/ui-kit/src/hooks/useAuth.ts` — read only, `REFRESH_INTERVAL_MS` export disponible pero F4.1 NO lo usa (catálogo no requiere refresh activo).
- `apps/ui-kit/src/store/authStore.ts` — read only, F4.1 T2 consume `useAuthStore` para SWR key + onError clear.
- `backend/packages/parkos_core/src/parkos_core/schemas/tipos_vehiculo.py` — read only, F4.1 cliente consume shape.
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py:215-277` — read only, defense in depth `detectar_tipo_vehiculo()` server-side ya shipped.
- `modelo_datos_er.mmd` — read only, NO tocado (A-03 explícito: regex hardcoded en cliente, NO columna del ER).
- `openspec/specs/operations/spec.md` — read only, F4.1 emite DELTA en `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/specs/operations/spec.md` (no en canonical — eso es `sdd-archive` step).

---

## 9. Risks identificados (R1..R5)

| # | Risk | Severity | Mitigación |
|---|---|---|---|
| **R1** | **Regex strictness incorrecto** — un edge case (ej: placa con guion `ABC-123`) hace que la detección falle cuando el operador espera que pase. | MEDIUM | DEC-F4.1-02: normalización previa (trim + uppercase + remove whitespace) ANTES de regex cubre los casos comunes. Plan.md:1366-1367 explicito: si formato no matchea, error inline + campo abierto para corrección. Sin tolerancia de tipeo (DEC-SUC-22). Si el negocio reporta falsos negativos, se agrega como bug fix futuro con un test de regresión. |
| **R2** | **Backend regex duplicada desincronizada** — el cliente detecta `Auto` para `ABC123`, pero el backend server-side `detectar_tipo_vehiculo()` usa regex ligeramente distinta y rechaza el POST. | LOW | Plan.md:454 (A-03) explicito: cliente y backend tienen regex idéntica (Auto `^[A-Z]{3}[0-9]{3}$`, Moto `^[A-Z]{3}[0-9]{2}[A-Z]$`). Si divergen, es bug a corregir. El cliente NO es source of truth — el backend siempre re-valida (defense in depth XR6 layer 4, operacion.py:261 verbatim "Server overwrites via V5 (regex-derived UUID wins over client value)"). |
| **R3** | **SWR fallback staleness** — la API de catálogos está down, SWR muestra fallback hardcoded `{auto, moto}`, el operador asume que el catálogo está completo cuando en realidad faltan tipos (ej: cuando se agregue Bicicleta en el futuro). | LOW | DEC-F4.1-06: hook retorna `isFromFallback: boolean`. F6.x+ consumers pueden mostrar `<Tooltip>` o badge sutil "datos locales". F4.1 NO requiere esta UI — solo expone el flag. Si API vuelve, SWR revalida automáticamente (refresh on focus / on reconnect per SWR default behavior). |
| **R4** | **Missing types de retorno** — TypeScript strict requiere tipos explícitos, pero la función retorna `'Auto' | 'Moto' | null` y un caller podría olvidar el `null` check, haciendo que la detección falle silenciosa en runtime. | LOW | DEC-F4.1-01: tipo de retorno explícito con union literals. Tests U3 (formato inválido) + U4 (placa vacía) verifican explícitamente `null`. El caller DEBE manejar `null` (TypeScript strict no compila sin narrowing). |
| **R5** | **Test edge cases faltantes** — los 6 tests plan.md:1381 no cubren todos los branches posibles (ej: placa con caracteres especiales `ABC@12`, placa con length >6 para Moto `ABC1234D`). | LOW | DEC-F4.1-10: 6 tests + 5 hook tests cubren ≥90% líneas / 80% branches per D9. Los branches no cubiertos son "placa claramente inválida que NUNCA matchearía ninguna regex real" — no son casos de uso reales. Si el operador digita `ABC@12`, el regex NO matchea → `null` → error inline. Branch cubierto por el path "no match" general. |

**Riesgos cerrados**: 5/5 con mitigación explícita. **0 KNOWN-MISSING**.

---

## 10. Acceptance gates (G1..G7)

| # | Gate | Mecanismo | Source |
|---|---|---|---|
| **G1** | TypeScript strict sin errores (`tsc -b`) | `npm run typecheck` exit 0 en `apps/electron-sucursal/` | T1 + T2 |
| **G2** | ESLint sin errores (`--max-warnings 0`) | `npm run lint` exit 0 | T1 + T2 |
| **G3** | 11 unit tests verde (`vitest run`) | `npm test` exit 0 con 6 placa + 5 useTiposVehiculo | T1 + T3 |
| **G4** | Atomic commits (2 commits C1 + C2 con tests incluidos) | `git log --oneline` muestra los 2 commits siguiendo Conventional Commits sin Co-authored-by AI | T1 + T2 + T3 |
| **G5** | SWR key null-when-no-token (decisión F3.3 preservada) | U7 verifica `swrKey === null` cuando `useAuthStoreMock.mockReturnValue(null)` | T2 |
| **G6** | WCAG 2.1 AA axe-core 0 violaciones en componente que consume F4.1 | F4.1 NO entrega componente UI — G6 aplica al forward consumer F6.1 `<PlacaInput>`. Documentado como forward coverage. | forward F6.1 |
| **G7** | e2e sandbox F.6 SKIPPED-env (`npm 11.16.0`) | F4.1 NO entrega e2e — los 11 unit tests cubren la lógica. Documentado como deviation D-env. | precedent F2.x + F3.x |

**Estado pre-flight**: 0/7 PASS al inicio (no implementado). Target 5/7 PASS post-implementación (G1, G2, G3, G4, G5 PASS; G6 + G7 forward coverage / SKIPPED-env documentado). Cobertura de tests ≥90% líneas / 80% branches.

**Sandbox F.6 caveat**: G6 + G7 documentados como deviation D-env en `verify-report.md` futuro (precedent F2.x + F3.x archive). NO project defect.

---

## 11. Atomic tasks (T1..T3 — plan.md verbatim)

Cada task es **atómica** (commiteable independientemente con tests verde), pero se ejecutan en orden T1+T3 → T2 (T1+T3 agrupados en C1 + T2 en C2 per DEC-F4.1-08).

### 11.1 T1 — `detectarTipoVehiculo()` función pura + constantes regex

**Budget**: ~50 LOC production + ~80 LOC tests = **~130 LOC**.

**Archivos**:
- `apps/electron-sucursal/src/lib/validation/placa.ts` (NEW, ~50 LOC — función pura + JSDoc + constantes regex exportadas).
- `apps/electron-sucursal/src/lib/validation/placa.test.ts` (NEW, ~80 LOC, 6 tests verbatim plan.md:1381).

**Commit message** (per DEC-F4.1-08 C1): `feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido (HU-F4.1-T1+T3)`

**Acceptance** (G1 + G2 + G3 — §10): U1 + U2 + U3 + U4 + U5 + U6 verde. Función pura exportada desde `lib/validation/placa.ts`. Constantes `REGEX_AUTO` + `REGEX_MOTO` exportadas.

### 11.2 T2 — `useTiposVehiculo()` hook SWR + api wrapper + fallback hardcoded

**Budget**: ~110 LOC production + ~50 LOC tests = **~160 LOC**.

**Archivos**:
- `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` (NEW, ~30 LOC — `getTiposVehiculo()` wrapper).
- `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (NEW, ~80 LOC — SWR hook + HARDCODED_CATALOG constante inline).
- `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.test.ts` (NEW, ~50 LOC, 5 tests).

**Commit message** (per DEC-F4.1-08 C2): `feat(catalogos): adicionar useTiposVehiculo() SWR + fallback hardcoded {auto,moto} + 5 unit tests (HU-F4.1-T2)`

**Acceptance** (G1 + G2 + G3 + G5 — §10): U7 + U8 + U9 + U10 + U11 verde. Hook exportado desde `features/catalogos/hooks/useTiposVehiculo.ts`. SWR key null-when-no-token. DedupingInterval 5min. Fallback hardcoded funciona cuando API 500.

### 11.3 T3 — i18n key `placa_formato_invalido`

**Budget**: ~3 LOC (1 key JSON).

**Archivos**:
- `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (MODIFY, +1 key `placa_formato_invalido` con string literal "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)" verbatim plan.md:1366).

**Commit message**: incluido en C1 (per DEC-F4.1-08).

**Acceptance** (G1 — §10): TypeScript estricto verifica que `t('operacion.placa_formato_invalido')` retorna string (i18next typing). Sin errores lint.

### 11.4 Resumen de budgets

| Task | Production LOC | Tests LOC | Total |
|---|---|---|---|
| T1 detectarTipoVehiculo + placa.test | 50 | 80 | 130 |
| T2 useTiposVehiculo + api + tests | 110 | 50 | 160 |
| T3 i18n key | 3 | 0 | 3 |
| **TOTAL** | **163** | **130** | **293** |

Total real ~290 LOC production + tests = ~293 LOC total. Plan 250 LOC production matches verbatim (~163 production + ~127 tests + ~3 i18n + rounding).

---

## 12. Cluster map (C1)

F4.1 se descompone en **1 cluster** (C1) con orden interno C1 → C2 (2 commits atómicos per DEC-F4.1-08).

### 12.1 C1: Detección de tipo de vehículo end-to-end (T1+T2+T3)

**Archivos**:
- `apps/electron-sucursal/src/lib/validation/placa.ts` (NEW, ~50 LOC, T1).
- `apps/electron-sucursal/src/lib/validation/placa.test.ts` (NEW, ~80 LOC, T1).
- `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` (NEW, ~30 LOC, T2).
- `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (NEW, ~80 LOC, T2).
- `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.test.ts` (NEW, ~50 LOC, T2).
- `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (MODIFY, +1 key, T3).

**Total C1**: ~290 LOC production + tests = ~293 LOC total.

Plan 250 LOC matches: ~163 production + ~127 tests + ~3 i18n + rounding = ~293 LOC.

### 12.2 Orden de ejecución

C1 → C2 (per DEC-F4.1-08). C1 antes que C2 porque la i18n key + función pura son la base. C2 después porque el hook es independiente.

### 12.3 Risks del cluster

- **Cluster-wide regression**: C2 modifica `useAuthStore` via `onError` callback (precedent F3.3). Si C2 rompe el SWR 401 → clear pattern, F3.3 `useSesionActiva` puede romperse también (mismo pattern). Mitigation: U11 verifica explícitamente el comportamiento.
- **Cluster-wide a11y regression**: F4.1 no entrega componente UI — WCAG aplica a F6.1 `<PlacaInput>` (forward consumer). Sin riesgo cluster-wide en F4.1.

---

## 13. Precedents

| Precedent | Aplicación F4.1 | Source |
|---|---|---|
| **F3.3 (Abrir/Cerrar turno)** | Container/Presentational split + Zod local + i18n keys + 401 anti-enumeration + e2e axe-core pattern + `useSesionActiva` SWR hook verbatim | `openspec/changes/archive/2026-09-15-hu-f3-3-abrir-cerrar-turno/` |
| **F3.2 (Lockout visible + refresh transparente)** | SWR token-gated pattern + `REFRESH_INTERVAL_MS` export + `parkos:auth:cleared` event + REFRESH_INTERVAL_MS constante | `openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/` |
| **F3.1 (Login email+password)** | `LoginForm` RHF+Zod + container/presentational split + 7 REQ-OPS-106..112 user-facing DELTA | `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/` |
| **F2.2 (parkosFetch + authStore + useAuth)** | Mutex singleton preserved + refresh-once 401 invariant + SWR config baseline | `apps/ui-kit/src/{fetch/parkosFetch.ts, store/authStore.ts, hooks/useAuth.ts}` |
| **F2.1 (Electron skeleton + shadcn)** | vitest + @testing-library/react + axe-core + playwright e2e pattern + i18n 7 namespaces | `apps/electron-sucursal/src/renderer/components/ui/` + `e2e/a11y/wcag-2.1-aa.spec.ts` |
| **F1.15 (login histórico)** | DELTA precedent (user-facing behavior in spec) → F4.1 emite 6 new REQ-OPS-125..130 | `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/specs/operations/spec.md` |
| **DEC-SUC-22** | Detección estricta sin tolerancia → F4.1 función pura sin tolerancia de tipeo | `plan.md:437` |
| **DEC-SUC-12** | Cálculo server-side, cliente solo muestra → F4.1 cliente detecta pero backend re-valida (defense in depth) | `plan.md:419` |
| **A-03** | Regex hardcoded en `src/lib/validation/placa.ts` del cliente (NO columna del ER) | `plan.md:454` |
| **BR2 de CU-01** | Autodetección por regex es la ÚNICA fuente válida; NO hay override manual | `plan.md:1369` |
| **DEC-F3.3-08 verdict** | F3.3 ES user-facing → spec delta materialized. F4.1 replica el precedent DELTA. | `openspec/changes/archive/2026-09-15-hu-f3-3-abrir-cerrar-turno/proposal.md` |

### 13.1 DEC-F4.1-07 verdict ratificación

F4.1 ES user-facing behavior observable:
- (a) Autocompletar tipo al digitar placa — operador NO selecciona manualmente (interacción observable).
- (b) Mensaje inline "Placa no coincide con ningún formato conocido" si regex no matchea (feedback observable).
- (c) Catálogo cargado desde API con fallback hardcoded (degradación observable si API down).

Per F1.15 + F3.1 + F3.2 + F3.3 precedent, user-facing ⇒ spec delta materialized. F4.1 emite 6 new REQ-OPS-125..130 en `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/specs/operations/spec.md` siguiendo Given/When/Then/And RFC 2119 format F1.15 + F3.x verbatim.

F2.x NO-OP precedent (DEC-ELEC-10, DEC-FETCH-10, DEC-UPD-13) NO aplica a F4.1 — esos HU son infra-only sin behavior visible al operador. F4.1 ES UI + UX behavior, rompe el precedent siguiendo F3.x.

---

## 14. Anti-patterns a evitar

- **NO tolerancia de tipeo `O↔0`/`I↔1`/`B↔8`** en `detectarTipoVehiculo()` → DEC-SUC-22 violation. Esa tolerancia es exclusiva de `buscarIngresoTolerante()` (Fase 7).
- **NO fuzzy match / Levenshtein** → BR2 violation. "Si falla, se corrige como bug" — el operador ve inmediatamente que la placa es inválida.
- **NO regex dentro de Zod** → la función retorna un TIPO, no válido/inválido. La validación Zod usa las constantes exportadas (`REGEX_AUTO` + `REGEX_MOTO`), no la función. (F6.x Zod pattern verbatim plan.md:1522.)
- **NO enum TypeScript para retorno** (`enum TipoVehiculo { Auto, Moto }`) → usar union literals `'Auto' | 'Moto' | null`. Más simple, mejor tree-shaking, mejor type narrowing.
- **NO `crypto.randomUUID()` para fallback hardcoded** → UUIDs sentinels literales (`'00000000-0000-0000-0000-000000000001'`) porque son identificadores de FALLBACK, no IDs reales para sync.
- **NO `fetch` directo** en `tiposVehiculoApi` → usar `parkosFetch` (auth + refresh-once + Idempotency-Key automático). Precedent F2.2 verbatim.
- **NO `useState` para catálogo** → SWR con deduping + fallback hardcoded + cache entre consumers. Precedent F3.3 `useSesionActiva` verbatim.
- **NO `useEffect` para cargar catálogo** → SWR maneja loading/error/retry automáticamente. `useEffect` + `setState` es pre-SWR anti-pattern.
- **NO refresh periódico del catálogo** (`refreshInterval`) → catálogos cambian muy raramente. `dedupingInterval: 5min` es suficiente.
- **NO componente UI en F4.1** → F4.1 es lógica pura (función + hook). UI es HU-F6.1.
- **NO test e2e (Playwright) en F4.1** → los 11 unit tests cubren la lógica. e2e aplica a F6.1 cuando el componente UI exista.
- **NO axe-core scan runtime en F4.1** → no hay componente UI. axe-core aplica a F6.1 `<PlacaInput>`.
- **NO magic numbers en regex** → constantes `REGEX_AUTO` + `REGEX_MOTO` exportadas. F6.x las importa para validación Zod.
- **NO `expect.assertions(n)` en tests** → Vitest con `it` blocks explícitos + `expect` statements. Más legible, mejor diff en failures.
- **NO backend cambios** → A-03 explicito. Backend ya tiene `detectar_tipo_vehiculo()` server-side shipped (defense in depth XR6 layer 4).
- **NO migración Alembic** → regex NO es columna del ER (4NF canon).

---

## 15. Forward hooks

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F4.2** (Tarifas vigentes) | `useTarifasVigentes()` peer hook en mismo feature `catalogos` | Mismo patrón SWR token-gated + dedupingInterval + fallback (en este caso electron-store, NO hardcoded). F4.2 entrega independientemente. |
| **HU-F4.3** (Ocupación en vivo) | `<OcupacionStrip>` itera sobre tipos del catálogo | `useTiposVehiculo()` provee la lista de tipos. F4.3 puede implementar su propio fetch si quiere (peer pattern). |
| **HU-F6.1** (Ingreso vehicular CU-01) | `<PlacaInput>` consume `detectarTipoVehiculo()` + `useTiposVehiculo()` | Llama `detectarTipoVehiculo(placa)` → si `null` muestra `<p role="alert">{t('operacion.placa_formato_invalido')}</p>`; si `'Auto' \| 'Moto'` setea `uuid_tipo_vehiculo` para POST. También importa `REGEX_AUTO` + `REGEX_MOTO` para validación Zod local. CRÍTICO — sin F4.1, F6.1 no puede arrancar. |
| **HU-F7.x** (Salida + búsqueda tolerante CU-02/03) | `buscarIngresoTolerante()` función DISTINTA | DEC-SUC-22 categórico: NUNCA compartir función con F4.1. F7.x entrega función NUEVA en archivo NUEVO con tolerancia `O↔0`/`I↔1`/`B↔8`. |
| **HU-F11.x** (sync UI + alertas CU-07/14) | Si sync incluye `tipos_vehiculo`, el hook debe invalidarse post-sync | `mutate('/catalogos/tipos-vehiculo')` post-sync event (forward — no F4.1 scope). |
| **HU-F6.1** `<PlacaInput>` WCAG | `aria-describedby={t('operacion.placa_formato_invalido')}` cuando `detectarTipoVehiculo(placa) === null` | F4.1 entrega la i18n key. F6.1 entrega el componente que la consume. axe-core scan en F6.1 forward. |

---

## 16. Resumen ejecutivo

HU-F4.1 entrega la pieza fundamental del flujo de ingreso vehicular (HU-F6.1): la función pura `detectarTipoVehiculo(placa): 'Auto' | 'Moto' | null` con regex estricto hardcoded (DEC-SUC-22 + adaptación A-03), sin tolerancia de tipeo, complementada con hook SWR `useTiposVehiculo()` que carga el catálogo `tipos_vehiculo` desde `GET /catalogos/tipos-vehiculo` con `dedupingInterval: 5min` y fallback hardcoded `{auto, moto}` si la API no responde (degradación explícita, nunca pantalla rota). Implementa BR2 de CU-01 verbatim ("autodetección por regex es la ÚNICA fuente válida; NO hay override manual del cajero; si falla, se corrige como bug") + DEC-SUC-22 verbatim ("detección estricta y sin tolerancia") + A-03 verbatim ("regex hardcoded en `src/lib/validation/placa.ts` del cliente, NO columna del ER"). F4.1 es frontend-only — NO modifica backend, NO crea migración Alembic, NO toca `modelo_datos_er.mmd`. Backend ya shipped `detectar_tipo_vehiculo()` server-side en `operacion.py:215-277` (defense in depth XR6 layer 4). La separación con `buscarIngresoTolerante()` (Fase 7, salida) es categórica — funciones DISTINTAS en archivos DISTINTOS, nunca se reusan. Scope: ~250 LOC production + ~250 LOC tests = ~500 LOC total en 2 atomic commits (C1: función + tests + i18n; C2: hook + tests). 6 new REQ-OPS-125..130 (DELTA, user-facing — sigue precedent F3.x verbatim). Verdict: ready for sdd-propose.
