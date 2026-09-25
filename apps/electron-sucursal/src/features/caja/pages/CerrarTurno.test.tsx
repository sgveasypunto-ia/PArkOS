/**
 * Unit tests for `<CerrarTurno />` container (F3.3 — T3; rewired for
 * HU-F10.2's 3-step arqueo+cierre chain — REQ-OPS-157/159/160).
 *
 * Cobertura U12..U14 (cross-ref tasks.md §2):
 *   U12: submit OK → useArqueo().submit() → useSesionActiva().cerrarSesion()
 *         → navigate('/login?closed=true', {replace:true}).
 *   U13: PUT 404 (sesión ya cerrada) → navigate('/login') sin ?closed=true,
 *         sin banner (case 5 en `cerrarTurnoChain.ts` — redirect silencioso).
 *   U14: Cancel button → navigate('/') sin invocar arqueo ni cierre.
 *
 * REGRESSION (2026-09-21, Engram #1899): `<CerrarTurno>` ya NO llama
 * `cerrarSesion` importado de `api/sesionActivaApi` directamente — ahora
 * orquesta `runCerrarTurnoChain()` (`cerrarTurnoChain.ts`), que:
 *   1. `useArqueo().submit(...)` (POST /caja/arqueo) PRIMERO.
 *   2. `bridge.imprimir(...)` (best-effort, sin bridge en jsdom).
 *   3. `useSesionActiva().cerrarSesion(uuid, payload)` — ahora vive EN el
 *      hook (no en `sesionActivaApi` como función suelta) y devuelve un
 *      envelope `{ok, status, ...}` en vez de lanzar excepciones típicas
 *      (`SesionAlreadyClosedError`). El trifecta F3.3 (`useAuthStore.clear()`
 *      + evento `parkos:auth:cleared`) vive AHORA dentro de ese helper
 *      (mockeado acá) — se verifica por separado en
 *      `useSesionActiva.cerrarSesion.test.ts`, no en este container test.
 *
 * `cerrarTurnoChain.ts` no tiene test dedicado todavía (gap de cobertura
 * pre-existente, fuera de alcance de este fix) — este archivo cubre el
 * container a nivel smoke (éxito / un remap silencioso / cancelar), no
 * los 8 casos de precedencia del chain.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type * as ReactRouterDom from 'react-router-dom';

const mockNavigate = vi.fn();
const mockCerrarSesion = vi.fn();
const mockSubmitArqueo = vi.fn();

const mockUseSesionActiva = vi.fn();
const mockUseTipoArqueoPorCodigo = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof ReactRouterDom>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../hooks/useSesionActiva', () => ({
  useSesionActiva: () => mockUseSesionActiva(),
}));

// F11.3: the arqueo POST requires `uuid_tipo_arqueo` (UUID), resolved
// from the 'cierre_turno' codigo via this catalog SWR hook.
vi.mock('../hooks/useTipoArqueoPorCodigo', () => ({
  useTipoArqueoPorCodigo: () => mockUseTipoArqueoPorCodigo(),
}));

vi.mock('../hooks/useArqueo', () => ({
  useArqueo: () => ({ submit: mockSubmitArqueo }),
}));

// Passthrough presentational — evita carga shadcn Form radix deps.
// `onSubmit` llega YA envuelto en `form.handleSubmit(...)` desde el
// container — se pasa directo al `<form onSubmit>` nativo, y los
// inputs se registran contra el `form` REAL para que RHF valide con
// valores reales (no placeholders sueltos).
vi.mock('../components/CerrarTurnoForm', () => ({
  CerrarTurnoForm: ({
    form,
    onSubmit,
    isSubmitting,
    error,
    sesion,
    onCancel,
  }: {
    form: {
      register: (
        name: string,
        options?: { valueAsNumber?: boolean },
      ) => Record<string, unknown>;
    };
    onSubmit: (e: React.FormEvent) => void;
    isSubmitting: boolean;
    error: { kind: string } | null;
    sesion: { uuid: string };
    onCancel: () => void;
  }) => (
    <form data-testid="cerrar-turno-form" onSubmit={onSubmit}>
      <div data-testid="cerrar-turno-resumen">
        <p>UUID: {sesion.uuid}</p>
      </div>
      {/* `cerrarTurnoSchema` types these 4 fields as `z.number()` (not
          string+transform like `abrirTurnoSchema`) — `valueAsNumber`
          makes RHF coerce the native input string to a number before
          Zod validates it. */}
      <input
        data-testid="cerrar-turno-valor-efectivo-reportado"
        type="text"
        {...form.register('valor_efectivo_reportado', { valueAsNumber: true })}
      />
      <input
        data-testid="cerrar-turno-valor-datafono-reportado"
        type="text"
        {...form.register('valor_datafono_reportado', { valueAsNumber: true })}
      />
      <input
        data-testid="cerrar-turno-justificacion"
        type="text"
        {...form.register('justificacion')}
      />
      <input
        data-testid="cerrar-turno-observaciones"
        type="text"
        {...form.register('observaciones_cierre')}
      />
      {error?.kind === 'cierre_ya_cerrado' && (
        <div data-testid="cerrar-turno-error-cierre-ya-cerrado" role="alert">
          Esta sesión ya está cerrada
        </div>
      )}
      {error?.kind === 'arqueo_fallido' && (
        <div data-testid="cerrar-turno-error-arqueo-fallido" role="alert">
          No se pudo registrar el arqueo
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

// `cerrarTurnoSchema` requires all 5 numeric/justificacion fields as
// real values before `form.handleSubmit` reaches the real async
// handler — fill them so the arqueo+cierre chain actually runs.
function fillValidForm(): void {
  fireEvent.change(screen.getByTestId('cerrar-turno-valor-efectivo-reportado'), {
    target: { value: '75000' },
  });
  fireEvent.change(screen.getByTestId('cerrar-turno-valor-datafono-reportado'), {
    target: { value: '25000' },
  });
  fireEvent.change(screen.getByTestId('cerrar-turno-observaciones'), {
    target: { value: 'Cierre turno tarde' },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseSesionActiva.mockReturnValue({
    sesion: baseSesion,
    cerrarSesion: mockCerrarSesion,
  });
  mockUseTipoArqueoPorCodigo.mockReturnValue({
    data: { uuid: 'tipo-arqueo-uuid-cierre-turno', codigo: 'cierre_turno' },
    uuid: 'tipo-arqueo-uuid-cierre-turno',
    error: undefined,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('<CerrarTurno /> container — T3', () => {
  it('U12: submit OK → arqueo + cerrarSesion → navigate("/login?closed=true")', async () => {
    mockSubmitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-1' });
    mockCerrarSesion.mockResolvedValueOnce({
      ok: true,
      status: 200,
      sesion: { ...baseSesion, timestamp_cierre: '2026-09-15T18:00:00Z' },
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    fillValidForm();
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    await waitFor(() => {
      expect(mockSubmitArqueo).toHaveBeenCalledWith(
        expect.objectContaining({
          uuid_sesion: 'sess-uuid-1',
          uuid_tipo_arqueo: 'tipo-arqueo-uuid-cierre-turno',
          valor_efectivo_reportado: 75000,
          valor_datafono_reportado: 25000,
        }),
      );
    });
    await waitFor(() => {
      expect(mockCerrarSesion).toHaveBeenCalledWith('sess-uuid-1', {
        valor_final_efectivo: 75000,
        valor_final_datafono: 25000,
        observaciones_cierre: 'Cierre turno tarde',
      });
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login?closed=true', { replace: true });
    });
  });

  it('U13: PUT 404 (sesión ya cerrada) → navigate("/login") sin ?closed=true, sin banner', async () => {
    // `cerrarTurnoChain.ts` case 5: a 404 from `cerrarSesion` is a
    // SILENT redirect (DEC-F3.3-07) — no error banner, unlike 409
    // ('cierre_ya_cerrado', which DOES render one).
    mockSubmitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-1' });
    mockCerrarSesion.mockResolvedValueOnce({
      ok: false,
      status: 404,
      error: { code: 'sesion_not_found' },
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    fillValidForm();
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login');
    });
    // Verify NO ?closed=true since this was not a successful cierre.
    expect(mockNavigate).not.toHaveBeenCalledWith('/login?closed=true', expect.anything());
    // No banner for this case — the redirect is silent.
    expect(screen.queryByTestId('cerrar-turno-error-cierre-ya-cerrado')).not.toBeInTheDocument();
  });

  it('U14: Cancel button → navigate("/") sin invocar arqueo ni cerrarSesion', async () => {
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
    expect(mockSubmitArqueo).not.toHaveBeenCalled();
    expect(mockCerrarSesion).not.toHaveBeenCalled();
  });

  it('uuid_tipo_arqueo aún no resuelto (catálogo cargando) → NO invoca arqueo ni cerrarSesion', async () => {
    mockUseTipoArqueoPorCodigo.mockReturnValue({
      data: undefined,
      uuid: undefined,
      error: undefined,
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    fillValidForm();
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));

    expect(mockSubmitArqueo).not.toHaveBeenCalled();
    expect(mockCerrarSesion).not.toHaveBeenCalled();
  });

  it('sin sesion activa (useSesionActiva retorna sesion: null) → retorna null', () => {
    mockUseSesionActiva.mockReturnValue({ sesion: null, cerrarSesion: mockCerrarSesion });
    const { container } = render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    expect(container.firstChild).toBeNull();
  });
});
