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

Plus a small UX fix in `Pairing.tsx`: when the cached `pairingTokenUuid` resolves
to a 404, evict the stale `localStorage` record so subsequent renders don't
re-fire the 404 (the response is correct — the row really doesn't exist — but the
network panel and the per-row state stay clean).

## How

### Backend — `backend/packages/parkos_core/src/parkos_core/api/v1/pairing.py`

1. Import `BranchScope` and `require_branch_scope` from `...auth.tenancy`.
2. Add `scope: BranchScope = Depends(require_branch_scope)` to all three
   endpoints (`issue_pairing_token`, `read_pairing_token`,
   `revoke_pairing_token`).
3. Replace each narrow check:
   - POST: `if payload.uuid_sucursal is not None and not scope.allows(payload.uuid_sucursal): raise 403`
   - GET: `if not scope.allows(row.uuid_sucursal): raise 403` (after the
     existing 404-not-found check; 403 vs 404 contract preserved so the public
     API behavior on truly-missing rows is unchanged).
   - revoke: same as GET.
4. The `uuid_sucursal is None` issuance case (pre-branch) stays unrestricted, as
   before.

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

### Frontend — `apps/web_admin/src/features/pairing/lib/pairingLocalState.ts` and `pages/Pairing.tsx`

1. Add `deleteLocalRecord(sucursalUuid)` helper that removes one entry from the
   `easypunto.pairing.lastToken.v1` map.
2. In `PairingRow`, when `useSWR` returns `PairingTokenNotFoundError`, call
   `deleteLocalRecord(sucursal.uuid)` and bump the local version so the row
   re-renders without the cached UUID (no further GETs).

## Non-goals

- No change to the `revoked_at` overlay behavior (kept as-is from 982209d8).
- No change to the `Revocar` button enablement (kept unconditional per
  982209d8 — Section B of the modal still needs to be reachable from any state).
- No new "list pairing tokens by branch" endpoint (still ABIERTO-52).
- No new pairing-token DB row created for the 404 stale-record case (the row
  really doesn't exist; the frontend just stops asking).

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
- **Stash / branch hygiene**: dev was 240 commits behind `origin/dev` at session
  start. The fix is layered on top of `982209d8` (already on dev), not on top
  of the pre-merge local. No revert / reapply.
