/**
 * `admin-sections.ts` — the gating rule that mirrors the backend.
 *
 * The load-bearing assertion is A2: a section whose backend route has NO
 * `require_permission` dep must stay visible even when the permission
 * array is empty. Encoding the permission NAME there would hide working
 * features and conceal the backend's over-permission.
 */
import { describe, expect, it } from 'vitest';

import { ADMIN_SECTIONS, visibleSections } from './admin-sections';

describe('visibleSections', () => {
  it('A1: hides a permission-gated section when the code is absent', () => {
    const keys = visibleSections([]).map((s) => s.key);
    expect(keys).not.toContain('auditoria');
  });

  it('A2: shows issuer-only sections even with an empty permission array', () => {
    // The backend gates Panel/Sucursales/Usuarios on the `admin-` issuer
    // alone, so a stricter UI would under-report real access.
    const keys = visibleSections([]).map((s) => s.key);
    expect(keys).toEqual(expect.arrayContaining(['dashboard', 'sucursales', 'usuarios']));
  });

  it('A3: reveals Auditoría once audit_read is granted (3 issuer-only + 1)', () => {
    // With just `audit_read`, the operator sees the 3 issuer-only
    // surfaces (dashboard / sucursales / usuarios) plus the audit
    // surface. Tarifas and Cupos require their own codes
    // (config_tarifas, config_cupos) which A3 does not grant.
    const keys = visibleSections(['audit_read']).map((s) => s.key);
    expect(keys).toContain('auditoria');
    expect(keys).toHaveLength(4);
  });

  it('A4: an unrelated permission does not unlock Auditoría', () => {
    const keys = visibleSections(['admin_usuarios', 'config_sucursal']).map((s) => s.key);
    expect(keys).not.toContain('auditoria');
  });

  it('A5: catalog paths are unique and every gated entry names its code', () => {
    const paths = ADMIN_SECTIONS.map((s) => s.path);
    expect(new Set(paths).size).toBe(paths.length);
    for (const section of ADMIN_SECTIONS) {
      if (section.permission !== null) {
        expect(section.permission).toBeTruthy();
      }
    }
  });

  it('A6: the catalog advertises every route the SPA can navigate to', () => {
    // PR-D added /tarifas and /cupos; the catalog must reflect both
    // or the user navigates to a 404 from a card that exists in the UI.
    expect(ADMIN_SECTIONS.map((s) => s.key)).toEqual([
      'dashboard',
      'sucursales',
      'usuarios',
      'tarifas',
      'cupos',
      'auditoria',
    ]);
  });

  it('A7: reveals Tarifas once config_tarifas is granted', () => {
    const keys = visibleSections(['config_tarifas']).map((s) => s.key);
    expect(keys).toContain('tarifas');
  });

  it('A8: reveals Cupos once config_cupos is granted', () => {
    const keys = visibleSections(['config_cupos']).map((s) => s.key);
    expect(keys).toContain('cupos');
  });
});
