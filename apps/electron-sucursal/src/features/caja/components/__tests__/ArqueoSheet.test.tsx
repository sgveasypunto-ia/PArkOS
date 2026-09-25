/**
 * `ArqueoSheet.test.tsx` — smoke coverage for the F10.1 drawer shell.
 *
 * REGRESSION (F10.1 "ArqueoSheet → ArqueoParcial split"): `<ArqueoSheet>`
 * used to take `uuid_sesion` / `requiredMode` / `expected` props directly
 * and render the arqueo form itself. It is now a THIN SHELL with NO
 * PROPS — the actual form (and its own `useSesionActiva()` fetch) lives
 * in `pages/ArqueoParcial.tsx`, and the `requiredMode` strict-justificacion
 * gating this file used to test moved to `<CerrarTurnoForm requiredMode>`
 * instead (see `CerrarTurno.test.tsx` for that flow's coverage; its
 * strict-mode UI gating specifically still has no dedicated unit test —
 * a pre-existing gap, unrelated to this fix).
 *
 * The previous "strict-1"/"strict-2" scenarios here asserted on a
 * `requiredMode` prop and an `arqueo-required-justificacion` testid that
 * do not exist on ANY current component (verified via grep) — a
 * Strict-TDD RED scaffold whose GREEN implementation commit never
 * landed on this component. This file now covers what `<ArqueoSheet>`
 * actually does: open/close via `useDashboardDrawerStore`.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

// Mock useArqueo so `<ArqueoParcial>` (mounted inside the sheet) doesn't
// need a real network layer.
vi.mock('../../hooks/useArqueo', () => ({
  useArqueo: () => ({ submit: vi.fn() }),
}));

// `<ArqueoParcial>` also reads the active sesion — no session is fine
// for this shell-level smoke test (it just renders its own "no session"
// placeholder, which is not what's under test here).
vi.mock('../../hooks/useSesionActiva', () => ({
  useSesionActiva: () => ({ sesion: null }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) =>
      opts?.defaultValue ?? key,
  }),
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

import { ArqueoSheet } from '../ArqueoSheet';

afterEach(() => {
  cleanup();
  openDrawer = null;
  mockClose.mockReset();
});

describe('<ArqueoSheet /> — F10.1 drawer shell', () => {
  it('mounts <ArqueoParcial /> inside the sheet when openDrawer==="arqueo"', () => {
    openDrawer = 'arqueo';
    render(<ArqueoSheet />);
    const sheet = screen.getByTestId('arqueo-sheet');
    expect(sheet).toHaveAttribute('data-state', 'open');
    expect(screen.getByTestId('arqueo-parcial-page')).toBeInTheDocument();
  });

  it('does not mount the sheet content when a different drawer (or none) is open', () => {
    openDrawer = 'ingreso';
    render(<ArqueoSheet />);
    // Radix `<Sheet>` unmounts `<SheetContent>` entirely when closed
    // rather than just toggling `data-state`.
    expect(screen.queryByTestId('arqueo-sheet')).not.toBeInTheDocument();
  });
});
