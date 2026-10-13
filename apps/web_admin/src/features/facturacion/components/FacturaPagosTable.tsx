/**
 * `<FacturaPagosTable />` — payment events for a factura (REQ-X-06).
 *
 * Source: `GET /api/v1/facturacion/factura-pagos?uuid_factura=...` (X.1a
 * fix). The badge color per `medio_pago` is semantic — never the only
 * channel (WCAG 2.1 AA).
 */
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
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
import type { FacturaPagoItem } from '../api/facturacionAdminApi';

function formatMoney(value: number): string {
  return value.toLocaleString('es-CO', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  // Use the same pattern as the reporteria dateRange util (no
  // timezone shift, the BE serializes naive UTC).
  const hasTzDesignator = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  const d = new Date(hasTzDesignator ? iso : `${iso}Z`);
  return d.toLocaleString('es-CO', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function medioPagoBadge(medio: string | null): JSX.Element {
  const m = (medio ?? '').toLowerCase();
  const variant: 'default' | 'secondary' | 'outline' = 'secondary';
  return (
    <Badge variant={variant} data-testid={`factura-pago-medio-${m || 'none'}`}>
      {medio ?? '—'}
    </Badge>
  );
}

function tipoMovimientoBadge(tipo: string | null): JSX.Element {
  const key = (tipo ?? '').toLowerCase();
  const variant = key === 'reverso' ? 'destructive' : 'success';
  return (
    <Badge variant={variant} data-testid={`factura-pago-tipo-${key || 'none'}`}>
      {tipo ?? '—'}
    </Badge>
  );
}

export interface FacturaPagosTableProps {
  pagos: FacturaPagoItem[];
  isLoading: boolean;
  error: Error | null | undefined;
  onRetry: () => void;
}

export function FacturaPagosTable({
  pagos,
  isLoading,
  error,
  onRetry,
}: FacturaPagosTableProps): JSX.Element {
  const { t } = useTranslation('facturacionAdmin');
  return (
    <div className="space-y-2">
      <h2 className="text-base font-semibold">{t('pagos.title', 'Pagos')}</h2>
      {error ? (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="factura-pagos-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('errors.sectionFail', 'No se pudo cargar esta sección.')}{' '}
          <Button type="button" size="sm" variant="ghost" onClick={onRetry}>
            {t('errors.retry', 'Reintentar')}
          </Button>
        </p>
      ) : isLoading && pagos.length === 0 ? (
        <p
          role="status"
          aria-live="polite"
          data-testid="factura-pagos-loading"
          className="text-sm text-muted-foreground"
        >
          {t('errors.sectionFail', 'Cargando…')}
        </p>
      ) : (
        <Table data-testid="factura-pagos-table">
          <TableCaption className="sr-only">
            {t('pagos.title', 'Pagos')}
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">
                {t('pagos.timestamp', 'Fecha')}
              </TableHead>
              <TableHead scope="col">
                {t('pagos.medioPago', 'Medio')}
              </TableHead>
              <TableHead scope="col" className="text-right">
                {t('pagos.valor', 'Valor')}
              </TableHead>
              <TableHead scope="col">
                {t('pagos.referencia', 'Referencia')}
              </TableHead>
              <TableHead scope="col">
                {t('pagos.tipoMovimiento', 'Tipo')}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pagos.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={5}
                  role="status"
                  aria-live="polite"
                  data-testid="factura-pagos-empty"
                  className="text-center text-sm text-muted-foreground"
                >
                  {t('pagos.empty', 'Sin pagos registrados.')}
                </TableCell>
              </TableRow>
            ) : (
              pagos.map((row) => (
                <TableRow
                  key={row.uuid}
                  data-testid={`factura-pago-row-${row.uuid}`}
                >
                  <TableCell className="text-sm tabular-nums">
                    {formatDate(row.timestamp_evento)}
                  </TableCell>
                  <TableCell>{medioPagoBadge(row.medio_pago)}</TableCell>
                  <TableCell className="text-right tabular-nums font-medium">
                    {formatMoney(row.valor)}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {row.referencia ?? '—'}
                  </TableCell>
                  <TableCell>{tipoMovimientoBadge(row.tipo_movimiento)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
