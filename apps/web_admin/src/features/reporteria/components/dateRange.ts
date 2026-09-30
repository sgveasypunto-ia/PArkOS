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