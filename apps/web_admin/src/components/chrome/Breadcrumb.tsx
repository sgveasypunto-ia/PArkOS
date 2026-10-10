/**
 * `<Breadcrumb />` — the navigation trail shown below `<TopNav />` on
 * every authed route. Renders a `<nav>` with an ordered list of
 * segments, each one either a `<Link>` (intermediate) or a `<span>`
 * with `aria-current="page"` (the last one).
 *
 * Source of truth: `lib/breadcrumbs.ts` (static route table) +
 * `lib/useBreadcrumbs.ts` (override hook for detail pages). The
 * component itself is dumb: it just renders whatever the resolver
 * returns. This keeps the markup testable and the policy (which
 * route gets which segments) in one place.
 *
 * Accessibility:
 *   - `<nav aria-label="...">` (resolves via i18n to "Migas de pan").
 *   - `<ol>` so the segment order is machine-readable.
 *   - The last segment gets `aria-current="page"` and is NOT a link.
 *   - Separators use a decorative `aria-hidden` `ChevronRight` icon
 *     so screen readers don't read it as part of the chain.
 *
 * Hidden when the resolver returns `null` crumbs (unmatched path,
 * e.g. `/login`). The wrapper `<nav>` is omitted entirely so the
 * a11y tree stays clean.
 */
import { Fragment } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ChevronRight, Home } from 'lucide-react';

import { cn } from '@/lib/utils';
import { useResolvedBreadcrumbs, type Crumb } from '@/lib/useBreadcrumbs';

export function Breadcrumb(): JSX.Element | null {
  const { t } = useTranslation();
  const { crumbs } = useResolvedBreadcrumbs();

  if (crumbs === null || crumbs.length === 0) {
    return null;
  }

  return (
    <nav
      aria-label={t('breadcrumb.ariaLabel', 'Migas de pan')}
      data-testid="breadcrumb"
      className="border-b border-border/40 bg-card/30 px-4 py-2 text-sm text-muted-foreground md:px-5 xl:px-6"
    >
      <ol className="flex flex-wrap items-center gap-1.5">
        {crumbs.map((crumb, idx) => (
          <Fragment key={`${crumb.to}-${idx}`}>
            {idx > 0 && (
              <li aria-hidden="true" className="flex items-center text-border">
                <ChevronRight className="size-3.5" />
              </li>
            )}
            <li className="flex min-w-0 items-center gap-1">
              <CrumbLink crumb={crumb} isFirst={idx === 0} />
            </li>
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}

interface CrumbLinkProps {
  crumb: Crumb;
  isFirst: boolean;
}

function CrumbLink({ crumb, isFirst }: CrumbLinkProps): JSX.Element {
  const { t } = useTranslation();
  const label = resolveLabel(crumb, t);

  if (crumb.current === true) {
    return (
      <span
        aria-current="page"
        data-testid="breadcrumb-current"
        className={cn(
          'flex min-w-0 items-center gap-1 truncate font-medium text-foreground',
          'max-w-[28rem]',
        )}
      >
        {isFirst && <Home className="size-3.5 shrink-0" aria-hidden="true" />}
        <span className="truncate">{label}</span>
      </span>
    );
  }

  return (
    <Link
      to={crumb.to ?? '/'}
      data-testid="breadcrumb-link"
      className={cn(
        'flex min-w-0 items-center gap-1 truncate rounded-sm hover:text-foreground',
        'focus-ring transition-colors duration-base ease-macos',
        'max-w-[28rem]',
      )}
    >
      {isFirst && <Home className="size-3.5 shrink-0" aria-hidden="true" />}
      <span className="truncate">{label}</span>
    </Link>
  );
}

function resolveLabel(crumb: Crumb, t: (key: string) => string): string {
  if (typeof crumb.label === 'string' && crumb.label.length > 0) {
    // Branch label is already-resolved (e.g. "BOG-CEN"); the table
    // either set it inline or it was filled by the resolver.
    return crumb.label;
  }
  if (crumb.staticLabel !== undefined) {
    return crumb.staticLabel;
  }
  if (crumb.i18nKey !== undefined) {
    return String(t(crumb.i18nKey));
  }
  return crumb.to ?? '';
}
