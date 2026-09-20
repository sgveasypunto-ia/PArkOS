/**
 * `<FacturaDetalle />` — routed page (HU-F8.2, REQ-OPS-167 + REQ-OPS-170).
 *
 * Lives at `/factura-electronica/:uuid` and mounts inside
 * `<ProtectedRoute>` (App.tsx). The page is a thin container over
 * two hooks:
 *
 *   - `useFacturaElectronica(uuid)` — 30 s polling (terminal-gated
 *     via `computeRefreshInterval` — see hooks/useFacturaElectronica.ts)
 *     so the operator sees the estado DIAN evolve live.
 *   - `useReintentarFE()` — `POST /reintentar` with Idempotency-Key
 *     SHA-256 + 409 `NumeracionAgotadaError` + 401 auth-clear +
 *     `mutate(cache)` re-engages polling after 201.
 *
 * Rendering rules:
 *   - Localized `estado` (`fe.estado.pendiente|enviado|aceptado|rechazado`).
 *   - `cufe` visible ONLY when `aceptado` (hidden otherwise).
 *   - "Reintentar" button ONLY when `rechazado`; disabled while
 *     `isMutating`.
 *   - `role="alert"` banner ONLY when the trigger throws
 *     `NumeracionAgotadaError` (WCAG 2.1 AA).
 *
 * The page bypasses `<FacturaElectronicaRetryPanel />` on purpose
 * (the panel still has its own reintentar button for Dashboard
 * mount contexts) — keeping the page self-contained avoids
 * double-rendering the button when both panel + page coexist.
 */
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

import { useFacturaElectronica } from '../hooks/useFacturaElectronica';
import {
  NumeracionAgotadaError,
  useReintentarFE,
} from '../hooks/useReintentarFE';

export function FacturaDetalle(): JSX.Element {
  const { uuid } = useParams<{ uuid: string }>();
  const { t } = useTranslation('facturacion');
  const { data } = useFacturaElectronica(uuid ?? null);
  const { trigger: reintentar, isMutating } = useReintentarFE();
  const [numeracionAgotada, setNumeracionAgotada] = useState(false);

  const estado = data?.estado_dian ?? null;
  const cufe = data?.respuesta_proveedor?.cufe ?? null;

  const estadoLabel = (() => {
    if (estado === 'aceptado') return t('fe.estado.aceptado', { defaultValue: 'Aceptado' });
    if (estado === 'rechazado') return t('fe.estado.rechazado', { defaultValue: 'Rechazado' });
    if (estado === 'enviado') return t('fe.estado.enviado', { defaultValue: 'Enviado' });
    return t('fe.estado.pendiente', { defaultValue: 'Pendiente' });
  })();

  const handleReintentar = async (): Promise<void> => {
    if (!uuid) return;
    setNumeracionAgotada(false);
    try {
      await reintentar(uuid);
    } catch (err) {
      if (err instanceof NumeracionAgotadaError) {
        setNumeracionAgotada(true);
      }
      // Other errors (network, 5xx) bubble up — the page does not
      // surface them; F1.10 logs them server-side and the
      // `envio_dian` retry chain takes care of transient failures.
    }
  };

  return (
    <article
      className="mx-auto max-w-2xl space-y-4 p-4"
      data-testid="factura-detalle"
    >
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">
          {t('fe.titulo', { defaultValue: 'Factura electrónica' })}
        </h1>
      </header>

      <section className="space-y-2">
        <p className="text-sm text-muted-foreground">
          {t('fe.estado', { defaultValue: 'Estado DIAN' })}
        </p>
        <p className="text-lg font-medium" data-testid="fe-estado" data-estado={estado ?? ''}>
          {estadoLabel}
        </p>

        {cufe && estado === 'aceptado' && (
          <p className="text-sm" data-testid="fe-cufe">
            {t('fe.cufe', { defaultValue: 'CUFE' })}: <code>{cufe}</code>
          </p>
        )}
      </section>

      {estado === 'rechazado' && (
        <div>
          <Button
            type="button"
            onClick={() => {
              void handleReintentar();
            }}
            disabled={isMutating}
            data-testid="fe-reintentar"
          >
            {t('fe.reintentar', { defaultValue: 'Reintentar' })}
          </Button>
        </div>
      )}

      {numeracionAgotada && (
        <div
          role="alert"
          data-testid="fe-banner-numeracion-agotada"
          className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm"
        >
          {t('fe.errors.numeracion_agotada', {
            defaultValue: 'Numeración agotada. Contactar proveedor.',
          })}
        </div>
      )}
    </article>
  );
}
