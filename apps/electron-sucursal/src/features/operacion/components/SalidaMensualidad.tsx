/**
 * `<SalidaMensualidad />` — mensualidad-branch orchestration wrapper
 * for HU-F7.2 (REQ-OPS-153 + REQ-OPS-154) + HU-F7.3 (REQ-OPS-160).
 *
 * Renders `<CotizacionPanel />` for the mensualidad short-circuit
 * (`cobrar: false`). On a successful 201 with
 * `tipo_salida='MENSUALIDAD'`, builds a factura showing the full
 * fiscal breakdown plus a discount line netting to $0 (operator
 * directive, 2026-09-24 — see below), opens `<FacturaDisplayModal />`
 * with the result, and fires the typed `bridge.imprimir` envelope for
 * CU-15SM only AFTER the operator dismisses the modal.
 *
 * **MIGRATION 0050 (operator directive 2026-09-24).** Before this
 * change, a subscribed exit never touched `POST /facturacion/factura`
 * at all — REQ-OPS-153's "NO PagoModal opens here" meant NO factura,
 * period. The operator's new directive: "el valor a cobrar es = 0 mas
 * sin embargo en factura se debe mostrar todos los valores, + un
 * descuento = al valor a facturar por concepto de subscripcion /
 * mensualidad / plan, conforme se llame la subscripcion adquirida" —
 * confirmed explicitly that this factura DOES need the full DIAN
 * pipeline (same as CU-04/CU-05 rotacion), not just an internal
 * record. The `cotizacion` prop (from `<SalidaPanel />`'s live
 * `useCotizacion` poll, migration 0050 shape) already carries the
 * full breakdown + `concepto_descuento` (the plan's real name) — no
 * PagoModal / operator interaction needed, `medio_pago='suscripcion'`
 * identifies this as a $0-via-subscription payment.
 *
 * Print: the former CU-15SM `bridge.imprimir('salida_mensualidad', { uuid_salida })`
 * envelope carried no buffer (the main process rejected it), so nothing was ever
 * printed. The $0 invoice shown by the modal (placa, entrada/salida, tiempo,
 * servicio + descuento, detalle de impuestos, total 0) is now printed complete
 * on dismiss through `lib/print/facturaPrint`.
 *
 * F7.3 (REQ-OPS-160 / DEC-SUC-08 + DEC-SUC-27) — the print envelope
 * is fired ASYNCHRONOUSLY via `queueMicrotask` to avoid blocking the
 * React render commit (DEC-SUC-08 verbatim). The `bridge.imprimir`
 * call is wrapped in `try/catch` — a printer failure (offline,
 * disconnected, IPC channel error) MUST NOT block the operator's
 * flow. The salida is already persisted in `prod.salidas` so a
 * silent print failure is strictly better than a fatal one. F8.x
 * owns the reprint-with-cost workflow; F7.3 only fires the envelope.
 */
import { useRef, useState } from 'react';

import {
  useRegistrarSalida,
  SalidaDuplicadaError,
} from '../hooks/useRegistrarSalida';
import type { SalidaReadForzado } from '../api/salidaApi';
import { CotizacionPanel } from './CotizacionPanel';
import type { CotizarMensualidad } from '../hooks/useCotizacion';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useInvalidateConteosOperacion } from '../hooks/useInvalidateConteosOperacion';
import { useAuth } from '@parkos/ui-kit/hooks';
import { useSesionActiva } from '../../caja/hooks/useSesionActiva';
import { useRegistrarPago } from '../../facturacion/hooks/useRegistrarPago';
import { useDashboardDrawerStore } from '../../../renderer/store/dashboardDrawerStore';
import { FacturaDisplayModal } from '../../facturacion/components/FacturaDisplayModal';
import { dispararImpresionFactura, type ImprimirFacturaFn } from '../../../lib/print/facturaPrint';
import type { FacturaRead, PostFacturaSuscripcion } from '../../facturacion/api/facturaApi';

export interface SalidaMensualidadProps {
  uuidIngreso: string;
  /**
   * Live-polled cotizacion (migration 0050 shape: full fiscal
   * breakdown + `concepto_descuento`) — sourced from `<SalidaPanel
   * />`'s `useCotizacion(uuid_ingreso)`, same pattern `<SalidaFlow />`
   * already uses for rotacion's `subtotal_cop`/`total_cop`. Used to
   * build the discount factura after the salida is confirmed.
   */
  cotizacion: CotizarMensualidad;
  /**
   * H7: called right after `useRegistrarSalida.trigger()` resolves, i.e.
   * once the ingreso is closed server-side. The parent uses it to stop
   * polling `/cotizar` (which would now 404 `ingreso_no_encontrado`).
   */
  onSalidaConfirmada?: () => void;
  /**
   * D2: the parent already confirmed this ingreso's salida (survives a
   * remount of this component). Keeps the confirm button disabled.
   */
  yaConfirmada?: boolean;
  /**
   * Invoice printer; defaults to the shared `imprimirFactura` which sends the
   * COMPLETE $0 invoice (servicio + descuento + detalle de impuestos) through
   * the bridge. Tests override it.
   */
  imprimirFactura?: ImprimirFacturaFn;
}

export function SalidaMensualidad({
  uuidIngreso,
  cotizacion,
  imprimirFactura,
  onSalidaConfirmada,
  yaConfirmada = false,
}: SalidaMensualidadProps): JSX.Element {
  const { trigger } = useRegistrarSalida();
  const { trigger: triggerPago } = useRegistrarPago();
  // REGRESSION fix (2026-09-22): invalidate the live-count SWR
  // caches immediately after a successful salida (ROTACION or
  // MENSUALIDAD) so <MiTurnoPanel />, <OcupacionPanel /> (Inventario)
  // and <VehiculosDentroList /> re-fetch without waiting for their
  // 10–15s polling tick — same fix as in <SalidaFlow />.
  const invalidarConteos = useInvalidateConteosOperacion();
  const { sucursal } = useAuth();
  const { sesion } = useSesionActiva();
  const [error, setError] = useState<Error | null>(null);
  // D2: set as soon as the salida POST resolves. The ingreso is closed
  // server-side, so confirming again could only duplicate the exit.
  const [salidaRegistrada, setSalidaRegistrada] = useState(false);
  const confirmandoRef = useRef(false);
  // HU-F8.4-equivalent for mensualidad (migration 0050): holds the
  // FacturaRead from the discount-factura POST so <FacturaDisplayModal
  // /> can render the full breakdown before the CU-15SM ticket prints.
  const [facturaDisplay, setFacturaDisplay] = useState<FacturaRead | null>(null);
  const handleConfirmar = async (): Promise<void> => {
    if (confirmandoRef.current || salidaRegistrada || yaConfirmada) return;
    confirmandoRef.current = true;
    setError(null);
    try {
      const result: SalidaReadForzado = await trigger({ uuid_ingreso: uuidIngreso });
      setSalidaRegistrada(true);
      // H7: the ingreso is closed now — tell the parent to stop polling /cotizar.
      onSalidaConfirmada?.();
      void invalidarConteos({
        uuid_sucursal: sucursal?.uuid ?? null,
        uuid_sesion: sesion?.uuid ?? null,
      });
      if (result.tipo_salida === 'MENSUALIDAD') {
        // MIGRATION 0050 (operator directive 2026-09-24): build the
        // discount factura — one `servicio` line for the full value
        // (as if it were rotacion) + one `descuento` line of the SAME
        // value (concept = the real subscription plan name), netting
        // `total=0`. `medio_pago='suscripcion'` identifies this as a
        // $0-via-subscription payment (no voucher, no operator
        // interaction — see V7 in `api/v1/facturacion.py`, exempt for
        // this medio_pago same as `efectivo`).
        const payload: PostFacturaSuscripcion = {
          uuid_salida: result.uuid,
          medio_pago: 'suscripcion',
          items: [
            {
              tipo: 'servicio',
              concepto: 'Estadía',
              cantidad: 1,
              valor_unitario: cotizacion.total,
            },
            {
              tipo: 'descuento',
              concepto: `Descuento por mensualidad - ${cotizacion.concepto_descuento}`,
              cantidad: 1,
              valor_unitario: cotizacion.total,
            },
          ],
          subtotal: cotizacion.subtotal,
          total: 0,
          // QA backlog cleanup (2026-10-02): this IS the "pago
          // automático" flow (no operator interaction, no PagoSheet) —
          // without this, the factura_pagos row landed with
          // `uuid_sesion IS NULL` even though a real turno was open,
          // silently excluding it from that session's arqueo. See
          // `facturaApi.ts::PostFacturaSuscripcion.uuid_sesion`.
          uuid_sesion: sesion?.uuid ?? null,
        };
        const facturaResult = await triggerPago(payload);
        setFacturaDisplay(facturaResult);
      }
    } catch (err) {
      if (err instanceof SalidaDuplicadaError || err instanceof ParkosHttpError) {
        setError(err);
      } else {
        setError(err as Error);
      }
    } finally {
      confirmandoRef.current = false;
    }
  };

  return (
    <div data-testid="salida-mensualidad">
      <CotizacionPanel
        data={cotizacion}
        error={error}
        secondsLeft={Number.MAX_SAFE_INTEGER}
        onConfirmar={() => {
          void handleConfirmar();
        }}
        onRecalcular={() => undefined}
        confirmarDeshabilitado={salidaRegistrada || yaConfirmada}
      />
      {/* F7.3 (DEC-SUC-27 + DEC-SUC-08) — CU-15SM prints IMMEDIATELY
          after the operator dismisses the discount-factura modal
          (deferred to the next microtask so the React render commit
          is not blocked; wrapped in try/catch so a printer failure
          never blocks the operator). */}
      <FacturaDisplayModal
        factura={facturaDisplay}
        onClose={() => {
          setFacturaDisplay(null);
          // The $0 invoice (what the modal just showed) prints complete.
          if (facturaDisplay) dispararImpresionFactura(facturaDisplay, imprimirFactura);
          // The salida is fully done once the factura modal is
          // dismissed — close the dashboard drawer so the operator
          // does not have to click outside it (H5). Print is already
          // queued, so unmounting this component is safe.
          useDashboardDrawerStore.getState().close();
        }}
      />
    </div>
  );
}
