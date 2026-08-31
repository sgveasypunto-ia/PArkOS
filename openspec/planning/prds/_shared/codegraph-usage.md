# CodeGraph Usage — per-PRD dependency review

> Each PRD's `## CodeGraph Dependencies` section is populated by querying
> CodeGraph. This doc explains how.

## One-time setup (after F1 lands)

```bash
# From the repo root
gentle-ai codegraph init --cwd .
# Wait for the indexer to finish (~5-10 minutes for 45 tables + models + routes)
codegraph status  # confirms index ready
```

The `.codegraph/` directory lives at the project root and is gitignored (per `AGENTS.md`).

## Per-PRD query

For each PRD, run:

```bash
# Outgoing references (this table → others)
codegraph_explore query="<TableName>" projectPath="E:\easypunto_parkos"
# Incoming references (others → this table)
codegraph callers <TableName>
```

Or use the CLI:

```bash
codegraph query --name <TableName> --direction both
codegraph impact --name <TableName>
```

The query returns:
- All FK relations from this table (outgoing).
- All FK relations to this table (incoming).
- All Python files that reference this table's model (callers/callees).
- All TypeScript files that reference this table's UUID in API calls.
- Blast radius: count of files that would change if this table's schema changes.

## What to write in each PRD

Each PRD has a `## CodeGraph Dependencies` section with two lists:

```markdown
### Outgoing references
- `prod.<other_table>.<column>` (FK) — references `<column>` of `<other_table>`. Impact: changes to `<other_table>` may require re-validation.

### Incoming references
- `prod.<other_table>.<column>` (FK to this table) — `<other_table>` references this table.
- Code callers (when code lands):
  - `backend/packages/api_admin/src/api_admin_main/routers/<router>.py` (admin endpoint)
  - `backend/packages/api_sucursal/src/api_sucursal_main/routers/<router>.py` (sucursal endpoint)
  - `backend/packages/job_sync_cloud/src/job_sync_cloud_main/__main__.py` (sync worker)
  - `apps/web_admin/src/routes/<page>.tsx` (admin UI)
  - `apps/web_sucursal/src/routes/<page>.tsx` (sucursal UI)
```

## Initial pass (before F1 lands)

Since `codegraph init` requires code, the initial PRDs document the **expected** CodeGraph dependencies based on the schema's FK declarations in `modelo_datos_er.mmd` + the system architecture. After F1 lands and `codegraph init` runs, update each PRD with the actual code references.

## Cross-reference check

When two PRDs claim conflicting relationships (e.g., one says `X → Y` but another says `Y → X`), resolve by re-reading `modelo_datos_er.mmd` and updating both PRDs.