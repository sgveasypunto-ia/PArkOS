import { describe, expect, it } from 'vitest';
import { hoyBogotaISO } from './fechaInicio';

describe('hoyBogotaISO', () => {
  it('uses the Bogota date late in the evening (UTC is already tomorrow)', () => {
    // 2026-09-30 23:30 Bogota == 2026-10-01T04:30Z
    expect(hoyBogotaISO(new Date('2026-10-01T04:30:00Z'))).toBe('2026-09-30');
  });

  it('flips exactly at 05:00Z (midnight Bogota)', () => {
    expect(hoyBogotaISO(new Date('2026-10-01T04:59:59Z'))).toBe('2026-09-30');
    expect(hoyBogotaISO(new Date('2026-10-01T05:00:00Z'))).toBe('2026-10-01');
  });

  it('handles leap day', () => {
    expect(hoyBogotaISO(new Date('2028-03-01T03:00:00Z'))).toBe('2028-02-29');
  });

  it('defaults to the current date in YYYY-MM-DD form', () => {
    expect(hoyBogotaISO()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
