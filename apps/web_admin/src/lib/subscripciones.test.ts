import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

import { diasParaVencer, useProximasVencer } from './subscripciones';

const FIXED_TODAY = new Date('2026-06-15T12:00:00Z');

describe('diasParaVencer', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(FIXED_TODAY);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns null for a null date', () => {
    expect(diasParaVencer(null)).toBeNull();
  });

  it('returns null for an undefined date', () => {
    expect(diasParaVencer(undefined)).toBeNull();
  });

  it('returns null for an invalid date string', () => {
    expect(diasParaVencer('not-a-date')).toBeNull();
  });

  it('returns 0 for a date that is exactly today', () => {
    expect(diasParaVencer('2026-06-15')).toBe(0);
  });

  it('returns a positive count for a future date', () => {
    expect(diasParaVencer('2026-06-25')).toBe(10);
  });

  it('returns a negative count for an already-vencida date', () => {
    expect(diasParaVencer('2026-06-05')).toBe(-10);
  });

  it('accepts a Date instance directly', () => {
    expect(diasParaVencer(new Date('2026-06-20T00:00:00Z'))).toBe(5);
  });
});

describe('useProximasVencer', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(FIXED_TODAY);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('excludes items with no fecha_vencimiento', () => {
    const items = [{ id: 'a', fecha_vencimiento: null }];
    const { result } = renderHook(() => useProximasVencer(items));
    expect(result.current).toEqual([]);
  });

  it('excludes already-vencidas items', () => {
    const items = [
      { id: 'vencida', fecha_vencimiento: '2026-06-05' },
      { id: 'vigente', fecha_vencimiento: '2026-06-20' },
    ];
    const { result } = renderHook(() => useProximasVencer(items));
    expect(result.current.map((i) => i.id)).toEqual(['vigente']);
  });

  it('includes an item exactly at the threshold (dias === diasUmbral)', () => {
    const items = [{ id: 'at-threshold', fecha_vencimiento: '2026-07-15' }]; // +30 days
    const { result } = renderHook(() => useProximasVencer(items, 30));
    expect(result.current.map((i) => i.id)).toEqual(['at-threshold']);
  });

  it('excludes an item one day past the threshold', () => {
    const items = [{ id: 'past-threshold', fecha_vencimiento: '2026-07-16' }]; // +31 days
    const { result } = renderHook(() => useProximasVencer(items, 30));
    expect(result.current).toEqual([]);
  });

  it('includes an item vencida exactamente hoy (dias === 0)', () => {
    const items = [{ id: 'today', fecha_vencimiento: '2026-06-15' }];
    const { result } = renderHook(() => useProximasVencer(items));
    expect(result.current.map((i) => i.id)).toEqual(['today']);
  });

  it('sorts ascending by days remaining', () => {
    const items = [
      { id: 'far', fecha_vencimiento: '2026-06-30' },
      { id: 'near', fecha_vencimiento: '2026-06-16' },
      { id: 'mid', fecha_vencimiento: '2026-06-20' },
    ];
    const { result } = renderHook(() => useProximasVencer(items));
    expect(result.current.map((i) => i.id)).toEqual(['near', 'mid', 'far']);
  });

  it('defaults diasUmbral to 30', () => {
    const items = [{ id: 'within-default', fecha_vencimiento: '2026-07-10' }];
    const { result } = renderHook(() => useProximasVencer(items));
    expect(result.current.map((i) => i.id)).toEqual(['within-default']);
  });
});
