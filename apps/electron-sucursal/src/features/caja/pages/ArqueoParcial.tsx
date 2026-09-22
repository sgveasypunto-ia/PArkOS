/**
 * `<ArqueoParcial />` -- HU-F10.1 partial arqueo (auditoria, sin cierre).
 *
 * Lives INSIDE the dashboard's SuscripcionesSheet-style drawer via
 * `<DrawerHost>`. F11.3 follow-up after the suscripciones wizard
 * rework: the arqueo flow now follows the same drawer-embedded
 * pattern (was: bare ArqueoSheet stub mounted with uuid_sesion=null,
 * which silently no-op'd the submit guard).
 *
 * Plan source of truth -- HU-F10.1 acceptance criteria verbatim:
 *   - Shows "base vigente" (sesion.valor_inicial_efectivo +
 *     sesion.valor_inicial_datafono, BR1 literal) + per-medio_pago
 *     sum of pagos during the session. The pagos sum is a TODO for
 *     F10.2/F10.3 (those HUs own the chain that needs it); F10.1
 *     ships with the initial values only and notes the limitation.
 *   - Operator enters physical count for efectivo + datáfono.
 *   - Live diferencia displayed: monto absoluto (informative:
 *     descuadre_pct per CU-10 BR2) + % info. Decision gate fires on
 *     the monto absoluto per configuracion_tolerancias -- NOT on %
 *     (reconciliation rule at plan.md line 2150).
 *   - If |diferencia total| > 0, advertencia (no bloquea) +
 *     justificacion becomes required (min 3 chars) per F10.1 lenient
 *     Zod refinement.
 *   - On submit, POST /caja/arqueo with tipo_arqueo='auditoria'.
 *     The BE resolves codigo -> uuid_tipo_arqueo internally (the
 *     POST payload schema accepts codigo per useArqueo's typing).
 *   - On success: close drawer + refresh sesion state.
 *
 * NOT in this PR (separate tasks per plan.md):
 *   - alerta `descuadre_critico` creation when |diferencia| > tolerancia
 *     (F10.1-T2 nuance; needs configuracion_tolerancias endpoint
 *     and an alertas POST flow that's still contract-drifted).
 *   - bridge.imprimir(escposBuilder.build('arqueo', payload)) tiquete
 *     (F10.1-T3; requires the print IPC + escposBuilder that lives
 *     in the Electron main process -- the renderer can only call
 *     window.bridge.imprimir).
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

import { useSesionActiva } from '../hooks/useSesionActiva';
import { useArqueo } from '../hooks/useArqueo';
import { formatCOP } from '../lib/format';

/**
 * F10.1 lenient Zod refinement (mirrors arqueoSchemaLenient in
 * ArqueoSheet.tsx). Justification becomes required when
 * |diferencia total| > 0. Inline here -- the page only needs this
 * one branch (the strict-mode variant lives in CerrarTurno).
 */
function hasDifferenceError(
  reportado: { efectivo: number; datafono: number },
  esperado: { efectivo: number; datafono: number },
  justificacion: string,
): string | null {
  const difTotal =
    Math.abs(reportado.efectivo - esperado.efectivo) +
    Math.abs(reportado.datafono - esperado.datafono);
  if (
    difTotal > 0 &&
    (!justificacion || justificacion.trim().length < 3)
  ) {
    return 'Justificación requerida si hay diferencia (mín. 3 caracteres).';
  }
  return null;
}

export function ArqueoParcial(): JSX.Element {
  const { t } = useTranslation('caja');
  const { sesion, isLoading: sesionLoading, error: sesionError, refresh: refreshSesion } =
    useSesionActiva();
  const { submit } = useArqueo();

  // Reported values: 0 by default, integer non-negative per the BE schema.
  const [reportEfectivo, setReportEfectivo] = useState(0);
  const [reportDatafono, setReportDatafono] = useState(0);
  const [justificacion, setJustificacion] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  // Reset submit-related state every time the drawer mounts fresh (the
  // parent DrawerHost unmounts us when openDrawer changes).
  useEffect(() => {
    setSubmitError(null);
    setSubmitted(false);
  }, []);

  // BR1 literal: "no necesariamente sesion.valor_inicial_efectivo fijo".
  // Use sesion.valor_inicial_efectivo (the authoritative opening value
  // for the current sesion) as the base. TODO F10.2/F10.3: add sum of
  // pagos during the session once `/caja-sesion/arqueos/.../pagos` (or
  // equivalent) is exposed for read.
  const esperadoEfectivo = sesion?.valor_inicial_efectivo ?? 0;
  const esperadoDatafono = sesion?.valor_inicial_datafono ?? 0;

  const reportadoEfectivoNum = Number.isFinite(reportEfectivo) ? reportEfectivo : 0;
  const reportadoDatafonoNum = Number.isFinite(reportDatafono) ? reportDatafono : 0;

  const difEfectivo = reportadoEfectivoNum - esperadoEfectivo;
  const difDatafono = reportadoDatafonoNum - esperadoDatafono;
  const difTotal = Math.abs(difEfectivo) + Math.abs(difDatafono);
  const reportadoTotal = reportadoEfectivoNum + reportadoDatafonoNum;
  const esperadoTotal = esperadoEfectivo + esperadoDatafono;
  // CU-10 BR2 informational percentage -- decision gate (alerta) uses
  // the absolute monto, not this %. Reconciliation rule from plan.md.
  const difPct =
    esperadoTotal > 0
      ? ((reportadoTotal - esperadoTotal) / esperadoTotal) * 100
      : 0;

  const validacionError = useMemo(
    () =>
      hasDifferenceError(
        { efectivo: reportadoEfectivoNum, datafono: reportadoDatafonoNum },
        { efectivo: esperadoEfectivo, datafono: esperadoDatafono },
        justificacion,
      ),
    [reportadoEfectivoNum, reportadoDatafonoNum, esperadoEfectivo, esperadoDatafono, justificacion],
  );

  const canSubmit = !!sesion && !submitting && !validacionError && !submitted;

  const handleSubmit = async (): Promise<void> => {
    if (!sesion) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await submit({
        uuid_sesion: sesion.uuid,
        tipo_arqueo: 'auditoria',
        valor_efectivo_reportado: reportadoEfectivoNum,
        valor_datafono_reportado: reportadoDatafonoNum,
        justificacion: difTotal > 0 ? justificacion.trim() : undefined,
      });
      // POST 200 -> close drawer, refresh sesion state. Parent
      // (DrawerHost / SuscripcionesSheet) handles close() on success
      // via the embedded pattern; here we just refresh the local
      // state so the next open of the drawer shows the up-to-date
      // sesion.
      await refreshSesion();
      setSubmitted(true);
    } catch (e) {
      setSubmitError(
        e instanceof Error ? e.message : 'Error desconocido al registrar el arqueo.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (sesionLoading) {
    return (
      <div className="space-y-4 p-4" data-testid="arqueo-parcial-page">
        <p data-testid="arqueo-loading">{t('caja:common:loading', { defaultValue: 'Cargando…' })}</p>
      </div>
    );
  }

  if (sesionError || !sesion) {
    return (
      <div className="space-y-4 p-4" data-testid="arqueo-parcial-page">
        <p className="text-sm text-destructive" data-testid="arqueo-no-session">
          {t('caja:arqueoParcial.noSession', {
            defaultValue: 'No hay sesión activa. Abrí turno antes de hacer arqueo.',
          })}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4" data-testid="arqueo-parcial-page">
      <header>
        <h1 className="text-xl font-semibold">
          {t('caja:arqueoParcial.titulo', {
            defaultValue: 'Arqueo parcial (auditoría)',
          })}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t('caja:arqueoParcial.descripcion', {
            defaultValue:
              'Contá la caja sin cerrar el turno. La diferencia es solo advertencia si es chica.',
          })}
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            {t('caja:arqueoParcial.sesionLabel', {
              defaultValue: 'Sesión activa',
            })}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">UUID</span>
            <span className="font-mono" data-testid="arqueo-sesion-uuid">
              {sesion.uuid.slice(0, 8)}…
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">
              {t('caja:arqueoParcial.baseEfectivoLabel', {
                defaultValue: 'Efectivo esperado',
              })}
            </span>
            <span
              className="font-medium tabular-nums"
              data-testid="arqueo-esperado-efectivo"
            >
              {formatCOP(esperadoEfectivo)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">
              {t('caja:arqueoParcial.baseDatafonoLabel', {
                defaultValue: 'Datáfono esperado',
              })}
            </span>
            <span
              className="font-medium tabular-nums"
              data-testid="arqueo-esperado-datafono"
            >
              {formatCOP(esperadoDatafono)}
            </span>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-3">
        <div className="space-y-1">
          <label className="text-sm font-medium" htmlFor="arqueo-efectivo-input">
            {t('caja:arqueoParcial.reportedEfectivoLabel', {
              defaultValue: 'Efectivo contado',
            })}
          </label>
          <Input
            id="arqueo-efectivo-input"
            type="number"
            inputMode="decimal"
            data-testid="arqueo-efectivo-input"
            value={reportEfectivo}
            onChange={(e) => {
              const v = Number(e.target.value);
              setReportEfectivo(Number.isFinite(v) && v >= 0 ? v : 0);
            }}
            placeholder="0"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium" htmlFor="arqueo-datafono-input">
            {t('caja:arqueoParcial.reportedDatafonoLabel', {
              defaultValue: 'Datáfono contado',
            })}
          </label>
          <Input
            id="arqueo-datafono-input"
            type="number"
            inputMode="decimal"
            data-testid="arqueo-datafono-input"
            value={reportDatafono}
            onChange={(e) => {
              const v = Number(e.target.value);
              setReportDatafono(Number.isFinite(v) && v >= 0 ? v : 0);
            }}
            placeholder="0"
          />
        </div>
      </div>

      {/* Live diferencia feedback. % is informational only (BR2
          reconciliation rule); the absolute monto is the decision
          gate that the BE uses for the alerta. */}
      <div
        className="rounded border bg-muted/50 p-3 text-sm space-y-1"
        data-testid="arqueo-diferencia"
      >
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">
            {t('caja:arqueoParcial.difEfectivo', {
              defaultValue: 'Dif. efectivo',
            })}
          </span>
          <span
            className={
              'tabular-nums ' + (difEfectivo === 0 ? '' : 'font-semibold')
            }
            data-testid="arqueo-dif-efectivo"
          >
            {formatCOP(difEfectivo)}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">
            {t('caja:arqueoParcial.difDatafono', {
              defaultValue: 'Dif. datáfono',
            })}
          </span>
          <span
            className={
              'tabular-nums ' + (difDatafono === 0 ? '' : 'font-semibold')
            }
            data-testid="arqueo-dif-datafono"
          >
            {formatCOP(difDatafono)}
          </span>
        </div>
        <div className="flex items-center justify-between border-t pt-1">
          <span className="font-medium">
            {t('caja:arqueoParcial.difTotal', {
              defaultValue: 'Dif. total',
            })}
          </span>
          <span
            className={
              'tabular-nums ' + (difTotal === 0 ? '' : 'font-semibold text-destructive')
            }
            data-testid="arqueo-dif-total"
          >
            {formatCOP(difTotal)}
          </span>
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {t('caja:arqueoParcial.difPct', { defaultValue: 'Descuadre' })}
          </span>
          <span className="tabular-nums" data-testid="arqueo-dif-pct">
            {difPct.toFixed(2)}%
          </span>
        </div>
        {difTotal > 0 && (
          <p
            role="status"
            className="text-xs text-yellow-700 dark:text-yellow-400 mt-2"
            data-testid="arqueo-advertencia"
          >
            {t('caja:arqueoParcial.advertencia', {
              defaultValue:
                'Hay diferencia. La auditoría queda registrada; solo se advierte (no bloquea).',
            })}
          </p>
        )}
      </div>

      {difTotal > 0 && (
        <div className="space-y-1">
          <label className="text-sm font-medium" htmlFor="arqueo-justificacion">
            {t('caja:arqueoParcial.justificacionLabel', {
              defaultValue: 'Justificación (mín. 3 caracteres)',
            })}
          </label>
          <Input
            id="arqueo-justificacion"
            data-testid="arqueo-justificacion"
            placeholder="Describe brevemente la diferencia"
            value={justificacion}
            onChange={(e) => setJustificacion(e.target.value)}
          />
          {validacionError && (
            <p
              role="alert"
              className="text-xs text-destructive"
              data-testid="arqueo-justificacion-error"
            >
              {validacionError}
            </p>
          )}
        </div>
      )}

      {submitError && (
        <p
          role="alert"
          className="text-sm text-destructive"
          data-testid="arqueo-submit-error"
        >
          {submitError}
        </p>
      )}

      <Button
        type="button"
        data-testid="arqueo-confirmar"
        disabled={!canSubmit}
        onClick={handleSubmit}
        className="w-full"
      >
        {submitting
          ? t('caja:common:loading', { defaultValue: 'Enviando…' })
          : t('caja:arqueoParcial.confirmar', {
              defaultValue: 'Confirmar auditoría',
            })}
      </Button>
    </div>
  );
}
