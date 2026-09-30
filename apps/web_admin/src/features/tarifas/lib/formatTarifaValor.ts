/**
 * `formatTarifaValor` — display-only formatter for tarifa amounts.
 *
 * WHY
 * ---
 * The backend serializes `tarifas_sucursal.valor` (and
 * `valor_plena`) from `NUMERIC(18,4)`, so the wire always carries four
 * decimals as a string: `"1000.0000"`. Rendering that string verbatim
 * in the admin table shows `1000.0000`, which reads as a fractional
 * amount when the operator priced the tarifa in whole pesos.
 *
 * This helper is PRESENTATION ONLY. It never touches the wire format,
 * the `TarifaForm` inputs (`type="number"` cannot hold a thousands
 * separator), the schemas, or the request payload. The stored value
 * keeps its four decimals; only the table cell is formatted.
 *
 * es-CO grouping: `1.000`, `10.000`, `1.000.000`. Rounding to zero
 * fraction digits is intentional — a tarifa with a real fractional
 * amount (e.g. `"1500.5000"`) rounds half-up per
 * `Intl.NumberFormat` default, and the exact amount stays available in
 * the edit modal and the version history.
 */
const TARIFA_FORMAT = new Intl.NumberFormat('es-CO', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

export const TARIFA_VACIO = '—';

/**
 * Format a wire value (`string | null`) for table display.
 *
 * - `null` / `undefined` / `''` → `'—'` (the existing empty marker)
 * - non-numeric garbage → the raw string, so a malformed value is
 *   visible to the operator instead of being silently swallowed
 * - numeric → thousands-grouped, zero fraction digits
 */
export function formatTarifaValor(valor: string | null | undefined): string {
  if (valor === null || valor === undefined || valor === '') return TARIFA_VACIO;
  const n = Number(valor);
  if (!Number.isFinite(n)) return valor;
  return TARIFA_FORMAT.format(n);
}
