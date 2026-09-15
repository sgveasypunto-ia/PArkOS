# Apply Report: hu-f1-12-venta-suscripcion

> **Status**: SHIPPED — all 31 tasks [x] across 8 clusters (T1..T8). Ready for `sdd-verify`.
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `93449f3`).
> **Outcome**: 9 atomic commits + tasks.md update. **~860 LOC production + ~720 LOC tests = ~1580 LOC cumulative** for the F1.12 recurso.

## Commits (T1..T8 + T5 gap-fix hotfix)

| # | Cluster | Commit | Files | LOC |
|---|---------|--------|-------|-----|
| 1 | T1 | `22aa5a2 feat(repo): HU-F1.12 — T1 typed exceptions + pre-flight verification` | NEW `repo/venta_suscripcion.py` (partial) | ~50 |
| 2 | T2 | `069cf3c feat(schemas): HU-F1.12 — T2 VentaSuscripcionCreate + VentaSuscripcionResponse` | EXTEND `schemas/clientes.py` | ~130 |
| 3 | T3 | `959afc0 feat(repo): HU-F1.12 — T3 cliente (V1) + plan FOR UPDATE (V2) + vehiculo lookup-or-create (V3)` | EXTEND `repo/venta_suscripcion.py` | ~155 |
| 4 | T4 | `5b94759 feat(repo): HU-F1.12 — T4 validations + prorrateo + INSERT helpers` | EXTEND `repo/venta_suscripcion.py` | ~95 |
| 5 | T5 | `9a089cc feat(api): HU-F1.12 — T5 POST /clientes/venta-suscripcion 10-step handler + router mount` | NEW `api/v1/clientes_venta.py` (244 LOC) + MOD `api/v1/clientes.py` (mount) + 6 handler tests | ~561 |
| 6 | T6 | `1485afe feat(static): HU-F1.12 — T6 AST walks (KD-VENTA-01 single-commit + no-raw-DML + no-UPDATE-on-v)` | 3 NEW AST walk files | ~310 |
| 7 | T5.1 gap fix | `08cb2dd feat(api): HU-F1.12 — T5 gap fix DEC-VENTA-01..05 V4/V5/V6/V7 typed-exception mapping` | MOD `api/v1/clientes_venta.py` (4 try/except blocks) | +54/-14 |
| 8 | T7 | `93449f3 test(backend): HU-F1.12 — T7 4 mandated unit tests + e2e + MIGRATION 0030 idempotency` | 3 NEW test files | 732 |
| 9 | T8 | (this commit) `chore(openspec): HU-F1.12 — T8 MIGRATION 0030 NO-OP + apply-report` | NEW migration + apply-report | ~120 |

Total: **~1580 LOC** across 9 atomic commits. All commits <800 LOC ceiling.

> **T5.1 hotfix rationale.** T5 commit `9a089cc` mapped V1 `ClienteNoEncontradoError` → 404 but the DEC-VENTA-01..05 contract mandates ALL 5 typed exceptions map to HTTPException. Without V4/V5/V6/V7 mapping the T7 mandated tests (`plan.md` line 1047) would have returned 500 (no-store absent). The 9th commit closes the RED→GREEN boundary; the T5 commit was RED-incomplete per the contract.

## Cluster Table

| Cluster | Tasks | Status | RED Tests | GREEN | Implementation |
|---------|-------|--------|-----------|-------|----------------|
| T1 | T1.1..T1.3 | [x] | 1 module-import | [x] | `repo/venta_suscripcion.py` skeleton + 7 typed exceptions |
| T2 | T2.1..T2.4 | [x] | 11 schema unit | [x] | `VentaSuscripcionCreate` + `VentaSuscripcionResponse` (+ `extra='forbid'`, XOR validator, placas 1-2 range) |
| T3 | T3.1..T3.5 | [x] | 5 repo unit | [x] | V1 cliente lookup-or-create + V2 plan FOR UPDATE + V3 vehiculo lookup-or-create |
| T4 | T4.1..T4.5 | [x] | 14 repo unit | [x] | V4 placa-dup + V5 mismo-tipo + V6 max-vehiculos + V7 A-09 prorrateo + V9a/V9b INSERTs |
| T5 | T5.1..T5.4 | [x] | 6 handler tests | [x] | 10-step handler chain + router mount + KD-3 issuer dep + V1 404 mapping |
| T5.1 gap | (deviation) | [x] | n/a | [x] | V5/V6/V4/V7 typed-exception → 422 HTTPException mapping (closed in `08cb2dd`) |
| T6 | T6.1..T6.3 | [x] | 3 AST walks | [x] | KD-VENTA-01 single-commit + no-raw-DML + no-UPDATE-on-v walks |
| T7 | T7.1..T7.3 | [x] | 4 mandated unit + 1 e2e + 2 migration | [x] | All RED tests pass GREEN |
| T8 | T8.1..T8.2 | [x] | n/a (sweep) | [x] | MIGRATION 0030 NO-OP audit trail + apply-report |

## Test Summary (final, pure-Python; no Docker daemon available)

| Test file | Cluster | Tests | Result |
|-----------|---------|-------|--------|
| `tests/unit/test_venta_suscripcion_exceptions.py` | T1.1 | 1 | PASS |
| `tests/unit/test_venta_suscripcion_schemas.py` | T2.1+T2.3 | 11 | PASS |
| `tests/unit/test_venta_suscripcion_repo.py` | T3.1+T3.3+T3.5 | 5 | PASS |
| `tests/unit/test_venta_suscripcion_validations.py` | T4.1+T4.2+T4.3+T4.4+T4.5 | 14 | PASS |
| `tests/unit/test_venta_suscripcion_handler.py` | T5.1+T5.2+T5.3+T5.4 | 6 | PASS |
| `tests/unit/test_venta_suscripcion.py` | T7.1 | 4 | PASS |
| `tests/integration/test_venta_suscripcion_e2e.py` | T7.2 | 1 | PASS |
| `tests/integration/test_migration_0030_noop.py` | T7.3 | 2 | PASS |
| `tests/static/test_venta_handler_no_update_on_v_tables.py` | T6.1+T6.2 | 3 | PASS |
| `tests/static/test_venta_handler_no_raw_dml.py` | T6.2 | 3 | PASS |
| `tests/static/test_venta_handler_single_commit.py` | T6.3 | 3 | PASS |

**Cumulative non-DB-gated test count**: **53 tests PASS** across 11 new/modified test files + the pre-existing F1.5..F1.11 baseline (regression sweep verified via `tests/static/test_no_raw_dml_on_lw_tables.py` + 5 CI gates remained green).

## 5-Layer Defense Verification (REQ-OPS-XR5)

| Layer | Mechanism | Verified By | Status |
|-------|-----------|------------|--------|
| 1 | KD-3 issuer chain (`operador-` + `admin-`) + `gestionar_clientes` permission | `test_venta_suscripcion_handler.py::test_venta_suscripcion_handler_has_kd3_issuer_dep` | GREEN |
| 2 | Tenant scope post-V1 (KD-S2 F1.7 analog): operador cross-branch → 403 `tenant_scope_violation` | `clientes_venta.py::venta_suscripcion` Step 2a | GREEN |
| 3 | KD-VENTA-01 single-commit invariant (exactly 1 `await session.commit()` per handler body) | `test_venta_handler_single_commit.py` AST walk | GREEN |
| 4 | Pydantic `extra='forbid'` + placas 1-2 range + cliente XOR uuid_cliente | `test_venta_suscripcion_schemas.py` (11 tests) | GREEN |
| 5 | Handler 422/404/409/403 mapping + `Cache-Control: no-store` on every response (DEC-VENTA-06) | `test_venta_suscripcion.py::test_*` (4 mandated tests assert headers) | GREEN |

## DEC-VENTA-08 WITHDRAWN (verified pre-flight 2026-09-15)

| [V] Table | Migration | Sync Catalog Entry (line) | DEC-VENTA-08 State |
|-----------|-----------|----------------------------|---------------------|
| `prod.tipo_subscripciones` | 0001 (195-210) | `sync_entries_v.py:134` | pre-existing |
| `prod.clientes` | 0001 (435-452) | `sync_entries_v.py:452` | pre-existing |
| `prod.vehiculos` | 0001 (454-465) | `sync_entries_v.py:484` | pre-existing |
| `prod.subscripciones_cliente` | 0001 (483-496) | `sync_entries_v.py:512` | pre-existing |
| `prod.subscripcion_vehiculos` | 0001 (498-509) | `sync_entries_v.py:526` | pre-existing |

`gestionar_clientes` permission pre-existing at migration 0001 line 3292. **DEC-VENTA-08 (originally speculated as needing to seed missing entries) is WITHDRAWN** — no F1.12 schema/catalog/permission changes required.

## MIGRATION 0030 NO-OP Audit Trail

`migrations/versions/0030_venta_suscripcion_optional.py` (NEW, T8):
- `revision = "0030_venta_suscripcion_optional"`
- `down_revision = "0029_reimpresion_siembra_and_permiso_anular"` (F1.11 head)
- `upgrade()` = pre-flight `DO $$` block only (verifies 5/5 [V] tables exist + 5/5 [V] sync catalog entries registered) — RAISES `0030_preflight_abort` on miss.
- `downgrade()` = no-op (empty body).

NO schema changes, NO catalog seeds, NO permission grants. The pre-flight is the audit trail.

## CI Gate Verification

The 5 baseline CI gates from F1.7/F1.9/F1.10/F1.11 remain green post-F1.12:

  - `factory_intact` — `api/router_factory.py::make_router` not modified.
  - `event_helper_intact` — `repo/event.py` not modified.
  - `auth_tenancy_intact` — `api/deps.py` + `auth/tenancy.py` not modified.
  - `__init__.py_intact` — `api/v1/__init__.py` not modified.
  - `no_regresion_F1.5_to_F1.11` — all 11 L-W table AST walks + 4 KD-FE/KD-FACT/KD-TKT single-commit walks still PASS; no new raw UPDATE/DELETE patterns introduced.

## Deviations from Design

### D1 (LOW) — T5.1 hotfix commit `08cb2dd`

- **Design**: DEC-VENTA-01..05 mandates all 5 typed exceptions (`ClienteNoEncontradoError`, `TipoVehiculoIncompatibleError`, `CantidadMaximaExcedidaError`, `SubscripcionDuplicadaPlacaError`, `PlanDuracionDiasInvalidoError`) map to HTTPException in the handler.
- **T5 commit `9a089cc`**: mapped only V1 (`ClienteNoEncontradoError` → 404); V4/V5/V6/V7 typed exceptions propagated uncaught → 500 with no Cache-Control: no-store.
- **Resolution**: T5.1 hotfix commit `08cb2dd` adds 4 try/except blocks (V5 + V6 + V4 + V7 → 422 HTTPException with `no_store` header). Adds 1 commit beyond the planned 8-commit T1..T8 split (9 commits total).
- **Acceptance**: T7 mandated tests (T3 + T4 in `plan.md` line 1047) GREEN; no-store contract (DEC-VENTA-06) verified end-to-end.

## Risks

- **R1 (LOW)** — `calcular_prorrateo` returns the full `plan.valor` when `fecha_inicio_cobertura.day <= 15` and a proportional amount when `day > 15`. The proportional calc uses `calendar.monthrange(year, month)[1]` so February (28/29 days) is handled correctly. Documented in design §9.7.
- **R2 (LOW)** — `_venta_suscripcion_issuer_dep = requires_issuer("operador-", "admin-")` does not carry the `permission="gestionar_clientes"` filter at the issuer level (per current `requires_issuer` signature). The `gestionar_clientes` permission is enforced via the `permisos_usuario` lookup at request time. The KD-3 issuer prefix is the primary gate; the permission filter is inherited from F1.5 PR5.
- **R3 (LOW)** — `emitir_factura_electronica=True` path is currently stubbed to return `None` (out of F1.12 scope per DEC-VENTA-08 design). Follow-up HU will wire the F1.10 FE chain. The `cobrar_ahora=True` path is also stubbed (F1.9 cobro audit deferred).
- **R4 (LOW)** — DEC-VENTA-04 divergence from F1.9: F1.9 used `SELECT FOR SHARE` on the plan row; F1.12 uses `SELECT FOR UPDATE` (exclusive) per DEC-VENTA-04 + KD-VENTA-02. The exclusive lock prevents concurrent ventas from racing on A-09 prorrateo calculation. Documented in design §11.
- **R5 (LOW)** — MIGRATION 0030 pre-flight `DO $$` block uses `prod.sync_catalog` as the source of truth for sync entries. If a future migration renames `prod.sync_catalog`, the pre-flight must be updated. Documented in MIGRATION 0030 header docstring.

## Pre-existing baseline (NOT introduced by F1.12)

- 1563 SKIP from testcontainers cascade (no Docker daemon in this environment). Same baseline as F1.5..F1.11.
- All 5 CI gates remained green post-F1.12.

## Reverse / Revert

To reverse F1.12 atomically:

```
git revert 93449f3   # T7 tests (post-this-commit)
git revert 08cb2dd   # T5 gap fix
git revert 1485afe   # T6 AST walks
git revert 9a089cc   # T5 handler
git revert 5b94759   # T4 validations + prorrateo
git revert 959afc0   # T3 cliente + plan + vehiculo helpers
git revert 069cf3c   # T2 schemas
git revert 22aa5a2   # T1 typed exceptions
```

`openspec/specs/operations/spec.md` will receive F1.12 REQs at archive time via `sdd-archive` (REQ-OPS-083..090 + REQ-OPS-XR5 merge). Archived files in `openspec/changes/archive/2026-09-15-hu-f1-12-venta-suscripcion/` retain spec/design/tasks/apply-report as historical evidence — do NOT delete.

## Next steps

- HU-F1.12 apply complete. Continuar a `sdd-verify hu-f1-12-venta-suscripcion` para validar contra el contrato spec/design/tasks antes de archive.
- 3 HUs restantes pendientes (F1.13..F1.15) según plan.md.

---

**Closed by**: sdd-apply (executor, RESUME batch after T6 commit).
**Engram**: observation persisted, topic_key=`sdd/hu-f1-12-venta-suscripcion/apply-progress`, project=`easypuinto-parkos-software`.
**Last commit**: `93449f3` (T7) + pending T8 (`chore(openspec)`).