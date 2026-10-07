/**
 * `router.test.ts` -- REQ-OPS-199 / D3 drill-down regression guard.
 *
 * F12.1.1 dropped the `diferencia_datafono` datafono decision from the
 * alert emission path (REQ-OPS-196). The FE drill-down route in
 * `router.ts:44` MUST nonetheless remain in place: alerts with
 * `valor_diferencia_datafono != 0` pre-dating F12.1.1 are preserved in the
 * bitácora (D3, no-DELETE compliance), and operators must be able to
 * navigate from those legacy rows to the arqueo detail page.
 *
 * The router map (`DRILL_DOWN_ROUTES`) is the single source of truth for
 * per-`tipo_alerta` drill-down. This test pins:
 *   S1: `diferencia_datafono` is a registered drill-down key (no removal).
 *   S2: `diferencia_datafono` routes to `/caja/arqueo/{uuid_arqueo}` when
 *       the alert carries `uuid_arqueo`, otherwise the default fallback.
 *   S3: `drillDownHref` resolves `diferencia_datafono` deterministically.
 *
 * The drill-down target matches the canonical arqueo detail route -- no
 * new route, no UI breakage for historical alerts.
 */
import { describe, it, expect } from 'vitest';

import type { MergedAlerta } from '../../api/schemas/alertas';
import { DRILL_DOWN_ROUTES, drillDownHref } from '../router';

const VALID_UUID_ARQUEO = '00000000-0000-0000-0000-000000000aaa';

// The router only reads `uuid`, `uuid_arqueo`, `tipo_alerta` and
// `datos_nuevos`; the full `MergedAlerta` carries ~17 more fields that are
// irrelevant here, so the fixture is a deliberate partial cast.
function makeAlert(overrides: Record<string, unknown> = {}): MergedAlerta {
  return {
    uuid: '00000000-0000-0000-0000-000000000bbb',
    uuid_arqueo: VALID_UUID_ARQUEO,
    tipo_alerta: 'diferencia_datafono',
    datos_nuevos: null,
    ...overrides,
  } as unknown as MergedAlerta;
}

const baseAlert = makeAlert();

function datafonoRoute(): (alert: MergedAlerta) => string {
  const fn = DRILL_DOWN_ROUTES['diferencia_datafono'];
  if (!fn) throw new Error('diferencia_datafono drill-down route is not registered');
  return fn;
}

describe('drill-down router -- REQ-OPS-199 / D3 (F12.1.1 preservation)', () => {
  it('S1: diferencia_datafono is a registered drill-down key', () => {
    // The map is the single source of truth: the entry MUST be present
    // post-F12.1.1 so historical alertas remain navigable. This pins
    // D3 (drill-down preserved) + REQ-OPS-199.
    const fn = DRILL_DOWN_ROUTES['diferencia_datafono'];
    expect(typeof fn).toBe('function');
  });

  it('S2: diferencia_datafono routes to /caja/arqueo/{uuid_arqueo} when arqueo is set', () => {
    const href = datafonoRoute()(baseAlert);
    expect(href).toBe(`/caja/arqueo/${VALID_UUID_ARQUEO}`);
  });

  it('S2b: diferencia_datafono falls back to /alertas/{uuid} when arqueo is missing', () => {
    const href = datafonoRoute()(makeAlert({ uuid_arqueo: null }));
    expect(href).toBe(`/alertas/${baseAlert.uuid}`);
  });

  it('S3: drillDownHref resolves diferencia_datafono via the map', () => {
    expect(drillDownHref(baseAlert)).toBe(`/caja/arqueo/${VALID_UUID_ARQUEO}`);
  });

  it('S3b: drillDownHref returns default when tipo_alerta is missing', () => {
    const noTipo = makeAlert({ tipo_alerta: undefined });
    expect(drillDownHref(noTipo)).toBe(`/alertas/${baseAlert.uuid}`);
  });
});