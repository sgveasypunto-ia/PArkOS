/**
 * Unit tests for `matchVehiculos` (HU-F7.1, T5 — búsqueda sin placa).
 *
 * Coverage:
 *   M1: prefix match on normalized placa (reuses `normalizarPlaca` —
 *       tolerant of lowercase / stray whitespace in the typed query).
 *   M2: substring match (case-insensitive) on `consecutivo`.
 *   M3: items with neither a placa-prefix nor a consecutivo-substring
 *       match are excluded.
 *   M4: empty / whitespace-only query → no candidates.
 *   M5: result is capped at the `limit` param (default 6).
 *   M6: placa matches are ranked before consecutivo matches.
 *   M7: items with `placa: null` are never matched on placa; items with
 *       `consecutivo: null` are never matched on consecutivo.
 *   M8: pure function — same input twice → same output (no mutation).
 *
 * Also covers the two small pure helpers colocated here (not in
 * `VehiculoSuggestions.tsx` — a plain export there trips
 * `react-refresh/only-export-components`):
 *   V7: `getNextSuggestionIndex` — arrow-key wraparound math.
 *   V6: `vehiculoSuggestionOptionId` — deterministic option id format.
 */
import { describe, it, expect } from 'vitest';

import {
  matchVehiculos,
  MAX_VEHICULO_CANDIDATOS,
  vehiculoSuggestionOptionId,
  getNextSuggestionIndex,
} from './vehiculoMatch';
import type { IngresoActivo } from '../hooks/useIngresosActivos';

function makeIngreso(overrides: Partial<IngresoActivo> & { uuid: string }): IngresoActivo {
  return {
    placa: null,
    fecha_ingreso: '2026-09-19T10:00:00Z',
    consecutivo: null,
    created_at: '2026-09-19T10:00:00Z',
    uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
    uuid_sucursal: '00000000-0000-0000-0000-000000000def',
    ...overrides,
  };
}

const ABC123 = makeIngreso({ uuid: 'uuid-abc123', placa: 'ABC123' });
const ABC999 = makeIngreso({ uuid: 'uuid-abc999', placa: 'ABC999' });
const XYZ777 = makeIngreso({ uuid: 'uuid-xyz777', placa: 'XYZ777' });
const PATINETA_3 = makeIngreso({
  uuid: 'uuid-patineta-3',
  consecutivo: 'PATINETA-000003-34a24bae',
});
const BICICLETA_1 = makeIngreso({
  uuid: 'uuid-bicicleta-1',
  consecutivo: 'BICICLETA-000001-9c0e21aa',
});

describe('matchVehiculos — HU-F7.1 ranked matching', () => {
  it('M1: prefix match on normalized placa (tolerant of case/whitespace)', () => {
    const result = matchVehiculos([ABC123, XYZ777], '  abc1  ');
    expect(result).toEqual([{ ingreso: ABC123, matchedOn: 'placa' }]);
  });

  it('M2: substring match (case-insensitive) on consecutivo', () => {
    const result = matchVehiculos([PATINETA_3, BICICLETA_1], 'patin');
    expect(result).toEqual([{ ingreso: PATINETA_3, matchedOn: 'consecutivo' }]);
  });

  it('M2b: substring match on consecutivo matches the middle of the string, not just a prefix', () => {
    const result = matchVehiculos([PATINETA_3], '000003');
    expect(result).toEqual([{ ingreso: PATINETA_3, matchedOn: 'consecutivo' }]);
  });

  it('M3: no match → excluded from result', () => {
    const result = matchVehiculos([ABC123, PATINETA_3], 'ZZZ');
    expect(result).toEqual([]);
  });

  it('M4: empty / whitespace-only query → no candidates', () => {
    expect(matchVehiculos([ABC123, PATINETA_3], '')).toEqual([]);
    expect(matchVehiculos([ABC123, PATINETA_3], '   ')).toEqual([]);
  });

  it('M5: result capped at limit (default MAX_VEHICULO_CANDIDATOS = 6)', () => {
    const many: IngresoActivo[] = Array.from({ length: 10 }, (_, i) =>
      makeIngreso({ uuid: `uuid-abc${i}`, placa: `ABC00${i}` }),
    );
    const result = matchVehiculos(many, 'ABC');
    expect(MAX_VEHICULO_CANDIDATOS).toBe(6);
    expect(result).toHaveLength(6);
  });

  it('M5b: explicit limit overrides the default', () => {
    const many: IngresoActivo[] = Array.from({ length: 10 }, (_, i) =>
      makeIngreso({ uuid: `uuid-abc${i}`, placa: `ABC00${i}` }),
    );
    const result = matchVehiculos(many, 'ABC', 2);
    expect(result).toHaveLength(2);
  });

  it('M6: placa matches rank before consecutivo matches', () => {
    // Neither field naturally overlaps here (placa vs consecutivo query
    // strings), so build a query that matches BOTH kinds explicitly and
    // assert relative ordering.
    const ambiguousConsecutivo = makeIngreso({
      uuid: 'uuid-amb',
      consecutivo: 'BICICLETA-ABC123-9c0e21aa',
    });
    const result = matchVehiculos([ambiguousConsecutivo, ABC123], 'ABC123');
    expect(result).toEqual([
      { ingreso: ABC123, matchedOn: 'placa' },
      { ingreso: ambiguousConsecutivo, matchedOn: 'consecutivo' },
    ]);
  });

  it('M7a: items with placa=null are never matched via the placa branch', () => {
    const result = matchVehiculos([PATINETA_3], 'PATINETA-000003-34a24bae');
    expect(result).toEqual([{ ingreso: PATINETA_3, matchedOn: 'consecutivo' }]);
  });

  it('M7b: items with consecutivo=null are never matched via the consecutivo branch', () => {
    // Query shaped like a consecutivo substring but the item only has a placa.
    const result = matchVehiculos([ABC999], '000003');
    expect(result).toEqual([]);
  });

  it('M8: pure function — repeated calls with the same input return equal (non-mutated) output', () => {
    const input = [ABC123, PATINETA_3];
    const r1 = matchVehiculos(input, 'ABC');
    const r2 = matchVehiculos(input, 'ABC');
    expect(r1).toEqual(r2);
    expect(input).toEqual([ABC123, PATINETA_3]);
  });
});

describe('vehiculoSuggestionOptionId — deterministic option id', () => {
  it('V6: formats as `${listboxId}-option-${index}`', () => {
    expect(vehiculoSuggestionOptionId('lb-1', 0)).toBe('lb-1-option-0');
    expect(vehiculoSuggestionOptionId('salida-placa-suggestions', 3)).toBe(
      'salida-placa-suggestions-option-3',
    );
  });
});

describe('getNextSuggestionIndex — arrow-key navigation math (pure)', () => {
  it('V7a: length=0 → always -1', () => {
    expect(getNextSuggestionIndex(-1, 'down', 0)).toBe(-1);
    expect(getNextSuggestionIndex(0, 'up', 0)).toBe(-1);
  });

  it('V7b: down from -1 (nothing highlighted) → 0', () => {
    expect(getNextSuggestionIndex(-1, 'down', 3)).toBe(0);
  });

  it('V7c: down wraps from the last index to 0', () => {
    expect(getNextSuggestionIndex(2, 'down', 3)).toBe(0);
  });

  it('V7d: up wraps from 0 (or -1) to the last index', () => {
    expect(getNextSuggestionIndex(0, 'up', 3)).toBe(2);
    expect(getNextSuggestionIndex(-1, 'up', 3)).toBe(2);
  });

  it('V7e: up/down within bounds move by one', () => {
    expect(getNextSuggestionIndex(1, 'down', 3)).toBe(2);
    expect(getNextSuggestionIndex(1, 'up', 3)).toBe(0);
  });
});
