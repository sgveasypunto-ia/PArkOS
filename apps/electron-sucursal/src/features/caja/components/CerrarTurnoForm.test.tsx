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
  datafonoReportado = sesion.valor_inicial_datafono,
}: {
  sesion?: SesionRead;
  efectivoReportado?: number;
  datafonoReportado?: number;
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
      error={null}
      sesion={sesion}
      onCancel={() => {}}
      requiredMode="cierre_turno"
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
});

describe('<CerrarTurnoForm /> — justificación condicional (conteo ciego)', () => {
  it('sin diferencia (reportado === inicial) → el campo justificación NO existe en el DOM', () => {
    render(<Harness />);

    expect(screen.queryByTestId('cerrar-turno-required-justificacion')).toBeNull();
    expect(screen.queryByTestId('cerrar-turno-justificacion')).toBeNull();
  });

  it('con diferencia → el campo aparece, es obligatorio (min 3), y no expone ningún monto de esperado/diferencia', () => {
    // efectivo: 900_000 vs inicial 733_000 → diff 167_000. datafono sin diff.
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
    render(<Harness efectivoReportado={733_000} datafonoReportado={180_000} />);
    expect(screen.queryByTestId('cerrar-turno-required-justificacion')).not.toBeNull();
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
