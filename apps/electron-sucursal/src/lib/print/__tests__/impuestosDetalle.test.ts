/**
 * Tax detail on EVERY printed invoice (salida CU-15S + recibo de pago, both
 * the ESC/POS buffer and the browser fallback HTML): tax name, rate, taxable
 * base and tax amount, plus subtotal (base) and total, taken from the
 * persisted `factura_impuestos` rows. Without `impuestos` the legacy
 * `IVA: <valor>` line is kept (reprints of invoices issued before the detail
 * existed).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { build } from '../escposBuilder';
import { copDecimalPlano } from './copPlano';
import { print } from '../fallbackBrowser';
import { impuestosDesdeFactura } from '../printBuilder';
import { formatCOPDecimal, type ReciboPagoPayload, type SalidaPayload } from '../escposTemplates';
import type { FacturaRead } from '../../../features/facturacion/api/facturaApi';
import { validSalidaPayload } from './escposBuilder.test';

// Subscription-style invoice: price 120.000 IVA included.
const IMPUESTOS = [
  { nombre: 'IVA', porcentaje: 0.19, base: 100840.34, valor: 19159.66 },
];

function conImpuestos<T extends SalidaPayload>(p: T): T {
  return { ...p, subtotal: 100840.34, iva: 19159.66, total: 120000, impuestos: IMPUESTOS };
}

function has(buf: Buffer, text: string): boolean {
  return buf.indexOf(Buffer.from(text)) >= 0;
}

describe('ESC/POS salida — detalle de impuestos', () => {
  it('prints tax name, rate, base and amount plus subtotal/total with cents', () => {
    const buf = build('salida', conImpuestos(validSalidaPayload() as SalidaPayload));
    expect(has(buf, 'IVA 19.00%')).toBe(true);
    expect(has(buf, `Base: ${copDecimalPlano(100840.34)}`)).toBe(true);
    expect(has(buf, copDecimalPlano(19159.66))).toBe(true);
    expect(has(buf, `Subtotal: ${copDecimalPlano(100840.34)}`)).toBe(true);
    expect(has(buf, `TOTAL: ${copDecimalPlano(120000)}`)).toBe(true);
  });

  it('keeps the legacy "IVA:" line when the invoice has no tax rows', () => {
    const buf = build('salida', validSalidaPayload() as SalidaPayload);
    expect(has(buf, 'IVA: ')).toBe(true);
    expect(has(buf, 'Base: ')).toBe(false);
  });
});

describe('ESC/POS recibo_pago — detalle de impuestos', () => {
  it('prints the same tax section as the salida ticket', () => {
    const payload = {
      ...conImpuestos(validSalidaPayload() as SalidaPayload),
      numero_recibo: 'sucursal-20260919-000001',
      medio_pago: 'efectivo',
    } as ReciboPagoPayload;
    const buf = build('recibo_pago', payload);
    expect(has(buf, 'IVA 19.00%')).toBe(true);
    expect(has(buf, `Base: ${copDecimalPlano(100840.34)}`)).toBe(true);
    expect(has(buf, `TOTAL: ${copDecimalPlano(120000)}`)).toBe(true);
  });
});

describe('fallback HTML — detalle de impuestos', () => {
  beforeEach(() => {
    document.head.innerHTML = '';
    document.body.innerHTML = '';
    vi.spyOn(window, 'print').mockImplementation(() => undefined);
  });

  it('salida HTML lists each tax with rate, base and amount', () => {
    print('salida', conImpuestos(validSalidaPayload() as SalidaPayload));
    const html = document.getElementById('parkos-escpos-fallback-container')?.textContent ?? '';
    expect(html).toContain('IVA 19.00%');
    expect(html).toContain(`Base: ${copDecimalPlano(100840.34)}`);
    expect(html).toContain(copDecimalPlano(19159.66));
    expect(html).toContain(`TOTAL: ${copDecimalPlano(120000)}`);
  });

  it('recibo HTML lists each tax with rate, base and amount', () => {
    print('recibo_pago', {
      ...conImpuestos(validSalidaPayload() as SalidaPayload),
      numero_recibo: 'sucursal-20260919-000001',
      medio_pago: 'efectivo',
    });
    const html = document.getElementById('parkos-escpos-fallback-container')?.textContent ?? '';
    expect(html).toContain('IVA 19.00%');
    expect(html).toContain(`Base: ${copDecimalPlano(100840.34)}`);
  });
});

describe('formatCOPDecimal', () => {
  it('keeps the cents of a tax amount', () => {
    expect(formatCOPDecimal(19159.66)).toContain('19.159,66');
  });
});

describe('impuestosDesdeFactura', () => {
  it('maps the persisted display rows to the print payload shape', () => {
    const factura = {
      impuestos: [
        {
          uuid: 'i1',
          uuid_impuesto: 'u1',
          nombre_impuesto: 'IVA',
          codigo_impuesto: 'IVA',
          base_calculo: 100840.34,
          porcentaje_aplicado: 0.19,
          valor: 19159.66,
        },
        {
          uuid: 'i2',
          uuid_impuesto: null,
          nombre_impuesto: null,
          codigo_impuesto: null,
          base_calculo: null,
          porcentaje_aplicado: null,
          valor: null,
        },
      ],
    } as unknown as FacturaRead;
    expect(impuestosDesdeFactura(factura)).toEqual([
      { nombre: 'IVA', porcentaje: 0.19, base: 100840.34, valor: 19159.66 },
      { nombre: 'Impuesto', porcentaje: 0, base: 0, valor: 0 },
    ]);
  });
});
