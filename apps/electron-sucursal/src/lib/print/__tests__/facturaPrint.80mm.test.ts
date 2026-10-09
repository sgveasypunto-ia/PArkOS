/**
 * Invoice on 80 mm thermal paper: 48 columns (Font A), printable area set to
 * 576 dots, fixed-width HTML (72 mm) independent of the window size.
 */
import { describe, expect, it } from 'vitest';

import {
  construirFactura,
  facturaAEscpos,
  facturaAHtml,
  facturaATexto,
  lineasEmpresaTicket,
} from '../facturaPrint';
import type { FacturaRead } from '../../../features/facturacion/api/facturaApi';
import { TICKET_COLUMNAS } from '../ticketBase';
import {
  FACTURA_BASE,
  FACTURA_MENSUALIDAD_CERO,
  FACTURA_ROTACION_200,
  FACTURA_SUSCRIPCION_120000,
} from './facturaFixtures';

const EMPRESA_LARGA = 'Inversiones y Representaciones Internacionales del Caribe Colombiano SAS';
const CUFE = 'f3a9'.repeat(24);

const mensualidadEmpresa: FacturaRead = {
  ...FACTURA_MENSUALIDAD_CERO,
  datos_vehiculo: {
    ...FACTURA_MENSUALIDAD_CERO.datos_vehiculo!,
    empresa_suscripcion: EMPRESA_LARGA,
  },
};
const suscripcionDatafono: FacturaRead = {
  ...FACTURA_SUSCRIPCION_120000,
  medio_pago: 'datafono',
  voucher: '004512',
  factura_electronica: {
    uuid: FACTURA_SUSCRIPCION_120000.factura_electronica!.uuid,
    prefijo: 'SETP',
    consecutivo: 5,
    estado_dian: 'aceptado',
    cufe: CUFE,
  },
};
const conceptoLargo: FacturaRead = {
  ...FACTURA_ROTACION_200,
  items: [
    {
      ...FACTURA_ROTACION_200.items[0]!,
      concepto: 'Estadia por fraccion con tarifa diferencial nocturna de fin de semana',
    },
  ],
};
const CASOS: Record<string, FacturaRead> = {
  rotacion: FACTURA_ROTACION_200,
  mensualidadEmpresa,
  suscripcionDatafono,
  conceptoLargo,
  base: FACTURA_BASE,
};

describe('factura a 48 columnas', () => {
  it.each(Object.entries(CASOS))('%s: ninguna linea del ticket excede 48 columnas', (_n, f) => {
    const lineas = facturaATexto(construirFactura(f), TICKET_COLUMNAS).split('\n');
    for (const l of lineas) expect(l.length).toBeLessThanOrEqual(48);
  });

  it('el texto por defecto usa 48 columnas: separador de 48 guiones', () => {
    const lineas = facturaATexto(construirFactura(FACTURA_ROTACION_200)).split('\n');
    expect(lineas).toContain('-'.repeat(48));
  });

  it('TOTAL y cifras quedan alineadas a la derecha en 48 columnas', () => {
    const lineas = facturaATexto(construirFactura(FACTURA_SUSCRIPCION_120000)).split('\n');
    const total = lineas.find((l) => l.startsWith('TOTAL'));
    expect(total).toHaveLength(48);
    expect(total).toMatch(/\$ ?120\.000,00$/);
    const iva = lineas.find((l) => l.startsWith('IVA 19%'));
    expect(iva).toHaveLength(48);
  });

  it('CUFE de 96 caracteres se parte sin perder ni un caracter', () => {
    const lineas = facturaATexto(construirFactura(suscripcionDatafono)).split('\n');
    expect(lineas.join('').replace(/\s/g, '')).toContain(`CUFE:${CUFE}`);
  });

  it('empresa larga: ajustada a 48 con sangria de 2 y sin perder texto', () => {
    const lineas = lineasEmpresaTicket(EMPRESA_LARGA);
    expect(lineas.length).toBeGreaterThan(1);
    for (const l of lineas) expect(l.length).toBeLessThanOrEqual(48);
    expect(lineas[0]?.startsWith('Empresa: ')).toBe(true);
    expect(lineas.slice(1).every((l) => l.startsWith('  '))).toBe(true);
    expect(lineas.map((l) => l.trim()).join(' ').replace(/^Empresa: /, '')).toBe(EMPRESA_LARGA);
  });

  it('lineasEmpresaTicket: por defecto 48 (una razon social de 36 caracteres cabe en una linea)', () => {
    expect(lineasEmpresaTicket('Verif Empresa Ronda Tres SAS')).toEqual([
      'Empresa: Verif Empresa Ronda Tres SAS',
    ]);
  });

  it('lineasEmpresaTicket respeta un ancho explicito', () => {
    expect(lineasEmpresaTicket('Verif Empresa Ronda Tres SAS', 32)).toEqual([
      'Empresa: Verif Empresa Ronda',
      '  Tres SAS',
    ]);
  });
});

describe('ESC/POS 80 mm', () => {
  const sub = (b: Buffer, seq: number[]): number => b.indexOf(Buffer.from(seq));

  it('tras ESC @ fija margen 0, area imprimible de 576 dots (GS W 0x40 0x02) y Font A', () => {
    const b = facturaAEscpos(FACTURA_ROTACION_200);
    expect([...b.subarray(0, 2)]).toEqual([0x1b, 0x40]);
    expect([...b.subarray(2, 13)]).toEqual([
      0x1d, 0x4c, 0x00, 0x00, 0x1d, 0x57, 0x40, 0x02, 0x1b, 0x4d, 0x00,
    ]);
  });

  it.each(Object.entries(CASOS))('%s: ninguna linea de texto impreso excede 48 columnas', (_n, f) => {
    const b = facturaAEscpos(f);
    // Text lines only: strip the ESC/GS commands the renderer emits.
    const texto = b
      .toString('utf8')
      // eslint-disable-next-line no-control-regex -- ESC/GS opcodes are control bytes by definition
      .replace(/\x1b@|\x1b[aEM!][\s\S]|\x1d[LW][\s\S]{2}|\x1dV[\s\S]/g, '');
    for (const l of texto.split('\n')) expect(l.length).toBeLessThanOrEqual(48);
  });

  it('encabezado centrado y cifras a la derecha en 48 columnas', () => {
    const b = facturaAEscpos(FACTURA_SUSCRIPCION_120000);
    expect(sub(b, [0x1b, 0x61, 0x01])).toBeGreaterThan(0);
    expect(b.toString('utf8')).toMatch(/TOTAL {20,}\$ ?120\.000,00\n/);
  });
});

describe('HTML 80 mm', () => {
  const html = facturaAHtml(FACTURA_SUSCRIPCION_120000);

  it('declara @page 80mm auto sin margen', () => {
    expect(html).toMatch(/@page\s*\{\s*size:\s*80mm auto;\s*margin:\s*0\s*\}/);
  });

  it('el contenido mide 72 mm fijos (no depende de la ventana) y es monoespaciado', () => {
    expect(html).toMatch(/width:\s*72mm/);
    expect(html).toMatch(/monospace/);
    expect(html).not.toMatch(/width:\s*100%/);
    expect(html).not.toMatch(/\d+(vw|vh)/);
  });

  it('no fija altura (el largo del ticket es libre)', () => {
    expect(html).not.toMatch(/[^-]height:\s*\d/);
  });

  it('conserva el contenido (total, impuesto)', () => {
    expect(html).toContain('TOTAL');
    expect(html).toContain('IVA 19%');
  });
});
