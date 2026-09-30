/**
 * `<DateRangePicker />` — presentational date-range selector for the
 * reporteria operacional page (HU-F17.1, web_admin).
 *
 * Two `<input type="date">` fields with native pickers (no extra
 * dependency), constrained so ``fecha_desde <= fecha_hasta`` and
 * neither is in the future (the backend rejects future ranges with
 * an empty response, but a friendly inline message beats a silent
 * empty). Four preset buttons collapse the common ranges the
 * operator reaches for: Hoy, Ayer, Últimos 7 días, Este mes.
 *
 * Why native date inputs (vs. a calendar popover):
 * - the existing dep set has no date picker library; the budget for
 *   PR-1 is small and the F17.1 user directive was "no charts" — a
 *   calendar picker with month-picker overviews lands in the same
 *   scope creep. Native date inputs are accessible by default
 *   (each browser ships a usable picker on every platform) and ship
 *   zero new code paths.
 *
 * Why "YYYY-MM-DD" and not a Date object: HTML date inputs already
 * emit that format, the backend query string accepts it directly,
 * and we sidestep the timezone trap (``new Date('2026-01-01')`` is
 * UTC midnight, not local midnight, which would silently shift the
 * range by 5 hours in Bogotá).
 *
 * Accessibility (RNF-022 WCAG 2.1 AA):
 * - `<label>` paired with each `<input>` via `htmlFor`/`id`.
 * - range-error rendered as `role="alert"`, aria-live="assertive".
 * - preset buttons are real `<button type="button">` so they cannot
 *   submit a wrapping form accidentally.
 */
import { useTranslation } from 'react-i18next';

import { Input } from '@/components/ui/input';

import {
  type DateRange,
  isValidDate,
  offsetISO,
  startOfMonthISO,
  todayISO,
} from './dateRange';

export type { DateRange } from './dateRange';

export interface DateRangePickerProps {
  value: DateRange;
  onChange: (next: DateRange) => void;
  disabled?: boolean;
}

export function DateRangePicker({
  value,
  onChange,
  disabled,
}: DateRangePickerProps) {
  const { t } = useTranslation();

  const today = todayISO();
  const invalid =
    !isValidDate(value.fecha_desde) ||
    !isValidDate(value.fecha_hasta) ||
    value.fecha_desde > value.fecha_hasta;
  const futureWarning =
    isValidDate(value.fecha_hasta) && value.fecha_hasta > today;
  const tooOldWarning =
    isValidDate(value.fecha_desde) && value.fecha_desde < offsetISO(-365);

  const applyPreset = (preset: 'hoy' | 'ayer' | '7d' | 'mes') => {
    if (preset === 'hoy') {
      onChange({ fecha_desde: today, fecha_hasta: today });
    } else if (preset === 'ayer') {
      const y = offsetISO(-1);
      onChange({ fecha_desde: y, fecha_hasta: y });
    } else if (preset === '7d') {
      onChange({ fecha_desde: offsetISO(-6), fecha_hasta: today });
    } else {
      onChange({ fecha_desde: startOfMonthISO(), fecha_hasta: today });
    }
  };

  return (
    <div
      className="flex flex-col gap-2 rounded-md border bg-muted/20 p-3"
      data-testid="reporteria-date-range"
    >
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium text-muted-foreground">
            {t('reporteria.dateRange.desde', 'Desde')}
          </span>
          <Input
            id="reporteria-fecha-desde"
            type="date"
            value={value.fecha_desde}
            max={value.fecha_hasta || today}
            onChange={(e) =>
              onChange({ ...value, fecha_desde: e.target.value })
            }
            disabled={disabled}
            data-testid="reporteria-fecha-desde"
            className="w-44"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium text-muted-foreground">
            {t('reporteria.dateRange.hasta', 'Hasta')}
          </span>
          <Input
            id="reporteria-fecha-hasta"
            type="date"
            value={value.fecha_hasta}
            min={value.fecha_desde || undefined}
            max={today}
            onChange={(e) =>
              onChange({ ...value, fecha_hasta: e.target.value })
            }
            disabled={disabled}
            data-testid="reporteria-fecha-hasta"
            className="w-44"
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <PresetButton
            onClick={() => applyPreset('hoy')}
            testid="reporteria-preset-hoy"
            label={t('reporteria.dateRange.preset.hoy', 'Hoy')}
          />
          <PresetButton
            onClick={() => applyPreset('ayer')}
            testid="reporteria-preset-ayer"
            label={t('reporteria.dateRange.preset.ayer', 'Ayer')}
          />
          <PresetButton
            onClick={() => applyPreset('7d')}
            testid="reporteria-preset-7d"
            label={t('reporteria.dateRange.preset.7d', 'Últimos 7 días')}
          />
          <PresetButton
            onClick={() => applyPreset('mes')}
            testid="reporteria-preset-mes"
            label={t('reporteria.dateRange.preset.mes', 'Este mes')}
          />
        </div>
      </div>
      {invalid ? (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="reporteria-range-error"
          className="text-xs text-destructive"
        >
          {t(
            'reporteria.dateRange.error',
            'Rango inválido: la fecha de inicio debe ser anterior o igual a la de fin.',
          )}
        </p>
      ) : futureWarning ? (
        <p
          role="status"
          aria-live="polite"
          data-testid="reporteria-range-future-warning"
          className="text-xs text-amber-700"
        >
          {t(
            'reporteria.dateRange.futureWarning',
            'La fecha de fin está en el futuro. Probablemente no hay datos para esos días.',
          )}
        </p>
      ) : tooOldWarning ? (
        <p
          role="status"
          aria-live="polite"
          data-testid="reporteria-range-too-old"
          className="text-xs text-muted-foreground"
        >
          {t(
            'reporteria.dateRange.tooOld',
            'El reporte cubre más de un año. La factura electrónica tiene retención DIAN de 5+ años pero el endpoint actual agrega solo las facturas vivas en el rango.',
          )}
        </p>
      ) : null}
    </div>
  );
}

function PresetButton({
  onClick,
  testid,
  label,
}: {
  onClick: () => void;
  testid: string;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className="rounded-md border bg-background px-2 py-1 text-xs font-medium hover:bg-muted"
    >
      {label}
    </button>
  );
}