/**
 * `EmpresaDatosTab.test.tsx` — invariantes del tab "Datos" de
 * Empresa (HU-F15.2 de `plan.md:3537`).
 *
 *   T1: muestra skeleton de loading mientras `useEmpresa` está
 *       fetching.
 *   T2: muestra empty state si el backend todavía no tiene fila
 *       sembrada.
 *   T3: el form se monta con los valores del singleton cuando el
 *       SWR resuelve.
 *   T4: tipear un NIT con DV incorrecto muestra el error inline de
 *       `validarNitModulo11` (BR1) y deshabilita el submit.
 *   T5: tipear un NIT con DV válido (módulo 11) NO muestra el error
 *       inline.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { SWRConfig } from 'swr';

import { EmpresaDatosTab } from './EmpresaDatosTab';

vi.mock('../api/empresaApi', () => ({
  getEmpresa: vi.fn(),
  updateEmpresa: vi.fn(),
  updateEmpresaMensajes: vi.fn(),
}));

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: (selector: (s: { accessToken: string | null }) => unknown) =>
    selector({ accessToken: 'test-token' }),
}));

import { getEmpresa } from '../api/empresaApi';

const mockedGet = getEmpresa as ReturnType<typeof vi.fn>;

const SAMPLE = {
  uuid: '00000000-0000-0000-0000-00000000c0ee',
  nombre: 'Parkos S.A.S.',
  nit: '123456789-6',
  mensaje_bienvenida: null,
  mensaje_salida: null,
  regimen: 'comun',
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
} as const;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(SWRConfig, {
    value: { provider: (): never => new Map() as never },
  }, children);
}

beforeEach(() => {
  mockedGet.mockReset();
});

describe('EmpresaDatosTab', () => {
  it('T1: muestra el skeleton de loading mientras el SWR está pending', () => {
    mockedGet.mockReturnValue(new Promise(() => undefined) as unknown as ReturnType<typeof getEmpresa>);
    render(createElement(wrapper, null, createElement(EmpresaDatosTab)));
    expect(screen.getByTestId('empresa-datos-loading')).toBeInTheDocument();
  });

  it('T2: muestra el empty state si el backend no devolvió fila', async () => {
    mockedGet.mockResolvedValue(null);
    render(createElement(wrapper, null, createElement(EmpresaDatosTab)));
    await waitFor(() => {
      expect(screen.getByTestId('empresa-datos-empty')).toBeInTheDocument();
    });
  });

  it('T3: el form se monta con los valores del singleton', async () => {
    mockedGet.mockResolvedValue(SAMPLE);
    render(createElement(wrapper, null, createElement(EmpresaDatosTab)));
    await waitFor(() => {
      expect(screen.getByTestId('empresa-datos-form')).toBeInTheDocument();
    });
    const nombre = screen.getByTestId('empresa-datos-nombre') as HTMLInputElement;
    const nit = screen.getByTestId('empresa-datos-nit') as HTMLInputElement;
    expect(nombre.value).toBe('Parkos S.A.S.');
    expect(nit.value).toBe('123456789-6');
  });

  it('T4: NIT con DV incorrecto muestra error inline y deshabilita el submit', async () => {
    const user = userEvent.setup();
    mockedGet.mockResolvedValue(SAMPLE);
    render(createElement(wrapper, null, createElement(EmpresaDatosTab)));
    await waitFor(() => {
      expect(screen.getByTestId('empresa-datos-form')).toBeInTheDocument();
    });
    const nit = screen.getByTestId('empresa-datos-nit') as HTMLInputElement;
    await user.clear(nit);
    await user.type(nit, '123456789-9');
    await waitFor(() => {
      expect(screen.getByTestId('empresa-datos-nit-error')).toBeInTheDocument();
    });
    const submit = screen.getByTestId('empresa-datos-submit') as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it('T5: NIT con DV válido módulo 11 NO muestra error inline', async () => {
    const user = userEvent.setup();
    mockedGet.mockResolvedValue(SAMPLE);
    render(createElement(wrapper, null, createElement(EmpresaDatosTab)));
    await waitFor(() => {
      expect(screen.getByTestId('empresa-datos-form')).toBeInTheDocument();
    });
    const nit = screen.getByTestId('empresa-datos-nit') as HTMLInputElement;
    await user.clear(nit);
    await user.type(nit, '800123456-5');
    // DV 5 es correcto para 800123456 (ver nit.test.ts).
    expect(screen.queryByTestId('empresa-datos-nit-error')).not.toBeInTheDocument();
  });
});
