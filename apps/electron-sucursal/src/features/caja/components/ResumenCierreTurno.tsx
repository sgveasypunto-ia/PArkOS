/**
 * `<ResumenCierreTurno />` — read-only post-close summary (PT-5).
 *
 * Shown inside the "Cerrar turno" sheet AFTER the cierre succeeded and
 * BEFORE the logout. Presentational: it receives the already-gathered data
 * and an `onFinalizar` callback (the orchestrator runs the deferred
 * logout there). There is no history: the summary lives only in the
 * component state of the operator who just closed.
 *
 * Content comes from `buildResumenCierreSections` — the same rows are
 * rendered on screen and written to the PDF ("Descargar PDF").
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { descargarResumenCierrePdf } from '../../../lib/print/resumenCierrePdf';
import { useImprimirCierre } from '../hooks/useImprimirCierre';
import { buildResumenCierreSections, type ResumenCierreInput } from '../lib/resumenCierre';

export interface ResumenCierreTurnoProps extends ResumenCierreInput {
  onFinalizar: () => void;
  /** True while the summary data is still loading: the ticket cannot be printed yet. */
  cargando?: boolean;
}

export function ResumenCierreTurno({
  onFinalizar,
  cargando = false,
  ...input
}: ResumenCierreTurnoProps): JSX.Element {
  const { t } = useTranslation(['caja', 'common']);
  const [pdfError, setPdfError] = useState(false);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [isPrinting, setIsPrinting] = useState(false);
  const imprimir = useImprimirCierre();

  const sections = useMemo(
    () => buildResumenCierreSections(input, t),
    // `input` is a fresh rest-object each render; depend on its members.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [input.sesion, input.arqueo, input.observaciones, input.resumen, t],
  );

  const title = t('caja:cerrarTurno.resumenCierre.titulo', { defaultValue: 'Turno cerrado' });

  const onDescargar = async (): Promise<void> => {
    setPdfError(false);
    setIsGeneratingPdf(true);
    try {
      await descargarResumenCierrePdf({
        title: t('caja:cerrarTurno.resumenCierre.pdfTitulo', {
          defaultValue: 'Resumen de cierre de turno',
        }),
        subtitle: `Sesión ${input.sesion.uuid}`,
        sections,
        footer: t('caja:cerrarTurno.resumenCierre.pdfPie', {
          defaultValue:
            'Documento informativo generado al cierre del turno. Los pagos electrónicos no hacen parte del cuadre de efectivo.',
        }),
        fileName: `cierre-turno-${input.sesion.uuid.slice(0, 8)}`,
      });
    } catch (err) {
      console.error('[ResumenCierreTurno] pdf export failed', err);
      setPdfError(true);
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  // The ticket needs the operator's count (the figure confirmed on screen); without it there is nothing to print.
  const puedeImprimir = !cargando && input.arqueo.valor_efectivo_reportado !== undefined;

  // Same single print route as the invoice and the automatic slip: failures leave the visible notice with retry.
  const onImprimir = async (): Promise<void> => {
    setIsPrinting(true);
    try {
      await imprimir.resumenTurno({
        sesion: input.sesion,
        arqueo: input.arqueo,
        secciones: sections,
        nota: t('caja:cerrarTurno.resumenCierre.notaElectronicos', {
          defaultValue:
            'Los pagos electrónicos se muestran solo como información: no cuentan como base ni para el cuadre de efectivo.',
        }),
      });
    } finally {
      setIsPrinting(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="resumen-cierre-turno">
      <div role="status" className="space-y-1">
        <h2 className="text-base font-semibold" data-testid="resumen-cierre-titulo">
          {title}
        </h2>
        <p className="text-sm text-muted-foreground">
          {t('caja:cerrarTurno.resumenCierre.descripcion', {
            defaultValue:
              'Este resumen es de solo lectura y no se guarda en la aplicación. Descárgalo si lo necesitas antes de salir.',
          })}
        </p>
      </div>

      {sections.map((section, index) => (
        <Card key={`${index}-${section.heading}`} data-testid={`resumen-cierre-seccion-${index}`}>
          <CardHeader className="px-4 pt-3 pb-2">
            <CardTitle className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
              {section.heading}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3">
            <ul role="list" className="divide-y divide-border/40 text-sm">
              {section.rows.map((row, rowIndex) => (
                <li
                  key={`${index}-${rowIndex}`}
                  className="flex items-start justify-between gap-3 py-1.5"
                >
                  <span className="text-muted-foreground/90">{row.label}</span>
                  <span className="text-right font-mono font-semibold tabular-nums break-words">
                    {row.value}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}

      <p className="text-xs text-muted-foreground" data-testid="resumen-cierre-nota-electronicos">
        {t('caja:cerrarTurno.resumenCierre.notaElectronicos', {
          defaultValue:
            'Los pagos electrónicos se muestran solo como información: no cuentan como base ni para el cuadre de efectivo.',
        })}
      </p>

      {pdfError && (
        <p role="alert" className="text-sm text-destructive" data-testid="resumen-cierre-pdf-error">
          {t('caja:cerrarTurno.resumenCierre.pdfError', {
            defaultValue: 'No se pudo generar el PDF. Inténtalo de nuevo.',
          })}
        </p>
      )}

      <div className="flex flex-wrap gap-2 pt-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => void onDescargar()}
          disabled={isGeneratingPdf}
          aria-disabled={isGeneratingPdf}
          data-testid="resumen-cierre-descargar-pdf"
        >
          {t('caja:cerrarTurno.resumenCierre.descargarPdf', { defaultValue: 'Descargar PDF' })}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => void onImprimir()}
          disabled={!puedeImprimir || isPrinting}
          aria-busy={isPrinting}
          data-testid="resumen-cierre-imprimir-ticket"
        >
          {t('caja:cerrarTurno.resumenCierre.imprimirTicket', { defaultValue: 'Imprimir ticket' })}
        </Button>
        <Button
          type="button"
          onClick={onFinalizar}
          autoFocus
          data-testid="resumen-cierre-finalizar"
        >
          {t('caja:cerrarTurno.resumenCierre.finalizar', { defaultValue: 'Finalizar y salir' })}
        </Button>
      </div>
    </div>
  );
}
