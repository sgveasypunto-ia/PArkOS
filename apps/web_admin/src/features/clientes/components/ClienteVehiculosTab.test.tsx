/**
 * `ClienteVehiculosTab.test.tsx` — the 3-hop client-side join
 * (subscripciones-cliente -> subscripcion-vehiculos -> vehiculos),
 * mocked at the `clientesApi.ts` boundary. Each test uses a distinct
 * `uuidCliente` (no shared SWR cache wrapper here, unlike the
 * `isolatedCache` helper in `ClientesList.test.tsx`), so a second test's
 * fresh SWR key never reads the first test's cached result.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const { UUID_CLIENTE, UUID_CLIENTE_SIN_VEHICULOS, UUID_SUBSCRIPCION, UUID_VEHICULO } = vi.hoisted(
  () => ({
    UUID_CLIENTE: '11111111-1111-1111-1111-111111111111',
    UUID_CLIENTE_SIN_VEHICULOS: '44444444-4444-4444-4444-444444444444',
    UUID_SUBSCRIPCION: '22222222-2222-2222-2222-222222222222',
    UUID_VEHICULO: '33333333-3333-3333-3333-333333333333',
  }),
);

vi.mock('../api/clientesApi', () => ({
  listSubscripcionesClienteByCliente: vi.fn(async (uuidCliente: string) =>
    uuidCliente === UUID_CLIENTE
      ? [{ uuid: UUID_SUBSCRIPCION, uuid_cliente: UUID_CLIENTE }]
      : [],
  ),
  listSubscripcionVehiculosByIds: vi.fn(async (ids: ReadonlySet<string>) =>
    ids.has(UUID_SUBSCRIPCION)
      ? [{ uuid: 'sv-1', uuid_subscripcion_cliente: UUID_SUBSCRIPCION, uuid_vehiculo: UUID_VEHICULO }]
      : [],
  ),
  listVehiculosByIds: vi.fn(async (ids: ReadonlySet<string>) =>
    ids.has(UUID_VEHICULO) ? [{ uuid: UUID_VEHICULO, placa: 'ABC123', estado: 'activo' }] : [],
  ),
}));

import { ClienteVehiculosTab } from './ClienteVehiculosTab';

describe('<ClienteVehiculosTab />', () => {
  it('renders the vehicle resolved through the 3-hop join', async () => {
    render(<ClienteVehiculosTab uuidCliente={UUID_CLIENTE} />);

    await waitFor(() => {
      expect(screen.getByTestId(`cliente-vehiculo-row-${UUID_VEHICULO}`)).toBeInTheDocument();
    });
    expect(screen.getByText('ABC123')).toBeInTheDocument();
  });

  it('shows the empty state when the cliente has no vehicles', async () => {
    render(<ClienteVehiculosTab uuidCliente={UUID_CLIENTE_SIN_VEHICULOS} />);

    await waitFor(() => {
      expect(screen.getByTestId('cliente-vehiculos-empty')).toBeInTheDocument();
    });
  });
});
