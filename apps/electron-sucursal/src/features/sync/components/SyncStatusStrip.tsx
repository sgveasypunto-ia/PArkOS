/**
 * `<SyncStatusStrip />` — F11.1 in-dashboard sync indicator.
 *
 * Three-color chip derived from `useSyncEstado().data.estado`
 * (online | lagging | offline). REQ-OPS-139 lazy-mount — when
 * `uuid_sucursal` is `null`, no `/sync/estado` fetch fires.
 */
import { useTranslation } from 'react-i18next';
import { CloudOff, Cloud, CloudFog } from 'lucide-react';

import { useSyncEstado } from '../hooks/useSyncEstado';

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

  const estado = data?.estado ?? 'offline';
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
      {data && (
        <span className="text-xs opacity-80" data-testid="sync-lag">
          ({data.lag_seg}s)
        </span>
      )}
    </div>
  );
}