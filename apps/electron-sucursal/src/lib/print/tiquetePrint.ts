/**
 * `tiquetePrint.ts` — print a tiquete (ingreso, or the reimpresión of an
 * ingreso) through the real bridge contract on BOTH channels:
 *   - Electron: `escposBuilder.build(tipo, payload)` → base64 →
 *     `bridge.imprimir({ buffer, ticketId, cut })` (bytes identical to
 *     `buildEntradaBuffer` / `buildReimpresionBuffer`).
 *   - Browser mode (`bridge.imprimir.modo === 'browser'`): the matching HTML
 *     (`fallbackBrowser.renderTiqueteHtml`) → `window.print`. Before this the
 *     browser shim's no-op `imprimir` made the ticket print nothing.
 * Never throws; an invalid payload or a printer failure is `{ ok: false }`.
 */
import type { BridgeSurface } from '../../../electron/bridge';
import { build } from './escposBuilder';
import { bridgeActual, enviarAlBridge, type ResultadoImpresion } from './facturaPrint';
import { renderTiqueteHtml } from './fallbackBrowser';

export type TiqueteImprimible = 'entrada' | 'reimpresion';

export async function imprimirTiquete(
  tipo: TiqueteImprimible,
  payload: unknown,
  opts: {
    ticketId: string;
    bridge?: Pick<BridgeSurface, 'imprimir'> | undefined;
  },
): Promise<ResultadoImpresion> {
  const bridge = 'bridge' in opts ? opts.bridge : bridgeActual();
  // Validate once, up front: a malformed payload must not reach the printer.
  let escpos: Buffer;
  let html: string;
  try {
    escpos = build(tipo, payload);
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
