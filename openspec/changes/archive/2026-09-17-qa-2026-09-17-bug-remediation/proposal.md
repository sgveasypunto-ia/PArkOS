# Proposal: QA 2026-09-17 Bug Remediation

> **Change**: `qa-2026-09-17-bug-remediation` · **Folder**: `openspec/changes/qa-2026-09-17-bug-remediation/`
> **Phase**: propose (sdd-propose) · **Branch**: `dev` (HEAD `251dba8`) · **PR target**: `origin/dev`
> **Delivery**: `single-pr` (user-approved override of sub-agent `auto-chain` recommendation, recorded below as a Risk)
> **Inputs**: `exploration.md` (5 confirmed E2E blockers + 1 cosmetic, ~330 LOC) · `operations/spec.md:4907` (REQ-OPS-119 `observaciones` mandate) · `operations/spec.md:738` (REQ-OPS-032 MV canon)

## Intent

During manual QA of the 6 already-merged F3–F6 phases on 2026-09-17, 5 E2E blockers prevent the canonical happy path (login → abrir turno → ver ocupación → crear ingreso vehicular → emitir tiquete → cerrar turno). Failures span frontend type-contract drift (Bug 1), SWR fetcher signature anti-pattern (Bug 2), missing materialized view on already-0024 branch containers (Bug 3), catalog-string case mismatch between `detectar_tipo_vehiculo` and the seed (Bug 4), and a missing `observaciones` column on `prod.sesion` rejected by `_Base`'s `extra='forbid'` (Bug 5). This change remediates all 5 so F3–F6 flows run end-to-end without manual workarounds.

## Scope

### In Scope
- **Bug 1 — AbrirTurno Zod silent reject** — `AuthUser.id → uuid` rename + 3 consumer updates + `<FormMessage>` for `uuid_*`. **(REQ-OPS-131)**
- **Bug 2 — `useOcupacion` URL duplication** — fetcher closure `() => getOcupacion(uuid_sucursal)` mirroring `useSesionActiva.ts:55-57`; new U-O10 vitest. **(REQ-OPS-132)**
- **Bug 3 — `prod.mv_ocupacion_diaria` missing** — new migration `0034_recreate_mv_ocupacion_diaria_idempotent.py` with `CREATE OR REPLACE VIEW` + `to_regclass` post-check; add MV to `check_schema_match.py`. **(REQ-OPS-133, extends REQ-OPS-032)**
- **Bug 4 — catalog mismatch** — read lowercase `tipo='carro'/'moto'` matching `replicate_catalogs_to_branch.py:20`; honor explicit `payload.uuid_tipo_vehiculo` first. **(REQ-OPS-134)**
- **Bug 5 — POST `/caja-sesion/sesiones` rejects `observaciones`** — migration `0035_add_observaciones_to_sesion.py` (`ADD COLUMN TEXT NULL`, PG11+ instant, no rewrite per ADR-002) + ORM + Pydantic + repo wiring per REQ-OPS-119. **(REQ-OPS-135)**

### Out of Scope
- `configuracion_seguridad_missing_fallback_to_defaults` warning — cosmetic, hardcoded `(5, 15)` matches `plan.md`; follow-up.
- Seed for missing `tipos_vehiculo` rows (`moto`/`bicicleta`/`patineta`) on stale branches — separate data-fix PR.
- F5.1/F5.2 printer test path — only testable after F6.1 happy path lands.
- F3.2 lockout regression — already verified in original F3.2 PR.

## Capabilities

> CONTRACT with sdd-spec.

### Modified Capabilities
- `operations` — extend `operations/spec.md` with **REQ-OPS-131..135** (frontend `AuthUser.uuid` shape + SWR fetcher-closure + MV idempotency gate + lowercase catalog + `sesion.observaciones`). No new capability files.

## Approach

Per-bug fix ≤3 files each. Bug 5 migration is non-destructive `ADD COLUMN TEXT NULL` (PG11+ instant). Bug 3 uses `CREATE OR REPLACE` so `alembic upgrade head` heals already-0024 containers. Tests: 1 pytest per backend bug + 1 vitest per frontend bug. **Single PR** approved by user; stacked into 3 commits via `work-unit-commits` boundaries (FE / BE-MV / BE-CATALOG-SESION) so partial `git revert` is possible. Net ~330 LOC under 800-LOC budget.

## Affected Areas

| Path | Impact | Description |
|---|---|---|
| `apps/ui-kit/src/hooks/useAuth.ts:33-36` | Modified | `AuthUser.id → uuid` |
| `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.tsx:51` | Modified | `user?.uuid` + `<FormMessage uuid_*>` |
| `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.ts:77` | Modified | Fetcher closure `() => getOcupacion(uuid_sucursal)` |
| `backend/.../migrations/versions/0034_recreate_mv_ocupacion_diaria_idempotent.py` | New | `CREATE OR REPLACE` + `to_regclass` post-check |
| `openspec/scripts/check_schema_match.py` | Modified | Add `prod.mv_ocupacion_diaria` to mandatory scan |
| `backend/.../src/parkos_core/repo/placa.py:48-60` | Modified | Lowercase `tipo_nombre = "carro"/"moto"` |
| `backend/.../api/v1/operacion.py:177` | Modified | Honor `payload.uuid_tipo_vehiculo` first |
| `backend/.../migrations/versions/0035_add_observaciones_to_sesion.py` | New | `ADD COLUMN observaciones TEXT NULL` |
| `backend/.../models/L_S/sesion.py`, `schemas/caja.py`, `repo/session_cycle.py` | Modified | Surface `observaciones` end-to-end |
| `apps/ui-kit/package.json` | Modified | Workspace version bump (breaking shape) |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Bug 1 `AuthUser.id → uuid` breaks unknown consumers | Low | `git grep -rn "user?.id\|user\.id" apps/` pre-merge; `tsc --noEmit` CI gate |
| Bug 3 leaves MV empty on first run after upgrade | Low | `CREATE OR REPLACE` recreates view; `RefreshMvOcupacionWorker` (REQ-OPS-033) refreshes on first cycle |
| Bug 5 `ADD COLUMN` rewrite on prod | Med | PG11+ instant, no rewrite; `alembic upgrade --sql` pre-flight; ADR-002 AUDIT-FIRST |
| User chose `single-pr` over sub-agent `auto-chain` | Med | 3 stacked commits via `work-unit-commits` boundaries; partial `git revert` possible |
| Sync replication of new MV (0034) cloud↔branch | High | MV definition is local-only `prod.*`; cloud gets its own copy via entrypoint replay; archive-report docs |
| Bug 4 catalog drift cloud (`Auto`) vs branch (`carro`) | Low | Fix only the lookup string; admin cleanup is separate PR |

## Rollback Plan

Single PR — `git revert <merge-sha>` reverts 5 commits atomically. Migrations `0034`/`0035` have `downgrade()` dropping the MV / column cleanly. Frontend revert restores the pre-2026-09-17 broken behavior (acceptable — releases already shipped with it). Partial rollback via `git revert <commit-sha>` of FE / BE-MV / BE-CATALOG-SESION commit independently.

## Dependencies

- `check_schema_match.py` MUST extend BEFORE bug 3 lands so CI catches future MV drift.
- `apps/ui-kit` is a workspace package; version bump required (breaking `AuthUser` shape).
- `replicate_catalogs_to_branch.py` is the canonical seed — no change needed (already lowercase).

## Success Criteria

- [ ] `vitest run src/features/operacion src/features/caja` passes with new U-O10
- [ ] `uv run pytest backend/tests/unit/test_repo_placa.py backend/tests/unit/test_auth_login_password.py backend/tests/unit/test_sesion_create.py -q` passes
- [ ] Manual E2E with `operador@parkos.local`: login → abrir turno → ver ocupación (no 422/500) → crear ingreso (no `placa_formato_invalido`) → cerrar turno, all green
- [ ] `python openspec/scripts/check_schema_match.py` exits 0 with MV + `observaciones` column verified
- [ ] Single PR merged to `dev` under `<800` LOC, 3 stacked commits
