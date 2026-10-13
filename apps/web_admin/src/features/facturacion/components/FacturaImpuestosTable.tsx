/**
 * `<FacturaImpuestosTable />` — IVA rows for a factura (REQ-X-05).
 *
 * Source: `GET /api/v1/facturacion/factura-impuestos?uuid_factura=...`.
 * Same factory-ignores-filter caveat as items (X.1a only fixed the
 * pagos endpoint).
 */
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { FacturaImpuestoItem } from '../api/facturacionAdminApi';

function formatMoney(value: number | null): string {
  if (value === null) return '—';
  return value.toLocaleString('es-CO', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

function formatPercent(value: number | null): string {
  if (value === null) return '—';
  return `${(value * 100).toLocaleString('es-CO', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })}%`;
}

export interface FacturaImpuestosTableProps {
  items: FacturaImpuestoItem[];
  isLoading: boolean;
  error: Error | null | undefined;
  onRetry: () => void;
}

export function FacturaImpuestosTable({
  items,
  isLoading,
  error,
  onRetry,
}: FacturaImpuestosTableProps): JSX.Element {
  const { t } = useTranslation('facturacionAdmin');
  return (
    <div className="space-y-2">
      <h2 className="text-base font-semibold">
        {t('impuestos.title', 'Impuestos')}
      </h2>
      {error ? (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="factura-impuestos-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('errors.sectionFail', 'No se pudo cargar esta sección.')}{' '}
          <Button type="button" size="sm" variant="ghost" onClick={onRetry}>
            {t('errors.retry', 'Reintentar')}
          </Button>
        </p>
      ) : isLoading && items.length === 0 ? (
        <p
          role="status"
          aria-live="polite"
          data-testid="factura-impuestos-loading"
          className="text-sm text-muted-foreground"
        >
          {t('errors.sectionFail', 'Cargando…')}
        </p>
      ) : (
        <Table data-testid="factura-impuestos-table">
          <TableCaption className="sr-only">
            {t('impuestos.title', 'Impuestos')}
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">
                {t('impuestos.nombre', 'Impuesto')}
              </TableHead>
              <TableHead scope="col" className="text-right">
                {t('impuestos.porcentaje', '%')}
              </TableHead>
              <TableHead scope="col" className="text-right">
                {t('impuestos.baseCalculo', 'Base')}
              </TableHead>
              <TableHead scope="col" className="text-right">
                {t('impuestos.valor', 'Valor')}
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
                  data-testid="factura-impuestos-empty"
                  className="text-center text-sm text-muted-foreground"
                >
                  {t('pagos.empty', 'Sin pagos registrados.')}
                </TableCell>
              </TableRow>
            ) : (
              items.map((row) => (
                <TableRow
                  key={row.uuid}
                  data-testid={`factura-impuesto-row-${row.uuid}`}
                >
                  <TableCell>
                    {row.uuid_impuesto
                      ? row.uuid_impuesto.slice(0, 8)
                      : '—'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatPercent(row.porcentaje_aplicado)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMoney(row.base_calculo)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">
                    {formatMoney(row.valor)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
