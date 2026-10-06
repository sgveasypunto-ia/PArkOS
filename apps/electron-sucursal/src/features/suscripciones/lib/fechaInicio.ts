/**
 * `fechaInicio.ts` — default coverage start date for the subscription sale.
 *
 * PT-3: the start date is "today" in Colombia (America/Bogota, UTC-5, no
 * DST), never the browser's local zone or a hardcoded date, so a sale made
 * at 20:00 Bogota (already tomorrow in UTC) still starts today. Mirrors the
 * backend `parkos_core.runtime.tiempo.hoy_bogota`.
 */
const bogotaDateFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Bogota',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

/** Returns `YYYY-MM-DD` for `now` as seen in Bogota. */
export function hoyBogotaISO(now: Date = new Date()): string {
  const parts = bogotaDateFormatter.formatToParts(now);
  const get = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((p) => p.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}
