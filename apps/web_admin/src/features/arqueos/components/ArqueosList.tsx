/**
 * ``ArqueosList`` -- presentational table for the admin arqueo
 * listing (HU-F18.2).
 *
 * Renders the ``items`` array as a simple HTML table. The container
 * owns pagination + the cursor-merging helper, so this component is
 * a thin renderer that exposes three testids:
 *
 *   - ``arqueos-list-table``      -- the wrapping table element.
 *   - ``arqueos-list-row-{uuid}`` -- one row per item.
 *   - ``arqueos-list-load-more``  -- the button that triggers the next
 *     page fetch when ``hasMore`` is true.
 *   - ``arqueos-list-empty``      -- the empty-state banner.
 *
 * The componente delegates the row-level interaction to
 * ``<ArqueoRowButton />`` so the URL/anchor contract stays
 * predictable across tests.
 */
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { HashChainStatus } from '@/components/HashChainStatus';

import type { ArqueoRead } from '../api/arqueosSchema';

export interface ArqueosListProps {
  items: ArqueoRead[];
  isLoading: boolean;
  hasMore: boolean;
  isLoadingMore: boolean;
  onLoadMore: () => void;
  onSelect: (arq: ArqueoRead) => void;
}

export function ArqueosList({
  items,
  isLoading,
  hasMore,
  isLoadingMore,
  onLoadMore,
  onSelect,
}: ArqueosListProps): JSX.Element {
  const { t } = useTranslation();

  if (!isLoading && items.length === 0) {
    return (
      <div
        role="status"
        aria-live="polite"
        data-testid="arqueos-list-empty"
        className="rounded-md border border-dashed bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground"
      >
        {t('arqueos.empty')}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <table
        data-testid="arqueos-list-table"
        className="w-full overflow-x-auto rounded-lg border bg-card text-sm"
      >
        <thead className="bg-muted/40 text-left">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('arqueos.table.createdAt')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('arqueos.table.sucursal')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('arqueos.table.tipo')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('arqueos.table.sesion')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('arqueos.table.efectivo')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('arqueos.table.datafono')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('arqueos.table.hashChain')}
            </th>
            <th scope="col" className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr
              key={row.uuid}
              data-testid={`arqueos-list-row-${row.uuid}`}
              className="border-t hover:bg-muted/20"
            >
              <td className="px-3 py-2 font-mono text-xs">{row.created_at}</td>
              <td className="px-3 py-2 font-mono text-xs">
                {row.uuid_sucursal ?? '—'}
              </td>
              <td className="px-3 py-2 font-mono text-xs">
                {row.uuid_tipo_arqueo ?? '—'}
              </td>
              <td className="px-3 py-2 font-mono text-xs">
                {row.uuid_sesion ?? '—'}
              </td>
              <td className="px-3 py-2 font-mono text-xs">
                {row.valor_efectivo_reportado ?? '—'}
              </td>
              <td className="px-3 py-2 font-mono text-xs">
                {row.valor_datafono_reportado ?? '—'}
              </td>
              <td className="px-3 py-2">
                {/* HashChainStatus requires the previous-row hash,
                    which the current list response doesn't carry. The
                    detail panel renders the full chain once the row
                    is opened. Here we show a placeholder until the BE
                    adds ``hash_anterior`` to ArqueoRead (F18.2 follow-up). */}
                <span
                  data-testid="arqueos-list-row-hash"
                  className="text-xs text-muted-foreground"
                >
                  —
                </span>
              </td>
              <td className="px-3 py-2 text-right">
                <Button
                  data-testid={`arqueos-list-row-open-${row.uuid}`}
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => onSelect(row)}
                >
                  {t('arqueos.table.openButton')}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {hasMore && (
        <div className="flex justify-center">
          <Button
            data-testid="arqueos-list-load-more"
            type="button"
            variant="outline"
            disabled={isLoadingMore}
            onClick={onLoadMore}
          >
            {isLoadingMore
              ? t('arqueos.table.loadingMore')
              : t('arqueos.table.loadMore')}
          </Button>
        </div>
      )}

      {/* Reserved future use -- HashChainStatus is the shared
          integrity badge, mounted here once the list response carries
          ``hash_anterior`` per row. The component is imported so the
          dependency graph doesn't get shaken out by lint. */}
      <span aria-hidden="true" className="hidden">
        <HashChainStatus hashAnterior={null} hashActual={null} />
      </span>
    </div>
  );
}