/**
 * `SucursalDetalle.test.tsx` — invariantes del shell de 7 pestañas
 * (HU-F15.1, T5 "componente del shell").
 *
 *   T1: el contenedor de la página se monta con el nombre de la sucursal.
 *   T2: el tab por defecto es "General" (defaultValue en shadcn Tabs),
 *       muestra `<SucursalGeneralForm />`.
 *   T3: click en "Tarifas" embebe `<Tarifas />` tal cual (no duplica
 *       lógica -- se mockea el módulo real, no se reimplementa).
 *   T4: click en "Capacidad" embebe `<Cupos />` tal cual.
 *   T5: click en "Resoluciones"/"Caja"/"Documentos" muestra el
 *       placeholder "Próximamente".
 *   T6: click en "Bitácora" muestra `<SucursalBitacoraTab />` scopeada
 *       al uuid de la ruta.
 *
 * Child pages/components (`Tarifas`, `Cupos`, `SucursalGeneralForm`,
 * `SucursalBitacoraTab`) are mocked as stubs: each already has (or, for
 * the two new components, will have) its own test suite -- this file's
 * job is the SHELL (tab wiring, default tab, routing), not re-testing
 * their internals.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { SucursalProvider } from '@/lib/sucursal-context';

// `vi.mock(...)` factories are hoisted above every other top-level
// statement (including plain `const` declarations), so a mock factory
// cannot close over an ordinary module-level const -- `vi.hoisted` is
// the escape hatch: its own callback runs BEFORE the hoisted mocks, so
// the value is already initialized when they reference it.
const { SAMPLE_SUCURSAL } = vi.hoisted(() => ({
  SAMPLE_SUCURSAL: {
    uuid: '11111111-1111-1111-1111-111111111111',
    nombre: 'Sucursal Centro',
    direccion: 'Calle 1',
    telefono: '+573001234567',
    prefijo_nombre: 'CTR',
    ciudad: 'Bogota',
    horario: '24/7',
    uuid_tipo_sucursal: null,
    uuid_empresa: null,
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
}));

vi.mock('../../sucursales/api/sucursalesApi', () => ({
  getSucursal: vi.fn().mockResolvedValue(SAMPLE_SUCURSAL),
}));

vi.mock('../api/parametrizacionEfectivaApi', () => ({
  getParametrizacionEfectiva: vi.fn().mockResolvedValue({
    tarifasVigentes: 0,
    capacidadVigente: 0,
    resolucionesVigentes: 0,
  }),
}));

vi.mock('@/features/tarifas/pages/Tarifas', () => ({
  default: () => <div data-testid="tarifas-mock">Tarifas embebida</div>,
}));

vi.mock('@/features/cupos/pages/Cupos', () => ({
  default: () => <div data-testid="cupos-mock">Cupos embebida</div>,
}));

vi.mock('../components/SucursalGeneralForm', () => ({
  SucursalGeneralForm: () => <div data-testid="sucursal-general-form-mock">General mock</div>,
}));

vi.mock('../components/SucursalBitacoraTab', () => ({
  SucursalBitacoraTab: ({ uuidSucursal }: { uuidSucursal: string }) => (
    <div data-testid="sucursal-bitacora-mock">Bitácora mock para {uuidSucursal}</div>
  ),
}));

import SucursalDetalle from './SucursalDetalle';

function renderPage(): void {
  render(
    <MemoryRouter initialEntries={[`/sucursales/${SAMPLE_SUCURSAL.uuid}`]}>
      <SucursalProvider>
        <Routes>
          <Route path="/sucursales/:uuid" element={<SucursalDetalle />} />
        </Routes>
      </SucursalProvider>
    </MemoryRouter>,
  );
}

describe('SucursalDetalle', () => {
  it('T1: monta el contenedor de la página con el nombre de la sucursal', async () => {
    renderPage();
    expect(await screen.findByTestId('sucursal-detalle-page')).toBeInTheDocument();
    expect(screen.getByTestId('sucursal-detalle-nombre')).toHaveTextContent('Sucursal Centro');
  });

  it('T2: el tab por defecto es General y muestra SucursalGeneralForm', async () => {
    renderPage();
    expect(await screen.findByTestId('sucursal-tab-general')).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.getByTestId('sucursal-general-form-mock')).toBeInTheDocument();
  });

  it('T3: click en "Tarifas" embebe la pantalla Tarifas existente', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId('sucursal-detalle-page');
    await user.click(screen.getByTestId('sucursal-tab-tarifas'));
    expect(screen.getByTestId('sucursal-tab-tarifas')).toHaveAttribute('data-state', 'active');
    expect(screen.getByTestId('tarifas-mock')).toBeInTheDocument();
  });

  it('T4: click en "Capacidad" embebe la pantalla Cupos existente', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId('sucursal-detalle-page');
    await user.click(screen.getByTestId('sucursal-tab-capacidad'));
    expect(screen.getByTestId('sucursal-tab-capacidad')).toHaveAttribute('data-state', 'active');
    expect(screen.getByTestId('cupos-mock')).toBeInTheDocument();
  });

  it.each(['resoluciones', 'caja', 'documentos'])(
    'T5: click en "%s" muestra el placeholder Próximamente',
    async (tabValue) => {
      const user = userEvent.setup();
      renderPage();
      await screen.findByTestId('sucursal-detalle-page');
      await user.click(screen.getByTestId(`sucursal-tab-${tabValue}`));
      expect(screen.getByTestId(`sucursal-tab-${tabValue}`)).toHaveAttribute(
        'data-state',
        'active',
      );
      expect(screen.getByTestId(`sucursal-placeholder-${tabValue}`)).toBeInTheDocument();
    },
  );

  it('T6: click en "Bitácora" muestra SucursalBitacoraTab scopeada al uuid de la ruta', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId('sucursal-detalle-page');
    await user.click(screen.getByTestId('sucursal-tab-bitacora'));
    expect(screen.getByTestId('sucursal-tab-bitacora')).toHaveAttribute('data-state', 'active');
    expect(screen.getByTestId('sucursal-bitacora-mock')).toHaveTextContent(SAMPLE_SUCURSAL.uuid);
  });
});
