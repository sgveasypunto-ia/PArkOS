/**
 * `<SyncLog />` — HU-F19.2 "Log" tab: cursor-paginated `sync_log`
 * history, filterable by sucursal + fecha range.
 *
 * Reuse note (apply report): none of the existing reportería table
 * components (`FacturasTable.tsx`, `IngresosTable.tsx`, etc. --
 * `features/reporteria/components/*Table.tsx`) actually render a
 * "load more" / next-page control despite their hooks already
 * threading a `cursor` param through to the backend -- every F17
 * container just fetches ONE page (`limit: 50`) and stops. There was
 * therefore no existing cursor-pagination UI control to reuse; the
 * "Cargar más" button below is new, built directly against
 * `next_cursor` the same way the hooks already expose it.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';

import { fetchSyncLog } from '../api/syncApi';
import type { SyncLogRead } from '../api/syncSchema';

export interface SyncLogProps {
  /** Pre-fills the sucursal filter (drill-down from the heatmap). */
  initialUuidSucursal?: string | null;
  onUuidSucursalChange?: (uuid: string | null) => void;
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toISOString().replace('T', ' ').slice(0, 19);
}

export default function SyncLog({
  initialUuidSucursal = null,
  onUuidSucursalChange,
}: SyncLogProps): JSX.Element {
  const { t } = useTranslation();
  const { sucursales } = useSucursalesDirectorio();

  const [uuidSucursal, setUuidSucursal] = useState<string>(initialUuidSucursal ?? '');
  const [desde, setDesde] = useState<string>('');
  const [hasta, setHasta] = useState<string>('');

  const [items, setItems] = useState<SyncLogRead[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Drill-down from the heatmap overrides the local filter.
  useEffect(() => {
    if (initialUuidSucursal !== null && initialUuidSucursal !== uuidSucursal) {
      setUuidSucursal(initialUuidSucursal);
    }
    // Only react to the external prop changing, not every local edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialUuidSucursal]);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    fetchSyncLog({
      uuid_sucursal: uuidSucursal || undefined,
      desde: desde || undefined,
      hasta: hasta || undefined,
      limit: 50,
    })
      .then((resp) => {
        if (cancelled) return;
        setItems(resp.items);
        setNextCursor(resp.next_cursor);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err : new Error(String(err)));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [uuidSucursal, desde, hasta]);

  function handleLoadMore(): void {
    if (!nextCursor) return;
    setIsLoadingMore(true);
    fetchSyncLog({
      uuid_sucursal: uuidSucursal || undefined,
      desde: desde || undefined,
      hasta: hasta || undefined,
      cursor: nextCursor,
      limit: 50,
    })
      .then((resp) => {
        setItems((prev) => [...prev, ...resp.items]);
        setNextCursor(resp.next_cursor);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err : new Error(String(err)));
      })
      .finally(() => setIsLoadingMore(false));
  }

  function handleUuidSucursalChange(value: string): void {
    setUuidSucursal(value);
    onUuidSucursalChange?.(value || null);
  }

  return (
    <div className="flex flex-col gap-3" data-testid="sync-log-tab">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium text-muted-foreground">
            {t('sync.log.filterSucursal', 'Sucursal')}
          </span>
          <select
            className="w-56 rounded-md border bg-background px-2 py-1 text-sm"
            value={uuidSucursal}
            onChange={(e) => handleUuidSucursalChange(e.target.value)}
            data-testid="sync-log-filter-sucursal"
          >
            <option value="">{t('sync.log.filterSucursalAll', 'Todas')}</option>
            {sucursales.map((s) => (
              <option key={s.uuid} value={s.uuid}>
                {s.nombre ?? s.uuid.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>

        <Label className="flex flex-col gap-1 text-xs">
          <span className="font-medium text-muted-foreground">
            {t('sync.log.filterDesde', 'Desde')}
          </span>
          <Input
            type="date"
            value={desde}
            onChange={(e) => setDesde(e.target.value)}
            data-testid="sync-log-filter-desde"
          />
        </Label>

        <Label className="flex flex-col gap-1 text-xs">
          <span className="font-medium text-muted-foreground">
            {t('sync.log.filterHasta', 'Hasta')}
          </span>
          <Input
            type="date"
            value={hasta}
            onChange={(e) => setHasta(e.target.value)}
            data-testid="sync-log-filter-hasta"
          />
        </Label>
      </div>

      {error ? (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="sync-log-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {error.message}
        </p>
      ) : isLoading && items.length === 0 ? (
        <p role="status" aria-live="polite" data-testid="sync-log-loading" className="text-sm text-muted-foreground">
          {t('sync.log.loading', 'Cargando...')}
        </p>
      ) : (
        <>
          <Table data-testid="sync-log-table">
            <TableCaption className="sr-only">
              {t('sync.log.caption', 'Histórico de ciclos de sincronización')}
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">{t('sync.log.col.sucursal', 'Sucursal')}</TableHead>
                <TableHead scope="col">{t('sync.log.col.timestampEvento', 'Fecha del ciclo')}</TableHead>
                <TableHead scope="col">{t('sync.log.col.enviadas', 'Enviadas')}</TableHead>
                <TableHead scope="col">{t('sync.log.col.exitosas', 'Exitosas')}</TableHead>
                <TableHead scope="col">{t('sync.log.col.fallidas', 'Fallidas')}</TableHead>
                <TableHead scope="col">{t('sync.log.col.conflictos', 'Conflictos')}</TableHead>
                <TableHead scope="col">{t('sync.log.col.duracion', 'Duración (ms)')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    role="status"
                    aria-live="polite"
                    data-testid="sync-log-empty"
                    className="text-center text-sm text-muted-foreground"
                  >
                    {t('sync.log.empty', 'No hay ciclos de sincronización para el filtro seleccionado.')}
                  </TableCell>
                </TableRow>
              ) : (
                items.map((row) => (
                  <TableRow key={row.uuid} data-testid={`sync-log-row-${row.uuid}`}>
                    <TableCell className="font-mono text-xs">
                      {sucursales.find((s) => s.uuid === row.uuid_sucursal)?.nombre ??
                        row.uuid_sucursal?.slice(0, 8) ??
                        '—'}
                    </TableCell>
                    <TableCell className="tabular-nums">{formatDate(row.timestamp_evento)}</TableCell>
                    <TableCell className="tabular-nums">{row.operaciones_enviadas ?? '—'}</TableCell>
                    <TableCell className="tabular-nums">{row.operaciones_exitosas ?? '—'}</TableCell>
                    <TableCell className="tabular-nums">{row.operaciones_fallidas ?? '—'}</TableCell>
                    <TableCell className="tabular-nums">{row.conflictos ?? '—'}</TableCell>
                    <TableCell className="tabular-nums">{row.duracion_ms ?? '—'}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>

          {nextCursor && (
            <div className="flex justify-center">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleLoadMore}
                disabled={isLoadingMore}
                data-testid="sync-log-load-more"
              >
                {isLoadingMore
                  ? t('sync.log.loadingMore', 'Cargando...')
                  : t('sync.log.loadMore', 'Cargar más')}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
