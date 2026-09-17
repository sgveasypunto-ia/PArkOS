# Tasks: orphan REQ-OPS materialization (F1.1 + F1.2)

> **Change**: `2026-09-17-orphan-req-f1-1-f1-2-coverage`
> **Phase**: tasks (sdd-tasks)
> **Capability**: operations

## Atomic tasks

### T1 — Create delta spec artifact
- Create `openspec/changes/2026-09-17-orphan-req-f1-1-f1-2-coverage/specs/operations/spec.md` with the 2 REQs (`REQ-OPS-141` + `REQ-OPS-142`) and the `## ADDED Requirements` line
- **Out**: canonical merge (separate task T2)
- **Acceptance**: file exists; `git diff` shows it as new file

### T2 — Merge delta to canonical `operations/spec.md`
- Append `### Requirement: REQ-OPS-141 ...` and `### Requirement: REQ-OPS-142 ...` to the end of `openspec/specs/operations/spec.md` (after `REQ-OPS-140` at line 5741)
- Append the line `## ADDED Requirements (delta: 2026-09-17-orphan-req-f1-1-f1-2-coverage, REQ-OPS-141..142, 2026-09-17)` at the end of the most recent `## ADDED Requirements` section
- **Acceptance**: `git grep "^### Requirement: REQ-OPS-141" openspec/specs/operations/spec.md` returns 1 match; `git grep "^### Requirement: REQ-OPS-142" openspec/specs/operations/spec.md` returns 1 match; `git grep "ADDED Requirements (delta: 2026-09-17-orphan-req-f1-1-f1-2-coverage"` returns 1 match

### T3 — Verify + archive
- Run the 8 acceptance gates (G1-G8) from `design.md` §Verification plan
- Author `verify-report.md` with PASS verdicts for each gate
- Author `archive-report.md` with the standard closure manifest
- Mechanical move: `git mv` (or `mv` for untracked source) `openspec/changes/2026-09-17-orphan-req-f1-1-f1-2-coverage/` to `openspec/changes/archive/2026-09-17-orphan-req-f1-1-f1-2-coverage/`
- **Acceptance**: archive folder contains all 7 SDD artifacts; `git status --short` shows no orphan `2026-09-17-orphan-req-f1-1-f1-2-coverage/` in untracked location

### T4 — Commit + merge to dev + push
- `git add` the 7 new files + modified canon
- `git commit -m "feat(openspec): adicionar REQ-OPS-141 + REQ-OPS-142 (router_factory + /auth/me cookie + lockout) — F1.1 + F1.2 coverage"`
- `git checkout dev`
- `git merge --no-ff feature/orphan-req-f1-1-f1-2-coverage`
- `git push origin dev`
- **Acceptance**: `git log --oneline -5 dev` shows the merge commit; `git status` is clean (modulo pre-existing untracked screenshots)

## Acceptance gates

| # | Gate | Method | Expected |
|---|---|---|---|
| G1 | REQ-OPS-141 in canon | `git grep "^### Requirement: REQ-OPS-141" openspec/specs/operations/spec.md` | 1 match |
| G2 | REQ-OPS-142 in canon | `git grep "^### Requirement: REQ-OPS-142" openspec/specs/operations/spec.md` | 1 match |
| G3 | ADDED Requirements line | `git grep "ADDED Requirements (delta: 2026-09-17-orphan-req-f1-1-f1-2-coverage"` | 1 match |
| G4 | All 7 artifacts in archive | `ls openspec/changes/archive/2026-09-17-orphan-req-f1-1-f1-2-coverage/` | 7 files |
| G5 | No code modifications | `git diff origin/dev -- backend/` | empty |
| G6 | factory_intact CI gate | `python openspec/scripts/check_schema_match.py` | exit 0 |
| G7 | mypy strict passes | `uv run mypy --strict packages/parkos_core/src/parkos_core/api/router_factory.py packages/parkos_core/src/parkos_core/api/v1/auth.py` | "Success: no issues found" |
| G8 | Working tree clean | `git status --short` | empty (modulo pre-existing untracked screenshots) |

## Out of scope (per proposal.md)

- AST walk tests for REQ-OPS-141 / REQ-OPS-142
- F1.12 V8/V8b STUB follow-up
- F1.10 / F1.11 missing verify-report.md archive policy decision
- Other HU Fase 1 without REQ coverage (none found in audit)