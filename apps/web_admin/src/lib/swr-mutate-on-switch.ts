/**
 * useInvalidateOnBranchSwitch — SWR cache invalidator.
 *
 * Every time the user picks a different branch in `<BranchSelector />`,
 * the dashboard SWR key
 * `/api/v1/admin/sucursales/{uuid}/dashboard` for the new UUID must be
 * invalidated so the page re-fetches under the new `X-Sucursal-Context`
 * header. We also invalidate the previous UUID's cache so any consumer
 * holding the old branch's data refetches if the user switches back.
 *
 * Mount this hook once near the root of the admin tree (next to
 * `<SucursalProvider>`) so it observes every switch without needing
 * callers to wire it themselves.
 */
import { useEffect, useRef } from 'react';
import { mutate } from 'swr';
import { useSucursal } from './sucursal-context';

const DASHBOARD_PATH = (uuid: string): string =>
  `/api/v1/admin/sucursales/${uuid}/dashboard`;

export function useInvalidateOnBranchSwitch(): void {
  const { selected } = useSucursal();
  const previousRef = useRef<string | null>(null);

  useEffect(() => {
    const previous = previousRef.current;
    if (previous !== null && previous !== selected) {
      // Old branch dashboard is now stale — drop its cache so a future
      // switch back refetches with the correct header.
      void mutate(DASHBOARD_PATH(previous));
    }
    if (selected !== null) {
      void mutate(DASHBOARD_PATH(selected));
    }
    previousRef.current = selected;
  }, [selected]);
}
