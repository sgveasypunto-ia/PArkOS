# Foreign Key Naming Convention — shared across all PRDs

> Canonical reference for how FK columns are named in the AUDIT-FIRST model
> and what each PRD must document in its `## FK Map` section.

## Naming Pattern

| Column form | Role | Notes |
|---|---|---|
| `uuid` (no suffix) | Primary Key | Server-generated via `gen_random_uuid()` from `pgcrypto`. Always NOT NULL. UNIQUE. |
| `uuid_<suffixed>` (e.g., `uuid_sucursal`, `uuid_usuario`) | Foreign Key to `prod.<suffix_singular>.uuid` | Always references another table's PK by UUID. Cardinality + ON DELETE behavior documented per PRD. |
| `uuid_<compound>` (e.g., `uuid_factura_electronica`, `uuid_subscripcion_cliente`) | Foreign Key to `prod.<compound_table>.uuid` | Same rule; the suffix is the singular form of the target table name. |
| `uuid_padre` (in workflow tables: `anulaciones`, `reclamos`, `alerta`, `reimpresion_ticket`) | Self-reference FK to the SAME table's `uuid` | Workflow chain link — see `_shared/workflow-chains.md` (TBD) for chain semantics. |
| `uuid_referencia` (in `log_transaccional`) | Polymorphic FK | Application-level validation; NO DB FK constraint. Used to point to the originating event for derived logs. |
| `uuid_reclamable` + `tipo_reclamable` (in `reclamos`) | Polymorphic FK | `tipo_reclamable ∈ {ingreso, salida, factura, subscripcion}`; `uuid_reclamable` references the chosen table. Application-level validation; NO DB FK constraint. |

## Cardinality Notation

Each PRD's `## FK Map` lists incoming and outgoing FKs with Mermaid cardinality notation:

| Symbol | Meaning |
|---|---|
| `||--||` | exactly one to exactly one |
| `||--o{` | exactly one to zero-or-many |
| `||--|{` | exactly one to one-or-many |
| `}o--o{` | zero-or-many to zero-or-many |
| `}o--||` | zero-or-many to exactly one |

## ON DELETE / ON UPDATE Rules (AUDIT-FIRST defaults)

| Enforcement | FK behavior | Rationale |
|---|---|---|
| `[V]` projection | `ON DELETE RESTRICT` + `ON UPDATE CASCADE` | Delete = archive (vigente_hasta=NOW()) for the parent row, never cascade-delete child rows. UUID update allowed (rare; if a row's PK is corrected, propagate). |
| `[L-E]` event | `ON DELETE RESTRICT` + `ON UPDATE CASCADE` | Append-only; parent can't be deleted. UUID update allowed. |
| `[L-W]` workflow | `ON DELETE RESTRICT` + `ON UPDATE CASCADE` | Workflow chains can't be broken by parent deletion. UUID update allowed. |
| `[L-S]` session | `ON DELETE RESTRICT` + `ON UPDATE CASCADE` | Audit trail; parent can't be deleted. UUID update allowed. |
| `[A]` source-of-truth | `ON DELETE RESTRICT` + `ON UPDATE CASCADE` | Append-only; parent can't be deleted. UUID update allowed. |

**Special case**: `sync_queue`, `sync_log`, `sync_conflict` use `ON DELETE CASCADE` from `sucursal` because these are operational state, not historical records; if a branch is decommissioned, the queue dies with it.

## CodeGraph Verification (initial pass before code lands)

For each PRD's FK Map, run:

```bash
# Find all FKs referencing this table
codegraph query --name <TableName> --direction incoming
# Find all FKs from this table
codegraph query --name <TableName> --direction outgoing
```

After `codegraph init` runs (post-F1), the CodeGraph section in each PRD can be auto-populated from the SQLAlchemy model relationships.

## Cross-cutting Checks

When two PRDs have overlapping FK declarations:

1. Both must declare the same cardinality (1:N vs N:1).
2. Both must declare the same ON DELETE behavior.
3. If either is wrong, fix BOTH PRDs and the migration.
4. The `.mmd` is the source of truth; PRDs are derived from it.