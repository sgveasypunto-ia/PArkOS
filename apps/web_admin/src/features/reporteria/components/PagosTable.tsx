/**
 * `<PagosTable />` — presentational table for HU-F17.3 reportería
 * financiera, tab "Pagos".
 *
 * BR2: rows are already netted (`pago - reverso`) and grouped by
 * `(fecha, medio_pago)` server-side — a `tipo_movimiento='reverso'` row
 * is never a separate line here, it has already been subtracted into its
 * bucket.
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

import type { ReportePagoMedioItem } from '../api/reporteriaSchema';

export interface PagosTableProps {
  items: ReportePagoMedioItem[];
  isLoading: boolean;
  error: Error | null | undefined;
  caption: string;
}

function formatMoney(value: number): string {
  return value.toLocaleString('es-CO', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export function PagosTable({ items, isLoading, error, caption }: PagosTableProps) {
  const { t } = useTranslation();

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="reporteria-financiera-pagos-error"
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
        data-testid="reporteria-financiera-pagos-loading"
        className="text-sm text-muted-foreground"
      >
        {t('reporteriaFinanciera.loading', 'Cargando...')}
      </p>
    );
  }

  return (
    <Table data-testid="reporteria-financiera-pagos-table">
      <TableCaption className="sr-only">{caption}</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">{t('reporteriaFinanciera.pagos.fecha', 'Fecha')}</TableHead>
          <TableHead scope="col">
            {t('reporteriaFinanciera.pagos.medioPago', 'Medio de pago')}
          </TableHead>
          <TableHead scope="col">
            {t('reporteriaFinanciera.pagos.montoNeto', 'Monto neto (pago - reverso)')}
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
              data-testid="reporteria-financiera-pagos-empty"
              className="text-center text-sm text-muted-foreground"
            >
              {t('reporteriaFinanciera.pagos.empty', 'No hay pagos para el rango seleccionado.')}
            </TableCell>
          </TableRow>
        ) : (
          items.map((row) => (
            <TableRow key={`${row.fecha}::${row.medio_pago}`}>
              <TableCell className="tabular-nums">{row.fecha}</TableCell>
              <TableCell className="capitalize">{row.medio_pago}</TableCell>
              <TableCell className="tabular-nums font-medium">
                {formatMoney(row.monto_neto)}
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}
