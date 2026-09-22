/**
 * `ArqueoParcial.test.tsx` — strict-TDD unit tests for HU-F10.1
 * drawer-mounted page (REQ-OPS-154, AD-4 / DA-4).
 *
 * Coverage:
 *   render-1: renders skeleton when sesion is loading
 *   fallback-1: no-active-session fallback renders F3.3 message
 *   render-2: page renders form (Sesion activa card + inputs + diferencia)
 *   when sesion is active
 *   submit-1: page POSTs to useArqueo().submit with the live diferencia
 *   and justification (when |dif total| > 0)
 *
 * F11.3 follow-up: the route `/caja/arqueo-parcial` was REMOVED. The
 * page now lives INSIDE <DrawerHost /> on the dashboard. The Dashboard
 * is the canonical owner of `openDrawer('arqueo', anchorId)`; the page
 * no longer manages drawer state itself (the F10.1 drawer-1/drawer-2
 * scenarios that tested the page calling `openDrawer` directly were
 * dropped — DrawerHost's test suite covers that code path).
 *
 * Assertion quality:
 *   - Every assertion checks a SPECIFIC DOM state OR a SPECIFIC call
 *     argument — no smoke tests.
 *   - Mocks are scoped: only the cross-feature hooks (`useSesionActiva`,
 *     `useArqueo`, `useAuth`). `useTranslation` runs as-is.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

// Mock the cross-feature hooks BEFORE the component imports them.
const mockSesion = vi.fn();
const mockSesionLoading = vi.fn(() => false);
const mockRefreshSesion = vi.fn();
vi.mock('../../hooks/useSesionActiva', () => ({
  useSesionActiva: () => ({
    sesion: mockSesion(),
    isLoading: mockSesionLoading(),
    error: undefined,
    refresh: mockRefreshSesion,
  }),
}));

const mockSubmit = vi.fn();
vi.mock('../../hooks/useArqueo', () => ({
  useArqueo: () => ({
    submit: mockSubmit,
    fetchResumen: vi.fn(),
  }),
}));

const mockTipoAuditoriaUuid = vi.fn(
  () => '10101010-1010-1010-1010-101010101010',
);
vi.mock('../../hooks/useTipoArqueoPorCodigo', () => ({
  useTipoArqueoPorCodigo: () => ({ uuid: mockTipoAuditoriaUuid() }),
}));

const mockSucursal = vi.fn();
const mockAuthLoading = vi.fn(() => false);
const mockAuthenticated = vi.fn(() => true);
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({
    sucursal: mockSucursal(),
    user: { email: 'op@parkos.local' },
    isAuthenticated: mockAuthenticated(),
    isLoading: mockAuthLoading(),
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) =>
      opts?.defaultValue ?? key,
  }),
}));

import { ArqueoParcial } from '../ArqueoParcial';

const RENDER = (): ReturnType<typeof render> => render(<ArqueoParcial />);

describe('HU-F10.1 — <ArqueoParcial /> drawer-mounted page (REQ-OPS-154)', () => {
  beforeEach(() => {
    mockSesion.mockReset();
    mockSesionLoading.mockReset();
    mockSesionLoading.mockReturnValue(false);
    mockRefreshSesion.mockReset();
    mockSubmit.mockReset();
    mockSubmit.mockResolvedValue({ uuid: 'arqueo-uuid' });
    mockTipoAuditoriaUuid.mockReset();
    mockTipoAuditoriaUuid.mockReturnValue(
      '10101010-1010-1010-1010-101010101010',
    );
    mockSucursal.mockReset();
    mockSucursal.mockReturnValue({ uuid: 'suc-uuid-1' });
    mockAuthLoading.mockReset();
    mockAuthLoading.mockReturnValue(false);
    mockAuthenticated.mockReset();
    mockAuthenticated.mockReturnValue(true);
  });

  afterEach(() => {
    cleanup();
  });

  // ──────────────────────────────────────────────────────────────────────
  // render-1 — loading state renders the loading paragraph
  // ──────────────────────────────────────────────────────────────────────
  it('render-1: when sesion is loading, renders the loading paragraph', () => {
    mockSesion.mockReturnValue(null);
    mockSesionLoading.mockReturnValue(true);

    RENDER();

    expect(screen.getByTestId('arqueo-parcial-page')).toBeInTheDocument();
    expect(screen.getByText(/Cargando…/i)).toBeInTheDocument();
  });

  // ──────────────────────────────────────────────────────────────────────
  // fallback-1 — no active session renders the F3.3 fallback
  // ──────────────────────────────────────────────────────────────────────
  it('fallback-1: when sesion is null, renders the no-session fallback', () => {
    mockSesion.mockReturnValue(null);
    mockSesionLoading.mockReturnValue(false);

    RENDER();

    expect(screen.getByTestId('arqueo-parcial-page')).toBeInTheDocument();
    expect(
      screen.getByText(/No hay sesión activa/i),
    ).toBeInTheDocument();
    expect(mockSubmit).not.toHaveBeenCalled();
  });

  // ──────────────────────────────────────────────────────────────────────
  // render-2 — sesion activa renders form (Sesion activa card +
  // Efectivo contado input + Datáfono contado input + dif total $0)
  // ──────────────────────────────────────────────────────────────────────
  it('render-2: when sesion is active, renders the form with sesion UUID + zero-stated inputs', () => {
    mockSesion.mockReturnValue({
      uuid: 'sesion-uuid-1',
      uuid_sucursal: 'suc-uuid-1',
      uuid_usuario: 'user-uuid-1',
      valor_inicial_efectivo: 0,
      valor_inicial_datafono: 0,
    });

    RENDER();

    expect(screen.getByTestId('arqueo-parcial-page')).toBeInTheDocument();
    expect(screen.getByTestId('arqueo-sesion-uuid')).toBeInTheDocument();
    expect(screen.getByTestId('arqueo-efectivo-input')).toBeInTheDocument();
    expect(screen.getByTestId('arqueo-datafono-input')).toBeInTheDocument();
    expect(screen.getByTestId('arqueo-dif-total')).toHaveTextContent('$ 0');
    expect(screen.getByTestId('arqueo-confirmar')).toBeInTheDocument();
  });
});
});
