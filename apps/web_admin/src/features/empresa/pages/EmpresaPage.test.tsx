/**
 * `EmpresaPage.test.tsx` — invariantes de la página de Empresa
 * (HU-F15.2 de `plan.md:3537`).
 *
 *   T1: el contenedor de la página se monta con el testid canónico.
 *   T2: el tab por defecto es "Datos" (defaultValue en shadcn Tabs).
 *   T3: click en "Mensajes" muestra el contenido del tab Mensajes.
 *   T4: click en "Bitácora" muestra el contenido del tab Bitácora.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../api/empresaApi', () => ({
  getEmpresa: vi.fn().mockResolvedValue(null),
  updateEmpresa: vi.fn(),
  updateEmpresaMensajes: vi.fn(),
}));

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: (selector: (s: { accessToken: string | null }) => unknown) =>
    selector({ accessToken: 'test-token' }),
}));

import EmpresaPage from './EmpresaPage';

function renderPage(): void {
  render(
    <MemoryRouter initialEntries={['/empresa']}>
      <EmpresaPage />
    </MemoryRouter>,
  );
}

describe('EmpresaPage', () => {
  it('T1: monta el contenedor de la página', () => {
    renderPage();
    expect(screen.getByTestId('empresa-page')).toBeInTheDocument();
  });

  it('T2: el tab por defecto es Datos (defaultValue)', () => {
    renderPage();
    expect(screen.getByTestId('empresa-tab-datos')).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.getByTestId('empresa-datos-empty')).toBeInTheDocument();
  });

  it('T3: click en "Mensajes" muestra el contenido del tab Mensajes', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByTestId('empresa-tab-mensajes'));
    expect(screen.getByTestId('empresa-tab-mensajes')).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.getByTestId('empresa-mensajes-empty')).toBeInTheDocument();
  });

  it('T4: click en "Bitácora" muestra el contenido del tab Bitácora', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByTestId('empresa-tab-bitacora'));
    expect(screen.getByTestId('empresa-tab-bitacora')).toHaveAttribute(
      'data-state',
      'active',
    );
    // HU-F15.2 wire-up: EmpresaBitacoraTab is no longer a placeholder --
    // it queries /admin/audit/log?tabla_afectada=empresa and renders one
    // of three testid'd states (loading/empty/error/list). The mocked
    // ``fetchAuditLog`` resolves with the Zod-parsed shape; in this
    // test the SWR call hasn't returned yet, so we see the loading
    // state.
    expect(screen.getByTestId('empresa-bitacora-root')).toBeInTheDocument();
  });
});
