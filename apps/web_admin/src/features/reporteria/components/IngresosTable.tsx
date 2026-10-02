/**
 * `<IngresosTable />` — presentational table for HU-F17.1 operational
 * reports (web_admin).
 *
 * Mirrors the container/presentational split used by
 * `features/audit/components/LogTable.tsx`:
 *   - this file owns only the rendering;
 *   - `pages/Reporteria.tsx` owns SWR + filters.
 *
 * Accessibility (RNF-022 WCAG 2.1 AA):
 *   - <table> with <caption> + <th scope="col">
 *   - empty branch state -> one row with colspan={N}, role="status", aria-live="polite"
 *   - error state -> role="alert", aria-live="assertive"
 *   - sync_status rendered as plain text, not a colored badge, so colour
 *     is never the sole carrier of state.
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

import type { IngresoRead } from '../api/reporteriaSchema';
import { formatBackendTimestampLocal } from './dateRange';

export interface IngresosTableProps {
  items: IngresoRead[];
  isLoading: boolean;
  error: Error | null | undefined;
  caption: string;
}

const formatDate = formatBackendTimestampLocal;

export function IngresosTable({ items, isLoading, error, caption }: IngresosTableProps) {
  const { t } = useTranslation();

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="reporteria-ingresos-error"
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
        data-testid="reporteria-ingresos-loading"
        className="text-sm text-muted-foreground"
      >
        {t('reporteria.loading', 'Cargando ingresos...')}
      </p>
    );
  }

  return (
    <Table data-testid="reporteria-ingresos-table">
      <TableCaption className="sr-only">{caption}</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">
            {t('reporteria.ingresos.placa', 'Placa')}
          </TableHead>
          <TableHead scope="col">
            {t('reporteria.ingresos.consecutivo', 'Consecutivo')}
          </TableHead>
          <TableHead scope="col">
            {t('reporteria.ingresos.fechaIngreso', 'Fecha de ingreso')}
          </TableHead>
          <TableHead scope="col">
            {t('reporteria.ingresos.observaciones', 'Observaciones')}
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={4}
              role="status"
              aria-live="polite"
              data-testid="reporteria-ingresos-empty"
              className="text-center text-sm text-muted-foreground"
            >
              {t('reporteria.empty', 'No hay ingresos para la sucursal seleccionada.')}
            </TableCell>
          </TableRow>
        ) : (
          items.map((row) => (
            <TableRow key={row.uuid}>
              <TableCell className="font-mono">{row.placa ?? '—'}</TableCell>
              <TableCell className="font-mono">{row.consecutivo ?? '—'}</TableCell>
              <TableCell className="tabular-nums">{formatDate(row.fecha_ingreso)}</TableCell>
              <TableCell className="text-muted-foreground">
                {row.observaciones ?? '—'}
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}