/**
 * `HomeHub` — invariantes que el resto del repo no debe romper.
 *
 * H1/H2: el chrome branch-scoped (con badge de sucursal) NO se monta acá.
 *        Si alguien mueve esta ruta adentro de `<RequireSucursal>` por
 *        simetría, el test falla.
 * H3:   cada card es un `<a>` real con href y nombre accesible.
 * H4:   el deep-link `?next=/ruta` sobrevive al login bounce
 *        cuando el guard nos manda a `/` (DEC-LOGIN-07 revisado).
 *
 * NOTA: la cobertura de `<TopNav />` montado en `/` vive en
 * `App.test.tsx` ("mounts TopNav but NOT AdminChrome on /"). Este test
 * mantiene la convencion de pinear invariantes de `HomeHub` en
 * aislamiento, sin el `App` completo.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import HomeHub from './HomeHub';

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div data-testid="mock-card" className={className}>
      {children}
    </div>
  ),
}));

function renderHomeHub(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<HomeHub />} />
        <Route
          path="/seleccionar-sucursal"
          element={<div data-testid="dest-sucursales" />}
        />
        <Route path="/catalogos" element={<div data-testid="dest-catalogos" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('HomeHub', () => {
  it('H1: NO renderiza el chrome con badge de sucursal (la ruta está fuera de RequireSucursal)', () => {
    renderHomeHub();
    expect(screen.queryByTestId('chrome-sucursal-selector')).not.toBeInTheDocument();
    expect(screen.queryByTestId('admin-chrome')).not.toBeInTheDocument();
  });

  it('H2: renderiza 2 cards (sucursales y catalogos)', () => {
    renderHomeHub();
    expect(screen.getByTestId('home-hub-card-sucursales')).toBeInTheDocument();
    expect(screen.getByTestId('home-hub-card-catalogos')).toBeInTheDocument();
  });

  it('H3: cada card es un <a> con href y nombre accesible correcto', () => {
    renderHomeHub();
    const sucursales = screen.getByTestId('home-hub-card-sucursales');
    const catalogos = screen.getByTestId('home-hub-card-catalogos');
    expect(sucursales.tagName).toBe('A');
    expect(sucursales).toHaveAttribute('href', '/seleccionar-sucursal');
    expect(sucursales).toHaveAccessibleName(/sucursales/i);
    expect(catalogos.tagName).toBe('A');
    expect(catalogos).toHaveAttribute('href', '/catalogos');
    expect(catalogos).toHaveAccessibleName(/cat[aá]logos/i);
  });

  it('H4: el deep-link ?next=/ruta preserva el destino después del login bounce', () => {
    renderHomeHub('/?next=%2Fdashboard');
    expect(screen.getByTestId('home-hub-card-sucursales')).toHaveAttribute(
      'href',
      '/seleccionar-sucursal',
    );
    expect(screen.getByTestId('home-hub-card-catalogos')).toHaveAttribute(
      'href',
      '/catalogos',
    );
  });
});
