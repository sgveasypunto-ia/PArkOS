/**
 * Tiquete de ingreso (y su reimpresión) por los dos canales: ESC/POS en
 * Electron (bytes idénticos a `buildEntradaBuffer`) y HTML + window.print en
 * modo navegador.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { build, buildEntradaBuffer, buildReimpresionBuffer } from '../escposBuilder';
import { testidTiquete } from '../fallbackBrowser';
import {
  buildEntradaPayloadFromResponse,
  buildReimpresionEntradaPayload,
} from '../printBuilder';
import { imprimirTiquete } from '../tiquetePrint';
import { ESCENARIOS_TIQUETE } from './tiqueteFixtures';

const norm = (s: string): string => s.replace(/ /g, ' ').replace(/[ \t]+/g, ' ');

const RESPONSE = {
  uuid: '11111111-2222-4333-8444-555555555555',
  tipo_entrada: 'ROTACION',
  uuid_subscripcion_cliente: null,
  consecutivo: null,
} as never;

const entrada = () => buildEntradaPayloadFromResponse(RESPONSE, 'ABC123', {});

describe('imprimirTiquete', () => {
  beforeEach(() => {
    window.print = vi.fn();
  });
  afterEach(() => {
    document.getElementById('parkos-escpos-fallback-container')?.remove();
    vi.restoreAllMocks();
  });

  it('Electron/entrada: buffer byte-idéntico a buildEntradaBuffer + ticketId + cut', async () => {
    const imprimir = vi.fn(async () => ({ ok: true, queueId: null }));
    const payload = entrada();
    const res = await imprimirTiquete('entrada', payload, {
      ticketId: 'tk-1',
      bridge: { imprimir } as never,
    });
    expect(res.ok).toBe(true);
    const calls = imprimir.mock.calls as unknown as unknown[][];
    const arg = calls[0]![0] as { buffer: string; ticketId: string; cut: boolean };
    expect(arg.ticketId).toBe('tk-1');
    expect(arg.cut).toBe(true);
    expect(arg.buffer).toBe(buildEntradaBuffer(payload).toString('base64'));
    expect(window.print).not.toHaveBeenCalled();
  });

  it('navegador/entrada: HTML del tiquete via window.print, sin llamar al bridge', async () => {
    const imprimir = vi.fn();
    const bridge = { imprimir: Object.assign(imprimir, { modo: 'browser' as const }) } as never;
    const res = await imprimirTiquete('entrada', entrada(), { ticketId: 'tk-1', bridge });
    expect(res.ok).toBe(true);
    expect(imprimir).not.toHaveBeenCalled();
    expect(window.print).toHaveBeenCalledTimes(1);
    const dom = norm(document.getElementById('parkos-escpos-fallback-container')?.textContent ?? '');
    expect(dom).toContain('TIQUETE DE ENTRADA');
    expect(dom).toContain('ABC123');
  });

  it('reimpresión (entrada): Electron envía buildReimpresionBuffer y navegador el HTML', async () => {
    const ingreso = {
      uuid: '11111111-2222-4333-8444-555555555555',
      placa: 'ABC123',
      consecutivo: null,
      fecha_ingreso: '2026-10-07T08:30:00Z',
      uuid_subscripcion_cliente: null,
    } as never;
    const payload = buildReimpresionEntradaPayload(ingreso, 'tiquete extraviado por el cliente');
    const imprimir = vi.fn(async () => ({ ok: true, queueId: null }));
    await imprimirTiquete('reimpresion', payload, { ticketId: 'r-1', bridge: { imprimir } as never });
    const calls = imprimir.mock.calls as unknown as unknown[][];
    expect((calls[0]![0] as { buffer: string }).buffer).toBe(
      buildReimpresionBuffer(payload).toString('base64'),
    );

    const imp2 = vi.fn();
    const res = await imprimirTiquete('reimpresion', payload, {
      ticketId: 'r-1',
      bridge: { imprimir: Object.assign(imp2, { modo: 'browser' as const }) } as never,
    });
    expect(res.ok).toBe(true);
    const dom = norm(document.getElementById('parkos-escpos-fallback-container')?.textContent ?? '');
    expect(dom).toContain('REIMPRESIÓN');
    expect(dom).toContain('tiquete extraviado por el cliente');
  });

  it('fallo del bridge, payload inválido o sin bridge: no lanza y devuelve ok=false', async () => {
    const rechaza = vi.fn(async () => {
      throw new Error('offline');
    });
    expect(
      (await imprimirTiquete('entrada', entrada(), { ticketId: 'x', bridge: { imprimir: rechaza } as never })).ok,
    ).toBe(false);
    const ok = vi.fn(async () => ({ ok: true }));
    expect(
      (await imprimirTiquete('entrada', { roto: true }, { ticketId: 'x', bridge: { imprimir: ok } as never })).ok,
    ).toBe(false);
    expect(ok).not.toHaveBeenCalled();
    expect((await imprimirTiquete('entrada', entrada(), { ticketId: 'x', bridge: undefined })).ok).toBe(false);
  });
});

describe('imprimirTiquete: una sola ruta para todos los tickets (80 mm)', () => {
  beforeEach(() => {
    window.print = vi.fn();
  });
  afterEach(() => {
    document.getElementById('parkos-escpos-fallback-container')?.remove();
    vi.restoreAllMocks();
  });

  it.each(ESCENARIOS_TIQUETE)('%s: Electron envia build() y navegador imprime el HTML 80 mm', async (_n, tipo, payload) => {
    const imprimir = vi.fn(async () => ({ ok: true, queueId: null }));
    const res = await imprimirTiquete(tipo, payload, { ticketId: 'tk', bridge: { imprimir } as never });
    expect(res.ok).toBe(true);
    const calls = imprimir.mock.calls as unknown as unknown[][];
    expect((calls[0]![0] as { buffer: string }).buffer).toBe(build(tipo, payload).toString('base64'));

    const imp2 = vi.fn();
    const res2 = await imprimirTiquete(tipo, payload, {
      ticketId: 'tk',
      bridge: { imprimir: Object.assign(imp2, { modo: 'browser' as const }) } as never,
    });
    expect(res2.ok).toBe(true);
    expect(imp2).not.toHaveBeenCalled();
    const contenedor = document.getElementById('parkos-escpos-fallback-container');
    expect(contenedor?.querySelector(`[data-testid="${testidTiquete(tipo)}"]`)).not.toBeNull();
    expect(contenedor?.innerHTML).toContain('@page { size: 80mm auto; margin: 0 }');
  });
});
