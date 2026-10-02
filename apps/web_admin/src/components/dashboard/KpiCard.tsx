/**
 * `KpiCard.tsx` — one cell of the 3x3 executive dashboard grid (HU-F17.1, T3).
 *
 * Same visual language as the original `pages/Dashboard.tsx::MetricCard`
 * (rounded card, uppercase label, large tabular-nums value, optional link
 * hint) but adds a real skeleton while `loading` is true instead of the
 * `'…'` placeholder text, and accepts a `render` escape hatch for cards
 * whose value isn't a single number (medios de pago, alertas por
 * severidad, sync agregado).
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

export interface KpiCardProps {
  label: string;
  loading: boolean;
  error: boolean;
  /** Plain numeric/string headline. Omit when using `render`. */
  value?: number | string;
  /** Escape hatch for a card whose body isn't a single headline number. */
  render?: () => ReactNode;
  to?: string;
  linkHint?: string;
  errorLabel?: string;
}

export function KpiCard({
  label,
  loading,
  error,
  value,
  render,
  to,
  linkHint,
  errorLabel,
}: KpiCardProps): JSX.Element {
  const testId = `kpi-card-${label.toLowerCase().replace(/\s+/g, '-')}`;

  const body = (
    <>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-20" data-testid={`${testId}-skeleton`} />
      ) : error ? (
        <p className="mt-2 text-lg font-medium text-destructive" data-testid={`${testId}-error`}>
          {errorLabel ?? 'No disponible'}
        </p>
      ) : render ? (
        <div className="mt-2" data-testid={`${testId}-content`}>
          {render()}
        </div>
      ) : (
        <p className="mt-2 text-3xl font-semibold tabular-nums" data-testid={`${testId}-value`}>
          {value ?? 0}
        </p>
      )}
      {linkHint && !loading ? (
        <p className="mt-2 text-xs font-medium text-primary">{linkHint}</p>
      ) : null}
    </>
  );

  const className = cn(
    'rounded-lg border bg-card p-4 text-card-foreground shadow-sm',
    to && 'transition-shadow hover:shadow-md focus:outline-none focus:ring-2 focus:ring-ring',
  );

  if (to) {
    return (
      <Link to={to} className={className} data-testid={testId}>
        {body}
      </Link>
    );
  }
  return (
    <article className={className} data-testid={testId}>
      {body}
    </article>
  );
}
