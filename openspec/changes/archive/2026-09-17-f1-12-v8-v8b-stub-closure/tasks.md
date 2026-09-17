# Tasks: F1.12 V8/V8b STUB closure

> **Change**: `2026-09-17-f1-12-v8-v8b-stub-closure`
> **Phase**: tasks (sdd-tasks)

## Atomic tasks

### T1 — MIGRATION 0037 + ORM column
- Create `backend/packages/parkos_core/migrations/versions/0037_add_uuid_subscripcion_cliente_to_facturas.py` (idempotent: `ADD COLUMN IF NOT EXISTS` + DO block for FK)
- Add `uuid_subscripcion_cliente: Mapped[uuid_lib.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)` to `models/L_E/facturas.py`
- **Acceptance**: MIGRATION 0037 file exists, ORM column present, `git diff --stat` shows +10 LOC on facturas.py

### T2 — TenantContext.uuid_sesion extension
- Add `uuid_sesion: uuid_lib.UUID | None = None` field to `TenantContext` dataclass in `auth/tenancy.py`
- Update `get_tenant_ctx()` operador branch to read `claims.get('sesion')`; admin-/sync-agent- branches set `uuid_sesion=None`
- **Acceptance**: `git diff --stat` shows +25 LOC on tenancy.py, `uv run mypy --strict auth/tenancy.py` exits 0

### T3 — V8 cobro sub-chain in clientes_venta.py
- Wire Step 8a: voucher check → IVA gate → crear_factura_evento (with `uuid_subscripcion_cliente`) → crear_factura_detalle_bulk → crear_factura_impuesto_iva → crear_factura_pago
- Update response: `monto_prorrateado` set when `cobrar_ahora AND monto_proporcional is not None`
- **Acceptance**: `uv run mypy --strict` shows same 5 pre-existing errors (no new); Step 8a block executes when `cobrar_ahora=True`

### T4 — V8b FE sub-chain in clientes_venta.py
- Wire Step 8b: buscar_resolucion_vigente_por_sucursal → assign_consecutivo → crear_factura_electronica_inicial → crear_envio_dian_inicial
- Handle: 404 resolucion_no_encontrada, 409 numeracion_agotada, 409 resolucion_sin_prefijo, 409 factura_electronica_ya_existe
- **Acceptance**: Step 8b block executes when `emitir_factura_electronica=True AND uuid_factura is not None`

### T5 — Unit tests for V8/V8b
- Add `test_venta_suscripcion_voucher_requerido_datafono_sin_referencia` → 400 voucher_requerido
- Add `test_venta_suscripcion_v8_cobro_subchain_calls_helpers_when_cobrar_ahora` → all 4 helpers called + `uuid_subscripcion_cliente` propagated
- **Acceptance**: `uv run pytest tests/unit/test_venta_suscripcion_handler.py -v` shows both tests PASS

### T6 — Verify + archive
- Run G1-G9 from `design.md` §Verification plan
- Author `verify-report.md` with gate matrix (PASS / SKIPPED-env / FAIL)
- Author `archive-report.md` with closure manifest
- Mechanical move: `mv` source folder → `openspec/changes/archive/2026-09-17-f1-12-v8-v8b-stub-closure/` with snapshot+diff-r
- **Acceptance**: archive folder contains 6 SDD artifacts; `git status --short` shows no orphan `2026-09-17-f1-12-v8-v8b-stub-closure/` in untracked location

### T7 — Commit + merge to dev + push
- `git add` the 5 new files + 4 modified files (no spec delta — REQ-OPS-090 unchanged)
- `git commit -m "feat(venta-suscripcion): wire V8 cobro + V8b FE sub-chains (F1.12 STUB closure)"`
- `git checkout dev`
- `git merge --no-ff feature/f1-12-v8-v8b-stub-closure`
- `git push origin dev`
- **Acceptance**: `git log --oneline -5 dev` shows the merge commit; `git status` clean

## Acceptance gates (from design.md)

| # | Gate | Status |
|---|---|---|
| G1 | MIGRATION 0037 applies | SKIPPED-env (no live DB) |
| G2 | Migration idempotency | SKIPPED-env |
| G3 | Migration downgrade + re-upgrade | SKIPPED-env |
| G4 | 50 unit tests pass | **PASS** |
| G5 | mypy strict handler (5 pre-existing, 0 new) | **PASS** |
| G6 | mypy strict tenancy (0 errors) | **PASS** |
| G7 | AST walk single-commit | **PASS** |
| G8 | Spec canon unchanged | **PASS** |
| G9 | Commit hygiene | **PASS** at T7 |

## Out of scope (per proposal.md)

- AST walk tests for V8 specifically
- Integration tests with Docker
- `ConsecutivoRangeExhaustedError` typed attributes refactor
- V8 FE dispatcher to DIAN provider (cloud-side, Fase 2 Parte II)