# ADR 002 — ER canon grows from 49 → 51 entities (54 physical prod tables)

> **Status**: Accepted — **amended 2026-09-08 (ER-alignment correction pass)**
> **Deciders**: sdd-tasks for `sync-overhaul` (original); sdd-design for `sync-overhaul` (amendment)
> **Date**: 2026-09-08 (original) · amended 2026-09-08
> **Spec ref**: `specs/cutover-migration.md` REQ-CUT-010
> **Design ref**: `design.md` §2 Issue #2, §4 Data Model Changes
> **Proposal ref**: `proposal.md` **§6.5** (the single canonical set of numbers) and **§9.2 / §9.3**
> **Filename note**: the slug `002-50-table-canon.md` is **historical** and predates this
> amendment's arithmetic. The path is kept so existing references do not break; the canonical figure
> is the one in the title above. Do not derive a count from the filename.

## Amendment note (2026-09-08)

The original decision — grow the ER canon by adding `prod.sync_queue_lw_buffer` and
`prod.alert_types` — **stands unchanged**, and so does its rationale. What is corrected here is
arithmetic and internal consistency:

| Item | Original text | Amended |
|---|---|---|
| Title | "49 → 51 tables" | "49 → **51 entities** (54 physical prod tables)" — the ER count and the physical count are now named separately, because conflating them is what produced the contradiction |
| `check_table_counts.py` target | Rationale said 51; **"Tasks affected" said "the new 50-table count"** | **51** ER entities everywhere — the internal contradiction is removed |
| Physical table total | not stated | **54** = 51 ER + 3 non-ER operational |
| `%% [A]` blocks in the `.mmd` | ">= 14 (12 audit + 3 operational + 1 buffer + 1 alert_types)" — arithmetically wrong, the 3 operational tables are **not** ER entities and have no `%% [A]` block | **exactly 14** = 12 existing ER `[A]` + 2 new |
| Derived constants (REVOKE / trigger / partman totals) | restated inline, and immediately inconsistent with the ADR's own new partman parent | no longer restated — `check_table_counts.py` is the single source for them (see Validation) |
| Third new table | — | **confirmed: there is none.** See below. |

**`prod.sync_back_events` is confirmed absent from this ADR.** The task input asked whether this ADR
added it as a third new table. It never did — the original Decision named exactly two new tables, the
buffer and the registry. That table came from `design.md` §2 Issue #1, which **D1-rev deleted in
full** (no table, no migration, no ORM, no repo helper, no hook, no emit loop). Checked against
proposal §6.5 and §9.2: the two new operational `[A]` tables that remain are exactly
`prod.sync_queue_lw_buffer` and `prod.alert_types`, and `prod.sync_back_events` "is **not** in any of
these counts and must not appear in any migration, ORM module, catalog, ADR, or task". So the count
is 51, not 52, and no removal from this ADR was required — only the corrections tabulated above.

The buffer + `alert_types` reasoning below is unchanged and still load-bearing. Nothing is deleted.

## Context

The project canon in `AGENTS.md` §"Architectural Principles" declares a 49-table AUDIT-FIRST model,
mirrored in `modelo_datos_er.mmd` and verified by `openspec/scripts/check_table_counts.py` and
`openspec/scripts/check_schema_match.py`. The 49-entity ER count excludes 3 **non-ER** operational
`[A]` tables added by `create-49-table-apis`:

| Operational table | Source change | Status |
|---|---|---|
| `idempotency_keys` | `create-49-table-apis` PR7 | Live (DB + ORM). |
| `pairing_tokens` | `create-49-table-apis` PR8 | Live. |
| `revoked_sync_jwts` | `create-49-table-apis` PR8 | Live. |

These three are physical prod tables but not ER entities: they have no `%% [A]` block in the `.mmd`
and they are `LocalOnlyCatalog` entries with `role_required='both'`. Keeping the two counts distinct
— **ER entities** and **physical prod tables** — is what this amendment fixes, because the original
text used one number for both.

`sync-overhaul` adds **two new operational `[A]` tables**:

- **`prod.sync_queue_lw_buffer`** — the dependency buffer. Under D18 it is no longer `[L-W]`-only: it
  holds a row for **any** entry with a missing declared `depends_on` parent, so it keys on the parent
  generically (`tabla_padre`, `uuid_padre`). Access pattern: 24 h TTL, parent-keyed lookup, FIFO
  within parent, TTL sweep.
- **`prod.alert_types`** — a small registry holding the project's alert-type catalog, seeded
  idempotently on **both** cloud and branch (mirroring the `seed_catalogs.py` idempotent pattern).

## Decision

**The ER canon grows from 49 → 51 entities; the physical prod table count becomes 54.**

- `prod.sync_queue_lw_buffer` is the 50th ER entity (migration `0009_add_sync_queue_lw_buffer.py`).
- `prod.alert_types` is the 51st ER entity (migration `0010_add_alert_types.py`).
- `modelo_datos_er.mmd` gains **two** `%% [A]` blocks plus their relationship lines to `sucursal`,
  bringing it to **14** `%% [A]` blocks.
- `check_table_counts.py` and `check_schema_match.py` assert the **51**-entity canon.
- Physical total: **54** = 51 ER + 3 non-ER operational.

The full canonical set of numbers, which every artifact must state identically (proposal §6.5):

| Quantity | Value | Composition |
|---|---|---|
| ER entities today | **49** | 26 `[V]` + 3 `[L-E]` + 6 `[L-W]` + 2 `[L-S]` + 12 `[A]` |
| ER entities after this change | **51** | 49 + `sync_queue_lw_buffer` `[A]` + `alert_types` `[A]` |
| Non-ER operational tables | **3** | `idempotency_keys`, `pairing_tokens`, `revoked_sync_jwts` |
| **Physical prod tables after this change** | **54** | 51 ER + 3 non-ER |
| `len(SYNC_CATALOG)` | **46** | 26 `[V]` + 3 `[L-E]` + 6 `[L-W]` + 2 `[L-S]` + 9 `[A]` |
| `len(LOCAL_ONLY_CATALOG)` | **3** | the 3 non-ER operational tables |
| `len(OUT_OF_CATALOG)` | **5** | `sync_queue`, `sync_log`, `sync_conflict`, `sync_queue_lw_buffer`, `alert_types` |
| Catalog coverage | 46 + 3 + 5 = **54** | every physical prod table classified exactly once |

**Both new tables are out of catalog** (proposal §6.3): buffering the buffer is meaningless, and the
registry is deploy-seeded rather than replicated. They are two of the five names the
`check_catalog_drift.py` exemption list must carry — exactly five, no more.

**Views and indexes do not affect these counts.** `design.md` §4 adds design-owned migrations `0014`
(natural-key lookup indexes) and `0015` (derived read views). Neither creates a table, so the
51 / 54 canon is untouched and neither count script changes because of them.

## Rationale

1. **The buffer has different semantics from `sync_queue`.** Mixing dependency rows into `sync_queue`
   would conflate retry-on-backoff semantics (the outbox's job) with hold-until-parent-arrives
   semantics (the buffer's job). They need different indexes, TTL policies, and partition schedules.
   **Reinforced by the amendment**: D18 makes this the *single* escalation path — the buffer owns the
   wait, its TTL sweep owns the timeout, and `sync_queue` is never re-enqueued for a dependency wait.
   Fusing the two tables would have made that separation unexpressible.
2. **The buffer is now general, which strengthens the case for its own table.** Originally it served
   6 `[L-W]` self-chains. Under D18 it serves any entry with a mandatory-FK parent, in both
   directions, including the first-pairing `cloud_to_branch` backfill. A general mechanism embedded in
   the outbox would couple every table's dependency waiting to outbox drain behaviour.
3. **Single source of truth.** Discovering both tables via the ER + the schema verifier means a
   future change cannot silently drop either without breaking CI.
4. **`alert_types` must not replicate, and being out of catalog is what says so.** The discriminator
   is *who authors the values*. Operator-editable catalogs must replicate because a new value has to
   reach the branch without a deploy; `alert_types` members are referenced by identifier in Python
   source, so adding one is a code change that ships with a deploy anyway. Stating this rule
   explicitly keeps future tables from being classified by analogy to whichever table they
   superficially resemble.
5. **Precedent.** `create-49-table-apis` grew the physical footprint the same way (PR7
   `idempotency_keys`, PR8 `pairing_tokens` + `revoked_sync_jwts`). `sync-overhaul` follows it,
   adding both tables inside one change rather than shipping an interim release with a buffer but no
   registry — the buffer's TTL sweep raises `orphan_workflow_chain`, which the registry must already
   contain for `repo/alert_types.py::validate` to accept it.

## Alternatives considered

| Option | Tradeoff | Decision |
|---|---|---|
| Amend the ER to 51 entities / 54 physical tables (two dedicated `[A]` tables) | Single source of truth; discoverable via the existing schema verification; each table keeps a crisp purpose | **CHOSEN** |
| Ephemeral Redis queue for the buffer | New infra dependency, Redis persistence policy, cluster placement; breaks the "no new infra" constraint for the cutover; a lost buffer silently drops causally-ordered rows | Rejected |
| Reuse `sync_queue` with a `kind='lw_buffer'` column | Pollutes the operational outbox; the outbox expects fast drain while the buffer holds for 24 h; and it would force the two escalation paths D18 exists to unify back into one table | Rejected |
| Keep `tipo_alerta` as free-form `TEXT` and only document the pre-registered values | No migration, but nothing prevents a typo'd identifier from being persisted, and `AlertEmitter` would have no registry to validate against | Rejected |
| Rename the buffer to `prod.sync_dependency_buffer` now that it is general | Reads better, but the name is ratified in proposal §6.3 / §9.2 and in the exemption list that must carry exactly five names; a rename costs a migration plus three artifact edits for zero functional gain. Only the Python module is generalized (`motor/dependency_buffer.py`) | Rejected — see `design.md` §2 Issue #2 |

## Consequences

### Positive

- `sync_queue` keeps its focused purpose: drain fast, retry on backoff, only 4 whitelisted columns
  mutate.
- `prod.sync_queue_lw_buffer` gets its own `pg_partman` parent (`p_control := 'buffered_at'`,
  `p_interval := '1 day'`, `p_premake := 3`), scheduled independently of the outbox.
- The schema verifier covers both new tables the same way it covers `idempotency_keys`,
  `pairing_tokens`, and `revoked_sync_jwts`.
- `prod.alert_types` gives `repo/alert_types.py::validate` a registry to reject unknown identifiers
  against, which is what makes `orphan_workflow_chain`, `fe_provider_error`, and
  `fe_numbering_exhausted` safe to emit from code.

### Negative

- **Count scripts and the `.mmd` must be updated in the same change.** `check_table_counts.py`
  currently declares 49 total / 12 `[A]`. **This was the impassable gate in the prior pass**: no task
  edited `modelo_datos_er.mmd`, yet both scripts gate on it. The amendment makes the `.mmd` edit an
  explicit deliverable (PR10).
- **ER diagram review.** Every future ER reviewer must hold both new tables in the mental model, and
  must keep the ER-entity count (51) distinct from the physical count (54).
- **Two counts, not one.** Stating both is more to keep consistent, but conflating them is precisely
  what produced this ADR's original internal contradiction.
- ~~**D14 direction ratification.** Both new tables are `[A]` operational; they do NOT participate in
  the 26 `[V]` direction ratification series.~~ **Void** — D14-rev removes the ratification series
  entirely; direction is ratified in this change. Both tables remain out of catalog and carry no
  `direction`.

## Tasks affected

Task IDs are owned by `sdd-tasks`; the PR mapping below follows `design.md` §13 / proposal §10.

- **PR8** — `0009_add_sync_queue_lw_buffer.py` (table + REVOKE + `BEFORE UPDATE OR DELETE` trigger +
  partial indexes + `pg_partman` parent) and `0010_add_alert_types.py` (table + REVOKE + trigger +
  idempotent seed on both cloud and branch), plus `infra/scripts/seed_alert_types.py`.
- **PR8** — `motor/dependency_buffer.py`: buffer insert, bounded iterative drain keyed on
  `(tabla_padre, uuid_padre)`, TTL sweep emitting `alerta tipo_alerta='orphan_workflow_chain'`.
- **PR10** — edit `modelo_datos_er.mmd`: two new `%% [A]` entity blocks + their relationship lines to
  `sucursal`.
- **PR10** — update `openspec/scripts/check_table_counts.py` to the **51**-entity canon (was
  incorrectly recorded as "the new 50-table count") and re-run `check_schema_match.py` against the 54
  physical tables.
- **PR2** — `catalog/out_of_catalog.py` declares exactly the five exempt names, both new tables
  included.

## Validation

- `python openspec/scripts/check_table_counts.py` exits 0 against the **51**-entity canon. Its
  `CANONICAL` mapping is bumped from `total: 49` / `[A]: 12` to `total: 51` / `[A]: 14`, and its
  stale-pattern list gains guards so `49 tables` and `12 [A]` cannot reappear as canonical. The
  script is the **single source** for the derived per-class REVOKE / trigger / `pg_partman` totals;
  this ADR deliberately does not restate them, because restating derived constants in prose is what
  made the original version contradict itself.
- `python openspec/scripts/check_schema_match.py` exits 0 — full match between the amended `.mmd` and
  the **54** physical prod tables, with the 3 non-ER operational tables treated exactly as before.
- `git grep -c "%% \[A\]" modelo_datos_er.mmd` returns **14** (12 existing ER `[A]` + buffer +
  `alert_types`). The 3 non-ER operational tables are **not** counted here — they have no `%% [A]`
  block, which is what makes them non-ER.
- `uv run pytest backend/tests/migrations/test_sync_queue_lw_buffer_schema.py` — table, the
  `tabla_padre` / `uuid_padre` generic parent columns, REVOKE, immutable trigger, both indexes, and
  the `pg_partman` parent verified.
- `uv run pytest backend/tests/migrations/test_alert_types_schema.py` — table, REVOKE, trigger, and
  the idempotent seed verified, including that re-running the seed is a no-op and that every
  identifier is generic (no third-party vendor name).
- `python openspec/scripts/check_catalog_drift.py` exits 0 with `len(OUT_OF_CATALOG) == 5` and the
  exemption list containing exactly `sync_queue`, `sync_log`, `sync_conflict`,
  `sync_queue_lw_buffer`, `alert_types`.
- Repo-wide grep for `sync_back_events` and `sync_back_event` returns zero hits outside explicitly
  marked superseded-decision text (R21, gated in PR14).

## References

- `proposal.md` §6.5 — the canonical set of numbers; §6.3 — the five out-of-catalog names;
  §9.2 — migrations `0009`-`0013`; §9.3 — the required `.mmd` amendment and its 51 / 14 / 54
  assertions.
- `proposal.md` D1-rev — deletes `prod.sync_back_events` in full, which is why the canon is 51 and
  not 52; D6-rev — the "who authors the values" classification rule behind `alert_types`;
  D18 — the generalized buffer and the single escalation path; D14-rev — voids the direction
  ratification series.
- `design.md` §2 Issue #2, §4 — the amended table design and migration list.
- `create-49-table-apis` precedent: `tasks.md` T-PR7 (`idempotency_keys`) and T-PR8
  (`pairing_tokens` + `revoked_sync_jwts`).
- `AGENTS.md` §"Risk Registers" — `idempotency_keys` precedent acknowledged.
- ER-conformance review findings **A2** (three conflicting table counts), **A3** (no task edits the
  `.mmd`), **A4** (new tables missing from the exemption list) — all closed by this amendment.
