/**
 * `<SyncStatusStrip />` — F11.1 in-dashboard sync indicator.
 *
 * Three-color chip derived from `useSyncEstado().data` (lag_seg,
 * pendientes). The backend `SyncEstadoRead` no longer returns
 * `estado` (REQ-OPS-170 + DA-F11.1-7 GATING); the frontend derives
 * state from `(lag_seg, pendientes, ultima_sync_at)` via
 * `deriveSyncState()` (F11.1 AD-2). REQ-OPS-139 lazy-mount — when
 * `uuid_sucursal` is `null`, no `/sync/estado` fetch fires.
 *
 * NOTE: This chip is the in-Dashboard summary; the top-of-page
 * `<SyncBanner />` lives in `apps/electron-sucursal/src/components/SyncBanner.tsx`
 * and supersedes it on every protected route (F11.1 AD-5). This file
 * is converted to a deprecation shim re-exporting `<SyncBanner />` in
 * C5 of the F11.1 PR (R-CARRY-2 — removal deferred to F12.x).
 */
import { useTranslation } from 'react-i18next';
import { CloudOff, Cloud, CloudFog } from 'lucide-react';

import { useSyncEstado } from '../hooks/useSyncEstado';
import { deriveSyncState, type SyncState } from '../deriveSyncState';

export interface SyncStatusStripProps {
  uuid_sucursal: string | null;
}

const COLOR_CLASS: Record<'online' | 'lagging' | 'offline', string> = {
  online: 'bg-green-500 text-white',
  lagging: 'bg-amber-500 text-white',
  offline: 'bg-destructive text-destructive-foreground',
};

export function SyncStatusStrip({ uuid_sucursal }: SyncStatusStripProps): JSX.Element {
  const { t } = useTranslation('sync');
  const { data } = useSyncEstado(uuid_sucursal);

  // Derive the visual state from the backend's 4-field shape. Never
  // null after data arrives; falls through to `offline` while loading.
  const estado: 'online' | 'lagging' | 'offline' = data
    ? ((): SyncState => deriveSyncState(data))() === 'never_synced'
      ? 'offline'
      : (deriveSyncState(data) as 'online' | 'lagging' | 'offline')
    : 'offline';
  const Icon = estado === 'online' ? Cloud : estado === 'lagging' ? CloudFog : CloudOff;

  return (
    <div
      role="status"
      data-testid="sync-status-strip"
      data-estado={estado}
      className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium ${COLOR_CLASS[estado]}`}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      <span>
        {t('status', { defaultValue: 'Estado de sincronización' })}: {estado}
      </span>
      {data && data.lag_seg !== null && (
        <span className="text-xs opacity-80" data-testid="sync-lag">
          ({data.lag_seg}s)
        </span>
      )}
    </div>
  );
}