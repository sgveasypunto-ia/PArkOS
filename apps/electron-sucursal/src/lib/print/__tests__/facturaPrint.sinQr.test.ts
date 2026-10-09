/**
 * The printed invoice never carries a QR code (customer requirement: it adds
 * no value). Guards the three outputs of the invoice route: ESC/POS bytes,
 * HTML and the source of the builder itself. The entrada ticket QR lives on
 * another route (escposBuilder entrada / fallbackBrowser entrada) and is NOT
 * covered here on purpose.
 */
import { describe, expect, it } from 'vitest';

import type { FacturaRead } from '../../../features/facturacion/api/facturaApi';
import { facturaAEscpos, facturaAHtml } from '../facturaPrint';
import fuenteFactura from '../facturaPrint.ts?raw';
import fuenteTicketBase from '../ticketBase.ts?raw';
import {
  FACTURA_BASE,
  FACTURA_MENSUALIDAD_CERO,
  FACTURA_ROTACION_200,
  FACTURA_SUSCRIPCION_120000,
} from './facturaFixtures';

const CASOS: Record<string, FacturaRead> = {
  base: FACTURA_BASE,
  rotacion: FACTURA_ROTACION_200,
  mensualidadCero: FACTURA_MENSUALIDAD_CERO,
  suscripcion: {
    ...FACTURA_SUSCRIPCION_120000,
    medio_pago: 'datafono',
    voucher: '004512',
  },
};

/** GS ( k — the ESC/POS 2D-symbol (QR) command family. */
const GS_PAREN_K = Buffer.from([0x1d, 0x28, 0x6b]);

describe.each(Object.entries(CASOS))('factura %s sin QR', (_n, f) => {
  it('el buffer ESC/POS no contiene GS ( k ni el marcador ;QR:', () => {
    const b = facturaAEscpos(f);
    expect(b.indexOf(GS_PAREN_K)).toBe(-1);
    expect(b.toString('latin1')).not.toMatch(/;QR:|qr/i);
  });

  it('el HTML no contiene QR, canvas ni svg inline', () => {
    // The brand logo travels as a data URI whose path data may contain any letters: ignore it.
    const html = facturaAHtml(f).replace(/src="data:image[^"]*"/g, 'src=""');
    expect(html).not.toMatch(/qr/i);
    expect(html).not.toMatch(/<canvas|<svg/i);
    // The only images allowed are the brand logos.
    for (const img of html.match(/<img\b[^>]*>/gi) ?? []) expect(img).toMatch(/alt="easypunto"/);
  });
});

describe('ruta de factura sin codigo QR', () => {
  it('ni el constructor de factura ni la base 80 mm mencionan ni emiten QR', () => {
    expect(fuenteFactura).not.toMatch(/qr|0x28,\s*0x6b/i);
    expect(fuenteTicketBase).not.toMatch(/qr|0x28,\s*0x6b/i);
  });
});
