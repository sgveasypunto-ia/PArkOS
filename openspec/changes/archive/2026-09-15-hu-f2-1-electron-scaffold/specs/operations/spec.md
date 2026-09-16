# Delta Spec: operations — HU-F2.1 (scaffold apps/electron-sucursal + apps/ui-kit + shadcn/ui 14 componentes)

> **Change**: `hu-f2-1-electron-scaffold`
> **Capability**: operations
> **Phase**: spec (sdd-spec)
> **Status**: ready for sdd-design (parallel) + sdd-tasks
> **Date**: 2026-09-15
> **Author**: orchestrator (sdd-spec sub-agent)

## 1. Delta Summary

**No new REQ added by this change.** Per DEC-ELEC-10 (proposal.md §6.10), F2.1 is frontend infrastructure scaffolding with no behavior contract — it adds NO HTTP endpoint, NO table, NO migration, NO sync catalog row, NO permission grant. The 10 architectural decisions DEC-ELEC-01..10 in proposal.md §6 are the contract carrier for this change.

## 2. Affected Capabilities

| Capability | Action | Reason |
|---|---|---|
| operations | NO-OP | F2.1 doesn't add HTTP endpoints, tables, migrations, or sync rows |
| hooks | NO-OP | F2.1 doesn't add sync hooks |
| cutover-migration | NO-OP | F2.1 doesn't change cutover semantics |
| sync-catalog | NO-OP | F2.1 doesn't add sync_catalog rows |
| sync-motor | NO-OP | F2.1 doesn't change sync behavior |

## 3. New Requirements

**NONE.** No REQ-OPS-NNN, no REQ-ELEC-NNN, no new capability spec created.

### 3.1 Why no new REQ

- F2.1 ships no HTTP endpoint → no behavior contract to specify.
- F2.1 ships no DB migration → no data contract.
- F2.1 ships no sync row → no sync contract.
- F2.1 ships no permission grant → no RBAC contract.
- The 10 DEC-ELEC-NN live in proposal.md §6 as architectural commitments. They are NOT REQs because they describe IMPLEMENTATION (tooling, config, build) not BEHAVIOR (what the system does in response to a stimulus).

### 3.2 What deferred specs will own

| Future spec | Will own | Phase |
|---|---|---|
| F2.2 spec.md (operations delta) | parkosFetch retry/refresh/idempotency semantics | F2.2 SDD |
| F2.3 spec.md (operations delta) | Auto-update signature, kiosko PIN bcrypt ≥12 | F2.3 SDD |
| F3.1 spec.md (operations delta) | Login UI flow + lockout visibility | F3.1 SDD |

## 4. Cross-References to Existing REQs

F2.1 references the following existing requirements INFORMATIONALLY only (does not amend them):

- REQ-OPS-XR6 (operations/spec.md:3951 — 5-layer defense in depth) — F2.1's engineering defense layers (TS strict, ESLint, Prettier, axe-core, shadcn typed) echo XR6's spirit but are scoped to frontend infra, not backend behavior. NO XR7 created (per F1.15 DEC-XR7 NOT-CREATED precedent at operations/spec.md:4386).
- REQ-OPS-002 (operations/spec.md:32 — sync module coverage ≥80%) — does NOT apply to F2.1 (F2.1 is not a sync module). F2.1 ships minimal Vitest smoke; ≥90% coverage starts F2.2.

## 5. Diff Against Canonical Spec

operations/spec.md canonical remains UNCHANGED at 112 REQs after this change. No REQ-NNN added, modified, or removed.

## 6. Open Questions

NONE.

## 7. Next Recommended Phase

PHASE: sdd-design hu-f2-1-electron-scaffold (16-section design at openspec/changes/hu-f2-1-electron-scaffold/design.md).

Pre-design handoff:
- 10 DEC-ELEC-NN verbatim from proposal.md §6.
- 4-cluster decomposition C1→C2→C3→C4 from exploration.md §16.
- 5 engineering defense layers from exploration.md §11.
- 8 risks from exploration.md §10.
- Reference apps/web_admin/{package.json,vite.config.ts,tsconfig*.json,tailwind.config.ts,components.json,eslint.config.js,.prettierrc.json,playwright.config.ts,vitest.config.ts,index.html,src/index.css,src/lib/utils.ts,src/i18n/index.ts,src/components/ui/button.tsx,e2e/smoke.spec.ts,src/App.tsx,src/main.tsx,src/test-setup.ts}.
