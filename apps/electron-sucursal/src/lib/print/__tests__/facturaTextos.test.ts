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
  descuentoEnBase,
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
    expect(etiquetaSemanticaLineas('base')).toBe('Valores antes de IVA');
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
    expect(txt).toContain('Valores antes de IVA');
    expect(txt).toContain('Subtotal (base)');
  });
});

/** Shape persisted by the backend since AUD2: IVA computed on the NET amount. */
const SALIDA_MENSUALIDAD_NETA = (descuento: number, total: number, base: number, valor: number) =>
  factura({
    subtotal: 1260.5,
    descuento,
    total,
    medio_pago: 'suscripcion',
    items: [
      linea('Parqueo', 1500),
      { ...linea('Descuento por mensualidad - Plan', descuento), tipo: 'descuento' },
    ],
    impuestos: iva(base, valor),
  });

describe('AUD2: factura con descuento y IVA sobre el neto', () => {
  it('total 0: el descuento se expresa en base y no hay IVA positivo', () => {
    const f = SALIDA_MENSUALIDAD_NETA(1500, 0, 0, 0);
    expect(descuentoEnBase(f)).toBe(1260.5);
    // subtotal - descuento + IVA == total
    expect(f.subtotal - descuentoEnBase(f) + f.impuestos[0].valor).toBeCloseTo(f.total, 2);
  });
  it('descuento parcial: 1500 - 500 -> base 840,34 + IVA 159,66 = 1.000', () => {
    const f = SALIDA_MENSUALIDAD_NETA(500, 1000, 840.34, 159.66);
    expect(descuentoEnBase(f)).toBeCloseTo(420.16, 2);
    expect(f.subtotal - descuentoEnBase(f) + f.impuestos[0].valor).toBeCloseTo(f.total, 2);
  });
  it('factura historica (IVA sobre el bruto) conserva el descuento persistido', () => {
    const f = factura({
      subtotal: 1260.5,
      descuento: 1500,
      total: 0,
      items: [linea('Parqueo', 1500)],
      impuestos: iva(1260.5, 239.5),
    });
    expect(descuentoEnBase(f)).toBe(1500);
  });
  it('sin descuento devuelve 0', () => {
    expect(descuentoEnBase(factura({ subtotal: 100, descuento: 0, total: 100 }))).toBe(0);
  });
  it('las lineas brutas se reconocen aunque el IVA neto sea 0', () => {
    expect(semanticaLineas(SALIDA_MENSUALIDAD_NETA(1500, 0, 0, 0))).toBe('bruto');
  });
  it('el ticket impreso lee Subtotal / Descuento / IVA / TOTAL con descuento en base', () => {
    const txt = facturaATexto(construirFactura(SALIDA_MENSUALIDAD_NETA(1500, 0, 0, 0))).replace(/\s+/g, ' ');
    expect(txt).toMatch(/Subtotal \(base\) \$ ?1\.260,50/);
    expect(txt).toMatch(/Descuento - \$ ?1\.260,50/);
    expect(txt).toMatch(/IVA 19% \$ ?0,00/);
    expect(txt).toMatch(/TOTAL \$ ?0,00/);
    expect(txt).toContain('Valores con IVA incluido');
  });
});

describe('AUD4: el bloque de totales se lee igual en todos los tipos', () => {
  const orden = (txt: string): string[] =>
    ['Subtotal (base)', 'IVA 19%', 'TOTAL'].filter((k) => txt.includes(k));
  const rot = facturaATexto(construirFactura(factura({
    subtotal: 1260.5, total: 1500, items: [linea('parqueo_tiempo', 1500)], impuestos: iva(1260.5, 239.5),
  })));
  const sub = facturaATexto(construirFactura(factura({
    subtotal: 100840.34, total: 120000, items: [linea('subscripcion_mensual', 100840.34)],
    impuestos: iva(100840.34, 19159.66),
  })));
  it('mismas filas y mismo orden', () => {
    expect(orden(rot)).toEqual(['Subtotal (base)', 'IVA 19%', 'TOTAL']);
    expect(orden(sub)).toEqual(orden(rot));
    for (const txt of [rot, sub]) {
      expect(txt.indexOf('Subtotal (base)')).toBeLessThan(txt.indexOf('IVA 19%'));
      expect(txt.indexOf('IVA 19%')).toBeLessThan(txt.indexOf('TOTAL'));
    }
  });
  it('las lineas declaran su semantica sin ambiguedad', () => {
    expect(rot).toContain('Valores con IVA incluido');
    expect(sub).toContain('Valores antes de IVA');
    expect(sub).not.toContain('Valores sin IVA');
  });
});
