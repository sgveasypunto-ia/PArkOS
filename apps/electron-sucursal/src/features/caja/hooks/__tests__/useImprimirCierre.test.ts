/**
 * Caller-level contract of the cierre slips: what the cierre de turno and the
 * cierre diario orchestrators actually put on `window.bridge.imprimir`
 * (real `{ buffer, ticketId, cut }` contract) in Electron and browser mode,
 * and the visible notice when the printer fails.
 */
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAvisosImpresion } from '../../../../lib/print/avisoImpresion';
import type { SesionRead } from '../../api/sesionActivaApi';
import { useImprimirCierre } from '../useImprimirCierre';

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({
    user: { uuid: 'u1', email: 'operador.qae2e@parkos.local', nombre: 'Operador', apellido: 'QA E2E' },
    sucursal: { uuid: 's1', nombre: 'Sucursal Norte' },
  }),
}));

const SESION: SesionRead = {
  uuid: 'abc12345-6789-0abc-1234-56789abcdef0',
  uuid_sucursal: 's1',
  uuid_usuario: 'u1',
  valor_inicial_efectivo: 50_000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-10-07T08:00:00-05:00',
  timestamp_cierre: '2026-10-07T16:30:00-05:00',
};

const norm = (s: string): string => s.replace(/ /g, ' ').replace(/[ \t]+/g, ' ');
const w = globalThis as unknown as { window: { bridge?: unknown } };
let original: unknown;

beforeEach(() => {
  original = w.window.bridge;
  useAvisosImpresion.setState({ avisos: [] });
  window.print = vi.fn();
});
afterEach(() => {
  w.window.bridge = original;
  document.getElementById('parkos-escpos-fallback-container')?.remove();
  vi.restoreAllMocks();
});

function decodificado(imprimir: ReturnType<typeof vi.fn>): string {
  const calls = imprimir.mock.calls as unknown as unknown[][];
  const arg = calls[0]![0] as { buffer: string };
  return norm(Buffer.from(arg.buffer, 'base64').toString('utf8'));
}

describe('useImprimirCierre', () => {
  it('cierre de turno (Electron): turno, operador, apertura/cierre, esperado/reportado/diferencia, sin datafono', async () => {
    const imprimir = vi.fn(async () => ({ ok: true }));
    w.window.bridge = { imprimir };
    const { result } = renderHook(() => useImprimirCierre());
    await result.current.turno({
      sesion: SESION,
      arqueo: {
        uuid: '99999999-2222-4333-8444-555555555555',
        valor_efectivo_esperado: 120_000,
        valor_efectivo_reportado: 118_000,
        diferencia_efectivo: -2_000,
      },
      observaciones: 'Faltante en caja menor',
    });
    expect(imprimir).toHaveBeenCalledTimes(1);
    const calls = imprimir.mock.calls as unknown as unknown[][];
    expect(typeof calls[0]![0]).toBe('object');
    const txt = decodificado(imprimir);
    expect(txt).toContain('CIERRE DE TURNO');
    expect(txt).toContain('Operador QA E2E');
    expect(txt).toContain('Sucursal Norte');
    expect(txt).toContain('abcdef0');
    expect(txt).toMatch(/Apertura.*07\/10\/2026/);
    expect(txt).toMatch(/Cierre.*07\/10\/2026/);
    expect(txt).toMatch(/Esperado.*120\.000/);
    expect(txt).toMatch(/Reportado.*118\.000/);
    expect(txt).toMatch(/Diferencia.*-.*2\.000/);
    expect(txt).toContain('Faltante en caja menor');
    expect(txt.toLowerCase()).not.toContain('datafono');
    expect(useAvisosImpresion.getState().avisos).toHaveLength(0);
  });

  it('cierre diario (modo navegador): HTML por window.print, sin tocar el bridge', async () => {
    const imprimir = Object.assign(vi.fn(), { modo: 'browser' as const });
    w.window.bridge = { imprimir };
    const { result } = renderHook(() => useImprimirCierre());
    await result.current.dia({
      arqueo: { uuid: '88888888-2222-4333-8444-555555555555', valor_efectivo_esperado: 500_000 },
      valor_efectivo_reportado: 500_000,
      justificacion: undefined,
    });
    expect(imprimir).not.toHaveBeenCalled();
    expect(window.print).toHaveBeenCalledTimes(1);
    const dom = norm(document.getElementById('parkos-escpos-fallback-container')?.textContent ?? '');
    expect(dom).toContain('CIERRE DIARIO');
    expect(dom).toMatch(/Reportado.*500\.000/);
    expect(dom.toLowerCase()).not.toContain('datafono');
  });

  it('si el bridge rechaza: no lanza y deja el aviso "No se pudo imprimir…" con reintento', async () => {
    const imprimir = vi.fn(async () => {
      throw new Error('printer_offline');
    });
    w.window.bridge = { imprimir };
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const { result } = renderHook(() => useImprimirCierre());
    await expect(
      result.current.turno({
        sesion: SESION,
        arqueo: { uuid: '99999999-2222-4333-8444-555555555555' },
        observaciones: undefined,
      }),
    ).resolves.toBeDefined();
    const [aviso] = useAvisosImpresion.getState().avisos;
    expect(aviso?.mensaje).toMatch(/^No se pudo imprimir el cierre de turno/);
    imprimir.mockImplementation(async () => ({ ok: true }) as never);
    await aviso!.reintentar();
    expect(useAvisosImpresion.getState().avisos).toHaveLength(0);
  });
});
