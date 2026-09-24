# Archive report — hu-f8-1-pago-bloquea-salida

**Change**: `hu-f8-1-pago-bloquea-salida`
**Archived**: 2026-09-23
**Operator directive**: *"descarta los flujos abiertos en openspec si puedes
archivalos"*
**Decision**: archived — no `apply` phase ever started. Pre-`sdd-apply` work
preserved verbatim for future reference.

---

## 1. Why this was archived (not discarded)

The artifacts under this directory were produced in the same morning's
session (2026-09-23, Engram `#2051`–`#2053`) and never reached the
`apply` phase. Per the project's gitflow canon, the operator's archival
directive means: keep the planning artifacts in
`openspec/changes/archive/<name>/` for traceability, do NOT lose the work,
and unblock any future "we need this again" cycle by re-reading from the
archive rather than rediscovering from scratch.

The orphan canonical-spec attempt at
`openspec/specs/salida-con-cobro/spec.md` was bundled into this archive
as `salida-con-cobro/spec.md` because it has no meaning outside this
change's context.

## 2. What was in the change (sanity check for the next reader)

| File | Lines | Status |
|---|---|---|
| `proposal.md` | 84 | draft — Approach (a) ratified (atomic `POST /operacion/salida-con-cobro`) |
| `design.md` | 100 | draft — 16-step handler, pre-mint UUIDs, KD-S7 lock continuity |
| `exploration.md` | 440 | draft — root-cause analysis of the operator-gap, 3 approaches compared |
| `tasks.md` | 80 | forecast — 1300–1800 LOC across 4 chained PRs (PR1..PR4) |
| `specs/operations/spec.md` | 122 | RE-DELT — REQ-OPS-053..055 |
| `salida-con-cobro/spec.md` | 108 | draft — REQ-SCC-001..006 (canonical-spec attempt) |

Total: ~934 LOC of pre-`apply` planning. **No code, no migrations, no
PRs were created.** The branch never diverged from `dev`.

## 3. Known spec drift documented in this work

The change correctly identified (and never resolved) the following
`plan.md` ↔ ER drift, which is why this fix is large and risky:

- `plan.md:898` asserts `salidas.estado='PAGADO'` after pago — the ER
  has no such column. Spec drift, repeated in `exploration.md:392-401`.
- The FE `FacturaRead` Zod schema (`facturaApi.ts:42-69`) does not
  match the BE `FacturaRead` Pydantic (`schemas/facturacion.py:606-626`)
  — a separate, pre-existing bug that this change did NOT touch.
  `exploration.md:38-46` documents the FE↔BE payload mismatch.

These drifts remain unfixed. Any future change that touches the
salida+factura atomic boundary MUST read this archive before designing.

## 4. Re-entry path (when this work is needed again)

1. `git checkout -b feature/revive-hu-f8-1-pago-bloquea-salida` from
   `dev`.
2. Read `exploration.md` first (rationale + approaches), then
   `proposal.md` (ratified Approach (a)), then `design.md` (16-step
   handler). The chain strategy is **pending** in `tasks.md` —
   re-ask the operator with the current per-PR LOC budget (800 lines).
3. The orphan `salida-con-cobro/spec.md` carries the canonical-spec
   attempt (REQ-SCC-001..006). Either re-promote it to
   `openspec/specs/salida-con-cobro/spec.md` (canonical location) or
   RE-DELT into a new operations/spec.md under the change folder.

## 5. Related archived work this DOES NOT supersede

- `openspec/changes/archive/2026-09-19-fase-8-1-pago-modal-fe/` — the
  F8.1 PagoModal that shipped. The current PagoSheet + `fix/hu-f8-1
  -anular-salida-no-pagada` series derive from that archive.
- `openspec/changes/archive/2026-09-09-sync-overhaul/` — sync boundary
  contract that the proposed atomic endpoint's FK direction must honor.

## 6. Verification

- `git status` clean after commit on `chore/sdd-archive-wip-hu-f8-1-pago-bloquea-salida`.
- `openspec/changes/hu-f8-1-pago-bloquea-salida/` no longer exists
  (active state).
- `openspec/specs/salida-con-cobro/` no longer exists (active state).
- `openspec/changes/archive/hu-f8-1-pago-bloquea-salida/` contains the
  full planning artifact set.
- No Alembic migration was applied or reverted (none proposed at this
  stage).

## 7. Open WIPs intentionally NOT archived

The operator's directive was scoped to "los flujos abiertos en
openspec". The following tracked WIPs were left in `active changes/`
because the operator has not (yet) directed their archival and they
represent ongoing work, not orphan artifacts:

| Change | State | Why left active |
|---|---|---|
| `openspec/changes/hu-f7-3-tiquetes-salida/` | TRACKED · proposal+design+tasks+spec | HU-F7.3 work merged to `dev` (commits `c7c19d2`, `2893213`); an archived copy `2026-09-19-fase-7-3-tiquetes-salida` already exists. The duplicate in `changes/` may be stale — operator should decide. |
| `openspec/changes/ingreso-multi-tipo-consecutivo/` | TRACKED · proposal+design+exploration+tasks+spec | Active WIP for Fase 4 (vehículos sin placa, bici/patineta). "ready for sdd-spec + sdd-design" per proposal.md. Operator should confirm before archival. |

**Status**: archived.
**Archived by**: SDD orchestrator session 2026-09-23 (operator-ratified).
**Canonical follow-up**: none required; the artifacts preserve the
rationale for re-entry.