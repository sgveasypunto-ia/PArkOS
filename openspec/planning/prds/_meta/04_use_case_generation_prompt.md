# Prompt: Build Parking-Lot Use Cases from Canonical Files

> A self-contained prompt that any LLM agent can execute to produce the
> complete set of use cases for the easypunto_parkos parking-lot management
> system. The prompt references the canonical files (model .mmd, PROJECT_CONTEXT,
> AGENTS, the 45 per-table PRDs, the 4 meta-PRDs) and enforces the domain rules
> (manual operator input, no cameras, multi-tenant cloud-edge topology).

---

## THE PROMPT (copy-paste ready)

```text
You are generating the **complete set of use cases** for the easypunto_parkos
parking-lot management system. Output is one PRD per table (T01..T45) and
the 4 meta-PRDs (`_meta/00_scaffold.md`, `01_models.md`, `02_jobs_queries.md`,
`03_apis_queries.md`). Each PRD's `## 7. Use Cases enabled by this table`
section must contain **concrete, end-to-end use cases** grounded in the
business operations of a real parking lot.

## Authoritative files you MUST consult (read ALL of them before writing)

1. **Data Model (source of truth for the schema)**
   - `E:\easypunto_parkos\modelo_datos_er.mmd` (1451 lines, 45 tables,
     AUDIT-FIRST architecture with 3 enforcement levels `[V|L-E|L-W|L-S|A]`,
     all FK relationships declared in the `%% RELACIONES` section)

3. **Project Context**
   - `E:\easypunto_parkos\openspec\PROJECT_CONTEXT.md` (assumed stack,
     multi-tenant cloud-edge topology, DIAN compliance, ASSUMED pre-SDD)

5. **Stack / Conventions**
   - `E:\easypunto_parkos\AGENTS.md` (Python 3.13 + FastAPI + SQLAlchemy 2.0
     async + Alembic + React 18 PWA + shadcn/ui + Docker Compose; JWT
     three-issuer model: admin / operador / sync_agent)

7. **Roadmap**
   - `E:\easypunto_parkos\openspec\_meta\roadmap.md` (7 phases, 14 PRs total)

9. **Iteration Plan**
   - `E:\easypunto_parkos\openspec\_meta\iteration-plan.md` (Foundation F1+F2
     + IT-1..IT-12 vertical slices)

11. **Meta-PRDs (shared docs cited by every PRD)**
    - `E:\easypunto_parkos\openspec\planning\prds\_meta\00_scaffold.md`
    - `E:\easypunto_parkos\openspec\planning\prds\_meta\01_models.md`
    - `E:\easypunto_parkos\openspec\planning\prds\_meta\02_jobs_queries.md`
    - `E:\easypunto_parkos\openspec\planning\prds\_meta\03_apis_queries.md`

13. **Shared PRD docs (cited by every PRD)**
    - `E:\easypunto_parkos\openspec\planning\prds\_shared\uuid-v4-strategy.md`
    - `E:\easypunto_parkos\openspec\planning\prds\_shared\solid-principles.md`
    - `E:\easypunto_parkos\openspec\planning\prds\_shared\fk-naming-convention.md`
    - `E:\easypunto_parkos\openspec\planning\prds\_shared\workflow-chains.md`
    - `E:\easypunto_parkos\openspec\planning\prds\_shared\layer-impact-map.md`
    - `E:\easypunto_parkos\openspec\planning\prds\_shared\references.md`

15. **Existing PRDs (in `openspec\planning\prds\NN_<table>.md`)**
    - Use them as templates for structure; **rewrite the use-cases section**
      to be domain-driven (parking-lot operations) instead of generic CRUD.

## Domain Rules (HARD CONSTRAINTS — never violate)

1. **NO cameras, NO OCR, NO automatic plate recognition, NO QR scanners**.
   All input is **manual** by a human operator at the booth or admin UI.

3. **Multi-tenant cloud-edge topology**:
   - Cloud admin (single) ↔ many branch Postgres (one per parking lot).
   - Each branch has its own operator UI (`web_sucursal`) and its own DB.
   - Cloud has admin UI (`web_admin`) and aggregates all branches.
   - Sync via `sync_queue` (branch → cloud) + parametrization pull (cloud → branch).
   - DIAN processing is **cloud-only**.

5. **Manual operator workflow** (replace any previous "camera/OCR" assumption):
   - Operator at the booth **types the plate** into `IngresoForm`.
   - Operator **selects** vehicle type (`tipos_vehiculo`) from dropdown.
   - Operator **selects** whether the customer has a subscription OR is a casual visitor.
   - If subscriber: operator **searches by customer cedula** (not by QR); the system displays matching `vehiculos` for the subscription; operator picks one.
   - If casual: operator proceeds to charge the visitor's vehicle when they leave.
   - Operator **manually triggers** all actions (no automation).

7. **Offline-first branch behavior**:
   - Each branch may operate offline (internet down).
   - On ingreso/salida/facturacion: branch writes locally first.
   - Each write enqueues to `sync_queue` for eventual sync to cloud.
   - For DIAN numbering: branch tries cloud first; on failure uses
     `numero_temporal` (`PRE-<8-char-uuid>`); SyncBackEvent fills real
     number when cloud processes.

9. **DIAN compliance (cloud-only)**:
   - `empresa.consecutivo_actual` atomic in cloud.
   - `factura_electronica` written ONLY in cloud (branches never write).
   - `revocacion_factura` written ONLY in cloud (with hash chain).

11. **Hash chain tables** (DIAN audit):
    - `log_transaccional` and `revocacion_factura` use SHA256 hash chain
      per `uuid_sucursal`.
    - Cloud preserves branch chain verbatim, only extends with cloud-originated rows.

## The Parking-Lot Domain — Business Operations

A real parking lot operates as follows. **Your use cases must reflect these.**

### Operator flow (branch side)

- **Arrival**: Operator types plate → selects vehicle type → if subscriber,
  searches customer by cedula → picks vehicle → system records ingreso →
  prints ticket (numero_temporal if offline, numero_oficial if online) →
  barrier opens.
- **During stay**: nothing (vehicle is parked).
- **Departure**: Operator scans barcode or types plate → system finds the
  ingreso → calculates cost (duration × tariff × vehicle type) → operator
  selects payment method(s) (efectivo / datafono) → system creates business
  factura + e factura (online → real number, offline → numero_temporal) →
  barrier opens → optionally operator clicks "Reimprimir" to print a clean
  copy (gated on uuid_factura_electronica populated).
- **Cash session**: Operator opens sesion at start of shift with initial
  cash → during shift, cash accumulates in caja snapshots → at end of
  shift, operator closes sesion, enters expected vs reported totals,
  system computes diferencia and creates arqueo; if diferencia exceeds
  tolerancia → alerta.

### Admin flow (cloud side)

- **Branch onboarding**: Admin creates sucursal in `web_admin` → issues
  pairing token → sends to branch operator → operator enters in
  PairingWizard → branch receives long-lived sync_agent JWT → parametrization
  sync begins.
- **Parametrization**: Admin manages catalogs (vehicles, taxes, tariffs,
  subscriptions, clients) in `web_admin`; cloud pushes parametrization to
  branches via parametrization pull.
- **Audit review**: Admin opens AuditDashboard; queries
  log_transaccional; investigates hash chain breaks via alertas.
- **Reports**: Admin views FacturasList cross-branch; arqueos history;
  alertas open; sync_log metrics.
- **Annullment**: Operator at branch requests anulación via web_sucursal;
  admin approves + executes via web_admin.

### Subscription flows

- Admin creates subscripcion for a cliente at a sucursal with one or more
  vehiculos.
- When a subscriber arrives, operator finds the subscription by cliente
  cedula; the ingreso is linked to the subscription and the bill is not
  generated at departure (instead, the subscription is consumed).

### Workflows (chain-driven)

- `anulaciones` (`[L-W]`): solicitada → aprobada → ejecutada.
- `reclamos` (`[L-W]`): abierto → en_revision → resuelto/rechazado.
- `alerta` (`[L-W]`): abierta → en_revision → resuelta.
- `reimpresion_ticket` (`[L-W]`): cobrada → anulada.

## Required Output Structure (for every PRD)

Each PRD's `## 7. Use Cases enabled by this table` section must include:

1. **At least 3 end-to-end use cases** that explain how a real parking-lot
   operator/admin interacts with this table.

3. **Each use case** must be written as:
   ```
   ### 7.X Use Case: `uc.<table>.<kebab-case-name>`

   <one sentence summary in plain Spanish/Spanglish describing the real-world
    parking-lot action this enables>

   **Actor**: <operator | admin | system | sync worker | dian_dispatcher | verifier>

   **Steps**:
   1. <concrete action in the operator UI / API / sync>
   2. <backend writes/reads>
   ... (5-10 steps)

   **Tables touched (writes/reads)**: <list with W/R per table>

   **FKs traversed**: <list incoming + outgoing FKs involved>

   **Sync behavior**:
   - Branch → cloud: <yes/no, when, what gets queued>
   - Cloud → branch: <yes/no, when, what gets pulled>
   - DIAN trigger: <yes/no, when>
   - Hash chain impact: <yes/no, when>

   **Integration with other tables**:
   - Reads from: <other tables this case reads from>
   - Writes to: <other tables this case writes to via cascade or workflow>
   ```

5. **Coverage rule**: between the 45 per-table PRDs, EVERY business operation
   of a parking lot must be covered. The mapping is:
   - Branch operator: arrival, departure, cash session, subscription lookup,
     reimprimir, reclamar.
   - Branch admin (operator-level): nothing (operators do CRUD only via
     cloud or via parametrization).
   - Cloud admin: parametrization, branch onboarding, audit, reports,
     annulment, alerts review.
   - System (sync worker): drain outbox, push to cloud, pull from cloud,
     DIAN dispatch, hash chain verifier.
   - DIAN provider (cloud-only): e-factura generation, CUFE, QR.

## Special Patterns to Use in Use Cases

### Pattern A: Sync-aware operation
When a branch operation creates a row that must reach cloud:

```text
7.X Use Case: `uc.<table>.<action>`
**Actor**: operator
**Steps**:
1. Operator opens <Form>, fills fields
2. Frontend POSTs `api_sucursal /<table>` with payload
3. Backend: bcrypt verify, tenant check, INSERT <table>, INSERT
   `log_transaccional`
4. `queue_processor.enqueue('<table>', uuid, datos)` → INSERT `sync_queue`
5. (Optional) Cloud call: backend POSTs `api_admin /<endpoint>` for
   cloud-side processing (e.g., DIAN)
6. (Optional) SyncBackEvent: cloud emits; branch polls; updates local
   `numero_oficial`
7. Return {uuid, ...} to frontend
**Tables touched**: <table> (W), `log_transaccional` (W), `sync_queue` (W)
**FKs traversed**: uuid_sucursal (mandatory), uuid_<X> (FKs from payload)
**Sync behavior**:
- Branch → cloud: yes, queue → push within 30s
- Cloud → branch: yes, if SyncBackEvent, poll within 30s
- DIAN trigger: yes/no
- Hash chain impact: yes (log_transaccional row written)
**Integration with other tables**: 
- Reads from: <catalog tables like tipos_vehiculo, tarifas_sucursal>
- Writes to: <cascade tables like log_transaccional, sync_queue>
```

### Pattern B: DIAN cloud-only flow
When a branch facturacion triggers cloud DIAN:

```text
7.X Use Case: `uc.factura.online-dian-process`
**Actor**: operator (triggers), cloud (processes)
**Steps**:
1. Branch operator POSTs `api_sucursal /facturas` with items + payments
2. Branch backend: INSERT `facturas` (without `numero_oficial`),
   INSERT `factura_detalle` lines, INSERT `factura_pagos`, INSERT
   `factura_impuestos` (snapshot from `impuestos`), INSERT
   `factura_otros_cobros` (snapshot from `otros_cobros`), INSERT
   `log_transaccional`
3. Branch backend: cloud `api_admin /facturas/procesar` (online mode)
4. Cloud: SELECT `empresa` FOR UPDATE; `consecutivo_new =
   consecutivo_actual + 1`; INSERT `factura_electronica` with
   `consecutivo=$consecutivo_new, numero_oficial=...`
5. Cloud: enqueue `dian_dispatcher` to send to DIAN provider
6. Cloud: INSERT `SyncBackEvent` (or returns directly)
7. Branch: receives `numero_oficial`, updates local `facturas`
8. Operator prints with real number
**Tables touched**: `facturas`, `factura_detalle`, `factura_pagos`,
`factura_impuestos`, `factura_otros_cobros`, `log_transaccional`,
`empresa`, `factura_electronica`, `SyncBackEvent`
**Sync behavior**:
- Branch → cloud: yes (queue)
- Cloud → branch: yes (SyncBackEvent)
- DIAN trigger: yes (dian_dispatcher)
- Hash chain impact: yes (log_transaccional + factura_electronica chain)
```

### Pattern C: Workflow chain transition
When a `[L-W]` table transitions:

```text
7.X Use Case: `uc.<workflow>.<step>`
**Actor**: <admin or operator>
**Steps**:
1. Actor clicks `<transition>` in web_<admin/sucursal>
2. Frontend POSTs `api_<admin/sucursal> /<workflow>/<uuid>/<transition>`
3. Backend: SELECT latest chain row from `<workflow>`
4. INSERT new chain row with `uuid_padre=$latest, estado=$new_state`
5. INSERT `log_transaccional`
6. `queue_processor.enqueue` (branch→cloud) or parametrization pull
   (cloud→branch)
**Tables touched**: `<workflow>` (W new row), `log_transaccional` (W)
**Sync behavior**:
- Branch → cloud: yes (when transition happens at branch)
- Cloud → branch: yes (when transition happens at cloud)
```

## Quality Gates

Before finalizing each PRD's `## 7. Use Cases enabled by this table`, verify:

1. ✅ All use cases are grounded in real parking-lot operations
   (operator / admin / system / sync / DIAN), NOT generic CRUD.
2. ✅ Every use case has **Actor**,** **Steps**, **Tables touched**,
   **FKs traversed**, **Sync behavior**, **Integration**.
3. ✅ At least one use case per table covers **branch-side** action.
4. ✅ At least one use case per table covers **cloud-side** action
   (when applicable — for `[V]` parametrization tables, cloud is primary).
5. ✅ Sync behavior is documented: branch→cloud? cloud→branch?
   DIAN trigger? hash chain impact?
6. ✅ Integration with related tables via FKs is enumerated.

## Execution

For EACH of the 45 per-table PRDs (`openspec/planning/prds/01_log_transaccional.md`
through `45_salidas.md`) AND the 4 meta-PRDs (`_meta/00_scaffold.md` through
`_meta/03_apis_queries.md`), REWRITE the `## 7. Use Cases enabled by this table`
section to comply with this prompt. Preserve all other sections.

Verify that every business operation of a parking lot is covered by at
least one use case across all 49 PRDs.

```

---

## How to use this prompt

1. **For a single PRD**: paste the prompt above into another LLM session
   along with the canonical files. Ask it to rewrite the `## 7. Use Cases`
   section of one specific PRD (e.g., `04_ingreso.md`).

2. **For all 49 PRDs in batch**: use the prompt in a loop:
   ```bash
   for prd in openspec/planning/prds/{_meta/,}*.md; do
     echo "--- Processing $prd ---"
     # Run the prompt with $prd as target
   done
   ```

3. **For consistency**: after all 49 PRDs are rewritten, run a final
   consistency check that confirms every parking-lot operation
   (arrival, parking, facturacion, cierre, etc.) is covered by at least
   one use case in at least one PRD.

## Why this prompt works

- **Grounded**: every use case MUST cite specific tables and FKs from
  the canonical model. No hallucination.
- **Domain-driven**: forces the LLM to think as a parking-lot operator,
  not as a generic CRUD author.
- **Sync-aware**: every use case documents branch↔cloud behavior explicitly.
- **Quality-gated**: explicit verification checklist before finalizing.
- **Reusable**: same prompt works for any per-table PRD with minor
  adjustments to the `Tables touched` lists.

---

## Validation: parking-lot operations covered by the 49 PRDs

After running this prompt across all PRDs, the following operations MUST
be covered (count of use cases listed per operation):

| Operation | Expected # of use cases | Expected PRDs |
|---|---|---|
| Branch operator: arrival / ingreso | 3+ | T04 ingreso, T03 (vehiculos lookup), T20 vehiculos |
| Branch operator: subscription lookup by cedula | 2+ | T16 clientes, T18 subscripciones_cliente, T20 vehiculos |
| Branch operator: departure / salida | 3+ | T45 salidas, T05 facturas, T36 factura_pagos |
| Branch operator: cash session apertura | 2+ | T43 sesion, T33 caja |
| Branch operator: cash session cierre / arqueo | 3+ | T43 sesion, T34 arqueo, T29 configuracion_tolerancias, T41 alerta |
| Branch operator: reimprimir ticket | 2+ | T38 reimpresion_ticket, T05 facturas (gate) |
| Branch operator: claim / reclamo | 2+ | T40 reclamos |
| Branch operator: anulación request | 2+ | T39 anulaciones, T04 ingreso |
| Admin: branch onboarding / pairing | 2+ | T11 sucursal, T10 usuarios_sucursal |
| Admin: parametrization of catalogs | 3+ | T13 documentos, T14 tarifas_sucursal, T23 tipos_vehiculo, T26 impuestos |
| Admin: client / subscripcion management | 2+ | T16 clientes, T18 subscripciones_cliente |
| Admin: anular approve / execute | 2+ | T39 anulaciones |
| Admin: alert review | 2+ | T41 alerta |
| Admin: report generation | 2+ | T05 facturas, T33 caja |
| Admin: audit hash chain verifier | 1+ | T01 log_transaccional |
| System: branch sync outbox | 2+ | T06 sync_queue, T31 sync_log |
| System: cloud sync push from branch | 2+ | T06 sync_queue, T03 factura_electronica |
| System: cloud parametrization pull | 1+ | T11 sucursal (or catalog T23..T30) |
| System: DIAN dispatch | 2+ | T03 factura_electronica, T02 revocacion_factura |
| System: hash chain verifier | 1+ | T01 log_transaccional, T02 revocacion_factura |
| System: branch-offline detection | 1+ | T41 alerta |
| System: sync_conflict detection | 1+ | T32 sync_conflict |

If any row is missing or has 0 use cases, re-run the prompt on the
corresponding PRD with explicit focus on that operation.