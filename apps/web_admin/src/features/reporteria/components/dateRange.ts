/**
 * `dateRange.ts` — non-component utilities for the reporteria date
 * range picker. Kept in its own file so ``DateRangePicker.tsx`` only
 * exports components (eslint-plugin-react-refresh / fast-refresh
 * warning otherwise).
 */
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export interface DateRange {
  fecha_desde: string; // YYYY-MM-DD (UTC date, inclusive)
  fecha_hasta: string; // YYYY-MM-DD (UTC date, inclusive)
}

export function todayISO(): string {
  // Date.toISOString slices at UTC midnight; that's the same anchor
  // the backend uses for ``func.date(Ingreso.created_at)``, so the
  // picker's "today" is consistent with what /admin/reporteria/operacional
  // returns.
  return new Date().toISOString().slice(0, 10);
}

export function offsetISO(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function startOfMonthISO(): string {
  const d = new Date();
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-01`;
}

export function isValidDate(value: string): boolean {
  return ISO_DATE.test(value) && !Number.isNaN(new Date(value).getTime());
}

export function defaultRange(): DateRange {
  return { fecha_desde: startOfMonthISO(), fecha_hasta: todayISO() };
}

/**
 * Parses a backend timestamp and formats it as LOCAL (browser timezone,
 * e.g. America/Bogota for this app) wall-clock "YYYY-MM-DD HH:mm:ss".
 *
 * Bug fixed here (qa-reporteria-operacional batch, 2026-10-02): the
 * backend serializes datetimes as naive UTC (no trailing "Z", e.g.
 * "2026-10-02T23:26:30.350129"). Per the ECMAScript Date Time String
 * spec, a date-TIME string WITHOUT a timezone designator is parsed as
 * LOCAL time (unlike a date-ONLY string, which is parsed as UTC). The
 * previous `new Date(value).toISOString()` pattern used across this
 * module double-shifted every timestamp: it mis-parsed the naive UTC
 * string as if it were already local time, then rendered that wrong
 * instant back out in UTC -- a 23:26 UTC event (18:26 Bogota) was shown
 * as "04:26 the NEXT DAY".
 */
export function formatBackendTimestampLocal(
  value: string | Date | null | undefined,
): string {
  if (value === null || value === undefined) return '—';
  let d: Date;
  if (value instanceof Date) {
    d = value;
  } else {
    const hasTzDesignator = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value);
    d = new Date(hasTzDesignator ? value : `${value}Z`);
  }
  if (Number.isNaN(d.getTime())) {
    return typeof value === 'string' ? value : '—';
  }
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}