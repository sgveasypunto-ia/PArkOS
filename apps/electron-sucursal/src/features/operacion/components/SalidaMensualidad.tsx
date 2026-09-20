/**
 * `<SalidaMensualidad />` — mensualidad-branch orchestration wrapper
 * for HU-F7.2 (REQ-OPS-153 + REQ-OPS-154).
 *
 * Renders `<CotizacionPanel />` for the mensualidad short-circuit
 * (`cobrar: false`). On a successful 201 with
 * `tipo_salida='MENSUALIDAD'`, fires the typed `bridge.imprimir`
 * envelope for CU-15SM (Fase 7.3 owns the actual print pipeline +
 * `escposBuilder`; F7.2 only emits the typed event).
 *
 * REQ-OPS-153: NO PagoModal opens here. The fee is settled by the
 * mensualidad subscription — DEC-SUC-27 verbatim, CU-15SM prints
 * immediately at salida mensualidad.
 */
import { useState } from 'react';

import {
  useRegistrarSalida,
} from '../hooks/useRegistrarSalida';
import type { SalidaReadForzado } from '../api/salidaApi';
import { CotizacionPanel } from './CotizacionPanel';
import type { CotizarMensualidad } from '../hooks/useCotizacion';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

export interface SalidaMensualidadProps {
  uuidIngreso: string;
  /** Optional override for the post-201 print envelope; tests spy on it. */
  onPrint?: (payload: { uuid_salida: string }) => void;
  /** Optional override for `window.bridge?.imprimir`; defaults to the global. */
  firePrintEnvelope?: (payload: { uuid_salida: string }) => void;
}

/**
 * Bridge print-envelope emitter (typed event `salida_mensualidad`).
 * F7.3 owns the actual `escposBuilder.build('salida_mensualidad', payload)`
 * + `bridge.imprimir` payload shape; F7.2 only fires the typed event
 * envelope. If `window.bridge?.imprimir` exists, we use it; otherwise
 * we fall back to the test override.
 */
function defaultFirePrintEnvelope(payload: { uuid_salida: string }): void {
  const bridge = (globalThis as { window?: { bridge?: { imprimir?: (k: string, p: unknown) => void } } }).window?.bridge;
  if (bridge?.imprimir) {
    bridge.imprimir('salida_mensualidad', payload);
  }
}

export function SalidaMensualidad({
  uuidIngreso,
  onPrint,
  firePrintEnvelope,
}: SalidaMensualidadProps): JSX.Element {
  const { trigger } = useRegistrarSalida();
  const [error, setError] = useState<Error | null>(null);

  const handleConfirmar = async (): Promise<void> => {
    setError(null);
    try {
      const result: SalidaReadForzado = await trigger({ uuid_ingreso: uuidIngreso });
      if (result.tipo_salida === 'MENSUALIDAD') {
        const payload = { uuid_salida: result.uuid };
        if (onPrint) {
          onPrint(payload);
        } else {
          (firePrintEnvelope ?? defaultFirePrintEnvelope)(payload);
        }
      }
    } catch (err) {
      if (err instanceof ParkosHttpError) {
        setError(err);
      } else {
        setError(err as Error);
      }
    }
  };

  const data: CotizarMensualidad = { cobrar: false, motivo: 'mensualidad_vigente' };

  return (
    <div data-testid="salida-mensualidad">
      <CotizacionPanel
        data={data}
        error={error}
        secondsLeft={Number.MAX_SAFE_INTEGER}
        onConfirmar={() => {
          void handleConfirmar();
        }}
        onRecalcular={() => undefined}
      />
    </div>
  );
}