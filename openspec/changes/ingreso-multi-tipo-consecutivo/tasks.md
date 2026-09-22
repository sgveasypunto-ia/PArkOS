# Tasks: `ingreso-multi-tipo-consecutivo`

> **Change**: `ingreso-multi-tipo-consecutivo` · **Folder**: `openspec/changes/ingreso-multi-tipo-consecutivo/`
> **Phase**: tasks (sdd-tasks) · **Status**: ready-for-sdd-apply
> **Date**: 2026-09-22 · **Author**: Parkos Dev <dev@parkos.local>
> **Inputs**: `design.md` (Engram `#1998`) + `specs/operations/spec.md` (Engram `#1997`) + `proposal.md` (Engram `#1996`) + `exploration.md` (Engram `#1995`)
> **PR strategy**: chained (PR-A backend → PR-B frontend, gitflow to `dev`)

---

## Metadata

| Field | Value |
|-------|-------|
| Estimated total changed lines | ~1055 LOC (NEW + MODIFY) |
| PR-A backend | ~600 LOC (under 800 budget, single PR) |
| PR-B frontend | ~455 LOC (under 800 budget, single PR) |
| Chained PRs recommended | YES (forecast >800 líneas total; per `delivery_strategy=auto-chain`) |
| 400-line budget risk | LOW for PR-A and PR-B individually |
| Decision needed before apply | NO (auto-chain handles the split) |

```text
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low
```

> **Chain strategy rationale**: PR-B depends on PR-A's response shape (`consecutivo` field on `IngresoRead`). Per AGENTS.md §Gitflow Estricto, both PRs land on `dev` independently with `--no-ff` (each is a separate feature branch with its own commits). PR-B cannot merge until PR-A is in `dev`.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Backend foundation: migration + ORM + helper + handler | PR-A | `uv run pytest backend/tests/unit/test_repo_ingreso_consecutivo.py backend/tests/unit/test_operacion_ingresos_validaciones.py backend/tests/integration/test_consecutivo_concurrent_posts.py -v` | `uv run alembic upgrade head` + smoke `curl -X POST /api/v1/operacion/ingresos -d '{"placa_presente":false,"uuid_tipo_vehiculo":"..."}'` | `alembic downgrade 0041` — drops column + counter table + REVOKE + trigger |
| 2 | Frontend wiring: Zod discriminated union + Panel + Toggle + Tiquete + print layer | PR-B | `pnpm --filter @parkos/electron-sucursal test` + `typecheck` + `lint` | Chrome DevTools smoke: click "Sin placa" → submit → verify `Identificación: BICI-...` in `<TiqueteModal>` | `git revert <merge-commit>` of PR-B (independent of PR-A) |

---

## Phase 1 — PR-A Backend foundation (chain #1)

**Branch**: `feature/hu-ingreso-sin-placa-backend`
**Target**: `origin/dev` (merge FIRST)
**Strategy**: single PR; 4 work-unit commits A.1 → A.4 → A.5

### Commit A.1 — `feat(backend): migration 0042 — counter table + consecutivo column + triggers`

- [ ] **T-A1.1**: Create `backend/packages/parkos_core/migrations/versions/0042_add_ingreso_consecutivo.py` with `revision='0042_<hash>'`, `down_revision='0041'`. `upgrade()`: `op.create_table('ingreso_consecutivo_contador', ...)` per design §3.1; `op.execute("REVOKE UPDATE, DELETE ON prod.ingreso_consecutivo_contador FROM rol_app;")`; trigger via `op.execute("CREATE TRIGGER trg_ingreso_consecutivo_contador_inmutable BEFORE UPDATE OR DELETE ON prod.ingreso_consecutivo_contador FOR EACH ROW EXECUTE FUNCTION prod.fn_revoke_modify_ingreso_consecutivo();")` — confirm exact trigger-function name in `backend/migrations/` (read-only) precedent; `op.add_column('ingreso', sa.Column('consecutivo', sa.String(20), nullable=True))`; `op.create_index('ingreso_consecutivo_uk', 'ingreso', ['uuid_sucursal', 'uuid_tipo_vehiculo', 'consecutivo'], unique=True, postgresql_where=sa.text('consecutivo IS NOT NULL'))`; sync-trigger exclusion inside `fn_enqueue_sync_catalog` precedent (read-only). `downgrade()` reverses. Pre-flight: `uv run alembic upgrade --sql > /tmp/0042.sql` and visual review.
- [ ] **T-A1.2**: Apply to branch-db: `uv run alembic upgrade head`. Verify `\d prod.ingreso_consecutivo_contador` shows columns + `\d prod.ingreso` shows `consecutivo VARCHAR(20) NULL`.
- [ ] **T-A1.3**: Verify REVOKE + trigger: `docker exec parkos-branch-db psql -U parkos -d parkos -c "SELECT grantee, privilege_type FROM information_schema.role_table_grants WHERE table_name='ingreso_consecutivo_contador'"` → `rol_app` MUST NOT have UPDATE/DELETE.
- [ ] **T-A1.4**: Verify partial UK: `docker exec parkos-branch-db psql -U parkos -d parkos -c "\d+ prod.ingreso"` → shows `ingreso_consecutivo_uk` with `WHERE consecutivo IS NOT NULL`.

### Commit A.2 — `feat(backend): assign_ingreso_consecutivo helper + ORM model + Pydantic schema`

- [ ] **T-A2.1**: Create `backend/packages/parkos_core/src/parkos_core/models/A/ingreso_consecutivo_contador.py`. Inherit from `AppendOnlyBase` (`backend/.../models/base.py:177`, read-only). Map columns per design §3.1; `__table_args__` adds bi-temporal UK `uq_ingreso_consecutivo_contador_ns(uuid_sucursal, uuid_tipo_vehiculo, vigente_desde, unique=True)` + `CheckConstraint("ultimo_consecutivo >= 0 AND ultimo_consecutivo < 1000000", name="ck_ingreso_consecutivo_contador_range")`.
- [ ] **T-A2.2**: Modify `backend/packages/parkos_core/src/parkos_core/models/L_E/ingreso.py`: add `consecutivo: Mapped[str | None] = mapped_column(String(20), nullable=True)`.
- [ ] **T-A2.3**: Create `backend/packages/parkos_core/src/parkos_core/repo/ingreso_consecutivo.py`. Implement `assign_ingreso_consecutivo(session, *, uuid_sucursal, uuid_tipo_vehiculo, source_event_uuid) -> str` per design §4 algorithm (mirror `assign_consecutivo` at `backend/.../repo/resolucion_facturacion.py:47-183` read-only). Add `ConsecutivoExhaustedError`. Re-export in `__all__`.
- [ ] **T-A2.4**: Modify `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py`: add `from .ingreso_consecutivo import assign_ingreso_consecutivo` and append to `__all__`.
- [ ] **T-A2.5**: Modify `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py`: add `consecutivo: str | None = None` to `IngresoRead` + `IngresoReadForzado`. `IngresoCreateForzado` no wire-shape change (already `placa=None` allowed).
- [ ] **T-A2.6**: `uv run mypy backend/packages/parkos_core/src/parkos_core/repo/ingreso_consecutivo.py` → clean.
- [ ] **T-A2.7**: `uv run python -c "from parkos_core.models.A.ingreso_consecutivo_contador import IngresoConsecutivoContador; print(IngresoConsecutivoContador)"` → no error.

### Commit A.3 — `feat(backend): extend POST /operacion/ingresos for no-placa path + consecutivo`

- [ ] **T-A3.1**: Modify `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py`: import `assign_ingreso_consecutivo`. **Step 2 REVISED** (design §5.1): `if payload.uuid_tipo_vehiculo is None and payload.placa is None: raise 422 tipo_vehiculo_requerido_sin_placa`; else behavior as-is. **Step 8 REVISED** (design §5.2): skip `existe_ingreso_activo` when `payload.placa is None`; else behavior as-is. **NEW Step 8.5** (design §5.3): when `payload.placa is None`, `new_uuid = uuid4(); consecutivo = await assign_ingreso_consecutivo(session, uuid_sucursal=target, uuid_tipo_vehiculo=uuid_tipo_vehiculo, source_event_uuid=new_uuid)`. **Step 9 REVISED** (design §5.4): `new_attrs["consecutivo"] = consecutivo; new_attrs["uuid"] = new_uuid` when applicable. **Step 11 REVISED** (design §5.5): include `consecutivo=consecutivo` in `IngresoReadForzado` response.
- [ ] **T-A3.2**: `uv run python -c "from parkos_core.api.v1.operacion import create_ingreso; print(create_ingreso)"` → no error.
- [ ] **T-A3.3**: Verify `__all__` of `api/v1/operacion.py` exports correctly.

### Commit A.4 — `test(backend): unit + integration tests for consec assignment + concurrent POSTs`

- [ ] **T-A4.1**: Create `backend/tests/unit/test_repo_ingreso_consecutivo.py` (8 scenarios): `test_assign_consecutivo_first_returns_000001`; `test_assign_consecutivo_monotonic_per_namespace`; `test_assign_consecutivo_independent_cross_sucursal`; `test_assign_consecutivo_independent_cross_tipo`; `test_assign_consecutivo_idempotent_on_source_event_uuid`; `test_assign_consecutivo_format_uppercase_tipo` (verify `BICI-000001-3f8a1b2c`); `test_assign_consecutivo_concurrent_lock_serializes` (10 `asyncio.gather` same namespace); `test_assign_consecutivo_partial_uk_db_level_defense` (direct INSERT dup → `UniqueViolation`).
- [ ] **T-A4.2**: Modify `backend/tests/unit/test_operacion_ingresos_validaciones.py` (+4 scenarios): `test_post_ingreso_sin_placa_accepted` (201 + `consecutivo`); `test_post_ingreso_sin_placa_sin_uuid_tipo_rejected` (422 `tipo_vehiculo_requerido_sin_placa`); `test_post_ingreso_sin_placa_cupo_agotado` (422 `motivo_forzado_requerido`); `test_post_ingreso_sin_placa_v8_skip` (mock verifies `existe_ingreso_activo` NOT called).
- [ ] **T-A4.3**: Create `backend/tests/integration/test_consecutivo_concurrent_posts.py` (1 scenario): `test_10_concurrent_posts_no_collision` (seed counter; 10 tasks `asyncio.gather` POST; verify 10 distinct consecutivos).
- [ ] **T-A4.4**: Modify `backend/tests/integration/test_ocupacion_view.py` (+1 scenario): `test_mv_ocupacion_diaria_counts_no_placa_ingreso` (POST bici no-placa → `mv_ocupacion_diaria.activos` increments).
- [ ] **T-A4.5**: Run `uv run pytest backend/tests/unit/test_repo_ingreso_consecutivo.py backend/tests/unit/test_operacion_ingresos_validaciones.py backend/tests/integration/test_consecutivo_concurrent_posts.py -v` → all pass.

### Commit A.5 — `chore(backend): merge to dev` (per AGENTS.md §Gitflow Estricto)

- [ ] **T-A5.1**: `git fetch --prune origin && git checkout dev && git -c user.name='Parkos Dev' -c user.email='dev@parkos.local' merge --ff-only origin/dev`.
- [ ] **T-A5.2**: `git checkout -b feature/hu-ingreso-sin-placa-backend`.
- [ ] **T-A5.3**: `git add backend/`.
- [ ] **T-A5.4**: Commit each chunk (A.1 → A.4) with Conventional Commits; NO `Co-Authored-By` AI trailers (AGENTS.md canon).
- [ ] **T-A5.5**: `git push -u origin feature/hu-ingreso-sin-placa-backend`.
- [ ] **T-A5.6**: `gh pr create --base dev --head feature/hu-ingreso-sin-placa-backend --title "feat(operacion): ingreso sin placa (bici/patineta) + consecutivo assignment" --body "<PR summary referencing REQ-OPS-191..198 + REQ-OPS-040 modified>"`.
- [ ] **T-A5.7**: After merge: `git checkout dev && git pull origin dev && git branch -d feature/hu-ingreso-sin-placa-backend && git push origin --delete feature/hu-ingreso-sin-placa-backend`.

---

## Phase 2 — PR-B Frontend wiring (chain #2)

**Branch**: `feature/hu-ingreso-sin-placa-frontend`
**Target**: `origin/dev` (merge AFTER PR-A)
**Dependency**: PR-A merged (response shape `consecutivo` field). PR-B MAY develop in parallel during PR-A review, but MUST NOT merge before PR-A.

### Commit B.1 — `feat(frontend): discriminated union Zod for POST /ingresos`

- [ ] **T-B1.1**: Modify `apps/electron-sucursal/src/features/operacion/lib/ingresoApi.ts`: refactor `PostIngresoPayloadSchema` to `z.discriminatedUnion('placa_presente', [placaConPlacaSchema, placaSinPlacaSchema])`. Add `consecutivo: z.string().nullable()` to `PostIngresoResponseSchema`.
- [ ] **T-B1.2**: Create `apps/electron-sucursal/src/features/operacion/lib/__tests__/ingresoApi.test.ts` (4 scenarios): `test_postIngreso_con_placa_payload_validation_accepted`; `test_postIngreso_sin_placa_payload_validation_accepted`; `test_postIngreso_mixed_payload_rejected` (`placa_presente:true + placa:null` → ZodError); `test_postIngreso_response_parses_consecutivo` (mock backend response with consecutivo → parse OK).
- [ ] **T-B1.3**: `pnpm --filter @parkos/electron-sucursal test ingresoApi` → all pass.
- [ ] **T-B1.4**: `pnpm --filter @parkos/electron-sucursal typecheck` → clean.

### Commit B.2 — `feat(frontend): IngresoSinPlacaPanel + TipoIngresoToggle + useTiposVehiculoSinPlaca hook + i18n`

- [ ] **T-B2.1**: Create `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculoSinPlaca.ts`. Filter logic excludes `carro` + `moto` (case-sensitive per canon lowercase), keeps `bicicleta` + `patineta`. Propagates `isFromFallback` from `useTiposVehiculo()`.
- [ ] **T-B2.2**: Create `apps/electron-sucursal/src/features/catalogos/hooks/__tests__/useTiposVehiculoSinPlaca.test.tsx` (3 scenarios): `test_filter_excludes_carro_moto`; `test_filter_includes_bicicleta_patineta`; `test_filter_empty_when_catalog_only_has_placa_tipos`.
- [ ] **T-B2.3**: Create `apps/electron-sucursal/src/features/operacion/components/IngresoSinPlacaPanel.tsx`. Uses `useTiposVehiculoSinPlaca()`; empty-state if `tipos.length===0`; shadcn `<Select>`; RHF + Zod (`placaSinPlacaSchema`); `<Button>` "Generar ingreso" submits `postIngreso({ placa_presente:false, placa:null, uuid_tipo_vehiculo:selected, ... })`; `onSuccess(response)` prop.
- [ ] **T-B2.4**: Create `apps/electron-sucursal/src/features/operacion/components/__tests__/IngresoSinPlacaPanel.test.tsx` (3 scenarios): `test_renders_with_tipos`; `test_submit_calls_postIngreso`; `test_empty_state_when_no_tipos`.
- [ ] **T-B2.5**: Create `apps/electron-sucursal/src/features/operacion/components/TipoIngresoToggle.tsx`. Wrapper with two `<Button>` side-by-side (`Con placa` default variant + `Sin placa` outline + `aria-describedby` tooltip); renders active panel via `renderConPlaca()` / `renderSinPlaca()` render props.
- [ ] **T-B2.6**: Modify `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json`: add 7 keys (`ingreso_sin_placa_cta`, `ingreso_sin_placa_selector_label`, `ingreso_sin_placa_tipo_bicicleta`, `ingreso_sin_placa_tipo_patineta`, `ingreso_sin_placa_generar_boton`, `ingreso_sin_placa_exito`, `ingreso_sin_placa_empty_state`, `tiquete_identificacion_label`).
- [ ] **T-B2.7**: `pnpm --filter @parkos/electron-sucursal typecheck` → clean.

### Commit B.3 — `feat(frontend): wire Principal + IngresoPanel + TiqueteModal + print layer for no-placa`

- [ ] **T-B3.1**: Modify `apps/electron-sucursal/src/features/operacion/pages/Principal.tsx`: replace direct `<PlacaInput>` with `<TipoIngresoToggle>` rendering both panels; add `handleIngresoSinPlacaSuccess`; reset toggle to `'con-placa'` after each submit (`key="fresh"` remount pattern).
- [ ] **T-B3.2**: Modify `apps/electron-sucursal/src/features/operacion/components/IngresoPanel.tsx`: same as T-B3.1.
- [ ] **T-B3.3**: Modify `apps/electron-sucursal/src/features/operacion/components/TiqueteModal.tsx`: add `consecutivo?: string | null` prop; render `Identificación: {consecutivo}` line when non-null; always render `Folio: {uuid_ingreso}` for QR + audit (DEC-SUC-26).
- [ ] **T-B3.4**: Create `apps/electron-sucursal/src/features/operacion/components/__tests__/TiqueteModal.test.tsx` (2 scenarios): `test_renders_con_placa_default`; `test_renders_identificacion_with_consecutivo`.
- [ ] **T-B3.5**: Modify `apps/electron-sucursal/src/lib/print/escposTemplates.ts`: refactor `entradaPayloadSchema` to discriminated union on `variant: 'con-placa' | 'con-consecutivo'`; `entradaConConsecutivoSchema` requires `consecutivo: z.string().regex(/^[A-Z]{3,12}-[0-9]{6}-[0-9a-f]{8}$/)` and `placa: z.null()`.
- [ ] **T-B3.6**: Modify `apps/electron-sucursal/src/lib/print/escposBuilder.ts`: in `buildEntradaBuffer`, branch on `payload.variant` — `con-placa` → `Placa: ${payload.placa}\n`; `con-consecutivo` → `Identificación: ${payload.consecutivo}\n`.
- [ ] **T-B3.7**: Modify `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts`: same conditional HTML line.
- [ ] **T-B3.8**: Modify `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts`: add 1 scenario byte-fixture pin exact `Identificación: BICI-000001-3f8a1b2c\n` at 12th conceptual field.
- [ ] **T-B3.9**: `pnpm --filter @parkos/electron-sucursal test` → all pass.
- [ ] **T-B3.10**: `pnpm --filter @parkos/electron-sucursal typecheck` → clean.
- [ ] **T-B3.11**: `pnpm --filter @parkos/electron-sucursal lint --max-warnings 0` → clean.

### Commit B.4 — `chore(frontend): merge to dev` (per AGENTS.md §Gitflow Estricto)

- [ ] **T-B4.1**: `git fetch --prune origin && git checkout dev && git pull origin dev`.
- [ ] **T-B4.2**: `git checkout -b feature/hu-ingreso-sin-placa-frontend`.
- [ ] **T-B4.3**: `git add apps/electron-sucursal/`.
- [ ] **T-B4.4**: Commit each chunk (B.1 → B.3) with Conventional Commits; NO `Co-Authored-By` AI trailers.
- [ ] **T-B4.5**: `git push -u origin feature/hu-ingreso-sin-placa-frontend`.
- [ ] **T-B4.6**: `gh pr create --base dev --head feature/hu-ingreso-sin-placa-frontend --title "feat(frontend): ingreso sin placa UI (bici/patineta)" --body "<PR summary referencing REQ-OPS-194..197 + design §7>"`.
- [ ] **T-B4.7**: After merge: cleanup (same as T-A5.7).

---

## Phase 3 — Verification gates (per PR)

### PR-A gates
- [ ] `uv run alembic upgrade --sql` pre-flight reviews SQL without errors.
- [ ] `uv run pytest backend/tests/unit/ backend/tests/integration/test_consecutivo_concurrent_posts.py -v` → all pass.
- [ ] `uv run mypy backend/packages/parkos_core/src/parkos_core/` → clean.
- [ ] `uv run ruff check backend/` → clean.
- [ ] `bash openspec/scripts/check_schema_match.py` → exit 0 (if exists).

### PR-B gates
- [ ] `pnpm --filter @parkos/electron-sucursal test` → all pass.
- [ ] `pnpm --filter @parkos/electron-sucursal typecheck` → clean.
- [ ] `pnpm --filter @parkos/electron-sucursal lint --max-warnings 0` → clean.
- [ ] Chrome DevTools smoke (UI running on `:5173`): login `operador@parkos.local`; verify INVENTARIO panel shows 4 tipos (carro/moto/bici/patineta); click "Sin placa" → select "Bicicleta" → click "Generar ingreso"; verify 201 + `<TiqueteModal>` shows `Identificación: BICI-000001-<uuid8>`; verify INVENTARIO `BICICLETA` `activos` increments 0→1.

---

## Phase 4 — Rollback strategy

- **PR-A**: `alembic downgrade 0041_seed_configuracion_tolerancias` drops `prod.ingreso.consecutivo` column + partial UK + `prod.ingreso_consecutivo_contador` table + REVOKE + trigger. ORM reverts on `git revert`.
- **PR-B**: `git revert <merge-commit>` of PR-B.
- Each PR is independently revertible. Reverting PR-B with PR-A still merged leaves the backend accepting `consecutivo` responses that the frontend cannot display — acceptable degraded state until PR-B re-lands.

---

## Phase 5 — Dependencies between PRs

- **PR-A**: NO dependencies (foundational).
- **PR-B**: depends on PR-A (response shape `consecutivo` field).
- **Merge order**: PR-A first → PR-B second.

---

## References

- `openspec/changes/ingreso-multi-tipo-consecutivo/design.md` (read-only) — 928 lines, primary input
- `openspec/changes/ingreso-multi-tipo-consecutivo/specs/operations/spec.md` (read-only) — REQ-OPS-191..198 + REQ-OPS-040 modified
- `openspec/changes/ingreso-multi-tipo-consecutivo/proposal.md` (read-only) — DEC-INCOME-01..05
- `openspec/changes/ingreso-multi-tipo-consecutivo/exploration.md` (read-only) — 12 gaps G1..G12, 11 risks R1..R11
- `AGENTS.md` §Architectural Principles (audit-first, bi-temporal, C/Q/U-no-D)
- `AGENTS.md` §Gitflow Estricto (PR → `dev`, no `Co-Authored-By` AI trailers)
- `openspec/config.yaml` `rules.tasks` (800 LOC/PR budget; REVOKE + trigger in same migration; pre-flight `alembic upgrade --sql`)
- `backend/packages/parkos_core/src/parkos_core/models/A/idempotency_keys.py` (read-only) — 50th `[A]` table precedent
- `backend/packages/parkos_core/src/parkos_core/models/base.py:177` (read-only) — `AppendOnlyBase`
- `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py:47-183` (read-only) — `assign_consecutivo` SELECT FOR UPDATE pattern
- `backend/packages/parkos_core/migrations/versions/0037_add_uuid_subscripcion_cliente_to_facturas.py` (read-only) — nullable ADD COLUMN precedent
- Engram: `#1995` explore · `#1996` proposal · `#1997` spec · `#1998` design · `#<new>` tasks