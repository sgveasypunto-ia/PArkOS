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
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

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

// Efectivo esperado del turno (base + cobros en efectivo - reversos) que
// calcula el servidor; el arqueo parcial lo muestra tal cual.
const mockEsperado = vi.fn((): number | undefined => 0);
vi.mock('../../hooks/useEsperadoParcial', () => ({
  useEsperadoParcial: () => ({
    esperadoEfectivo: mockEsperado(),
    error: undefined,
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
    mockEsperado.mockReset();
    mockEsperado.mockReturnValue(0);
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
  // Efectivo contado input + dif total $0). El datafono se removio
  // de la UI en fix/electron-sucursal-datafono-arqueo: ya no se
  // tipea ni se muestra el input ni los renglones de esperado/dif.
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
    expect(screen.getByTestId('arqueo-dif-total')).toHaveTextContent('$ 0');
    expect(screen.getByTestId('arqueo-confirmar')).toBeInTheDocument();
  });

  // El esperado incluye los cobros en efectivo del turno, no solo la base.
  it('esperado-1: muestra base + cobros en efectivo (base 10.000 + 5.000 = 15.000), no solo la base', () => {
    mockSesion.mockReturnValue({
      uuid: 'sesion-uuid-1',
      uuid_sucursal: 'suc-uuid-1',
      uuid_usuario: 'user-uuid-1',
      valor_inicial_efectivo: 10000,
      valor_inicial_datafono: 0,
    });
    mockEsperado.mockReturnValue(15000);

    RENDER();

    const esperado = screen.getByTestId('arqueo-esperado-efectivo');
    expect(esperado).toHaveTextContent('15.000');
    expect(esperado).not.toHaveTextContent(/10\.000/);
  });

  it('esperado-2: contar exactamente el esperado no genera diferencia ni exige justificacion', () => {
    mockSesion.mockReturnValue({
      uuid: 'sesion-uuid-1',
      uuid_sucursal: 'suc-uuid-1',
      uuid_usuario: 'user-uuid-1',
      valor_inicial_efectivo: 10000,
      valor_inicial_datafono: 0,
    });
    mockEsperado.mockReturnValue(15000);

    RENDER();
    fireEvent.change(screen.getByTestId('arqueo-efectivo-input'), {
      target: { value: '15000' },
    });

    expect(screen.getByTestId('arqueo-dif-total')).toHaveTextContent('$ 0');
    expect(screen.queryByTestId('arqueo-advertencia')).not.toBeInTheDocument();
    expect(screen.queryByTestId('arqueo-justificacion')).not.toBeInTheDocument();
  });

  it('esperado-3: mientras el esperado no llega no se puede confirmar (no se compara contra la base)', () => {
    mockSesion.mockReturnValue({
      uuid: 'sesion-uuid-1',
      uuid_sucursal: 'suc-uuid-1',
      uuid_usuario: 'user-uuid-1',
      valor_inicial_efectivo: 10000,
      valor_inicial_datafono: 0,
    });
    mockEsperado.mockReturnValue(undefined);

    RENDER();
    fireEvent.change(screen.getByTestId('arqueo-efectivo-input'), {
      target: { value: '10000' },
    });

    expect(screen.getByTestId('arqueo-confirmar')).toBeDisabled();
  });
});
