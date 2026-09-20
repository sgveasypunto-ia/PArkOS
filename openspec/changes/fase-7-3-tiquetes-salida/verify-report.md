# Verify Report: HU-F7.3 — Tiquetes de salida (CU-15S) + salida-mensualidad (CU-15SM)

> **Change**: `fase-7-3-tiquetes-salida`
> **Phase**: sdd-verify (placeholder — populated by sdd-verify sub-agent)

## Status

`pending` — populated by sdd-verify

## Pre-Verification Snapshot

- **Branch**: `feature/hu-f7-3-tiquetes-salida`
- **Base**: `dev @ d157195`
- **Forecast**: ~360 LOC under 800 budget
- **Apply progress**: see `apply-progress.md`

## Verification Plan (sdd-verify populates)

The sdd-verify sub-agent will:
1. Run `pnpm vitest run` over the full `electron-sucursal` workspace — exit 0 required
2. Run `pnpm typecheck` — exit 0 required (pre-existing errors noted, none introduced by F7.3)
3. Run `git grep -nE 'PARKINGOS' apps/electron-sucursal/src` — only docstring refs allowed
4. Run `git diff dev..feature/hu-f7-3-tiquetes-salida --stat` — ≤ 800 LOC
5. Verify per-file coverage thresholds in `vitest.config.ts` — `escposBuilder.ts` ≥85/85/80
6. Map each REQ-OPS-158..160 scenario to a passing test (`escposBuilder.salida.test.ts`, `escposBuilder.salida_mensualidad.test.ts`, `SalidaMensualidad.test.tsx`)
7. Validate spec field-count invariants:
   - CU-15S: 19 fields + 2 DEC-SUC-26 additions (QR + logo)
   - CU-15SM: 15 fields + 2 DEC-SUC-26 additions

## Acceptance Criteria Traceability

| Spec | Test file | Status |
|------|-----------|--------|
| REQ-OPS-158 — CU-15S 19 fields + dynamic header + QR + logo | `escposBuilder.salida.test.ts` (T1, T2, T3, T4 + T1.drift) | ⏳ pending verify |
| REQ-OPS-159 — CU-15SM 15 fields + sello + QR + logo + no $ | `escposBuilder.salida_mensualidad.test.ts` (T5, T6, T7, T7.strict) | ⏳ pending verify |
| REQ-OPS-160 — `bridge.imprimir` via queueMicrotask on 201 | `SalidaMensualidad.test.tsx` (3 scenarios) | ⏳ pending verify |

## Drift Guard Expected Output

```
$ git grep -nE 'PARKINGOS' apps/electron-sucursal/src | grep -v '_test\.ts:' | grep -v 'drift guard' | grep -v '\* '
# expected: 0 matches outside docstrings — or ONLY docstring references
```
