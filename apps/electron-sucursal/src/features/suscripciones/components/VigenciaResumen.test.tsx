/**
 * `<VigenciaResumen />` — fecha de fin editable (solo acortar).
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { VigenciaResumen } from './VigenciaResumen';

afterEach(cleanup);

const input = (): HTMLInputElement =>
  screen.getByTestId('venta-vigencia-fin-input') as HTMLInputElement;

describe('<VigenciaResumen /> fin editable', () => {
  it('sin edicion muestra el fin del plan y el input limita min/max', () => {
    render(<VigenciaResumen fechaInicio="2026-10-01" duracionDias={30} onFechaFinChange={vi.fn()} />);
    expect(screen.getByTestId('venta-vigencia-fin').textContent).toBe('30/10/2026');
    expect(input().type).toBe('date');
    expect(input().min).toBe('2026-10-01');
    expect(input().max).toBe('2026-10-30');
    expect(input().value).toBe('2026-10-30');
    expect(input().getAttribute('aria-invalid')).toBeNull();
    expect(screen.queryByTestId('venta-vigencia-fin-error')).toBeNull();
  });

  it('editar la fecha notifica el nuevo valor', () => {
    const onChange = vi.fn();
    render(<VigenciaResumen fechaInicio="2026-10-01" duracionDias={30} onFechaFinChange={onChange} />);
    fireEvent.change(input(), { target: { value: '2026-10-15' } });
    expect(onChange).toHaveBeenCalledWith('2026-10-15');
  });

  it('con una fecha editada valida el resumen la refleja', () => {
    render(
      <VigenciaResumen
        fechaInicio="2026-10-01"
        duracionDias={30}
        fechaFin="2026-10-15"
        onFechaFinChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId('venta-vigencia-fin').textContent).toBe('15/10/2026');
    expect(input().value).toBe('2026-10-15');
    expect(input().getAttribute('aria-invalid')).toBeNull();
  });

  it('fecha mayor al fin del plan: mensaje accesible junto al campo', () => {
    render(
      <VigenciaResumen
        fechaInicio="2026-10-01"
        duracionDias={30}
        fechaFin="2026-11-05"
        onFechaFinChange={vi.fn()}
      />,
    );
    const err = screen.getByTestId('venta-vigencia-fin-error');
    expect(err.getAttribute('role')).toBe('alert');
    expect(err.className).toMatch(/text-destructive/);
    expect(err.textContent).toMatch(/despues_maximo/);
    expect(input().getAttribute('aria-invalid')).toBe('true');
    expect(input().getAttribute('aria-describedby')).toContain(err.id);
    // El resumen no muestra una vigencia invalida como valida.
    expect(screen.getByTestId('venta-vigencia-fin').textContent).toBe('30/10/2026');
  });

  it('fecha anterior al inicio: error antes_inicio', () => {
    render(
      <VigenciaResumen
        fechaInicio="2026-10-01"
        duracionDias={30}
        fechaFin="2026-09-20"
        onFechaFinChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId('venta-vigencia-fin-error').textContent).toMatch(/antes_inicio/);
  });

  it('el error del servidor tiene prioridad y es accesible', () => {
    render(
      <VigenciaResumen
        fechaInicio="2026-10-01"
        duracionDias={30}
        fechaFin="2026-10-15"
        errorServidor="El servidor rechazo la fecha"
        onFechaFinChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId('venta-vigencia-fin-error').textContent).toBe(
      'El servidor rechazo la fecha',
    );
    expect(input().getAttribute('aria-invalid')).toBe('true');
  });

  it('"usar fin del plan" restablece (null)', () => {
    const onChange = vi.fn();
    render(
      <VigenciaResumen
        fechaInicio="2026-10-01"
        duracionDias={30}
        fechaFin="2026-10-15"
        onFechaFinChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId('venta-vigencia-fin-restablecer'));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('focusSignal enfoca el input', () => {
    const { rerender } = render(
      <VigenciaResumen fechaInicio="2026-10-01" duracionDias={30} onFechaFinChange={vi.fn()} focusSignal={0} />,
    );
    expect(document.activeElement).not.toBe(input());
    rerender(
      <VigenciaResumen fechaInicio="2026-10-01" duracionDias={30} onFechaFinChange={vi.fn()} focusSignal={1} />,
    );
    expect(document.activeElement).toBe(input());
  });

  it('sin onFechaFinChange es solo lectura (compatibilidad)', () => {
    render(<VigenciaResumen fechaInicio="2026-10-01" duracionDias={30} />);
    expect(screen.queryByTestId('venta-vigencia-fin-input')).toBeNull();
    expect(screen.getByTestId('venta-vigencia-fin').textContent).toBe('30/10/2026');
  });
});
