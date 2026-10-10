/**
 * easypunto brand on the 80 mm ticket: black-on-white vector, raster layer
 * with injected pixels (jsdom has no canvas), cache, text fallback, HTML img.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ANCHO_LOGO_ENCABEZADO,
  ANCHO_LOGO_PIE,
  LOGO_SVG_NEGRO,
  MARCA_ENCABEZADO,
  MARCA_PIE,
  cargarMarcaRaster,
  logoDataUri,
  reiniciarCacheMarca,
  type RasterizadorSvg,
} from '../marcaTicket';
import {
  construirFactura,
  facturaAEscpos,
  facturaAHtml,
  facturaATexto,
  imprimirFactura,
  lineasAEscpos,
} from '../facturaPrint';
import { TICKET_PUNTOS } from '../ticketBase';
import { FACTURA_ROTACION_200 } from './facturaFixtures';

/** Fake rasterizer: solid black pixels of the requested size. */
function negro(): RasterizadorSvg {
  return vi.fn(async (_svg: string, ancho: number, alto: number) => ({
    ancho,
    alto,
    datos: new Uint8ClampedArray(ancho * alto * 4).map((_, i) => (i % 4 === 3 ? 255 : 0)),
  }));
}

beforeEach(() => reiniciarCacheMarca());

describe('logo vectorial para termica', () => {
  it('el SVG de marca es blanco sobre transparente: se recolorea a negro', () => {
    expect(LOGO_SVG_NEGRO).toContain('<svg');
    expect(LOGO_SVG_NEGRO).not.toMatch(/#fff/i);
    expect(LOGO_SVG_NEGRO).toMatch(/fill="#000"/);
  });

  it('data URI del SVG para el HTML', () => {
    expect(logoDataUri()).toMatch(/^data:image\/svg\+xml;charset=utf-8,%3Csvg/);
  });

  it('los anchos son multiplos de 8 y caben en 576 dots', () => {
    for (const a of [ANCHO_LOGO_ENCABEZADO, ANCHO_LOGO_PIE]) {
      expect(a % 8).toBe(0);
      expect(a).toBeLessThanOrEqual(TICKET_PUNTOS);
    }
    expect(ANCHO_LOGO_PIE).toBeLessThan(ANCHO_LOGO_ENCABEZADO);
  });
});

describe('cargarMarcaRaster', () => {
  it('rasteriza encabezado y pie con la proporcion del logo y devuelve GS v 0', async () => {
    const r = negro();
    const marca = await cargarMarcaRaster(r);
    expect(marca).not.toBeNull();
    for (const [buf, ancho] of [
      [marca!.encabezado, ANCHO_LOGO_ENCABEZADO],
      [marca!.pie, ANCHO_LOGO_PIE],
    ] as const) {
      expect([...buf.subarray(0, 4)]).toEqual([0x1d, 0x76, 0x30, 0x00]);
      expect(buf[4]! + buf[5]! * 256).toBe(ancho / 8);
    }
    const [, w, h] = (r as ReturnType<typeof vi.fn>).mock.calls[0] as [string, number, number];
    expect(w).toBe(ANCHO_LOGO_ENCABEZADO);
    expect(h / w).toBeCloseTo(45.533 / 176.75, 1);
  });

  it('cachea: el logo no cambia, un segundo llamado no vuelve a rasterizar', async () => {
    const r = negro();
    const a = await cargarMarcaRaster(r);
    const b = await cargarMarcaRaster(r);
    expect(b).toBe(a);
    expect(r).toHaveBeenCalledTimes(2); // header + footer, once
  });

  it('si el rasterizador falla o no hay pixeles: null, y reintenta la proxima vez', async () => {
    const malo = vi.fn(async () => {
      throw new Error('sin canvas');
    });
    expect(await cargarMarcaRaster(malo)).toBeNull();
    const vacio = vi.fn(async () => null);
    expect(await cargarMarcaRaster(vacio)).toBeNull();
    expect(await cargarMarcaRaster(negro())).not.toBeNull();
  });

  it('en jsdom (sin canvas real) el rasterizador por defecto devuelve null sin colgarse', async () => {
    expect(await cargarMarcaRaster()).toBeNull();
  });
});

describe('factura con marca', () => {
  it('modelo: marca de encabezado primero y de pie al final', () => {
    const l = construirFactura(FACTURA_ROTACION_200);
    expect(l[0]).toEqual(MARCA_ENCABEZADO);
    expect(l[l.length - 1]).toEqual(MARCA_PIE);
  });

  it('ESC/POS con raster: imagen centrada tras init y antes del emisor, pie al final', async () => {
    const marca = (await cargarMarcaRaster(negro()))!;
    const b = facturaAEscpos(FACTURA_ROTACION_200, marca);
    const iEnc = b.indexOf(marca.encabezado);
    const iPie = b.lastIndexOf(marca.pie);
    expect(iEnc).toBeGreaterThan(0);
    expect(b.indexOf(Buffer.from('Parqueadero Centro'))).toBeGreaterThan(iEnc);
    expect(iPie).toBeGreaterThan(b.indexOf(Buffer.from('Gracias por su visita')));
    // centred before the image
    expect([...b.subarray(iEnc - 3, iEnc)]).toEqual([0x1b, 0x61, 0x01]);
    expect(b.toString('latin1')).not.toContain('easypunto');
  });

  it('sin logo cargado: cae al texto "easypunto" centrado (no rompe)', () => {
    const b = facturaAEscpos(FACTURA_ROTACION_200, null);
    expect([...b].join(',')).not.toContain('29,118,48');
    expect(b.toString('utf8').match(/easypunto/g)).toHaveLength(2);
    expect(b.indexOf(Buffer.from([0x1d, 0x76, 0x30]))).toBe(-1);
    expect(facturaATexto(construirFactura(FACTURA_ROTACION_200))).toContain('easypunto');
  });

  it('lineasAEscpos sin segundo argumento == sin logo', () => {
    const l = construirFactura(FACTURA_ROTACION_200);
    expect(lineasAEscpos(l).equals(lineasAEscpos(l, null))).toBe(true);
  });

  it('imprimirFactura (Electron) sin canvas: imprime con el texto de marca, sin fallar', async () => {
    const imprimir = Object.assign(vi.fn(async () => ({ ok: true })), { getQueue: async () => ({}), onStatus: () => () => undefined });
    const res = await imprimirFactura(FACTURA_ROTACION_200, { imprimir } as never);
    expect(res.ok).toBe(true);
    const arg = imprimir.mock.calls[0] as unknown as [{ buffer: string }];
    expect(Buffer.from(arg[0].buffer, 'base64').toString('utf8')).toContain('easypunto');
  });

  it('HTML: dos <img> SVG en blanco y negro, max 72 mm, sin romper', () => {
    const html = facturaAHtml(FACTURA_ROTACION_200);
    const imgs = html.match(/<img\b[^>]*>/g) ?? [];
    expect(imgs).toHaveLength(2);
    for (const img of imgs) {
      expect(img).toMatch(/src="data:image\/svg\+xml;charset=utf-8,%3Csvg/);
      expect(img).toContain('alt="easypunto"');
      expect(img).toMatch(/filter:\s*grayscale\(1\)/);
      expect(img).toMatch(/max-width:\s*72mm/);
    }
  });
});
