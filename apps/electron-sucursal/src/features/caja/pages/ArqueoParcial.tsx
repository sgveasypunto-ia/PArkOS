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
import { useTipoArqueoPorCodigo } from '../hooks/useTipoArqueoPorCodigo';
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
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
  // F11.3 -- resolve 'auditoria' -> UUID via the catalog SWR hook.
  // The BE V2 schema (api/v1/caja.py:ArqueoCreateV2) requires
  // ``uuid_tipo_arqueo`` (UUID); the previous FE sending
  // ``tipo_arqueo: 'auditoria'`` was rejected by extra='forbid'.
  // The hook SWR-dedupes the catalog GET (60s) so the round-trip is
  // once-per-session at most.
  const { uuid: uuidTipoAuditoria, error: tipoArqueoError } =
    useTipoArqueoPorCodigo('auditoria');
  // F11.3 follow-up -- on successful submit we close the right-side
  // drawer so the operator returns to the dashboard route (`/`).
  // The store clears ``openDrawer`` which unmounts the page body
  // via DrawerHost, restoring focus to the trigger anchor via the
  // ``lastAnchorId`` set by the ``open('arqueo', anchorId)`` call.
  const closeDrawer = useDashboardDrawerStore((s) => s.close);

  // Reported values: 0 by default, integer non-negative per the BE schema.
  const [reportEfectivo, setReportEfectivo] = useState(0);
  const [reportDatafono, setReportDatafono] = useState(0);
  const [justificacion, setJustificacion] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Reset state every time the drawer mounts fresh (the parent
  // ArqueoSheet unmounts us when openDrawer changes). Also reset the
  // reported values + justificacion so a stale fill from a prior
  // open doesn't trip `validacionError` on the next open (REQ-OPS-138
  // single-drawer invariant + F11.3 UX note). The successful
  // submit path now closes the drawer so the operator returns to
  // the dashboard route; this effect handles the next-open reset.
  useEffect(() => {
    setSubmitError(null);
    setReportEfectivo(0);
    setReportDatafono(0);
    setJustificacion('');
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

  const canSubmit =
    !!sesion &&
    !submitting &&
    !validacionError &&
    !!uuidTipoAuditoria;

  const handleSubmit = async (): Promise<void> => {
    if (!sesion) return;
    if (!uuidTipoAuditoria) {
      setSubmitError(
        tipoArqueoError?.message ??
          'No se pudo resolver el tipo de arqueo. Reintentá en unos segundos.',
      );
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      await submit({
        uuid_sesion: sesion.uuid,
        uuid_tipo_arqueo: uuidTipoAuditoria,
        valor_efectivo_reportado: reportadoEfectivoNum,
        valor_datafono_reportado: reportadoDatafonoNum,
        justificacion: difTotal > 0 ? justificacion.trim() : undefined,
      });
      // POST 201 -> refresh sesion state THEN close the drawer so
      // the operator returns to the dashboard route (/). Closing
      // BEFORE the refresh would leave a stale sesion snapshot in
      // the SWR cache for the next drawer open. DrawerHost unmounts
      // the page body when openDrawer is cleared, so the reset
      // effect on next mount handles the inputs/justificacion
      // reset for free.
      await refreshSesion();
      closeDrawer();
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
      {/* F11.3 follow-up -- the title + description are rendered by
          the parent <ArqueoSheet /> via SheetHeader/SheetTitle/
          SheetDescription. The page body no longer duplicates them
          (was previously both Sheet + <h1>+<p> rendered -- two
          headings, two descriptions). The page body now owns ONLY
          the form: sesion card + inputs + diferencia + justificacion
          + confirmar button. */}

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
              'tabular-nums ' +
              (difEfectivo === 0 ? '' : 'font-semibold text-destructive')
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
              'tabular-nums ' +
              (difDatafono === 0 ? '' : 'font-semibold text-destructive')
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
            className="mt-2 inline-flex items-center rounded-md bg-warning px-2 py-1 text-xs font-medium text-warning-foreground"
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
