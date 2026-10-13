/**
 * `<FacturasTable />` — presentational table for HU-F17.3 reportería
 * financiera, tab "Facturas" (web_admin).
 *
 * Mirrors the container/presentational split `IngresosTable.tsx` already
 * uses: this file owns only the rendering; `pages/ReporteriaFinanciera.tsx`
 * owns SWR + filters.
 *
 * Column resolution (backend `reporte_facturas`, HU-F17.3):
 *   - `numero_completo` — `prefijo + consecutivo` from the joined
 *     `factura_electronica` row, `null` when the factura has no FE yet
 *     (rendered as "—", NOT confused with the FE tab's own `estado_dian`).
 *   - `iva` — `SUM(factura_impuestos.valor)` for the factura.
 *   - `estado` — closed `vigente | anulada` enum, rendered as a `<Badge>`
 *     (success / destructive) so the state reads without relying on
 *     color alone (the label itself carries the meaning).
 *
 * HU-X.2: the trailing "Detalle" cell renders a `<Link to={/facturacion/...}>`
 * (REQ-X-09) so the admin can drill down from the reporteria list
 * into the per-factura page (HU-X.1b). Uses lucide's `ExternalLink`
 * icon as a visual cue; the link text is in es-CO.
 *
 * Accessibility (RNF-022 WCAG 2.1 AA): same conventions as
 * `IngresosTable.tsx` (caption, `scope="col"`, status/alert live regions).
 */
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';

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

import type { ReporteFacturaItem } from '../api/reporteriaSchema';
import { formatBackendTimestampLocal } from './dateRange';

export interface FacturasTableProps {
  items: ReporteFacturaItem[];
  isLoading: boolean;
  error: Error | null | undefined;
  caption: string;
}

function formatMoney(value: number | null): string {
  if (value === null) return '—';
  return value.toLocaleString('es-CO', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

const formatDate = formatBackendTimestampLocal;

export function FacturasTable({ items, isLoading, error, caption }: FacturasTableProps) {
  const { t } = useTranslation();

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="reporteria-financiera-facturas-error"
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
        data-testid="reporteria-financiera-facturas-loading"
        className="text-sm text-muted-foreground"
      >
        {t('reporteriaFinanciera.loading', 'Cargando...')}
      </p>
    );
  }

  return (
    <Table data-testid="reporteria-financiera-facturas-table">
      <TableCaption className="sr-only">{caption}</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">
            {t('reporteriaFinanciera.facturas.numeroCompleto', 'Número')}
          </TableHead>
          <TableHead scope="col">{t('reporteriaFinanciera.facturas.fecha', 'Fecha')}</TableHead>
          <TableHead scope="col">
            {t('reporteriaFinanciera.facturas.subtotal', 'Subtotal')}
          </TableHead>
          <TableHead scope="col">
            {t('reporteriaFinanciera.facturas.descuento', 'Descuento')}
          </TableHead>
          <TableHead scope="col">{t('reporteriaFinanciera.facturas.iva', 'IVA')}</TableHead>
          <TableHead scope="col">{t('reporteriaFinanciera.facturas.total', 'Total')}</TableHead>
          <TableHead scope="col">{t('reporteriaFinanciera.facturas.estado', 'Estado')}</TableHead>
          <TableHead scope="col" className="text-right">
            {t('reporteriaFinanciera.facturas.acciones', 'Detalle')}
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={8}
              role="status"
              aria-live="polite"
              data-testid="reporteria-financiera-facturas-empty"
              className="text-center text-sm text-muted-foreground"
            >
              {t(
                'reporteriaFinanciera.facturas.empty',
                'No hay facturas para el rango seleccionado.',
              )}
            </TableCell>
          </TableRow>
        ) : (
          items.map((row) => (
            <TableRow key={row.uuid} data-testid={`reporteria-financiera-facturas-row-${row.uuid}`}>
              <TableCell className="font-mono">{row.numero_completo ?? '—'}</TableCell>
              <TableCell className="tabular-nums">{formatDate(row.created_at)}</TableCell>
              <TableCell className="tabular-nums">{formatMoney(row.subtotal)}</TableCell>
              <TableCell className="tabular-nums">{formatMoney(row.descuento)}</TableCell>
              <TableCell className="tabular-nums">{formatMoney(row.iva)}</TableCell>
              <TableCell className="tabular-nums font-medium">
                {formatMoney(row.total)}
              </TableCell>
              <TableCell>
                <Badge
                  variant={row.estado === 'vigente' ? 'success' : 'destructive'}
                  data-testid={`reporteria-financiera-facturas-estado-${row.uuid}`}
                >
                  {row.estado === 'vigente'
                    ? t('reporteriaFinanciera.facturas.estadoVigente', 'Vigente')
                    : t('reporteriaFinanciera.facturas.estadoAnulada', 'Anulada')}
                </Badge>
              </TableCell>
              <TableCell className="text-right">
                <Link
                  to={`/facturacion/${row.uuid}`}
                  className="inline-flex items-center gap-1 text-sm text-primary underline-offset-2 hover:underline"
                  data-testid={`reporteria-financiera-facturas-detalle-${row.uuid}`}
                >
                  {t('reporteriaFinanciera.facturas.verDetalle', 'Ver detalle')}
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                </Link>
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}
