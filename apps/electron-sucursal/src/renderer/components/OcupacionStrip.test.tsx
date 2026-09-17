/**
 * RTL tests for `<OcupacionStrip />` (HU-F4.3).
 *
 * Coverage (verbatim tasks.md §3.3):
 *   S1: render con 2 chips (Auto 23/50 → green, Moto 1/5 → green).
 *   S2: cambio de color al cruzar threshold (mock retorna Auto 40/50 → yellow).
 *   S3: `data-stale="true"` cuando el último poll falla después de un éxito.
 *   S4: atributos `aria-live="polite"` + `aria-atomic="false"` presentes
 *       en cada chip.
 *
 * Mocking strategy:
 *   - `vi.mock('react-i18next')` → `useTranslation` returns the key string
 *     so tests assert on the literal `operacion.*` strings without
 *     loading the JSON catalog.
 *   - `vi.mock('../features/operacion/hooks/useOcupacion')` → swap the
 *     hook with a tiny controlled stub so each scenario can flip
 *     `data` / `isStale` without spinning up SWR + parkosFetch.
 */
import * as React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Mock the shadcn Tooltip wrappers — Radix Tooltip triggers a React
// duplicate-instance warning under jsdom in this sandbox. The Radix
// integration is verified end-to-end in `e2e/operacion/ocupacion.spec.ts`
// (A1 axe-core + keyboard-accessible via Radix's WAI-ARIA primitives).
// Here we only assert the data → DOM logic: chips, colors, aria-live,
// data-stale, AlertCircle visibility.
vi.mock('@/components/ui/tooltip', () => ({
  TooltipProvider: ({ children }: { children: React.ReactNode }) => children,
  Tooltip: ({ children }: { children: React.ReactNode }) => children,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => children,
  TooltipContent: ({ children }: { children: React.ReactNode }) => children,
}));

const useOcupacionMock = vi.fn();
vi.mock('../../features/operacion/hooks/useOcupacion', () => ({
  useOcupacion: (...args: unknown[]) => useOcupacionMock(...args),
}));

// Import after mocks.
import { OcupacionStrip } from './OcupacionStrip';
import type { OcupacionResponse } from '../../features/operacion/api/ocupacionApi';

beforeEach(() => {
  useOcupacionMock.mockReset();
});

const SAMPLE_OK: OcupacionResponse = {
  uuid_sucursal: '00000000-0000-0000-0000-000000000099',
  items: [
    {
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
      tipo: 'Auto',
      cupo_maximo: 50,
      activos: 23,
      disponible: 27,
    },
    {
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000002',
      tipo: 'Moto',
      cupo_maximo: 5,
      activos: 1,
      disponible: 4,
    },
  ],
  generado_en: '2026-09-16T10:00:00Z',
};

describe('<OcupacionStrip />', () => {
  it('S1: render con 2 chips — Auto 23/50 verde, Moto 1/5 verde', () => {
    useOcupacionMock.mockReturnValue({
      data: SAMPLE_OK,
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });

    render(<OcupacionStrip uuid_sucursal="00000000-0000-0000-0000-000000000099" />);

    const autoChip = screen.getByTestId('ocupacion-chip-Auto');
    const motoChip = screen.getByTestId('ocupacion-chip-Moto');
    expect(autoChip.textContent).toBe('Auto: 23/50');
    expect(autoChip.getAttribute('data-color')).toBe('green');
    expect(motoChip.textContent).toBe('Moto: 1/5');
    expect(motoChip.getAttribute('data-color')).toBe('green');
  });

  it('S1b: renderiza el título desde i18n', () => {
    useOcupacionMock.mockReturnValue({
      data: SAMPLE_OK,
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });
    render(<OcupacionStrip uuid_sucursal="00000000-0000-0000-0000-000000000099" />);
    expect(screen.getByTestId('ocupacion-strip-title').textContent).toContain(
      'ocupacion_titulo',
    );
  });

  it('S2: cambio de color al cruzar threshold (Auto 40/50 → yellow)', () => {
    useOcupacionMock.mockReturnValue({
      data: {
        uuid_sucursal: '00000000-0000-0000-0000-000000000099',
        items: [
          {
            uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
            tipo: 'Auto',
            cupo_maximo: 50,
            activos: 40,
            disponible: 10,
          },
        ],
        generado_en: '2026-09-16T10:00:00Z',
      },
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });

    render(<OcupacionStrip uuid_sucursal="00000000-0000-0000-0000-000000000099" />);
    const autoChip = screen.getByTestId('ocupacion-chip-Auto');
    expect(autoChip.textContent).toBe('Auto: 40/50');
    expect(autoChip.getAttribute('data-color')).toBe('yellow');
  });

  it('S2b: cupo_maximo === 0 (KD-6) → chip red con text "Auto: 3/0"', () => {
    useOcupacionMock.mockReturnValue({
      data: {
        uuid_sucursal: '00000000-0000-0000-0000-000000000099',
        items: [
          {
            uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
            tipo: 'Auto',
            cupo_maximo: 0,
            activos: 3,
            disponible: -3,
          },
        ],
        generado_en: '2026-09-16T10:00:00Z',
      },
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });

    render(<OcupacionStrip uuid_sucursal="00000000-0000-0000-0000-000000000099" />);
    const autoChip = screen.getByTestId('ocupacion-chip-Auto');
    expect(autoChip.textContent).toBe('Auto: 3/0');
    expect(autoChip.getAttribute('data-color')).toBe('red');
  });

  it('S3: data-stale="true" cuando el último poll falla después de un éxito', () => {
    useOcupacionMock.mockReturnValue({
      data: SAMPLE_OK,
      error: new Error('NetworkError'),
      isStale: true,
      refresh: vi.fn(),
    });

    render(<OcupacionStrip uuid_sucursal="00000000-0000-0000-0000-000000000099" />);

    const root = screen.getByTestId('ocupacion-strip');
    expect(root.getAttribute('data-stale')).toBe('true');
    expect(screen.getByTestId('ocupacion-strip-stale-icon')).toBeTruthy();
    // Last known values must still render.
    expect(screen.getByTestId('ocupacion-chip-Auto').textContent).toBe('Auto: 23/50');
  });

  it('S3b: data-stale="false" cuando el poll está limpio', () => {
    useOcupacionMock.mockReturnValue({
      data: SAMPLE_OK,
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });
    render(<OcupacionStrip uuid_sucursal="00000000-0000-0000-0000-000000000099" />);
    const root = screen.getByTestId('ocupacion-strip');
    expect(root.getAttribute('data-stale')).toBe('false');
    expect(screen.queryByTestId('ocupacion-strip-stale-icon')).toBeNull();
  });

  it('S4: aria-live="polite" + aria-atomic="false" presentes en cada chip', () => {
    useOcupacionMock.mockReturnValue({
      data: SAMPLE_OK,
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });

    render(<OcupacionStrip uuid_sucursal="00000000-0000-0000-0000-000000000099" />);

    const autoChip = screen.getByTestId('ocupacion-chip-Auto');
    const motoChip = screen.getByTestId('ocupacion-chip-Moto');
    expect(autoChip.getAttribute('aria-live')).toBe('polite');
    expect(autoChip.getAttribute('aria-atomic')).toBe('false');
    expect(motoChip.getAttribute('aria-live')).toBe('polite');
    expect(motoChip.getAttribute('aria-atomic')).toBe('false');
  });

  it('no renderiza chips cuando data es undefined (pre-auth)', () => {
    useOcupacionMock.mockReturnValue({
      data: undefined,
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });
    render(<OcupacionStrip uuid_sucursal="00000000-0000-0000-0000-000000000099" />);
    expect(screen.getByTestId('ocupacion-strip-empty')).toBeTruthy();
  });

  it('cleanup no rompe tests subsecuentes (smoke)', () => {
    useOcupacionMock.mockReturnValue({
      data: SAMPLE_OK,
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });
    const { unmount } = render(
      <OcupacionStrip uuid_sucursal="00000000-0000-0000-0000-000000000099" />,
    );
    unmount();
    cleanup();
  });
});