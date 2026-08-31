# SOLID Atomic Principles — applied per PRD

> Each PRD references this doc for the S/O/L/I/D breakdown and adds only
> table-specific notes.

## S — Single Responsibility

- Each table represents ONE bounded concept. The schema's columns capture only the data attributes of that concept.
- The table's `uuid` PK + audit columns + sync columns are part of the contract, not behavior.
- No triggers that mutate this table's own columns. Triggers MAY exist for cross-table concerns (e.g., `[L-S]` session guard that logs to `log_transaccional`), but they don't change this table's data.

## O — Open/Closed

- Adding columns requires a migration (closed for modification of existing rows, open for extension via new column + migration).
- Adding FK relations to other tables requires a migration.
- Adding indexes for performance is allowed without changing the API contract.
- The table's column types are NOT expected to evolve in incompatible ways (e.g., `string` →`int`); if such evolution is needed, write a multi-migration rollout.

## L — Liskov Substitution

- Applies to "subclasses" of the concept. E.g., for `usuarios`: admin users and operador users MUST satisfy the same column invariants (`email` NOT NULL, `password_hash` NOT NULL, etc.). Role-specific behavior lives in the API layer, not in different schemas.
- FK targets must accept the UUID space uniformly (no table-typed UUIDs).

## I — Interface Segregation

- API endpoints that touch this table MUST be specific to the concept. E.g., `POST /usuarios` for create, `GET /usuarios/{uuid}` for read — NOT a "god endpoint" handling users + roles + permissions.
- Schemas (Pydantic v2 / Zod) MUST be split per use case: `UsuarioCreate`, `UsuarioRead`, `UsuarioUpdate`, `UsuarioAdminRead` (with permissions), etc. NOT one monolithic `Usuario` schema with every field.

## D — Dependency Inversion

- API routers depend on `parkos_core.models.<table>.Model` (SQLAlchemy declarative), not raw SQL strings.
- Sync workers depend on `parkos_core.sync.queue_processor` abstractions, not raw queries.
- DI: SQLAlchemy `AsyncSession` injected via `Depends(get_session)` FastAPI dependency.
- Pydantic schemas depend on the SQLAlchemy model via `model_validate()`, not the other way around.

## Atomic Operations

Atomic at the DB level (single statement OR explicit transaction):

| Operation | Atomicity rule |
|---|---|
| INSERT | Always atomic. For idempotent sync: `INSERT ... ON CONFLICT DO NOTHING`. |
| UPDATE on `[V]` | Wrapped in TX + concurrent `log_transaccional` insert in same TX (mandatory per `[V]` audit). |
| UPDATE on `[L-S]` state fields | Wrapped in TX + concurrent `log_transaccional` insert in same TX (mandatory per `[L-S]` guard). |
| UPDATE on `[L-E|L-W|A]` | **Rejected** by REVOKE on `rol_app` + trigger raises `AUDIT_FIRST_INMUTABLE`. |
| DELETE on `[V]` | NOT allowed. Use archive (new row with `vigente_hasta=NOW()`). |
| DELETE on `[L-E|L-W|L-S|A]` | **Rejected** by REVOKE on `rol_app` + trigger. |
| Hash chain extension (`log_transaccional`, `revocacion_factura`) | MUST verify `hash_anterior == previous.hash_actual` per `uuid_sucursal` BEFORE INSERT. |

## Implementation Discipline

- **No "fat services"**: each domain operation = one function per layer (router → service → repository). No business logic in the router; no SQL in the service.
- **No "smart triggers"**: triggers do one thing (e.g., `reject_mutation` only). Multi-step logic lives in Python.
- **No "magic middleware"**: tenancy, auth, logging are explicit decorators/dependencies, not implicit.
- **No "implicit UUIDs"**: every endpoint accepts/returns UUIDs as strings, never raw bytes; no auto-incrementing integers; no natural keys in URLs.