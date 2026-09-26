/**
 * `<RequireAdmin />` — Route guard for authenticated admin routes
 * (IT-1.10).
 *
 * Behavior:
 *   - While `useAuth().isLoading` is true: render a neutral loading
 *     state with `role="status" aria-live="polite"` (WCAG 2.1 AA
 *     live-region). DO NOT redirect on the first render — wait for
 *     SWR to hydrate before deciding.
 *   - When `isLoading === false && isAuthenticated === false`:
 *     redirect to `/login?next=<current-path>`. The `<Login />`
 *     container reads `next` from the query string (DEC-LOGIN-07)
 *     and bounces the user back to the intended route after a
 *     successful login.
 *   - When `isAuthenticated === true`: render `children`.
 *
 * Why not use the `Navigate` from `react-router-dom` directly: it
 * triggers a full re-render cycle. Wrapping with a guard component
 * gives us a single, testable decision point and keeps the route
 * table in `App.tsx` declarative.
 *
 * Why `next` survives via query string and not router state: the
 * admin might deep-link to `/dashboard/reports/2026-09` from an
 * email; preserving that across a login bounce requires either
 * a server-stored return URL (out of scope) or a query string.
 * The query string is the simplest viable solution that also
 * survives full-page refresh.
 */
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useAuth } from '@parkos/ui-kit/hooks';

export interface RequireAdminProps {
  children: ReactNode;
}

export function RequireAdmin({ children }: RequireAdminProps): JSX.Element {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        data-testid="require-admin-loading"
        className="flex min-h-screen items-center justify-center bg-background"
      >
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    const search = new URLSearchParams({ next: location.pathname + location.search }).toString();
    return <Navigate to={`/login?${search}`} replace />;
  }

  return <>{children}</>;
}
