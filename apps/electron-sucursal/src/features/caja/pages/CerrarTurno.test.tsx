/**
 * Unit tests for `<CerrarTurno />` container (F3.3 — T3; rewired for
 * HU-F10.2's 3-step arqueo+cierre chain — REQ-OPS-157/159/160).
 *
 * Cobertura U12..U14 (cross-ref tasks.md §2):
 *   U12: submit OK → useArqueo().submit() → useSesionActiva().cerrarSesion()
 *         (logout DEFERRED, PT-5) → read-only summary → "Finalizar y salir"
 *         → logout trifecta + navigate('/login?closed=true', {replace:true}).
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

import '@/i18n';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

const mockNavigate = vi.fn();
const mockCerrarSesion = vi.fn();
const mockLogoutAfterClose = vi.fn();
const mockGetResumenCierreTurno = vi.fn();
const mockSubmitArqueo = vi.fn();

const mockUseSesionActiva = vi.fn();
const mockUseTipoArqueoPorCodigo = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof ReactRouterDom>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../hooks/useSesionActiva', () => ({
  useSesionActiva: () => mockUseSesionActiva(),
  logoutAfterClose: () => mockLogoutAfterClose(),
}));

// PT-5: new read-only endpoint behind the post-close summary.
vi.mock('../api/resumenCierreTurnoApi', () => ({
  getResumenCierreTurno: (uuid: string) => mockGetResumenCierreTurno(uuid),
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
// `onSubmit` llega como el handler CRUDO `(data) => Promise<void>`
// (contrato real de `CerrarTurnoFormProps.onSubmit`, DEC-F3.3-06) — el
// mock replica lo que `<CerrarTurnoForm>` real hace internamente
// (`form.handleSubmit(onSubmit)`), en vez de bindear `onSubmit` directo
// al evento nativo. Los inputs se registran contra el `form` REAL para
// que RHF valide con valores reales (no placeholders sueltos).
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
      handleSubmit: (
        onValid: (data: Record<string, unknown>) => Promise<void>,
      ) => (e: React.FormEvent) => void;
    };
    onSubmit: (data: Record<string, unknown>) => Promise<void>;
    isSubmitting: boolean;
    error: { kind: string } | null;
    sesion: { uuid: string };
    onCancel: () => void;
  }) => (
    <form data-testid="cerrar-turno-form" onSubmit={form.handleSubmit(onSubmit)}>
      <div data-testid="cerrar-turno-resumen">
        <p>UUID: {sesion.uuid}</p>
      </div>
      {/* `cerrarTurnoSchema` types the efectivo field as `z.number()` (not
          string+transform like `abrirTurnoSchema`) — `valueAsNumber`
          makes RHF coerce the native input string to a number before
          Zod validates it. */}
      <input
        data-testid="cerrar-turno-valor-efectivo-reportado"
        type="text"
        {...form.register('valor_efectivo_reportado', { valueAsNumber: true })}
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
      {error?.kind === 'catalogo_no_disponible' && (
        <div data-testid="cerrar-turno-error-catalogo-no-disponible" role="alert">
          Catálogo de tipos de arqueo no disponible
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

// `cerrarTurnoSchema` requires the efectivo field as a
// real value before `form.handleSubmit` reaches the real async
// handler — fill them so the arqueo+cierre chain actually runs.
function fillValidForm(): void {
  fireEvent.change(screen.getByTestId('cerrar-turno-valor-efectivo-reportado'), {
    target: { value: '75000' },
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
  const RESUMEN_OK = {
    uuid_sesion: 'sess-uuid-1',
    uuid_sucursal: 'suc-uuid-1',
    timestamp_calculo: '2026-09-15T18:00:00',
    ingresos_count: 9,
    salidas_count: 8,
    transacciones_count: 6,
    medios_pago: [
      { medio_pago: 'efectivo', pagos_count: 4, total_cop: 40000 },
      { medio_pago: 'datafono', pagos_count: 2, total_cop: 30000 },
    ],
    reversos_count: 1,
    reversos_total_cop: 5000,
  };
  const ARQUEO_OK = {
    uuid: 'arqueo-uuid-1',
    valor_efectivo_esperado: 90000,
    valor_efectivo_reportado: 75000,
    diferencia_efectivo: -15000,
  };

  async function submitOk(): Promise<ReturnType<typeof userEvent.setup>> {
    mockSubmitArqueo.mockResolvedValueOnce(ARQUEO_OK);
    mockCerrarSesion.mockResolvedValueOnce({
      ok: true,
      status: 200,
      sesion: { ...baseSesion, timestamp_cierre: '2026-09-15T18:00:00Z' },
    });
    const user = userEvent.setup();
    fillValidForm();
    await user.click(screen.getByTestId('cerrar-turno-confirmar'));
    return user;
  }

  it('U12: submit OK → arqueo + cerrarSesion (logout diferido) → resumen de solo lectura, SIN navegar ni cerrar sesión todavía', async () => {
    mockGetResumenCierreTurno.mockResolvedValueOnce(RESUMEN_OK);
    render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );

    // Conteo ciego: antes de enviar NO hay esperado/diferencia en pantalla.
    expect(screen.queryByTestId('resumen-cierre-turno')).toBeNull();
    expect(document.body.textContent ?? '').not.toContain('90.000');

    await submitOk();

    await waitFor(() => {
      expect(mockSubmitArqueo).toHaveBeenCalledWith(
        expect.objectContaining({
          uuid_sesion: 'sess-uuid-1',
          uuid_tipo_arqueo: 'tipo-arqueo-uuid-cierre-turno',
          valor_efectivo_reportado: 75000,
        }),
      );
    });
    // Balanced-close rule: the first POST carries no justificacion.
    expect(
      'justificacion' in (mockSubmitArqueo.mock.calls[0]?.[0] as Record<string, unknown>),
    ).toBe(false);
    // PT-6: ningún datáfono viaja en el arqueo ni en el cierre.
    const arqueoBody = mockSubmitArqueo.mock.calls[0]?.[0] as Record<string, unknown>;
    expect('valor_datafono_reportado' in arqueoBody).toBe(false);
    await waitFor(() => {
      expect(mockCerrarSesion).toHaveBeenCalledWith(
        'sess-uuid-1',
        { valor_final_efectivo: 75000, observaciones_cierre: 'Cierre turno tarde' },
        { deferLogout: true },
      );
    });

    // PT-5: resumen visible con TODOS los datos.
    const resumen = await screen.findByTestId('resumen-cierre-turno');
    const text = resumen.textContent ?? '';
    expect(text).toContain('Turno cerrado');
    expect(text).toContain('Hora de cierre');
    expect(text).toContain('Base (efectivo inicial)');
    expect(text).toContain('Efectivo esperado');
    expect(text).toContain('Efectivo contado');
    expect(text).toContain('Diferencia');
    expect(text).toContain('Transacciones (pagos)');
    expect(text).toContain('Efectivo (4)');
    expect(text).toContain('Datáfono (2)');
    expect(text).toContain('Reversos (1)');
    expect(text).toContain('Cierre turno tarde');
    expect(mockGetResumenCierreTurno).toHaveBeenCalledWith('sess-uuid-1');

    // El logout NO ocurrió aún: el operador sigue leyendo el resumen.
    expect(mockLogoutAfterClose).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('U12g: con diferencia el backend responde 400 y el reintento lleva Observaciones como justificacion', async () => {
    mockGetResumenCierreTurno.mockResolvedValueOnce(RESUMEN_OK);
    mockSubmitArqueo.mockRejectedValueOnce(
      new ParkosHttpError(
        400,
        JSON.stringify({ detail: { error: 'justificacion_requerida' } }),
        '/api/v1/caja/arqueo',
      ),
    );
    render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    await submitOk();

    await screen.findByTestId('resumen-cierre-turno');
    expect(mockSubmitArqueo).toHaveBeenCalledTimes(2);
    expect(mockSubmitArqueo.mock.calls[1]?.[0]).toMatchObject({
      justificacion: 'Cierre turno tarde',
    });
  });

  it('U12b: "Finalizar y salir" → recién ahí corre el logout y navega a /login?closed=true', async () => {
    mockGetResumenCierreTurno.mockResolvedValueOnce(RESUMEN_OK);
    render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    const user = await submitOk();

    await user.click(await screen.findByTestId('resumen-cierre-finalizar'));

    expect(mockLogoutAfterClose).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledWith('/login?closed=true', { replace: true });
  });

  it('U12c: si el endpoint del resumen falla, el cierre igual muestra esperado/contado/diferencia y avisa que el detalle no está disponible', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    mockGetResumenCierreTurno.mockRejectedValueOnce(new Error('boom'));
    render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    await submitOk();

    const resumen = await screen.findByTestId('resumen-cierre-turno');
    const text = resumen.textContent ?? '';
    expect(text).toContain('Efectivo esperado');
    expect(text).toContain('No disponible');
    expect(text).not.toContain('Totales por medio de pago');
    expect(mockLogoutAfterClose).not.toHaveBeenCalled();
  });

  it('U12d: el resumen sobrevive a que useSesionActiva pase a null tras el cierre (404 en /sesion/me)', async () => {
    mockGetResumenCierreTurno.mockResolvedValueOnce(RESUMEN_OK);
    const { rerender } = render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    await submitOk();
    await screen.findByTestId('resumen-cierre-turno');

    mockUseSesionActiva.mockReturnValue({ sesion: null, cerrarSesion: mockCerrarSesion });
    rerender(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('resumen-cierre-turno')).not.toBeNull();
  });

  it('U12e: si el drawer se descarta con el resumen pendiente (unmount) → red de seguridad: se cierra la sesión de auth', async () => {
    mockGetResumenCierreTurno.mockResolvedValueOnce(RESUMEN_OK);
    const { unmount } = render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    await submitOk();
    await screen.findByTestId('resumen-cierre-turno');
    expect(mockLogoutAfterClose).not.toHaveBeenCalled();

    unmount();

    expect(mockLogoutAfterClose).toHaveBeenCalledTimes(1);
  });

  it('U12f: el unmount SIN cierre completado no cierra la sesión de auth', () => {
    const { unmount } = render(
      <MemoryRouter>
        <CerrarTurno />
      </MemoryRouter>,
    );
    unmount();
    expect(mockLogoutAfterClose).not.toHaveBeenCalled();
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

  it('uuid_tipo_arqueo aún no resuelto (catálogo cargando) → NO invoca arqueo ni cerrarSesion, y muestra banner (Cambio 2 — ya no es un silent return)', async () => {
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
    await waitFor(() => {
      expect(
        screen.getByTestId('cerrar-turno-error-catalogo-no-disponible'),
      ).toBeInTheDocument();
    });
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
