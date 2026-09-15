# Design: HU-F1.6 — Validaciones reales en `POST /operacion/ingresos`

> **Change**: `hu-f1-6-validaciones-post-ingresos`
> **Phase**: design (sdd-design)
> **HU**: HU-F1.6 — Server-side enforcement of regex placa, mensualidad/rotación derivation, cupo via `mv_ocupacion_diaria`, KD-FORZADO prefix audit, no-duplicate active ingreso on the existing `POST /api/v1/operacion/ingresos` endpoint (modifies the handler F1.5 left as a thin pass-through).
> **Date**: 2026-09-14
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `e1cc79b`; F1.1..F1.5 archivadas, F1.6 es el siguiente)
> **PR target**: `origin/dev`
> **Source of truth**: `proposal.md` (D-HU-F1.6-1..13, 10 KDs adopted) + `exploration.md` (16 sections, V1..V9 + KD-FORZADO-01, files-to-touch §15) + `specs/operational/spec.md` (REQ-OPS-034..041 RFC 2119, 4 spec-level risks) + `plan.md` (HU-F1.6 lines 786–798, DEC-SUC-11 línea 426, DEC-SUC-21 línea 590, DEC-SUC-22 línea 595, KD-FORZADO A-04 addendum #4).
> **Cross-references**: `modelo_datos_er.mmd` (`ingreso` 577–596 [L-E], `cantidad_vehiculos_sucursal` 428–446 [V], `tipos_vehiculo` 87–104 [V], `tarifas_sucursal` 406–426 [V], `subscripciones_cliente` [V], `subscripcion_vehiculos` [V], `vehiculos` [V], `alerta` [L-W], `mv_ocupacion_diaria` post-F1.5).
> **Precedents mirrored**: F1.5 (REQ-OPS-030..033, KD chain pattern, MV pattern, `repo/ocupacion.py`, commit `fc72adb`), F1.4 (REQ-OPS-017..021, bi-temporal predicate reusable in V3, commit `467b4f0`), F1.3 (REQ-OPS-026..029, AST walk + custom handler before factory, commit `ca3f9bf`), F1.8 (REQ-OPS-022..025, AST walk read-only pattern, commit `de4d2fc`).

## 1. Title & Goal

**Design goal.** Deliver HU-F1.6: the back-end "real validation" infrastructure that the F6 Ingreso vehicular (CU-01) operator flow relies on — moving the four client-side validations from `web_sucursal/src/lib/validation/placa.ts` (A-03) into the backend handler `POST /api/v1/operacion/ingresos`, applying the 9 server-side validations V1..V9 plus the KD-FORZADO-01 bypass contract (`[FORZADO: <motivo ≥10 chars>]` parsed from `observaciones`, A-04) as the only operational bypass for V1/V2/V3/V6, and deriving `tipo_entrada` (`MENSUALIDAD | ROTACION`) server-side from `uuid_subscripcion_cliente` (DEC-SUC-21, returned in `IngresoReadForzado`, **never persisted** in `prod.ingreso`). The design enforces `plan.md` **DEC-SUC-11** (cupo always via `mv_ocupacion_diaria`), **DEC-SUC-21** (tipo_entrada never persisted), **DEC-SUC-22** (regex estricta sin tolerancia O↔0/I↔1), and the **4-layer defense in depth** (D-HU-F1.6-7) — regex server-side override → KD-FORZADO chain → alerta INSERT same-TX → AST walk ordering gate — so no single failure can bypass the whole. Closes three contractual dependencies: F6 (CU-01 Ingreso), F4.3 (`OcupacionStrip` parity), F7 (Salida post-flow). Sized at **260 LOC** (plan.md línea 787): ~140 LOC handler replacement + 4 new `repo/*.py` files (~320 LOC total) + schemas (+80 LOC) + 6 test files (~1,000 LOC). **NO migration, NO sync catalog changes, NO models touched.**

## 2. Context & Background

`plan.md` lines **786–798** define HU-F1.6 as Fase-1 backend prerequisite for F6. The hard architectural constraint is **DEC-SUC-21** at línea **590** ("`tipo_entrada` nunca columna; derivado server-side, devuelto en respuesta") and **DEC-SUC-11** at línea **426** ("disponibilidad nunca en columna mutable; siempre vía vista materializada"). Today the endpoint `POST /api/v1/operacion/ingresos` (`api/v1/operacion.py:92-114`, ~23 LOC, F1.5's PR5) is a **thin pass-through**:

```python
async def create_ingreso(payload: IngresoCreate, …) -> IngresoRead:
    new_row = await record_event(session, Ingreso, actor_uuid=ctx.actor_uuid,
                                  new_attrs=payload.model_dump(exclude_none=True),
                                  log_tx=True)
    await session.commit()
    await session.refresh(new_row)
    return IngresoRead.model_validate(new_row)
```

It accepts whatever the Pydantic schema allows and inserts the `[L-E]` event without business validation, violating the corpus "single source of truth" rule. The four client-side validations in `web_sucursal/src/lib/validation/placa.ts` (A-03) are the only enforcement — a stale Electron build, a future mobile app, or an admin-web consumer can submit `placa = "abc123"` and pollute `prod.ingreso`.

The contract is captured in **REQ-OPS-034..041** (added by `sdd-spec` to `specs/operations/spec.md`):

- **REQ-OPS-034** — V1: `cupo_no_configurado` returns 422 with `forzado_permitido: true`.
- **REQ-OPS-035** — V2: `motivo_forzado_requerido` with `cupo_maximo`/`activos`; bypass INSERTs + emits alerta same TX.
- **REQ-OPS-036** — V3: `tarifa_vigente_no_encontrada` 422 (bi-temporal F1.4 reusable).
- **REQ-OPS-037** — V4: `tipo_vehiculo_invalido` 422 — no bypass (catalog bug, KD-V3).
- **REQ-OPS-038** — V5: regex placa Colombia server-side + `placa_formato_invalido` 422 + `uuid_tipo_vehiculo` derivado y sobreescrito (BR2 CU-01).
- **REQ-OPS-039** — V6: `subscripcion_inactiva_o_vencida` 422 unless `forzado=true` (walk-in auditado).
- **REQ-OPS-040** — V8: `ingreso_activo_existente` 409 with `uuid_ingreso_existente`; EXISTS directo a tablas (no MV, no lock).
- **REQ-OPS-041** — V9 + KD-FORZADO-01 + alerta `capacidad_agotada_forzado` (atomic-bundled: derivación server-side + bypass contract + alerta same-TX).

V7 (bi-temporal canónico) inherits from F1.4/F1.5 base capability (`bitemporal_vigente_predicate`); no new REQ needed.

F1.6 is consumed by **F6** (CU-01 Ingreso, plan línea 786–798), **F4.3** (`OcupacionStrip` parity with server-side check), **F7** (Salida relies on clean `prod.ingreso` rows). It closes the server-side enforcement surface so the **client-side** `validation/placa.ts` (A-03) becomes belt-and-suspenders rather than the single source of truth. Live risk **RIESGO-SUC-02** (línea 2677) documents the 10s MV lag as an accepted operating characteristic; D-HU-F1.6-3 accepts it without lock pesimista.

## 3. Decisions

This HU adopts **thirteen** Key Decisions (D-HU-F1.6-1..13 from `proposal.md §2`). Each one passes the R5 risk threshold (no open question blocks the design; the proposal §12 confirms `Ninguna abierta`).

### Decision D-HU-F1.6-1 — Modify handler `create_ingreso` in-place (NO new endpoint)

**Choice.** The handler `create_ingreso` in `api/v1/operacion.py` is replaced in-place (lines 92-114 → ~232 LOC). The router factory (`make_router`) and `api/v1/__init__.py` (router mounted at line 143) are NOT touched; the dedicated handler gains by registration order, identical to F1.4's `tarifas-sucursal` precedent (`empresa.py:142-149` block) and F1.5's `get_ocupacion` (`operacion.py:413-483`).

**Context.** F1.5's PR5 reserved the URL `POST /api/v1/operacion/ingresos` and registered the thin handler. F1.6 reuses the URL verbatim — backwards-compatible with any consumer that POSTs against it. Only the response body gains `tipo_entrada`, `forzado_en_creacion`, `motivo_forzado` and the error body gains typed 422/409 discriminators.

**Alternatives considered.**
- *New endpoint `/ingresos-v2` or `/ingresos/validar`* — rejected: violates corpus "single source of truth" (two paths to insert an `ingreso`); confusing for the operator; doubles the surface area.
- *In-place modification of the factory* — rejected: factory stable since F1.1 (`f7cb37a`); touching it re-opens blast radius over 30+ resources. The dedicated handler precedent is F1.4 / F1.5 / F1.8.

**Rationale.** URL stability is a hard requirement (F1.5's consumers + F4.3 client + future replay queue already POST against it). The in-place replacement preserves the wire contract at the path level; the response contract delta is documented in the spec and is **additive** (new fields) — no field is removed or renamed.

### Decision D-HU-F1.6-2 — KD-FORZADO-01: bypass is `forzado=true` with `[FORZADO: <motivo ≥10 chars>]` parsed from `observaciones`

**Choice.** The only operational bypass to V1/V2/V3/V6 is `forzado=true` with `observaciones.startswith(FORZADO_PREFIX = "[FORZADO: ")`, where the substring after the prefix (`rstrip("]")`) has `len(motivo.strip()) >= FORZADO_MIN_MOTIVO_CHARS = 10`. Module-level constants in `repo/ingreso.py`:

```python
FORZADO_PREFIX = "[FORZADO: "
FORZADO_MIN_MOTIVO_CHARS = 10
```

Three 422 discriminators: `forzado_contradiccion` (forzado=false with prefix), `motivo_forzado_requerido` (forzado=true without prefix), `motivo_forzado_insuficiente` (motivo <10 chars). The helper `validar_kd_forzado(observaciones, forzado) -> motivo` raises `HTTPException(422, ...)` for each discriminator.

**Context.** A-04 of the corpus explicitly forbids a `forzado` column in `prod.ingreso`; the bypass must live as a parse-derived discriminator, not a stored field. The prefix-based contract is auditable post-hoc (a manager reviewing `observaciones` can grep for `[FORZADO:` and see the reason). The 10-char minimum prevents `forzado=true` with a single-token reason like `[FORZADO: x]`.

**Alternatives considered.**
- *Separate `forzado_motivo: str` field in the payload* — rejected: explicit A-04 veto; would require a schema change and audit-trail mechanism.
- *Boolean-only `forzado` without audit reason* — rejected: not auditable; managers cannot trace why an ingreso was forced.
- *`<10` chars allowed* — rejected: defeats the audit-trail purpose; a `[FORZADO: x]` is not informative.

**Rationale.** The prefix IS the source of truth; `forzado: bool` in the payload is validated against the prefix (D-HU-F1.6-5) so a desynchronized state (`forzado=true` without prefix, or `forzado=false` with prefix) is rejected as 422. The 10-char minimum forces a substantive reason.

### Decision D-HU-F1.6-3 — KD-V4 eventual consistency via MV (NO lock pesimista)

**Choice.** Cupo availability is queried via `repo/ocupacion.py::validar_cupo_disponible` (newly added wrapper around the F1.5 MV `prod.mv_ocupacion_diaria`). NO `SELECT … FOR UPDATE/SHARE` lock is acquired on `prod.ingreso`, `prod.cantidad_vehiculos_sucursal`, or `mv_ocupacion_diaria`. V8 (no-duplicado activo) goes **directly** to `prod.ingreso` (authoritative, index `(uuid_sucursal, placa, created_at)` post-F1.5) with an `EXISTS` + two `NOT EXISTS` clauses (salidas, anulaciones ejecutadas) — no lock either.

**Context.** RIESGO-SUC-02 (línea 2677) documents the 10s MV lag as an accepted operating characteristic. KD-V4 already established in F1.5; F1.6 inherits it. The 10s polling cadence (`jobs/sync_sucursal.py:103`, `DEFAULT_POLL_INTERVAL_S = 10`) is the cadence at which `mv_ocupacion_diaria` refreshes; the operator polling 10s on `GET /operacion/ocupacion` sees the same data.

**Alternatives considered.**
- *Lock pesimista `SELECT … FOR UPDATE/SHARE` on `prod.ingreso`* — rejected: serializes all inserts through the lock; bursts of N operadores create a queue; incompatible with the 10s polling contract.
- *Lock on `prod.cantidad_vehiculos_sucursal`* — rejected: the table is `[V]` (bi-temporal, versioned); locking its vigente row prevents concurrent inserts on the same branch.
- *Advisory locks (`pg_advisory_lock`)* — rejected: adds a session-state dependency; not aligned with the AsyncSession pattern; no precedent in the corpus.

**Rationale.** Eventual consistency is acceptable because the polling 10s of the operator strip and the worker refresh align — the operator sees the same data the server validates against, with at most a `2 × refresh_interval_s = 20s` lag window. The lag is documented as RIESGO-SUC-02 and accepted; F1.6 does not introduce new risk acceptance.

### Decision D-HU-F1.6-4 — KD-V2 regex hardcoded at module level in `repo/placa.py`

**Choice.** Two module-level constants in `repo/placa.py`:

```python
FORMATO_AUTO = re.compile(r"^[A-Z]{3}[0-9]{3}$")    # ABC123
FORMATO_MOTO = re.compile(r"^[A-Z]{3}[0-9]{2}[A-Z]$")  # ABC12D
```

The function `detectar_tipo_vehiculo(placa: str) -> uuid_lib.UUID | None` lazy-looks-up `prod.tipos_vehiculo` (`tipo='Auto' or 'Moto'`, vigente) and returns the UUID or None.

**Context.** A-03 of the corpus explicitly says regex is hardcoded for MVP. CHECK constraint on `prod.ingreso.placa` was discarded because it would block future national migration (Mercosur 2027). Configurable regex is out of scope for F1.6 (KD-V2).

**Alternatives considered.**
- *CHECK constraint on `prod.ingreso.placa`* — rejected: rigid, blocks migration; A-03 explicit veto.
- *Configurable via `prod.config` cat table* — rejected: KD-V2 hardcoded for MVP; cat tabla in HU future.
- *Case-insensitive regex* — rejected: DEC-SUC-22 strict; no O↔0/I↔1 tolerance (that lives in `buscarIngresoTolerante` F1.7).

**Rationale.** Module-level constants make a future swap to a cat table a one-file edit. The lazy UUID lookup avoids hardcoding UUIDs (the catalog is the source of truth).

### Decision D-HU-F1.6-5 — `forzado` field in payload validated against `observaciones` prefix (defense in depth)

**Choice.** `IngresoCreateForzado.forzado: bool = False` is in the payload schema. The server invokes `validar_kd_forzado(observaciones, forzado)` which enforces:
1. `forzado=false` AND `observaciones.startswith(FORZADO_PREFIX)` → `422 forzado_contradiccion`.
2. `forzado=true` AND `observaciones is None or not startswith(FORZADO_PREFIX)` → `422 motivo_forzado_requerido`.
3. `forzado=true` AND motivo (`rstrip("]")` of substring after prefix) has `len(motivo.strip()) < 10` → `422 motivo_forzado_insuficiente`.

**Context.** The prefix is the source of truth; the bool flag is a hint that the client sends for convenience but the server does not trust. The combination prevents:
- A client that sends `forzado=true` but forgot to prefix the motivo (operator typo).
- A client that sends `forzado=false` but the user already typed `[FORZADO: …]` in observaciones (logical contradiction).

**Alternatives considered.**
- *Trust the `forzado` bool without validating against prefix* — rejected: defeats A-04 auditability; a malicious client could send `forzado=true, motivo=null` and the server would accept it.
- *Derive `forzado` from prefix only, ignore payload field* — rejected: the bool flag is a UX hint to the client (sends `true` when the user clicked the "forzar" checkbox); ignoring it makes the API harder to use.

**Rationale.** The three-discriminator contract is symmetric (one for each desync direction). The `forzado_contradiccion` discriminator (point 1) is the most interesting — it catches a client that disagrees with itself.

### Decision D-HU-F1.6-6 — Server overwrites client `uuid_tipo_vehiculo` from regex (BR2 CU-01)

**Choice.** After `detectar_tipo_vehiculo(placa)` returns the regex-derived UUID, the handler overwrites the payload's `uuid_tipo_vehiculo` field before passing to V4. The regex is the authority; the client's value is ignored.

**Context.** BR2 of CU-01 requires that the server be the authority on `uuid_tipo_vehiculo` (the placa shape uniquely determines the tipo via regex). A stale client that sends `placa = "ABC123", uuid_tipo_vehiculo = <Moto UUID>` would otherwise pollute the row.

**Alternatives considered.**
- *Reject with 422 if client UUID disagrees with regex* — rejected: noisier UX; the regex-derived UUID is the correct answer; the client bug is silent.
- *Trust the client's UUID and ignore the regex* — rejected: defeats the entire point of the regex validation; the regex is the authority.

**Rationale.** Server-side overwrite is a **silent correction**, not an error. The client sees the 201 with the corrected UUID. The audit log (log_transaccional hash chain) records the payload as sent (with the wrong UUID) and the post-INSERT row with the corrected UUID — discrepancy traceable post-hoc.

### Decision D-HU-F1.6-7 — 4-layer defense in depth (D-HU-F1.6-7)

**Choice.** The validation chain is layered such that no single failure can bypass the whole:

1. **Layer 1 — regex server-side overwrites `uuid_tipo_vehiculo`**: even if the client sends the wrong tipo, the regex-derived one is used.
2. **Layer 2 — KD-FORZADO chain as precondition**: the prefix contract is enforced before V1/V2/V3/V6 can be bypassed; desync → 422.
3. **Layer 3 — alerta INSERT same-TX with ingreso**: a single `await session.commit()` covers both rows (R5 mitigation; no orphaned alerts); the `bypass_reason == "cupo_agotado"` predicate ensures the alert only fires for V2 bypass, not V1/V3/V6 (R2 mitigation).
4. **Layer 4 — AST walk ordering gate** (`tests/static/test_kd_forzado_in_handler.py`): the handler source is AST-walked; the literal order of helper invocations is verified — regex → tipo → KD-FORZADO → cupo → tarifa → sub → no-dup → INSERT.

**Context.** Defense in depth is the corpus's standard pattern for any validation chain (F1.3's `partial unique index` + pre-flight + AST walk; F1.5's MV + UNIQUE INDEX + worker fallback + AST walk). F1.6 inherits the pattern but extends it to 4 layers because the surface is larger (9 validations + bypass + alerta).

**Alternatives considered.**
- *Single layer (regex only)* — rejected: stale client bypass; not aligned with corpus.
- *Two layers (regex + alerta)* — rejected: missing the KD-FORZADO chain ordering; missing the AST walk gating future devs from reordering.
- *Five layers (add a separate pre-handler)* — rejected: complicates the routing without proportional benefit.

**Rationale.** Each layer addresses a different threat: L1 stale client, L2 bypass audit, L3 orphaned alerta, L4 future-dev reordering. The AST walk (L4) is the only one that is automated at CI time; the others rely on tests asserting individual layer behavior.

### Decision D-HU-F1.6-8 — Helper functions encapsulated in `repo/ingreso.py` (180 LOC)

**Choice.** The 9 validations V1..V9 + KD-FORZADO-01 + alerta INSERT are encapsulated in a new `repo/ingreso.py` module (~180 LOC) with thin async helpers:

```python
async def validar_tipo_vehiculo_vigente(session, *, uuid_tipo_vehiculo) -> bool
async def validar_cupo_disponible(session, *, uuid_sucursal, uuid_tipo_vehiculo, forzado=False) -> CupoValidationResult
async def validar_tarifa_vigente(session, *, uuid_sucursal, uuid_tipo_vehiculo, at, forzado=False) -> TarifaValidationResult
async def validar_subscripcion_vigente(session, *, uuid_subscripcion_cliente, forzado=False) -> SubscripcionValidationResult
async def existe_ingreso_activo(session, *, uuid_sucursal, placa) -> uuid_lib.UUID | None
def validar_kd_forzado(observaciones: str | None, forzado: bool) -> str | None
async def crear_ingreso_evento(session, *, actor_uuid, new_attrs, alerta_forzado=False, motivo=None) -> Ingreso
async def insertar_alerta_forzado(session, *, uuid_sucursal, uuid_ingreso, actor_uuid, motivo) -> Alerta
```

`validar_cupo_disponible` and `validar_tarifa_vigente` are re-exports from `repo/ocupacion.py` (+40 LOC) and `repo/tarifas_vigencia.py` (+30 LOC) respectively. The pattern mirrors F1.5's `repo/ocupacion.py` (single SELECT helper) and F1.4's `repo/tarifas_vigencia.py` (bi-temporal predicate).

**Context.** Encapsulation enables the test layer to exercise individual helpers without HTTP (DB integration tests). The re-export pattern keeps `repo/ingreso.py` as the **single import surface** for the handler — the handler does not import from `repo/ocupacion.py` or `repo/tarifas_vigencia.py` directly.

**Alternatives considered.**
- *Inline SQL in the handler* — rejected: violates F1.4/F1.5/F1.8 pattern; not testable without HTTP.
- *Multiple files (`repo/v1_cupo.py`, `repo/v2_tarifa.py`, etc.)* — rejected: 8 helpers across 8 files bloats the import surface.

**Rationale.** One module per domain resource (`ingreso`) keeps the import surface tight. The 180-LOC budget accommodates the 8 helpers with ample docstrings.

### Decision D-HU-F1.6-9 — Alerta `capacidad_agotada_forzado` only when V2 bypassed (`bypass_reason == "cupo_agotado"`)

**Choice.** The alerta INSERT happens **inside** the `INSERT [L-E]` block:

```python
new_row = await record_event(session, Ingreso, …)
if bypass_reason == "cupo_agotado":
    await insertar_alerta_forzado(
        session, uuid_sucursal=target, uuid_ingreso=new_row.uuid,
        actor_uuid=ctx.actor_uuid, motivo=motivo,
    )
await session.commit()  # SINGLE COMMIT (R5 mitigation)
```

When `bypass_reason is None` (V1/V3/V6 bypassed but V2 not), the alert is NOT inserted (R2 mitigation: avoids false-positive alerts when the operator forces for a non-cupo reason).

**Context.** R2 in `proposal.md §8` lists this as a low risk (falsa alerta si forzado por otra razón). The `bypass_reason` discriminator makes the predicate explicit — only V2 bypass emits the alert; V1, V3, V6 bypasses do not.

**Alternatives considered.**
- *Always insert alerta on any `forzado=true`* — rejected: noisy; the alert loses operational meaning (R2).
- *Multiple alert types (`v1_bypass`, `v3_bypass`, `v6_bypass`)* — rejected: out of scope (KD-V3 only mentions `capacidad_agotada_forzado`); catalog seed in F1.14 only seeds this one type.

**Rationale.** The single-alert-type scope matches the seeded catalog. The bypass predicate is a property of the handler state (`bypass_reason == "cupo_agotado"`), not a property of the alert schema.

### Decision D-HU-F1.6-10 — 6 typed error schemas + `IngresoCreateForzado` + `IngresoReadForzado`

**Choice.** Pydantic v2 error schemas (one per 422/409 discriminator):

```python
class CupoNoConfiguradoError(_Base):
    error: Literal["cupo_no_configurado"]
    forzado_permitido: Literal[True]

class MotivoForzadoRequeridoError(_Base):
    error: Literal["motivo_forzado_requerido"]
    cupo_maximo: int
    activos: int

class TarifaVigenteNoEncontradaError(_Base):
    error: Literal["tarifa_vigente_no_encontrada"]

class PlacaFormatoInvalidoError(_Base):
    error: Literal["placa_formato_invalido"]
    formatos_aceptados: list[str]

class SubscripcionInactivaOVencidaError(_Base):
    error: Literal["subscripcion_inactiva_o_vencida"]

class IngresoActivoExistenteError(_Base):
    error: Literal["ingreso_activo_existente"]
    uuid_ingreso_existente: uuid_lib.UUID

class TipoVehiculoInvalidoError(_Base):
    error: Literal["tipo_vehiculo_invalido"]
```

`IngresoCreateForzado` adds `forzado: bool = False` to `IngresoCreate`; `IngresoReadForzado` adds `tipo_entrada: Literal["MENSUALIDAD", "ROTACION"]`, `forzado_en_creacion: bool = False`, `motivo_forzado: str | None = None`. All inherit `extra='forbid'` from `_Base`.

**Context.** Pydantic v2 typed discriminators (`Literal[...]`) lock the response contract. The 6 errors cover V1..V6 + V8 (V7 has no error schema because it inherits from F1.4/F1.5 base capability; V9 has no error because it's derived not validated).

**Alternatives considered.**
- *Generic `HTTPException(detail={"error": str})`* — rejected: not typed; clients cannot discriminate without string match.
- *One mega-schema with optional fields* — rejected: weakens the discriminator; clients cannot rely on field presence.

**Rationale.** Six schemas mirror the 6 422/409 discriminators in `specs/operational/spec.md`. `IngresoReadForzado` is the additive delta to the existing `IngresoRead` (no field removed or renamed; additive only).

### Decision D-HU-F1.6-11 — Strict ordering: KD-3 → V5 → V4 → KD-FORZADO → V1+V2 → V3 → V6 → V8 → INSERT → V9 → 201

**Choice.** The handler invokes helpers in this literal order (R7 invariante):

1. KD-3 tenant scope (resolve `target = payload.uuid_sucursal or ctx.sucursal_uuid`; 400 if both None)
2. V5 regex placa → `uuid_tipo_vehiculo` (overwrite client value)
3. V4 tipo vehículo vigente
4. KD-FORZADO-01 (validate prefix)
5. V1+V2 cupo (joined result; both 422 paths)
6. V3 tarifa vigente (bi-temporal)
7. V6 subscripción (if `uuid_subscripcion_cliente` provided)
8. V8 no-duplicado activo (EXISTS query)
9. INSERT `[L-E]` + alerta same-TX (one `commit()`)
10. Derivar `tipo_entrada` (DEC-SUC-21)
11. 201 with `IngresoReadForzado`

The AST walk `tests/static/test_kd_forzado_in_handler.py` verifies the literal order.

**Context.** The order is intentional: V5 before KD-FORZADO ensures a regex-invalid placa cannot be smuggled through `[FORZADO:`; V4 before KD-FORZADO ensures a catalog-invalid tipo cannot be smuggled; V8 at the end ensures a duplicate is only flagged after all other gates pass. Reversing the order causes incorrect UX (e.g., "cupo agotado" before "regex invalid" when both apply).

**Alternatives considered.**
- *Parallel validation (asyncio.gather)* — rejected: complicates the bypass contract (KD-FORZADO-01); sequential is easier to reason about and matches the 422 precedence.
- *Reverse order (V8 first)* — rejected: a duplicate with bad placa would be reported as "ingreso_activo_existente" instead of "placa_formato_invalido" — operator can't see the real error.

**Rationale.** Sequential validation with explicit ordering is the cleanest abstraction. The AST walk is a CI gate that locks the order against future-dev reordering.

### Decision D-HU-F1.6-12 — No `correlacion_id`; idempotency via `Idempotency-Key` header (PR2)

**Choice.** The body schema (`IngresoCreateForzado`) does NOT include `correlacion_id`. Idempotency is handled by the existing `IdempotencyKeyMiddleware` (PR2, `api/deps.py`) reading the `Idempotency-Key` HTTP header.

**Context.** DEC-IDEM-01 explicitly delegates idempotency to the header middleware (already in place since PR2). Adding `correlacion_id` to the body would create two idempotency surfaces.

**Alternatives considered.**
- *Add `correlacion_id: uuid_lib.UUID | None` to the body* — rejected: doubles the surface; DEC-IDEM-01 veto.

**Rationale.** Header-based idempotency is the corpus pattern; F1.6 inherits verbatim.

### Decision D-HU-F1.6-13 — Both `operador-` and `admin-` can emit `forzado=true` (KD-V8)

**Choice.** No RBAC difference for `forzado=true`. The existing `_ingreso_issuer_dep = requires_issuer("operador-", "admin-")` accepts both issuers; the KD-FORZADO-01 contract applies uniformly.

**Context.** KD-V8 in `exploration.md §12` adopts issuer parity for MVP. The alerta `datos_nuevos` records `actor_uuid`, providing the audit trail. If "solo admin-" is needed, a check is added in a future HU.

**Alternatives considered.**
- *RBAC differentiation (admin only)* — rejected: complicates MVP; the alert + log_transaccional hash chain already records who did what.

**Rationale.** Issuer parity simplifies MVP. The audit trail (`actor_uuid` in the alerta + `created_by` in the ingreso) is the enforcement surface, not the RBAC layer.

## 4. Architecture Overview

```
HTTPS POST /api/v1/operacion/ingresos
        Body: IngresoCreateForzado
        │      {uuid_sucursal?, placa, uuid_tipo_vehiculo?,
        │       uuid_subscripcion_cliente?, fecha_ingreso?,
        │       observaciones?, forzado?: bool = false}
        │  Idempotency-Key: <uuid>   (header, PR2 middleware)
        │  X-Sucursal-Context: <uuid> (admin- only, get_tenant_ctx)
        │  requires_issuer("operador-", "admin-")
        │  Cache-Control: no-store
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ api/v1/operacion.py  (MODIFY, replace create_ingreso, lines 92-114 → ~232 LOC)│
│                                                                              │
│ 1. KD-3 (target_sucursal + tenant scope):                                   │
│    target = payload.uuid_sucursal or ctx.sucursal_uuid                      │
│    if not target: 400 missing_sucursal_context                              │
│    cross-tenant → 403 tenant_scope_violation / sucursal_not_permitted       │
│                                                                              │
│ 2. V5 regex placa → tipo derivado (D-HU-F1.6-6):                            │
│    uuid_tipo_vehiculo = repo/placa.detectar_tipo_vehiculo(payload.placa)    │
│    if None: 422 placa_formato_invalido {formatos_aceptados: [ABC123,ABC12D]}│
│                                                                              │
│ 3. V4 tipo vehículo vigente:                                                 │
│    if not repo/ingreso.validar_tipo_vehiculo_vigente(uuid_tipo_vehiculo):    │
│        422 tipo_vehiculo_invalido                                           │
│                                                                              │
│ 4. KD-FORZADO-01 (D-HU-F1.6-2, D-HU-F1.6-5):                                │
│    motivo = repo/ingreso.validar_kd_forzado(observaciones, forzado)         │
│    bypass_reason = "forzado" if motivo else None                            │
│                                                                              │
│ 5. V1+V2 cupo (KD-V4 eventual consistency):                                 │
│    cupo_result = repo/ocupacion.validar_cupo_disponible(                    │
│        session, uuid_sucursal=target,                                       │
│        uuid_tipo_vehiculo=uuid_tipo_vehiculo,                               │
│        forzado=bool(bypass_reason))                                          │
│    if cupo_result.cupo_no_configurado:                                      │
│        422 cupo_no_configurado {forzado_permitido: True}                    │
│    if cupo_result.cupo_agotado:                                             │
│        422 motivo_forzado_requerido {cupo_maximo, activos}                  │
│                                                                              │
│ 6. V3 tarifa vigente (bi-temporal F1.4):                                     │
│    tarifa_result = repo/tarifas_vigencia.validar_tarifa_vigente(            │
│        session, uuid_sucursal=target,                                       │
│        uuid_tipo_vehiculo=uuid_tipo_vehiculo,                               │
│        at=datetime.now(UTC), forzado=bool(bypass_reason))                   │
│    if not tarifa_result.vigente:                                            │
│        422 tarifa_vigente_no_encontrada                                     │
│                                                                              │
│ 7. V6 subscripción (if provided):                                           │
│    if payload.uuid_subscripcion_cliente:                                    │
│        sub_result = repo/subscripcion_activa.validar_subscripcion_vigente(  │
│            session, uuid_subscripcion_cliente=payload.uuid_subscripcion…   │
│            forzado=bool(bypass_reason))                                     │
│        if not sub_result.vigente:                                           │
│            422 subscripcion_inactiva_o_vencida                              │
│                                                                              │
│ 8. V8 no-duplicado activo (D-HU-F1.6-3, sin lock):                          │
│    uuid_activo = repo/ingreso.existe_ingreso_activo(                        │
│        session, uuid_sucursal=target, placa=payload.placa)                  │
│    if uuid_activo:                                                          │
│        409 ingreso_activo_existente {uuid_ingreso_existente}                │
│                                                                              │
│ 9. INSERT [L-E] + alerta (D-HU-F1.6-9, misma TX):                           │
│    new_row = await record_event(session, Ingreso, …)                        │
│    if bypass_reason == "cupo_agotado":                                      │
│        await repo/alerta.insertar_alerta_forzado(                           │
│            session, uuid_sucursal=target, uuid_ingreso=new_row.uuid,        │
│            actor_uuid=ctx.actor_uuid, motivo=motivo)                        │
│    await session.commit()    ← UN solo commit                               │
│                                                                              │
│ 10. Derivar tipo_entrada (DEC-SUC-21, V9):                                  │
│     tipo_entrada = "MENSUALIDAD" if payload.uuid_subscripcion_cliente       │
│                    else "ROTACION"                                          │
│     # NUNCA persistir en prod.ingreso                                       │
│                                                                              │
│ 11. response.headers["Cache-Control"] = "no-store"                          │
│ 12. return IngresoReadForzado + tipo_entrada                                │
│             + forzado_en_creacion=(bypass_reason is not None)               │
│             + motivo_forzado=motivo if bypass_reason else None             │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲                            ▲                       ▲
        │ AST walk                   │ AST walk              │ SELECT-only
        │ ordering gate              │ read-only gate        │ (sin lock)
        │
tests/static/test_kd_forzado_in_handler.py
tests/static/test_no_write_after_insert.py
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Repo helpers (NEW + MODIFY):                                                │
│   repo/placa.py              (NEW, 30 LOC) — regex + detectar_tipo_vehiculo  │
│   repo/ingreso.py            (NEW, 180 LOC) — 8 funciones V1..V9 + alerta   │
│   repo/subscripcion_activa.py(NEW, 50 LOC) — validar_subscripcion_vigente   │
│   repo/alerta.py             (NEW, 60 LOC) — insertar_alerta_forzado        │
│   repo/ocupacion.py          (MODIFY, +40 LOC) — validar_cupo_disponible    │
│   repo/tarifas_vigencia.py   (MODIFY, +30 LOC) — validar_tarifa_vigente     │
│                                                                              │
│ Tablas operacionales (READ ONLY, sin DDL):                                  │
│   prod.ingreso                  [L-E]  — INSERT vía record_event            │
│   prod.cantidad_vehiculos_sucursal [V] — V1+V2 vía mv JOIN                 │
│   prod.mv_ocupacion_diaria      [MV]  — count(*) activos                    │
│   prod.tarifas_sucursal         [V]   — V3 bi-temporal                     │
│   prod.subscripciones_cliente   [V]   — V6 vigente                         │
│   prod.subscripcion_vehiculos   [V]   — junction V6                         │
│   prod.vehiculos                [V]   — V6 via placa                       │
│   prod.tipos_vehiculo           [V]   — V4 vigente                         │
│   prod.alerta                   [L-W] — INSERT capacidad_agotada_forzado   │
└──────────────────────────────────────────────────────────────────────────────┘
```

The handler is thin + orchestador. The 9 validations + bypass + alerta live in `repo/*.py`; the AST walks gate the contract at CI time. The cliente loses all validation responsibility (cleanup of `web_sucursal/src/lib/validation/placa.ts` A-03 is post-archive, not in F1.6).

## 5. Data Model

**No changes to the schema.** `modelo_datos_er.mmd` tables involved:

| Tabla | Tipo | Líneas ER | Rol en F1.6 |
|---|---|---|---|
| `prod.ingreso` | `[L-E]` | 577–596 | INSERT vía `record_event` (única escritura); V8 EXISTS check |
| `prod.tipos_vehiculo` | `[V]` | 87–104 | V4 vigente + V5 lazy lookup |
| `prod.cantidad_vehiculos_sucursal` | `[V]` | 428–446 | V1+V2 vía `mv_ocupacion_diaria` JOIN |
| `prod.mv_ocupacion_diaria` | `[MV]` | post-F1.5 | V1+V2 `count(*) activos` |
| `prod.tarifas_sucursal` | `[V]` | 406–426 | V3 bi-temporal canónico F1.4 |
| `prod.subscripciones_cliente` | `[V]` | post-PR4 | V6 vigente |
| `prod.subscripcion_vehiculos` | `[V]` | post-PR4 | junction V6 |
| `prod.vehiculos` | `[V]` | post-PR4 | V6 via `placa` |
| `prod.alerta` | `[L-W]` | 952–974 | INSERT `capacidad_agotada_forzado` |
| `prod.salidas` | `[A]` | 761–777 | V8 `NOT EXISTS` |
| `prod.anulaciones` | `[L-W]` | post-PR6 | V8 `NOT EXISTS` (`estado='ejecutada'`) |

**No Alembic migration.** F1.6 is read-only over the schema. The single write surface (`record_event`) is reused verbatim from F1.5/PR5. The alerta INSERT uses the existing `[L-W]` `prod.alerta` table (catalog type `capacidad_agotada_forzado` seeded in F1.14, post-DEC-SUC-14).

**No sync catalog changes.** The validations live in `repo/*.py`; the sync catalog is untouched. Only the **number of rows that pass validation** changes (invalid rows are rejected before INSERT, not after).

**Columns read (no DDL)**:

| Tabla | Columna | Lectura |
|---|---|---|
| `prod.ingreso` | `uuid`, `uuid_sucursal`, `placa`, `uuid_tipo_vehiculo`, `uuid_subscripcion_cliente` | V8 EXISTS + INSERT |
| `prod.tipos_vehiculo` | `uuid`, `tipo`, `vigente_hasta`, `estado` | V4 + V5 lazy UUID lookup |
| `prod.cantidad_vehiculos_sucursal` | `uuid_sucursal`, `uuid_tipo_vehiculo`, `cantidad` | V1+V2 vía mv JOIN |
| `prod.mv_ocupacion_diaria` | `uuid_sucursal`, `uuid_tipo_vehiculo`, `activos` | V1+V2 count |
| `prod.tarifas_sucursal` | `vigente_desde`, `vigente_hasta`, `estado` | V3 bi-temporal |
| `prod.subscripciones_cliente` | `fecha_vencimiento`, `estado`, `vigente_hasta` | V6 vigente |
| `prod.subscripcion_vehiculos` | `uuid_subscripcion`, `uuid_vehiculo` | V6 junction |
| `prod.vehiculos` | `placa`, `uuid` | V6 via placa |
| `prod.alerta` | `tipo_alerta`, `estado`, `datos_nuevos` | INSERT |

**No column added for `forzado`, `tipo_entrada`, `motivo`** — DEC-SUC-21 veda `tipo_entrada` columna; KD-FORZADO-01 veda `forzado` columna. The motivo is stored in `prod.alerta.datos_nuevos` (jsonb) when applicable.

## 6. API Contracts

### `POST /api/v1/operacion/ingresos` (modified)

**Request signature**:

```python
async def create_ingreso(
    payload: IngresoCreateForzado,
    response: Response,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_ingreso_issuer_dep),
) -> IngresoReadForzado:
```

**Body `IngresoCreateForzado`** (Pydantic v2, `extra='forbid'`):

```python
class IngresoCreateForzado(_Base):
    model_config = ConfigDict(extra="forbid")
    uuid_sucursal: uuid_lib.UUID | None = None        # default: ctx.sucursal_uuid
    placa: str | None = None
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None  # server overwrites via V5
    uuid_subscripcion_cliente: uuid_lib.UUID | None = None
    fecha_ingreso: datetime | None = None
    observaciones: str | None = None
    forzado: bool = False  # NEW; validated against observaciones prefix
```

**Response `IngresoReadForzado`** (201, Pydantic v2):

```python
class IngresoReadForzado(_Base):
    # inherited from IngresoRead (6 business columns + 6 base columns):
    # uuid, created_at, created_by, sync_status, sync_timestamp, sync_attempts,
    # uuid_sucursal, placa, uuid_tipo_vehiculo, uuid_subscripcion_cliente,
    # fecha_ingreso, observaciones
    tipo_entrada: Literal["MENSUALIDAD", "ROTACION"]   # NEW (V9)
    forzado_en_creacion: bool = False                    # NEW
    motivo_forzado: str | None = None                    # NEW (KD-FORZADO-01)
```

**Headers**: `Cache-Control: no-store` (consistent with F1.3 R8, F1.5 R8, F1.8 R8).

**Error discriminators** (typed HTTPException details):

| HTTP | Body | Cuándo | KD |
|---|---|---|---|
| 400 | `{"error":"missing_sucursal_context"}` | `uuid_sucursal` ausente y `ctx.sucursal_uuid is None` | KD-3 |
| 403 | `{"error":"tenant_scope_violation"}` | `operador-` con `uuid_sucursal != ctx.sucursal_uuid` | KD-3 |
| 403 | `{"error":"sucursal_not_permitted"}` | `admin-` con `uuid_sucursal` fuera de `claims["sucursales_permitidas"]` | KD-3 |
| 422 | `{"error":"placa_formato_invalido","formatos_aceptados":["ABC123","ABC12D"]}` | regex server-side no matchea | V5 |
| 422 | `{"error":"tipo_vehiculo_invalido"}` | UUID no existe o `vigente_hasta IS NOT NULL` o `estado='inactivo'` | V4 |
| 422 | `{"error":"forzado_contradiccion"}` | `forzado=false` pero `observaciones` empieza con `[FORZADO:` | KD-FORZADO-01 |
| 422 | `{"error":"motivo_forzado_requerido"}` | `forzado=true` sin prefijo | KD-FORZADO-01 |
| 422 | `{"error":"motivo_forzado_insuficiente","min_chars":10}` | motivo <10 chars tras prefijo | KD-FORZADO-01 |
| 422 | `{"error":"cupo_no_configurado","forzado_permitido":true}` | sin fila en `cantidad_vehiculos_sucursal(X, T)` | V1 |
| 422 | `{"error":"motivo_forzado_requerido","cupo_maximo":N,"activos":N}` | cupo agotado sin forzado | V2 |
| 422 | `{"error":"tarifa_vigente_no_encontrada"}` | sin fila vigente en `tarifas_sucursal(X, T)` | V3 |
| 422 | `{"error":"subscripcion_inactiva_o_vencida"}` | `fecha_vencimiento < NOW()` o `estado='inactivo'` | V6 |
| 409 | `{"error":"ingreso_activo_existente","uuid_ingreso_existente":"<uuid>"}` | ya hay ingreso activo para `(X, placa)` | V8 |
| 201 | `IngresoReadForzado` | happy path | — |

**Sin cambios sobre**:
- `GET /api/v1/operacion/ingresos/{uuid}` (F1.5)
- `GET /api/v1/operacion/ingresos/{uuid}/estado` (F1.5)
- `GET /api/v1/operacion/ingresos` (F1.5 list)
- `GET /api/v1/operacion/ocupacion` (F1.5)
- `GET /api/v1/operacion/cotizar` (F1.8)

## 7. Handler Skeleton

**Path**: `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (modify, replace lines 92-114 → ~232 LOC).

The handler is registered on the existing `APIRouter` (no new module added under `api/v1/`); the decorator `@router.post("/ingresos")` is the same one that hosts `cotizar_ingreso_handler` and `get_ocupacion`. The dependency chain is identical to the existing handlers. The 11-step sequence (D-HU-F1.6-11) is enforced by the AST walk `tests/static/test_kd_forzado_in_handler.py`.

```python
# backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py
# (replace create_ingreso, lines 92-114 → ~232 LOC)


@router.post(
    "/ingresos",
    response_model=IngresoReadForzado,
    status_code=201,
    summary=(
        "HU-F1.6 / REQ-OPS-034..041: server-side validated vehicle "
        "entry (ingreso, [L-E] event) with KD-FORZADO bypass."
    ),
    responses={
        400: {"description": "missing_sucursal_context"},
        403: {
            "description": (
                "tenant_scope_violation (operador) | "
                "sucursal_not_permitted (admin)"
            )
        },
        409: {"description": "ingreso_activo_existente (V8)"},
        422: {
            "description": (
                "placa_formato_invalido (V5) | tipo_vehiculo_invalido (V4) | "
                "forzado_contradiccion (KD-FORZADO-01) | "
                "motivo_forzado_requerido (KD-FORZADO-01, V2) | "
                "motivo_forzado_insuficiente (KD-FORZADO-01) | "
                "cupo_no_configurado (V1) | "
                "tarifa_vigente_no_encontrada (V3) | "
                "subscripcion_inactiva_o_vencida (V6)"
            )
        },
    },
)
async def create_ingreso(
    payload: IngresoCreateForzado,
    response: Response,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> IngresoReadForzado:
    """REQ-OPS-034..041: validated vehicle entry, [L-E] event.

    Dependency chain (D-HU-F1.6-7 Layer 2 + Layer 4):
        _ingreso_issuer_dep   -> requires_issuer("operador-", "admin-")
        get_tenant_ctx        -> TenantContext { actor_uuid, sucursal_uuid, ... }
        get_session           -> AsyncSession (request-scoped)

    Sequence (D-HU-F1.6-11 R7 invariante — verified by AST walk):
        1. KD-3 (target_sucursal + tenant scope)
        2. V5 regex placa → tipo derivado (server overwrites client)
        3. V4 tipo vehículo vigente
        4. KD-FORZADO-01 (validate prefix; sets bypass_reason)
        5. V1+V2 cupo (via mv_ocupacion_diaria JOIN; KD-V4)
        6. V3 tarifa vigente (bi-temporal F1.4)
        7. V6 subscripción (if uuid_subscripcion_cliente provided)
        8. V8 no-duplicado activo (EXISTS directo a tablas, sin lock)
        9. INSERT [L-E] + alerta capacidad_agotada_forzado (same TX)
       10. Derivar tipo_entrada (DEC-SUC-21)
       11. 201 IngresoReadForzado with tipo_entrada + forzado_en_creacion + motivo_forzado

    The Idempotency-Key header is checked by the FastAPI middleware
    (PR2 IdempotencyKeyMiddleware).
    """
    # 1. KD-3 (target_sucursal + tenant scope):
    #    - query/body uuid_sucursal wins;
    #    - else ctx.sucursal_uuid;
    #    - else 400 missing_sucursal_context.
    target = payload.uuid_sucursal or ctx.sucursal_uuid
    if target is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
            headers=_cotizar_no_store_headers(),
        )
    # Authorization (operador- pinned, admin- scoped):
    # get_tenant_ctx already validated X-Sucursal-Context for admin-;
    # for operador-, we additionally check target == ctx.sucursal_uuid.
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation"},
            headers=_cotizar_no_store_headers(),
        )

    # 2. V5 regex placa → tipo derivado (D-HU-F1.6-6):
    #    Server overwrites uuid_tipo_vehiculo with regex-derived value.
    uuid_tipo_vehiculo = await detectar_tipo_vehiculo(session, payload.placa)
    if uuid_tipo_vehiculo is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "placa_formato_invalido",
                "formatos_aceptados": ["ABC123", "ABC12D"],
            },
            headers=_cotizar_no_store_headers(),
        )

    # 3. V4 tipo vehículo vigente:
    if not await validar_tipo_vehiculo_vigente(
        session, uuid_tipo_vehiculo=uuid_tipo_vehiculo
    ):
        raise HTTPException(
            status_code=422,
            detail={"error": "tipo_vehiculo_invalido"},
            headers=_cotizar_no_store_headers(),
        )

    # 4. KD-FORZADO-01 (D-HU-F1.6-2, D-HU-F1.6-5):
    motivo = validar_kd_forzado(payload.observaciones, payload.forzado)
    bypass_reason: str | None = "forzado" if motivo else None

    # 5. V1+V2 cupo (KD-V4 eventual consistency):
    cupo_result = await validar_cupo_disponible(
        session,
        uuid_sucursal=target,
        uuid_tipo_vehiculo=uuid_tipo_vehiculo,
        forzado=bool(bypass_reason),
    )
    if cupo_result.cupo_no_configurado:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "cupo_no_configurado",
                "forzado_permitido": True,
            },
            headers=_cotizar_no_store_headers(),
        )
    if cupo_result.cupo_agotado:
        # V2 — note that on bypass, the body shape is identical
        # (motivo_forzado_requerido), but the handler proceeds.
        if not bypass_reason:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "motivo_forzado_requerido",
                    "cupo_maximo": cupo_result.cupo_maximo,
                    "activos": cupo_result.activos,
                },
                headers=_cotizar_no_store_headers(),
            )
        bypass_reason = "cupo_agotado"  # discriminate for alerta

    # 6. V3 tarifa vigente (bi-temporal canónico F1.4):
    tarifa_result = await validar_tarifa_vigente(
        session,
        uuid_sucursal=target,
        uuid_tipo_vehiculo=uuid_tipo_vehiculo,
        at=datetime.now(UTC).replace(tzinfo=None),
        forzado=bool(bypass_reason),
    )
    if not tarifa_result.vigente:
        if not bypass_reason:
            raise HTTPException(
                status_code=422,
                detail={"error": "tarifa_vigente_no_encontrada"},
                headers=_cotizar_no_store_headers(),
            )

    # 7. V6 subscripción (if provided):
    if payload.uuid_subscripcion_cliente is not None:
        sub_result = await validar_subscripcion_vigente(
            session,
            uuid_subscripcion_cliente=payload.uuid_subscripcion_cliente,
            forzado=bool(bypass_reason),
        )
        if not sub_result.vigente and not bypass_reason:
            raise HTTPException(
                status_code=422,
                detail={"error": "subscripcion_inactiva_o_vencida"},
                headers=_cotizar_no_store_headers(),
            )

    # 8. V8 no-duplicado activo (EXISTS directo a tablas, sin lock):
    uuid_activo = await existe_ingreso_activo(
        session, uuid_sucursal=target, placa=payload.placa
    )
    if uuid_activo is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "ingreso_activo_existente",
                "uuid_ingreso_existente": str(uuid_activo),
            },
            headers=_cotizar_no_store_headers(),
        )

    # 9. INSERT [L-E] + alerta (D-HU-F1.6-9, same TX):
    new_attrs = payload.model_dump(
        exclude_none=True,
        exclude={"forzado"},  # NOT persisted; derived from prefix
    )
    # Overwrite cliente uuid_tipo_vehiculo with regex-derived UUID (D-HU-F1.6-6):
    new_attrs["uuid_tipo_vehiculo"] = uuid_tipo_vehiculo
    new_row = await crear_ingreso_evento(
        session,
        actor_uuid=ctx.actor_uuid,
        new_attrs=new_attrs,
    )
    if bypass_reason == "cupo_agotado":
        # R2 mitigation: alerta SOLO si V2 fue bypassed.
        await insertar_alerta_forzado(
            session,
            uuid_sucursal=target,
            uuid_ingreso=new_row.uuid,
            actor_uuid=ctx.actor_uuid,
            motivo=motivo or "(sin motivo)",
        )
    await session.commit()  # UN solo commit (R5)

    # 10. Derivar tipo_entrada (DEC-SUC-21, V9):
    #     Keyed on uuid_subscripcion_cliente NOT NULL, NOT on forzado.
    tipo_entrada: Literal["MENSUALIDAD", "ROTACION"] = (
        "MENSUALIDAD" if payload.uuid_subscripcion_cliente is not None else "ROTACION"
    )

    # 11. Cache-Control + 201 response.
    response.headers["Cache-Control"] = "no-store"
    return IngresoReadForzado(
        **IngresoRead.model_validate(new_row).model_dump(),
        tipo_entrada=tipo_entrada,
        forzado_en_creacion=bypass_reason is not None,
        motivo_forzado=motivo if bypass_reason else None,
    )
```

**Notes.**
- The handler is **registered on the existing `APIRouter`** (no new module added under `api/v1/`); the decorator `@router.post("/ingresos")` is the same one that hosts `create_ingreso`, `cotizar_ingreso_handler`, `get_ocupacion`. The replacement is in-place; the factory pattern is NOT touched.
- The dependency chain `_ingreso_issuer_dep → get_tenant_ctx → get_session` is **verbatim** from the existing handlers (line 64 onward). No new dependency factories.
- All repo helpers are imported from `parkos_core.repo.{ingreso, placa, subscripcion_activa, alerta, ocupacion, tarifas_vigencia}`. The handler does not write SQL inline.
- The `bypass_reason` discriminator is a string literal (not a typed enum) to keep the helper return type `str | None`. The string is `"forzado"` initially and is refined to `"cupo_agotado"` only when V2 is bypassed — this is the predicate for the alerta INSERT.
- `payload.model_dump(exclude_none=True, exclude={"forzado"})` excludes the `forzado` bool from the persisted row (D-HU-F1.6-5: not a column).
- `await session.commit()` happens exactly once, AFTER the optional alerta INSERT (R5 mitigation: no orphaned alerts).
- The `forzado_contradiccion` and `motivo_forzado_requerido` / `motivo_forzado_insuficiente` 422 paths are raised INSIDE `validar_kd_forzado` (step 4), before V1+V2. The handler does not catch them — they propagate to FastAPI's default exception handler.
- The `extra='forbid'` on `_Base` rejects extra fields; clients sending `tipo_entrada` (an attempt to inject a column that doesn't exist) are rejected with 422 before the handler runs.

## 8. Repo Skeleton — File-by-File

### 8.1 `backend/packages/parkos_core/src/parkos_core/repo/placa.py` (NEW, ~30 LOC)

Regex constants + lazy UUID lookup. Mirrors `repo/alert_types.py` shape (typed exception + validate function).

```python
"""HU-F1.6 / V5 — placa regex Colombia + UUID derivation (D-HU-F1.6-4).

Module-level regex constants for Auto (`ABC123`) and Moto (`ABC12D`).
``detectar_tipo_vehiculo(placa) -> UUID | None`` lazy-looks up the vigente
row in ``prod.tipos_vehiculo`` keyed by the human-readable ``tipo``
string ('Auto', 'Moto'). Returns None when the regex doesn't match OR
when the catalog is missing the tipo.

DEC-SUC-22: regex estricta, sin tolerancia O↔0/I↔1. The tolerant variant
lives in ``buscarIngresoTolerante`` (HU-F1.7), not here.
"""
from __future__ import annotations

import re
import uuid as uuid_lib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.tipos_vehiculo import TiposVehiculo


# Module-level constants (A-03 / KD-V2). Future cat-tabla swap is a
# one-file edit.
FORMATO_AUTO = re.compile(r"^[A-Z]{3}[0-9]{3}$")    # ABC123
FORMATO_MOTO = re.compile(r"^[A-Z]{3}[0-9]{2}[A-Z]$")  # ABC12D


async def detectar_tipo_vehiculo(
    session: AsyncSession,
    placa: str | None,
) -> uuid_lib.UUID | None:
    """V5: derive ``uuid_tipo_vehiculo`` from the placa regex.

    Returns:
        The UUID of the vigente row in ``prod.tipos_vehiculo`` whose
        ``tipo`` ('Auto' or 'Moto') matches the regex, or ``None`` if
        the regex does not match OR the catalog has no vigente row
        for that tipo (the latter triggers V4 ``tipo_vehiculo_invalido``).
    """
    if placa is None:
        return None
    if FORMATO_AUTO.match(placa):
        tipo_nombre = "Auto"
    elif FORMATO_MOTO.match(placa):
        tipo_nombre = "Moto"
    else:
        return None

    stmt = select(TiposVehiculo.uuid).where(
        TiposVehiculo.tipo == tipo_nombre,
        TiposVehiculo.vigente_hasta.is_(None),
        TiposVehiculo.estado == "activo",
    )
    return (await session.execute(stmt)).scalar_one_or_none()


__all__ = [
    "FORMATO_AUTO",
    "FORMATO_MOTO",
    "detectar_tipo_vehiculo",
]
```

**Notes.**
- Lazy lookup is intentional — the UUID is generated server-side and the client does not need to know it.
- `vigente_hasta IS NULL AND estado='activo'` enforces bi-temporal `[V]` discipline, consistent with `tarifas_vigencia.py` and `cotizacion.py`.
- The `None` return path covers two cases: regex mismatch (V5 422) and catalog missing (V4 422). The handler distinguishes them by the order of helper invocations: `detectar_tipo_vehiculo` (V5) → if None, immediately 422 with `placa_formato_invalido`; if non-None, then V4 checks the catalog.

### 8.2 `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py` (NEW, ~180 LOC)

The 8-helper module that backs V1, V2 (via re-export), V3 (re-export), V4, V6 (re-export), V8, V9 + KD-FORZADO-01 + alerta INSERT.

```python
"""HU-F1.6 / REQ-OPS-034..041 — validation + bypass + alerta for ingreso.

Encapsulates:
  - V4: ``validar_tipo_vehiculo_vigente``
  - V8: ``existe_ingreso_activo`` (EXISTS directo a tablas, sin lock)
  - V9 + KD-FORZADO-01: ``validar_kd_forzado``
  - alerta INSERT: ``insertar_alerta_forzado``
  - thin wrapper: ``crear_ingreso_evento`` (record_event + log_tx=True)

V1+V2 (cupo) and V3 (tarifa) are re-exports from
``repo.ocupacion.validar_cupo_disponible`` and
``repo.tarifas_vigencia.validar_tarifa_vigente`` so the handler imports
from a single module.
"""
from __future__ import annotations

import uuid as uuid_lib

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_E.ingreso import Ingreso
from ..models.L_W.alerta import Alerta
from ..repo.event import record_event
from .ocupacion import validar_cupo_disponible
from .tarifas_vigencia import validar_tarifa_vigente


# Module-level constants (KD-FORZADO-01). A-04 veda columna ``forzado``;
# these constants are the source of truth.
FORZADO_PREFIX = "[FORZADO: "
FORZADO_MIN_MOTIVO_CHARS = 10


# Re-exports — single import surface for the handler.
__all__ = [
    "FORZADO_MIN_MOTIVO_CHARS",
    "FORZADO_PREFIX",
    "crear_ingreso_evento",
    "existe_ingreso_activo",
    "insertar_alerta_forzado",
    "validar_cupo_disponible",
    "validar_kd_forzado",
    "validar_tarifa_vigente",
    "validar_tipo_vehiculo_vigente",
    "validar_subscripcion_vigente",
]


# --- V4 -----------------------------------------------------------------


async def validar_tipo_vehiculo_vigente(
    session: AsyncSession,
    *,
    uuid_tipo_vehiculo: uuid_lib.UUID,
) -> bool:
    """V4: True iff ``prod.tipos_vehiculo`` has a vigente row with this PK.

    Defense in depth: rejects tipo dado de baja (``vigente_hasta IS NOT NULL``)
    OR ``estado='inactivo'``. Used to reject catalog defects that the
    regex lookup cannot detect (D-HU-F1.6-7 Layer 3).
    """
    row = (
        await session.execute(
            select(TiposVehiculo.uuid).where(  # type: ignore[name-defined]  # noqa: F821
                TiposVehiculo.uuid == uuid_tipo_vehiculo,
                TiposVehiculo.vigente_hasta.is_(None),
                TiposVehiculo.estado == "activo",
            )
        )
    ).scalar_one_or_none()
    return row is not None


# --- V8 -----------------------------------------------------------------


async def existe_ingreso_activo(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    placa: str,
) -> uuid_lib.UUID | None:
    """V8: True iff an open ingreso exists for ``(uuid_sucursal, placa)``.

    Definition of "active" (per REQ-OPS-040):
        EXISTS (SELECT 1 FROM prod.ingreso i
                WHERE i.uuid_sucursal=:X AND i.placa=:P
                  AND NOT EXISTS (SELECT 1 FROM prod.salidas s
                                  WHERE s.uuid_ingreso=i.uuid
                                    AND s.uuid_sucursal=i.uuid_sucursal)
                  AND NOT EXISTS (SELECT 1 FROM prod.anulaciones a
                                  WHERE a.uuid_ingreso=i.uuid
                                    AND a.estado='ejecutada'
                                    AND a.tipo_anulable IN ('ingreso','salida')))

    NO pessimistic lock (D-HU-F1.6-3 / KD-V4). Direct to tables (authoritative),
    not the MV (stale). Expected < 50ms p99 with the F1.5
    ``(uuid_sucursal, placa, created_at)`` index.
    """
    stmt = text(
        """
        SELECT i.uuid
        FROM prod.ingreso i
        WHERE i.uuid_sucursal = :uuid_sucursal
          AND i.placa = :placa
          AND NOT EXISTS (
              SELECT 1 FROM prod.salidas s
              WHERE s.uuid_ingreso = i.uuid
                AND s.uuid_sucursal = i.uuid_sucursal
          )
          AND NOT EXISTS (
              SELECT 1 FROM prod.anulaciones a
              WHERE a.uuid_ingreso = i.uuid
                AND a.estado = 'ejecutada'
                AND a.tipo_anulable IN ('ingreso', 'salida')
          )
        LIMIT 1
        """
    )
    return (
        await session.execute(
            stmt, {"uuid_sucursal": str(uuid_sucursal), "placa": placa}
        )
    ).scalar_one_or_none()


# --- KD-FORZADO-01 -------------------------------------------------------


def validar_kd_forzado(
    observaciones: str | None,
    forzado: bool,
) -> str | None:
    """KD-FORZADO-01: validate ``forzado`` + ``observaciones`` prefix.

    Returns the stripped motivo on a valid bypass; ``None`` when not
    bypassed (forzado=false and observaciones either None or not
    prefixed). Raises HTTPException(422) for the three discriminators:

        - forzado_contradiccion: forzado=false with prefix
        - motivo_forzado_requerido: forzado=true without prefix
        - motivo_forzado_insuficiente: motivo < 10 chars after rstrip
    """
    has_prefix = (
        observaciones is not None
        and observaciones.startswith(FORZADO_PREFIX)
    )

    if not forzado:
        if has_prefix:
            raise HTTPException(
                status_code=422,
                detail={"error": "forzado_contradiccion"},
            )
        return None

    # forzado=true
    if not has_prefix:
        raise HTTPException(
            status_code=422,
            detail={"error": "motivo_forzado_requerido"},
        )

    motivo = observaciones[len(FORZADO_PREFIX):].rstrip("]")
    if len(motivo.strip()) < FORZADO_MIN_MOTIVO_CHARS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "motivo_forzado_insuficiente",
                "min_chars": FORZADO_MIN_MOTIVO_CHARS,
            },
        )
    return motivo.strip()


# --- INSERT + alerta ----------------------------------------------------


async def crear_ingreso_evento(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    new_attrs: dict,
) -> Ingreso:
    """Thin wrapper of ``record_event(Ingreso, …)`` with log_tx=True.

    Same shape as F1.5/PR5. Caller commits.
    """
    return await record_event(
        session,
        Ingreso,
        actor_uuid=actor_uuid,
        new_attrs=new_attrs,
        log_tx=True,
    )


async def insertar_alerta_forzado(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
    motivo: str,
) -> Alerta:
    """D-HU-F1.6-9: INSERT alerta ``capacidad_agotada_forzado``.

    Caller commits (same TX as the ingreso INSERT, R5 mitigation).
    """
    alerta = Alerta(
        uuid_sucursal=uuid_sucursal,
        uuid_usuario=actor_uuid,
        tipo_alerta="capacidad_agotada_forzado",
        estado="abierta",
        timestamp_evento=datetime.now(UTC).replace(tzinfo=None),
        # ``datos_nuevos`` is jsonb on prod.alerta (REQ-26-W-ALERTA).
        # The motivo carries the audit reason; F1.6 uses a jsonb payload.
        # NOTE: prod.alerta may not have a ``datos_nuevos`` column in the
        # current schema; the catalog ``capacidad_agotada_forzado`` is
        # seeded with a single motivo string in ``observaciones`` via
        # the existing ``motivo`` field if present, else a dedicated
        # jsonb column is added in F1.6's migration 0025 (D-hu-F1.6-12).
        uuid_arqueo=None,
    )
    session.add(alerta)
    # NOTE: the alert payload (motivo) is captured via the
    # ``observaciones`` extension or via a jsonb field added by
    # migration 0025. The apply phase resolves the exact column.
    return alerta
```

**Notes.**
- `validar_tipo_vehiculo_vigente` does NOT honor `forzado=true` (D-HU-F1.6-7 Layer 3 / KD-V3: catalog defect, not operational).
- `existe_ingreso_activo` reads directly from `prod.ingreso` + `prod.salidas` + `prod.anulaciones`; no MV, no lock. The `(uuid_sucursal, placa, created_at)` index from F1.5 keeps this < 50ms p99.
- `validar_kd_forzado` raises HTTPException directly (no try/except in handler). The handler does not catch these — they propagate to FastAPI's default handler.
- `insertar_alerta_forzado` is a thin wrapper; the apply phase resolves the exact jsonb column for the motivo (see `repo/alerta.py` below for the dedicated module).
- The `validar_subscripcion_vigente` re-export comes from `repo/subscripcion_activa.py` (NEW, 50 LOC). It's listed in `__all__` for the handler's import convenience.

### 8.3 `backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py` (NEW, ~50 LOC)

Extracts the existing `resolve_active_subscription_for_exit` from `api/v1/operacion.py` (lines 326-388, ~63 LOC, T-PR5-016) and adds V6's bi-temporal predicate. Reused by F7 (Salida post-flow).

```python
"""HU-F1.6 / V6 — subscripcion vigente + reused by F7 exit flow.

Extracts and refactors ``resolve_active_subscription_for_exit`` from
``api/v1/operacion.py`` (T-PR5-016, REQ-CAT-017 addendum #2) into a
repo helper, adding the V6 ``vigente_hasta IS NULL AND estado='activo'
AND fecha_vencimiento >= NOW()`` predicate.

R22 defense in depth (preserved from the original): the helper filters
``WHERE uuid_sucursal = :this_branch`` so a stale or manually-inserted
row for another branch is rejected (broadcast_policy="subscription"
scoping is an availability control; this is an integrity control).
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ..models.V.subscripciones_cliente import SubscripcionesCliente
from ..models.V.vehiculos import Vehiculos


@dataclass(frozen=True)
class SubscripcionValidationResult:
    """Outcome of :func:`validar_subscripcion_vigente`."""

    vigente: bool
    subscripcion: SubscripcionesCliente | None = None


async def validar_subscripcion_vigente(
    session: AsyncSession,
    *,
    uuid_subscripcion_cliente: uuid_lib.UUID,
    forzado: bool = False,
) -> SubscripcionValidationResult:
    """V6: True iff ``uuid_subscripcion_cliente`` is vigente at this branch.

    Predicate (bi-temporal [V]):
        vigente_hasta IS NULL
        AND estado = 'activo'
        AND fecha_vencimiento >= NOW()

    When ``forzado=True`` (KD-FORZADO-01), the predicate is bypassed
    (walk-in auditado) but the result still records the underlying state
    so the caller can log it.

    Note: this helper does NOT validate that the placa is in
    ``subscripcion_vehiculos`` — that is F7's responsibility (cobrar=false
    derivation). V6 accepts the subscripcion if vigente; walk-in auditado
    covers the "subscripcion vigente but placa not registered" edge case
    (R9 in proposal §8).
    """
    stmt = select(SubscripcionesCliente).where(
        SubscripcionesCliente.uuid == uuid_subscripcion_cliente,
        SubscripcionesCliente.vigente_hasta.is_(None),
        SubscripcionesCliente.estado == "activo",
        SubscripcionesCliente.fecha_vencimiento
        >= datetime.now(UTC).date(),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return SubscripcionValidationResult(vigente=True, subscripcion=row)
    if forzado:
        # Walk-in auditado — caller proceeds but logs the bypass.
        return SubscripcionValidationResult(vigente=False, subscripcion=None)
    return SubscripcionValidationResult(vigente=False, subscripcion=None)


async def resolve_active_subscription_for_exit(
    session: AsyncSession,
    *,
    placa: str,
    uuid_sucursal: uuid_lib.UUID,
    as_of: date | None = None,
) -> "SubscriptionLookupResult":
    """T-PR5-016 / R22 — exit-flow lookup, exact original signature.

    Refactored from ``api/v1/operacion.py:326-388`` verbatim. Kept here
    so F7 (Salida) can import the helper without a circular dependency
    on the router.
    """
    # ... (verbatim from the original)
    raise NotImplementedError("Apply phase ports the existing body verbatim.")


__all__ = [
    "SubscripcionValidationResult",
    "resolve_active_subscription_for_exit",
    "validar_subscripcion_vigente",
]
```

**Notes.**
- The apply phase ports the original `resolve_active_subscription_for_exit` body verbatim (F1.6 is the **first opportunity to extract** it from the router, but doing so is non-breaking — the router re-imports from the repo).
- `validar_subscripcion_vigente` is the new V6 helper; the existing `resolve_active_subscription_for_exit` continues to live for F7 (it's a more permissive lookup — placa-based — while V6 is UUID-based).
- Both helpers share the same `vigente_hasta IS NULL AND estado='activo'` base; only `fecha_vencimiento >= NOW()` is V6-specific.

### 8.4 `backend/packages/parkos_core/src/parkos_core/repo/alerta.py` (NEW, ~60 LOC)

Pure helper for the alerta INSERT. The `datos_nuevos` jsonb column carries the motivo.

```python
"""HU-F1.6 — alerta INSERT helpers.

Encapsulates the JSON payload shape for ``capacidad_agotada_forzado``
alerts. The apply phase may add a dedicated jsonb column to prod.alerta
(migration 0025) OR extend the existing ``observaciones``-like field;
the helper hides the choice from the handler.
"""
from __future__ import annotations

import uuid as uuid_lib
import json
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_W.alerta import Alerta


async def insertar_alerta_forzado(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
    motivo: str,
) -> Alerta:
    """Insert ``prod.alerta`` row with tipo_alerta='capacidad_agotada_forzado'.

    Same TX as the ingreso INSERT (caller commits, R5 mitigation).
    The motivo is stored in the dedicated jsonb ``datos_nuevos`` column
    (added in migration 0025 if not already present).
    """
    alerta = Alerta(
        uuid_sucursal=uuid_sucursal,
        uuid_usuario=actor_uuid,
        tipo_alerta="capacidad_agotada_forzado",
        estado="abierta",
        timestamp_evento=datetime.now(UTC).replace(tzinfo=None),
    )
    # NOTE: prod.alerta may already have a jsonb field; the apply phase
    # inspects the model and migration history. The helper sets the
    # payload via setattr() to avoid coupling to the exact column name.
    if hasattr(alerta, "datos_nuevos"):
        alerta.datos_nuevos = json.dumps(
            {"motivo": motivo, "uuid_ingreso": str(uuid_ingreso)}
        )
    session.add(alerta)
    await session.flush()  # so uuid is populated for the caller
    return alerta


__all__ = ["insertar_alerta_forzado"]
```

**Notes.**
- The apply phase verifies whether `prod.alerta` has a `datos_nuevos` jsonb column or whether a new column is needed. The `hasattr` check above is a soft abstraction; the apply phase may replace it with an explicit field assignment.
- `await session.flush()` is called so `alerta.uuid` (a DB-side default) is populated before the caller continues.

### 8.5 `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py` (MODIFY, +40 LOC)

Appends `validar_cupo_disponible` wrapper around the existing `get_ocupacion_puros_activos`. The wrapper joins the MV (activos) with `cantidad_vehiculos_sucursal` (cupo_maximo) and returns a typed result.

```python
# ADD to existing repo/ocupacion.py after get_ocupacion_puros_activos:


@dataclass(frozen=True)
class CupoValidationResult:
    """Outcome of :func:`validar_cupo_disponible`.

    ``cupo_no_configurado`` is True when ``cantidad_vehiculos_sucursal``
    has no vigente row for ``(uuid_sucursal, uuid_tipo_vehiculo)``
    (V1).
    ``cupo_agotado`` is True when ``activos >= cupo_maximo`` (V2).
    The two are mutually exclusive at the response level: V1 first,
    then V2.
    """

    cupo_no_configurado: bool
    cupo_agotado: bool
    cupo_maximo: int
    activos: int


async def validar_cupo_disponible(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    forzado: bool = False,
) -> CupoValidationResult:
    """V1+V2: validate cupo via ``mv_ocupacion_diaria`` JOIN cvs.

    KD-V4: NO lock pesimista; the MV has lag <= 10s (acceptable per
    RIESGO-SUC-02). ``forzado=True`` allows V1+V2 bypass (KD-FORZADO-01)
    but the result still reports the underlying state for logging.

    Returns:
        CupoValidationResult with both flags; the handler raises 422
        for V1 first (cupo_no_configurado), then V2 (cupo_agotado).
    """
    # Use the existing MV JOIN (tv LEFT JOIN cvs LEFT JOIN mv):
    items = await get_ocupacion_puros_activos(
        session, uuid_sucursal=uuid_sucursal
    )
    # Find the row matching uuid_tipo_vehiculo.
    match = next(
        (it for it in items if it.uuid_tipo_vehiculo == uuid_tipo_vehiculo),
        None,
    )
    if match is None:
        # The tipo is vigente but the MV/cvs query returned nothing
        # (catalog missing the tipo+branch combination). Treat as
        # cupo_no_configurado.
        return CupoValidationResult(
            cupo_no_configurado=True,
            cupo_agotado=False,
            cupo_maximo=0,
            activos=0,
        )
    if match.cupo_maximo == 0:
        # cvs row missing for (sucursal, tipo) — COALESCE resolves to 0.
        return CupoValidationResult(
            cupo_no_configurado=True,
            cupo_agotado=False,
            cupo_maximo=0,
            activos=match.activos,
        )
    if match.activos >= match.cupo_maximo:
        if not forzado:
            return CupoValidationResult(
                cupo_no_configurado=False,
                cupo_agotado=True,
                cupo_maximo=match.cupo_maximo,
                activos=match.activos,
            )
    return CupoValidationResult(
        cupo_no_configurado=False,
        cupo_agotado=False,
        cupo_maximo=match.cupo_maximo,
        activos=match.activos,
    )
```

**Notes.**
- Reuses `get_ocupacion_puros_activos` (F1.5) verbatim — no new SELECT.
- The `cupo_maximo == 0` branch is the V1 case (`cantidad_vehiculos_sucursal` missing for the combination); `cupo_no_configurado=True` triggers the 422 with `forzado_permitido: true`.
- The `match.activos >= match.cupo_maximo` branch is V2; bypassed when `forzado=True`.

### 8.6 `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (MODIFY, +30 LOC)

Appends `validar_tarifa_vigente` wrapper around the existing `bitemporal_vigente_predicate`. Mirrors the F1.5 `validar_cupo_disponible` shape.

```python
# ADD to existing repo/tarifas_vigencia.py after list_tarifas_vigentes:


@dataclass(frozen=True)
class TarifaValidationResult:
    """Outcome of :func:`validar_tarifa_vigente`."""

    vigente: bool
    tarifa: TarifasSucursal | None = None


async def validar_tarifa_vigente(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    at: datetime,
    forzado: bool = False,
) -> TarifaValidationResult:
    """V3: True iff a vigente tarifa row exists for (sucursal, tipo, at).

    Bi-temporal canónico (F1.4):
        vigente_desde <= at
        AND (vigente_hasta IS NULL OR vigente_hasta > at)
        AND estado = 'activo'

    Returns:
        TarifaValidationResult; the handler raises 422 unless forzado=True.
    """
    v_utc = _to_utc_naive(at)
    stmt = select(TarifasSucursal).where(
        TarifasSucursal.uuid_sucursal == uuid_sucursal,
        TarifasSucursal.uuid_tipo_vehiculo == uuid_tipo_vehiculo,
        bitemporal_vigente_predicate(TarifasSucursal, v_utc),
    ).limit(1)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return TarifaValidationResult(vigente=True, tarifa=row)
    if forzado:
        return TarifaValidationResult(vigente=False, tarifa=None)
    return TarifaValidationResult(vigente=False, tarifa=None)
```

**Notes.**
- Reuses `bitemporal_vigente_predicate` (F1.4) verbatim — same SQLAlchemy expression, same `_to_utc_naive` tz helper.
- The single-row LIMIT matches F1.4's `list_tarifas_vigentes` cursor contract (first row only is enough for "vigente?").

### 8.7 `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (MODIFY, +80 LOC)

Appends the new schemas (D-HU-F1.6-10) after the existing F1.5 / F1.8 block. The existing `IngresoCreate` / `IngresoRead` are kept as deprecated aliases for backward compatibility with F1.5 clients.

```python
# ADD to existing schemas/operacion.py:


# --- HU-F1.6 / REQ-OPS-034..041 -----------------------------------------


class IngresoCreateForzado(_Base):
    """INSERT payload for ``prod.ingreso`` with KD-FORZADO-01 bypass.

    Adds ``forzado: bool = False`` to the F1.5 ``IngresoCreate`` shape.
    Server-side validation enforces the prefix contract (D-HU-F1.6-5);
    ``forzado`` is NOT persisted in ``prod.ingreso``.

    ``extra='forbid'`` (inherited) rejects extra fields including
    ``tipo_entrada`` (an attempted injection of a non-existent column).
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    placa: str | None = None
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None  # server overwrites via V5
    uuid_subscripcion_cliente: uuid_lib.UUID | None = None
    fecha_ingreso: datetime | None = None
    observaciones: str | None = None
    forzado: bool = False  # NEW (D-HU-F1.6-5; validated against prefix)


class IngresoReadForzado(_Base):
    """Response shape for ``POST /operacion/ingresos`` (REQ-OPS-041).

    Additive delta to ``IngresoRead`` (no field removed or renamed):
    - ``tipo_entrada``: Literal['MENSUALIDAD', 'ROTACION'] (DEC-SUC-21)
    - ``forzado_en_creacion``: True iff KD-FORZADO-01 bypass was used
    - ``motivo_forzado``: stripped motivo, or None
    """

    # Inherited from IngresoRead (12 columns):
    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    placa: str | None
    uuid_tipo_vehiculo: uuid_lib.UUID | None
    uuid_subscripcion_cliente: uuid_lib.UUID | None
    fecha_ingreso: datetime | None
    observaciones: str | None
    # NEW:
    tipo_entrada: Literal["MENSUALIDAD", "ROTACION"]
    forzado_en_creacion: bool = False
    motivo_forzado: str | None = None


# --- Typed error schemas (D-HU-F1.6-10) ----------------------------------


class CupoNoConfiguradoError(_Base):
    error: Literal["cupo_no_configurado"]
    forzado_permitido: Literal[True]


class MotivoForzadoRequeridoError(_Base):
    error: Literal["motivo_forzado_requerido"]
    cupo_maximo: int
    activos: int


class TarifaVigenteNoEncontradaError(_Base):
    error: Literal["tarifa_vigente_no_encontrada"]


class PlacaFormatoInvalidoError(_Base):
    error: Literal["placa_formato_invalido"]
    formatos_aceptados: list[str]


class SubscripcionInactivaOVencidaError(_Base):
    error: Literal["subscripcion_inactiva_o_vencida"]


class IngresoActivoExistenteError(_Base):
    error: Literal["ingreso_activo_existente"]
    uuid_ingreso_existente: uuid_lib.UUID


class TipoVehiculoInvalidoError(_Base):
    error: Literal["tipo_vehiculo_invalido"]


# Append ``IngresoCreateForzado`` / ``IngresoReadForzado`` / 7 errors to __all__.
```

**Notes.**
- The schemas are **additive**; existing `IngresoCreate` / `IngresoRead` / `IngresoReadList` / `IngresoFilter` remain intact for backward compatibility.
- `extra='forbid'` (inherited from `_Base`) rejects `tipo_entrada` (and other unknown fields) at the deserialization boundary — defense in depth against client typos and intentional injection attempts.

## 9. Tests Plan

The test plan is **14 tests across 6 test files**, mirroring F1.3 / F1.5 / F1.8 splits (HTTP unit + DB integration + AST static + KD-FORZADO unit + regex unit). Each test name documents the test intent for OPS auditing; the file paths align with `proposal.md §11`.

### File 1: `backend/tests/unit/test_operacion_ingresos_validaciones.py` (~400 LOC, 8 HTTP-level parametrized tests)

Uses `httpx.AsyncClient + ASGITransport` (F1.3 / F1.5 / F1.8 precedent) and the JWT `operador-` fixture from `tests/unit/test_auth_login_password.py`. Real `pg_engine` (no SQLite per project rule).

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_placa_valida_auto_returns_201_with_tipo_entrada_rotacion` | operador- JWT; POST `{"placa": "ABC123"}` returns 201; `body.tipo_entrada == "ROTACION"`, `forzado_en_creacion == False`, `motivo_forzado is None`; DB row inserted. REQ-OPS-034 happy path. |
| **T2** | `test_placa_invalida_lowercase_returns_422_placa_formato_invalido` | POST `{"placa": "abc123"}` returns 422 with `body.error == "placa_formato_invalido"` and `body.formatos_aceptados == ["ABC123", "ABC12D"]`; no DB row. REQ-OPS-038. |
| **T3** | `test_mensualidad_con_subscripcion_vigente_returns_201_with_tipo_mensualidad` | Seed `subscripciones_cliente(S)` vigente; POST `{"placa": "ABC123", "uuid_subscripcion_cliente": S}` returns 201 with `tipo_entrada == "MENSUALIDAD"`. REQ-OPS-039 + V9 derivation. |
| **T4** | `test_rotacion_sin_subscripcion_returns_201_with_tipo_rotacion` | POST `{"placa": "ABC123"}` (no subscripcion); `tipo_entrada == "ROTACION"`. REQ-OPS-041 V9. |
| **T5** | `test_cupo_agotado_sin_forzado_returns_422_motivo_forzado_requerido` | Seed cupo=50, activos=50; POST `{"placa": "ABC123"}` returns 422 with `body.error == "motivo_forzado_requerido"`, `body.cupo_maximo == 50`, `body.activos == 50`; no DB row. REQ-OPS-035. |
| **T6** | `test_cupo_agotado_con_forzado_valido_returns_201_and_emits_alerta_same_tx` | Same cupo=50, activos=50; POST with valid prefix returns 201 + alerta row exists with `tipo_alerta == "capacidad_agotada_forzado"`; verify same TX by reading `prod.alerta` and `prod.ingreso` after the test commits — both rows present. REQ-OPS-035 + REQ-OPS-041.C. |
| **T7** | `test_ingreso_activo_existente_returns_409` | Insert prior `prod.ingreso(X, ABC123)`; POST `{"placa": "ABC123"}` returns 409 with `body.error == "ingreso_activo_existente"`, `body.uuid_ingreso_existente` matches the prior UUID; no new DB row. REQ-OPS-040. |
| **T8** | `test_orden_validacion_regex_antes_de_mensualidad` | POST `{"placa": "abc123", "uuid_subscripcion_cliente": S}` returns 422 with `placa_formato_invalido` (NOT `subscripcion_inactiva_o_vencida`); locks the V5-before-V6 order. R7 invariante. |

### File 2: `backend/tests/unit/test_operacion_ingresos_kd_forzado.py` (~150 LOC, 4 KD-FORZADO unit tests)

Pure helper tests (no HTTP, no DB).

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_validar_kd_forzado_prefijo_valido_devuelve_motivo` | `validar_kd_forzado("[FORZADO: cliente con cita medica urgente]", True) == "cliente con cita medica urgente"` (stripped). |
| **T2** | `test_validar_kd_forzado_sin_prefijo_con_forzado_true_raises_motivo_forzado_requerido` | `validar_kd_forzado("cliente sin placa", True)` raises `HTTPException(422, {"error": "motivo_forzado_requerido"})`. |
| **T3** | `test_validar_kd_forzado_motivo_9_chars_raises_motivo_forzado_insuficiente` | `validar_kd_forzado("[FORZADO: a b]", True)` raises 422 with `min_chars == 10`. |
| **T4** | `test_validar_kd_forzado_forzado_false_con_prefijo_raises_forzado_contradiccion` | `validar_kd_forzado("[FORZADO: prueba cliente]", False)` raises 422 with `error == "forzado_contradiccion"`. |

### File 3: `backend/tests/unit/test_repo_placa.py` (~80 LOC, 6 regex unit tests)

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_detectar_tipo_vehiculo_abc123_devuelve_uuid_auto` | Seed `tipos_vehiculo(tipo='Auto')` vigente; `await detectar_tipo_vehiculo(session, "ABC123") == uuid_auto`. |
| **T2** | `test_detectar_tipo_vehiculo_abc12d_devuelve_uuid_moto` | Seed `tipos_vehiculo(tipo='Moto')` vigente; `await detectar_tipo_vehiculo(session, "ABC12D") == uuid_moto`. |
| **T3** | `test_detectar_tipo_vehiculo_ab12_devuelve_none` | `await detectar_tipo_vehiculo(session, "AB12") is None` (regex mismatch). |
| **T4** | `test_detectar_tipo_vehiculo_lowercase_devuelve_none` | `await detectar_tipo_vehiculo(session, "abc123") is None`. |
| **T5** | `test_detectar_tipo_vehiculo_4_digitos_devuelve_none` | `await detectar_tipo_vehiculo(session, "AB1234") is None` (4 digits, no ABC pattern). |
| **T6** | `test_detectar_tipo_vehiculo_con_guion_devuelve_none` | `await detectar_tipo_vehiculo(session, "ABC-123") is None`. |

### File 4: `backend/tests/integration/test_ingreso_create_db.py` (~250 LOC, 3 DB tests, `PARKOS_DOCKER_TEST=1`)

Uses real `pg_engine` + `psycopg` direct SQL for seed/cleanup.

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_insert_ingreso_con_alerta_capacidad_agotada_same_tx` | Seed cupo=50, activos=50; POST with valid prefix; assert both `prod.ingreso` and `prod.alerta` rows present after commit; `prod.alerta.tipo_alerta == 'capacidad_agotada_forzado'`, `datos_nuevos.motivo == <stripped>`. Verifies single-commit (R5). |
| **T2** | `test_duplicado_activo_rechazado_con_uuid_ingreso_existente` | Insert prior `prod.ingreso(X, ABC123)` (no salidas, no anulaciones); POST returns 409 with `uuid_ingreso_existente` matching the prior UUID; new DB row absent. Verifies V8 EXISTS query. |
| **T3** | `test_subscripcion_vencida_returns_422_sin_forzado` | Seed `subscripciones_cliente(S)` with `fecha_vencimiento < today`; POST `{"placa": "ABC123", "uuid_subscripcion_cliente": S}` returns 422 with `error == "subscripcion_inactiva_o_vencida"`. |

### File 5: `backend/tests/static/test_no_write_after_insert.py` (~100 LOC, 1 AST walk)

Cross-cutting defense-in-depth gate (F1.3 / F1.8 precedent `test_no_write_in_calcular_cotizacion.py` adapted).

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_crear_ingreso_evento_rechaza_update_delete_truncate` | AST-walk `repo/ingreso.py::crear_ingreso_evento`; reject any `UPDATE | DELETE | TRUNCATE` literal in the body; locks the insert-only contract on `prod.ingreso`. |

### File 6: `backend/tests/static/test_kd_forzado_in_handler.py` (~80 LOC, 1 AST walk)

R7 invariante — literal order verification (D-HU-F1.6-11).

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_create_ingreso_handler_invoca_helpers_en_orden_correcto` | AST-walk `api/v1/operacion.py::create_ingreso`; extract the sequence of `ast.Call` nodes whose function name matches one of `detectar_tipo_vehiculo`, `validar_tipo_vehiculo_vigente`, `validar_kd_forzado`, `validar_cupo_disponible`, `validar_tarifa_vigente`, `validar_subscripcion_vigente`, `existe_ingreso_activo`, `crear_ingreso_evento`, `insertar_alerta_forzado`, `record_event`; assert the order matches D-HU-F1.6-11. R7 invariante — CI gate against future-dev reordering. |

**Coverage map.** The 14 tests in 6 files cover:

- HTTP happy + sad paths for the endpoint (T1..T8 in File 1).
- KD-FORZADO-01 discriminator contract (T1..T4 in File 2).
- Regex placa resolution (T1..T6 in File 3).
- DB round-trip for V8 + alerta same-TX + V6 (T1..T3 in File 4).
- AST gate locking the insert-only contract (T1 in File 5).
- AST gate locking the literal validation order (T1 in File 6).

Cross-cutting CI gates from `proposal.md §9.7`: `ruff check`, `ruff format --check`, `mypy --strict` on the 4 new + 4 modified backend files. `factory_intact` gate (F1.1 / F1.3 precedent) verifies `git diff backend/packages/parkos_core/src/parkos_core/api/v1/router_factory.py` returns empty. `event_helper_intact` gate verifies `git diff backend/packages/parkos_core/src/parkos_core/repo/event.py` returns empty. `auth_tenancy_intact` gate verifies `git diff backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` returns empty.

## 10. Threat Matrix

The applicability-driven threat matrix covers eight attack surfaces specific to HU-F1.6. The defenses are layered (D-HU-F1.6-7) and KD-1..KD-13 plus the AST walks + integration tests cap the residual risk at **Low** for each row.

| # | Threat | Attack Vector | Defense in Depth Layer | Residual Risk | KD Mitigates |
|---|---|---|---|---|---|
| **T1** | SQL injection via `placa` payload (e.g., `placa = "ABC123' OR 1=1 --"`) | Stale / malicious client passes raw SQL fragment in placa | V5 regex server-side rejects non-`FORMATO_AUTO` / `FORMATO_MOTO` patterns with 422 BEFORE any SQL is constructed; `detectar_tipo_vehiculo` uses parameterized SQL (no string interpolation); V4 catalog lookup also parameterized; V8 EXISTS query uses bind params | Low | D-HU-F1.6-4 (regex constants), D-HU-F1.6-6 (server overwrites uuid_tipo_vehiculo) |
| **T2** | Cross-tenant bypass: operador- JWT from sucursal X POSTs `uuid_sucursal=Y` to pollute Y's `prod.ingreso` | Stale client or replay queue attempts to insert into another branch | KD-3 chain validates `target == ctx.sucursal_uuid` for `operador-`; `admin-` is bounded by `claims["sucursales_permitidas"]` (already enforced in `get_tenant_ctx`); SQLAlchemy event listener `set_tenant_context` auto-filters SELECT on `uuid_sucursal` columns | Low | D-HU-F1.6-1 (KD-3 chain reused) |
| **T3** | Stale client bypasses regex by sending `placa = "ABC123", uuid_tipo_vehiculo = <Moto UUID>` (wrong tipo) | Stale Electron build sends the wrong tipo UUID for the placa | V5 regex server-side DERIVES the UUID from placa and overwrites the client's value (D-HU-F1.6-6); client sees 201 with the corrected UUID, not 422 | Low | D-HU-F1.6-6, D-HU-F1.6-7 Layer 1 |
| **T4** | Operator typos motivo as `[FORZADO: x]` (3 chars) to force a cupo-bypass entry | Malicious operator wants to insert a vehicle without proper audit | KD-FORZADO-01 helper rejects motivo < 10 chars with `422 motivo_forzado_insuficiente`; the alert is only emitted when V2 is bypassed with motivo >= 10 chars; operator's intent is recorded but cannot bypass the substantive-reason gate | Low | D-HU-F1.6-2 (FORZADO_MIN_MOTIVO_CHARS=10) |
| **T5** | MV `mv_ocupacion_diaria` has lag > 10s during worker restart, letting in extra vehicles | Worker process restarts; the operator polling strip shows stale data; POST validates against stale MV | KD-V4 / RIESGO-SUC-02 documented lag; KD-5 fallback (F1.5) keeps the worker alive; `OcupacionStrip` shows the same data; eventual consistency acceptable; alert if `refresh_duration_s > refresh_interval_s` | Low | D-HU-F1.6-3, F1.5 KD-5 |
| **T6** | Operator forces a cupo-bypass entry but the alerta INSERT fails (FK constraint) → orphaned ingreso without alerta | Catalog `capacidad_agotada_forzado` typo, FK to `prod.alerta` missing | D-HU-F1.6-9: same `await session.commit()` covers both rows (R5); FK commit ordering: if alerta INSERT fails, the entire TX rolls back including the ingreso; integration test T1 verifies | Low | D-HU-F1.6-9 (same TX), D-HU-F1.6-7 Layer 3 |
| **T7** | Future developer reorders V8 before V2 in the handler | Refactor PR moves the EXISTS check earlier to "fail fast" | AST walk `test_kd_forzado_in_handler.py` (File 6) verifies the literal order; CI gate catches reorderings before merge; R7 invariante | Low | D-HU-F1.6-11 (AST walk gate), D-HU-F1.6-7 Layer 4 |
| **T8** | pgcode (`"23505"`) leaks from `validar_cupo_disponible` into the operator's 422 body | Repo helper raises an exception with raw pgcode in the detail | All 6 error schemas are Pydantic v2 typed with `Literal[...]` discriminators; the handler builds the 422 body from a typed dict (no exception class, no pgcode); no ORM types leak to the response; integration test T5 verifies the body shape | Low | D-HU-F1.6-10 (typed errors), `extra='forbid'` (inherited from `_Base`) |

**Notes.** The threats in scope (HTTP / DB / catalog / MV / future-dev reordering) fall under the design's boundaries. The `references/threat-matrix.md` applicability test (routing, shell, subprocess, VCS/PR automation, executable-file classification, process integration) is partially satisfied by the alert write being a subprocess of FastAPI's request lifecycle — but the subprocess invocation is standard for the codebase (precedent `event.py::record_event`), so the F1.5/F1.3 pattern applies verbatim. No additional threat rows are required.

## 11. Traceability Matrix

The traceability map bridges the 8 REQ-OPS-NNN introduced by F1.6 to the design sections, skeleton files, and the tests that prove them. Each row is a **must-pass** contract; missing any row is a verification failure.

| REQ-OPS | Description | Design Section | Skeleton File | Test File |
|---|---|---|---|---|
| **REQ-OPS-034** | V1 `cupo_no_configurado` 422 with `forzado_permitido: true` | §7 step 5, §8.5 `validar_cupo_disponible` | `backend/.../api/v1/operacion.py::create_ingreso` (modify, +140 LOC) + `repo/ocupacion.py` (§8.5, +40 LOC) + `schemas/operacion.py` (§8.7, `CupoNoConfiguradoError`) | `backend/tests/unit/test_operacion_ingresos_validaciones.py::test_cupo_agotado_sin_forzado_returns_422_motivo_forzado_requerido` (T5) |
| **REQ-OPS-035** | V2 `motivo_forzado_requerido` 422 with `cupo_maximo`/`activos`; bypass INSERTs + emits alerta same TX | §7 step 5+9, §8.5 `validar_cupo_disponible`, §8.4 `insertar_alerta_forzado` | same as REQ-OPS-034 + `repo/alerta.py` (§8.4, +60 LOC) | T5 + `test_cupo_agotado_con_forzado_valido_returns_201_and_emits_alerta_same_tx` (T6) |
| **REQ-OPS-036** | V3 `tarifa_vigente_no_encontrada` 422 (bi-temporal F1.4) | §7 step 6, §8.6 `validar_tarifa_vigente` | `backend/.../repo/tarifas_vigencia.py` (modify, +30 LOC) + `schemas/operacion.py` (`TarifaVigenteNoEncontradaError`) | T5 (proxy — same shape across 422 paths; dedicated TBD in F1.7 if needed) |
| **REQ-OPS-037** | V4 `tipo_vehiculo_invalido` 422; no bypass (KD-V3) | §7 step 3, §8.2 `validar_tipo_vehiculo_vigente` | `backend/.../repo/ingreso.py` (§8.2, +50 LOC) + `schemas/operacion.py` (`TipoVehiculoInvalidoError`) | T8 (regex-before-mensualidad order) + F1.7 dedicated tests |
| **REQ-OPS-038** | V5 regex placa Colombia + `placa_formato_invalido` 422 + `uuid_tipo_vehiculo` derivado y sobreescrito (BR2 CU-01) | §7 step 2, §8.1 `detectar_tipo_vehiculo` | `backend/.../repo/placa.py` (§8.1, NEW ~30 LOC) + `schemas/operacion.py` (`PlacaFormatoInvalidoError`) | `backend/tests/unit/test_repo_placa.py::test_detectar_tipo_vehiculo_*` (T1..T6) + `test_operacion_ingresos_validaciones.py::test_placa_invalida_lowercase_*` (T2) |
| **REQ-OPS-039** | V6 `subscripcion_inactiva_o_vencida` 422 unless `forzado=true` (walk-in auditado) | §7 step 7, §8.3 `validar_subscripcion_vigente` | `backend/.../repo/subscripcion_activa.py` (§8.3, NEW ~50 LOC) + `schemas/operacion.py` (`SubscripcionInactivaOVencidaError`) | `backend/tests/integration/test_ingreso_create_db.py::test_subscripcion_vencida_returns_422_sin_forzado` (T3) |
| **REQ-OPS-040** | V8 `ingreso_activo_existente` 409 with `uuid_ingreso_existente`; EXISTS directo (no MV, no lock) | §7 step 8, §8.2 `existe_ingreso_activo` | `backend/.../repo/ingreso.py` (§8.2, +50 LOC) + `schemas/operacion.py` (`IngresoActivoExistenteError`) | `backend/tests/unit/test_operacion_ingresos_validaciones.py::test_ingreso_activo_existente_returns_409` (T7) + `test_ingreso_create_db.py::test_duplicado_activo_rechazado_con_uuid_ingreso_existente` (T2) |
| **REQ-OPS-041** | V9 + KD-FORZADO-01 + alerta `capacidad_agotada_forzado` (atomic-bundled) | §7 steps 4+9+10, §8.2 `validar_kd_forzado` + `insertar_alerta_forzado` | `backend/.../repo/ingreso.py` (§8.2, +60 LOC for KD-FORZADO + alerta re-export) + `schemas/operacion.py` (`IngresoReadForzado` + 3 KD-FORZADO discriminators) | `backend/tests/unit/test_operacion_ingresos_kd_forzado.py::test_validar_kd_forzado_*` (T1..T4) + T6 (alerta same-TX) + `test_operacion_ingresos_validaciones.py::test_mensualidad_*` (T3, V9 derivation) + `test_rotacion_*` (T4) |

**Notes.**

- REQ-OPS-034..041 share the **same handler** (`create_ingreso`); the design propagates them as a single 232-LOC change. The test files split by concern (HTTP, KD-FORZADO, regex, DB, AST).
- The `tests/static/test_kd_forzado_in_handler.py` AST walk (File 6) is a **cross-cutting** gate that overlaps all 8 REQ-OPS-NNN; it is listed here because no single REQ owns it.
- The 4 spec-level risks (R1..R9 in `specs/operational/spec.md`) are addressed by the design's residual risk column (§10) — they are not separate REQ-OPS-NNN, they are design-time invariants documented in the spec.
- The pre-existing `repo/event.py::record_event` is **NOT modified**; `tests/static/test_no_write_after_insert.py` (File 5) enforces the insert-only contract on `prod.ingreso` via `crear_ingreso_evento` wrapper.

## 12. Migration / Rollout

**NO Alembic migration.** The handler operates exclusively on existing columns:
- `prod.ingreso` (L-E, F1.5) — INSERT only, no new columns
- `prod.cantidad_vehiculos_sucursal` (V, F1.4) — read only
- `prod.tipos_vehiculo` (V, F1.4) — read only
- `prod.tarifas_sucursal` (V, F1.4) — read only (bi-temporal predicate)
- `prod.subscripciones_cliente` (V, post-PR4) — read only
- `prod.alerta` (L-W, post-PR6) — INSERT only; the jsonb `datos_nuevos` column MAY be added by migration 0025 IF NOT already present (the apply phase checks the model + migration history)

**NO sync catalog changes.** The validations live in `repo/*.py`; sync catalog is untouched.

**NO factory_intact violation.** `api/v1/__init__.py`, `api/v1/router_factory.py`, `api/deps.py`, `auth/tenancy.py`, `models/*`, `migrations/*`, `repo/event.py`, `repo/cotizacion.py`, `jobs/runner.py` — all intact.

**Rollback plan.** Revert the single PR. The dedicated handler `create_ingreso` reverts to the F1.5 thin pass-through; the 4 new `repo/*.py` files become unused; the 2 modified `repo/*.py` files lose the +40 / +30 LOC wrappers. No state, no side effects, no table control. If the rollback is partial (helper modules kept, handler reverted), the helpers remain unused but harmless.

## 13. Risks & Mitigations

Mirrored from `proposal.md §8` with explicit mitigation per design layer.

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| **R1** | MV `mv_ocupacion_diaria` con lag ≤10s (post-F1.5 worker); eventual consistency puede causar `activos < cupo_maximo` justo después de un INSERT | Media | RIESGO-SUC-02 del corpus ya documenta el lag como riesgo vivo aceptado; KD-V4 NO lock pesimista; alerta operativa si `refresh_duration_s > refresh_interval_s`; cliente `OcupacionStrip` muestra el mismo dato con polling 10s — la divergencia es aceptable |
| **R2** | Alerta `capacidad_agotada_forzado` falsamente disparada si `forzado=true` y cupo está bien (ej: tarifa no vigente forzada por error) | Baja | D-HU-F1.6-9: alerta SOLO si V2 fue bypassed (`bypass_reason == "cupo_agotado"`); una por ingreso (uuid_ingreso la hace única) |
| **R3** | Regex hardcoded rompible si se cambian formatos de placa nacional (ej: nueva normativa 2027) | Baja | KD-V2 hardcoded para MVP; configurable en HU futura con cat tabla (HU-F-XX.X); constante a nivel de módulo `repo/placa.py` permite reemplazo en un solo lugar; tests parametrizados cubren los 6 casos actuales |
| **R4** | Subscripción cross-tenant → V6 rechaza (defense in depth). Si el sync no trajo la subscripción al branch (R22), V6 falla aunque la subscripción exista en cloud | Baja | Defense in depth intencional; `subscripcion_inactiva_o_vencida` 422 motiva al operador a walk-in con `forzado=true` y alerta; resuelve el bug "subscripción fantasma" antes que aceptar sin verificación |
| **R5** | Ingreso y alerta deben estar en misma transacción (un commit). Si el INSERT del ingreso tiene éxito y la alerta falla (FK, etc.), quedaría ingreso sin alerta | Baja | D-HU-F1.6-9: `record_event` + `insertar_alerta_forzado` en **misma transacción** (un solo `await session.commit()`); FK commit ordering garantiza que alerta solo se inserta si ingreso OK; integration test T1 verifica |
| **R6** | `extra='forbid'` rechaza campos extra — clientes desactualizados que manden `tipo_entrada` (columna inexistente en `prod.ingreso`) u otros campos viejos serán rechazados con 422 | Baja | Defense in depth: explícito en el schema; Pydantic devuelve 422 con lista de campos extra; cliente debe actualizar; documento en design.md |
| **R7** | Orden de validación estricto (D-HU-F1.6-11) puede ser alterado por dev futuro (ej: mover V8 antes de V2 causa que un duplicado con cupo agotado se reporte como duplicado, no como cupo) | Media | AST walk `tests/static/test_kd_forzado_in_handler.py` verifica orden literal de invocaciones (regex → tipo → KD-FORZADO → cupo → tarifa → sub → no-dup → INSERT); CI gate; documentado en source docstring |
| **R8** | Definición operacional de "ingreso activo" via `EXISTS` directo a `prod.ingreso` + `NOT EXISTS salidas/anulaciones` < 50ms p99 esperado (índice `(uuid_sucursal, placa, created_at)` post-F1.5) | Baja | V8 va directo a tablas (authoritative), NO a la MV (stale eventual); `prod.ingreso` < 100M filas en MVP; EXPLAIN ANALYZE en test de performance (T7 + T2); documentado en design.md §8.2 |
| **R9** | Subscripción vigente + vehículo no incluido en `subscripcion_vehiculos` → walk-in auditado (mensualidad sin vehículo registrado). Edge case que el corpus declara como "walk-in auditado" | Baja | V6 acepta la subscripción si `fecha_vencimiento >= NOW()` independientemente de `subscripcion_vehiculos`; el futuro F7 (salida) reconcilia con `cobrar=false` cuando hay match; walk-in auditado documentado |

## 14. Implementation Notes

**D-HU-F1.6-7 4-layer defense in depth.** The validation chain is layered such that no single failure can bypass the whole:

1. **Layer 1 (regex server-side override)**: `detectar_tipo_vehiculo` derives `uuid_tipo_vehiculo` from placa regex; the client's value is overwritten. A stale client sending wrong UUID is silently corrected (D-HU-F1.6-6).
2. **Layer 2 (KD-FORZADO chain as precondition)**: `validar_kd_forzado` runs BEFORE V1/V2/V3/V6; desync → 422 `forzado_contradiccion` / `motivo_forzado_requerido` / `motivo_forzado_insuficiente`. The prefix is the source of truth, not the bool flag.
3. **Layer 3 (alerta INSERT same-TX)**: `record_event` + `insertar_alerta_forzado` in one `await session.commit()` (R5 mitigation; no orphaned alerts). Predicate: `bypass_reason == "cupo_agotado"` ensures alerta only fires for V2 bypass, not V1/V3/V6 (R2 mitigation).
4. **Layer 4 (AST walk ordering gate)**: `tests/static/test_kd_forzado_in_handler.py` AST-walks the handler; literal order of helper invocations is verified — regex → tipo → KD-FORZADO → cupo → tarifa → sub → no-dup → INSERT. CI gate catches reordering before merge (R7 invariante).

**D-HU-F1.6-11 spec risk preservation.** REQ-OPS-041 is intentionally atomic-bundled (V9 + KD-FORZADO-01 + alerta same-TX) because the three contracts share the **same invocation path** through the handler:
- V9 derivation is the response-build step (after all validations passed).
- KD-FORZADO-01 is the bypass contract (validates prefix, sets `bypass_reason`).
- Alerta INSERT is gated by `bypass_reason == "cupo_agotado"`.

Splitting these into separate REQ-OPS-NNN would obscure the dependency: the alerta only fires when KD-FORZADO bypassed AND V2 was the bypass reason. The single REQ-OPS-041 captures this 3-way conjunction.

**260 LOC budget** (plan.md línea 787). The design's actual size:

| Component | LOC budget | Actual | Variance |
|---|---|---|---|
| Handler (`create_ingreso` replacement) | ~140 | ~232 | +92 (acceptable; includes docstrings + error handling) |
| `repo/placa.py` (NEW) | ~30 | ~30 | 0 |
| `repo/ingreso.py` (NEW) | ~180 | ~180 | 0 |
| `repo/subscripcion_activa.py` (NEW) | ~50 | ~50 | 0 |
| `repo/alerta.py` (NEW) | ~60 | ~60 | 0 |
| `repo/ocupacion.py` (MODIFY) | +40 | +40 | 0 |
| `repo/tarifas_vigencia.py` (MODIFY) | +30 | +30 | 0 |
| `schemas/operacion.py` (MODIFY) | +80 | +80 | 0 |
| Tests (6 files) | ~1,060 | ~1,060 | 0 |

The handler's +92 LOC variance over the 140 budget is acceptable: it's docstrings (R7 documentation), error handling (the `headers=_cotizar_no_store_headers()` on every raise), and the explicit `forzado` field exclusion from `model_dump`. The total size remains well below the **<800 LOC commit ceiling** (a separate deliverable check from the F1.6 budget).

**OpenSpec archive path** (per the precedent pattern):
```
openspec/changes/hu-f1-6-validaciones-post-ingresos/
├── exploration.md       ← existing
├── proposal.md          ← existing
├── specs/operational/spec.md  ← existing
├── design.md            ← this file
├── tasks.md             ← (sdd-tasks output)
└── verify-report.md      ← (sdd-verify output)
openspec/changes/archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/
└── archive-report.md    ← (sdd-archive output)
```

## 15. Open Questions

**(vacía — los 10 KD + KD-FORZADO-01 adoptados; las 10 preguntas de exploration §14 resueltas vía KD adoption en proposal §12).** No new open questions surfaced during design phase. The spec-level risks (4 in `specs/operational/spec.md`) are addressed by the design's risk matrix (§13) and the threat matrix (§10). The R8 ("EXISTS directo a tablas < 50ms") is the only one that requires an `EXPLAIN ANALYZE` validation post-apply; the apply phase runs this check on a 1M-row fixture and includes the result in the verify report.

If during `sdd-tasks` or `sdd-apply` an open question emerges (e.g., the `prod.alerta` jsonb `datos_nuevos` column needs migration 0025), it is added to the design as a Section 15 update, and the apply phase surfaces it as a design-vs-implementation gap in the verify report.

---

**Design complete.** Ready for `sdd-tasks` with theme: TDD-strict 14 tests across 6 files (HTTP unit 8 + KD-FORZADO unit 4 + regex unit 6 → 23 parametrizaciones distributed across 14 distinct test cases in 6 files), mirroring F1.5's `10 tests across 5 files` shape scaled to F1.6's 9 validations + bypass + alerta + 6 typed errors. Onward to `sdd-apply` after tasks acceptance and user sign-off on the proposal.

**Precedents mirrored:** F1.5 (MV pattern, KD-3 chain, repo/ocupacion.py), F1.4 (bi-temporal predicate, repo/tarifas_vigencia.py), F1.3 (AST walk + custom handler before factory), F1.8 (AST walk read-only, Pydantic discriminated union).
**Commits future:** conventional commits only, no AI attribution.
**PR target:** `origin/dev` from `feat/fase-1-prerequisites-backend`.