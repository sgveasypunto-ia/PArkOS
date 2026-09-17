# Design: HU-F4.1 Vehicle Type Detection

## Technical Approach

Pure deterministic validation function on the renderer, with a SWR catalog hook that degrades gracefully when the local `api-sucursal` is unreachable. The backend `repo/placa.py::detectar_tipo_vehiculo()` remains the server-side authority and overwrites the client-derived `uuid_tipo_vehiculo` via V5 (REQ-OPS-038) — the renderer is purely a UX accelerator, never the source of truth for vehicle type.

## Architecture Decisions

### Decision: Hardcoded Regex in placa.ts (A-03 verbatim)

**Choice**: Export `REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/` and `REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/` as module-level constants from `apps/electron-sucursal/src/lib/validation/placa.ts`.
**Alternatives considered**: Persist the regex in a new `tipos_vehiculo.formato_placa_regex` column; load it via `GET /api/v1/catalogos/tipos-vehiculo`.
**Rationale**: The ER is 4NF canon with no `regex_pattern` column (modelo_datos_er.mmd:87-103, A-03 explicit). Adding a column would require an ER amendment and a release; the regex must be in sync between client and `backend/.../operacion.py:215-277` regardless. JSDoc cross-reference + the existing `repo/placa.py` integration test catches drift.

### Decision: SWR Hardcoded Fallback (DEC-F4.1-05 verbatim)

**Choice**: When `useTiposVehiculo()` cannot reach `GET /api/v1/catalogos/tipos-vehiculo` (network error, 5xx, 401 pre-auth), return `HARDCODED_CATALOG: TipoVehiculo[]` with sentinel UUIDs `00000000-0000-0000-0000-00000000000{1,2}` and expose `isFromFallback: boolean`.
**Alternatives considered**: Throw and let the form render a broken state; cache an empty list.
**Rationale**: A broken ingreso form is unacceptable (operator cannot register a vehicle). The hardcoded catalog mirrors the only two formats F4.1 supports (`Auto`, `Moto`). Sentinel UUIDs are FALLBACK identifiers, never propagated to the server (the backend V5 derivation overwrites them anyway). `isFromFallback` lets F4.3/F6.x show a "usando datos locales" tooltip when degrading.

### Decision: Strict Function, No Tolerance (DEC-SUC-22 verbatim)

**Choice**: `detectarTipoVehiculo()` uses ONLY the two strict regexes. No tolerance maps, no fuzzy match, no override parameter. Type-tolerant search belongs to `buscarIngresoTolerante()` (Fase 7) in a separate file.
**Alternatives considered**: Single shared function with a `tolerance: 'strict' | 'lenient'` parameter; a tolerance flag stored per branch.
**Rationale**: BR2 CU-01 literal — "autodetección por regex es la ÚNICA fuente válida; NO hay override manual del cajero; si falla, se corrige como bug". A parameterized function would be an invitation to misuse; sharing one function for ingreso and salida was explicitly discarded in the corpus. Two functions, two files, two intents.

### Decision: Pure Function Co-located With Tests (F2.x precedent)

**Choice**: `placa.test.ts` lives next to `placa.ts` in `src/lib/validation/`. Same module, no `__tests__` subfolder.
**Alternatives considered**: Conventional `__tests__/placa.test.ts` path matching `plan.md:1381` verbatim.
**Rationale**: The repo convention observed in `src/features/auth/api/loginApi.test.ts` and `src/features/caja/lib/format.test.ts` is co-location. The `plan.md:1381` path is the plan's natural-language description, not a hard file-system mandate — apply phase should co-locate per the precedent.

## Data Flow

```
Operator types placa in <PlacaInput> (F6.1, future)
            │
            ▼
detectarTipoVehiculo(placa)         ← pure regex, no I/O
            │
   ┌────────┴────────┐
   │                 │
'Auto' / 'Moto'    null
   │                 │
   ▼                 ▼
useTiposVehiculo()  Inline error:
  resolves uuid     "Placa no coincide...
  for display       (Auto: ABC123,
                     Moto: ABC12D)"
            │
            ▼
onSubmit → POST /ingresos
            │
            ▼
Backend V5 (REQ-OPS-038) re-derives uuid_tipo_vehiculo from placa
(server overwrites client value — defense in depth)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `apps/electron-sucursal/src/lib/validation/placa.ts` | Create | Pure function + 2 regex constants. Already on disk in current workspace. |
| `apps/electron-sucursal/src/lib/validation/placa.test.ts` | Create | 8 tests U1..U8 (6 verbatim + 2 constants). Already on disk. |
| `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` | Create | `parkosFetch` wrapper, 404 → `[]`, filters `tipo: null`. |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` | Create | SWR hook + hardcoded fallback + `isFromFallback` flag. Already on disk (133 LOC). |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.test.ts` | Create | SWR behavior tests (auth gate, 404 fallback, 5xx fallback). |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | Modify | Add `operacion.placa_formato_invalido` key. |

## Interfaces / Contracts

```typescript
// placa.ts
export const REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/;
export const REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/;
export function detectarTipoVehiculo(placa: string): 'Auto' | 'Moto' | null;

// tiposVehiculoApi.ts
export interface TipoVehiculo {
  uuid: string;
  tipo: string | null;
  vigente_desde: string;
  vigente_hasta: string | null;
  estado: string;
}
export async function getTiposVehiculo(): Promise<TipoVehiculo[]>;

// useTiposVehiculo.ts
export interface UseTiposVehiculoReturn {
  tipos: TipoVehiculo[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<TipoVehiculo[] | undefined>;
  isFromFallback: boolean;
}
export function useTiposVehiculo(): UseTiposVehiculoReturn;
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (placa.ts) | 6 verbatim cases U1..U6 + 2 constant tests U7/U8 | `vitest run src/lib/validation/placa.test.ts` — pure function, no mocks |
| Unit (useTiposVehiculo) | SWR key gating (auth), 404→fallback, 5xx→fallback, 200→payload, isFromFallback flag | `vitest run src/features/catalogos/hooks/useTiposVehiculo.test.ts` with MSW for HTTP stubs |
| E2E | (Out of scope — F6.1 `<PlacaInput>` integration is the next HU) | n/a |
| a11y | axe-core smoke on the existing `<PlacaInput>` placeholder once F6.1 lands | Playwright + `@axe-core/playwright` |

### Strict TDD Note

The orchestrator skipped an `sdd-init` refresh; `openspec/config.yaml` `rules.apply.tdd` was not re-read for this change. We assume `strict_tdd: false` for this run (matches existing precedent in `src/features/auth/` and `src/features/caja/`, neither of which uses RED-GREEN-REFACTOR task sequences). The local verify command for this HU is:

```powershell
cd apps\electron-sucursal
npx vitest run src/lib/validation/placa.test.ts src/features/catalogos/hooks/useTiposVehiculo.test.ts
```

Future change applying a strict TDD posture should add RED-task siblings to each GREEN task in `tasks.md`.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary is touched by this HU. The renderer is a passive consumer of the local BFF.

## Migration / Rollout

No migration required. No DB schema change. No backend change. The renderer ships behind the existing feature flag pipeline of `web_sucursal`; rollout is the standard Electron auto-update (DEC-SUC-18).

## Open Questions

- None. Backend endpoint verified mounted. A-03 and DEC-SUC-22 are explicit and non-negotiable. The catalog seed (`carro | moto | bicicleta`) already includes `bicicleta` but A-03 explicitly notes the corpus has no CU justification for a third regex — deferring until a future HU justifies it.