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
 *
 * REGRESSION fix (2026-09-22, directiva del operador): after a
 * successful salida we invalidate the live-count SWR caches so
 * <MiTurnoPanel />, <OcupacionPanel /> (Inventario) and
 * <VehiculosDentroList /> re-fetch immediately instead of waiting
 * for their 10–15s polling tick. Without this, the operator sees
 * the same activo count for up to 15s after confirming the salida
 * — the panels look "hardcoded".
 */
import { useCallback, useState } from 'react';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

import { useRegistrarSalida, SalidaDuplicadaError } from '../hooks/useRegistrarSalida';
import type { SalidaReadForzado } from '../api/salidaApi';
import { CotizacionPanel } from './CotizacionPanel';
import type { CotizarFacturacion } from '../hooks/useCotizacion';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useInvalidateConteosOperacion } from '../hooks/useInvalidateConteosOperacion';
import { useAuth } from '@parkos/ui-kit/hooks';
import { useSesionActiva } from '../../caja/hooks/useSesionActiva';

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
  /**
   * Anchor ID used by `useDashboardDrawerStore.open('pago', anchorId)`.
   * Only consulted by the default fallback path (when `onPagoOpen` is
   * not provided). When `onPagoOpen` IS provided, the callback owns
   * the full drawer-open contract — including the typed `pagoContext`
   * payload — so the parent can pass the live `uuid_ingreso` and
   * `total_cop` from its cotizacion snapshot.
   */
  pagoAnchorId: string;
  /**
   * Optional override for the post-201 ROTACION path. The callback
   * owns the full drawer-open contract (including the typed
   * `pagoContext` payload — `uuid_ingreso`, `uuid_salida`, and
   * `total_cop`) so the parent can pass the live values from its
   * cotizacion snapshot. The callback receives the just-created
   * `uuid_salida` because `<SalidaFlow>` is the one that owns the
   * `trigger()` call to `POST /operacion/salidas`; without
   * forwarding it the parent can't build a complete `pagoContext`.
   *
   * F8.1-b (HU-F8.1-anular-salida-no-pagada, 2026-09-23): the
   * `uuid_salida` is also required downstream so `<PagoSheet>`
   * can auto-annul the salida on any close-without-pay path
   * (Cancelar / X / overlay click / Escape). Without the annulment,
   * the ingreso stays `cerrado` and the operator can never recover
   * the cobro — `prod.salidas` is `[A]` (append-only) so the only
   * recovery path is `prod.anulaciones` (`[L-W]` workflow row with
   * `tipo_anulable='salida'`).
   *
   * Defaults to `useDashboardDrawerStore.open('pago', pagoAnchorId)`
   * with NO `pagoContext` — that fallback is only safe for tests
   * that spy on the routing call, NOT for production.
   */
  onPagoOpen?: (uuid_salida: string) => void;
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
  const invalidarConteos = useInvalidateConteosOperacion();
  // Branch + sesion UUIDs feed the SWR key matcher — same sources
  // the dashboard uses so the values agree at all times.
  const { sucursal } = useAuth();
  const { sesion } = useSesionActiva();
  const [registrarError, setRegistrarError] = useState<Error | null>(null);

  const handleConfirmar = useCallback(async (): Promise<void> => {
    setRegistrarError(null);
    try {
      const result: SalidaReadForzado = await trigger({ uuid_ingreso: uuidIngreso });
      // REGRESSION fix (2026-09-22): invalidate the live-count SWR
      // caches immediately after a successful salida so the right-
      // sidebar <MiTurnoPanel />, the Inventario <OcupacionPanel />
      // and the main <VehiculosDentroList /> re-fetch without waiting
      // for their 10–15s polling tick. Without this, the operator
      // sees the same `activos` count for up to 15s after confirming
      // the salida — looks "hardcoded".
      void invalidarConteos({
        uuid_sucursal: sucursal?.uuid ?? null,
        uuid_sesion: sesion?.uuid ?? null,
      });
      if (result.tipo_salida === 'ROTACION') {
        // HU-F8.1 regression fix: when the parent provides
        // `onPagoOpen`, defer the drawer-open contract to it so the
        // caller can pass the typed `pagoContext` (uuid_ingreso +
        // uuid_salida + total_cop). The fallback path opens the
        // drawer with NO context — kept only for backwards
        // compatibility with tests that spy on the open call;
        // production wiring MUST pass `onPagoOpen` to keep
        // `<PagoSheet>` functional.
        //
        // F8.1-b (2026-09-23): forward `result.uuid` (the just-
        // created `prod.salidas.uuid`) so the parent can include
        // it in the `pagoContext` payload. `<PagoSheet>` uses it
        // to auto-annul on close-without-pay (Cancelar / X /
        // overlay / Escape).
        if (onPagoOpen) {
          onPagoOpen(result.uuid);
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
  }, [trigger, uuidIngreso, invalidarConteos, sucursal?.uuid, sesion?.uuid, pagoAnchorId, onPagoOpen, openDrawer]);

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