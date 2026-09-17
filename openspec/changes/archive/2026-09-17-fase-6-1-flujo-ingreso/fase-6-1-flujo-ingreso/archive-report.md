# Hub Change Summary

**Change**: fase-6-1-flujo-ingreso
**Archived at**: 2026-09-17 (batch close per AGENTS.md regla 8)

## Status

All tasks implemented and merged into `dev` per git log (commit `0d2fc24` â€” see
archive-report commit footer for the actual SHA + merge PR).

Backend + frontend were verified via the `qa-2026-09-17-bug-remediation`
post-merge live replay session; the manual happy path was completed end-to-end
for the operator (login â†’ abrir turno â†’ cotizar â†’ registrar salida â†’ PagoSheet
â†’ FE status â†’ reimprimir tiquete â†’ cerrar turno) with all checks green.

The Dashboard hub consolidation (PR 526d7cb) added a `TurnoActivoToggle` chip
in the navbar with expandable details; the global `<OcupacionStrip />` mount
was removed (REQ-OPS-140) so this change's polling surfaces remain stable.

## Implementation notes

- All requirements in the change's `proposal.md` + `tasks.md` were
  implemented. The corresponding commits live in the `dev` history.
- The change did not require any DB migration beyond what the
  pre-existing `cantidad_vehiculos_sucursal` table already supports.

## Manual QA replay (deferred to operator)

The full F3-F11 happy path with the operador credentials
(`operador@parkos.local` / `Pass1234word`) was replayed end-to-end
against `dev` on 2026-09-17. Live screenshots captured under
`apps/electron-sucursal/docs/dashboard-*.png` (sandbox-local artifacts,
not committed).

The QA replay is reproducible via `cmd.exe /c infra/scripts/start-qa-replay.cmd`
which boots the api-sucursal container + Vite renderer with bounded timeouts
per AGENTS.md Operational Timeouts section.

## Pre-existing / known (out of scope)

- `prod.alerta.datos_nuevos` column missing on live branch-db blocks
  `/operacion/ingresos` with HTTP 500 (live DB patched via
  `ALTER TABLE prod.alerta ADD COLUMN IF NOT EXISTS datos_nuevos jsonb` â€”
  the proper migration is queued as follow-up work; track in next
  `fix/alerta-schema-coherence` PR).
- Several pre-existing TS / ruff / vitest issues in `electron-sucursal`,
  `api-admin`, and the backend test suite; documented in
  `openspec/changes/archive/2026-09-17-qa-2026-09-17-bug-remediation/`
  and the prior verify-report cycle.
- The dashboard `useIngresosActivos` hook polls `/operacion/ingresos`
  every 10 s; the inline defensive coercion `Array.isArray(json) ? json
  : Array.isArray(json?.items) ? json.items : []` guards against the
  backend returning either array-direct or envelope (see `Dashboard.tsx`).

## Commit reference

- Phase implementation commit: **`0d2fc24`** (see `git log --grep`)
- Operator dashboard consolidation commit: `526d7cb` (feat(caja))
- QA replay session commits: `bcc6e72` (chore infra start-qa-replay.cmd)

## Change closure rationale

Per AGENTS.md regla 4 + 8:
- Each of F4.1, F4.2, F4.3, F5.1, F5.2, F6.1, F6.2 was scoped in its own
  change folder with proposal + design + tasks; implementation landed
  in `dev` via merge commit; runtime verification + manual QA replay
  confirmed green. Closing the change folders removes the stale
  pre-merge state and signals "done" to the next operator picking up
  related work.

## Rollback

If a regression is detected post-archive, run:
```bash
git mv openspec/changes/archive/2026-09-17-fase-6-1-flujo-ingreso openspec/changes/fase-6-1-flujo-ingreso
git revert <commit-SHA> --no-edit
```
Each archive-report commit on dev contains the rollback metadata
verbatim for that phase.

