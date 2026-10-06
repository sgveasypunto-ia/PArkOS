import { describe, expect, it } from 'vitest';

import { planAceptaTipos, planesCompatibles, tiposDistintos } from './planes';

const ANY = { uuid: 'any', uuid_tipo_vehiculo: null };
const CARRO = { uuid: 'carro', uuid_tipo_vehiculo: 't-carro' };
const MOTO = { uuid: 'moto', uuid_tipo_vehiculo: 't-moto' };
const LEGACY = { uuid: 'legacy' }; // server without the column

describe('planes <-> tipo de vehículo (PT-2)', () => {
  it('tiposDistintos drops empties/nulls and dedupes', () => {
    expect(tiposDistintos(['a', null, undefined, '', 'a', 'b'])).toEqual(['a', 'b']);
  });

  it('a plan without type accepts any vehicle type', () => {
    expect(planAceptaTipos(ANY, ['t-carro'])).toBe(true);
    expect(planAceptaTipos(LEGACY, ['t-moto', 't-carro'])).toBe(true);
  });

  it('a typed plan accepts only that type', () => {
    expect(planAceptaTipos(CARRO, ['t-carro'])).toBe(true);
    expect(planAceptaTipos(CARRO, ['t-moto'])).toBe(false);
    expect(planAceptaTipos(CARRO, ['t-carro', 't-moto'])).toBe(false);
  });

  it('with no vehicles every plan is offered', () => {
    expect(planesCompatibles([ANY, CARRO, MOTO], []).map((p) => p.uuid)).toEqual([
      'any',
      'carro',
      'moto',
    ]);
  });

  it('filters to the plans compatible with the vehicles chosen', () => {
    expect(planesCompatibles([ANY, CARRO, MOTO], ['t-moto']).map((p) => p.uuid)).toEqual([
      'any',
      'moto',
    ]);
    expect(planesCompatibles([ANY, CARRO, MOTO], ['t-moto', 't-carro']).map((p) => p.uuid)).toEqual([
      'any',
    ]);
  });
});
