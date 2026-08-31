# Planning PRDs — easypunto_parkos

> 4 Meta-PRDs (cross-cutting concerns) + 45 per-table PRDs (one per table in the
> AUDIT-FIRST data model). Each PRD identifies: UUIDv4 handling, SOLID atomic
> breakdown, FK map, CodeGraph dependencies, and layer-by-layer impact across
> the system.

#### Structure

```
openspec/planning/prds/
├── README.md                   ← this file
├── _shared/                    ← 7 canonical docs cited by every PRD
│   ├── uuid-v4-strategy.md
│   ├── solid-principles.md
│   ├── codegraph-usage.md
│   ├── layer-impact-map.md
│   ├── fk-naming-convention.md
│   ├── workflow-chains.md
│   └── references.md
├── _meta/                      ← 5 Meta-PRDs (cross-cutting)
│   ├── 00_scaffold.md          ← Python monorepo + uv workspace
│   ├── 01_models.md            ← 45 SQLAlchemy models + mixins
│   ├── 02_jobs_queries.md      ← sync worker queries
│   ├── 03_apis_queries.md      ← API endpoint matrix
│   └── 04_use_case_generation_prompt.md  ← Executable prompt for use-case generation
└── NN_<table>.md               ← 45 per-table PRDs (one per table)
    ├── 01_log_transaccional.md
    ├── 02_revocacion_factura.md
    ├── 03_factura_electronica.md
    ├── 04_ingreso.md
    ├── 05_facturas.md
    ├── 06_sync_queue.md
    ├── 07..30 [V] projection
    ├── 31..37 [A] source-of-truth
    ├── 38..41 [L-W] workflow
    ├── 42..43 [L-S] session
    └── 44..45 [A] sync_log + sync_conflict
```

#### Build Order

1. **Meta-PRDs first** (in order):
   - `00_scaffold.md` (monorepo + tooling)
   - `01_models.md` (45 SQLAlchemy models)
   - `02_jobs_queries.md` (sync workers read/write tables)
   - `03_apis_queries.md` (API endpoints per table)
2. **Per-table PRDs second** (T01..T45), in any order; per-table PRDs cite the meta-PRDs.

#### PRD Format (canonical)

### Meta-PRDs (`_meta/`)

Each meta-PRD covers a cross-cutting concern (scaffold, models, jobs, APIs) that ALL 45 per-table PRDs depend on. Format: same 12 sections as per-table PRDs (Required References, Metadata, ..., Open Questions).

### Per-table PRDs (`NN_<table>.md`)

Each per-table PRD follows the same template. Sections in order:

1. **Required References** — cites all canonical files (data model, project context, testing capabilities, stack, roadmap, iteration plan, all 7 `_shared/` docs).
2. **Metadata** — table name, enforcement level, retention, lifecycle origin.
3. **UUIDv4 Handling** — concrete column-level decisions (references `_shared/uuid-v4-strategy.md`).
4. **SOLID Atomic Breakdown** — S/O/L/I/D applied to this specific entity.
5. **FK Map (incoming + outgoing)** — exhaustive list per `_shared/fk-naming-convention.md`.
6. **Atomic DB Operations** — exactly what INSERT/UPDATE/DELETE is allowed; what triggers fire; what REVOKE applies.
7. **CodeGraph Dependencies** — incoming FKs + outgoing FKs + code callers.
8. **Layer-by-Layer Impact** — see `_shared/layer-impact-map.md`; PRD specifies which layers this table actually touches.
9. **RED Tests** — failing tests that prove the contract holds BEFORE production code lands.
10. **Implementation Tasks** — sequenced list (RED → GREEN → REFACTOR) with verification commands.
11. **Risks** — at least 2, with mitigations.
12. **Open Questions** — anything blocking or needing ratification.

#### Conventions

- **Naming**: `NN_<table>.md` where `NN` is the order in the canonical table list.
- **Lifecycle tags**: `[V]` versioned, `[L-E]` event, `[L-W]` workflow, `[L-S]` session, `[A]` source-of-truth.
- **Origin**: which iteration (IT-X) first implements write logic. Schema lands in F1 for all tables.
- **Status**: `Draft` (initial), `Reviewed` (after user/cross-agent review), `Approved` (locked for implementation), `Implemented` (code landed).

#### When to Update

- After F1 lands and `0001_initial_schema.py` is real: run `codegraph init` then update each PRD's CodeGraph section.
- After each iteration (IT-X) lands: update the originating PRD to `Implemented`.
- After any model change in `modelo_datos_er.mmd`: re-derive the affected PRDs.

#### How to Read These

If you only have 5 minutes: read this README + `_shared/references.md` + `_meta/00_scaffold.md` + one per-table PRD.
If you want the full picture: read all `_shared/` docs + all 4 meta-PRDs + all 45 per-table PRDs in order.

#### References (always load)

Per `_shared/references.md`, every PRD cites these canonical files:

- **Data Model**: `E:\easypunto_parkos\modelo_datos_er.mmd`
- **Project Context**: `E:\easypunto_parkos\openspec\PROJECT_CONTEXT.md`
- **Testing Capabilities**: `E:\easypunto_parkos\openspec\TESTING_CAPABILITIES.md`
- **Stack / Conventions**: `E:\easypunto_parkos\AGENTS.md`
- **Roadmap**: `E:\easypunto_parkos\openspec\_meta\roadmap.md`
- **Iteration Plan**: `E:\easypunto_parkos\openspec\_meta\iteration-plan.md`
- **SDD Init context**: `sdd-bootstrap-monorepo-foundation/*`