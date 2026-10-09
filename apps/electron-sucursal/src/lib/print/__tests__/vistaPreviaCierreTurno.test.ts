/**
 * Dev utility: writes the 80 mm cierre-de-turno ticket preview. Skipped unless
 * `PARKOS_VISTA_PREVIA=1` (see `vistaPreviaCierreTurno.ts`). The content checks
 * run always and never touch the filesystem.
 */
import { describe, expect, it } from 'vitest';

import {
  escribirVistaPreviaCierreTurno,
  paginaHtmlCierreTurno,
  volcadoTextoCierreTurno,
} from './vistaPreviaCierreTurno';

describe('vista previa del ticket de cierre de turno (contenido)', () => {
  it('cubre cuadrada, faltante y sobrante', () => {
    const texto = volcadoTextoCierreTurno();
    expect(texto).toContain('Caja cuadrada');
    expect(texto).toContain('Faltante');
    expect(texto).toContain('Sobrante');
    expect(texto.match(/CIERRE DE TURNO/g)).toHaveLength(3);
  });

  it('el volcado respeta el borde de 48 columnas', () => {
    for (const l of volcadoTextoCierreTurno().split('\n').filter((x) => x.endsWith('|'))) {
      expect(l.length).toBe(49);
      expect(l[48]).toBe('|');
    }
  });

  it('la página HTML ubica cada ticket en 302 px, con logo y sin QR', () => {
    const html = paginaHtmlCierreTurno();
    expect(html.match(/width:302px/g)).toHaveLength(3);
    expect(html).toContain('width:72mm');
    expect(html).toContain('<img');
    expect(html.toLowerCase()).not.toMatch(/qr/);
  });
});

describe.skipIf(process.env.PARKOS_VISTA_PREVIA !== '1')('escribe la vista previa', () => {
  it('genera ticket-cierre-turno-80mm.html y .txt', () => {
    const { html, txt } = escribirVistaPreviaCierreTurno();
    console.log(`vista previa: ${html}\n              ${txt}`);
    expect(html).toMatch(/ticket-cierre-turno-80mm\.html$/);
  });
});
