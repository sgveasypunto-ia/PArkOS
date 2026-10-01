/**
 * `admin-sections.ts` — the single source of truth for the admin's
 * navigable surfaces. Both `<AdminShell />`'s nav and `<Home />`'s card
 * grid read from this list so they cannot drift apart.
 *
 * PERMISSION COLUMN IS NOT A POLICY WISH — IT MIRRORS THE BACKEND.
 * Audited 2026-09-27 against the live routes:
 *
 *   Section            Route(s)                                  Actual gate
 *   ─────────────────────────────────────────────────────────────────────────
 *   Panel de sucursal  GET /admin/me                            admin- issuer only
 *                      GET /sucursales                          admin- issuer only
 *                      GET /admin/sucursales/{uuid}/dashboard    admin- issuer only
 *   Sucursales         GET /sucursales                          admin- issuer only
 *   Usuarios           * /admin/usuarios                        admin- issuer only
 *   Reportería         GET /operacion/ingresos, /operacion/salidas,
 *                            /operacion/ocupacion               admin-/operador- issuer + branch_scope (PR-A)
 *   Auditoría          * /audit/*                               admin- issuer + audit_read
 *
 * `admin_usuarios.py` and `admin_views.py` depend on
 * `requires_issuer("admin-")` and nothing else — there is no
 * `require_permission(...)` on any of those endpoints. Only
 * `audit.py` carries a permission dep (`require_permission("audit_read")`,
 * line 59).
 *
 * So three of the four sections are reachable by ANY admin-issued JWT
 * regardless of the `permissions` array. This catalog encodes that
 * reality: `permission: null` means "no gate exists to mirror", NOT
 * "everyone should see it by design".
 *
 * Why not gate them on `admin_usuarios` / `config_sucursal` anyway,
 * which is what the permission names suggest? Because the UI would then
 * under-report real access: an admin without `admin_usuarios` would be
 * shown no Usuarios card, click nothing, and conclude the feature is
 * broken — while `GET /admin/usuarios` would have happily returned every
 * user in the tenant. Hiding an over-permission behind a stricter UI is
 * the wrong direction: it conceals the backend gap instead of surfacing
 * it. The gap is tracked for the backend, not papered over in the SPA.
 *
 * Adding a real `require_permission` dep to those routers is a backend
 * change; when it lands, flip the `permission` field here and the UI
 * follows in the same PR that closes it.
 */

/** Mirrors the backend's gate: `null` = issuer-only, no permission dep. */
export type SectionPermission = string | null;

export interface AdminSection {
  /** Stable key for testids + i18n lookup. */
  key:
    | 'dashboard'
    | 'sucursales'
    | 'catalogos'
    | 'gestion-usuarios'
    | 'tarifas'
    | 'cupos'
    | 'tipos-vehiculo'
    | 'tipo-tarifa'
    | 'configuracion-tolerancias'
    | 'configuracion-seguridad'
    | 'reporteria'
    | 'auditoria';
  path: string;
  /** i18n key suffix under `home.section.*`. */
  labelKey: string;
  descriptionKey: string;
  permission: SectionPermission;
}

export const ADMIN_SECTIONS: readonly AdminSection[] = [
  {
    key: 'dashboard',
    path: '/dashboard',
    labelKey: 'home.section.dashboard.label',
    descriptionKey: 'home.section.dashboard.description',
    permission: null,
  },
  {
    key: 'sucursales',
    path: '/sucursales',
    labelKey: 'home.section.sucursales.label',
    descriptionKey: 'home.section.sucursales.description',
    permission: null,
  },
  {
    key: 'catalogos',
    path: '/catalogos',
    labelKey: 'home.section.catalogos.label',
    descriptionKey: 'home.section.catalogos.description',
    permission: 'config_catalogo',
  },
  {
    key: 'gestion-usuarios',
    path: '/gestion-usuarios',
    labelKey: 'home.section.gestionUsuarios.label',
    descriptionKey: 'home.section.gestionUsuarios.description',
    permission: null,
  },
  {
    key: 'tarifas',
    path: '/tarifas',
    labelKey: 'home.section.tarifas.label',
    descriptionKey: 'home.section.tarifas.description',
    permission: 'config_tarifas',
  },
  {
    key: 'cupos',
    path: '/cupos',
    labelKey: 'home.section.cupos.label',
    descriptionKey: 'home.section.cupos.description',
    permission: 'config_cupos',
  },
  {
    key: 'tipos-vehiculo',
    path: '/tipos-vehiculo',
    labelKey: 'home.section.tiposVehiculo.label',
    descriptionKey: 'home.section.tiposVehiculo.description',
    permission: 'config_catalogo',
  },
  {
    key: 'tipo-tarifa',
    path: '/tipo-tarifa',
    labelKey: 'home.section.tipoTarifa.label',
    descriptionKey: 'home.section.tipoTarifa.description',
    permission: 'config_catalogo',
  },
  {
    key: 'configuracion-tolerancias',
    path: '/configuracion-tolerancias',
    labelKey: 'home.section.configuracionTolerancias.label',
    descriptionKey: 'home.section.configuracionTolerancias.description',
    permission: 'config_tolerancias',
  },
  {
    key: 'configuracion-seguridad',
    path: '/configuracion-seguridad',
    labelKey: 'home.section.configuracionSeguridad.label',
    descriptionKey: 'home.section.configuracionSeguridad.description',
    permission: 'config_seguridad',
  },
  {
    // HU-F17.1: operational report list views (HU-F17.1 includes the
    // aggregate endpoints that ship in PR-C; this entry exposes the
    // raw /operacion reads the current slice has data for).
    key: 'reporteria',
    path: '/reporteria',
    labelKey: 'home.section.reporteria.label',
    descriptionKey: 'home.section.reporteria.description',
    // The /operacion read paths are gated by issuer + require_branch_scope
    // (see auth/tenancy.py), with no permission dep. Mirrors the
    // permission-null pattern of `sucursales` and `gestion-usuarios`.
    permission: null,
  },
  {
    key: 'auditoria',
    path: '/audit',
    labelKey: 'home.section.auditoria.label',
    descriptionKey: 'home.section.auditoria.description',
    permission: 'audit_read',
  },
] as const;

/**
 * Sections the actor can actually reach, given the backend gates above.
 * A `null` permission is not a filter — it always passes.
 */
export function visibleSections(permisos: readonly string[]): AdminSection[] {
  const granted = new Set(permisos);
  return ADMIN_SECTIONS.filter(
    (s) => s.permission === null || granted.has(s.permission),
  );
}
