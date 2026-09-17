# Manual QA Replay — operador-dashboard-hub (post PR-6)

> **Analog of `qa-2026-09-17-bug-remediation`** — replay the operator
> happy path on a fresh branch install to confirm the dashboard hub
> absorbs all F4-F11 actions.

## Pre-requisites

1. **Stack up**: `docker compose -f infra/deploy/docker-compose.branch.yml up -d`
   (branch Postgres + api-sucursal + reverse-proxy).
2. **Migrated**: `alembic upgrade head` inside the branch api container.
3. **Frontend dev**: `cd apps/electron-sucursal && pnpm dev` (Vite on `:5173`).

## Happy path (manual)

| # | Step | Expected | REQ-OPS |
|---|---|---|---|
| 1 | Open `http://localhost:5173` → redirected to `/login`. | Login form. | REQ-OPS-121 |
| 2 | Login with `operador@sucursal.local` / credentials. | Redirect to `/` → `<AbrirTurno />` (sesion===null). | REQ-OPS-119 |
| 3 | Submit "Abrir turno" with `valor_inicial_efectivo=50000`. | 201 → navigate('/') → Dashboard renders TurnoActivoPanel + OcupacionPanel + 6 sections. | REQ-OPS-119, REQ-OPS-136 |
| 4 | Observe OcupacionPanel chip "Auto: 23/50 verde". | Same chip as the old global `<OcupacionStrip />`. | REQ-OPS-140 §inline baseline |
| 5 | Type `ABC12D` in `<IngresoPanel />` → press Enter. | 201 + `<TiqueteModal>` opens; auto-print fires; observador can re-imprimir. | F6.1, DEC-SUC-27 |
| 6 | Observe SyncStatusStrip is `online` (lag < 60s). | Cloud icon, green chip. | F11.1 |
| 7 | (Optional) Trigger `POST /operacion/salidas?uuid_ingreso=X` directly from a sibling client to create an active ingreso, then re-submit `ABC12D` from this branch. | 409 `ingreso_activo_existente` → transparently redirect to `/operacion/salida`. | F6.1, DEC-F6.1 |
| 8 | Click "Cobrar" in the cotización breakdown. | Right-side `<PagoSheet />` opens (FE consumidor-final NIT pre-filled). | F8.1, REQ-OPS-138 |
| 9 | Submit PagoSheet (efectivo, monto = total_cop). | 200/201; sheet closes; draw focus restored to "Cobrar" anchor. | REQ-OPS-138 §Esc |
| 10 | Click "Reimprimir tiquete" trigger. | Right-side `<ReimprimirTiqueteSheet />` opens; PagoSheet closes (single-drawer invariant). | REQ-OPS-138 |
| 11 | Type plate `ABC12D` + motivo ≥10 chars + confirm. | POST `/workflows/reimpresion-ticket` succeeds; drawer closes. | F8.3 |
| 12 | Click "Arqueo" → fill efectivo + datáfono contado. | `<ArqueoSheet />` opens; submit posts `tipo_arqueo=auditoria`. | F10.1 |
| 13 | Click "Cierre diario" → verify resumen table + submit. | `<CierreDiarioDialog />` opens; submit posts `tipo_arqueo=cierre_dia`. | F10.3 |
| 14 | Click "Cerrar turno" → PUT `/caja-sesion/sesion/{uuid}/cerrar`. | Navigate `/` → redirect `/caja/abrir-turno` (sesion===null again). | REQ-OPS-121 |
| 15 | Verify NO global `<OcupacionStrip />` at `App.tsx:48`. | grep returns empty. | REQ-OPS-140 §App.tsx global strip removed |
| 16 | Verify Dashboard `data-testid="dashboard-section-sync"` shows `online` chip. | Renders correctly. | F11.1 |
| 17 | (If applicable) Observe `<AlertasPanel />` lists any open alerts. | Renders 0 alerts when none. | F11.2 |

## Regression sweep

- `pnpm exec vitest run src/features/caja/pages src/features/operacion src/features/facturacion src/features/reimpresion src/features/suscripciones src/features/sync src/renderer/store`
  → all NEW tests green (95+); pre-existing F.6 sandbox failures documented.
- `pnpm exec tsc -b` → 0 NEW errors (pre-existing failures in `useOcupacion.ts:91`, `TiqueteModal.test.tsx`, etc., out of scope per AGENTS.md verify #4).

## Rollback

`git revert <merge-sha>` of any PR — surgical revert preserves the rest of the chain (per `proposal.md` §Rollback Plan). Backend untouched.