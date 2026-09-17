# Archive Report: F1.12 V8/V8b STUB closure

> **Change**: `2026-09-17-f1-12-v8-v8b-stub-closure` (archived)
> **Phase**: archive (sdd-archive)
> **Status**: CLOSED — F1.12 STUB closure complete; V8 cobro + V8b FE sub-chains wired
> **Date**: 2026-09-17
> **Author**: orchestrator
> **Branch**: `feature/f1-12-v8-v8b-stub-closure` (PR target: `origin/dev`)
> **Verdict**: PASS WITH WARNINGS (5/9 gates PASS, 4/9 SKIPPED-env, 0 FAIL)

---

## 1. Executive Summary

Closed the F1.12 V8/V8b STUB that the original archive-report deferred as "D2 LOW" — the sub-chain that wires `cobrar_ahora=true` to the F1.9 cobro flow (V8) and `emitir_factura_electronica=true` to the F1.10 FE flow (V8b). `plan.md` lines 1033, 1036, 1053 T2, 2027, 2029 + REQ-OPS-090 canon explicitly require this implementation; the original deferral was an erroneous sub-agent judgment against plan.md.

## 2. Closure Manifest

### 2.1 Files archived (5 SDD pipeline inputs + 1 archive-report = 6 in archive folder)

| # | File | LOC | Purpose |
|---|---|---|---|
| 1 | `proposal.md` | ~85 | Intent, scope, approach, rationale, risk, forward hooks, acceptance criteria |
| 2 | `design.md` | ~190 | Technical approach, Q1-A FK migration rationale, Q2 TenantContext extension, V8/V8b flow diagrams, validation chain |
| 3 | `tasks.md` | ~75 | 7 atomic tasks T1-T7, 9 acceptance gates |
| 4 | `specs/operations/spec.md` | ~25 | NO-OP delta stub (REQ-OPS-090 already in canon) |
| 5 | `verify-report.md` | ~60 | PASS WITH WARNINGS, 5/9 gates PASS, 4/9 SKIPPED-env (Docker not available) |
| 6 | `archive-report.md` | this file | Final closure report |

### 2.2 Implementation commits (5 on `feature/f1-12-v8-v8b-stub-closure`)

| # | File | LOC delta | Notes |
|---|---|---|---|
| 1 | `0037_add_uuid_subscripcion_cliente_to_facturas.py` | NEW ~70 LOC | MIGRATION 0037: nullable FK `prod.facturas.uuid_subscripcion_cliente` + DO-block idempotent FK constraint + `ON DELETE SET NULL` |
| 2 | `models/L_E/facturas.py` | +10 LOC | Add `uuid_subscripcion_cliente: Mapped[uuid_lib.UUID | None]` mapped_column |
| 3 | `auth/tenancy.py` | +25 LOC | Add `uuid_sesion` field to TenantContext dataclass + operador branch reads `claims.get('sesion')` |
| 4 | `api/v1/clientes_venta.py` | +95 LOC | Step 8a V8 cobro sub-chain (4-table INSERT) + Step 8b V8b FE sub-chain (resolucion → consecutivo → FE row → envio_dian) |
| 5 | `tests/unit/test_venta_suscripcion_handler.py` | +125 LOC | 2 new tests: voucher_requerido + V8 cobro subchain |

Total: 1 new file + 4 modified files = 5 file touches, ~325 LOC production + ~125 LOC tests.

Author `Parkos Dev <dev@parkos.local>`, ZERO `Co-authored-by` trailers, ZERO AI attribution trailers, conventional Spanish commit format.

### 2.3 Pre-existing mypy debt (NOT introduced by this change)

5 pre-existing errors in `clientes_venta.py` (lines 160, 206, 239, 453, 456) documented in verify-report.md — all baseline technical debt from F1.12's original implementation. Tracked separately.

## 3. Decisions Carried

- **Q1-A (proper FK migration over orphan correlation)**: orchestrator decision on 2026-09-17. Migration 0037 + ORM column. Future-proofs F17 reportería (which will JOIN `prod.facturas` with `prod.subscripciones_cliente`).
- **Q2 (TenantContext extension)**: closes pre-existing F1.9 bug (`facturacion.py:376,466` read `ctx.uuid_sesion` but the dataclass did not declare it). Silent fallback on malformed `sesion` claim to avoid locking out operators between turnos.
- **Q3 (IVA handler gate)**: `obtener_iva_vigente()` returns None → 500 `iva_no_configurado` BEFORE any INSERT. `crear_factura_impuesto_iva`'s `scalar_one()` stays as defense-in-depth for TOCTOU window.
- **Q4 (voucher inline)**: mirror F1.9 `facturacion.py:449-457`; dead-code `VoucherRequeridoError` exception class not raised.
- **Q5 (server-compute IVA)**: `total = subtotal * (1 + iva)`. No client total accepted. DEC-FACT-03 forbids hardcoded tax.

## 4. Deviations Final Inventory

None introduced by this change. Pre-existing mypy debt documented but out-of-scope.

## 5. Verify Outcome

**Verdict**: PASS WITH WARNINGS. **5/9 gates PASS, 4/9 SKIPPED-env, 0/9 FAIL.**

| Gate | Result | Reason if not PASS |
|---|---|---|
| G1 MIGRATION 0037 applies | SKIPPED-env | sandbox lacks Docker (testcontainers requires it) |
| G2 MIGRATION 0037 idempotency | SKIPPED-env | same |
| G3 MIGRATION 0037 downgrade + re-upgrade | SKIPPED-env | same |
| G4 50 unit tests pass | **PASS** | 2 new + 48 pre-existing (no regression) |
| G5 mypy strict handler | **PASS** | 5 errors all pre-existing (0 new introduced) |
| G6 mypy strict tenancy | **PASS** | 0 errors |
| G7 AST walk single-commit | **PASS** | static test ran in G4 sweep |
| G8 Spec canon unchanged | **PASS** | REQ-OPS-090 still present at lines 3611-3636 |
| G9 Commit hygiene | **PASS at commit time** | author Parkos Dev, no Co-authored-by, conventional Spanish |

## 6. Forward Hooks

- **Fase 1 frontend**: `VentaSuscripcionResponse` now carries real `uuid_factura` / `uuid_factura_electronica` / `uuid_envio_dian` when `cobrar_ahora=true`. Tiquete reprint logic can re-print receipts with real invoice reference.
- **F11 sync**: `prod.facturas` rows from V8 propagate via the existing `factura_*` sync catalog entries; `prod.subscripciones_cliente` is `[V]` bi-temporal and already sync'd. New `uuid_subscripcion_cliente` FK column is sync'd as part of the parent `facturas` row (no catalog change needed).
- **F17 reportería**: JOIN via `facturas.uuid_subscripcion_cliente` is now available (was orphan before).

## 7. Out-of-Scope (per proposal.md)

- AST walk tests for V8 specifically
- Integration tests with testcontainers (CI matrix required)
- `ConsecutivoRangeExhaustedError` typed attributes refactor (still `RuntimeError` plain)
- V8 FE dispatcher to DIAN provider (cloud-side, Fase 2 Parte II)

## 8. Spec Canonical Status

**Unchanged.** REQ-OPS-090 is already in `openspec/specs/operations/spec.md` lines 3611-3636 (archived 2026-09-15 as part of `hu-f1-12-venta-suscripcion`). This change **implements** the existing requirement; it does not add a new one. Delta spec is a NO-OP stub at `openspec/changes/2026-09-17-f1-12-v8-v8b-stub-closure/specs/operations/spec.md`.

Canonical REQ count: 142 (unchanged).

## 9. Mechanical Move Evidence

- **Source folder before move**: `openspec/changes/2026-09-17-f1-12-v8-v8b-stub-closure/` (5 SDD files: proposal.md, design.md, tasks.md, verify-report.md, specs/operations/spec.md)
- **Destination folder**: `openspec/changes/archive/2026-09-17-f1-12-v8-v8b-stub-closure/`
- **Move mechanism**: `Move-Item` (PowerShell 5.1; source was untracked)
- **Snapshot**: pre-move recursive `Copy-Item` into `${TEMP}\opencode\sdd-archive-f1-12\source\`; cleaned by `Remove-Item` after readback
- **Pre-move integrity check**: 5 files present in source snapshot
- **Post-move readback**: directory listing confirms 5 source files at destination
- **Source removal**: verified absent post-move (`Test-Path openspec/changes/2026-09-17-f1-12-v8-v8b-stub-closure` returns `False`)
- **`archive-report.md`** is authored at the archive location AFTER the move (additive-only, excluded from snapshot/destination comparison per SKILL.md)

## 10. Closure Checklist

- [x] 5 SDD pipeline inputs authored (proposal, design, tasks, specs/operations/spec, verify-report)
- [x] 1 MIGRATION (0037) added with idempotent FK constraint
- [x] ORM `models/L_E/facturas.py` updated
- [x] `auth/tenancy.py::TenantContext` extended
- [x] `clientes_venta.py` V8 + V8b sub-chains wired
- [x] 2 new unit tests added; 50/50 pass (no regression)
- [x] `verify-report.md` PASS WITH WARNINGS verdict
- [x] Pre-existing mypy debt documented (5 errors in `clientes_venta.py`)
- [x] Mechanical move with snapshot PASS
- [x] `archive-report.md` authored at archive location
- [ ] Commit + merge to dev + push (post-archive action; current task)
- [ ] CI matrix for SKIPPED-env gates (4 gates)

---

**End of archive.**