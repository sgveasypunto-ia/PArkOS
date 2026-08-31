# UUIDv4 Strategy — shared across all PRDs

> Canonical reference. Each PRD references this doc for the UUID column
> decisions and adds only the table-specific overrides (e.g., `numero_temporal`
> prefix for `facturas`).

## Primary Key Convention

Every table has a single `uuid` column:

```sql
CREATE TABLE prod.<table> (
  uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),  -- pgcrypto
  -- ... other columns ...
);
```

- **Type**: PostgreSQL native `UUID` (128-bit, RFC 4122 v4).
- **Generation**: server-side via `gen_random_uuid()` from the `pgcrypto` extension. Always server-side for safety; clients MAY pre-generate for optimistic UI, but the server uses the provided UUID (no client-generated override of the server default unless explicitly accepted).
- **Storage**: native UUID (16 bytes).
- **API representation**: canonical string `xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx` (RFC 4122). Always lowercase.
- **URL representation**: same canonical string; no URL-encoding needed.
- **Log representation**: `[first 8 chars uppercase]` in human logs; full UUID in JSON logs.
- **`numero_temporal` prefix** (for offline-first facturas only): `PRE-<8-char-uuid>` (e.g., `PRE-A3F9B12C`).

## Cross-system Propagation (sync)

When a row is created in one DB and synced to the other, the UUID travels verbatim.
The UUID is the idempotency key for the entire system — same UUID across cloud,
branch, sync_queue, sync_log, log_transaccional.

| Scenario | UUID source | UUID at destination |
|---|---|---|
| Branch operator creates row | Server-generated at branch | Travels to cloud (no re-gen) |
| Cloud admin creates row | Server-generated at cloud | Travels to branch (parametrization pull) |
| Re-delivery of sync message | Already on the row | UPSERT (idempotent) |
| Manual reseed from backup | Already on the row | UPSERT (idempotent) |

## Idempotency

- `sync_queue.datos.uuid_registro` MUST equal the source row's `uuid`.
- `sync_queue` uses `ON CONFLICT (uuid_registro, operacion) DO NOTHING` semantics at the receiver.
- Idempotency key = `(uuid_registro, operacion, uuid_sucursal_receiver)`.

## Foreign Keys

- All FKs use the same `uuid` value; never a slug, code, or natural key.
- Composite FKs not used (UUID alone is sufficient).
- Cascade rules per enforcement level:
  - `[V]` tables: NO cascade. Audit trails mean delete = archive (vigente_hasta=NOW()), and FK constraints are checked at INSERT time, never cascade.
  - `[L-E|L-W|L-S|A]` tables: NO cascade. Rows are append-only; deletion not allowed.

## Uniqueness Across the System

- UUID collision is statistically impossible (122 bits of randomness). Defensive check: if a duplicate UUID appears, the INSERT/UPSERT must fail loudly.
- UUIDs are NOT namespaced by `uuid_sucursal`. The same UUID space is used across all branches and cloud. This makes cross-branch references trivial and avoids UUID duplication.
- `vigente_desde`/`vigente_hasta` (on `[V]` tables) handle the "multiple versions of the same logical entity over time" pattern without needing separate UUID namespaces.

## Format in Different Surfaces

| Surface | Format | Example |
|---|---|---|
| PostgreSQL column | UUID native | `0xa3f9b12c-...` |
| JSON API response | String lowercase | `"uuid": "a3f9b12c-3456-4789-9abc-def012345678"` |
| URL path | String lowercase, URL-safe | `/api/v1/facturas/a3f9b12c-3456-4789-9abc-def012345678` |
| HTTP header (`X-Resource-Id`) | String lowercase | `X-Resource-Id: a3f9b12c-3456-4789-9abc-def012345678` |
| Structured log | Full | `"uuid": "a3f9b12c-3456-4789-9abc-def012345678"` |
| Human log | Truncated uppercase | `[A3F9B12C] created ingreso` |
| `numero_temporal` (offline-only facturas) | `PRE-<8 chars uppercase>` | `PRE-A3F9B12C` |
| `idempotency_key` (sync) | `f"{uuid_registro}:{operacion}"` | `a3f9b12c-...:INSERT` |

## Edge Cases

- **Client-supplied UUID**: API may accept a client-generated UUID for create endpoints, validated by regex `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` (RFC 4122 v4). If not supplied, server generates via `gen_random_uuid()`.
- **Pre-existing data migration**: when migrating from an external system, map each source row's natural key to a deterministic UUIDv4 (e.g., `uuid.uuid5(namespace, f"easypunto:{natural_key}")`). Document the namespace per migration.
- **Tampering**: if a UUID is altered in transit (TLS breach + active MITM), the receiver's UNIQUE constraint catches it; the sync message is rejected.

## Libraries

- Python (backend): `uuid.uuid4()` (stdlib) + SQLAlchemy 2.0 native `UUID` type.
- Python (sync): `uuid` field in Pydantic v2 `BaseModel`.
- TypeScript (frontend): `crypto.randomUUID()` (Web Crypto API) — never use Math.random or hand-rolled UUIDs.
- PostgreSQL: `gen_random_uuid()` from `pgcrypto` extension (already enabled in `infra/postgres/init/02_extensions.sql`).