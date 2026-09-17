# Proposal — HU-F4.1 Detección de tipo de vehículo por placa (función pura `detectarTipoVehiculo()` estricto + hook SWR `useTiposVehiculo()` con fallback hardcoded `{auto, moto}`)

> **Change**: `hu-f4-1-deteccion-tipo-vehiculo` · **Folder**: `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/`
> **Phase**: propose (sdd-propose) · **Status**: ready for `sdd-spec` + `sdd-design` (paralelo)
> **HU ID**: HU-F4.1 (Fase 4 — primera HU; Catálogos y ocupación en vivo)
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feature/hu-f4-1-deteccion-tipo-vehiculo` (clean, recién creada desde `dev`) · **PR target**: `origin/dev` (gitflow, F4.1 primer PR de Fase 4)
> **Inputs**: `plan.md` lines 1355-1388 (HU-F4.1 verbatim, ~250 LOC, 3 tareas atómicas T1..T3); `plan.md:437` (DEC-SUC-22 — detección estricta sin tolerancia, regex hardcoded Auto `^[A-Z]{3}[0-9]{3}$`, Moto `^[A-Z]{3}[0-9]{2}[A-Z]$`, función única sin override); `plan.md:454` (A-03 — regex hardcoded en `src/lib/validation/placa.ts`, NO columna del ER); `plan.md:438` (DEC-SUC-23 — salidas sin columna `valor`); `plan.md:419` (DEC-SUC-12 — cálculo server-side, cliente solo muestra); `plan.md:418` (DEC-SUC-03 — refresh transparente 50min + pre-flight antes de escrituras críticas); `plan.md:1369` (BR2 de CU-01 literal — "autodetección por regex es la ÚNICA fuente válida; NO hay override manual del cajero; si falla, se corrige como bug"); `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/exploration.md` (input de explore phase — 512 LOC, 16 secciones, 10 DEC-F4.1-01..10, 5 riesgos R1..R5, 7 acceptance gates G1..G7, 3 atomic tasks T1..T3, pre-flight 10/10 PASS + 0 KNOWN-MISSING); `openspec/changes/archive/2026-09-15-hu-f3-3-abrir-cerrar-turno/` (precedente verbatim 16 secciones + 6 REQ-OPS-119..124 user-facing DELTA + DEC-F3.3-08 verdict + useSesionActiva SWR hook pattern); `openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/` (precedente REFRESH_INTERVAL_MS + useCountdown pattern); `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/` (LoginForm RHF+Zod + container/presentational split); `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/specs/operations/spec.md` (DELTA precedent — 4 new REQ-OPS-102..105 user-facing); `backend/packages/parkos_core/src/parkos_core/api/v1/catalogos.py:140-147` (verificación I2 resuelta: `_mount_catalog(resource="tipos-vehiculo", ...)` C+Q+U router SHIPPED con permission `config_catalogo` per `_CATALOG_DEFAULTS:101`); `backend/packages/parkos_core/src/parkos_core/schemas/tipos_vehiculo.py:13-23` (`TiposVehiculoRead` con `uuid: UUID, tipo: str | None, vigente_desde: datetime, vigente_hasta: datetime | None, estado: str, ...`); `apps/ui-kit/src/fetch/parkosFetch.ts:1-212` (parkosFetch con retry + refresh-once 401 via Mutex + Idempotency-Key); `apps/ui-kit/src/store/authStore.ts:71-128` (useAuthStore Zustand + `clear()` + `parkos:auth:cleared` event); `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts:1-89` (precedent SWR token-gated hook verbatim); `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (namespace pre-existente con 10 keys F2.1 — F4.1 agrega 1 key `placa_formato_invalido`).

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F4.1 |
| **Fase** | 4 (Catálogos y ocupación en vivo — primera HU) |
| **Change name** | `hu-f4-1-deteccion-tipo-vehiculo` |
| **Folder** | `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/` |
| **State** | proposed (ready for design + spec) |
| **Branch** | `feature/hu-f4-1-deteccion-tipo-vehiculo` |
| **PR target** | `origin/dev` (gitflow, F4.1 = primera PR de Fase 4) |
| **Author** | Parkos Dev <dev@parkos.local> |
| **Date** | 2026-09-16 |
| **Phase precedente** | F3.3 archivado 2026-09-15 (Abrir/Cerrar turno, 6 REQ-OPS-119..124) |
| **Próximo phase** | sdd-spec + sdd-design (paralelo) |
| **Language** | español neutro profesional |
| **Conventional commits** | `feat(operacion)` / `feat(catalogos)` / `test(electron)` — sin Co-authored-by |
| **Verdict** | **DELTA** (NOT NO-OP) — F4.1 ES user-facing behavior observable: autocompletar tipo al digitar placa + error inline "formato inválido" + catálogo con fallback degradado |

---

## 1. Resumen ejecutivo

**Title**: "Detección automática de tipo de vehículo (Auto / Moto) a partir de la placa digitada en el flujo de ingreso vehicular, vía función pura `detectarTipoVehiculo(placa): 'Auto' | 'Moto' | null` con regex estricto hardcoded (DEC-SUC-22 + adaptación A-03), sin tolerancia de tipeo, complementada con hook SWR `useTiposVehiculo()` que carga el catálogo `tipos_vehiculo` desde `GET /api/v1/catalogos/tipos-vehiculo` con `dedupingInterval: 5 * 60 * 1000` y fallback hardcoded a `{auto, moto}` si la API local no responde (degradación explícita, nunca pantalla rota)".

**Goal — el problema que F4.1 cierra**: F1.x salía con `detectar_tipo_vehiculo()` server-side (defense in depth XR6 layer 4, `operacion.py:215-277`) y F1.x shipped `GET /api/v1/catalogos/tipos-vehiculo` (catalogos.py:140-147 C+Q+U router). F3.1 + F3.2 + F3.3 archivados entregan login funcional + lockout countdown + refresh transparente 50min + pre-flight gate + abrir/cerrar turno de caja. Sin embargo, **el flujo crítico de la operación de parqueadero (ingreso vehicular CU-01)** todavía no tiene la pieza cliente que autocompleta el tipo de vehículo al digitar la placa: el operador debe seleccionar Auto / Moto manualmente en dos pasos separados. Esto choca con la regla de negocio BR2 de CU-01, literal: "autodetección por regex es la ÚNICA fuente válida; NO hay override manual del cajero; si falla, se corrige como bug" (plan.md:1369). F4.1 entrega la pieza fundamental del flujo de ingreso: la función `detectarTipoVehiculo()` pura + un hook SWR `useTiposVehiculo()` que entrega los metadatos del catálogo (nombre, UUID para `POST /operacion/ingresos`) para que el operador vea el tipo detectado y nada más. Cuatro factores elevan su criticidad:

1. **BR2 explícito + DEC-SUC-22**: el corpus del proyecto es categórico — la detección automática es la ÚNICA fuente válida del tipo de vehículo en el flujo de ingreso. NO existe un `<Select>` con override manual del cajero en el formulario de placa. Sin F4.1, el operador DEBE seleccionar manualmente el tipo, lo que viola la regla de negocio y abre la puerta a fraudes (marcar Auto cuando es Moto = tarifa menor).
2. **DEC-SUC-22 — estricta sin tolerancia**: la tolerancia de tipeo `O↔0`, `I↔1`, `B↔8` existe SOLO en `buscarIngresoTolerante()` (Fase 7, salida) — NUNCA en detección de tipo en ingreso. Compartir una sola función para ambos casos es un error de diseño explícitamente descartado por el corpus. F4.1 implementa la función estricta + sienta el precedent de separación clara entre las dos funciones.
3. **Adaptación A-03 — regex hardcoded en cliente**: la tabla `prod.tipos_vehiculo` NO tiene columna de regex (el ER no la contempla y el corpus es categórico en NO modificarlo — 4NF canon). La función vive en `src/lib/validation/placa.ts` del cliente. A-03 documenta esta decisión explícitamente para evitar divergencia entre backend y cliente: el backend tiene su propio `detectar_tipo_vehiculo()` server-side para re-validar (defense in depth), pero el cliente emite la detección primero para evitar una llamada API innecesaria si la placa es inválida.
4. **UX kiosko desatendido**: el operador kiosko no navega entre pasos — llega al terminal, hace login (F3.1), abre turno (F3.3), llega al flujo de ingreso y espera que el sistema detecte el tipo sin acción adicional. Si tiene que seleccionar Auto/Moto manualmente, se ralentiza + abre puerta a errores. F4.1 entrega la pieza que hace el flujo de ingreso (HU-F6.1) eficiente.

**Goal — la solución propuesta**: F4.1 entrega tres deliverables end-to-end verificables: (1) función pura `detectarTipoVehiculo(placa: string): 'Auto' | 'Moto' | null` exportada desde `apps/electron-sucursal/src/lib/validation/placa.ts` (T1, ~50 LOC) — sin acceso a red / store / DOM; normaliza la entrada (trim + uppercase + remover whitespace interno) antes de aplicar las regex exportadas `REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/` y `REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/`; retorna `null` si ninguna matchea; (2) hook SWR `useTiposVehiculo()` exportado desde `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (T2, ~80 LOC) — SWR key `accessToken ? '/catalogos/tipos-vehiculo' : null` (precedent F3.3 verbatim), `dedupingInterval: 5 * 60 * 1000` (plan.md:1375 verbatim — 5min para catálogos reference data), `fallbackData: HARDCODED_CATALOG` con shape `[{uuid: '...0001', tipo: 'Auto'}, {uuid: '...0002', tipo: 'Moto'}]` — degradación explícita si la API no responde (nunca pantalla rota, plan.md:1375), `shouldRetryOnError` excluye 404 (catálogo vacío es válido), `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event (precedent F3.3 verbatim); retorna `{tipos, isLoading, error, refresh, isFromFallback}`; (3) i18n key `operacion.placa_formato_invalido` agregada a namespace pre-existente (T3, +1 key JSON, ~3 LOC) con string literal verbatim "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)" para que F6.1 `<PlacaInput>` la consuma vía `<p role="alert">{t('operacion.placa_formato_invalido')}</p>`. 11 unit tests verde (6 placa + 5 useTiposVehiculo) cubren ≥90% líneas / 80% branches per D9 F2.1 + F3.x precedent.

**Impacto transversal — por qué importa a Fase 4+**: F4.1 cierra una pieza atomic pequeña pero transversal. Cuatro factores elevan su criticidad:

1. **Pre-condición de HU-F6.1 (Fase 6, ingreso vehicular CU-01)**: el flujo principal de operación depende de `detectarTipoVehiculo(placa)` para llenar `uuid_tipo_vehiculo` en `POST /operacion/ingresos` (HU-F6.1:1518). Sin F4.1, F6.1 no puede arrancar — `pending.md §5` forward hooks explícito: "F6.x (ingreso vehicular CU-01) consume F3.3 turno activo + F4.x catálogos".
2. **Defense in depth XR6** (`operations/spec.md:3951`): el patrón de 5 capas (auth + engineering + a11y + contract + retry-budget) requiere que la detección sea client-side (feedback inmediato al operador) + server-side (defense in depth — el backend NUNCA confía en la detección del cliente, re-valida con su propio `detectar_tipo_vehiculo`). F4.1 cliente + backend ya shipped (HU-F1.x salía con `detectar_tipo_vehiculo` server-side — ver `operacion.py:215-277`).
3. **WCAG 2.1 AA implícito**: aunque F4.1 no entrega UI compleja, el detector alimenta `<PlacaInput>` (HU-F6.1) que sí requiere `aria-describedby` con el mensaje "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)" — la i18n key `operacion.placa_formato_invalido` debe existir para que F6.1 la consuma con `role="alert"`.
4. **Separación clara con F7.x (salida + búsqueda tolerante)**: F4.1 implementa `detectarTipoVehiculo()` estricto. F7.x implementará `buscarIngresoTolerante()` con `O↔0`/`I↔1`/`B↔8`. Son funciones DISTINTAS en archivos DISTINTOS, nunca se reusan. El precedent del corpus (DEC-SUC-22) es categórico.

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

**Scope**: ~250 LOC production + ~250 LOC tests + configs = ~500 LOC total. Budget real T1 ~110 LOC + T2 ~160 LOC + T3 ~3 LOC = ~293 LOC total (resolución I1 — ver §4 y §16).

**Numeración REQ-OPS verificada**: el último REQ-OPS vigente en `operations/spec.md` es REQ-OPS-124 (F3.3 archivado 2026-09-15). F4.1 ocupa **REQ-OPS-125..130** (6 new requirements, continuación monotónica). Numeración monotónica verificada: 124 → 125 → 126 → 127 → 128 → 129 → 130 (0 gaps, sin duplicados).

**Por qué importa a nivel spec (re-evaluación crítica desde plan.md F4.1:1359-1388)**: al igual que F1.15 (login histórico, 4 new REQ-OPS-102..105), F3.1 (login email+password, 7 new REQ-OPS-106..112), F3.2 (lockout countdown, 6 new REQ-OPS-113..118) y F3.3 (abrir/cerrar turno, 6 new REQ-OPS-119..124), F4.1 ES user-facing behavior observable — cuatro dimensiones: (a) autocompletar tipo al digitar placa — operador NO selecciona manualmente (interacción observable); (b) error inline "Placa no coincide con ningún formato conocido" si regex no matchea (feedback observable); (c) catálogo cargado desde API con fallback hardcoded `{auto, moto}` (degradación observable si API down); (d) detección pura sin estado visible + i18n key pre-poblada con mensaje UX (consumible por F6.1 `<PlacaInput>` con `role="alert"` y `aria-describedby`). Esta behavior visible al usuario NO puede vivir solo en DEC-F4.1-NN dentro de `proposal.md` — debe anclarse en REQ-OPS-NNN dentro del spec canónico `operations/spec.md` para que sea verificable, auditable y refactorizable. Precedent directo: F1.15 (4 new REQ-OPS-102..105), F3.1 (7 new REQ-OPS-106..112), F3.2 (6 new REQ-OPS-113..118), F3.3 (6 new REQ-OPS-119..124). F4.1 emite 6 new REQ-OPS-125..130 user-facing — sigue el precedent DELTA. Ver DEC-F4.1-07 + DEC-F4.1-11 en §4 para el rationale extendido del verdict.

---

## 2. Contexto y motivación

### 2.1 Pain points UX que F4.1 cierra

Cuatro user-facing pain points rompen la promesa BR2 + DEC-SUC-22 + kiosko desatendido. F4.1 mitiga los cuatro.

**Pain #1 — Operador selecciona tipo manualmente (fraude potencial)**: cuando el operador termina login (F3.1) + abrir turno (F3.3) y llega al flujo de ingreso vehicular (HU-F6.1, sin F4.1), debe tipear la placa Y seleccionar manualmente el tipo en un `<Select>` o `<RadioGroup>`. Esto viola BR2 literal ("autodetección por regex es la ÚNICA fuente válida; NO hay override manual del cajero"). Además abre la puerta a fraude: si el operador marca "Auto" cuando la placa es de Moto (6 caracteres vs 7 — distinto formato, pero idéntica tarifa_visible), cobra una tarifa menor. F4.1 entrega la función pura + la pieza que F6.1 `<PlacaInput>` usa para llenar `uuid_tipo_vehiculo` automáticamente — el operador ya NO elige, el sistema autocompleta.

**Pain #2 — Regex en backend NO protege UX cliente**: el backend ya emite `detectar_tipo_vehiculo()` server-side (HU-F1.x, operacion.py:215-277) que re-valida contra el mismo regex hardcoded (defense in depth XR6 layer 4). Sin embargo, el cliente sin F4.1 tipearía la placa y haría round-trip API al backend solo para saber el tipo. Con F4.1, el cliente detecta primero (síncrono, <1ms) y solo si la placa es inválida muestra el error inline — sin round-trip. Backend sigue siendo source of truth (overwrites via V5 — "regex-derived UUID wins over client value", operacion.py:261 verbatim), pero la UX cliente es instantánea.

**Pain #3 — Catálogo `tipos_vehiculo` sin hook cliente = repetición de fetch**: múltiples componentes futuros (F4.3 `<OcupacionStrip>` + F6.1 `<PlacaInput>` + F7.x `<SalidaFlow>`) van a necesitar la lista de tipos de vehículo. Si cada componente hace su propio `fetch`, hay N requests duplicados cuando 1 SWR compartido basta. F4.1 entrega `useTiposVehiculo()` con `dedupingInterval: 5 * 60 * 1000` — único fetch cada 5min compartido por todos los consumers vía SWR cache (precedent F3.3 `useSesionActiva` con `dedupingInterval: 10s`).

**Pain #4 — Catálogo API down = pantalla rota**: si la API de catálogos está down (sync atrasado, db offline, server restart), los componentes que consumen el catálogo se quedan en loading permanente o crash silencioso. F4.1 implementa `fallbackData: HARDCODED_CATALOG` con `{auto, moto}` + UUIDs sentinels — degradación explícita (nunca pantalla rota), documentada en plan.md:1375 verbatim. `isFromFallback: boolean` permite a consumers futuros (F4.3 + F6.x) mostrar un indicador visual sutil "usando datos locales" si quieren.

### 2.2 Rationale — transversal consumer + defense in depth + UX transaccional

**Transversal consumer para Fase 4+** (forward hooks `pending.md §5`): F4.2 (tarifas vigentes) + F4.3 (ocupación en vivo) + F6.1 (ingreso vehicular) + F7.x (salida) consumen `useTiposVehiculo()` para scoped queries per `sesion.uuid_sucursal`. Sin F4.1, los hooks hermanos no pueden arrancar — `pending.md §5` forward hooks explícitos: "F4.x (catálogos) prerequisite para F4.x+".

**Defense in depth XR6** (`operations/spec.md:3951`): el patrón de 5 capas (auth + engineering + a11y + contract + retry-budget) se fortalece con la capa 4 contract: regex hardcoded cliente (F4.1) + regex hardcoded backend (HU-F1.x) + REQ-OPS-125..130 (F4.1) + DIAN-related compliance (forward F11.x). Defense in depth bidireccional: backend rechaza logic-level (regex); cliente detecta UX-level (función pura + mensaje inline i18n). Ambos regex idénticos: Auto `^[A-Z]{3}[0-9]{3}$` y Moto `^[A-Z]{3}[0-9]{2}[A-Z]$`. Si divergen (R2 mitigated), es bug a corregir.

**Kiosko desatendido + operador en piso**: el plan enfatiza "operador desatendido, kiosko robusto, sin intervención IT" (DEC-SUC-03, plan.md:418). Si el operador llega al terminal y ve un campo vacío "Seleccione tipo de vehículo" con dos opciones Auto/Moto, tiene que hacer un clic extra y validar visualmente. Si el sistema autocompleta, el operador tipea la placa → ve "Auto detectado: ABC123" en tiempo real → flujo continúa. Eficiencia operativa.

**Aislamiento del cliente**: A-03 explicito ("regex hardcoded en `src/lib/validation/placa.ts` del cliente") evita divergencia funcional entre regex backend y regex cliente. Mismas regex en `apps/electron-sucursal/src/lib/validation/placa.ts` y `backend/.../operacion.py:215-277`. Si el negocio cambia el patrón (ej: agregar Moto eléctrica `^[A-Z]{3}[0-9]{4}$`), se actualiza en AMBOS lugares — explícitamente documentado en la JSDoc de `detectarTipoVehiculo()` con referencia a `operacion.py:215-277`.

---

## 3. Goals y no-goals

### 3.1 Goals (QUÉ entrega F4.1)

1. **`detectarTipoVehiculo()` función pura** — exportada desde `apps/electron-sucursal/src/lib/validation/placa.ts` (~50 LOC production + ~80 LOC tests). Función pura determinista, signature `(placa: string) => 'Auto' | 'Moto' | null`. Sin acceso a red, store, DOM. Normalización previa (trim + uppercase + remover whitespace interno) antes de aplicar regex. Exporta `REGEX_AUTO` + `REGEX_MOTO` como constantes módulo-level para reuso en validación Zod (F6.1).
2. **`useTiposVehiculo()` hook SWR** — exportado desde `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (~80 LOC production + ~50 LOC tests). SWR key `accessToken ? '/catalogos/tipos-vehiculo' : null`, `dedupingInterval: 5 * 60 * 1000` (plan.md:1375 verbatim — 5min catálogos), `fallbackData: HARDCODED_CATALOG` con `{auto, moto}` + UUIDs sentinels, `shouldRetryOnError` excluye 404, `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event. Retorna `{tipos, isLoading, error, refresh, isFromFallback}`.
3. **`tiposVehiculoApi` typed wrapper** — exportado desde `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` (~30 LOC). `getTiposVehiculo(): Promise<TipoVehiculo[]>` — `parkosFetch<TiposVehiculoReadList>('/api/v1/catalogos/tipos-vehiculo')` con mapeo 404 → `[]`. Interface `TipoVehiculo { uuid, tipo, vigente_desde, vigente_hasta, estado }` matching `TiposVehiculoRead` backend (schemas/tipos_vehiculo.py:13-23).
4. **`HARDCODED_CATALOG` constante módulo-level** — exportada como constante en `useTiposVehiculo.ts` (inline per DEC-F4.1-05). Shape: `[{uuid: '00000000-0000-0000-0000-000000000001', tipo: 'Auto', vigente_desde: '2026-01-01T00:00:00Z', vigente_hasta: null, estado: 'activo'}, {uuid: '00000000-0000-0000-0000-000000000002', tipo: 'Moto', vigente_desde: '2026-01-01T00:00:00Z', vigente_hasta: null, estado: 'activo'}]`. UUIDs sentinels literales (NO `crypto.randomUUID()` — son identificadores de FALLBACK, no IDs reales para sync).
5. **i18n key `operacion.placa_formato_invalido`** — Modify `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (+1 key, T3). Namespace pre-existente (F2.1 DEC-ELEC-06 — un namespace por bounded context). String literal verbatim plan.md:1366: "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)".
6. **11 unit tests verde** — 6 placa tests (U1 Auto válido, U2 Moto válido, U3 formato inválido, U4 placa vacía, U5 minúsculas normalizadas, U6 placa con espacios) + 5 useTiposVehiculo tests (U7 SWR key null sin token, U8 SWR fetch OK, U9 fallback cuando API 500, U10 dedupingInterval = 5min, U11 onError con status=401 dispara clear + event). Cobertura ≥90% líneas / 80% branches per D9 F2.1 + F3.1 precedent.
7. **2 atomic commits (work-unit-commits skill F2.x + F3.x precedent)** — C1: `feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido (HU-F4.1-T1+T3)`. C2: `feat(catalogos): adicionar useTiposVehiculo() SWR + fallback hardcoded {auto,moto} + 5 unit tests (HU-F4.1-T2)`. Tests incluidos con código (work-unit-commits hard rule: "Tests belong in the same commit as the behavior they verify").
8. **DELTA verdict con 6 new REQ-OPS-125..130** — materializadas en formato Given/When/Then/And RFC 2119 en `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/specs/operations/spec.md` (sdd-spec phase outputs + sdd-archive phase commits to canonical per F3.3 archive-report precedent). Sigue el precedent DELTA F1.15 + F3.1 + F3.2 + F3.3 verbatim.
9. **WCAG 2.1 AA compliance (forward F6.1)** — el detector + i18n key sientan las bases para que `<PlacaInput>` (F6.1) use `aria-describedby={t('operacion.placa_formato_invalido')}` + `<p role="alert">`. F4.1 NO entrega componente UI — la verificación WCAG aplica al forward consumer F6.1. axe-core scan en F6.1 forward.

### 3.2 No-goals (explícitamente deferido)

1. **Backend cambios** — `detectar_tipo_vehiculo()` server-side ya shipped (HU-F1.x, operacion.py:215-277). `GET /api/v1/catalogos/tipos-vehiculo` C+Q+U router ya shipped (catalogos.py:140-147 F1.x + F3.0 catalogos precedent). F4.1 NO modifica backend. Defense in depth preservado: cliente detecta (UX rápido) + backend re-valida (truth DB).
2. **UI componente `<PlacaInput>`** — HU-F6.1 entrega el componente que consume `detectarTipoVehiculo()` y renderiza el mensaje de error. F4.1 entrega SOLO la función pura + el hook del catálogo + la i18n key. F6.1 los compone.
3. **Selector manual de tipo de vehículo** — el corpus es categórico (BR2 + DEC-SUC-22). NO existe `<Select>` ni `<RadioGroup>` para tipo. F4.1 NO entrega UI de override. El operador kiosko NUNCA selecciona manualmente.
4. **Tolerancia de tipeo `O↔0`/`I↔1`/`B↔8`** — pertenece a `buscarIngresoTolerante()` de Fase 7 (salida vehicular). F4.1 entrega función estricta sin tolerancia. DEC-SUC-22 verbatim: "función estricta y sin tolerancia de tipeo".
5. **Migraciones Alembic** — ninguna tabla nueva ni columna nueva (regex vive en código cliente, NO en BD — adaptación A-03 explícita). F4.1 NO crea migration.
6. **`electron-store` fallback persistente** — plan.md menciona fallback hardcoded `{auto, moto}`, NO persistente entre sesiones (a diferencia de HU-F4.2 tarifas que usa electron-store para caché de tarifa). Catálogos cambian muy raramente — fallback hardcoded suficiente.
7. **`refreshInterval` periódico** — SWR usa solo `dedupingInterval` (deduplicación entre consumers concurrentes). NO `refreshInterval` (catálogos cambian muy raramente — el operador no espera actualización en tiempo real). Si admin cambia `tipos_vehiculo`, el operador verá el cambio al próximo refresh SWR (5min) o al cerrar/abrir turno.
8. **e2e test (Playwright)** — F4.1 es lógica pura (función + hook). Los 11 unit tests cubren la lógica. e2e (Playwright) testeará la integración cuando F6.1 consuma la función en `<PlacaInput>`. Documentado como forward coverage (no F4.1 scope). Sandbox F.6 deviation esperada (npm 11.16.0 limit, F.6 precedent) — D-env en `verify-report.md` futuro.
9. **WCAG axe-core scan runtime** — 6 unit tests + 5 hook tests cubren lógica. axe-core A1 scan es para HU-F6.1 (`<PlacaInput>` componente visible). F4.1 NO entrega componente UI, NO aplica axe-core scan runtime. axe-core source-level (unit test alternative con vitest-axe) aplica al JSDoc/doc-comment compliance — forward F6.1.
10. **i18n plurals** — mensaje de error es string único (no plural). NO requiere `i18next-resources-types` (F2.1 baseline permite strings libres).
11. **`crypto.randomUUID()` para fallback uuids** — fallback hardcoded usa UUIDs fijos `'00000000-0000-0000-0000-000000000001'` y `'00000000-0000-0000-0000-000000000002'` (literales, NO generados dinámicamente — son sentinels, no IDs reales).
12. **Tipos de vehículo adicionales** (`Bicicleta`, `Camión`, `Moto eléctrica`, etc.) — A-03 explícito: "no hay respaldo en el corpus de CU para un tercer patrón". Si el negocio lo requiere, se agrega como decisión de producto explícita (DEC-F4.1-NN futura), no como dato asumido. Si se agrega, el regex hardcoded se extiende Y el `HARDCODED_CATALOG` también.
13. **Decoradores TypeScript / runtime guards** — la función es pura; no requiere validador runtime externo. F6.x Zod usa las constantes `REGEX_AUTO` + `REGEX_MOTO` exportadas (no la función).
14. **Permisos granulares por acción** — backend ya emite 403 si el `permisos[]` del usuario no incluye `config_catalogo` (per catalogos.py:101 `_CATALOG_DEFAULTS`). F4.1 NO agrega client-side permission gating — backend es source of truth (Defense in depth XR6).

---

## 4. Decisions ratified (DEC-F4.1-NN)

F4.1 introduce **11 decisiones arquitectónicas** (DEC-F4.1-01..10 ratified en exploration §7 + DEC-F4.1-11 NUEVA decisión de spec delta introducida en esta propuesta). El detalle verbatim vive en `exploration.md` §7 (DEC-F4.1-01..10) y en §4.11 abajo (DEC-F4.1-11). Esta sección referencia y resume cada DECISION + RATIONALE + ALTERNATIVES CONSIDERED.

### 4.1 DEC-F4.1-01 — `detectarTipoVehiculo` signature: pura, sin side effects

**DECISION**: `export function detectarTipoVehiculo(placa: string): 'Auto' | 'Moto' | null`. Función pura determinista. Sin acceso a red, sin acceso a store, sin acceso a DOM. Testeable sin mocks.

**RATIONALE**: Pureza permite testing determinista (6 tests sin setUp complejo). Side effects (logging, métricas) se agregan en F6.1 layer que consume la función, NO en F4.1. Precedent `formatCOP` (F4.2 plan.md:1416) y `buscarIngresoTolerante()` (forward F7.x) — ambas puras. Tipo de retorno como union literals (`'Auto' | 'Moto' | null`) en vez de enum TypeScript: mejor tree-shaking + mejor type narrowing con `if (tipo === 'Auto')`.

**ALTERNATIVES CONSIDERED**:
- A. Función con side effects (logging interno) — RECHAZADA. Rompe pureza + agregar dependencia (`winston`, `pino`). F6.1 capa de logging si necesita.
- B. Función pura con union literals (DECIDIDA) — Determinista + tree-shakeable + type-safe.
- C. Enum TypeScript `enum TipoVehiculo { Auto, Moto }` con función retornando enum — RECHAZADA. Enum TypeScript emite object en runtime (no erasable), peor tree-shaking. Union literals es el patrón F2.x + F3.x.

### 4.2 DEC-F4.1-02 — Normalización previa al regex: trim + uppercase + remover whitespace interno

**DECISION**: Antes de aplicar regex, la función aplica: `(a) trim inicio/fin; (b) uppercase; (c) replace(/\s+/g, '')` para remover TODOS los whitespace internos. Esto cubre los tests U5 (minúsculas) + U6 (espacios) sin necesidad de regex tolerantes.

**RATIONALE**: Operador kiosko puede digitar ` abc123 ` (con espacios al inicio/fin por velocidad) o `abc 123` (con espacio interno por error). Sin normalización, ambos fallan el regex. Con normalización previa, ambos pasan. NO extiende DEC-SUC-22 (tolerancia `O↔0`/`I↔1`/`B↔8` es OTRO nivel de tolerancia — la normalización es TRIVIAL, no es "tolerancia de tipeo"). La normalización es whitespace-only (espacios, tabs, linebreaks); NUNCA caracteres alfanuméricos similares.

**ALTERNATIVES CONSIDERED**:
- A. Regex tolerante sin normalización (ej. `[A-Z\s]{3}[0-9\s]{3}`) — RECHAZADA. Regex se vuelve frágil + introduce matches falsos (espacios en posiciones inválidas).
- B. Trim + uppercase sin remover whitespace interno — RECHAZADA. Caso `"abc 123"` (con espacio interno) NO matchea `^[A-Z]{3}[0-9]{3}$`.
- C. trim + uppercase + remove whitespace interno (DECIDIDA) — Normalización total + regex estricta + tests U5 + U6 pasan.

### 4.3 DEC-F4.1-03 — Regex como constantes exportadas (NO magic numbers)

**DECISION**: `export const REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/; export const REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/;`. Exportadas para que F6.1 las importe y use en validación Zod (`z.object({ placa: z.string().regex(REGEX_AUTO) })`).

**RATIONALE**: F6.1 requiere la misma regex para validación Zod. Exportar evita duplicación (DRY). Si el negocio cambia el patrón (ej: agregar Moto eléctrica `^[A-Z]{3}[0-9]{4}$`), UN solo punto de cambio en el cliente + el backend (`operacion.py:215-277` sincronizado manualmente). Testeable independientemente (`expect(REGEX_AUTO.test('ABC123')).toBe(true)`). Documentación en JSDoc verbatim DEC-SUC-22 + A-03 + BR2.

**ALTERNATIVES CONSIDERED**:
- A. Regex inline dentro de `detectarTipoVehiculo()` (no exportadas) — RECHAZADA. F6.1 necesitaría duplicar regex (DRY violation) o importar la función para usarla como Zod refinement (overkill).
- B. Regex como constantes exportadas (DECIDIDA) — DRY + testable + JSDoc referencia canónica.

### 4.4 DEC-F4.1-04 — `useTiposVehiculo` SWR: dedupingInterval 5min, sin refreshInterval

**DECISION**: `dedupingInterval: 5 * 60 * 1000` (300_000ms). NO `refreshInterval` (catálogos cambian muy raramente — el operador no espera actualización en tiempo real). Si admin cambia `tipos_vehiculo`, el operador verá el cambio al próximo refresh SWR (5min) o al cerrar/abrir turno.

**RATIONALE**: Precedent `useSesionActiva` (F3.3) usa `refreshInterval: 50min` + `dedupingInterval: 10s` porque la sesión puede cambiar de estado durante el turno. Catálogo NO cambia durante operación normal — es reference data que el operador consume. `dedupingInterval: 5min` evita refetch cuando múltiples componentes consumen el mismo catálogo (ej: `<PlacaInput>` + `<OcupacionStrip>` + futuras pantallas). plan.md:1375 verbatim 5min.

**ALTERNATIVES CONSIDERED**:
- A. `dedupingInterval: 10s` (mismo que `useSesionActiva`) — RECHAZADA. Catálogos NO son transaccionales (no necesitan refrescarse cada 10s). 10s malgasta requests.
- B. `refreshInterval: 50min` (refresco activo) — RECHAZADA. Catálogos cambian raramente. Refresco activo malgasta bandwidth.
- C. `dedupingInterval: 5 * 60 * 1000` sin refreshInterval (DECIDIDA) — Catálogo reference data + deduplicación multi-consumer sin refresh activo.

### 4.5 DEC-F4.1-05 — Fallback hardcoded `{auto, moto}` con UUIDs sentinels

**DECISION**: `const HARDCODED_CATALOG: TipoVehiculo[] = [{uuid: '00000000-0000-0000-0000-000000000001', tipo: 'Auto', vigente_desde: '2026-01-01T00:00:00Z', vigente_hasta: null, estado: 'activo'}, {uuid: '00000000-0000-0000-0000-000000000002', tipo: 'Moto', vigente_desde: '2026-01-01T00:00:00Z', vigente_hasta: null, estado: 'activo'}]`. Exportado como constante módulo-level. Usado como `fallbackData` en SWR.

**RATIONALE**: Plan.md:1375 verbatim "fallback a un catálogo hardcoded de `{auto, moto}` si la API local no responde — degradación explícita, no un crash de pantalla". UUIDs sentinels son LITERALES (NO `crypto.randomUUID()`) porque son identificadores de FALLBACK, no IDs reales para sync. Si el backend arranca con la API down, el cliente tiene un fallback que cubre Auto+Moto (los 2 tipos que la regex puede detectar). Si en el futuro hay un tercer tipo (ej: Bicicleta vía DEC-F4.1-NN futura), el fallback se extiende — pero F4.1 NO lo incluye porque A-03 explícito "no hay respaldo en el corpus de CU para un tercer patrón". Constante inline (NO archivo separado) per DEC-F4.1-05 ratified — mantiene cohesión con el hook que la usa.

**ALTERNATIVES CONSIDERED**:
- A. Fallback con `crypto.randomUUID()` — RECHAZADA. UUIDs aleatorios cada boot = `uuid_tipo_vehiculo` inconsistente entre detecciones (bug latente).
- B. Fallback con `electron-store` persistente — RECHAZADA para F4.1. Catálogos cambian raramente (reference data). Persistencia entre sesiones over-engineering. F4.2 (tarifas) sí usa electron-store (datos transaccionales).
- C. Fallback hardcoded `{auto, moto}` con UUIDs sentinels literales inline (DECIDIDA) — Simple + cubre Auto+Moto + sentinels explícitos.

### 4.6 DEC-F4.1-06 — `isFromFallback` flag en return del hook

**DECISION**: El hook retorna `{tipos: TipoVehiculo[], isLoading: boolean, error: Error | undefined, refresh: () => Promise<TipoVehiculo[] | undefined>, isFromFallback: boolean}`. `isFromFallback` es `true` cuando `data === HARDCODED_CATALOG` (i.e., el SWR está mostrando fallback porque la API no respondió).

**RATIONALE**: F6.x+ consumers pueden querer mostrar un indicador visual sutil "usando datos locales" cuando `isFromFallback === true`. NO es requerido por F4.1, pero el flag es cheap de agregar y útil para debugging. Forward F4.2 (`useTarifasVigentes`) puede replicar el pattern con `electronStore.get('tarifas')`. Comparación por referencia (`data === HARDCODED_CATALOG`) porque es la misma referencia constante — no hace falta deep-equal.

**ALTERNATIVES CONSIDERED**:
- A. Sin flag `isFromFallback` — RECHAZADA. Consumers futuros (F6.x+ tooltip "usando datos locales") necesitan el flag. Cheap de agregar upfront.
- B. Flag derivado de `error !== undefined` — RECHAZADA. `error` puede ser 404 (catálogo vacío) que NO requiere fallback visible.
- C. Flag `isFromFallback` derivado de `data === HARDCODED_CATALOG` (DECIDIDA) — True source of truth + cheap + forward extensibility.

### 4.7 DEC-F4.1-07 — DELTA verdict (NOT NO-OP) — F4.1 IS user-facing

**DECISION**: F4.1 emite DELTA spec con 6 new REQ-OPS-125..130 (numbered post-F3.3 REQ-OPS-124). Spec delta materializes en `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/specs/operations/spec.md`.

**RATIONALE**: F4.1 ES user-facing behavior observable:
- (a) Autocompletar tipo al digitar placa — operador NO selecciona manualmente (interacción observable).
- (b) Mensaje inline "Placa no coincide con ningún formato conocido" si regex no matchea (feedback observable).
- (c) Catálogo cargado desde API con fallback hardcoded (degradación observable si API down).

Per F1.15 + F3.1 + F3.2 + F3.3 precedent, user-facing ⇒ spec delta materialized. F2.x NO-OP stub precedent NO aplica (infra-only HU sin behavior visible). Ver DEC-F4.1-11 abajo para el rationale extendido del verdict.

**ALTERNATIVES CONSIDERED**:
- A. NO-OP stub (DEC-FETCH-10 precedent verbatim) — RECHAZADA tras re-evaluación. F2.x fueron infra-only; F4.1 ES user-facing behavior. Aplicar precedent equivocado rompería el audit trail del spec.
- B. DELTA con 4 new REQ-OPS-125..128 (minimum viable) — RECHAZADA. Reduciría cobertura de comportamiento. 6 REQs balancean audit trail exhaustivo sin overload.
- C. DELTA con 6 new REQ-OPS-125..130 (DECIDIDA) — Cobertura completa de behavior observable al operador. Match precedent F3.1 (7 new REQ-OPS-106..112) + F3.2 (6 new REQ-OPS-113..118) + F3.3 (6 new REQ-OPS-119..124).

### 4.8 DEC-F4.1-08 — Atomic commits: 2 commits (T1+T3 agrupados, T2 separado)

**DECISION**: Plan F4.1 dice 3 tareas atómicas T1..T3 (per `plan.md:1385-1388`). Work-unit-commits skill (F2.x + F3.x precedent): commits agrupan por DELIVERABLE, NO por TAREA. F4.1 emite 2 commits:
- **C1**: `feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido (HU-F4.1-T1+T3)` (T1 + T3 agrupados: función pura + i18n + tests — deliverable cohesivo "detección de placa funciona en cliente").
- **C2**: `feat(catalogos): adicionar useTiposVehiculo() SWR + fallback hardcoded {auto,moto} + 5 unit tests (HU-F4.1-T2)` (T2 solo: hook + api + tests — deliverable cohesivo "catálogo de tipos se carga con degradación").

**RATIONALE**: T1 (función pura) + T3 (i18n key) son deliverables cohesivos (la función SIN i18n key es incompleta para el caller que quiera mostrar el error en F6.1). T2 (hook) es deliverable independiente (consumible por F4.3 antes que F6.1 exista, peer con F4.2 hook independiente). Tests incluidos con código (work-unit-commits hard rule: "Tests belong in the same commit as the behavior they verify"). Conventional Commits sin Co-authored-by AI (prohibido per AGENTS.md).

**ALTERNATIVES CONSIDERED**:
- A. 3 commits separados por tarea (T1, T2, T3) — RECHAZADA. Work-unit-commits skill: commits agrupan por DELIVERABLE cohesivo, NO por tarea atómica. T1 sin T3 = función sin mensaje de error. T3 sin T1 = i18n key sin función consumidora.
- B. 1 commit monolítico con todo — RECHAZADA. >400 LOC en un commit = review cognitiva pesada + rollback granular imposible.
- C. 2 commits (T1+T3 agrupados en C1, T2 separado en C2) (DECIDIDA) — Work-unit commits F2.x + F3.x verbatim + tests incluidos + deliverable cohesivo cada uno.

### 4.9 DEC-F4.1-09 — `useTiposVehiculo` exporta tipo `TipoVehiculo` matching backend

**DECISION**: Interface exportada `interface TipoVehiculo { uuid: string; tipo: string | null; vigente_desde: string; vigente_hasta: string | null; estado: string }`. Shape matching `TiposVehiculoRead` backend (`schemas/tipos_vehiculo.py:13-23`). `tipo` es `string | None` en backend pero en cliente lo tratamos como `string | null` con filtro defensivo en `tiposVehiculoApi.getTiposVehiculo()`.

**RATIONALE**: TypeScript strict (F2.1 baseline) requiere tipos explícitos. Backend puede retornar `tipo: null` para una fila corrupta — cliente debe manejarlo (filtro descarta filas con `tipo: null` antes de exponer al hook). Para F4.1, si backend retorna `tipo: null`, la fila se ignora silenciosamente (filtro en `tiposVehiculoApi.getTiposVehiculo()` antes de retornar). Forward F6.1 consume `tipo` para matching contra detección regex: solo `tipo === 'Auto' | tipo === 'Moto'` son válidos.

**ALTERNATIVES CONSIDERED**:
- A. Tipo con `tipo: string` (no nullable) — RECHAZADA. Backend Pydantic permite `tipo: str | None`. Mentir al cliente sobre la nulabilidad es bug latente.
- B. Tipo con `tipo: string | null` + filtro defensivo en api wrapper (DECIDIDA) — TypeScript strict + defensa contra backend corrupto.

### 4.10 DEC-F4.1-10 — Test coverage: 6 placa + 5 hook = 11 unit tests

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

**RATIONALE**: Cobertura ≥90% líneas / 80% branches per D9 F2.1 + F3.1 precedent. Tests placa cubren todos los branches de la función pura (regex match both types, no match, empty, normalización min+may+whitespace). Tests hook cubren SWR config crítica (key null-when-no-token, dedup, fallback, 401 clear + event dispatch).

**ALTERNATIVES CONSIDERED**:
- A. 6 tests placa + 3 tests hook (mínimo viable) — RECHAZADA. Reduce cobertura de branches. Tests hook deben cubrir SWR config completa (key, dedup, fallback, 401).
- B. 11 tests (6 + 5) (DECIDIDA) — Cobertura completa branches críticos + D9 compliance.

### 4.11 DEC-F4.1-11 — **NUEVA** Spec delta a `operations/spec.md` con 6 new REQ-OPS-125..130 (DELTA, NO NO-OP)

**DECISION**: `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/specs/operations/spec.md` AGREGA 6 new REQ-OPS-125..130 al spec canónico, NO es NO-OP stub. Las 6 REQ-OPS documentan el comportamiento observable al operador (autodetectar tipo + error inline i18n + catálogo con fallback degradado + SWR token-gated + WCAG-future + DELTA verdict) en formato Given/When/Then/And RFC 2119.

**RATIONALE — re-evaluación crítica desde exploration §7 (DEC-FETCH-10 NO-OP precedent)**: F4.1 sigue el precedent F1.15 (4 new REQ-OPS-102..105) + F3.1 (7 new REQ-OPS-106..112) + F3.2 (6 new REQ-OPS-113..118) + F3.3 (6 new REQ-OPS-119..124) que SÍ escribieron new REQ-OPS al spec canónico con la misma justificación: detección de tipo de vehículo es user-facing behavior que el operador observa y depende (a través del flujo de ingreso F6.1 que consume F4.1). La justificación detallada:

| Aspecto | F2.1/F2.2/F2.3 (NO-OP precedent) | F4.1 (DELTA con new REQ-OPS-NNN) |
|---|---|---|
| Tipo de cambio | Infra-only (scaffold + IPC + runtime) | User-facing behavior observable (autodetectar + error inline + catálogo) |
| Componente visible al operador | Ninguno (electron main, ipc preload, services) | (forward) F6.1 `<PlacaInput>` consume F4.1 (autocompletar tipo) + error inline `role="alert"` + fallback degradado si catálogo down |
| Behavior observable | N/A (no UI) | Función pura `detectarTipoVehiculo` + i18n key pre-poblada + hook SWR con fallback |
| Pre-flight correctness | N/A (no POST críticos) | `/catalogos/tipos-vehiculo` es GET read idempotente — NO requiere pre-flight gate (DEC-SUC-03 + F3.2 verbatim) |
| Precedent directo | DEC-ELEC-10 / DEC-FETCH-10 / DEC-UPD-13 (infra) | REQ-OPS-102..105 (F1.15) + REQ-OPS-106..112 (F3.1) + REQ-OPS-113..118 (F3.2) + REQ-OPS-119..124 (F3.3) user-facing |
| Verificabilidad | DEC-* documentan; sin REQ spec-level | REQ-OPS-NNN + DEC-* cross-linked |

**Numeración**: el último REQ-OPS vigente en `operations/spec.md` es REQ-OPS-124 (F3.3 archivado 2026-09-15). Las 6 new REQs ocupan REQ-OPS-125..130 (continuación monotónica post-F3.3 REQ-OPS-124). Numeración verificada: 124 → 125 → 126 → 127 → 128 → 129 → 130 (0 gaps, sin duplicados).

**Las 6 new REQ-OPS-125..130** (detail en §6):

| ID | Behavior observable | Anchor DEC |
|---|---|---|
| REQ-OPS-125 | `detectarTipoVehiculo(placa: string): 'Auto' \| 'Moto' \| null` función pura con regex estricto hardcoded (Auto `^[A-Z]{3}[0-9]{3}$`, Moto `^[A-Z]{3}[0-9]{2}[A-Z]$`), sin tolerancia de tipeo, normalización previa (trim + uppercase + remove whitespace interno), exports `REGEX_AUTO` + `REGEX_MOTO` | DEC-F4.1-01, -02, -03 |
| REQ-OPS-126 | i18n key `operacion.placa_formato_invalido` con literal "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)" para consumo forward F6.1 `<PlacaInput>` `<p role="alert" aria-describedby>` | DEC-F4.1-07 (forward hook) |
| REQ-OPS-127 | `useTiposVehiculo()` hook SWR con key `accessToken ? '/catalogos/tipos-vehiculo' : null`, `dedupingInterval: 5 * 60 * 1000`, `fallbackData: HARDCODED_CATALOG` con `{auto, moto}`, `shouldRetryOnError` excluye 404, `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event | DEC-F4.1-04, -05, -06 |
| REQ-OPS-128 | `tiposVehiculoApi.getTiposVehiculo()` typed wrapper `parkosFetch<TiposVehiculoReadList>('/api/v1/catalogos/tipos-vehiculo')` con mapeo 404 → `[]` (catálogo vacío es estado válido) y filtro defensivo de filas con `tipo: null` | DEC-F4.1-09 |
| REQ-OPS-129 | Defense in depth XR6 layer 4: cliente detecta (F4.1) + backend re-valida con `detectar_tipo_vehiculo()` server-side (shipped HU-F1.x — `operacion.py:215-277`); backend SIEMPRE wins (overwrites via V5 "regex-derived UUID wins over client value", operacion.py:261) | DEC-F4.1-01 (defense layer) |
| REQ-OPS-130 | WCAG 2.1 AA compliance (forward F6.1) — la i18n key + el detector sienta las bases para que `<PlacaInput>` use `aria-describedby` + `<p role="alert">` con 0 violaciones axe-core (verificación en F6.1 forward) | DEC-F4.1-11 (forward coverage) |

**ALTERNATIVES CONSIDERED**:
- A. NO-OP stub (DEC-FETCH-10 precedent verbatim) — RECHAZADA tras re-evaluación. F2.1/F2.2/F2.3 fueron infra-only; F4.1 ES user-facing behavior. Aplicar precedent equivocado rompería el audit trail del spec.
- B. DELTA con 4 new REQ-OPS-125..128 (minimum viable) — RECHAZADA. Reduciría cobertura de comportamiento. 6 REQs balancean audit trail exhaustivo sin overload.
- C. DELTA con 6 new REQ-OPS-125..130 (DECIDIDA) — Cobertura completa de behavior observable al operador (incluyendo defense in depth + WCAG forward). Match precedent F3.1 (7 new REQ-OPS-106..112) + F3.2 (6 new REQ-OPS-113..118) + F3.3 (6 new REQ-OPS-119..124).

**Convención de identificadores**: DEC-F4.1-NN sigue el patrón DEC-ELEC-NN (F2.1), DEC-FETCH-NN (F2.2), DEC-UPD-NN (F2.3), DEC-LOGIN-NN (F1.15), DEC-F3.1-NN (F3.1), DEC-F3.2-NN (F3.2), DEC-F3.3-NN (F3.3). REQ-OPS-NNN sigue la numeración monotónica del spec canónico vigente. F4.1 ocupa REQ-OPS-125..130 (continuación de F3.3 REQ-OPS-119..124). DEC-F4.1-11 es la decisión de propuesta que formaliza el anchor al spec canónico (ratifica DEC-F4.1-07 de exploración con anchors explícitos a REQ-OPS-NNN).

---

## 5. Scope y out-of-scope

### 5.1 In Scope (~250 LOC production + ~250 LOC tests)

| Area | Detalle |
|---|---|
| **`detectarTipoVehiculo` función pura (T1)** | New `apps/electron-sucursal/src/lib/validation/placa.ts` (~50 LOC production). Función pura sin dependencias externas. Signature: `detectarTipoVehiculo(placa: string): 'Auto' \| 'Moto' \| null`. Comportamiento: (a) trim + uppercase + remover whitespace interno; (b) test contra `REGEX_AUTO` → return `'Auto'`; (c) test contra `REGEX_MOTO` → return `'Moto'`; (d) sin match → return `null`. Regex exportadas como constantes `REGEX_AUTO` + `REGEX_MOTO`. JSDoc explícito referenciando DEC-SUC-22 + A-03 + BR2 literal + `operacion.py:215-277` backend counterpart. |
| **`placa.test.ts` 6 unit tests (T1)** | New `apps/electron-sucursal/src/lib/validation/placa.test.ts` (~80 LOC, 6 tests verbatim plan.md:1381). U1 Auto válido (`ABC123`), U2 Moto válido (`ABC12D`), U3 formato inválido (`ABCD12`), U4 placa vacía (U4a `""`, U4b `null` cast como `""`), U5 minúsculas normalizadas (`abc123` → `'Auto'`), U6 placa con espacios (`"  ABC123  "` → `'Auto'`). Cobertura ≥90% líneas / 80% branches. |
| **`tiposVehiculoApi` typed wrappers (T2)** | New `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` (~30 LOC). `getTiposVehiculo(): Promise<TipoVehiculo[]>` — `parkosFetch<TiposVehiculoReadList>('/api/v1/catalogos/tipos-vehiculo')` con mapeo 404 → `[]` + filtro defensivo de filas con `tipo: null`. Interface `TipoVehiculo { uuid: string; tipo: string \| null; vigente_desde: string; vigente_hasta: string \| null; estado: string }` matching `TiposVehiculoRead` backend (schemas/tipos_vehiculo.py:13-23). NO `fetch` directo (precedent F2.2 — parkosFetch con auth + refresh-once + retry). |
| **`useTiposVehiculo` hook SWR (T2)** | New `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (~80 LOC production + ~40 LOC tests). SWR key `accessToken ? '/catalogos/tipos-vehiculo' : null`. `dedupingInterval: 5 * 60 * 1000`. `fallbackData: HARDCODED_CATALOG` con shape `{auto, moto}`. `shouldRetryOnError` excluye 404. `onError` con `status===401` dispara `useAuthStore.getState().clear()` + `window.dispatchEvent(new Event('parkos:auth:cleared'))` (precedent F3.3 verbatim). Retorna `{tipos: TipoVehiculo[], isLoading: boolean, error: Error \| undefined, refresh: () => Promise<TipoVehiculo[] \| undefined>, isFromFallback: boolean}`. `HARDCODED_CATALOG` constante inline (DEC-F4.1-05). |
| **`useTiposVehiculo.test.ts` 5 unit tests (T2)** | New `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.test.ts` (~50 LOC, 5 tests). U7 SWR key null sin token (mock `useAuthStore` retornando `null`), U8 SWR fetch OK con catálogo poblado (mock 200 OK), U9 fallback hardcoded cuando API 500 (mock 500 → `data === HARDCODED_CATALOG`), U10 dedupingInterval = 5min (inspeccionar swrOptions.dedupingInterval === 300000), U11 onError con status=401 dispara `useAuthStore.getState().clear` + dispatch event. |
| **i18n key (T3)** | Modify `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (+1 key `placa_formato_invalido`, ~3 LOC). Namespace pre-existente (F2.1 DEC-ELEC-06 — un namespace por bounded context). NO requiere nuevo namespace. String literal verbatim plan.md:1366: "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)". |
| **Atomic commits (DEC-F4.1-08)** | 2 commits: (C1) `feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido (HU-F4.1-T1+T3)`; (C2) `feat(catalogos): adicionar useTiposVehiculo() SWR + fallback hardcoded {auto,moto} + 5 unit tests (HU-F4.1-T2)`. Tests incluidos con código (work-unit-commits skill — F2.x + F3.x verbatim precedent). Conventional Commits sin Co-authored-by AI. |

### 5.2 Out of Scope (explícitamente deferido)

- **Backend cambios**: `detectar_tipo_vehiculo()` server-side ya shipped (HU-F1.x — `operacion.py:215-277`). `GET /api/v1/catalogos/tipos-vehiculo` C+Q+U router ya shipped (catalogos.py:140-147 F1.x + F3.0 precedent). F4.1 NO modifica backend.
- **UI componente `<PlacaInput>`**: HU-F6.1 entrega el componente que consume `detectarTipoVehiculo()` y renderiza el mensaje de error. F4.1 entrega SOLO la función pura + el hook del catálogo + la i18n key.
- **Selector manual de tipo de vehículo**: el corpus es categórico (BR2 + DEC-SUC-22) — NO existe un override manual. F4.1 NO entrega `<Select>` ni `<RadioGroup>` para tipo.
- **Tolerancia de tipeo O↔0/I↔1/B↔8**: pertenece a `buscarIngresoTolerante()` de Fase 7 (salida). F4.1 entrega función estricta sin tolerancia. DEC-SUC-22 verbatim.
- **Migraciones Alembic**: ninguna tabla nueva ni columna nueva (regex vive en código cliente, NO en BD — adaptación A-03 explícita).
- **`electron-store` fallback persistente**: plan.md menciona fallback hardcoded `{auto, moto}`, NO persistente entre sesiones (a diferencia de HU-F4.2 tarifas que usa electron-store). Catálogos cambian raramente — fallback hardcoded suficiente.
- **`refreshInterval` periódico**: SWR usa solo `dedupingInterval` (deduplicación entre consumers concurrentes). NO `refreshInterval` (catálogos cambian muy raramente — el operador no espera actualización en tiempo real).
- **e2e test (Playwright)**: F4.1 es lógica pura (función + hook) — los 11 unit tests cubren la lógica. e2e (Playwright) testeará la integración cuando F6.1 consuma la función en `<PlacaInput>`. Sandbox F.6 deviation esperada (npm 11.16.0 limit) — D-env en `verify-report.md` futuro, NO project defect.
- **WCAG axe-core scan runtime**: 11 unit tests cubren lógica. axe-core A1 scan es para HU-F6.1 (`<PlacaInput>` componente visible). F4.1 NO entrega componente UI, NO aplica axe-core scan runtime.
- **i18n plurals**: mensaje de error es string único (no plural). NO requiere `i18next-resources-types`.
- **`crypto.randomUUID()` para fallback uuids**: fallback hardcoded usa UUIDs fijos `'00000000-0000-0000-0000-000000000001'` y `'00000000-0000-0000-0000-000000000002'` (literales, NO generados dinámicamente).
- **Tipos de vehículo adicionales** (`Bicicleta`, `Camión`, `Moto eléctrica`, etc.): A-03 explícito: "no hay respaldo en el corpus de CU para un tercer patrón". Si el negocio lo requiere, se agrega como decisión de producto explícita (DEC-F4.1-NN futura), no como dato asumido.
- **Decoradores TypeScript / runtime guards**: la función es pura; no requiere validador runtime externo. F6.x Zod usa las constantes `REGEX_AUTO` + `REGEX_MOTO` exportadas (no la función).
- **Permisos granulares por acción**: backend ya emite 403 si el `permisos[]` del usuario no incluye `config_catalogo` (per `_CATALOG_DEFAULTS:101` catalogos.py). F4.1 NO agrega client-side permission gating.

---

## 6. Arquitectura propuesta

### 6.1 Diagrama de componentes (ASCII)

```
+------------------------------------------------------------------+
| <PlacaInput> (HU-F6.1 forward — consume F4.1)                    |
|  +-- useForm<{placa}>() with zodResolver(...)                    |
|  |     + z.string().regex(REGEX_AUTO) o .regex(REGEX_MOTO)      |
|  +-- detectarTipoVehiculo(form.placa) → 'Auto'|'Moto'|null      |
|  |     → si null: <p role="alert">                               |
|  |              {t('operacion.placa_formato_invalido')}</p>       |
|  |     → si 'Auto'|'Moto': setea uuid_tipo_vehiculo via          |
|  |       useTiposVehiculo().tipos.find(t => t.tipo === ...)      |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| detectarTipoVehiculo (NEW ~50 LOC, T1)                            |
|  detectarTipoVehiculo(placa: string): 'Auto'|'Moto'|null         |
|   internals:                                                      |
|     1. const normalizada = placa.trim().toUpperCase()            |
|                              .replace(/\s+/g, '')                |
|     2. if (REGEX_AUTO.test(normalizada)) return 'Auto'           |
|     3. if (REGEX_MOTO.test(normalizada)) return 'Moto'           |
|     4. return null                                               |
|  exports:                                                         |
|     REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/                            |
|     REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/                       |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| useTiposVehiculo (NEW ~80 LOC, T2)                               |
|  useTiposVehiculo():                                             |
|    { tipos, isLoading, error, refresh, isFromFallback }          |
|   internals:                                                      |
|     accessToken = useAuthStore(s => s.accessToken)               |
|     HARDCODED_CATALOG: TipoVehiculo[] = [                        |
|       { uuid: '...0001', tipo: 'Auto', vigente_desde:            |
|         '2026-01-01T00:00:00Z', vigente_hasta: null,             |
|         estado: 'activo' },                                       |
|       { uuid: '...0002', tipo: 'Moto', vigente_desde:            |
|         '2026-01-01T00:00:00Z', vigente_hasta: null,             |
|         estado: 'activo' }                                        |
|     ]                                                            |
|     useSWR(                                                       |
|       key: accessToken ? '/catalogos/tipos-vehiculo' : null,     |
|       fetcher: () => tiposVehiculoApi.getTiposVehiculo(),         |
|       fallbackData: HARDCODED_CATALOG,                            |
|       dedupingInterval: 5 * 60 * 1000,                            |
|       shouldRetryOnError: (err) => err?.status !== 404,           |
|       onError: (err) => if (err?.status === 401) {                |
|                          useAuthStore.getState().clear()          |
|                          window.dispatchEvent(                    |
|                            new Event('parkos:auth:cleared'))      |
|                        }                                        |
|     )                                                             |
|     isFromFallback = data === HARDCODED_CATALOG                  |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| tiposVehiculoApi (NEW ~30 LOC, T2)                               |
|  +-- getTiposVehiculo(): Promise<TipoVehiculo[]>                 |
|       → parkosFetch<TiposVehiculoReadList>(                       |
|           '/api/v1/catalogos/tipos-vehiculo')                     |
|       → if status 404: return []                                 |
|       → filter rows where tipo !== null                          |
|       → return items.map(toTipoVehiculo)                         |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| backend GET /api/v1/catalogos/tipos-vehiculo (F3.0 READ ONLY)     |
|  +-- permission_required='config_catalogo'                       |
|  |     (issuer_required='admin-,operador-')                      |
|  +-- 200 OK → TiposVehiculoReadList                              |
|  |     (lista de {uuid, tipo, vigente_desde,                      |
|  |      vigente_hasta, estado, created_at, ...})                  |
|  +-- 404 → catálogo no encontrado (sucursal sin tipos)           |
|  |     (catálogo vacío mapeado a [] en cliente)                  |
|  +-- 403 → permission denied                                     |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| backend detectar_tipo_vehiculo() (HU-F1.x READ ONLY)             |
|  +-- Defense in depth XR6 layer 4                                |
|  |     (operacion.py:215-277)                                    |
|  +-- Server overwrites via V5:                                   |
|  |     "regex-derived UUID wins over client value"                |
|  |     (operacion.py:261)                                        |
|  +-- Same regex cliente + backend:                               |
|       Auto: ^[A-Z]{3}[0-9]{3}$                                   |
|       Moto: ^[A-Z]{3}[0-9]{2}[A-Z]$                              |
+------------------------------------------------------------------+
```

### 6.2 Tabla de componentes

| Componente | Tipo | Responsabilidad | Tests | DEC |
|---|---|---|---|---|
| `detectarTipoVehiculo` | Función pura (NEW) | Trim + uppercase + remove whitespace + test contra REGEX_AUTO + REGEX_MOTO → return 'Auto'\|'Moto'\|null | `placa.test.ts` (NEW) | DEC-F4.1-01, -02, -03 |
| `REGEX_AUTO` + `REGEX_MOTO` | Constantes módulo-level (NEW) | Regex exportadas para reuso en Zod (F6.x) | (cubierto por placa.test.ts) | DEC-F4.1-03 |
| `tiposVehiculoApi` | API wrapper (NEW) | parkosFetch GET con mapeo 404 → [] + filtro null | (cubierto por useTiposVehiculo.test.ts via mock) | DEC-F4.1-09 |
| `useTiposVehiculo` | Hook (NEW) | SWR token-gated con deduping 5min + fallback hardcoded + onError 401 clear | `useTiposVehiculo.test.ts` (NEW) | DEC-F4.1-04, -05, -06 |
| `HARDCODED_CATALOG` | Constante módulo-level (NEW) | Shape sentinels Auto+Moto con UUIDs literales | (cubierto por useTiposVehiculo.test.ts U9) | DEC-F4.1-05 |
| `useAuthStore` | Store (F2.2, READ ONLY) | setTokens + clear + refreshAccessToken Mutex (consumido por F4.1 T2 para SWR key + onError clear) | (F2.2 already tested) | DEC-F4.1-04 |
| `parkosFetch` | HTTP (F2.2, READ ONLY) | retry + refresh-once 401 via Mutex + Idempotency-Key (consumido por F4.1 T2) | (F2.2 already tested) | DEC-F4.1-09 |
| `operacion.json` | i18n (F2.1, MODIFY) | +1 key `placa_formato_invalido` | snapshot test | DEC-F4.1-11 (REQ-OPS-126) |
| `useSesionActiva` | Hook (F3.3, READ ONLY) | SWR precedent pattern — F4.1 replica config (key null-when-no-token + deduping + 401 clear) | (F3.3 already tested) | DEC-F4.1-04 |

### 6.3 Layers + flow de datos

1. **Pure logic layer**: `detectarTipoVehiculo()` función pura exportada desde `lib/validation/placa.ts`. Sin dependencias runtime. Determinista. Testeable sin mocks. Consume por F6.1 `<PlacaInput>` (forward).
2. **Hook layer**: `useTiposVehiculo()` SWR retorna `{tipos, isLoading, error, refresh, isFromFallback}`. Key null-when-no-token (gate contra 401 noise pre-login). `dedupingInterval: 5min` evita refetch entre consumers concurrentes (`<PlacaInput>` + `<OcupacionStrip>` F4.3 + futuras pantallas). Fallback hardcoded explícito. `onError` 401 → `useAuthStore.clear()` + `parkos:auth:cleared` event.
3. **API layer**: `tiposVehiculoApi.getTiposVehiculo()` typed wrapper con `parkosFetch`. Mapeo 404 → `[]` (sucursal sin tipos configurados). Filtro defensivo de filas con `tipo: null` (backend Pydantic permite `tipo: str | None`).
4. **State layer**: `useAuthStore.accessToken` consumido por SWR key. `useAuthStore.clear()` post-401 dispara logout defensivo (forward AuthGuard F3.x+ intercepta `parkos:auth:cleared`).
5. **i18n layer**: `operacion.json` namespace pre-existente (F2.1 DEC-ELEC-06). +1 key `placa_formato_invalido` en F4.1. Consumible por F6.1 `<PlacaInput>` `<p role="alert" aria-describedby>`.
6. **Backend layer (READ ONLY)**: `GET /api/v1/catalogos/tipos-vehiculo` C+Q+U router (`catalogos.py:140-147` — `_CATALOG_DEFAULTS:101` con `permission_required='config_catalogo'`). `detectar_tipo_vehiculo()` server-side (`operacion.py:215-277` — defense in depth, server overwrites via V5). Cero cambios backend.

### 6.4 Stack técnico

- **React 18.3.1** (renderer, F2.1 baseline).
- **TypeScript strict** (F2.1 baseline) — interfaces `TipoVehiculo` con nullability explícita matching backend.
- **SWR 2.2.5** (F2.2 baseline) — `useTiposVehiculo` hereda pattern F3.3 `useSesionActiva` (key null-when-no-token + dedupingInterval).
- **parkosFetch** (F2.2 primitive, ui-kit) — pre-flight gate preservado (NO extension F4.1, mismo precedent F3.3 — `/catalogos/*` GET read idempotente, NO requiere pre-flight).
- **useAuthStore** (F2.2 primitive, ui-kit) — `clear()` post-401 (precedent F3.3).
- **Vitest 2.1.x + @testing-library/react 16.0.1 + jsdom 25.0.1** (F2.1 baseline) — 11 unit tests verde (6 placa + 5 useTiposVehiculo). Sandbox F.6 SKIPPED-env e2e (NO F4.1 scope; axe-core aplica a F6.1 forward).
- **i18next 23.x** (F2.1 baseline) — namespace `operacion.json` pre-existente, +1 key.
- **react-hook-form 7.53.0 + zod 3.23.8** (F2.1 + F3.1 baseline, no usado directamente F4.1 — F6.1 los consume forward con regex exportadas).

---

## 7. Implementation strategy

### 7.1 Cluster map (C1)

F4.1 se descompone en **1 cluster** (C1) con orden interno C1 → C2 (2 commits atómicos per DEC-F4.1-08).

### 7.2 Orden de ejecución

**C1 → C2** (per DEC-F4.1-08).

- C1 antes que C2 porque la i18n key + función pura son la base (forward F6.1 las necesita). C2 después porque el hook SWR es independiente (forward F4.3 podría consumirlo antes de F6.1 exista).
- C2 modifica `useAuthStore` via `onError` callback (precedent F3.3). Si C2 rompe el SWR 401 → clear pattern, F3.3 `useSesionActiva` puede romperse también (mismo pattern compartido). Mitigation: U11 verifica explícitamente el comportamiento.

### 7.3 Estrategia TDD

Cada task es **atómica** (commiteable independientemente con tests verde). TDD estricto:

- Tests rojos primero, luego código que los hace verde.
- Cobertura >80% exigida en `placa.ts` + `useTiposVehiculo.ts` (≥90% líneas / 80% branches per D9 F2.1 + F3.1 precedent).
- Defense in depth 5 capas preservado (F4.1 contributes contract layer al XR6 pattern).

### 7.4 Forward hooks — implementación transversal

`detectarTipoVehiculo()` se exporta desde `lib/validation/placa.ts` para consumo cross-feature. F6.1 `<PlacaInput>` (Fase 6) importa + lo llama sincrónicamente + matching contra `useTiposVehiculo().tipos[]`. Las constantes `REGEX_AUTO` + `REGEX_MOTO` se reusan en validación Zod F6.1 (`z.string().regex(REGEX_AUTO)`).

`useTiposVehiculo()` se exporta desde `features/catalogos/hooks/useTiposVehiculo.ts` para consumo cross-feature. F4.3 `<OcupacionStrip>` itera sobre `tipos` para renderizar `Auto: 23/50` por tipo. F6.1 `<PlacaInput>` consume para resolver `uuid_tipo_vehiculo` después de detectar. F11.x (sync UI) invalida el SWR cache con `mutate('/catalogos/tipos-vehiculo')` post-sync event.

`parkosFetch` pre-flight gate permanece F3.2 (NO extension F4.1 per DEC-F3.3-10 precedent). `/catalogos/*` (GET) es read idempotente — NO requiere pre-flight gate. Si Fase 4+ requiere pre-flight en `/catalogos/*` para mutaciones (POST/PUT), se agrega via DEC-F3.2-10 precedent.

---

## 8. Atomic tasks preview (T1..T3)

Cada task es **atómica** (commiteable independientemente con tests verde), pero se ejecutan en orden T1+T3 → T2 agrupados por commit per DEC-F4.1-08 (work-unit-commits skill). Detalle verbatim en `exploration.md` §11.

| Task | Budget (LOC) | Archivos | Commit message | Gate |
|---|---|---|---|---|
| **T1 — `detectarTipoVehiculo()` función pura + `placa.test.ts` 6 unit tests + T3 i18n key `placa_formato_invalido`** (agrupados en C1 per DEC-F4.1-08) | ~133 (53 prod + 80 tests) | `apps/electron-sucursal/src/lib/validation/placa.ts` (NEW, ~50 LOC — función pura + JSDoc + constantes regex exportadas con referencia verbatim DEC-SUC-22 + A-03 + BR2 + `operacion.py:215-277` backend counterpart) · `apps/electron-sucursal/src/lib/validation/placa.test.ts` (NEW, ~80 LOC — U1..U6 verbatim plan.md:1381) · `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (MODIFY, +1 key ~3 LOC — `placa_formato_invalido` con string literal verbatim plan.md:1366) | `feat(operacion): adicionar detectarTipoVehiculo() estricto + 6 unit tests + i18n key placa_formato_invalido (HU-F4.1-T1+T3)` | G1, G2, G3, G4 |
| **T2 — `useTiposVehiculo()` hook SWR + `tiposVehiculoApi` wrapper + `useTiposVehiculo.test.ts` 5 unit tests** | ~160 (110 prod + 50 tests) | `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` (NEW, ~30 LOC — `getTiposVehiculo()` wrapper con parkosFetch + mapeo 404 → [] + filtro tipo null) · `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (NEW, ~80 LOC — SWR hook + HARDCODED_CATALOG constante inline) · `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.test.ts` (NEW, ~50 LOC — U7..U11) | `feat(catalogos): adicionar useTiposVehiculo() SWR + fallback hardcoded {auto,moto} + 5 unit tests (HU-F4.1-T2)` | G1, G2, G3, G5 |
| **TOTAL** | **~293 LOC** (163 prod + 130 tests + i18n) | 5 archivos nuevos + 1 modificación | 2 commits atómicos | 5+2 gates (G6 + G7 forward coverage / SKIPPED-env) |

**Resumen de budgets**:

| Task | Production LOC | Tests LOC | Total |
|---|---|---|---|
| T1 detectarTipoVehiculo + placa.test | 50 | 80 | 130 |
| T2 useTiposVehiculo + api + tests | 110 | 50 | 160 |
| T3 i18n key | 3 | 0 | 3 |
| **TOTAL** | **163** | **130** | **293** |

Plan 250 LOC production matches verbatim (~163 production + ~127 tests + ~3 i18n + rounding = ~293 LOC). Resolución I1: el "100 LOC" del plan.md:1383 cubre T1 sola (`detectarTipoVehiculo` puro); el budget total real es ~250 LOC production si se cuentan T1+T2+T3 con tests (~293 total).

---

## 9. Acceptance gates (G1..G7)

7 gates que deben pasar ANTES de mergear F4.1 a `origin/dev`. Los gates G1..G5 son source-level (unit tests + typecheck + lint + atomic commits + SWR config); G6 + G7 son forward coverage / sandbox deviation documentada (no F4.1 scope).

| # | Gate | Mecanismo | Source | Anchor REQ-OPS |
|---|---|---|---|---|
| G1 | TypeScript strict sin errores (`tsc -b`) | `npm run typecheck` exit 0 en `apps/electron-sucursal/` (TODOS los archivos NEW compilan) | T1 + T2 | REQ-OPS-125, -127, -128 |
| G2 | ESLint sin errores (`--max-warnings 0`) | `npm run lint` exit 0 (sin warnings en placa.ts + useTiposVehiculo.ts + tiposVehiculoApi.ts) | T1 + T2 | (regla global, no REQ-OPS anclada) |
| G3 | 11 unit tests verde (`vitest run`) | `npm test` exit 0 con 6 placa (U1..U6) + 5 useTiposVehiculo (U7..U11) — cobertura ≥90% líneas / 80% branches | T1 + T2 | REQ-OPS-125, -127 |
| G4 | Atomic commits (2 commits C1 + C2 con tests incluidos) | `git log --oneline` muestra 2 commits siguiendo Conventional Commits sin Co-authored-by AI (prohibido per AGENTS.md) | T1 + T2 + T3 | (regla global, no REQ-OPS anclada) |
| G5 | SWR key null-when-no-token (decisión F3.3 preservada) | U7 verifica `swrKey === null` cuando `useAuthStoreMock.mockReturnValue(null)`; U11 verifica `useAuthStore.getState().clear()` + dispatch `parkos:auth:cleared` cuando `onError(401)` | T2 | REQ-OPS-127 |
| G6 | WCAG 2.1 AA axe-core 0 violaciones en componente que consume F4.1 | F4.1 NO entrega componente UI — G6 aplica al forward consumer F6.1 `<PlacaInput>` consuming `detectarTipoVehiculo()` + `t('operacion.placa_formato_invalido')`. axe-core scan en F6.1 forward. Documentado como forward coverage (no F4.1 scope). | forward F6.1 | REQ-OPS-130 |
| G7 | e2e sandbox F.6 SKIPPED-env (`npm 11.16.0`) | F4.1 NO entrega e2e — los 11 unit tests cubren la lógica. e2e (Playwright) aplica a F6.1 `<PlacaInput>` cuando exista el componente UI. SKIPPED-env per F.6 precedent — deviation D-env en `verify-report.md` futuro (no project defect). | precedent F2.x + F3.x + sandbox F.6 | (no REQ-OPS anclada — sandbox limitation) |

**Estado pre-flight**: 0/7 PASS al inicio (no implementado). Target 5/7 PASS post-implementación (G1, G2, G3, G4, G5 verde); G6 + G7 documentados como forward coverage / SKIPPED-env (no F4.1 scope, sandbox limitation). Cobertura de tests ≥90% líneas / 80% branches per D9.

**Sandbox F.6 caveat**: G6 + G7 documentados como deviation D-env en `verify-report.md` futuro (precedent F2.x + F3.x archive). NO project defect.

---

## 10. Risks y mitigaciones

| # | Risk | Severity | Mitigación |
|---|---|---|---|
| **R1** | **Regex strictness incorrecto** — un edge case (ej: placa con guion `ABC-123`) hace que la detección falle cuando el operador espera que pase. | MEDIUM | DEC-F4.1-02: normalización previa (trim + uppercase + remove whitespace) ANTES de regex cubre los casos comunes (espacios en cualquier posición). `replace(/\s+/g, '')` remueve TODO whitespace (espacios + tabs + linebreaks), pero NO caracteres no-espacio como `-`. Si el operador tipea `ABC-123`, el guion persiste y el regex NO matchea → `null` → error inline i18n. Plan.md:1366-1367 explícito: si formato no matchea, error inline + campo abierto para corrección. Sin tolerancia de tipeo (DEC-SUC-22). Si el negocio reporta falsos negativos, se agrega como bug fix futuro con un test de regresión. |
| **R2** | **Backend regex duplicada desincronizada** — el cliente detecta `Auto` para `ABC123`, pero el backend server-side `detectar_tipo_vehiculo()` usa regex ligeramente distinta y rechaza el POST (`operacion.py:261` overwrites via V5 — el "regex-derived UUID wins over client value"). | LOW | A-03 verbatim (plan.md:454): cliente y backend tienen regex idéntica (Auto `^[A-Z]{3}[0-9]{3}$`, Moto `^[A-Z]{3}[0-9]{2}[A-Z]$`). JSDoc de `detectarTipoVehiculo()` referencia explícitamente `operacion.py:215-277` para mantenerlas sync. Si divergen, es bug a corregir. El cliente NO es source of truth — el backend siempre re-valida (defense in depth XR6 layer 4). Para evitar divergencia silenciosa, F4.1 entrega U3 (formato inválido) que verifica `null` return, alineado con la impl backend de `detectar_tipo_vehiculo()`. |
| **R3** | **SWR fallback staleness** — la API de catálogos está down, SWR muestra fallback hardcoded `{auto, moto}`, el operador asume que el catálogo está completo cuando en realidad faltan tipos (ej: cuando se agregue Bicicleta en el futuro). | LOW | DEC-F4.1-06: hook retorna `isFromFallback: boolean`. F6.x+ consumers pueden mostrar `<Tooltip>` o badge sutil "datos locales". F4.1 NO requiere esta UI — solo expone el flag. Si API vuelve, SWR revalida automáticamente (refresh on focus / on reconnect per SWR default behavior). Plan.md:1375 verbatim "fallback a un catálogo hardcoded de {auto, moto}" explícitamente documenta la degradación esperada. |
| **R4** | **Missing types de retorno** — TypeScript strict requiere tipos explícitos, pero la función retorna `'Auto' \| 'Moto' \| null` y un caller podría olvidar el `null` check, haciendo que la detección falle silenciosa en runtime. | LOW | DEC-F4.1-01: tipo de retorno explícito con union literals. Tests U3 (formato inválido) + U4 (placa vacía) verifican explícitamente `null`. El caller DEBE manejar `null` (TypeScript strict no compila sin narrowing). En F6.1 `<PlacaInput>`, el caller hace `if (tipo === null) { /* error inline */ } else { /* setea uuid */ }`. |
| **R5** | **Test edge cases faltantes** — los 6 tests plan.md:1381 no cubren todos los branches posibles (ej: placa con caracteres especiales `ABC@12`, placa con length >6 para Moto `ABC1234D`). | LOW | DEC-F4.1-10: 6 tests + 5 hook tests cubren ≥90% líneas / 80% branches per D9. Los branches no cubiertos son "placa claramente inválida que NUNCA matchearía ninguna regex real" — no son casos de uso reales. Si el operador digita `ABC@12`, el regex NO matchea → `null` → error inline. Branch cubierto por el path "no match" general. Si el reporte de bugs del operador revela casos faltantes, se agregan tests de regresión en PR futuro. |

**Riesgos cerrados**: 5/5 con mitigación explícita. **0 KNOWN-MISSING**.

**Sandbox F.6 deviation esperada**: e2e (G6) + axe-core runtime (G7) documentados como deviations D-env en `verify-report.md` futuro (precedent F2.x + F3.x archive). NO project defect.

---

## 11. Dependencies

### 11.1 Shipped (F1.x + F2.1 + F2.2 + F3.1 + F3.2 + F3.3 — prerequisites)

- **HU-F1.x** ✅ closed Fase 1: `detectar_tipo_vehiculo()` server-side shipped en `operacion.py:215-277` (defense in depth XR6 layer 4). `GET /api/v1/catalogos/tipos-vehiculo` C+Q+U router shipped (`catalogos.py:140-147` con `_CATALOG_DEFAULTS:101` permission `config_catalogo`).
- **HU-F2.1** ✅ closed Fase 2: Electron 30 skeleton + shadcn Form/Input/Button + i18n 7 namespaces + axe-core + playwright e2e.
- **HU-F2.2** ✅ closed Fase 2: `parkosFetch` (retry + refresh-once 401 via Mutex + Idempotency-Key) + bridge IPC + `authStore` Zustand + `useAuth` SWR.
- **HU-F3.1** ✅ closed 2026-09-15: Login page + LoginForm + loginApi + loginSchema + ruta `/login` + 7 REQ-OPS-106..112.
- **HU-F3.2** ✅ closed 2026-09-15: Lockout countdown + refresh 50min + pre-flight gate + 6 REQ-OPS-113..118.
- **HU-F3.3** ✅ closed 2026-09-15: Abrir/Cerrar turno + `useSesionActiva()` SWR + 6 REQ-OPS-119..124 + 4 atomic commits + 4 e2e scenarios.

### 11.2 Precondiciones verificadas (pre-flight §3 exploration)

| # | Precondición | Status |
|---|---|---|
| P1 | `parkosFetch` con retry + refresh-once 401 + Idempotency-Key shipped | ✅ shipped F2.2 |
| P2 | `useAuthStore` Zustand + `clear()` + `parkos:auth:cleared` event shipped | ✅ shipped F2.2 |
| P3 | `useSesionActiva` SWR pattern (key null-when-no-token + dedupingInterval + shouldRetryOnError + onError 401 → clear + event) | ✅ shipped F3.3 verbatim |
| P4 | `vitest` + `@testing-library/react` + `jsdom` instalado | ✅ shipped F2.1 |
| P5 | `operacion.json` namespace registrado en `i18n/index.ts` con 10 keys pre-F4.1 | ✅ shipped F2.1 |
| P6 | vitest alias `@/` → `src/renderer` configurado | ✅ shipped F2.1 |
| P7 | Backend `detectar_tipo_vehiculo()` server-side shipped (defense in depth) | ✅ shipped HU-F1.x (`operacion.py:215-277`) |
| P8 | Backend `GET /api/v1/catalogos/tipos-vehiculo` shipped | ✅ shipped F3.0 (`catalogos.py:140-147` con `_CATALOG_DEFAULTS:101` permission `config_catalogo`) — **I2 RESUELTA en propose phase** |
| P9 | Backend `TiposVehiculoRead` schema con `uuid, tipo, vigente_desde, vigente_hasta, estado, ...` | ✅ shipped F3.0 (`schemas/tipos_vehiculo.py:13-23`) |
| P10 | `useSesionActiva` precedent verbatim (key null-when-no-token + dedupingInterval + 401 clear) | ✅ shipped F3.3 — F4.1 replica verbatim en `useTiposVehiculo` |

### 11.3 NO requiere (out of dependencies)

- **Backend cambios**: F4.1 NO modifica backend. Todos los endpoints + permission + schema ya shipped (verificación I2 resuelta).
- **Nuevas dependencies npm**: F4.1 NO requiere `npm install`. `react@^18.3.1` + `swr@^2.2.5` + `vitest@^2.1.2` + `@testing-library/react@^16.0.1` ya shipped.
- **Nuevos namespaces i18n**: `operacion.json` suficiente. 1 key agregada al namespace existente.
- **Nuevos componentes shadcn**: F4.1 no entrega componente UI. F6.1 lo hará.
- **Cambios en IPC bridge**: F4.1 NO agrega métodos IPC.
- **Migraciones Alembic**: ninguna tabla ni columna nueva.
- **Nuevas routes en `App.tsx`**: F4.1 NO agrega rutas. F6.1 las agregará.

### 11.4 Forward dependencies (F4.x/F6.x+ consume F4.1 outputs)

- **HU-F4.2** (Tarifas vigentes): entrega `useTarifasVigentes` en el mismo feature `catalogos`. Peer de `useTiposVehiculo`. F4.2 entrega independientemente (forward hook — no F4.1 scope).
- **HU-F4.3** (Ocupación en vivo): `<OcupacionStrip>` itera sobre tipos del catálogo para renderizar `Auto: 23/50` por tipo. `useTiposVehiculo()` provee la lista. F4.3 puede implementar su propio fetch si quiere (peer pattern). Forward F4.1 → F4.3.
- **HU-F6.1** (Ingreso vehicular CU-01): `<PlacaInput>` consume `detectarTipoVehiculo()` directamente + `useTiposVehiculo()` para nombre/UUID. HU crítica — sin F4.1, F6.1 no puede arrancar. `pending.md §5` forward hooks explícito.
- **HU-F7.x** (Salida + cálculo tarifa CU-02/03): depende de F6.x. `buscarIngresoTolerante()` función DISTINTA (Fase 7) con tolerancia `O↔0`/`I↔1`/`B↔8`. DEC-SUC-22 categórico: NUNCA compartir función con F4.1.
- **HU-F11.x** (sync UI): si sync incluye `tipos_vehiculo`, el hook debe invalidarse post-sync. `mutate('/catalogos/tipos-vehiculo')` post-sync event (forward — no F4.1 scope).

---

## 12. Forward hooks (Fase 4+ consumer map)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F4.2** (Tarifas vigentes) | `useTarifasVigentes()` peer hook en mismo feature `catalogos` | Mismo patrón SWR token-gated + dedupingInterval + fallback (en este caso electron-store, NO hardcoded). F4.2 entrega independientemente (peer con F4.1). |
| **HU-F4.3** (Ocupación en vivo) | `<OcupacionStrip>` itera sobre tipos del catálogo | `useTiposVehiculo()` provee la lista de tipos. F4.3 puede implementar su propio fetch si quiere (peer pattern). |
| **HU-F6.1** (Ingreso vehicular CU-01) | `<PlacaInput>` consume `detectarTipoVehiculo()` + `useTiposVehiculo()` + `REGEX_AUTO` + `REGEX_MOTO` | Llama `detectarTipoVehiculo(placa)` → si `null` muestra `<p role="alert" aria-describedby>{t('operacion.placa_formato_invalido')}</p>`; si `'Auto' \| 'Moto'` setea `uuid_tipo_vehiculo` (= `tipos.find(t => t.tipo === ...).uuid`) para POST. Las constantes `REGEX_AUTO` + `REGEX_MOTO` se reusan en `z.string().regex(REGEX_AUTO)`. CRÍTICO — sin F4.1, F6.1 no puede arrancar. |
| **HU-F7.x** (Salida + búsqueda tolerante CU-02/03) | `buscarIngresoTolerante()` función DISTINTA en archivo NUEVO | DEC-SUC-22 categórico: NUNCA compartir función con F4.1. F7.x entrega función NUEVA con tolerancia `O↔0`/`I↔1`/`B↔8`. |
| **HU-F11.x** (sync UI + alertas CU-07/14) | Si sync incluye `tipos_vehiculo`, el hook debe invalidarse post-sync | `mutate('/catalogos/tipos-vehiculo')` post-sync event (forward — no F4.1 scope). |
| **HU-F6.1** `<PlacaInput>` WCAG | `aria-describedby={t('operacion.placa_formato_invalido')}` + `<p role="alert">` | F4.1 entrega la i18n key + la función que detecta. F6.1 entrega el componente que las compone con axe-core compliance. |

---

## 13. Trade-offs y alternatives considered

### 13.1 Función pura con normalización vs regex tolerante (DEC-F4.1-02)

**Trade-off**: Normalización previa (chosen) requiere código adicional (3 líneas de transformación) pero permite regex estricta. Regex tolerante (rejected) mete tolerancia en la regex misma.

**Decisión**: Normalización previa. Regex estricta es principio BR2 + DEC-SUC-22; la normalización es TRIVIAL (whitespace, no caracteres). Si aceptáramos regex tolerante, aceptamos `O` ↔ `0` en `ABC12O` → falla. Eso ES tolerancia de tipeo, NO whitespace.

### 13.2 Regex hardcoded cliente vs columna DB (DEC-F4.1-03 / A-03)

**Trade-off**: Regex hardcoded en código cliente (chosen) evita migración DB + mantiene 4NF canon. Columna DB en `prod.tipos_vehiculo` (rejected) permitiría admins cambiar regex sin redeploy.

**Decisión**: Hardcoded cliente. A-03 explícito: "no hay respaldo en el corpus de CU para un tercer patrón". Si el negocio cambia, es decisión de producto explícita + redeploy coordinado de cliente + backend. Forward extensibilidad: cuando haya 4+ tipos, se reconsidera columna DB.

### 13.3 Fallback hardcoded vs electron-store persistente (DEC-F4.1-05)

**Trade-off**: Fallback hardcoded `{auto, moto}` (chosen) es simple, cubre Auto+Moto, NO persiste entre sesiones. electron-store persistente (rejected para F4.1, pero F4.2 lo usa para tarifas) persiste entre sesiones.

**Decisión**: Hardcoded para F4.1. Catálogos cambian raramente (reference data). Si API down + kiosko reboot, fallback sigue disponible (constante en el bundle JS). electron-store es para datos transaccionales (F4.2 tarifas con cálculos derivados).

### 13.4 `isFromFallback` flag derivado de referencia vs derivación desde error (DEC-F4.1-06)

**Trade-off**: `data === HARDCODED_CATALOG` (chosen) es true source of truth vía comparación referencial. Derivación desde `error` (rejected) es aproximado pero incorrecto para 404.

**Decisión**: Comparación referencial. `HARDCODED_CATALOG` es constante módulo-level exportada — la misma referencia se inyecta en SWR fallback y se compara en el return. Si API 404 → SWR inyecta fallback → `data === HARDCODED_CATALOG` → `isFromFallback === true`. Si API 200 OK con la misma data del HARDCODED, NO son la misma referencia → `isFromFallback === false`. Correcto.

### 13.5 2 commits C1+C2 vs 3 commits T1/T2/T3 o 1 monolítico (DEC-F4.1-08)

**Trade-off**: 2 commits (chosen) agrupa por deliverable cohesivo: detección de placa (T1+T3 juntos) + catálogo de tipos (T2 solo). 3 commits separados (rejected) parten deliverables cohesivos (T1 sin T3 = función sin mensaje de error). 1 monolítico (rejected) >400 LOC = review cognitiva pesada.

**Decisión**: 2 commits. Work-unit-commits skill F2.x + F3.x verbatim. C1 cubre detección cliente + i18n (forward F6.1 consume); C2 cubre catálogo SWR (forward F4.3 + F6.1 consumen). Tests incluidos con código.

### 13.6 e2e sandbox F.6 SKIP vs CI override

**Trade-off**: SKIP-env (chosen, F2.x + F3.1 + F3.2 + F3.3 precedent) evita CI rotura pero deja e2e sin coverage local. CI override requiere Docker + npm compatible image.

**Decisión**: SKIP-env documentado como deviation D-env en `verify-report.md`. Unit tests SÍ corren (11 verde). Si CI migra a npm 11.16+ e2e verde — pero F4.1 NO entrega e2e (forward F6.1 sí).

### 13.7 Tipos de retorno `'Auto' | 'Moto' | null` vs enum TypeScript

**Trade-off**: Union literals (chosen) mejor tree-shaking + mejor type narrowing. Enum TypeScript (rejected) emite object en runtime + tree-shaking worst.

**Decisión**: Union literals. Precedent F2.x + F3.x verbatim.

### 13.8 Tolerancia de tipeo `O↔0`/`I↔1`/`B↔8` en `detectarTipoVehiculo` vs NO (DEC-SUC-22)

**Trade-off**: Tolerancia (rejected) facilitaría UX operador (auto-corrección de tipeo) pero viola DEC-SUC-22 categórico. Sin tolerancia (chosen) requiere corrección manual del operador.

**Decisión**: Sin tolerancia. DEC-SUC-22 verbatim "detección estricta y sin tolerancia de tipeo". La tolerancia es exclusiva de `buscarIngresoTolerante()` (Fase 7). Si operador tipea `ABC12O` (con O al final), la detección falla → error inline → corrige. UX kiosko espera este feedback inmediato vs falso positivo silencioso.

### 13.9 Componente UI en F4.1 vs NO (forward F6.1)

**Trade-off**: Componente UI en F4.1 (rejected) ataría la HU al flujo de ingreso + requeriría e2e + axe-core scan runtime. NO componente UI (chosen) deja F4.1 como lógica pura + e2e + axe-core aplica a F6.1.

**Decisión**: NO componente UI. F4.1 = lógica pura (función + hook + i18n). F6.1 = componente UI que las consume + e2e + axe-core.

---

## 14. Precedents

| Precedent | Aplicación F4.1 | Source |
|---|---|---|
| **F3.3 (Abrir/Cerrar turno)** | Container/Presentational split + Zod local + i18n keys + 401 anti-enumeration + e2e axe-core pattern + `useSesionActiva` SWR hook verbatim — F4.1 replica el SWR pattern en `useTiposVehiculo` con deduping 5min en vez de 10s | `openspec/changes/archive/2026-09-15-hu-f3-3-abrir-cerrar-turno/` |
| **F3.2 (Lockout visible + refresh transparente)** | SWR token-gated pattern + `REFRESH_INTERVAL_MS` export + `parkos:auth:cleared` event + REFRESH_INTERVAL_MS constante — F4.1 replica el evento en onError 401 → clear | `openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/` |
| **F3.1 (Login email+password)** | `LoginForm` RHF+Zod + container/presentational split + 7 REQ-OPS-106..112 user-facing DELTA — F4.1 NO consume directamente (forward F6.1 Zod usa las constantes regex exportadas) | `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/` |
| **F2.2 (parkosFetch + authStore + useAuth)** | Mutex singleton preserved + refresh-once 401 invariant + SWR config baseline — F4.1 replica el patrón F3.3 useSesionActiva verbatim | `apps/ui-kit/src/{fetch/parkosFetch.ts, store/authStore.ts, hooks/useAuth.ts}` |
| **F2.1 (Electron skeleton + shadcn)** | vitest + @testing-library/react + axe-core + playwright e2e pattern + i18n 7 namespaces — F4.1 NO usa shadcn directamente (NO componente UI), pero la infra de testing SÍ | `apps/electron-sucursal/src/renderer/components/ui/` + `e2e/a11y/wcag-2.1-aa.spec.ts` |
| **F1.x (Backend catalogos + detectar_tipo_vehiculo)** | `GET /api/v1/catalogos/tipos-vehiculo` C+Q+U router (`catalogos.py:140-147` con `_CATALOG_DEFAULTS:101` permission `config_catalogo`) + `detectar_tipo_vehiculo()` server-side (`operacion.py:215-277` defense in depth XR6 layer 4) — F4.1 cliente consume vía parkosFetch sin modificar backend | `backend/.../api/v1/catalogos.py` + `backend/.../api/v1/operacion.py:215-277` + `backend/.../schemas/tipos_vehiculo.py` |
| **F1.15 (login histórico)** | DELTA precedent (user-facing behavior in spec) → F4.1 emite 6 new REQ-OPS-125..130 — sigue precedent F1.15 + F3.1 + F3.2 + F3.3 verbatim | `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/specs/operations/spec.md` |
| **DEC-SUC-22** | Detección estricta sin tolerancia → F4.1 función pura sin tolerancia de tipeo (normalización whitespace-only, NO caracteres alfanuméricos similares) | `plan.md:437` |
| **DEC-SUC-12** | Cálculo server-side, cliente solo muestra → F4.1 cliente detecta (UX rápido + feedback inmediato) + backend re-valida (`operacion.py:261` overwrites via V5 — defense in depth XR6 layer 4) | `plan.md:419` |
| **DEC-SUC-03** | Refresh transparente 50min + pre-flight gate antes de escrituras críticas — F4.1 NO requiere pre-flight porque `/catalogos/*` GET es read idempotente. F4.1 NO agrega refreshInterval porque catálogos son reference data (5min deduping suficiente). | `plan.md:418` |
| **A-03** | Regex hardcoded en `src/lib/validation/placa.ts` del cliente (NO columna del ER) — F4.1 implementa verbatim con JSDoc referencia a `operacion.py:215-277` backend counterpart | `plan.md:454` |
| **BR2 de CU-01** | Autodetección por regex es la ÚNICA fuente válida; NO hay override manual del cajero — F4.1 NO entrega `<Select>` ni `<RadioGroup>` para tipo. JSDoc de `detectarTipoVehiculo` cita BR2 verbatim. | `plan.md:1369` |
| **DEC-F3.3-08 verdict** | F3.3 ES user-facing → spec delta materialized. F4.1 replica el precedent DELTA con 6 new REQ-OPS-125..130 (cuarto DELTA en Fase 3+4 después de F1.15 + F3.1 + F3.2 + F3.3). | `openspec/changes/archive/2026-09-15-hu-f3-3-abrir-cerrar-turno/proposal.md` |

### 14.1 DEC-F4.1-07 + DEC-F4.1-11 verdict ratificación

F4.1 ES user-facing behavior observable en cuatro dimensiones: (a) autocompletar tipo al digitar placa — operador NO selecciona manualmente (interacción observable); (b) mensaje inline "Placa no coincide con ningún formato conocido" si regex no matchea (feedback observable); (c) catálogo cargado desde API con fallback hardcoded `{auto, moto}` (degradación observable si API down); (d) detección pura sin estado visible + i18n key pre-poblada con mensaje UX (consumible por F6.1 `<PlacaInput>` con `role="alert"` y `aria-describedby`).

Per F1.15 + F3.1 + F3.2 + F3.3 precedent, user-facing ⇒ spec delta materialized. F4.1 emite 6 new REQ-OPS-125..130 en `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/specs/operations/spec.md` siguiendo Given/When/Then/And RFC 2119 format F1.15 + F3.x verbatim.

F2.x NO-OP precedent (DEC-ELEC-10, DEC-FETCH-10, DEC-UPD-13) NO aplica a F4.1 — esos HU son infra-only sin behavior visible al operador. F4.1 ES UI + UX behavior (forward F6.1), sigue el precedent DELTA de F3.x.

---

## 15. DoD checklist (preliminar)

- [ ] 2 atomic commits landed (`feat(operacion): detectarTipoVehiculo() + tests + i18n`, `feat(catalogos): useTiposVehiculo() + tests`).
- [ ] 6 new REQ-OPS-125..130 materializadas en `openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/specs/operations/spec.md` (sdd-spec phase).
- [ ] Given/When/Then/And format RFC 2119 per F1.15 + F3.1 + F3.2 + F3.3 precedent verbatim.
- [ ] Anchor links explícitos a DEC-F4.1-NN ratificados en §4.
- [ ] 7 acceptance gates: G1 + G2 + G3 + G4 + G5 PASS source-level; G6 + G7 forward coverage / SKIPPED-env documentado como D-env per F.6 precedent.
- [ ] 11 unit tests verde (6 placa U1..U6 + 5 useTiposVehiculo U7..U11) con cobertura ≥90% líneas / 80% branches per D9.
- [ ] `detectarTipoVehiculo()` función pura exportada desde `lib/validation/placa.ts` consumible por F6.x `<PlacaInput>` (forward hook crítico).
- [ ] Constantes `REGEX_AUTO` + `REGEX_MOTO` exportadas consumibles por F6.x Zod (`z.string().regex(REGEX_AUTO)`).
- [ ] `useTiposVehiculo()` hook exportado desde `features/catalogos/hooks/useTiposVehiculo.ts` consumible por F4.3 + F6.1.
- [ ] `tiposVehiculoApi` typed wrapper exportado consumible por futuro forward hook.
- [ ] `HARDCODED_CATALOG` constante módulo-level exportada (peer pattern para F4.2).
- [ ] i18n `operacion.json` agrega 1 key `placa_formato_invalido` con string literal verbatim plan.md:1366 — snapshot test verde.
- [ ] `useAuthStore.clear()` invariante preservado (F2.2 DEC-FETCH-03 invariant intacto) — U11 verifica.
- [ ] `parkosFetch` pre-flight gate NO modificado (DEC-F3.3-10 precedent — `/catalogos/*` GET read idempotente NO requiere pre-flight).
- [ ] TypeScript strict compliance — `tsc -b` exit 0 con `strict: true` (F2.1 baseline).
- [ ] 0 KNOWN-MISSING (pre-flight 10/10 PASS exploration §3 + I2 RESUELTA en propose phase con verificación `catalogos.py:140-147`).
- [ ] Author: `Parkos Dev <dev@parkos.local>` (F2.1 + F3.1 + F3.2 + F3.3 verbatim precedent).
- [ ] Conventional commits sin Co-authored-by, sin AI trailers (prohibido per AGENTS.md canon).
- [ ] Numeración REQ-OPS monotónica verificada (REQ-OPS-124 vigente post-F3.3; F4.1 ocupa REQ-OPS-125..130, 0 gaps).
- [ ] READ-ONLY anchors respetados: backend `catalogos.py` + `operacion.py` + `schemas/tipos_vehiculo.py`, electron main/preload/bridge, `apps/ui-kit/src/{cn,tokens,store/authStore,fetch/parkosFetch,hooks/useAuth}.ts` (except read), `apps/electron-sucursal/electron/*`, `i18n/index.ts`, `modelo_datos_er.mmd`, `plan.md`.
- [ ] Sandbox F.6 caveat documentado en §10 + §15 como deviation esperada D-env (e2e + axe-core runtime SKIPPED-env), NO project defect.
- [ ] JSDoc de `detectarTipoVehiculo()` referencia verbatim DEC-SUC-22 + A-03 + BR2 + `operacion.py:215-277` backend counterpart (mantener sync cliente-backend).
- [ ] `useTiposVehiculo` SWR config documentada verbatim DEC-F4.1-04 (deduping 5min) + DEC-F4.1-05 (fallback hardcoded) + DEC-F4.1-06 (isFromFallback flag).
- [ ] Verificación backend (I2 resuelta en propose): `GET /api/v1/catalogos/tipos-vehiculo` C+Q+U router shipped F3.0 con `_CATALOG_DEFAULTS:101` permission `config_catalogo`. `detectar_tipo_vehiculo()` server-side shipped HU-F1.x (`operacion.py:215-277`).

---

## 16. Open questions

**Resoluciones de inconsistencies detectadas en exploration §1**:

1. **I1 — LOC budget**: `plan.md:1383` dice "Tamaño estimado: 100 LOC" pero las 3 tareas atómicas (T1 + T2 + T3 con tests) suman ~293 LOC total. La cifra 100 LOC cubre solo T1 (`detectarTipoVehiculo` puro). **Resolution** (cerrada en §8): el budget total real es ~293 LOC (T1 ~130 + T2 ~160 + T3 ~3). El "100 LOC" del plan.md se interpreta como producción neta de T1 (no incluye T2 hook + T3 tests).

2. **I2 — Backend `GET /catalogos/tipos-vehiculo` verificación**: `plan.md:1375` menciona el endpoint pero la verificación final se delega a `sdd-propose`. **Resolution** (cerrada en §11.2 precondición P8): el endpoint existe, shipped F3.0 (`catalogos.py:140-147` con `_CATALOG_DEFAULTS:101` permission `config_catalogo`). C+Q+U router via `make_router` con `repo_kind='versioned'` (forward permite F4.x modificar tipos vía POST/PUT — F4.1 cliente NO modifica, solo lee). **NO requiere fallback hardcoded como degradación primaria** — el fallback `{auto, moto}` está como safety net per plan.md:1375 pero la API normalmente responde 200 OK.

3. **I3 — `dedupingInterval` 5min para catálogos**: `plan.md:1375` menciona "SWR, `dedupingInterval: 5*60*1000`" — 5min literal. **Resolution** (cerrada en DEC-F4.1-04): 5min (300_000ms) confirmado. Más agresivo que `useSesionActiva` 10s porque catálogos son reference data que cambian raramente; 5min evita refetch cada vez que se monta un componente que lo consume.

4. **I4 — Mensaje i18n literal**: `plan.md:1365` define mensaje de error inline "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)". El backend NO envía este mensaje — es decisión 100% cliente. **Resolution** (cerrada en T3): i18n key `operacion.placa_formato_invalido` con el string literal verbatim (sin variables), namespace pre-existente `operacion.json`.

5. **I5 — Verificación `tiposVehiculoApi` shape backend** (NUEVA en propose phase): ¿backend `TiposVehiculoRead` tiene shape exacta matching interface TypeScript? **Resolution** (cerrada en DEC-F4.1-09): shape verificada contra `schemas/tipos_vehiculo.py:13-23`. Interface TypeScript: `{uuid: string, tipo: string | null, vigente_desde: string, vigente_hasta: string | null, estado: string, created_at: string, created_by: string | null, sync_status: string | null}`. Filtro defensivo descarta filas con `tipo: null` (sucursal con tipos corruptos). Mapeo 404 → `[]` preservado en el wrapper.

**Notas para `sdd-verify`**:

- **N1**: tsc clean post-C1+C2 — verificar que `apps/electron-sucursal/tsconfig.*` compila sin errores después de agregar `placa.ts` + `tiposVehiculoApi.ts` + `useTiposVehiculo.ts`. TypeScript strict con union literals `'Auto' | 'Moto' | null` requiere narrowing explícito en callers (F6.1).
- **N2**: vitest 11 tests verde con cobertura ≥90% líneas / 80% branches per D9. Verificar que los 6 tests placa cubren todos los branches (incluyendo normalización whitespace + empty string) y los 5 tests hook cubren SWR config (key null, fetch OK, fallback, dedup, 401 clear).
- **N3**: U11 mock SWR mock module — verificar que el mock de `useAuthStore` permite inspeccionar `useAuthStore.getState().clear()` calls + verificar `window.dispatchEvent` calls con `'parkos:auth:cleared'`. Si vitest jest-dom + jsdom 25.x requiere mock adicional para `window`, ajustar el setup.
- **N4**: parkosFetch 404 mapping — verificar que `tiposVehiculoApi.getTiposVehiculo()` retorna `[]` cuando 404 (no propaga error). El filter `tipo !== null` se aplica después del 404 check para no descartar filas válidas accidentalmente.
- **N5**: JSDoc compliance — verificar que el JSDoc de `detectarTipoVehiculo()` cita verbatim DEC-SUC-22 + A-03 + BR2 + `operacion.py:215-277` backend counterpart. Esto es crítico para mantener sincronización cliente-backend cuando el negocio cambie regex (forward hook).

**0 KNOWN-MISSING** (pre-flight 10/10 PASS + 0 KNOWN-MISSING en exploration §16 + 5 inconsistencies I1..I5 resueltas en propose §16). Items N1..N5 son verificaciones standard en `sdd-verify`, NO blockers.

---

## CHANGELOG

- (2026-09-16) F4.1 propose phase complete — 16 secciones + CHANGELOG, 11 DEC-F4.1-01..11 (DEC-F4.1-11 NUEVA, esta proposal), 5 riesgos R1..R5 (subset de exploration §9 con focus top-5), 7 acceptance gates G1..G7, 3 atomic tasks T1..T3, 1 cluster C1. Numeración REQ-OPS monotónica verificada: REQ-OPS-124 vigente post-F3.3 archive; F4.1 ocupa REQ-OPS-125..130 (6 new requirements, 0 gaps). Pre-flight 10/10 PASS + 0 KNOWN-MISSING. **I2 RESUELTA en propose phase** con verificación `catalogos.py:140-147` (`_mount_catalog(resource="tipos-vehiculo", ...)` con `_CATALOG_DEFAULTS:101` permission `config_catalogo`) — endpoint `GET /api/v1/catalogos/tipos-vehiculo` C+Q+U router SHIPPED F3.0. Backward endpoint `detectar_tipo_vehiculo()` server-side ya shipped HU-F1.x (`operacion.py:215-277`) defense in depth XR6 layer 4. DEC-F4.1-07 + DEC-F4.1-11 verdict = **DELTA** (F4.1 IS user-facing forward: `detectarTipoVehiculo` autocompleta + i18n key pre-poblada para F6.1 `<PlacaInput>` + catálogo con fallback degradado + defense in depth XR6). 5 inconsistencies (I1 LOC budget I2 endpoint verificación I3 deduping 5min I4 i18n literal I5 backend shape verification) cerradas en DEC-F4.1-01..11 + §11.2 precondiciones + §16 open questions. Sandbox F.6 deviation esperada documentada en §10 + §15 (G6 axe-core runtime + G7 e2e SKIPPED-env, NO project defect, ambos forward coverage F6.1). Precedente directo: F3.3 archivado 2026-09-15 con 6 REQ-OPS-119..124 user-facing DELTA — F4.1 replica pattern con 6 REQ-OPS-125..130 (cuarto DELTA en Fase 3+4 después de F1.15 + F3.1 + F3.2 + F3.3, primer DELTA de Fase 4). Ready for `sdd-spec` + `sdd-design` (paralelo).

---

**End of proposal — HU-F4.1.**
