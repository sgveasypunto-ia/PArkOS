/**
 * RTL tests for `<CuposLibresStrip />` (footer del Dashboard).
 *
 * Cobertura (directiva del operador — footer más legible + tipos
 * deshabilitados nunca se muestran + rediseño 2026-09-24 más grande):
 *   S1: un tipo con `cupo_maximo === 0` (no habilitado en la sucursal)
 *       NO se renderiza como tarjeta.
 *   S2: un tipo habilitado muestra explícitamente su conteo de "libres"
 *       (`disponible`), no solo `activos/cupo_maximo`.
 *   S3: el total agregado de la derecha sigue sumando solo los tipos
 *       reales (cupo_maximo > 0) — comportamiento preexistente intacto.
 *   S4: si TODOS los tipos tienen `cupo_maximo === 0`, el footer
 *       muestra el estado vacío (ningún tipo real habilitado).
 *
 * Nota de infra: este proyecto declara `@testing-library/jest-dom/vitest`
 * en `test-setup.ts`, pero los matchers (`toBeInTheDocument`,
 * `toHaveTextContent`) no quedan registrados en este entorno (falla
 * "Invalid Chai property" incluso en un test mínimo sin imports de
 * componente) — gap de infraestructura preexistente, no introducido
 * por este cambio. Este archivo usa aserciones planas de DOM/vitest
 * (igual que el precedente `OcupacionStrip.test.tsx`, que tampoco usa
 * jest-dom) para no depender de ese matcher roto.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_ns: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _ns }),
}));

const useOcupacionMock = vi.fn();
vi.mock('../hooks/useOcupacion', () => ({
  useOcupacion: (...args: unknown[]) => useOcupacionMock(...args),
}));

import { CuposLibresStrip } from './CuposLibresStrip';
import type { OcupacionResponse } from '../api/ocupacionApi';

beforeEach(() => {
  useOcupacionMock.mockReset();
  cleanup();
});

const SAMPLE_MIXED: OcupacionResponse = {
  uuid_sucursal: '00000000-0000-0000-0000-000000000099',
  items: [
    {
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
      tipo: 'Auto',
      cupo_maximo: 50,
      activos: 23,
      disponible: 27,
    },
    {
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000002',
      tipo: 'Moto',
      cupo_maximo: 5,
      activos: 1,
      disponible: 4,
    },
    // Tipo NO habilitado en esta sucursal — nunca debe verse.
    {
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000003',
      tipo: 'Bicicleta',
      cupo_maximo: 0,
      activos: 0,
      disponible: 0,
    },
  ],
  generado_en: '2026-09-24T10:00:00Z',
};

describe('<CuposLibresStrip />', () => {
  it('S1: un tipo con cupo_maximo=0 (no habilitado) no se renderiza', () => {
    useOcupacionMock.mockReturnValue({ data: SAMPLE_MIXED, error: undefined, isStale: false, refresh: vi.fn() });
    render(<CuposLibresStrip uuid_sucursal="s1" />);

    expect(screen.getByTestId('cupos-libres-strip-row-Auto')).not.toBeNull();
    expect(screen.getByTestId('cupos-libres-strip-row-Moto')).not.toBeNull();
    expect(screen.queryByTestId('cupos-libres-strip-row-Bicicleta')).toBeNull();
  });

  it('S2: cada tipo habilitado muestra explícitamente sus cupos libres', () => {
    useOcupacionMock.mockReturnValue({ data: SAMPLE_MIXED, error: undefined, isStale: false, refresh: vi.fn() });
    render(<CuposLibresStrip uuid_sucursal="s1" />);

    const autoRow = screen.getByTestId('cupos-libres-strip-row-Auto');
    expect(autoRow.textContent).toContain('27');
    expect(autoRow.textContent).toMatch(/libres/i);
    expect(autoRow.textContent).toContain('23/50');

    const motoRow = screen.getByTestId('cupos-libres-strip-row-Moto');
    expect(motoRow.textContent).toContain('4');
    expect(motoRow.textContent).toMatch(/libres/i);
    expect(motoRow.textContent).toContain('1/5');
  });

  it('S3: el total agregado solo suma los tipos con cupo_maximo > 0 (27 + 4 = 31)', () => {
    useOcupacionMock.mockReturnValue({ data: SAMPLE_MIXED, error: undefined, isStale: false, refresh: vi.fn() });
    render(<CuposLibresStrip uuid_sucursal="s1" />);

    expect(screen.getByTestId('cupos-libres-strip-total').textContent).toContain('31');
  });

  it('S4: si ningún tipo está habilitado (todos cupo_maximo=0), el footer queda vacío', () => {
    useOcupacionMock.mockReturnValue({
      data: {
        ...SAMPLE_MIXED,
        items: [SAMPLE_MIXED.items[2]],
      },
      error: undefined,
      isStale: false,
      refresh: vi.fn(),
    });
    render(<CuposLibresStrip uuid_sucursal="s1" />);

    expect(screen.getByTestId('cupos-libres-strip-empty')).not.toBeNull();
    expect(screen.getByTestId('cupos-libres-strip-total').textContent).toContain('—');
  });
});
