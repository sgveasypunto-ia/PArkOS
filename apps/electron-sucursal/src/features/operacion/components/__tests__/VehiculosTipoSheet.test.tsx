/**
 * `<CuposLibresStrip />` chips → `<VehiculosTipoSheet />`: placas dentro por
 * tipo + acciones que enrutan a los drawers existentes (salida / reimpresión).
 * Sólo se monta el sheet (no `<DrawerHost />`): se afirma sobre el store.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const raw =
        (opts?.defaultValue as string | undefined) ??
        (opts?.count === 1
          ? (opts?.defaultValue_one as string | undefined)
          : (opts?.defaultValue_other as string | undefined)) ??
        key;
      return raw.replace(/\{\{(\w+)\}\}/g, (_m, k: string) => String(opts?.[k] ?? ''));
    },
  }),
}));

const useOcupacionMock = vi.fn();
vi.mock('../../hooks/useOcupacion', () => ({
  useOcupacion: (...args: unknown[]) => useOcupacionMock(...args),
}));
const useIngresosActivosMock = vi.fn();
vi.mock('../../hooks/useIngresosActivos', () => ({
  useIngresosActivos: (...args: unknown[]) => useIngresosActivosMock(...args),
}));
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({ sucursal: { uuid: 'suc-1' } }),
}));

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { CuposLibresStrip } from '../CuposLibresStrip';
import { VehiculosTipoSheet } from '../VehiculosTipoSheet';

const T_CARRO = '00000000-0000-0000-0000-0000000000c1';
const T_MOTO = '00000000-0000-0000-0000-0000000000a2';
const T_BICI = '00000000-0000-0000-0000-0000000000b3';

const OCUPACION = {
  uuid_sucursal: 'suc-1',
  generado_en: '2026-10-14T10:00:00Z',
  items: [
    { uuid_tipo_vehiculo: T_CARRO, tipo: 'CARRO', cupo_maximo: 30, activos: 2, disponible: 28 },
    { uuid_tipo_vehiculo: T_MOTO, tipo: 'MOTO', cupo_maximo: 20, activos: 1, disponible: 19 },
    { uuid_tipo_vehiculo: T_BICI, tipo: 'BICICLETA', cupo_maximo: 12, activos: 0, disponible: 12 },
  ],
};

function ingreso(
  uuid: string,
  placa: string | null,
  uuid_tipo_vehiculo: string,
  consecutivo: string | null = null,
): Record<string, unknown> {
  return {
    uuid,
    placa,
    consecutivo,
    uuid_tipo_vehiculo,
    uuid_sucursal: 'suc-1',
    fecha_ingreso: '2026-10-14T15:30:00Z',
    created_at: '2026-10-14T15:30:00Z',
  };
}

const INGRESOS = [
  ingreso('i-1', 'ABC123', T_CARRO),
  ingreso('i-2', 'XYZ987', T_CARRO),
  ingreso('i-3', 'MOT11A', T_MOTO),
];

function renderAll(): ReturnType<typeof render> {
  return render(
    <>
      <CuposLibresStrip uuid_sucursal="suc-1" />
      <VehiculosTipoSheet />
    </>,
  );
}

beforeEach(() => {
  useOcupacionMock.mockReset();
  useIngresosActivosMock.mockReset();
  useOcupacionMock.mockReturnValue({ data: OCUPACION, error: undefined, isStale: false, refresh: vi.fn() });
  useIngresosActivosMock.mockReturnValue(INGRESOS);
  useDashboardDrawerStore.getState().close();
});
afterEach(() => {
  cleanup();
});

describe('chips de cupos como botones', () => {
  it('exponen aria-haspopup/expanded y una etiqueta con ocupados y total', () => {
    renderAll();
    const chip = screen.getByTestId('cupos-libres-strip-chip-CARRO');
    expect(chip.tagName).toBe('BUTTON');
    expect(chip.getAttribute('aria-haspopup')).toBe('dialog');
    expect(chip.getAttribute('aria-expanded')).toBe('false');
    expect(chip.getAttribute('aria-label')).toBe('CARRO: 2 de 30 ocupados, ver placas');
  });

  it('click abre el sheet sólo con las placas de ese tipo y marca aria-expanded', () => {
    renderAll();
    fireEvent.click(screen.getByTestId('cupos-libres-strip-chip-CARRO'));

    const dialog = screen.getByRole('dialog');
    expect(dialog).toBe(screen.getByTestId('vehiculos-tipo-sheet'));
    expect(dialog.getAttribute('aria-labelledby')).toBe('vehiculos-tipo-title');
    expect(within(dialog).getByText('CARRO')).not.toBeNull();
    expect(within(dialog).getByTestId('vehiculos-tipo-row-i-1').textContent).toContain('ABC123');
    expect(within(dialog).getByTestId('vehiculos-tipo-row-i-2').textContent).toContain('XYZ987');
    expect(within(dialog).queryByTestId('vehiculos-tipo-row-i-3')).toBeNull();
    // El conteo del sheet coincide con el del chip (2).
    expect(within(dialog).getByTestId('vehiculos-tipo-count').textContent).toContain('2');
    expect(screen.getByTestId('cupos-libres-strip-chip-CARRO').getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByTestId('cupos-libres-strip-chip-MOTO').getAttribute('aria-expanded')).toBe('false');
  });

  it('muestra el tipo que el catálogo trae, no sólo carro/moto', () => {
    renderAll();
    fireEvent.click(screen.getByTestId('cupos-libres-strip-chip-MOTO'));
    expect(screen.getByTestId('vehiculos-tipo-row-i-3')).not.toBeNull();
    expect(screen.queryByTestId('vehiculos-tipo-row-i-1')).toBeNull();
  });

  it('estado vacío cuando el tipo no tiene vehículos dentro', () => {
    renderAll();
    fireEvent.click(screen.getByTestId('cupos-libres-strip-chip-BICICLETA'));
    expect(screen.getByTestId('vehiculos-tipo-empty')).not.toBeNull();
    expect(screen.queryByTestId('vehiculos-tipo-list')).toBeNull();
    expect(screen.queryByTestId('vehiculos-tipo-search')).toBeNull();
  });

  it('el buscador filtra por placa dentro del tipo', () => {
    renderAll();
    fireEvent.click(screen.getByTestId('cupos-libres-strip-chip-CARRO'));
    fireEvent.change(screen.getByTestId('vehiculos-tipo-search'), { target: { value: 'xyz' } });
    expect(screen.queryByTestId('vehiculos-tipo-row-i-1')).toBeNull();
    expect(screen.getByTestId('vehiculos-tipo-row-i-2')).not.toBeNull();
    fireEvent.change(screen.getByTestId('vehiculos-tipo-search'), { target: { value: 'nope' } });
    expect(screen.getByTestId('vehiculos-tipo-no-match')).not.toBeNull();
  });

  it('Escape cierra el sheet y limpia el store', () => {
    renderAll();
    fireEvent.click(screen.getByTestId('cupos-libres-strip-chip-CARRO'));
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByTestId('vehiculos-tipo-sheet')).toBeNull();
    const st = useDashboardDrawerStore.getState();
    expect(st.openDrawer).toBeNull();
    expect(st.tipoVehiculoUuid).toBeNull();
  });
});

describe('acciones de fila', () => {
  it('"Registrar salida" abre el drawer de salida con la placa y reemplaza al sheet', () => {
    renderAll();
    fireEvent.click(screen.getByTestId('cupos-libres-strip-chip-CARRO'));
    fireEvent.click(screen.getByTestId('vehiculos-tipo-salida-i-2'));

    const st = useDashboardDrawerStore.getState();
    expect(st.openDrawer).toBe('salida');
    expect(st.initialPlaca).toBe('XYZ987');
    expect(st.initialUuidIngreso).toBeNull();
    expect(st.tipoVehiculoUuid).toBeNull();
    expect(screen.queryByTestId('vehiculos-tipo-sheet')).toBeNull();
  });

  it('sin placa, la salida viaja con el uuid_ingreso (igual que "Vehículos dentro")', () => {
    useIngresosActivosMock.mockReturnValue([ingreso('i-9', null, T_BICI, 'BICICLETA-000001-abcd1234')]);
    renderAll();
    fireEvent.click(screen.getByTestId('cupos-libres-strip-chip-BICICLETA'));
    fireEvent.click(screen.getByTestId('vehiculos-tipo-salida-i-9'));

    const st = useDashboardDrawerStore.getState();
    expect(st.openDrawer).toBe('salida');
    expect(st.initialPlaca).toBeNull();
    expect(st.initialUuidIngreso).toBe('i-9');
  });

  it('"Reimprimir ticket" abre el drawer de reimpresión con la placa como término', () => {
    renderAll();
    fireEvent.click(screen.getByTestId('cupos-libres-strip-chip-CARRO'));
    fireEvent.click(screen.getByTestId('vehiculos-tipo-reimprimir-i-1'));

    const st = useDashboardDrawerStore.getState();
    expect(st.openDrawer).toBe('reimpresion');
    expect(st.initialPlaca).toBe('ABC123');
    expect(screen.queryByTestId('vehiculos-tipo-sheet')).toBeNull();
  });

  it('sin placa, la reimpresión usa el consecutivo como término', () => {
    useIngresosActivosMock.mockReturnValue([ingreso('i-9', null, T_BICI, 'BICICLETA-000001-abcd1234')]);
    renderAll();
    fireEvent.click(screen.getByTestId('cupos-libres-strip-chip-BICICLETA'));
    fireEvent.click(screen.getByTestId('vehiculos-tipo-reimprimir-i-9'));
    expect(useDashboardDrawerStore.getState().initialPlaca).toBe('BICICLETA-000001-abcd1234');
  });
});
