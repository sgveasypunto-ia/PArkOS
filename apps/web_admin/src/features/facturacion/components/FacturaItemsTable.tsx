/**
 * `<FacturaItemsTable />` — invoice line items (REQ-X-04).
 *
 * Source: `GET /api/v1/facturacion/factura-detalle?uuid_factura=...` (the
 * factory mount; as of X.1a the endpoint does NOT honour the
 * `?uuid_factura=` filter — same bug as the pagos endpoint, fixed in
 * a follow-up). The page filters items by `item.uuid_factura === uuid`
 * as a safety net (defense in depth: server should also filter).
 *
 * Per-section error/loading: a 5xx on this endpoint shows the inline
 * alert but does NOT fatal the page (REQ-X-11).
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
import type { FacturaDetalleItem } from '../api/facturacionAdminApi';

function formatMoney(value: number): string {
  return value.toLocaleString('es-CO', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

export interface FacturaItemsTableProps {
  items: FacturaDetalleItem[];
  isLoading: boolean;
  error: Error | null | undefined;
  onRetry: () => void;
}

export function FacturaItemsTable({
  items,
  isLoading,
  error,
  onRetry,
}: FacturaItemsTableProps): JSX.Element {
  const { t } = useTranslation('facturacionAdmin');
  return (
    <div className="space-y-2">
      <h2 className="text-base font-semibold">
        {t('items.title', 'Líneas de la factura')}
      </h2>
      {error ? (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="factura-items-error"
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
          data-testid="factura-items-loading"
          className="text-sm text-muted-foreground"
        >
          {t('errors.sectionFail', 'Cargando…')}
        </p>
      ) : (
        <Table data-testid="factura-items-table">
          <TableCaption className="sr-only">
            {t('items.title', 'Líneas de la factura')}
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">
                {t('items.concepto', 'Concepto')}
              </TableHead>
              <TableHead scope="col" className="text-right">
                {t('items.cantidad', 'Cantidad')}
              </TableHead>
              <TableHead scope="col" className="text-right">
                {t('items.valorUnitario', 'Valor unitario')}
              </TableHead>
              <TableHead scope="col" className="text-right">
                {t('items.subtotal', 'Subtotal')}
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
                  data-testid="factura-items-empty"
                  className="text-center text-sm text-muted-foreground"
                >
                  {t('pagos.empty', 'Sin pagos registrados.')}
                </TableCell>
              </TableRow>
            ) : (
              items.map((row) => (
                <TableRow key={row.uuid} data-testid={`factura-item-row-${row.uuid}`}>
                  <TableCell>{row.concepto}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {row.cantidad}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMoney(row.valor_unitario)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">
                    {formatMoney(row.subtotal)}
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
