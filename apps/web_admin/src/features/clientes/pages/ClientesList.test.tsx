/**
 * `ClientesList.test.tsx` — HU-F20.1 search filtering + loading/error
 * states. Mirrors `features/admin/pages/UsuariosList.test.tsx`'s style:
 * mock `@parkos/ui-kit/fetch` directly, isolated SWR cache + MemoryRouter.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, type ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetchRaw: vi.fn(),
  parkosFetch: vi.fn(),
}));

import { parkosFetchRaw } from '@parkos/ui-kit/fetch';

import ClientesList from './ClientesList';

const mockedRaw = vi.mocked(parkosFetchRaw);

function makeCliente(overrides: Record<string, unknown> = {}) {
  return {
    uuid: '11111111-1111-4111-8111-111111111111',
    tipo_identificador: 'CC',
    numero_identificacion: '1000000001',
    nombre: 'Ada',
    apellido: 'Lovelace',
    telefono: '3000000000',
    email: 'ada@example.com',
    uuid_tipo_persona: null,
    registro: null,
    vigente_desde: '2026-01-01T00:00:00Z',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00Z',
    created_by: null,
    sync_status: null,
    ...overrides,
  };
}

const CLIENTE_ADA = makeCliente();
const CLIENTE_GRACE = makeCliente({
  uuid: '22222222-2222-4222-8222-222222222222',
  numero_identificacion: '2000000002',
  nombre: 'Grace',
  apellido: 'Hopper',
});

function isolatedCache({ children }: { children: ReactNode }) {
  return createElement(
    SWRConfig,
    { value: { provider: () => new Map(), dedupingInterval: 0 } },
    createElement(MemoryRouter, null, children),
  );
}

describe('<ClientesList />', () => {
  beforeEach(() => {
    mockedRaw.mockReset();
  });

  it('shows every row by default and narrows down to a search match', async () => {
    mockedRaw.mockImplementation(async (input: unknown) => {
      const url = String(input);
      if (url.includes('/api/v1/clientes/clientes')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: [CLIENTE_ADA, CLIENTE_GRACE], next_cursor: null }),
          text: async () => '',
        } as Response;
      }
      return { ok: true, status: 200, json: async () => ({}), text: async () => '' } as Response;
    });

    const user = userEvent.setup();
    render(<ClientesList />, { wrapper: isolatedCache });

    await waitFor(() => {
      expect(screen.getByTestId(`clientes-row-${CLIENTE_ADA.uuid}`)).toBeInTheDocument();
      expect(screen.getByTestId(`clientes-row-${CLIENTE_GRACE.uuid}`)).toBeInTheDocument();
    });

    await user.type(screen.getByTestId('clientes-search'), 'Grace');

    await waitFor(
      () => {
        expect(screen.queryByTestId(`clientes-row-${CLIENTE_ADA.uuid}`)).not.toBeInTheDocument();
        expect(screen.getByTestId(`clientes-row-${CLIENTE_GRACE.uuid}`)).toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });

  it('matches by numero_identificacion substring too', async () => {
    mockedRaw.mockImplementation(async (input: unknown) => {
      const url = String(input);
      if (url.includes('/api/v1/clientes/clientes')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: [CLIENTE_ADA, CLIENTE_GRACE], next_cursor: null }),
          text: async () => '',
        } as Response;
      }
      return { ok: true, status: 200, json: async () => ({}), text: async () => '' } as Response;
    });

    const user = userEvent.setup();
    render(<ClientesList />, { wrapper: isolatedCache });

    await waitFor(() => {
      expect(screen.getByTestId(`clientes-row-${CLIENTE_ADA.uuid}`)).toBeInTheDocument();
    });

    await user.type(screen.getByTestId('clientes-search'), '2000000002');

    await waitFor(
      () => {
        expect(screen.queryByTestId(`clientes-row-${CLIENTE_ADA.uuid}`)).not.toBeInTheDocument();
        expect(screen.getByTestId(`clientes-row-${CLIENTE_GRACE.uuid}`)).toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });

  it('shows the loading state before data arrives', () => {
    mockedRaw.mockImplementation(() => new Promise(() => undefined));
    render(<ClientesList />, { wrapper: isolatedCache });
    expect(screen.getByTestId('clientes-loading')).toBeInTheDocument();
  });

  it('shows the error state when the fetch fails', async () => {
    mockedRaw.mockImplementation(
      async () =>
        ({
          ok: false,
          status: 500,
          json: async () => ({}),
          text: async () => 'boom',
        }) as Response,
    );

    render(<ClientesList />, { wrapper: isolatedCache });

    await waitFor(() => {
      expect(screen.getByTestId('clientes-error')).toBeInTheDocument();
    });
  });

  it('shows the empty state when the list has no clientes', async () => {
    mockedRaw.mockImplementation(
      async () =>
        ({
          ok: true,
          status: 200,
          json: async () => ({ items: [], next_cursor: null }),
          text: async () => '',
        }) as Response,
    );

    render(<ClientesList />, { wrapper: isolatedCache });

    await waitFor(() => {
      expect(screen.getByTestId('clientes-empty')).toBeInTheDocument();
    });
  });

  it('hides the standard billing client "Consumidor final" by default and can show it on demand', async () => {
    const CONSUMIDOR_FINAL = makeCliente({
      uuid: '33333333-3333-4333-8333-333333333333',
      numero_identificacion: '222222222222',
      nombre: 'Consumidor',
      apellido: 'Final',
    });
    mockedRaw.mockImplementation(
      async () =>
        ({
          ok: true,
          status: 200,
          json: async () => ({ items: [CLIENTE_ADA, CONSUMIDOR_FINAL], next_cursor: null }),
          text: async () => '',
        }) as Response,
    );
    const user = userEvent.setup();
    render(<ClientesList />, { wrapper: isolatedCache });

    await waitFor(() => {
      expect(screen.getByTestId(`clientes-row-${CLIENTE_ADA.uuid}`)).toBeInTheDocument();
    });
    expect(screen.queryByTestId(`clientes-row-${CONSUMIDOR_FINAL.uuid}`)).not.toBeInTheDocument();

    // Search does not surface it either by default.
    await user.type(screen.getByTestId('clientes-search'), 'Consumidor');
    await waitFor(() => {
      expect(screen.getByTestId('clientes-empty')).toBeInTheDocument();
    });
    await user.clear(screen.getByTestId('clientes-search'));

    await user.click(screen.getByTestId('clientes-mostrar-consumidor-final'));
    await waitFor(() => {
      expect(screen.getByTestId(`clientes-row-${CONSUMIDOR_FINAL.uuid}`)).toBeInTheDocument();
    });
  });
});
