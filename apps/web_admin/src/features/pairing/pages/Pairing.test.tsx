/**
 * `Pairing.test.tsx` -- HU-F19.3 page-level integration tests.
 *
 * Covers:
 *  - renders the branch list.
 *  - a sucursal with no local pairing-token record shows "Sin información".
 *  - pre-seeding `localStorage` + a mocked `getPairingToken` derives
 *    each of "Pendiente" / "Pareada" / "Revocado" / "Expirado".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { SWRConfig } from 'swr';
import type * as PairingApiModule from '../api/pairingApi';

vi.mock('@/features/sucursales/api/sucursalesApi', () => ({
  listSucursales: vi.fn(),
}));

vi.mock('../api/pairingApi', async () => {
  const actual = await vi.importActual<typeof PairingApiModule>('../api/pairingApi');
  return {
    ...actual,
    getPairingToken: vi.fn(),
  };
});

import { listSucursales } from '@/features/sucursales/api/sucursalesApi';
import { PairingTokenNotFoundError, getPairingToken } from '../api/pairingApi';
import Pairing from './Pairing';

const mockedList = listSucursales as ReturnType<typeof vi.fn>;
const mockedGetPairingToken = getPairingToken as ReturnType<typeof vi.fn>;

const STORAGE_KEY = 'easypunto.pairing.lastToken.v1';

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(
    SWRConfig,
    { value: { provider: (): never => new Map() as never } },
    createElement(MemoryRouter, null, children),
  );
}

function baseSucursal(overrides: Partial<Record<string, unknown>>): Record<string, unknown> {
  return {
    uuid: '00000000-0000-0000-0000-000000000000',
    nombre: 'Sucursal',
    direccion: null,
    telefono: null,
    prefijo_nombre: 'PRE-01',
    ciudad: 'Bogota',
    horario: null,
    uuid_tipo_sucursal: null,
    uuid_empresa: null,
    vigente_desde: '2026-09-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-09-01T00:00:00',
    created_by: null,
    sync_status: null,
    ...overrides,
  };
}

const SUC_SIN = baseSucursal({
  uuid: '11111111-1111-1111-1111-111111111111',
  nombre: 'Sucursal Sin Info',
});
const SUC_PENDIENTE = baseSucursal({
  uuid: '22222222-2222-2222-2222-222222222222',
  nombre: 'Sucursal Pendiente',
});
const SUC_PAREADA = baseSucursal({
  uuid: '33333333-3333-3333-3333-333333333333',
  nombre: 'Sucursal Pareada',
});
const SUC_REVOCADA = baseSucursal({
  uuid: '44444444-4444-4444-4444-444444444444',
  nombre: 'Sucursal Revocada',
});
const SUC_EXPIRADA = baseSucursal({
  uuid: '55555555-5555-5555-5555-555555555555',
  nombre: 'Sucursal Expirada',
});

const TOKEN_PENDIENTE = 'aaaaaaaa-0000-0000-0000-000000000001';
const TOKEN_PAREADA = 'aaaaaaaa-0000-0000-0000-000000000002';
const TOKEN_REVOCADA = 'aaaaaaaa-0000-0000-0000-000000000003';
const TOKEN_EXPIRADA = 'aaaaaaaa-0000-0000-0000-000000000004';

function pairingReadFixture(overrides: Partial<Record<string, unknown>>): Record<string, unknown> {
  return {
    uuid: '00000000-0000-0000-0000-000000000000',
    fecha_retencion_hasta: '2027-09-01T00:00:00',
    created_at: '2026-09-01T00:00:00',
    created_by: null,
    uuid_sucursal: null,
    expires_at: '2099-01-01T00:00:00',
    used: false,
    used_at: null,
    revoked_at: null,
    revoked_by: null,
    ...overrides,
  };
}

function seedLocalStorage(): void {
  const map = {
    [SUC_PENDIENTE.uuid as string]: {
      pairingTokenUuid: TOKEN_PENDIENTE,
      issuedAt: '2026-09-01T00:00:00',
    },
    [SUC_PAREADA.uuid as string]: {
      pairingTokenUuid: TOKEN_PAREADA,
      issuedAt: '2026-09-01T00:00:00',
    },
    [SUC_REVOCADA.uuid as string]: {
      pairingTokenUuid: TOKEN_REVOCADA,
      issuedAt: '2026-09-01T00:00:00',
    },
    [SUC_EXPIRADA.uuid as string]: {
      pairingTokenUuid: TOKEN_EXPIRADA,
      issuedAt: '2026-09-01T00:00:00',
    },
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
}

beforeEach(() => {
  mockedList.mockReset();
  mockedGetPairingToken.mockReset();
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('Pairing page', () => {
  it('renders the branch list', async () => {
    mockedList.mockResolvedValue([SUC_SIN, SUC_PENDIENTE]);
    render(<Pairing />, { wrapper });
    await waitFor(() => {
      expect(screen.getByTestId(`pairing-row-${SUC_SIN.uuid as string}`)).toBeInTheDocument();
    });
    expect(screen.getByText('Sucursal Sin Info')).toBeInTheDocument();
    expect(screen.getByText('Sucursal Pendiente')).toBeInTheDocument();
  });

  it('shows "Sin información" for a sucursal with no local pairing-token record', async () => {
    mockedList.mockResolvedValue([SUC_SIN]);
    render(<Pairing />, { wrapper });
    await waitFor(() => {
      expect(screen.getByTestId(`pairing-status-${SUC_SIN.uuid as string}`)).toHaveTextContent(
        'Sin información',
      );
    });
    expect(mockedGetPairingToken).not.toHaveBeenCalled();
  });

  it('derives "Pendiente" from a local record whose token is not used and not expired', async () => {
    seedLocalStorage();
    mockedList.mockResolvedValue([SUC_PENDIENTE]);
    mockedGetPairingToken.mockImplementation(async (uuid: string) =>
      pairingReadFixture({
        uuid,
        uuid_sucursal: SUC_PENDIENTE.uuid,
        used: false,
        expires_at: '2099-01-01T00:00:00',
        revoked_at: null,
      }),
    );
    render(<Pairing />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByTestId(`pairing-status-${SUC_PENDIENTE.uuid as string}`),
      ).toHaveTextContent('Pendiente');
    });
    expect(mockedGetPairingToken).toHaveBeenCalledWith(TOKEN_PENDIENTE);
    expect(screen.getByTestId(`pairing-revocar-${SUC_PENDIENTE.uuid as string}`)).toBeEnabled();
  });

  it('derives "Pareada" from a local record whose token was used', async () => {
    seedLocalStorage();
    mockedList.mockResolvedValue([SUC_PAREADA]);
    mockedGetPairingToken.mockImplementation(async (uuid: string) =>
      pairingReadFixture({
        uuid,
        uuid_sucursal: SUC_PAREADA.uuid,
        used: true,
        used_at: '2026-09-01T10:00:00',
        expires_at: '2026-09-02T00:00:00',
        revoked_at: null,
      }),
    );
    render(<Pairing />, { wrapper });
    await waitFor(() => {
      expect(screen.getByTestId(`pairing-status-${SUC_PAREADA.uuid as string}`)).toHaveTextContent(
        'Pareada',
      );
    });
    expect(screen.getByTestId(`pairing-revocar-${SUC_PAREADA.uuid as string}`)).toBeEnabled();
  });

  it('derives "Revocado" from a local record whose token was revoked', async () => {
    seedLocalStorage();
    mockedList.mockResolvedValue([SUC_REVOCADA]);
    mockedGetPairingToken.mockImplementation(async (uuid: string) =>
      pairingReadFixture({
        uuid,
        uuid_sucursal: SUC_REVOCADA.uuid,
        used: false,
        revoked_at: '2026-09-01T12:00:00',
        revoked_by: '22222222-2222-2222-2222-222222222222',
      }),
    );
    render(<Pairing />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByTestId(`pairing-status-${SUC_REVOCADA.uuid as string}`),
      ).toHaveTextContent('Revocado');
    });
    // Bugfix (QA batch pairing): the row button must stay enabled
    // regardless of the derived status — `<RevocarPairingModal />`'s
    // Section B (advanced sync-credential revoke) needs no locally-
    // known token at all, so gating the row button on "something
    // actionable in Section A" made Section B unreachable here.
    expect(screen.getByTestId(`pairing-revocar-${SUC_REVOCADA.uuid as string}`)).toBeEnabled();
  });

  it('derives "Expirado" from a local record whose token is unused and past expires_at', async () => {
    seedLocalStorage();
    mockedList.mockResolvedValue([SUC_EXPIRADA]);
    mockedGetPairingToken.mockImplementation(async (uuid: string) =>
      pairingReadFixture({
        uuid,
        uuid_sucursal: SUC_EXPIRADA.uuid,
        used: false,
        expires_at: '2020-01-01T00:00:00',
        revoked_at: null,
      }),
    );
    render(<Pairing />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByTestId(`pairing-status-${SUC_EXPIRADA.uuid as string}`),
      ).toHaveTextContent('Expirado');
    });
    // Bugfix (QA batch pairing): see the "Revocado" case above — the
    // row button stays enabled so Section B stays reachable.
    expect(screen.getByTestId(`pairing-revocar-${SUC_EXPIRADA.uuid as string}`)).toBeEnabled();
  });

  it('treats a local record whose GET 404s the same as "Sin información"', async () => {
    seedLocalStorage();
    mockedList.mockResolvedValue([SUC_PENDIENTE]);
    mockedGetPairingToken.mockRejectedValue(new PairingTokenNotFoundError(TOKEN_PENDIENTE));
    render(<Pairing />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByTestId(`pairing-status-${SUC_PENDIENTE.uuid as string}`),
      ).toHaveTextContent('Sin información');
    });
  });

  it('evicts a stale local record when GET 404s (2026-10-08 UX fix)', async () => {
    // Regression for the user-reported DevTools noise: a cached UUID
    // that no longer exists on the server (DB reseeded, token issued
    // in a different browser, etc.) used to keep firing GET 404s on
    // every page load. The fix: on the first 404, delete the
    // localStorage entry so the next render finds no record and the
    // SWR key becomes null (no further GETs).
    seedLocalStorage();
    mockedList.mockResolvedValue([SUC_PENDIENTE]);
    mockedGetPairingToken.mockRejectedValue(new PairingTokenNotFoundError(TOKEN_PENDIENTE));

    expect(
      (JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '{}') as Record<string, unknown>)[
        SUC_PENDIENTE.uuid as string
      ],
    ).toBeDefined();

    render(<Pairing />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByTestId(`pairing-status-${SUC_PENDIENTE.uuid as string}`),
      ).toHaveTextContent('Sin información');
    });

    // The cache entry for the stale UUID has been evicted; sibling
    // entries for unrelated sucursales are untouched.
    const remaining = JSON.parse(
      window.localStorage.getItem(STORAGE_KEY) ?? '{}',
    ) as Record<string, unknown>;
    expect(remaining[SUC_PENDIENTE.uuid as string]).toBeUndefined();
    expect(remaining[SUC_PAREADA.uuid as string]).toBeDefined();
    expect(remaining[SUC_REVOCADA.uuid as string]).toBeDefined();
    expect(remaining[SUC_EXPIRADA.uuid as string]).toBeDefined();
  });
});
