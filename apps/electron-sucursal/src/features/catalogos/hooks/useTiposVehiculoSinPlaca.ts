/**
 * `useTiposVehiculoSinPlaca()` — filter `useTiposVehiculo()` to tipos
 * that have NO placa regex (REQ-OPS-196). Used by `<IngresoSinPlacaPanel>`
 * (HU-INGRESO-SIN-PLACA) to populate the `<Select>` for bici / patineta.
 *
 * Filters on the F4.1 `tipo` string (lowercase per canon):
 *   - Keep: `bicicleta`, `patineta`.
 *   - Exclude: `carro`, `moto` (those flow through `<PlacaInput>` —
 *     they have placa regex validation upstream).
 *
 * `isFromFallback` is propagated from `useTiposVehiculo()`: when the
 * API is down, `HARDCODED_CATALOG` only contains `{carro, moto}` (the
 * F4.1 sentinel UUIDs); the filter result is then empty and
 * `<IngresoSinPlacaPanel>` renders the documented degraded-UX message
 * "Esta sucursal no admite ingresos sin placa" (REQ-OPS-196 scenario 2).
 *
 * The 5-minute `dedupingInterval` is INHERITED from `useTiposVehiculo`
 * (F4.1, DEC-F4.1-04) — both hooks share the same SWR key, so the
 * catalog refetch fires at most once across both consumers.
 */
import {
  useTiposVehiculo,
  type UseTiposVehiculoReturn,
} from './useTiposVehiculo';

/**
 * Tipo string values that participate in the no-placa flow. Kept as a
 * const-tuple so the compiler enforces membership — if a new tipo is
 * added later (e.g. `scooter`), the filter must be updated explicitly.
 */
const TIPOS_SIN_PLACA = ['bicicleta', 'patineta'] as const;

export type TipoSinPlaca = (typeof TIPOS_SIN_PLACA)[number];

/**
 * `useTiposVehiculoSinPlaca()` — typed wrapper over `useTiposVehiculo()`
 * that returns ONLY the tipos that admit ingresos sin placa
 * (bicicleta, patineta). The return shape mirrors `UseTiposVehiculoReturn`
 * so the caller can drop in either hook transparently.
 *
 * Purity: this hook has no local state and no SWR cache of its own —
 * it is a pure projection over `useTiposVehiculo()`. Filter cost is
 * `O(n)` over the catalog (4 tipos maximum), so the projection adds
 * negligible overhead.
 */
export function useTiposVehiculoSinPlaca(): UseTiposVehiculoReturn {
  const full = useTiposVehiculo();
  const filtered = full.tipos.filter(
    (t): t is typeof full.tipos[number] =>
      t.tipo !== null && (TIPOS_SIN_PLACA as readonly string[]).includes(t.tipo),
  );
  return {
    ...full,
    tipos: filtered,
  };
}
