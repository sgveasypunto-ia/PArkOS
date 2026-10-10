/**
 * `Breadcrumb.test.tsx` — invariantes de la miga de pan que el resto
 * del repo no debe romper.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SWRConfig } from 'swr';

import { SucursalProvider } from '@/lib/sucursal-context';
import { BreadcrumbsProvider, useBreadcrumbs } from '@/lib/useBreadcrumbs';
import { Breadcrumb } from './Breadcrumb';

const SUCURSAL_UUID = '2049f2cd-b2a8-4e45-9d19-31fa87eb67c6';
const SUCURSAL_UUID_OTHER = '11111111-1111-1111-1111-111111111111';

const SUCURSAL_NOMBRE = 'Bogotá Centro';
const SUCURSAL_PREFIJO = 'BOG-CEN';
const SUCURSAL_OTHER_NOMBRE = 'Medellín Norte';

const DIRECTORIO = [
  {
    uuid: SUCURSAL_UUID,
    nombre: SUCURSAL_NOMBRE,
    prefijo_nombre: SUCURSAL_PREFIJO,
    direccion: null,
    telefono: null,
    ciudad: null,
    horario: null,
    uuid_tipo_sucursal: null,
    uuid_empresa: null,
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: SUCURSAL_UUID_OTHER,
    nombre: SUCURSAL_OTHER_NOMBRE,
    prefijo_nombre: 'MED-NOR',
    direccion: null,
    telefono: null,
    ciudad: null,
    horario: null,
    uuid_tipo_sucursal: null,
    uuid_empresa: null,
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
];

vi.mock('@/features/sucursales/hooks/useSucursalesDirectorio', () => ({
  useSucursalesDirectorio: () => ({
    sucursales: DIRECTORIO,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
  }),
  useSucursalOptions: () => ({
    sucursales: DIRECTORIO,
    options: DIRECTORIO.map((s) => ({ uuid: s.uuid, nombre: s.nombre })),
    isLoading: false,
    error: undefined,
  }),
}));

function Providers({
  children,
  initialEntries,
  selectedUuid,
}: {
  children: React.ReactNode;
  initialEntries: string[];
  selectedUuid?: string | null;
}): JSX.Element {
  if (selectedUuid === null || selectedUuid === undefined) {
    window.localStorage.removeItem('parkos.lastSelectedSucursal');
  } else {
    window.localStorage.setItem('parkos.lastSelectedSucursal', selectedUuid);
  }

  return (
    <SWRConfig value={{ provider: (): never => new Map() as never }}>
      <SucursalProvider>
        <MemoryRouter initialEntries={initialEntries}>
          <BreadcrumbsProvider>
            {children}
          </BreadcrumbsProvider>
        </MemoryRouter>
      </SucursalProvider>
    </SWRConfig>
  );
}

describe('Breadcrumb', () => {
  beforeEach(() => {
    window.localStorage.removeItem('parkos.lastSelectedSucursal');
  });

  it('T1: en "/" la miga tiene solo "Inicio" como segmento actual', () => {
    render(<Providers initialEntries={['/']}><Breadcrumb /></Providers>);
    const nav = screen.getByTestId('breadcrumb');
    expect(nav.tagName).toBe('NAV');
    expect(nav).toHaveAccessibleName(/migas de pan/i);
    const current = screen.getByTestId('breadcrumb-current');
    expect(current).toHaveTextContent(/inicio/i);
    expect(current).toHaveAttribute('aria-current', 'page');
  });

  it('T2: en "/usuarios" la cadena es Inicio → Usuarios', () => {
    render(<Providers initialEntries={['/usuarios']}><Breadcrumb /></Providers>);
    const links = screen.getAllByTestId('breadcrumb-link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', '/');
    expect(links[0]).toHaveTextContent(/inicio/i);
    const current = screen.getByTestId('breadcrumb-current');
    expect(current).toHaveTextContent(/usuarios/i);
  });

  it('T3: en "/dashboard" con sucursal activa, la cadena es Inicio → Sucursales → <Branch> → Panel ejecutivo', () => {
    render(
      <Providers initialEntries={['/dashboard']} selectedUuid={SUCURSAL_UUID}>
        <Breadcrumb />
      </Providers>,
    );
    const links = screen.getAllByTestId('breadcrumb-link');
    // 3 links + 1 current segment: Inicio → Sucursales → BOG-CEN → Panel ejecutivo
    expect(links).toHaveLength(3);
    expect(links[0]).toHaveAttribute('href', '/');
    expect(links[0]).toHaveTextContent(/inicio/i);
    expect(links[1]).toHaveAttribute('href', '/seleccionar-sucursal');
    expect(links[1]).toHaveTextContent(/sucursales/i);
    expect(links[2]).toHaveAttribute('href', '/dashboard');
    expect(links[2]).toHaveTextContent(SUCURSAL_NOMBRE);
    const current = screen.getByTestId('breadcrumb-current');
    expect(current).toHaveTextContent(/panel ejecutivo/i);
  });

  it('T4: en "/dashboard" sin sucursal activa, no se prepende el segmento', () => {
    render(
      <Providers initialEntries={['/dashboard']} selectedUuid={null}>
        <Breadcrumb />
      </Providers>,
    );
    const links = screen.getAllByTestId('breadcrumb-link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', '/');
    const current = screen.getByTestId('breadcrumb-current');
    expect(current).toHaveTextContent(/panel ejecutivo/i);
  });

  it('T5: en "/sucursales/:uuid" el último segmento es el nombre de la URL (no la activa)', () => {
    render(
      <Providers initialEntries={[`/sucursales/${SUCURSAL_UUID_OTHER}`]} selectedUuid={SUCURSAL_UUID}>
        <Breadcrumb />
      </Providers>,
    );
    const current = screen.getByTestId('breadcrumb-current');
    expect(current).toHaveTextContent(SUCURSAL_OTHER_NOMBRE);
  });

  it('T6: en "/login" (path no matcheado) la miga no se renderiza', () => {
    render(<Providers initialEntries={['/login']}><Breadcrumb /></Providers>);
    expect(screen.queryByTestId('breadcrumb')).not.toBeInTheDocument();
  });

  it('T7: un detail page con useBreadcrumbs() reemplaza la cadena estática', () => {
    function DetailHarness(): JSX.Element {
      useBreadcrumbs([
        { to: '/', i18nKey: 'breadcrumb.home' },
        { to: '/usuarios', i18nKey: 'breadcrumb.section.usuarios' },
        { staticLabel: 'Ana Ruiz', current: true },
      ]);
      return <Breadcrumb />;
    }
    render(
      <Providers initialEntries={['/usuarios/abc-123']}>
        <DetailHarness />
      </Providers>,
    );
    const current = screen.getByTestId('breadcrumb-current');
    expect(current).toHaveTextContent('Ana Ruiz');
  });

  it('T8: los links conservan el path base, ignorando el querystring', () => {
    render(
      <Providers initialEntries={['/usuarios?estado=activo&pagina=2']}>
        <Breadcrumb />
      </Providers>,
    );
    const link = screen.getByTestId('breadcrumb-link');
    expect(link).toHaveAttribute('href', '/');
  });

  it('T9: el separador entre segmentos es decorativo (aria-hidden)', () => {
    render(<Providers initialEntries={['/usuarios']}><Breadcrumb /></Providers>);
    const nav = screen.getByTestId('breadcrumb');
    const lis = nav.querySelectorAll('li');
    expect(lis.length).toBeGreaterThanOrEqual(3);
    const separators = Array.from(lis).filter((li) => li.getAttribute('aria-hidden') === 'true');
    expect(separators.length).toBeGreaterThanOrEqual(1);
  });

  it('T10: en "/tarifas" (branch-scoped) sin seleccionada no se prepende', () => {
    render(
      <Providers initialEntries={['/tarifas']} selectedUuid={null}>
        <Breadcrumb />
      </Providers>,
    );
    const links = screen.getAllByTestId('breadcrumb-link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', '/');
    const current = screen.getByTestId('breadcrumb-current');
    expect(current).toHaveTextContent(/tarifas/i);
  });

  it('T11: en "/tarifas" con sucursal activa, el branch link va a /dashboard', () => {
    render(
      <Providers initialEntries={['/tarifas']} selectedUuid={SUCURSAL_UUID}>
        <Breadcrumb />
      </Providers>,
    );
    const links = screen.getAllByTestId('breadcrumb-link');
    // Inicio → Sucursales → BOG-CEN → Tarifas (current)
    expect(links).toHaveLength(3);
    expect(links[0]).toHaveAttribute('href', '/');
    expect(links[1]).toHaveAttribute('href', '/seleccionar-sucursal');
    expect(links[1]).toHaveTextContent(/sucursales/i);
    expect(links[2]).toHaveAttribute('href', '/dashboard');
    expect(links[2]).toHaveTextContent(SUCURSAL_NOMBRE);
    const current = screen.getByTestId('breadcrumb-current');
    expect(current).toHaveTextContent(/tarifas/i);
  });
});
