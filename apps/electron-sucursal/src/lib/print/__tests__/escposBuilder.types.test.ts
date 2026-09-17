/**
 * End-to-end payload → Buffer tests for `escposBuilder.build(...)` (HU-F5.2).
 *
 * One test per tiquete tipo. Each test asserts:
 *   1. The returned `Buffer` starts with `0x1B 0x40` (init).
 *   2. The `Buffer` ends with `0x1D 0x56 0x00 0x0A` (cut + LF).
 *   3. The body contains expected field tokens (placa, money, sello).
 *   4. The sello bytes (`0x1B 0x21 0x30` text 2x) appear where applicable.
 *   5. Specific byte sequences are NOT present when forbidden (e.g.
 *      salida-mensualidad MUST NOT contain `Subtotal:`).
 */
import { describe, it, expect } from 'vitest';

import {
  build,
  escInit,
  cutPartial,
} from '../escposBuilder';
import {
  validEntradaPayload,
  validSalidaPayload,
} from './escposBuilder.test';

// ──────────────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────────────

function startsWith(buf: Buffer, sequence: readonly number[]): boolean {
  if (buf.length < sequence.length) return false;
  for (let i = 0; i < sequence.length; i++) {
    if (buf[i] !== sequence[i]) return false;
  }
  return true;
}

function endsWith(buf: Buffer, sequence: readonly number[]): boolean {
  if (buf.length < sequence.length) return false;
  const offset = buf.length - sequence.length;
  for (let i = 0; i < sequence.length; i++) {
    if (buf[offset + i] !== sequence[i]) return false;
  }
  return true;
}

function contains(buf: Buffer, needle: Buffer): boolean {
  return buf.indexOf(needle) !== -1;
}

// ──────────────────────────────────────────────────────────────────────────
// entrada
// ──────────────────────────────────────────────────────────────────────────

describe('build("entrada", payload)', () => {
  it('emits init + sello bytes + body + cut + LF in order', () => {
    const buf = build('entrada', validEntradaPayload());
    // 1. starts with init
    expect(startsWith(buf, [0x1b, 0x40])).toBe(true);
    // 2. contains sello (text 2x) for "*** ENTRADA ***"
    expect(contains(buf, Buffer.from([0x1b, 0x21, 0x30]))).toBe(true);
    // 3. contains bold on/off
    expect(contains(buf, Buffer.from([0x1b, 0x45]))).toBe(true);
    expect(contains(buf, Buffer.from([0x1b, 0x46]))).toBe(true);
    // 4. body contains placa + folio
    expect(contains(buf, Buffer.from('ABC123'))).toBe(true);
    expect(contains(buf, Buffer.from('00000000-0000-4000-8000-000000000001'))).toBe(true);
    // 5. ends with cut + LF
    expect(endsWith(buf, [0x1d, 0x56, 0x00, 0x0a])).toBe(true);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// salida
// ──────────────────────────────────────────────────────────────────────────

describe('build("salida", payload)', () => {
  it('emits init + sello bytes + money fields + cut + LF', () => {
    const buf = build('salida', validSalidaPayload());
    expect(startsWith(buf, [0x1b, 0x40])).toBe(true);
    expect(contains(buf, Buffer.from([0x1b, 0x21, 0x30]))).toBe(true);
    expect(contains(buf, Buffer.from([0x1b, 0x45]))).toBe(true);
    // Money tokens (formatCOP "$ 10.000", "$ 1.900", "$ 11.900")
    expect(contains(buf, Buffer.from('$'))).toBe(true);
    // "Subtotal:" and "TOTAL:" must appear
    expect(contains(buf, Buffer.from('Subtotal:'))).toBe(true);
    expect(contains(buf, Buffer.from('TOTAL:'))).toBe(true);
    // medioPago token
    expect(contains(buf, Buffer.from('efectivo'))).toBe(true);
    // resolucion
    expect(contains(buf, Buffer.from('RES-1876'))).toBe(true);
    // MUST NOT contain the mensualidad sello
    expect(contains(buf, Buffer.from('PAGO CON MENSUALIDAD'))).toBe(false);
    expect(endsWith(buf, [0x1d, 0x56, 0x00, 0x0a])).toBe(true);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// salida-mensualidad
// ──────────────────────────────────────────────────────────────────────────

describe('build("salida-mensualidad", payload)', () => {
  it('emits 2x-height sello "*** PAGO CON MENSUALIDAD ***" and NO money fields', () => {
    const payload = {
      placa: 'ABC12D',
      fechaEntrada: '2026-09-01T00:00:00Z',
      fechaSalida: '2026-09-16T08:00:00Z',
      qrDataUrl: 'data:image/png;base64,CCC',
      logoDataUrl: 'data:image/png;base64,DDD',
      empresa: {
        nombre: 'PARKINGOS S.A.S.',
        nit: '900123456-7',
        direccion: 'Calle 1 #2-3, Bogota',
        regimen: 'Responsable de IVA',
      },
      operario: 'op-002',
      horarioAtencion: '24 horas',
      polizaRC: 'POL-99999',
      folio: '00000000-0000-4000-8000-000000000007',
      observaciones: 'Mensualidad vigente',
      esMensualidad: true as const,
    };
    const buf = build('salida-mensualidad', payload);
    expect(startsWith(buf, [0x1b, 0x40])).toBe(true);
    // sello text-2x present
    expect(contains(buf, Buffer.from([0x1b, 0x21, 0x30]))).toBe(true);
    // sello text
    expect(contains(buf, Buffer.from('PAGO CON MENSUALIDAD'))).toBe(true);
    // placa token
    expect(contains(buf, Buffer.from('ABC12D'))).toBe(true);
    // NO money fields
    expect(contains(buf, Buffer.from('Subtotal:'))).toBe(false);
    expect(contains(buf, Buffer.from('TOTAL:'))).toBe(false);
    expect(contains(buf, Buffer.from('IVA:'))).toBe(false);
    expect(contains(buf, Buffer.from('Medio de pago:'))).toBe(false);
    expect(endsWith(buf, [0x1d, 0x56, 0x00, 0x0a])).toBe(true);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// reimpresion
// ──────────────────────────────────────────────────────────────────────────

describe('build("reimpresion", payload)', () => {
  it('emits REIMPRESION header + motivo + delegates to entrada body', () => {
    const payload = {
      motivo: 'Tiquete extraviado por cliente',
      qrDataUrl: 'data:image/png;base64,EEE',
      logoDataUrl: 'data:image/png;base64,FFF',
      empresa: {
        nombre: 'PARKINGOS S.A.S.',
        nit: '900123456-7',
        direccion: 'Calle 1 #2-3, Bogota',
        regimen: 'Responsable de IVA',
      },
      folioOriginal: '00000000-0000-4000-8000-000000000099',
      originalTipo: 'entrada' as const,
      payload: validEntradaPayload(),
    };
    const buf = build('reimpresion', payload);
    expect(startsWith(buf, [0x1b, 0x40])).toBe(true);
    expect(contains(buf, Buffer.from('REIMPRESION'))).toBe(true);
    expect(contains(buf, Buffer.from('Tiquete extraviado por cliente'))).toBe(true);
    expect(contains(buf, Buffer.from('00000000-0000-4000-8000-000000000099'))).toBe(true);
    // entrada sello
    expect(contains(buf, Buffer.from('*** ENTRADA ***'))).toBe(true);
    expect(endsWith(buf, [0x1d, 0x56, 0x00, 0x0a])).toBe(true);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// Module-level byte equivalence sanity check
// ──────────────────────────────────────────────────────────────────────────

describe('byte fixture equivalence (sanity)', () => {
  it('escInit() helper equals literal Buffer.from([0x1B, 0x40])', () => {
    expect(escInit()).toEqual(Buffer.from([0x1b, 0x40]));
    expect(cutPartial()).toEqual(Buffer.from([0x1d, 0x56, 0x00]));
  });
});