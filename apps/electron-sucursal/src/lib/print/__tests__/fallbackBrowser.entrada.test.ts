/**
 * Unit tests for F6.2 — `renderEntradaTiqueteHtml()` and `print('entrada', ...)`.
 *
 * Covers:
 *   - HTML 17-field layout — `<h1>`, `<p>`, `<img>` tags for QR + logo.
 *   - Verbatim `@page { size: 80mm auto; margin: 2mm }` CSS rule (DEC-SUC-08).
 *   - `window.print()` exactly once (F5.2 contract preserved).
 *   - Mensualidad tag conditional — `<strong>MENSUALIDAD</strong>` under sello.
 *   - Logo placeholder — `▢` glyph when `logoDataUrl === ''`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

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
    fecha_ingreso: '2026-09-16T08:30:00Z',
    uuid_subscripcion_cliente: overrides?.uuid_subscripcion_cliente ?? null,
  };
}

function buildPayloadFromFactory(opts?: { esMensualidad?: boolean; emptyLogo?: boolean }) {
  return buildEntradaPayload({
    ingreso: makeIngreso({
      uuid_subscripcion_cliente: opts?.esMensualidad ? 'sub-uuid-123' : null,
    }),
    sucursal: { horario_atencion: '24 horas' },
    empresa: {
      nombre: 'Parkos Demo S.A.S.',
      nit: '900123456-7',
      direccion: 'Calle 1 #2-3, Bogota',
      regimen: 'Responsable de IVA',
    },
    operario: 'op-001',
    tipoVehiculo: 'auto' as const,
    tarifa: { valor_hora_cents: 5000 },
    documentos: opts?.emptyLogo
      ? []
      : [
          { tipo: 'logo' as const, documento_b64: 'data:image/png;base64,FAKE_LOGO' },
          { tipo: 'certificado' as const, documento_b64: 'POL-12345' },
        ],
    fechaHora: '2026-09-16T08:30:00Z',
  });
}

// ──────────────────────────────────────────────────────────────────────────
// renderEntradaTiqueteHtml — 17-field HTML layout
// ──────────────────────────────────────────────────────────────────────────

describe('renderEntradaTiqueteHtml — 17-field HTML layout', () => {
  it('renders the ENCABEZADO as <h1>PARKINGOS</h1>', () => {
    const html = renderEntradaTiqueteHtml(validEntradaPayload());
    expect(html).toContain('<h1>PARKINGOS</h1>');
  });

  it('renders empresa.nombre, direccion, nit, regimen as <p> tags', () => {
    const html = renderEntradaTiqueteHtml(validEntradaPayload());
    expect(html).toContain('<p>Parkos Demo S.A.S.</p>');
    expect(html).toContain('<p>Calle 1 #2-3, Bogota</p>');
    expect(html).toContain('<p>NIT 900123456-7</p>');
    expect(html).toContain('<p>Responsable de IVA</p>');
  });

  it('renders operario as <p>Operario: ...</p>', () => {
    const html = renderEntradaTiqueteHtml(validEntradaPayload());
    expect(html).toContain('<p>Operario: op-001</p>');
  });

  it('renders sello <h2>*** TIQUETE DE ENTRADA ***</h2>', () => {
    const html = renderEntradaTiqueteHtml(validEntradaPayload());
    expect(html).toContain('<h2>*** TIQUETE DE ENTRADA ***</h2>');
  });

  it('renders folio, placa, tarifa, horario as <p> tags', () => {
    const html = renderEntradaTiqueteHtml(validEntradaPayload());
    expect(html).toContain('<p>Folio: 00000000-0000-4000-8000-000000000001</p>');
    expect(html).toContain('<p>Placa: ABC123</p>');
    // formatCOP produces non-breaking space (U+00A0) between "$" and
    // the amount; assert via regex to avoid literal-char fragility.
    expect(html).toMatch(/<p>Tarifa: \$[\s\u00A0]+5\.000\/hora<\/p>/);
    expect(html).toContain('<p>Horario: 24 horas</p>');
  });

  it('splits fechaEntrada into Fecha (date) and Hora (time) <p> tags', () => {
    const html = renderEntradaTiqueteHtml(validEntradaPayload());
    expect(html).toContain('<p>Fecha: 16/09/2026</p>');
    // Hora is timezone-dependent — assert via regex (HH:mm pattern).
    expect(html).toMatch(/<p>Hora: \d{2}:\d{2}<\/p>/);
  });

  it('renders polizaRC as <p>Poliza RC: ...</p> when present', () => {
    const html = renderEntradaTiqueteHtml(validEntradaPayload());
    expect(html).toContain('<p>Poliza RC: POL-12345</p>');
  });

  it('renders observaciones as <p>Observaciones: ...</p> when present', () => {
    const html = renderEntradaTiqueteHtml(validEntradaPayload());
    expect(html).toContain('<p>Observaciones: Sin novedad</p>');
  });

  it('renders QR as inline <img src="{qrDataUrl}" alt="QR ingreso" />', () => {
    const html = renderEntradaTiqueteHtml(validEntradaPayload());
    expect(html).toContain('<img src="data:image/png;base64,AAA" alt="QR ingreso" />');
  });

  it('renders logo as inline <img src="{logoDataUrl}" alt="Logo" /> when present', () => {
    const html = renderEntradaTiqueteHtml(validEntradaPayload());
    expect(html).toContain('<img src="data:image/png;base64,BBB" alt="Logo" />');
  });

  it('renders Mensualidad tag <strong>MENSUALIDAD</strong> when esMensualidad=true', () => {
    const payload = buildPayloadFromFactory({ esMensualidad: true });
    const html = renderEntradaTiqueteHtml(payload);
    expect(html).toContain('<strong>MENSUALIDAD</strong>');
  });

  it('does NOT render Mensualidad tag when esMensualidad=false', () => {
    const payload = buildPayloadFromFactory({ esMensualidad: false });
    const html = renderEntradaTiqueteHtml(payload);
    expect(html).not.toContain('<strong>MENSUALIDAD</strong>');
  });

  it('renders logo placeholder glyph ▢ when logoDataUrl is empty (cold cache)', () => {
    const payload = buildPayloadFromFactory({ emptyLogo: true });
    expect(payload.logoDataUrl).toBe('');
    const html = renderEntradaTiqueteHtml(payload);
    expect(html).toContain('\u25A2');
    // No <img> with empty src
    expect(html).not.toContain('<img src=""');
  });
});

// ──────────────────────────────────────────────────────────────────────────
// print('entrada', payload) — window.print() and @page CSS rule
// ──────────────────────────────────────────────────────────────────────────

describe('print("entrada", payload) — F6.2 wiring', () => {
  let printSpy: ReturnType<typeof vi.spyOn>;
  let appendSpy: ReturnType<typeof vi.spyOn>;

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
    expect(PAGE_RULE).toBe('@page { size: 80mm auto; margin: 2mm }');
  });

  it('calls window.print() exactly once', () => {
    print('entrada', validEntradaPayload());
    expect(printSpy).toHaveBeenCalledTimes(1);
  });

  it('removes the injected <style> after window.print() resolves', () => {
    print('entrada', validEntradaPayload());
    expect(document.getElementById('parkos-escpos-fallback-style')).toBeNull();
  });

  it('renders the Mensualidad tag in the fallback HTML when esMensualidad=true', () => {
    const payload = buildPayloadFromFactory({ esMensualidad: true });
    print('entrada', payload);
    const container = document.getElementById('parkos-escpos-fallback-container');
    expect(container?.innerHTML).toContain('<strong>MENSUALIDAD</strong>');
  });
});
