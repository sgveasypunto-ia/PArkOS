# Design: HU-F7.1 — Búsqueda tolerante y cotización (CU-02)

> **Change**: `fase-7-1-busqueda-tolerante-cotizacion`
> **Phase**: design (sdd-design)
> **Status**: ready for `sdd-tasks`
> **Inputs read**: `proposal.md` §1..§12 (ratified 2026-09-19); `specs/operations.md` REQ-OPS-143..151 (delta spec, ratified); `backend/.../schemas/operacion.py:137-201` (canonical `CotizarResponse` discriminated union — note: line range 251-263 cited in proposal is the **actual** schema range is 137-201 per current repo state; verbatim schema captured below); `apps/electron-sucursal/src/lib/validation/placa.ts:1-83` (F4.1 strict detector — DEC-SUC-22 separation precedent); `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts:1-114` (current DRIFTED impl — 6-field flat schema, target of R1); `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx:1-196` (current DRIFTED `<dl>` at lines 152-163, target of R2); `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts:1-67` (F3.2 reusable drift-resistant countdown); `apps/electron-sucursal/src/features/caja/lib/format.ts:19-33` (F3.3 `formatCOP`); `apps/electron-sucursal/src/features/operacion/constants.ts:1-23` (F4.3 `OPERACION_REFRESH_INTERVAL_MS` precedent); `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json:58-66` (drifted `cotizar.*` keys); `apps/electron-sucursal/vitest.config.ts:1-46` (per-file coverage threshold precedent at lines 25-43); `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts:1-88` (REQ-OPS-138 single-drawer invariant); `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.ts:1-129` (F4.3 SWR + 401 logout pattern precedent); `apps/electron-sucursal/src/features/operacion/hooks/useIngresoActivo.ts:1-112` (F6.1 SWR fetcher-closure precedent); `openspec/changes/archive/2026-09-17-fase-6-1-flujo-ingreso/design.md:13-17` (Decision Path 1 — client-side composition, zero backend change); `openspec/changes/archive/2026-09-17-fase-4-1-deteccion-tipo-vehiculo/proposal.md:17` (DEC-SUC-22 split precedent — strict detector in `placa.ts`, tolerant in a separate file).
> **Skills loaded**: `sdd-design`, `_shared/sdd-phase-common`, `react`, `shadcn`.

## Technical Approach

This design operationalizes the ratified proposal: F7.1 ships (a) a pure
`placaTolerante.ts` (DEC-SUC-22 mandate — separate file from `placa.ts`)
that generates bounded tolerance variants client-side and walks them
through the existing F1.6 `GET /operacion/ingresos?placa=X` endpoint
(Path 1 precedent per F6.1 design.md:13-17 — zero backend change);
(b) the rewritten `useCotizacion.ts` whose Zod discriminated union
mirrors the canonical F1.8 backend contract at
`backend/.../schemas/operacion.py:142-201` (`CotizarFacturacion` |
`CotizarMensualidad`, discriminator `cobrar`) — closing the schema
drift on the consumer side; (c) a pure presentational
`<CotizacionPanel />` (shadcn atomic-design leaf, parent owns SWR +
drawer) that renders a semantic `<dl>` for the fiscal breakdown OR a
mensualidad info banner when `cobrar === false`, with a 15-minute
countdown that turns `text-destructive` + `<AlertTriangle />` when
`secondsLeft < 120`. Schema reconciliation is in-place atomic (R1+R2+R3
+R4+R5+R6 in a single self-contained PR per proposal §3.2 — no
intermediate state where `SalidaPanel` renders against a stale schema).
The drift closes mechanically: 4 existing `SalidaPanel.test.tsx` tests
migrate to canonical schema mocks (assertions flip from
`'$'+x.toLocaleString('es-CO')` to `formatCOP(x)` literal `"$ 50.000"`),
3 NEW hook tests pin the canonical contract (rotación / mensualidad /
tiempo ≥ tarifa-plena), 6 NEW pure-function tests pin the placa
tolerance variant generation.

## Architecture Decisions

### Decision: `placaTolerante.ts` lives in a separate file from `placa.ts`

**Choice**: `apps/electron-sucursal/src/lib/validation/placaTolerante.ts`
is a new, independent file exporting `buscarIngresoTolerante()`,
`generarVariantesTolerantes()`, and the `TOLERANCIA_PLACA` constant.
It does NOT import from `placa.ts`. The two files share no constants,
no regex, no utilities — separation is structural, not just naming.

**Rationale**: DEC-SUC-22 verbatim, cited in
`apps/electron-sucursal/src/lib/validation/placa.ts:5-8`:

> "DEC-SUC-22 verbatim: detección ESTRICTA, sin tolerancia de tipeo. La
> tolerancia `O↔0`/`I↔1`/`B↔8` pertenece a `buscarIngresoTolerante()`
> (Fase 7, CU-02/03 salida) — funciones DISTINTAS en archivos
> DISTINTOS. F4.1 sienta el precedent de separación clara entre las dos
> funciones."

The precedent was set by F4.1 proposal.md line 17:
> "The type-tolerant search `buscarIngresoTolerante()` (Fase 7,
> CU-02/03 salida) — lives in a separate function in a separate file
> by design (DEC-SUC-22)."

**Alternatives rejected**: (a) merge into `placa.ts` with a single
`STRICT_MODE` flag — would couple two semantically different operations
and require re-running `placa.test.ts` (F4.1) for tolerance changes;
(b) `placa/index.ts` barrel re-export — same coupling, no real
isolation; (c) shared utility module — would create a third file that
both depend on, violating the "funciones DISTINTAS en archivos
DISTINTOS" verbatim.

**Consequence**: `placaTolerante.ts` owns its own normalization
(`trim + uppercase + strip whitespace`) — duplicated 1-line verbatim
from `placa.ts:79`. The duplication is acceptable because DEC-SUC-22
mandates file-level isolation; refactoring into a shared helper would
re-couple the two functions. Coverage threshold (R6) ≥95/95/90 mirrors
F4.1's `placa.ts` threshold at `vitest.config.ts:25-30`.

### Decision: Client-side variant generation, no backend endpoint

**Choice**: `buscarIngresoTolerante(placa, getIngresosByPlaca)`
generates variants via the pure `generarVariantesTolerantes(placa)`
and iterates them through `getIngresosByPlaca(variante)` — composing
the existing F6.1 `useIngresoActivo` endpoint. No backend change.

**Rationale**: F6.1 design.md:13-17 verbatim (Path 1):

> "**Choice**: `GET /operacion/ingresos?placa=X` returns 0..N historical
> rows; `useIngresoActivo` SWR hook filters client-side to most-recent
> UUID and exposes `hasActive`. No backend change in F6.1."
> "**Rationale**: zero backend dependency keeps F6.1 a pure renderer
> change; placa cardinality is typically 0-3 rows so most-recent
> approximation is MVP-acceptable."

The same trade-off applies here: placa cardinality is 0-3 active rows
per sucursal, the variant search is bounded to ~10 variants realistically
(1 typo × 3 confusable classes per binary pair), and the operator handles
multi-candidate ambiguity via a `<RadioGroup>` candidate list
(`ToleranteResultado.kind: 'multiple'`) per plan.md:1668.

**Variants combinatorial bound** (proposal §3.1, REQ-OPS-151):
- Input placa = `[placa]` (1 entry, no-tolerance happy path).
- For each character position with a confusable class, emit one variant
  per binary replacement (`O↔0`, `I↔1`, `B↔8`). 6-char placa × 3 pairs × 2 = 18 single-position variants max.
- Two-position variants: ≤ 6 × 5 × 3 × 3 = 270 entries.
- **Bounded heuristic**: skip two-position variants if single-position
  variants exceed 50 entries (defensive — never triggers in practice
  for 6-char placas; prevents pathological inputs).
- **Worst-case ceiling**: 729 (3 confusables × 6 positions × 3 binary
  replacements × 13 deduplicated). Realistic case (1 typo): ≤13 variants.
- The hook early-exits on the first hit (line 39 of the algorithm in
  proposal §3.1), so realistic operator flows trigger ≤3 backend queries.

**Alternatives rejected**: (a) backend endpoint `GET /operacion/ingresos?placa_tolerante=X`
— requires coordinated backend PR (couples F7.1 to backend team
calendar), would still need rate-limiting (worst-case 729 queries),
and violates the established F6.1 Path 1 precedent; (b) PG `fuzzy_match_placa()`
function — requires PL/pgSQL + migration + AST walk (per REQ-OPS-025),
disproportionate to the renderer-side concern; (c) pure regex with
optional characters — does not produce the bounded variant list that
lets the operator see multi-candidate ambiguity.

### Decision: Discriminated union Zod schema mirrors backend Pydantic

**Choice**: `CotizacionSchema = z.discriminatedUnion('cobrar', [CotizarFacturacionSchema, CotizarMensualidadSchema])`
in `useCotizacion.ts`. Each variant mirrors the canonical backend
schema verbatim (DRY contract):

```typescript
// useCotizacion.ts (R1 rewrite)
export const CotizarFacturacionSchema = z.object({
  cobrar: z.literal(true),
  subtotal: z.number(),
  iva: z.number(),
  total: z.number(),
  tiempo_minutos: z.number(),            // T-HU-F1.8-7: NOT z.number().int()
  tarifa_uuid: z.string().uuid(),
  vigente_hasta: z.string(),              // ISO 8601 string from JSON
});

export const CotizarMensualidadSchema = z.object({
  cobrar: z.literal(false),
  motivo: z.literal('mensualidad_vigente'),
});

export const CotizacionSchema = z.discriminatedUnion('cobrar', [
  CotizarFacturacionSchema,
  CotizarMensualidadSchema,
]);

export type Cotizacion = z.infer<typeof CotizacionSchema>;
```

This mirrors `CotizarFacturacion` + `CotizarMensualidad` in
`backend/.../schemas/operacion.py:142-201` (the canonical F1.8 contract).

**Apply-time deviation T-HU-F1.8-7** (documented in backend
schema docstring lines 153-161): `tiempo_minutos` is typed
`z.number()` (NOT `z.number().int()`) because the PL/pgSQL function
computes `EXTRACT(EPOCH FROM (NOW() - fecha_ingreso)) / 60.0` which
returns a sub-second-precision `numeric` (e.g. `89.0025` for an
89-minute-old row). Postgres serializes via asyncpg jsonb bridge as
a Python `float`; the schema accepts `int | float`. The design's
original `int` typing was relaxed in the apply phase — F7.1 honors
that deviation.

**Rationale**: discriminated union on `cobrar` gives TS exhaustive
narrowing inside `CotizacionPanel`: `if (data.cobrar === true)` triggers
the full fiscal branch, `else` triggers the mensualidad banner — the
compiler enforces both paths are handled. Plain union (`z.union(...)`)
would not give this narrowing.

**Alternatives rejected**: (a) `z.union(...)` (no discriminator) —
loses TS narrowing, the component would need runtime type guards;
(b) hand-written `interface Cotizacion` — duplicates the Zod schema
in two places, drift risk per OD-3; (c) import the backend Pydantic
schema — impossible (Python ↔ TS boundary); (d) `z.number().int()` for
`tiempo_minutos` — would crash against the real wire value (89.0025
rejected), violating the canonical contract.

### Decision: `<CotizacionPanel />` is pure presentational, parent owns SWR + drawer

**Choice**: `<CotizacionPanel data={cotizacion} secondsLeft={n} onConfirmar={fn} onRecalcular={fn} />`
is a leaf in the `operacion/components/` tree. It owns:
- The semantic `<dl>` rendering for the fiscal breakdown
- The mensualidad info banner short-circuit (`data.cobrar === false`)
- The `useCountdown(15 * 60)` integration + red-threshold UX
- `formatCOP(value)` for monetary values

It does NOT own:
- SWR polling — `SalidaPanel` calls `useCotizacion(uuid_ingreso)` and
  passes the result as `data`
- Drawer state — `SalidaPanel` wires `onConfirmar` to
  `useDashboardDrawerStore.open('pago', pagoAnchorId)` (REQ-OPS-138
  single-drawer invariant)
- Auth — `SalidaPanel` reads `useAuthStore` (no token passed down)

**Rationale**: shadcn atomic-design mandates a leaf component is
pure (props in, JSX out). This matches the F4.3 `<OcupacionStrip />`
precedent (`operacion/components/OcupacionStrip.tsx` — also
presentational, parent owns SWR + auth). The pure-component boundary
makes `<CotizacionPanel />` trivially testable: pass mock props, assert
rendered JSX, no SWR/fetch mocks needed.

**Consequence**: `<CotizacionPanel />` MUST be wrapped in `React.memo`
with `data` / `secondsLeft` / `onConfirmar` / `onRecalcular` as prop
deps. The countdown re-renders 60×/min when `secondsLeft` decrements;
without memoization, the entire `SalidaPanel` re-renders, polluting
the F4.3 `useOcupacion` polling cadence (10s) and the F6.1 SWR cache.
`onConfirmar` / `onRecalcular` MUST be `useCallback`-wrapped in
`SalidaPanel` (line 104-106 already does this for `handleOpenPago`).

### Decision: `formatCOP` direct import — no copy of format logic

**Choice**: `<CotizacionPanel />` imports `formatCOP` from
`apps/electron-sucursal/src/features/caja/lib/format.ts:31`
(F3.3 shipped, tested verbatim at `format.test.ts:15-29`). No raw
`.toLocaleString('es-CO') + '$'` concatenation in this PR.

**Rationale**: `formatCOP(50000)` → `"$ 50.000"` (es-CO locale,
thousands separator `.`, no decimals for COP) — the canonical fixture
used by every test in this PR (e.g. literal `"$ 50.000"` in
`SalidaPanel.test.tsx` and `CotizacionPanel.test.tsx`). Copy-pasting
the format logic would create drift risk (es-CO locale change,
currency change) and violates the "REUSE not COPY" canon from the
AGENTS.md architectural principles.

**Enforcement**: REQ-OPS-147 mandates that an automated
`git grep -nE "toLocaleString\\('es-CO'\\)" apps/electron-sucursal/src/features/operacion/`
returns zero matches in the F7.1 PR. This grep runs in the verify
phase as part of the acceptance gate.

### Decision: `aria-live="polite"` + `role="alert"` when `secondsLeft < 120`

**Choice**: The countdown `<div>` inside `<CotizacionPanel />` carries
`aria-live="polite"` (RNF-022 WCAG 2.1 AA, screen reader announces
each tick). When `secondsLeft < 120` (2-minute threshold), the
`<div>` flips to `text-destructive` (shadcn semantic token
`--destructive`), renders `<AlertTriangle />` from `lucide-react`,
and sets `role="alert"` so screen readers interrupt the user
immediately when the threshold crosses.

**Rationale**: OD-2 ratified in proposal §7 — inline approach is
acceptable per the F4.2 `<TarifaBadge />` precedent (atomic-design
prefers primitives over heavier shadcn `<Alert>` DOM). The full
text "Cotización expira pronto — confirma o recalcula" appears in
a `<span>` next to the countdown for visible WCAG 2.1 AA contrast
(verified against existing F6.2 banner). At `secondsLeft === 0`,
the text flips to "Cotización expirada — recalculando…" and the
SWR re-fetch produces a fresh `vigente_hasta` that resets the
countdown.

**Test coverage**: 1 of 4 `CotizacionPanel.test.tsx` tests verifies
the red-threshold flip at `<120s` boundary with `aria-live` + `role`
assertions.

### Decision: Drift reconciliation in single atomic PR

**Choice**: R1+R2+R3+R4+R5+R6 ship as a single self-contained PR
(no intermediate state, no "audit + fix" split). Work units split
into 8 commits per proposal §8.2 commit plan.

**Rationale** (proposal §3.2 verbatim "WHY"):
> "The drift is mechanical (field rename + discriminated union). 4
> test files lose and regain coverage in one atomic commit. Splitting
> it would require 2 PRs touching the same files in sequence (CI
> re-run cost > atomic fix cost). `SalidaPanel.tsx` is on the hot
> dashboard path — any mid-state where SalidaPanel renders against an
> old schema while useCotizacion polls a new one would crash the
> operator flow."

The commit ordering matters and is enforced by strict TDD:
1. T1 RED → GREEN: `placaTolerante.ts` + 6 unit tests (commit 1)
2. R1+T2 RED → GREEN: `useCotizacion.ts` Zod rewrite + 3 migrated + 3 new hook tests (commit 2)
3. T3 RED → GREEN: `<CotizacionPanel />` + 4 component tests (commit 3)
4. R2+R4 RED → GREEN: `<SalidaPanel />` consumer migration + 4 test updates (commit 4)
5. R3: `operacion.json` i18n migration (commit 5, mechanical; tests migrated in commit 4)
6. R6: `vitest.config.ts` per-file thresholds (commit 6, gate enforcement)
7. chore: formatCOP reuse + useCountdown integration verified (commit 7, `git grep` no copy-paste)
8. docs: `apply-progress.md` + `verify-report.md` seed (commit 8)

Every commit compiles + passes tests independently (strict TDD).
No commit leaves an intermediate state where `SalidaPanel` would
crash against a stale schema.

## Data Flow

```
Operator types placa in <SalidaPanel /> form
  │
  ├─ Zod placaSchema.parse → "ABC12O" (5+ chars, normalized)
  │
  └─ form.handleSubmit(values)
       │
       ├─ buscarIngresoTolerante('ABC12O', getIngresosByPlaca)
       │    │
       │    ├─ generarVariantesTolerantes('ABC12O')
       │    │    └─ normalize + uppercase + strip whitespace
       │    │    └─ emit ['ABC12O', 'ABC120']   (1 confusable at pos 5)
       │    │
       │    └─ for each variante: getIngresosByPlaca(variante)
       │         │
       │         ├─ 'ABC12O' → [] (no match)
       │         ├─ 'ABC120' → [Ingreso] ← match!
       │         │
       │         └─ return { kind: 'found',
       │                       uuid_ingreso: 'X',
       │                       placaReal: 'ABC120',
       │                       varianteUsada: 'ABC12O' }
       │
       ├─ setState(uuid_ingreso: 'X') → triggers <CotizacionPanel /> mount
       │
       └─ useCotizacion('X') SWR hook polls GET /cotizar?uuid_ingreso=X
            │
            ├─ CotizacionSchema.parse(raw) — discriminated union on 'cobrar'
            │
            ├─ cobrar=true → { subtotal, iva, total, tiempo_minutos, tarifa_uuid, vigente_hasta }
            │     │
            │     └─ <CotizacionPanel data={cotizacion} secondsLeft={n} />
            │           │
            │           ├─ semantic <dl> with formatCOP(value)
            │           ├─ useCountdown(15 * 60) → secondsLeft
            │           ├─ if (secondsLeft < 120) → text-destructive + AlertTriangle + role=alert
            │           └─ <Button onClick={onConfirmar}>{t('operacion:cotizar.confirmar')}</Button>
            │
            └─ cobrar=false → { motivo: 'mensualidad_vigente' }
                  │
                  └─ <CotizacionPanel /> short-circuit → mensualidad info banner
                        └─ <Button onClick={onConfirmar}>{t('operacion:cotizar.mensualidad.accion')}</Button>
                              (forward to HU-F7.2 SalidaMensualidad POST)

onConfirmar (SalidaPanel handler):
  │
  └─ useDashboardDrawerStore.open('pago', pagoAnchorId)
       │           │
       │           └─ REQ-OPS-138 single-drawer: only 'pago' drawer visible
       │
       └─ <DrawerHost /> mounts <PagoSheet anchorId={pagoAnchorId} />
              │
              └─ HU-F7.2 POST /operacion/salidas (rotación)
                 OR
                 HU-F7.2 POST /operacion/salidas/mensualidad (mensualidad)
```

## File Changes

| File | Action | LOC est. | Description |
|---|---|---|---|
| `apps/electron-sucursal/src/lib/validation/placaTolerante.ts` | NEW | 90 | Pure `buscarIngresoTolerante` + `generarVariantesTolerantes` + `TOLERANCIA_PLACA` constant. DEC-SUC-22 JSDoc cites the F4.1 separation verbatim. |
| `apps/electron-sucursal/src/lib/validation/placaTolerante.test.ts` | NEW | 70 | 6 tests U1..U6 verbatim: U1 happy path, U2 confusable `ABC12O` → matches `ABC120`, U3 multi-position `0BC1I3` → matches `OBC113`, U4 none, U5 multiple candidates, U6 normalization. Mirrors `placa.test.ts` precedent. |
| `apps/electron-sucursal/src/features/operacion/components/CotizacionPanel.tsx` | NEW | 110 | Pure presentational. `<dl>` semantic breakdown, `<AlertTriangle />` countdown red-threshold, mensualidad short-circuit. `formatCOP` direct import from `features/caja/lib/format`. `React.memo` wrap. |
| `apps/electron-sucursal/src/features/operacion/components/CotizacionPanel.test.tsx` | NEW | 80 | 4 tests: rotación render with desglose, mensualidad render with banner, countdown red-threshold at `<120s`, click handlers fire. |
| `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts` | REWRITE | 130 | Canonical discriminated union Zod schema (R1). `refreshInterval: OPERACION_COTIZAR_REFRESH_INTERVAL_MS = 1_000`. `shouldRetryOnError` excludes 401/403/404. 401 → `useAuthStore.clear()` + `parkos:auth:cleared` event (preserved from current impl lines 96-105). AbortController with 5s timeout. |
| `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.test.ts` | UPDATE | 95 | 6 tests total: 3 migrated (C1 null key / C2 fetcher-closure / C3 401 logout) + 3 NEW (R5) — rotación / mensualidad / tiempo ≥ tarifa-plena. SWR mock with `vi.mock('swr')`. |
| `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` | UPDATE | 60 (delta) | Replace inline `<dl>` (lines 152-163) with `<CotizacionPanel />`. Add `buscarIngresoTolerante` glue on form submit. Keep `handleOpenPago` (line 104-106) + `pagoAnchorId` (line 78) + `useDashboardDrawerStore` wiring (line 76-77) intact. Replace `$X.toLocaleString('es-CO')` (lines 156/158/161) with `formatCOP()`. |
| `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.test.tsx` | UPDATE | 30 (delta) | 4 existing tests migrated to canonical schema mocks (R4). Assertions on `formatCOP` output (literal `"$ 50.000"`). REQ-OPS-132 fetcher-closure + REQ-OPS-138 single-drawer invariants preserved. |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | UPDATE | 18 (delta) | DELETE 2 keys (`cotizar.base`, `cotizar.fraccion`), UPDATE 1 (`cotizar.minutos` rebind), ADD 18 keys per proposal §2.1 R3. Net +17 keys. |
| `apps/electron-sucursal/src/features/operacion/constants.ts` | UPDATE | 5 (delta) | Add `OPERACION_COTIZAR_REFRESH_INTERVAL_MS = 1_000` + `OPERACION_COTIZAR_TIMEOUT_MS = 5_000`. Existing 2 constants stay. |
| `apps/electron-sucursal/vitest.config.ts` | UPDATE | 22 (delta) | Add 3 per-file threshold entries (R6) per F4.x precedent at lines 25-43. |
| **Total new LOC** | | **+575** | |
| **Total updated LOC (deltas)** | | **+360** | |
| **Grand total LOC** | | **~935** | **Exceeds 800 LOC budget** — flagged for `size:exception`. |

## Interfaces / Contracts

### `placaTolerante.ts` API

```typescript
/**
 * Tolerance map for DEC-SUC-22 confusable characters.
 * Exported as a `const` (not enum) for direct equality-test in tests.
 *
 * DEC-SUC-22 verbatim: "La tolerancia `O↔0`/`I↔1`/`B↔8` pertenece a
 * `buscarIngresoTolerante()` — funciones DISTINTAS en archivos DISTINTOS."
 *
 * This constant lives ONLY in `placaTolerante.ts` — `placa.ts` does
 * NOT import it (separation mandate).
 */
export const TOLERANCIA_PLACA = {
  'O': '0', '0': 'O',
  'I': '1', '1': 'I',
  'B': '8', '8': 'B',
} as const;

export type ToleranteResultado =
  | { kind: 'found'; uuid_ingreso: string; placaReal: string; varianteUsada: string }
  | { kind: 'none'; placaProbada: string }
  | { kind: 'multiple'; candidatos: Array<{ uuid_ingreso: string; placaReal: string }> };

/**
 * Pure deterministic variant generator. Same input → same output (no I/O).
 * Returns the input placa as the first entry (no-tolerance happy path),
 * then single-position variants, then (if single-position ≤50) two-position
 * variants. Worst-case ceiling: 729. Realistic (1 typo): ≤13.
 */
export function generarVariantesTolerantes(placa: string): readonly string[];

/**
 * Async resolver. Iterates variants through `getIngresosByPlaca(variante)`.
 * Early-exits on the first variant with ≥1 result (single match → 'found').
 * If multiple variants each produce ≥1 result → returns 'multiple' with
 * the union of candidates (deduplicated by uuid_ingreso).
 * If all variants return 0 → returns 'none' with the original placa.
 */
export async function buscarIngresoTolerante(
  placa: string,
  getIngresosByPlaca: (placa: string) => Promise<readonly Ingreso[]>,
): Promise<ToleranteResultado>;
```

### `useCotizacion.ts` canonical Zod schema

```typescript
import { z } from 'zod';

/**
 * F1.8 canonical discriminated union (REQ-OPS-022..025).
 * Mirrors backend `CotizarFacturacion` + `CotizarMensualidad` at
 * `backend/.../schemas/operacion.py:142-201`.
 *
 * Apply-time deviation T-HU-F1.8-7: `tiempo_minutos` is `z.number()`
 * (NOT `z.number().int()`) because the PL/pgSQL function returns float
 * from `EXTRACT(EPOCH FROM ...)/60.0`. The Pydantic schema accepts
 * `int | float` for the same reason.
 */
export const CotizarFacturacionSchema = z.object({
  cobrar: z.literal(true),
  subtotal: z.number(),
  iva: z.number(),
  total: z.number(),
  tiempo_minutos: z.number(),
  tarifa_uuid: z.string().uuid(),
  vigente_hasta: z.string(),
});

export const CotizarMensualidadSchema = z.object({
  cobrar: z.literal(false),
  motivo: z.literal('mensualidad_vigente'),
});

export const CotizacionSchema = z.discriminatedUnion('cobrar', [
  CotizarFacturacionSchema,
  CotizarMensualidadSchema,
]);

export type Cotizacion = z.infer<typeof CotizacionSchema>;
export type CotizarFacturacion = z.infer<typeof CotizarFacturacionSchema>;
export type CotizarMensualidad = z.infer<typeof CotizarMensualidadSchema>;
```

### `CotizacionPanel.tsx` prop signature

```typescript
import type { Cotizacion } from '../hooks/useCotizacion';

export interface CotizacionPanelProps {
  /** Canonical discriminated union (REQ-OPS-143). `cobrar === false` short-circuits to mensualidad banner. */
  data: Cotizacion;
  /** Seconds until `vigente_hasta` — from `useCountdown(15 * 60)`. <120 flips to destructive. */
  secondsLeft: number;
  /**
   * Parent wires to `useDashboardDrawerStore.open('pago', pagoAnchorId)`
   * for rotación, or to HU-F7.2 mensualidad forwarder for `cobrar === false`.
   * REQ-OPS-138 single-drawer invariant preserved.
   */
  onConfirmar: () => void;
  /** Parent wires to SWR `mutate()` for manual re-fetch. */
  onRecalcular: () => void;
}

/**
 * Pure presentational. Wrapped in `React.memo` with the four prop deps.
 * Uses shadcn `<Card>`, semantic `<dl>`, `<AlertTriangle />` from lucide-react,
 * `formatCOP` from `features/caja/lib/format`.
 */
export const CotizacionPanel = React.memo(function CotizacionPanel({
  data,
  secondsLeft,
  onConfirmar,
  onRecalcular,
}: CotizacionPanelProps): JSX.Element {
  // ... two render paths: rotación (dl) | mensualidad (banner)
});
```

## Testing Strategy

| Layer | What | How |
|---|---|---|
| **Unit (placaTolerante.ts)** | U1..U6 verbatim per proposal §2.1 T1: U1 happy path no typo → `kind: 'found'`, U2 confusable `ABC12O` → matches `ABC120`, U3 multi-position `0BC1I3` → matches `OBC113`, U4 none (`ABC124`), U5 multiple (3 candidates → `kind: 'multiple'`), U6 normalization (`  abc12o  ` → matches `ABC120`). Plus bounded count assertions (REQ-OPS-151). | vitest + happy-dom; 6 tests; threshold ≥95/95/90 per R6. |
| **Hook (useCotizacion.ts)** | 3 migrated (C1 null key no fetch / C2 fetcher-closure / C3 401 → useAuthStore.clear) + 3 NEW (R5) — rotación / mensualidad / tiempo ≥ tarifa-plena. SWR key asserted as `/operacion/cotizar?uuid_ingreso=X` (not the full cache key string). 401 logout invariant preserved verbatim from current impl. | vitest + SWR mock (`vi.mock('swr')`); threshold ≥90/90/85 per R6. |
| **Component (CotizacionPanel)** | 4 tests: (1) rotación render with full desglose + `formatCOP(50000) === '$ 50.000'` literal assertion, (2) mensualidad render with banner (no `<dl>`), (3) countdown red-threshold at `<120s` with `role="alert"` + `text-destructive` class, (4) `onConfirmar` / `onRecalcular` click handlers fire. | vitest + Testing Library + axe-core WCAG 2.1 AA gate; threshold ≥90/90/85 per R6. |
| **Migrated (SalidaPanel.test.tsx)** | 4 existing tests migrated to canonical schema mocks (R4). Field rename `base_cop`/`fraccion_cop` → `subtotal`/`iva`/`total`. Assertions on `formatCOP(x)` literal `"$ 50.000"` instead of `'$'+x.toLocaleString('es-CO')`. REQ-OPS-138 single-drawer invariant preserved (`open('pago', anchorId)` still fires on confirm). REQ-OPS-132 fetcher-closure preserved. | vitest + Testing Library. |
| **E2E (verify phase)** | F7.1 is renderer-only — e2e scope per `plan.md:1787-1816` is HU-F7.2 only. F7.1 verify phase runs `vitest run --coverage` + `git grep` for `.toLocaleString('es-CO')` enforcement (REQ-OPS-147) + axe-core on `<CotizacionPanel />`. | n/a (no e2e in F7.1 scope). |

## Threat Matrix

N/A — F7.1 is renderer-only (React components + a pure function +
an SWR hook). No routing changes (existing `/` route serves the
operator dashboard), no shell commands, no subprocesses, no VCS/PR
automation (handled by AGENTS.md gitflow + override rule), no
executable-file classification, no process integration. The risk
surface is bounded to: (a) Zod parse crash if the backend wire shape
drifts again (mitigated by `CotizacionSchema.parse(raw)` surfacing a
typed error that the component renders as the `cotizar.errors.*`
banner — see REQ-OPS-148); (b) variant combinatorial explosion (mitigated
by the bounded heuristic and the early-exit at first hit — see R5
mitigation in proposal §6); (c) WCAG 2.1 AA violations on
`<CotizacionPanel />` (mitigated by `aria-live="polite"` + `role="alert"`
+ axe-core gate in the verify phase — see OD-2). All eight proposal §6
risks (R1..R8) carry specific mitigations already documented there;
this design does not introduce new threats.

## Migration / Rollout

No migration required. No DB schema change. No backend endpoint change.
No feature flag. The drift reconciliation is a pure renderer-side
consumer rewrite that closes against the canonical F1.8 contract that
has been live on `dev` since 2026-09-14 (REQ-OPS-022..025 in
`openspec/specs/operations/spec.md:441-502`).

Atomic merge to `dev` per gitflow override (2026-09-17):
```
git checkout dev
git merge --ff-only feature/hu-f7-1-busqueda-tolerante-cotizacion   # or --no-ff if not direct descendant
git push origin dev
git branch -d feature/hu-f7-1-busqueda-tolerante-cotizacion
git push origin --delete feature/hu-f7-1-busqueda-tolerante-cotizacion
```

Post-merge Vite cache invalidation per AGENTS.md post-merge script
(kill port 5173 + restart with `--force`).

No release branch + tag in F7.1 PR scope (per proposal §2.2).

## Open Questions

None — all three open decisions (OD-1, OD-2, OD-3) ratified in
proposal §7:
- **OD-1**: `generarVariantesTolerantes` colocated in `placaTolerante.ts` as exported pure function (default proposal accepted; over-engineering to split into separate file rejected).
- **OD-2**: countdown red-threshold via inline `text-destructive` + `<AlertTriangle />` + `role="alert"` (default proposal accepted per F4.2 `<TarifaBadge />` atomic-design precedent).
- **OD-3**: `Cotizacion` props typed as `z.infer<typeof CotizacionSchema>` (default proposal accepted; hand-written interface drift risk rejected; F4.2 precedent verbatim).

## Review Workload Forecast

- **Total estimated LOC**: ~935 (575 new + 360 deltas).
- **800 LOC budget breach**: F7.1 forecast is +135 LOC over the proposal §4 budget. The breach is mechanical: 17 NEW tests (6 placaTolerante + 6 useCotizacion + 4 CotizacionPanel + 1 isolated) + 4 migrated test rewrites + 18 NEW i18n keys + 3 NEW per-file coverage thresholds. The "REUSE not COPY" canon prevents compressing further: `formatCOP` + `useCountdown` + `useIngresoActivo.getIngresosByPlaca` are direct imports with no copy logic added.
- **`size:exception` required**: YES — flagged at proposal §4 line 168 ("flagged for review at `size:exception` if final diff >800") and here in the design §Review Workload Forecast.
- **Delivery strategy**: `single-pr` (per proposal §8.1 — `delivery_strategy=single-pr` cache hit from session preflight Engram #1838). The forecast does not fit chained PRs cleanly because the drift reconciliation is atomic by construction (proposal §3.2 verbatim).
- **Decision needed before apply**: **YES** — user must ratify the `size:exception` for 935 LOC vs 800 budget. The gitflow override rule (2026-09-17) requires this to be reported in `tasks.md` and the apply phase is held until the user ratifies the exception (or splits into chained PRs per the `auto-chain` cache fallback).

## Cross-References

- **Proposal** (`openspec/changes/fase-7-1-busqueda-tolerante-cotizacion/proposal.md`): §3.1 Path 1 client-side, §3.2 in-place reconciliation, §3.3 prop signature, §3.4 `SalidaPanel` refactor — all operationalized by this design.
- **Spec delta** (`openspec/changes/fase-7-1-busqueda-tolerante-cotizacion/specs/operations.md`): REQ-OPS-143 (panel consumes canonical DU), REQ-OPS-144 (`buscarIngresoTolerante` + DEC-SUC-22 separation), REQ-OPS-145 (1s poll + 401 logout), REQ-OPS-146 (countdown red + `aria-live`), REQ-OPS-147 (`formatCOP` only), REQ-OPS-148 (iva_no_configurado banner), REQ-OPS-149 (10 tests total), REQ-OPS-150 (3 per-file thresholds), REQ-OPS-151 (variant generation bounds).
- **Canonical wire contract**: `openspec/specs/operations/spec.md:441-502` (REQ-OPS-022..025) + `backend/.../schemas/operacion.py:142-201` (`CotizarFacturacion` + `CotizarMensualidad` + `CotizarResponse` discriminator).
- **DEC-SUC-22 precedent**: `apps/electron-sucursal/src/lib/validation/placa.ts:5-8` (verbatim separation quote) + `openspec/changes/archive/2026-09-17-fase-4-1-deteccion-tipo-vehiculo/proposal.md:17`.
- **F6.1 Path 1 precedent**: `openspec/changes/archive/2026-09-17-fase-6-1-flujo-ingreso/design.md:13-17` (verbatim client-side composition quote).
- **Reuse targets**: `apps/electron-sucursal/src/features/caja/lib/format.ts:31` (`formatCOP`) + `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts:42-66` (`useCountdown`) + `apps/electron-sucursal/src/features/operacion/api/ingresoActivoApi.ts` (`getIngresosByPlaca`) + `apps/electron-sucursal/src/features/operacion/constants.ts:13` (refresh interval precedent).

(End of design.md — total ~330 lines)
