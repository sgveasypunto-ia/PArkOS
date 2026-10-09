/**
 * Dev utility: writes the 80 mm operation-ticket previews. Skipped unless
 * `PARKOS_VISTA_PREVIA=1` (see `vistaPreviaTiquetes.ts`). The content checks
 * run always and never touch the filesystem.
 */
import { describe, expect, it } from 'vitest';

import {
  ESCENARIOS_TIQUETES,
  escribirVistaPreviaTiquetes,
  paginaHtmlTiquetes,
  volcadoTextoTiquetes,
} from './vistaPreviaTiquetes';

describe('vista previa de los tickets de operacion (contenido)', () => {
  it('cubre entrada, reimpresion de entrada, salida, salida con mensualidad y recibo', () => {
    const texto = volcadoTextoTiquetes();
    expect(texto).toContain('*** TIQUETE DE ENTRADA ***');
    expect(texto).toContain('*** REIMPRESIÓN ***');
    expect(texto).toContain('*** SALIDA ***');
    expect(texto).toContain('*** PAGO CON MENSUALIDAD ***');
    expect(texto).toContain('*** RECIBO DE PAGO ***');
    expect(texto.match(/^=== /gm)).toHaveLength(ESCENARIOS_TIQUETES.length);
  });

  it('el volcado respeta el borde de 48 columnas', () => {
    for (const l of volcadoTextoTiquetes().split('\n').filter((x) => x.endsWith('|'))) {
      expect(l.length).toBe(49);
      expect(l[48]).toBe('|');
    }
  });

  it('la pagina HTML ubica cada ticket en 302 px, con logo y sin QR', () => {
    const html = paginaHtmlTiquetes();
    expect(html.match(/width:302px/g)).toHaveLength(ESCENARIOS_TIQUETES.length);
    expect(html).toContain('width:72mm');
    expect(html).toContain('<img');
    expect(html.replace(/src="data:image[^"]*"/g, 'src=""').toLowerCase()).not.toMatch(/qr/);
  });
});

describe.skipIf(process.env.PARKOS_VISTA_PREVIA !== '1')('escribe la vista previa', () => {
  it('genera ticket-tiquetes-80mm.html y .txt', () => {
    const { html, txt } = escribirVistaPreviaTiquetes();
    console.log(`vista previa: ${html}\n              ${txt}`);
    expect(html).toMatch(/ticket-tiquetes-80mm\.html$/);
  });
});
