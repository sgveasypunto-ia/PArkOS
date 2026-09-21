/**
 * `<MiTurnoKpiCard />` — single KPI cell of the per-turn aggregate panel
 * (HU-F12.1, AD-4).
 *
 * Renders a shadcn `<Card>` with:
 *   - `data-testid="mi-turno-kpi-<slug>"` (test surface)
 *   - `aria-label` = the i18n label
 *   - `tabular-nums` so the numeric value does not jitter as digits shift
 *   - semantic tokens only (`text-foreground`, `text-muted-foreground`)
 *
 * The card is purely presentational; it does NOT subscribe to the SWR
 * hook. The orchestrator `<MiTurnoPanel />` resolves the data and passes
 * each KPI down — keeps the test surface flat (one render prop per card).
 */
import { useTranslation } from 'react-i18next';

import {
  Card,
  CardContent,
  CardDescription,
  CardTitle,
} from '@/components/ui/card';

/**
 * Convert a Spanish label like "Total cobrado" into a stable kebab-case
 * slug for the `data-testid` (`mi-turno-kpi-total-cobrado`). Tests
 * assert these slugs; do NOT change the algorithm without updating
 * the panel tests.
 */
function slugify(label: string): string {
  return label
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export interface MiTurnoKpiCardProps {
  /** i18n key (full path) for the label. */
  labelKey: string;
  /** Optional explicit display value override; defaults to labelKey. */
  label?: string;
  value: number | string;
  /** Optional `i18n` key for a unit suffix (e.g. "COP"). */
  unitKey?: string;
  /** Test surface slug override; defaults to label slug. */
  testIdSlug?: string;
}

export function MiTurnoKpiCard({
  labelKey,
  label,
  value,
  unitKey,
  testIdSlug,
}: MiTurnoKpiCardProps): JSX.Element {
  const { t } = useTranslation('operacion');
  const resolvedLabel = label ?? t(labelKey);
  const testId = `mi-turno-kpi-${testIdSlug ?? slugify(resolvedLabel)}`;
  const unit = unitKey ? t(unitKey) : '';

  return (
    <Card data-testid={testId} aria-label={resolvedLabel} className="p-3">
      <CardDescription className="text-xs uppercase tracking-wider text-muted-foreground">
        {resolvedLabel}
      </CardDescription>
      <CardTitle className="mt-1 font-mono text-2xl tabular-nums">
        {value.toLocaleString('es-CO')}
        {unit !== '' && (
          <span className="ml-1 text-xs font-normal text-muted-foreground">{unit}</span>
        )}
      </CardTitle>
      <CardContent className="hidden">{resolvedLabel}</CardContent>
    </Card>
  );
}