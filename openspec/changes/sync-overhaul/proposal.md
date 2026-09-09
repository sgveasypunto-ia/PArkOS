# Proposal: `sync-overhaul`

> **Change**: `sync-overhaul`
> **Phase**: propose (sdd-propose) — **amended 2026-09-08 (ER-alignment correction pass)**
> **Status**: draft, ready for `sdd-spec` + `sdd-design` (both must re-read this amended file)
> **Preflight**: `pace=auto`, `artifact=hybrid` (OpenSpec + Engram), `delivery=auto-chain`,
> `chain=gitflow` (PRs → `dev`), `review_budget=800 lines/PR` (per
> `create-49-table-apis` precedent), `strict_tdd=true` from PR1.
> **Inputs**: `modelo_datos_er.mmd` (**canonical source of truth for every direction/scope
> decision in §6**), `exploration.md` (§1-§9), Engram `sdd/sync-overhaul/decisions` (#1408),
> Engram `sdd/sync-overhaul/explore` (#1406, #1407), AGENTS.md,
> `openspec/config.yaml`, `create-49-table-apis/proposal.md` (delivery pattern reference),
> plus the ER-conformance review of this change (4 critical / 6 high / 6 medium findings).

## 0. Amendment log — why this proposal was corrected

**Root cause of the original defect.** The first pass derived the `SyncCatalog`
direction and scope decisions from the `fn_enqueue_sync` trigger inventory
**already installed in the database**, not from `modelo_datos_er.mmd`. The
installed triggers are an artifact of incremental delivery; they are not a
policy statement. Reading them as policy produced four structural
contradictions with the canonical ER:

1. **Global catalogs never reached the branch.** 18 `[V]` tables were declared
   `never_propagated` and justified with a "boot snapshot" mechanism that exists
   in no requirement, task, or module. The ER says the opposite for `usuarios`
   ("se replica a sucursales para login offline"), `permisos` ("replica cloud a
   sucursales") and `sucursal` ("la réplica local de cada sede contiene solo sus
   filas **+ catálogos**"). This is the exact failure observed in the manual test
   at the start of the period: a vehicle type created in cloud admin never
   arrived at the branch.
2. **DIAN numbering was inverted.** D1 assumed cloud assigns a `numero_oficial`
   and the branch writes a `numero_temporal`, carried back by an invented
   `prod.sync_back_events` table. The ER states the electronic invoice is issued
   **at the branch with the branch's own resolution**, and the `consecutivo` is
   assigned in-branch inside that resolution's authorized range. No
   `numero_temporal` / `numero_oficial` / `preliminar` column exists anywhere in
   the ER.
3. **Cloud-only tables pointed the wrong way.** `envio_dian` and
   `validacion_evento` were declared `branch_to_cloud`; the ER marks both
   CLOUD-ONLY.
4. **No FK application order existed for branch→cloud.** The only wait mechanism
   was a buffer keyed on the `[L-W]` self-chain `uuid_padre`. Nine parent/child
   FK pairs on the invoicing path had no protection at all, and the legacy
   `priority` value actively ordered children ahead of parents.

**What this amendment does.** Every direction and scope decision in §6 is now
derived from the ER class tag plus the entity description, with the FK graph
(92 declared relationships) as the ordering constraint. Reversed decisions are
kept visible with a `Superseded` marker and the reversal rationale — nothing is
deleted silently. Three cascading consequences are resolved here rather than
deferred, because the direction reversal makes them incoherent otherwise: the
`PIIRedactor` hook contract (§8), the `PlateChangeCascade` target table (§8),
and the cloud-side identity reconciliation rule for `clientes` / `vehiculos`
(D17).

**Amendment rule for downstream phases.** `sdd-spec`, `sdd-design`, and
`sdd-tasks` amend their existing artifacts in place. No parallel v2 files. Where
this proposal reverses a decision, the downstream artifact keeps the old text
with a `Superseded — see D-xx-rev` marker.

## 1. Why

The current sync engine has four structural defects that grow linearly with the
table count (today: **54 prod tables** after this change — see §6.5 — of which
30 are replicated via trigger + JSONB + per-class hardcoded `frozenset` + stub
seq lookup):

1. **Opaque payload** — `fn_enqueue_sync` ships the whole row as
   `to_jsonb(NEW)` inside `sync_queue.datos`. The branch-side applier must
   re-parse JSON, filter out server-controlled columns, and still cannot
   recover the per-row `seq` without a second JSON parse on every conflict.
2. **Stub conflict detection for [V]** — `ConflictResolver._read_local_seq`
   returns `None`, so every `[V]` conflict silently resolves to `APPLIED`.
   All 26 `[V]` tables are exposed to this defect, and after this amendment
   **all 26 actually carry traffic**, so the defect stops being latent.
3. **Global catalogs and master data never reach the branch** (the corrected
   framing of the original defect #4). 18 `[V]` tables have no `fn_enqueue_sync`
   trigger and no declared sync policy. The visible consequences:
   - an admin-created `tipos_vehiculo` / `impuestos` / `tarifas_sucursal`
     dependency never lands at the branch, so the branch cannot price or
     classify an entry offline;
   - branch→cloud rows carry FKs to catalog **versions** the branch never
     received (`factura_impuestos→impuestos`, `factura_otros_cobros→otros_cobros`,
     `reimpresion_ticket→costos_servicios`, `ingreso→tipos_vehiculo`,
     `arqueo→tipo_arqueo`, `factura_electronica→clientes`,
     `log_transaccional→usuarios`);
   - offline login has no local `usuarios` / `permisos` / `permisos_usuario`
     rows to authenticate and authorize against;
   - three of the four `[V]` hooks (`PIIRedactor`, `PlateChangeCascade`,
     `SubscriptionLifecycle`) hang off `never_propagated` tables, so the motor
     would never invoke them — the whole hook PR would ship as dead code.
4. **The DIAN return path was invented instead of modeled.** The dispatcher
   inserts `operacion='sync_back_event'` rows into the operational outbox
   (`dian/cloud/dispatcher.py` ~line 496). Under the ER the return channel
   already exists: `envio_dian` is the cloud-only record of the provider
   exchange, and it carries `cufe` / `estado` back to the branch as an ordinary
   `cloud_to_branch` catalog entry. The special-case path, its table, its hook,
   and its UI rule are all removable.

The proposed hybrid **declarative `SyncCatalog` + reusable `SyncMotor` +
per-table HOOKS** architecture replaces the opaque pipeline with a typed,
table-aware, hook-extensible, CI-verifiable surface whose direction and scope
are derived from the ER and asserted in CI against it.

## 2. Decision Summary

### 2.1 Ratified (D1-D16, from Engram #1408) — with amendment markers

| # | Decision | Amendment status |
|---|---|---|
| **D1** | ~~DIAN `sync_back_event` — branch receives `numero_oficial`; reprint only **manual**. `reimpresion_ticket` gets new `origen: manual\|auto` field.~~ | **Superseded — see D1-rev** |
| **D2** | `[V]` bi-temporal generic apply + **hooks** for `clientes` (PII), `vehiculos` (plate changes), `subscripcion_vehiculos` (lifecycle). | **Amended** — the three tables are now actually replicated (D8-rev), so the hooks become live. Two hook contracts change: see §8 and D17. |
| **D3** | Cutover order **cloud-first** (branches after). | Unchanged |
| **D4** | Fix `_read_local_seq` stub bug **inside this change** (closes the silent-APPLY defect for 26 `[V]` tables). | Unchanged — now mandatory rather than opportunistic, since all 26 `[V]` tables carry traffic. |
| **D5** | Per-table `direction: cloud_to_branch \| branch_to_cloud \| bidirectional` in `SyncCatalog`. | **Amended — see D5-rev** (the field stays; its derivation changes) |
| **D6** | ~~`SyncCatalog` (47) + `LocalOnlyCatalog` (5): `factura_electronica` + `revocacion_factura` (DIAN-only) + `idempotency_keys` + `pairing_tokens` + `revoked_sync_jwts`.~~ | **Superseded — see D6-rev** |
| **D7** | `[L-W]` **append + `validate_parent_chain` hook** (parent must exist locally OR in same batch; missing → `sync_queue` retry with `parent_missing` flag). | **Amended — generalized by D18** (any declared parent, not only the `[L-W]` self-chain) |
| **D8** | ~~18 `[V]` tables without triggers → `sync_strategy: never_propagated` with per-table justification. NO new triggers in this change.~~ | **Superseded — see D8-rev** |
| **D9** | pytest **from PR1** (pytest + pytest-asyncio + testcontainers + coverage gate). `strict_tdd: true` activates from PR1. | Unchanged |
| **D10** | Observability = (a) Prometheus counters per table (`sync_apply_total{status,tabla,uuid_sucursal}`), (b) structured logs with `uuid_sucursal`+`tabla`, (c) Grafana alerts: backlog > N, conflict rate > X%, chain verifier fail. | **Amended** — add a `sync_dependency_wait` gauge and a `catalog_backfill_complete` per-branch gauge (D18, R3-rev) |
| **D11** | Cutover compat = **dual protocol grace period** (suggested 14 days). Cloud serves old + new endpoints; branch auto-detects. | Unchanged |
| **D12** | Rollback = `PARKOS_SYNC_ENGINE=legacy` kill switch + `sync_queue WHERE estado='pendiente' = 0` drain + reverse migration script. | Unchanged |
| **D13** | Cloud cutover **staged por servicio**: (1) Catalog skeleton, (2) `api_admin` reads catalog but applies legacy, (3) DIAN dispatcher, (4) `job_sync_cloud`, (5) cleanup legacy triggers. | **Amended** — stage 2's gate criteria change with D1-rev; see §11 |
| **D14** | ~~Per-table `direction` ratification: propose proposes defaults for 26 `[V]`; separate PRs ratify iteratively. This change ships the catalog skeleton with `direction: bidirectional` placeholder + `direction_proposed: <value>` comment per `[V]` entry.~~ | **Superseded — see D14-rev** |
| **D15** | `[L-W]` out-of-order events = **dependency buffer** keyed by `uuid_padre`. Worker holds rows until parent arrives (TTL 24h, then alert). Strict causal order, no best-effort apply. | **Amended — generalized by D18** (buffer keyed by any declared missing parent; one escalation path) |
| **D16** | Network partition = branch **buffers locally + UI degraded mode** (banner amarillo, hides features dependent on cloud writes). Local `[V]/[A]` writes continue. | **Amended** — the degraded feature list shrinks: `reimpresion_ticket` and `factura_electronica` emission no longer depend on a cloud round-trip (D1-rev). What degrades is DIAN *acknowledgement* visibility only. |

### 2.2 Reversed and re-derived decisions

#### D1-rev — DIAN numbering is branch-local (supersedes D1)

**Decision.** The branch emits `factura_electronica` **locally**, using **its own**
`resolucion_facturacion` row (which it already holds — `cloud_to_branch`,
`single_branch`), and assigns `consecutivo` from that resolution's authorized
`rango_desde`/`rango_hasta`. The cloud validates the resolution and range on
receipt, then forwards the document to the DIAN provider and records the
exchange in `envio_dian` (cloud-only). The provider outcome (`cufe`, `estado`)
reaches the branch through the ordinary `envio_dian` `cloud_to_branch` catalog
entry.

**Rationale.** This is what the ER already models:
`factura_electronica` is `[L-E]` "se emite EN sucursal con SU resolución y cloud
la envía (`envio_dian`)"; `consecutivo` is "asignado en sucursal dentro del rango
de su resolución"; UK01 is `(uuid_resolucion_facturacion, consecutivo)`, which is
globally unique *because* the resolution is per-branch — no central allocator is
required for uniqueness. `resolucion_facturacion` carries `rango_desde` /
`rango_hasta` and, per the 4NF pass, no `consecutivo_actual` column at all.
The old D1 required a central allocator that the schema cannot express, and it
made offline invoicing impossible: a branch without connectivity could not
number a document, which is precisely the scenario the offline-first
architecture exists to serve.

**Consequences to apply in every downstream artifact.** Drop, in full:
- the `prod.sync_back_events` table and its migration;
- the `SyncBackEventEmitter` hook and its registration;
- the dispatcher's `operacion='sync_back_event'` emit loop;
- the `sync_back_event: bool` field on `SyncCatalogEntry`;
- the `numero_temporal` / `numero_oficial` / `preliminar` vocabulary;
- the UI rule "reprint blocked until sync-back" and the `preliminar` badge;
- the `reimpresion_ticket.origen: manual|auto` column proposed by D1 (it existed
  only to distinguish an auto-reprint triggered by the sync-back arrival).

**Side effect — a cross-direction FK hazard disappears.** The review flagged
`factura_electronica` (`branch_to_cloud`) → `resolucion_facturacion`
(`cloud_to_branch`, bi-temporal) as unprotected: each `close_and_insert`
produces a new version `uuid`, so the cloud could receive an FK to a version it
did not know. Under D1-rev the resolution version the branch emits against
**originated in the cloud** and, because `[V]` history is insert-only, the cloud
still holds that exact version row. The FK always resolves. No special case is
needed.

**Canon correction required.** `AGENTS.md` still carries the superseded rule —
see §9.5 for the exact required edits.

#### D5-rev — direction is derived from the ER, not from installed triggers (amends D5)

**Decision.** `direction` and `broadcast_policy` are derived from the ER entity's
class tag and description, with the following rules, and asserted in CI against
`modelo_datos_er.mmd`:

| ER signal | `direction` | `broadcast_policy` |
|---|---|---|
| `[V]` without `uuid_sucursal` | `cloud_to_branch` | `all_branches` |
| `[V]` with `uuid_sucursal` | `cloud_to_branch` | `single_branch` |
| `[V]` with nullable `uuid_sucursal` (global default + override) | `cloud_to_branch` | `all_branches_with_override` (D19) |
| `[V]` identity master written on both sides | `bidirectional` | per §6.1, reconciled by D17 |
| `[V]` scoped to the selling/owning branch, written on both sides | `bidirectional` | `subscription` — target branch resolved from the row's own `uuid_sucursal`, or transitively from its parent's when the row has none (§16 Q1) |
| `[L-E]`, `[L-S]`, `[A]` | `branch_to_cloud` | — |
| `[L-W]` | `branch_to_cloud` | — |
| `[L-W]` marked CLOUD-ONLY in the ER | `cloud_to_branch` or excluded | `single_branch` |
| `[A]` infrastructure (`sync_*`) | out of catalog | — |

**Rationale.** The installed-trigger inventory is a delivery artifact. The ER is
the ratified data model and the only artifact both `check_schema_match.py` and
`check_table_counts.py` already gate on. Deriving policy from the ER makes the
policy verifiable; deriving it from triggers makes it unfalsifiable.

**Rule of last resort.** Where the ER is genuinely silent on a scope question,
this proposal picks the option that does not silently break a workflow, states
the rationale inline in §6.1, and lists the question in §16 for the user to
confirm. It does not pick the narrower option by default, because a too-narrow
broadcast fails **offline, at the counter, with no error path**, whereas a
too-wide broadcast fails as a bounded volume cost with a metric attached.

#### D6-rev — exactly one catalog per table (supersedes D6)

**Decision.** Every prod table resolves to **exactly one** of three sets:

- **`SyncCatalog` — 46 entries.** Every ER business entity that participates in
  replication, plus `validacion_evento` (declared `never_propagated`, see
  D8-rev).
- **`LocalOnlyCatalog` — 3 entries.** `idempotency_keys`, `pairing_tokens`,
  `revoked_sync_jwts` — non-ER operational tables, `role_required=both`.
- **Out of catalog — 5 entries.** `sync_queue`, `sync_log`, `sync_conflict`,
  `sync_queue_lw_buffer` (sync infrastructure) and `alert_types` (deploy-seeded
  registry, see below).

`factura_electronica` and `revocacion_factura` leave `LocalOnlyCatalog` and keep
a **single** `SyncCatalog` entry each (`branch_to_cloud`).

**Rationale.** The dual-catalog entry was the second-order effect of the old D1:
it existed to express "the branch writes but the cloud owns the number". With
D1-rev there is no split ownership, so there is nothing to express. The dual
entry was also actively harmful: it violated `check_catalog_drift.py` rule 2
("exactly one catalog per table") and it produced **two independent hash chains
for the same `(tabla, uuid_sucursal)`**. Since `verify_chain` walks by
`uuid_sucursal` in `(timestamp_evento, uuid)` order, it would see the two chains
interleaved and raise a guaranteed false `HashChainBreak` on the DIAN
evidentiary path.

**Why `alert_types` is out of catalog rather than a replicated catalog.** The
discriminator is *who authors the values*, not the table's class tag. Tables an
operator edits at runtime through the admin UI (`tipos_vehiculo`, `impuestos`,
`tarifas_sucursal`, …) must replicate, because a new value must reach the branch
without a deploy. `alert_types` is a registry whose members are referenced **by
identifier in Python source** (`orphan_workflow_chain`, `hash_chain_anomaly`,
`dian_timeout`, …); adding a member is a code change that ships with a deploy
anyway. It is therefore seeded idempotently by the same migration + seed script
on both cloud and branch, and never enters the replication pipeline. This rule
is stated explicitly so future tables are classified consistently and not by
analogy to whichever table they superficially resemble.

#### D8-rev — `never_propagated` is eliminated except for one table (supersedes D8)

**Decision.** `never_propagated` survives as a strategy for exactly one table:
`validacion_evento`. Every other `[V]` table receives a real `direction` and
flows through the same catalog mechanism as everything else. New
`fn_enqueue_sync_catalog` coverage for the 18 previously-untriggered `[V]` tables
is **in scope for this change**.

**Rationale.** `never_propagated` was justified by a "boot snapshot" mechanism
that does not exist in any requirement, task, or module. There is no reason to
invent a second distribution channel for catalog data when the catalog pipeline
is precisely the channel being built. Removing the strategy also removes the
need for the `justification` free-text field on 18 entries, and it makes the
four `[V]` hooks reachable in production.

`validacion_evento` keeps the strategy because the ER marks it CLOUD-ONLY
("bandeja del admin para validar cada evento recibido de sucursal") and states no
branch-side need. It stays **structurally present** in the branch schema (schema
parity is a hard project invariant) but is never populated there. It remains a
`SyncCatalog` entry rather than an out-of-catalog exemption, for two reasons:
`check_catalog_drift.py` rule 1 requires every ORM class to resolve to exactly
one catalog, and only a catalog entry has somewhere to declare
`role_required=cloud`, which is what makes the R6 import guard enforceable.

#### D14-rev — direction is ratified in this change (supersedes D14)

**Decision.** The `direction` / `broadcast_policy` values in §6.1 are **ratified
now**. The `direction_proposed: bool` field is removed from `SyncCatalogEntry`,
and there are no follow-up per-table ratification PRs.

**Rationale.** D14 deferred ratification because the original direction values
were guesses derived from trigger presence, so each one needed individual
review. Once direction is *derived* from the ER by a stated rule and asserted in
CI against the ER, a per-table human ratification gate adds a review queue
without adding information. The two genuinely undetermined business questions
are surfaced in §16 instead, where they can be answered once.

### 2.3 New decisions introduced by this amendment

#### D17 — cloud-side identity reconciliation for `clientes`, `clientes_b2b`, `vehiculos`

**Problem.** These three `[V]` tables become `bidirectional` (§6.1), which means
two branches, both offline, can independently register the same natural person
or the same plate. Each generates its own `uuid`, and because the UK includes
`vigente_desde` (`clientes`: `(tipo_identificador, numero_identificacion,
vigente_desde)`; `vehiculos`: `(placa, vigente_desde)`), both rows insert without
a UK violation. The result is **two concurrently-open versions of one entity**,
which breaks the bi-temporal invariant "at most one row with
`vigente_hasta IS NULL` per natural key".

**Decision — natural-key version reconciliation, insert-only.** In these three
tables the `uuid` identifies a **version**, not the entity; the natural key
identifies the entity. Cloud apply therefore keys on the natural key:

1. **Idempotent no-op.** If the arriving row's business columns are identical to
   the currently-open version (ignoring `uuid`, `created_at`, `created_by`,
   `sync_*`), the apply is a no-op returning `APPLIED`. This is the common case
   for two branches registering the same client from the same document, and it
   is what prevents version-chain inflation.
2. **Normal forward version.** If the arriving `vigente_desde` is **later** than
   the open version's, perform the ordinary `close_and_insert`: close the open
   version at the arriving row's `vigente_desde`, insert the arriving row as the
   new open version. The arriving branch's `uuid` survives as the current
   version.
3. **Late arrival after a partition.** If the arriving `vigente_desde` is
   **earlier** than the open version's, insert the arriving row as an already-
   closed historical version (`vigente_hasta` = the open version's
   `vigente_desde`). History stays ordered; the current version is not touched;
   no UPDATE of a newer row's business columns ever occurs.
4. **Divergent data, same key.** If cases 2 or 3 apply *and* business columns
   differ materially (name, email, phone, `uuid_tipo_persona`), also write a
   `sync_conflict` row at informational severity so an operator can review. The
   apply still succeeds — it must not block, because blocking a client
   registration blocks the invoice on the DIAN critical path.
5. **No FK rewriting, ever.** Existing FKs (`factura_electronica.uuid_cliente`,
   `subscripcion_vehiculos.uuid_vehiculo`, …) keep pointing at the version the
   emitting branch actually saw. That is the correct snapshot semantics and it is
   consistent with the ER's snapshot rule for `impuestos` / `otros_cobros`.
   Current-identity resolution happens by natural key at read time, in a view.

**Rationale.** This needs no new table, no alias/merge mechanism, and no
deviation from `uuid` v4 node generation. It relies only on properties the ER
already has: a natural key in the UK, insert-only history, and a surrogate key
that is per-version. The alternatives were worse: a deterministic UUIDv5 derived
from the natural key would contradict the ER's explicit "UUIDv4 generado en el
nodo" column contract for these tables, and a survivor-election alias table
would require rewriting FKs, which the no-UPDATE / no-DELETE canon forbids
outright.

**Normalization is part of the rule.** The natural key must be compared on a
normalized form: `numero_identificacion` trimmed of separators and whitespace;
`placa` uppercased and stripped of separators. Without this, `ABC-123` and
`ABC123` are two entities and the reconciliation silently fails to fire.

#### D18 — `depends_on` and a generalized `RETRY(parent_missing)` (generalizes D7 + D15)

**Decision.** Each `SyncCatalogEntry` declares
`depends_on: tuple[str, ...]` — every table it holds a **mandatory** FK to that
is itself a `SyncCatalog` entry. The motor applies rows in **topological order
over `depends_on`** within a batch. Any missing declared parent (not only the
`[L-W]` self-chain `uuid_padre`) produces `RETRY(parent_missing)` and buffers the
row in the existing dependency buffer.

Concrete consequences:

- **`priority` stops being an ordering mechanism.** Its legacy values (inherited
  from trigger insertion order) put `factura_pagos` ahead of `facturas` — a
  child ahead of its parent. `priority` survives only as a FIFO tie-breaker
  *within* one topological level, and using it for cross-table ordering is
  explicitly forbidden.
- **`depends_on` is CI-derived, not hand-maintained.** `check_catalog_drift.py`
  gains a rule asserting that each entry's `depends_on` equals the set of
  mandatory-FK parents the ER declares for that entity. A hand-edited value that
  drifts from the ER fails the build. This is what stops the FK-ordering fix from
  rotting the way the direction values did.
- **The `depends_on` graph must be a DAG.** Self-referential FKs
  (`reclamos.uuid_reclamo_padre`, `anulaciones.uuid_anulacion_padre`,
  `alerta.uuid_alerta_padre`, `reimpresion_ticket.uuid_reimpresion_padre`,
  `envio_dian.uuid_envio_padre`, `validacion_evento.uuid_validacion_padre`,
  `factura_pagos.uuid_pago_revertido`) are excluded from the topological sort and
  handled by the existing self-chain logic. CI asserts the graph is acyclic
  after removing self-edges.
- **One escalation path, not two.** The two currently-uncoordinated paths —
  re-enqueue into `sync_queue` at `intentos>=6`, and the buffer's TTL sweep — are
  reconciled into a single mechanism: the buffer owns the wait, the sweep owns
  the timeout, and the timeout emits `alerta tipo_alerta='orphan_workflow_chain'`.
  `sync_queue` is never re-enqueued for a dependency wait.
- **`parent_fk_column: str | None`** is added to the entry so
  `ValidateParentChain` can resolve the right column per table. The six `[L-W]`
  tables each use a differently-named parent column, which the original hook
  contract did not account for.
- **The rule is direction-agnostic.** Dependency ordering matters at least as
  much for `cloud_to_branch`: on first pairing a branch has an empty catalog set,
  so the initial backfill must apply in topological order or every child fails.

#### D19 — global-default rows for `configuracion_tolerancias` / `configuracion_seguridad`

**Decision.** New `broadcast_policy` member `all_branches_with_override`:

- rows with `uuid_sucursal IS NULL` (the global default) broadcast to **all**
  branches;
- rows with a non-NULL `uuid_sucursal` go **only** to that branch;
- the branch **does** store the NULL-default row;
- the branch pull query is
  `WHERE uuid_sucursal IS NULL OR uuid_sucursal = :branch_uuid`;
- resolution precedence at read time is most-specific-wins: a branch row
  overrides the NULL default.

**Rationale.** The ER establishes this default+override pattern explicitly for
both tables. Under the previous `single_branch` policy the NULL-default row
resolved to a NULL `branch_uuid` and fell through to a silent broadcast, which
happens to work today by accident and would break the moment the broadcast
resolver is tightened. Declaring the policy makes the accident intentional and
testable.

#### D20 — snapshot values are never recomputed on apply

**Decision.** For `factura_impuestos` and `factura_otros_cobros`, the applier
persists the snapshot values exactly as received. It must not re-read the live
`impuestos` / `otros_cobros` catalog to recompute a rate or amount, on either
side, at any time.

**Rationale.** The ER states this as a hard rule ("la factura NUNCA lo lee en
vivo"). It became a real hazard the moment `impuestos` and `otros_cobros` started
replicating: a branch that receives a new tax-rate version between emission and
apply would silently recompute the invoice to a rate that was not in force when
the document was issued — a tax-compliance defect, not a data-quality one.

#### D21 — stop enqueueing infrastructure tables

**Decision.** Two independent guards, both in scope:

1. Drop the `fn_enqueue_sync` trigger from `sync_log` and `sync_conflict`.
2. Make the cloud worker **skip** a row whose table is a known out-of-catalog
   infrastructure table, instead of `mark_failed(unknown_table)`.

**Rationale.** Both tables carry the legacy trigger today, so their rows arrive
at the cloud, resolve to no catalog entry, and are marked `unknown_table` →
`mark_failed`. That inflates the failure rate metric and buries real failures.
Guard 1 stops the source; guard 2 keeps the cloud correct for any branch still
running the old trigger set during the grace period.

#### D22 — `PARKOS_SYNC_ENGINE` has one enum

**Decision.** The enum is `legacy | catalog_admin | catalog_dian | catalog |
catalog_branch`. The design/ADR-001 variant
(`legacy | catalog_read | catalog_dual | catalog_only | catalog_lite`) is
withdrawn; `design.md` and `adr/001` must be amended to the chosen values.

**Rationale.** D13 stages the cutover **by service**, and these five values name
the services in stage order, so the flag value tells an operator exactly which
stage is live. The withdrawn variant names engine *modes*, which do not map onto
the stage gates and would require a second mapping table to interpret during an
incident.

### 2.4 Recommended defaults (this proposal proposes, future PRs may tune)

| # | Default | Rationale |
|---|---|---|
| **R-D1** | ~~Per-table `direction` defaults for 26 `[V]` tables~~ | **Superseded** — direction is ratified here (D14-rev), not defaulted. |
| **R-D2** | Cloud cutover stage gates (see §11) | Each stage passes only when the observable metrics in D10 meet thresholds for 24h continuous. |
| **R-D3** | AST/CI guard for `sync_queue` carve-out (R8) | `openspec/scripts/check_sync_queue_carveout.py` AST-walks `src/` and fails on any `UPDATE`/`DELETE` on `SyncQueue` outside `repo/sync_queue.py`. |
| **R-D4** | Build-time guard for cloud-only entries (R6) | `parkos_core/sync/role_guard.py::assert_role(role: 'cloud'\|'branch')` raises `ImportError` at module import when a branch process imports an entry with `role_required='cloud'`. Mirrors the existing precedent in the Factus provider module. **Scope narrowed**: only `validacion_evento` is `role_required='cloud'`. `envio_dian` is `role_required='both'` with `originating_role='cloud'` — the branch legitimately holds and reads those rows. |
| **R-D5** | pytest coverage threshold | **80%** line+branch for `parkos_core/sync/{catalog,motor,hooks}/`. CI fails below 80%. |
| **R-D6** | Dual-protocol grace period | **14 days** from stage-4 cutover. Branch auto-detects via the `hello` response field `protocol_version: 'legacy'\|'catalog'`. |
| **R-D7** | Stage gate criteria | (see §11) — backlog < 1000, conflict rate < 0.5%, chain verifier 0 anomalies, 0 `ImportError` crashes, dependency-wait backlog draining, all for 24h continuous. |
| **R-D8** | **New** — catalog backfill gate before branch cutover | A branch may not advance past `catalog_branch` stage 0 until `catalog_backfill_complete{uuid_sucursal}` = 1, i.e. every `cloud_to_branch` entry has applied its initial topological backfill. This is the direct guard against the failure that motivated the amendment. |

## 3. Goals & Non-Goals

### 3.1 Goals

1. One declarative source of truth (`SyncCatalog`) per table — replaces 4
   hardcoded `frozenset` + 30 trigger definitions + per-class try/except fallback
   in the applier.
2. **Direction and scope derived from the ER and asserted against it in CI**, so
   the class of defect this amendment corrects cannot recur silently (D5-rev,
   D18).
3. **Every global catalog and master-data table actually reaches the branch**, so
   a branch can classify, price, authenticate, authorize, and invoice offline
   (D8-rev). This is the user-visible outcome of the change.
4. Reusable `SyncMotor` with 3 methods: `apply_row(spec, payload)`,
   `verify_chain(spec, branch)`, `resolve_conflict(spec, local, remote)`, plus
   dependency-ordered batch application (D18).
5. Per-table **hooks** for: bi-temporal close (generic) + identity
   reconciliation (`clientes`, `clientes_b2b`, `vehiculos` — D17) + plate-change
   subscription cascade (`vehiculos`) + subscription lifecycle
   (`subscripcion_vehiculos`) + hash chain (`log_transaccional`,
   `revocacion_factura`) + generalized parent validation (any entry with
   `depends_on`).
6. CI-verifiable catalog ↔ ER drift (R1) + `depends_on` ↔ ER FK graph (D18) +
   `sync_queue` carve-out (R8) + cloud-only entry boot guard (R6).
7. Cloud-first cutover with rollback switch (D12) + dual-protocol grace (D11) +
   per-branch backfill gate (R-D8).
8. Observability the operator can act on (D10).

### 3.2 Non-Goals (explicit)

- **No central `consecutivo` allocator** — numbering is branch-local per
  resolution (D1-rev).
- **No `prod.sync_back_events` table, hook, or protocol** (D1-rev).
- **No new repo helpers** — `repo/{versioned,event,workflow,append_only,hash_chain,session_cycle}`
  already cover every table. The motor dispatches to them.
- **No changes to the auth chain** (`sync_router` JWT, pairing, revocation). The
  catalog refactor is payload-layer only.
- **No WebSocket transport** — HTTP polling only (AGENTS.md §"Sync").
- **No physical DELETE** — the existing defense in depth (no API endpoint, no ORM
  helper, DB `REVOKE` + `BEFORE UPDATE OR DELETE` trigger on `[A]`) is canon and
  is not touched.
- **No identity alias/merge table** — D17 reconciles by natural key without one.
- **No filtered/bounded client-master broadcast** — `clientes` broadcasts in full
  (§6.1); a volume-bounded broadcast is deferred (§14, R18).

## 4. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Cloud admin / Branch process                                    │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │   SyncCatalog    │  │ LocalOnlyCatalog │  │ Out of catalog│  │
│  │   (46 entries)   │  │   (3 entries)    │  │  (5 entries)  │  │
│  └────────┬─────────┘  └──────────────────┘  └───────────────┘  │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────────────────────────────┐                   │
│  │        DependencyOrderer (D18)           │                   │
│  │  topological sort over depends_on        │                   │
│  └──────┬───────────────────────────────────┘                   │
│         ▼                                                       │
│  ┌──────────────────────────────────────────┐                   │
│  │             SyncMotor                    │                   │
│  │  apply_row(spec, payload)                │                   │
│  │  verify_chain(spec, branch_uuid)         │                   │
│  │  resolve_conflict(spec, local, remote)   │                   │
│  └──────┬───────────────┬─────────────┬─────┘                   │
│         │               │             │                         │
│         ▼               ▼             ▼                         │
│   repo/versioned   repo/event   repo/workflow                   │
│       (close_       (record_     (append_                       │
│        and_insert)   event)      transition)                    │
│                              │                                  │
│                              ▼                                  │
│                       repo/append_only                          │
│                       repo/hash_chain                           │
│                       repo/session_cycle                        │
│                                                                 │
│  Hooks (per spec):                                              │
│   - hook_pre_insert  - hook_post_insert  - hook_chain_extend    │
│   - hook_validate_parent  (any entry with depends_on)           │
│                                                                 │
│  RETRY(parent_missing) ──▶ prod.sync_queue_lw_buffer             │
│                            (TTL sweep ──▶ alerta)               │
└─────────────────────────────────────────────────────────────────┘
```

The catalog is the **policy decision**, declared in source, not auto-discovered
from ORM metadata. It references ORM classes but declares per-table
`sync_strategy`, `direction`, `broadcast_policy`, `apply_strategy`, `depends_on`,
`hash_chain`, `role_required`, and so on. Auto-discovery is explicitly rejected:
a reflective registry cannot express direction, scope, dependency order, or role
constraints, and it silently absorbs new tables without a policy decision.

The motor is **stateless**. Each call takes a `spec` + payload and dispatches to
the existing repo helpers. The motor **never** writes to the DB directly — it
calls into `repo/*` so every audit-first invariant (close+insert, append-only,
hash chain) is honored in one place.

Hooks are **pure callables** (`Callable[[HookContext], Awaitable[HookResult]]`)
attached to a spec. They run before/after the repo call and may adjust the
payload before persistence, veto the apply, or extend a hash chain.

## 5. Catalog Schema (`SyncCatalogEntry`)

```python
@dataclass(frozen=True)
class SyncCatalogEntry:
    # Identity
    name: str                                # __tablename__
    model_cls: type[DeclarativeBase]
    audit_class: Literal["V", "L_E", "L_W", "L_S", "A"]

    # Policy (D5-rev, D8-rev, D14-rev)
    sync_strategy: Literal["append", "manual", "grace_window",
                           "never_propagated", "local_only",
                           "is_sync_outbox"]
    direction: Literal["cloud_to_branch", "branch_to_cloud",
                       "bidirectional"] | None      # None iff never_propagated
    broadcast_policy: Literal["single_branch", "all_branches",
                              "all_branches_with_override",   # D19
                              "subscription"] | None = "single_branch"

    # Apply
    apply_strategy: Literal["close_and_insert", "record_event",
                            "append_event", "append_transition",
                            "session_cycle"] | None

    # Dependency ordering (D18)
    depends_on: tuple[str, ...] = ()         # mandatory-FK parents in SyncCatalog
    parent_fk_column: str | None = None      # self-chain column, per table
    self_chain: bool = False                 # excluded from topological sort

    # Sequence
    has_uuid_sucursal: bool                  # derived from the ORM
    seq_strategy: Literal["seq_via_datos",
                          "max_timestamp_evento",
                          "max_created_at",
                          "none"] | None

    # Identity reconciliation (D17)
    natural_key: tuple[str, ...] = ()        # non-empty for the 3 bidirectional masters
    natural_key_normalizer: Callable[[dict], dict] | None = None

    # Hash chain
    hash_chain: bool = False                 # log_transaccional, revocacion_factura
    verify_chain: bool = False               # sync_cloud verifier iterates

    # Role / scope
    role_required: Literal["cloud", "branch", "both"] = "both"
    originating_role: Literal["cloud", "branch", "both"] = "branch"

    # Snapshot immutability (D20)
    snapshot_columns: frozenset[str] | None = None   # never recomputed on apply

    # Hooks (per-table callable — §8)
    hook_pre_insert: HookFn | None = None
    hook_post_insert: HookFn | None = None
    hook_chain_extend: HookFn | None = None
    hook_validate_parent: HookFn | None = None

    # Operational
    is_sync_outbox: bool = False             # sync_queue only
    state_mutable_columns: frozenset[str] | None = None

    # Metadata
    justification: str | None = None         # required iff never_propagated
    priority: int = 1                        # intra-level FIFO tie-break ONLY (D18)
    chain_priority: int = 0
```

**Fields removed by this amendment**: `cloud_only: bool` (replaced by the
`role_required` / `originating_role` pair, which distinguishes "may not exist
here" from "is not authored here"), `sync_back_event: bool` (D1-rev),
`direction_proposed: bool` (D14-rev).

**Fields added**: `depends_on`, `parent_fk_column`, `self_chain`, `natural_key`,
`natural_key_normalizer`, `originating_role`, `snapshot_columns`,
`justification`.

**Typing fix**: `broadcast_policy` accepted a `direction` value
(`bidirectional`) in one requirement. It is a distinct enum and must never
receive a direction value; CI asserts the two enums are disjoint.

## 6. Per-Table Catalog (54 tables)

Direction and scope below are derived per D5-rev. The `Derivation` column names
the ER evidence, so a reviewer can check each row against the model rather than
against an installed trigger.

### 6.1 SyncCatalog (46 entries)

**[V] versioned — 26 entries** (D2, D8-rev, D14-rev)

| Table | `uuid_sucursal` | direction | broadcast_policy | apply / seq | Derivation |
|---|---|---|---|---|---|
| `usuarios` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | ER: "se administra en cloud y **se replica a sucursales para login offline**". Was wrongly `never_propagated`; `usuarios_sucursal` carries no credential columns, so the junction cannot substitute for offline login. |
| `permisos` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | ER: "**replica cloud a sucursales**". Was wrongly `never_propagated`. |
| `permisos_usuario` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | Junction `usuarios`×`permisos`; required for offline authorization. No `uuid_sucursal` ⇒ global grid. |
| `tipo_persona` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | `[V]` global catalog; branch needs it to classify a client for electronic invoicing. |
| `tipos_vehiculo` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | `[V]` global catalog; parent of `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `ingreso`, `vehiculos`. |
| `tipo_subscripciones` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | `[V]` global catalog; parent of `subscripciones_cliente`. |
| `tipo_tarifa` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | `[V]` global catalog; gives `tarifas_sucursal` its billing semantics. |
| `tipo_sucursal` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | `[V]` global catalog; its characteristics enable branch modules. |
| `tipo_arqueo` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | `[V]` global catalog; mandatory parent of `arqueo`. |
| `impuestos` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | `[V]` tax catalog; the branch must snapshot the in-force rate at emission (D20). |
| `otros_cobros` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | `[V]` catalog; same snapshot pattern (D20). |
| `costos_servicios` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | `[V]` catalog; `reimpresion_ticket` charges the in-force service cost. |
| `configuracion_tolerancias` | nullable | `cloud_to_branch` | `all_branches_with_override` | `close_and_insert` / `max_created_at` | ER: global default + per-branch override. See D19. |
| `configuracion_seguridad` | nullable | `cloud_to_branch` | `all_branches_with_override` | `close_and_insert` / `max_created_at` | ER: global default + per-branch override. See D19. |
| `empresa` | no | `cloud_to_branch` | `all_branches` | `close_and_insert` / `max_created_at` | `[V]` tax identity of the operator; the branch needs it for the DIAN document header. **Tenant filter**: broadcast only the version reachable from the branch's own `sucursal.uuid_empresa` — today one operator, so functionally `all_branches`, but multi-operator-safe. |
| `resolucion_facturacion` | yes | `cloud_to_branch` | `single_branch` | `close_and_insert` / `max_created_at` | ER: one resolution **per branch**, with `rango_desde`/`rango_hasta`. The branch numbers with its own resolution (D1-rev). Unchanged from the original proposal. |
| `sucursal` | no | `cloud_to_branch` | `single_branch` | `close_and_insert` / `max_created_at` | ER: "la réplica local de cada sede contiene **solo sus filas** + catálogos", and `web_sucursal` is branch-pinned. Do not broadcast every branch's identity to every other branch. |
| `usuarios_sucursal` | yes | `cloud_to_branch` | `single_branch` | `close_and_insert` / `max_created_at` | Authorizes a user to operate at one branch; the branch needs only its own rows. |
| `documentos` | yes | `cloud_to_branch` | `single_branch` | `close_and_insert` / `max_created_at` | Branch-owned administrative files, inline base64 for offline availability. |
| `tarifas_sucursal` | yes | `cloud_to_branch` | `single_branch` | `close_and_insert` / `max_created_at` | Price per branch × vehicle type × modality; supports future-dated rows. |
| `cantidad_vehiculos_sucursal` | yes | `cloud_to_branch` | `single_branch` | `close_and_insert` / `max_created_at` | Per-branch capacity by vehicle type. |
| `clientes` | no | `bidirectional` | `all_branches` | `close_and_insert` / `max_created_at` | Identity master with no `uuid_sucursal` ⇒ global per the ER replication rule. Written on **both** sides: cloud admin registers B2B clients, and a cashier must be able to register an identified client offline to issue an electronic invoice. Reconciled by **D17** (`natural_key=(tipo_identificador, numero_identificacion)`). Was wrongly `never_propagated`, which made `PIIRedactor` unreachable. |
| `clientes_b2b` | no | `bidirectional` | `all_branches` | `close_and_insert` / `max_created_at` | 1:1 extension of `clientes`; must follow its parent's direction and scope or the extension is unreachable wherever the parent is present. `natural_key=(uuid_cliente,)`. |
| `subscripciones_cliente` | yes | `bidirectional` | `subscription` | `close_and_insert` / `max_created_at` | **Ratified by the product decision closing §16 Q1**: a subscription is honored **only at the branch that sold it**. `broadcast_policy=subscription` resolves the target branch from the row's own `uuid_sucursal`, so the subscription reaches the selling branch and no other. `bidirectional` is retained because the row is authored on both sides — cloud admin sells or renews a plan, and a cashier must be able to enrol one offline. |
| `vehiculos` | no | `bidirectional` | `all_branches` | `close_and_insert` / `max_created_at` | Identity master with no `uuid_sucursal`. Registered at whichever branch enrolls the subscription. Reconciled by **D17** (`natural_key=(placa,)`). Was wrongly `never_propagated`, which made `PlateChangeCascade` dead code. |
| `subscripcion_vehiculos` | no | `bidirectional` | `subscription` | `close_and_insert` / `max_created_at` | Junction; follows its parent's scope per the §16 Q1 decision. It carries no `uuid_sucursal` of its own, so the target branch is resolved **transitively** through `subscripciones_cliente.uuid_sucursal` — which is precisely what `broadcast_policy=subscription` means and why the enum member exists. FK closure holds: the selling branch is the only branch that receives both the parent subscription and this junction. |

**[L-E] lifecycle events — 3 entries**

| Table | direction | apply / seq | hash_chain | Derivation |
|---|---|---|---|---|
| `ingreso` | `branch_to_cloud` | `record_event` / `max_timestamp_evento` | via `record_event` | `[L-E]` core business event, "se crea offline-first y sube a cloud". |
| `facturas` | `branch_to_cloud` | `record_event` / `max_timestamp_evento` | via `record_event` | `[L-E]` internal sales document issued at the branch. |
| `factura_electronica` | `branch_to_cloud` | `record_event` / `max_timestamp_evento` | via `record_event` | `[L-E]` "se emite **EN sucursal** con SU resolución y cloud la envía". **Single catalog entry** — removed from `LocalOnlyCatalog`, no `sync_back_event` flag (D1-rev, D6-rev). |

**[L-W] workflows — 6 entries** (D7 as generalized by D18)

| Table | direction | broadcast | apply / seq | Derivation |
|---|---|---|---|---|
| `reimpresion_ticket` | `branch_to_cloud` | — | `append_transition` / `seq_via_datos` | `[L-W]` branch-side reprint workflow. Direction narrowed from `bidirectional`: with D1-rev nothing in the cloud initiates a reprint, so there is no cloud→branch leg to model. |
| `anulaciones` | `branch_to_cloud` | — | `append_transition` / `seq_via_datos` | `[L-W]` branch-side cancellation workflow with an approval chain. |
| `reclamos` | `branch_to_cloud` | — | `append_transition` / `seq_via_datos` | `[L-W]` customer claims raised at the branch. |
| `alerta` | `branch_to_cloud` | — | `append_transition` / `seq_via_datos` | `[L-W]` operational alerts; born automatically (arqueo, sync, offline) or manually at the branch. Cloud-originated alerts are recorded against the cloud's own `uuid_sucursal` context and are out of scope here. |
| `envio_dian` | **`cloud_to_branch`** | `single_branch` | `append_transition` / `seq_via_datos` | ER: "**CLOUD-ONLY: único punto de salida hacia el proveedor** de factura electrónica DIAN". **Flipped** from `branch_to_cloud`. This entry **is** the DIAN return channel (`cufe`, `estado`) and replaces the invented `sync_back_events` table entirely (D1-rev). `originating_role='cloud'`, `role_required='both'` — the branch legitimately holds and reads these rows. |
| `validacion_evento` | **`None`** (`never_propagated`) | — | — | ER: "**CLOUD-ONLY: bandeja del admin** para validar cada evento recibido de sucursal". **Flipped** from `branch_to_cloud`. No stated branch-side need. Structurally present in the branch schema (schema parity), never populated there. `role_required='cloud'`, `originating_role='cloud'`, `justification` required. The **only** table keeping `never_propagated` (D8-rev). |

**[L-S] sessions — 2 entries** (D11 grace window)

| Table | direction | apply / seq | grace_window | Derivation |
|---|---|---|---|---|
| `login` | `branch_to_cloud` | `session_cycle` / `max_timestamp_evento` | 24h JWT overlap | `[L-S]` authentication attempt log, written at the branch. |
| `sesion` | `branch_to_cloud` | `session_cycle` / `max_timestamp_evento` | 24h JWT overlap | `[L-S]` cashier shift, opened and closed at the branch. |

**[A] append-only — 9 entries** (header previously said 10 while listing 9 — corrected)

| Table | direction | apply / seq | hash_chain | Notes |
|---|---|---|---|---|
| `salidas` | `branch_to_cloud` | `append_event` / `seq_via_datos` | no | Closes the stay; corrections flow through `anulaciones`. |
| `factura_detalle` | `branch_to_cloud` | `append_event` / `seq_via_datos` | no | Invoice lines with the exact emitted values. |
| `factura_impuestos` | `branch_to_cloud` | `append_event` / `seq_via_datos` | no | **D20**: `snapshot_columns` never recomputed from the live `impuestos` catalog on apply. |
| `factura_otros_cobros` | `branch_to_cloud` | `append_event` / `seq_via_datos` | no | **D20**: same snapshot rule. |
| `factura_pagos` | `branch_to_cloud` | `append_event` / `seq_via_datos` | no | `BiTemporalCompensation` hook for `tipo_movimiento='reverso'`; `uuid_pago_revertido` is a self-FK (`self_chain=True`). |
| `caja` | `branch_to_cloud` | `append_event` / `seq_via_datos` | no | Periodic cash snapshots per branch. |
| `arqueo` | `branch_to_cloud` | `append_event` / `seq_via_datos` | no | Physical count vs. expected; over-tolerance raises an `alerta`. |
| `log_transaccional` | `bidirectional` | `append_event` / `seq_via_datos` | **YES** + `verify_chain` | Hash-chain carrier. Keeps the existing per-`uuid_sucursal` monotonic-seq mitigation; cloud preserves the branch chain verbatim and only extends it with cloud-originated rows. |
| `revocacion_factura` | `branch_to_cloud` | `append_event` / `seq_via_datos` | **YES** + `verify_chain` | `[A]` DIAN revocations with an evidentiary hash chain per branch. **Single catalog entry** — removed from `LocalOnlyCatalog`, no `sync_back_event` flag (D1-rev, D6-rev). This removal is what eliminates the guaranteed false `HashChainBreak` from two interleaved chains on the same `(tabla, uuid_sucursal)`. |

### 6.2 LocalOnlyCatalog (3 entries — D6-rev)

| Table | sync_strategy | role_required | Reason |
|---|---|---|---|
| `idempotency_keys` | `local_only` | `both` | TTL-pruned request-dedup store; never replicated. Not an ER entity. |
| `pairing_tokens` | `local_only` | `both` | Pre-issuance single-use tokens; never replicated. Not an ER entity. |
| `revoked_sync_jwts` | `local_only` | `both` | JWT revocation list; never replicated. Not an ER entity. |

`factura_electronica` and `revocacion_factura` **no longer appear here** — see
D6-rev. `check_catalog_drift.py` rule 2 ("exactly one catalog per table") now
holds with **no exceptions**.

### 6.3 Out of catalog (5 entries — explicitly excluded)

| Table | Why excluded |
|---|---|
| `sync_queue` | Sync infrastructure: the branch's outbox. The only table with mutable state by design; state-mutable columns are `{estado, intentos, next_retry_at, ultimo_error}`. Motor reads and mutates it only through `repo/sync_queue.py`; it is never enqueued into itself. |
| `sync_log` | Sync infrastructure: per-cycle metrics, local only. **D21**: drop its `fn_enqueue_sync` trigger. |
| `sync_conflict` | Sync infrastructure: detected conflicts with both versions retained, local only. **D21**: drop its `fn_enqueue_sync` trigger. |
| `sync_queue_lw_buffer` | **New `[A]`** dependency buffer (D18). Sync infrastructure by construction; buffering the buffer is meaningless. |
| `alert_types` | **New `[A]`** registry, deploy-seeded on both cloud and branch. Its members are referenced by identifier in Python source, so a new member ships with a deploy, not with replication. See the classification rule in D6-rev. |

`check_catalog_drift.py` must carry **exactly these five names** in its exemption
list, and R-D3 AST-asserts none of them appears in any catalog with propagation
enabled.

### 6.4 Dependency graph (`depends_on` — D18)

Declared per entry as the set of **mandatory** FK parents that are themselves
`SyncCatalog` entries. CI derives the expected set from the ER's relationship
block and fails on drift, so this table is documentation of the rule rather than
a hand-maintained list.

| Entry | `depends_on` | Self-chain column |
|---|---|---|
| `permisos_usuario` | `usuarios`, `permisos` | — |
| `usuarios_sucursal` | `usuarios`, `sucursal` | — |
| `sucursal` | `empresa`, `tipo_sucursal` | — |
| `resolucion_facturacion` | `sucursal` | — |
| `documentos` | `sucursal` | — |
| `tarifas_sucursal` | `sucursal`, `tipos_vehiculo`, `tipo_tarifa` | — |
| `cantidad_vehiculos_sucursal` | `sucursal`, `tipos_vehiculo` | — |
| `configuracion_tolerancias` / `configuracion_seguridad` | — (`uuid_sucursal` nullable) | — |
| `clientes` | `tipo_persona` | — |
| `clientes_b2b` | `clientes` | — |
| `subscripciones_cliente` | `clientes`, `sucursal`, `tipo_subscripciones` | — |
| `vehiculos` | `tipos_vehiculo` | — |
| `subscripcion_vehiculos` | `subscripciones_cliente`, `vehiculos` | — |
| `login` | `usuarios`, `sucursal` | — |
| `ingreso` | `sucursal`, `tipos_vehiculo` | — |
| `salidas` | `sucursal`, `ingreso` | — |
| `facturas` | `sucursal`, `ingreso`, `salidas` | — |
| `factura_detalle` | `sucursal`, `facturas` | — |
| `factura_impuestos` | `sucursal`, `facturas`, `impuestos` | — |
| `factura_otros_cobros` | `sucursal`, `facturas`, `otros_cobros` | — |
| `factura_pagos` | `sucursal`, `facturas`, `sesion` | `uuid_pago_revertido` |
| `factura_electronica` | `sucursal`, `facturas`, `clientes`, `resolucion_facturacion` | — |
| `revocacion_factura` | `sucursal`, `factura_electronica` | — |
| `envio_dian` | `sucursal`, `factura_electronica`, `resolucion_facturacion` | `uuid_envio_padre` |
| `sesion` | `sucursal`, `usuarios` | — |
| `caja` | `sucursal` | — |
| `arqueo` | `sucursal`, `sesion`, `tipo_arqueo` | — |
| `alerta` | `sucursal`, `usuarios` | `uuid_alerta_padre` |
| `reimpresion_ticket` | `sucursal`, `ingreso`, `usuarios`, `costos_servicios`, `facturas` | `uuid_reimpresion_padre` |
| `anulaciones` | `sucursal`, `ingreso`, `salidas`, `usuarios` | `uuid_anulacion_padre` |
| `reclamos` | `sucursal`, `ingreso`, `salidas`, `facturas`, `subscripciones_cliente` | `uuid_reclamo_padre` |
| `log_transaccional` | `sucursal`, `usuarios` | — |
| `validacion_evento` | — (`never_propagated`) | `uuid_validacion_padre` |

Two properties worth stating because they were the original hazards:

- **`log_transaccional` → `usuarios`** only resolves at the branch because
  `usuarios` now replicates (D8-rev). Under the old catalog this FK was
  unsatisfiable at the branch.
- **`envio_dian` → `factura_electronica`** crosses directions
  (`cloud_to_branch` child, `branch_to_cloud` parent) but is always satisfiable
  at the branch: the branch itself emitted the parent before the cloud could
  create the child.

Two further properties follow from the §16 Q1 decision and are stated so a later
pass does not "tidy" them into a defect:

- **`subscripcion_vehiculos` → `subscripciones_cliente`, `vehiculos` still holds
  under `subscription` scope.** The selling branch is by construction the only
  branch that receives the junction, and it is also the branch that authored or
  received both parents. No other branch receives a junction row whose parent it
  lacks, so the narrower scope removes dependency waits rather than creating
  them.
- **`vehiculos` and `clientes` must stay `all_branches`; they cannot be
  `subscription`-scoped.** Neither carries a `uuid_sucursal`, so their only link
  to a branch runs *through* `subscripcion_vehiculos` — a child. Deriving a
  parent's scope from its child inverts the dependency order (D18 requires the
  parent to arrive first), so the attempt is circular by construction. The
  consequence is accepted deliberately: the vehicle and client identity masters
  remain network-wide while the subscription linkage that gives them commercial
  meaning is branch-scoped. Identity is global; entitlement is local.

### 6.5 Count reconciliation (single canonical set of numbers)

| Quantity | Value | Composition |
|---|---|---|
| ER entities today | **49** | 26 `[V]` + 3 `[L-E]` + 6 `[L-W]` + 2 `[L-S]` + 12 `[A]` |
| ER entities after this change | **51** | 49 + `sync_queue_lw_buffer` `[A]` + `alert_types` `[A]` |
| Non-ER operational tables | **3** | `idempotency_keys`, `pairing_tokens`, `revoked_sync_jwts` |
| **Physical prod tables after this change** | **54** | 51 ER + 3 non-ER |
| `len(SYNC_CATALOG)` | **46** | 26 `[V]` + 3 `[L-E]` + 6 `[L-W]` + 2 `[L-S]` + 9 `[A]` |
| `len(LOCAL_ONLY_CATALOG)` | **3** | §6.2 |
| `len(OUT_OF_CATALOG)` | **5** | §6.3 |
| Catalog coverage check | 46 + 3 + 5 = **54** | every prod table classified exactly once |

**Every artifact must state these same numbers.** The prior pass carried 47 / 5 /
3, plus 49→50 in `design.md`, 51 in the ADR title with "50-table count" in its
body, and both values in `tasks.md`. The corrected canon is **51 ER entities, 54
physical tables, 46 catalog entries** — and `sync_back_events` does not exist.

`prod.sync_back_events` is **not** in any of these counts and must not appear in
any migration, ORM module, catalog, ADR, or task.

## 7. SyncMotor API

```python
class SyncMotor:
    """Stateless. Dispatches per spec to repo/* helpers. Honors audit-first."""

    async def apply_batch(
        self, rows: Sequence[tuple[SyncCatalogEntry, dict]],
        *, actor_uuid: UUID,
    ) -> BatchResult:
        """Apply a batch in dependency order (D18).

        1. Topologically sort `rows` over `spec.depends_on`, excluding
           self-chain edges. A cycle is a programming error, not a runtime
           condition: raise, do not best-effort.
        2. Apply each row via `apply_row`.
        3. Any RETRY(parent_missing) row goes to prod.sync_queue_lw_buffer,
           keyed on the missing (tabla, uuid). Its children in the same batch
           are buffered with it rather than attempted and failed.
        """

    async def apply_row(
        self, spec: SyncCatalogEntry, payload: dict,
        *, actor_uuid: UUID, log_tx: bool = True,
    ) -> ApplyResult:
        """Insert/update one row from a remote push.

        Dispatches on spec.apply_strategy:
          close_and_insert  -> repo.versioned.close_and_insert
          record_event      -> repo.event.record_event
          append_event      -> repo.append_only.append_event
                               (chain_hash=spec.hash_chain)
          append_transition -> repo.workflow.append_transition
          session_cycle     -> repo.session_cycle.record_login /
                               close_login_with_log

        Before dispatch: validate every declared parent in spec.depends_on
        exists locally; missing -> RETRY(parent_missing) (D18).
        Pre-insert hook (identity reconciliation, cascades).
        Post-insert hook (telemetry).
        Chain-extend hook (hash_chain specs).
        Snapshot columns in spec.snapshot_columns are persisted verbatim and
        never recomputed (D20).
        Returns ApplyResult(status=APPLIED|CONFLICT|RETRY, row_uuid, ...).
        """

    async def verify_chain(
        self, spec: SyncCatalogEntry, branch_uuid: UUID,
    ) -> list[ChainAnomaly]:
        """Walk spec.model_cls per uuid_sucursal in (timestamp_evento, uuid)
        order. Used by the cloud hash-chain verifier loop, which now covers
        both log_transaccional and revocacion_factura.
        Returns empty list on a clean chain; anomalies otherwise.
        """

    async def resolve_conflict(
        self, spec: SyncCatalogEntry,
        *, local: dict, remote: dict,
    ) -> ConflictResolution:
        """Decide between APPLIED (apply remote), MANUAL (sync_conflict row),
        or REVERSED (apply local). Implements D4 (replaces the stub
        _read_local_seq).

        Strategy per spec.audit_class:
          [V] with natural_key -> D17 reconciliation (no-op | forward version |
                                  historical insert), never blocking
          [V] otherwise        -> max(seq_strategy) > local_seen -> APPLIED
                                  else MANUAL
          [L-E]                -> APPLIED once every declared parent resolves,
                                  else RETRY(parent_missing)
          [L-W]                -> parent chain valid -> APPLIED
                                  else RETRY(parent_missing)
          [L-S]                -> grace window check -> APPLIED else MANUAL
          [A]                  -> APPLIED once every declared parent resolves,
                                  else RETRY(parent_missing)
        """
```

**Change from the prior pass**: `[L-E]` and `[A]` were "always APPLIED". That
policy has no `RETRY(parent_missing)` path, so a child arriving before its
parent produced a raw FK violation rather than a resolvable condition — on the
invoicing path, which is where children arrive first most often. Both classes now
gate on parent resolution (D18) while keeping append-only immutability: the row
is never modified, only deferred.

## 8. Hook Contract

```python
@dataclass
class HookContext:
    spec: SyncCatalogEntry
    payload: dict                      # mutable; pre-insert may adjust fields
    session: AsyncSession
    actor_uuid: UUID
    chain_head: bytes | None = None    # set for chain_extend hook
    parent_local: dict | None = None   # set for validate_parent hook
    open_version: dict | None = None   # set for natural_key specs (D17)

@dataclass
class HookResult:
    proceed: bool                      # False aborts apply_row
    payload_override: dict | None      # used by pre_insert
    chain_extension: tuple[bytes, bytes] | None  # (hash_anterior, hash_actual)
    parent_valid: bool = True          # False -> RETRY(parent_missing)
    reconciliation: Literal["noop", "forward", "historical"] | None = None  # D17
    cascade_rows: list[tuple[str, dict]] = field(default_factory=list)

HookFn = Callable[[HookContext], Awaitable[HookResult]]
```

**Hook lifecycle in `apply_row`**:

1. **Validate parents** (`hook_validate_parent`) — for any spec with a non-empty
   `depends_on` (D18, generalizing D7). If a declared parent is missing locally
   and not earlier in the same batch, return `RETRY(parent_missing)`; the row is
   buffered, the TTL sweep escalates to
   `alerta tipo_alerta='orphan_workflow_chain'`.
2. **Pre-insert** (`hook_pre_insert`) — identity reconciliation (D17), cascades.
   Sets `payload_override`, `reconciliation`, and/or `cascade_rows`.
3. **Repo call** — dispatches to the `repo/*` helper per `apply_strategy`.
   `snapshot_columns` are written verbatim (D20).
4. **Post-insert** (`hook_post_insert`) — telemetry (D10); emits
   `sync_apply_total{status,tabla,uuid_sucursal}`; applies `cascade_rows` through
   the motor so cascades honor the same invariants as primary rows.
5. **Chain extend** (`hook_chain_extend`) — for `hash_chain=True` specs. Sets
   `chain_extension`; the motor calls `repo/hash_chain.append` with the computed
   pair, and the DB trigger re-verifies server-side.

Step 1 moved ahead of the repo call. In the prior pass parent validation ran
*after* persistence, which cannot prevent an FK violation — it can only observe
one.

**Per-table hook bindings**

| Table | Hook | Purpose |
|---|---|---|
| `clientes`, `clientes_b2b`, `vehiculos` | `hook_pre_insert` (`IdentityReconciler`) | **D17** — normalize the natural key, classify the arrival as `noop` / `forward` / `historical`, emit an informational `sync_conflict` on divergent data. Never blocks. |
| `vehiculos` | `hook_post_insert` (`PlateChangeCascade`) | **Re-targeted.** On a plate change, close the affected `subscripcion_vehiculos` rows and insert replacements pointing at the new `vehiculos` version, so a subscription cannot silently cover a stale plate. |
| `subscripcion_vehiculos` | `hook_pre_insert` (`SubscriptionLifecycle`) | Validate the state transition against the current row and the plan's `cantidad_maxima_vehiculos`. |
| `factura_pagos` | `hook_post_insert` (`BiTemporalCompensation`) | For `tipo_movimiento='reverso'`, emit a compensating `log_transaccional` row. |
| `log_transaccional` | `hook_chain_extend` (`LogTransaccionalChain`) | Every event extends the per-branch chain. |
| `revocacion_factura` | `hook_chain_extend` (`RevocacionFacturaChain`) | A DIAN-accepted revocation extends the chain (replaces the manual dispatcher call). |
| every spec with non-empty `depends_on` | `hook_validate_parent` (`ValidateParentChain`) | **D18** — resolve each declared parent using `spec.parent_fk_column` for self-chains. |
| — | ~~`SyncBackEventEmitter`~~ | **Removed** (D1-rev). No table, no hook, no dispatcher emit loop. |

**Two hook contracts changed, and the reasons matter for `sdd-spec`:**

- **`PIIRedactor` is withdrawn as a payload hook and re-scoped to observability.**
  Its original contract was "redact email, phone, address before push". Once
  `clientes` is `bidirectional`, that contract would destroy data the DIAN flow
  requires: the ER states `clientes.email` "recibe la representación gráfica de
  la factura electrónica", and `telefono` / `nombre` / `apellido` are the
  acquirer identity on the electronic document. A hook that strips them makes
  every replicated client unusable as an invoice acquirer. PII handling belongs
  where PII is *not* required for the business function: redaction in
  `sync_log`, in structured logs, and in `sync_conflict.datos_local` /
  `datos_remoto`. The transport itself is already protected by TLS 1.3 plus the
  `sync-agent-` JWT, which is the correct control for data that must arrive
  intact.
- **`PlateChangeCascade` cannot write `reclamos`.** The original binding emitted
  a `reclamos` row with `uuid_padre=<vehiculos>`, but `reclamos.uuid_reclamo_padre`
  is a **self**-FK and `tipo_reclamable ∈ {ingreso, salida, factura, subscripcion}`
  — there is no vehicle reclamable, so the row is not storable. The genuine
  integrity concern behind the hook is different and narrower: `vehiculos.uuid`
  identifies a *version*, so a plate change mints a new version while existing
  `subscripcion_vehiculos` rows still point at the old one, i.e. the subscription
  keeps covering the previous plate. The cascade therefore closes and re-inserts
  the junction rows, and the audit trail is `log_transaccional`, as for every
  other bi-temporal transition.

## 9. Migration Plan

### 9.1 Pre-flight (PR1)

- pytest installed (`backend/pyproject.toml` dev deps updated; `uv lock --check`
  passes).
- `openspec/scripts/check_sync_queue_carveout.py` added (R-D3).
- `parkos_core/sync/role_guard.py::assert_role` added (R-D4).
- Coverage gate configured: 80% threshold for `sync/{catalog,motor,hooks}/`.
- `infra/deploy/.env.*` added to `.gitignore` **before** any task stages files
  under `infra/deploy/`. `infra/deploy/.env.cloud` is currently untracked and
  **not** ignored (`.gitignore` covers `.env`, `.env.local`, `.env.*.local` but
  not `.env.<name>`), and the cloud compose file expects a DIAN provider URL and
  a token path in it.

### 9.2 Schema migrations

New migrations only — `0001_initial_schema.py` is already applied in production
and must not be edited. This corrects an inconsistency in the prior pass, where
one spec placed the dependency buffer inside `0001_initial_schema.py` while the
design and tasks placed it in a new revision.

| Migration | Contents |
|---|---|
| `0009_add_sync_queue_lw_buffer.py` | `prod.sync_queue_lw_buffer` `[A]` + `REVOKE UPDATE, DELETE` + `BEFORE UPDATE OR DELETE` trigger + `pg_partman.create_parent(..., p_interval := '1 day', p_premake := 3)`. Columns cover any declared parent, not only `uuid_padre`: `(uuid, uuid_sucursal, tabla, uuid_registro, tabla_padre, uuid_padre, datos JSONB, estado, buffered_at, expires_at)`. Partial index on `(tabla_padre, uuid_padre) WHERE estado='pendiente'`; index on `(expires_at)` for the sweep. |
| `0010_add_alert_types.py` | `prod.alert_types (tipo_alerta TEXT PK, descripcion TEXT, severity TEXT CHECK IN ('info','warning','critical'), created_at TIMESTAMPTZ)` + `REVOKE` + trigger. Seeded idempotently (`ON CONFLICT DO NOTHING`) on **both** cloud and branch. |
| `0011_add_catalog_triggers.py` | `fn_enqueue_sync_catalog` coverage for the 18 previously-untriggered `[V]` tables (D8-rev). Reads `SyncCatalogEntry.priority` only as an intra-level tie-break. |
| `0012_drop_infra_triggers.py` | Drop `fn_enqueue_sync` from `sync_log` and `sync_conflict` (D21). |
| `0013_add_seq_lookup_indexes.py` | Concrete per-table seq lookup support for D4. |
| — | **No `sync_back_events` migration.** Any reference must be deleted, not amended (D1-rev). |
| — | **No `reimpresion_ticket.origen` column.** It existed only for the withdrawn auto-reprint-on-sync-back rule (D1-rev). |

Every migration sets `lock_timeout` on its first statement and is dry-run
verified with `alembic upgrade --sql` before staging. Downgrade is exercised on
staging before merge.

### 9.3 ER canon amendment (a task must actually do this)

`modelo_datos_er.mmd` must gain two `%% [A]` entity blocks
(`sync_queue_lw_buffer`, `alert_types`) plus their relationship lines to
`sucursal`. **No task in the prior pass edited this file**, yet
`check_schema_match.py` and `check_table_counts.py` both gate on it, which made
the gate impassable. Required assertions afterward: 51 ER entities, 14 `[A]`
blocks, and `check_schema_match.py` exit 0 against 54 physical tables.

### 9.4 Drain check (before stage 4)

```sql
SELECT count(*) FROM prod.sync_queue WHERE estado='pendiente';
-- MUST return 0 within 2 * poll_interval_s after cutover
```

### 9.5 Project-canon corrections in `AGENTS.md` (required by D1-rev)

`AGENTS.md` still asserts the superseded numbering model and is read as canon by
every agent, so leaving it uncorrected would re-introduce the defect on the next
change. A task must apply these edits. **`AGENTS.md` is not edited by this
proposal phase.**

| Line | Current text (superseded) | Required correction |
|---|---|---|
| **113** | "**`empresa.consecutivo_actual`** is atomic in cloud; branches read via sync" | **Remove.** Replace with: "**Invoice numbering is branch-local**: `consecutivo` is assigned at the branch inside its own `resolucion_facturacion` range (`rango_desde`/`rango_hasta`); uniqueness comes from UK `(uuid_resolucion_facturacion, consecutivo)`. `empresa` has no `consecutivo_actual` column (removed in the 4NF pass)." |
| **208** | "Atomic `empresa.consecutivo_actual` mutated only in cloud" | **Remove.** Replace with: "The cloud validates the branch-assigned `consecutivo` against the resolution's authorized range and forwards the document to the DIAN provider (`envio_dian`, cloud-only); `cufe` and `estado` return to the branch through the ordinary `envio_dian` `cloud_to_branch` catalog entry." |
| **255** | risk row "DIAN `consecutivo_actual` race \| atomic UPDATE in cloud only; branches read via sync" | **Replace** with: "DIAN `consecutivo` collision \| one resolution per branch with a disjoint authorized range; UK `(uuid_resolucion_facturacion, consecutivo)`; the cloud rejects a document whose `consecutivo` falls outside the resolution range, and range exhaustion raises an `alerta`." |

**Three further lines carry the same superseded rule and must be corrected in the
same task** — the corrective brief named 113/208/255, but leaving these three
would keep the contradiction alive:

| Line | Current text | Required correction |
|---|---|---|
| **112** | "**DIAN-only tables** (`factura_electronica`, `revocacion_factura`) live ONLY in cloud; branches have schema parity but never write" | Contradicts the ER directly ("se emite **EN sucursal** con SU resolución"). Replace with: "`factura_electronica` and `revocacion_factura` are **emitted at the branch** and replicated `branch_to_cloud`; the cloud is the only egress point to the DIAN provider (`envio_dian`), which is cloud-only." |
| **205-207** | "`factura_electronica` and `revocacion_factura` written ONLY in cloud" / "Branch online mode: synchronous POST … returns real `numero_oficial`" / "Branch offline mode: prints `numero_temporal` (preliminar) … cloud assigns real and sends `SyncBackEvent` back; `reimpresion_ticket` enabled only after sync-back" | **Remove all three.** Replace with a single rule: "The branch emits and numbers locally, online or offline, with no behavioural difference; the cloud forwards to the provider asynchronously and the outcome returns via `envio_dian`. Reprint is never gated on a cloud round-trip." |
| **234-235** | "`preliminar` badge on `web_sucursal` until `SyncBackEvent` arrives" / "`reimpresion_ticket` disabled until `SyncBackEvent`" | **Remove both.** The document is final at emission. What may be pending is the DIAN acknowledgement, which is a status indicator on the document, not a gate on reprinting. |

### 9.6 Working-tree cleanup (tasks must be explicit about each)

| Path | State | Required action |
|---|---|---|
| `parkos_core/sync/table_registry.py` | untracked | **Discard.** Reflective auto-discovery (`pkgutil.walk_packages` + `inspect`) contradicts the declarative-catalog decision. It also registers the `sync_*` infrastructure tables, hardcodes `pk_column="uuid"`, and equates "branch-scopable" with "has `uuid_sucursal`", which breaks on the D19 NULL defaults. The catalog module replaces it entirely. Do not merge it. |
| `parkos_core/api/v1/sync_router.py` | modified, uncommitted | **Do not build on the uncommitted hunks.** The trial-and-error strategy lookup (`close_and_insert` then `append_event` inside an `except Exception`) is exactly what this change exists to delete. `SyncMotor` replaces it. |
| `parkos_core/jobs/sync_cloud.py` | modified, uncommitted | Same: ad-hoc `get_table()` routing and `branch_scopable` fan-out belong to the legacy emit loop. `SyncMotor` + `DependencyOrderer` replace them. |
| `backend/scripts/{insert_null_genesis,replicate_catalogs_to_branch,verify_branch_catalogs}.py` | untracked | Manual demo workarounds for the old pipeline, with hardcoded local DSNs. **Not part of this deliverable.** Leave untouched or ask the user to remove them; do not extend them. |
| `infra/scripts/seed_catalogs.py` | untracked | Keep as the idempotent-seed **pattern reference** for `seed_alert_types.py` only. It is not the catalog distribution mechanism — the catalog pipeline is (D8-rev). |
| `infra/deploy/.env.cloud` | untracked, **not ignored** | Add `infra/deploy/.env.*` to `.gitignore` before any staging under `infra/deploy/` (§9.1). |

### 9.7 Dual protocol grace period (D11 + R-D6 = 14 days)

The cloud `hello` endpoint returns:

```json
{ "protocol_version": "catalog", "min_branch_version": "1.5.0", "grace_until": "<+14d>" }
```

Branch auto-detects: `protocol_version == "legacy"` → legacy applier;
`"catalog"` and `version >= min_branch_version` → catalog applier. After the
grace period the cloud removes the legacy endpoints.

### 9.8 Reverse migration (D12)

```python
# openspec/scripts/reverse_sync_overhaul.py
# Idempotent: reverts catalog deployment + restores legacy behavior.
# 1. Set PARKOS_SYNC_ENGINE=legacy on all workers (D12 kill switch)
# 2. Wait sync_queue.pendiente == 0 (drain check)
# 3. Drain prod.sync_queue_lw_buffer (buffered rows re-enter the legacy path)
# 4. Disable the new endpoints; restore the legacy push/pull paths
# 5. Verify the chain verifier is still green
# NOTE: the new fn_enqueue_sync_catalog triggers on the 18 [V] tables are
# LEFT IN PLACE on rollback. Removing them would re-open the missing-catalog
# gap; the legacy applier tolerates the extra sync_queue rows.
```

## 10. Delivery Plan (chained PRs)

**Strategy**: feature-branch-chain for the cutover stages (per the
`create-49-table-apis` precedent); gitflow for pytest and the reverse migration.
Each PR ≤ 800 LOC.

| PR | Title | LOC est. | Gate to next |
|---|---|---|---|
| **PR1** | pytest scaffold + strict_tdd + role_guard + sync_queue AST check + `.gitignore` fix | ~280 | CI green |
| **PR2** | `SyncCatalog` skeleton + `LocalOnlyCatalog` + 46 + 3 entries declared, direction ratified (no motor yet) | ~750 | 80% coverage on catalog; count assertions 46/3/5/54 green |
| **PR3** | `depends_on` graph + `DependencyOrderer` + `check_catalog_drift.py` `depends_on`↔ER rule + DAG assertion | ~600 | Topological order verified against the ER; cycle detection tested |
| **PR4** | `SyncMotor` skeleton + `apply_row` + `apply_batch` + hooks registry | ~650 | Motor dispatches correctly per `apply_strategy`; parent validation precedes persistence |
| **PR5** | `IdentityReconciler` (D17) + `SubscriptionLifecycle` + `PlateChangeCascade` (re-targeted) + `BiTemporalCompensation` | ~700 | All four reconciliation branches (`noop`/`forward`/`historical`/divergent) tested; cascade closes junction rows |
| **PR6** | Hash chain: `LogTransaccionalChain` + `RevocacionFacturaChain` + verifier extension | ~550 | Verifier covers both tables; single-chain-per-`(tabla, uuid_sucursal)` asserted |
| **PR7** | `_read_local_seq` materialization (D4) — concrete per-table lookup | ~400 | Every `[V]` table produces a concrete seq; conflict tests pass |
| **PR8** | `RETRY(parent_missing)` + `sync_queue_lw_buffer` migration + TTL sweep + `alert_types` + single escalation path | ~700 | Orphan alerts within TTL; no `sync_queue` re-enqueue for dependency waits |
| **PR9** | DIAN path: delete the `sync_back_event` emit path; `envio_dian` as `cloud_to_branch`; range validation on receipt (D1-rev) | ~600 | Branch-emitted document reaches the provider and `cufe`/`estado` returns via `envio_dian`; zero `sync_back_event` rows anywhere |
| **PR10** | `fn_enqueue_sync_catalog` for the 18 `[V]` tables + drop infra triggers (D21) + ER `.mmd` amendment + count checks | ~600 | `check_schema_match.py` and `check_table_counts.py` exit 0 at 51/54 |
| **PR11** | Cloud-side worker switch: `job_sync_cloud` loops read the catalog | ~600 | Dual protocol active; metrics emit |
| **PR12** | Branch-side worker switch + initial topological backfill + `catalog_backfill_complete` gauge (R-D8) | ~650 | A freshly paired branch reaches full catalog coverage with zero unresolved parents |
| **PR13** | Observability: Prometheus counters + `sync_dependency_wait` + structured logs + alert rules | ~450 | Metrics exposed; alert rules tested |
| **PR14** | Cutover stage gates + reverse migration + `AGENTS.md` canon correction (§9.5) | ~500 | Reverse dry-run OK; no `consecutivo_actual` or `numero_temporal` reference survives anywhere in the repo |

**Task granularity directive for `sdd-tasks`.** Tasks inside each PR must be
**more atomic** than the prior pass. Each task is independently completable and
independently verifiable: one file, or one tightly coupled cluster (a migration
plus its own test), with one clear acceptance check. No task bundles unrelated
work such as "and also fix the catalog count and also update the ADR". Split any
task exceeding ~150-200 lines or touching more than 2-3 unrelated files into
ordered tasks with explicit dependencies. The PR grouping stays as a coherent
review slice; the granularity change is *within* each PR, and the corrected
scope should end with **more, smaller** tasks than the prior pass, not fewer.

## 11. Cutover Plan (D3 + D13 + D22 + R-D7)

Cloud-first, staged by service. Each stage passes only when the D10 / R-D7 gate
metrics hold for 24h continuous. Flag values per D22.

| Stage | Service | `PARKOS_SYNC_ENGINE` | Gate criteria (24h continuous) |
|---|---|---|---|
| **0 — Catalog skeleton** | All | `legacy` (no behaviour change; catalog declared) | CI green; catalog drift check green; `depends_on`↔ER green; DAG assertion green; reverse dry-run OK |
| **1 — api_admin reads catalog, applies legacy** | `api_admin` | `catalog_admin` | 0 `ImportError`; 0 5xx on the events endpoint; chain verifier 0 anomalies |
| **2 — DIAN path** | `dian/cloud/dispatcher` | `catalog_dian` | Zero rows with `operacion='sync_back_event'` anywhere; a branch-emitted `factura_electronica` is range-validated against its `resolucion_facturacion` and forwarded to the provider; `envio_dian` (`cufe`, `estado`) applies at the originating branch; **reprint remains available at the branch throughout, including with the cloud unreachable** |
| **3 — job_sync_cloud** | `jobs/sync_cloud` | `catalog` | Backlog < 1000; conflict rate < 0.5%; `sync_dependency_wait` draining (no row past TTL); chain verifier 0 anomalies; `sync_apply_total` emits per table |
| **4 — Branch cutover** | branch workers | `catalog_branch` | **R-D8**: `catalog_backfill_complete{uuid_sucursal}` = 1 for the branch before it advances; all `cloud_to_branch` entries applied in topological order with zero unresolved parents; offline login, pricing, and invoice emission verified with the cloud unreachable |
| **5 — Cleanup** | All | flag default = `catalog` | Legacy `fn_enqueue_sync` dropped from replicated tables (`fn_enqueue_sync_catalog` is now the source); infra triggers dropped (D21); rollback switch tested; drain check < 60s |

**Branch cutover ordering** (D3): branches follow the cloud by 7 days so the
cloud catalog stabilizes first. Stage 4's backfill gate is the direct control for
the failure that motivated this amendment: a branch is not considered cut over
until it demonstrably holds every catalog it needs to operate offline.

**Rollback** (D12): at any stage, set `PARKOS_SYNC_ENGINE=legacy`; workers fall
back to the legacy applier without restart (flag re-read every 60s). The drain
check runs automatically. The new catalog triggers stay in place on rollback
(§9.8).

## 12. Risks & Mitigations

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | Catalog drift from `modelo_datos_er.mmd` | HIGH | `check_catalog_drift.py`: every entry `name` resolves to an ORM class; exactly one catalog per table (now exception-free per D6-rev); exemption list is exactly the five names in §6.3; **direction and `broadcast_policy` re-derived from the ER class tag and `uuid_sucursal` presence and compared to the declared values** (D5-rev). Build fails on any mismatch. |
| **R2** | In-flight `sync_queue` rows during cutover lose seq interpretation | HIGH | D12 drain check; both protocols read `datos->>'seq'` identically during the overlap. |
| **R3-rev** | Initial catalog backfill floods a freshly paired branch | MEDIUM | Replaces the old R3 ("18 `[V]` tables suddenly replicate"), which described the *intended* behaviour as a hazard. The real risk is the one-time backfill burst. Mitigation: topologically ordered, paginated backfill with the `catalog_backfill_complete` gauge (R-D8) and a bounded page size; `[V]` catalogs are low-cardinality except `clientes` (see R18). |
| **R4** | `never_propagated` justifications rot into stale policy | LOW | Only one table keeps the strategy (D8-rev) and `justification` is required for it; CI asserts no other entry sets `never_propagated`. |
| ~~**R5**~~ | ~~DIAN `sync_back_event` leak into `sync_queue` after cutover~~ | — | **Removed.** `prod.sync_back_events`, the `sync_back_event` flag, the emitter hook, and the dispatcher emit loop no longer exist (D1-rev). There is nothing left to leak. The residual concern — legacy rows arriving during the grace period — is covered by D21 guard 2 (skip, do not `mark_failed`). |
| **R6** | Branch process imports a cloud-only entry → `ImportError` at boot | MEDIUM | R-D4 `assert_role`. **Scope narrowed**: only `validacion_evento` is `role_required='cloud'`. `envio_dian` is `role_required='both'` / `originating_role='cloud'` — the earlier catalog would have crashed branch boot on a table the branch must legitimately read. Tested in PR1. |
| **R7** | Test mocks do not see new hook callables | MEDIUM | D9 pytest from PR1; documented mock pattern injecting a trivial `HookResult(proceed=True)`. |
| **R8** | `sync_queue` carve-out enforcement regresses | MEDIUM | R-D3 AST check rejects `UPDATE`/`DELETE` on `SyncQueue` outside `repo/sync_queue.py`. CI gate. |
| **R9** | Offline login fails because `usuarios`/`permisos` arrive late | HIGH | These three tables sit at the root of the topological order and are part of the R-D8 backfill gate; a branch cannot be declared cut over until they are present. Integration test: authenticate and authorize with the cloud unreachable. |
| **R10** | Invoice numbering collides across branches after D1-rev | HIGH | One `resolucion_facturacion` per branch with a disjoint authorized range; UK `(uuid_resolucion_facturacion, consecutivo)`; the cloud rejects an out-of-range `consecutivo` on receipt; range exhaustion raises an `alerta`. This is the ER's own uniqueness mechanism, not a new one. |
| **R11** | Hash-chain verifier dual-walk doubles DB load | LOW | Single TX per tenant; walk order `log_transaccional` → `revocacion_factura`; per-tenant chain head cached for the sweep. Load test asserts < 5% overhead. |
| **R12** | Per-table `priority` misused for cross-table ordering | MEDIUM | Upgraded from LOW: the legacy values actively ordered `factura_pagos` ahead of `facturas`. D18 makes `depends_on` the only ordering mechanism; CI asserts `priority` is referenced nowhere in the ordering path. |
| **R13** | Dependency buffer grows unbounded on a persistent parent gap | MEDIUM | TTL per buffered row; sweep escalates to `alerta tipo_alerta='orphan_workflow_chain'`; `sync_dependency_wait` gauge alerts before the TTL. Single escalation path (D18) — no double-counting with `sync_queue` retries. |
| **R14** | Branch network partition leaves the worker applying out-of-order rows | MEDIUM | D18 dependency buffer + D16 degraded UI mode. With D1-rev the degraded surface shrinks: emission, numbering, and reprint all keep working offline; only DIAN acknowledgement visibility degrades. |
| **R15** | Test factory creates `[V]` rows with non-null `vigente_hasta` (defeats close+insert) | LOW | `VFixtureFactory` defaults `vigente_hasta=None`; coverage asserts all 26 `[V]` classes are exercised. |
| **R16** | Coverage gate blocks at 80% because some hooks are trivial | LOW | Threshold applies to `sync/{catalog,motor,hooks}/` combined; trivial hooks get parametrized multi-table tests. |
| **R17** | *(new)* Concurrent offline registration creates two open versions of one client or plate | HIGH | **D17** natural-key reconciliation with normalized comparison, plus a CI invariant test asserting at most one `vigente_hasta IS NULL` row per natural key in `clientes` / `clientes_b2b` / `vehiculos`. Divergent data is recorded as an informational `sync_conflict`, never as a blocking `MANUAL` — blocking a client registration would block the invoice. |
| **R18** | *(new)* `clientes` broadcast to `all_branches` grows past a practical branch-side volume | MEDIUM | `clientes` holds only *identified* clients (the ER states the occasional driver needs no row), so growth tracks invoicing and subscriptions, not entries. Mitigation now: paginated backfill, a `catalog_rows_total{tabla,uuid_sucursal}` gauge, and an alert threshold. Mitigation deferred (§14): a volume-bounded broadcast (clients with an active subscription or a recent invoice) if the gauge crosses the threshold. Chosen over an on-demand pull because on-demand breaks offline invoicing. |
| **R19** | *(new)* `depends_on` graph contains a cycle and the topological sort deadlocks | MEDIUM | Self-FK edges are marked `self_chain=True` and excluded from the sort; CI asserts the remaining graph is a DAG. A cycle raises at import time rather than at apply time — a programming error, not a runtime condition. |
| **R20** | *(new)* PII now crosses the branch↔cloud boundary in both directions on `clientes` | MEDIUM | Deliberate and required: the acquirer identity is part of the electronic document. Controls are TLS 1.3 in transit plus the `sync-agent-` JWT; the re-scoped redactor keeps PII out of `sync_log`, structured logs, and `sync_conflict` payloads (§8). Test fixtures use generated data only — no real PII in tests. |
| **R21** | *(new)* `AGENTS.md` keeps the superseded numbering rule and a later change re-derives from it | HIGH | This is how the original defect propagated. §9.5 lists the exact edits at lines 112, 113, 205-207, 208, 234-235, 255; PR14 gates on a repo-wide grep for `consecutivo_actual`, `numero_temporal`, `numero_oficial`, `sync_back_event`, and `SyncBackEvent` returning zero hits outside superseded-decision blocks. |
| **R22** | *(new)* A subscribed vehicle presents at a non-selling branch and the missing subscription reads as a data-sync fault | MEDIUM | Direct consequence of the §16 Q1 decision, and the reason it is recorded here rather than left implicit. Under `broadcast_policy=subscription` the non-selling branch legitimately holds no subscription row, so the lookup miss is the **correct** state, not a replication failure. Required behaviour: charge the standard tariff, and do **not** raise a sync alert, a `sync_conflict`, or a `RETRY(parent_missing)` for the absent subscription. Concretely: `ingreso.uuid_subscripcion_cliente` is optional, so it must never appear in `ingreso`'s `depends_on` (§6.4), or every occasional entry at a non-selling branch would buffer against a parent that will never arrive. `sdd-spec` must state the operator-facing wording ("no subscription at this branch"), which is distinct from "subscription expired". |

## 13. Success Criteria

- **A branch operates offline end to end**: authenticate, authorize, classify a
  vehicle, price a stay, register an identified client, emit and number an
  electronic invoice, and reprint a ticket — with the cloud unreachable. This is
  the outcome the amendment exists to deliver.
- **`catalog_backfill_complete{uuid_sucursal}` = 1** for every paired branch,
  with zero unresolved declared parents.
- **Apply success rate** ≥ 99.5% (`sync_apply_total{status="applied"}` over
  `sync_apply_total`, 7-day window).
- **Conflict rate** < 0.5% (same window).
- **Dependency waits drain**: no `sync_queue_lw_buffer` row exceeds its TTL over
  a 7-day window.
- **Hash-chain verifier** passes 100% — 0 anomalies across both
  `log_transaccional` and `revocacion_factura`, with exactly one chain per
  `(tabla, uuid_sucursal)`.
- **Identity invariant**: at most one `vigente_hasta IS NULL` row per normalized
  natural key in `clientes`, `clientes_b2b`, `vehiculos`.
- **pytest coverage** ≥ 80% line+branch for
  `parkos_core/sync/{catalog,motor,hooks}/`.
- **Catalog drift check green** — every entry resolves to an ORM class; exactly
  one catalog per table; direction and `broadcast_policy` match the ER
  derivation; `depends_on` matches the ER FK graph; the graph is a DAG.
- **Count assertions green** — `len(SYNC_CATALOG) == 46`,
  `len(LOCAL_ONLY_CATALOG) == 3`, `len(OUT_OF_CATALOG) == 5`, 51 ER entities, 54
  physical prod tables; `check_schema_match.py` and `check_table_counts.py` exit
  0.
- **`sync_queue` carve-out AST green** — no `UPDATE`/`DELETE` on `sync_queue`
  outside `repo/sync_queue.py`.
- **Role guard green** — branch processes boot without importing
  `role_required='cloud'` entries.
- **Zero survivors of the superseded model** — repo-wide grep for
  `consecutivo_actual`, `numero_temporal`, `numero_oficial`, `sync_back_event`,
  `SyncBackEvent` returns nothing outside explicitly-marked superseded-decision
  text.
- **Reverse migration** runs successfully in dry-run against staging.

## 14. Out of Scope (deferred)

- **Volume-bounded `clientes` broadcast** (only clients with an active
  subscription or a recent invoice) — deferred until the
  `catalog_rows_total{tabla}` gauge crosses its threshold (R18).
- **Identity alias / merge table** — D17 reconciles by natural key without one; a
  merge mechanism would require FK rewriting, which the no-UPDATE canon forbids.
- **Cloud-originated `[L-W]` workflows** (an admin opening a claim or a
  cancellation in the cloud on behalf of a branch) — the four branch-side `[L-W]`
  tables are `branch_to_cloud` in this change.
- **New repo helpers** — the existing `repo/*` layer is sufficient.
- **Auth chain changes** — JWT, pairing, and revocation are untouched.
- **WebSocket transport** — HTTP polling only.
- **DIAN provider swap** — this change only removes the invented sync-back path
  and adds range validation on receipt.
- **Frontend work for D16 degraded mode** and the removal of the `preliminar`
  badge / reprint gate — a separate change; §9.5 records the canon correction so
  the frontend change has a correct source to work from.
- ~~Per-table direction ratification (D14)~~ — **now in scope** (D14-rev).
- ~~Adding triggers for the 18 `[V]` tables (D8)~~ — **now in scope** (D8-rev).

## 15. Relevant Files (read by this proposal; NOT modified here)

**Canonical model** (the source of truth for §6):
- `modelo_datos_er.mmd` — 49 ER entities today, 51 after this change

**Sync surface**:
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (applied; not editable)
- `parkos_core/sync/conflict_resolver.py`
- `parkos_core/sync/table_registry.py` (untracked — to be discarded, §9.6)
- `parkos_core/sync/transport.py`
- `parkos_core/sync/auto_discovery.py`
- `parkos_core/sync/jwt_manager.py`
- `parkos_core/sync/router_helpers.py`
- `parkos_core/jobs/sync_cloud.py` (modified, uncommitted — §9.6)
- `parkos_core/jobs/sync_sucursal.py`
- `parkos_core/api/v1/sync_router.py` (modified, uncommitted — §9.6)

**Repo layer** (the motor dispatches here — unchanged):
- `repo/{sync_queue,sync_outbox,append_only,hash_chain,event,versioned,workflow,session_cycle,factura_pagos,pairing,revoked_sync_jwt}.py`

**DIAN**:
- `parkos_core/dian/cloud/dispatcher.py` (the `sync_back_event` emit path is deleted by PR9)
- `parkos_core/dian/cloud/dian_providers/factus.py` (build-time role-guard precedent)
- `parkos_core/dian/cloud_router.py`

**Models** (catalog references, unchanged):
- `parkos_core/models/base.py`, `parkos_core/models/{V,L_E,L_W,L_S,A}/*.py`

**Artifacts**:
- `openspec/changes/sync-overhaul/exploration.md`
- `openspec/changes/sync-overhaul/proposal.md` (this file)
- `openspec/changes/create-49-table-apis/{proposal,design,tasks}.md` (chained-PR precedent)

**Project canon**:
- `AGENTS.md` — **requires the corrections in §9.5**; a task must apply them
- `openspec/config.yaml`, `openspec/PROJECT_CONTEXT.md`
- `openspec/scripts/{check_schema_match,check_table_counts,check_catalog_drift}.py`

**Engram**:
- `sdd/sync-overhaul/decisions` (#1408 — the original 16 decisions; D1, D6, D8, D14 superseded here)
- `sdd/sync-overhaul/explore` (#1406), `sdd/sync-overhaul/explore/gaps` (#1407)
- `sdd/sync-overhaul/proposal` (this artifact)

## 16. Open questions for the user

These are business rules the ER does not settle. Q1 is **closed** by a product
decision; Q2 and Q3 have stated defaults so no phase is blocked, and confirming
or reversing either is a small, localized change.

**Q1 — Is a subscription honored at any branch, or only at the branch that sold
it? — CLOSED: only at the selling branch.**

*Decision.* A subscription is honored **exclusively at the branch that sold it**.
Both `subscripciones_cliente` and `subscripcion_vehiculos` therefore carry
`broadcast_policy=subscription`: the rows reach the selling branch and are not
broadcast network-wide (§6.1).

*Rationale.* This is a **deliberate business constraint, not a technical
limitation.** The customer returns to the branch where the plan was purchased in
order to use it. The ER's ambiguity — the `sucursal` relationship is labelled
"origen" (sales origin), and `ingreso.uuid_subscripcion_cliente` is an optional
FK with no constraint tying it to the entry's branch — is resolved in favour of
branch-scoped coverage. The mechanism is the `subscription` broadcast policy
rather than plain `single_branch` so that the junction, which has no
`uuid_sucursal` of its own, resolves through its parent's; declaring the same
value on both entries keeps the pair legible as one policy rather than two
coincidentally-aligned ones.

*Product consequence to carry downstream.* A subscribed vehicle presenting at a
**non-selling** branch is an ordinary occasional entry: that branch holds no
subscription row, so it must charge the standard tariff. This is the intended
outcome, and it needs a deliberate product behaviour rather than a silent
lookup miss — see the note in §12 R22.

**Q2 — Is `clientes` a single shared customer master, or per-operator?** *Default
taken*: a single shared master, since `clientes` has no `uuid_sucursal` and the
ER treats such tables as global. If a future multi-operator deployment must not
share customers, `clientes` needs a tenant discriminator, which is an ER change
outside this scope.

**Q3 — Should a divergent client record (same document, different name or email
from two branches) block or warn?** *Default taken*: warn — apply the later
version and write an informational `sync_conflict` (D17 step 4). Blocking would
stop an invoice at the counter over a typo in a phone number.
