/**
 * `<AlertaDetalle />` -- HU-F19.5 detail screen: one alerta's data +
 * its best-effort transition history (`useAlertaChain`, generic
 * `<WorkflowChain />`) + the "descartar" action (HU-F19.4's already-real
 * `POST /workflows/alerta/{uuid}/descartar`, reused via
 * `DescartarAlertaModal`).
 *
 * `severity` is NOT carried by `GET /workflows/alerta/{uuid}` (the
 * generic single-item read -- see `alertasSchema.ts`). When this page
 * is reached via a row click from `<AlertasList />`, the list already
 * knows `severity`; it's forwarded through router `state` as a small,
 * best-effort enhancement (never trusted as the source of truth for
 * anything else -- a direct deep-link / refresh has no `state` and
 * simply renders "—", per BR4's own "—" convention for "don't know").
 */
import { useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';
import { useGoBack } from '@/lib/useGoBack';

import { WorkflowChain, type WorkflowTransition } from '@/features/workflows/components/WorkflowChain';

import { SeverityBadge } from '../components/SeverityBadge';
import { EstadoAlertaBadge } from '../components/EstadoAlertaBadge';
import { DescartarAlertaModal } from '../components/DescartarAlertaModal';
import { useAlertaDetalle } from '../hooks/useAlertaDetalle';
import { useAlertaChain } from '../hooks/useAlertaChain';
import type { AlertaSeverity } from '../api/alertasSchema';
import { alertaTipoLabel, extraerDatosRelevantes } from '../lib/alertaTipos';

interface LocationState {
  severity?: AlertaSeverity | null;
}

export default function AlertaDetalle(): JSX.Element {
  const { t } = useTranslation();
  const { uuid } = useParams<{ uuid: string }>();
  const location = useLocation();
  const forwardedSeverity = (location.state as LocationState | null)?.severity ?? undefined;

  const { alerta, isLoading, error, setAlerta } = useAlertaDetalle(uuid ?? null);
  const { chain, isLoading: chainLoading, error: chainError } = useAlertaChain(uuid ?? null);

  const [descartarOpen, setDescartarOpen] = useState(false);
  const { sucursales } = useSucursalesDirectorio();
  // PT-1: back to the previous screen (the inbox with its filters).
  const goBack = useGoBack('/alertas');

  const transitions: WorkflowTransition[] = chain.map((row) => ({
    id: row.uuid,
    status: row.estado ?? t('alertas.estado.none', '—'),
    timestamp: row.timestamp_evento ?? row.vigente_desde,
    actor: row.uuid_usuario,
    // KNOWN GAP (BE): `AlertaRead` doesn't expose `datos_nuevos`, so the
    // "descartar" observaciones text isn't retrievable from history --
    // see `useAlertaChain.ts`'s docblock.
    observaciones: null,
  }));

  if (uuid === undefined) {
    return (
      <main
        className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
        data-testid="alerta-detalle-page"
      >
        <PageHeader
          title={t('alertas.detalle.title', 'Detalle de la alerta')}
        />
        <p role="alert">{t('alertas.detalle.missingUuid', 'Falta el identificador de la alerta.')}</p>
      </main>
    );
  }

  const canDescartar = alerta !== undefined && alerta.estado !== 'resuelta';
  const datosRelevantes = extraerDatosRelevantes(alerta?.datos_nuevos);
  const sucursalUuid = alerta?.uuid_sucursal ?? datosRelevantes?.uuidSucursal ?? null;
  const sucursalNombre =
    sucursalUuid === null ? null : (sucursales.find((s) => s.uuid === sucursalUuid)?.nombre ?? null);

  function accionLabel(accion: string): string {
    if (accion === 'agregada' || accion === 'agregar') return t('alertas.accion.agregada', 'Agregada');
    if (accion === 'quitada' || accion === 'quitar') return t('alertas.accion.quitada', 'Quitada');
    return accion;
  }

  return (
    <main
      className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
      data-testid="alerta-detalle-page"
    >
      <PageHeader
        title={t('alertas.detalle.title', 'Detalle de la alerta')}
        subtitle={<span className="font-mono text-xs">{uuid}</span>}
        actions={
          <Button
            type="button"
            variant="outline"
            onClick={goBack}
            data-testid="alerta-detalle-back"
          >
            {t('alertas.detalle.back', 'Volver a la bandeja')}
          </Button>
        }
      />

      {isLoading && alerta === undefined && (
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {t('alertas.detalle.loading', 'Cargando alerta...')}
        </p>
      )}

      {error !== undefined && (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="alerta-detalle-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('alertas.detalle.errorLoading', 'No se pudo cargar la alerta.')}
        </p>
      )}

      {alerta !== undefined && (
        <>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <CardTitle className="text-sm">{t('alertas.detalle.dataTitle', 'Datos')}</CardTitle>
              <div className="flex items-center gap-2">
                <SeverityBadge severity={alerta.severity ?? forwardedSeverity} />
                <EstadoAlertaBadge estado={alerta.estado} />
              </div>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
              <div data-testid="alerta-detalle-tipo">
                <span className="text-muted-foreground">{t('alertas.detalle.tipo', 'Tipo')}: </span>
                {alertaTipoLabel(alerta.tipo_alerta, t)}
              </div>
              <div>
                <span className="text-muted-foreground">{t('alertas.detalle.sucursal', 'Sucursal')}: </span>
                {sucursalNombre !== null ? (
                  <span data-testid="alerta-detalle-sucursal">{sucursalNombre}</span>
                ) : (
                  <span className="font-mono text-xs" data-testid="alerta-detalle-sucursal">
                    {alerta.uuid_sucursal ?? '—'}
                  </span>
                )}
              </div>
              {datosRelevantes !== null && (
                <>
                  {datosRelevantes.placa !== null && (
                    <div data-testid="alerta-detalle-placa">
                      <span className="text-muted-foreground">{t('alertas.detalle.placa', 'Placa')}: </span>
                      <span className="font-mono">{datosRelevantes.placa}</span>
                    </div>
                  )}
                  {datosRelevantes.accion !== null && (
                    <div data-testid="alerta-detalle-accion">
                      <span className="text-muted-foreground">{t('alertas.detalle.accion', 'Acción')}: </span>
                      {accionLabel(datosRelevantes.accion)}
                    </div>
                  )}
                  {datosRelevantes.suscripcionRef !== null && (
                    <div data-testid="alerta-detalle-suscripcion">
                      <span className="text-muted-foreground">
                        {t('alertas.detalle.suscripcion', 'Suscripción')}:{' '}
                      </span>
                      <span className="font-mono text-xs">…{datosRelevantes.suscripcionRef}</span>
                    </div>
                  )}
                </>
              )}
              <div>
                <span className="text-muted-foreground">{t('alertas.detalle.fecha', 'Fecha del evento')}: </span>
                {alerta.timestamp_evento ?? '—'}
              </div>
              <div>
                <span className="text-muted-foreground">{t('alertas.detalle.diferenciaEfectivo', 'Diferencia efectivo')}: </span>
                {alerta.valor_diferencia_efectivo ?? '—'}
              </div>
              <div>
                <span className="text-muted-foreground">{t('alertas.detalle.diferenciaDatafono', 'Diferencia datáfono')}: </span>
                {alerta.valor_diferencia_datafono ?? '—'}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <CardTitle className="text-sm">{t('alertas.detalle.historyTitle', 'Historial de transiciones')}</CardTitle>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                disabled={!canDescartar}
                onClick={() => setDescartarOpen(true)}
                data-testid="alerta-detalle-descartar-button"
                title={canDescartar ? undefined : t('alertas.detalle.yaResuelta', 'Esta alerta ya está resuelta.')}
              >
                {t('alertas.descartar.submit', 'Descartar')}
              </Button>
            </CardHeader>
            <CardContent>
              <WorkflowChain
                transitions={transitions}
                isLoading={chainLoading}
                error={chainError ?? null}
                renderStatusBadge={(status) => (
                  <EstadoAlertaBadge
                    estado={
                      status === 'abierta' || status === 'en_revision' || status === 'resuelta'
                        ? status
                        : null
                    }
                  />
                )}
              />
            </CardContent>
          </Card>
        </>
      )}

      {descartarOpen && (
        <DescartarAlertaModal
          uuidAlerta={uuid}
          open
          onClose={() => setDescartarOpen(false)}
          onDescartada={(updated) => {
            setAlerta(updated);
            setDescartarOpen(false);
          }}
        />
      )}
    </main>
  );
}
