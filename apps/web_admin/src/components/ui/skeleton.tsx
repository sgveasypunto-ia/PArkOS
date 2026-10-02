/**
 * `skeleton.tsx` — shadcn primitive loading placeholder.
 *
 * Standard shadcn/ui recipe: a pulsing muted block. Used by `KpiCard`
 * (HU-F17.1) while its SWR key is still loading, instead of the ad hoc
 * `'…'` text the original `MetricCard` used in `pages/Dashboard.tsx`.
 */
import * as React from 'react';

import { cn } from '@/lib/utils';

export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>): JSX.Element {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-muted', className)}
      role="status"
      aria-label="Cargando"
      {...props}
    />
  );
}
