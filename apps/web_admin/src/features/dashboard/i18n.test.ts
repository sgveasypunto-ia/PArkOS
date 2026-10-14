/**
 * `dashboard.facturasEmpty` -- regression test for the i18n key
 * updated in Bug #3 (2026-10-14).
 *
 * The pre-fix copy was "Ninguna factura activa" -- a lie. The
 * ``prod.facturas`` model has no ``estado='activa'`` (the valid
 * states are ``emitida`` / ``pagada`` / ``anulada``), so the empty
 * state could never trigger legitimately. The post-fix copy is
 * "Sin facturas" -- generic, does not lie about a state that
 * does not exist.
 *
 * The Dashboard.tsx ``t('dashboard.facturasEmpty', 'Sin facturas')``
 * call also has the same default string as a safety net for missing
 * keys (other locales fall through to the default). This test
 * covers both surfaces: the JSON bundle and the inline default
 * string inside the source.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

describe('dashboard.facturasEmpty (Bug #3 regression)', () => {
  // The test file lives at
  // ``apps/web_admin/src/features/dashboard/i18n.test.ts`` and the
  // JSON bundle sits two levels up at
  // ``apps/web_admin/src/i18n/locales/es-CO.json``. ``process.cwd()``
  // when vitest runs is the package root (``apps/web_admin``), so
  // we resolve relative to that -- the path is independent of
  // where the test file is, and the assertion survives a rename of
  // either side.
  const esCO = JSON.parse(
    readFileSync(
      resolve(process.cwd(), 'src', 'i18n', 'locales', 'es-CO.json'),
      'utf8',
    ),
  ) as Record<string, unknown>;

  it('es-CO locale has the post-fix copy', () => {
    // The Zod schema doesn't apply here -- the i18n bundle is a
    // plain JSON map. Direct lookup is the simplest, most readable
    // assertion.
    const dashboard = esCO.dashboard as Record<string, unknown> | undefined;
    expect(dashboard, 'es-CO.json must expose a "dashboard" key').toBeDefined();
    expect(dashboard?.facturasEmpty).toBe('Sin facturas');
  });

  it('does not regress to the pre-fix "activa" copy', () => {
    // Hard guard: if someone refactors the empty-state copy back to
    // an "activa" phrasing (which is not a valid ``prod.facturas``
    // estado), this test fails. The dashboard's empty state is
    // about the absence of rows, not about a "not-active" filter.
    const dashboard = esCO.dashboard as Record<string, unknown> | undefined;
    const value = dashboard?.facturasEmpty as string | undefined;
    expect(value).not.toMatch(/activa/i);
  });

  it('Dashboard.tsx inline default matches the JSON key (no drift)', () => {
    // The Dashboard.tsx source has
    //   t('dashboard.facturasEmpty', 'Sin facturas')
    // -- the second arg is the safety net for missing keys. If the
    // source and the JSON drift, the FE renders inconsistent copy
    // across deployments. This is a cheap regex on the file source.
    const srcPath = resolve(process.cwd(), 'src', 'features', 'dashboard', 'pages', 'Dashboard.tsx');
    const src = readFileSync(srcPath, 'utf8');
    expect(src).toMatch(/t\(\s*'dashboard\.facturasEmpty',\s*'Sin facturas'\s*\)/);
  });
});

