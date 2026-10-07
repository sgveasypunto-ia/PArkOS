/**
 * FC2 — the cotización panel labelled every tariff "/min", but the tariff
 * row's unit depends on its modalidad (`uuid_tipo_tarifa`, fixed uuids seeded by
 * migration 0071): the 1500 shown as "$ 1.500/min" was the HOURLY tariff.
 */
import { describe, it, expect } from 'vitest';

import { etiquetaUnidadTarifa } from './modalidadTarifa';

describe('etiquetaUnidadTarifa', () => {
  it.each([
    ['12e3886a-7059-47ee-bdb2-aa5fb1272bea', '/hora'],
    ['c41b6602-f7b2-437d-bcfc-0462cd385eda', '/fracción'],
    ['d83ebff8-9546-43b3-91b1-bedffa57717f', '/día'],
    ['9f8ba4a9-6fd9-4da7-8ddb-97ce323a8600', '/noche'],
  ])('%s → %s', (uuid, esperado) => {
    expect(etiquetaUnidadTarifa(uuid)).toBe(esperado);
  });

  it('es insensible a mayúsculas', () => {
    expect(etiquetaUnidadTarifa('12E3886A-7059-47EE-BDB2-AA5FB1272BEA')).toBe('/hora');
  });

  it.each([[null], [undefined], [''], ['00000000-0000-0000-0000-000000000000'], ['otro']])(
    'modalidad desconocida (%s) → sin unidad (nunca inventa "/min")',
    (uuid) => {
      expect(etiquetaUnidadTarifa(uuid as string | null | undefined)).toBe('');
    },
  );
});
