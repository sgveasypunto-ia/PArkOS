# Delta Spec: operations — HU-F2.2 (Cliente HTTP parkosFetch + IPC bridge tipado + authStore Zustand + useAuth SWR)

> **Change**: `hu-f2-2-parkos-fetch-ipc-auth-store`
> **Capability**: operations
> **Phase**: spec (sdd-spec)
> **Status**: ready for sdd-design (parallel) + sdd-tasks
> **Date**: 2026-09-15
> **Author**: orchestrator (sdd-spec sub-agent)

## 1. Delta Summary

**No new REQ added by this change.** Per **DEC-FETCH-10** (proposal.md §6.1), F2.2 es infraestructura HTTP — mismo razonamiento que F2.1 DEC-ELEC-10. Las 8 decisiones arquitectónicas DEC-FETCH-01..08 en proposal.md §4 cargan el mismo peso RFC 2119 que las REQs. No se introducen endpoints HTTP nuevos, no se agregan tablas/migraciones, no se modifican filas del sync_catalog, no se conceden permisos RBAC. El behavior contract implícito reside en los 8 acceptance gates G1..G8 (proposal.md §10) ejecutados por vitest + playwright + axe-core.

## 2. Affected Capabilities

| Capability | Action | Reason |
|---|---|---|
| operations | NO-OP | F2.2 no agrega REQ-OPS-NNN; comportamiento vive en DEC-FETCH-NN |
| hooks | NO-OP | F2.2 no agrega sync hooks (authStore es client-side) |
| cutover-migration | NO-OP | F2.2 no cambia cutover semantics |
| sync-catalog | NO-OP | F2.2 no agrega filas sync_catalog |
| sync-motor | NO-OP | F2.2 no modifica sync behavior |

## 3. New Requirements

**NONE.** No REQ-OPS-NNN, no REQ-FETCH-NNN, no REQ-ELEC-NNN, no nueva capability spec creada.

### 3.1 Why no new REQ

- F2.2 no shippea endpoint HTTP backend nuevo — consume-only de `/auth/{login,refresh,logout,me}` existentes. El contrato backend ya está especificado.
- F2.2 no agrega DB migration — `authStore` persiste en `app.getPath('userData')/auth.json` (electron-store, filesystem local).
- F2.2 no agrega sync_catalog row — la autenticación no es un hook de sincronización servidor↔cliente; el JWT vive enteramente en el cliente.
- F2.2 no concede permiso RBAC — el token bearer reemplaza credenciales pero no introduce grants nuevos.
- Las 8 DEC-FETCH-NN viven en `proposal.md §4` como compromisos arquitectónicos. NO son REQs porque describen IMPLEMENTATION (retry policy, idempotency key hashing, IPC whitelist pattern, persist backend) no BEHAVIOR (qué hace el sistema ante un estímulo externo). El behavior contract es interno (vitest 14 + playwright 14 + axe-core) — no necesita enforcement externo.

### 3.2 What deferred specs will own

| Future spec | Will own | Phase |
|---|---|---|
| F2.3 spec.md (operations delta) | Auto-update signature, kiosko PIN bcrypt ≥12, single-instance lock | F2.3 SDD |
| F3.1 spec.md (operations delta) | Login UI flow: form + POST /auth/login + redirect `/login?next=<path>` | F3.1 SDD |
| F3.2 spec.md (operations delta) | Lockout visible con countdown 429 Retry-After | F3.2 SDD |
| F3.3 spec.md (operations delta) | Turno abrir/cerrar + logout cleanup | F3.3 SDD |
| IT-3..IT-10 spec.md (operations delta) | Consumo de parkosFetch + useAuth + bridge.* desde features downstream | IT-3..IT-10 SDD |

### 3.3 Si la propuesta decidiera formalizar como REQ-OPS-106..112

`exploration.md §15.4` enumera las 7 candidatas:

| ID candidato | Behavior (si se formalizara) | Forward consumer |
|---|---|---|
| ~~REQ-OPS-106~~ | `parkosFetch retries 5xx + 408 with backoff 300/600/1200ms` | F3.x features |
| ~~REQ-OPS-107~~ | `parkosFetch triggers single 401 refresh via POST /auth/refresh con Mutex` | F3.x features |
| ~~REQ-OPS-108~~ | `parkosFetch emits Idempotency-Key SHA-256(method+path+body) on POST/PUT/DELETE/PATCH` | F5.x facturación DIAN |
| ~~REQ-OPS-109~~ | `parkosFetch validates response via Zod schema on boundary (opcional)` | F3.x features |
| ~~REQ-OPS-110~~ | `useAuth() SWR refresh every 5*60*1000ms + auto-clear on second 401` | F3.1 login UI |
| ~~REQ-OPS-111~~ | `preload whitelists bridge.* via contextBridge.exposeInMainWorld` | F4.x features |
| ~~REQ-OPS-112~~ | `bridge.imprimir invokes escpos-usb with PrintPayload` | F5.1 reimpresión térmica |

**DECIDIDO** (per `proposal.md §6.1`): no se crean en esta change. Las DEC-FETCH-NN cargan peso equivalente para enforcement interno. Reversible: si Fase 3 determina que el comportamiento necesita enforcement cross-team, el spec F3.1 las materializa.

## 4. Cross-References to Existing REQs

F2.2 referencia las siguientes requirements existentes **INFORMATIONALLY** only (no las enmienda):

- **REQ-OPS-XR6** (operations/spec.md:3951 — 5-layer defense in depth) — el patrón XR6 (auth HTTP + a11y + engineering + contract + retry-budget) es exactamente la arquitectura de F2.2: capa auth (parkosFetch bearer injection), capa contract (bridge.d.ts + preload.contract.test.ts), capa retry-budget (timeout + refresh-once Mutex). NO crea XR7 (precedente F1.15 DEC-XR7 NOT-CREATED en operations/spec.md:4386).
- **REQ-OPS-002** (operations/spec.md:32 — sync module coverage ≥80%) — NO aplica a F2.2 (F2.2 no es sync module). Cobertura mínima del change: >90% en `parkosFetch.ts`, >80% en `authStore.ts` + `useAuth.ts`. Esta es decisión de F2.2 DEC-FETCH-06, no REQ-OPS canónico.
- **`apps/web_admin/src/lib/fetch.ts:1-66`** (parkosFetch preexistente en web_admin) — F2.2 lo extrae a `@parkos/ui-kit/fetch` y lo extiende con retry/refresh/idempotency/Zod. Comportamiento preservado: Authorization Bearer + X-Sucursal-Context headers idénticos a F1.x.
- **`apps/electron-sucursal/electron/preload.ts:1-11`** (contextBridge `window.bridge = {}` vacío post-F2.1) — F2.2 expande la superficie con 8 métodos typed. Comportamiento backward-compatible: no había nada en `bridge`, sigue no habiendo nada hasta que código render llame explícitamente.

## 5. Diff Against Canonical Spec

`operations/spec.md` canónico permanece **UNCHANGED** (112 REQs vigentes) después de este change. Ningún REQ-NNN añadido, modificado o removido.

## 6. Acceptance Gates Mapping (cross-reference a `proposal.md §10`)

| Gate | Behavior validad | Test source | Tipo |
|---|---|---|---|
| **G1** | parkosFetch retries 5xx + 408 con backoff 300/600/1200ms | `parkosFetch.test.ts` (T1, 14 escenarios MSW + `vi.useFakeTimers()`) | Unit (vitest) |
| **G2** | 401 refresh-once con Mutex singleton + segundo 401 limpia authStore | `parkosFetch.test.ts` (T1, 14 escenarios MSW) | Unit (vitest) |
| **G3** | Idempotency-Key SHA-256(method+path+body) en POST/PUT/DELETE/PATCH | `parkosFetch.test.ts` (T1, 14 escenarios MSW) | Unit (vitest) |
| **G4** | Zod validation opcional en boundary via `parkosFetch<T>(url, schema)` | `parkosFetch.test.ts` (T1, 14 escenarios MSW) | Unit (vitest) |
| **G5** | bridge IPC typed — `preload.contract.test.ts` valida shape + tsc --noEmit | `tsc --noEmit` (typecheck) + `preload.contract.test.ts` (T2+T3, 8 escenarios) | Typecheck + Unit |
| **G6** | authStore Zustand persist contra electron-store + cleanup on 401 | `authStore.test.ts` (T4, ≥4 escenarios) | Unit (vitest) |
| **G7** | useAuth() SWR refresh 5min + auto-clear en `authStore.cleared` event | `useAuth.test.ts` (T5, ≥4 escenarios) | Unit (vitest) |
| **G8** | e2e 22 escenarios (14 parkosFetch + 8 bridge) + axe-core RNF-022 | `parkos-fetch.spec.ts` (T6) + `bridge.spec.ts` (T6) + `wcag-2.1-aa.spec.ts` (T7) | E2E (playwright _electron) |

**Total enforcement**: 14 (parkosFetch MSW) + 8 (bridge contract) + ≥4 (authStore) + ≥4 (useAuth) + 22 (e2e) + 1 (axe-core) = 53+ escenarios vitest/playwright/axe-core. Todos enforcement interno, ninguno es REQ-OPS canónico.

## 7. Open Questions

NONE.

## 8. Next Recommended Phase

**PHASE**: `sdd-design hu-f2-2-parkos-fetch-ipc-auth-store` (12-section design at `openspec/changes/hu-f2-2-parkos-fetch-ipc-auth-store/design.md`).

Pre-design handoff:
- **8 DEC-FETCH-NN** verbatim desde `proposal.md §4` (DEC-FETCH-01..08).
- **3-cluster decomposition** C1→C2→C3 desde `proposal.md §9` (C1 parkosFetch+bridge ~230 LOC, C2 authStore+useAuth ~130 LOC, C3 e2e+axe-core+contract ~190 LOC).
- **7 atomic tasks** T1..T7 desde `exploration.md §10` con budget LOC cada uno.
- **8 acceptance gates** G1..G8 desde `proposal.md §10`.
- **8 riesgos** R1..R8 desde `exploration.md §8`.
- **Pre-flight 10/10 PASS** verificado en `exploration.md §12`.
- **Reference files**: `apps/web_admin/src/lib/fetch.ts:1-66`, `apps/electron-sucursal/electron/preload.ts:1-11`, `apps/ui-kit/src/Button.tsx`, `apps/ui-kit/src/cn.ts`, `apps/ui-kit/src/tokens.ts`, `apps/package.json:5-8` (workspaces).

## 9. Forward Hook (Fase 3+)

Si HU-F3.1 (login email+password) decide formalizar los contratos de parkosFetch/bridge/authStore como REQ-OPS-NNN, la propuesta F3.1 puede invocar las 7 REQ-OPS-106..112 que están pre-enumeradas en `exploration.md §15.4` (ahora §3.3 arriba). F2.2 abre la puerta pero no la cruza — el behavior contract vive en el código fuente + tests, los REQ-OPS-NNN se materializan cuando sea necesario enforcement cross-team.

---

## CHANGELOG

- **(2026-09-15)** F2.2 — NO-OP delta. DEC-FETCH-10 mantiene cero REQ-OPS-NNN nuevos. Las 8 DEC-FETCH-NN viven en `proposal.md §4`. 53+ acceptance gates internos (vitest + playwright + axe-core) son el enforcement real. Precedente F2.1 DEC-ELEC-10 verbatim aplicado.
