/**
 * `datetimeTz.test.ts` — regression tests for the shared datetime TZ util.
 *
 * The previous inline helpers in ``CupoForm.tsx`` / ``TarifaForm.tsx``
 * had three independent bugs (see ``datetimeTz.ts`` module docstring).
 * These tests pin the contract: every helper is TZ-safe and the
 * "boundary equality" check agrees with the backend's ``<=`` pre-check
 * at ``empresa.py:1143``.
 *
 * All clock tests are pinned to a fixed instant via
 * ``vi.setSystemTime`` and a forced ``process.env.TZ`` so they pass
 * identically on a UTC host, a Colombia host, or any other TZ.
 */
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  __testHelpers,
  datetimeLocalToIso,
  isoToDatetimeLocal,
  isAtOrBefore,
  localNowAsDatetimeLocal,
  parseApiUtc,
  utcNowPlusMinutesAsIso,
} from './datetimeTz';

const ORIGINAL_TZ = process.env.TZ;

// Pin a non-UTC offset (America/Bogota, UTC-5, no DST) so the
// regression reproduces deterministically regardless of the host's
// own local timezone. Mirror the pattern used by FeTable.test.tsx
// and FacturasTable.test.tsx.
beforeAll(() => {
  process.env.TZ = 'America/Bogota';
});

afterAll(() => {
  process.env.TZ = ORIGINAL_TZ;
});

beforeEach(() => {
  // Anchor the clock to a fixed instant. 2026-10-11T00:30:00Z is
  // 2026-10-10T19:30 local in Bogota.
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-10-11T00:30:00Z'));
});

describe('parseApiUtc', () => {
  it('parses a Z-suffixed ISO as UTC', () => {
    const d = parseApiUtc('2026-10-11T00:30:00Z');
    expect(d).not.toBeNull();
    expect(d?.toISOString()).toBe('2026-10-11T00:30:00.000Z');
  });

  it('parses an offset-suffixed ISO honoring the offset (not converting to local)', () => {
    // 02:30 in a +05:00 offset = 21:30 UTC the previous day.
    const d = parseApiUtc('2026-10-11T02:30:00+05:00');
    expect(d).not.toBeNull();
    expect(d?.toISOString()).toBe('2026-10-10T21:30:00.000Z');
  });

  it('defensively appends Z to a naive ISO (AGENTS.md "Naive-UTC convention")', () => {
    // The bug being fixed: previous code did `new Date("2026-10-11T00:30:00")`
    // which ECMAScript parses as LOCAL. On a Bogota host that lands at
    // 2026-10-11T05:30:00Z, not 00:30:00Z. The util now appends Z so the
    // resulting Date is the real UTC instant.
    const d = parseApiUtc('2026-10-11T00:30:00');
    expect(d).not.toBeNull();
    expect(d?.toISOString()).toBe('2026-10-11T00:30:00.000Z');
  });

  it('returns null for null / undefined / empty / whitespace', () => {
    expect(parseApiUtc(null)).toBeNull();
    expect(parseApiUtc(undefined)).toBeNull();
    expect(parseApiUtc('')).toBeNull();
    expect(parseApiUtc('   ')).toBeNull();
  });

  it('returns null for unparseable strings (callers must check, never throw)', () => {
    expect(parseApiUtc('not a date')).toBeNull();
    expect(parseApiUtc('2026-13-99T99:99:99Z')).toBeNull();
  });
});

describe('isoToDatetimeLocal', () => {
  it('returns an empty string for missing / unparseable input', () => {
    expect(isoToDatetimeLocal(null)).toBe('');
    expect(isoToDatetimeLocal(undefined)).toBe('');
    expect(isoToDatetimeLocal('not a date')).toBe('');
  });

  it('formats a UTC instant in the BROWSER local timezone for the input value', () => {
    // Pin to Bogota: 00:30 UTC -> 19:30 local (the day before in Bogota's
    // wall clock because the host offset is -05:00).
    const local = isoToDatetimeLocal('2026-10-11T00:30:00Z');
    expect(local).toBe('2026-10-10T19:30');
  });

  it('preserves the date when the UTC offset does not cross midnight', () => {
    // 14:00 UTC → 09:00 Bogota same day.
    const local = isoToDatetimeLocal('2026-10-11T14:00:00Z');
    expect(local).toBe('2026-10-11T09:00');
  });

  it('uses hour12: false (regression: en-US hosts would emit "7:30 PM" otherwise)', () => {
    const local = isoToDatetimeLocal('2026-10-11T03:00:00Z');
    // 22:00 Bogota — afternoon, would be "10:00 PM" in en-US.
    expect(local).toBe('2026-10-10T22:00');
    expect(local).not.toMatch(/PM|AM/i);
  });

  it('accepts both naive and Z-suffixed inputs (defensive parse)', () => {
    const naive = isoToDatetimeLocal('2026-10-11T00:30:00');
    const z = isoToDatetimeLocal('2026-10-11T00:30:00Z');
    expect(naive).toBe(z);
  });
});

describe('datetimeLocalToIso', () => {
  it('converts a LOCAL datetime-local string to UTC ISO with the canonical suffix', () => {
    // The form delivers "2026-10-10T19:30" because the operator is in
    // Bogota and the input value is local. The wire format must be
    // 2026-10-11T00:30:00+00:00 (the real UTC instant).
    const iso = datetimeLocalToIso('2026-10-10T19:30');
    expect(iso).toBe('2026-10-11T00:30:00+00:00');
  });

  it('round-trips with isoToDatetimeLocal under the same TZ', () => {
    const original = '2026-10-11T00:30:00Z';
    const local = isoToDatetimeLocal(original);
    const back = datetimeLocalToIso(local);
    expect(back).toBe('2026-10-11T00:30:00+00:00');
  });

  it('regression: previous code emitted LOCAL components with +00:00 (off by N hours)', () => {
    // OLD `datetimeLocalToIso` returned "2026-10-10T19:30:00+00:00" for
    // an input of "2026-10-10T19:30" in Bogota, which is 5h behind
    // the real UTC instant. The new code must return the real UTC
    // instant ("2026-10-11T00:30:00+00:00").
    const iso = datetimeLocalToIso('2026-10-10T19:30');
    expect(iso).not.toBe('2026-10-10T19:30:00+00:00');
    expect(iso).toBe('2026-10-11T00:30:00+00:00');
  });

  it('returns the empty string for empty / invalid input', () => {
    expect(datetimeLocalToIso('')).toBe('');
    expect(datetimeLocalToIso('not a date')).toBe('');
  });
});

describe('localNowAsDatetimeLocal', () => {
  it('returns the BROWSER local clock (Bogota: 19:30 for 00:30 UTC)', () => {
    expect(localNowAsDatetimeLocal()).toBe('2026-10-10T19:30');
  });
});

describe('utcNowPlusMinutesAsIso', () => {
  it('regression: previous code labeled LOCAL components as UTC, off by N hours', () => {
    // OLD `localNowPlusMinutesAsIso(0)` returned "2026-10-10T19:30:00+00:00"
    // for a Bogota host at 00:30 UTC, which is 5h BEHIND the real
    // instant. The new util returns the real UTC instant.
    const iso = utcNowPlusMinutesAsIso(0);
    expect(iso).toBe('2026-10-11T00:30:00+00:00');
  });

  it('returns the real UTC instant shifted by N minutes', () => {
    expect(utcNowPlusMinutesAsIso(1)).toBe('2026-10-11T00:31:00+00:00');
    expect(utcNowPlusMinutesAsIso(60)).toBe('2026-10-11T01:30:00+00:00');
    expect(utcNowPlusMinutesAsIso(-1)).toBe('2026-10-11T00:29:00+00:00');
  });

  it('emits the canonical +00:00 suffix regardless of host TZ', () => {
    // Pin the host to Asia/Tokyo and re-import the module to pick up
    // the new env. (Module-level TZ caching is the only place
    // getBrowserTimeZone() could give a stale value, and we don't
    // depend on it here — this util always formats in UTC.)
    const originalTz = process.env.TZ;
    process.env.TZ = 'Asia/Tokyo';
    try {
      expect(utcNowPlusMinutesAsIso(0)).toBe('2026-10-11T00:30:00+00:00');
    } finally {
      process.env.TZ = originalTz;
    }
  });
});

describe('isAtOrBefore', () => {
  it('agrees with the backend `<=` pre-check at empresa.py:1143', () => {
    // Regression for the operator-reported bug: the form's
    // `vigente_desde` exactly equal to the row's `vigente_desde`
    // MUST be flagged as a boundary edit (so the form can disable
    // submit) AND the backend will return 409 cantidad_overlap.
    const row = '2026-10-11T00:30:00Z';
    const same = '2026-10-11T00:30:00Z';
    const before = '2026-10-11T00:29:00Z';
    const after = '2026-10-11T00:31:00Z';
    expect(isAtOrBefore(same, row)).toBe(true);
    expect(isAtOrBefore(before, row)).toBe(true);
    expect(isAtOrBefore(after, row)).toBe(false);
  });

  it('handles naive and Z-suffixed inputs the same way (defensive parse)', () => {
    const rowZ = '2026-10-11T00:30:00Z';
    const sameNaive = '2026-10-11T00:30:00';
    expect(isAtOrBefore(sameNaive, rowZ)).toBe(true);
  });

  it('returns true (permissive) when either input is unparseable', () => {
    // Defensive default: better to let the backend reject with a
    // clean 409 than to mask a malformed payload with a false
    // negative on the front.
    expect(isAtOrBefore(null, '2026-10-11T00:30:00Z')).toBe(true);
    expect(isAtOrBefore('not a date', '2026-10-11T00:30:00Z')).toBe(true);
  });
});

describe('__testHelpers.getBrowserTimeZone', () => {
  it('returns the forced TZ (Bogota) under test', () => {
    expect(__testHelpers.getBrowserTimeZone()).toBe('America/Bogota');
  });
});
