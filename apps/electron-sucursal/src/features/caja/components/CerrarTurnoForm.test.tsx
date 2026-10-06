/**
 * `CerrarTurnoForm.test.tsx` — cobertura dedicada (no existía) para el
 * fix de justificación condicional + conteo ciego (directiva operador,
 * plan.md HU-F10.2 línea 2273: "justificación obligatoria SI HAY
 * diferencia", no incondicional) y para el resumen del turno con
 * ingresos/salidas (HU-F12.1, mismo KPI que `<MiTurnoPanel>` /
 * `<ResumenTurno>`).
 *
 * NOTA: NO usar `.toBeInTheDocument()` — hay un bug preexistente de
 * infra (dos instalaciones de `vitest` en el monorepo) que rompe el
 * registro de matchers `jest-dom` en este workspace (fuera de alcance
 * de este fix, reportado aparte). Se usan matchers nativos de vitest
 * (`toBeNull`, `toBe`, etc.) que no dependen de esa extensión.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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
// crosses the wire). Tests drive that verdict directly instead of via
// `efectivoReportado`/`datafonoReportado` props.
const useRequiereJustificacionMock = vi.fn();
vi.mock('../hooks/useRequiereJustificacion', () => ({
  useRequiereJustificacion: (
    uuid_sesion: string | null,
    efectivo: number,
    datafono: number,
  ) => useRequiereJustificacionMock(uuid_sesion, efectivo, datafono),
}));

const SESION: SesionRead = {
  uuid: 'sess-uuid-1',
  uuid_sucursal: 'suc-uuid-1',
  uuid_usuario: 'usr-uuid-1',
  valor_inicial_efectivo: 733_000,
  valor_inicial_datafono: 211_000,
  timestamp_apertura: '2026-09-21T08:00:00Z',
  timestamp_cierre: null,
};

function Harness({
  sesion = SESION,
  efectivoReportado = sesion.valor_inicial_efectivo,
  // El campo `valor_inicial_datafono` sigue en `SesionRead` (mock línea 51)
  // aunque la UI no muestre el datafono inicial en el resumen
  // (fix/electron-sucursal-datafono-display). El form de cierre sigue
  // aceptando un `valor_datafono_reportado` que el operador tipea al
  // cerrar — por eso el default de `datafonoReportado` se mantiene.
  datafonoReportado = sesion.valor_inicial_datafono,
  forceRequireJustificacion = false,
  error = null,
}: {
  sesion?: SesionRead;
  efectivoReportado?: number;
  datafonoReportado?: number;
  forceRequireJustificacion?: boolean;
  error?: Parameters<typeof CerrarTurnoForm>[0]['error'];
}): JSX.Element {
  const form = useForm<CerrarTurnoInput>({
    resolver: zodResolver(cerrarTurnoSchema),
    defaultValues: {
      valor_efectivo_reportado: efectivoReportado,
      valor_datafono_reportado: datafonoReportado,
      justificacion: '',
      observaciones_cierre: '',
    },
  });
  return (
    <CerrarTurnoForm
      form={form}
      onSubmit={async () => {}}
      isSubmitting={false}
      error={error}
      sesion={sesion}
      onCancel={() => {}}
      requiredMode="cierre_turno"
      forceRequireJustificacion={forceRequireJustificacion}
    />
  );
}

beforeEach(() => {
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

describe('<CerrarTurnoForm /> — justificación condicional (conteo ciego)', () => {
  it('sin diferencia (reportado === inicial) → el campo justificación NO existe en el DOM', () => {
    render(<Harness />);

    expect(screen.queryByTestId('cerrar-turno-required-justificacion')).toBeNull();
    expect(screen.queryByTestId('cerrar-turno-justificacion')).toBeNull();
  });

  it('con diferencia → el campo aparece, es obligatorio (min 3), y no expone ningún monto de esperado/diferencia', () => {
    // El backend (useRequiereJustificacion) confirma que hay diferencia
    // — el componente ya NO decide esto comparando contra valor_inicial_*.
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: true,
      error: undefined,
    });
    render(<Harness efectivoReportado={900_000} datafonoReportado={211_000} />);

    const justificacionInput = screen.queryByTestId('cerrar-turno-required-justificacion');
    expect(justificacionInput).not.toBeNull();

    const confirmarBtn = screen.getByTestId('cerrar-turno-confirmar') as HTMLButtonElement;
    expect(confirmarBtn.disabled).toBe(true);

    fireEvent.change(justificacionInput as HTMLElement, {
      target: { value: 'Faltante en caja' },
    });
    expect((screen.getByTestId('cerrar-turno-confirmar') as HTMLButtonElement).disabled).toBe(
      false,
    );

    // Conteo ciego: el MONTO de la diferencia (167.000 / 167000) NUNCA
    // debe aparecer en el DOM, ni siquiera oculto. El texto genérico
    // ("hay una diferencia respecto a lo esperado") SÍ es esperable —
    // lo prohibido es el número, no la palabra.
    const html = document.body.innerHTML;
    expect(html).not.toContain('167000');
    expect(html).not.toContain('167.000');
  });

  it('con diferencia solo en datáfono → también exige justificación', () => {
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: true,
      error: undefined,
    });
    render(<Harness efectivoReportado={733_000} datafonoReportado={180_000} />);
    expect(screen.queryByTestId('cerrar-turno-required-justificacion')).not.toBeNull();
  });

  // REGRESSION (2026-09-25, bug real encontrado en vivo; fix 2026-10-01):
  // el backend calcula el esperado real (inicial + transacciones del
  // turno) SOLO server-side (conteo ciego). El heurístico `difTotal`
  // original comparaba contra `valor_inicial_*` client-side y daba falso
  // negativo en cuanto el turno tenía CUALQUIER transacción — reemplazado
  // por `useRequiereJustificacion` (ver arriba), que corre el mismo
  // cálculo en el backend. Este test ahora cubre el caso residual: una
  // condición de carrera entre el pre-flight (debounced) y el POST real
  // — `forceRequireJustificacion` sigue siendo la red de seguridad para
  // ese caso, incluso si el pre-flight responde `requiereJustificacion:
  // false` (stale).
  it('useRequiereJustificacion responde false (stale) pero forceRequireJustificacion=true (backend ya rechazó el POST real) → el campo aparece igual y es obligatorio', () => {
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: false,
      error: undefined,
    });
    render(<Harness forceRequireJustificacion />);

    const justificacionInput = screen.queryByTestId('cerrar-turno-required-justificacion');
    expect(justificacionInput).not.toBeNull();

    const confirmarBtn = screen.getByTestId('cerrar-turno-confirmar') as HTMLButtonElement;
    expect(confirmarBtn.disabled).toBe(true);

    fireEvent.change(justificacionInput as HTMLElement, {
      target: { value: 'Descuadre reportado por el backend' },
    });
    expect((screen.getByTestId('cerrar-turno-confirmar') as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it('mientras useRequiereJustificacion está cargando (undefined) → conservador: campo visible y botón disabled, nunca asume "sin diferencia"', () => {
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: undefined,
      error: undefined,
    });
    render(<Harness />);

    expect(screen.queryByTestId('cerrar-turno-required-justificacion')).not.toBeNull();
    expect((screen.getByTestId('cerrar-turno-confirmar') as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
});

describe('<CerrarTurnoForm /> — banner explicativo del botón disabled (Cambio 1)', () => {
  it('aparece cuando el botón está disabled por falta de justificación', () => {
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: true,
      error: undefined,
    });
    render(<Harness />);

    expect(screen.queryByTestId('cerrar-turno-boton-disabled-motivo')).not.toBeNull();
  });

  it('desaparece en cuanto se completa una justificación válida (botón habilitado)', () => {
    useRequiereJustificacionMock.mockReturnValue({
      requiereJustificacion: true,
      error: undefined,
    });
    render(<Harness />);

    fireEvent.change(screen.getByTestId('cerrar-turno-required-justificacion'), {
      target: { value: 'Motivo válido' },
    });

    expect(screen.queryByTestId('cerrar-turno-boton-disabled-motivo')).toBeNull();
  });

  it('no aparece cuando el backend confirma que no hace falta justificación', () => {
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
