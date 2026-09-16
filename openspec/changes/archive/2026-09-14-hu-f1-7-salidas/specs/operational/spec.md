# Spec: operational

> **Delta for change**: `hu-f1-7-salidas`
> **Capability**: `operational`
> **Date**: 2026-09-14
> **Source of truth**: `openspec/changes/hu-f1-7-salidas/proposal.md`
> (D-HU-F1.7-1..20, 12 KDs adopted), `exploration.md` (16 sections, V1..V5 +
> KD-FORZADO-01 reuse, 9 riesgos R1..R9, files-to-touch §16), `plan.md`
> (HU-F1.7 lines 798-841, DEC-MONO-01 orchestrator consolidation, KD-IVA
> blocker advance, KD-S7 lock continuity), `modelo_datos_er.mmd`
> (`prod.salidas` 761-777 `[A]`, `prod.ingreso` 577-596 `[L-E]`,
> `prod.impuestos` 187-207 `[V]`, `prod.tarifas_sucursal` 406-426 `[V]`,
> `prod.subscripciones_cliente` 496-518 `[V]`, `prod.alert_types` `[V]`,
> `prod.alerta` `[L-W]`).
>
> **Precedente upstream**: this delta extends the `operational` capability
> already consolidated in `openspec/specs/operations/spec.md` (last
> REQ-OPS-NNN vigente: REQ-OPS-041 after the merge of HU-F1.6 in commit
> `21097c8`). HU-F1.7 introduces 11 new requirements (REQ-OPS-042..052)
> covering the consolidated single handler `POST /api/v1/operacion/salidas`,
> the 5 server-side validations V1..V5 (V1 ingreso activo, V2 subscripción
> vigente al momento salida, V3 placa matches ingreso, V4 KD-FORZADO-01
> prefix contract verbatim F1.6, V5 tarifa vigente via F1.8 PL/pgSQL),
> the `tipo_salida` server-side derivation (DEC-SUC-21-NEW), the alerta
> same-TX contract for V2/V5 bypass (KD-S12), the partial unique index
> `one_exit_per_ingreso` (DEC-SAL-01 defense), and the inline-seed of
> `impuestos.IVA` (DEC-IMP-01 KD-IVA blocker resolution). REQ-OPS-001..041
> remain unchanged.

## Purpose

HU-F1.7 closes the symmetric "salida" half of CU-01 / CU-02 / CU-03M by
exposing **one** handler `POST /api/v1/operacion/salidas` that registers a
vehicle exit (`[A]` append-only event in `prod.salidas`) with 5 server-side
validations (V1..V5), reuses the KD-FORZADO-01 bypass contract verbatim from
F1.6 (DEC-FORZADO-01), invokes the F1.8 PL/pgSQL `prod.calcular_cotizacion`
inline within the same transaction as the INSERT (KD-S7 lock continuity on
`tarifas_sucursal`), and derives `tipo_salida = MENSUALIDAD | ROTACION`
server-side from the `cobrar` flag returned by F1.8 (DEC-SUC-21-NEW,
DEC-MONO-01). The endpoint was zero-validated before F1.7 — `grep "POST.*salidas"
backend/` returned 0 matches confirmed during F1.8 exploration, and the
`resolve_active_subscription_for_exit` helper (T-PR5-016) lifted to
`api/v1/operacion.py:500-562` was never invoked by an HTTP handler.

The change enforces 5 server-side validations plus the KD-FORZADO-01 bypass
contract — `[FORZADO: <motivo ≥10 chars>]` parsed from `observaciones`
(A-04) — as the **only** operational bypass for V2 (subscripción vencida)
and V5 (tarifa no vigente). V1 (ingreso activo exists) and V3 (placa matches
ingreso) are correctness invariants and are NOT bypassable. The bypass
scope is narrower than F1.6 by design (D-HU-F1.7-6): V2/V5 are operational
state that may legitimately change between ingreso and salida; V1/V3 are
data-integrity invariants.

`tipo_salida` (`MENSUALIDAD | ROTACION`) is derived server-side from
`prod.calcular_cotizacion(ingreso).cobrar` (DEC-SUC-21-NEW) — the analogue
of DEC-SUC-21 for ingreso (F1.6) — and is **NEVER** persisted in
`prod.salidas` (the table has no column for it, by 4FN design). The
`cotizacion_snapshot` field of `SalidaReadForzado` is populated only when
`tipo_salida == "ROTACION"`; when `MENSUALIDAD`, it is `None` (KD-S4 —
mensualidad subscribers do not get billed for the exit).

Defense in depth (D-HU-F1.7-7): 5 layers close the validation pipeline —
(a) KD-3 server-side tenant scope chain, (b) KD-FORZADO-01 prefix
contract reused from F1.6, (c) alerta INSERT same-TX as salida INSERT
(R5 mitigation), (d) AST walk `tests/static/test_salida_handler_step_order.py`
locking the literal 12-step order, (e) partial unique index
`one_exit_per_ingreso` (MIGRATION 0026 Op 4) closing the TOCTOU race on
V1 EXISTS subquery (R4 mitigation). No single failure can bypass the
whole.

The migration MIGRATION 0026 (4 operations) is a **precondition runtime**
of F1.7: it inline-seeds `impuestos.IVA` (DEC-IMP-01, KD-IVA blocker
resolution for F1.8), seeds 2 new `alert_types`
(`subscripcion_vencida_forzado`, `tarifa_vigente_forzado`), and creates
the partial unique index `one_exit_per_ingreso`. Without 0026 applied, every
salida returns `500 iva_no_configurado`. The pre-flight `DO $$` (KD-7
pattern from F1.6) aborts with `0026_preflight_abort` if any of the 3
referenced tables is missing.

## ADDED Requirements

### REQ-OPS-042 — POST /operacion/salidas contract: handler `create_salida` with `SalidaCreateForzado` / `SalidaReadForzado`, KD-3 tenant scope, `Cache-Control: no-store`, Idempotency-Key header

**Given** the FastAPI router `api/v1/operacion.py` already hosts
`@router.post("/ingresos", ...)` (F1.6, lines 132-294) and `api/v1/__init__.py`
mounts `r.include_router(operacion.router)` at line 143 (no changes to
`__init__.py`)
**When** the new handler `@router.post("/salidas", response_model=SalidaReadForzado, status_code=201)` is registered on the same custom `APIRouter`
(line 52) with the signature `async def create_salida(response: Response,
payload: SalidaCreateForzado, session: AsyncSession = Depends(get_session),
ctx: TenantContext = Depends(get_tenant_ctx), _claims: None = Depends(_ingreso_issuer_dep)) -> SalidaReadForzado`
**Then** the handler MUST accept a JSON body `SalidaCreateForzado` with
`extra='forbid'` (inherited from `_Base`) carrying the required field
`uuid_ingreso: uuid_lib.UUID` and the optional fields `placa: str | None`,
`observaciones: str | None`, `forzado: bool = False` — rejecting any extra
field (defense-in-depth against `tipo_salida` injection, DEC-SUC-21-NEW)
**And** MUST resolve the target `uuid_sucursal` **server-side** from the
ingreso located in V1 (the client does not send `uuid_sucursal`; this is a
behavioral delta from F1.6 where the client supplied the sucursal in the
payload)
**And** MUST respond `201 Created` with `SalidaReadForzado` carrying the
fields `uuid`, `created_at`, `created_by`, `sync_status`, `sync_timestamp`,
`sync_attempts`, `uuid_sucursal`, `uuid_ingreso`, `fecha_salida`, plus the
NEW F1.7 fields `tipo_salida: Literal["MENSUALIDAD", "ROTACION"]`,
`forzado_en_creacion: bool = False`, `motivo_forzado: str | None = None`,
and `cotizacion_snapshot: CotizarFacturacion | None = None`
**And** MUST set the header `Cache-Control: no-store` on every 2xx, 4xx,
and 5xx response (aligned with F1.3 / F1.5 / F1.6 / F1.8 precedents)
**And** MUST be guarded by `_ingreso_issuer_dep = requires_issuer("operador-",
"admin-")` so only those JWT roles can POST (KD-3 chain reuso)
**And** MUST rely on the PR2 `Idempotency-Key` HTTP header for retry
deduplication (DEC-IDEM-01) — the payload MUST NOT carry a `correlacion_id`
field (rejected by `extra='forbid'`).
**RFC 2119**: MUST (response shape, `extra='forbid'`, `Cache-Control: no-store`,
issuer dep, Idempotency-Key delegation).

#### Scenario: rotación exitosa with full payload returns 201 ROTACION snapshot

**Given** an existing `prod.ingreso` with `uuid_ingreso=:p` and
`uuid_sucursal=:s`, no `prod.salidas` linked to it, and a vigente
`prod.tarifas_sucursal` row for `(s, tipo_vehiculo)` at `datetime.now(UTC)`
**And** an `operador-:s` JWT (or `admin-` with :s in `sucursales_permitidas`)
**And** a vigente `prod.impuestos` row with `codigo='IVA'` and `porcentaje > 0`
(post-MIGRATION 0026 deploy)
**When** the client sends `POST /api/v1/operacion/salidas` with
`{"uuid_ingreso":":p","placa":"ABC123","observaciones":null,"forzado":false}`
and header `Idempotency-Key: <uuid>`
**Then** the server MUST insert one row in `prod.salidas` with
`uuid_ingreso=:p`, `uuid_sucursal=:s`, `fecha_salida=NOW()`,
`fecha_retencion_hasta=fecha_salida + 2 years`
**And** MUST respond `201 Created` with `SalidaReadForzado{tipo_salida:"ROTACION",
forzado_en_creacion:false, motivo_forzado:null, cotizacion_snapshot:{...}}`
**And** MUST set `Cache-Control: no-store` on the response.

#### Scenario: mensualidad exitosa returns 201 MENSUALIDAD with `cotizacion_snapshot: None`

**Given** an existing `prod.ingreso` with `uuid_ingreso=:p` and
`uuid_subscripcion_cliente=:sub` where `:sub` is vigente at `NOW()` (per
`validar_subscripcion_vigente` predicate `vigente_hasta IS NULL AND
estado='activo' AND fecha_vencimiento >= NOW()`)
**When** the client sends `POST /api/v1/operacion/salidas` with
`{"uuid_ingreso":":p"}` (no `placa`, no `forzado`, no `observaciones`)
**Then** the server MUST respond `201 Created` with `SalidaReadForzado{
`tipo_salida:"MENSUALIDAD"`, `forzado_en_creacion:false`,
`motivo_forzado:null`, `cotizacion_snapshot:null}`
**And** MUST set `Cache-Control: no-store` on the response
**And** MUST NOT insert any row in `prod.alerta` (no bypass was used).

### REQ-OPS-043 — V1 ingreso activo exists: `404 ingreso_no_encontrado` unified discriminator

**Given** the request body carries `uuid_ingreso=:p` and the handler has
resolved KD-3 issuer claims via `_ingreso_issuer_dep`
**When** the handler invokes
`repo/salida.py::buscar_ingreso_activo_por_uuid(session,
*, uuid_ingreso=:p)` which executes
`SELECT i.* FROM prod.ingreso i WHERE i.uuid = :p AND i.vigente_hasta IS
NULL AND NOT EXISTS (SELECT 1 FROM prod.salidas s WHERE s.uuid_ingreso = i.uuid
AND NOT EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_salida = s.uuid
AND a.tipo_anulable = 'salida' AND a.estado = 'ejecutada'))`
**Then** the helper MUST return `None` if any of the following hold:
the `uuid_ingreso` does not exist in `prod.ingreso`; the ingreso already
has a non-anulada row in `prod.salidas`; or the ingreso was anulado (DEC-SUC-21,
analogous "no hay nada que cerrar")
**And** if `None`, the handler MUST raise
`HTTPException(status_code=404, detail={"error":
"ingreso_no_encontrado", "uuid_ingreso": str(:p)}, headers={"Cache-Control":
"no-store"})`
**And** MUST NOT honor `forzado=true` for V1 — V1 is a correctness
invariant (D-HU-F1.7-6; without an ingreso, there is nothing to close)
**And** MUST NOT insert any row in `prod.ingreso`, `prod.salidas`, or
`prod.alerta`.
**RFC 2119**: MUST (single 404 discriminator for the three unified cases,
no bypass on `forzado=true`, `Cache-Control: no-store` header).

#### Scenario: uuid_ingreso inexistente returns 404

**Given** no row in `prod.ingreso` with `uuid=:p`
**When** the client sends `POST /operacion/salidas` with `{"uuid_ingreso":":p"}`
**Then** the response MUST be `404 Not Found` with body
`{"error":"ingreso_no_encontrado","uuid_ingreso":":p"}`
**And** the response MUST carry `Cache-Control: no-store`
**And** `prod.salidas` MUST have no new rows.

#### Scenario: ingreso ya con salida no anulada returns 404 (KD-S1 unified)

**Given** `prod.ingreso` with `uuid=:p` exists with `vigente_hasta IS NULL`
**And** `prod.salidas` contains a row with `uuid_ingreso=:p` and no row in
`prod.anulaciones` references that salida with `tipo_anulable='salida' AND
estado='ejecutada'`
**When** the client sends `POST /operacion/salidas` with `{"uuid_ingreso":":p"}`
**Then** the response MUST be `404 Not Found` with body
`{"error":"ingreso_no_encontrado","uuid_ingreso":":p"}` (operationally
equivalent to "no existe" — there is nothing to close).

#### Scenario: ingreso anulado returns 404 (KD-S1 unified)

**Given** `prod.ingreso` with `uuid=:p` was anulado (a row in
`prod.anulaciones` with `tipo_anulable='ingreso' AND estado='ejecutada'`
references `:p`)
**When** the client sends `POST /operacion/salidas` with `{"uuid_ingreso":":p"}`
**Then** the response MUST be `404 Not Found` with body
`{"error":"ingreso_no_encontrado","uuid_ingreso":":p"}` (KD-S1 — same
unified discriminator).

### REQ-OPS-044 — V2 subscripción vigente al momento salida: reuso verbatim F1.6 `validar_subscripcion_vigente`; 422 sin forzado; alerta `subscripcion_vencida_forzado` con forzado

**Given** V1 passed (REQ-OPS-043) and the located `ingreso` has
`uuid_subscripcion_cliente=:sub` (non-None)
**When** the handler invokes
`repo/subscripcion_activa.py::validar_subscripcion_vigente(session, *,
uuid_subscripcion_cliente=:sub, forzado=bool(bypass_reason))` (the F1.6
helper reused verbatim, no modification)
**Then** the helper MUST apply the three-predicate AND:
`vigente_hasta IS NULL AND estado='activo' AND fecha_vencimiento >= NOW()`
against `prod.subscripciones_cliente`
**And** MUST return `vigente=true` only if all three predicates hold;
otherwise `vigente=false`
**And** when `vigente=false AND forzado=false`, the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"subscripcion_inactiva_o_vencida"}, headers={"Cache-Control":"no-store"})`
and MUST NOT insert any row in `prod.salidas` or `prod.alerta`
**And** when `vigente=false AND forzado=true` (a valid KD-FORZADO-01
bypass from V4), the handler MUST accept the request as a "walk-in
auditado" (F1.6 D-HU-F1.6-2) and proceed with `bypass_reason =
"subscripcion_vencida"` so the Step 9 alerta (REQ-OPS-050) inserts
`subscripcion_vencida_forzado` same-TX as the salida INSERT
**And** MUST re-validate at the moment of salida (not trust the snapshot
of the ingreso) — the subscripción may have expired since ingreso
(estacionamiento prolongado, monthly subscription that expired during
the stay).
**RFC 2119**: MUST (three-predicate AND, verbatim F1.6 reuse, 422 shape,
no bypass on `forzado=false`, alerta path on `forzado=true`, re-validate
at `NOW()`).

#### Scenario: subscripcion vigente al momento salida proceeds without forzado

**Given** `prod.subscripciones_cliente(:sub)` has `vigente_hasta IS NULL`,
`estado='activo'`, `fecha_vencimiento = '2026-12-31'` (future)
**And** V1 passed with `ingreso.uuid_subscripcion_cliente = :sub`
**When** the operator POSTs `{"uuid_ingreso":":p"}` (no `forzado`,
no `observaciones`)
**Then** the handler MUST pass V2 with `vigente=true` and proceed to V3,
V4, V5, INSERT (REQ-OPS-048), and 201 response
**And** MUST NOT insert any row in `prod.alerta` (no bypass was used).

#### Scenario: subscripcion vencida al momento salida sin forzado returns 422

**Given** `prod.subscripciones_cliente(:sub)` has `fecha_vencimiento =
'2026-01-01'` (past)
**And** V1 passed with `ingreso.uuid_subscripcion_cliente = :sub`
**When** the operator POSTs `{"uuid_ingreso":":p"}` (no `forzado`)
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error":"subscripcion_inactiva_o_vencida"}`
**And** MUST carry `Cache-Control: no-store`
**And** `prod.salidas` MUST have no new rows
**And** `prod.alerta` MUST have no new rows.

#### Scenario: subscripcion vencida al momento salida con forzado válido proceeds + alerta `subscripcion_vencida_forzado`

**Given** the past-`fecha_vencimiento` state above
**And** V1 passed
**When** the operator POSTs `{"uuid_ingreso":":p","forzado":true,
"observaciones":"[FORZADO: cliente pago en efectivo tras vencer 2026-01-15]"}`
**Then** V4 (REQ-OPS-046) MUST return the stripped motivo and set
`bypass_reason="forzado"`
**And** V2 MUST mark `bypass_reason="subscripcion_vencida"` for the alerta
discriminator
**And** V3 (if `placa` provided) MUST pass, V5 MUST compute
`cobrar=true` from `prod.calcular_cotizacion(:p)` (F1.8 PL/pgSQL returns
`cobrar:true` when no active subscription is found at the branch — the
subscription expired, so it falls through to rotación pricing)
**And** the INSERT in REQ-OPS-048 MUST commit with
`tipo_salida="ROTACION"`
**And** the alerta (REQ-OPS-050) MUST commit same-TX with
`tipo_alerta='subscripcion_vencida_forzado'`, `estado='abierta'`,
`datos_nuevos={motivo: "cliente pago en efectivo tras vencer 2026-01-15",
uuid_salida: <new>}`
**And** the response MUST be `201 Created` with `SalidaReadForzado{
tipo_salida:"ROTACION", forzado_en_creacion:true, motivo_forzado:"cliente
pago en efectivo tras vencer 2026-01-15", cotizacion_snapshot:{...}}`.

### REQ-OPS-045 — V3 placa matches ingreso: reuso verbatim F1.6 `detectar_tipo_vehiculo`; 422 sin bypass; placa opcional

**Given** V1 (REQ-OPS-043) and V2 (REQ-OPS-044, if applicable) passed,
and `payload.placa` is non-None (the placa field is optional per KD-S3 —
client may know `uuid_ingreso` from a QR scan but not remember the placa)
**When** the handler invokes
`repo/placa.py::detectar_tipo_vehiculo(payload.placa)` (F1.6 helper
reused verbatim) to derive the regex-based tipo `T_req`, and
`repo/placa.py::detectar_tipo_vehiculo(ingreso.placa)` to derive `T_ing`
**Then** if `T_req != T_ing` (mismatch in regex-derived vehicle type —
Auto vs Moto, or None vs tipo), the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"placa_no_coincide_con_ingreso", "placa_request": payload.placa,
"placa_ingreso": ingreso.placa}, headers={"Cache-Control":"no-store"})`
**And** if `payload.placa is None`, the server MUST skip V3 entirely
(trust the `uuid_ingreso` mapping)
**And** MUST NOT honor `forzado=true` for V3 — placa mismatch is a
correctness invariant (D-HU-F1.7-6: bug del operador or fraud attempt,
not operational state)
**And** MUST NOT insert any row in `prod.salidas` or `prod.alerta`.
**RFC 2119**: MUST (regex reuse verbatim F1.6, optional placa, 422 shape
with both placa values, no bypass on `forzado=true`).

#### Scenario: placa Auto matches ingreso Auto proceeds

**Given** V1 and V2 passed, `ingreso.placa = "ABC123"` (matches `FORMATO_AUTO`)
**When** the operator POSTs `{"uuid_ingreso":":p","placa":"ABC123"}`
**Then** V3 MUST pass (`T_req = T_ing = uuid_tipo_vehiculo(Auto)`)
**And** the handler MUST proceed to V4, V5, INSERT, and 201 response.

#### Scenario: placa Moto mismatches ingreso Auto returns 422

**Given** `ingreso.placa = "ABC123"` (Auto) and the request carries
`placa = "ABC12D"` (Moto)
**When** the operator POSTs `{"uuid_ingreso":":p","placa":"ABC12D"}`
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error":"placa_no_coincide_con_ingreso","placa_request":"ABC12D",
"placa_ingreso":"ABC123"}`
**And** MUST carry `Cache-Control: no-store`
**And** `prod.salidas` MUST have no new rows.

#### Scenario: placa omitida proceeds (KD-S3 trust uuid_ingreso)

**Given** V1 and V2 passed, `ingreso.placa = "ABC123"`
**When** the operator POSTs `{"uuid_ingreso":":p"}` (no `placa` field)
**Then** the handler MUST skip V3 and proceed to V4, V5, INSERT, and 201
response (the server trusts the uuid→placa mapping).

### REQ-OPS-046 — V4 KD-FORZADO-01 prefix contract: reusado verbatim de F1.6 (`repo/ingreso.py::validar_kd_forzado`); mismo set 422

**Given** the request body carries `observaciones` (possibly `None`) and
`forzado: bool` (default `False`), and V1, V2 (if applicable), V3 (if
applicable) passed
**When** the handler invokes
`repo/ingreso.py::validar_kd_forzado(payload.observaciones, payload.forzado)`
(F1.6 helper reused verbatim — single implementation, single test suite,
single audit; no modification)
**Then** the helper MUST enforce exactly three discriminators using the
module-level constants `FORZADO_PREFIX = "[FORZADO: "` and
`FORZADO_MIN_MOTIVO_CHARS = 10`:

1. If `forzado=false` AND `observaciones` starts with `FORZADO_PREFIX`,
   the helper MUST raise
   `HTTPException(status_code=422, detail={"error":"forzado_contradiccion"},
   headers={"Cache-Control":"no-store"})` — D-HU-F1.6-5 defense in
   depth (the prefix is the source of truth, not the bool flag).
2. If `forzado=true` AND (`observaciones is None` OR does not start with
   `FORZADO_PREFIX`), the helper MUST raise
   `HTTPException(status_code=422, detail={"error":
   "motivo_forzado_requerido"}, headers={"Cache-Control":"no-store"})`.
3. If `forzado=true` AND `observaciones` starts with `FORZADO_PREFIX` AND
   the motivo (substring after `FORZADO_PREFIX`, `rstrip("]")`) has
   `len(motivo.strip()) < FORZADO_MIN_MOTIVO_CHARS = 10`, the helper MUST
   raise `HTTPException(status_code=422, detail={"error":
   "motivo_forzado_insuficiente", "min_chars": 10}, headers={"Cache-Control":
   "no-store"})`.

**And** on a valid `forzado=true` + valid prefix + motivo ≥10 chars, the
helper MUST return the stripped motivo string (the handler records
`forzado_en_creacion=true` and `motivo_forzado=<motivo>` in the response)
**And** MUST set `bypass_reason = "forzado"` only after the helper returns
a valid stripped motivo (not on the bool flag alone — defense in depth).
**RFC 2119**: MUST (prefix constants verbatim F1.6, three discriminators
with literal key names, helper reused verbatim, `bypass_reason` set on
returned motivo only).

#### Scenario: KD-FORZADO-01 valid prefix + motivo ≥10 chars bypasses V2/V5

**Given** V1 passed and `ingreso.uuid_subscripcion_cliente = :sub` is
expired, and `prod.tarifas_sucursal` has no vigente row at `NOW()` for
the `(uuid_sucursal, uuid_tipo_vehiculo)` combination
**When** the operator POSTs `{"uuid_ingreso":":p","forzado":true,
"observaciones":"[FORZADO: cliente pago en efectivo tras vencer 2026-01-15]"}`
**Then** `validar_kd_forzado` MUST return the stripped motivo
`"cliente pago en efectivo tras vencer 2026-01-15"` (len ≥ 10)
**And** the handler MUST set `bypass_reason = "forzado"` initially
**And** the response MUST carry `forzado_en_creacion:true` and
`motivo_forzado:"cliente pago en efectivo tras vencer 2026-01-15"`.

#### Scenario: KD-FORZADO-01 `forzado_contradiccion` when `forzado=false` with prefix

**Given** the request carries `{"uuid_ingreso":":p","forzado":false,
"observaciones":"[FORZADO: prueba cliente]"}`
**When** the handler invokes `validar_kd_forzado(observaciones, forzado)`
**Then** the helper MUST raise `HTTPException(422, {"error":
"forzado_contradiccion"})` (the bool flag contradicts the prefix — the
prefix is the source of truth per D-HU-F1.6-5)
**And** MUST NOT insert any row in `prod.salidas` or `prod.alerta`.

#### Scenario: KD-FORZADO-01 `motivo_forzado_requerido` when `forzado=true` without prefix

**Given** the request carries `{"uuid_ingreso":":p","forzado":true,
"observaciones":"cliente sin placa"}` (no `[FORZADO: ` prefix)
**When** the handler invokes `validar_kd_forzado(observaciones, forzado)`
**Then** the helper MUST raise `HTTPException(422, {"error":
"motivo_forzado_requerido"})`.

#### Scenario: KD-FORZADO-01 `motivo_forzado_insuficiente` when motivo <10 chars

**Given** the request carries `{"uuid_ingreso":":p","forzado":true,
"observaciones":"[FORZADO: a b]"}` (motivo `"a b"` = 3 chars after prefix
+ `rstrip("]")`)
**When** the handler invokes `validar_kd_forzado(observaciones, forzado)`
**Then** the helper MUST raise `HTTPException(422, {"error":
"motivo_forzado_insuficiente", "min_chars": 10})`.

### REQ-OPS-047 — V5 tarifa vigente via `prod.calcular_cotizacion(:uuid_ingreso)` (F1.8 PL/pgSQL VOLATILE, KD-S7 lock continuity); 422 sin forzado; alerta `tarifa_vigente_forzado` con forzado; 500 post-0026: never

**Given** V1, V2 (if applicable), V3 (if applicable), V4 passed, and the
`bypass_reason` is determined
**When** the handler invokes
`repo/salida.py::cotizar_para_salida(session, *, uuid_ingreso=:p)` which
delegates to `repo/cotizacion.py::cotizar_ingreso(session, uuid_ingreso=:p)`
(F1.8 thin wrapper) and that wrapper executes
`SELECT prod.calcular_cotizacion(:p)` — the F1.8 PL/pgSQL function with
`LANGUAGE plpgsql VOLATILE` (REQ-OPS-025 deviation letter, user approved
2026-09-14) which acquires `SELECT … FOR SHARE` on the matching
`prod.tarifas_sucursal` row at the bi-temporal predicate
`vigente_desde <= NOW() AND (vigente_hasta IS NULL OR vigente_hasta > NOW())
AND estado='activo'` (F1.4 `bitemporal_vigente_predicate` reused verbatim)
**Then** the F1.8 function MUST return one of these JSONB payloads, in
strict precedence order:

- `{"cobrar": true, subtotal, iva, total, tiempo_minutos, tarifa_uuid,
  vigente_hasta}` → the handler MUST derive `tipo_salida = "ROTACION"` (per
  REQ-OPS-049) and `cotizacion_snapshot` MUST be populated in the response.
- `{"cobrar": false, motivo: "mensualidad_vigente"}` → the handler MUST
  derive `tipo_salida = "MENSUALIDAD"` (per REQ-OPS-049) and
  `cotizacion_snapshot` MUST be `None` (KD-S4).
- `{"error": "ingreso_no_encontrado"}` → covered by V1 (REQ-OPS-043).
- `{"error": "tarifa_no_vigente"}` → if `bypass_reason` is None, the
  handler MUST raise `HTTPException(status_code=422, detail={"error":
  "tarifa_vigente_no_encontrada"}, headers={"Cache-Control":"no-store"})`
  and MUST NOT insert any row in `prod.salidas` or `prod.alerta`; if
  `bypass_reason` is set, the handler MUST set
  `bypass_reason = "tarifa_no_vigente"` for the alerta discriminator in
  REQ-OPS-050 and proceed with INSERT.
- `{"error": "iva_no_configurado"}` → the handler MUST raise
  `HTTPException(status_code=500, detail={"error":"iva_no_configurado"},
  headers={"Cache-Control":"no-store"})`. Post-MIGRATION 0026 deploy
  (REQ-OPS-052), this MUST never occur because the IVA row is seeded.

**And** the `prod.calcular_cotizacion` invoke MUST execute **inside the
same transaction** as the INSERT into `prod.salidas` (Step 8, REQ-OPS-048)
and the alerta INSERT (Step 9, REQ-OPS-050) — the `FOR SHARE` lock
acquired on `prod.tarifas_sucursal` is held through `session.commit()`
(KD-S7 lock continuity invariant). The handler MUST NOT use
sub-transactions, `SAVEPOINT`, or multiple `session.commit()` calls
**And** the precedence MUST be strictly
`ingreso_no_encontrado > tarifa_no_vigente > iva_no_configurado`; a
single response MUST never combine two error codes.
**RFC 2119**: MUST (F1.8 verbatim reuse, FOR SHARE continuity in same TX,
422 shape for `tarifa_no_vigente`, 500 shape for `iva_no_configurado`,
precedence, single commit).

#### Scenario: tarifa vigente returns 201 ROTACION with full fiscal breakdown

**Given** V1, V2, V3, V4 passed (no `forzado`)
**And** `prod.tarifas_sucursal(s, tipo_vehiculo)` has a vigente row at
`datetime.now(UTC)`
**When** the handler invokes `cotizar_para_salida(session, uuid_ingreso=:p)`
**Then** `prod.calcular_cotizacion(:p)` MUST return
`{"cobrar":true,"subtotal":X,"iva":Y,"total":Z,"tiempo_minutos":N,"tarifa_uuid":...,
"vigente_hasta":"..."}`
**And** the handler MUST derive `tipo_salida="ROTACION"` and the INSERT in
REQ-OPS-048 MUST commit
**And** the response MUST be `201 Created` with `SalidaReadForzado{
tipo_salida:"ROTACION", forzado_en_creacion:false, motivo_forzado:null,
cotizacion_snapshot:{...}}` (KD-S4 snapshot populated for ROTACION).

#### Scenario: tarifa no vigente sin forzado returns 422

**Given** V1, V2, V3, V4 passed (no `forzado`)
**And** `prod.tarifas_sucursal(s, tipo_vehiculo)` has NO row satisfying the
bi-temporal predicate at `NOW()`
**When** the handler invokes `cotizar_para_salida(session, uuid_ingreso=:p)`
**Then** `prod.calcular_cotizacion(:p)` MUST return `{"error":
"tarifa_no_vigente"}`
**And** the handler MUST raise `HTTPException(422, {"error":
"tarifa_vigente_no_encontrada"})`
**And** MUST carry `Cache-Control: no-store`
**And** `prod.salidas` MUST have no new rows
**And** `prod.alerta` MUST have no new rows.

#### Scenario: tarifa no vigente con forzado válido proceeds + alerta `tarifa_vigente_forzado`

**Given** the same expired-tarifa state and a valid KD-FORZADO-01 bypass
from V4 with motivo ≥10 chars
**When** the handler invokes `cotizar_para_salida(session, uuid_ingreso=:p)`
**Then** `prod.calcular_cotizacion(:p)` MUST return `{"error":
"tarifa_no_vigente"}`
**And** the handler MUST set `bypass_reason = "tarifa_no_vigente"`
**And** the INSERT in REQ-OPS-048 MUST commit with `tipo_salida="ROTACION"`
**And** the alerta (REQ-OPS-050) MUST commit same-TX with
`tipo_alerta='tarifa_vigente_forzado'`, `estado='abierta'`,
`datos_nuevos={motivo: <stripped motivo>, uuid_salida: <new>}`
**And** the response MUST be `201 Created` with `SalidaReadForzado{
tipo_salida:"ROTACION", forzado_en_creacion:true, motivo_forzado:<motivo>,
cotizacion_snapshot:{...}}`.

#### Scenario: iva_no_configurado (KD-IVA pre-0026) returns 500

**Given** MIGRATION 0026 has NOT been applied (pre-deploy state, or
post-deploy with the IVA row deleted for testing)
**And** V1, V2, V3, V4 passed
**And** `prod.tarifas_sucursal` has a vigente row
**When** the handler invokes `cotizar_para_salida(session, uuid_ingreso=:p)`
**Then** `prod.calcular_cotizacion(:p)` MUST return `{"error":
"iva_no_configurado"}`
**And** the handler MUST raise `HTTPException(500, {"error":
"iva_no_configurado"})` (this error MUST never occur post-MIGRATION 0026
deploy per REQ-OPS-052).

### REQ-OPS-048 — INSERT `prod.salidas` `[A]` append-only via `repo/salida.py::crear_salida_evento`; defense in depth (REVOKE + trigger + partial unique index); NUNCA UPDATE (DEC-SAL-01)

**Given** V1, V2 (if applicable), V3 (if applicable), V4, V5 passed (all
prior validations passed; either `bypass_reason` is set or no bypass was
needed)
**When** the handler invokes
`repo/salida.py::crear_salida_evento(session, *, actor_uuid=ctx.actor_uuid,
new_attrs={"uuid_sucursal": target_sucursal, "uuid_ingreso": payload.uuid_ingreso,
"fecha_salida": datetime.now(UTC).replace(tzinfo=None),
"fecha_retencion_hasta": date.today() + relativedelta(years=2)})` (KD-S6
retention 2 years from `fecha_salida`)
**Then** the helper MUST INSERT one row in `prod.salidas` via the
`models/L_S/salida.py::Salida(LifecycleEventBase)` ORM model with the
audit + sync mixins inherited from the base class
**And** MUST NOT acquire a `FOR UPDATE` or `FOR SHARE` lock on `prod.ingreso`
(KD-V4: read-mostly; the partial unique index `one_exit_per_ingreso` from
REQ-OPS-051 closes the TOCTOU race)
**And** MUST map any `IntegrityError` whose `err.orig` (psycopg2/asyncpg)
contains the string `"one_exit_per_ingreso"` to the typed exception
`SalidaDuplicada`, which the handler MUST translate to
`HTTPException(status_code=409, detail={"error":"salida_duplicada",
"uuid_ingreso": str(payload.uuid_ingreso)}, headers={"Cache-Control":
"no-store"})`
**And** MUST NOT persist any of the following in `prod.salidas` columns
(DEC-SUC-21-NEW + DEC-SUC-23): `tipo_salida`, `valor`, `subtotal`, `iva`,
`total`, `cobrar`, `forzado`, `motivo_forzado` — these belong in the
response (`SalidaReadForzado`) and/or in `prod.alerta.datos_nuevos` (when
bypassed), never in the `[A]` event row
**And** MUST respect the defense-in-depth at DB layer:
- `REVOKE UPDATE, DELETE ON prod.salidas FROM parkos_app` (migration 0001
  línea 2923) — already applied
- `CREATE TRIGGER fn_salidas_inmutable BEFORE UPDATE OR DELETE ON
  prod.salidas` (migration 0001 líneas 1990-2003) — already applied
- `CREATE UNIQUE INDEX one_exit_per_ingreso ON prod.salidas (uuid_ingreso)
  WHERE NOT EXISTS (anulaciones ejecutadas)` (MIGRATION 0026 Op 4, REQ-OPS-051)
  — applied in F1.7 apply phase
**And** the INSERT MUST commit in the SAME `await session.commit()` call as
the alerta INSERT in REQ-OPS-050 (R5 mitigation — no orphan alerts, no
orphan salidas without alerts when bypassed).
**RFC 2119**: MUST (single INSERT via `Salida` ORM, `IntegrityError` →
`SalidaDuplicada` → 409, no monto/tipo in columns, REVOKE + trigger +
index all respected, same TX as alerta).

#### Scenario: INSERT exitosa sin bypass commits in same TX

**Given** V1, V2, V3, V4, V5 passed, no `forzado` flag, no bypass used
**When** the handler invokes `crear_salida_evento(session, ...)`
**Then** one row MUST be INSERTed in `prod.salidas` with the computed
`uuid_sucursal`, `uuid_ingreso`, `fecha_salida`, `fecha_retencion_hasta`
**And** the response MUST be `201 Created` with `SalidaReadForzado{...}`
carrying `forzado_en_creacion:false` and `motivo_forzado:null`
**And** NO row in `prod.alerta` MUST be inserted (no bypass).

#### Scenario: INSERT conflictiva por partial unique index returns 409 `salida_duplicada`

**Given** V1 passed and `prod.salidas` already has a row with
`uuid_ingreso=:p` (no anulación ejecutada referencing that salida's UUID)
**When** the handler invokes `crear_salida_evento(session, ...)`
**Then** Postgres MUST raise `UniqueViolationError` (sqlstate `23505`)
violating the `one_exit_per_ingreso` index
**And** `crear_salida_evento` MUST catch the `IntegrityError` and raise
`SalidaDuplicada`
**And** the handler MUST translate to
`HTTPException(409, {"error":"salida_duplicada","uuid_ingreso":":p"})`
**And** MUST carry `Cache-Control: no-store`.

#### Scenario: type_salida NO persisted in prod.salidas (DEC-SUC-21-NEW AST guard)

**Given** the INSERT committed
**When** a direct query `SELECT tipo_salida FROM prod.salidas WHERE
uuid=<new>` is executed against the DB
**Then** the query MUST error with `column "tipo_salida" does not exist`
(DEC-SUC-21-NEW — `prod.salidas` has no `tipo_salida` column by 4FN
design, and the AST walk `tests/static/test_no_write_after_salida_insert.py`
verifies that `repo/salida.py::crear_salida_evento` does not introduce
one in the future).

### REQ-OPS-049 — `tipo_salida = MENSUALIDAD | ROTACION` derivado server-side (DEC-SUC-21-NEW, DEC-FORZADO-01 irrelevante); retornado en `SalidaReadForzado`; NUNCA persistido

**Given** V5 (REQ-OPS-047) returned `cotizacion` from
`prod.calcular_cotizacion(:p)`, and the INSERT in REQ-OPS-048 committed
(or is about to commit in the same TX)
**When** the handler derives `tipo_salida` from `cotizacion`
**Then** the handler MUST set `tipo_salida = "MENSUALIDAD"` if and only
if `cotizacion.get("cobrar") is False` (the F1.8 PL/pgSQL short-circuit on
`resolve_active_subscription_for_exit` returned `cobrar:false,
motivo:"mensualidad_vigente"` because the plate has an active subscription
vigente at `NOW()` at this branch)
**And** MUST set `tipo_salida = "ROTACION"` otherwise (any of: `cobrar:true`
with a vigente tarifa, OR `error:tarifa_no_vigente` bypassed with
`forzado=true`)
**And** MUST include `tipo_salida` in the `SalidaReadForzado` response body
**And** MUST NOT persist `tipo_salida` in any column of `prod.salidas`
(DEC-SUC-21-NEW — derived value, not a column, by 4FN design); the
analogous `tipo_entrada` for ingreso (F1.6 DEC-SUC-21) shares the same
invariant
**And** MUST derive `tipo_salida` keyed on the `cobrar` flag, NOT on
`forzado` (D-HU-F1.7-11: KD-FORZADO-01 is irrelevant to the derivation —
a monthly subscriber who is forced to walk-in because their subscription
expired during the stay still gets `tipo_salida="ROTACION"` because F1.8
returns `cobrar:true` for "no subscription at branch" — see REQ-OPS-044
Scenario "subscripcion vencida con forzado válido").
**RFC 2119**: MUST (literal `cobrar` flag rule, NEVER persisted, returned
in response, keyed on F1.8 output).

#### Scenario: mensualidad derivation returns 201 MENSUALIDAD

**Given** V1, V2, V3, V4, V5 passed
**And** `prod.calcular_cotizacion(:p)` returned
`{"cobrar":false,"motivo":"mensualidad_vigente"}` (F1.8 short-circuit per
REQ-OPS-023)
**When** the handler derives `tipo_salida` and builds the response
**Then** `tipo_salida` MUST be `"MENSUALIDAD"`
**And** `cotizacion_snapshot` MUST be `None` (KD-S4 — mensualidad
subscribers do not get billed for the exit; no fiscal breakdown)
**And** the response MUST be `201 Created` with `SalidaReadForzado{
tipo_salida:"MENSUALIDAD", forzado_en_creacion:false, motivo_forzado:null,
cotizacion_snapshot:null}`
**And** a direct query `SELECT tipo_salida FROM prod.salidas WHERE
uuid=<new>` MUST error with "column does not exist" (DEC-SUC-21-NEW).

#### Scenario: rotación derivation returns 201 ROTACION

**Given** V1, V2, V3, V4, V5 passed
**And** `prod.calcular_cotizacion(:p)` returned
`{"cobrar":true,"subtotal":X,"iva":Y,"total":Z,"tiempo_minutos":N,
"tarifa_uuid":...,"vigente_hasta":"..."}` (REQ-OPS-047)
**When** the handler derives `tipo_salida` and builds the response
**Then** `tipo_salida` MUST be `"ROTACION"`
**And** `cotizacion_snapshot` MUST be populated with the full fiscal
breakdown (KD-S4 — snapshot populated for ROTACION)
**And** the response MUST be `201 Created` with `SalidaReadForzado{
tipo_salida:"ROTACION", ..., cotizacion_snapshot:{...}}`.

#### Scenario: walk-in mensualidad (sub vencida + forzado) sigue siendo ROTACION

**Given** `ingreso.uuid_subscripcion_cliente = :sub` is expired at salida
time, and `forzado=true` with motivo ≥10 chars
**When** the handler runs V2 (sets `bypass_reason="subscripcion_vencida"`),
V5 (F1.8 finds no active subscription at branch → `cobrar:true`)
**Then** `tipo_salida` MUST be `"ROTACION"` (keyed on `cobrar=true`, NOT
on the original `uuid_subscripcion_cliente`)
**And** the response MUST carry `forzado_en_creacion:true` and
`motivo_forzado:<motivo>` (KD-FORZADO-01 marker preserved independently).

### REQ-OPS-050 — alerta same-TX for V2/V5 bypass (`subscripcion_vencida_forzado` or `tarifa_vigente_forzado`); one alerta per bypassed validation; DEF-INDEX no orphan alerts (R5)

**Given** the INSERT in REQ-OPS-048 reached Step 9 (alertas), and
`bypass_reason` is one of `"subscripcion_vencida"`, `"tarifa_no_vigente"`,
or unset/no bypass
**When** the handler invokes the alerta path
**Then** if `bypass_reason is None` (no bypass), the handler MUST NOT
insert any row in `prod.alerta` (R2 mitigation — alerta only on V2/V5
bypass, not other bypasses)
**And** if `bypass_reason == "subscripcion_vencida"`, the handler MUST
invoke `repo/salida.py::insertar_alerta_salida_forzado(session, *,
uuid_sucursal=target_sucursal, uuid_salida=new_row.uuid,
actor_uuid=ctx.actor_uuid, motivo=<stripped motivo>,
tipo_alerta="subscripcion_vencida_forzado")`
**And** if `bypass_reason == "tarifa_no_vigente"`, the handler MUST
invoke `repo/salida.py::insertar_alerta_salida_forzado(session, *,
uuid_sucursal=target_sucursal, uuid_salida=new_row.uuid,
actor_uuid=ctx.actor_uuid, motivo=<stripped motivo>,
tipo_alerta="tarifa_vigente_forzado")`
**And** each invocation MUST INSERT one row in `prod.alerta` with
`tipo_alerta=<above>`, `estado='abierta'`, `timestamp_evento=NOW()`,
`datos_nuevos={"motivo": <motivo>, "uuid_salida": <new_row.uuid>}`
(jsonb, F1.6 R-A2 audit), `uuid_sucursal=<target>`,
`uuid_usuario=<actor_uuid>`
**And** the alerta INSERT MUST commit in the SAME
`await session.commit()` call as the salida INSERT (REQ-OPS-048) — no
`session.commit()` between the two INSERTs (R5 mitigation against orphan
alerts)
**And** if the alerta INSERT fails (FK violation, etc.), the salida INSERT
MUST rollback atomically — no huérfanas (R5 verification via
integration test `test_insert_salida_con_alerta_forzado_atomico`)
**And** the `alert_types_inmutable` trigger (migration 0013) MUST be
respected — the handler MUST NOT attempt UPDATE/DELETE on
`prod.alert_types` (the alert_type rows are inserted by MIGRATION 0026
Op 3 with INSERT-only privileges for `rol_app`).
**RFC 2119**: MUST (one alerta per bypassed validation, `datos_nuevos`
jsonb shape, same TX as salida INSERT, atomic rollback, alert_type trigger
respected).

#### Scenario: V2 bypass (sub vencida) emits `subscripcion_vencida_forzado` same TX

**Given** V2 was bypassed (`bypass_reason="subscripcion_vencida"`) and
Step 8 INSERT in REQ-OPS-048 reached Step 9
**When** the handler invokes `insertar_alerta_salida_forzado(session, ...,
tipo_alerta="subscripcion_vencida_forzado")`
**Then** `prod.alerta` MUST receive one new row with
`tipo_alerta='subscripcion_vencida_forzado'`, `estado='abierta'`,
`datos_nuevos={"motivo":<motivo>,"uuid_salida":<new>}`,
`uuid_sucursal=<target>`, `uuid_usuario=<actor>`
**And** both the salida INSERT and the alerta INSERT MUST commit in ONE
`await session.commit()` call.

#### Scenario: V5 bypass (tarifa no vigente) emits `tarifa_vigente_forzado` same TX

**Given** V5 was bypassed (`bypass_reason="tarifa_no_vigente"`) and
Step 8 INSERT in REQ-OPS-048 reached Step 9
**When** the handler invokes `insertar_alerta_salida_forzado(session, ...,
tipo_alerta="tarifa_vigente_forzado")`
**Then** `prod.alerta` MUST receive one new row with
`tipo_alerta='tarifa_vigente_forzado'`, `estado='abierta'`,
`datos_nuevos={"motivo":<motivo>,"uuid_salida":<new>}`,
`uuid_sucursal=<target>`, `uuid_usuario=<actor>`
**And** both the salida INSERT and the alerta INSERT MUST commit in ONE
`await session.commit()` call.

#### Scenario: no bypass used — no alerta emitted (R2)

**Given** V1, V2, V3, V4, V5 all passed without `forzado=true`
(`bypass_reason is None`)
**When** Step 9 executes
**Then** the handler MUST NOT insert any row in `prod.alerta` (R2
mitigation — alerta only on V2/V5 bypass)
**And** only the salida INSERT commits.

#### Scenario: alerta INSERT falla — salida INSERT rollback (R5 atomic)

**Given** the alerta INSERT in Step 9 fails (FK violation simulated in
integration test, e.g. `uuid_usuario` references a non-existent user)
**When** the single `await session.commit()` call is reached
**Then** both the salida INSERT and the alerta INSERT MUST rollback
together — `prod.salidas` MUST have no new rows for this attempt, and
`prod.alerta` MUST have no new rows (verified by
`test_insert_salida_con_alerta_forzado_atomico` in
`tests/integration/test_salida_create_db.py`).

### REQ-OPS-051 — partial unique index `one_exit_per_ingreso` on `prod.salidas` (MIGRATION 0026 Op 4); `UniqueViolationError` → 409 `salida_duplicada`; cierra TOCTOU race en V1 EXISTS subquery (R4)

**Given** MIGRATION 0026 Op 4 has been applied:
`CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_exit_per_ingreso
ON prod.salidas (uuid_ingreso)
WHERE NOT EXISTS (
    SELECT 1 FROM prod.anulaciones a
    WHERE a.uuid_salida = prod.salidas.uuid
      AND a.tipo_anulable = 'salida'
      AND a.estado = 'ejecutada'
);`
**When** the handler in Step 8 (REQ-OPS-048) calls
`repo/salida.py::crear_salida_evento(session, ...)` and Postgres raises
`UniqueViolationError` (sqlstate `23505`) because a non-anulada row in
`prod.salidas` already has the same `uuid_ingreso=:p`
**Then** `crear_salida_evento` MUST catch the `IntegrityError` whose
`err.orig` (psycopg2/asyncpg) contains the substring `"one_exit_per_ingreso"`,
and MUST re-raise as the typed exception `SalidaDuplicada`
**And** the handler MUST translate `SalidaDuplicada` to
`HTTPException(status_code=409, detail={"error":"salida_duplicada",
"uuid_ingreso": str(payload.uuid_ingreso)}, headers={"Cache-Control":
"no-store"})`
**And** MUST NOT retry the INSERT (defense in depth — the partial unique
index is the authoritative closure of the TOCTOU race in V1 EXISTS
subquery per R4; retries would mask concurrent requests)
**And** the partial predicate MUST allow a new `prod.salidas` row for the
same `uuid_ingreso` if the previous one was anulada — the `NOT EXISTS`
subquery on `prod.anulaciones WHERE tipo_anulable='salida' AND
estado='ejecutada'` excludes the anulada case, so a new INSERT succeeds
after anulación ejecutada (DEC-SAL-01 + R4 mitigation — defense in depth
without violating the original append-only semantics for non-anuladas).
**RFC 2119**: MUST (substring detection on `err.orig`, 409 shape with
literal `uuid_ingreso`, no retry, `NOT EXISTS` partial predicate
respecting anulación ejecutada).

#### Scenario: second POST same uuid_ingreso returns 409

**Given** `prod.salidas` already has a row with `uuid_ingreso=:p` and no
anulación ejecutada references that salida's UUID
**When** the client sends a second `POST /operacion/salidas` with
`{"uuid_ingreso":":p"}`
**Then** the response MUST be `409 Conflict` with body
`{"error":"salida_duplicada","uuid_ingreso":":p"}`
**And** MUST carry `Cache-Control: no-store`
**And** `prod.salidas` MUST have no new rows for this second request.

#### Scenario: salida anulada allows a new salida for same uuid_ingreso

**Given** `prod.salidas` has a row with `uuid_ingreso=:p` and
`uuid=<old_salida>`
**And** `prod.anulaciones` has a row with `uuid_salida=<old_salida>`,
`tipo_anulable='salida'`, `estado='ejecutada'`
**When** the client sends `POST /operacion/salidas` with `{"uuid_ingreso":":p"}`
**Then** the partial unique index predicate MUST evaluate `NOT EXISTS` as
`true` (the anulación ejecutada excludes the old salida)
**And** the INSERT MUST succeed, committing a new `prod.salidas` row with
a new `uuid=<new_salida>`
**And** the response MUST be `201 Created` with `SalidaReadForzado{...}`.

### REQ-OPS-052 — inline-seed `impuestos.IVA` en MIGRATION 0026 Op 2 (`codigo='IVA'`, `porcentaje=0.19`); KD-IVA blocker de F1.8 resuelto; pre-flight abort si `prod.impuestos` no existe

**Given** MIGRATION 0026 Op 1 (pre-flight `DO $$` block) has verified that
`prod.impuestos`, `prod.salidas`, and `prod.alert_types` tables exist in
the DB schema (KD-7 pattern from F1.6 migration 0024):
- If `_n_impuestos IS NULL OR _n_impuestos = 0` → RAISE EXCEPTION
  `'0026_preflight_abort: tabla prod.impuestos no existe. Aplique
  migrations 0001-0025 antes.'`
- If `_n_salidas IS NULL OR _n_salidas = 0` → RAISE EXCEPTION
  `'0026_preflight_abort: tabla prod.salidas no existe.'`
- If `_n_alert_types IS NULL OR _n_alert_types = 0` → RAISE EXCEPTION
  `'0026_preflight_abort: tabla prod.alert_types no existe.'`

**Then** MIGRATION 0026 Op 2 MUST execute the following inline-seed:
```sql
INSERT INTO prod.impuestos (
    uuid, codigo, nombre, porcentaje,
    valid_desde, vigente_hasta, estado, created_at
) VALUES (
    gen_random_uuid(), 'IVA', 'IVA', 0.19,
    NOW() AT TIME ZONE 'UTC', NULL, 'activo', NOW()
)
ON CONFLICT (codigo, vigente_desde) DO NOTHING;
```

**And** `porcentaje=0.19` MUST be the regulatory constant for IVA Colombia
2026 (locked in F1.8 design.md §4 KD-IVA; F1.7 respects the same value)
**And** the UK constraint `(codigo, vigente_desde)` MUST be the
idempotency key — running MIGRATION 0026 a second time MUST be a no-op
(verified by `tests/integration/test_migration_0026_idempotent.py`)
**And** after MIGRATION 0026 deploy, the F1.8 PL/pgSQL function
`prod.calcular_cotizacion` MUST NOT return `iva_no_configurado` for any
valid `(uuid_sucursal, uuid_tipo_vehiculo)` combination with a vigente
tarifa — the KD-IVA blocker is resolved
**And** the row MUST be insertable by `rol_app` (the `impuestos`
permissions MUST allow INSERT for the alembic migration context; the
handler reads via `prod.calcular_cotizacion` which bypasses rol_app
directly via PL/pgSQL execution)
**And** the MIGRATION 0026 Op 2 insert MUST commit before any F1.7 test
runs (DEC-IMP-01: ownership of the catalog scope remains HU-F14.2
Parte II; F1.7 apply advances the dependency as a side effect, mirroring
F1.6's `INSERT … ON CONFLICT (tipo_alerta) DO NOTHING` in MIGRATION
0025).
**RFC 2119**: MUST (pre-flight on 3 tables, `porcentaje=0.19` constant,
UK `(codigo, vigente_desde)` for idempotency, no `iva_no_configurado`
post-deploy).

#### Scenario: MIGRATION 0026 first apply seeds IVA successfully

**Given** MIGRATION 0025 (`alerta_datos_nuevos`) is the current `head` and
`prod.impuestos`, `prod.salidas`, `prod.alert_types` tables exist
**When** `alembic upgrade head` runs MIGRATION 0026
**Then** Op 1 (pre-flight) MUST NOT raise (all 3 tables exist)
**And** Op 2 MUST insert one row in `prod.impuestos` with `codigo='IVA'`,
`nombre='IVA'`, `porcentaje=0.19`, `vigente_desde=NOW() AT TIME ZONE
'UTC'`, `vigente_hasta=NULL`, `estado='activo'`, `created_at=NOW()`
**And** Op 3 MUST insert two rows in `prod.alert_types`
(`subscripcion_vencida_forzado`, `tarifa_vigente_forzado`) — see REQ-OPS-050
for the alerta contract
**And** Op 4 MUST create the partial unique index `one_exit_per_ingreso`
— see REQ-OPS-051.

#### Scenario: MIGRATION 0026 second apply is idempotent (no-op)

**Given** MIGRATION 0026 was applied successfully and is the current `head`
**When** `alembic upgrade head` runs again
**Then** Op 2 MUST be a no-op (`ON CONFLICT (codigo, vigente_desde) DO
NOTHING` matches the existing IVA row)
**And** Op 3 MUST be a no-op (`ON CONFLICT (tipo_alerta) DO NOTHING` for
both alert_types)
**And** Op 4 MUST be a no-op (`IF NOT EXISTS` on the partial unique
index)
**And** the migration MUST NOT produce duplicate rows.

#### Scenario: pre-flight aborts when `prod.impuestos` missing (regression test)

**Given** a test environment where `prod.impuestos` has been dropped (or
MIGRATION 0001-0025 have not run) — simulated in
`tests/integration/test_migration_0026_preflight.py`
**When** `alembic upgrade head` runs MIGRATION 0026
**Then** Op 1 (pre-flight `DO $$` block) MUST raise
`0026_preflight_abort: tabla prod.impuestos no existe. Aplique migrations
0001-0025 antes.`
**And** Op 2, Op 3, Op 4 MUST NOT execute.

#### Scenario: post-0026 deploy, F1.8 `iva_no_configurado` no longer occurs

**Given** MIGRATION 0026 has been applied and `prod.impuestos` has the
IVA row with `porcentaje=0.19`, `vigente_desde <= NOW()`, `vigente_hasta
IS NULL`, `estado='activo'`
**When** any valid `POST /operacion/salidas` reaches V5 (REQ-OPS-047) and
invokes `prod.calcular_cotizacion(:p)`
**Then** the F1.8 PL/pgSQL MUST find the IVA row, compute `iva = total *
0.19`, `subtotal = total - iva`, and return `{"cobrar":true,"subtotal":...,
"iva":...,"total":...}` (or `{"cobrar":false,...}` for mensualidad)
**And** MUST NOT return `{"error":"iva_no_configurado"}` — the KD-IVA
blocker is resolved (verified by F1.8 regression test
`pytest backend/tests/integration/test_cotizar_db.py`).

## Modified Capabilities

- **`operational`** — the canonical capability adds REQ-OPS-042..052
  (11 requirements): POST /operacion/salidas contract, V1..V5
  validations, KD-FORZADO-01 prefix contract verbatim F1.6 reuse,
  server-side `tipo_salida` derivation, alerta same-TX contract for
  V2/V5 bypass, partial unique index `one_exit_per_ingreso` with 409
  mapping, and inline-seed `impuestos.IVA` via MIGRATION 0026. The merged
  main spec (`openspec/specs/operations/spec.md`) gains 11 new
  requirements and no existing requirement is modified (REQ-OPS-001..041
  remain unchanged). The new `prod.salidas` table inserts are
  coordinated with the existing `prod.anulaciones` workflow (Fase 7+)
  via the partial unique index's `NOT EXISTS` predicate (REQ-OPS-051).

## Out of Scope

- **Workflow de anulación para salidas** (`prod.anulaciones(tipo_anulable='salida')`
  workflow for reversing a salida post-creation). DEC-SAL-01 delega a
  Fase 7+. `prod.salidas` is append-only; corrections via the existing
  `anulaciones` workflow which the partial unique index's `NOT EXISTS`
  predicate already accounts for (REQ-OPS-051).
- **`correlacion_id`** in the payload. DEC-IDEM-01 delegates idempotency
  to the `Idempotency-Key` HTTP header (PR2 middleware, intact); the
  `extra='forbid'` rejection of unknown fields enforces this contract.
- **Lock pesimista** (`SELECT … FOR UPDATE/SHARE`) on `prod.ingreso`
  (V1) or `prod.subscripciones_cliente` (V2). KD-S7 lock continuity on
  `tarifas_sucursal` via F1.8 PL/pgSQL is sufficient; the other tables
  are read-mostly. The partial unique index `one_exit_per_ingreso`
  (REQ-OPS-051) closes the V1 TOCTOU race without pessimistic locks.
- **Versionado de UI cliente** (Fase 2 frontend — `web_sucursal/src/lib/validation/salida.ts`
  should disable any client-side `tipo_salida` pre-classification once
  this endpoint is in production). F1.7 **NO** modifies the client;
  the client cleanup is post-archive.
- **Endpoint `POST /operacion/salidas/mensualidad`** — out of scope per
  DEC-MONO-01; consolidated into one handler with server-side derivation.
- **Endpoint `GET /operacion/salidas/{uuid}`** (preview without
  inserting) — out of scope; the handler does insert or 422, no preview.
- **Alertas adicionales** (e.g. `placa_no_coincide_forzado`,
  `subscripcion_sin_vehiculo`). Only `subscripcion_vencida_forzado` and
  `tarifa_vigente_forzado` are seeded in MIGRATION 0026 Op 3; other
  alertas are operational and out of scope for F1.7.
- **Numeración de factura electrónica (FE)** — Fase 8 (HU-F1.10);
  F1.7 only persists the lifecycle event, not the factura.
- **Permisos RBAC diferenciados para `forzado`** (e.g. "solo admin-").
  D-HU-F1.7-18 accepts both `operador-` and `admin-` for MVP; the
  alerta + audit log detect abuse; check dedicated in future HU.
- **Vista `V_SALIDA_TIPO`** for direct `tipo_salida` query — out of scope;
  the client derives from the response field. If a direct query is
  needed, create the view in a future HU.
- **Métricas / observabilidad del handler** (counter of `forzado=true`
  per day, latency p99 of `create_salida`). Out of scope; aligned with
  future observability HU.
- **Cleanup del cliente** (`web_sucursal/src/lib/validation/salida.ts`
  pre-classification of `tipo_salida`). F1.7 delivers the server-side
  enforcement; the client cleanup is post-archive.
- **Modificación a `IdempotencyKeyMiddleware`** (PR2). Intact; the
  handler changes the response in the happy path (201) and adds
  404/409/422 before the INSERT, but the middleware behavior is
  preserved.

## Files affected (F1.7 delta)

- `backend/packages/parkos_core/migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py`
  (NEW, ~140 LOC) — Alembic migration with 4 operations (KD-7 pre-flight
  `DO $$` over `prod.impuestos`, `prod.salidas`, `prod.alert_types`;
  inline-seed `impuestos.IVA` row with `porcentaje=0.19` via `INSERT …
  ON CONFLICT (codigo, vigente_desde) DO NOTHING`; inline-seed 2
  `alert_types` rows for V2/V5 bypass alerts via `INSERT … ON CONFLICT
  (tipo_alerta) DO NOTHING`; `CREATE UNIQUE INDEX CONCURRENTLY IF NOT
  EXISTS one_exit_per_ingreso` on `prod.salidas (uuid_ingreso) WHERE
  NOT EXISTS (anulaciones ejecutadas)`). `revision =
  "0026_seed_impuestos_iva_and_one_exit_per_ingreso"`, `down_revision =
  "0025_alerta_datos_nuevos"`. Downgrade is reverse-order
  (`DROP INDEX` then `DELETE` on the 2 alert_types then `DELETE` on the
  IVA row, all under superuser context to bypass `alert_types_inmutable`
  trigger). (REQ-OPS-051, REQ-OPS-052)

- `backend/packages/parkos_core/src/parkos_core/models/L_S/salida.py`
  (NEW, ~40 LOC) — ORM model `Salida(LifecycleEventBase)` with audit +
  sync mixins; schema `prod.salidas`; closes the pre-existing gap (the
  `salidas` table has existed since migration 0001 but had no ORM
  mapping). (REQ-OPS-048)

- `backend/packages/parkos_core/src/parkos_core/repo/salida.py`
  (NEW, ~180 LOC) — 4 helper functions:
  - `buscar_ingreso_activo_por_uuid(session, *, uuid_ingreso) -> Ingreso | None`
    (V1, REQ-OPS-043)
  - `cotizar_para_salida(session, *, uuid_ingreso) -> dict[str, Any]`
    (V5 thin wrapper over `repo.cotizacion.cotizar_ingreso` F1.8;
    REQ-OPS-047)
  - `crear_salida_evento(session, *, actor_uuid, new_attrs) -> Salida`
    (Step 8 INSERT via ORM + `IntegrityError("one_exit_per_ingreso")`
    → typed exception `SalidaDuplicada`; REQ-OPS-048, REQ-OPS-051)
  - `insertar_alerta_salida_forzado(session, *, uuid_sucursal,
    uuid_salida, actor_uuid, motivo, tipo_alerta) -> None` (Step 9
    alerta INSERT with `datos_nuevos={"motivo": <motivo>, "uuid_salida":
    <uuid>}` jsonb; REQ-OPS-050)

  Plus typed exceptions `SalidaDuplicada` (mapped to 409 by handler).

- `backend/packages/parkos_core/src/parkos_core/repo/impuestos.py`
  (NEW, ~50 LOC) — `validar_iva_configurado(session) -> bool` read helper
  for HU-F1.9 (facturación) snapshot validation, HU-F14.2 audit, and
  test mocks. The PL/pgSQL function `prod.calcular_cotizacion` reads
  `prod.impuestos` directly without going through this Python helper.
  (REQ-OPS-052)

- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py`
  (MODIFICAR, add `create_salida` lines ~296-360, ~200 LOC) — handler
  with the 12-step chain per D-HU-F1.7-20: KD-3 issuer claims → V1
  ingreso activo → tenant scope (post-V1, KD-S2) → V2 subscripción
  vigente al momento salida → V3 placa matches ingreso (optional) →
  V4 KD-FORZADO-01 prefix contract (F1.6 verbatim reuse) → V5 tarifa
  vigente via F1.8 PL/pgSQL → INSERT salida `[A]` → alerta if V2/V5
  bypassed → `await session.commit()` (single commit for KD-S7 lock
  continuity) → derive `tipo_salida` (DEC-SUC-21-NEW) → response shape.
  Same `_ingreso_issuer_dep` and `get_tenant_ctx` reuso as
  `create_ingreso` (lines 132-294, F1.6). `api/v1/__init__.py` and
  `router_factory.py` intact. (REQ-OPS-042..050)

- `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py`
  (MODIFICAR, +80 LOC) — `SalidaCreateForzado(uuid_ingreso: UUID,
  placa: str | None, observaciones: str | None, forzado: bool = False)`
  (REQ-OPS-042 input); `SalidaReadForzado(uuid, created_at, created_by,
  sync_status, sync_timestamp, sync_attempts, uuid_sucursal,
  uuid_ingreso, fecha_salida, tipo_salida: Literal["MENSUALIDAD",
  "ROTACION"], forzado_en_creacion: bool = False, motivo_forzado: str |
  None = None, cotizacion_snapshot: CotizarFacturacion | None = None)`
  (REQ-OPS-042 output, REQ-OPS-049 derivation field); 4 typed error
  classes (`IngresoNoEncontradoError` 404 discriminator for V1,
  `SalidaDuplicadaError` 409 discriminator for the partial unique index
  violation, `PlacaNoCoincideConIngresoError` 422 discriminator for V3,
  `TarifaVigenteNoEncontradaError` 422 discriminator for V5 without
  bypass). `extra='forbid'` inherited from `_Base` rejects injection of
  `tipo_salida` and any other extra field.

- `openspec/specs/operations/spec.md` (raíz, modified via archive phase)
  — gains REQ-OPS-042..052 (11 requirements) + entry in
  `## Modified Capabilities`. No change to REQ-OPS-001..041.

- `backend/tests/unit/test_operacion_salidas.py` (NEW, ~400 LOC, 10
  tests) — T1 rotación exitosa 201 + `tipo_salida=ROTACION` +
  `cotizacion_snapshot`; T2 rotación sin tarifa 422; T3 rotación forzada
  con alerta 201 + `tarifa_vigente_forzado`; T4 duplicada 409; T5
  mensualidad exitosa 201 + `tipo_salida=MENSUALIDAD` +
  `cotizacion_snapshot=None`; T6 mensualidad vencida sin forzado 422; T7
  mensualidad vencida con forzado 201 + `ROTACION` + alerta
  `subscripcion_vencida_forzado`; T8 placa no coincide 422; T9
  KD-FORZADO prefijo válido 201; T10 KD-FORZADO motivo <10 chars 422.
  (REQ-OPS-042..050)

- `backend/tests/unit/test_operacion_salidas_kd_forzado.py` (NEW,
  ~80 LOC, 2 tests) — T-aux prefix mid-string no-startswith returns
  None; T-aux KD-FORZADO contract reuse validation (no duplicate of
  F1.6 tests). (REQ-OPS-046)

- `backend/tests/integration/test_salida_create_db.py` (NEW, ~250 LOC,
  3 tests) — T11 insert+alerta same-TX atomicity; T12 partial unique
  index concurrent threads → 409; T13 IVA not seeded (DELETED for test)
  → 500. Requires `PARKOS_DOCKER_TEST=1`. (REQ-OPS-048, REQ-OPS-050,
  REQ-OPS-051, REQ-OPS-052)

- `backend/tests/integration/test_migration_0026_idempotent.py` (NEW,
  ~150 LOC, 1 test) — runs `alembic upgrade head` 2 times, second is
  no-op. (REQ-OPS-052)

- `backend/tests/integration/test_migration_0026_preflight.py` (NEW,
  ~120 LOC, 1 test) — pre-flight `DO $$` aborts on simulated missing
  tables. (REQ-OPS-052)

- `backend/tests/static/test_salida_handler_step_order.py` (NEW, ~100
  LOC, 1 AST walk) — `ast.walk()` over `api/v1/operacion.py::create_salida`
  verifying literal order of helper invocations
  (`buscar_ingreso_activo_por_uuid` → `validar_subscripcion_vigente` →
  `detectar_tipo_vehiculo` → `validar_kd_forzado` →
  `cotizar_para_salida` → `crear_salida_evento` →
  `insertar_alerta_salida_forzado`) and rejecting multiple
  `session.commit()` calls (KD-S20 invariant). (REQ-OPS-042..050)

- `backend/tests/static/test_no_write_after_salida_insert.py` (NEW,
  ~100 LOC, 1 AST walk) — `ast.walk()` over `repo/salida.py` rejecting
  `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` outside `crear_salida_evento`
  and rejecting the introduction of `tipo_salida`/`valor`/`subtotal`/
  `iva`/`total` columns to `new_attrs` (DEC-SUC-21-NEW + DEC-SUC-23 + R6
  mitigation). (REQ-OPS-048, REQ-OPS-049)

## Files NOT touched (deliberate)

- `backend/packages/parkos_core/src/parkos_core/api/v1/__init__.py` —
  router already mounted at line 143 (`r.include_router(operacion.router)`).
- `backend/packages/parkos_core/src/parkos_core/api/v1/router_factory.py`
  — `make_router` intact (F1.1 commit `f7cb37a`); not used in `/operacion`.
- `backend/packages/parkos_core/src/parkos_core/api/deps.py` — KD-3
  chain intact (`get_tenant_ctx`, `requires_issuer`).
- `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` —
  `get_tenant_ctx` validated in F1.2.
- `backend/packages/parkos_core/src/parkos_core/models/L_E/ingreso.py`
  — V1 is read-only (no schema change).
- `backend/packages/parkos_core/src/parkos_core/models/V/*` — no schema
  changes.
- `backend/packages/parkos_core/migrations/versions/0022_create_calcular_cotizacion.py`
  — F1.8 PL/pgSQL function unchanged; F1.7 invokes it.
- `backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py`
  — F1.5 materialized view unchanged.
- `backend/packages/parkos_core/migrations/versions/0025_alerta_datos_nuevos.py`
  — F1.6 alert_type seed; MIGRATION 0026 stacks on top via
  `down_revision = "0025_alerta_datos_nuevos"`.
- `backend/packages/parkos_core/src/parkos_core/repo/event.py`,
  `repo/cotizacion.py` (F1.8) — helpers reused without modification.
- `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py` —
  `validar_kd_forzado` reused verbatim for V4 (REQ-OPS-046).
- `backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py`
  — `validar_subscripcion_vigente` + `resolve_active_subscription_for_exit`
  reused verbatim for V2 (REQ-OPS-044).
- `backend/packages/parkos_core/src/parkos_core/repo/placa.py` —
  `detectar_tipo_vehiculo` reused verbatim for V3 (REQ-OPS-045).
- `backend/packages/parkos_core/src/parkos_core/repo/alerta.py` — F1.6
  `insertar_alerta_forzado` pattern; F1.7 creates
  `insertar_alerta_salida_forzado` with `datos_nuevos` shape carrying
  `uuid_salida` instead of `uuid_ingreso` (different identifier for the
  bypassed entity).
- `web_sucursal/src/lib/validation/salida.ts` — Fase 2 frontend scope;
  client cleanup of pre-classification is post-archive.