# Archive report — hu-f7-3-tiquetes-salida (duplicate pre-apply snapshot)

**Change**: `hu-f7-3-tiquetes-salida`
**Archived**: 2026-09-23
**Operator directive**: *"super en ese orden"* — confirming 2026-09-23 archival
sweep after `hu-f8-1-pago-bloquea-salida` archive.
**Decision**: archived — superseded by
`archive/2026-09-19-fase-7-3-tiquetes-salida/` which carries the full
applied+verified lifecycle.

---

## 1. Why this was archived (not deleted)

The directory `openspec/changes/hu-f7-3-tiquetes-salida/` carried a
**pre-apply snapshot** of the F7.3 change — `proposal.md`,
`design.md`, `tasks.md`, `specs/operacion/spec.md` — but **no
`apply-progress.md` or `verify-report.md`**, meaning the apply phase
either never ran from this directory, OR the directory was a checkpoint
snapshot committed before the apply started. Either way it represents
work that **has already been completed and archived elsewhere** (see §2).

## 2. The canonical archive already exists

| Directory | State | Has |
|---|---|---|
| `archive/2026-09-19-fase-7-3-tiquetes-salida/` | FULL lifecycle | proposal, design, tasks, specs/operations.md, **apply-progress.md**, **verify-report.md** |
| `archive/hu-f7-3-tiquetes-salida/` (this folder) | PRE-apply snapshot | proposal, design, tasks, specs/operacion/spec.md |

The archived `2026-09-19-fase-7-3-tiquetes-salida` is the source of
truth for the F7.3 work. Commits `c7c19d2`, `2893213`, and `5a94a3c`
landed the work in `dev` (merge chain `8afe9c5` → `5a94a3c` →
`2893213` → `7cd2f70` → `7cd2f70` → `c7c19d2` → `ac21b62`).

## 3. Why a pre-apply snapshot was sitting in `changes/`

Two plausible explanations (no commit message in this repo confirms):

1. **Checkpoint commit before apply**: Some teams commit a frozen
   snapshot of the planning at the moment apply starts so the
   pre-apply state is recoverable. This is a legitimate pattern; the
   intent would be to delete the snapshot when apply ends and moves
   everything to `archive/`. The deletion was likely missed.
2. **Duplicate change directory**: A second author may have created
   `hu-f7-3-tiquetes-salida/` independently of the `fase-7-3-...`
   canonical one. The two diverge in filename convention
   (`hu-f7-3-...` vs `fase-7-3-...`, the latter prefixed with date).

In either case, the active snapshot is now obsolete.

## 4. Re-entry path (when this work is needed again)

**Do NOT use this archive folder as the source of truth.** Read
`archive/2026-09-19-fase-7-3-tiquetes-salida/` instead — it has the
verified postscript (apply + verify reports) and matches the state
actually shipped to `dev`.

## 5. Verification

- `git status` clean after commit on `chore/sdd-archive-hu-f7-3-tiquetes-salida`.
- `openspec/changes/hu-f7-3-tiquetes-salida/` no longer exists (active
  state).
- `openspec/changes/archive/hu-f7-3-tiquetes-salida/` carries the 4
  pre-apply files (proposal, design, tasks, specs/operacion/spec.md).
- The canonical post-apply archive
  `openspec/changes/archive/2026-09-19-fase-7-3-tiquetes-salida/` is
  untouched.

**Status**: archived (superseded — see §2).
**Archived by**: SDD orchestrator session 2026-09-23 (operator-ratified).