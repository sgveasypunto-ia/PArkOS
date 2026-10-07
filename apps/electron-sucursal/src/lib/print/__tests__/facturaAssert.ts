/**
 * Test helpers for the invoice-print callers: install a fake Electron bridge
 * and assert that what reached `bridge.imprimir` is the COMPLETE document
 * (an object `{ buffer, ticketId, ... }`, never the old `(tipo, envelope)`).
 */
import { expect, vi, type Mock } from 'vitest';

export function instalarBridgeImprimir(): Mock {
  const imprimir = vi.fn(async () => ({ ok: true, queueId: null }));
  (window as unknown as { bridge: unknown }).bridge = {
    imprimir: Object.assign(imprimir, {
      getQueue: async () => ({}),
      onStatus: () => () => undefined,
    }),
  };
  return imprimir;
}

/** Decoded, whitespace-normalised ESC/POS text of the n-th `bridge.imprimir` call. */
export function textoImpreso(imprimir: Mock, n = 0): string {
  const arg = imprimir.mock.calls[n]?.[0] as { buffer?: string } | string | undefined;
  expect(typeof arg, 'bridge.imprimir debe recibir el documento completo, no (tipo, envelope)').toBe(
    'object',
  );
  const buffer = (arg as { buffer?: string }).buffer;
  expect(typeof buffer).toBe('string');
  return Buffer.from(buffer as string, 'base64')
    .toString('utf8')
    .replace(/\u00a0/g, ' ')
    .replace(/[ \t]+/g, ' ');
}

/** Same tax-detail contract for every invoice type. */
export function expectDetalleImpuestos(texto: string, numeroRecibo: string): void {
  expect(texto).toContain(numeroRecibo);
  expect(texto).toMatch(/Subtotal \$ ?[\d.]+,\d\d/);
  expect(texto).toMatch(/IVA 19% \$ ?[\d.]+,\d\d/);
  expect(texto).toMatch(/Base \$ ?[\d.]+,\d\d/);
  expect(texto).toMatch(/TOTAL \$ ?[\d.]+,\d\d/);
}
