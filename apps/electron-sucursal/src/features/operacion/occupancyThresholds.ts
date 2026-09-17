/**
 * Occupancy threshold map (HU-F4.3 — DEC-SUC-11 + KD-6).
 *
 * Single source of truth for the per-chip color decision. Pure module —
 * no DOM, no I/O, no React — so the unit test does not need a renderer.
 *
 * Range contract (verbatim `specs/operacion/spec.md` §"Per-Tipo Render"):
 *
 * | Range                                         | Color  |
 * |-----------------------------------------------|--------|
 * | `0 <= p < THRESHOLD_YELLOW (0.7)`             | green  |
 * | `THRESHOLD_YELLOW (0.7) <= p <= THRESHOLD_RED (0.9)` | yellow |
 * | `p > THRESHOLD_RED (0.9)`                     | red    |
 *
 * KD-6 valid negative: when `cupo_maximo === 0` (admin has not configured
 * capacity for a tipo), the resulting percentage is `Infinity` (or NaN if
 * `activos` is also 0). The client maps both to `red` so the operator sees
 * the "cupo no configurado" tooltip on that chip — the chip text reads
 * `Auto: 3/0` and the color is `red` because the tipo cannot accept more
 * vehicles until the admin configures capacity.
 */

/** Lower bound of the yellow band. `p >= THRESHOLD_YELLOW` → yellow. */
export const THRESHOLD_YELLOW = 0.7;

/** Upper bound of the yellow band. `p > THRESHOLD_RED` → red. */
export const THRESHOLD_RED = 0.9;

/**
 * Maps a percentage `activos / cupo_maximo` to a chip color.
 *
 * @param p - occupancy ratio, e.g. `0.46` for "23 / 50".
 * @returns `'green' | 'yellow' | 'red'`. Negative and `NaN` map to `red`
 *          so the chip surfaces "cupo no configurado" (KD-6 invariant).
 *
 * Boundary cases (covered by `occupancyThresholds.test.ts`):
 *   - `p === 0`           → green (no occupancy, full capacity)
 *   - `p === 0.69`        → green (just below threshold)
 *   - `p === 0.7`         → yellow (inclusive lower bound)
 *   - `p === 0.85`        → yellow (mid-band)
 *   - `p === 0.9`         → yellow (inclusive upper bound)
 *   - `p === 0.91`        → red (just above threshold)
 *   - `p === 1.5`         → red (overflow, also KD-6 surface)
 *   - `p === NaN`/`Infinity` → red (cupo no configurado — KD-6)
 */
export function classForPorcentaje(p: number): 'green' | 'yellow' | 'red' {
  if (!Number.isFinite(p) || p < 0) return 'red';
  if (p < THRESHOLD_YELLOW) return 'green';
  if (p <= THRESHOLD_RED) return 'yellow';
  return 'red';
}