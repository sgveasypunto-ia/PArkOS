/**
 * `useSync.ts` — SWR hooks for the HU-F19.2 sync dashboard (web_admin).
 *
 * Same `STALE` convention as `features/reporteria/hooks/useReporteria.ts`.
 *
 * `useSyncHeatmap` is the one hook with real logic worth documenting:
 * there is NO backend endpoint that returns a 24h x N sucursales lag
 * history (HU-F19.1 only ships `sync/log`, `sync/conflict`, and a
 * CURRENT-moment `sync/estado` aggregate) -- see `bucketSyncLogByHour`'s
 * own docstring for how this client reconstructs an approximate one
 * from `sync/log` instead, and why it never reclassifies into verde/
 * amarillo/rojo while doing so.
 */
import { useMemo } from 'react';
import useSWR from 'swr';

import { fetchSyncConflict, fetchSyncEstado, fetchSyncLog } from '../api/syncApi';
import type {
  SyncConflictListResponse,
  SyncConflictQuery,
  SyncEstadoAgregadoResponse,
  SyncLogListResponse,
  SyncLogQuery,
  SyncLogRead,
} from '../api/syncSchema';
import type { HeatmapBranch, HeatmapCell } from '@/components/charts/HeatmapOcupacion';

const STALE = { revalidateOnFocus: false, dedupingInterval: 30_000 };

export function useSyncEstado() {
  return useSWR<SyncEstadoAgregadoResponse>('sync:estado', fetchSyncEstado, STALE);
}

export function syncLogKey(q: SyncLogQuery): string {
  return [
    'sync:log',
    q.uuid_sucursal ?? '',
    q.desde ?? '',
    q.hasta ?? '',
    q.cursor ?? '',
    q.limit ?? 50,
  ].join('::');
}

export function useSyncLog(query: SyncLogQuery | null) {
  return useSWR<SyncLogListResponse>(
    query ? syncLogKey(query) : null,
    () => fetchSyncLog(query as SyncLogQuery),
    STALE,
  );
}

export function syncConflictKey(q: SyncConflictQuery): string {
  return ['sync:conflict', q.uuid_sucursal ?? '', q.cursor ?? '', q.limit ?? 50].join('::');
}

export function useSyncConflict(query: SyncConflictQuery | null) {
  return useSWR<SyncConflictListResponse>(
    query ? syncConflictKey(query) : null,
    () => fetchSyncConflict(query as SyncConflictQuery),
    STALE,
  );
}

// ---------------------------------------------------------------------------
// Heatmap reconstruction from `sync/log` (HU-F19.2 design decision).
// ---------------------------------------------------------------------------

/** Safety bound on the `sync/log` pagination sweep below -- 10 pages x
 *  200 rows/page = 2000 rows max per heatmap refresh, so a very chatty
 *  24h window degrades to a partial (not frozen) heatmap instead of an
 *  unbounded fetch loop. */
const MAX_HEATMAP_PAGES = 10;
const HEATMAP_PAGE_LIMIT = 200;

function utcDateOnly(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/**
 * `sync_log.timestamp_evento` is a naive `DateTime(timezone=False)`
 * column (UTC wall-clock, no offset in the serialized string). Parsing
 * a timezone-less ISO string with the bare `Date` constructor treats it
 * as LOCAL time, which would silently shift both the computed lag and
 * the UTC hour bucket by the host's offset. Force UTC interpretation by
 * appending `Z` when the string carries no zone indicator already.
 */
function parseUtcTimestamp(raw: string): Date {
  const hasZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(raw);
  return new Date(hasZone ? raw : `${raw}Z`);
}

/**
 * Pages through `GET /admin/sync/log` (no `uuid_sucursal` filter --
 * every permitted branch) for the last ~24h, following `next_cursor`
 * until it is `null` or `MAX_HEATMAP_PAGES` is reached.
 */
export async function fetchSyncLogLast24h(now: Date = new Date()): Promise<SyncLogRead[]> {
  const hasta = utcDateOnly(now);
  const desde = utcDateOnly(new Date(now.getTime() - 24 * 60 * 60 * 1000));

  const rows: SyncLogRead[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < MAX_HEATMAP_PAGES; page += 1) {
    const resp = await fetchSyncLog({ desde, hasta, cursor, limit: HEATMAP_PAGE_LIMIT });
    rows.push(...resp.items);
    if (!resp.next_cursor) break;
    cursor = resp.next_cursor;
  }
  return rows;
}

/**
 * Reconstructs a per-(sucursal, UTC hour) lag-in-seconds grid from raw
 * `sync_log` rows, because HU-F19.1 ships no endpoint that already
 * aggregates lag by hour.
 *
 * For each branch, rows are sorted by `timestamp_evento` ascending; the
 * lag charted for a given sync cycle is the gap until that branch's
 * NEXT recorded cycle (or until `now`, for its most recent row) -- the
 * exact same `now - timestamp_evento` arithmetic BR1 / `_clasificar_sync_estado`
 * uses server-side, just evaluated at each historical point instead of
 * only "now". This produces a plain NUMBER OF SECONDS per cell -- it
 * does NOT reclassify into verde/amarillo/rojo (that stays the server's
 * job, surfaced verbatim by `useSyncEstado` for the dashboard's resumen).
 *
 * Known, disclosed limitation: an hour with zero `sync_log` rows for a
 * branch renders as an empty/blank cell (0 lag, opacity 0 in
 * `HeatmapOcupacion`'s existing convention) rather than "worst-case".
 * That is acceptable because the authoritative tri-color signal for an
 * admin is the resumen counts from `/admin/sync/estado`, never this
 * heatmap -- the heatmap is supplementary historical color, same
 * "proxy, not ground truth" spirit `HeatmapOcupacion.tsx`'s own
 * docstring already documents for its original ingresos use.
 */
export function bucketSyncLogByHour(
  rows: readonly SyncLogRead[],
  now: Date = new Date(),
): HeatmapCell[] {
  const byBranch = new Map<string, SyncLogRead[]>();
  for (const row of rows) {
    if (!row.uuid_sucursal || !row.timestamp_evento) continue;
    const list = byBranch.get(row.uuid_sucursal) ?? [];
    list.push(row);
    byBranch.set(row.uuid_sucursal, list);
  }

  const maxLagByCell = new Map<string, number>();
  for (const [uuidSucursal, branchRows] of byBranch) {
    const sorted = [...branchRows].sort(
      (a, b) =>
        parseUtcTimestamp(a.timestamp_evento as string).getTime() -
        parseUtcTimestamp(b.timestamp_evento as string).getTime(),
    );
    for (let i = 0; i < sorted.length; i += 1) {
      const current = sorted[i]!;
      const currentTs = parseUtcTimestamp(current.timestamp_evento as string);
      const nextTs =
        i + 1 < sorted.length ? parseUtcTimestamp(sorted[i + 1]!.timestamp_evento as string) : now;
      const lagSeg = Math.max(0, Math.round((nextTs.getTime() - currentTs.getTime()) / 1000));
      const hora = currentTs.getUTCHours();
      const key = `${uuidSucursal}:${hora}`;
      maxLagByCell.set(key, Math.max(maxLagByCell.get(key) ?? 0, lagSeg));
    }
  }

  const cells: HeatmapCell[] = [];
  for (const [key, lagSeg] of maxLagByCell) {
    const [uuidSucursal, horaStr] = key.split(':');
    cells.push({
      uuid_sucursal: uuidSucursal as string,
      hora: Number(horaStr),
      ingresos_count: lagSeg,
    });
  }
  return cells;
}

/**
 * Combines the branch list from `/admin/sync/estado` (so the heatmap's
 * rows always match the dashboard's resumen, even for a branch with
 * zero `sync_log` rows in the window) with the bucketed lag grid above.
 */
export function useSyncHeatmap(): {
  data: HeatmapCell[];
  sucursales: HeatmapBranch[];
  isLoading: boolean;
  error: Error | undefined;
} {
  const estado = useSyncEstado();
  const logSweep = useSWR<SyncLogRead[]>('sync:heatmap:log-sweep:last24h', () =>
    fetchSyncLogLast24h(),
  );

  const data = useMemo(
    () => bucketSyncLogByHour(logSweep.data ?? []),
    [logSweep.data],
  );
  const sucursales = useMemo<HeatmapBranch[]>(
    () =>
      (estado.data?.items ?? []).map((item) => ({
        uuid: item.uuid_sucursal,
        nombre: item.nombre,
      })),
    [estado.data],
  );

  return {
    data,
    sucursales,
    isLoading: estado.isLoading || logSweep.isLoading,
    error: estado.error ?? logSweep.error,
  };
}
