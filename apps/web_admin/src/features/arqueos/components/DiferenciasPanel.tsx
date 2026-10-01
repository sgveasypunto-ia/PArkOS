/**
 * ``DiferenciasPanel`` -- presentational component that renders the
 * expected-vs-reported deltas for one arqueo (HU-F18.2).
 *
 * Source of data: ``useArqueoDetalle`` hook calls
 * ``GET /caja-sesion/arqueos/{uuid}/diferencias`` and returns a
 * ``DiferenciasRead`` with four numeric fields plus two computed
 * differences. This component consumes the hook output and renders:
 *
 *   - The four raw columns (esperado / reportado) per medio de pago.
 *   - The signed difference (reported / esperado). Bold + red if
 *     non-zero (DEC-ARQUEO-07: diferencia != 0 means just ificacion
 *     required). The string copy is i18n'd so locale can flip the
 *     phrasing.
 *   - Loading / error / missing-data testids per the panel contract.
 *
 * The ``diferencias_generadas`` boolean on the ArqueoResumenItem is
 * surfaced through the ``AlertaLink`` child (separate file) once the
 * admin clicks through to the detail.
 */
import { useTranslation } from 'react-i18next';

import type { DiferenciasRead } from '../api/arqueosSchema';

export interface DiferenciasPanelProps {
  diferencias: DiferenciasRead | null;
  isLoading: boolean;
  error: Error | undefined;
}

function fmt(value: number): string {
  // Mirror ``formatTarifaValor`` semantics -- 2 decimals, locale-aware.
  return new Intl.NumberFormat('es-CO', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function DiferenciasPanel({
  diferencias,
  isLoading,
  error,
}: DiferenciasPanelProps): JSX.Element {
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <div
        role="status"
        data-testid="diferencias-loading"
        className="rounded-md border bg-muted/20 px-3 py-3 text-sm text-muted-foreground"
      >
        {t('arqueos.detail.loading')}
      </div>
    );
  }

  if (error !== undefined) {
    return (
      <div
        role="alert"
        data-testid="diferencias-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-3 text-sm text-destructive"
      >
        {t('arqueos.detail.errorLoading', 'No se pudo cargar la diferencia.')}
      </div>
    );
  }

  if (diferencias === null) {
    return (
      <div
        role="status"
        data-testid="diferencias-empty"
        className="rounded-md border border-dashed bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground"
      >
        {t('arqueos.detail.pickRow', 'Selecciona un arqueo para ver sus diferencias.')}
      </div>
    );
  }

  const hasDesc =
    diferencias.diferencia_efectivo !== 0 ||
    diferencias.diferencia_datafono !== 0;

  return (
    <section
      data-testid="diferencias-panel"
      aria-label="Diferencias entre esperado y reportado"
      className="rounded-md border bg-card"
    >
      <header className="border-b px-4 py-2">
        <h4 className="text-sm font-medium">
          {t('arqueos.detail.diferenciasTitle', 'Diferencias')}
        </h4>
      </header>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th scope="col" className="px-4 py-2">
              {t('arqueos.detail.medio', 'Medio')}
            </th>
            <th scope="col" className="px-4 py-2">
              {t('arqueos.detail.esperado', 'Esperado')}
            </th>
            <th scope="col" className="px-4 py-2">
              {t('arqueos.detail.reportado', 'Reportado')}
            </th>
            <th scope="col" className="px-4 py-2">
              {t('arqueos.detail.diferencia', 'Diferencia')}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr data-testid="diferencias-row-efectivo" className="border-t">
            <th
              scope="row"
              className="px-4 py-2 font-medium"
              data-testid="diferencias-label-efectivo"
            >
              {t('arqueos.detail.efectivo', 'Efectivo')}
            </th>
            <td className="px-4 py-2 font-mono text-xs">
              {fmt(diferencias.valor_efectivo_esperado)}
            </td>
            <td className="px-4 py-2 font-mono text-xs">
              {fmt(diferencias.valor_efectivo_reportado)}
            </td>
            <td
              data-testid="diferencias-cell-efectivo"
              className={`px-4 py-2 font-mono text-xs ${hasDesc && diferencias.diferencia_efectivo !== 0 ? 'font-semibold text-destructive' : ''}`}
            >
              {fmt(diferencias.diferencia_efectivo)}
            </td>
          </tr>
          <tr data-testid="diferencias-row-datafono" className="border-t">
            <th
              scope="row"
              className="px-4 py-2 font-medium"
              data-testid="diferencias-label-datafono"
            >
              {t('arqueos.detail.datafono', 'Datáfono')}
            </th>
            <td className="px-4 py-2 font-mono text-xs">
              {fmt(diferencias.valor_datafono_esperado)}
            </td>
            <td className="px-4 py-2 font-mono text-xs">
              {fmt(diferencias.valor_datafono_reportado)}
            </td>
            <td
              data-testid="diferencias-cell-datafono"
              className={`px-4 py-2 font-mono text-xs ${hasDesc && diferencias.diferencia_datafono !== 0 ? 'font-semibold text-destructive' : ''}`}
            >
              {fmt(diferencias.diferencia_datafono)}
            </td>
          </tr>
        </tbody>
      </table>
      {hasDesc && (
        <p
          data-testid="diferencias-descuadre-warning"
          className="border-t bg-destructive/10 px-4 py-2 text-sm text-destructive"
        >
          {t(
            'arqueos.detail.descuadreWarning',
            'Hay descuadre: el arqueo requiere justificación en el siguiente paso.',
          )}
        </p>
      )}
    </section>
  );
}