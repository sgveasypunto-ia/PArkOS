/**
 * `GlobalHQ` — invariantes que el resto del repo no debe romper
 * (post-split refactor: antes `HomeHub.test.tsx`).
 *
 * H1: el chrome branch-scoped (con badge de sucursal) NO se monta acá.
 *     Si alguien mueve esta ruta adentro de `<RequireSucursal>` por
 *     simetría, el test falla.
 *     Post-sidebar: el branch selector sigue en `<TopNav>` y SOLO se
 *     monta cuando `selected !== null` (probado en
 *     `TopNav.test.tsx`). En `/` con `selected = null` no aparece.
 * H2: el panel ejecutivo se renderiza con header + KPI grid + charts
 *     (single-column main). El acceso rápido a las secciones vive
 *     en `<AppSidebar>`, no acá.
 * H3: el sidebar NO se monta dentro de GlobalHQ (es responsabilidad
 *     del layout shell en `App.tsx`).
 *
 * Las cards de navegación (los 8 HUB_CARDS) se cubren en
 * `AppSidebar.test.tsx` con el contrato data-driven que antes vivía
 * acá. El deep-link `?next=` se prueba en AppSidebar (los hrefs
 * canónicos no se ven afectados por la query string).
 *
 * NOTA: la cobertura de `<TopNav />` montado en `/` vive en
 * `App.test.tsx` ("mounts TopNav but NOT AdminChrome on /"). Este test
 * mantiene la convención de pinear invariantes de `GlobalHQ` en
 * aislamiento, sin el `App` completo.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import GlobalHQ from './GlobalHQ';

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
      <GlobalHQ />
    </MemoryRouter>,
  );
}

describe('GlobalHQ', () => {
  it('H1: NO renderiza el chrome con badge de sucursal (la ruta está fuera de RequireSucursal)', () => {
    renderGlobalHQ();
    expect(screen.queryByTestId('chrome-sucursal-selector')).not.toBeInTheDocument();
    expect(screen.queryByTestId('admin-chrome')).not.toBeInTheDocument();
  });

  it('H2: renderiza el panel ejecutivo (header + KPIs + charts) en single-column', () => {
    renderGlobalHQ();
    expect(screen.getByTestId('global-hq')).toBeInTheDocument();
    expect(screen.getByTestId('global-hq-header')).toBeInTheDocument();
    expect(screen.getByTestId('global-hq-kpi-grid')).toBeInTheDocument();
    expect(screen.getByTestId('global-hq-charts')).toBeInTheDocument();
  });

  it('H3: el sidebar NO se monta dentro de GlobalHQ (responsabilidad del layout shell)', () => {
    renderGlobalHQ();
    expect(screen.queryByTestId('app-sidebar')).not.toBeInTheDocument();
  });
});
