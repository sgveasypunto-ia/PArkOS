/**
 * `constants.test.ts` — Strict-TDD unit coverage for the
 * BUSINESS_ALERT_CODES / TECHNICAL_ALERT_CODES whitelist (HU-F11.2,
 * REQ-OPS-182 + DA-F11.2-5).
 *
 * Coverage:
 *   C1: 11 business codes + 8 technical codes (canonical split per
 *       the spec §REQ-OPS-182 + plan.md:2311-2323).
 *   C2: disjoint sets — no overlap (defense against future typos).
 *   C3: O(1) `Set.has` membership — array `.includes()` would be
 *       O(n) and is forbidden per the spec §REQ-OPS-182 scenario.
 *   C4: `isBusinessAlert` rejects null / undefined / unknown codes.
 */
import { describe, it, expect } from 'vitest';

import {
  BUSINESS_ALERT_CODES,
  TECHNICAL_ALERT_CODES,
  isBusinessAlert,
  isTechnicalAlert,
} from '../constants';

describe('constants — REQ-OPS-182 (HU-F11.2)', () => {
  it('C1: 11 business codes + 8 technical codes', () => {
    expect(BUSINESS_ALERT_CODES.size).toBe(11);
    expect(TECHNICAL_ALERT_CODES.size).toBe(8);
  });

  it('C2: business and technical sets are disjoint (no overlap)', () => {
    for (const code of BUSINESS_ALERT_CODES) {
      expect(TECHNICAL_ALERT_CODES.has(code)).toBe(false);
    }
    for (const code of TECHNICAL_ALERT_CODES) {
      expect(BUSINESS_ALERT_CODES.has(code)).toBe(false);
    }
  });

  it('C3: membership is O(1) — Set is used, not array.includes', () => {
    // Defense: an array `.includes()` here would be O(n). The hook
    // calls `Set.has(...)` for every row of every poll cycle, so
    // the implementation MUST keep the constant as a Set.
    expect(BUSINESS_ALERT_CODES instanceof Set).toBe(true);
    expect(TECHNICAL_ALERT_CODES instanceof Set).toBe(true);
  });

  it('C4: isBusinessAlert rejects null / undefined / unknown codes', () => {
    expect(isBusinessAlert(null)).toBe(false);
    expect(isBusinessAlert(undefined)).toBe(false);
    expect(isBusinessAlert('invented_code_xxx')).toBe(false);
    expect(isBusinessAlert('descuadre_critico')).toBe(true);
    expect(isTechnicalAlert('hash_chain_anomaly')).toBe(true);
    expect(isTechnicalAlert('descuadre_critico')).toBe(false);
  });
});
