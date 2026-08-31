# Workflow Chain Convention — for `[L-W]` tables

> Canonical reference for how `uuid_padre` chains work in workflow tables
> (`anulaciones`, `reclamos`, `alerta`, `reimpresion_ticket`).

## Pattern

A workflow is a sequence of state transitions, each as a NEW row chained by
`uuid_padre` to the previous row. The state vigente is the LAST row in the
chain (highest `created_at` for the same logical workflow).

```
chain_root (uuid_padre = NULL)            → estado = 'solicitada'
  └─ transition_1 (uuid_padre = chain_root.uuid) → estado = 'aprobada'
       └─ transition_2 (uuid_padre = transition_1.uuid) → estado = 'ejecutada'
```

## Resolution query

To get the vigente state of a workflow:

```sql
WITH RECURSIVE chain AS (
  SELECT * FROM prod.<workflow_table> WHERE uuid = $1
  UNION ALL
  SELECT next.* FROM prod.<workflow_table> next
  JOIN chain c ON next.uuid_padre = c.uuid
)
SELECT * FROM chain ORDER BY created_at DESC LIMIT 1;
```

## Per-workflow rules

| Table | Chain states |
|---|---|
| `anulaciones` | `solicitada` → `aprobada` → `ejecutada` |
| `reclamos` | `abierto` → `en_revision` → (`resuelto` \| `rechazado`) |
| `alerta` | `abierta` → `en_revision` → `resuelta` |
| `reimpresion_ticket` | `cobrada` → `anulada` (only if cancelled) |

## Per-PRD documentation

Each workflow PRD's `## FK Map` includes:

```markdown
### Outgoing FKs
- `uuid_padre` (self-reference) → same table. Cardinality: 0..N per chain (1 root + N transitions).
  Workflow chain: <states list>.

### Incoming FKs
- <list per chain root referenced by other tables>
```

## CodeGraph Verification

```bash
codegraph query --name <workflow_table> --direction both
codegraph query --name <workflow_table> --filter self_reference=true
```