/**
 * ``ResumenSucursalCard`` -- presentational card per branch in the
 * HU-F18.3 admin resumen. Shows expected vs reported and the cierre_dia
 * detail when present.
 *
 * Number formatting uses Intl.NumberFormat with es-CO locale to mirror
 * the operator-side arqueo resumen. The card emphasizes the
 * cierre_dia row when present (the summary event for the day).
 */
import { useTranslation } from 'react-i18next';

import type {
  ArqueoResumenAdminItem,
  ArqueoResumenItem,
} from '../api/arqueosSchema';

export interface ResumenSucursalCardProps {
  item: ArqueoResumenAdminItem;
}

function fmt(value: string | null): string {
  if (value === null) return '—';
  return new Intl.NumberFormat('es-CO', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value));
}

function fmtCierre(item: ArqueoResumenItem | null): {
  esperado_efectivo: string;
  reportado_efectivo: string;
  diferencia_efectivo: string;
  esperado_datafono: string;
  reportado_datafono: string;
  diferencia_datafono: string;
} {
  return {
    esperado_efectivo: fmt(item?.valor_efectivo_esperado ?? null),
    reportado_efectivo: fmt(item?.valor_efectivo_reportado ?? null),
    diferencia_efectivo: fmt(item?.diferencia_efectivo ?? null),
    esperado_datafono: fmt(item?.valor_datafono_esperado ?? null),
    reportado_datafono: fmt(item?.valor_datafono_reportado ?? null),
    diferencia_datafono: fmt(item?.diferencia_datafono ?? null),
  };
}

export function ResumenSucursalCard({
  item,
}: ResumenSucursalCardProps): JSX.Element {
  const { t } = useTranslation();
  const cierre = item.cierre_dia;
  const f = fmtCierre(cierre);
  const hasCierre = cierre !== null;
  const hasDesc =
    cierre !== null &&
    cierre.diferencia_efectivo !== null &&
    cierre.diferencia_datafono !== null &&
    (Number(cierre.diferencia_efectivo) !== 0 ||
      Number(cierre.diferencia_datafono) !== 0);

  return (
    <article
      data-testid={`resumen-sucursal-card-${item.uuid_sucursal}`}
      className="rounded-md border bg-card p-4"
    >
      <header className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold">
          {item.nombre ?? item.uuid_sucursal}
        </h3>
        <span
          data-testid={`resumen-total-${item.uuid_sucursal}`}
          className="font-mono text-xs text-muted-foreground"
        >
          {t('arqueos.resumen.totalArqueos', { count: item.total_arqueos })}
        </span>
      </header>

      {hasCierre && (
        <div
          data-testid={`resumen-cierre-${item.uuid_sucursal}`}
          className="mt-3 rounded-md border bg-muted/20 p-3"
        >
          <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
            {t('arqueos.resumen.cierreTitle', 'Cierre del día')}
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-2" />
                <th className="px-2">
                  {t('arqueos.detail.esperado', 'Esperado')}
                </th>
                <th className="px-2">
                  {t('arqueos.detail.reportado', 'Reportado')}
                </th>
                <th className="px-2">
                  {t('arqueos.detail.diferencia', 'Diferencia')}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr data-testid={`resumen-efectivo-${item.uuid_sucursal}`}>
                <th
                  scope="row"
                  className="px-2 text-left font-medium"
                >
                  {t('arqueos.detail.efectivo', 'Efectivo')}
                </th>
                <td className="px-2 font-mono text-xs">{f.esperado_efectivo}</td>
                <td className="px-2 font-mono text-xs">{f.reportado_efectivo}</td>
                <td
                  className={`px-2 font-mono text-xs ${
                    hasDesc && Number(cierre.diferencia_efectivo) !== 0
                      ? 'font-semibold text-destructive'
                      : ''
                  }`}
                >
                  {f.diferencia_efectivo}
                </td>
              </tr>
              <tr data-testid={`resumen-datafono-${item.uuid_sucursal}`}>
                <th
                  scope="row"
                  className="px-2 text-left font-medium"
                >
                  {t('arqueos.detail.datafono', 'Datáfono')}
                </th>
                <td className="px-2 font-mono text-xs">{f.esperado_datafono}</td>
                <td className="px-2 font-mono text-xs">{f.reportado_datafono}</td>
                <td
                  className={`px-2 font-mono text-xs ${
                    hasDesc && Number(cierre.diferencia_datafono) !== 0
                      ? 'font-semibold text-destructive'
                      : ''
                  }`}
                >
                  {f.diferencia_datafono}
                </td>
              </tr>
            </tbody>
          </table>
          {hasDesc && (
            <p
              data-testid={`resumen-descuadre-${item.uuid_sucursal}`}
              className="mt-2 border-t bg-destructive/10 px-2 py-1 text-xs text-destructive"
            >
              {t(
                'arqueos.detail.descuadreWarning',
                'Hay descuadre: el cierre requiere just ificación.',
              )}
            </p>
          )}
        </div>
      )}

      {!hasCierre && (
        <p
          data-testid={`resumen-no-cierre-${item.uuid_sucursal}`}
          className="mt-3 rounded-md border border-dashed bg-muted/20 px-3 py-2 text-xs text-muted-foreground"
        >
          {t(
            'arqueos.resumen.noCierre',
            'Sin cierre del día registrado para esta sucursal.',
          )}
        </p>
      )}
    </article>
  );
}