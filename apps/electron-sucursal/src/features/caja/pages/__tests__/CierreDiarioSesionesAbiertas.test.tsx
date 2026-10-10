/**
 * Caja bug 4 — el Cierre Diario debe explicar por qué el botón está
 * deshabilitado cuando hay sesiones abiertas y mostrar "abiertas/total".
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useForm } from 'react-hook-form';

import { CierreDiarioForm } from '../CierreDiarioForm';
import type { ArqueoResumenPorSesion } from '../../hooks/useArqueoResumenPorSesion';

type Sesiones = ArqueoResumenPorSesion['sesiones'];

const ABIERTA = {
  uuid_sesion: '44444444-5555-4666-8777-888888888888',
  uuid_usuario: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
  timestamp_apertura: '2026-09-21T08:00:00Z',
  timestamp_cierre: null,
  estado: 'abierta',
  valor_efectivo_esperado: null,
  valor_efectivo_reportado: null,
  uuid_arqueo: null,
};
const CERRADA = {
  ...ABIERTA,
  uuid_sesion: '22222222-3333-4444-8555-666666666666',
  timestamp_cierre: '2026-09-21T18:00:00Z',
  estado: 'cerrada',
  valor_efectivo_esperado: 50_000,
  valor_efectivo_reportado: 50_000,
  uuid_arqueo: 'cccccccc-dddd-4eee-8fff-111111111111',
};

function Host(props: { sesiones: Sesiones; reportado: number }): JSX.Element {
  const form = useForm({
    defaultValues: { valor_efectivo_reportado: 0, justificacion: '' },
  });
  return (
    <CierreDiarioForm
      sesiones={props.sesiones}
      totals={{ valor_efectivo_reportado: props.reportado, diferencia: 0 }}
      cierreDiaExists={false}
      isSubmitting={false}
      fecha="2026-09-21"
      form={form as unknown as Parameters<typeof CierreDiarioForm>[0]['form']}
      onSubmit={vi.fn().mockResolvedValue(undefined)}
      onCancel={vi.fn()}
    />
  );
}

describe('CierreDiarioForm — sesiones abiertas (Caja bug 4)', () => {
  it('1 sesión abierta: mensaje singular, botón deshabilitado y vinculado, Σ = 1/1', () => {
    render(<Host sesiones={[ABIERTA]} reportado={0} />);
    const msg = screen.getByTestId('cierre-diario-sesiones-abiertas');
    expect(msg).toHaveTextContent(
      'Hay 1 sesión abierta. Ciérrela antes de hacer el cierre diario.',
    );
    expect(msg).toHaveAttribute('role', 'status');
    const btn = screen.getByTestId('cierre-diario-confirmar');
    expect(btn).toBeDisabled();
    expect(btn.getAttribute('aria-describedby')).toContain(msg.id);
    expect(screen.getByTestId('cierre-diario-totals')).toHaveTextContent(
      /Σ\s*1\/1/,
    );
  });

  it('N sesiones abiertas: mensaje plural y Σ = N/total', () => {
    render(
      <Host
        sesiones={[
          ABIERTA,
          { ...ABIERTA, uuid_sesion: '55555555-5555-4666-8777-888888888888' },
          CERRADA,
        ]}
        reportado={50_000}
      />,
    );
    expect(
      screen.getByTestId('cierre-diario-sesiones-abiertas'),
    ).toHaveTextContent(
      'Hay 2 sesiones abiertas. Ciérrelas antes de hacer el cierre diario.',
    );
    expect(screen.getByTestId('cierre-diario-confirmar')).toBeDisabled();
    expect(screen.getByTestId('cierre-diario-totals')).toHaveTextContent(
      /Σ\s*2\/3/,
    );
  });

  it('sin sesiones abiertas: sin mensaje, botón habilitado y Σ = 0/1', () => {
    render(<Host sesiones={[CERRADA]} reportado={50_000} />);
    expect(
      screen.queryByTestId('cierre-diario-sesiones-abiertas'),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId('cierre-diario-confirmar')).toBeEnabled();
    expect(
      screen.getByTestId('cierre-diario-confirmar').getAttribute(
        'aria-describedby',
      ),
    ).toBeNull();
    expect(screen.getByTestId('cierre-diario-totals')).toHaveTextContent(
      /Σ\s*0\/1/,
    );
  });

  it('la insignia de estado distingue cerrada de abierta con el estado real del backend', () => {
    render(<Host sesiones={[ABIERTA, CERRADA]} reportado={50_000} />);
    const filas = screen.getAllByTestId('cierre-diario-sesion-row');
    expect(filas[0].querySelector('span')?.className).toContain('bg-warning');
    expect(filas[1].querySelector('span')?.className).toContain('bg-success');
  });

  it('el encabezado de la columna de hora dice "Apertura", no "Base"', () => {
    render(<Host sesiones={[ABIERTA]} reportado={0} />);
    const encabezados = screen
      .getAllByRole('columnheader')
      .map((th) => th.textContent?.trim());
    expect(encabezados).toContain('Apertura');
    expect(encabezados).not.toContain('Base');
    // La celda de esa columna muestra una hora, no un monto.
    const celdas = screen
      .getByTestId('cierre-diario-sesion-row')
      .querySelectorAll('td');
    expect(celdas[1]?.textContent).not.toMatch(/\$/);
  });
});
