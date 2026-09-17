# Delta Spec: F1.12 V8/V8b STUB closure

> **Change**: `2026-09-17-f1-12-v8-v8b-stub-closure`
> **Capability**: operations
> **Type**: NO-OP delta stub (existing REQ already in canon)
> **Date**: 2026-09-17

## ADDED Requirements

**None.** REQ-OPS-090 is already in the canonical
`openspec/specs/operations/spec.md` (lines 3611-3636, archived 2026-09-15 as
part of `hu-f1-12-venta-suscripcion`). This change **implements** the existing
requirement; it does not add a new one.

Per `plan.md` line 1053 T2 verbatim: "cálculo de prorrateo si la venta ocurre
después del día 15 (adaptación A-09: el monto prorrateado se persiste en
`factura_detalle`, no en `subscripciones_cliente`)." The implementation gap that
the original archive-report marked as "D2 LOW deferred" is closed by this
change.

## Modified Capabilities

None. No existing REQ is modified.

## Out of Scope

- AST walk tests for V8 (current mock tests pin the contract; AST walk to land in a future quality refactor)
- Integration tests with testcontainers (CI matrix required)
- `ConsecutivoRangeExhaustedError` typed attributes refactor (still `RuntimeError` plain; F1.10 untouched)
- V8 FE dispatcher to DIAN provider (cloud-side, Fase 2 Parte II; this change stops at `factura_electronica` + `envio_dian` row creation)