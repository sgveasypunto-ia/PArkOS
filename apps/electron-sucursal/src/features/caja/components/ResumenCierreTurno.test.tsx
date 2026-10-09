/**
 * `<ResumenCierreTurno />` — read-only post-close summary (PT-5).
 *
 * NOTA: sin `.toBeInTheDocument()` (bug de infra preexistente con jest-dom,
 * ver `CerrarTurnoForm.test.tsx`).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import '@/i18n';

import { ResumenCierreTurno } from './ResumenCierreTurno';
import type { SesionRead } from '../api/sesionActivaApi';
import type { ResumenCierreTurnoRead } from '../../../lib/api/schemas/resumen-cierre-turno';

const descargarMock = vi.fn();
vi.mock('../../../lib/print/resumenCierrePdf', () => ({
  descargarResumenCierrePdf: (data: unknown) => descargarMock(data),
}));

const SESION: SesionRead = {
  uuid: '11111111-2222-4333-8444-555555555555',
  uuid_sucursal: 'suc-1',
  uuid_usuario: 'usr-1',
  valor_inicial_efectivo: 50_000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-09-15T13:00:00Z',
  timestamp_cierre: '2026-09-15T23:00:00Z',
};

const RESUMEN: ResumenCierreTurnoRead = {
  uuid_sesion: SESION.uuid,
  uuid_sucursal: 'suc-1',
  timestamp_calculo: '2026-09-15T23:00:00',
  ingresos_count: 9,
  salidas_count: 8,
  transacciones_count: 6,
  medios_pago: [
    { medio_pago: 'efectivo', pagos_count: 4, total_cop: 40_000 },
    { medio_pago: 'datafono', pagos_count: 2, total_cop: 30_000 },
  ],
  reversos_count: 0,
  reversos_total_cop: 0,
};

const ARQUEO = {
  uuid: 'arqueo-1',
  valor_efectivo_esperado: 90_000,
  valor_efectivo_reportado: 75_000,
  diferencia_efectivo: -15_000,
};

beforeEach(() => {
  descargarMock.mockReset();
  descargarMock.mockResolvedValue(undefined);
});

describe('<ResumenCierreTurno /> — producido y base entregada', () => {
  it('deriva el producido (contado − base) y muestra la base que pasa al siguiente turno', () => {
    render(
      <ResumenCierreTurno
        sesion={SESION}
        arqueo={ARQUEO}
        resumen={null}
        onFinalizar={() => {}}
      />,
    );

    const text = screen.getByTestId('resumen-cierre-turno').textContent ?? '';
    expect(text).toContain('Producido consignado');
    expect(text).toContain('25.000'); // 75.000 contado − 50.000 base
    expect(text).toContain('Base entregada al siguiente turno');
  });

  it('prefiere las cifras del servidor cuando vienen en el resumen', () => {
    render(
      <ResumenCierreTurno
        sesion={SESION}
        arqueo={ARQUEO}
        resumen={{ ...RESUMEN, base_entregada: 50_000, efectivo_reportado: 75_000, producido: 31_000 }}
        onFinalizar={() => {}}
      />,
    );

    const text = screen.getByTestId('resumen-cierre-turno').textContent ?? '';
    expect(text).toContain('31.000');
  });
});

describe('<ResumenCierreTurno />', () => {
  it('muestra TODOS los datos: base, esperado vs contado, diferencia, hora de cierre, nº de transacciones, totales por medio y observaciones', () => {
    render(
      <ResumenCierreTurno
        sesion={SESION}
        arqueo={ARQUEO}
        observaciones="Faltante en caja"
        resumen={RESUMEN}
        onFinalizar={() => {}}
      />,
    );

    const text = screen.getByTestId('resumen-cierre-turno').textContent ?? '';
    expect(text).toContain('Hora de cierre');
    expect(text).toContain('Base (efectivo inicial)');
    expect(text).toContain('50.000');
    expect(text).toContain('Efectivo esperado');
    expect(text).toContain('90.000');
    expect(text).toContain('Efectivo contado');
    expect(text).toContain('75.000');
    expect(text).toContain('-$');
    expect(text).toContain('15.000');
    expect(text).toContain('Transacciones (pagos)');
    expect(text).toContain('Efectivo (4)');
    expect(text).toContain('Datáfono (2)');
    expect(text).toContain('Faltante en caja');
    // Sin reversos → sin línea de reversos.
    expect(text).not.toContain('Reversos');
  });

  it('diferencia positiva lleva signo +, y sin diferencia muestra $ 0 sin signo', () => {
    const { rerender } = render(
      <ResumenCierreTurno
        sesion={SESION}
        arqueo={{ ...ARQUEO, valor_efectivo_reportado: 95_000, diferencia_efectivo: 5_000 }}
        resumen={RESUMEN}
        onFinalizar={() => {}}
      />,
    );
    expect(screen.getByTestId('resumen-cierre-turno').textContent).toContain('+$');

    rerender(
      <ResumenCierreTurno
        sesion={SESION}
        arqueo={{ ...ARQUEO, valor_efectivo_reportado: 90_000, diferencia_efectivo: 0 }}
        resumen={RESUMEN}
        onFinalizar={() => {}}
      />,
    );
    const text = screen.getByTestId('resumen-cierre-turno').textContent ?? '';
    expect(text).not.toContain('+$');
    expect(text).not.toContain('-$');
  });

  it('sin observaciones no renderiza la sección de observaciones', () => {
    render(
      <ResumenCierreTurno
        sesion={SESION}
        arqueo={ARQUEO}
        resumen={RESUMEN}
        onFinalizar={() => {}}
      />,
    );
    expect(screen.getByTestId('resumen-cierre-turno').textContent).not.toContain(
      'Observaciones del cierre',
    );
  });

  it('con reversos los muestra en línea aparte', () => {
    render(
      <ResumenCierreTurno
        sesion={SESION}
        arqueo={ARQUEO}
        resumen={{ ...RESUMEN, reversos_count: 2, reversos_total_cop: 12_000 }}
        onFinalizar={() => {}}
      />,
    );
    const text = screen.getByTestId('resumen-cierre-turno').textContent ?? '';
    expect(text).toContain('Reversos (2)');
    expect(text).toContain('12.000');
  });

  it('PT-6: no muestra ningún campo de base/contado de datáfono', () => {
    render(
      <ResumenCierreTurno
        sesion={{ ...SESION, valor_inicial_datafono: 123_456 }}
        arqueo={ARQUEO}
        resumen={RESUMEN}
        onFinalizar={() => {}}
      />,
    );
    const text = screen.getByTestId('resumen-cierre-turno').textContent ?? '';
    expect(text).not.toContain('123.456');
    expect(text).not.toMatch(/datáfono (esperado|contado)/i);
  });

  it('"Descargar PDF" entrega al generador las mismas secciones que se ven en pantalla', async () => {
    render(
      <ResumenCierreTurno
        sesion={SESION}
        arqueo={ARQUEO}
        observaciones="Nota"
        resumen={RESUMEN}
        onFinalizar={() => {}}
      />,
    );

    fireEvent.click(screen.getByTestId('resumen-cierre-descargar-pdf'));

    await waitFor(() => expect(descargarMock).toHaveBeenCalledTimes(1));
    const data = descargarMock.mock.calls[0]?.[0] as {
      fileName: string;
      sections: { heading: string; rows: { label: string; value: string }[] }[];
    };
    expect(data.fileName).toBe('cierre-turno-11111111');
    const headings = data.sections.map((s) => s.heading);
    expect(headings).toEqual([
      'Turno',
      'Cuadre de efectivo',
      'Actividad del turno',
      'Totales por medio de pago',
      'Observaciones',
    ]);
    const onScreen = screen.getByTestId('resumen-cierre-turno').textContent ?? '';
    for (const section of data.sections) {
      for (const row of section.rows) {
        expect(onScreen).toContain(row.label);
        expect(onScreen).toContain(row.value);
      }
    }
  });

  it('si el PDF falla muestra un error y NO finaliza', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    descargarMock.mockRejectedValueOnce(new Error('pdf boom'));
    const onFinalizar = vi.fn();
    render(
      <ResumenCierreTurno
        sesion={SESION}
        arqueo={ARQUEO}
        resumen={RESUMEN}
        onFinalizar={onFinalizar}
      />,
    );

    fireEvent.click(screen.getByTestId('resumen-cierre-descargar-pdf'));

    await waitFor(() => expect(screen.queryByTestId('resumen-cierre-pdf-error')).not.toBeNull());
    expect(onFinalizar).not.toHaveBeenCalled();
  });

  it('"Finalizar y salir" invoca onFinalizar', () => {
    const onFinalizar = vi.fn();
    render(
      <ResumenCierreTurno
        sesion={SESION}
        arqueo={ARQUEO}
        resumen={RESUMEN}
        onFinalizar={onFinalizar}
      />,
    );
    fireEvent.click(screen.getByTestId('resumen-cierre-finalizar'));
    expect(onFinalizar).toHaveBeenCalledTimes(1);
  });

  it('sin resumen (endpoint caído) sigue mostrando el cuadre de efectivo y avisa que el detalle no está disponible', () => {
    render(
      <ResumenCierreTurno
        sesion={SESION}
        arqueo={ARQUEO}
        resumen={null}
        onFinalizar={() => {}}
      />,
    );
    const text = screen.getByTestId('resumen-cierre-turno').textContent ?? '';
    expect(text).toContain('Efectivo esperado');
    expect(text).toContain('No disponible');
    expect(text).not.toContain('Totales por medio de pago');
  });

  it('arqueo sin campos de reconciliación (respuesta mínima) → guiones, sin romper', () => {
    render(
      <ResumenCierreTurno
        sesion={SESION}
        arqueo={{ uuid: 'arqueo-1' }}
        resumen={RESUMEN}
        onFinalizar={() => {}}
      />,
    );
    expect(screen.getByTestId('resumen-cierre-turno').textContent).toContain('—');
  });
});
