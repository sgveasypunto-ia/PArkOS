/**
 * `<SyncConflict />` — HU-F19.2 "Conflictos" tab: cursor-paginated
 * `sync_conflict` listing, filterable by sucursal, with a side-by-side
 * `datos_local` vs `datos_cloud` diff viewer (BR2: read-only, no manual
 * resolution mechanism -- `resolucion` is the policy the sync worker
 * already applied, shown verbatim).
 */
import { Fragment, useEffect, useState } from 'react';
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

import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';

import { fetchSyncConflict } from '../api/syncApi';
import type { SyncConflictRead } from '../api/syncSchema';

export interface SyncConflictProps {
  initialUuidSucursal?: string | null;
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toISOString().replace('T', ' ').slice(0, 19);
}

function prettyJson(value: Record<string, unknown> | null): string {
  if (value === null) return '—';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export default function SyncConflict({
  initialUuidSucursal = null,
}: SyncConflictProps): JSX.Element {
  const { t } = useTranslation();
  const { sucursales } = useSucursalesDirectorio();

  const [uuidSucursal, setUuidSucursal] = useState<string>(initialUuidSucursal ?? '');
  const [items, setItems] = useState<SyncConflictRead[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [expandedUuid, setExpandedUuid] = useState<string | null>(null);

  useEffect(() => {
    if (initialUuidSucursal !== null && initialUuidSucursal !== uuidSucursal) {
      setUuidSucursal(initialUuidSucursal);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialUuidSucursal]);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    fetchSyncConflict({ uuid_sucursal: uuidSucursal || undefined, limit: 50 })
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
  }, [uuidSucursal]);

  function handleLoadMore(): void {
    if (!nextCursor) return;
    setIsLoadingMore(true);
    fetchSyncConflict({ uuid_sucursal: uuidSucursal || undefined, cursor: nextCursor, limit: 50 })
      .then((resp) => {
        setItems((prev) => [...prev, ...resp.items]);
        setNextCursor(resp.next_cursor);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err : new Error(String(err)));
      })
      .finally(() => setIsLoadingMore(false));
  }

  return (
    <div className="flex flex-col gap-3" data-testid="sync-conflict-tab">
      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium text-muted-foreground">
          {t('sync.conflict.filterSucursal', 'Sucursal')}
        </span>
        <select
          className="w-56 rounded-md border bg-background px-2 py-1 text-sm"
          value={uuidSucursal}
          onChange={(e) => setUuidSucursal(e.target.value)}
          data-testid="sync-conflict-filter-sucursal"
        >
          <option value="">{t('sync.conflict.filterSucursalAll', 'Todas')}</option>
          {sucursales.map((s) => (
            <option key={s.uuid} value={s.uuid}>
              {s.nombre ?? s.uuid.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>

      {error ? (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="sync-conflict-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {error.message}
        </p>
      ) : isLoading && items.length === 0 ? (
        <p
          role="status"
          aria-live="polite"
          data-testid="sync-conflict-loading"
          className="text-sm text-muted-foreground"
        >
          {t('sync.conflict.loading', 'Cargando...')}
        </p>
      ) : (
        <>
          <Table data-testid="sync-conflict-table">
            <TableCaption className="sr-only">
              {t('sync.conflict.caption', 'Conflictos de sincronización detectados')}
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">{t('sync.conflict.col.sucursal', 'Sucursal')}</TableHead>
                <TableHead scope="col">{t('sync.conflict.col.tabla', 'Tabla')}</TableHead>
                <TableHead scope="col">{t('sync.conflict.col.fecha', 'Fecha')}</TableHead>
                <TableHead scope="col">{t('sync.conflict.col.resolucion', 'Resolución')}</TableHead>
                <TableHead scope="col" className="text-right">
                  {t('sync.conflict.col.acciones', 'Acciones')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    role="status"
                    aria-live="polite"
                    data-testid="sync-conflict-empty"
                    className="text-center text-sm text-muted-foreground"
                  >
                    {t('sync.conflict.empty', 'No hay conflictos para el filtro seleccionado.')}
                  </TableCell>
                </TableRow>
              ) : (
                items.map((row) => (
                  <Fragment key={row.uuid}>
                    <TableRow data-testid={`sync-conflict-row-${row.uuid}`}>
                      <TableCell className="font-mono text-xs">
                        {sucursales.find((s) => s.uuid === row.uuid_sucursal)?.nombre ??
                          row.uuid_sucursal?.slice(0, 8) ??
                          '—'}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{row.tabla ?? '—'}</TableCell>
                      <TableCell className="tabular-nums">
                        {formatDate(row.timestamp_evento)}
                      </TableCell>
                      <TableCell>{row.resolucion ?? '—'}</TableCell>
                      <TableCell className="text-right">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            setExpandedUuid((cur) => (cur === row.uuid ? null : row.uuid))
                          }
                          data-testid={`sync-conflict-ver-diff-${row.uuid}`}
                        >
                          {expandedUuid === row.uuid
                            ? t('sync.conflict.hideDiff', 'Ocultar diff')
                            : t('sync.conflict.viewDiff', 'Ver diff')}
                        </Button>
                      </TableCell>
                    </TableRow>
                    {expandedUuid === row.uuid && (
                      <TableRow>
                        <TableCell colSpan={5}>
                          <div
                            className="grid grid-cols-1 gap-3 md:grid-cols-2"
                            data-testid={`sync-conflict-diff-${row.uuid}`}
                          >
                            <div className="rounded-md border bg-muted/20 p-3">
                              <h3 className="mb-1 text-xs font-semibold text-muted-foreground">
                                {t('sync.conflict.datosLocal', 'Datos local (sucursal)')}
                              </h3>
                              <pre className="overflow-x-auto whitespace-pre-wrap break-all text-xs">
                                {prettyJson(row.datos_local)}
                              </pre>
                            </div>
                            <div className="rounded-md border bg-muted/20 p-3">
                              <h3 className="mb-1 text-xs font-semibold text-muted-foreground">
                                {t('sync.conflict.datosCloud', 'Datos cloud')}
                              </h3>
                              <pre className="overflow-x-auto whitespace-pre-wrap break-all text-xs">
                                {prettyJson(row.datos_cloud)}
                              </pre>
                            </div>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
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
                data-testid="sync-conflict-load-more"
              >
                {isLoadingMore
                  ? t('sync.conflict.loadingMore', 'Cargando...')
                  : t('sync.conflict.loadMore', 'Cargar más')}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
