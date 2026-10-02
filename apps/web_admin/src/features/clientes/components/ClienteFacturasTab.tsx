/**
 * `<ClienteFacturasTab />` — tab "Facturas" de `ClienteDetalle`
 * (HU-F20.1). Read-only: no create/edit affordances.
 *
 * Calls `fetchReporteriaFacturas({ uuid_cliente: uuidCliente })` (no
 * `uuid_sucursal` -- cross-branch cliente view). Backend contract
 * (`reporte_facturas`, `backend/.../api/v1/reporteria.py`): both
 * `uuid_sucursal` and `uuid_cliente` are optional query params, 422
 * `{"error":"missing_filter"}` if neither is given. The response
 * envelope's top-level `uuid_sucursal` is nullable (null in cliente-only
 * mode, since a client's invoices can legitimately span branches) --
 * this tab never reads that top-level field, only the per-row
 * `ReporteFacturaItem.uuid_sucursal`, rendered as its own column since
 * rows here can come from different branches.
 */
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';

import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';

import { fetchReporteriaFacturas } from '@/features/reporteria/api/reporteriaApi';

export interface ClienteFacturasTabProps {
  uuidCliente: string;
}

function formatMoney(value: number | null): string {
  if (value === null) return '—';
  return value.toLocaleString('es-CO', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export function ClienteFacturasTab({ uuidCliente }: ClienteFacturasTabProps): JSX.Element {
  const { t } = useTranslation();

  const { data, error, isLoading } = useSWR(
    `/api/v1/admin/reporteria/facturas::uuid_cliente::${uuidCliente}`,
    () => fetchReporteriaFacturas({ uuid_cliente: uuidCliente, limit: 50 }),
    { revalidateOnFocus: false },
  );

  if (isLoading) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="cliente-facturas-loading"
        className="text-sm text-muted-foreground"
      >
        {t('common.loading', 'Cargando…')}
      </p>
    );
  }

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="cliente-facturas-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {error instanceof Error ? error.message : t('clienteFacturas.error', 'No se pudieron cargar las facturas.')}
      </p>
    );
  }

  const items = data?.items ?? [];

  if (items.length === 0) {
    return (
      <p
        role="status"
        data-testid="cliente-facturas-empty"
        className="text-sm text-muted-foreground"
      >
        {t('clienteFacturas.empty', 'Este cliente no tiene facturas registradas.')}
      </p>
    );
  }

  return (
    <Table data-testid="cliente-facturas-table">
      <TableCaption className="sr-only">
        {t('clienteFacturas.caption', 'Facturas del cliente')}
      </TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">{t('clienteFacturas.numero', 'Número')}</TableHead>
          <TableHead scope="col">{t('clienteFacturas.fecha', 'Fecha')}</TableHead>
          <TableHead scope="col">{t('clienteFacturas.sucursal', 'Sucursal')}</TableHead>
          <TableHead scope="col">{t('clienteFacturas.subtotal', 'Subtotal')}</TableHead>
          <TableHead scope="col">{t('clienteFacturas.descuento', 'Descuento')}</TableHead>
          <TableHead scope="col">{t('clienteFacturas.iva', 'IVA')}</TableHead>
          <TableHead scope="col">{t('clienteFacturas.total', 'Total')}</TableHead>
          <TableHead scope="col">{t('clienteFacturas.estado', 'Estado')}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((row) => (
          <TableRow key={row.uuid} data-testid={`cliente-factura-row-${row.uuid}`}>
            <TableCell className="font-mono">{row.numero_completo ?? '—'}</TableCell>
            <TableCell className="tabular-nums">{row.created_at}</TableCell>
            <TableCell>{row.uuid_sucursal ?? '—'}</TableCell>
            <TableCell className="tabular-nums">{formatMoney(row.subtotal)}</TableCell>
            <TableCell className="tabular-nums">{formatMoney(row.descuento)}</TableCell>
            <TableCell className="tabular-nums">{formatMoney(row.iva)}</TableCell>
            <TableCell className="tabular-nums font-medium">{formatMoney(row.total)}</TableCell>
            <TableCell>
              <Badge
                variant={row.estado === 'vigente' ? 'success' : 'destructive'}
                data-testid={`cliente-factura-estado-${row.uuid}`}
              >
                {row.estado === 'vigente'
                  ? t('clienteFacturas.estadoVigente', 'Vigente')
                  : t('clienteFacturas.estadoAnulada', 'Anulada')}
              </Badge>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
