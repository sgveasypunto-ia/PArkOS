/**
 * `EmpresaPage.test.tsx` — invariantes de la página de Empresa
 * (HU-F15.2 de `plan.md:3537`).
 *
 *   T1: el contenedor de la página se monta con el testid canónico.
 *   T2: el tab por defecto es "Datos" (defaultValue en shadcn Tabs).
 *   T3: click en "Mensajes" muestra el placeholder del tab Mensajes.
 *   T4: click en "Bitácora" muestra el placeholder del tab Bitácora.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

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
    expect(screen.getByTestId('empresa-datos-placeholder')).toBeInTheDocument();
  });

  it('T3: click en "Mensajes" muestra el placeholder del tab Mensajes', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByTestId('empresa-tab-mensajes'));
    expect(screen.getByTestId('empresa-tab-mensajes')).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.getByTestId('empresa-mensajes-placeholder')).toBeInTheDocument();
  });

  it('T4: click en "Bitácora" muestra el placeholder del tab Bitácora', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByTestId('empresa-tab-bitacora'));
    expect(screen.getByTestId('empresa-tab-bitacora')).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.getByTestId('empresa-bitacora-placeholder')).toBeInTheDocument();
  });
});
