/**
 * `GlobalHQ` — invariantes que el resto del repo no debe romper
 * (post-split refactor: antes `HomeHub.test.tsx`).
 *
 * H1: el chrome branch-scoped (con badge de sucursal) NO se monta acá.
 *     Si alguien mueve esta ruta adentro de `<RequireSucursal>` por
 *     simetría, el test falla.
 * H2: las cards de acceso rápido son las de `HUB_CARDS` (data-driven:
 *     agregar una card no requiere tocar este test, solo el array
 *     fuente).
 * H3: cada card es un `<a>` real con href y nombre accesible.
 * H4: el deep-link `?next=/ruta` sobrevive al login bounce
 *     cuando el guard nos manda a `/` (DEC-LOGIN-07 revisado).
 * H5: el panel ejecutivo se renderiza con las 6 cards cross-branch
 *     (Ocupación agregada, Suscripciones, Medios de pago, Top
 *     sucursal, Sync, Alertas) y los accesos rápidos debajo.
 *
 * NOTA: la cobertura de `<TopNav />` montado en `/` vive en
 * `App.test.tsx` ("mounts TopNav but NOT AdminChrome on /"). Este test
 * mantiene la convención de pinear invariantes de `GlobalHQ` en
 * aislamiento, sin el `App` completo.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import GlobalHQ, { HUB_CARDS } from './GlobalHQ';

// Mock the cross-branch data hook so the test does not need the
// network. The shape mirrors the real `useResumenKpi` return so the
// `KpiCard` consumers can render their loading/value/derived views.
vi.mock('@/features/dashboard/hooks/useResumenKpi', () => ({
  useResumenKpi: () => ({
    ocupacion: { value: { ocupados: 8, capacidad: 20, porcentaje: 40 }, loading: false, error: false },
    suscripciones: { value: 5, loading: false, error: false },
    mediosPago: { value: [{ medio_pago: 'efectivo', monto_total: 100000 }], loading: false, error: false },
    topSucursales: { value: [{ uuid_sucursal: '22222222-2222-2222-2222-222222222222', nombre: 'Sucursal B', monto_total: 900000 }], loading: false, error: false },
    sync: { value: { sucursales_ok: 2, sucursales_degradadas: 1, queue_depth_total: 3, max_lag_seconds: 120 }, loading: false, error: false },
    alertas: { value: [{ severity: 'critical', count: 2 }], loading: false, error: false },
    resumen: undefined,
    ocupacionHoraria: [],
  }),
}));

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div data-testid="mock-card" className={className}>
      {children}
    </div>
  ),
}));

vi.mock('@/components/AlertasBadge', () => ({
  AlertasBadge: () => <div data-testid="alertas-badge-mock" />,
}));

vi.mock('@/features/dashboard/components/CrossBranchCharts', () => ({
  default: () => <div data-testid="cross-branch-charts-mock" />,
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({
    sucursalUuids: ['11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222'],
  }),
}));

function renderGlobalHQ(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<GlobalHQ />} />
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

describe('GlobalHQ', () => {
  it('H1: NO renderiza el chrome con badge de sucursal (la ruta está fuera de RequireSucursal)', () => {
    renderGlobalHQ();
    expect(screen.queryByTestId('chrome-sucursal-selector')).not.toBeInTheDocument();
    expect(screen.queryByTestId('admin-chrome')).not.toBeInTheDocument();
  });

  it('H2: cada card declarada en HUB_CARDS se renderiza (data-driven)', () => {
    renderGlobalHQ();
    for (const card of HUB_CARDS) {
      expect(
        screen.getByTestId(card.testId),
        `card "${card.key}" debe estar renderizada`,
      ).toBeInTheDocument();
    }
  });

  it('H3: cada card es un <a> con href y nombre accesible correcto', () => {
    renderGlobalHQ();
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
    renderGlobalHQ('/?next=%2Fdashboard');
    for (const card of HUB_CARDS) {
      expect(
        screen.getByTestId(card.testId),
        `card "${card.key}" debe mantener su href canónico`,
      ).toHaveAttribute('href', card.path);
    }
  });

  it('H5: renderiza el header con KPIs cross-branch y los accesos rápidos', () => {
    renderGlobalHQ();
    expect(screen.getByTestId('global-hq')).toBeInTheDocument();
    expect(screen.getByTestId('global-hq-header')).toBeInTheDocument();
    expect(screen.getByTestId('global-hq-kpi-grid')).toBeInTheDocument();
    expect(screen.getByTestId('global-hq-quick-links')).toBeInTheDocument();
  });
});
