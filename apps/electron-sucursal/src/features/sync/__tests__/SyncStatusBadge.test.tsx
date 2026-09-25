/**
 * `SyncStatusBadge.test.tsx` — Strict-TDD RED scaffold for HU-F11.1
 * (REQ-OPS-171, AD-3/AD-4/AD-5 realineados: el indicador de sync ya
 * NO es un banner de arriba de la página — vive en el badge
 * `dashboard-online` del navbar, con el detalle en un tooltip Radix).
 *
 * Reemplaza `SyncBanner.test.tsx` (componente eliminado, sin más
 * consumidores tras este cambio). Coverage adaptada (verbatim origen
 * `SyncBanner.test.tsx` S1-S5) + dos casos nuevos propios del badge:
 *
 *   S0: sin `data` todavía (pre-fetch) → badge neutro (zinc), SIN
 *       anunciador sr-only montado (nada que anunciar todavía).
 *   S1: verde (`lag_seg<=60`, `pendientes<=5`) → clases emerald.
 *   S2/S2b: ámbar (`60 < lag_seg <= 3600` O `pendientes > 5`).
 *   S3: rojo (`lag_seg > 3600` O `pendientes > 100`).
 *   S4: `never_synced` (`lag_seg === null`) → NEUTRAL (zinc), no rojo.
 *   S5: el anunciador sr-only (`role="status"` + `aria-live="polite"`)
 *       solo cambia en transición de estado, con debounce de 2 s
 *       (verbatim patrón F2.3 `StatusBar.tsx:90-100`).
 *   S6: el tooltip (Radix, abierto al hover) muestra el label
 *       completo del estado + `lag_seg`/`pendientes` cuando
 *       `lag_seg !== null`.
 *
 * RED hasta que `SyncStatusBadge.tsx` exista en
 * `apps/electron-sucursal/src/features/sync/components/`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, act, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const useSyncEstadoMock = vi.fn();

vi.mock('../hooks/useSyncEstado', () => ({
  useSyncEstado: (...args: unknown[]) => useSyncEstadoMock(...args),
}));

// Import after mocks so the mocked modules are wired.
import { SyncStatusBadge } from '../components/SyncStatusBadge';
import type { SyncEstado } from '../hooks/useSyncEstado';

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
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('<SyncStatusBadge /> — REQ-OPS-171 (HU-F11.1, indicador en navbar)', () => {
  it('S0: sin data todavia (pre-fetch) -> badge neutro, sin anunciador montado', () => {
    useSyncEstadoMock.mockReturnValue({ data: undefined, error: undefined });

    render(<SyncStatusBadge uuid_sucursal={BRANCH_UUID} />);

    const badge = screen.getByTestId('dashboard-online');
    expect(badge.getAttribute('data-state')).toBe('loading');
    expect(badge.className).not.toContain('bg-emerald');
    expect(screen.queryByTestId('sync-badge-announcer')).not.toBeInTheDocument();
  });

  it('S1: verde para sync al dia (lag_seg<=60, pendientes<=5)', () => {
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 30, pendientes: 0 }),
      error: undefined,
    });

    render(<SyncStatusBadge uuid_sucursal={BRANCH_UUID} />);

    const badge = screen.getByTestId('dashboard-online');
    expect(badge.getAttribute('data-state')).toBe('online');
    expect(badge.className).toContain('bg-success');
  });

  it('S2: amarillo cuando 60 < lag_seg <= 3600', () => {
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 600, pendientes: 0 }),
      error: undefined,
    });

    render(<SyncStatusBadge uuid_sucursal={BRANCH_UUID} />);

    const badge = screen.getByTestId('dashboard-online');
    expect(badge.getAttribute('data-state')).toBe('lagging');
    expect(badge.className).toContain('bg-warning');
  });

  it('S2b: amarillo tambien con pendientes > 5 (lag_seg dentro de la ventana)', () => {
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 30, pendientes: 12 }),
      error: undefined,
    });

    render(<SyncStatusBadge uuid_sucursal={BRANCH_UUID} />);

    expect(screen.getByTestId('dashboard-online').getAttribute('data-state')).toBe('lagging');
  });

  it('S3: rojo cuando lag_seg > 3600 o pendientes > 100', () => {
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 7200, pendientes: 0 }),
      error: undefined,
    });

    render(<SyncStatusBadge uuid_sucursal={BRANCH_UUID} />);

    const badge = screen.getByTestId('dashboard-online');
    expect(badge.getAttribute('data-state')).toBe('offline');
    expect(badge.className).toContain('bg-destructive');
  });

  it('S4: never_synced (lag_seg === null) es NEUTRAL, no rojo', () => {
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ ultima_sync_at: null, lag_seg: null, pendientes: 0 }),
      error: undefined,
    });

    render(<SyncStatusBadge uuid_sucursal={BRANCH_UUID} />);

    const badge = screen.getByTestId('dashboard-online');
    expect(badge.getAttribute('data-state')).toBe('never_synced');
    expect(badge.className).not.toContain('bg-destructive');
    expect(badge.className).toMatch(/bg-muted\b/);
  });

  it('S5: el anunciador sr-only cambia SOLO en transicion de estado (debounce 2s)', () => {
    vi.useFakeTimers();
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 30, pendientes: 0 }),
      error: undefined,
    });
    const { rerender } = render(<SyncStatusBadge uuid_sucursal={BRANCH_UUID} />);
    let announcer = screen.getByTestId('sync-badge-announcer');
    expect(announcer.getAttribute('data-announced-state')).toBe('online');

    // Same state (online -> online, distinto lag): no re-anuncia.
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 45, pendientes: 0 }),
      error: undefined,
    });
    rerender(<SyncStatusBadge uuid_sucursal={BRANCH_UUID} />);
    announcer = screen.getByTestId('sync-badge-announcer');
    expect(announcer.getAttribute('data-announced-state')).toBe('online');

    // Pasado el debounce de 2s, la transicion online -> lagging SI se anuncia.
    act(() => {
      vi.advanceTimersByTime(2_500);
    });
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 600, pendientes: 0 }),
      error: undefined,
    });
    rerender(<SyncStatusBadge uuid_sucursal={BRANCH_UUID} />);
    announcer = screen.getByTestId('sync-badge-announcer');
    expect(announcer.getAttribute('data-announced-state')).toBe('lagging');
    expect(announcer.getAttribute('role')).toBe('status');
    expect(announcer.getAttribute('aria-live')).toBe('polite');
    expect(announcer.className).toContain('sr-only');

    // Dentro del debounce: otra transicion se difiere.
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 7200, pendientes: 0 }),
      error: undefined,
    });
    rerender(<SyncStatusBadge uuid_sucursal={BRANCH_UUID} />);
    announcer = screen.getByTestId('sync-badge-announcer');
    expect(screen.getByTestId('dashboard-online').getAttribute('data-state')).toBe('offline');
    expect(announcer.getAttribute('data-announced-state')).toBe('lagging');
  });

  it('S6: el tooltip muestra el label del estado + lag_seg/pendientes al enfocar el badge', () => {
    // Radix abre el tooltip INSTANTANEAMENTE en `onFocus` (sin el delay
    // de `delayDuration`, reservado al hover con mouse) — foco es la
    // via determinista y rapida de abrirlo en test, sin timers reales.
    useSyncEstadoMock.mockReturnValue({
      data: makeEstado({ lag_seg: 600, pendientes: 3 }),
      error: undefined,
    });

    render(<SyncStatusBadge uuid_sucursal={BRANCH_UUID} />);
    act(() => {
      fireEvent.focus(screen.getByTestId('dashboard-online'));
    });

    const tooltip = screen.getByRole('tooltip');
    expect(tooltip.textContent).toContain('syncBanner.lagging');
    expect(tooltip.textContent).toContain('600s');
    expect(tooltip.textContent).toContain('3');
  });
});
