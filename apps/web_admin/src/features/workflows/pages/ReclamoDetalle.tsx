/**
 * `<ReclamoDetalle />` -- HU-F20.3 detail screen: one reclamo's data +
 * its best-effort transition history (`useReclamoChain`, generic
 * `<WorkflowChain />`) + the "transición" actions
 * (`POST /workflows/reclamos/{uuid}/transicion`, via
 * `TransicionReclamoModal`). Mirrors `AnulacionDetalle.tsx`.
 *
 * Which destination buttons render depends on the CURRENT tip's
 * `estado` (`RECLAMO_TRANSICIONES`):
 *   - `recibido`                       -> "Tomar en revisión" (en_investigacion)
 *   - `en_investigacion`               -> "Resolver" (resuelto) / "Rechazar" (rechazado)
 *   - `resuelto`/`rechazado`           -> terminal, no buttons.
 *
 * `tipo_reclamable` is EXACTLY `ingreso | salida | factura` server-side
 * (the real polymorphic discriminator -- see `reclamosSchema.ts`'s
 * docblock). A `subscripcion` 4th category sometimes mentioned in
 * plain-language task descriptions does NOT exist server-side, so it is
 * deliberately NOT handled here. This app has no dedicated
 * `/operacion/{ingresos,salidas,facturas}/:uuid` DETAIL route (only flat
 * `GET /api/v1/operacion/ingresos` / `/salidas` LIST endpoints exist, per
 * `reporteria/api/reporteriaApi.ts`) to drill into, so `uuid_reclamable`
 * just renders as raw text below -- no fake link is invented.
 *
 * `actor` on `<WorkflowChain />` is ALWAYS `null` for reclamos: unlike
 * `prod.anulacion`, `prod.reclamo` has NO `uuid_usuario` column at all
 * (confirmed against the real ORM model) -- do not invent one.
 */
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { useGoBack } from '@/lib/useGoBack';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { WorkflowChain, type WorkflowTransition } from '@/features/workflows/components/WorkflowChain';

import { EstadoReclamoBadge } from '../components/EstadoReclamoBadge';
import { TransicionReclamoModal } from '../components/TransicionReclamoModal';
import { useReclamoDetalle } from '../hooks/useReclamoDetalle';
import { useReclamoChain } from '../hooks/useReclamoChain';
import { RECLAMO_TRANSICIONES, type ReclamoEstado } from '../api/reclamosSchema';

const BUTTON_LABEL: Record<Exclude<ReclamoEstado, 'recibido'>, { key: string; fallback: string }> = {
  en_investigacion: { key: 'reclamos.detalle.tomarEnRevision', fallback: 'Tomar en revisión' },
  resuelto: { key: 'reclamos.detalle.resolver', fallback: 'Resolver' },
  rechazado: { key: 'reclamos.detalle.rechazar', fallback: 'Rechazar' },
};

export default function ReclamoDetalle(): JSX.Element {
  const { t } = useTranslation();
  // PT-1: back to the previous screen, fallback to the list on a deep link.
  const goBack = useGoBack('/reclamos');
  const { uuid } = useParams<{ uuid: string }>();

  const { reclamo, isLoading, error, setReclamo } = useReclamoDetalle(uuid ?? null);
  const { chain, isLoading: chainLoading, error: chainError } = useReclamoChain(uuid ?? null);

  const [pendingDestino, setPendingDestino] = useState<Exclude<ReclamoEstado, 'recibido'> | null>(
    null,
  );

  const transitions: WorkflowTransition[] = chain.map((row) => ({
    id: row.uuid,
    status: row.estado ?? t('reclamos.estado.none', '—'),
    timestamp: row.timestamp_evento ?? row.vigente_desde,
    // `prod.reclamo` has no `uuid_usuario` column -- see module docblock.
    actor: null,
    observaciones: row.motivo,
  }));

  if (uuid === undefined) {
    return (
      <main className="p-4 md:p-6" data-testid="reclamo-detalle-page">
        <p role="alert">{t('reclamos.detalle.missingUuid', 'Falta el identificador del reclamo.')}</p>
      </main>
    );
  }

  const destinos: ReadonlyArray<Exclude<ReclamoEstado, 'recibido'>> =
    reclamo?.estado !== undefined && reclamo?.estado !== null
      ? (RECLAMO_TRANSICIONES[reclamo.estado] as ReadonlyArray<Exclude<ReclamoEstado, 'recibido'>>)
      : [];

  return (
    <main className="space-y-4 p-4 md:p-6" data-testid="reclamo-detalle-page">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t('reclamos.detalle.title', 'Detalle del reclamo')}
          </h1>
          <p className="text-muted-foreground font-mono text-xs">{uuid}</p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => goBack()}
          data-testid="reclamo-detalle-back"
        >
          {t('reclamos.detalle.back', 'Volver a la bandeja')}
        </Button>
      </header>

      {isLoading && reclamo === undefined && (
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {t('reclamos.detalle.loading', 'Cargando reclamo...')}
        </p>
      )}

      {error !== undefined && (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="reclamo-detalle-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('reclamos.detalle.errorLoading', 'No se pudo cargar el reclamo.')}
        </p>
      )}

      {reclamo !== undefined && (
        <>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <CardTitle className="text-sm">{t('reclamos.detalle.dataTitle', 'Datos')}</CardTitle>
              <EstadoReclamoBadge estado={reclamo.estado} />
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
              <div>
                <span className="text-muted-foreground">{t('reclamos.detalle.tipo', 'Tipo reclamable')}: </span>
                {reclamo.tipo_reclamable ?? '—'}
              </div>
              <div>
                <span className="text-muted-foreground">{t('reclamos.detalle.sucursal', 'Sucursal')}: </span>
                <span className="font-mono text-xs">{reclamo.uuid_sucursal ?? '—'}</span>
              </div>
              <div>
                <span className="text-muted-foreground">
                  {t('reclamos.detalle.reclamable', 'Elemento reclamado')}:{' '}
                </span>
                <span className="font-mono text-xs">{reclamo.uuid_reclamable ?? '—'}</span>
              </div>
              <div>
                <span className="text-muted-foreground">{t('reclamos.detalle.fecha', 'Fecha del evento')}: </span>
                {reclamo.timestamp_evento ?? '—'}
              </div>
              <div className="sm:col-span-2">
                <span className="text-muted-foreground">{t('reclamos.detalle.motivo', 'Motivo')}: </span>
                {reclamo.motivo ?? '—'}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <CardTitle className="text-sm">{t('reclamos.detalle.historyTitle', 'Historial de transiciones')}</CardTitle>
              <div className="flex gap-2">
                {destinos.length === 0 ? (
                  <span className="text-xs text-muted-foreground" data-testid="reclamo-detalle-terminal">
                    {t('reclamos.detalle.terminal', 'Este reclamo ya está en un estado terminal.')}
                  </span>
                ) : (
                  destinos.map((destino) => (
                    <Button
                      key={destino}
                      type="button"
                      variant={destino === 'rechazado' ? 'destructive' : 'default'}
                      size="sm"
                      onClick={() => setPendingDestino(destino)}
                      data-testid={`reclamo-detalle-transicion-${destino}`}
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
                  <EstadoReclamoBadge
                    estado={
                      status === 'recibido' ||
                      status === 'en_investigacion' ||
                      status === 'resuelto' ||
                      status === 'rechazado'
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
        <TransicionReclamoModal
          uuidReclamo={uuid}
          estadoDestino={pendingDestino}
          open
          onClose={() => setPendingDestino(null)}
          onTransicionada={(updated) => {
            setReclamo(updated);
            setPendingDestino(null);
          }}
        />
      )}
    </main>
  );
}
