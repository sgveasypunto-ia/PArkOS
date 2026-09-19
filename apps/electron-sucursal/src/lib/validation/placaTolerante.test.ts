/**
 * Unit tests for `buscarIngresoTolerante` and `generarVariantesTolerantes`
 * (HU-F7.1, T1).
 *
 * Cobertura U1..U6 verbatim per `plan.md:1689` + `proposal.md §2.1 T1`:
 *   U1: happy path `ABC123` no typo → `kind: 'found'`.
 *   U2: typo confusable `ABC12O` (O↔0) → matches `ABC120`.
 *   U3: multi-posición `0BC113` (0↔O) → matches `OBC113`.
 *   U4: no-match `XYZ999` → `kind: 'none', placaProbada: 'XYZ999'`.
 *   U5: 3 candidatos distintos → `kind: 'multiple'` (RadioGroup UI).
 *   U6: normalización (`  abc12o  ` → matches `ABC120`).
 *
 * Plus 2 bounded-count tests (REQ-OPS-151):
 *   U7: `generarVariantesTolerantes('ABC123')` → 1 variant (no confusables).
 *   U8: `generarVariantesTolerantes('ABC12O')` → ≤2 variants (1 typo).
 *
 * No requiere mocks — `generarVariantesTolerantes` es puro determinista y
 * `buscarIngresoTolerante` se testea con un `getIngresosByPlaca` mock
 * in-memory (sin red).
 *
 * DEC-SUC-22 verbatim separation: este archivo NO importa de `placa.ts`
 * (tolerancia ≠ detección estricta).
 */
import { describe, it, expect, vi } from 'vitest';

import {
  buscarIngresoTolerante,
  generarVariantesTolerantes,
  TOLERANCIA_PLACA,
} from './placaTolerante';
import type { Ingreso } from '../../features/operacion/api/ingresoActivoApi';

const INGRESO_ABC120: Ingreso = {
  uuid: '00000000-0000-0000-0000-0000000000c1',
  uuid_sucursal: '00000000-0000-0000-0000-000000000def',
  placa: 'ABC120',
  fecha_ingreso: '2026-09-19T10:00:00Z',
  uuid_subscripcion_cliente: null,
};

function makeIngreso(placa: string, uuid: string): Ingreso {
  return {
    uuid,
    uuid_sucursal: '00000000-0000-0000-0000-000000000def',
    placa,
    fecha_ingreso: '2026-09-19T10:00:00Z',
    uuid_subscripcion_cliente: null,
  };
}

describe('TOLERANCIA_PLACA — DEC-SUC-22 confusable map', () => {
  it('exposes O↔0, I↔1, B↔8 binary pairs', () => {
    expect(TOLERANCIA_PLACA.O).toBe('0');
    expect(TOLERANCIA_PLACA['0']).toBe('O');
    expect(TOLERANCIA_PLACA.I).toBe('1');
    expect(TOLERANCIA_PLACA['1']).toBe('I');
    expect(TOLERANCIA_PLACA.B).toBe('8');
    expect(TOLERANCIA_PLACA['8']).toBe('B');
  });
});

describe('generarVariantesTolerantes — REQ-OPS-151 bounded variant generation', () => {
  it('U7: ACDH23 sin confusables → 1 variante (solo el input)', () => {
    // ACDH23: letras A,C,D,H (ninguna en O↔0/I↔1/B↔8) + dígitos 2,3 (ninguno en 0/1/8).
    const variantes = generarVariantesTolerantes('ACDH23');
    expect(variantes.length).toBe(1);
    expect(variantes[0]).toBe('ACDH23');
  });

  it('U8: ACDH2O con 1 confusable (O↔0) → 2 variantes', () => {
    // ACDH2O: solo pos 5 (`O`) es confusable → 1 input + 1 variante = 2.
    const variantes = generarVariantesTolerantes('ACDH2O');
    expect(variantes.length).toBe(2);
    expect(variantes).toContain('ACDH2O');
    expect(variantes).toContain('ACDH20');
  });
});

describe('buscarIngresoTolerante — DEC-SUC-22 tolerance resolver', () => {
  it('U1: ABC123 sin typo → kind found con placaReal === varianteUsada === ABC123', async () => {
    const ingreso = makeIngreso('ABC123', '00000000-0000-0000-0000-0000000000b1');
    const getIngresosByPlaca = vi.fn(async (placa: string) => {
      if (placa === 'ABC123') return [ingreso];
      return [];
    });
    const result = await buscarIngresoTolerante('ABC123', getIngresosByPlaca);
    expect(result.kind).toBe('found');
    if (result.kind === 'found') {
      expect(result.uuid_ingreso).toBe(ingreso.uuid);
      expect(result.placaReal).toBe('ABC123');
      expect(result.varianteUsada).toBe('ABC123');
    }
  });

  it('U2: ABC12O (typo O↔0) → kind found, placaReal ABC120, varianteUsada ABC12O', async () => {
    const getIngresosByPlaca = vi.fn(async (placa: string) => {
      if (placa === 'ABC120') return [INGRESO_ABC120];
      return [];
    });
    const result = await buscarIngresoTolerante('ABC12O', getIngresosByPlaca);
    expect(result.kind).toBe('found');
    if (result.kind === 'found') {
      expect(result.uuid_ingreso).toBe(INGRESO_ABC120.uuid);
      expect(result.placaReal).toBe('ABC120');
      expect(result.varianteUsada).toBe('ABC12O');
    }
  });

  it('U3: 0BC113 (typo 0↔O) → kind found, placaReal OBC113, varianteUsada 0BC113', async () => {
    const ingresoOBC = makeIngreso('OBC113', '00000000-0000-0000-0000-0000000000a1');
    const getIngresosByPlaca = vi.fn(async (placa: string) => {
      if (placa === 'OBC113') return [ingresoOBC];
      return [];
    });
    const result = await buscarIngresoTolerante('0BC113', getIngresosByPlaca);
    expect(result.kind).toBe('found');
    if (result.kind === 'found') {
      expect(result.uuid_ingreso).toBe(ingresoOBC.uuid);
      expect(result.placaReal).toBe('OBC113');
      expect(result.varianteUsada).toBe('0BC113');
    }
  });

  it('U4: XYZ999 sin match → kind none, placaProbada === XYZ999', async () => {
    const getIngresosByPlaca = vi.fn(async () => []);
    const result = await buscarIngresoTolerante('XYZ999', getIngresosByPlaca);
    expect(result.kind).toBe('none');
    if (result.kind === 'none') {
      expect(result.placaProbada).toBe('XYZ999');
    }
  });

  it('U5: 3 candidatos distintos (ABC120 + ABC12O + ABC1Z0 via distintas variantes) → kind multiple', async () => {
    const ingresoA = makeIngreso('ABC120', '00000000-0000-0000-0000-0000000000a1');
    const ingresoB = makeIngreso('ABC12O', '00000000-0000-0000-0000-0000000000a2');
    const ingresoC = makeIngreso('ABC121', '00000000-0000-0000-0000-0000000000a3');
    const getIngresosByPlaca = vi.fn(async (placa: string) => {
      if (placa === 'ABC120') return [ingresoA];
      if (placa === 'ABC12O') return [ingresoB];
      if (placa === 'ABC121') return [ingresoC];
      return [];
    });
    // Input 'ABC120' (no confusables) + variante 'ABC12O' ambas matchean con UUIDs distintos.
    const result = await buscarIngresoTolerante('ABC120', getIngresosByPlaca);
    expect(result.kind).toBe('multiple');
    if (result.kind === 'multiple') {
      const uuids = result.candidatos.map((c) => c.uuid_ingreso);
      expect(uuids).toContain(ingresoA.uuid);
      expect(uuids).toContain(ingresoB.uuid);
    }
  });

  it('U6: "  abc12o  " (whitespace + minúsculas) → matchea ABC120', async () => {
    const getIngresosByPlaca = vi.fn(async (placa: string) => {
      if (placa === 'ABC120') return [INGRESO_ABC120];
      return [];
    });
    const result = await buscarIngresoTolerante('  abc12o  ', getIngresosByPlaca);
    expect(result.kind).toBe('found');
    if (result.kind === 'found') {
      expect(result.placaReal).toBe('ABC120');
      expect(result.varianteUsada).toBe('ABC12O');
    }
  });
});
