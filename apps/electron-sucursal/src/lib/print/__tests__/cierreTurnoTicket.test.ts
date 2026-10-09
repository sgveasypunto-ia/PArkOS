/**
 * Ticket de cierre de TURNO en papel térmico de 80 mm: 48 columnas, logos
 * easypunto (encabezado y pie), sin QR, con firma del operador y exactamente las
 * filas del resumen post-cierre en pantalla.
 */
import { describe, expect, it } from 'vitest';

import { cierreAEscpos, cierreAHtml, construirCierre } from '../arqueoPrint';
import { expandirLineas, facturaATexto } from '../facturaPrint';
import { TICKET_COLUMNAS } from '../ticketBase';
import { ESCENARIOS_CIERRE } from './cierreTurnoFixtures';

const GS_PAREN_K = Buffer.from([0x1d, 0x28, 0x6b]);
const norm = (s: string): string => s.replace(/\u00a0/g, ' ');

describe.each(ESCENARIOS_CIERRE)('cierre de turno: $nombre', ({ cierre }) => {
  const lineas = construirCierre(cierre);
  const texto = norm(facturaATexto(lineas));

  it('ninguna línea física excede 48 columnas', () => {
    for (const l of expandirLineas(lineas)) expect(l.texto.length).toBeLessThanOrEqual(TICKET_COLUMNAS);
  });

  it('abre y cierra con la marca easypunto', () => {
    expect(lineas[0]).toEqual({ tipo: 'marca', posicion: 'encabezado' });
    expect(lineas[lineas.length - 1]).toEqual({ tipo: 'marca', posicion: 'pie' });
    expect(cierreAHtml(cierre)).toContain('<img');
  });

  it('lleva título, sucursal, operador y fechas de apertura y cierre', () => {
    expect(texto).toContain('CIERRE DE TURNO');
    expect(texto).toContain('Sucursal Norte');
    expect(texto).toContain('Operador: Operador QA');
    expect(texto).toMatch(/Hora de apertura\s+07\/10\/26 08:00/);
    expect(texto).toMatch(/Hora de cierre\s+07\/10\/26 16:30/);
  });

  it('repite cada fila del resumen en pantalla con su etiqueta y valor', () => {
    for (const s of cierre.secciones ?? []) {
      for (const r of s.rows) {
        expect(texto).toContain(r.label.slice(0, 20));
        if (r.value.length <= 24) expect(texto).toContain(norm(r.value));
      }
    }
  });

  it('deja el espacio de firma del operador', () => {
    expect(texto).toMatch(/Firma: _{10,}/);
  });

  it('no tiene QR en ESC/POS ni en HTML', () => {
    expect(cierreAEscpos(cierre).indexOf(GS_PAREN_K)).toBe(-1);
    expect(cierreAHtml(cierre).toLowerCase()).not.toMatch(/qr/);
    expect(texto.toLowerCase()).not.toMatch(/\bqr\b/);
  });

  it('no inventa cuadre de datáfono', () => {
    expect(texto.toLowerCase()).not.toMatch(/datafono (esperado|reportado|contado)|datáfono (esperado|reportado|contado)/);
  });
});

describe('contenido por escenario', () => {
  const [cuadrada, faltante, sobrante] = ESCENARIOS_CIERRE.map((e) => norm(facturaATexto(construirCierre(e.cierre))));

  it('diferencia 0: muestra $ 0 sin signo y el detalle de cobros', () => {
    expect(cuadrada).toMatch(/Diferencia\s+\$ 0\b/);
    expect(cuadrada).toMatch(/Efectivo \(39\)\s+\$ 187\.500/);
    expect(cuadrada).toMatch(/Ingresos\s+41/);
    expect(cuadrada).toMatch(/Salidas\s+39/);
    expect(cuadrada).toMatch(/Reversos \(1\)\s+\$ 4\.000/);
    expect(cuadrada).toMatch(/Producido consignado\s+\$ 187\.500/);
  });

  it('faltante: diferencia negativa y observaciones completas y envueltas', () => {
    expect(faltante).toMatch(/Diferencia\s+-\$ 5\.000/);
    expect(faltante).toMatch(/Efectivo contado\s+\$ 232\.500/);
    expect(faltante).toMatch(/Efectivo esperado\s+\$ 237\.500/);
    expect(faltante).toContain('sin registrar el pago en el sistema');
  });

  it('sobrante sin detalle: positiva y avisa que el detalle no está disponible', () => {
    expect(sobrante).toMatch(/Diferencia\s+\+\$ 2\.500/);
    expect(sobrante).toContain('No disponible');
    expect(sobrante).not.toMatch(/Ingresos\s+\d/);
  });
});

describe('cierre diario y cierre de turno automático heredan ancho y marca', () => {
  const BASE = { operador: 'Supervisor Demo', reportado: 500_000, esperado: 500_000, diferencia: 0 } as const;
  it.each([
    ['cierre_dia' as const],
    ['cierre_turno' as const],
  ])('%s: 48 columnas, logo arriba y abajo, sin QR', (tipo) => {
    const d = { tipo, ...BASE, sucursal: 'Sucursal con un nombre bastante largo para forzar el ajuste de línea' };
    const lineas = construirCierre(d);
    expect(lineas[0]).toEqual({ tipo: 'marca', posicion: 'encabezado' });
    expect(lineas[lineas.length - 1]).toEqual({ tipo: 'marca', posicion: 'pie' });
    for (const l of expandirLineas(lineas)) expect(l.texto.length).toBeLessThanOrEqual(TICKET_COLUMNAS);
    expect(cierreAEscpos(d).indexOf(GS_PAREN_K)).toBe(-1);
    expect(cierreAHtml(d)).not.toMatch(/qr/i);
  });
});
