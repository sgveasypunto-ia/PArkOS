/**
 * Unit tests for `classForPorcentaje()` (HU-F4.3).
 *
 * Verbatim spec §"Per-Tipo Render with Color Threshold Map":
 *   - `0 <= p < 0.7` → green
 *   - `0.7 <= p <= 0.9` → yellow
 *   - `p > 0.9` → red
 * Plus KD-6 cases (`Infinity`, `NaN`) which also map to `red` so the
 * "cupo no configurado" tooltip is the correct chip surface.
 */
import { describe, it, expect } from 'vitest';

import { classForPorcentaje, THRESHOLD_RED, THRESHOLD_YELLOW } from './occupancyThresholds';

describe('classForPorcentaje', () => {
  it('p === 0 → green (empty branch)', () => {
    expect(classForPorcentaje(0)).toBe('green');
  });

  it('p === 0.5 → green (mid-low band)', () => {
    expect(classForPorcentaje(0.5)).toBe('green');
  });

  it('p === 0.69 → green (just below the lower bound)', () => {
    expect(classForPorcentaje(0.69)).toBe('green');
  });

  it('p === THRESHOLD_YELLOW (0.7) → yellow (inclusive lower bound)', () => {
    expect(THRESHOLD_YELLOW).toBe(0.7);
    expect(classForPorcentaje(0.7)).toBe('yellow');
  });

  it('p === 0.85 → yellow (mid-band)', () => {
    expect(classForPorcentaje(0.85)).toBe('yellow');
  });

  it('p === THRESHOLD_RED (0.9) → yellow (inclusive upper bound)', () => {
    expect(THRESHOLD_RED).toBe(0.9);
    expect(classForPorcentaje(0.9)).toBe('yellow');
  });

  it('p === 0.91 → red (just above the upper bound)', () => {
    expect(classForPorcentaje(0.91)).toBe('red');
  });

  it('p === 1.5 → red (overflow)', () => {
    expect(classForPorcentaje(1.5)).toBe('red');
  });

  it('KD-6: cupo_maximo === 0 → activos / 0 = Infinity → red (cupo no configurado)', () => {
    // `3 / 0` produces `Infinity` in JavaScript; the chip must surface red
    // so the operator sees "cupo no configurado".
    expect(classForPorcentaje(3 / 0)).toBe('red');
  });

  it('KD-6: NaN → red (defensive against unexpected payloads)', () => {
    expect(classForPorcentaje(Number.NaN)).toBe('red');
  });

  it('negative p → red (defensive, should not happen in practice)', () => {
    expect(classForPorcentaje(-0.1)).toBe('red');
  });
});