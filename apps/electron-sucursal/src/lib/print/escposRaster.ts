/**
 * `escposRaster.ts` — pure ESC/POS raster image encoder (`GS v 0`).
 *
 * RGBA pixels in, command bytes out. No DOM, no canvas: the caller supplies
 * the pixels (the thin canvas layer lives in `marcaTicket.ts`).
 *
 * Command: `GS v 0 m xL xH yL yH d1…dk` — m = 0 (normal density), xL/xH =
 * bytes per row (width / 8, rounded up), yL/yH = rows; each byte packs 8
 * pixels, MSB = leftmost, bit 1 = black dot.
 */
import { TICKET_PUNTOS } from './ticketBase';

/** Luminance (0-255) below which a pixel prints black. Biased high on purpose: thermal heads thin out strokes. */
export const UMBRAL_TERMICO = 176;

export interface ImagenRgba {
  ancho: number;
  alto: number;
  /** RGBA, 4 bytes per pixel, row-major. */
  datos: ArrayLike<number>;
}

export interface OpcionesRaster {
  umbral?: number;
  /** Maximum width in dots (default: the 80 mm printable width). */
  anchoMaxDots?: number;
}

/** Encode `img` as a `GS v 0` raster command. Transparent pixels count as white paper. */
export function rasterGsV0(img: ImagenRgba, opciones: OpcionesRaster = {}): Buffer {
  const { ancho, alto, datos } = img;
  const umbral = opciones.umbral ?? UMBRAL_TERMICO;
  const maxDots = opciones.anchoMaxDots ?? TICKET_PUNTOS;
  if (!Number.isInteger(ancho) || !Number.isInteger(alto) || ancho < 1 || alto < 1) {
    throw new RangeError('raster: ancho/alto invalidos');
  }
  if (ancho > maxDots) throw new RangeError(`raster: ancho ${ancho} excede ${maxDots} dots`);
  if (alto > 0xffff) throw new RangeError('raster: alto excede 65535 filas');
  if (datos.length !== ancho * alto * 4) throw new RangeError('raster: datos no coinciden con ancho x alto');

  const bytesFila = Math.ceil(ancho / 8);
  const out = Buffer.alloc(8 + bytesFila * alto);
  out.set([0x1d, 0x76, 0x30, 0x00, bytesFila & 0xff, bytesFila >> 8, alto & 0xff, alto >> 8], 0);
  for (let y = 0; y < alto; y++) {
    for (let x = 0; x < ancho; x++) {
      const i = (y * ancho + x) * 4;
      const a = (datos[i + 3] as number) / 255;
      const lum =
        (0.299 * (datos[i] as number) + 0.587 * (datos[i + 1] as number) + 0.114 * (datos[i + 2] as number)) * a +
        255 * (1 - a);
      if (lum < umbral) {
        const pos = 8 + y * bytesFila + (x >> 3);
        out[pos] = (out[pos] as number) | (0x80 >> (x & 7));
      }
    }
  }
  return out;
}
