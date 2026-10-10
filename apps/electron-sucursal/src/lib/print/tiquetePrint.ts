/**
 * `tiquetePrint.ts` — print an operation ticket (entrada, reimpresión, salida,
 * salida con mensualidad, recibo de pago, arqueo parcial) through the real
 * bridge contract on BOTH channels, from the same 80 mm lines:
 *   - Electron: `escposBuilder.build(tipo, payload, marca)` → base64 →
 *     `bridge.imprimir({ buffer, ticketId, cut })`, with the easypunto raster
 *     logo from `marcaParaBridge`.
 *   - Browser mode (`bridge.imprimir.modo === 'browser'`): the matching HTML
 *     (`fallbackBrowser.renderTiqueteHtml`) → `window.print`.
 * Never throws; an invalid payload or a printer failure is `{ ok: false }`.
 */
import type { BridgeSurface } from '../../../electron/bridge';
import type { TiqueteTipo } from './escposTemplates';
import { build } from './escposBuilder';
import {
  bridgeActual,
  enviarAlBridge,
  marcaParaBridge,
  type ResultadoImpresion,
} from './facturaPrint';
import { renderTiqueteHtml } from './fallbackBrowser';

export type TiqueteImprimible = TiqueteTipo;

export async function imprimirTiquete(
  tipo: TiqueteImprimible,
  payload: unknown,
  opts: {
    ticketId: string;
    bridge?: Pick<BridgeSurface, 'imprimir'> | undefined;
  },
): Promise<ResultadoImpresion> {
  const bridge = 'bridge' in opts ? opts.bridge : bridgeActual();
  const marca = await marcaParaBridge(bridge);
  // Validate once, up front: a malformed payload must not reach the printer.
  let escpos: Buffer;
  let html: string;
  try {
    escpos = build(tipo, payload, marca);
    html = renderTiqueteHtml(tipo, payload);
  } catch (err) {
    console.warn('[imprimirTiquete] payload inválido', err);
    return { ok: false, motivo: 'payload_invalido' };
  }
  return enviarAlBridge(bridge, {
    escpos: () => escpos,
    html: () => html,
    ticketId: opts.ticketId,
  });
}
