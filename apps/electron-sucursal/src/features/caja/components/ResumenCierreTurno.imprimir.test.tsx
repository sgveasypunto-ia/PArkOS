/**
 * Botón "Imprimir ticket" del resumen de turno cerrado: ticket térmico de 80 mm
 * por la ruta única de impresión (bridge Electron / window.print en navegador),
 * reimprimible, con aviso visible si falla y sin inventar datáfono.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import '@/i18n';

import { useAvisosImpresion } from '../../../lib/print/avisoImpresion';
import type { ResumenCierreTurnoRead } from '../../../lib/api/schemas/resumen-cierre-turno';
import type { SesionRead } from '../api/sesionActivaApi';
import { ResumenCierreTurno } from './ResumenCierreTurno';

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({
    user: { uuid: 'u1', email: 'operador.qae2e@parkos.local', nombre: 'Operador', apellido: 'QA' },
    sucursal: { uuid: 's1', nombre: 'Sucursal Norte' },
  }),
}));
vi.mock('../../../lib/print/resumenCierrePdf', () => ({ descargarResumenCierrePdf: vi.fn() }));

const SESION: SesionRead = {
  uuid: '11111111-2222-4333-8444-555555555555',
  uuid_sucursal: 's1',
  uuid_usuario: 'u1',
  valor_inicial_efectivo: 50_000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-09-15T13:00:00Z',
  timestamp_cierre: '2026-09-15T23:00:00Z',
};
const RESUMEN: ResumenCierreTurnoRead = {
  uuid_sesion: SESION.uuid,
  uuid_sucursal: 's1',
  timestamp_calculo: '2026-09-15T23:00:00',
  ingresos_count: 9,
  salidas_count: 8,
  transacciones_count: 4,
  medios_pago: [{ medio_pago: 'efectivo', pagos_count: 4, total_cop: 40_000 }],
  reversos_count: 0,
  reversos_total_cop: 0,
};
const ARQUEO = {
  uuid: 'arqueo-1',
  valor_efectivo_esperado: 90_000,
  valor_efectivo_reportado: 75_000,
  diferencia_efectivo: -15_000,
};

const norm = (s: string): string => s.replace(/\u00a0/g, ' ');
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

const montar = (props: Partial<Parameters<typeof ResumenCierreTurno>[0]> = {}) =>
  render(
    <ResumenCierreTurno sesion={SESION} arqueo={ARQUEO} resumen={RESUMEN} onFinalizar={() => {}} {...props} />,
  );

describe('<ResumenCierreTurno /> — Imprimir ticket', () => {
  it('muestra el botón accesible junto al de PDF', () => {
    montar();
    const btn = screen.getByRole('button', { name: 'Imprimir ticket' });
    expect(btn.getAttribute('data-testid')).toBe('resumen-cierre-imprimir-ticket');
    expect((btn as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByTestId('resumen-cierre-descargar-pdf')).toBeTruthy();
  });

  it('está deshabilitado mientras el resumen no tiene el efectivo contado', () => {
    montar({ arqueo: { uuid: 'arqueo-1' } });
    expect((screen.getByTestId('resumen-cierre-imprimir-ticket') as HTMLButtonElement).disabled).toBe(true);
  });

  it('está deshabilitado mientras los datos cargan', () => {
    montar({ cargando: true });
    expect((screen.getByTestId('resumen-cierre-imprimir-ticket') as HTMLButtonElement).disabled).toBe(true);
  });

  it('Electron: manda ESC/POS 48 col. al bridge con las filas de la pantalla, sin QR ni datáfono', async () => {
    const imprimir = vi.fn(async () => ({ ok: true }));
    w.window.bridge = { imprimir };
    montar({ observaciones: 'Faltante en caja' });
    fireEvent.click(screen.getByTestId('resumen-cierre-imprimir-ticket'));
    await waitFor(() => expect(imprimir).toHaveBeenCalledTimes(1));
    const arg = (imprimir.mock.calls as unknown as unknown[][])[0]![0] as { buffer: string; cut: boolean };
    const bytes = Buffer.from(arg.buffer, 'base64');
    expect(arg.cut).toBe(true);
    expect(bytes.indexOf(Buffer.from([0x1d, 0x28, 0x6b]))).toBe(-1);
    const txt = norm(bytes.toString('utf8'));
    expect(txt).toContain('CIERRE DE TURNO');
    expect(txt).toContain('Sucursal Norte');
    expect(txt).toContain('Operador: Operador QA');
    expect(txt).toMatch(/Efectivo contado\s+\$ 75\.000/);
    expect(txt).toMatch(/Diferencia\s+-\$ 15\.000/);
    expect(txt).toContain('Faltante en caja');
    expect(txt).toMatch(/Firma: _+/);
    expect(txt.toLowerCase()).not.toContain('datáfono');
    for (const l of txt.split('\n')) expect(l.length).toBeLessThanOrEqual(48 + 8); // + bytes de control
  });

  it('navegador: imprime el HTML con window.print y se puede reimprimir', async () => {
    const imprimir = Object.assign(vi.fn(), { modo: 'browser' as const });
    w.window.bridge = { imprimir };
    montar();
    const btn = screen.getByTestId('resumen-cierre-imprimir-ticket');
    fireEvent.click(btn);
    await waitFor(() => expect(window.print).toHaveBeenCalledTimes(1));
    expect(imprimir).not.toHaveBeenCalled();
    const dom = norm(document.getElementById('parkos-escpos-fallback-container')?.textContent ?? '');
    expect(dom).toContain('CIERRE DE TURNO');
    expect(document.getElementById('parkos-escpos-fallback-container')?.innerHTML.toLowerCase()).not.toContain('qr');
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(btn);
    await waitFor(() => expect(window.print).toHaveBeenCalledTimes(2));
  });

  it('si falla la impresora deja el aviso visible con reintento y el resumen sigue en pantalla', async () => {
    w.window.bridge = { imprimir: vi.fn(async () => ({ ok: false, error: 'printer_offline' })) };
    montar();
    fireEvent.click(screen.getByTestId('resumen-cierre-imprimir-ticket'));
    await waitFor(() => expect(useAvisosImpresion.getState().avisos).toHaveLength(1));
    expect(useAvisosImpresion.getState().avisos[0]!.mensaje).toContain('el cierre de turno');
    expect(screen.getByTestId('resumen-cierre-turno')).toBeTruthy();
    expect((screen.getByTestId('resumen-cierre-imprimir-ticket') as HTMLButtonElement).disabled).toBe(false);
  });

  it('sin detalle de pagos imprime "No disponible", sin valores inventados', async () => {
    const imprimir = vi.fn(async () => ({ ok: true }));
    w.window.bridge = { imprimir };
    montar({ resumen: null });
    fireEvent.click(screen.getByTestId('resumen-cierre-imprimir-ticket'));
    await waitFor(() => expect(imprimir).toHaveBeenCalled());
    const arg = (imprimir.mock.calls as unknown as unknown[][])[0]![0] as { buffer: string };
    const txt = norm(Buffer.from(arg.buffer, 'base64').toString('utf8'));
    expect(txt).toContain('No disponible');
    expect(txt).not.toMatch(/Ingresos\s+\d/);
  });
});
