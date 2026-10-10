/**
 * `CerrarTurnoForm.test.tsx` — cobertura dedicada para:
 *   - PT-4: el motivo del descuadre se escribe en "Observaciones" (no hay
 *     campo "Justificación") y es obligatorio (min 3) SOLO si hay
 *     diferencia (plan.md HU-F10.2 línea 2273) + conteo ciego.
 *   - PT-6: no hay campo de datáfono en el cierre.
 *   - el resumen del turno con ingresos/salidas (HU-F12.1, mismo KPI que
 *     `<MiTurnoPanel>` / `<ResumenTurno>`).
 *
 * NOTA: NO usar `.toBeInTheDocument()` — hay un bug preexistente de
 * infra (dos instalaciones de `vitest` en el monorepo) que rompe el
 * registro de matchers `jest-dom` en este workspace (fuera de alcance
 * de este fix, reportado aparte). Se usan matchers nativos de vitest
 * (`toBeNull`, `toBe`, etc.) que no dependen de esa extensión.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

import '@/i18n';

import { CerrarTurnoForm } from './CerrarTurnoForm';
import { cerrarTurnoSchema, type CerrarTurnoInput } from '../api/schemas/turnoSchema';
import type { SesionRead } from '../api/sesionActivaApi';

const useMiTurnoMock = vi.fn();
vi.mock('../../operacion/hooks/useMiTurno', () => ({
  useMiTurno: (uuid_sesion: string | null) => useMiTurnoMock(uuid_sesion),
}));

// HU-F10.2 follow-up (REGRESSION fix 2026-10-01): the component no
// longer guesses `hayDiferencia` client-side against
// `sesion.valor_inicial_*` — it asks the backend via
// `useRequiereJustificacion` (conteo ciego: only the boolean verdict
// crosses the wire). Tests drive that verdict directly. PT-6: the hook
// takes (uuid, efectivo) only — no datáfono.
const useRequiereJustificacionMock = vi.fn();
vi.mock('../hooks/useRequiereJustificacion', () => ({
  useRequiereJustificacion: (uuid_sesion: string | null, efectivo: number) =>
    useRequiereJustificacionMock(uuid_sesion, efectivo),
}));

const SESION: SesionRead = {
  uuid: 'sess-uuid-1',
  uuid_sucursal: 'suc-uuid-1',
  uuid_usuario: 'usr-uuid-1',
  valor_inicial_efectivo: 733_000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-09-21T08:00:00Z',
  timestamp_cierre: null,
};

function Harness({
  sesion = SESION,
  efectivoReportado = sesion.valor_inicial_efectivo,
  forceRequireMotivo = false,
  error = null,
  onSubmit = async () => {},
}: {
  sesion?: SesionRead;
  efectivoReportado?: number;
  forceRequireMotivo?: boolean;
  error?: Parameters<typeof CerrarTurnoForm>[0]['error'];
  onSubmit?: (data: CerrarTurnoInput) => Promise<void>;
}): JSX.Element {
  const form = useForm<CerrarTurnoInput>({
    resolver: zodResolver(cerrarTurnoSchema),
    defaultValues: {
      valor_efectivo_reportado: efectivoReportado,
      observaciones_cierre: '',
    },
  });
  return (
    <CerrarTurnoForm
      form={form}
      onSubmit={onSubmit}
      isSubmitting={false}
      error={error}
      sesion={sesion}
      onCancel={() => {}}
      requiredMode="cierre_turno"
      forceRequireMotivo={forceRequireMotivo}
    />
  );
}

beforeEach(() => {
  useRequiereJustificacionMock.mockReset();
  useMiTurnoMock.mockReturnValue({
    data: { ingresos_count: 7, salidas_count: 4 },
    error: undefined,
    isStale: false,
    refresh: vi.fn(),
  });
  // Default: backend confirms NO difference (baseline "sin diferencia").
  // Individual tests override this per scenario.
  useRequiereJustificacionMock.mockReturnValue({
    requiereJustificacion: false,
    error: undefined,
  });
});

describe('<CerrarTurnoForm /> — PT-4/PT-6: sin campos de justificación ni datáfono', () => {
  it.each([false, true, undefined])(
    'pre-flight=%s → nunca hay campo de justificación ni de datáfono en el DOM',
    (verdict) => {
      useRequiereJustificacionMock.mockReturnValue({
        requiereJustificacion: verdict,
        error: undefined,
      });
      render(<Harness />);

      expect(screen.queryByTestId('cerrar-turno-required-justificacion')).toBeNull();
      expect(screen.queryByTestId('cerrar-turno-justificacion')).toBeNull();
      expect(screen.queryByTestId('cerrar-turno-valor-datafono-reportado')).toBeNull();
      expect(document.body.textContent ?? '').not.toMatch(/datáfono contado/i);
      expect(document.body.textContent ?? '').not.toMatch(/justificación/i);
    },
  );

  it('muestra el producido a consignar (contado − base) mientras el operador cuenta', () => {
    render(<Harness efectivoReportado={SESION.valor_inicial_efectivo + 100_000} />);

    const producido = screen.getByTestId('cerrar-turno-producido').textContent ?? '';
    expect(producido).toContain('Producido a consignar');
    expect(producido).toContain('100.000');
  });

  it('no muestra un producido negativo mientras el operador no ha contado', () => {
    render(<Harness efectivoReportado={0} />);

    const producido = screen.getByTestId('cerrar-turno-producido').textContent ?? '';
    expect(producido).toContain('—');
    expect(producido).not.toContain('-$');
  });

  it('el pre-flight se consulta solo con el efectivo (sin datáfono)', () => {
    render(<Harness efectivoReportado={500_000} />);
    expect(useRequiereJustificacionMock).toHaveBeenCalledWith(SESION.uuid, 500_000);
  });
});

describe('<CerrarTurnoForm /> — motivo del descuadre en Observaciones (conteo ciego)', () => {
  it('sin diferencia → Observaciones es opcional y el botón queda habilitado', () => {
    render(<Harness />);

    const obs = screen.getByTestId('cerrar-turno-observaciones');
    expect(obs).not.toBeNull();
    expect(screen.getByTestId('cerrar-turno-observaciones-ayuda').textContent).toContain(
      'Opcional',
    );
    expect((screen.getByTestId('cerrar-turno-confirmar') as HTMLButtonElement).disabled).toBe(
      false,
    );
    expect(screen.queryByTestId('cerrar-turno-boton-disabled-motivo')).toBeNull();
  });

  it('con diferencia → Observaciones pasa a ser obligatoria (min 3) y no expone ningún monto esperado/diferencia', () => {
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: true,
      error: undefined,
    });
    render(<Harness efectivoReportado={900_000} />);

    const obs = screen.getByTestId('cerrar-turno-observaciones') as HTMLInputElement;
    expect(obs.getAttribute('aria-required')).toBe('true');
    expect(screen.getByTestId('cerrar-turno-observaciones-ayuda').textContent).toContain(
      'motivo del descuadre',
    );
    expect((screen.getByTestId('cerrar-turno-confirmar') as HTMLButtonElement).disabled).toBe(
      true,
    );

    fireEvent.change(obs, { target: { value: 'ab' } });
    expect((screen.getByTestId('cerrar-turno-confirmar') as HTMLButtonElement).disabled).toBe(
      true,
    );

    fireEvent.change(obs, { target: { value: 'Faltante en caja' } });
    expect((screen.getByTestId('cerrar-turno-confirmar') as HTMLButtonElement).disabled).toBe(
      false,
    );

    // Conteo ciego: el MONTO de la diferencia (167.000 / 167000) NUNCA
    // debe aparecer en el DOM, ni siquiera oculto.
    //
    // El "producido a consignar" (contado − base) sí se muestra: sale solo del
    // conteo del operador y de la base visible, nunca del esperado del servidor.
    // Con este fixture (sin ventas) coincide numéricamente con la diferencia,
    // así que se excluye ese bloque del barrido.
    const clone = document.body.cloneNode(true) as HTMLElement;
    clone.querySelector('[data-testid="cerrar-turno-producido"]')?.remove();
    const html = clone.innerHTML;
    expect(html).not.toContain('167000');
    expect(html).not.toContain('167.000');
  });

  it('Observaciones limita el texto al máximo del backend (500)', () => {
    render(<Harness />);
    const obs = screen.getByTestId('cerrar-turno-observaciones') as HTMLInputElement;
    expect(obs.maxLength).toBe(500);
  });

  it('con diferencia y motivo válido → submit entrega observaciones_cierre al padre', async () => {
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: true,
      error: undefined,
    });
    const onSubmit = vi.fn(async () => {});
    render(<Harness efectivoReportado={900_000} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByTestId('cerrar-turno-observaciones'), {
      target: { value: 'Billete roto' },
    });
    fireEvent.submit(screen.getByTestId('cerrar-turno-form'));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const firstCall = onSubmit.mock.calls[0] as unknown as [CerrarTurnoInput];
    expect(firstCall[0]).toMatchObject({
      valor_efectivo_reportado: 900_000,
      observaciones_cierre: 'Billete roto',
    });
  });

  it('(E) el veredicto del pre-flight viaja al padre: true con diferencia, false sin diferencia', async () => {
    const onSubmit = vi.fn(async () => {});

    useRequiereJustificacionMock.mockReturnValue({ requiereJustificacion: true, error: undefined });
    const { unmount } = render(<Harness efectivoReportado={900_000} onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId('cerrar-turno-observaciones'), {
      target: { value: 'Billete roto' },
    });
    fireEvent.submit(screen.getByTestId('cerrar-turno-form'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect((onSubmit.mock.calls[0] as unknown as [unknown, unknown])[1]).toEqual({
      requiereJustificacion: true,
    });
    unmount();

    onSubmit.mockClear();
    useRequiereJustificacionMock.mockReturnValue({ requiereJustificacion: false, error: undefined });
    render(<Harness efectivoReportado={100_000} onSubmit={onSubmit} />);
    fireEvent.submit(screen.getByTestId('cerrar-turno-form'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect((onSubmit.mock.calls[0] as unknown as [unknown, unknown])[1]).toEqual({
      requiereJustificacion: false,
    });
  });

  it('con diferencia y motivo vacío → el submit NO llega al padre (red de seguridad del handler)', async () => {
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: true,
      error: undefined,
    });
    const onSubmit = vi.fn(async () => {});
    render(<Harness efectivoReportado={900_000} onSubmit={onSubmit} />);

    fireEvent.submit(screen.getByTestId('cerrar-turno-form'));
    await waitFor(() => {
      expect(screen.queryByText(/motivo del descuadre \(mínimo 3/i)).not.toBeNull();
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  // REGRESSION (2026-09-25, fix 2026-10-01): el backend calcula el esperado
  // real SOLO server-side. `forceRequireMotivo` es la red de seguridad ante
  // una condición de carrera entre el pre-flight (debounced) y el POST real,
  // incluso si el pre-flight responde `false` (stale).
  it('pre-flight false (stale) pero forceRequireMotivo=true (el backend ya rechazó el POST) → Observaciones obligatoria', () => {
    render(<Harness forceRequireMotivo />);

    expect((screen.getByTestId('cerrar-turno-confirmar') as HTMLButtonElement).disabled).toBe(
      true,
    );
    fireEvent.change(screen.getByTestId('cerrar-turno-observaciones'), {
      target: { value: 'Descuadre reportado por el backend' },
    });
    expect((screen.getByTestId('cerrar-turno-confirmar') as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it('mientras el pre-flight carga (undefined) → conservador: motivo exigido y botón disabled, nunca asume "sin diferencia"', () => {
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: undefined,
      error: undefined,
    });
    render(<Harness />);

    expect(
      (screen.getByTestId('cerrar-turno-observaciones') as HTMLInputElement).getAttribute(
        'aria-required',
      ),
    ).toBe('true');
    expect((screen.getByTestId('cerrar-turno-confirmar') as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
});

describe('<CerrarTurnoForm /> — banner explicativo del botón disabled (Cambio 1)', () => {
  it('aparece cuando el botón está disabled por falta del motivo en Observaciones', () => {
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: true,
      error: undefined,
    });
    render(<Harness />);

    expect(screen.queryByTestId('cerrar-turno-boton-disabled-motivo')).not.toBeNull();
  });

  it('desaparece en cuanto se escribe un motivo válido (botón habilitado)', () => {
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: true,
      error: undefined,
    });
    render(<Harness />);

    fireEvent.change(screen.getByTestId('cerrar-turno-observaciones'), {
      target: { value: 'Motivo válido' },
    });

    expect(screen.queryByTestId('cerrar-turno-boton-disabled-motivo')).toBeNull();
  });

  it('no aparece cuando el backend confirma que no hace falta motivo', () => {
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: false,
      error: undefined,
    });
    render(<Harness />);

    expect(screen.queryByTestId('cerrar-turno-boton-disabled-motivo')).toBeNull();
  });
});

describe('<CerrarTurnoForm /> — banner catálogo no disponible (Cambio 2)', () => {
  it('error.kind === "catalogo_no_disponible" → muestra banner role=alert', () => {
    render(<Harness error={{ kind: 'catalogo_no_disponible' }} />);

    expect(
      screen.queryByTestId('cerrar-turno-error-catalogo-no-disponible'),
    ).not.toBeNull();
  });
});

describe('<CerrarTurnoForm /> — resumen del turno (ingresos/salidas, HU-F12.1)', () => {
  it('muestra ingresos y salidas del turno desde useMiTurno', () => {
    render(<Harness />);

    expect(useMiTurnoMock).toHaveBeenCalledWith(SESION.uuid);
    const ingresosRow = screen.getByTestId('cerrar-turno-resumen-row-ingresos');
    const salidasRow = screen.getByTestId('cerrar-turno-resumen-row-salidas');
    expect(ingresosRow.textContent).toContain('7');
    expect(salidasRow.textContent).toContain('4');
  });

  it('zero-state: useMiTurno sin datos aún → filas muestran 0, no rompe el render', () => {
    useMiTurnoMock.mockReturnValue({
      data: { ingresos_count: 0, salidas_count: 0 },
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });
    render(<Harness />);

    expect(screen.getByTestId('cerrar-turno-resumen-row-ingresos').textContent).toContain('0');
    expect(screen.getByTestId('cerrar-turno-resumen-row-salidas').textContent).toContain('0');
  });
});
