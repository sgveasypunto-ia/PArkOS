# Archive report — ingreso-multi-tipo-consecutivo

**Change**: `ingreso-multi-tipo-consecutivo`
**Archived**: 2026-09-23
**Operator directive**: *"super en ese orden"* — confirming 2026-09-23 archival
sweep after `hu-f8-1-pago-bloquea-salida` and `hu-f7-3-tiquetes-salida`
archives.
**Decision**: archived — pre-`apply` WIP for Fase 4 multi-tipo vehículos
sin placa (bicicleta / patineta). Planning fully preserved verbatim;
apply phase was never started.

---

## 1. Why this was archived (not deleted)

This change covers a real product gap (vehículos sin placa: bici y
patineta) that the operator has not yet prioritized for implementation.
The seed catalog (`commit 281bb66 chore(backend): seed tipos_vehiculo +
cupos for D2049f2`, already on `dev`) created the supporting data
(`tipos_vehiculo` rows + `cantidad_vehiculos_sucursal` cupos), but the
ingreso flow's UI + handler + ORM + tests are still pending. The
planning artifacts here describe the full target state.

Per the operator's archival directive, the planning is preserved so any
future "we need bici/patineta now" cycle can re-enter from
`openspec/changes/archive/ingreso-multi-tipo-consecutivo/` without
rediscovering the design from scratch.

## 2. What was in the change

| File | Lines | Status |
|---|---|---|
| `proposal.md` | 205 | intent + 2 chained PRs (PR-A backend ~600 LOC, PR-B frontend ~455 LOC); forecast ~1115 LOC |
| `exploration.md` | 278 | 12 gaps G1..G12, 3 approaches A1..A3, 10 open questions, 11 risks R1..R11 |
| `design.md` | (substantial) | full technical design, decision matrix, file changes |
| `tasks.md` | (substantial) | task breakdown ready for `sdd-tasks` |
| `specs/operations/spec.md` | (substantial) | REQ deltas ready for `sdd-spec` |

State: ready for `sdd-spec` + `sdd-design` (per proposal §5). Apply
phase never started — no PR was created, no branch diverged from `dev`.

## 3. The seed that makes this work remains live

The catalog seed `commit 281bb66` is already on `dev` and the table
`prod.tipos_vehiculo` carries the 4 tipos (`carro`/`moto`/`bicicleta`/
`patineta`, lowercase per ER canon) plus their cupos in
`prod.cantidad_vehiculos_sucursal`. If the operator restarts this
change, the supporting data is already in place — only the ingreso
handler + UI + tests are missing.

## 4. Critical re-entry items (read these FIRST when reviving)

From `exploration.md` and `proposal.md`:

- **Column `consecutivo` does NOT exist on `prod.ingreso` yet** (4NF
  canon, ER.mmd:577–596). The proposal's PR-A creates it via migration
  `0042_add_ingreso_consecutivo.py`, plus a **NEW `[A]` table
  `prod.ingreso_consecutivo_contador`** as the 51st canonical table.
  This expansion of the table count is OUTSIDE the
  `bootstrap-monorepo-foundation` scope and requires explicit operator
  ratification per the precedent set by `idempotency_keys`.
- **REVOKE + trigger discipline**: per `config.yaml` `rules.tasks`,
  the new `[A]` table MUST ship with `REVOKE UPDATE, DELETE` from
  `rol_app` AND a `BEFORE UPDATE OR DELETE` trigger in the SAME
  migration. Per `openspec/scripts/check_schema_match.py`, this is
  part of the CI gate.
- **Sync trigger exclusion** (`WHEN TG_TABLE_NAME <>
  'ingreso_consecutivo_contador'`) needed to prevent recursion when the
  outbox trigger fires on the counter table (R9 in `exploration.md`).
- **Frontend pattern**: two-button layout in `Principal.tsx` and
  `IngresoPanel.tsx` (`Con placa` | `Sin placa`), NOT a toggle or
  inference — preserves BR2 of CU-01 (regex autodetección es la ÚNICA
  fuente válida).
- **ER invariants preserved — `tipo_entrada` derived, not stored**
  (DEC-SUC-21). The proposal uses `consecutivo` (a UUID8-suffixed
  number) as the user-visible identifier, NOT as a replacement for
  `tipo_entrada`.

## 5. Risks that were already known (preserved for re-entry review)

From `exploration.md` §"Open questions" and proposal §"Risks":

- **R1 race condition**: two concurrent POST /ingresos for the same
  `(uuid_sucursal, uuid_tipo_vehiculo)` could mint the same `consecutivo`.
  Mitigation: partial unique index `(uuid_sucursal, uuid_tipo_vehiculo,
  consecutivo) WHERE consecutivo IS NOT NULL` + the counter row's
  `SELECT FOR UPDATE` lock pattern (proven in
  `repo/resolucion_facturacion.py::assign_consecutivo:47-183`).
- **R9 trigger recursion**: outbox sync trigger could fire on the
  counter table. Mitigation: `WHEN TG_TABLE_NAME <>
  'ingreso_consecutivo_contador'` carve-out (per precedent in
  `repo/ingreso_consecutivo.py` design).
- **DIAN retention concern**: the new counter table is `[A]`
  (insert-only by policy) but its `ultimo_consecutivo` column
  legitimately needs UPDATE — explicit `WHEN` carve-out in the
  REVOKE/trigger per `config.yaml` `rules.tasks`.
- **Mesa migration concern (R7)**: existing AST walker
  `test_ingreso_handler_step_order.py` locks the 9-step chain — the
  proposal inserts a Step 9.5 call to `assign_ingreso_consecutivo()`
  inside the existing handler to avoid the AST test breaking.

## 6. Verification

- `git status` clean after commit on
  `chore/sdd-archive-ingreso-multi-tipo-consecutivo`.
- `openspec/changes/ingreso-multi-tipo-consecutivo/` no longer exists
  (active state).
- `openspec/changes/archive/ingreso-multi-tipo-consecutivo/` contains
  the 5 files: `proposal.md`, `exploration.md`, `design.md`, `tasks.md`,
  `specs/operations/spec.md`. All renames captured by `git mv`.
- No Alembic migration was applied or reverted (none proposed at this
  stage).
- The supporting seed `commit 281bb66` on `dev` is untouched.

## 7. Open WIPs status

| Change | State | Has archived? |
|---|---|---|
| `hu-f8-1-pago-bloquea-salida` | archived 2026-09-23 | `archive/hu-f8-1-pago-bloquea-salida/` |
| `hu-f7-3-tiquetes-salida` | archived 2026-09-23 (pre-apply duplicate) | `archive/hu-f7-3-tiquetes-salida/` + canonical `archive/2026-09-19-fase-7-3-tiquetes-salida/` |
| `ingreso-multi-tipo-consecutivo` | archived 2026-09-23 (this) | `archive/ingreso-multi-tipo-consecutivo/` |

No remaining WIPs in `openspec/changes/`.

**Status**: archived.
**Archived by**: SDD orchestrator session 2026-09-23 (operator-ratified).
**Re-entry path**: see §4.