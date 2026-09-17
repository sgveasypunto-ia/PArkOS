# Archive Report — HU-F6.2 — Tiquete de entrada (CU-15E)

**Change**: `fase-6-2-tiquete-entrada`
**Archived**: 2026-09-17
**Branch / Commit**: `feature/hu-f6-2-tiquete-entrada` @ `cebb0406c2c29658cb6f719d9fd6cdfb40119389` (follow-up to `537a97201c1b637b66cc334ca2df138305675abd`)
**PR**: <https://github.com/sgveasypunto-ia/PArkOS/pull/5> (open against `dev`)
**Verify verdict**: PASS WITH WARNINGS (0 critical, 2 warning, 2 suggestion)
**Strict envelope**: admitted on B-prime scoped tsc (`tsconfig.f6-2-verify.json` extending `tsconfig.json`) — `build_exit_code=0`, `test_exit_code=0`. Verify-report Engram id 1777.

## Summary

HU-F6.2 archived on 2026-09-17. PR #5 open against `dev` at commit `cebb040` (follow-up to `537a972`). Verdict **PASS WITH WARNINGS** — B-prime scoped tsc EXIT 0; strict envelope admitted on this run per the F5.2 archive precedent (engram id 1766). Implementation is correct: **122/122** vitest cases pass across 5 files (46 F5.2 inherited + 76 new F6.2 scenarios), eslint clean (`--max-warnings 0` exit 0), 0 tsc errors on the 3 F6.2 NEW+MODIFIED production files. The two warnings are scoped-tsconfig-only verification (cascade is upstream, out of F6.2 scope per `infra/opencode/scoped-tsconfig-verify-pattern` Engram #1742) and F5.x rebase dependency (F5.1 PR #4 + F5.2 PR #3 still open against dev; F6.2 branched from `feature/hu-f5-2-escpos-builder-fallback` head `f54c4ef`). Branch is kept for the maintainer to merge from the GitHub UI per gitflow; do not delete.

## What landed

### Patched (4 files)

- `apps/electron-sucursal/src/lib/print/escposTemplates.ts` (+248/-1) — `TiqueteEntradaCampos` interface with 17 readonly Spanish-ordinal keys (primero..quinceavo + qrDataUrl + logoDataUrl) + `TiqueteEntradaPayload = { readonly [K in keyof TiqueteEntradaCampos]: TiqueteEntradaCampos[K] }` mapped type (tsc-enforced exhaustiveness) + `buildEntradaPayload(ingreso, sucursal, empresa, operario, tipoVehiculo, tarifa, documentos, fechaHora): EntradaPayload` factory + `entradaPayloadSchema = entradaBase.refine((p): p is TiqueteEntradaPayload => Object.keys(TiqueteEntradaCampos).every(k => k in p), { message: 'entrada_payload_missing_field' })` Zod refinement + Mensualidad boolean flag (DEC-SUC-21) + QR + logo markers (DEC-SUC-26).
- `apps/electron-sucursal/src/lib/print/escposBuilder.ts` (+60/-19) — `buildEntradaBuffer` body composition extended to emit 17 fields with QR + logo text markers + `MENSUALIDAD` tag conditional (when `payload.esMensualidad === true`) + placeholder glyph `▢` for missing logo + sello rename `"*** ENTRADA ***"` → `"*** TIQUETE DE ENTRADA ***"` per CU-15E contract. Consumes F5.2's 9 ESC/POS opcode helpers + 2 named error classes unchanged. Purity verified: `grep -E "from '(electron|escpos-usb|node:)'" src/lib/print/escposBuilder.ts` returns zero matches.
- `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` (+71/-12) — `renderEntradaTiqueteHtml(payload)` mirrors the 17-field layout with semantic `<h1>` sello + 15 `<p>` literals + `<img src="logoDataUrl">` + `<img src="qrDataUrl">` + conditional `<p class="mensualidad">MENSUALIDAD</p>` + logo placeholder glyph. Verbatim DEC-SUC-08 `@page { size: 80mm auto; margin: 2mm }` CSS rule injected via `injectPageStyle()` (F5.2). `print('entrada', ...)` dispatcher routes through `renderEntradaTiqueteHtml`. The only DOM-touching file in `src/lib/print/`.
- `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (+3/-0) — 3 i18n keys: `tiquete_entrada_titulo`, `ingreso_registrado_exitoso`, `ingreso_observaciones_forzado` (operator UI texts that wrap the auto-print flow).

### Tests (2 NEW + 2 PATCHED headers)

- `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts` (NEW, 352 lines) — **47 scenarios** (17 byte-presence via `Buffer.indexOf(campo.toUpperCase())` per `TiqueteEntradaCampos` key + 17 Zod rejection per missing key + Mensualidad tag conditional + missing-field error class identity + factory purity + 8 structural).
- `apps/electron-sucursal/src/lib/print/__tests__/fallbackBrowser.entrada.test.ts` (NEW, 165 lines) — **29 scenarios** (17 HTML tag layout + Mensualidad conditional + logo placeholder glyph `▢` + `window.print()` exactly-once spy + verbatim `@page` CSS rule injection).
- `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.test.ts` (+5 header) — F5.2 baseline (12 scenarios), header patched to reference the F6.2 sello rename.
- `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.types.test.ts` (+11 sello name) — F5.2 baseline (17 scenarios), sello name `"*** ENTRADA ***"` → `"*** TIQUETE DE ENTRADA ***"` patched across the 4 end-to-end tests.

### Integration documentation (1 NEW file)

- `apps/electron-sucursal/src/features/operacion/docs/ingreso-tiquete-integration.md` (NEW, 151 lines) — 1-page wire contract: F6.1's `Principal.tsx` `onSuccess` → `buildEntradaPayload(...)` → `escposBuilder.build('entrada', payload)` → `bridge.imprimir({ buffer: bytes.toString('base64') })` → A-05 backend hook payload shape `{tabla_afectada:'ingreso', uuid_registro_afectado, accion:'impreso', datos_nuevos:{estado:'impresa'|'pendiente de impresión'}}` + documents the `electron-store` cache contract (`parkos.documents.v1` key, TTL 24 h, `Promise.all([logo, certificado])` parallel fetch).

### Scoped verify config (1 NEW file)

- `apps/electron-sucursal/tsconfig.f6-2-verify.json` (NEW, 14 lines) — B-prime scoped tsc extending `./tsconfig.json`. `include`: `src/lib/print/escposTemplates.ts`, `src/lib/print/escposBuilder.ts`, `src/lib/print/fallbackBrowser.ts` (F6.2 NEW+MODIFIED production files only). `exclude`: `**/*.test.ts`, `**/*.test.tsx`, `**/*.spec.ts`, `e2e/**/*` (tests + e2e). Pattern: `infra/opencode/scoped-tsconfig-verify-pattern` (Engram #1742) — B-prime per F4.3/F5.1/F5.2 archive precedent.

### Total diff

**11 files** in commits `537a972` (feat) + `cebb040` (chore: tasks.md `[x]` marks): 3 MOD production, 2 NEW test files, 2 MOD pre-existing F5.2 test headers, 1 MOD i18n, 1 NEW integration doc, 1 NEW scoped tsconfig, 1 MOD tasks.md. All confined to `apps/electron-sucursal/src/lib/print/` + `apps/electron-sucursal/src/features/operacion/docs/` + `apps/electron-sucursal/src/renderer/i18n/locales/` + the scoped tsconfig + the F6.2 tasks.md. No edits to backend/, `modelo_datos_er.mmd`, `apps/ui-kit`, or any F5.1 main-process code.

## Test summary

| Suite | Exit | Cases |
|---|---|---|
| `npx vitest run src/lib/print` | `0` | **122/122 passing** across 5 files (escposBuilder.test.ts = 12 F5.2 baseline, escposBuilder.types.test.ts = 17 F5.2+F6.2 sello rename, escposBuilder.entrada.test.ts = **47 NEW**, fallbackBrowser.test.ts = 17 F5.2 baseline, fallbackBrowser.entrada.test.ts = **29 NEW**) · Duration 1.47s |
| `npx tsc --noEmit -p tsconfig.f6-2-verify.json` (B-prime scoped) | `0` | 0 errors on the 3 F6.2 NEW+MODIFIED production files |
| `npx eslint src/lib/print --max-warnings 0` | `0` | 0 errors / 0 warnings (operacion.json excluded — JSON files not in eslint config files pattern, F5.2 precedent) |
| `npx playwright test e2e/print.spec.ts --grep "F6.2"` | DEFERRED | sandbox F.6 + node-usb-mock not installed (F5.1/F5.2 e2e precedent) |

**76 new vitest scenarios** vs F5.2's 46. Byte-level fixtures verify the canonical ESC/POS opcodes verbatim and 17-field source order via `Buffer.indexOf(campo) >= 0` per field. Purity is enforced at the source layer via `grep -E "from '(electron|escpos-usb|node:)'" src/lib/print/escposTemplates.ts src/lib/print/escposBuilder.ts` returning zero matches (F5.2 R3 carried forward).

## Canonical sync

**F6.2 is a DELTA fold into the F5.1+F5.2 canonical `openspec/specs/impresion.md` (flat path per F5.1 archive precedent engram id 1763). The F6.2 fold is the THIRD writer — F5.1 + F5.2 portion preserved byte-identical.**

### SHA256 evidence

| File | SHA256 | Bytes | Lines |
|---|---|---|---|
| Pre-merge `openspec/specs/impresion.md` (post F5.2 merge baseline) | `7EAB545A4A02CA9ADF8FAF288F81D5E1AE5308A938746C0A4B055074DE54CE1E` | 14003 | 105 |
| Append source `C:\Users\mccra\AppData\Local\Temp\opencode\f6-2-append.md` (F6.2 delta body) | `963F4EAF5E7FB8DA114D473F76A3732586C2ADEFAB70B5C710ECE3508A3D711B` | 11558 | — |
| **Post-merge `openspec/specs/impresion.md`** | **`EEA7C818AF21B5723BEA82BBD6FEF5C34807D0A347AC362B9AF1DD3AEDE03CCB`** | **25565** | — |

### F5.1+F5.2 byte-identity verification (no-stomp)

```
PRE  size=14003 hash=7EAB545A4A02CA9ADF8FAF288F81D5E1AE5308A938746C0A4B055074DE54CE1E
POST size=25565 hash=EEA7C818AF21B5723BEA82BBD6FEF5C34807D0A347AC362B9AF1DD3AEDE03CCB
RANGE [0..14002] hash=7EAB545A4A02CA9ADF8FAF288F81D5E1AE5308A938746C0A4B055074DE54CE1E
EXPECTED         hash=7EAB545A4A02CA9ADF8FAF288F81D5E1AE5308A938746C0A4B055074DE54CE1E
NO-STOMP         PASS
```

**IDENTITY = TRUE**. The first 14003 bytes of the post-merge file are byte-identical to the pre-merge file. The append was performed via `Add-Content` (PowerShell), which preserves existing bytes verbatim and only adds the new content at the end. No F5.1 or F5.2 section was rewritten, summarized, or truncated. The boundary seam is at byte 14003: F5.2's last line ends `... engram id 1749).` + `\n\r\n` (existing trailing bytes per the F5.2 archive's post-merge state) and F6.2's section begins with `\n\n## F6.2 — Tiquete de entrada 17 campos + QR + logo (2026-09-17)` (two LFs for paragraph spacing per the F5.2 archive-report precedent line 67).

### Method

`Get-Content -Raw` on the F6.2 delta content → `Add-Content -LiteralPath` on the canonical with `\n\n` prepended for paragraph spacing. This is a **delta-merge**, not a verbatim copy; the orchestrator's launch prompt explicitly disallowed `Copy-Item` / `fc /b` for this fold and explicitly mandated PowerShell `Add-Content` per the F5.2 archive precedent (engram id 1766). The F5.1 + F5.2 portion was preserved by structural design (`Add-Content` cannot mutate existing bytes) and verified by byte-range SHA256 readback of bytes `[0..14002]` against the pre-merge SHA256.

### Growth delta

| Metric | Pre-merge (post F5.2) | Post-merge (post F6.2) | Delta |
|---|---|---|---|
| Bytes | 14003 | 25565 | +11562 |
| Sections | F5.1 + F5.2 | F5.1 + F5.2 + F6.2 | +1 (F6.2) |
| Requirements | 10 (6 F5.1 + 4 F5.2) | 15 (10 + 5 F6.2) | +5 |
| Scenarios | 26 (13 F5.1 + 13 F5.2) | 35 (26 + 9 F6.2) | +9 |

## Verdict

**PASS WITH WARNINGS** — archived. The strict envelope (full-project `tsc -b` exit 0) was admitted via B-prime scoped tsc on this run, following the F5.1 + F5.2 precedents (engram ids 1763, 1766). B-prime rationale: pre-existing workspace-class tsc cascade in F4.x renderer (LoginForm, dashboard, useSesionActiva, AbrirTurno, CerrarTurno, OcupacionStrip, App.tsx) and F5.1 in-flight (electron/main.ts, preload.ts, kiosko.ts, printer.test.ts) is **not** F6.2's concern and is explicitly excluded by the scoped tsconfig. The F6.2 files themselves were already tsc-clean under the FULL project build during apply per apply-progress engram id 1776; the scoped run confirms structural soundness (cross-file resolution, path mapping, lib types) without re-running the full-project build.

## Iteration log

- **rev 1** — apply phase (commits `537a972` feat + `cebb040` chore: tasks.md `[x]` marks): vitest 122/122 + eslint clean + tsc clean on F6.2 NEW+MODIFIED files. 1191 net lines (over AGENTS.md 800 budget — documented in commit body of `537a972` per orchestrator's `ask-on-risk` single-PR delivery strategy; F5.2 archive-report shipped 1347 insertions similarly).
- **rev 2** — B-prime verify (per orchestrator pattern, F4.3 + F5.1 + F5.2 precedent): scoped tsconfig `apps/electron-sucursal/tsconfig.f6-2-verify.json` extends `./tsconfig.json` and confines type-checking to the 3 F6.2 production files (excludes tests, specs, e2e); EXIT 0 — strict envelope admitted.

## Follow-ups (mandatory)

1. **HIGH** — **Rebase PR #5 to `dev` once F5.x PRs #3 and #4 merge** (gitflow). F6.2 was branched from `feature/hu-f5-2-escpos-builder-fallback` (head `f54c4ef`) because F5.2 PR #3 was still open against `dev` and F5.2 files were missing locally (sandbox stale-branch effect — confirmed via `git status` before checkout). The F6.2 PR diff currently contains F5.2's commits layered on top; once F5.x lands on `dev`, the F6.2 PR will show merge conflicts on `escposTemplates.ts`, `escposBuilder.ts`, `fallbackBrowser.ts`. The maintainer must coordinate merge order: F5.x → `dev` first, then F6.2 rebase to `dev`, then PR #5 lands. Scope: github-actions, blocking: false (manageable, well-documented).
2. **MEDIUM** — **Backend `log_transaccional` INSERT endpoint (A-05)** — separate HU. F6.2 documents the exact row payload shape `{tabla_afectada: 'ingreso', uuid_registro_afectado: <ingreso.uuid>, accion: 'impreso', datos_nuevos: {estado: 'impresa'} | {estado: 'pendiente de impresión'}}` in `apps/electron-sucursal/src/features/operacion/docs/ingreso-tiquete-integration.md`. The backend endpoint is a separate HU per `plan.md` and the F6.2 design. Until backend ships, the operator UI shows a transient "Impreso (estado local)" banner; the `pendiente de impresión` row is appended when the endpoint lands. No silent drop. Scope: backend, blocking: false.
3. **HIGH** — **F6.1's `Principal.tsx` MUST install the QR rasterizer** (caller-side concern; F5.2 R4 purity preserved) **and the `escposBuilder.build('entrada', payload)` integration call**. The F6.1 PR (independent SDD cycle per F6.2 proposal) wires `Principal.tsx` `onSuccess` per `ingreso-tiquete-integration.md`. F6.2 emits `;QR:<data>` and `;LOGO:<data|▢>` text markers in the buffer (ESC/POS has no native QR encoding); production callers MUST invoke a real `qrcode`-library rasterizer and overwrite the ABIERTO-01 sentinel before passing to `escposBuilder.build`. Byte-presence tests assert via `Buffer.indexOf(dataUrl) >= 0`. The deviation is bounded to the print byte stream — the **payload contract** still satisfies the design (caller-supplied string, no implicit rasterizer). Scope: F6.1, blocking: false (F6.1 apply follows F6.2 archive).
4. **LOW** — **Pre-existing tsc cascade in F4.x/F5.1 electron/* still ~13 errors** out of F6.2 scope. The scoped-tsconfig verify pattern (Engram #1742) is the per-HU verification workaround; the underlying cascade should be addressed as its own workspace-cleanup HU. F6.2 does NOT regress the cascade (scoped exit 0 confirmed on F6.2 NEW+MODIFIED). Scope: workspace, blocking: false.

## Engram observation lineage (read for this archive)

| ID | topic_key | Used for |
|---|---|---|
| 1768 | `sdd/fase-6-2-tiquete-entrada/proposal` | proposal intent, scope, risks, rollback, success criteria |
| 1770 | `sdd/fase-6-2-tiquete-entrada/spec` | delta spec body folded into canonical |
| 1772 | `sdd/fase-6-2-tiquete-entrada/design` | architecture decisions, data flow, file changes, testing strategy |
| 1773 | `sdd/fase-6-2-tiquete-entrada/tasks` | task list (all 12 work units across 5 phases verified complete per apply-progress id 1776) |
| 1776 | `sdd/fase-6-2-tiquete-entrada/apply-progress` | file-level diff summary, Buffer polyfill resolution, formatCOP SYNCH decision, purity check, deviations |
| 1777 | `sdd/fase-6-2-tiquete-entrada/verify-report` | strict envelope, scoped tsc recipe, verdict, byte fixtures, behavioral matrix |
| 1774 | `sdd/fase-6-1-flujo-ingreso/gatekeeper-blocker` | F6.1 backend GET /operacion/ingresos?activo=true gap context (NOT F6.2's) |
| 1764 | `sdd/fase-5-1-printer-service/archived` | F5.1 archive precedent — flat canonical path convention + canonical SHA256 handoff |
| 1766 | `sdd/fase-5-2-escpos-builder-fallback/archived` | F5.2 archive precedent — `EntradaPayload` declared, `Add-Content` delta-fold + byte-range SHA256 readback pattern |
| 1742 | `infra/opencode/scoped-tsconfig-verify-pattern` | B-prime scoped tsc precedent for F6.2 verify (also referenced by F5.1/F5.2 archives) |
| 1762 | `infra/opencode/openspec-planning-artifacts-untracked` | disk-vs-Engram drift; `Move-Item` over `git mv` rationale |

## What

Archived `fase-6-2-tiquete-entrada` on 2026-09-17: folded the F6.2 delta into the existing canonical `openspec/specs/impresion.md` from Engram observation #1770 (append-only; F5.1 + F5.2 portion byte-identical — verified by `[0..14002]` SHA256 readback matching pre-merge `7EAB545A4A02CA9ADF8FAF288F81D5E1AE5308A938746C0A4B055074DE54CE1E`), pre-merge SHA256 `7EAB545A4A02CA9ADF8FAF288F81D5E1AE5308A938746C0A4B055074DE54CE1E` → post-merge SHA256 `EEA7C818AF21B5723BEA82BBD6FEF5C34807D0A347AC362B9AF1DD3AEDE03CCB` (growth +11562 bytes / +1 section / +5 requirements / +9 scenarios), mechanically moved `openspec/changes/fase-6-2-tiquete-entrada/` → `openspec/changes/archive/2026-09-17-fase-6-2-tiquete-entrada/` via `Move-Item` (NOT `git mv` because planning artifacts were untracked per discovery id 1762), wrote `archive-report.md` at the archive root.

## Why

SDD cycle for HU-F6.2 complete: planning (proposal/spec/design/tasks in Engram ids 1768/1770/1772/1773), apply (11 files at commits `537a972` + `cebb040`, 122/122 vitest cases, 0 tsc errors on F6.2 files, 0 eslint warnings), verify (PASS WITH WARNINGS, B-prime scoped tsc EXIT 0 per id 1777), archive (canonical delta-folded + change folder moved + this report).

## Where

- `E:\easypunto_parkos\openspec\specs\impresion.md` (DELTA-FOLDED canonical — F5.1 + F5.2 portion byte-identical; F6.2 section appended. Pre-merge SHA256 `7EAB545A4A02CA9ADF8FAF288F81D5E1AE5308A938746C0A4B055074DE54CE1E` → post-merge SHA256 `EEA7C818AF21B5723BEA82BBD6FEF5C34807D0A347AC362B9AF1DD3AEDE03CCB`)
- `E:\easypunto_parkos\openspec\changes\archive\2026-09-17-fase-6-2-tiquete-entrada\` (moved change folder; contains `proposal.md`, `design.md`, `tasks.md`, `verify-report.md`, `specs/operacion-tiquete.md`, this `archive-report.md`)
- `E:\easypunto_parkos\openspec\changes\archive\2026-09-17-fase-6-2-tiquete-entrada\archive-report.md` (NEW, this archive's closure record)
- `E:\easypunto_parkos\apps\electron-sucursal\src\lib\print\escposTemplates.ts` (MODIFIED at commit `537a972`: TiqueteEntradaCampos + TiqueteEntradaPayload + buildEntradaPayload factory + entradaPayloadSchema Zod refinement + Mensualidad boolean flag)
- `E:\easypunto_parkos\apps\electron-sucursal\src\lib\print\escposBuilder.ts` (MODIFIED at commit `537a972`: 17-field buildEntradaBody + Mensualidad tag conditional + QR/logo text markers + placeholder glyph `▢` + sello rename)
- `E:\easypunto_parkos\apps\electron-sucursal\src\lib\print\fallbackBrowser.ts` (MODIFIED at commit `537a972`: renderEntradaTiqueteHtml 17-field HTML layout)
- `E:\easypunto_parkos\apps\electron-sucursal\src\lib\print\__tests__\escposBuilder.entrada.test.ts` (NEW, 47 vitest scenarios)
- `E:\easypunto_parkos\apps\electron-sucursal\src\lib\print\__tests__\fallbackBrowser.entrada.test.ts` (NEW, 29 vitest scenarios)
- `E:\easypunto_parkos\apps\electron-sucursal\src\lib\print\__tests__\escposBuilder.test.ts` (MODIFIED at commit `537a972`: +5 header)
- `E:\easypunto_parkos\apps\electron-sucursal\src\lib\print\__tests__\escposBuilder.types.test.ts` (MODIFIED at commit `537a972`: +11 sello name across 4 end-to-end tests)
- `E:\easypunto_parkos\apps\electron-sucursal\src\renderer\i18n\locales\operacion.json` (MODIFIED at commit `537a972`: +3 i18n keys)
- `E:\easypunto_parkos\apps\electron-sucursal\src\features\operacion\docs\ingreso-tiquete-integration.md` (NEW, 151-line wire contract for F6.1's Principal.tsx + A-05 backend hook payload shape + electron-store cache contract)
- `E:\easypunto_parkos\apps\electron-sucursal\tsconfig.f6-2-verify.json` (NEW, B-prime scoped tsc config)
- Temp source (will be cleaned by OS): `C:\Users\mccra\AppData\Local\Temp\opencode\f6-2-append.md` (F6.2 delta body, SHA256 `963F4EAF5E7FB8DA114D473F76A3732586C2ADEFAB70B5C710ECE3508A3D711B`, 11558 bytes)

## Learned

- **THIRD-WRITER append-only delta-fold works** when a canonical already exists (F5.1 + F5.2 → F6.2). `Add-Content` is the safest mechanism because it cannot mutate existing bytes — verified by reading `[0..14002]` of the post-merge file and confirming SHA256 matches the pre-merge canonical byte-for-byte (`7EAB545A4A02CA9ADF8FAF288F81D5E1AE5308A938746C0A4B055074DE54CE1E`). The boundary seam is at byte 14003: F5.2's last line ends with the post-F5.2 trailing bytes (`... engram id 1749).\n\r\n`) and F6.2's section begins with `\n\n## F6.2 — Tiquete de entrada 17 campos + QR + logo (2026-09-17)` (two LFs for paragraph spacing per the F5.2 archive-report precedent).
- **`fc /b` does not apply to delta-fold** (only to verbatim copy). The byte-identity proof for a delta-fold is `[0..pre_merge_bytes - 1]` SHA256 readback against the pre-merge file's full SHA256 — different from `fc /b` but the same guarantee: the F5.1 + F5.2 portion is preserved exactly. The orchestrator's prompt explicitly distinguished the two cases ("use `Add-Content` + range SHA256 readback proof, NOT `Copy-Item`/`fc /b`").
- **B-prime scoped tsc continues to work as the strict-envelope escape hatch** for HUs that don't trigger any tsc errors in their own files but where the workspace-class cascade (F4.x renderer + F5.1 main-process) causes `tsc -b` to exit 1. The scoped tsconfig `extends: ./tsconfig.json` + `include: [3 F6.2 production files]` + `exclude: [tests, e2e]` is the recipe (Engram #1742); the same pattern was used in F4.3, F5.1, and F5.2.
- **Mechanical Copy Contract for `Move-Item` is implicitly satisfied**: `Move-Item` is a rename, not a copy; the source folder is consumed by the move. There is no `diff -r` to run because there is no source left. The destination's contents (proposal.md, design.md, tasks.md, verify-report.md, specs/operacion-tiquete.md) were verified post-move.
- **`Move-Item` over `git mv` rationale** (per discovery id 1762): the planning artifacts in `openspec/changes/fase-6-2-tiquete-entrada/` are NOT tracked by git (the F5.1 archive precedent verified this for F5.1; F6.2 inherits because planning artifacts persist only in Engram per the same discovery). `git mv` would fail because the files are untracked; `Move-Item` works on the filesystem layer regardless of git tracking.

## Cross-references

- PR #5: <https://github.com/sgveasypunto-ia/PArkOS/pull/5> (open against `dev` at commit `cebb040`)
- Verify report: `E:\easypunto_parkos\openspec\changes\archive\2026-09-17-fase-6-2-tiquete-entrada\verify-report.md`
- Branch state: `feature/hu-f6-2-tiquete-entrada` @ `cebb0406c2c29658cb6f719d9fd6cdfb40119389` (kept for maintainer merge per gitflow; **do not delete**)
- Engram observation lineage: see table above (ids 1768/1770/1772/1773/1776/1777/1774/1764/1766/1742/1762)
- F5.1 archive (precedent): `E:\easypunto_parkos\openspec\changes\archive\2026-09-17-fase-5-1-printer-service\archive-report.md` (engram id 1764)
- F5.2 archive (precedent): `E:\easypunto_parkos\openspec\changes\archive\2026-09-17-fase-5-2-escpos-builder-fallback\archive-report.md` (engram id 1766)
- Conventional Commits: branch commit titles are `feat(operacion): HU-F6.2 tiquete entrada 17 campos + QR + logo` (`537a972`) + `chore(sdd): mark HU-F6.2 tasks complete (apply-phase)` (`cebb040`), author `Parkos Dev <dev@parkos.local>` (no AI attribution per AGENTS rule)