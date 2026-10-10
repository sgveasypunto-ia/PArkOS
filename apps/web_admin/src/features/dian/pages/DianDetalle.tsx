/**
 * `<DianDetalle />` -- HU-F20.5 detail screen for one envio_dian row:
 * raw `payload` / `respuesta_proveedor` (PLAIN TEXT ONLY -- these are
 * third-party-controlled JSON payloads; NEVER rendered via
 * `dangerouslySetInnerHTML` or any HTML-interpreting path, which would
 * be an XSS vector if a provider or a malformed payload ever smuggled
 * markup through `motivo_rechazo` or similar free-text provider fields),
 * the retry-chain history (`<DianRetryHistory />`), and the "Reintentar"
 * action.
 *
 * KNOWN GAP (BE-side, confirmed not assumed -- see `useEnvioDianChain.ts`
 * and `envioDianApi.ts` docblocks): `envio_dian` has no single-item GET
 * and no `/history` endpoint, unlike `prod.alerta`. So this page cannot
 * recover its row from a direct deep-link or a hard refresh -- it only
 * renders when reached via `<DianCola />`'s row click, which forwards
 * the FULL row through router `state`. A direct link shows an
 * informational empty state instead of crashing. This mirrors (and goes
 * one step further than) `AlertaDetalle.tsx`'s own documented
 * `severity`-only forwarding gap.
 *
 * No "Anular" / revoke action exists here by design: `POST
 * /revocacion-factura-webhook` is invoked BY DIAN (an inbound webhook),
 * never admin-initiated (ABIERTO-55, already documented, out of scope).
 */
import { useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/button';
import { useGoBack } from '@/lib/useGoBack';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { useRetryEnvioDian } from '../hooks/useRetryEnvioDian';
import { DianRetryHistory } from '../components/DianRetryHistory';
import { canRetryEnvioDian } from '../lib/canRetryEnvioDian';
import { EstadoEnvioDianBadge } from '../components/EstadoEnvioDianBadge';
import type { EnvioDianRead } from '../api/envioDianSchema';

interface LocationState {
  envio?: EnvioDianRead;
}

/** Plain-text JSON rendering -- never HTML-interpreted (XSS defense). */
function JsonPane({ value }: { value: Record<string, unknown> | null }): JSX.Element {
  const { t } = useTranslation();
  if (value === null) {
    return <p className="text-sm text-muted-foreground">{t('dian.detalle.noData', 'Sin datos.')}</p>;
  }
  return (
    <pre className="max-h-80 overflow-auto rounded-md bg-muted/40 p-3 text-xs whitespace-pre-wrap break-words">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export default function DianDetalle(): JSX.Element {
  const { t } = useTranslation();
  // PT-1: back to the previous screen, fallback to the queue on a deep link.
  const goBack = useGoBack('/dian');
  const { uuid } = useParams<{ uuid: string }>();
  const location = useLocation();
  const envio = (location.state as LocationState | null)?.envio;

  const { trigger, isRetrying, error: retryError, data: retryResult } = useRetryEnvioDian();
  const [justRetried, setJustRetried] = useState(false);

  async function handleRetry(): Promise<void> {
    if (envio === undefined || envio.uuid_factura_electronica === null) return;
    const result = await trigger(envio.uuid_factura_electronica);
    if (result) setJustRetried(true);
  }

  if (envio === undefined) {
    return (
      <main
        className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
        data-testid="dian-detalle-page"
      >
        <PageHeader
          title={t('dian.detalle.title', 'Detalle del envío DIAN')}
          subtitle={<span className="font-mono text-xs">{uuid}</span>}
          actions={
            <Button
              type="button"
              variant="outline"
              onClick={() => goBack()}
              data-testid="dian-detalle-back"
            >
              {t('dian.detalle.back', 'Volver a la cola')}
            </Button>
          }
        />
        <div
          role="status"
          aria-live="polite"
          data-testid="dian-detalle-no-state"
          className="rounded-md border bg-muted/40 p-4 text-sm text-muted-foreground"
        >
          {t(
            'dian.detalle.noState',
            'Este envío no está disponible por acceso directo o recarga -- volvé a la cola y abrilo desde ahí.',
          )}
        </div>
      </main>
    );
  }

  const retrying = envio.uuid_factura_electronica !== null && isRetrying(envio.uuid_factura_electronica);
  const retryEnabled = canRetryEnvioDian(envio) && !retrying && !justRetried;

  return (
    <main
      className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
      data-testid="dian-detalle-page"
    >
      <PageHeader
        title={t('dian.detalle.title', 'Detalle del envío DIAN')}
        subtitle={<span className="font-mono text-xs">{envio.uuid}</span>}
        actions={
          <Button
            type="button"
            variant="outline"
            onClick={() => goBack()}
            data-testid="dian-detalle-back"
          >
            {t('dian.detalle.back', 'Volver a la cola')}
          </Button>
        }
      />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle className="text-sm">{t('dian.detalle.dataTitle', 'Datos')}</CardTitle>
          <EstadoEnvioDianBadge estado={envio.estado} />
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          <div>
            <span className="text-muted-foreground">{t('dian.detalle.sucursal', 'Sucursal')}: </span>
            <span className="font-mono text-xs">{envio.uuid_sucursal ?? '—'}</span>
          </div>
          <div>
            <span className="text-muted-foreground">{t('dian.detalle.factura', 'Factura electrónica')}: </span>
            <span className="font-mono text-xs">{envio.uuid_factura_electronica ?? '—'}</span>
          </div>
          <div>
            <span className="text-muted-foreground">{t('dian.detalle.cufe', 'CUFE')}: </span>
            <span className="font-mono text-xs">{envio.cufe ?? '—'}</span>
          </div>
          <div>
            <span className="text-muted-foreground">{t('dian.detalle.fecha', 'Fecha del evento')}: </span>
            {envio.timestamp_evento ?? '—'}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle className="text-sm">{t('dian.detalle.retryTitle', 'Reintentar envío')}</CardTitle>
          <Button
            type="button"
            variant="destructive"
            size="sm"
            disabled={!retryEnabled}
            onClick={() => {
              void handleRetry();
            }}
            data-testid="dian-detalle-retry-button"
            title={
              canRetryEnvioDian(envio)
                ? undefined
                : t('dian.table.retryDisabledTitle', 'Solo se puede reintentar un envío rechazado.')
            }
          >
            {retrying
              ? t('dian.table.retrying', 'Reintentando…')
              : t('dian.table.retryButton', 'Reintentar')}
          </Button>
        </CardHeader>
        <CardContent>
          {retryError !== undefined && (
            <p role="alert" data-testid="dian-detalle-retry-error" className="text-sm text-destructive">
              {retryError.message}
            </p>
          )}
          {justRetried && retryResult !== undefined && (
            <p
              role="status"
              data-testid="dian-detalle-retry-success"
              className="rounded-md bg-success px-3 py-2 text-sm text-success-foreground"
            >
              {t('dian.detalle.retrySuccess', 'Reintento creado: nuevo envío {{uuid}} en estado pendiente.', {
                uuid: retryResult.uuid,
              })}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('dian.detalle.payloadTitle', 'Payload enviado')}</CardTitle>
        </CardHeader>
        <CardContent>
          <JsonPane value={envio.payload} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('dian.detalle.respuestaTitle', 'Respuesta del proveedor')}</CardTitle>
        </CardHeader>
        <CardContent>
          <JsonPane value={envio.respuesta_proveedor} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('dian.detalle.historyTitle', 'Historial de reintentos')}</CardTitle>
        </CardHeader>
        <CardContent>
          <DianRetryHistory tip={envio} />
        </CardContent>
      </Card>
    </main>
  );
}
