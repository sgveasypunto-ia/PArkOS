/**
 * `<FeTable />` — presentational table for HU-F17.3 reportería financiera,
 * tab "FE" (facturación electrónica / DIAN ack state).
 *
 * BR1: ``estado_dian`` (the raw `prod.v_factura_electronica_acuse.estado`
 * value) is DISTINCT from a factura's own internal `estado`
 * (vigente/anulada, shown in `<FacturasTable />`). This table labels the
 * column explicitly "Estado DIAN" and never reuses the vigente/anulada
 * badge styling, so the two concepts cannot be visually conflated.
 *
 * ``estado_dian`` is rendered as plain text (not a `<Badge>` with a fixed
 * palette): its real domain has 8 values (`pendiente|enviado|ack|error|
 * aceptado|rechazado|timeout|en_proceso`, see the backend's
 * `_ESTADO_DIAN_VALUES` comment) and keeps growing as the DIAN dispatcher
 * adds states — a hardcoded color-per-value map would silently fall back
 * to "unstyled" for values this UI has never seen, which is actually the
 * safer default here.
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

import type { ReporteFeItem } from '../api/reporteriaSchema';
import { formatBackendTimestampLocal } from './dateRange';

export interface FeTableProps {
  items: ReporteFeItem[];
  isLoading: boolean;
  error: Error | null | undefined;
  caption: string;
}

const formatDate = formatBackendTimestampLocal;

export function FeTable({ items, isLoading, error, caption }: FeTableProps) {
  const { t } = useTranslation();

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="reporteria-financiera-fe-error"
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
        data-testid="reporteria-financiera-fe-loading"
        className="text-sm text-muted-foreground"
      >
        {t('reporteriaFinanciera.loading', 'Cargando...')}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground" data-testid="reporteria-financiera-fe-note">
        {t(
          'reporteriaFinanciera.fe.estadoDianNote',
          'El "Estado DIAN" es el estado de envío/acuse ante la DIAN — distinto del estado interno de la factura (vigente/anulada).',
        )}
      </p>
      <Table data-testid="reporteria-financiera-fe-table">
        <TableCaption className="sr-only">{caption}</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">{t('reporteriaFinanciera.fe.numeroCompleto', 'Número')}</TableHead>
            <TableHead scope="col">{t('reporteriaFinanciera.fe.cufe', 'CUFE')}</TableHead>
            <TableHead scope="col">
              {t('reporteriaFinanciera.fe.estadoDian', 'Estado DIAN (distinto del estado de la factura)')}
            </TableHead>
            <TableHead scope="col">
              {t('reporteriaFinanciera.fe.timestampEvento', 'Último evento')}
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
                data-testid="reporteria-financiera-fe-empty"
                className="text-center text-sm text-muted-foreground"
              >
                {t('reporteriaFinanciera.fe.empty', 'No hay facturas electrónicas para mostrar.')}
              </TableCell>
            </TableRow>
          ) : (
            items.map((row) => (
              <TableRow key={row.uuid}>
                <TableCell className="font-mono">{row.numero_completo ?? '—'}</TableCell>
                <TableCell className="font-mono text-xs">{row.cufe ?? '—'}</TableCell>
                <TableCell data-testid={`reporteria-financiera-fe-estado-dian-${row.uuid}`}>
                  {row.estado_dian ?? t('reporteriaFinanciera.fe.sinEnvio', 'Sin envío')}
                </TableCell>
                <TableCell className="tabular-nums">
                  {formatDate(row.timestamp_evento)}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
