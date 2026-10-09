/**
 * Dev utility: writes the 80 mm ticket preview files. Skipped unless
 * `PARKOS_VISTA_PREVIA=1` (see `vistaPreviaTicket.ts`). The content checks run
 * always and never touch the filesystem.
 */
import { describe, expect, it } from 'vitest';

import { CASOS_VISTA_PREVIA, escribirVistaPrevia, paginaHtml, volcadoTexto } from './vistaPreviaTicket';

describe('vista previa del ticket 80 mm (contenido)', () => {
  it('cubre rotacion, mensualidad $0 con Empresa larga y suscripcion con datafono + voucher', () => {
    const texto = volcadoTexto();
    expect(CASOS_VISTA_PREVIA).toHaveLength(3);
    expect(texto).toContain('Empresa: Inversiones');
    expect(texto).toContain('Voucher: 004512');
    expect(texto).toContain('Mensualidad');
  });

  it('el volcado respeta el borde de 48 columnas (marcador | en la columna 49)', () => {
    for (const l of volcadoTexto().split('\n').filter((x) => x.endsWith('|'))) expect(l.length).toBe(49);
  });

  it('la pagina HTML ubica cada ticket en 302 px', () => {
    const html = paginaHtml();
    expect(html.match(/width:302px/g)).toHaveLength(3);
    expect(html).toContain('width:72mm');
  });
});

describe.skipIf(process.env.PARKOS_VISTA_PREVIA !== '1')('escribe la vista previa', () => {
  it('genera ticket-factura-80mm.html y .txt', () => {
    const { html, txt } = escribirVistaPrevia();
    console.log(`vista previa: ${html}\n              ${txt}`);
    expect(html).toMatch(/ticket-factura-80mm\.html$/);
  });
});
