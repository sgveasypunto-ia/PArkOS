/**
 * FC1 — the ticket header printed the hard-coded placeholder company
 * ("Parkos S.A.S." / NIT 900.000.000-1 / "Operador"). The print context must
 * carry the REAL empresa (with the NIT's DV), the branch data and the logged-in
 * operator; the placeholder is only a fallback when the API fails.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { build } from '../escposBuilder';
import { renderEntradaTiqueteHtml } from '../fallbackBrowser';
import { buildEntradaPayloadFromResponse, buildReimpresionEntradaPayload } from '../printBuilder';
import {
  construirContextoImpresion,
  limpiarCacheContextoImpresion,
  resolverContextoImpresion,
} from '../contextoImpresion';
import type { PostIngresoResponse } from '../../../features/operacion/lib/ingresoApi';
import type { Ingreso } from '../../../features/operacion/api/ingresoActivoApi';

const mocks = vi.hoisted(() => ({ parkosFetch: vi.fn() }));
vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: mocks.parkosFetch,
  ParkosHttpError: class extends Error {
    status = 0;
  },
}));

const EMPRESA = {
  uuid: 'e5757f00-1d04-4e55-96f2-8b6011a2af9f',
  nombre: 'Parkos Demo Actualizado',
  nit: '900000000-5',
  regimen: 'comun',
  vigente_hasta: null,
  estado: 'activo',
};
const SUCURSAL = {
  uuid: 'e7240ab8-d32d-4f28-83ba-ecc2c2f90555',
  nombre: 'Sucursal QA E2E',
  direccion: 'Cra 45 # 10-20',
  prefijo_nombre: 'QA-E2E',
  horario: 'Lun-Sab 7:00-20:00',
  vigente_hasta: null,
  estado: 'activo',
};
const ME = {
  user: { email: 'operador.qae2e@parkos.local', nombre: 'Operador', apellido: 'QA E2E' },
  sucursal: { uuid: SUCURSAL.uuid, nombre: 'Sucursal QA E2E', prefijo_nombre: 'QA-E2E' },
};

function respuestas(): void {
  mocks.parkosFetch.mockImplementation(async (path: string) => {
    if (path.startsWith('/api/v1/empresa/empresa')) return { items: [EMPRESA], next_cursor: null };
    if (path.startsWith('/api/v1/empresa/sucursal')) return { items: [SUCURSAL], next_cursor: null };
    if (path.startsWith('/api/v1/auth/me')) return ME;
    throw new Error(`ruta inesperada ${path}`);
  });
}

function response(): PostIngresoResponse {
  return {
    uuid: '00000000-0000-4000-8000-000000000001',
    tipo_entrada: 'ROTACION',
    uuid_subscripcion_cliente: null,
    consecutivo: null,
  };
}

function ingreso(): Ingreso {
  return {
    uuid: '00000000-0000-4000-8000-000000000001',
    uuid_sucursal: SUCURSAL.uuid,
    placa: 'ABC123',
    fecha_ingreso: '2026-09-17T10:00:00Z',
    uuid_subscripcion_cliente: null,
    consecutivo: null,
  } as unknown as Ingreso;
}

beforeEach(() => {
  mocks.parkosFetch.mockReset();
  limpiarCacheContextoImpresion();
});
afterEach(() => vi.restoreAllMocks());

describe('construirContextoImpresion', () => {
  it('arma empresa real (NIT con DV), encabezado, horario y operario', () => {
    const ctx = construirContextoImpresion({ empresa: EMPRESA, sucursal: SUCURSAL, me: ME });
    expect(ctx.empresa).toEqual({
      nombre: 'Parkos Demo Actualizado',
      nit: '900000000-5',
      direccion: 'Cra 45 # 10-20',
      regimen: 'Comun',
    });
    expect(ctx.sucursalEncabezado).toBe('Sucursal QA E2E');
    expect(ctx.horarioAtencion).toBe('Lun-Sab 7:00-20:00');
    expect(ctx.operario).toBe('Operador QA E2E');
  });

  it('sin nombre usa el correo del operador; sin datos no inventa nada', () => {
    const ctx = construirContextoImpresion({
      empresa: null,
      sucursal: null,
      me: { user: { email: 'a@b.local' }, sucursal: null },
    });
    expect(ctx.operario).toBe('a@b.local');
    expect(ctx.empresa).toBeUndefined();
    expect(ctx.sucursalEncabezado).toBeUndefined();
  });

  it('campos nulos de la empresa quedan rotulados, nunca vacíos', () => {
    const ctx = construirContextoImpresion({
      empresa: { ...EMPRESA, nit: null, regimen: null },
      sucursal: { ...SUCURSAL, direccion: null },
      me: null,
    });
    expect(ctx.empresa?.nit).toBe('No registrado');
    expect(ctx.empresa?.regimen).toBe('No registrado');
    expect(ctx.empresa?.direccion).toBe('Sin direccion registrada');
  });
});

describe('resolverContextoImpresion', () => {
  it('consulta empresa, sucursal y auth/me una sola vez (cache)', async () => {
    respuestas();
    const a = await resolverContextoImpresion();
    const b = await resolverContextoImpresion();
    expect(a.empresa?.nit).toBe('900000000-5');
    expect(b).toBe(a);
    expect(mocks.parkosFetch).toHaveBeenCalledTimes(3);
  });

  it('toma la sucursal del operador entre las devueltas', async () => {
    mocks.parkosFetch.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/v1/empresa/empresa')) return { items: [EMPRESA], next_cursor: null };
      if (path.startsWith('/api/v1/empresa/sucursal'))
        return {
          items: [{ ...SUCURSAL, uuid: 'otra', nombre: 'Otra', direccion: 'Otra dir' }, SUCURSAL],
          next_cursor: null,
        };
      return ME;
    });
    const ctx = await resolverContextoImpresion();
    expect(ctx.sucursalEncabezado).toBe('Sucursal QA E2E');
    expect(ctx.empresa?.direccion).toBe('Cra 45 # 10-20');
  });

  it('si la API falla devuelve contexto vacío (fallback) y avisa en consola', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    mocks.parkosFetch.mockRejectedValue(new Error('boom'));
    const ctx = await resolverContextoImpresion();
    expect(ctx.empresa).toBeUndefined();
    expect(ctx.operario).toBeUndefined();
    expect(warn).toHaveBeenCalled();
  });

  it('una API colgada no bloquea la impresión: tras el plazo cae al fallback', async () => {
    vi.useFakeTimers();
    try {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      mocks.parkosFetch.mockImplementation(() => new Promise(() => undefined));
      const pendiente = resolverContextoImpresion();
      await vi.advanceTimersByTimeAsync(5_000);
      await expect(pendiente).resolves.toEqual({});
      expect(warn).toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('un fallo no queda cacheado: el siguiente intento vuelve a pedir', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    mocks.parkosFetch.mockRejectedValueOnce(new Error('boom'));
    mocks.parkosFetch.mockRejectedValueOnce(new Error('boom'));
    mocks.parkosFetch.mockRejectedValueOnce(new Error('boom'));
    await resolverContextoImpresion();
    respuestas();
    const ctx = await resolverContextoImpresion();
    expect(ctx.empresa?.nombre).toBe('Parkos Demo Actualizado');
  });
});

describe('los builders usan el contexto real', () => {
  it('ingreso: empresa y operario reales en payload, ESC/POS y HTML', async () => {
    respuestas();
    const ctx = await resolverContextoImpresion();
    const payload = buildEntradaPayloadFromResponse(response(), 'ABC123', ctx);
    expect(payload.empresa.nombre).toBe('Parkos Demo Actualizado');
    expect(payload.operario).toBe('Operador QA E2E');
    const bytes = Buffer.from(build('entrada', payload)).toString('latin1');
    expect(bytes).toContain('Parkos Demo Actualizado');
    expect(bytes).toContain('NIT 900000000-5');
    expect(bytes).not.toContain('Parkos S.A.S.');
    const html = renderEntradaTiqueteHtml(payload);
    expect(html).toContain('NIT 900000000-5');
    expect(html).toContain('Operario: Operador QA E2E');
  });

  it('reimpresión: empresa real también en el sobre externo', async () => {
    respuestas();
    const ctx = await resolverContextoImpresion();
    const p = buildReimpresionEntradaPayload(ingreso(), 'motivo', ctx);
    expect(p.empresa.nit).toBe('900000000-5');
    expect(p.payload.empresa.nit).toBe('900000000-5');
    expect(p.payload.operario).toBe('Operador QA E2E');
  });

  it('sin contexto cae al placeholder', () => {
    const p = buildEntradaPayloadFromResponse(response(), 'ABC123', {});
    expect(p.empresa.nombre).toBe('Parkos S.A.S.');
    expect(p.operario).toBe('Operador');
  });
});
