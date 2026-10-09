/**
 * El HTML del ticket (fallback de navegador) debe conservar los espacios
 * iniciales de las líneas de continuación ("  Tres SAS", sangría de 2): con
 * `white-space: normal` el navegador los colapsa y la sangría desaparece.
 */
import { describe, expect, it } from 'vitest';

import { lineasAHtml, type FacturaLinea } from '../facturaPrint';

describe('lineasAHtml — espacios del ticket', () => {
  it('las líneas de texto conservan espacios iniciales (white-space: pre-wrap)', () => {
    const lineas: FacturaLinea[] = [
      { tipo: 'texto', texto: 'Empresa: Internacionales del Caribe' },
      { tipo: 'texto', texto: '  Colombiano SAS' },
    ];
    const doc = new DOMParser().parseFromString(lineasAHtml(lineas, 't'), 'text/html');
    const parrafos = Array.from(doc.querySelectorAll('p'));
    expect(parrafos).toHaveLength(2);
    for (const p of parrafos) {
      expect(p.getAttribute('style')).toMatch(/white-space:\s*pre-wrap/);
    }
    expect(parrafos[1]?.textContent).toBe('  Colombiano SAS');
  });

  it('el lado izquierdo de una fila con sangría conserva sus espacios', () => {
    const lineas: FacturaLinea[] = [
      { tipo: 'fila', izq: '  Descuento por mensualidad', der: '-$ 0,00', sangria: true },
    ];
    const doc = new DOMParser().parseFromString(lineasAHtml(lineas, 't'), 'text/html');
    const izq = doc.querySelector('div.fila span');
    expect(izq?.getAttribute('style')).toMatch(/white-space:\s*pre-wrap/);
  });
});
