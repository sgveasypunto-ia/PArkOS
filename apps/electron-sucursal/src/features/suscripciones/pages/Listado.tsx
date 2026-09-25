/**
 * `<Listado />` — F9.2 listado paginado de suscripciones con
 * búsqueda cliente-side (HU-F9.2, REQ-OPS-182).
 *
 * Layout:
 *   - Header con título i18n.
 *   - Input de búsqueda (`data-testid="listado-search-input"`) →
 *     filtra case-insensitive por `placa` OR `cliente_nombre` SIN
 *     emitir un nuevo GET (filter is client-side, no SWR mutate).
 *   - DataTable con 5 columnas: cliente | plan | fecha_vencimiento |
 *     dias_restantes | estado (badge).
 *   - Filtro: vencidas (estado='vencida') se renderizan con badge
 *     destructive; el listado general del plan.md:2102 las incluye,
 *     el banner NO (REQ-OPS-181 filter lives at the hook layer).
 *
 * Ruta: `/suscripciones` (registrada en `App.tsx`). El F9.1 wizard
 * vive en `/suscripciones/venta` y permanece inalterado.
 *
 * Data fetching: SWR over `GET /api/v1/suscripciones-cliente?uuid_sucursal=X`
 * (Path A — paginado por cursor, plan.md:2099). El hook here is
 * intentionally minimal; the polling cadence is the same as
 * `useSuscripcionesProximasVencer` but the SWR key is distinct.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';

import { useAuth } from '@parkos/ui-kit/hooks';
import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';

const ONE_DAY_MS = 86_400_000;

export interface ListadoRow {
  uuid: string;
  placa: string;
  cliente_nombre: string;
  plan_nombre: string;
  fecha_vencimiento: string; // ISO YYYY-MM-DD
  estado: 'activa' | 'vencida' | 'suspendida';
}

/**
 * Pure helper — case-insensitive substring search over `placa` OR
 * `cliente_nombre`. Empty query passes the rows through (REQ-OPS-182
 * "empty search shows all rows"). Exported for testability.
 */
function filterListado(rows: ListadoRow[], query: string): ListadoRow[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter(
    (r) =>
      r.placa.toLowerCase().includes(q) ||
      r.cliente_nombre.toLowerCase().includes(q),
  );
}

/**
 * Pure helper — days remaining from `now` to `fecha_vencimiento`.
 * Negative means already expired (rendered via badge, NOT in the
 * banner hook — REQ-OPS-181 filter excludes those).
 */
function diasRestantes(fecha_vencimiento: string, now: Date): number {
  const v = new Date(`${fecha_vencimiento}T00:00:00Z`).getTime();
  return Math.floor((v - now.getTime()) / ONE_DAY_MS);
}

export function Listado(): JSX.Element {
  const { t } = useTranslation('suscripciones');
  const { sucursal } = useAuth();
  const accessToken = useAuthStore((s) => s.accessToken);
  const uuid_sucursal = sucursal?.uuid ?? null;
  const [search, setSearch] = useState('');

  const key =
    uuid_sucursal && accessToken
      ? `/api/v1/suscripciones-cliente?uuid_sucursal=${uuid_sucursal}`
      : null;

  const fetcher = async (k: string): Promise<ListadoRow[]> => {
    const { parkosFetch } = await import('@parkos/ui-kit/fetch');
    const raw = (await parkosFetch<unknown>(k)) as ListadoRow[];
    if (!Array.isArray(raw)) return [];
    return raw;
  };

  const { data, error } = useSWR<ListadoRow[]>(key, fetcher, {
    dedupingInterval: 30_000,
    shouldRetryOnError: (err) => {
      if (err instanceof ParkosHttpError) {
        return err.status !== 401 && err.status !== 403 && err.status !== 404;
      }
      return true;
    },
    onError: (err) => {
      if (err instanceof ParkosHttpError && err.status === 401) {
        useAuthStore.getState().clear();
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('parkos:auth:cleared'));
        }
      }
    },
  });

  const filtered = useMemo(
    () => filterListado(data ?? [], search),
    [data, search],
  );

  return (
    // F31.3 rediseño: `max-w-5xl mx-auto` — sin tope, la tabla de 5
    // columnas se estiraba ilegible en 4K/ultrawide (columnas con
    // metros de espacio en blanco). `w-full` conserva 320-480px sin
    // recorte (el `<Table>` de shadcn ya envuelve en `overflow-auto`
    // propio para el caso de que 5 columnas no quepan).
    <div className="mx-auto w-full max-w-5xl space-y-4 p-4" data-testid="listado-page">
      <header>
        <h1 className="text-xl font-semibold">
          {t('listado.titulo', { defaultValue: 'Suscripciones' })}
        </h1>
      </header>
      <Input
        data-testid="listado-search-input"
        placeholder={t('listado.searchPlaceholder', {
          defaultValue: 'Buscar por placa o cliente',
        })}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {error && (
        <p data-testid="listado-error" className="text-sm text-destructive" role="alert">
          {t('error', { defaultValue: 'Error al cargar suscripciones.' })}
        </p>
      )}
      <Table data-testid="listado-table">
        <TableHeader>
          <TableRow>
            <TableHead>{t('listado.colCliente', { defaultValue: 'Cliente' })}</TableHead>
            <TableHead>{t('listado.colPlan', { defaultValue: 'Plan' })}</TableHead>
            <TableHead>{t('listado.colFechaVencimiento', { defaultValue: 'Fecha vencimiento' })}</TableHead>
            <TableHead>{t('listado.colDiasRestantes', { defaultValue: 'Días restantes' })}</TableHead>
            <TableHead>{t('listado.colEstado', { defaultValue: 'Estado' })}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filtered.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} data-testid="listado-empty">
                <span className="text-muted-foreground">
                  {t('vacio', { defaultValue: 'Sin suscripciones activas.' })}
                </span>
              </TableCell>
            </TableRow>
          )}
          {filtered.map((r) => (
            <TableRow key={r.uuid} data-testid={`listado-row-${r.placa}`}>
              <TableCell>{r.cliente_nombre}</TableCell>
              <TableCell>{r.plan_nombre}</TableCell>
              <TableCell>{r.fecha_vencimiento}</TableCell>
              <TableCell data-testid={`listado-diasrestantes-${r.placa}`}>
                {diasRestantes(r.fecha_vencimiento, new Date())}
              </TableCell>
              <TableCell>
                <Badge
                  variant={r.estado === 'vencida' ? 'destructive' : 'default'}
                  data-testid={`listado-estado-${r.placa}`}
                >
                  {t(r.estado, { defaultValue: r.estado })}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
