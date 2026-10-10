/**
 * `AppSidebar` — invariantes que el resto del repo no debe romper.
 *
 * T1: el sidebar es un `<aside>` con `aria-label` resoluble via i18n
 *     y queda dentro de la layout shell.
 * T2: cada item declarado se renderiza como `<a>` con href + nombre
 *     accesible (data-driven: agregar un item no requiere tocar este
 *     test, solo `HUB_CARDS`).
 * T3: el item activo (path = URL actual) recibe `aria-current="page"`
 *     via `<NavLink>`.
 * T4: filtrado por permisos -- los items con `permission: null` son
 *     visibles para cualquier actor; los que declaran un string se
 *     filtran contra `permisos[]`.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Building2 } from 'lucide-react';

import { AppSidebar, type SidebarItem } from './AppSidebar';

const SAMPLE_ITEMS: readonly SidebarItem[] = [
  {
    key: 'home',
    path: '/',
    icon: Building2,
    labelKey: 'home.label',
    permission: null,
    testId: 'app-sidebar-item-home',
  },
  {
    key: 'catalogos',
    path: '/catalogos',
    icon: Building2,
    labelKey: 'catalogos.label',
    permission: 'config_catalogo',
    testId: 'app-sidebar-item-catalogos',
  },
  {
    key: 'auditoria',
    path: '/auditoria/log',
    icon: Building2,
    labelKey: 'auditoria.label',
    permission: 'audit_read',
    testId: 'app-sidebar-item-auditoria',
  },
];

function renderSidebar(
  initialPath: string,
  permisos: readonly string[] = [],
  items: readonly SidebarItem[] = SAMPLE_ITEMS,
) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppSidebar items={items} permisos={permisos} />
    </MemoryRouter>,
  );
}

describe('AppSidebar', () => {
  it('T1: renderiza como <aside> con aria-label de i18n', () => {
    renderSidebar('/');
    const sidebar = screen.getByTestId('app-sidebar');
    expect(sidebar.tagName).toBe('ASIDE');
    expect(sidebar).toHaveAttribute('aria-label');
  });

  it('T2: cada item se renderiza como <a> con href y nombre accesible', () => {
    renderSidebar('/', ['config_catalogo', 'audit_read']);
    for (const item of SAMPLE_ITEMS) {
      const el = screen.getByTestId(item.testId);
      expect(el.tagName, `${item.key} debe ser <a>`).toBe('A');
      expect(el, `${item.key} href`).toHaveAttribute('href', item.path);
      expect(el, `${item.key} accessible name`).toHaveAccessibleName();
    }
  });

  it('T3: el item activo recibe aria-current="page" via NavLink', () => {
    renderSidebar('/catalogos', ['config_catalogo', 'audit_read']);
    const active = screen.getByTestId('app-sidebar-item-catalogos');
    expect(active).toHaveAttribute('aria-current', 'page');
    // Los demás items NO deben tener aria-current
    expect(screen.getByTestId('app-sidebar-item-home')).not.toHaveAttribute(
      'aria-current',
    );
    expect(screen.getByTestId('app-sidebar-item-auditoria')).not.toHaveAttribute(
      'aria-current',
    );
  });

  it('T4: con permisos=[] solo se ven los items permission:null', () => {
    renderSidebar('/', []);
    expect(screen.getByTestId('app-sidebar-item-home')).toBeInTheDocument();
    expect(
      screen.queryByTestId('app-sidebar-item-catalogos'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('app-sidebar-item-auditoria'),
    ).not.toBeInTheDocument();
  });

  it('T4b: con permisos parciales, se filtran los items correspondientes', () => {
    renderSidebar('/', ['config_catalogo']);
    expect(screen.getByTestId('app-sidebar-item-home')).toBeInTheDocument();
    expect(screen.getByTestId('app-sidebar-item-catalogos')).toBeInTheDocument();
    expect(
      screen.queryByTestId('app-sidebar-item-auditoria'),
    ).not.toBeInTheDocument();
  });

  it('T4c: con todos los permisos, se ven todos los items', () => {
    renderSidebar('/', ['config_catalogo', 'audit_read']);
    for (const item of SAMPLE_ITEMS) {
      expect(screen.getByTestId(item.testId)).toBeInTheDocument();
    }
  });

  it('T5: el item root (path="/") usa `end` para no matchear todas las rutas', () => {
    // / tiene `end={true}` en NavLink -- en /dashboard NO debe marcarse
    // activo. Verificamos que el item "home" (path="/") con permisos
    // [config_catalogo, audit_read] NO tiene aria-current cuando
    // estamos parados en /catalogos.
    renderSidebar('/catalogos', ['config_catalogo', 'audit_read']);
    expect(screen.getByTestId('app-sidebar-item-home')).not.toHaveAttribute(
      'aria-current',
    );
  });
});
