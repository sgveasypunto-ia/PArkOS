/**
 * Negrita ESC/POS: `ESC E n` lleva SIEMPRE su parametro `n` (00 apaga, 01 enciende).
 * Sin `n`, la impresora consume el primer caracter del texto como parametro.
 */
import { describe, it, expect } from 'vitest';

import { build, escBoldOn, escBoldOff } from '../escposBuilder';
import { escNegrita } from '../ticketBase';
import { validEntradaPayload, validSalidaPayload } from './escposBuilder.test';

/** Recorre el buffer y devuelve el byte que sigue a cada `1B 45`. */
function parametrosEscE(buf: Buffer): Array<number | undefined> {
  const out: Array<number | undefined> = [];
  for (let i = 0; i < buf.length - 1; i++) {
    if (buf[i] === 0x1b && buf[i + 1] === 0x45) out.push(buf[i + 2]);
  }
  return out;
}

describe('escposBuilder — negrita ESC E n', () => {
  it('escBoldOn es ESC E 1', () => {
    expect([...escBoldOn()]).toEqual([0x1b, 0x45, 0x01]);
  });

  it('escBoldOff es ESC E 0', () => {
    expect([...escBoldOff()]).toEqual([0x1b, 0x45, 0x00]);
  });

  it('comparte una sola definicion con escNegrita', () => {
    expect(escBoldOn()).toEqual(escNegrita(true));
    expect(escBoldOff()).toEqual(escNegrita(false));
  });

  it.each([
    ['entrada', () => build('entrada', validEntradaPayload())],
    ['salida', () => build('salida', validSalidaPayload())],
  ])('en el tiquete %s cada ESC E va seguido de 00 o 01', (_n, mk) => {
    const params = parametrosEscE(mk());
    expect(params.length).toBeGreaterThan(0);
    for (const p of params) expect([0x00, 0x01]).toContain(p);
  });

  it('en el tiquete nunca aparece ESC F (1B 46)', () => {
    const buf = build('entrada', validEntradaPayload());
    expect(buf.indexOf(Buffer.from([0x1b, 0x46]))).toBe(-1);
  });
});
