/**
 * `LogTransaccionalTable` -- presentational table for the HU-F20.4
 * bitácora listing. Mirrors `alertas/components/AlertasTable.tsx` /
 * `arqueos/components/ArqueosList.tsx` (raw table, "Cargar más" cursor
 * button). Reuses the shared `<HashChainStatus />` badge (already used by
 * `ArqueosList.tsx`) instead of hand-rolling a hash-truncation renderer.
 */
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { HashChainStatus } from '@/components/HashChainStatus';
import { formatBackendTimestampLocal } from '@/features/reporteria/components/dateRange';

import type { AuditLogItem } from '../api/auditoriaSchema';

export interface LogTransaccionalTableProps {
  items: AuditLogItem[];
  isLoading: boolean;
  hasMore: boolean;
  isLoadingMore: boolean;
  onLoadMore: () => void;
  onOpen: (item: AuditLogItem) => void;
}

function short(uuid: string | null): string {
  return uuid ? `${uuid.slice(0, 8)}…` : '—';
}

export function LogTransaccionalTable({
  items,
  isLoading,
  hasMore,
  isLoadingMore,
  onLoadMore,
  onOpen,
}: LogTransaccionalTableProps): JSX.Element {
  const { t } = useTranslation();

  if (!isLoading && items.length === 0) {
    return (
      <div
        role="status"
        aria-live="polite"
        data-testid="log-transaccional-empty"
        className="rounded-md border border-dashed bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground"
      >
        {t('auditoria.table.empty', 'No hay eventos de bitácora para el filtro seleccionado.')}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <table
        data-testid="log-transaccional-table"
        className="w-full overflow-x-auto rounded-lg border bg-card text-sm"
      >
        <thead className="bg-muted/40 text-left">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('auditoria.table.fecha', 'Fecha')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('auditoria.table.tabla', 'Tabla')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('auditoria.table.accion', 'Acción')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('auditoria.table.sucursal', 'Sucursal')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('auditoria.table.usuario', 'Usuario')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('auditoria.table.hashChain', 'Cadena')}
            </th>
            <th scope="col" className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr
              key={row.uuid}
              data-testid={`log-transaccional-row-${row.uuid}`}
              className="border-t hover:bg-muted/20"
            >
              <td className="px-3 py-2 tabular-nums text-xs">
                {formatBackendTimestampLocal(row.timestamp_evento)}
              </td>
              <td className="px-3 py-2 font-mono text-xs">{row.tabla_afectada ?? '—'}</td>
              <td className="px-3 py-2 text-xs">{row.accion ?? '—'}</td>
              <td className="px-3 py-2 font-mono text-xs">{short(row.uuid_sucursal)}</td>
              <td className="px-3 py-2 font-mono text-xs">{short(row.uuid_usuario)}</td>
              <td className="px-3 py-2">
                <HashChainStatus
                  hashAnterior={row.hash_anterior}
                  hashActual={row.hash_actual}
                  compact
                />
              </td>
              <td className="px-3 py-2 text-right">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => onOpen(row)}
                  data-testid={`log-transaccional-row-open-${row.uuid}`}
                >
                  {t('auditoria.table.openButton', 'Ver detalle')}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {hasMore && (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onLoadMore}
            disabled={isLoadingMore}
            data-testid="log-transaccional-load-more"
          >
            {isLoadingMore
              ? t('auditoria.table.loadingMore', 'Cargando...')
              : t('auditoria.table.loadMore', 'Cargar más')}
          </Button>
        </div>
      )}
    </div>
  );
}
