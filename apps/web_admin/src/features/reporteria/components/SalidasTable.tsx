/**
 * `<SalidasTable />` — presentational table for HU-F17.1 operational
 * reports (web_admin).
 *
 * Sister of `<IngresosTable />`. Same accessibility pattern (caption +
 * scope col + role="status" empty + role="alert" error) and same
 * container/presentational split. The joined placa (read off the
 * LEFT-JOINed `prod.ingreso` row) is rendered as a fallback when the
 * exit has no linked ingreso; a missing `fecha_salida` shows "—"
 * because the column is nullable by design.
 */
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

import type { SalidaListRead } from '../api/reporteriaSchema';
import { formatBackendTimestampLocal } from './dateRange';

export interface SalidasTableProps {
  items: SalidaListRead[];
  isLoading: boolean;
  error: Error | null | undefined;
  caption: string;
}

const formatDate = formatBackendTimestampLocal;

export function SalidasTable({ items, isLoading, error, caption }: SalidasTableProps) {
  const { t } = useTranslation();

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="reporteria-salidas-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {error.message}
      </p>
    );
  }

  if (isLoading && items.length === 0) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="reporteria-salidas-loading"
        className="text-sm text-muted-foreground"
      >
        {t('reporteria.loading', 'Cargando salidas...')}
      </p>
    );
  }

  return (
    <Table data-testid="reporteria-salidas-table">
      <TableCaption className="sr-only">{caption}</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">
            {t('reporteria.salidas.placa', 'Placa')}
          </TableHead>
          <TableHead scope="col">
            {t('reporteria.salidas.consecutivo', 'Consecutivo')}
          </TableHead>
          <TableHead scope="col">
            {t('reporteria.salidas.fechaSalida', 'Fecha de salida')}
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={3}
              role="status"
              aria-live="polite"
              data-testid="reporteria-salidas-empty"
              className="text-center text-sm text-muted-foreground"
            >
              {t('reporteria.empty', 'No hay salidas para la sucursal seleccionada.')}
            </TableCell>
          </TableRow>
        ) : (
          items.map((row) => (
            <TableRow key={row.uuid}>
              <TableCell className="font-mono">{row.placa ?? '—'}</TableCell>
              <TableCell className="font-mono">{row.consecutivo ?? '—'}</TableCell>
              <TableCell className="tabular-nums">{formatDate(row.fecha_salida)}</TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}