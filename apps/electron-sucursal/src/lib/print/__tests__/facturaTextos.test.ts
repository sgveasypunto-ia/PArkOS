/**
 * FB3 — one shared mapper of invoice concept codes and of the line-amount
 * semantics (stored base vs stored gross), used by the display modal and the
 * printed invoice.
 */
import { describe, it, expect } from 'vitest';

import {
  conceptoLegible,
  semanticaLineas,
  etiquetaSemanticaLineas,
} from '../facturaTextos';
import { construirFactura, facturaATexto } from '../facturaPrint';
import { FACTURA_BASE } from './facturaFixtures';
import type { FacturaRead } from '../../../features/facturacion/api/facturaApi';

const U = (n: number): string => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;

describe('conceptoLegible', () => {
  it('maps the known codes to Spanish labels', () => {
    expect(conceptoLegible('subscripcion_mensual')).toBe('Suscripción mensual');
    expect(conceptoLegible('suscripcion_mensual')).toBe('Suscripción mensual');
    expect(conceptoLegible('reimpresion')).toBe('Reimpresión de tiquete');
    expect(conceptoLegible('reimpresion_tiquete')).toBe('Reimpresión de tiquete');
    expect(conceptoLegible('parqueo_tiempo')).toBe('Parqueo por tiempo');
    expect(conceptoLegible('descuento_mensualidad')).toBe('Descuento mensualidad');
  });
  it('humanizes unknown codes (underscores, capital)', () => {
    expect(conceptoLegible('lavado_de_vehiculo')).toBe('Lavado de vehiculo');
  });
  it('leaves already human text untouched', () => {
    expect(conceptoLegible('Servicio de parqueo')).toBe('Servicio de parqueo');
    expect(conceptoLegible('Mensualidad automovil')).toBe('Mensualidad automovil');
  });
  it('is tolerant of empty values', () => {
    expect(conceptoLegible('')).toBe('');
    expect(conceptoLegible(null)).toBe('');
  });
});

function factura(over: Partial<FacturaRead>): FacturaRead {
  return { ...FACTURA_BASE, ...over };
}
const iva = (base: number, valor: number): FacturaRead['impuestos'] => [
  {
    uuid: U(1),
    uuid_impuesto: U(2),
    nombre_impuesto: 'IVA',
    codigo_impuesto: '01',
    base_calculo: base,
    porcentaje_aplicado: 0.19,
    valor,
  },
];
const linea = (concepto: string, subtotal: number): FacturaRead['items'][number] => ({
  uuid: U(subtotal),
  tipo: 'servicio',
  concepto,
  cantidad: 1,
  valor_unitario: subtotal,
  subtotal,
});

describe('semanticaLineas', () => {
  it('parking invoice: lines are the gross (IVA included)', () => {
    const f = factura({
      subtotal: 1260.5,
      total: 1500,
      items: [linea('parqueo_tiempo', 1500)],
      impuestos: iva(1260.5, 239.5),
    });
    expect(semanticaLineas(f)).toBe('bruto');
    expect(etiquetaSemanticaLineas('bruto')).toBe('Valores con IVA incluido');
  });
  it('subscription invoice: lines are the base (no IVA)', () => {
    const f = factura({
      subtotal: 100840.34,
      total: 120000,
      items: [linea('subscripcion_mensual', 100840.34)],
      impuestos: iva(100840.34, 19159.66),
    });
    expect(semanticaLineas(f)).toBe('base');
    expect(etiquetaSemanticaLineas('base')).toBe('Valores sin IVA');
  });
  it('unknown when neither reconciles (no misleading label)', () => {
    const f = factura({
      subtotal: 1000,
      total: 1190,
      items: [linea('x', 777)],
      impuestos: iva(1000, 190),
    });
    expect(semanticaLineas(f)).toBeNull();
    expect(etiquetaSemanticaLineas(null)).toBeNull();
  });
});

describe('printed invoice', () => {
  const sub = factura({
    subtotal: 100840.34,
    total: 120000,
    items: [linea('subscripcion_mensual', 100840.34)],
    impuestos: iva(100840.34, 19159.66),
  });
  it('prints the Spanish concept, never the raw code', () => {
    const txt = facturaATexto(construirFactura(sub));
    expect(txt).toContain('Suscripción mensual');
    expect(txt).not.toContain('subscripcion_mensual');
  });
  it('labels the line values and the totals block', () => {
    const txt = facturaATexto(construirFactura(sub));
    expect(txt).toContain('Valores sin IVA');
    expect(txt).toContain('Subtotal (base)');
  });
});
