/**
 * `SyncBanner.test.tsx` — Strict-TDD RED scaffold for HU-F11.1
 * (REQ-OPS-171 sync-to-cloud top-of-page banner).
 *
 * Coverage (verbatim tasks.md §C3.1):
 *   S1: green (`lag_seg<=60`, `pendientes<=5`, recent `ultima_sync_at`)
 *       renders the `bg-emerald-500` CVA variant.
 *   S2: yellow (60 < `lag_seg` <= 3600 OR `pendientes > 5`) renders
 *       the `bg-amber-500` variant.
 *   S3: red (`lag_seg > 3600` OR `pendientes > 100`) renders the
 *       `bg-red-500` variant.
 *   S4: never-synced (`lag_seg === null` → never_synced badge) renders
 *       a NEUTRAL badge — NOT red — to avoid alarm fatigue on fresh
 *       installs.
 *   S5: `aria-live` announces only on state transition via the
 *       `lastAnnouncedState` ref + 2 s debounce (verbatim pattern from
 *       F2.3 `StatusBar.tsx:90-100`). The textContent MUST change when
 *       state changes, and MUST NOT re-announce identical state.
 *
 * Mocking strategy (mirrors `OcupacionStrip.test.tsx`):
 *   - `vi.mock('react-i18next')` → returns the key string so tests
 *     assert on literal `syncBanner.*` keys.
 *   - `vi.mock('swr')` → swap useSWR with a controlled stub.
 *   - `vi.mock('../../features/sync/hooks/useSyncEstado')` → swap the
 *     hook with a controlled stub so each scenario can flip `data`.
 *
 * RED until C4 lands `apps/electron-sucursal/src/components/SyncBanner.tsx`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, act } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Capture the SWR config so the banner can be tested deterministically.
const useSyncEstadoMock = vi.fn();

vi.mock('../../features/sync/hooks/useSyncEstado', () => ({
  useSyncEstado: (...args: unknown[]) => useSyncEstadoMock(...args),
}));

// Import after mocks so the mocked modules are wired.
import { SyncBanner } from '../SyncBanner';
import type { SyncEstado } from '../../features/sync/hooks/useSyncEstado';

const RECENT_ISO = '2026-09-21T10:00:00.000Z';
const BRANCH_UUID = '00000000-0000-0000-0000-000000000001';

function makeEstado(overrides: Partial<SyncEstado> = {}): SyncEstado {
  return {
    uuid_sucursal: BRANCH_UUID,
    ultima_sync_at: RECENT_ISO,
    lag_seg: 30,
    pendientes: 0,
    ...overrides,
  };
}

beforeEach(() => {
  useSyncEstadoMock.mockReset();
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('<SyncBanner /> — REQ-OPS-171 (HU-F11.1)', () => {
  it('S1: green variant for in-window sync (lag_seg<=60, pendientes<=5, recent ultima_sync_at)', () => {
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 30, pendientes: 0 }),
      error: undefined,
    });

    render(<SyncBanner uuid_sucursal={BRANCH_UUID} />);

    const banner = screen.getByTestId('sync-banner');
    expect(banner.getAttribute('data-state')).toBe('online');
    expect(banner.className).toContain('bg-emerald-500');
    expect(banner.getAttribute('role')).toBe('status');
    expect(banner.getAttribute('aria-live')).toBe('polite');
  });

  it('S2: yellow variant when 60 < lag_seg <= 3600 OR pendientes > 5', () => {
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 600, pendientes: 0 }),
      error: undefined,
    });

    render(<SyncBanner uuid_sucursal={BRANCH_UUID} />);

    const banner = screen.getByTestId('sync-banner');
    expect(banner.getAttribute('data-state')).toBe('lagging');
    expect(banner.className).toContain('bg-amber-500');
  });

  it('S2b: yellow also triggered by pendientes > 5 alone (lag_seg within window)', () => {
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 30, pendientes: 12 }),
      error: undefined,
    });

    render(<SyncBanner uuid_sucursal={BRANCH_UUID} />);

    const banner = screen.getByTestId('sync-banner');
    expect(banner.getAttribute('data-state')).toBe('lagging');
    expect(banner.className).toContain('bg-amber-500');
  });

  it('S3: red variant when lag_seg > 3600 OR pendientes > 100', () => {
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 7200, pendientes: 0 }),
      error: undefined,
    });

    render(<SyncBanner uuid_sucursal={BRANCH_UUID} />);

    const banner = screen.getByTestId('sync-banner');
    expect(banner.getAttribute('data-state')).toBe('offline');
    expect(banner.className).toContain('bg-red-500');
  });

  it('S4: never_synced badge (lag_seg === null) renders NEUTRAL — NOT red', () => {
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ ultima_sync_at: null, lag_seg: null, pendientes: 0 }),
      error: undefined,
    });

    render(<SyncBanner uuid_sucursal={BRANCH_UUID} />);

    const banner = screen.getByTestId('sync-banner');
    expect(banner.getAttribute('data-state')).toBe('never_synced');
    // Must NOT be red — avoids alarm fatigue on fresh installs.
    expect(banner.className).not.toContain('bg-red-500');
    // Must be a neutral tone (slate/zinc/gray family).
    expect(banner.className).toMatch(/bg-(slate|zinc|gray|neutral)-/);
  });

  it('S5: aria-live announces ONLY on state transition (prev-state-ref + 2s debounce)', () => {
    // First render → online.
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 30, pendientes: 0 }),
      error: undefined,
    });
    const { rerender } = render(<SyncBanner uuid_sucursal={BRANCH_UUID} />);
    const banner = screen.getByTestId('sync-banner');
    expect(banner.getAttribute('data-state')).toBe('online');
    expect(banner.getAttribute('data-announced-state')).toBe('online');

    // Same state (online → online with different numbers): no announce.
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 45, pendientes: 0 }),
      error: undefined,
    });
    rerender(<SyncBanner uuid_sucursal={BRANCH_UUID} />);
    expect(banner.getAttribute('data-state')).toBe('online');
    // The announced state MUST NOT change on identical state (no re-announce spam).
    expect(banner.getAttribute('data-announced-state')).toBe('online');

    // Advance past the 2 s debounce gate. The next transition
    // (online → lagging) MUST be announced.
    act(() => {
      vi.advanceTimersByTime(2_500);
    });
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 600, pendientes: 0 }),
      error: undefined,
    });
    rerender(<SyncBanner uuid_sucursal={BRANCH_UUID} />);
    expect(banner.getAttribute('data-state')).toBe('lagging');
    expect(banner.getAttribute('data-announced-state')).toBe('lagging');

    // Within 2 s debounce: another transition MUST be deferred.
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 7200, pendientes: 0 }),
      error: undefined,
    });
    rerender(<SyncBanner uuid_sucursal={BRANCH_UUID} />);
    expect(banner.getAttribute('data-state')).toBe('offline');
    // The announced state still 'lagging' because the 2s debounce gate
    // has not elapsed.
    expect(banner.getAttribute('data-announced-state')).toBe('lagging');
  });
});
