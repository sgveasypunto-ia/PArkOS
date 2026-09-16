/**
 * Unit tests for `<CerrarTurno />` container (F3.3 — T3).
 *
 * Cobertura U12..U14 (cross-ref tasks.md §2):
 *   U12: submit OK → useAuthStore.getState().clear() + parkos:auth:cleared
 *         event + navigate('/login?closed=true', {replace:true}).
 *   U13: PUT 404 → SesionAlreadyClosedError → navigate('/login') sin
 *         ?closed=true.
 *   U14: Cancel button → navigate('/') sin invocar cerrarSesion.
 *
 * Sandbox F.6 caveat: mismo precedent F3.1 Login.test.tsx — test depende de
 * `@testing-library/user-event` que no se instala en este sandbox
 * (npm refuses workspace:*).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

const mockNavigate = vi.fn();
const mockCerrarSesion = vi.fn();
const mockClear = vi.fn();
const dispatchEventSpy = vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true);

const mockUseSesionActiva = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (selector: (s: unknown) => unknown) => selector({}),
    { getState: () => ({ clear: mockClear }) },
  ),
}));

vi.mock('../hooks/useSesionActiva', () => ({
  useSesionActiva: () => mockUseSesionActiva(),
}));

vi.mock('../api/sesionActivaApi', () => ({
  cerrarSesion: (...args: unknown[]) => mockCerrarSesion(...args),
  SesionAlreadyClosedError: class extends Error {
    readonly name = 'SesionAlreadyClosedError';
    constructor(
      public readonly status: number,
      public override readonly body: string,
      public readonly url: string,
    ) {
      super('sesion_not_found');
    }
  },
}));

// Passthrough presentational — evita carga shadcn Form radix deps.
vi.mock('../components/CerrarTurnoForm', () => ({
  CerrarTurnoForm: ({
    form,
    onSubmit,
    isSubmitting,
    error,
    sesion,
    onCancel,
  }: {
    form: { handleSubmit: (cb: (v: unknown) => void) => () => void };
    onSubmit: (v: unknown) => Promise<void>;
    isSubmitting: boolean;
    error: { kind: string } | null;
    sesion: { uuid: string };
    onCancel: () => void;
  }) => (
    <form
      data-testid="cerrar-turno-form"
      onSubmit={(e) => {
        e.preventDefault();
        void form.handleSubmit(onSubmit)({
          valor_final_efectivo: 75000,
          valor_final_datafono: 25000,
          observaciones_cierre: 'Cierre turno tarde',
        });
      }}
    >
      <div data-testid="cerrar-turno-resumen">
        <p>UUID: {sesion.uuid}</p>
      </div>
      {error?.kind === 'sesion_already_closed' && (
        <div data-testid="cerrar-turno-error-sesion-ya-cerrada" role="alert">
          Esta sesión ya está cerrada
        </div>
      )}
      <button
        type="submit"
        data-testid="cerrar-turno-confirmar"
        disabled={isSubmitting}
        aria-disabled={isSubmitting}
      >
        Confirmar cierre
      </button>
      <button
        type="button"
        data-testid="cerrar-turno-cancelar"
        onClick={onCancel}
      >
        Cancelar
      </button>
    </form>
  ),
}));

import { SesionAlreadyClosedError } from '../api/sesionActivaApi';
import { CerrarTurno } from './CerrarTurno';

const baseSesion = {
  uuid: 'sess-uuid-1',
  uuid_sucursal: 'suc-uuid-1',
  uuid_usuario: 'usr-uuid-1',
  valor_inicial_efectivo: 50000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-09-15T08:00:00Z',
  timestamp_cierre: null,
  observaciones: 'Apertura',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseSesionActiva.mockReturnValue({ sesion: baseSesion });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('<CerrarTurno /> container — T3', () => {
  it('U12: submit OK → useAuthStore.clear() + dispatchEvent + navigate("/login?closed=true")', async () => {
    mockCerrarSesion.mockResolvedValueOnce({
      ...baseSesion,
      timestamp_cierre: '2026-09-15T18:00:00Z',
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    await waitFor(() => {
      expect(mockCerrarSesion).toHaveBeenCalledWith('sess-uuid-1', {
        valor_final_efectivo: 75000,
        valor_final_datafono: 25000,
        observaciones_cierre: 'Cierre turno tarde',
      });
    });
    await waitFor(() => {
      expect(mockClear).toHaveBeenCalledOnce();
    });
    await waitFor(() => {
      expect(dispatchEventSpy).toHaveBeenCalledWith(expect.any(Event));
      const event = dispatchEventSpy.mock.calls[0]?.[0] as Event;
      expect(event?.type).toBe('parkos:auth:cleared');
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login?closed=true', { replace: true });
    });
  });

  it('U13: PUT 404 → SesionAlreadyClosedError → navigate("/login") sin ?closed=true', async () => {
    mockCerrarSesion.mockRejectedValueOnce(
      new SesionAlreadyClosedError(
        404,
        '{"error":"sesion_not_found"}',
        '/api/v1/caja-sesion/sesion/sess-uuid-1/cerrar',
      ),
    );
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    await waitFor(() => {
      const alert = screen.getByTestId('cerrar-turno-error-sesion-ya-cerrada');
      expect(alert).toHaveAttribute('role', 'alert');
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login');
    });
    // Verify NO ?closed=true since this was not a successful cierre.
    expect(mockNavigate).not.toHaveBeenCalledWith('/login?closed=true', expect.anything());
    // Verify NO clear dispatched (no logout, redirige directo).
    expect(mockClear).not.toHaveBeenCalled();
  });

  it('U14: Cancel button → navigate("/") sin invocar cerrarSesion', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    await user.click(screen.getByTestId('cerrar-turno-cancelar'));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/');
    });
    expect(mockCerrarSesion).not.toHaveBeenCalled();
    expect(mockClear).not.toHaveBeenCalled();
  });

  it('sin sesion activa (useSesionActiva retorna sesion: null) → retorna null', () => {
    mockUseSesionActiva.mockReturnValue({ sesion: null });
    const { container } = render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    expect(container.firstChild).toBeNull();
  });
});