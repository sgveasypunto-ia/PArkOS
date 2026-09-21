# Deprecation Log — `useCierreDiario()`

> HU-F10.3 (Cierre Diario) — REQ-OPS-168 timeline for the deprecation
> marker added to the buggy legacy `useCierreDiario()` helper at
> `apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts:100-118`.

## Release Note (F10.3, 2026-09-21)

`useCierreDiario()` is **deprecated** as of HU-F10.3 (merge SHA TBD per
`sdd-archive`). The helper carries a `@deprecated` JSDoc tag + a
dev-mode `console.warn(...)` that fires once per page-load when the
helper is called. **No behavior change** — the helper body is
bit-identical; the bug (`uuid_sesion: string` collides with backend
cross-validation at `caja_arqueo.py:122-128`) remains documented but
uncorrected.

The forward path for the F10.3 routed page is
`runCierreDiarioChain` (NEW — `apps/electron-sucursal/src/features/caja/pages/cierreDiarioChain.ts`).
Removal target: F11.x or later Fase 11 housekeeping, AFTER the F8.x
`CierreDiarioDialog.tsx:91` consumer migrates (the dialog does NOT
call `useCierreDiario()` directly per repo inspection — it calls
`useArqueo().submit(...)` — so the dialog's bug surface is
independent of this deprecation).

**Action required**: none. The deprecation is forward-looking; the
helper continues to work as before. **Action recommended** for F11.x
housekeeping: migrate the F8.x dialog's submit path to the new
`runCierreDiarioChain` helper, THEN remove `useCierreDiario()` in the
same PR.

## Status

**DEPRECATED — 2026-09-21**

The `useCierreDiario()` helper carries a `@deprecated` JSDoc tag and a
dev-mode `console.warn(...)` guard (REQ-OPS-168 scenario 1). Production
builds dead-code-eliminate the guard via Vite + Rollup tree-shake
(REQ-OPS-168 scenario 2).

The helper body is **bit-identical to the pre-F10.3 state** — the bug
remains documented but uncorrected. The forward path is:

```
useArqueo().submit({ uuid_sesion: null, tipo_arqueo: 'cierre_dia', ... })
  → runCierreDiarioChain (apps/electron-sucursal/src/features/caja/pages/cierreDiarioChain.ts)
  → POST /caja/arqueo with cierre_dia discriminator
  → bridge.imprimir('arqueo', { ..., auditoria_codigo: 'cierre_dia' })
```

## Why deprecated, not removed

The helper's payload schema declares `uuid_sesion: string` (line 109)
which collides with the backend cross-validation at
`backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py:122-128`
that REJECTS `cierre_dia` with non-null `uuid_sesion`
(`400 cierre_dia_no_acepta_uuid_sesion`).

The F8.x consumer
`apps/electron-sucursal/src/features/caja/components/CierreDiarioDialog.tsx:91`
does NOT call `useCierreDiario().ejecutar(...)` directly — it calls
`useArqueo().submit(...)` — so the dialog's bug surface is independent
of the deprecation. **Removing the helper in F10.3 scope would
regress the dialog's call path**, hence deprecate-without-delete.

## Timeline

| Date | Phase | Action |
|---|---|---|
| 2026-09-21 | HU-F10.3 (this PR) | `@deprecated` JSDoc + dev-mode `console.warn` + this log file. Helper body unchanged. |
| 2026-09-21 | HU-F10.3 (this PR) | Forward path: `runCierreDiarioChain` + `<CierreDiario />` page at `/caja/cierre-diario`. The new `<CierreDiario />` page does NOT use `useCierreDiario()`. |
| TBD | F11.x (or later Fase 11 housekeeping) | Migrate `CierreDiarioDialog.tsx:91` consumer (if any direct `useCierreDiario()` invocations exist). THEN remove the helper. |

## Forward path consumers (F10.3)

- `<CierreDiario />` routed page at `/caja/cierre-diario` (NEW —
  supervisor flow per AD-3 + REQ-OPS-164).
- `runCierreDiarioChain` (NEW — pure helper per REQ-OPS-166, 2-step
  sequencer POST arqueo + bridge.imprimir).

## Backward path consumers (F8.x — out of F10.3 scope)

- `<CierreDiarioDialog />` (drawer pattern — independent of the
  `useCierreDiario()` deprecation per the dialog's direct
  `useArqueo().submit(...)` call path).