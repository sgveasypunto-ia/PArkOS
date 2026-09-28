/**
 * RequireSucursal — second-layer route guard. `RequireAdmin` already
 * proved we have a valid admin- token; this guard proves the operator
 * has SELECTED a branch the token authorizes.
 *
 * Decision (confirmed by the user): ALWAYS force a stop at
 * `/seleccionar-sucursal`, even when there is exactly one permitted
 * branch. The auto-skip was rejected because it would let the operator
 * end up on `/dashboard` after a stale `localStorage` selection without
 * ever confirming the choice — making branch switches non-obvious.
 *
 * Edge cases handled:
 *   - `useAdminAuth().isLoading` -> loading state (do not redirect yet).
 *   - `sucursalUuids.length === 0` -> /forbidden. There is no point
 *     showing a picker with zero options.
 *   - `selected === null` OR `selected not in sucursalUuids` ->
 *     redirect to /seleccionar-sucursal (clears stale selection first).
 *   - Otherwise -> Outlet.
 *
 * Stale-selection cleanup: when the persisted `selected` UUID is no
 * longer in the operator's claim (branch revoked, token rotated), we
 * wipe it via `setSelected(null)` so the picker truly starts fresh and
 * subsequent SWR cache invalidation reflects the new scope.
 */
import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useAdminAuth } from '@parkos/ui-kit/hooks';
import { useSucursal } from '@/lib/sucursal-context';

export interface RequireSucursalProps {
  children?: ReactNode;
}

export function RequireSucursal({ children }: RequireSucursalProps): JSX.Element {
  const { isLoading, sucursalUuids } = useAdminAuth();
  const { selected, setSelected } = useSucursal();
  const location = useLocation();

  const hasSelection = selected !== null && sucursalUuids.includes(selected);

  useEffect(() => {
    if (!isLoading && selected !== null && !sucursalUuids.includes(selected)) {
      setSelected(null);
    }
  }, [isLoading, selected, sucursalUuids, setSelected]);

  if (isLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        data-testid="require-sucursal-loading"
        className="flex min-h-screen items-center justify-center bg-background"
      >
        <p className="text-muted-foreground text-sm">Loading…</p>
      </div>
    );
  }

  if (sucursalUuids.length === 0) {
    return <Navigate to="/forbidden" replace state={{ from: location.pathname }} />;
  }

  if (!hasSelection) {
    return <Navigate to="/seleccionar-sucursal" replace />;
  }

  return <>{children ?? <Outlet />}</>;
}
