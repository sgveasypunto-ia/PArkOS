/**
 * Pure ESC/POS raster rasterizer (`GS v 0`): RGBA pixels in, command bytes out.
 */
import { describe, expect, it } from 'vitest';

import { UMBRAL_TERMICO, rasterGsV0 } from '../escposRaster';
import { TICKET_PUNTOS } from '../ticketBase';

/** Build RGBA from a grid of 'X' (opaque black), '.' (opaque white), 't' (transparent). */
function img(filas: string[]): { ancho: number; alto: number; datos: Uint8ClampedArray } {
  const ancho = filas[0]!.length;
  const datos = new Uint8ClampedArray(ancho * filas.length * 4);
  filas.forEach((fila, y) => {
    [...fila].forEach((c, x) => {
      const i = (y * ancho + x) * 4;
      const v = c === 'X' ? 0 : 255;
      datos[i] = v;
      datos[i + 1] = v;
      datos[i + 2] = v;
      datos[i + 3] = c === 't' ? 0 : 255;
    });
  });
  return { ancho, alto: filas.length, datos };
}

describe('rasterGsV0', () => {
  it('cabecera GS v 0 m xL xH yL yH y tamano exacto de datos', () => {
    const b = rasterGsV0(img(['XXXXXXXX', '........', 'XXXXXXXX']));
    expect([...b.subarray(0, 8)]).toEqual([0x1d, 0x76, 0x30, 0x00, 1, 0, 3, 0]);
    expect(b.length).toBe(8 + 1 * 3);
  });

  it('empaqueta 8 pixeles por byte, MSB = pixel izquierdo, 1 = negro', () => {
    const b = rasterGsV0(img(['X.......', '.......X', 'X.X.X.X.', 'XXXX....']));
    expect([...b.subarray(8)]).toEqual([0b10000000, 0b00000001, 0b10101010, 0b11110000]);
  });

  it('ancho no multiplo de 8: rellena con blanco hasta el byte completo', () => {
    const b = rasterGsV0(img(['XXXXXXXXXX'])); // 10 px -> 2 bytes/fila
    expect([...b.subarray(4, 8)]).toEqual([2, 0, 1, 0]);
    expect([...b.subarray(8)]).toEqual([0xff, 0b11000000]);
  });

  it('umbral: gris claro queda blanco, gris oscuro queda negro', () => {
    const datos = new Uint8ClampedArray(2 * 4);
    datos.set([UMBRAL_TERMICO + 10, UMBRAL_TERMICO + 10, UMBRAL_TERMICO + 10, 255], 0);
    datos.set([UMBRAL_TERMICO - 10, UMBRAL_TERMICO - 10, UMBRAL_TERMICO - 10, 255], 4);
    const b = rasterGsV0({ ancho: 2, alto: 1, datos });
    expect(b[8]).toBe(0b01000000);
  });

  it('umbral explicito', () => {
    const datos = new Uint8ClampedArray([100, 100, 100, 255]);
    expect(rasterGsV0({ ancho: 1, alto: 1, datos }, { umbral: 50 })[8]).toBe(0);
    expect(rasterGsV0({ ancho: 1, alto: 1, datos }, { umbral: 150 })[8]).toBe(0b10000000);
  });

  it('pixeles transparentes se tratan como papel blanco (no imprimen)', () => {
    const b = rasterGsV0(img(['tttttttt']));
    expect(b[8]).toBe(0);
  });

  it('usa la luminancia: rojo y azul puros imprimen, amarillo claro no', () => {
    const datos = new Uint8ClampedArray([255, 0, 0, 255, 0, 0, 255, 255]);
    const b = rasterGsV0({ ancho: 2, alto: 1, datos });
    // red lum ~76 and blue lum ~29 are below the threshold; yellow (~226) is not.
    expect(b[8]).toBe(0b11000000);
    const amarillo = rasterGsV0({ ancho: 1, alto: 1, datos: new Uint8ClampedArray([255, 255, 0, 255]) });
    expect(amarillo[8]).toBe(0);
  });

  it('acepta hasta 576 dots y rechaza mas', () => {
    const ok = rasterGsV0({ ancho: TICKET_PUNTOS, alto: 1, datos: new Uint8ClampedArray(TICKET_PUNTOS * 4).fill(255) });
    expect([...ok.subarray(4, 6)]).toEqual([72, 0]);
    expect(() =>
      rasterGsV0({ ancho: TICKET_PUNTOS + 1, alto: 1, datos: new Uint8ClampedArray((TICKET_PUNTOS + 1) * 4) }),
    ).toThrow(RangeError);
  });

  it('rechaza datos que no coinciden con ancho x alto', () => {
    expect(() => rasterGsV0({ ancho: 4, alto: 2, datos: new Uint8ClampedArray(4) })).toThrow(RangeError);
  });

  it('alto > 255 se codifica en yL yH', () => {
    const b = rasterGsV0({ ancho: 8, alto: 300, datos: new Uint8ClampedArray(8 * 300 * 4) });
    expect([...b.subarray(6, 8)]).toEqual([300 & 0xff, 300 >> 8]);
  });
});
