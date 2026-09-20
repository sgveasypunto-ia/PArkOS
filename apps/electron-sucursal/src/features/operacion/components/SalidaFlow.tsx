/**
 * `<SalidaFlow />` — rotation-branch orchestration wrapper for HU-F7.2
 * (REQ-OPS-152 + REQ-OPS-154).
 *
 * Composes `<CotizacionPanel />` (F7.1 presentational) with the
 * `useRegistrarSalida` SWR mutation hook. On a successful 201 with
 * `tipo_salida='ROTACION'`, opens the pago drawer via the
 * single-drawer store (REQ-OPS-138 invariant). On 409, surfaces a
 * localized banner via the inline error state.
 *
 * Mirrors `useCotizacion.ts:155-159` for the 401 → clear-auth +
 * `parkos:auth:cleared` contract (already handled inside
 * `useRegistrarSalida`).
 *
 * Reuses F7.1 invariant: REQ-OPS-138 single-drawer — F7.2 NEVER owns
 * drawer state; it calls `useDashboardDrawerStore.open('pago', ...)`.
 */
import { useState } from 'react';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

import { useRegistrarSalida, SalidaDuplicadaError } from '../hooks/useRegistrarSalida';
import type { SalidaReadForzado } from '../api/salidaApi';
import { CotizacionPanel } from './CotizacionPanel';
import type { CotizarFacturacion } from '../hooks/useCotizacion';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

export interface SalidaFlowProps {
  /** Active ingreso UUID (parent owns the lookup). */
  uuidIngreso: string;
  /** Canonical `CotizarFacturacion` from `useCotizacion` (cobrar:true). */
  cotizacion: CotizarFacturacion;
  /** Seconds remaining on `vigente_hasta` (from `useCountdown`). */
  secondsLeft: number;
  /** Fetch error from `useCotizacion` polling. */
  error: Error | null | undefined;
  /** Parent wires to SWR `mutate()` for manual re-fetch. */
  onRecalcular: () => void;
  /** Anchor ID used by `useDashboardDrawerStore.open('pago', anchorId)`. */
  pagoAnchorId: string;
  /**
   * Optional override for the post-201 path. Defaults to
   * `useDashboardDrawerStore.open('pago', pagoAnchorId)`. SalidaPanel
   * passes nothing; tests use this to spy on the routing call.
   */
  onPagoOpen?: (pagoAnchorId: string) => void;
}

/**
 * Renders `<CotizacionPanel />` with `onConfirmar` wired to
 * `useRegistrarSalida.trigger()`. On `tipo_salida='ROTACION'`, fires
 * the pago drawer (REQ-OPS-138). On `SalidaDuplicadaError` (409),
 * surfaces the inline error so CotizacionPanel renders the banner.
 */
export function SalidaFlow({
  uuidIngreso,
  cotizacion,
  secondsLeft,
  error,
  onRecalcular,
  pagoAnchorId,
  onPagoOpen,
}: SalidaFlowProps): JSX.Element {
  const { trigger } = useRegistrarSalida();
  const openDrawer = useDashboardDrawerStore((s) => s.open);
  const [registrarError, setRegistrarError] = useState<Error | null>(null);

  const handleConfirmar = async (): Promise<void> => {
    setRegistrarError(null);
    try {
      const result: SalidaReadForzado = await trigger({ uuid_ingreso: uuidIngreso });
      if (result.tipo_salida === 'ROTACION') {
        if (onPagoOpen) {
          onPagoOpen(pagoAnchorId);
        } else {
          openDrawer('pago', pagoAnchorId);
        }
      }
    } catch (err) {
      // 409 → SalidaDuplicadaError (typed, carries uuid_ingreso).
      // 401 → already handled inside useRegistrarSalida (auth clear).
      // Other → bubble up as a generic Error.
      if (err instanceof SalidaDuplicadaError || err instanceof ParkosHttpError) {
        setRegistrarError(err);
      } else {
        setRegistrarError(err as Error);
      }
    }
  };

  return (
    <div data-testid="salida-flow" data-anchor-for="pago" id={pagoAnchorId}>
      <CotizacionPanel
        data={cotizacion}
        error={registrarError ?? error}
        secondsLeft={secondsLeft}
        onConfirmar={() => {
          void handleConfirmar();
        }}
        onRecalcular={onRecalcular}
      />
    </div>
  );
}