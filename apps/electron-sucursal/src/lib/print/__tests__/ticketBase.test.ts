/**
 * Shared 80 mm thermal base: column constant, row/wrap primitives and the
 * printable-area ESC/POS command.
 */
import { describe, expect, it } from 'vitest';

import {
  TICKET_ANCHO_IMPRIMIBLE_MM,
  TICKET_ANCHO_PAPEL_MM,
  TICKET_COLUMNAS,
  TICKET_PUNTOS,
  ajustarTexto,
  escAreaImprimible,
  filaTicket,
  separadorTicket,
} from '../ticketBase';
import { FACTURA_COLUMNAS } from '../facturaPrint';

describe('constantes 80 mm', () => {
  it('48 columnas Font A = 576 dots = 72 mm sobre papel de 80 mm', () => {
    expect(TICKET_COLUMNAS).toBe(48);
    expect(TICKET_PUNTOS).toBe(576);
    expect(TICKET_PUNTOS / TICKET_COLUMNAS).toBe(12);
    expect(TICKET_ANCHO_PAPEL_MM).toBe(80);
    expect(TICKET_ANCHO_IMPRIMIBLE_MM).toBe(72);
  });

  it('FACTURA_COLUMNAS deriva de la constante comun', () => {
    expect(FACTURA_COLUMNAS).toBe(TICKET_COLUMNAS);
  });
});

describe('escAreaImprimible', () => {
  it('GS L 0 0, GS W 0x40 0x02 (576) y ESC M 0', () => {
    expect([...escAreaImprimible()]).toEqual([
      0x1d, 0x4c, 0x00, 0x00, 0x1d, 0x57, 0x40, 0x02, 0x1b, 0x4d, 0x00,
    ]);
  });

  it('acepta otro ancho (640 dots = 80 mm completos)', () => {
    expect([...escAreaImprimible(640)].slice(4, 8)).toEqual([0x1d, 0x57, 0x80, 0x02]);
  });
});

describe('ajustarTexto', () => {
  it('no toca lo que cabe', () => {
    expect(ajustarTexto('hola', 48)).toEqual(['hola']);
  });

  it('parte por palabras y respeta el ancho', () => {
    const t = 'uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce';
    const l = ajustarTexto(t, 48);
    expect(l.length).toBeGreaterThan(1);
    for (const x of l) expect(x.length).toBeLessThanOrEqual(48);
    expect(l.join(' ')).toBe(t);
  });

  it('corta duro un token mas largo que la linea (CUFE) sin perder caracteres', () => {
    const cufe = 'a1'.repeat(48);
    const l = ajustarTexto(`CUFE: ${cufe}`, 48);
    for (const x of l) expect(x.length).toBeLessThanOrEqual(48);
    expect(l.join('').replace(/\s/g, '')).toBe(`CUFE:${cufe}`);
  });

  it('conserva la sangria en las lineas de continuacion', () => {
    const l = ajustarTexto('  ' + 'palabra '.repeat(12).trim(), 48);
    expect(l.every((x) => x.startsWith('  '))).toBe(true);
    expect(l.every((x) => x.length <= 48)).toBe(true);
  });
});

describe('filaTicket / separadorTicket', () => {
  it('fila corta: exactamente 48 columnas, cifra alineada a la derecha', () => {
    const [l, ...resto] = filaTicket('TOTAL', '$ 120.000,00', 48);
    expect(resto).toEqual([]);
    expect(l).toHaveLength(48);
    expect(l?.startsWith('TOTAL')).toBe(true);
    expect(l?.endsWith('$ 120.000,00')).toBe(true);
  });

  it('etiqueta que no cabe junto a la cifra: la cifra baja alineada a la derecha', () => {
    const izq = 'Mensualidad automovil premium con cobertura extendida x1';
    const l = filaTicket(izq, '$ 120.000,00', 48);
    for (const x of l) expect(x.length).toBeLessThanOrEqual(48);
    expect(l[l.length - 1]).toHaveLength(48);
    expect(l[l.length - 1]?.endsWith('$ 120.000,00')).toBe(true);
    expect(l.slice(0, -1).join(' ').replace(/\s+/g, ' ')).toContain('Mensualidad automovil premium');
  });

  it('con sangria', () => {
    const [l] = filaTicket('Detalle', '$ 1,00', 48, true);
    expect(l?.startsWith('  Detalle')).toBe(true);
    expect(l).toHaveLength(48);
  });

  it('separador de 48', () => {
    expect(separadorTicket()).toBe('-'.repeat(48));
  });
});
