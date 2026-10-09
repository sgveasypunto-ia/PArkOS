/**
 * `marcaTicket.ts` — easypunto brand for the 80 mm thermal tickets (invoice,
 * cierre de turno, future tickets): header logo + small footer logo.
 *
 * Asset: `logo-horizontal-light.svg` is the only VECTOR logo and it is drawn
 * white (`fill="#fff"`, meant for dark backgrounds). Thermal paper is black on
 * white, so the SVG text is recoloured to black here (no bitmap placeholder
 * `--REQUIERE-VECTOR` is used). There is no separate isotipo asset (the
 * `marker-glyph-*` icons are decorative capsules), so the footer is the same
 * logo, smaller.
 *
 * Three layers:
 *   - model: `MARCA_ENCABEZADO` / `MARCA_PIE` lines (channel-neutral, see
 *     `FacturaLinea`), rendered by `facturaPrint.ts` for every channel;
 *   - pure raster: `escposRaster.rasterGsV0` (RGBA → `GS v 0`);
 *   - thin canvas layer: `rasterizarConCanvas` (Electron renderer only),
 *     injectable so tests need no canvas.
 */
import logoSvgBlanco from '../../assets/brand/logos/logo-horizontal-light.svg?raw';
import { rasterGsV0, type ImagenRgba } from './escposRaster';
import type { FacturaLinea } from './facturaPrint';

/** Brand header / footer lines to put first / last in a ticket's line list. */
export const MARCA_ENCABEZADO: FacturaLinea = { tipo: 'marca', posicion: 'encabezado' };
export const MARCA_PIE: FacturaLinea = { tipo: 'marca', posicion: 'pie' };

/** Logo drawn black on transparent (the shipped SVG is white). */
export const LOGO_SVG_NEGRO: string = logoSvgBlanco.replace(/#fff\b/gi, '#000');

/** Intrinsic proportions of the SVG viewBox (176.75 x 45.533). */
const PROPORCION_ALTO = 45.533 / 176.75;

/** Raster widths in dots (multiples of 8; dots / 8 = millimetres in the HTML). */
export const ANCHO_LOGO_ENCABEZADO = 480;
export const ANCHO_LOGO_PIE = 240;

/** `data:` URI of the black SVG for the HTML channel (`<img src>`). */
export function logoDataUri(): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(LOGO_SVG_NEGRO)}`;
}

/** Ready-to-send `GS v 0` commands of both brand images. */
export interface MarcaRaster {
  encabezado: Buffer;
  pie: Buffer;
}

/** Turns an SVG into RGBA pixels of the given size (white background), or null if it cannot. */
export type RasterizadorSvg = (svg: string, ancho: number, alto: number) => Promise<ImagenRgba | null>;

const TIMEOUT_CARGA_MS = 3000;

/**
 * Canvas rasterizer for the Electron renderer. Returns null (never throws, never
 * hangs) where there is no real canvas: SSR and jsdom.
 */
export const rasterizarConCanvas: RasterizadorSvg = async (svg, ancho, alto) => {
  if (typeof document === 'undefined' || typeof Image === 'undefined') return null;
  if (typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent)) return null;
  const img = new Image();
  await new Promise<void>((resolver, rechazar) => {
    const timer = setTimeout(() => rechazar(new Error('logo: timeout')), TIMEOUT_CARGA_MS);
    img.onload = (): void => {
      clearTimeout(timer);
      resolver();
    };
    img.onerror = (): void => {
      clearTimeout(timer);
      rechazar(new Error('logo: no se pudo cargar'));
    };
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  });
  const canvas = document.createElement('canvas');
  canvas.width = ancho;
  canvas.height = alto;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return null;
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, ancho, alto);
  ctx.drawImage(img, 0, 0, ancho, alto);
  const { data } = ctx.getImageData(0, 0, ancho, alto);
  return { ancho, alto, datos: data };
};

let cache: Promise<MarcaRaster | null> | null = null;

/** Forget the cached raster (tests). */
export function reiniciarCacheMarca(): void {
  cache = null;
}

async function construir(rasterizar: RasterizadorSvg): Promise<MarcaRaster | null> {
  try {
    const pixeles = async (ancho: number): Promise<Buffer | null> => {
      const alto = Math.round(ancho * PROPORCION_ALTO);
      const img = await rasterizar(LOGO_SVG_NEGRO, ancho, alto);
      return img ? rasterGsV0(img) : null;
    };
    const encabezado = await pixeles(ANCHO_LOGO_ENCABEZADO);
    const pie = await pixeles(ANCHO_LOGO_PIE);
    return encabezado && pie ? { encabezado, pie } : null;
  } catch (err) {
    console.warn('[imprimir] el logo no se pudo rasterizar; se imprime el texto de marca:', err);
    return null;
  }
}

/**
 * Raster brand images, cached (the logo never changes). `null` when the pixels
 * cannot be obtained: callers then print the text fallback. A failure is not
 * cached, so the next print retries.
 */
export function cargarMarcaRaster(rasterizar: RasterizadorSvg = rasterizarConCanvas): Promise<MarcaRaster | null> {
  if (cache === null) {
    const pendiente = construir(rasterizar).then((m) => {
      if (m === null && cache === pendiente) cache = null;
      return m;
    });
    cache = pendiente;
  }
  return cache;
}
