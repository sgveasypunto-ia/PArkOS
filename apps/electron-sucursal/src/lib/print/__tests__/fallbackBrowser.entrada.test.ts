/**
 * Unit tests for F6.2 — `renderEntradaTiqueteHtml()` and `print('entrada', ...)`.
 *
 * Covers (80 mm format, intentional change: the HTML is the one of the common
 * ticket base — fixed-width rows, easypunto logos, NO QR image):
 *   - 15-field layout as rows of text.
 *   - `@page { size: 80mm auto; margin: 0 }` (no browser margin on the 72 mm column).
 *   - `window.print()` exactly once (F5.2 contract preserved).
 *   - Tipo de operación — always-on `Tipo: ROTACIÓN` / `Tipo: MENSUALIDAD` (bold).
 */
import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from 'vitest';

import { print, PAGE_RULE, renderEntradaTiqueteHtml } from '../fallbackBrowser';
import { validEntradaPayload } from './escposBuilder.test';
import { buildEntradaPayload } from '../escposTemplates';

// ──────────────────────────────────────────────────────────────────────────
// Fixtures
// ──────────────────────────────────────────────────────────────────────────

function makeIngreso(overrides?: { uuid_subscripcion_cliente?: string | null }) {
  return {
    uuid: '11111111-2222-4333-8444-555555555555',
    placa: 'ABC123',
    // REQ-OPS-197: `consecutivo` is required (nullable) on `IngresoForPayload` —
    // this fixture only exercises the legacy con-placa variant, so it is
    // always `null` (the backend never omits the field).
    consecutivo: null,
    fecha_ingreso: '2026-09-16T08:30:00Z',
    uuid_subscripcion_cliente: overrides?.uuid_subscripcion_cliente ?? null,
  };
}

function buildPayloadFromFactory(opts?: { esMensualidad?: boolean }) {
  return buildEntradaPayload({
    ingreso: makeIngreso({
      uuid_subscripcion_cliente: opts?.esMensualidad ? 'sub-uuid-123' : null,
    }),
    sucursal: { horario_atencion: '24 horas', encabezado: 'Sucursal Demo' },
    empresa: {
      nombre: 'Parkos Demo S.A.S.',
      nit: '900123456-7',
      direccion: 'Calle 1 #2-3, Bogota',
      regimen: 'Responsable de IVA',
    },
    operario: 'op-001',
    tipoVehiculo: 'auto' as const,
    tarifa: { valor_hora_cents: 5000 },
    documentos: [{ tipo: 'certificado' as const, documento_b64: 'POL-12345' }],
    fechaHora: '2026-09-16T08:30:00Z',
  });
}

// ──────────────────────────────────────────────────────────────────────────
// renderEntradaTiqueteHtml — 15-field HTML layout (rows of the 80 mm base)
// ──────────────────────────────────────────────────────────────────────────

/** Visible text lines of the ticket HTML (one per row, `<style>` excluded). */
function lineasDe(html: string): string[] {
  const root = document.createElement('div');
  root.innerHTML = html;
  root.querySelectorAll('style').forEach((n) => n.remove());
  return Array.from(root.querySelectorAll('p, div.fila'))
    .map((n) => (n.textContent ?? '').replace(/[\u00a0\u202f]/g, ' ').trim())
    .filter((t) => t !== '');
}

describe('renderEntradaTiqueteHtml — 15-field HTML layout', () => {
  it('renders the ENCABEZADO (dynamic sucursal header, DEC-SUC-28), bold and centred', () => {
    const html = renderEntradaTiqueteHtml(validEntradaPayload());
    expect(lineasDe(html)).toContain('Sucursal Centro');
    expect(html).toMatch(/text-align:center;font-weight:bold;[^"]*">Sucursal Centro<\/p>/);
    expect(html).not.toContain('PARKINGOS');
  });

  it('renders empresa.nombre, direccion, nit and regimen', () => {
    const lineas = lineasDe(renderEntradaTiqueteHtml(validEntradaPayload()));
    expect(lineas).toContain('Parkos Demo S.A.S.');
    expect(lineas).toContain('Calle 1 #2-3, Bogota');
    expect(lineas).toContain('NIT 900123456-7');
    expect(lineas).toContain('Responsable de IVA');
  });

  it('renders operario and the sello', () => {
    const lineas = lineasDe(renderEntradaTiqueteHtml(validEntradaPayload()));
    expect(lineas).toContain('Operario: op-001');
    expect(lineas).toContain('*** TIQUETE DE ENTRADA ***');
  });

  it('renders folio, placa, tarifa and horario', () => {
    const lineas = lineasDe(renderEntradaTiqueteHtml(validEntradaPayload()));
    expect(lineas).toContain('Folio: 00000000-0000-4000-8000-000000000001');
    expect(lineas).toContain('Placa: ABC123');
    expect(lineas).toContain('Tarifa: $ 5.000/hora');
    expect(lineas).toContain('Horario: 24 horas');
  });

  it('splits fechaEntrada into Fecha (date) and Hora (time)', () => {
    const lineas = lineasDe(renderEntradaTiqueteHtml(validEntradaPayload()));
    expect(lineas).toContain('Fecha: 16/09/2026');
    expect(lineas.some((l) => /^Hora: \d{2}:\d{2}$/.test(l))).toBe(true);
  });

  it('renders polizaRC and observaciones when present', () => {
    const lineas = lineasDe(renderEntradaTiqueteHtml(validEntradaPayload()));
    expect(lineas).toContain('Poliza RC: POL-12345');
    expect(lineas).toContain('Observaciones: Sin novedad');
  });

  it('has NO QR image: the only images are the two easypunto logos (header and footer)', () => {
    const html = renderEntradaTiqueteHtml(validEntradaPayload());
    const sinLogo = html.replace(/src="data:image[^"]*"/g, 'src=""');
    expect(sinLogo).not.toMatch(/qr/i);
    expect(html.match(/<img\b[^>]*>/gi)).toHaveLength(2);
    for (const img of html.match(/<img\b[^>]*>/gi) ?? []) expect(img).toContain('alt="easypunto"');
  });

  it('renders the Tipo line MENSUALIDAD (bold) when esMensualidad=true', () => {
    const html = renderEntradaTiqueteHtml(buildPayloadFromFactory({ esMensualidad: true }));
    expect(lineasDe(html)).toContain('Tipo: MENSUALIDAD');
    expect(html).toMatch(/font-weight:bold;[^"]*">Tipo: MENSUALIDAD<\/p>/);
  });

  it('renders the Tipo line ROTACIÓN when esMensualidad=false (pedido del operador — siempre explícito)', () => {
    const html = renderEntradaTiqueteHtml(buildPayloadFromFactory({ esMensualidad: false }));
    expect(lineasDe(html)).toContain('Tipo: ROTACIÓN');
    expect(html).not.toContain('MENSUALIDAD');
  });
});

// ──────────────────────────────────────────────────────────────────────────
// print('entrada', payload) — window.print() and @page CSS rule
// ──────────────────────────────────────────────────────────────────────────

describe('print("entrada", payload) — F6.2 wiring', () => {
  let printSpy: ReturnType<typeof vi.spyOn>;
  // `document.head.appendChild` overload is generic (`<T extends Node>(node: T) => T`);
  // `ReturnType<typeof vi.spyOn>` resolves to the wrong overload and mismatches the
  // actual `vi.spyOn(document.head, 'appendChild')` return type. Pin the spy's type to
  // the real method signature instead.
  let appendSpy: MockInstance<typeof document.head.appendChild>;

  beforeEach(() => {
    document.head.innerHTML = '';
    document.body.innerHTML = '';
    printSpy = vi.spyOn(window, 'print').mockImplementation(() => undefined);
    appendSpy = vi.spyOn(document.head, 'appendChild');
  });

  afterEach(() => {
    printSpy.mockRestore();
    appendSpy.mockRestore();
  });

  it('injects a <style> element with the verbatim DEC-SUC-08 @page rule', () => {
    print('entrada', validEntradaPayload());
    expect(appendSpy).toHaveBeenCalled();
    const injectedNode = appendSpy.mock.calls
      .map((call) => call[0])
      .find((node) => (node as Element).tagName?.toLowerCase?.() === 'style') as
      | (HTMLStyleElement & { id?: string })
      | undefined;
    expect(injectedNode).toBeDefined();
    expect(injectedNode?.textContent).toBe(PAGE_RULE);
    // Intentional change (80 mm): margin 0, the 72 mm column is centred by the ticket CSS.
    expect(PAGE_RULE).toBe('@page { size: 80mm auto; margin: 0 }');
  });

  it('calls window.print() exactly once', () => {
    print('entrada', validEntradaPayload());
    expect(printSpy).toHaveBeenCalledTimes(1);
  });

  it('removes the injected <style> after window.print() resolves', () => {
    print('entrada', validEntradaPayload());
    expect(document.getElementById('parkos-escpos-fallback-style')).toBeNull();
  });

  it('renders the Tipo line in the fallback HTML when esMensualidad=true', () => {
    const payload = buildPayloadFromFactory({ esMensualidad: true });
    print('entrada', payload);
    const container = document.getElementById('parkos-escpos-fallback-container');
    expect(container?.innerHTML).toContain('Tipo: MENSUALIDAD');
    expect(container?.querySelector('[data-testid="tiquete-entrada-print"]')).not.toBeNull();
  });
});
