/**
 * `<SalidaMensualidad />` — mensualidad-branch orchestration wrapper
 * for HU-F7.2 (REQ-OPS-153 + REQ-OPS-154) + HU-F7.3 (REQ-OPS-160).
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
import { useState } from 'react';

import {
  useRegistrarSalida,
  SalidaDuplicadaError,
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
 * we fall back to the test override. Failures (offline, disconnected,
 * IPC channel error) are caught and logged to `console.warn` — they
 * MUST NOT propagate to the React error boundary.
 */
function defaultFirePrintEnvelope(payload: { uuid_salida: string }): void {
  const w = globalThis as unknown as { window?: { bridge?: { imprimir?: (k: string, p: unknown) => void } } };
  const bridge = w.window?.bridge;
  if (bridge?.imprimir) {
    bridge.imprimir('salida_mensualidad', payload);
  }
}

/**
 * F7.3 (DEC-SUC-08 + DEC-SUC-27) — defer the print envelope to the
 * next microtask (so the React render commit completes BEFORE the
 * IPC round-trip begins), and wrap in `try/catch` so a printer
 * failure never blocks the operator's flow. Reprint is F8.x.
 */
function deferredSafePrint(
  emit: (payload: { uuid_salida: string }) => void,
  payload: { uuid_salida: string },
): void {
  queueMicrotask(() => {
    try {
      emit(payload);
    } catch (err) {
      // eslint-disable-next-line no-console -- operator-facing: printer offline.
      console.warn(
        '[SalidaMensualidad] bridge.imprimir failed (printer_offline / disconnected — reprint is F8.x):',
        err,
      );
    }
  });
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
        // F7.3 (DEC-SUC-27 + DEC-SUC-08) — CU-15SM prints IMMEDIATELY at
        // salida mensualidad. The bridge call is deferred to the next
        // microtask so the React render commit is not blocked, and wrapped
        // in try/catch so a printer failure never blocks the operator.
        const payload = { uuid_salida: result.uuid };
        const emit = (p: { uuid_salida: string }): void => {
          if (onPrint) {
            onPrint(p);
          } else {
            (firePrintEnvelope ?? defaultFirePrintEnvelope)(p);
          }
        };
        deferredSafePrint(emit, payload);
      }
    } catch (err) {
      if (err instanceof SalidaDuplicadaError || err instanceof ParkosHttpError) {
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