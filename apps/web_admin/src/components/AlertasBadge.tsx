/**
 * `<AlertasBadge />` -- HU-F19.5 nav counter: alertas `abierta` +
 * `en_revision` across the actor's `sucursales permitidas`.
 *
 * No real persistent sidebar exists yet in `web_admin` (checked before
 * writing this: `TopNav.tsx` has no nav list, `AdminChrome.tsx` is just
 * an `<Outlet />` wrapper, and `lib/admin-sections.ts` -- the one place
 * that LOOKS like a nav catalog -- is dead code outside its own test,
 * per `ReporteriaSuscripciones.tsx`'s own docblock admission). The
 * closest LIVE, rendered nav surface is `pages/GlobalHQ.tsx`'s
 * `HUB_CARDS` grid (same surface `/arqueos` uses), so this component is
 * mounted there, overlaid on the "Alertas" card's icon -- see that
 * file for the mount point.
 *
 * Why a plain SWR hook here and NOT a new Zustand store: this repo
 * already has exactly one global store for FE state
 * (`apps/ui-kit/src/store/authStore.ts`), and it is scoped tightly to
 * auth identity/tokens (checked its contents before deciding) -- it has
 * no concept of "alert counts" and bolting one on would widen an
 * auth-only store's responsibility for a single counter only this
 * component needs. A short-lived SWR cache entry, polled like
 * `useAdminAuth` already does for `/admin/me`, is the proportional
 * choice; nothing else in the app needs this count yet.
 *
 * No dedicated "count" endpoint exists on `GET /workflows/alerta`
 * (cursor-paginated, no total). This fetches `estado=abierta` and
 * `estado=en_revision` in parallel (the query only takes ONE `estado`
 * value at a time) with a generous `limit`, filters each page
 * client-side to the permitted branches (same defense-in-depth as
 * `AlertasList.tsx`), and sums the two page lengths. When either page's
 * `next_cursor` is non-null the real total exceeds what was fetched --
 * the badge then renders `"N+"` instead of pretending to be exact.
 */
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import useSWR from 'swr';
import { Bell } from 'lucide-react';
import { useAdminAuth } from '@parkos/ui-kit/hooks';

import { fetchAlertas } from '@/features/alertas/api/alertasApi';
import type { AlertasListResponse } from '@/features/alertas/api/alertasSchema';

const REFRESH_INTERVAL_MS = 60_000;
const COUNT_PAGE_LIMIT = 100;

interface AlertasCount {
  count: number;
  /** True when at least one of the two pages had a `next_cursor` (undercount). */
  approximate: boolean;
}

function scopedLength(resp: AlertasListResponse, permitted: ReadonlySet<string>): number {
  return resp.items.filter((item) => item.uuid_sucursal !== null && permitted.has(item.uuid_sucursal))
    .length;
}

async function fetchAbiertasCount(sucursalUuids: readonly string[]): Promise<AlertasCount> {
  if (sucursalUuids.length === 0) return { count: 0, approximate: false };
  const permitted = new Set(sucursalUuids);
  const [abiertas, enRevision] = await Promise.all([
    fetchAlertas({ estado: 'abierta', limit: COUNT_PAGE_LIMIT }),
    fetchAlertas({ estado: 'en_revision', limit: COUNT_PAGE_LIMIT }),
  ]);
  return {
    count: scopedLength(abiertas, permitted) + scopedLength(enRevision, permitted),
    approximate: abiertas.next_cursor !== null || enRevision.next_cursor !== null,
  };
}

export function AlertasBadge(): JSX.Element | null {
  const { t } = useTranslation();
  const { sucursalUuids, isAuthenticated } = useAdminAuth();

  const swrKey = isAuthenticated ? `alertas-badge:${sucursalUuids.slice().sort().join(',')}` : null;
  const { data } = useSWR<AlertasCount>(swrKey, () => fetchAbiertasCount(sucursalUuids), {
    refreshInterval: REFRESH_INTERVAL_MS,
    revalidateOnFocus: false,
  });

  if (data === undefined || data.count === 0) return null;

  const display = data.approximate ? `${data.count}+` : String(data.count);

  return (
    <Link
      to="/alertas"
      data-testid="alertas-badge"
      aria-label={t('alertas.badge.label', '{{count}} alertas abiertas o en revisión', {
        count: data.count,
      })}
      className="bg-destructive text-destructive-foreground inline-flex min-w-5 items-center justify-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-semibold leading-none shadow-elevation-1"
    >
      <Bell className="size-3" aria-hidden="true" />
      {display}
    </Link>
  );
}
