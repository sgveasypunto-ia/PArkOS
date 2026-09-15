# Delta Spec: operations — HU-F2.3 (Auto-actualización electron-updater + single-instance lock + kiosko PIN bcrypt + api-status polling + electron-log rotación + StatusBar aria-live polite)

> **Change**: `hu-f2-3-electron-auto-update-kiosko`
> **Capability**: operations
> **Phase**: spec (sdd-spec)
> **Status**: ready for sdd-design (parallel) + sdd-tasks
> **Date**: 2026-09-15
> **Author**: Parkos Dev <dev@parkos.local>

## 1. Delta Summary

**No new REQ added by this change.** Per **DEC-UPD-13** (proposal.md §5.13), F2.3 es infraestructura de runtime — mismo razonamiento que F2.1 DEC-ELEC-10 y F2.2 DEC-FETCH-10. Las 13 decisiones arquitectónicas DEC-UPD-01..13 en proposal.md §5 cargan el mismo peso RFC 2119 que las REQs. No se introducen endpoints HTTP nuevos (el `/health` polling consume un endpoint hipotético que degrada gracefully a 🔴), no se agregan tablas/migraciones, no se modifican filas del sync_catalog, no se conceden permisos RBAC. El behavior contract implícito reside en los 8 acceptance gates G1..G8 (proposal.md §11) ejecutados por vitest + playwright + axe-core.

## 2. Affected Capabilities

| Capability | Action | Reason |
|---|---|---|
| operations | NO-OP | F2.3 no agrega REQ-OPS-NNN; comportamiento vive en DEC-UPD-NN |
| hooks | NO-OP | F2.3 no agrega sync hooks (kiosko+updater son client-side) |
| cutover-migration | NO-OP | F2.3 no cambia cutover semantics |
| sync-catalog | NO-OP | F2.3 no agrega filas sync_catalog |
| sync-motor | NO-OP | F2.3 no modifica sync behavior |

## 3. New Requirements

**NONE.** No REQ-OPS-NNN, no REQ-UPD-NNN, no REQ-ELEC-NNN, no nueva capability spec creada.

### 3.1 Why no new REQ

- F2.3 no shippea endpoint HTTP backend nuevo — consume-only de `GET /api/v1/health` HIPOTÉTICO (degrada a 🔴 mientras no exista). El contrato backend ya está especificado o se especificará en HU backend separada F3+.
- F2.3 no agrega DB migration — el hash bcrypt del PIN se persiste en `app.getPath('userData')/auth.json` (electron-store, filesystem local, ya existente por F2.2).
- F2.3 no agrega sync_catalog row — auto-update, single-instance, kiosko y api-status no son hooks de sincronización servidor↔cliente; viven enteramente en el cliente.
- F2.3 no concede permiso RBAC — kiosko PIN es local (electron-store), no introduce grants nuevos de backend.
- Las 13 DEC-UPD-NN viven en `proposal.md §5` como compromisos arquitectónicos. NO son REQs porque describen IMPLEMENTATION (feed runtime env, polling 30s main process, bcrypt factor 12, before-input-event scoped) no BEHAVIOR (qué hace el sistema ante un estímulo externo de negocio). El behavior contract es interno (vitest + playwright + axe-core) — no necesita enforcement externo.

### 3.2 What deferred specs will own

| Future spec | Will own | Phase |
|---|---|---|
| F3.1 spec.md (operations delta) | Login UI flow: form + POST /auth/login + redirect `/login?next=<path>` | F3.1 SDD |
| F3.2 spec.md (operations delta) | Lockout visible con countdown 429 Retry-After + bridge.kiosk toggle UI para admin override | F3.2 SDD |
| F3.3 spec.md (operations delta) | Turno abrir/cerrar + logout cleanup + verifica 🔴 antes de abrir turno vía bridge.apiStatus | F3.3 SDD |
| F5.1+ spec.md (operations delta) | Impresión térmica escpos-usb dentro de kiosko mode (no operation conflict) | F5.1+ SDD |
| F11.x spec.md (operations delta) | Sync UI extendiendo `<StatusBar>` con queue depth + lag seconds | F11.x SDD |
| IT-3..IT-10 spec.md (operations delta) | Consumo de bridge.apiStatus + bridge.kiosk + auto-update silencioso desde features downstream | IT-3..IT-10 SDD |

### 3.3 Si la propuesta decidiera formalizar como REQ-OPS-113..125

`proposal.md §6.2` enumera las 13 candidatas:

| ID candidato | Behavior (si se formalizara) | Source DEC |
|---|---|---|
| ~~REQ-OPS-113~~ | `electron-updater autoDownload:true + autoInstallOnAppQuit:true + allowDowngrade:false` | DEC-UPD-02/03 |
| ~~REQ-OPS-114~~ | `electron-updater signature verification via electron-builder publish config` | DEC-UPD-04 |
| ~~REQ-OPS-115~~ | `api-status polling 30s main process + timeout 5s AbortController` | DEC-UPD-05/06 |
| ~~REQ-OPS-116~~ | `app.requestSingleInstanceLock() before whenReady + second-instance focus` | DEC-UPD-07 |
| ~~REQ-OPS-117~~ | `kiosko mode via env PARKOS_KIOSK_MODE=1` | DEC-UPD-08 |
| ~~REQ-OPS-118~~ | `kiosko PIN bcrypt factor 12 + constant-time compare + never logged` | DEC-UPD-09 |
| ~~REQ-OPS-119~~ | `kiosko shortcuts blocked via before-input-event (Ctrl+W, Alt+F4)` | DEC-UPD-10 |
| ~~REQ-OPS-120~~ | `electron-log rotation 10MB×5 JSON + uncaughtException capture` | DEC-UPD-11 |
| ~~REQ-OPS-121~~ | `<StatusBar> aria-live="polite" + dedup consecutiva + debounce 2s` | DEC-UPD-12 |
| ~~REQ-OPS-122~~ | `electron-updater feed configurable via env PARKOS_UPDATE_FEED_URL` | DEC-UPD-01 |
| ~~REQ-OPS-123~~ | `autoUpdater autoInstall retry every 6h on signature failure` | DEC-UPD-04 |
| ~~REQ-OPS-124~~ | `kiosko unlock audit log kiosko.unlock_attempt{success, attempt_id, timestamp}` | DEC-UPD-09 |
| ~~REQ-OPS-125~~ | `bridge.apiStatus shape {ok: boolean, latency_ms: number, code?: number}` | DEC-UPD-12 |

**DECIDIDO** (per `proposal.md §5.13` + §6.1): no se crean en esta change. Las DEC-UPD-NN cargan peso equivalente para enforcement interno. Reversible: si Fase 3 determina que el comportamiento necesita enforcement cross-team, el spec F3.x las materializa.

## 4. Cross-References to Existing REQs

F2.3 referencia las siguientes requirements existentes **INFORMATIONALLY** only (no las enmienda):

- **REQ-OPS-XR6** (operations/spec.md:3951 — 5-layer defense in depth) — el patrón XR6 (auth HTTP + a11y + engineering + contract + retry-budget) es exactamente la arquitectura de F2.3: capa auth (kiosko PIN bcrypt factor 12 via electron-store, F2.3 DEC-UPD-09), capa a11y (`<StatusBar>` aria-live polite + axe-core WCAG 2.1 AA, DEC-UPD-12 + RNF-022), capa engineering (TS strict + noUncheckedIndexedAccess en services/*.ts, F2.1 DEC-ELEC-02), capa contract (bridge.d.ts `ApiStatus` shape delta + preload.contract.test.ts, F2.2 DEC-FETCH-08 + F2.3 DEC-UPD-12), capa retry-budget (api-status polling 30s + updater retry 6h + kiosko lockout 3 attempts, DEC-UPD-02/06/09). NO crea XR7 (precedente F1.15 DEC-XR7 NOT-CREATED en operations/spec.md:4386 + F2.1 DEC-ELEC-10 + F2.2 DEC-FETCH-10).
- **REQ-OPS-002** (operations/spec.md:32 — sync module coverage ≥80%) — NO aplica a F2.3 (F2.3 no es sync module). Cobertura mínima del change: >80% en `services/{updater,api-status,kiosko}.ts`, >80% en `StatusBar.tsx`. Esta es decisión de F2.3 exploration §15.2, no REQ-OPS canónico.
- **`apps/electron-sucursal/electron/main.ts:1-55`** (F2.1 minimal app shell con whenReady + createMainWindow + window-all-closed) — F2.3 lo extiende con init calls en orden + IPC handlers (`api:status`, `kiosk:toggle`, `app:quit`) + lock check. Comportamiento backward-compatible preservado: `app.quit()` en `window-all-closed` solo dispara si platform !== 'darwin'.
- **`apps/electron-sucursal/electron/preload.ts:1-49`** (F2.2 whitelist IPC 8 métodos) — F2.3 NO lo modifica. Solo agrega handlers en main process que escuchan los canales que preload ya emite. Esto preserva el contract test verde (F2.2 G5) y mantiene el principio de whitelist filtering (R-IPC del F2.2 DEC-FETCH-08).
- **`apps/electron-sucursal/electron/bridge.d.ts:1-87`** (F2.2 BridgeSurface typed con apiStatus/kiosk/app) — F2.3 modifica SOLO el shape `ApiStatus`: `{online, lastSync}` → `{ok, latency_ms, code?}`. Cambio breaking aceptado (DEC-UPD-12) porque solo hay 1 consumer en F2.3 (`<StatusBar>`) y 1 stub en F2.2 (`bridge.spec.ts` test 5) que se actualizan simultáneamente.

## 5. Diff Against Canonical Spec

`operations/spec.md` canónico permanece **UNCHANGED** (112 REQs vigentes) después de este change. Ningún REQ-NNN añadido, modificado o removido. Verificación cross-fase: sdd-verify debe validar que el canonical NO se modifica vía `git diff openspec/specs/operations/spec.md` retornando empty diff + byte count idéntico.

## 6. Acceptance Gates Mapping (cross-reference a `proposal.md §11`)

| Gate | Behavior validado | Test source | Tipo |
|---|---|---|---|
| **G1** | `electron-updater.autoDownload:true` + `autoInstallOnAppQuit:true` + `allowDowngrade:false` configurados | `updater.test.ts` (T1) assert config | Unit (vitest) |
| **G2** | Signature verification failure → NO instala + log error + retry next cycle (6h) | `updater.test.ts` (T1) mock `autoUpdater.on('error')` | Unit (vitest) |
| **G3** | `app.requestSingleInstanceLock()` retorna `false` en segunda invocación → enfoca primera + termina | `lifecycle.spec.ts` (T7) con `_electron.launch` 2 veces | E2E (playwright _electron) |
| **G4** | `PARKOS_KIOSK_MODE=1` → full-screen + `Menu.setApplicationMenu(null)` + `Ctrl+W`/`Alt+F4` bloqueados + `Ctrl+Shift+K` + PIN bcrypt factor 12 (correcto desactiva, incorrecto no desactiva, nunca logueado) | `kiosko.test.ts` (T4) + `kiosko.spec.ts` (T7) | Unit + E2E |
| **G5** | `electron-log` rotación 10MB×5 JSON + captura `uncaughtException`/`unhandledRejection` | `log-config.test.ts` (T5) mock electron-log | Unit (vitest) |
| **G6** | api-status polling 30s + timeout 5s AbortController + IPC handler retorna `{ok, latency_ms, code?}` + 3 estados (🟢/🟡/🔴) | `api-status.test.ts` (T2) con mock fetch | Unit (vitest) |
| **G7** | `<StatusBar>` con `aria-live="polite"` + texto exacto por estado (`🟢 API OK` / `🟡 API lento` / `🔴 Sin API`) + de-duplicación consecutiva + debounce 2s | `StatusBar.test.tsx` (T6) + axe-core extension (F2.2 axe pattern, RNF-022) | Unit (vitest) + a11y |
| **G8** | 2 e2e verde (segunda instancia enfoca, `Ctrl+W` bloqueado, PIN incorrecto no desbloquea) | `lifecycle.spec.ts` + `kiosko.spec.ts` (T7) | E2E (playwright _electron) |

**Total enforcement**: 30 LOC updater.test + 20 LOC api-status.test + 40 LOC kiosko.test + 30 LOC StatusBar.test + 60 LOC lifecycle.spec + 60 LOC kiosko.spec + 1 axe-core WCAG 2.1 AA scan = **240 LOC tests** (T1+T2+T4+T5+T6 unit + T7 e2e). Todos enforcement interno, ninguno es REQ-OPS canónico.

**Sandbox F.6 caveat**: Per F2.1 + F2.2 archive precedent (npm 11.16.0 refuses `workspace:*` resolution), las e2e (`lifecycle.spec.ts`, `kiosko.spec.ts`) SKIP en sandbox F.6 — documentado como deviation D-env en verify-report, NO project defect. G3 + G4 + G8 enforcement es por e2e; las gates unit (G1, G2, G5, G6, G7) sí corren en sandbox.

## 7. Open Questions

NONE.

## 8. Next Recommended Phase

**PHASE**: `sdd-design hu-f2-3-electron-auto-update-kiosko` (parallel con tasks; design completo de 4 clusters C1..C4 en `openspec/changes/hu-f2-3-electron-auto-update-kiosko/design.md`).

Pre-design handoff:
- **13 DEC-UPD-NN** verbatim desde `proposal.md §5` (DEC-UPD-01..13).
- **4-cluster decomposition** C1→C2→C3→C4 desde `proposal.md §10` (C1 updater+log-config ~145 LOC, C2 api-status+StatusBar ~180 LOC, C3 single-instance+kiosko ~170 LOC, C4 e2e ~120 LOC).
- **7 atomic tasks** T1..T7 desde `exploration.md §9` con budget LOC cada uno (T1 ~110, T2 ~70, T3 ~30, T4 ~140, T5 ~40, T6 ~110, T7 ~120 = ~620 LOC).
- **8 acceptance gates** G1..G8 desde `proposal.md §11`.
- **8 riesgos** R1..R8 desde `exploration.md §6` (signature verification failure, /health 404, single-instance race, kiosko bypass task manager, PIN brute force, bcrypt CPU cost, electron-log disk fill, StatusBar screen reader spam).
- **Pre-flight 9/10 PASS + 1 KNOWN-MISSING** verificado en `exploration.md §12` (bcrypt se mitiga en T4).
- **Orden de inicialización mandatorio** desde `proposal.md §7.1`: lock → log-config → process.on('uncaughtException') → whenReady → updater → api-status → kiosko env → createMainWindow → IPC handlers.
- **Reference files**: `apps/electron-sucursal/electron/main.ts:1-55`, `apps/electron-sucursal/electron/preload.ts:1-49`, `apps/electron-sucursal/electron/bridge.d.ts:1-87`, `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts:1-110`, `apps/electron-sucursal/electron/__mocks__/electron.ts`, `apps/electron-sucursal/package.json:22-77`, `apps/electron-sucursal/tsconfig.{json,main.json}`, `apps/electron-sucursal/vite.config.ts`, `apps/electron-sucursal/esbuild-main.mjs`, `apps/electron-sucursal/playwright.config.ts`, `apps/electron-sucursal/src/renderer/App.tsx`, `apps/electron-sucursal/src/renderer/i18n/locales/common.json`, `apps/electron-sucursal/electron-builder.yml`, `docs/01-requisitos/no-funcionales.md:126` (RNF-022 WCAG 2.1 AA), `docs/03-desarrollo/{setup.md:15, estandares.md:79-91}`.

## 9. Forward Hook (Fase 3+)

Si HU-F3.x (login/lockout/turno) decide formalizar los contratos de F2.3 como REQ-OPS-NNN, las propuestas F3.x pueden invocar las 13 REQ-OPS-113..125 que están pre-enumeradas en `proposal.md §6.2` (ahora §3.3 arriba). F2.3 abre la puerta pero no la cruza — el behavior contract vive en el código fuente + tests, los REQ-OPS-NNN se materializan cuando sea necesario enforcement cross-team. Precedente verbatim aplicado de F2.1 DEC-ELEC-10 + F2.2 DEC-FETCH-10 (mismo NO-OP stub pattern). Adicionalmente:

- **F11.x sync UI** — puede extender `<StatusBar>` con sync state (queue depth, lag seconds) consumiendo `bridge.apiStatus.get()` + nuevo `bridge.sync.status`. Forward consumer explícito.
- **F2.4+ post-Fase 2 ops** — `bridge.kiosk.toggle(on)` puede usarse para admin override remoto via backend command (forward hook declarado en exploration §14).
- **F3.2 lockout visible** — `parkosFetch` (F2.2) emite log `auth.lockout{retry_after: seconds}` que `<StatusBar>` puede anunciar como estado extendido 🔒 vía nuevo forward consumer.

---

## CHANGELOG

- **(2026-09-15)** F2.3 — NO-OP delta. DEC-UPD-13 mantiene cero REQ-OPS-NNN nuevos. Las 13 DEC-UPD-NN viven en `proposal.md §5`. 8 acceptance gates internos (vitest + playwright + axe-core) son el enforcement real. Precedente F2.1 DEC-ELEC-10 + F2.2 DEC-FETCH-10 verbatim aplicado. 240 LOC tests total + 1 axe-core scan. Ready for sdd-design.