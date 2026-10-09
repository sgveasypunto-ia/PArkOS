import { describe, expect, it } from 'vitest';

import { contarSesiones, esSesionAbierta } from './sesionEstado';

const base = {
  uuid_sesion: null,
  uuid_usuario: null,
  timestamp_apertura: null,
  valor_efectivo_esperado: null,
  valor_efectivo_reportado: null,
  uuid_arqueo: null,
};

describe('sesionEstado', () => {
  it('estado "abierta" del backend (sin timestamp_cierre) es abierta', () => {
    expect(
      esSesionAbierta({ ...base, estado: 'abierta', timestamp_cierre: null }),
    ).toBe(true);
  });

  it('estado "cerrada" del backend es cerrada (no abierta)', () => {
    expect(
      esSesionAbierta({
        ...base,
        estado: 'cerrada',
        timestamp_cierre: '2026-09-21T18:00:00Z',
      }),
    ).toBe(false);
  });

  it('un timestamp_cierre presente es cerrada aunque el estado sea ambiguo', () => {
    expect(
      esSesionAbierta({
        ...base,
        estado: null,
        timestamp_cierre: '2026-09-21T18:00:00Z',
      }),
    ).toBe(false);
  });

  it('contarSesiones devuelve abiertas y total', () => {
    expect(
      contarSesiones([
        { ...base, estado: 'abierta', timestamp_cierre: null },
        {
          ...base,
          estado: 'cerrada',
          timestamp_cierre: '2026-09-21T18:00:00Z',
        },
      ]),
    ).toEqual({ abiertas: 1, total: 2 });
    expect(contarSesiones([])).toEqual({ abiertas: 0, total: 0 });
  });
});
