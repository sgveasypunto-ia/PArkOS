/**
 * `<Listado />` — F9.2 listado paginado de suscripciones con
 * búsqueda cliente-side (HU-F9.2, REQ-OPS-182).
 *
 * Layout:
 *   - Header con título i18n.
 *   - Input de búsqueda (`data-testid="listado-search-input"`) →
 *     filtra case-insensitive por cliente OR identificación SIN
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
 * Data fetching: `useSuscripcionesActivas` -> `GET /api/v1/clientes/subscripciones-activas`
 * (branch-scoped server-side, enriched with cliente/plan/dias_restantes). The raw
 * `/clientes/subscripciones-cliente` CRUD list only carries FKs (no client/plan names), and
 * the old `/api/v1/suscripciones-cliente` path never existed (404).
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@parkos/ui-kit/hooks';

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

import type { SubscripcionActivaItem } from '../api/cuposApi';
import { useSuscripcionesActivas } from '../hooks/useSuscripcionesActivas';

export interface ListadoRow {
  uuid: string;
  cliente_nombre: string;
  numero_identificacion: string;
  plan_nombre: string;
  fecha_vencimiento: string; // ISO YYYY-MM-DD ('' when unknown)
  dias_restantes: number | null;
  estado: 'activa' | 'vencida';
}

/** Maps the backend item; `dias_restantes` is server-computed (Bogota calendar), never recomputed here. */
function toRow(i: SubscripcionActivaItem): ListadoRow {
  const dias = i.dias_restantes ?? null;
  return {
    uuid: i.uuid,
    cliente_nombre: [i.cliente.nombre, i.cliente.apellido].filter(Boolean).join(' '),
    numero_identificacion: i.cliente.numero_identificacion ?? '',
    plan_nombre: i.plan.tipo ?? '',
    fecha_vencimiento: i.fecha_vencimiento ?? '',
    dias_restantes: dias,
    estado: dias !== null && dias < 0 ? 'vencida' : 'activa',
  };
}

/** Case-insensitive substring search over cliente name OR identification. Empty query passes all. */
function filterListado(rows: ListadoRow[], query: string): ListadoRow[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter(
    (r) =>
      r.cliente_nombre.toLowerCase().includes(q) ||
      r.numero_identificacion.toLowerCase().includes(q),
  );
}

export function Listado(): JSX.Element {
  const { t } = useTranslation('suscripciones');
  const { sucursal } = useAuth();
  const uuid_sucursal = sucursal?.uuid ?? null;
  const [search, setSearch] = useState('');
  const { data, error } = useSuscripcionesActivas(uuid_sucursal);

  const rows = useMemo(() => (data ?? []).map(toRow), [data]);
  const filtered = useMemo(
    () => filterListado(rows, search),
    [rows, search],
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
          defaultValue: 'Buscar por cliente o identificación',
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
            <TableRow key={r.uuid} data-testid={`listado-row-${r.uuid}`}>
              <TableCell>{r.cliente_nombre}</TableCell>
              <TableCell>{r.plan_nombre}</TableCell>
              <TableCell>{r.fecha_vencimiento}</TableCell>
              <TableCell data-testid={`listado-diasrestantes-${r.uuid}`}>
                {r.dias_restantes ?? '—'}
              </TableCell>
              <TableCell>
                <Badge
                  variant={r.estado === 'vencida' ? 'destructive' : 'default'}
                  data-testid={`listado-estado-${r.uuid}`}
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
