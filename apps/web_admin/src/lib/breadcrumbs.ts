/**
 * `breadcrumbs.ts` — single source of truth for the admin breadcrumb
 * trail. One entry per route declared in `App.tsx`; the ChromeShell
 * matches the current `pathname` against the table and renders the
 * resulting list below the TopNav.
 *
 * Design (HU-breadcrumbs-1):
 *   - The list of segments per route is STATIC, not derived at runtime
 *     from `pathname` segments, so a route like `/usuarios` always says
 *     "Inicio → Usuarios" (not "Inicio → usuarios"). Mirrors the
 *     convention `lib/admin-sections.ts` and `HUB_CARDS` already use.
 *   - When a route is a `:uuid` placeholder, the table only declares
 *     the static portion (e.g. "Inicio → Usuarios → Detalle"). Detail
 *     pages that want a meaningful last segment (user/sucursal/cliente
 *     name) opt in via `useBreadcrumbs()` (`lib/useBreadcrumbs.ts`),
 *     which REPLACES the placeholder via the breadcrumbs context.
 *   - Routes inside the branch-scoped group (`<RequireSucursal>`)
 *     declare `branchScoped: true` so the resolver prepends a
 *     "SucursalActiva" segment using `useSucursal().selected`. The
 *     detail page `/sucursales/:uuid` is NOT branchScoped -- it shows
 *     the URL branch's name, not the active one.
 *   - Labels prefer existing i18n keys (`home.section.*`, `homeHub.*`,
 *     `breadcrumb.*`) so the breadcrumb text follows whatever the rest
 *     of the app already shows. NO new duplicated strings.
 */
import type { ReactNode } from 'react';

/**
 * A `Crumb` is the FINAL shape rendered by `<Breadcrumb />`. The table
 * declares `CrumbTemplate`s (a more compact form) which the resolver
 * turns into `Crumb`s at runtime.
 */
export interface Crumb {
  /** Path WITHOUT querystring -- the click target. */
  to?: string;
  /** Final label rendered. Either an i18n key, a static string, or a ReactNode (for rich cases). */
  label?: string | ReactNode;
  /** I18n key to resolve at render time. Mutually exclusive with `staticLabel`. */
  i18nKey?: string;
  /** Static label, resolved at table declaration. */
  staticLabel?: string;
  /** Last segment in the chain: rendered as `aria-current="page"`, no link. */
  current?: boolean;
}

export interface CrumbTemplate {
  /** Path WITHOUT querystring, the click target. Optional for the last segment (no link when `current`). */
  to?: string;
  /** I18n key (preferred) for the label, or `staticLabel` for hard-coded text. */
  i18nKey?: string;
  staticLabel?: string;
  /** Mark the last segment as the current page. */
  current?: boolean;
}

export interface BreadcrumbEntry {
  /**
   * Either an exact path match or a `:param` pattern. Patterns are
   * matched in declaration order; FIRST match wins. Order matters --
   * more-specific patterns (`/auditoria/log/:uuid`) MUST come before
   * less-specific ones (`/auditoria/log`).
   */
  match: 'exact' | 'prefix';
  pattern: string;
  /** Static chain of segments. The resolver may PREPEND a branch segment (see `branchScoped`). */
  crumbs: readonly CrumbTemplate[];
  /**
   * `true` for routes inside the branch-scoped group (`<RequireSucursal>`)
   * so the resolver prepends a "SucursalActiva" segment using the
   * selected branch. Default: `false` (no branch segment).
   */
  branchScoped?: boolean;
}

/**
 * `BREADCRUMB_ROUTES` — ordered list. More specific first.
 *
 * Conventions:
 *   - All routes start with `Inicio` (i18nKey `breadcrumb.home`).
 *   - Static labels reuse existing i18n keys so we don't duplicate copy.
 *   - Detail pages (`/usuarios/:uuid`, `/sucursales/:uuid`,
 *     `/clientes/:uuid`, `/alertas/:uuid`, etc.) use the placeholder
 *     "Detalle" — detail pages may override via `useBreadcrumbs()` to
 *     show the resource's real name.
 */
export const BREADCRUMB_ROUTES: readonly BreadcrumbEntry[] = [
  // ---- Detail routes (more specific) ----
  {
    match: 'prefix',
    pattern: '/usuarios/:uuid',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { to: '/usuarios', i18nKey: 'breadcrumb.section.usuarios' },
      { i18nKey: 'breadcrumb.detail' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/sucursales/:uuid',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { to: '/seleccionar-sucursal', i18nKey: 'breadcrumb.section.sucursales' },
      { i18nKey: 'breadcrumb.detail' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/clientes/:uuid',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { to: '/clientes', i18nKey: 'breadcrumb.section.clientes' },
      { i18nKey: 'breadcrumb.detail' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/alertas/:uuid',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { to: '/alertas', i18nKey: 'breadcrumb.section.alertas' },
      { i18nKey: 'breadcrumb.detail' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/anulaciones/:uuid',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { to: '/anulaciones', i18nKey: 'breadcrumb.section.anulaciones' },
      { i18nKey: 'breadcrumb.detail' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/reclamos/:uuid',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { to: '/reclamos', i18nKey: 'breadcrumb.section.reclamos' },
      { i18nKey: 'breadcrumb.detail' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/dian/:uuid',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { to: '/dian', i18nKey: 'breadcrumb.section.dian' },
      { i18nKey: 'breadcrumb.detail' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/auditoria/log/:uuid',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { to: '/auditoria/log', i18nKey: 'breadcrumb.section.auditoria' },
      { i18nKey: 'breadcrumb.detail' },
    ],
  },
  // ---- Branch-scoped detail (more specific than branch-scoped lists) ----
  {
    match: 'prefix',
    pattern: '/reporteria/financiera',
    branchScoped: true,
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { to: '/reporteria', i18nKey: 'breadcrumb.section.reporteria' },
      { i18nKey: 'breadcrumb.reporteriaFinanciera' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/reporteria/suscripciones',
    branchScoped: true,
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { to: '/reporteria', i18nKey: 'breadcrumb.section.reporteria' },
      { i18nKey: 'breadcrumb.reporteriaSuscripciones' },
    ],
  },
  // ---- Branch-scoped lists ----
  {
    match: 'prefix',
    pattern: '/dashboard',
    branchScoped: true,
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.dashboard' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/tarifas',
    branchScoped: true,
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.tarifas' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/cupos',
    branchScoped: true,
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.cupos' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/tipos-vehiculo',
    branchScoped: true,
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.tiposVehiculo' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/tipo-tarifa',
    branchScoped: true,
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.tipoTarifa' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/configuracion-tolerancias',
    branchScoped: true,
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.configuracionTolerancias' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/configuracion-seguridad',
    branchScoped: true,
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.configuracionSeguridad' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/reporteria',
    branchScoped: true,
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.reporteria' },
    ],
  },
  {
    match: 'prefix',
    pattern: '/audit',
    branchScoped: true,
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.auditoria' },
    ],
  },
  // ---- Global (authed, no branch) ----
  {
    match: 'exact',
    pattern: '/seleccionar-sucursal',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.sucursales' },
    ],
  },
  {
    match: 'exact',
    pattern: '/catalogos',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.catalogos' },
    ],
  },
  {
    match: 'exact',
    pattern: '/empresa',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.empresa' },
    ],
  },
  {
    match: 'exact',
    pattern: '/usuarios',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.usuarios' },
    ],
  },
  {
    match: 'exact',
    pattern: '/clientes',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.clientes' },
    ],
  },
  {
    match: 'exact',
    pattern: '/arqueos',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.arqueos' },
    ],
  },
  {
    match: 'exact',
    pattern: '/pairing',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.pairing' },
    ],
  },
  {
    match: 'exact',
    pattern: '/alertas',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.alertas' },
    ],
  },
  {
    match: 'exact',
    pattern: '/anulaciones',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.anulaciones' },
    ],
  },
  {
    match: 'exact',
    pattern: '/reclamos',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.reclamos' },
    ],
  },
  {
    match: 'exact',
    pattern: '/sync',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.sync' },
    ],
  },
  {
    match: 'exact',
    pattern: '/dian',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.dian' },
    ],
  },
  {
    match: 'exact',
    pattern: '/auditoria/log',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.auditoria' },
      { i18nKey: 'breadcrumb.section.bitacora' },
    ],
  },
  {
    match: 'exact',
    pattern: '/auditoria/verify-chain',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.auditoria' },
      { i18nKey: 'breadcrumb.section.verifyChain' },
    ],
  },
  {
    match: 'exact',
    pattern: '/auditoria/buscar',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.auditoria' },
      { i18nKey: 'breadcrumb.section.buscarGlobal' },
    ],
  },
  {
    match: 'exact',
    pattern: '/perfil',
    crumbs: [
      { to: '/', i18nKey: 'breadcrumb.home' },
      { i18nKey: 'breadcrumb.section.perfil' },
    ],
  },
  {
    match: 'exact',
    pattern: '/',
    crumbs: [{ i18nKey: 'breadcrumb.home' }],
  },
];

/**
 * `matchBreadcrumb(pathname)` — find the entry whose pattern matches
 * the given URL. Returns `null` for unmatched paths so the caller can
 * hide the breadcrumb (e.g. on `/login`).
 *
 * Matching:
 *   - `exact`: pathname === pattern
 *   - `prefix`: pattern with `:param` tokens; the segment count MUST
 *     match exactly, AND each literal segment must match literally.
 *     `/usuarios/:uuid` matches `/usuarios/abc-123` but NOT
 *     `/usuarios/abc-123/extra`. (That's the only sensible meaning --
 *     prefixing a `:uuid` would leak unrelated nested routes.)
 *
 * The first match wins; ordering in `BREADCRUMB_ROUTES` is the
 * stability contract.
 */
export function matchBreadcrumb(pathname: string): BreadcrumbEntry | null {
  for (const entry of BREADCRUMB_ROUTES) {
    if (matches(entry, pathname)) {
      return entry;
    }
  }
  return null;
}

function matches(entry: BreadcrumbEntry, pathname: string): boolean {
  if (entry.match === 'exact') {
    return entry.pattern === pathname;
  }
  return matchPrefix(entry.pattern, pathname);
}

function matchPrefix(pattern: string, pathname: string): boolean {
  const patternSegs = pattern.split('/').filter((s) => s.length > 0);
  const pathSegs = pathname.split('/').filter((s) => s.length > 0);
  if (patternSegs.length !== pathSegs.length) {
    return false;
  }
  for (let i = 0; i < patternSegs.length; i++) {
    const pSeg = patternSegs[i] ?? '';
    const aSeg = pathSegs[i] ?? '';
    if (pSeg.startsWith(':')) {
      // Param token: matches any non-empty segment.
      if (aSeg.length === 0) return false;
      continue;
    }
    if (pSeg !== aSeg) return false;
  }
  return true;
}

/**
 * Normalize a `CrumbTemplate` into a `Crumb`. The resolver calls this
 * after deciding which `to` and `label` to use; the `current` flag is
 * applied to the LAST crumb in the chain by the consumer.
 */
export function templateToCrumb(template: CrumbTemplate): Crumb {
  const crumb: Crumb = { to: template.to };
  if (template.i18nKey !== undefined) {
    crumb.i18nKey = template.i18nKey;
  } else if (template.staticLabel !== undefined) {
    crumb.staticLabel = template.staticLabel;
    crumb.label = template.staticLabel;
  } else {
    crumb.label = template.to;
  }
  return crumb;
}
