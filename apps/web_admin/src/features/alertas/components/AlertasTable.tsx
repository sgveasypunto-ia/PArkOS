/**
 * `AlertasTable` -- presentational table for the HU-F19.5 alertas
 * inbox, with BR3's visual grouping layered on top.
 *
 * BR3 (plan.md): when `(tipo_alerta, uuid_sucursal, día)` repeats across
 * rows, the UI groups those rows under ONE collapsed-by-default header
 * with a count badge; expanding it reveals every row inside, unchanged.
 * This is presentation-only (`groupAlertas.ts` never drops a row) -- a
 * lone-item "group" just renders as a normal row, no header, no toggle.
 *
 * Three testids per spec:
 *   - `alertas-table`               -- the wrapping table.
 *   - `alertas-row-{uuid}`          -- one row per alerta (inside or
 *     outside a group, same shape).
 *   - `alertas-group-toggle-{key}`  -- the expand/collapse control for a
 *     multi-item group (key is URL-safe-ish but only used as a testid
 *     suffix, never parsed back).
 */
import { Fragment, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { Button } from '@/components/ui/button';

import type { AlertaRead } from '../api/alertasSchema';
import { buildAlertaGroups } from '../lib/groupAlertas';
import { SeverityBadge } from './SeverityBadge';
import { EstadoAlertaBadge } from './EstadoAlertaBadge';

export interface AlertasTableProps {
  items: AlertaRead[];
  isLoading: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
  onOpen: (alerta: AlertaRead) => void;
}

function AlertaRow({
  alerta,
  onOpen,
}: {
  alerta: AlertaRead;
  onOpen: (alerta: AlertaRead) => void;
}): JSX.Element {
  const { t } = useTranslation();
  return (
    <tr
      key={alerta.uuid}
      data-testid={`alertas-row-${alerta.uuid}`}
      className="border-t hover:bg-muted/20"
    >
      <td className="px-3 py-2 font-mono text-xs">
        {alerta.timestamp_evento ?? alerta.created_at}
      </td>
      <td className="px-3 py-2 font-mono text-xs">{alerta.uuid_sucursal ?? '—'}</td>
      <td className="px-3 py-2 text-xs">{alerta.tipo_alerta ?? '—'}</td>
      <td className="px-3 py-2">
        <SeverityBadge severity={alerta.severity} />
      </td>
      <td className="px-3 py-2">
        <EstadoAlertaBadge estado={alerta.estado} />
      </td>
      <td className="px-3 py-2 text-right">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => onOpen(alerta)}
          data-testid={`alertas-row-open-${alerta.uuid}`}
        >
          {t('alertas.table.openButton', 'Ver detalle')}
        </Button>
      </td>
    </tr>
  );
}

export function AlertasTable({
  items,
  isLoading,
  hasMore,
  onLoadMore,
  onOpen,
}: AlertasTableProps): JSX.Element {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (!isLoading && items.length === 0) {
    return (
      <div
        role="status"
        aria-live="polite"
        data-testid="alertas-empty"
        className="rounded-md border border-dashed bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground"
      >
        {t('alertas.empty', 'No hay alertas con esos filtros.')}
      </div>
    );
  }

  const groups = buildAlertaGroups(items);

  function toggle(key: string): void {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <div className="space-y-3">
      <table
        data-testid="alertas-table"
        className="w-full overflow-x-auto rounded-lg border bg-card text-sm"
      >
        <thead className="bg-muted/40 text-left">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('alertas.table.fecha', 'Fecha')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('alertas.table.sucursal', 'Sucursal')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('alertas.table.tipo', 'Tipo')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('alertas.table.severidad', 'Severidad')}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {t('alertas.table.estado', 'Estado')}
            </th>
            <th scope="col" className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => {
            if (group.items.length === 1) {
              return <AlertaRow key={group.key} alerta={group.items[0]!} onOpen={onOpen} />;
            }

            const isOpen = expanded.has(group.key);
            return (
              <Fragment key={group.key}>
                <tr
                  className="border-t bg-muted/10"
                  data-testid={`alertas-group-${group.key}`}
                >
                  <td colSpan={6} className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => toggle(group.key)}
                      data-testid={`alertas-group-toggle-${group.key}`}
                      aria-expanded={isOpen}
                      className="flex w-full items-center gap-2 text-left text-sm font-medium"
                    >
                      {isOpen ? (
                        <ChevronDown className="size-4 shrink-0" aria-hidden="true" />
                      ) : (
                        <ChevronRight className="size-4 shrink-0" aria-hidden="true" />
                      )}
                      <span>{group.tipoAlerta || '—'}</span>
                      <span className="text-muted-foreground">·</span>
                      <span className="font-mono text-xs text-muted-foreground">
                        {group.uuidSucursal || '—'}
                      </span>
                      <span className="text-muted-foreground">·</span>
                      <span className="text-muted-foreground">{group.dia}</span>
                      <span
                        data-testid={`alertas-group-count-${group.key}`}
                        className="ml-auto rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary"
                      >
                        {t('alertas.group.count', '{{count}} alertas', { count: group.items.length })}
                      </span>
                    </button>
                  </td>
                </tr>
                {isOpen &&
                  group.items.map((alerta) => (
                    <AlertaRow key={alerta.uuid} alerta={alerta} onOpen={onOpen} />
                  ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>

      {hasMore && (
        <div className="flex justify-center">
          <Button
            data-testid="alertas-load-more"
            type="button"
            variant="outline"
            onClick={onLoadMore}
          >
            {t('alertas.table.loadMore', 'Cargar más')}
          </Button>
        </div>
      )}
    </div>
  );
}
