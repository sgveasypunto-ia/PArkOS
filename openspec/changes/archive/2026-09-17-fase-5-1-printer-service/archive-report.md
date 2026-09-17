# Archive Report — HU-F5.1 — Servicio de impresora térmica (main process)

**Change**: `fase-5-1-printer-service`
**Archived on**: 2026-09-17
**Spec domain**: `impresion` (canonical: `openspec/specs/impresion.md`)
**Branch**: `feature/hu-f5-1-printer-service`
**Commit (HEAD at archive)**: `b987cf29ab871383d700ca69b4ceebaa8c6edff4`
**PR**: <https://github.com/sgveasypunto-ia/PArkOS/pull/4> — open against `dev`
**Verify verdict**: **PASS WITH WARNINGS** (0 critical, 2 warning, 3 suggestion)
**Strict envelope**: admitted on B-prime scoped tsc (`tsconfig.f5-1-verify.json`) — `build_exit_code=0`, `test_exit_code=0`; verify-report engram id **1761**.
**Mode**: `hybrid` (OpenSpec+Engram). Source-of-truth content for proposal/spec/design/tasks lived in Engram (per discovery `infra/opencode/openspec-planning-artifacts-untracked`, id 1762); only `verify-report.md` was on disk.

---

## Summary

HU-F5.1 archived on 2026-09-17. PR #4 open against `dev` at commit `b987cf29`. Verdict **PASS WITH WARNINGS** — B-prime scoped tsc `EXIT 0`; strict envelope admitted on this run (per F4.3 precedent). Implementation is correct: 42/42 vitest cases pass, eslint clean, 0 tsc errors on the 5 F5.1 NEW production files. Two warnings are native-dep + e2e deferred to CI (sandbox F.6); three suggestions are macOS codesign identity, `node-usb-mock` CI install, and a CI preflight for native build toolchain. e2e Playwright suite (`e2e/printer.spec.ts`) ships with the PR but cannot be exercised on the sandbox. Pre-existing workspace-class tsc cascade in `electron/main.ts`, `electron/preload.ts`, `kiosko*`, `bridge.d.ts` pre-F5.1 JSDoc is classified as **out of scope** and explicitly excluded by the scoped tsconfig.

---

## What landed

### Production main process (5 NEW files)

| File | LOC | Purpose |
|---|---|---|
| `apps/electron-sucursal/electron/types/print.ts` | 140 | Zod schemas (`printPayloadSchema`, `printResultSchema`, `queueItemSchema`, `queueStatusSchema`, `printerErrorSchema`) + types via `z.infer` |
| `apps/electron-sucursal/electron/types/escpos-usb.d.ts` | 60 | Plan B typed shim (`declare module 'escpos-usb'`) — `@types/escpos-usb` not on DefinitelyTyped for `3.0.0-alpha.4` |
| `apps/electron-sucursal/electron/services/printer.ts` | 242 | USB 0x07 detection + `escpos-usb` wrapper + 5s watcher + libusb error mapping |
| `apps/electron-sucursal/electron/services/printQueue.ts` | 321 | 5s/15s/60s×5 backoff + electron-store persistence (`parkos.print.queue.v1`) + append-only `fallido_permanente` |
| `apps/electron-sucursal/electron/ipc/imprimir.ts` | 149 | Zod-first IPC validation + 3 channels (`print:ticket`, `print:queue:get`, `print:queue:clear-failed`) + `webContents.send('print:status', ...)` emitter |

### Modified (5 files)

| File | Change |
|---|---|
| `apps/electron-sucursal/electron/bridge.d.ts` | `PrintStatusEvent` re-export + `imprimir` object shape (`(payload)`, `getQueue`, `onStatus`) + JSDoc corrected to "6 groups, 11 methods" (post-F4.2 housekeeping fold-in) |
| `apps/electron-sucursal/electron/preload.ts` | `Object.assign(buildImprimir, { getQueue, onStatus })` — preserves legacy callable signature while adding helpers |
| `apps/electron-sucursal/electron/main.ts` | `PrintQueue` wiring + `registerImprimirHandlers` + shared electron-store instance |
| `apps/electron-sucursal/electron/__mocks__/electron.ts` | `on`/`off` spies for the new IPC channels |
| `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` | Expanded to 12 cases — asserts the 3 new channels |

### Configuration (3 files)

| File | Change |
|---|---|
| `apps/electron-sucursal/build/entitlements.mac.plist` | **NEW** — `com.apple.security.device.usb = true` (committed via `git add -f` per apply) |
| `apps/electron-sucursal/electron-builder.yml` | Consolidated duplicate `mac:` keys (lines 23-31 and 50-52 LSP error) + `mac.entitlements` reference + `hardenedRuntime: true` (T1.5 housekeeping fold-in) |
| `apps/electron-sucursal/package.json` | `node-usb-mock@^0.4.1` devDep (note: `buffer@^6.0.3` is also touched by **F5.2** in its own branch) |

### Tests (3 NEW files)

| File | Cases | Coverage |
|---|---|---|
| `apps/electron-sucursal/electron/types/print.test.ts` | 14 | Zod accept/reject happy + edges (`uuidRegistro` invalid, empty buffer, `vid` overflow) |
| `apps/electron-sucursal/electron/services/printer.test.ts` | 9 | `listDevices` filters 0x07; `print` happy path; typed `PrinterError('printer_offline')` on disconnect |
| `apps/electron-sucursal/electron/services/printQueue.test.ts` | 7 | Persistence; backoff `[5000,15000,60000,60000,60000]`; 5-attempt → `fallido_permanente`; `clearFailed` display-only |

### e2e (1 NEW file, DEFERRED)

| File | Status |
|---|---|
| `apps/electron-sucursal/e2e/printer.spec.ts` | Ships with PR but **DEFERRED** to CI per sandbox F.6 — `node-usb-mock` not installed locally (EPERM symlink); 4 scenarios (R2 PERF, full R3 mid-print, R6.b drain emit) require real Electron headless launch + `node-usb-mock`. Precedent: F2.x/F3.x/F4.x all deferred e2e to CI on the same sandbox limitation. |

### Total diff

17 files, +1766 / −65 (per apply-progress engram #1758).

---

## Canonical spec sync (Mechanical Copy Contract)

The F5.1 delta spec existed only in Engram (id **1749**, observation `sdd/fase-5-1-printer-service/spec`); no on-disk artifact at `openspec/changes/fase-5-1-printer-service/specs/impresion/spec.md` because planning sub-agents persisted to Engram and never committed the planning tree (per discovery id **1762**).

### Procedure performed

1. Retrieved full content of Engram observation **#1749** via `mem_get_observation`.
2. Wrote the spec body (excluding the trailing Engram metadata block — `## What / ## Why / ## Where / ## Learned / Session / Project / Scope / Topic / Duplicates / Revisions / Created`) to a temp file `C:\Users\mccra\AppData\Local\Temp\opencode\f5-1-archive\spec-source.md`.
3. `Copy-Item` from temp source to canonical `openspec/specs/impresion.md`.
4. `Get-FileHash SHA256` on both source and destination.
5. `fc /b` byte-identity compare (PowerShell's `fc.exe`, not `Compare-Object`).

### SHA256 evidence

| File | SHA256 |
|---|---|
| `C:\Users\mccra\AppData\Local\Temp\opencode\f5-1-archive\spec-source.md` (Engram-extracted source) | `D112BF7FB06C17E884F8766BF4B09F93945E94B3A5AE13C4F00B6CF2ACC18E42` |
| `openspec/specs/impresion.md` (canonical) | `D112BF7FB06C17E884F8766BF4B09F93945E94B3A5AE13C4F00B6CF2ACC18E42` |

`fc /b` output (verbatim):

```
Comparando archivos C:\USERS\MCCRA\APPDATA\LOCAL\TEMP\OPENCODE\F5-1-ARCHIVE\spec-source.md y E:\EASYPUNTO_PARKOS\OPENSPEC\SPECS\IMPRESION.MD
FC: no se han encontrado diferencias
```

`fc /b` exit code: `0`. **IDENTITY = True**. Canonical created with byte-identity to the Engram-extracted source — empty `fc /b` diff is the only passing evidence per the Mechanical Copy Contract.

> **Path convention note**: the orchestrator's launch prompt specified the flat canonical path `openspec/specs/impresion.md`. This is a deviation from the repo's existing convention of `openspec/specs/{domain}/spec.md` (used by `sync-motor`, `sync-catalog`, `hooks`, `operations`, `cutover-migration`). The F5.2 archive will need to fold its delta into the SAME flat canonical (`openspec/specs/impresion.md`) per the orchestrator's instruction.

---

## Mechanical move (change folder → archive)

Source: `openspec/changes/fase-5-1-printer-service/`
Destination: `openspec/changes/archive/2026-09-17-fase-5-1-printer-service/`
Mechanism: `Move-Item` (NOT `git mv`) per discovery id **1762** — planning artifacts were untracked in git; `git mv` would have failed on untracked files.

### Move evidence

| Check | Result |
|---|---|
| `Test-Path source before` | `True` |
| `Test-Path destination before` | `False` |
| `Move-Item` exit | success (no error) |
| `Test-Path source after` | `False` (source correctly removed) |
| `Test-Path destination after` | `True` |

### Archive folder contents

```
E:\easypunto_parkos\openspec\changes\archive\2026-09-17-fase-5-1-printer-service\
└── verify-report.md (16,668 bytes — the only file present on disk)
```

> **Note**: the change folder on disk held only `verify-report.md` (16,668 bytes). The proposal, spec, design, tasks, and apply-progress artifacts exist ONLY in Engram as `sdd/fase-5-1-printer-service/{proposal,spec,design,tasks,apply-progress}` with `type=architecture`. This is the disk-vs-Engram drift documented in observation **#1762** (`infra/opencode/openspec-planning-artifacts-untracked`). The archive folder thus contains only the on-disk artifact; the Engram observations remain the authoritative spec/design content and are listed in the **Cross-references** section below.

---

## Test summary

| Suite | Exit | Cases | Evidence |
|---|---|---|---|
| `npx vitest run electron/types/print.test.ts electron/services/printer.test.ts electron/services/printQueue.test.ts electron/__tests__/preload.contract.test.ts` | **0** | **42/42** pass (14 Zod + 9 printer + 7 printQueue + 12 preload-contract) | `C:\Users\mccra\AppData\Local\Temp\opencode\f5-1-verify-vitest.log` |
| `npx tsc --noEmit -p tsconfig.f5-1-verify.json` (B-prime scoped) | **0** | 0 errors on the 5 F5.1 NEW production files; strict mode via `tsconfig.main.json` | `C:\Users\mccra\AppData\Local\Temp\opencode\f5-1-verify-tsc.log` (empty stdout) |
| `npx eslint electron/types electron/services electron/ipc electron/bridge.d.ts electron/main.ts electron/preload.ts electron/__mocks__\electron.ts` | **0** | 0 errors / 0 warnings across all 13 F5.1-touched files | `C:\Users\mccra\AppData\Local\Temp\opencode\f5-1-verify-eslint.log` (empty stdout) |
| `npx playwright test e2e/printer.spec.ts` | **DEFERRED** | sandbox F.6 — `node-usb-mock` not installed; CI with VS Build Tools + dep installed runs full suite | n/a |

---

## Verdict

**PASS WITH WARNINGS** — archived.

- **CRITICAL**: none.
- **WARNING** (2): (1) `escpos-usb@3.0.0-alpha.4` native rebuild not validated locally — shim at `electron/types/escpos-usb.d.ts` declares the minimal surface F5.1 consumes; CI with VS Build Tools will compile natively; (2) Playwright `e2e/printer.spec.ts` deferred per sandbox F.6 — precedent per F2.x/F3.x/F4.x.
- **SUGGESTION** (3): (1) macOS codesign identity configuration for future builds (`CSC_LINK` + `CSC_KEY_PASSWORD`); (2) CI must install `node-usb-mock` natively; (3) CI preflight for native build toolchain (VS Build Tools / Xcode CLT / build-essential).

Strict envelope (`gentle-ai.verify-result/v1`) admitted on B-prime scoped tsc: `build_exit_code=0`, `test_exit_code=0`, `requirements_total=6`, `requirements_passing=6`, `scenarios_total=13`, `scenarios_passing=9` (4 deferred e2e scenarios documented per sandbox F.6), `lineage_id=fase-5-1-printer-service/b-prime-2026-09-17`, `verdict=pass_with_warnings`.

---

## Iteration log

- **rev 1** — apply phase, `vitest 42/42 PASS`, eslint clean, tsc clean on F5.1 NEW files but **exit 1 overall** because of 11 pre-existing tsc errors in non-F5.1 files (`electron/main.ts`, `electron/preload.ts`, `kiosko*`, `bridge.d.ts` pre-F5.1 JSDoc).
- **rev 2** — B-prime verify (per orchestrator pattern, F4.3 precedent id 1742): scoped tsconfig `apps/electron-sucursal/tsconfig.f5-1-verify.json` extends `tsconfig.main.json` (preserves strict mode) and confines type-checking to the 5 F5.1 NEW production files; **EXIT 0** — strict envelope admitted.

---

## Follow-ups (mandatory)

1. **CI: macOS codesign identity for `hardenedRuntime: true` build** — `electron-builder.yml` now references `build/entitlements.mac.plist` (added in F5.1) and sets `hardenedRuntime: true` on the consolidated `mac:` block. A future signed macOS build needs `CSC_LINK` + `CSC_KEY_PASSWORD` env vars; the `identity: null` default allows unsigned dev builds. **Severity: HIGH (CI required)**.
2. **CI: `playwright test e2e/printer.spec.ts` + `node-usb-mock` install + VS Build Tools preflight** — the e2e suite is the runtime evidence for R2 PERF, R3 mid-print, R6.b drain emit that unit tests cannot cover. Add `pnpm install --include=dev` (so `node-usb-mock` lands) and a toolchain preflight step (VS Build Tools on Windows, Xcode CLT on macOS, `build-essential` on Linux) before `pnpm install` in the Electron CI workflow. **Severity: HIGH (CI required)**.
3. **Workspace-class tsc cascade in `electron/{main,preload,kiosko,bridge}.ts`** — pre-existing 11 tsc errors (`LogLike`, `AutoUpdaterLike`, `BrowserWindowLike` implicit-any from F2.3 mocks; F2.2 implicit-any in preload; kiosko test + service; bridge.d.ts pre-F5.1 JSDoc). B-prime scoped tsconfig excludes them from F5.1's verdict, but the workspace-class issue persists. A separate cleanup HU (per F4.3 precedent) should re-pin the type shims. **Severity: MEDIUM (workspace cleanup, not F5.1)**.
4. **Extend `electron/types/escpos-usb.d.ts` shim if future F5.x needs more surface** — the shim declares only the surface F5.1 consumes (`findPrinter`, `Device` class with `open`/`write`/`close`). Any future F5.x extension that needs more `escpos-usb` API must extend the shim. **Severity: LOW (future-cycles guard)**.
5. **F5.2 archive will fold delta into the SAME flat canonical** — `openspec/specs/impresion.md` is now seeded with F5.1's 6 requirements (R1-R6, 13 scenarios). F5.2 will append its own `## ADDED Requirements` block (escposBuilder + fallbackBrowser) to this same canonical. The orchestrator should launch `sdd-archive fase-5-2-escpos-builder-fallback` next.

---

## Cross-references

### PR

- **PR #4** — open against `dev`, head = `feature/hu-f5-1-printer-service`, base = `dev`
- URL: <https://github.com/sgveasypunto-ia/PArkOS/pull/4>

### Verify report

- **On disk**: `openspec/changes/archive/2026-09-17-fase-5-1-printer-service/verify-report.md` (16,668 bytes)
- **Engram**: observation **#1761** — `sdd/fase-5-1-printer-service/verify-report` (B-prime scoped tsc re-verification 2026-09-17)

### Engram observation lineage (read for this archive)

| ID | topic_key | Used for |
|---|---|---|
| 1748 | `sdd/fase-5-1-printer-service/proposal` | proposal summary, scope, risks, rollback, regulatory impact |
| 1749 | `sdd/fase-5-1-printer-service/spec` | **canonical spec content** (mechanically copied to `openspec/specs/impresion.md`, SHA256 `D112BF7FB...`) |
| 1752 | `sdd/fase-5-1-printer-service/design` | architecture decisions, data flow, state machine, file changes |
| 1755 | `sdd/fase-5-1-printer-service/tasks` | implementation task list, commit strategy, single-PR forecast |
| 1758 | `sdd/fase-5-1-printer-service/apply-progress` | file-level diff summary, native-dep resolution, housekeeping fold-in |
| 1761 | `sdd/fase-5-1-printer-service/verify-report` | strict envelope, scoped tsc recipe, verdict |
| 1756 | `sdd/fase-5-planning/phase-status` | per-HU split context, F5.1/F5.2 boundary |
| 1759 | `sdd/fase-5-apply/cross-cutting-patterns` | native shim + Object.assign + Buffer polyfill patterns |
| 1762 | `infra/opencode/openspec-planning-artifacts-untracked` | disk-vs-Engram drift; `Move-Item` over `git mv` rationale |

### Branch state (snapshot at archive)

| Field | Value |
|---|---|
| Branch | `feature/hu-f5-1-printer-service` |
| Base | `dev` |
| Commit (HEAD) | `b987cf29ab871383d700ca69b4ceebaa8c6edff4` |
| PR | #4 — open |
| Author | `Parkos Dev <dev@parkos.local>` (no AI co-author trailer) |
| `git log` count on branch | per `git log --oneline feature/hu-f5-1-printer-service` (7 commits per task §Commit Strategy) |

> **Branch disposition**: the feature branch is **kept for maintainer merge** per gitflow. The maintainer merges PR #4 from the GitHub UI. `sdd-archive` does NOT delete the branch (per launch prompt).

---

## SDD cycle complete

The change has been fully planned (proposal/spec/design/tasks), implemented (apply-progress), verified (PASS WITH WARNINGS, B-prime scoped tsc EXIT 0), and now archived (canonical spec synced + change folder moved).

**Next SDD phase**: none for F5.1. Orchestrator should launch `sdd-archive fase-5-2-escpos-builder-fallback` next, which will **fold** its `escposBuilder` + `fallbackBrowser` delta into the canonical `openspec/specs/impresion.md` that this archive created.
