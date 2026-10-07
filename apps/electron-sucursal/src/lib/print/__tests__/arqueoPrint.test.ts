/**
 * Cierre de turno / cierre diario slips: ONE document model rendered to
 * ESC/POS (Electron) and HTML (browser mode). The operator-visible contract:
 * turno/sesión, operador, apertura/cierre, efectivo esperado vs reportado vs
 * diferencia, justificación if any, and NEVER datáfono (removed from the flow).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  cierreAEscpos,
  cierreAHtml,
  construirCierre,
  imprimirCierre,
  type CierreImpresion,
} from '../arqueoPrint';
import { facturaATexto } from '../facturaPrint';

const norm = (s: string): string => s.replace(/ /g, ' ').replace(/[ \t]+/g, ' ');

const TURNO: CierreImpresion = {
  tipo: 'cierre_turno',
  sucursal: 'Sucursal Norte',
  operador: 'Operador QA E2E',
  uuidSesion: 'abc12345-6789-0abc-1234-56789abcdef0',
  aperturaIso: '2026-10-07T08:00:00-05:00',
  cierreIso: '2026-10-07T16:30:00-05:00',
  baseEfectivo: 50000,
  esperado: 120000,
  reportado: 118000,
  diferencia: -2000,
  justificacion: 'Faltante en caja menor',
  uuidArqueo: '99999999-2222-4333-8444-555555555555',
};

const DIA: CierreImpresion = {
  tipo: 'cierre_dia',
  sucursal: 'Sucursal Norte',
  operador: 'Supervisor Demo',
  cierreIso: '2026-10-07T22:00:00-05:00',
  esperado: 500000,
  reportado: 500000,
  diferencia: 0,
  uuidArqueo: '88888888-2222-4333-8444-555555555555',
};

describe('construirCierre', () => {
  it('turno: sesión, operador, apertura, cierre, esperado/reportado/diferencia y justificación', () => {
    const txt = norm(facturaATexto(construirCierre(TURNO)));
    expect(txt).toContain('CIERRE DE TURNO');
    expect(txt).toContain('Sucursal Norte');
    expect(txt).toContain('Operador QA E2E');
    expect(txt).toContain('abcdef0'); // sesión corta (últimos 8)
    expect(txt).toMatch(/Apertura.*07\/10\/2026/);
    expect(txt).toMatch(/Cierre.*07\/10\/2026/);
    expect(txt).toMatch(/Base.*50\.000/);
    expect(txt).toMatch(/Esperado.*120\.000/);
    expect(txt).toMatch(/Reportado.*118\.000/);
    expect(txt).toMatch(/Diferencia.*-.*2\.000/);
    expect(txt).toContain('Faltante en caja menor');
  });

  it('diario: sin sesión ni apertura, sin justificación si no hay', () => {
    const txt = norm(facturaATexto(construirCierre(DIA)));
    expect(txt).toContain('CIERRE DIARIO');
    expect(txt).toContain('Supervisor Demo');
    expect(txt).not.toContain('Apertura');
    expect(txt).not.toContain('Justificación');
    expect(txt).toMatch(/Diferencia.*0/);
  });

  it('el backend manda UTC sin zona: se interpreta como UTC (no como hora local)', () => {
    const d = { ...TURNO, aperturaIso: '2026-10-07T22:21:00', cierreIso: '2026-10-07T22:34:00' };
    const esperadaApertura = new Date('2026-10-07T22:21:00Z');
    const hh = String(esperadaApertura.getHours()).padStart(2, '0');
    const mm = String(esperadaApertura.getMinutes()).padStart(2, '0');
    const txt = norm(facturaATexto(construirCierre(d)));
    expect(txt).toContain(`${hh}:${mm}`);
  });

  it('nunca imprime datáfono, ni siquiera si el payload lo trae', () => {
    const extra = { ...TURNO, valor_datafono_reportado: 1 } as unknown as CierreImpresion;
    for (const d of [TURNO, DIA, extra]) {
      const txt = facturaATexto(construirCierre(d)).toLowerCase();
      expect(txt).not.toContain('datafono');
      expect(txt).not.toContain('datáfono');
    }
  });

  it('calcula la diferencia cuando el backend no la trae', () => {
    const txt = norm(
      facturaATexto(construirCierre({ ...TURNO, diferencia: null, esperado: 100000, reportado: 100500 })),
    );
    expect(txt).toMatch(/Diferencia.*\+.*500/);
  });
});

describe('imprimirCierre', () => {
  beforeEach(() => {
    window.print = vi.fn();
  });
  afterEach(() => {
    document.getElementById('parkos-escpos-fallback-container')?.remove();
    vi.restoreAllMocks();
  });

  it('Electron: bridge.imprimir({buffer,ticketId,cut}) con el slip decodificable', async () => {
    const imprimir = vi.fn(async () => ({ ok: true, queueId: null }));
    const res = await imprimirCierre(TURNO, { imprimir } as never);
    expect(res.ok).toBe(true);
    expect(imprimir).toHaveBeenCalledTimes(1);
    const calls = imprimir.mock.calls as unknown as unknown[][];
    const arg = calls[0]![0] as Record<string, unknown>;
    expect(typeof calls[0]![0]).toBe('object'); // contrato real, no (tipo, payload)
    expect(Object.keys(arg).sort()).toEqual(['buffer', 'cut', 'ticketId']);
    expect(arg.cut).toBe(true);
    const decoded = norm(Buffer.from(arg.buffer as string, 'base64').toString('utf8'));
    expect(decoded).toContain('CIERRE DE TURNO');
    expect(decoded).toMatch(/Reportado.*118\.000/);
    expect(Buffer.from(arg.buffer as string, 'base64').equals(cierreAEscpos(TURNO))).toBe(true);
  });

  it('modo navegador: el slip va por window.print (HTML) y no por el bridge', async () => {
    const imprimir = vi.fn();
    const bridge = { imprimir: Object.assign(imprimir, { modo: 'browser' as const }) } as never;
    const res = await imprimirCierre(DIA, bridge);
    expect(res.ok).toBe(true);
    expect(imprimir).not.toHaveBeenCalled();
    expect(window.print).toHaveBeenCalledTimes(1);
    const dom = norm(document.getElementById('parkos-escpos-fallback-container')?.textContent ?? '');
    expect(dom).toContain('CIERRE DIARIO');
    expect(dom).toMatch(/Esperado.*500\.000/);
    expect(cierreAHtml(DIA)).toContain('data-testid="cierre-print"');
  });

  it('el bridge responde ok:false o rechaza: no lanza, devuelve ok=false', async () => {
    const fallo = vi.fn(async () => ({ ok: false, error: 'printer_offline' }));
    expect((await imprimirCierre(TURNO, { imprimir: fallo } as never)).ok).toBe(false);
    const rechaza = vi.fn(async () => {
      throw new Error('boom');
    });
    expect((await imprimirCierre(TURNO, { imprimir: rechaza } as never)).ok).toBe(false);
  });
});
