/**
 * `router.test.ts` -- drill-down regression guard (HU-F11.2, REQ-OPS-178).
 *
 * The router map (`DRILL_DOWN_ROUTES`) is the single source of truth for
 * per-`tipo_alerta` drill-down. The codes that never had a backend emitter
 * (arqueo_sin_cerrar, caja_sin_apertura, fallo_conexion_local,
 * diferencia_datafono) were retired from the map together with the panel
 * whitelist. This test pins:
 *   S1: only live business codes are registered drill-down keys.
 *   S2: `descuadre_critico` routes to `/caja/arqueo/{uuid_arqueo}` when the
 *       alert carries `uuid_arqueo`, otherwise the default fallback.
 *   S3: `drillDownHref` resolves via the map, and falls back to the default
 *       detail route for an unknown or missing `tipo_alerta`.
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
    tipo_alerta: 'descuadre_critico',
    datos_nuevos: null,
    ...overrides,
  } as unknown as MergedAlerta;
}

const baseAlert = makeAlert();

describe('drill-down router -- REQ-OPS-178', () => {
  it('S1: retired orphan codes are not drill-down keys', () => {
    for (const code of [
      'arqueo_sin_cerrar',
      'caja_sin_apertura',
      'fallo_conexion_local',
      'diferencia_datafono',
    ]) {
      expect(DRILL_DOWN_ROUTES[code]).toBeUndefined();
    }
    expect(typeof DRILL_DOWN_ROUTES['descuadre_critico']).toBe('function');
  });

  it('S2: descuadre_critico routes to /caja/arqueo/{uuid_arqueo} when arqueo is set', () => {
    expect(drillDownHref(baseAlert)).toBe(`/caja/arqueo/${VALID_UUID_ARQUEO}`);
  });

  it('S2b: descuadre_critico falls back to /alertas/{uuid} when arqueo is missing', () => {
    expect(drillDownHref(makeAlert({ uuid_arqueo: null }))).toBe(`/alertas/${baseAlert.uuid}`);
  });

  it('S3: unknown tipo_alerta falls back to the default detail route', () => {
    expect(drillDownHref(makeAlert({ tipo_alerta: 'diferencia_datafono' }))).toBe(
      `/alertas/${baseAlert.uuid}`,
    );
  });

  it('S3b: drillDownHref returns default when tipo_alerta is missing', () => {
    const noTipo = makeAlert({ tipo_alerta: undefined });
    expect(drillDownHref(noTipo)).toBe(`/alertas/${baseAlert.uuid}`);
  });
});
