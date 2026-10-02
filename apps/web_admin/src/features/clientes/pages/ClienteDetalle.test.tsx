/**
 * `ClienteDetalle.test.tsx` — tab-wiring shell test (HU-F20.1). Mirrors
 * `features/parametrizacion/pages/SucursalDetalle.test.tsx`'s style:
 * each tab component is mocked as a stub (its own suite covers its
 * internals), `useCliente` is mocked directly so no network mocking is
 * needed here, `vi.hoisted` for the shared fixture referenced inside
 * hoisted `vi.mock` factories.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

const { SAMPLE_CLIENTE } = vi.hoisted(() => ({
  SAMPLE_CLIENTE: {
    uuid: '11111111-1111-1111-1111-111111111111',
    tipo_identificador: 'CC',
    numero_identificacion: '1000000001',
    nombre: 'Ada',
    apellido: 'Lovelace',
    telefono: '3000000000',
    email: 'ada@example.com',
    uuid_tipo_persona: null,
    registro: null,
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: null,
  },
}));

vi.mock('../hooks/useCliente', () => ({
  useCliente: () => ({
    cliente: SAMPLE_CLIENTE,
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
    update: vi.fn(),
  }),
}));

vi.mock('../components/ClienteDatosTab', () => ({
  ClienteDatosTab: () => <div data-testid="cliente-datos-mock">Datos mock</div>,
}));

vi.mock('../components/ClienteVehiculosTab', () => ({
  ClienteVehiculosTab: ({ uuidCliente }: { uuidCliente: string }) => (
    <div data-testid="cliente-vehiculos-mock">Vehículos mock para {uuidCliente}</div>
  ),
}));

vi.mock('../components/ClienteSuscripciones', () => ({
  ClienteSuscripciones: ({ uuidCliente }: { uuidCliente: string }) => (
    <div data-testid="cliente-suscripciones-mock">Suscripciones mock para {uuidCliente}</div>
  ),
}));

vi.mock('../components/ClienteFacturasTab', () => ({
  ClienteFacturasTab: ({ uuidCliente }: { uuidCliente: string }) => (
    <div data-testid="cliente-facturas-mock">Facturas mock para {uuidCliente}</div>
  ),
}));

vi.mock('../components/ClienteBitacoraTab', () => ({
  ClienteBitacoraTab: ({ uuidCliente }: { uuidCliente: string }) => (
    <div data-testid="cliente-bitacora-mock">Bitácora mock para {uuidCliente}</div>
  ),
}));

import ClienteDetalle from './ClienteDetalle';

function renderPage(): void {
  render(
    <MemoryRouter initialEntries={[`/clientes/${SAMPLE_CLIENTE.uuid}`]}>
      <Routes>
        <Route path="/clientes/:uuid" element={<ClienteDetalle />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ClienteDetalle', () => {
  it('monta el contenedor de la página con el nombre del cliente', async () => {
    renderPage();
    expect(await screen.findByTestId('cliente-detalle-page')).toBeInTheDocument();
    expect(screen.getByTestId('cliente-detalle-nombre')).toHaveTextContent('Ada Lovelace');
  });

  it('el tab por defecto es Datos y muestra ClienteDatosTab', async () => {
    renderPage();
    expect(await screen.findByTestId('cliente-tab-datos')).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.getByTestId('cliente-datos-mock')).toBeInTheDocument();
  });

  it('click en "Vehículos" muestra ClienteVehiculosTab scopeada al uuid de la ruta', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId('cliente-detalle-page');
    await user.click(screen.getByTestId('cliente-tab-vehiculos'));
    expect(screen.getByTestId('cliente-tab-vehiculos')).toHaveAttribute('data-state', 'active');
    expect(screen.getByTestId('cliente-vehiculos-mock')).toHaveTextContent(SAMPLE_CLIENTE.uuid);
  });

  it('click en "Suscripciones" muestra ClienteSuscripciones scopeada al uuid de la ruta', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId('cliente-detalle-page');
    await user.click(screen.getByTestId('cliente-tab-suscripciones'));
    expect(screen.getByTestId('cliente-tab-suscripciones')).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.getByTestId('cliente-suscripciones-mock')).toHaveTextContent(
      SAMPLE_CLIENTE.uuid,
    );
  });

  it('click en "Facturas" muestra ClienteFacturasTab scopeada al uuid de la ruta', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId('cliente-detalle-page');
    await user.click(screen.getByTestId('cliente-tab-facturas'));
    expect(screen.getByTestId('cliente-tab-facturas')).toHaveAttribute('data-state', 'active');
    expect(screen.getByTestId('cliente-facturas-mock')).toHaveTextContent(SAMPLE_CLIENTE.uuid);
  });

  it('click en "Bitácora" muestra ClienteBitacoraTab scopeada al uuid de la ruta', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId('cliente-detalle-page');
    await user.click(screen.getByTestId('cliente-tab-bitacora'));
    expect(screen.getByTestId('cliente-tab-bitacora')).toHaveAttribute('data-state', 'active');
    expect(screen.getByTestId('cliente-bitacora-mock')).toHaveTextContent(SAMPLE_CLIENTE.uuid);
  });
});
