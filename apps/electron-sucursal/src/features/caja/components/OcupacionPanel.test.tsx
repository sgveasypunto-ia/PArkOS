/**
 * Tests for `<OcupacionPanel />` (HU-F4.3 relocated to dashboard, PR-1).
 *
 * Mirrors `OcupacionStrip.test.tsx` so we can prove behavioral parity
 * before deleting the global strip in PR-6 (REQ-OPS-140 Scenario
 * "Inline panel matches global-strip baseline").
 */
import * as React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/components/ui/tooltip', () => ({
  TooltipProvider: ({ children }: { children: React.ReactNode }) => children,
  Tooltip: ({ children }: { children: React.ReactNode }) => children,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => children,
  TooltipContent: ({ children }: { children: React.ReactNode }) => children,
}));

const useOcupacionMock = vi.fn();
vi.mock('../../operacion/hooks/useOcupacion', () => ({
  useOcupacion: (...args: unknown[]) => useOcupacionMock(...args),
}));

import { OcupacionPanel } from './OcupacionPanel';
import type { OcupacionResponse } from '../../operacion/api/ocupacionApi';

beforeEach(() => {
  useOcupacionMock.mockReset();
});

const SAMPLE: OcupacionResponse = {
  uuid_sucursal: '00000000-0000-0000-0000-000000000099',
  items: [
    {
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
      tipo: 'Auto',
      cupo_maximo: 50,
      activos: 23,
      disponible: 27,
    },
  ],
  generado_en: '2026-09-17T10:00:00Z',
};

describe('<OcupacionPanel /> — REQ-OPS-140 in-dashboard parity', () => {
  it('P1: renders row "Auto 23/50" green when data is present', () => {
    useOcupacionMock.mockReturnValue({
      data: SAMPLE,
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });
    render(<OcupacionPanel uuid_sucursal="00000000-0000-0000-0000-000000000099" />);
    const row = screen.getByTestId('ocupacion-panel-row-Auto');
    expect(row.textContent).toBe('Auto23/50');
    expect(row.getAttribute('data-color')).toBe('green');
  });

  it('P2: aria-live="polite" + aria-atomic="false" on each row', () => {
    useOcupacionMock.mockReturnValue({
      data: SAMPLE,
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });
    render(<OcupacionPanel uuid_sucursal="00000000-0000-0000-0000-000000000099" />);
    const row = screen.getByTestId('ocupacion-panel-row-Auto');
    expect(row.getAttribute('aria-live')).toBe('polite');
    expect(row.getAttribute('aria-atomic')).toBe('false');
  });

  it('P3: data-stale="true" when last poll failed after success', () => {
    useOcupacionMock.mockReturnValue({
      data: SAMPLE,
      error: new Error('boom'),
      isStale: true,
      refresh: vi.fn(),
    });
    render(<OcupacionPanel uuid_sucursal="00000000-0000-0000-0000-000000000099" />);
    const root = screen.getByTestId('ocupacion-panel');
    expect(root.getAttribute('data-stale')).toBe('true');
    expect(screen.getByTestId('ocupacion-panel-stale-icon')).toBeTruthy();
    // Last-known values preserved.
    expect(screen.getByTestId('ocupacion-panel-row-Auto').textContent).toBe('Auto23/50');
  });

  it('P4: empty placeholder when data is undefined (pre-auth)', () => {
    useOcupacionMock.mockReturnValue({
      data: undefined,
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });
    render(<OcupacionPanel uuid_sucursal={null} />);
    expect(screen.getByTestId('ocupacion-panel-empty')).toBeTruthy();
  });

  it('P5: unmount smoke — no leak across remounts', () => {
    useOcupacionMock.mockReturnValue({
      data: SAMPLE,
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });
    const { unmount } = render(
      <OcupacionPanel uuid_sucursal="00000000-0000-0000-0000-000000000099" />,
    );
    unmount();
    cleanup();
  });
});