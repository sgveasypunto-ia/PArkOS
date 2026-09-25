/**
 * `ReimprimirTiqueteSheet.test.tsx` — smoke coverage for the HU-F8.3
 * drawer shell (directiva del operador 2026-09-25: el flujo entero
 * vive dentro de un sheet, no una ruta aparte).
 *
 * Mirrors `ArqueoSheet.test.tsx`: this is a THIN SHELL with no props —
 * the actual form logic lives in `pages/ReimprimirTiquete.tsx` and has
 * its own dedicated test suite (`ReimprimirTiquete.test.tsx`). Here we
 * only assert open/close via `useDashboardDrawerStore`; the hooks the
 * inner form needs are mocked to no-ops so it mounts without a real
 * network layer.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}));

vi.mock('../../hooks/useReimprimir', () => ({
  useReimprimir: () => ({ trigger: vi.fn(), isMutating: false, error: undefined, data: undefined }),
}));

vi.mock('../../hooks/useAnularReimpresion', () => ({
  useAnularReimpresion: () => ({
    trigger: vi.fn(),
    isMutating: false,
    error: undefined,
    data: undefined,
  }),
}));

vi.mock('../../lib/resolverIngresoReimpresion', () => ({
  resolverIngresoReimpresion: vi.fn(),
}));

vi.mock('../../../operacion/hooks/useIngresosActivos', () => ({
  useIngresosActivos: () => [],
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({ sucursal: { uuid: 'suc-1' } }),
}));

let openDrawer: string | null = null;
const mockClose = vi.fn();

vi.mock('@/store/dashboardDrawerStore', () => ({
  useDashboardDrawerStore: (
    selector: (s: {
      openDrawer: string | null;
      lastAnchorId: string | null;
      open: () => void;
      close: () => void;
    }) => unknown,
  ) =>
    selector({
      openDrawer,
      lastAnchorId: null,
      open: vi.fn(),
      close: mockClose,
    }),
}));

import { ReimprimirTiqueteSheet } from '../ReimprimirTiqueteSheet';

afterEach(() => {
  cleanup();
  openDrawer = null;
  mockClose.mockReset();
});

describe('<ReimprimirTiqueteSheet /> — HU-F8.3 drawer shell', () => {
  it('mounts <ReimprimirTiquete /> inside the sheet when openDrawer==="reimpresion"', () => {
    openDrawer = 'reimpresion';
    render(<ReimprimirTiqueteSheet />);
    const sheet = screen.getByTestId('reimprimir-sheet');
    expect(sheet).toHaveAttribute('data-state', 'open');
    expect(screen.getByTestId('reimprimir-tiquete-page')).toBeInTheDocument();
  });

  it('does not mount the sheet content when a different drawer (or none) is open', () => {
    openDrawer = 'ingreso';
    render(<ReimprimirTiqueteSheet />);
    // Radix `<Sheet>` unmounts `<SheetContent>` entirely when closed
    // rather than just toggling `data-state`.
    expect(screen.queryByTestId('reimprimir-sheet')).not.toBeInTheDocument();
  });
});
