/**
 * `<SuscripcionesPorVencer />` — top-20 "próximas a vencer" list with a
 * yellow badge (HU-F17.4).
 *
 * The "próximas a vencer" criterion was NOT invented for this HU: it
 * already exists (HU-F9.2, REQ-OPS-181,
 * `apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesProximasVencer.ts`
 * → `computeProximasVencer`) — `dias_para_vencer = floor((fecha_vencimiento
 * - hoy) / 1 día)`, vencidas (`dias < 0`) excluded, ascending by
 * `fecha_vencimiento`. That prior art is single-branch (its backend
 * endpoint takes a required `uuid_sucursal` and does not exist in this
 * backend snapshot yet); this component is the cross-branch admin
 * equivalent, fed by `GET /admin/reporteria/suscripciones/cohorte`'s
 * `proximas_a_vencer` field, which applies the exact same filter + order
 * + a top-20 cap server-side. This component is purely presentational.
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
import { Badge } from '@/components/ui/badge';

import type { SuscripcionPorVencerItem } from '../api/reporteriaSchema';

export interface SuscripcionesPorVencerProps {
  items: SuscripcionPorVencerItem[];
  isLoading: boolean;
  error: Error | null | undefined;
  caption: string;
}

export function SuscripcionesPorVencer({
  items,
  isLoading,
  error,
  caption,
}: SuscripcionesPorVencerProps) {
  const { t } = useTranslation();

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="suscripciones-por-vencer-error"
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
        data-testid="suscripciones-por-vencer-loading"
        className="text-sm text-muted-foreground"
      >
        {t('reporteriaSuscripciones.loading', 'Cargando...')}
      </p>
    );
  }

  return (
    <Table data-testid="suscripciones-por-vencer-table">
      <TableCaption className="sr-only">{caption}</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">
            {t('reporteriaSuscripciones.porVencer.cliente', 'Cliente')}
          </TableHead>
          <TableHead scope="col">
            {t('reporteriaSuscripciones.porVencer.vencimiento', 'Vence')}
          </TableHead>
          <TableHead scope="col">
            {t('reporteriaSuscripciones.porVencer.diasRestantes', 'Días restantes')}
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
              data-testid="suscripciones-por-vencer-empty"
              className="text-center text-sm text-muted-foreground"
            >
              {t(
                'reporteriaSuscripciones.porVencer.empty',
                'No hay suscripciones próximas a vencer.',
              )}
            </TableCell>
          </TableRow>
        ) : (
          items.map((row) => (
            <TableRow key={row.uuid}>
              <TableCell className="font-mono text-xs">
                {row.uuid_cliente ? row.uuid_cliente.slice(0, 8) : '—'}
              </TableCell>
              <TableCell className="tabular-nums">{row.fecha_vencimiento}</TableCell>
              <TableCell>
                <Badge variant="warning" data-testid={`suscripciones-por-vencer-badge-${row.uuid}`}>
                  {t('reporteriaSuscripciones.porVencer.diasBadge', '{{dias}} días', {
                    dias: row.dias_para_vencer,
                  })}
                </Badge>
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}
