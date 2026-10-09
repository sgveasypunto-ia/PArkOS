/**
 * Every ticket the app prints (entrada, salida, salida con mensualidad, recibo
 * de pago, reimpresion, arqueo parcial) shares ONE format: 80 mm roll, 48
 * columns / 576 dots, easypunto logo on top and bottom, NO QR.
 */
import { describe, expect, it } from 'vitest';

import { build, lineasDeTiquete, type TiqueteTipo } from '../escposBuilder';
import { PAGE_RULE, renderTiqueteHtml } from '../fallbackBrowser';
import { expandirLineas, facturaATexto, lineasAEscpos } from '../facturaPrint';
import { TICKET_COLUMNAS } from '../ticketBase';
import fuenteBuilder from '../escposBuilder.ts?raw';
import fuenteFallback from '../fallbackBrowser.ts?raw';
import fuentePrintBuilder from '../printBuilder.ts?raw';
import fuentePrintHtml from '../printHtml.ts?raw';
import fuenteTemplates from '../escposTemplates.ts?raw';
import fuenteTiqueteLineas from '../tiqueteLineas.ts?raw';
import fuenteTiquetePrint from '../tiquetePrint.ts?raw';
import {
  ESCENARIOS_TIQUETE,
  FOLIO,
  NUMERO_REIMPRESION,
  entradaConPlaca,
  entradaSinPlaca,
  reimpresionEntrada,
} from './tiqueteFixtures';

const GS_PAREN_K = Buffer.from([0x1d, 0x28, 0x6b]);
const GS_W_576 = Buffer.from([0x1d, 0x57, 0x40, 0x02]);
const norm = (s: string): string => s.replace(/\u00a0/g, ' ');

/** The byte that follows every `ESC E` (bold). */
function parametrosEscE(buf: Buffer): Array<number | undefined> {
  const out: Array<number | undefined> = [];
  for (let i = 0; i < buf.length - 1; i++) {
    if (buf[i] === 0x1b && buf[i + 1] === 0x45) out.push(buf[i + 2]);
  }
  return out;
}

describe.each(ESCENARIOS_TIQUETE)('ticket 80 mm: %s', (_nombre, tipo, payload) => {
  const t = tipo as TiqueteTipo;
  const lineas = lineasDeTiquete(t, payload);
  const texto = norm(facturaATexto(lineas));
  const html = renderTiqueteHtml(t, payload);

  it('ninguna linea fisica excede 48 columnas', () => {
    for (const l of expandirLineas(lineas)) expect(l.texto.length).toBeLessThanOrEqual(TICKET_COLUMNAS);
  });

  it('abre y cierra con el logo easypunto (encabezado y pie)', () => {
    expect(lineas[0]).toEqual({ tipo: 'marca', posicion: 'encabezado' });
    expect(lineas[lineas.length - 1]).toEqual({ tipo: 'marca', posicion: 'pie' });
    expect(html.match(/<img[^>]*alt="easypunto"/g)).toHaveLength(2);
  });

  it('ESC/POS: area imprimible de 576 dots y logo raster cuando hay marca', () => {
    const buf = build(t, payload);
    expect(buf.indexOf(GS_W_576)).toBeGreaterThanOrEqual(0);
    const marca = { encabezado: Buffer.from([0xaa, 0xbb, 0xcc]), pie: Buffer.from([0xdd, 0xee, 0xff]) };
    const conMarca = lineasAEscpos(lineas, marca);
    expect(conMarca.indexOf(marca.encabezado)).toBeGreaterThanOrEqual(0);
    expect(conMarca.indexOf(marca.pie)).toBeGreaterThanOrEqual(0);
  });

  it('no tiene QR: ni GS ( k, ni ;QR:, ni <img alt=QR>, ni la palabra qr', () => {
    const buf = build(t, payload);
    expect(buf.indexOf(GS_PAREN_K)).toBe(-1);
    expect(buf.toString('latin1')).not.toMatch(/;QR:|qr/i);
    // The brand logo travels as a data URI whose path data may contain any letters: ignore it.
    const sinLogo = html.replace(/src="data:image[^"]*"/g, 'src=""');
    expect(sinLogo).not.toMatch(/qr/i);
    expect(sinLogo).not.toMatch(/<canvas|<svg/i);
    for (const img of sinLogo.match(/<img\b[^>]*>/gi) ?? []) expect(img).toMatch(/alt="easypunto"/);
    expect(texto.toLowerCase()).not.toMatch(/\bqr\b|;logo:/);
  });

  it('ESC E siempre lleva su parametro (00 o 01) y nunca aparece ESC F', () => {
    const buf = build(t, payload);
    const params = parametrosEscE(buf);
    expect(params.length).toBeGreaterThan(0);
    for (const p of params) expect([0x00, 0x01]).toContain(p);
    expect(buf.indexOf(Buffer.from([0x1b, 0x46]))).toBe(-1);
  });

  it('no usa ESC ! (texto 2x de 24 columnas): el ticket entero es de 48 columnas', () => {
    expect(build(t, payload).indexOf(Buffer.from([0x1b, 0x21]))).toBe(-1);
  });

  it('HTML: @page de 80 mm sin margen y ancho imprimible de 72 mm', () => {
    expect(html).toContain('@page { size: 80mm auto; margin: 0 }');
    expect(html).toContain('width:72mm');
    expect(html).toContain('white-space:pre-wrap');
    expect(PAGE_RULE).toBe('@page { size: 80mm auto; margin: 0 }');
  });
});

describe('ticket de entrada: contenido esencial', () => {
  const texto = norm(facturaATexto(lineasDeTiquete('entrada', entradaConPlaca())));

  it('lleva sucursal, empresa, NIT, direccion, regimen y operario', () => {
    expect(texto).toContain('Sede Centro');
    expect(texto).toContain('Inversiones y Representaciones');
    expect(texto).toContain('NIT 900123456-7');
    expect(texto).toContain('Carrera 43A No. 1 Sur - 31');
    expect(texto).toContain('Responsable de IVA');
    expect(texto).toContain('Operario: Operador de prueba');
  });

  it('lleva sello, tipo, folio, tarifa informativa, fecha y hora de Bogota, placa y horario', () => {
    expect(texto).toContain('*** TIQUETE DE ENTRADA ***');
    expect(texto).toContain('Tipo: ROTACIÓN');
    expect(texto).toContain(`Folio: ${FOLIO}`);
    expect(texto).toMatch(/Tarifa: \$ ?5\.000\/hora/);
    expect(texto).toContain('Fecha: 07/10/2026');
    expect(texto).toContain('Hora: 16:07');
    expect(texto).toContain('Placa: ABC123');
    expect(texto).toContain('Horario: Lunes a domingo, 24 horas');
    expect(texto).toContain('Poliza RC: POL-12345');
    expect(texto).toContain('Observaciones: Vehiculo con rayon');
    expect(texto).toContain('Conserve este tiquete para la salida.');
  });

  it('mensualidad y sin placa conservan sus reglas', () => {
    const mens = norm(
      facturaATexto(lineasDeTiquete('entrada', entradaConPlaca({ esMensualidad: true }))),
    );
    expect(mens).toContain('Tipo: MENSUALIDAD');
    const sinPlaca = norm(facturaATexto(lineasDeTiquete('entrada', entradaSinPlaca())));
    expect(sinPlaca).toContain('Identificación: BICI-000001-3f8a1b2c');
    expect(sinPlaca).not.toContain('Placa:');
    expect(sinPlaca).not.toContain('Tarifa:');
  });
});

describe('ticket de salida, mensualidad y recibo: contenido esencial', () => {
  it('salida: sello, tipo ROTACION, tiempos, montos con impuestos, medio de pago y resolucion', () => {
    const [, , payload] = ESCENARIOS_TIQUETE.find(([n]) => n === 'salida')!;
    const texto = norm(facturaATexto(lineasDeTiquete('salida', payload)));
    expect(texto).toContain('*** SALIDA ***');
    expect(texto).toContain('Tipo: ROTACIÓN');
    expect(texto).toContain('Hora entrada: 16:07');
    expect(texto).toContain('Hora salida: 18:37');
    expect(texto).toContain('Tiempo: 2 h 30 min');
    expect(texto).toMatch(/Subtotal: \$ ?10\.000,00/);
    expect(texto).toMatch(/IVA 19\.00%: \$ ?1\.900,00/);
    expect(texto).toMatch(/TOTAL: \$ ?11\.900,00/);
    expect(texto).toContain('Medio de pago: efectivo');
    expect(texto).toContain('Resolucion FE: RES-18760000001 de 2026');
    expect(texto).toContain('Gracias por su visita.');
  });

  it('salida con mensualidad: sello propio y NINGUN campo monetario', () => {
    const [, , payload] = ESCENARIOS_TIQUETE.find(([n]) => n === 'salida con mensualidad')!;
    const texto = norm(facturaATexto(lineasDeTiquete('salida-mensualidad', payload)));
    expect(texto).toContain('*** PAGO CON MENSUALIDAD ***');
    expect(texto).toContain('Tipo: MENSUALIDAD');
    expect(texto).toContain('Placa: ABC123');
    expect(texto).toContain('Conserve este tiquete como soporte.');
    expect(texto).not.toMatch(/Subtotal|IVA \d|TOTAL:|Medio de pago|\$/);
  });

  it('recibo: numero de recibo, medio de pago tipado y cierre de pago', () => {
    const [, , payload] = ESCENARIOS_TIQUETE.find(([n]) => n === 'recibo de pago')!;
    const texto = norm(facturaATexto(lineasDeTiquete('recibo_pago', payload)));
    expect(texto).toContain('*** RECIBO DE PAGO ***');
    expect(texto).toContain('Numero de recibo: sucursal-20261007-000042');
    expect(texto).toContain('Medio de pago: datafono');
    expect(texto).toMatch(/TOTAL: \$ ?11\.900,00/);
    expect(texto).toContain('Gracias por su pago.');
  });
});

describe('reimpresion', () => {
  it('lleva la leyenda REIMPRESION, su numero, el motivo y el folio original', () => {
    const texto = norm(facturaATexto(lineasDeTiquete('reimpresion', reimpresionEntrada())));
    expect(texto).toContain('*** REIMPRESIÓN ***');
    expect(texto).toContain(`Reimpresión No. ${NUMERO_REIMPRESION}`);
    expect(texto).toContain('--- COPIA AUTORIZADA ---');
    expect(texto).toContain('Motivo: Cliente perdio el tiquete original');
    expect(texto.replace(/\s+/g, ' ')).toContain(`Folio original: ${FOLIO}`);
  });

  it('se ve igual que el original: cada linea del tiquete de entrada esta en la reimpresion', () => {
    const original = expandirLineas(lineasDeTiquete('entrada', entradaConPlaca()))
      .map((l) => l.texto)
      .filter((l) => l.trim() !== '' && !/^-+$/.test(l));
    const reimpreso = expandirLineas(lineasDeTiquete('reimpresion', reimpresionEntrada())).map((l) => l.texto);
    for (const l of original) expect(reimpreso).toContain(l);
  });

  it('sin numero sigue mostrando la leyenda (sin inventar un numero)', () => {
    const texto = norm(
      facturaATexto(lineasDeTiquete('reimpresion', reimpresionEntrada(null))),
    );
    expect(texto).toContain('*** REIMPRESIÓN ***');
    expect(texto).not.toContain('Reimpresión No.');
  });

  it('el HTML trae la leyenda de reimpresion', () => {
    const html = renderTiqueteHtml('reimpresion', reimpresionEntrada());
    expect(html).toContain('REIMPRESIÓN');
    expect(html).toContain(NUMERO_REIMPRESION);
  });
});

describe('ninguna plantilla de ticket menciona ni emite QR', () => {
  it.each([
    ['escposBuilder', fuenteBuilder],
    ['fallbackBrowser', fuenteFallback],
    ['printHtml', fuentePrintHtml],
    ['printBuilder', fuentePrintBuilder],
    ['escposTemplates', fuenteTemplates],
    ['tiqueteLineas', fuenteTiqueteLineas],
    ['tiquetePrint', fuenteTiquetePrint],
  ])('%s', (_n, fuente) => {
    expect(fuente).not.toMatch(/qr|0x28,\s*0x6b|;LOGO:/i);
  });
});
