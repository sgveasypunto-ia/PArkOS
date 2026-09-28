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

  it('A3: reveals Auditoría once audit_read is granted', () => {
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

  it('A6: the catalog advertises no route that does not exist yet', () => {
    // Cupos, tarifas and reports are deliberately absent — a hub that
    // links to unimplemented surfaces is worse than a smaller honest one.
    expect(ADMIN_SECTIONS.map((s) => s.key)).toEqual([
      'dashboard',
      'sucursales',
      'usuarios',
      'auditoria',
    ]);
  });
});
