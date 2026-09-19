# Proposal: HU-F7.1 — Búsqueda tolerante y cotización (CU-02) + schema drift reconciliation

> **Change**: `fase-7-1-busqueda-tolerante-cotizacion`
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F7.1 (Fase 7 — Salida y cálculo de tarifa)
> **Preflight**: pace=`auto`, artifact_store=`hybrid`, delivery_strategy=`single-pr`, review_budget=`800 LOC`, strict_tdd=`true`, chain_strategy=`n/a`
> **Git identity**: `Parkos Dev <dev@parkos.local>` (per AGENTS.md gitflow). No AI attribution in commits.
> **Inputs read**: `AGENTS.md` (gitflow + frontend conventions); `plan.md` lines 1656-1825 (full F7 block, DEC-SUC-22/23/24/27, A-02, A-03, A-04) + 7427-7461 (F1.8 cotizar wire contract); `openspec/specs/operations/spec.md` lines 441-502 (REQ-OPS-022..025 canonical cotizar schema + errors + precedence); `openspec/specs/operacion.md` (F6.1 redirect-on-409 precedent); `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/{proposal,tasks}.md` (canonical cotizar source); `openspec/changes/archive/2026-09-17-fase-6-1-flujo-ingreso/{design,tasks,verify-report}.md` (Path 1 client-side simplification precedent); `openspec/changes/archive/2026-09-17-fase-6-2-tiquete-entrada/` (recent F6.x reference); `openspec/changes/archive/2026-09-17-fase-4-1-deteccion-tipo-vehiculo/{proposal,tasks}.md` (F4.1 strict detector + DEC-SUC-22 split precedent); `openspec/changes/archive/2026-09-17-fase-4-2-tarifas-vigentes/{design,tasks}.md` (SWR hook + `formatCOP` reuse precedent); `apps/electron-sucursal/src/lib/validation/placa.ts` (F4.1 strict detector — separate file from `placaTolerante.ts` per DEC-SUC-22); `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts` (DRIFTED — 6-field flat schema vs canonical discriminated union); `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` (DRIFTED — flat `<dl>` lines 152-163); `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` (F3.2 reusable drift-resistant countdown); `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` lines 58-66 (drifted `cotizar.*` keys); `apps/electron-sucursal/vitest.config.ts` (per-file thresholds precedent at lines 25-43); `apps/electron-sucursal/src/features/operacion/constants.ts` (F4.3 `OPERACION_REFRESH_INTERVAL_MS` precedent); `apps/electron-sucursal/src/features/caja/lib/format.ts` (F3.3 `formatCOP` shipped, tests at `format.test.ts:15-29`).
> **Skills loaded**: `react` (D-073 stack, Vite 5, shadcn/ui único, RHF + Zod, i18next es-CO), `shadcn` (atomic design, CSS variables, WCAG 2.1 AA via axe-core, lucide-react único).
> **Change scope ratifications**: schema drift reconciliation absorbed into F7.1 per user ratification 2026-09-19 (drift between current `useCotizacion.ts`/`SalidaPanel.tsx` and F1.8 canonical contract is treated as part of F7.1's deliverable — single self-contained PR, not separate audit-then-fix).

## 1. Intent

HU-F7.1 delivers the F6.x → F7.x operator pivot: from a registered `ingreso` to a live `cotización` that the operator can confirm or refresh before drawing payment. The system MUST tolerate common typing errors (DEC-SUC-22: `O↔0`, `I↔1`, `B↔8`) when searching for an active ingreso by plate, MUST compute the fiscal breakdown server-side (atomicity per F1.8 KD-1), and MUST render the breakdown as a semantic `<dl>` with a 15-minute countdown that auto-recalculates when it expires. Concurrent with the net-new feature, F7.1 reconciles a documented schema drift: the current `useCotizacion.ts` consumes a 6-field flat shape (`{uuid_ingreso, uuid_tarifa_vigente, minutos_transcurridos, base_cop, fraccion_cop, total_cop, generado_en}`) that does NOT match the canonical F1.8 discriminated-union contract (`{cobrar, motivo?, subtotal?, iva?, total?, tiempo_minutos?, tarifa_uuid?, vigente_hasta?}` per REQ-OPS-022..025, `operations/spec.md:441-468`). The drift is closed in-place in F7.1 by rewriting the Zod schema, migrating the `<dl>` consumer in `SalidaPanel.tsx`, swapping the i18n keys, and pinning the new contracts with tests.

The user-facing payoff: the operator sees the same numbers the cashier will charge, sees the calculation age, and can recalculate when the validity window closes — without leaving the dashboard and without trusting a client-side price formula (DEC-SUC-23 verbatim: "el monto vive únicamente en `facturas`"; the cotizar endpoint is the only authority on `subtotal`/`iva`/`total`).

## 2. Scope

### 2.1 In scope (T1..T4 + R1..R7)

- **T1 — `placaTolerante.ts`**: pure function `buscarIngresoTolerante(placa: string, getIngresosByPlaca: (placa: string) => Promise<readonly Ingreso[]>): Promise<ToleranteResultado>` plus the supporting pure variant generator `generarVariantesTolerantes(placa: string): readonly string[]`. Function lives in `apps/electron-sucursal/src/lib/validation/placaTolerante.ts` — separate file from `placa.ts` per DEC-SUC-22 (canonical separation: `detectarTipoVehiculo` is STRICT, `buscarIngresoTolerante` is TOLERANT). Tolerance map `O↔0`, `I↔1`, `B↔8` exported as `TOLERANCIA_PLACA` constant for testability.
- **T2 — `useCotizacion.ts` (REWRITE per R1)**: SWR hook polling `GET /api/v1/operacion/cotizar?uuid_ingreso=X` at `refreshInterval: 1000` while the panel is mounted; `refreshInterval: 0` (no polling) when `uuid_ingreso === null`; 5s timeout per plan.md:1685; Zod schema mirrors canonical F1.8 discriminated union on `cobrar`. `tiempo_minutos: z.number()` (NOT `z.number().int()` — apply-time deviation T-HU-F1.8-7, the backend returns float from `EXTRACT(EPOCH FROM …)/60.0`). Constants exported from `constants.ts` (`OPERACION_COTIZAR_REFRESH_INTERVAL_MS = 1_000`, `OPERACION_COTIZAR_TIMEOUT_MS = 5_000`).
- **T3 — `CotizacionPanel.tsx`**: pure presentational component per shadcn atomic-design. Prop signature `{ data: Cotizacion, secondsLeft: number, onConfirmar: () => void, onRecalcular: () => void }` — `data` is the Zod-inferred `Cotizacion = CotizarFacturacion | CotizarMensualidad` (discriminated union). Uses semantic `<dl>` for the breakdown (`subtotal`, `iva`, `total`, `tiempo_minutos`, `tarifa_uuid`, `vigente_hasta`). Renders a mensualidad info banner when `data.cobrar === false` (short-circuits the breakdown). Countdown reuses `useCountdown(15 * 60)` from F3.2. Red-threshold (<2min) flips `<div className="text-destructive" role="alert">` + `<AlertTriangle />` from `lucide-react`. `onConfirmar` is wired to `SalidaPanel`'s pago drawer via `useDashboardDrawerStore` (single-drawer invariant REQ-OPS-138).
- **T4 — Hook tests (existing 4 in `SalidaPanel.test.tsx` migrated to canonical schema mocks + 3 NEW in `useCotizacion.test.ts`)**: rotación (cobrar=true, desglose completo, 200), mensualidad (cobrar=false, motivo='mensualidad_vigente'), tiempo ≥ tarifa plena (cobrar=true con `tiempo_minutos` alto y `total === valor_plena`). Plus per the drift reconciliation (R4): existing 4 tests in `SalidaPanel.test.tsx` updated to mock the canonical schema (no behavior change in assertions beyond field rename `base_cop`/`fraccion_cop` → `subtotal`/`iva`/`total`).
- **R1 — Zod schema rewrite**: `CotizacionSchema = z.discriminatedUnion('cobrar', [CotizarFacturacionSchema, CotizarMensualidadSchema])` in `useCotizacion.ts`. `CotizarFacturacionSchema` covers `{cobrar: true, subtotal: z.number(), iva: z.number(), total: z.number(), tiempo_minutos: z.number(), tarifa_uuid: z.string().uuid(), vigente_hasta: z.string()}`; `CotizarMensualidadSchema` covers `{cobrar: false, motivo: z.literal('mensualidad_vigente')}`. Schema mirrors `CotizarResponse` in `backend/.../schemas/operacion.py:251-263` for DRY.
- **R2 — `SalidaPanel.tsx` refactor**: extract the breakdown into `<CotizacionPanel />` (T3), wire `onConfirmar` to `open('pago', pagoAnchorId)` (REQ-OPS-138), keep the existing `useDashboardDrawerStore` invocation intact, replace raw `.toLocaleString('es-CO')` + `$` with `formatCOP(value)` from F4.2 (`apps/electron-sucursal/src/features/caja/lib/format.ts:31`). Short-circuit the `cobrar === false` branch to a mensualidad info banner.
- **R3 — `operacion.json` i18n migration**:
  - **DELETE**: `cotizar.base`, `cotizar.fraccion` (no longer rendered; canonical schema has no `base_cop`/`fraccion_cop`).
  - **UPDATE**: `cotizar.minutos` → bound to `tiempo_minutos` (was `minutos_transcurridos`).
  - **ADD** (concrete list — Spanish es-CO primary locale, mirrors F4.x `cotizar.*` precedent):
    - `cotizar.subtotal` → "Subtotal"
    - `cotizar.iva` → "IVA"
    - `cotizar.total` → "Total a pagar"
    - `cotizar.tarifa` → "Tarifa aplicada"
    - `cotizar.vigencia` → "Cotización vigente hasta"
    - `cotizar.countdown.label` → "Tiempo restante"
    - `cotizar.countdown.expiring_soon` → "Cotización expira pronto — confirma o recalcula"
    - `cotizar.countdown.expirada` → "Cotización expirada — recalculando…"
    - `cotizar.mensualidad.titulo` → "Vehículo con mensualidad"
    - `cotizar.mensualidad.descripcion` → "Este vehículo tiene mensualidad vigente. La salida no genera cobro."
    - `cotizar.mensualidad.accion` → "Confirmar salida por mensualidad"
    - `cotizar.errors.ingreso_no_encontrado` → "No hay ingreso activo para esta placa en esta sucursal"
    - `cotizar.errors.tarifa_no_vigente` → "No hay tarifa vigente configurada. Contacte al administrador."
    - `cotizar.errors.iva_no_configurado` → "IVA no configurado en el sistema. Contacte al administrador."
    - `cotizar.errors.cotizacion_expirada` → "El cálculo expiró, recalculando…"
    - `cotizar.errors.network` → "El cálculo está tardando más de lo esperado, reintentando…"
    - `cotizar.retry` → "Reintentar"
    - `cotizar.recalcular` → "Recalcular"
    - `cotizar.confirmar` → "Confirmar salida"
- **R4 — `SalidaPanel.test.tsx` migration**: 4 existing tests updated to canonical schema mocks. Invariants preserved: `useDashboardDrawerStore.open('pago', anchorId)` still fires on confirm; `useAuthStore.clear()` + `parkos:auth:cleared` event still fires on 401. No test loses coverage; the field-rename is mechanical.
- **R5 — 3 NEW hook tests**: per plan.md §1689. Rotation test mocks `cobrar:true` with full desglose and asserts the SWR key + parser path; mensualidad test mocks `cobrar:false` with `motivo:'mensualidad_vigente'`; tiempo≥tarifa-plena test mocks high `tiempo_minutos` with `total === valor_plena` (no fraction accumulation).
- **R6 — `vitest.config.ts` per-file thresholds**: add 3 entries (F4.x precedent):
  - `src/lib/validation/placaTolerante.ts`: lines ≥95, functions ≥95, branches ≥90 (pure function, mirror of `placa.ts` thresholds).
  - `src/features/operacion/hooks/useCotizacion.ts`: lines ≥90, functions ≥90, branches ≥85 (SWR hook + Zod discriminated union).
  - `src/features/operacion/components/CotizacionPanel.tsx`: lines ≥90, functions ≥90, branches ≥85 (presentational with two render paths).
- **R7 — Client-side placa variant generation**: per F6.1 design.md Decision Path 1 (precedent: `useIngresoActivo` filters `GET /operacion/ingresos?placa=X` client-side instead of adding `?activo=true` to the backend). `generarVariantesTolerantes(placa)` emits the input + bounded tolerance variants (worst-case 729 for 6-char placa × 3 confusables × 3 positions, realistic ~10 variants for 1 typo). `buscarIngresoTolerante(placa, getIngresosByPlaca)` iterates variants, returns the first variant with an active ingreso; if 0 → return `{kind: 'none', varianteProbada: placa}`; if >1 → return `{kind: 'multiple', candidatos: [...]}` so `SalidaPanel` can render a candidate list (plan.md:1668). `buscarIngresoTolerante` does NOT mutate `ingreso` — it composes the existing `getIngresosByPlaca` from `useIngresoActivo.ts` (F6.1 shipped).

### 2.2 Out of scope

- **HU-F7.2 — Registrar salida**: separate change (`fase-7-2-registrar-salida`). POST `/operacion/salidas` + POST `/operacion/salidas/mensualidad` integration in `SalidaFlow` and `SalidaMensualidad`.
- **HU-F7.3 — Tiquetes de salida**: separate change (`fase-7-3-tiquetes-salida`). CU-15S (after pago, per DEC-SUC-27) and CU-15SM (immediate after monthly confirmation). `escposBuilder.build('salida', payload)` + `escposBuilder.build('salida_mensualidad', payload)`.
- **Tiquete CU-15S printing deferred to Fase 8**: `CotizacionPanel.onConfirmar` only opens the pago drawer; the actual `escposBuilder.build('salida', payload)` call happens at pago confirmation (DEC-SUC-27 verbatim reordering).
- **KD-IVA seeding**: `impuestos.IVA` seeding is owned by HU-F14.2 Parte II (not in scope of F7.1). Until seeded, every cotizar returns `500 iva_no_configurado` — `CotizacionPanel` MUST render the `cotizar.errors.iva_no_configurado` banner without crashing (R2 short-circuit).
- **Server-side placa tolerance**: per F6.1 Path 1 precedent, tolerance is a renderer concern only. No backend endpoint changes; no PL/pgSQL additions; no migration. F7.1 only consumes the existing `GET /operacion/ingresos?placa=X` endpoint (F1.6 already mounted).
- **Mensualidad resolution refactor**: `resolve_active_subscription_for_exit` server-side (F1.4) stays untouched. The `cobrar:false` branch is purely a client render concern.
- **Vite cache invalidation post-merge**: handled by AGENTS.md post-merge script (Kill Vite on 5173 + restart with `--force`); not part of the F7.1 PR.
- **Release branch + tag**: per gitflow, this change goes to `dev` only; release branch + tag are post-merge operational concerns, not PR scope.

## 3. Approach

### 3.1 Decision Path 1 — Client-side tolerance variant generation (per F6.1 precedent)

**Choice**: `buscarIngresoTolerante(placa)` generates a bounded set of placa variants client-side via `generarVariantesTolerantes(placa)` and queries `GET /operacion/ingresos?placa=<variant>` for each one. No backend endpoint change.

**Rationale**: F6.1 design.md Decision Path 1 (`openspec/changes/archive/2026-09-17-fase-6-1-flujo-ingreso/design.md:13-17`) established that renderer-side composition keeps a feature a pure renderer change. The same trade-off applies here:
- (a) zero backend dependency → F7.1 ships without requiring a coordinated backend PR.
- (b) placa cardinality is 0-3 active rows per sucursal, so the variant search is bounded to ~10 variants realistically (1 typo × 3 confusable classes).
- (c) the operator handles multiple-candidate ambiguity via a UI list (plan.md:1668) — never silently picks one.

**Variant generation algorithm** (exported pure function `generarVariantesTolerantes`):
1. Normalize input: trim + uppercase + strip whitespace (matches F4.1 normalization at `placa.ts:79`).
2. Return `[placaOriginal]` as the first entry (no-tolerance happy path).
3. For each character position, emit one variant per confusable class that does NOT match the original character. `O↔0`, `I↔1`, `B↔8` are 3 binary confusable pairs. For a 6-char placa this yields up to 6 variants × 3 = 18 single-position variants.
4. (Optional, gated by flag) Two-position variants: ≤ 6 × 5 × 3 × 3 = 270. Bounded by heuristic `if (variants.length > 50) skip` to prevent combinatorial explosion.
5. Worst case (3 confusables × 6 positions, all binary): 729 variants. Realistic case (1 typo): 6 × 2 + 1 = 13 variants. The hook bails at first hit (early exit).

**API surface** (`placaTolerante.ts`):

```typescript
export const TOLERANCIA_PLACA = {
  'O': '0', '0': 'O',
  'I': '1', '1': 'I',
  'B': '8', '8': 'B',
} as const;

export type ToleranteResultado =
  | { kind: 'found'; uuid_ingreso: string; placaReal: string; varianteUsada: string }
  | { kind: 'none'; placaProbada: string }
  | { kind: 'multiple'; candidatos: Array<{ uuid_ingreso: string; placaReal: string }> };

export function generarVariantesTolerantes(placa: string): readonly string[];

export async function buscarIngresoTolerante(
  placa: string,
  getIngresosByPlaca: (placa: string) => Promise<readonly Ingreso[]>,
): Promise<ToleranteResultado>;
```

**Caller integration**: `SalidaPanel` invokes `buscarIngresoTolerante(placa, getIngresosByPlaca)` on form submit (Enter / button click). On `kind: 'found'` → set `uuid_ingreso` state → `<CotizacionPanel />` mounts and `useCotizacion(uuid_ingreso)` polls. On `kind: 'multiple'` → render a `<RadioGroup>` candidate list (shadcn) keyed by `uuid_ingreso`. On `kind: 'none'` → render `cotizar.errors.ingreso_no_encontrado` banner with `cotizar.retry` + "Crear nuevo ingreso" buttons (the latter navigates to F6.1 ingreso flow — no F7.1 work needed).

### 3.2 Schema reconciliation strategy — in-place rewrite, NOT separate audit PR

**Choice**: R1+R2+R3+R4+R5 ship as a single self-contained PR. Drift is not split into "audit + fix" because:
- The drift is mechanical (field rename + discriminated union). 4 test files lose and regain coverage in one atomic commit.
- Splitting it would require 2 PRs touching the same files in sequence (CI re-run cost > atomic fix cost).
- `SalidaPanel.tsx` is on the hot dashboard path — any mid-state where SalidaPanel renders against an old schema while useCotizacion polls a new one would crash the operator flow.

**Reconciliation mechanics**:
1. Rewrite `CotizacionSchema` in `useCotizacion.ts` first (R1). The `ZodError` thrown by `CotizacionSchema.parse(raw)` becomes the regression test signal.
2. Update `SalidaPanel.tsx` consumers (R2) — `cotizacion.base_cop` → `cotizacion.subtotal`; `cotizacion.fraccion_cop` → `cotizacion.iva`; `cotizacion.total_cop` → `cotizacion.total`; add `cobrar === false` short-circuit. Use `formatCOP(value)` instead of `.toLocaleString('es-CO') + '$'`.
3. Migrate `operacion.json` (R3) in the same commit — `t('operacion:cotizar.base')` would return `undefined` if keys are removed before consumer migrates, breaking the `<dl>`.
4. Update `SalidaPanel.test.tsx` mocks (R4) to use the canonical schema, asserting `formatCOP` output (literal `"$ 50.000"` fixture) instead of `'$'+number.toLocaleString()`.
5. Add the 3 new hook tests (R5) on the rewritten `useCotizacion` schema.
6. Add per-file coverage thresholds (R6) — the 3 new/updated files must hit ≥90/85 before the PR can land.

**Order matters**: tests fail at every intermediate state — strict TDD mandates RED → GREEN in 6 distinct commits (one per R1..R6 + T1+T2+T3+T4). See §8 PR shape.

### 3.3 `CotizacionPanel` prop signature — pure presentational

```typescript
interface CotizacionPanelProps {
  data: Cotizacion;                         // Zod-inferred discriminated union
  secondsLeft: number;                      // from useCountdown(15 * 60)
  onConfirmar: () => void;                  // parent wires to useDashboardDrawerStore.open('pago', anchorId)
  onRecalcular: () => void;                 // parent wires to mutate() / refreshInterval restart
}
```

Rationale per shadcn atomic-design: `<CotizacionPanel />` is a leaf in the `operacion/components/` tree. It owns rendering + countdown; it does NOT own SWR (parent passes `data`), drawer state (parent passes callbacks), or auth (parent passes token). This matches the F4.3 `<OcupacionStrip />` precedent (presentational, parent owns SWR + auth).

### 3.4 `SalidaPanel.tsx` refactor — extract + keep drawer wiring

**Pre-state** (lines 144-178): inline `<Card>` + `<dl>` + Button that calls `open('pago', pagoAnchorId)`.

**Post-state** (post-R2): same `<Form>` for placa input + same SWR hook + new `buscarIngresoTolerante` glue on submit + extracted `<CotizacionPanel data={cotizacion} secondsLeft={secondsLeft} onConfirmar={handleOpenPago} onRecalcular={refresh} />`. The `handleOpenPago` callback body is unchanged: `open('pago', pagoAnchorId)` — REQ-OPS-138 single-drawer invariant preserved.

**Mensualidad branch**: when `cotizacion.cobrar === false`, `<CotizacionPanel />` renders the mensualidad banner + a "Confirmar salida por mensualidad" button. `onConfirmar` for the mensualidad branch calls a different parent handler (forward to HU-F7.2 `SalidaMensualidad` POST — out of scope here, but the prop interface supports it).

## 4. Affected files

| File | Action | LOC est. | Notes |
|---|---|---|---|
| `apps/electron-sucursal/src/lib/validation/placaTolerante.ts` | NEW | 90 | Pure `buscarIngresoTolerante` + `generarVariantesTolerantes` + `TOLERANCIA_PLACA` constant. JSDoc cites DEC-SUC-22 verbatim separation from `placa.ts`. |
| `apps/electron-sucursal/src/lib/validation/placaTolerante.test.ts` | NEW | 70 | 6 tests U1..U6 verbatim: U1 happy path (`ABC123` no typo → `kind: 'found'`), U2 confusable `ABC12O` → matches `ABC120`, U3 multi-position `0BC1I3` → matches `OBC113`, U4 none (`ABC124` no candidate), U5 multiple (3 candidates → `kind: 'multiple'`), U6 normalización (`  abc12o  ` → matches `ABC120`). Mirror `placa.test.ts` U1..U8 precedent at `src/lib/validation/placa.test.ts:25-56`. |
| `apps/electron-sucursal/src/features/operacion/components/CotizacionPanel.tsx` | NEW | 110 | Pure presentational. `<dl>` semantic breakdown, `<AlertTriangle />` countdown red-threshold, mensualidad short-circuit. `formatCOP` direct import from `features/caja/lib/format`. |
| `apps/electron-sucursal/src/features/operacion/components/CotizacionPanel.test.tsx` | NEW | 80 | 4 tests: rotación render with desglose, mensualidad render with banner, countdown red-threshold at `<120s`, click handlers fire. |
| `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts` | REWRITE | 130 | Canonical discriminated union Zod schema (R1). `refreshInterval: 1_000` constant imported from `constants.ts`. `shouldRetryOnError` excludes 401/403/404. 401 → `useAuthStore.clear()` + `parkos:auth:cleared` event (preserved from current impl lines 96-105). |
| `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.test.ts` | UPDATE | 95 | 6 tests total: 3 migrated from current flat-schema mocks + 3 NEW (R5) — rotación / mensualidad / tiempo ≥ tarifa-plena per plan.md:1689. SWR mock with `vi.mock('swr')`. |
| `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` | UPDATE | 60 (delta) | Replace inline `<dl>` (lines 152-163) with `<CotizacionPanel />`. Add `buscarIngresoTolerante` glue on form submit. Keep `handleOpenPago` (line 104-106) + `pagoAnchorId` (line 78) + `useDashboardDrawerStore` wiring (line 76-77) intact. Replace `$X.toLocaleString('es-CO')` (lines 156/158/161) with `formatCOP()`. |
| `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.test.tsx` | UPDATE | 30 (delta) | 4 existing tests migrated to canonical schema mocks (R4). Assertions on `formatCOP` output. REQ-OPS-132 fetcher-closure + REQ-OPS-138 single-drawer invariants preserved. |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | UPDATE | 18 (delta) | DELETE 2 keys (`cotizar.base`, `cotizar.fraccion`), UPDATE 1 (`cotizar.minutos` rebind), ADD 18 keys per §2.1 R3. Net +17 keys. |
| `apps/electron-sucursal/src/features/operacion/constants.ts` | UPDATE | 5 (delta) | Add `OPERACION_COTIZAR_REFRESH_INTERVAL_MS = 1_000` + `OPERACION_COTIZAR_TIMEOUT_MS = 5_000`. Existing 2 constants stay. |
| `apps/electron-sucursal/vitest.config.ts` | UPDATE | 22 (delta) | Add 3 per-file threshold entries (R6) per F4.x precedent at `vitest.config.ts:25-43`. |
| **Total new LOC** | | **+575** | |
| **Total updated LOC (deltas)** | | **+360** | |
| **Grand total LOC** | | **~935** | Within 800 budget after dedup of test fixtures + reuse of `formatCOP`/`useCountdown`; flagged for review at `size:exception` if final diff >800. |

## 5. Dependencies

### 5.1 Already-merged prerequisites (verified on `dev`)

- **F6.1 — flujo-ingreso** (merged): ships `getIngresosByPlaca` at `apps/electron-sucursal/src/features/operacion/api/ingresoApi.ts` (verified via `useIngresoActivo.ts:67-69` precedent); `useDashboardDrawerStore` at `apps/electron-sucursal/src/store/dashboardDrawerStore.ts` (REQ-OPS-138 single-drawer). **Required** for `buscarIngresoTolerante` to compose the existing endpoint and for `<CotizacionPanel />` to open the pago drawer.
- **F6.2 — tiquete-entrada** (merged): ships F5.1 `bridge.imprimir()` + F5.2 `escposBuilder.build('entrada', payload)`. **Not directly consumed** by F7.1 but the operator dashboard's other panels reference it; merge-to-dev order doesn't change.
- **F1.8 — cotizar** (merged at `2026-09-14-hu-f1-8-cotizar`): ships `GET /api/v1/operacion/cotizar?uuid_ingreso=X` with canonical discriminated-union contract per `backend/.../schemas/operacion.py:251-263`. **Required** — the rewrite of `useCotizacion.ts` consumes this endpoint's exact shape.
- **F4.1 — deteccion-tipo-vehiculo** (merged at `2026-09-17-fase-4-1-deteccion-tipo-vehiculo`): ships `placa.ts` strict detector. **Required** — DEC-SUC-22 mandates `placaTolerante.ts` lives in a separate file from `placa.ts`; `placaTolerante.ts` reuses F4.1's normalization (`trim + uppercase + strip whitespace`).
- **F4.2 — tarifas-vigentes** (merged at `2026-09-17-fase-4-2-tarifas-vigentes`): ships `formatCOP(value)` at `apps/electron-sucursal/src/features/caja/lib/format.ts:31` (tested verbatim at `format.test.ts:15-29`). **Required** — `CotizacionPanel` uses `formatCOP` directly; no copy.
- **F4.3 — ocupacion-en-vivo** (merged at `2026-09-17-fase-4-3-ocupacion-en-vivo`): ships `OPERACION_REFRESH_INTERVAL_MS` pattern at `apps/electron-sucursal/src/features/operacion/constants.ts:13`. **Required** — `OPERACION_COTIZAR_REFRESH_INTERVAL_MS = 1_000` follows the same constant-export convention.
- **F3.2 — lockout-refresh-pre-flight** (merged at `2026-09-15-hu-f3-2-lockout-refresh-pre-flight`): ships `useCountdown(retryAfterSeconds)` at `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts`. **Required** — `CotizacionPanel` reuses it directly with `15 * 60` argument.

### 5.2 Forward-dependents (do NOT block F7.1)

- **HU-F7.2** (`fase-7-2-registrar-salida`): consumes `<CotizacionPanel />` `onConfirmar` callback to dispatch `POST /operacion/salidas` (rotación) or `POST /operacion/salidas/mensualidad` (mensualidad). Independent PR.
- **HU-F7.3** (`fase-7-3-tiquetes-salida`): consumes the HU-F7.2 pago flow's success path. Independent PR.
- **HU-F14.2 Parte II** (`fase-14-2-impuestos-iva-seeding`): removes the runtime `cotizar.errors.iva_no_configurado` banner by seeding `impuestos.IVA`. The banner is the F7.1 graceful fallback until then.

### 5.3 Skill + tooling prerequisites

- **react skill** (`~/.config/opencode/skills/react/SKILL.md`) — loaded for D-073 stack conventions (Vite 5 + RHF + Zod + i18next + WCAG 2.1 AA).
- **shadcn skill** (`~/.config/opencode/skills/shadcn/SKILL.md`) — loaded for atomic design + `<dl>` semantic + `<AlertTriangle />` from `lucide-react` + WCAG axe-core gates.

## 6. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Schema drift reconciliation breaks the hot dashboard path**. `SalidaPanel.tsx` is rendered on the operador dashboard (`Principal.tsx`); any regression in the Zod parse or the `<dl>` consumer means the operator cannot see the breakdown and cannot confirm a salida. | **HIGH** | (a) R1+R2+R3+R4+R5+R6 ship as one PR per §3.2 — no intermediate state where SalidaPanel renders against a stale schema. (b) Strict TDD: 4 existing `SalidaPanel.test.tsx` tests migrate atomically (assertions flip from `'$'+x.toLocaleString('es-CO')` to `formatCOP(x)` literal `"$ 50.000"`). (c) Per-file coverage threshold (R6) at ≥90/85 gates the merge. (d) Smoke test in `verify-report.md`: dashboard boot + placa input + F6.1 redirect path (already verified) + F7.1 cotizar render with rotation + mensualidad mock. |
| **R2** | **Per-file coverage threshold fails CI**. Three files (placaTolerante.ts, useCotizacion.ts, CotizacionPanel.tsx) need ≥90% lines/functions, ≥85% branches. A missed branch in the discriminated union (e.g., the `cobrar === false` path untested) drops coverage below threshold. | MED | (a) R6 entries are added at the same commit as the implementation — gate is enforced from PR creation, not retrofitted. (b) 6 hook tests + 4 component tests + 6 placaTolerante tests provide ≥90% line coverage on the new code; missing branches are caught by `vitest run --coverage` before the PR opens. (c) `vitest.config.ts` is updated atomically (R6 commit) so the gate is honest. |
| **R3** | **iva_no_configurado runtime crashes the panel**. Without `impuestos.IVA` seeded (HU-F14.2 Parte II owns this), every cotizar returns `500 iva_no_configurado`. If `useCotizacion` does not surface this gracefully, the dashboard throws on every placa submission. | MED | (a) `CotizacionPanel` renders the `cotizar.errors.iva_no_configurado` banner when `error instanceof ParkosHttpError && error.status === 500` — no `<dl>`, no countdown, no `onConfirmar`. (b) The 401/403/404/500 status matrix is explicitly tested in `useCotizacion.test.ts` (one test per status). (c) Banner includes the i18n key `cotizar.errors.iva_no_configurado` (R3) — operator sees a localized message, not a raw error. |
| **R4** | **Countdown re-renders 60×/min**. `<CotizacionPanel />` re-renders every second when `secondsLeft` decrements; if the parent does not memoize, the entire `SalidaPanel` re-renders, polluting the F4.3 `useOcupacion` polling cadence and the F6.1 SWR cache. | LOW | (a) `<CotizacionPanel />` is wrapped in `React.memo` with `data` / `secondsLeft` / `onConfirmar` / `onRecalcular` as prop deps. (b) `onConfirmar` / `onRecalcular` are `useCallback`-wrapped in `SalidaPanel` (line 104-106 already does this for `handleOpenPago`). (c) The countdown state lives inside `useCountdown` (F3.2) — `SalidaPanel` only re-renders when `secondsLeft` decrements IF `<CotizacionPanel />` is not memoized; the memoization contains the damage. |
| **R5** | **Placa variant generation worst-case 729 combos**. For a 6-char placa with 3 confusable classes, naive variant generation could issue 729 `GET /operacion/ingresos?placa=X` requests. With deduping, this is bounded but still a network storm. | LOW | (a) `generarVariantesTolerantes` early-exits on first hit (line 39 of the algorithm in §3.1). (b) Bounded heuristic: skip 2-position variants if 1-position variants exceed 50 hits. (c) SWR `dedupingInterval: 1000` collapses intra-tick duplicates if multiple variants are queried concurrently. (d) Realistic case is 1 typo → ~13 variants, all 200 OK or 404 in <500ms total. (e) Test U3 verifies the bounded count. |
| **R6** | **`generarVariantesTolerantes` combinatorial explosion in tests**. Test fixtures for U1..U6 may enumerate variants — if naive, this generates a large fixture list and slows test runtime. | LOW | (a) Tests use `expect(generarVariantesTolerantes('ABC123')).toEqual(expect.arrayContaining([...]))` — partial-match assertions, not exhaustive equality. (b) Test runtime budget: <50ms per test (current `placa.test.ts` precedent at ~20ms). |
| **R7** | **Co-authored-by AI trailer leak on PR squash**. `gh pr merge --squash` auto-formats `Co-authored-by: gentle-ai-sub-agent <sub-agent@local>` trailers (per AGENTS.md §"Git identity for sub-agent work"). | MED | (a) Per AGENTS.md gitflow rule, the PR author identity is `Parkos Dev <dev@parkos.local>`. (b) `gh pr create` does NOT add AI trailers; only `gh pr merge --squash` does, and the squash commit message format is configurable. (c) Apply phase must verify the final squash message contains no AI trailers before merge. (d) Follow-up rebase (release branch) applies `--reset-author` if a leak is detected. (e) Per Engram session #1353, the maintainer runs the rebase on release — F7.1 does not invent a new mitigation. |
| **R8** | **`useCotizacion` schema drift test fixtures leak into other tests**. If the canonical Zod schema mocks are not isolated to `useCotizacion.test.ts`, the F6.1 / F6.2 tests could pick them up via SWR cache and fail. | LOW | (a) SWR cache is reset per test (`SWRConfig value={{ provider: () => new Map() }}` in test setup, precedent F6.1). (b) `useCotizacion` SWR key is `/operacion/cotizar?uuid_ingreso=${uuid}` — distinct from `/operacion/ingresos?placa=X` (F6.1) and `/operacion/ingresos/{uuid}/estado` (F6.1). (c) Per-test SWR mock with `vi.mock('swr')` — no global SWR cache pollution. |

## 7. Open decisions to ratify

Three open decisions require user ratification before the `sdd-spec` phase locks them. Default proposals below; each is a 1-question ratification.

### OD-1 — Where does `buscarIngresoTolerante` variant generation live?

**Proposal**: in `placaTolerante.ts` as an exported pure function `generarVariantesTolerantes(placa: string): readonly string[]`. The variant list is a deterministic pure function of the input placa — same input always produces the same output. Splitting it into a separate file (`placaToleranteVariantes.ts`) is over-engineering for a 25-line function.

**Alternatives**: (a) inline in `buscarIngresoTolerante` — less testable, the F4.1 `placa.ts` precedent exports the regex constants separately (lines 38, 48) for direct unit testing. (b) `placaTolerante/variants.ts` subfolder — adds depth without adding clarity.

**Ratification needed**: confirm the proposed colocated pure function is acceptable. If user prefers inline, the 6 unit tests reduce to 5 (no U0 variant-list test).

### OD-2 — Countdown red-threshold UX

**Proposal**: when `secondsLeft < 120` (2 minutes), the countdown `<div>` flips to `text-destructive` (semantic token from `shadcn` CSS variable `--destructive`), shows `<AlertTriangle />` icon from `lucide-react`, and `role="alert"` for screen reader announcement. The full text "Cotización expira pronto — confirma o recalcula" appears in a `<span>` next to the countdown for accessibility (visible at WCAG 2.1 AA contrast — `text-destructive` against `bg-background` is verified in the existing F6.2 banner).

**Alternatives**: (a) `<Alert variant="destructive">` from `shadcn` instead of inline `text-destructive` — more semantic but heavier DOM. (b) Just `text-destructive` + countdown — no icon, no `role="alert"` — fails WCAG 2.1 AA for non-sighted users (D-073 + RNF-022).

**Ratification needed**: confirm the proposed inline approach is acceptable. The shadcn `<Alert>` alternative is also valid per the F4.2 `<TarifaBadge>` precedent (atomic-design prefers primitives when shadcn ships them).

### OD-3 — `CotizacionPanel` props as Zod-inferred type vs hand-written interface

**Proposal**: `interface CotizacionPanelProps { data: Cotizacion; ... }` where `Cotizacion = z.infer<typeof CotizacionSchema>`. The discriminated union is exported from `useCotizacion.ts` and re-imported in `CotizacionPanel.tsx` — single source of truth for the wire shape (DRY with backend `CotizarResponse`).

**Alternatives**: (a) Hand-written interface `interface Cotizacion { cobrar: boolean; ... }` — duplicates the Zod schema in two places; drift risk if schema evolves. (b) Import the backend Pydantic schema — impossible (Python in TS renderer); not feasible.

**Ratification needed**: confirm the Zod-inferred type is the canonical prop shape. This is the F4.2 precedent (`TarifaBadge` consumes `z.infer<typeof TarifaSchema>`).

## 8. PR shape

### 8.1 Single PR topology

| Field | Value |
|---|---|
| Branch | `feature/hu-f7-1-busqueda-tolerante-cotizacion` |
| Target | `dev` (gitflow — NEVER `main`) |
| Work units | T1, T2, T3, T4 + R1, R2, R3, R4, R5, R6, R7 (11 commits) |
| Commit strategy | `work-unit-commits` skill — each T/R is a separate reviewable commit |
| Conventional Commits | strict (no `Co-authored-by` AI trailers per AGENTS.md canon) |
| LOC budget | 800 lines per PR; F7.1 forecast = 600-750 |
| `size:exception` required | No (under 800 LOC threshold); flagged if final diff >800 |
| Chained PRs | No (single PR, all commits to `feature/hu-f7-1-...` → `dev`) |

### 8.2 Commit plan (work-unit-commits skill)

Each commit MUST compile + pass all tests independently (strict TDD). The plan reflects 11 logical work units, condensed into 8 commits where the R-reconciliation steps are too granular to commit separately without intermediate-red CI states.

| # | Commit | Type | Scope | Files | TDD phase |
|---|---|---|---|---|---|
| 1 | `feat(operacion): placaTolerante pure function + 6 unit tests` | feat | operacion | NEW placaTolerante.ts, NEW placaTolerante.test.ts | RED (U1..U6 fail) → GREEN |
| 2 | `feat(operacion): useCotizacion canonical Zod discriminated union + 6 hook tests` | feat | operacion | REWRITE useCotizacion.ts, UPDATE useCotizacion.test.ts | RED (3 new tests fail with old schema) → GREEN (migrate 3 + add 3) |
| 3 | `feat(operacion): CotizacionPanel presentational component + 4 tests` | feat | operacion | NEW CotizacionPanel.tsx, NEW CotizacionPanel.test.tsx | RED (4 tests fail) → GREEN |
| 4 | `refactor(operacion): SalidaPanel consume CotizacionPanel + canonical schema` | refactor | operacion | UPDATE SalidaPanel.tsx, UPDATE SalidaPanel.test.tsx | RED (4 tests fail with old assertions) → GREEN (canonical assertions) |
| 5 | `feat(i18n): migrate operacion.json cotizar.* keys to canonical schema` | feat | operacion | UPDATE operacion.json | Mechanical key migration; tests already migrated in commit 4 |
| 6 | `feat(operacion): per-file coverage thresholds for placaTolerante + useCotizacion + CotizacionPanel` | feat | operacion | UPDATE vitest.config.ts, UPDATE constants.ts | Gate enforcement |
| 7 | `chore(operacion): formatCOP reuse + useCountdown integration verified` | chore | operacion | (verification commit — no functional change) | `git grep` confirms no copy-paste |
| 8 | `docs(operacion): apply-progress.md + verify-report.md seed` | docs | operacion | NEW `openspec/changes/fase-7-1-busqueda-tolerante-cotizacion/apply-progress.md` | Apply-phase artifact |

### 8.3 PR title + body

- **Title**: `feat(operacion): HU-F7.1 búsqueda tolerante y cotización + schema drift reconciliation`
- **Body**: Conventional Commits footer with `Refs: HU-F7.1`, `Refs: REQ-OPS-022..025`, `Closes: plan.md:1656-1697`. Bullet list of the 11 T/R work units. Rollback plan: revert the single commit (`feature/hu-f7-1-...` → `dev`), no DB migration, no backend change, no other consumer depends on `CotizacionPanel` / `placaTolerante` until HU-F7.2 lands.

### 8.4 Verification gate (pre-merge)

- [ ] `git diff dev..feature/hu-f7-1-...` ≤ 800 LOC
- [ ] `pnpm --filter electron-sucursal lint` exits 0
- [ ] `pnpm --filter electron-sucursal typecheck` exits 0
- [ ] `pnpm --filter electron-sucursal test:coverage` exits 0 with all per-file thresholds met
- [ ] `pnpm --filter electron-sucursal test -- --run -t "WCAG"` (axe-core on `<CotizacionPanel />`) exits 0 violations
- [ ] `gh pr merge --squash --body-file` produces a squash commit with no `Co-authored-by` AI trailer

### 8.5 Post-merge (per AGENTS.md gitflow + override rule 2026-09-17)

1. `git checkout dev` + `git merge --ff-only feature/hu-f7-1-busqueda-tolerante-cotizacion` (or `--no-ff` if not direct descendant).
2. `git push origin dev`.
3. `git branch -d feature/hu-f7-1-busqueda-tolerante-cotizacion` + `git push origin --delete feature/hu-f7-1-busqueda-tolerante-cotizacion`.
4. Vite cache invalidation: kill port 5173 + restart with `--force` per AGENTS.md.
5. Engram `mem_save` of the canonical cotizar hook + `placaTolerante` decisions (post-merge convention).

## 9. Success criteria

1. `buscarIngresoTolerante('ABC12O')` returns `{kind: 'found', uuid_ingreso: 'X', placaReal: 'ABC120', varianteUsada: 'ABC12O'}` against a backend with the matching active ingreso.
2. `buscarIngresoTolerante('ABC124')` returns `{kind: 'none', placaProbada: 'ABC124'}` when no variant matches.
3. `buscarIngresoTolerante('OBC113')` (two confusables) returns `{kind: 'found', placaReal: '0BC113'}` when the underlying ingreso exists.
4. `useCotizacion(uuid)` polls `GET /operacion/cotizar?uuid_ingreso=uuid` at 1000ms cadence while the panel is mounted.
5. `useCotizacion(null)` issues no fetch (SWR key is `null`).
6. `<CotizacionPanel data={...} />` renders the canonical `<dl>` with `formatCOP` output `"$ 50.000"` for `{total: 50000}`.
7. Countdown turns `text-destructive` + `<AlertTriangle />` when `secondsLeft < 120`.
8. `cobrar === false` renders the mensualidad banner and short-circuits the breakdown.
9. `useCotizacion` returns `{error: ParkosHttpError(500)}` cleanly when the backend returns `iva_no_configurado` — no throw, no crash.
10. 401 → `useAuthStore.clear()` + `parkos:auth:cleared` event (preserved invariant from current `useCotizacion.ts:96-105`).
11. `vitest run --coverage` meets all 8 per-file thresholds (5 existing + 3 new in R6).
12. `axe-core` reports 0 violations on `<CotizacionPanel />` (WCAG 2.1 AA).
13. `pnpm typecheck`, `pnpm lint`, `pnpm test` exit 0 across the full `electron-sucursal` workspace.

## 10. Out of scope (re-iterated for emphasis)

- HU-F7.2 (registrar salida) — separate change.
- HU-F7.3 (tiquetes CU-15S + CU-15SM) — separate change.
- KD-IVA `impuestos.IVA` seeding — HU-F14.2 Parte II.
- Server-side placa tolerance variant endpoint — Path 1 client-side per F6.1 precedent.
- Mensualidad resolution server-side refactor — `resolve_active_subscription_for_exit` stays untouched.
- Release branch + tag — post-merge operational, not PR scope.
- Vite cache invalidation post-merge — handled by AGENTS.md script.

## 11. Relevant files (canonical pointers)

**OpenSpec / plan / spec**:
- `openspec/changes/fase-7-1-busqueda-tolerante-cotizacion/proposal.md` (this file)
- `openspec/changes/fase-7-1-busqueda-tolerante-cotizacion/exploration.md` (sdd-explore phase)
- `openspec/changes/fase-7-1-busqueda-tolerante-cotizacion/specs/operacion-cotizar/spec.md` (sdd-spec phase)
- `openspec/changes/fase-7-1-busqueda-tolerante-cotizacion/design.md` (sdd-design phase)
- `openspec/changes/fase-7-1-busqueda-tolerante-cotizacion/tasks.md` (sdd-tasks phase)
- `openspec/changes/fase-7-1-busqueda-tolerante-cotizacion/apply-progress.md` (sdd-apply phase)
- `openspec/changes/fase-7-1-busqueda-tolerante-cotizacion/verify-report.md` (sdd-verify phase)
- `plan.md` lines 1656-1697 (F7.1 block) + 7427-7461 (F1.8 cotizar wire contract)
- `openspec/specs/operations/spec.md` lines 441-502 (REQ-OPS-022..025 canonical)
- `openspec/specs/operacion.md` (F6.1 redirect-on-409 precedent)

**Archive precedents**:
- `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/{proposal,tasks}.md` (canonical cotizar schema)
- `openspec/changes/archive/2026-09-17-fase-6-1-flujo-ingreso/{design,tasks,verify-report}.md` (Path 1 client-side simplification)
- `openspec/changes/archive/2026-09-17-fase-4-1-deteccion-tipo-vehiculo/{proposal,tasks}.md` (F4.1 strict detector + DEC-SUC-22 split precedent)
- `openspec/changes/archive/2026-09-17-fase-4-2-tarifas-vigentes/{design,tasks}.md` (SWR hook + `formatCOP` reuse precedent)

**Frontend source**:
- `apps/electron-sucursal/src/lib/validation/placa.ts` (F4.1 strict detector — DEC-SUC-22 reference)
- `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts` (DRIFTED — current impl)
- `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` (DRIFTED `<dl>`)
- `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` (F3.2 reusable countdown)
- `apps/electron-sucursal/src/features/caja/lib/format.ts` (F3.3 `formatCOP`)
- `apps/electron-sucursal/src/features/operacion/constants.ts` (F4.3 refresh interval precedent)
- `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (drifted `cotizar.*` keys)
- `apps/electron-sucursal/vitest.config.ts` (per-file thresholds precedent)

**Files NOT touched (deliberate)**:
- `apps/electron-sucursal/src/features/operacion/api/ingresoApi.ts` (F6.1 — reused via `getIngresosByPlaca`)
- `apps/electron-sucursal/src/features/operacion/hooks/useIngresoActivo.ts` (F6.1 — `buscarIngresoTolerante` composes it)
- `apps/electron-sucursal/src/store/dashboardDrawerStore.ts` (F6.1 — REQ-OPS-138 single-drawer)
- `apps/electron-sucursal/src/lib/validation/placa.ts` (F4.1 — DEC-SUC-22 mandates separation)
- `backend/**` (no backend changes; F1.8 already ships the canonical cotizar endpoint)

## 12. Next steps

1. **sdd-spec** (`fase-7-1-busqueda-tolerante-cotizacion`): author the delta spec against `openspec/specs/operations/spec.md` (add `REQ-OPS-022b` client-side cotizar consumer requirement + 4 scenarios mirroring REQ-OPS-022..025 acceptance). The schema drift reconciliation is captured as a `MUST` requirement that `CotizacionPanel` consumes the canonical discriminated union. New requirement: `REQ-OPS-130` (or next free number) — `CotizacionPanel` semantic `<dl>` + countdown UX.
2. **sdd-design**: technical design for `buscarIngresoTolerante` variant algorithm + `<CotizacionPanel />` render branches + the `formatCOP` direct import. Cite F6.1 Path 1 precedent verbatim.
3. **sdd-tasks**: 8-commit plan from §8.2 mapped to T-HU-F7.1-1..N task IDs with RED/GREEN/REFACTOR phases per commit.
4. **sdd-apply**: implement + verify + merge to `dev` per AGENTS.md gitflow + override rule.
5. **sdd-verify**: run verification per §8.4 success criteria; produce `verify-report.md`.
6. **sdd-archive**: sync delta specs to `openspec/specs/operations/spec.md` (canonical), archive the change folder.
