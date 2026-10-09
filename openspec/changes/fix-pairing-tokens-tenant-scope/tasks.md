# fix-pairing-tokens-tenant-scope — Tasks

Total LOC budget: ~250 (backend ~120, frontend ~30, tests ~80, SDD ~30). One
PR to `dev` is enough; no chained-PR split needed.

## T1 — Backend: swap the narrow check for `require_branch_scope`

File: `backend/packages/parkos_core/src/parkos_core/api/v1/pairing.py`

- [ ] Import `BranchScope` and `require_branch_scope` from `...auth.tenancy`.
- [ ] Add `scope: BranchScope = Depends(require_branch_scope)` to
      `issue_pairing_token`, `read_pairing_token`, `revoke_pairing_token`.
- [ ] Replace the three narrow `ctx.sucursal_uuid != ...` checks with
      `scope.allows(...)`. Keep the 403 / 404 / 422 status codes identical to
      the pre-982209d8 public contract; only the comparison changes.
- [ ] Update the module docstring at `pairing.py:1-43` to cite
      `require_branch_scope` / `BranchScope` as the source of truth for
      `admin-` scope (replacing the now-stale "X-Sucursal-Context header"
      wording at lines 27-30).

## T2 — Tests: pin the multi-branch contract

File: `backend/tests/unit/test_pairing_endpoints.py`

- [ ] Add a `scope: BranchScope` override in both `app` and `_make_app`
      fixtures, parameterizable per test (default = `permitidas = {SUCURSAL_UUID}`).
- [ ] Rewrite
      `TestIssuePairingToken.test_rejects_out_of_scope_sucursal_before_insert`
      to express the new contract: `permitidas = {SUCURSAL_UUID}`,
      body `uuid_sucursal=other_sucursal` → 403, no row added.
- [ ] Add
      `TestIssuePairingToken.test_admin_with_multi_branch_scope_can_issue_for_any_branch`:
      `permitidas = {A, B}`, body = A or B → 201; verifies the bug the user
      reported is fixed.
- [ ] Add `TestReadPairingToken.test_out_of_scope_row_returns_403`:
      row's `uuid_sucursal` outside `permitidas` → 403.
- [ ] Add `TestRevokePairingToken.test_out_of_scope_row_returns_403`:
      same shape.

## T3 — Frontend: evict stale localStorage on 404

File: `apps/web_admin/src/features/pairing/lib/pairingLocalState.ts`
File: `apps/web_admin/src/features/pairing/pages/Pairing.tsx`

- [ ] Add `deleteLocalRecord(sucursalUuid)` to `pairingLocalState.ts`.
- [ ] In `PairingRow`, when `useSWR` resolves to
      `PairingTokenNotFoundError`, call `deleteLocalRecord(sucursal.uuid)` so
      the cached UUID is gone after the first sustained 404.

## T4 — Verify

- [ ] `uv run pytest backend/tests/unit/test_pairing_endpoints.py -q`
- [ ] `uv run pytest backend/tests/integration/test_pairing_flow.py -q` (if it
      still exists; it was `xfail`-heavy in AGENTS.md — confirm it still
      imports and run it).
- [ ] `uv run ruff check backend/packages/parkos_core/src/parkos_core/api/v1/pairing.py`
- [ ] `pnpm --filter web_admin run lint && pnpm --filter web_admin run typecheck`

## T5 — Commit + close

- [ ] `git add backend/ apps/web_admin/ openspec/changes/fix-pairing-tokens-tenant-scope/`
- [ ] Conventional commit:
      `fix(pairing): tenant-scope uses require_branch_scope (multi-branch admin) + evict stale localStorage on 404`
- [ ] `git push -u origin fix/hu-f19-3-pairing-tokens-tenant-scope`
- [ ] `gh pr create --base dev --head fix/hu-f19-3-pairing-tokens-tenant-scope` —
      F3.x requires 1 review.
- [ ] After merge to dev: delete branch local + remote, invalidate Vite cache
      per AGENTS.md "Post-merge: invalidar Vite cache" recipe.

## Out of scope (deferred)

- 50th pairing endpoint `GET /admin/pairing-tokens?uuid_sucursal=...` to list
  tokens per branch (replaces the BR4 `localStorage` workaround entirely).
  Tracked as `ABIERTO-52` per AGENTS.md.
- DIAN retention visibility on stale records (separate concern; out of this
  change's blast radius).
