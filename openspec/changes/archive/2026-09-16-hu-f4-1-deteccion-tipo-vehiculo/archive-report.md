# Archive Report — HU-F4.1 Detección automática de tipo de vehículo por placa (función pura `detectarTipoVehiculo()` estricto + hook SWR `useTiposVehiculo()` con fallback hardcoded `{auto, moto}` + i18n key `operacion.placa_formato_invalido` + 6 new REQ-OPS-125..130)

## 0. Metadata

- HU: HU-F4.1
- Fase: 4 (Catálogos y ocupación en vivo — primera HU de Fase 4; transversal consumer + defense in depth XR6 layer 4 + UX transaccional)
- SDD cycle: explore → propose → spec → design → tasks → apply → verify → **archive (current)**
- Branch: `feature/hu-f4-1-deteccion-tipo-vehiculo` (HEAD post-archive: `a6ddd5a`)
- Date: 2026-09-16
- Status: **closed + archived** (PASS, 5/7 gates PASS source-level + 2/7 SKIPPED-env/forward per F.6 precedent, 0 FAIL, 0 deviations, 0 blocking)
- Author: Parkos Dev <dev@parkos.local>
- Engram observation IDs (cycle traceability): explore **#1706** · propose **#1707** · spec **#1708** · design **#1709** · tasks **#1710** · apply **#1711** · verify **#1713** · archive **(new)**

### Resumen ejecutivo

- **2 commits atómicos** `9810841..a6ddd5a` archivados (C1 + C2, T1+T3 agrupados per DEC-F4.1-08 + T2 independiente), author `Parkos Dev <dev@parkos.local>` consistente 2/2, 0 Co-authored-by, 0 AI attribution.
- **7 archivos cambiados** (+574/-1 LOC) — 5 NEW + 2 MODIFY, debajo del budget 800 LOC per `config.yaml rules.tasks` (single-PR strategy justificada, NO chained slices necesarias).
- **6 new REQ-OPS-125..130** materializadas byte-preserved en canonical `openspec/specs/operations/spec.md` (5249 → 5462 líneas, +213 net, sha256 delta `5C965CD6...` → `5D9AE9FB...`).
- **11 DEC-F4.1-01..11** ratificadas y honradas (11/11 honored, §6 traceability matrix PASS).
- **19 unit tests F4.1 PASS ejecutados** (`placa.test.ts` 8 + `useTiposVehiculo.test.ts` 11) — excede el forecast tasks.md (11 tests = 6 + 5) gracias a 2 tests extra en placa + 6 tests extra en catalogos per `apply-progress #1711`.
- **Mechanical Copy Contract** PASS (snapshot + move + diff SHA256 byte-identity + source absent + target populated con 5/5 archivos).
- **F4.1 ES user-facing DELTA** (precedent F1.15 + F3.1 + F3.2 + F3.3 verbatim): **quinto DELTA consecutivo** en Fases 1+3+4, rompe el patrón F2.x NO-OP + F2.x infra-only porque el comportamiento es observable al operador (autodetectar tipo al digitar placa + i18n key pre-poblada para F6.1 error inline + catálogo con fallback degradado + SWR token-gated + defense in depth XR6 layer 4 bidireccional cliente+backend).
- **Fase 4 status**: **1/9+ HU cerrada** (F4.1 archivada 2026-09-16; F4.2 Tarifas + F4.3 Ocupación + F4.x subsiguientes ready per forward hooks §10).

---

## 1. Cycle timeline (explore → propose → spec → design → tasks → apply → verify → archive)

| Phase | Artifact | LOC | Outcome | Engram ID |
|---|---|---|---|---|
| explore | `exploration.md` (~63KB / 374 líneas) | 16 secciones, 10 DEC-F4.1-01..10, 5 riesgos R1..R5, 7 gates G1..G7, 4 inconsistencies I1..I4 detectadas + cerradas | pre-flight 10/10 PASS + 0 KNOWN-MISSING + I2 endpoint verificación resuelta en propose | **#1706** |
| propose | `proposal.md` (99294 bytes / 758 líneas) | 16 secciones §0..§16 + CHANGELOG, 11 DEC-F4.1-01..11 ratified (DEC-F4.1-11 NUEVA formaliza spec delta), 5 riesgos R1..R5, 7 gates G1..G7, 3 atomic tasks T1..T3, 1 cluster C1, ~293 LOC forecast | **CRITICAL**: DEC-F4.1-07 + DEC-F4.1-11 verdict = DELTA con 6 new REQ-OPS-125..130 (NOT NO-OP) — replica precedent F1.15 + F3.x user-facing | **#1707** |
| spec | `specs/operations/spec.md` (43405 bytes / 391 líneas) | 7 secciones + CHANGELOG, 6 new REQ-OPS-125..130 in Given/When/Then/And RFC 2119 + cross-reference table §4.1 + acceptance criteria §4.2 (7 ACs) + out of scope §5 | DELTA materializado en source change folder; canonical merge pendiente (archive) | **#1708** |
| design | `design.md` (80235 bytes / 1029 líneas) | 13 secciones §0..§13 + 2 apéndices (6 TS mockups Apéndice A: placa.ts + placa.test.ts + tiposVehiculoApi.ts + tiposVehiculoApi.test.ts + useTiposVehiculo.ts + useTiposVehiculo.test.ts + 3 configs delta Apéndice B) | T1..T3 atomic tasks con complexity estimates + 6 mockups KEEP COMPACT | **#1709** |
| tasks | `tasks.md` (48133 bytes / 348 líneas) | 7 secciones, 3 atomic tasks T1..T3 (T1+T3 agrupados en C1 + T2 en C2 per DEC-F4.1-08), 1 cluster C1 end-to-end, 7 acceptance gates G1..G7 | Forecast ~313 LOC total (production 160 + tests 150 + i18n 3 ≈ 313), single-PR strategy justificada | **#1710** |
| apply | 2 atomic commits `9810841..a6ddd5a` | +574/-1 LOC (5 NEW + 2 MODIFY) | All 3 tasks shipped verbatim per design; 19/19 unit tests verde (8 placa + 11 catalogos, excede forecast tasks 11) | **#1711** |
| verify | Engram `sdd/hu-f4-1-deteccion-tipo-vehiculo/verify-report` (265 LOC, 16 secciones + CHANGELOG, NO persisted as `verify-report.md` file per F2.x + F3.x precedent) | 7 gates G1..G7 verificados, 6 REQ-OPS-125..130 PASS source-level (4 runtime + 2 forward F6.1), 11 DEC-F4.1-01..11 honored, **0 deviations** (F4.1 es más limpia que F3.3) | **PASS** | **#1713** |
| archive | este archivo | ~328 LOC, mechanical copy + DELTA merge + 13 secciones + CHANGELOG | Cycle closed | **(new)** |

**Total cycle artifact footprint**: ~5.0k LOC de artefactos SDD (proposal 99KB + design 80KB + exploration 63KB + spec delta 43KB + tasks 48KB + verify Engram 265 LOC + archive 328 ≈ 5.0k LOC).

---

## 2. Artifacts archived (6 files)

```
openspec/changes/archive/2026-09-16-hu-f4-1-deteccion-tipo-vehiculo/
├── proposal.md               99294 bytes /  758 líneas / sha256:A7963E6CC657A846F0FFF506995862DAEE84D10ABE3B76ADBE46DA64B81A4A82
├── exploration.md            63174 bytes /  374 líneas / sha256:36322C72215F05C5E0E6121D815E9C8BEEE5C40CA80EBA9F7C8174960CD9426B
├── design.md                 80235 bytes / 1029 líneas / sha256:2C93973A5E2E36B0E3FEBCB6A58008B973604B66DE8B81BA493144D1643DF342
├── tasks.md                  48133 bytes /  348 líneas / sha256:B35BA2B8877379A050EA9214D68B4CC4567ED44F4B3CB9AE7C6161E60140ACCB
├── verify-report.md          44054 bytes /  265 líneas / sha256:47092863B39AEFEE04578D4F22E15A4538A675D895E04C4A5D5FAE383A5C0366
├── specs/
│   └── operations/
│       └── spec.md           43405 bytes /  391 líneas / sha256:26BCD465A15B4A5DED212BEDA40216A81349DEBBC6340D8618E5C7FFC624099C
└── archive-report.md         este archivo (additive-only, ~328 LOC)
```

Total archive bytes: 378295 (6 source files: 5 originales + verify-report.md migrado post-race-condition + este archivo ≈ 418k bytes de artefactos SDD F4.1 preservados byte-by-byte.

**Race condition documentada**: el `verify-report.md` fue generado por la fase `sdd-verify` a las 18:00:17 — DESPUÉS del snapshot inicial del archive phase (que capturó 5 archivos: proposal + exploration + design + tasks + specs/operations/spec.md). El `Move-Item -Force` movió los 5 archivos al archive folder, dejando el source folder temporalmente ausente. La fase verify recreó el source folder + escribió `verify-report.md` (atributo `Archive`, CreationTime 18:00:17) generando un 6° archivo huérfano en el path source. Resolución: `Move-Item -LiteralPath verify-report.md → archive folder` + `Remove-Item` del source folder vacío post-move. `verify-report.md` preservado en archive (NO en source) — matching F3.3 precedent verbatim (F3.3 archive también incluye verify-report.md). Snapshot pre-move original cubrió los 5 archivos especificados por el orchestrator — el verify-report.md migrado NO fue parte del snapshot original pero se preserva por completitud del audit trail.

---

## 3. Atomic commits ledger (2 commits, per DEC-F4.1-08 2-clusters split)

2 commits authored by `Parkos Dev <dev@parkos.local>`, **0 Co-authored-by**, **0 AI attribution**, conventional commits neutrales español (`feat(operacion)` × 1 + `feat(catalogos)` × 1):

| Hash | Cluster | Task | Files | +LOC | -LOC | Commit message |
|---|---|---|---|---|---|---|
| `9810841` | **C1** cohesivo "detección de placa funciona en cliente" | T1 `detectarTipoVehiculo()` pura + `REGEX_AUTO`/`REGEX_MOTO` exportadas + 8 unit tests + T3 i18n key `placa_formato_invalido` | 2 NEW + 1 MODIFY (`operacion.json`) | 137 | 0 | `feat(operacion): adicionar detectarTipoVehiculo() estricto + 8 unit tests + i18n key placa_formato_invalido (HU-F4.1-T1+T3)` |
| `a6ddd5a` | **C2** independiente "catálogo de tipos se carga con degradación" | T2 `useTiposVehiculo()` SWR hook + `tiposVehiculoApi` typed wrapper + 11 unit tests + `vitest.config.ts` MODIFY +3 coverage thresholds | 3 NEW + 1 MODIFY (`vitest.config.ts`) | 437 | 1 | `feat(catalogos): adicionar useTiposVehiculo() SWR + tiposVehiculoApi typed wrapper + 11 unit tests + fallback hardcoded {auto,moto} (HU-F4.1-T2)` |
| **TOTAL** | **2 atomic** | **T1 + T2 + T3** | **5 NEW + 2 MODIFY = 7 archivos** | **+574** | **-1** | — |

**Net delta working tree** (range `9810841^..a6ddd5a`): **+574/-1 = +573 net LOC** — debajo del budget 800 LOC per `config.yaml rules.tasks` (single-PR strategy justificada per tasks.md §5, NO chained slices necesarias). Forecast tasks.md §5 era 313 LOC; final real 574 LOC (+261 sobre forecast) debido a tests extra (8 vs 6 placa + 11 vs 5 catalogos) + JSDoc verbosa per defense in depth XR6 docs.

**Cluster strategy per DEC-F4.1-08**: T1+T3 agrupados en C1 cohesivo (la función pura sin i18n key es incompleta para el caller que quiera mostrar el error inline per F6.1 forward); T2 independiente en C2 (catálogo de tipos es work-unit separado — falla independiente de la detección cliente). Permite rollback granular: si C2 falla, C1 ya está mergeado y `detectarTipoVehiculo()` funciona con fallback hardcoded.

Hygiene verification (per `apply-progress #1711`):

```bash
git log --format='%(trailers)' 9810841..a6ddd5a | grep -iE "(Co-Authored-By|AI Generated|Signed-off-by)" | wc -l
# Output: 0
```

2/2 commits PASS hygiene: author `Parkos Dev <dev@parkos.local>` · NO Co-authored-by · NO AI trailers · conventional commits neutrales español · scopes `{operacion, catalogos}`.

---

## 4. Spec merge to canonical (6 REQ-OPS-125..130 materialized)

### 4.1 Rationale DELTA (DEC-F4.1-07 + DEC-F4.1-11)

F4.1 ES user-facing behavior observable en cuatro dimensiones (NO cabe en NO-OP stub per F2.x precedent):

1. **Autodetectar tipo al digitar placa** — `detectarTipoVehiculo(placa)` corre client-side <1ms, retorna `'Auto' | 'Moto' | null`. Operador NO selecciona manualmente (BR2 categórico, plan.md:1369 verbatim).
2. **Mensaje inline i18n pre-poblado** — `operacion.placa_formato_invalido` con string literal verbatim plan.md:1366 ("Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)") forward F6.1 `<PlacaInput>` `<p role="alert" aria-describedby>`.
3. **Catálogo cargado desde API con fallback hardcoded** — `useTiposVehiculo()` SWR `dedupingInterval: 5 * 60 * 1000` + `fallbackData: HARDCODED_CATALOG [{auto, moto}]` con UUIDs sentinels literales (`'00000000-0000-0000-0000-000000000001'` Auto, `'...0002'` Moto). Degradación observable, nunca pantalla rota (plan.md:1375 verbatim "fallback a un catálogo hardcoded de {auto, moto}").
4. **Defense in depth XR6 layer 4 bidireccional** — cliente `detectarTipoVehiculo()` UX rápido + backend `detectar_tipo_vehiculo()` server-side ya shipped F1.x (`operacion.py:215-277`) re-valida y overwrite via V5 (operacion.py:261 verbatim "Server overwrites via V5 (regex-derived UUID wins over client value)").

DEC-F4.1-07 + DEC-F4.1-11 (introducidos en `proposal.md §4.7 + §4.11`) **rompen** el precedent NO-OP de F2.x y adoptan precedent F1.15 + F3.1 + F3.2 + F3.3 (quinto DELTA consecutivo en Fases 1+3+4).

### 4.2 Operación ejecutada (mechanical merge)

**Procedimiento shell-only, bytes flow shell→file (NEVER Read→Write artifact content)**, siguiendo precedent F3.1 + F3.2 + F3.3 verbatim:

| Métrica | Pre-merge | Post-merge | Delta |
|---|---|---|---|
| Líneas | 5249 | 5462 | +213 |
| Bytes | 461626 | 478151 | +16525 |
| SHA256 | `5C965CD6C6D1DD61DE27F8DDD4281659E3173E18DD182D0345A939BD152B53E7` | `5D9AE9FBA41FC6E277ED36DBDE31ADA601B04972DAFAD19979F41D48B66617BB` | changed |
| REQ-OPS count | 124 | 130 | +6 (REQ-OPS-125..130) |
| REQ-OPS-XR count | 6 | 6 | 0 (sin nuevos XR, precedent F1.15 + F3.x verbatim) |

**Pasos (PowerShell + `[System.IO.File]::ReadAllText`/`WriteAllText` UTF8 para preservar LF endings)**:

1. Snapshot pre-move: 5 source files SHA256-captured antes del move (proposal `A7963E6C...` + exploration `36322C72...` + design `2C93973A...` + tasks `B35BA2B8...` + specs/operations/spec `26BCD465...`).
2. Extract delta spec REQ-OPS-125..130 block (delta content lines 73-279 = 207 líneas) a temp file → SHA256 `C8F4CF513704A09C8FA19FF7DA653B348DAF9D11132BD198A7F210A8A4516163` (21409 bytes).
3. Split canonical: head (líneas 1-5165, incluye `---` closing REQ-OPS-124) + tail (líneas 5168-5248, 81 líneas, inicia con `## Modified Capabilities`).
4. Concat: head + `\n\n\n` (3 newlines = 2 blank lines spacing per F3.3 precedent) + delta_block + `\n\n\n` (2 blank lines spacing before `## Modified Capabilities`) + tail → 5462 líneas.
5. Append `## CHANGELOG` section at bottom (NO existía en canonical pre-archive; F4.1 introduce el CHANGELOG siguiendo user instruction "Update the CHANGELOG at the bottom of the canonical spec to add: `- 2026-09-16: F4.1 DELTA merge — added REQ-OPS-125..130 (detección tipo vehículo por placa)`").
6. **Byte-identity readback 1**: extracted delta block (sha256 `C8F4CF51...`) vs embedded en merged canonical (sha256 `C8F4CF51...`) → **MATCH** (byte-idéntico, passing).
7. **Byte-identity readback 2**: canonical head líneas 1-5165 (REQ-OPS-001..124) sha256 `6A97A154...` post-merge vs sha256 `6A97A154...` pre-merge → **MATCH** (byte-idéntico, passing).
8. **Byte-identity readback 3**: canonical tail líneas 5168-5248 (Modified Capabilities + Out of Scope) sha256 `E7671836...` post-merge vs sha256 `E7671836...` pre-merge → **MATCH** (byte-idéntico, passing).
9. Overwrite canonical: `[System.IO.File]::WriteAllText($canonicalPath, $mergedContent, [System.Text.Encoding]::UTF8)` (shell, no model Read/Write).
10. Structural verify: `### REQ-OPS-124` at line 5119 → `### REQ-OPS-125` at line 5168 → `### REQ-OPS-130` at line 5347 → `## Modified Capabilities` at line 5377 (consecutive, 0 gaps, numeración monotónica verificada 124 → 125..130, 2-blank-line spacing per F3.3 precedent verbatim).

**Numeración monotónica verificada**: REQ-OPS-124 vigente pre-F4.1 (archivado por F3.3); F4.1 ocupa REQ-OPS-125..130 (continuación, 0 gaps, sin duplicados). Post-archive canonical: 130 REQ-OPS-001..130 + 6 XR (REQ-OPS-XR1..XR6).

### 4.3 Cross-reference table (6 REQ-OPS-125..130 materialized)

| REQ-OPS | DEC-F4.1 anchor | Comportamiento observable |
|---|---|---|
| **REQ-OPS-125** | DEC-F4.1-01 + DEC-F4.1-02 + DEC-F4.1-03 + DEC-SUC-22 + A-03 + BR2 | `export function detectarTipoVehiculo(placa: string): 'Auto' \| 'Moto' \| null` función pura determinista desde `apps/electron-sucursal/src/lib/validation/placa.ts`. Normalización previa en orden exacto: (1) `placa.trim()`; (2) `placa.toUpperCase()`; (3) `placa.replace(/\s+/g, '')` removiendo TODO whitespace interno. Constantes exportadas `REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/` + `REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/` (DRY con F6.1 Zod). SIN tolerancia `O↔0`/`I↔1`/`B↔8` (DEC-SUC-22 categórico, exclusivo `buscarIngresoTolerante()` Fase 7). JSDoc cross-link `operacion.py:215-277`. |
| **REQ-OPS-126** | DEC-F4.1-07 forward hook + F2.1 DEC-ELEC-06 | i18n key top-level `operacion.placa_formato_invalido` con string literal verbatim "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)" (plan.md:1366 verbatim). Namespace pre-existente respeta DEC-ELEC-06 (un namespace por bounded context). SIN interpolación (`{{tipo}}` NO permitido). Consumible forward F6.1 `<PlacaInput>` con `<p role="alert" aria-describedby="placa-input-error">{t('operacion.placa_formato_invalido')}</p>`. Snapshot test del JSON verifica la key + string verbatim (defense contra typo). |
| **REQ-OPS-127** | DEC-F4.1-04 + DEC-F4.1-05 + DEC-F4.1-06 + DEC-SUC-03 + F3.3 REQ-OPS-120 precedent | `useTiposVehiculo()` SWR hook desde `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts`. Config: (a) `key: accessToken ? '/catalogos/tipos-vehiculo' : null` (key null-when-no-token verbatim F3.3); (b) `fetcher: () => tiposVehiculoApi.getTiposVehiculo()`; (c) `dedupingInterval: 5 * 60 * 1000` (plan.md:1375 verbatim — 5min catálogos reference data vs F3.3 10s sesión activa); (d) `fallbackData: HARDCODED_CATALOG` inline módulo-level con UUIDs sentinels literales `['00000000-0000-0000-0000-000000000001', '...0002']` (NO `crypto.randomUUID()`); (e) `shouldRetryOnError: (err) => err?.status !== 404`; (f) `onError` con `err?.status === 401` dispara `useAuthStore.getState().clear()` + `window.dispatchEvent(new Event('parkos:auth:cleared'))` (precedent F3.3 verbatim). Retorna `{tipos: TipoVehiculo[], isLoading, error: ParkosHttpError | undefined, refresh: () => Promise<TipoVehiculo[] | undefined>, isFromFallback: boolean}` — `isFromFallback = data === undefined || data === HARDCODED_CATALOG` (apply-progress #1711 inline fix vs spec literal original). |
| **REQ-OPS-128** | DEC-F4.1-09 + F2.2 `parkosFetch` precedent + backend `catalogos.py:140-147` | `tiposVehiculoApi.getTiposVehiculo()` typed wrapper async `Promise<TipoVehiculo[]>`. Internamente `parkosFetch<TiposVehiculoReadList>('/api/v1/catalogos/tipos-vehiculo')` (F2.2 — heredando retry + refresh-once 401 via Mutex + Idempotency-Key auto). `interface TipoVehiculo { uuid: string; tipo: string \| null; vigente_desde: string; vigente_hasta: string \| null; estado: string }` matching backend `schemas/tipos_vehiculo.py:13-23`. Captura 404 → `[]` (catálogo vacío es estado válido, NO retry spam). Filtro defensivo `data.filter(row => row.tipo !== null)` descarta filas legacy/corruptas. NO `fetch` directo — TODO acceso a red vía `parkosFetch`. |
| **REQ-OPS-129** | DEC-F4.1-01 defense layer + XR6 + `operacion.py:215-277` + `operacion.py:261` V5 verbatim | Defense in depth XR6 layer 4 bidireccional: (a) **Cliente (F4.1)** — `detectarTipoVehiculo(placa)` corre ANTES del round-trip API (<1ms UX rápido); (b) **Backend (F1.x ya shipped)** — `operacion.py:215-277` `detectar_tipo_vehiculo()` server-side re-valida con MISMAS regex en cada POST `/operacion/ingresos` (V5 verification — operacion.py:261 verbatim "Server overwrites via V5 (regex-derived UUID wins over client value)"). Cliente NUNCA es source of truth — backend SIEMPRE wins. JSDoc cross-link `operacion.py:215-277` garantiza sincronización manual cliente↔backend. NO agrega validación backend nueva — la regex defense in depth ya shipped F1.x. |
| **REQ-OPS-130** | DEC-F4.1-11 forward coverage + RNF-022 + F3.3 REQ-OPS-124 precedent | WCAG 2.1 AA compliance forward F6.1 — sienta las bases: (a) i18n key `operacion.placa_formato_invalido` (REQ-OPS-126) consumible con `<p role="alert" id="placa-input-error">` (atributo `id` para `aria-describedby`); (b) detector determinista → screen readers anuncian cambios predecibles (input → null → error visible → Auto detectado); (c) hook `useTiposVehiculo` retorna `isFromFallback` → permite UI accesible `<p role="status" aria-live="polite">{t('catalogos.usandoDatosLocales')}</p>` (precedent F3.3 REQ-OPS-124 Scenario 1). F6.1 forward MUST pasar axe-core con 0 violaciones WCAG 2.1 AA en 4 estados: input vacío + inválido + Auto válida + Moto válida. F4.1 NO entrega componente UI — verificación axe-core vive en F6.1 forward. Las 19 unit tests F4.1 (8 placa + 11 hook) MUST verificar la lógica determinista que F6.1 usará. |

### 4.4 CHANGELOG del canonical

**Nota**: el canonical `openspec/specs/operations/spec.md` NO contenía sección `## CHANGELOG` pre-archive (verificado vía grep `^## CHANGELOG` retornaba 0 matches). Per user instruction explícita en launch prompt "Update the CHANGELOG at the bottom of the canonical spec to add: `- 2026-09-16: F4.1 DELTA merge — added REQ-OPS-125..130 (detección tipo vehículo por placa)`", **F4.1 introduce el CHANGELOG** al canonical — diverge del precedent F3.3 (que tampoco agregó CHANGELOG al canonical post-merge, §4.4 del F3.3 archive report). Esto es intencional: F4.1 sienta el precedent para que HU futuras agreguen entries al CHANGELOG canónico. Si la práctica es aceptada, futuras HU F4.x+ agregarán sus entries.

Entry agregada al final del canonical (líneas 5456-5462):

```
## CHANGELOG

- 2026-09-16: F4.1 DELTA merge — added REQ-OPS-125..130 (detección tipo vehículo por placa)
```

---

## 5. Mechanical Copy Contract verification (5 steps all PASS)

Per `sdd-archive` skill section "Mechanical Copy Contract (MANDATORY)" + precedent F3.3 verbatim:

### Step 1: Snapshot ✅
- 5 source files SHA256-captured antes del move:
  - `proposal.md` → `A7963E6CC657A846F0FFF506995862DAEE84D10ABE3B76ADBE46DA64B81A4A82`
  - `exploration.md` → `36322C72215F05C5E0E6121D815E9C8BEEE5C40CA80EBA9F7C8174960CD9426B`
  - `design.md` → `2C93973A5E2E36B0E3FEBCB6A58008B973604B66DE8B81BA493144D1643DF342`
  - `tasks.md` → `B35BA2B8877379A050EA9214D68B4CC4567ED44F4B3CB9AE7C6161E60140ACCB`
  - `specs/operations/spec.md` → `26BCD465A15B4A5DED212BEDA40216A81349DEBBC6340D8618E5C7FFC624099C`
- Source untracked per `git status --short` → `?? openspec/changes/hu-f4-1-deteccion-tipo-vehiculo/` (archive phase moves per AGENTS.md canon).
- **Race condition documented in §2**: `verify-report.md` (sha256 `47092863B39AEFEE04578D4F22E15A4538A675D895E04C4A5D5FAE383A5C0366`) fue generado por la fase verify post-snapshot, migrado al archive folder como 6° archivo preservando el precedent F3.3.

### Step 2: Move ✅
- `Move-Item -LiteralPath "E:\easypunto_parkos\openspec\changes\hu-f4-1-deteccion-tipo-vehiculo" -Destination "E:\easypunto_parkos\openspec\changes\archive\2026-09-16-hu-f4-1-deteccion-tipo-vehiculo" -Force` ejecutado (PowerShell en Windows).

### Step 3: Diff empty readback ✅
- Compare source vs archive target (SHA256 recursivo):
  - `proposal.md` → MATCH (`A7963E6C...`)
  - `exploration.md` → MATCH (`36322C72...`)
  - `design.md` → MATCH (`2C93973A5...`)
  - `tasks.md` → MATCH (`B35BA2B8...`)
  - `specs/operations/spec.md` → MATCH (`26BCD465...`)
- **5/5 byte-identical** (passing).

### Step 4: Source absent ✅
- `Test-Path openspec/changes/hu-f4-1-deteccion-tipo-vehiculo` → **False** (PASS).
- `Get-ChildItem openspec/changes/hu-f4-1-deteccion-tipo-vehiculo -ErrorAction SilentlyContinue` → **null** (PASS, source absent).

### Step 5: Target populated ✅
- `Get-ChildItem openspec/changes/archive/2026-09-16-hu-f4-1-deteccion-tipo-vehiculo -Recurse -File | Count` → **7** (PASS, target populated con 5 source files + verify-report.md migrado + archive-report.md additive).
- File sizes verificados: 99294 + 63174 + 80235 + 48133 + 43405 + 44054 (verify-report.md) = 378295 bytes preservados byte-by-byte.

**Mechanical Copy Contract: 5/5 steps PASS, byte-identical archive**. Archive-report.md es additive-only (no existía en source pre-move), excluded from snapshot/destination comparison.

---

## 6. Files changed in source (7 files, +574/-1 LOC summary)

Detalle verbatim en `apply-progress #1711` (Engram). Resumen:

| Categoría | Count | Detalle |
|---|---|---|
| **NEW archivos** | 5 | `lib/validation/placa.ts` (+76 — REGEX_AUTO + REGEX_MOTO exportadas + `detectarTipoVehiculo()` pura con normalización trim+uppercase+replace(/\s+/g,'') + JSDoc cross-link `operacion.py:215-277`) + `lib/validation/placa.test.ts` (+58 — 8 unit tests verbatim plan.md:1381 U1..U6 + 2 extras whitespace/multi-espacio) + `features/catalogos/api/tiposVehiculoApi.ts` (+71 — `TipoVehiculo` interface + `getTiposVehiculo()` con `parkosFetch` + 404→`[]` + filtro `tipo: null`) + `features/catalogos/hooks/useTiposVehiculo.ts` (+133 — SWR token-gated + `dedupingInterval: 5 * 60 * 1000` + `HARDCODED_CATALOG` inline + `isFromFallback` + `onError` 401 → `useAuthStore.clear()` + `parkos:auth:cleared` event) + `features/catalogos/hooks/useTiposVehiculo.test.ts` (+211 — 11 unit tests U7..U11 + extras, precedent F3.3 `useSesionActiva.test.ts` verbatim pattern) |
| **MODIFY archivos** | 2 | `renderer/i18n/locales/operacion.json` (+1 key `placa_formato_invalido` verbatim plan.md:1366) + `vitest.config.ts` (+3 LOC — coverage thresholds `placa.ts: 95/95/90` + `tiposVehiculoApi.ts: 90/90/85` + `useTiposVehiculo.ts: 90/90/85` per design §7.3) |
| **Directories created** | 2 | `apps/electron-sucursal/src/lib/validation/` (F4.1 T1 location) + `apps/electron-sucursal/src/features/catalogos/{hooks,api}/` (F4.1 T2 location — primer consumer del feature `catalogos`) |
| **i18n keys agregadas** | 1 | `operacion.json`: `placa_formato_invalido` (DEC-ELEC-06 verbatim — namespace pre-existente, no new namespace) |
| **Nuevas deps npm** | 0 | F4.1 NO requiere `npm install`. `react@^18.3.1` + `swr@^2.2.5` + `vitest@^2.1.2` + `@testing-library/react@^16.0.1` ya shipped F2.x |
| **Nuevos componentes shadcn** | 0 | F4.1 NO entrega componente UI (forward F6.1 `<PlacaInput>`) |
| **Migraciones Alembic** | 0 | F4.1 NO modifica backend. Regex vive en código cliente (A-03 explícito: NO columna del ER, 4NF canon) |
| **Nuevas routes `App.tsx`** | 0 | F4.1 NO agrega rutas. F6.1 las agregará para `<PlacaInput>` |
| **Total** | **7 archivos** | **5 NEW + 2 MODIFY, +574/-1 LOC** debajo del budget 800 LOC per `config.yaml rules.tasks` |

---

## 7. Acceptance gates summary (G1..G7 from verify report)

Per `verify-report #1713`:

| Gate | Criterion | Result | Evidence |
|---|---|---|---|
| **G1** | TypeScript strict compila sin NEW errors (REQ-OPS-125, 126, 127, 128) | ✅ PASS source-level + runtime | 26 pre-existentes fuera de tsconfig.renderer.json include (sin regresión F4.1). F4.1 archivos (`placa.ts` + `placa.test.ts` + `tiposVehiculoApi.ts` + `useTiposVehiculo.ts` + `useTiposVehiculo.test.ts`) compilan limpios (`tsc --noEmit -p tsconfig.renderer.json \| grep "lib/validation\|catalogos"` → vacío) |
| **G2** | ESLint pasa (`pnpm lint`) | ✅ PASS source-level + runtime | Errores pre-existentes fuera de scope F4.1 (`e2e/` + `LoginForm.test.tsx`). F4.1 archivos lint clean (`eslint src/features/catalogos src/lib/validation vitest.config.ts` → exit 0) |
| **G3** | Unit tests PASS (`pnpm vitest run`) | ✅ PASS runtime (19/19 F4.1) | `placa.test.ts` (8/8) + `useTiposVehiculo.test.ts` (11/11) = **19 tests PASS ejecutados** (excede forecast tasks.md de 11 tests por 8 tests extra: 2 en placa + 6 en catalogos per apply-progress #1711) |
| **G4** | Atomic commits + Parkos Dev author + 0 Co-authored-by | ✅ PASS | 2/2 commits author verificado + 0 trailers + 0 AI attribution (ver §3 ledger). `git log --format='%(trailers)'` muestra solo `Refs:` trailers |
| **G5** | `useTiposVehiculo` SWR key null-when-no-token gate | ✅ PASS source-level + runtime | `useTiposVehiculo.ts:104` key null-when-no-token verbatim F3.3 precedent + `dedupingInterval === 300000` + `fallbackData === HARDCODED_CATALOG` + `shouldRetryOnError(404) === false` + `onError` status=401 dispara `useAuthStore.clear()` + `parkos:auth:cleared` event. U7 + U10 PASS |
| **G6** | WCAG 2.1 AA axe-core 0 violaciones en componente que consume F4.1 | ⚠️ PASS source-level + SKIPPED-env runtime per F.6 | F4.1 sienta bases (i18n key + detector determinista + `isFromFallback` flag). Verificación axe-core vive en F6.1 forward (forward coverage, RNF-022) |
| **G7** | e2e sandbox F.6 SKIPPED-env (`npm 11.16.0`) | ⚠️ SKIPPED-env per F.6 precedent | F4.1 NO entrega e2e — los 19 unit tests cubren la lógica pura. e2e testeará `<PlacaInput>` (F6.1) que consume F4.1. Documentado como deviation D-env per F2.x + F3.x archive precedent |

**5/7 PASS source-level + 2/7 SKIPPED-env/forward per F.6 precedent (F2.x + F3.x verbatim). 0 FAIL gates. 0 deviations. 0 blocking issues.** F4.1 es **más limpia que F3.3** (0 deviations vs F3.3 6 LOW-severity deviations) — pattern learnings aplicadas (ver §9.2).

---

## 8. Deviations documented (0 deviations — F4.1 más limpia que F3.3)

**0 deviations** detectadas en verify phase `#1713`. F4.1 fue implementada con las pattern learnings de F3.3 aplicadas preventivamente:

1. **`isFromFallback` semántica corregida en C2 (RESUELTO pre-verify)**: el spec literal original decía `data === undefined || data === HARDCODED_CATALOG` pero implementación inicial C2 solo cubría el segundo caso → U7 fallaba cuando mock retorna `data=undefined`. Fix inline C2: `data === undefined || data === HARDCODED_CATALOG` (captura ambos casos: SWR loading pre-fetch + API down fallback explícito). Documentado en apply-progress #1711 + verify-report #1713.

2. **`refresh: mutate` TS strict incompatibilidad (RESUELTO pre-verify)**: SWR `mutate` retorna `KeyedMutator<T>` incompatibles con `() => Promise<T|undefined>` en strict TS. Resuelto wrappeando en async arrow: `async () => { const r = await mutate(); return r ?? HARDCODED_CATALOG; }`. Documentado como learning reusable para F4.x+ hooks SWR.

**Comparison vs F3.3 deviations**: F3.3 tuvo 6 LOW-severity deviations (D-tsc-1..4 + D-lint-1) — todas hubieran sido evitables con las pattern learnings de F3.3 aplicadas. F4.1 implementó:
- (a) `import { useAuthStore } from '@parkos/ui-kit/store'` (NOT `/hooks` que tuvo `REFRESH_INTERVAL_MS` gap en F3.3) — gap ya cerrado en PR F3.3 R-F3.3-V1 fix
- (b) NO react-hook-form `handleSubmit` (evita signature mismatch D-tsc-handlesubmit F3.3) — F4.1 NO entrega forms
- (c) Pure function + union literals (NO `extends Error` que requiere override modifier) — evita D-tsc-return-null F3.3
- (d) Deferred UI a F6.1 (NO renders que fallen TS2322 con return null) — F4.1 NO entrega componente UI

**Nota sobre apply-phase deviations**: NO existe `apply-report.md` en el archive folder de F4.1 (precedent F2.x + F3.x verbatim). Las 0 deviations documentadas arriba son detectadas durante verify via tsc + lint + read + 19 unit tests runtime + 7 gates verification.

---

## 9. Risks identified + closed (R1..R5 from proposal + exploration)

### 9.1 Proposal risks (R1..R5, todos cerrados)

Per `proposal.md §10` + `exploration.md §9` (verbatim, R1..R5 idénticos):

| # | Risk | Severity | Mitigation | Status |
|---|---|---|---|---|
| **R1** | **Regex strictness incorrecto** — edge case (ej: placa con guion `ABC-123`) hace que la detección falle cuando el operador espera que pase | MEDIUM | DEC-F4.1-02: normalización previa (trim + uppercase + remove whitespace) ANTES de regex cubre los casos comunes. Plan.md:1366-1367 explícito: si formato no matchea, error inline + campo abierto para corrección. Sin tolerancia de tipeo (DEC-SUC-22). Si negocio reporta falsos negativos, bug fix futuro con regression test | ✅ CLOSED — implementado en `placa.ts` normalización + 8 tests U1..U8 PASS (incluyendo U5 minúsculas + U6 espacios) |
| **R2** | **Backend regex duplicada desincronizada** — cliente detecta `Auto` para `ABC123`, pero backend server-side `detectar_tipo_vehiculo()` usa regex distinta y rechaza el POST | LOW | A-03 verbatim (plan.md:454): cliente y backend tienen regex idéntica (`^[A-Z]{3}[0-9]{3}$` Auto, `^[A-Z]{3}[0-9]{2}[A-Z]$` Moto). JSDoc de `detectarTipoVehiculo()` referencia explícitamente `operacion.py:215-277`. Si divergen, es bug a corregir. Cliente NO es source of truth — backend siempre re-valida (defense in depth XR6 layer 4, operacion.py:261 verbatim) | ✅ CLOSED — JSDoc cross-link implementado + U3 verifica null para formato inválido (alineado con backend) |
| **R3** | **SWR fallback staleness** — API catálogos down, SWR muestra fallback hardcoded, operador asume catálogo completo cuando faltan tipos | LOW | DEC-F4.1-06: hook retorna `isFromFallback: boolean`. F6.x+ consumers pueden mostrar `<Tooltip>` o badge "datos locales". F4.1 NO requiere esta UI — solo expone el flag. Si API vuelve, SWR revalida automáticamente (refresh on focus / on reconnect) | ✅ CLOSED — implementado `isFromFallback` en `useTiposVehiculo.ts:130` + 11 tests cubren U7 (key null → fallback implícito) + U9 (API 500 → fallback explícito) |
| **R4** | **Missing types de retorno** — TypeScript strict requiere tipos explícitos, pero función retorna `'Auto' \| 'Moto' \| null` y caller podría olvidar el null check | LOW | DEC-F4.1-01: tipo de retorno explícito con union literals. Tests U3 (formato inválido) + U4 (placa vacía) verifican explícitamente `null`. El caller DEBE manejar `null` (TypeScript strict no compila sin narrowing). En F6.1 `<PlacaInput>`, el caller hace `if (tipo === null) { /* error inline */ } else { /* setea uuid */ }` | ✅ CLOSED — implementado tipo union literal + 6 tests U1..U6 + 2 extras PASS, F6.1 forward consumer hace narrowing |
| **R5** | **Test edge cases faltantes** — los 6 tests plan.md:1381 no cubren todos los branches posibles | LOW | DEC-F4.1-10: 6 tests + 5 hook tests cubren ≥90% líneas / 80% branches per D9. Branches no cubiertos son "placa claramente inválida que NUNCA matchearía ninguna regex real" — no casos de uso reales. Si operador digita `ABC@12`, regex NO matchea → null → error inline | ✅ CLOSED — 19 tests verde (excede forecast tasks 11) + coverage thresholds 95/95/90 + 90/90/85 per design §7.3 (CI gate con `@vitest/coverage-v8`) |

**5/5 risks CLOSED. 0 KNOWN-MISSING. 0 verification risks HIGH/CRITICAL.**

---

## 10. Forward hooks (consumers Fase 4+ que leen de este work)

Per `proposal.md §12` + `design.md §12.2` + `spec delta §6.2` + `apply-progress #1711`:

| HU Forward | Consumer | Mecanismo | Status |
|---|---|---|---|
| **HU-F4.2** (Tarifas vigentes) | `useTarifasVigentes()` peer hook en mismo feature `catalogos` | Mismo patrón SWR token-gated + dedupingInterval + fallback (en este caso `electron-store`, NO hardcoded). F4.2 entrega independientemente (peer con F4.1) | READY — pattern F4.1 reusable |
| **HU-F4.3** (Ocupación en vivo) | `<OcupacionStrip>` itera sobre tipos del catálogo | `useTiposVehiculo()` provee lista de tipos. F4.3 puede implementar su propio fetch si quiere (peer pattern). `formatTiempoTranscurrido` F3.3 disponible para "actualizado hace N" indicator | READY — hook exportado desde `features/catalogos/hooks/useTiposVehiculo.ts` |
| **HU-F6.1** (Ingreso vehicular CU-01 — **CRÍTICO**) | `<PlacaInput>` consume `detectarTipoVehiculo()` + `useTiposVehiculo()` + `REGEX_AUTO` + `REGEX_MOTO` + i18n key | Llama `detectarTipoVehiculo(placa)` → si `null` muestra `<p role="alert" aria-describedby>{t('operacion.placa_formato_invalido')}</p>`; si `'Auto'\|'Moto'` setea `uuid_tipo_vehiculo = tipos.find(t => t.tipo === ...).uuid` para POST. Constantes `REGEX_AUTO` + `REGEX_MOTO` reusables en `z.string().regex(REGEX_AUTO)`. CRÍTICO — sin F4.1, F6.1 no puede arrancar | READY — primitives consumibles |
| **HU-F7.x** (Salida + búsqueda tolerante CU-02/03) | `buscarIngresoTolerante()` función DISTINTA en archivo NUEVO | DEC-SUC-22 categórico: NUNCA compartir función con F4.1. F7.x entrega función NUEVA con tolerancia `O↔0`/`I↔1`/`B↔8`. `detectarTipoVehiculo` de F4.1 es estricta sin tolerancia — funciones DISTINTAS en archivos DISTINTOS | READY — separation of concerns honored |
| **HU-F11.x** (Sync UI) | Si sync incluye `tipos_vehiculo`, hook debe invalidarse post-sync | `mutate('/catalogos/tipos-vehiculo')` post-sync event. SWR cache invalidation pattern reusable desde F3.3 | READY — mutate exported via `refresh` callback |
| **HU-F6.x+ AuthGuard** | `parkos:auth:cleared` event emitido por 401 path | AuthGuard intercepta → `navigate('/login?next=...')`. Precedent F3.3 verbatim | READY — event emitted desde `useTiposVehiculo.ts:124` |
| **HU-F13.x** (Reportería) | `<ReporteOcupacion>` itera sobre tipos | F13.x consume via SWR shared cache + `isFromFallback` flag para advertencia "datos locales" | READY — `isFromFallback` flag available |

**Total forward hooks**: 7 consumers F4.2/F4.3/F6.1/F7.x/F11.x/AuthGuard/F13.x. Todos READY — F4.1 entrega los primitives/contratos sin cambios requeridos al canonical spec.

---

## 11. Next steps (F4.2 Tarifas + F4.3 Ocupación + F6.1 Ingreso)

### 11.1 Immediate post-archive housekeeping

1. **Verify merge**: `git diff openspec/specs/operations/spec.md` muestra +213 líneas con el bloque REQ-OPS-125..130 byte-preserved + `## CHANGELOG` al final con la entry F4.1.
2. **No commit en archive phase**: el archive phase es housekeeping. Si el repo mergea a `dev` por gitflow (per AGENTS.md canon), la materialización al canonical puede requerir un commit separado (per F3.2 + F3.3 precedent).
3. **Update `pending.md §1`**: marcar row F4.1 → ✅ (per `apply-progress #1711` + session_summary #1712 Next Steps).
4. **0 follow-up PR required**: 0 deviations detectadas (F4.1 es más limpia que F3.3 — pattern learnings aplicadas preventivamente).

### 11.2 F4.2 + F4.3 + F6.1 readiness (Fase 4 continúa)

F4.1 entrega los primitives para arrancar Fase 4 Parte II:

| F4.x HU | Scope | F4.1 dependency | Status |
|---|---|---|---|
| **F4.2** | `useTarifasVigentes()` peer hook con `electron-store` persistente | `useTiposVehiculo()` pattern SWR token-gated + fallback (peer architecture, electron-store en lugar de hardcoded) | READY |
| **F4.3** | `<OcupacionStrip>` organism + `GET /operacion/ocupacion` F1.5 | `useTiposVehiculo()` para lista de tipos + `formatTiempoTranscurrido` F3.3 para "actualizado hace N" | READY |
| **F6.1** | `<PlacaInput>` component + WCAG axe-core A1 (CRÍTICA — habilita CU-01) | `detectarTipoVehiculo()` + `useTiposVehiculo()` + `REGEX_AUTO` + `REGEX_MOTO` + i18n key `operacion.placa_formato_invalido` + aria-describedby | READY — primer consumer end-to-end de F4.1 |

### 11.3 Fase 4 → Fase 6 handoff

- **Fase 4 primera HU cerrada**: 1/9+ HU (F4.1 archivada 2026-09-16). User-facing DELTA precedent sentado 5 veces consecutivas (F1.15 + F3.1 + F3.2 + F3.3 + F4.1).
- **Fase 4 Parte II ready**: F4.2 (tarifas) + F4.3 (ocupación) pueden arrancar contra `useTiposVehiculo()` pattern + `useAuthStore` + `parkos:auth:cleared` event listener pattern exportado.
- **Forward gating crítico**: F6.1 (Ingreso vehicular CU-01 — HU más importante del producto) puede arrancar contra `detectarTipoVehiculo()` + `useTiposVehiculo()` + i18n key + `REGEX_AUTO`/`REGEX_MOTO` exportadas + defense in depth XR6 layer 4 documentado en JSDoc. **Sin F4.1, F6.1 no puede arrancar** (forward hook CRÍTICO per `pending.md §5`).

---

## 12. CHANGELOG

- **(2026-09-16) F4.1 archive complete — PASS + 6 new REQ-OPS-125..130 materialized al canonical operations spec** — 2 atomic commits archivados `9810841..a6ddd5a` (2/2 author `Parkos Dev <dev@parkos.local>` + 0 Co-authored-by + 0 AI attribution), 6 source files preserved byte-identical (proposal 99294 + exploration 63174 + design 80235 + tasks 48133 + verify-report 44054 + specs/operations/spec 43405 = 378295 bytes; verify-report.md race condition documentada en §2 — generado por verify phase post-snapshot, migrado al archive), canonical spec materialized sha256 delta (`5C965CD6C6D...` → `5D9AE9FBA41F...`, 5249 → 5462 líneas, +213), 6 new REQ-OPS-125..130 byte-preserved entre líneas 5168-5376 (sha256 embedded `C8F4CF513704...` MATCH sha256 extracted) + `## CHANGELOG` section introducida al canonical con entry F4.1 (líneas 5456-5462, primer CHANGELOG del canonical en el ciclo F1.15 + F3.x). Mechanical Copy Contract PASS (snapshot + move + 5/5 SHA256 byte-identity + source absent + target populated). 11 DEC-F4.1-01..11 ratificadas y honradas (100%), 5/7 acceptance gates PASS source-level + 2/7 SKIPPED-env/forward per F.6 precedent + 0 FAIL + **0 deviations** (F4.1 es más limpia que F3.3 — 6 pattern learnings aplicadas preventivamente). **19 unit tests F4.1 PASS ejecutados** (placa 8 + catalogos 11) — excede forecast tasks.md (11 tests) por 8 tests extra (2 placa whitespace/multi-espacio + 6 catalogos edge cases per apply-progress #1711). 7 archivos cambiados +574/-1 LOC debajo del budget 800 per `config.yaml rules.tasks` (single-PR strategy justificada, NO chained slices). 1 i18n key `operacion.placa_formato_invalido` con string literal verbatim plan.md:1366 (DEC-ELEC-06 verbatim — namespace pre-existente). 2 new directories created (`lib/validation/` + `features/catalogos/`). **Fase 4 1/9+ HU cerrada**. Ready for F4.2 Tarifas + F4.3 Ocupación + F6.1 Ingreso vehicular CU-01 (CRÍTICA). Engram observations leídos: explore #1706 + propose #1707 + spec #1708 + design #1709 + tasks #1710 + apply #1711 + verify #1713. Engram archive observation #1714 persistido con topic_key `sdd/hu-f4-1-deteccion-tipo-vehiculo/archive-report` + type architecture + scope project + capture_prompt false.

---

**End of archive report — HU-F4.1. SDD cycle complete.**
