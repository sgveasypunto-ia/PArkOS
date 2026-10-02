/**
 * `DianQueueTable` -- presentational table for the HU-F20.5 "monitor de
 * envíos DIAN" queue. Mirrors `alertas/components/AlertasTable.tsx`'s
 * shape (plain `<table>`, `data-testid` per row, "Cargar más" pagination).
 *
 * "Reintentar" gating (UX-only -- the backend, `retry_envio_dian`, is the
 * real authority via its own chain-tip state check):
 *   - Enabled only when `estado === 'rechazado'` AND
 *     `uuid_factura_electronica !== null` (the retry endpoint's path
 *     param).
 *   - RIESGO-ADM-09: disabled IMMEDIATELY on click, before the response
 *     arrives (`isRetrying`, lifted to `useRetryEnvioDian` so it survives
 *     this row's own re-renders and is shared across the whole table).
 */
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

import type { EnvioDianRead } from '../api/envioDianSchema';
import { canRetryEnvioDian } from '../lib/canRetryEnvioDian';
import { EstadoEnvioDianBadge } from './EstadoEnvioDianBadge';

export interface DianQueueTableProps {
  items: EnvioDianRead[];
  isLoading: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
  onOpen: (envio: EnvioDianRead) => void;
  onRetry: (envio: EnvioDianRead) => void;
  isRetrying: (uuidFacturaElectronica: string) => boolean;
}

function DianQueueRow({
  envio,
  onOpen,
  onRetry,
  isRetrying,
}: {
  envio: EnvioDianRead;
  onOpen: (envio: EnvioDianRead) => void;
  onRetry: (envio: EnvioDianRead) => void;
  isRetrying: (uuidFacturaElectronica: string) => boolean;
}): JSX.Element {
  const { t } = useTranslation();
  const retrying = envio.uuid_factura_electronica !== null && isRetrying(envio.uuid_factura_electronica);
  const retryEnabled = canRetryEnvioDian(envio) && !retrying;

  return (
    <tr
      key={envio.uuid}
      data-testid={`dian-row-${envio.uuid}`}
      className="border-t hover:bg-muted/20"
    >
      <td className="px-3 py-2 font-mono text-xs">
        {envio.timestamp_evento ?? envio.created_at}
      </td>
      <td className="px-3 py-2 font-mono text-xs">{envio.uuid_sucursal ?? '—'}</td>
      <td className="px-3 py-2 font-mono text-xs">{envio.uuid_factura_electronica ?? '—'}</td>
      <td className="px-3 py-2">
        <EstadoEnvioDianBadge estado={envio.estado} />
      </td>
      <td className="px-3 py-2 font-mono text-xs">{envio.cufe ?? '—'}</td>
      <td className="px-3 py-2 text-right">
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onOpen(envio)}
            data-testid={`dian-row-open-${envio.uuid}`}
          >
            {t('dian.table.openButton', 'Ver detalle')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="destructive"
            disabled={!retryEnabled}
            onClick={() => onRetry(envio)}
            data-testid={`dian-row-retry-${envio.uuid}`}
            title={
              canRetryEnvioDian(envio)
                ? undefined
                : t('dian.table.retryDisabledTitle', 'Solo se puede reintentar un envío rechazado.')
            }
          >
            {retrying
              ? t('dian.table.retrying', 'Reintentando…')
              : t('dian.table.retryButton', 'Reintentar')}
          </Button>
        </div>
      </td>
    </tr>
  );
}

export function DianQueueTable({
  items,
  isLoading,
  hasMore,
  onLoadMore,
  onOpen,
  onRetry,
  isRetrying,
}: DianQueueTableProps): JSX.Element {
  const { t } = useTranslation();

  if (!isLoading && items.length === 0) {
    return (
      <div
        role="status"
        aria-live="polite"
        data-testid="dian-empty"
        className="rounded-md border border-dashed bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground"
      >
        {t('dian.empty', 'No hay envíos DIAN con esos filtros.')}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <table
        data-testid="dian-table"
        className="w-full overflow-x-auto rounded-lg border bg-card text-sm"
      >
        <thead className="bg-muted/40 text-left">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('dian.table.fecha', 'Fecha')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('dian.table.sucursal', 'Sucursal')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('dian.table.factura', 'Factura electrónica')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('dian.table.estado', 'Estado')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('dian.table.cufe', 'CUFE')}
            </th>
            <th scope="col" className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {items.map((envio) => (
            <DianQueueRow
              key={envio.uuid}
              envio={envio}
              onOpen={onOpen}
              onRetry={onRetry}
              isRetrying={isRetrying}
            />
          ))}
        </tbody>
      </table>

      {hasMore && (
        <div className="flex justify-center">
          <Button
            data-testid="dian-load-more"
            type="button"
            variant="outline"
            onClick={onLoadMore}
          >
            {t('dian.table.loadMore', 'Cargar más')}
          </Button>
        </div>
      )}
    </div>
  );
}
