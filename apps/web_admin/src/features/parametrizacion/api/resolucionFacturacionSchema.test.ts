/**
 * Zod schema + typed-error tests for the resolución de facturación numbering
 * (`prefijo`, `rango_desde`, `rango_hasta`). Rules mirror the backend
 * (`ResolucionFacturacionCreate`): prefijo 1-4 alphanumeric (upper-cased),
 * rango_desde >= 1, rango_hasta >= rango_desde.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { RANGO_MAXIMO, resolucionFacturacionCreateSchema } from './resolucionFacturacionSchema';

const base = {
  uuid_sucursal: '11111111-1111-1111-1111-111111111111',
  numero_resolucion: '18764000001234',
  fecha_resolucion: '2026-01-01',
  fecha_inicio_vigencia: '2026-01-01',
  fecha_fin_vigencia: '2027-01-01',
  prefijo: 'QA',
  rango_desde: 1,
  rango_hasta: 5000,
};

function mensajes(input: Record<string, unknown>): string[] {
  const r = resolucionFacturacionCreateSchema.safeParse({ ...base, ...input });
  return r.success ? [] : r.error.issues.map((i) => i.message);
}

describe('resolucionFacturacionCreateSchema — numeración', () => {
  it('acepta prefijo QA con rango 1–5000', () => {
    const r = resolucionFacturacionCreateSchema.parse(base);
    expect(r).toMatchObject({ prefijo: 'QA', rango_desde: 1, rango_hasta: 5000 });
  });

  it('pone el prefijo en mayúsculas y recorta espacios', () => {
    expect(resolucionFacturacionCreateSchema.parse({ ...base, prefijo: ' setp ' }).prefijo).toBe(
      'SETP',
    );
  });

  it('convierte los rangos que llegan como string del input numérico', () => {
    const r = resolucionFacturacionCreateSchema.parse({
      ...base,
      rango_desde: '10',
      rango_hasta: '20',
    });
    expect([r.rango_desde, r.rango_hasta]).toEqual([10, 20]);
  });

  it('acepta un rango de un solo número', () => {
    expect(mensajes({ rango_desde: 7, rango_hasta: 7 })).toEqual([]);
  });

  it.each([
    ['vacío', '', 'El prefijo es obligatorio'],
    ['demasiado largo', 'ABCDE', 'Máximo 4 caracteres'],
    ['con símbolo', 'A-B', 'Solo letras y números, sin espacios ni símbolos'],
    ['con espacio interno', 'A B', 'Solo letras y números, sin espacios ni símbolos'],
  ])('rechaza prefijo %s', (_nombre, prefijo, mensaje) => {
    expect(mensajes({ prefijo })).toContain(mensaje);
  });

  it.each([
    ['0', 'El rango inicial debe ser mayor o igual a 1'],
    [-3, 'El rango inicial debe ser mayor o igual a 1'],
    [1.5, 'El rango inicial debe ser un número entero'],
    ['', 'El rango inicial es obligatorio'],
  ])('rechaza rango_desde %s', (rango_desde, mensaje) => {
    expect(mensajes({ rango_desde, rango_hasta: 10 })).toContain(mensaje);
  });

  it('rechaza rango_hasta menor que rango_desde en el campo rango_hasta', () => {
    const r = resolucionFacturacionCreateSchema.safeParse({
      ...base,
      rango_desde: 100,
      rango_hasta: 99,
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      const issue = r.error.issues.find((i) => i.path[0] === 'rango_hasta');
      expect(issue?.message).toBe('El rango final debe ser mayor o igual al rango inicial');
    }
  });

  it('rechaza un rango por encima del máximo DIAN', () => {
    expect(mensajes({ rango_hasta: RANGO_MAXIMO + 1 })).toContain(
      `El rango final no puede superar ${RANGO_MAXIMO}`,
    );
  });

  it('mantiene la validación de vigencia', () => {
    expect(mensajes({ fecha_fin_vigencia: '2026-01-01' })).toContain(
      'fecha_fin_vigencia debe ser posterior a fecha_inicio_vigencia',
    );
  });
});

describe('createResolucionFacturacion — errores tipados del backend', () => {
  afterEach(() => {
    vi.resetModules();
    vi.doUnmock('@parkos/ui-kit/fetch');
  });

  async function conRespuesta(status: number, body: unknown) {
    vi.doMock('@parkos/ui-kit/fetch', () => ({
      parkosFetchRaw: vi.fn().mockResolvedValue(
        new Response(JSON.stringify(body), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    }));
    return import('./resolucionFacturacionApi');
  }

  const payload = resolucionFacturacionCreateSchema.parse(base);

  it('422 por rango invertido -> error de numeración en rango_hasta', async () => {
    const api = await conRespuesta(422, {
      detail: [
        {
          loc: ['body'],
          msg: 'Value error, rango_hasta debe ser mayor o igual a rango_desde',
          type: 'value_error',
        },
      ],
    });
    const err = await api.createResolucionFacturacion(payload).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(api.ResolucionFacturacionNumeracionError);
    expect((err as { campo: string }).campo).toBe('rango_hasta');
    expect((err as Error).message).toBe('El rango final debe ser mayor o igual al rango inicial');
  });

  it('422 por prefijo inválido -> error de numeración en prefijo', async () => {
    const api = await conRespuesta(422, {
      detail: [
        {
          loc: ['body'],
          msg: 'Value error, prefijo debe ser alfanumérico de 1 a 4 caracteres',
          type: 'value_error',
        },
      ],
    });
    const err = await api.createResolucionFacturacion(payload).catch((e: unknown) => e);
    expect((err as { campo: string }).campo).toBe('prefijo');
  });

  it('409 resolucion_rango_solapado -> error de numeración en rango_desde', async () => {
    const api = await conRespuesta(409, { detail: { error: 'resolucion_rango_solapado' } });
    const err = await api.createResolucionFacturacion(payload).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(api.ResolucionFacturacionNumeracionError);
    expect((err as { campo: string }).campo).toBe('rango_desde');
    expect((err as Error).message).toMatch(/se solapa/);
  });

  it('422 por vigencia sigue siendo ResolucionFacturacionVigenciaError', async () => {
    const api = await conRespuesta(422, {
      detail: [
        {
          loc: ['body'],
          msg: 'Value error, fecha_fin_vigencia debe ser posterior a fecha_inicio_vigencia',
          type: 'value_error',
        },
      ],
    });
    const err = await api.createResolucionFacturacion(payload).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(api.ResolucionFacturacionVigenciaError);
  });

  it('PUT usa la ruta con uuid y el cuerpo con la numeración', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          uuid: '22222222-2222-2222-2222-222222222222',
          uuid_sucursal: base.uuid_sucursal,
          numero_resolucion: base.numero_resolucion,
          prefijo: 'QA',
          rango_desde: 1,
          rango_hasta: 5000,
          fecha_resolucion: '2026-01-01',
          fecha_inicio_vigencia: '2026-01-01',
          fecha_fin_vigencia: '2027-01-01',
          vigente_desde: '2026-02-01T00:00:00',
          vigente_hasta: null,
          estado: 'activo',
          created_at: '2026-02-01T00:00:00',
          created_by: null,
          sync_status: null,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    vi.doMock('@parkos/ui-kit/fetch', () => ({ parkosFetchRaw: fetchMock }));
    const api = await import('./resolucionFacturacionApi');
    const res = await api.updateResolucionFacturacion('11111111-0000-0000-0000-000000000001', payload);

    expect(res.prefijo).toBe('QA');
    const [url, init] = fetchMock.mock.calls[0] as [string, { method: string; body: string }];
    expect(url).toBe('/api/v1/empresa/resolucion-facturacion/11111111-0000-0000-0000-000000000001');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body)).toMatchObject({ prefijo: 'QA', rango_desde: 1, rango_hasta: 5000 });
  });
});
