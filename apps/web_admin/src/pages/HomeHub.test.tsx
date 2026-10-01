/**
 * `HomeHub` — invariantes que el resto del repo no debe romper.
 *
 * H1: el chrome branch-scoped (con badge de sucursal) NO se monta acá.
 *     Si alguien mueve esta ruta adentro de `<RequireSucursal>` por
 *     simetría, el test falla.
 * H2: las cards de HomeHub son las de `HUB_CARDS` (data-driven: agregar
 *     una card no requiere tocar este test, solo el array fuente).
 * H3: cada card es un `<a>` real con href y nombre accesible.
 * H4: el deep-link `?next=/ruta` sobrevive al login bounce
 *     cuando el guard nos manda a `/` (DEC-LOGIN-07 revisado).
 *
 * NOTA: la cobertura de `<TopNav />` montado en `/` vive en
 * `App.test.tsx` ("mounts TopNav but NOT AdminChrome on /"). Este test
 * mantiene la convencion de pinear invariantes de `HomeHub` en
 * aislamiento, sin el `App` completo.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import HomeHub, { HUB_CARDS } from './HomeHub';

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
        <Route path="/empresa" element={<div data-testid="dest-empresa" />} />
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

  it('H2: cada card declarada en HUB_CARDS se renderiza (data-driven)', () => {
    renderHomeHub();
    for (const card of HUB_CARDS) {
      expect(
        screen.getByTestId(card.testId),
        `card "${card.key}" debe estar renderizada`,
      ).toBeInTheDocument();
    }
  });

  it('H3: cada card es un <a> con href y nombre accesible correcto', () => {
    renderHomeHub();
    for (const card of HUB_CARDS) {
      const el = screen.getByTestId(card.testId);
      expect(el.tagName, `card "${card.key}" debe ser un <a>`).toBe('A');
      expect(el, `card "${card.key}" debe apuntar a ${card.path}`).toHaveAttribute(
        'href',
        card.path,
      );
      expect(el, `card "${card.key}" debe tener nombre accesible`).toHaveAccessibleName();
    }
  });

  it('H4: el deep-link ?next=/ruta preserva el destino después del login bounce', () => {
    renderHomeHub('/?next=%2Fdashboard');
    for (const card of HUB_CARDS) {
      expect(
        screen.getByTestId(card.testId),
        `card "${card.key}" debe mantener su href canónico`,
      ).toHaveAttribute('href', card.path);
    }
  });
});
