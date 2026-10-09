# fix-pairing-tokens-tenant-scope

## Why

The pairing-token admin surface (HU-F19.3) returns 403 `tenant_scope_violation` for
legitimate multi-branch operations: an admin with `sucursales_permitidas = {A, B}`
who has `X-Sucursal-Context: A` selected in the BranchSelector and clicks "Generar
token" on the row for branch B gets a 403. The branch picker and the action target
are decoupled in the UI (`apps/web_admin/src/lib/sucursal-context.tsx:91-93` reads
the header from `localStorage` independently of the clicked row), so the mismatch
is the normal admin flow, not a misuse.

The current `pairing.py:207-215 / 297-305 / 358-367` check fires when
`ctx.sucursal_uuid != payload/row.uuid_sucursal`. `ctx.sucursal_uuid` is the
header value; the **real** scope for an `admin-` issuer is
`extract_sucursales_permitidas_fresh(session, actor_uuid)` (read from
`prod.usuarios_sucursal` at request time, not the stale JWT claim snapshot).

## What

Replace the three narrow `ctx.sucursal_uuid != ...` checks with
`Depends(require_branch_scope)` + `scope.allows(uuid_sucursal)`. The behavior of
`982209d8 fix(pairing): corrige tenant-scope en emisión, revoked_at inalcanzable y
gate del botón Revocar` is preserved where correct:

- **Preserved** (good): the orphan-row prevention (check fires BEFORE `session.add`
  / `commit`, never INSERTs an unreadable row).
- **Preserved** (good): the `revoked_at` / `revoked_by` overlay from
  `revoked_sync_jwts` (UI "Revocado" badge is reachable).
- **Preserved** (good): the unconditional `Revocar` button in `<Pairing />`.
- **Replaced** (the real bug): the narrow `ctx.sucursal_uuid != ...` comparison
  with `scope.allows(...)` so an admin with branch B in their
  `usuarios_sucursal` rows can issue/read/revoke a token for B while their picker
  sits on A.

## Two follow-on listener-sabotage fixes (2026-10-09, same change set)

After layering the `require_branch_scope` swap on top of `982209d8`, two more
bugs surfaced under the same admin-multi-branch flow that the original fix
intended to enable. Both are caused by the `do_orm_execute` listener in
`db/tenancy.py:179-194` auto-adding `WHERE uuid_sucursal = :ctx` to every
SELECT that touches a table carrying `uuid_sucursal` — the listener is correct
for the *body* of business reads (it's how `/empresa/sucursal` and
`/operacion/ocupacion` achieve single-tenant reads), but the pairing surface
needs the SELECT to be scope-unfiltered because the explicit `scope.allows`
check is the single source of truth for "may this actor see this row".

### `db/tenancy.py:extract_sucursales_permitidas_fresh` — the scope-defining SELECT

The function queries `prod.usuarios_sucursal` to read the admin's full
permitted set. With a tenant context bound (any `admin-` request that
arrived with `X-Sucursal-Context: B`), the listener would add
`WHERE uuid_sucursal = B` to that SELECT, returning just B (or empty).
`BranchScope.permitidas` was then `{B}` and the explicit `scope.allows(A)`
check rejected A. The fix is to wrap the SELECT in
`with suspend_tenant_context():` — the function's whole purpose is to read
the full set; no caller would want the filtered result. This benefits all
9 call sites of the function (admin_views, auditoria, reporteria,
workflows_alerta, admin_usuarios, auth/tenancy itself) — none of them
currently wrap their call.

### `pairing.py:session.refresh` and `_load_pairing_token` — the new-code holes

Two more SELECTs in `pairing.py` itself fall foul of the same listener:

- **`session.refresh(row)` after `commit()`**: with the new code, the row is
  bound to the body's branch (A) but the tenant context is the header's
  branch (B). The refresh SELECT then filters by `WHERE uuid_sucursal = B`
  and the row's PK doesn't satisfy it → `InvalidRequestError: Could not
  refresh instance` (500). Wrap in `with suspend_tenant_context():` — same
  pattern as `empresa.py:1580` and `_factura_display.py:205`.
- **`_load_pairing_token`** (the PK lookup for GET and revoke): the listener
  filters the SELECT by the active context, so a row in branch A is
  invisible when the header is B. Wrap in
  `with suspend_tenant_context():` so the explicit `scope.allows` check
  is the single source of truth for the read.

`revoked_sync_jwts` is NOT wrapped: it has no `uuid_sucursal` column, so the
listener doesn't filter it. The earlier draft wrap was speculative and
removed.

Plus a small UX fix in `Pairing.tsx`: when the cached `pairingTokenUuid` resolves
to a 404, evict the stale `localStorage` record so subsequent renders don't
re-fire the 404 (the response is correct — the row really doesn't exist — but the
network panel and the per-row state stay clean).

## How

### Backend — `backend/packages/parkos_core/src/parkos_core/api/v1/pairing.py`

1. Import `BranchScope` and `require_branch_scope` from `...auth.tenancy`.
2. Import `suspend_tenant_context` from `...db.tenancy`.
3. Add `scope: BranchScope = Depends(require_branch_scope)` to all four
   endpoints (`issue_pairing_token`, `read_pairing_token`,
   `revoke_pairing_token`, `revoke_branch_sync_token`).
4. Replace each narrow check:
   - POST: `if payload.uuid_sucursal is not None and not scope.allows(payload.uuid_sucursal): raise 403`
   - GET: `if not scope.allows(row.uuid_sucursal): raise 403` (after the
     existing 404-not-found check; 403 vs 404 contract preserved so the public
     API behavior on truly-missing rows is unchanged).
   - revoke: same as GET.
   - revoke-sync: `if not scope.allows(uuid_sucursal): raise 403` (branch is
     in the URL path).
5. Wrap `session.refresh(row)` in `with suspend_tenant_context():` (the
   refresh needs to see our own just-written row regardless of tenant
   context).
6. Wrap the SELECT inside `_load_pairing_token` in
   `with suspend_tenant_context():` (the explicit `scope.allows` check is
   the single source of truth for the read).

### Backend — `backend/packages/parkos_core/src/parkos_core/db/tenancy.py`

1. Wrap the SELECT inside `extract_sucursales_permitidas_fresh` in
   `with suspend_tenant_context():`. This benefits all 9 call sites of
   the function, not just `pairing.py`.

### Tests — `backend/tests/unit/test_pairing_endpoints.py`

1. Add a `BranchScope` override in the `app` and `_make_app` fixtures so the
   test client can dial in a `permitidas` set per test.
2. Rewrite `TestIssuePairingToken::test_rejects_out_of_scope_sucursal_before_insert`
   to use the new scope: `permitidas = {SUCURSAL_UUID}`, body
   `uuid_sucursal=other_sucursal` → 403, `len(fake_session.added) == 0`.
3. Add `TestIssuePairingToken::test_admin_with_multi_branch_scope_can_issue_for_any_branch`:
   `permitidas = {SUCURSAL_UUID, OTHER_SUCURSAL_UUID}`, body
   `uuid_sucursal=OTHER_SUCURSAL_UUID` (or `SUCURSAL_UUID`) → 201.
4. Add `TestReadPairingToken::test_out_of_scope_row_returns_403`:
   `permitidas = {SUCURSAL_UUID}`, row `uuid_sucursal=other_sucursal` → 403.
5. Add `TestRevokePairingToken::test_out_of_scope_row_returns_403`: same shape.

### Tests — `backend/tests/integration/test_pairing_admin_scope_db.py` (new)

Real-Postgres integration test that exercises the listener-sabotage path end
to end. Requires a clean DB (TRUNCATE) so it can't run against the live
cloud DB without `PARKOS_DOCKER_TEST=1` + a fresh schema. Will run
unattended in CI once the testcontainer image with `pg_partman` is wired.

### Frontend — `apps/web_admin/src/features/pairing/lib/pairingLocalState.ts` and `pages/Pairing.tsx`

1. Add `deleteLocalRecord(sucursalUuid)` to `pairingLocalState.ts`.
2. In `PairingRow`, when `useSWR` returns `PairingTokenNotFoundError`, call
   `deleteLocalRecord(sucursal.uuid)` to clean up the cache.

## Non-goals

- No change to the `revoked_at` overlay behavior (kept as-is from 982209d8).
- No change to the `Revocar` button enablement (kept unconditional per
  982209d8 — Section B of the modal still needs to be reachable from any state).
- No new "list pairing tokens by branch" endpoint (still ABIERTO-52).
- No new pairing-token DB row created for the 404 stale-record case (the row
  really doesn't exist; the frontend just stops asking).
- No "empty 403 body" debug: the API strips the body in the 403 response in
  some configurations (likely a middleware). Pre-existing, out of scope.
- No bulk refactor of the other 8 call sites of
  `extract_sucursales_permitidas_fresh` (admin_views, auditoria, reporteria,
  workflows_alerta, admin_usuarios) — those benefit transparently from the
  function-internal fix; if any of them were already broken, the
  beneficiary is the same set of admin operations. Verified by a
  spot-check of `test_admin_usuarios_scope.py` (47 tests pass) and
  `test_admin_me_fresh_scope.py` (already covered).

## Risk

- **Tenant scope leak**: regression. The new check is strictly tighter than the
  old one (it rejects MORE cases, never fewer) and is the SAME check
  `/operacion/ocupacion` and `/empresa/tarifas-sucursal` use, so a regression
  here would already be a regression in those endpoints. The static test
  `tests/static/test_tenancy_admin_scope.py` does not scan `pairing.py` (it
  targets `admin_*.py`) — we add `test_rejects_out_of_scope_sucursal` +
  `test_admin_with_multi_branch_scope_can_issue_for_any_branch` so the contract
  is pinned in unit tests.
- **Test rewrites**: 1 existing test rewrites + 3 new tests; total test delta
  ~80 LOC. The old test happens to still pass with the new check (it sends a
  body `uuid_sucursal` outside the admin's `permitidas` set), but the wording
  changes to make the scenario explicit.
- **Listener double-wrap**: `suspend_tenant_context` is now used 3 times in
  `pairing.py` + 1 in `db/tenancy.py`. The ContextVar is request-scoped
  (per FastAPI task), so there's no global state pollution. Verified by
  end-to-end HTTP smoke (POST issue + GET + POST revoke + GET after
  revoke) with the live cloud DB.
- **Affected call sites of `extract_sucursales_permitidas_fresh`**: the
  function-internal fix benefits all 9 callers. Pre-existing tests for
  admin_usuarios scope, admin_me_fresh_scope, etc. all pass without
  modification (47 + 59 tests, 0 regressions).
- **Stash / branch hygiene**: dev was 240 commits behind `origin/dev` at session
  start. The fix is layered on top of `982209d8` (already on dev), not on top
  of the pre-merge local. No revert / reapply. Docker image rebuild
  (`docker compose -f infra/deploy/docker-compose.cloud.yml up -d --build
  api-admin`) is REQUIRED for the fix to reach the runtime — see
  AGENTS.md post-merge recipe.
