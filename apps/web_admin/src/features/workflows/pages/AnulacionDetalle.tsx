/**
 * `<AnulacionDetalle />` -- HU-F20.3 detail screen: one anulación's data
 * + its best-effort transition history (`useAnulacionChain`, generic
 * `<WorkflowChain />`) + the "transición" actions
 * (`POST /workflows/anulaciones/{uuid}/transicion`, HU-F20.3, via
 * `TransicionAnulacionModal`). Mirrors
 * `alertas/pages/AlertaDetalle.tsx`'s composition.
 *
 * Which destination buttons render depends on the CURRENT tip's
 * `estado` (`ANULACION_TRANSICIONES`):
 *   - `iniciada`              -> "Aprobar" (autorizada) / "Rechazar" (rechazada)
 *   - `autorizada`            -> "Ejecutar" (ejecutada) / "Rechazar" (rechazada)
 *   - `ejecutada`/`rechazada` -> terminal, no buttons.
 */
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { WorkflowChain, type WorkflowTransition } from '@/features/workflows/components/WorkflowChain';

import { EstadoAnulacionBadge } from '../components/EstadoAnulacionBadge';
import { TransicionAnulacionModal } from '../components/TransicionAnulacionModal';
import { useAnulacionDetalle } from '../hooks/useAnulacionDetalle';
import { useAnulacionChain } from '../hooks/useAnulacionChain';
import { ANULACION_TRANSICIONES, type AnulacionEstado } from '../api/anulacionesSchema';

const BUTTON_LABEL: Record<Exclude<AnulacionEstado, 'iniciada'>, { key: string; fallback: string }> = {
  autorizada: { key: 'anulaciones.detalle.aprobar', fallback: 'Aprobar' },
  ejecutada: { key: 'anulaciones.detalle.ejecutar', fallback: 'Ejecutar' },
  rechazada: { key: 'anulaciones.detalle.rechazar', fallback: 'Rechazar' },
};

export default function AnulacionDetalle(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { uuid } = useParams<{ uuid: string }>();

  const { anulacion, isLoading, error, setAnulacion } = useAnulacionDetalle(uuid ?? null);
  const { chain, isLoading: chainLoading, error: chainError } = useAnulacionChain(uuid ?? null);

  const [pendingDestino, setPendingDestino] = useState<Exclude<AnulacionEstado, 'iniciada'> | null>(
    null,
  );

  const transitions: WorkflowTransition[] = chain.map((row) => ({
    id: row.uuid,
    status: row.estado ?? t('anulaciones.estado.none', '—'),
    timestamp: row.timestamp_evento ?? row.vigente_desde,
    actor: row.uuid_usuario,
    observaciones: row.motivo,
  }));

  if (uuid === undefined) {
    return (
      <main className="p-4 md:p-6" data-testid="anulacion-detalle-page">
        <p role="alert">{t('anulaciones.detalle.missingUuid', 'Falta el identificador de la anulación.')}</p>
      </main>
    );
  }

  const destinos: ReadonlyArray<Exclude<AnulacionEstado, 'iniciada'>> =
    anulacion?.estado !== undefined && anulacion?.estado !== null
      ? (ANULACION_TRANSICIONES[anulacion.estado] as ReadonlyArray<Exclude<AnulacionEstado, 'iniciada'>>)
      : [];

  return (
    <main className="space-y-4 p-4 md:p-6" data-testid="anulacion-detalle-page">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t('anulaciones.detalle.title', 'Detalle de la anulación')}
          </h1>
          <p className="text-muted-foreground font-mono text-xs">{uuid}</p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => navigate('/anulaciones')}
          data-testid="anulacion-detalle-back"
        >
          {t('anulaciones.detalle.back', 'Volver a la bandeja')}
        </Button>
      </header>

      {isLoading && anulacion === undefined && (
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {t('anulaciones.detalle.loading', 'Cargando anulación...')}
        </p>
      )}

      {error !== undefined && (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="anulacion-detalle-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('anulaciones.detalle.errorLoading', 'No se pudo cargar la anulación.')}
        </p>
      )}

      {anulacion !== undefined && (
        <>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <CardTitle className="text-sm">{t('anulaciones.detalle.dataTitle', 'Datos')}</CardTitle>
              <EstadoAnulacionBadge estado={anulacion.estado} />
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
              <div>
                <span className="text-muted-foreground">{t('anulaciones.detalle.tipo', 'Tipo anulable')}: </span>
                {anulacion.tipo_anulable ?? '—'}
              </div>
              <div>
                <span className="text-muted-foreground">{t('anulaciones.detalle.sucursal', 'Sucursal')}: </span>
                <span className="font-mono text-xs">{anulacion.uuid_sucursal ?? '—'}</span>
              </div>
              <div>
                <span className="text-muted-foreground">
                  {t('anulaciones.detalle.ingreso', 'Ingreso anulado')}:{' '}
                </span>
                <span className="font-mono text-xs">{anulacion.uuid_ingreso ?? '—'}</span>
              </div>
              <div>
                <span className="text-muted-foreground">
                  {t('anulaciones.detalle.salida', 'Salida anulada')}:{' '}
                </span>
                <span className="font-mono text-xs">{anulacion.uuid_salida ?? '—'}</span>
              </div>
              <div>
                <span className="text-muted-foreground">{t('anulaciones.detalle.fecha', 'Fecha del evento')}: </span>
                {anulacion.timestamp_evento ?? '—'}
              </div>
              <div className="sm:col-span-2">
                <span className="text-muted-foreground">{t('anulaciones.detalle.motivo', 'Motivo')}: </span>
                {anulacion.motivo ?? '—'}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <CardTitle className="text-sm">{t('anulaciones.detalle.historyTitle', 'Historial de transiciones')}</CardTitle>
              <div className="flex gap-2">
                {destinos.length === 0 ? (
                  <span
                    className="text-xs text-muted-foreground"
                    data-testid="anulacion-detalle-terminal"
                  >
                    {t('anulaciones.detalle.terminal', 'Esta anulación ya está en un estado terminal.')}
                  </span>
                ) : (
                  destinos.map((destino) => (
                    <Button
                      key={destino}
                      type="button"
                      variant={destino === 'rechazada' ? 'destructive' : 'default'}
                      size="sm"
                      onClick={() => setPendingDestino(destino)}
                      data-testid={`anulacion-detalle-transicion-${destino}`}
                    >
                      {t(BUTTON_LABEL[destino].key, BUTTON_LABEL[destino].fallback)}
                    </Button>
                  ))
                )}
              </div>
            </CardHeader>
            <CardContent>
              <WorkflowChain
                transitions={transitions}
                isLoading={chainLoading}
                error={chainError ?? null}
                renderStatusBadge={(status) => (
                  <EstadoAnulacionBadge
                    estado={
                      status === 'iniciada' ||
                      status === 'autorizada' ||
                      status === 'ejecutada' ||
                      status === 'rechazada'
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

      {pendingDestino !== null && (
        <TransicionAnulacionModal
          uuidAnulacion={uuid}
          estadoDestino={pendingDestino}
          open
          onClose={() => setPendingDestino(null)}
          onTransicionada={(updated) => {
            setAnulacion(updated);
            setPendingDestino(null);
          }}
        />
      )}
    </main>
  );
}
