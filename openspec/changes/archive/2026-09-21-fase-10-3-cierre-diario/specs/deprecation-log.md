# Deprecation Log — HU-F10.3

## `useCierreDiario()` (apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts:100-118)

**Deprecated**: 2026-09-21 (HU-F10.3 PR, T2 of F10.3 atomic tasks)

**Reason**: payload schema declares `uuid_sesion: string` (line 109)
which collides with the backend cross-validation at
`backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py:122-128`
that REJECTS `cierre_dia` with non-null `uuid_sesion` (returns
`400 cierre_dia_no_acepta_uuid_sesion`).

**Migration path**: use `useArqueo().submit({ uuid_sesion: null,
tipo_arqueo: 'cierre_dia', ... })` directly via the
`runCierreDiarioChain` helper from
`apps/electron-sucursal/src/features/caja/pages/cierreDiarioChain.ts`
(REQ-OPS-166).

**Current consumers**:

| File | Line | Call shape | Migration status |
|---|---|---|---|
| `apps/electron-sucursal/src/features/caja/components/CierreDiarioDialog.tsx` | 91 | `useArqueo().submit({ uuid_sesion, tipo_arqueo: 'cierre_dia', ... })` (note: dialog calls `submit` directly, NOT `useCierreDiario().ejecutar`) | NOT in F10.3 scope (F8.x; out of proposal §Out-of-Scope). The dialog's bug surface (passes `uuid_sesion: uuid_sesion` where backend requires `null` for cierre_dia) is independent of the helper deprecation. Migration target: future housekeeping PR. |
| (search-wide) | n/a | `useCierreDiario().ejecutar(...)` direct callers | 0 hits in current codebase as of 2026-09-21 (the helper is exported but the only usage-shaped caller is the dialog, which uses `useArqueo().submit(...)` directly). |

**Removal target**: HU-F11.x (sync worker UI migration) or later
Fase 11 housekeeping PR. The F8.x CierreDiarioDialog.tsx:91 consumer
MUST migrate to either the chain helper or the
`useArqueo().submit({ uuid_sesion: null, ... })` direct path BEFORE
the helper is deleted.

**Deprecation surface in F10.3 PR**:
- `@deprecated` JSDoc tag immediately above the function
- `console.warn(...)` in dev mode (`import.meta.env.DEV === true`)
  fires the first time `useCierreDiario().ejecutar` is called
  per page-load
- Production builds tree-shake the warn guard (Vite + Rollup
  dead-code-elimination; the `if (import.meta.env.DEV)` branch
  becomes unreachable at build time)

**Regression guard**: the function body is NOT modified in F10.3
scope. The bug remains, but the helper is documented as deprecated
and the FE team has a clear migration path via REQ-OPS-166.
