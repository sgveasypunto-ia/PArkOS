/**
 * tarifasApi — regression test for `listTarifasByKey`'s response shape.
 *
 * QA batch tarifas/cupos: `GET /tarifas-sucursal/by-key` returns a bare
 * JSON array (`response_model=list[TarifasSucursalRead]`), but
 * `listTarifasByKey` used to parse it with `tarifaReadListEnvelopeSchema`
 * (expects `{items: [...], next_cursor}`). Every real call threw a
 * ZodError, silently swallowed by SWR into `versiones: []` -- "Ver
 * histórico" always rendered "Sin versiones registradas." even when the
 * backend had real version rows (confirmed live via chrome-devtools).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type * as FetchModule from '@parkos/ui-kit/fetch';

vi.mock('@parkos/ui-kit/fetch', async () => {
  const actual = await vi.importActual<typeof FetchModule>('@parkos/ui-kit/fetch');
  return {
    ...actual,
    parkosFetchRaw: vi.fn(),
  };
});

import { parkosFetchRaw } from '@parkos/ui-kit/fetch';
import { useAuthStore } from '@parkos/ui-kit/store';
import {
  createTarifa,
  createTarifaBatch,
  listTarifasByKey,
  TarifaConflictError,
  TarifaValidationError,
} from './tarifasApi';

const mockedFetchRaw = parkosFetchRaw as ReturnType<typeof vi.fn>;

const SAMPLE = {
  uuid: 'bbbbbbbb-1111-1111-1111-111111111111',
  uuid_sucursal: '22222222-2222-2222-2222-222222222222',
  uuid_tipo_vehiculo: 'cccccccc-1111-1111-1111-111111111111',
  uuid_tipo_tarifa: '12e3886a-7059-47ee-bdb2-aa5fb1272bea',
  valor: '3000.0000',
  valor_plena: null,
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: null,
};

beforeEach(() => {
  mockedFetchRaw.mockReset();
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('listTarifasByKey', () => {
  it('parses the bare array the backend actually returns (not an {items} envelope)', async () => {
    mockedFetchRaw.mockResolvedValueOnce(
      new Response(JSON.stringify([SAMPLE]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const result = await listTarifasByKey({ sucursal: SAMPLE.uuid_sucursal! });
    expect(result).toHaveLength(1);
    expect(result[0]?.uuid).toBe(SAMPLE.uuid);
  });
});

// ---------------------------------------------------------------------------
// HU-tarifas-batch -- typed validation error and conflict error mapping
// ---------------------------------------------------------------------------

const VALID_HORA_UUID = '12e3886a-7059-47ee-bdb2-aa5fb1272bea';
const VALID_FRACCION_UUID = 'c41b6602-f7b2-437d-bcfc-0462cd385eda';
const VALID_PLENA_UUID = 'd83ebff8-9546-43b3-91b1-bedffa57717f';
const VALID_NOCTURNA_UUID = '9f8ba4a9-6fd9-4da7-8ddb-97ce323a8600';

describe('createTarifa -- validation guard (HU-tarifas-batch)', () => {
  it('throws TarifaValidationError (NOT raw ZodError) when valor=0', async () => {
    // The page-side used to convert null to '0' and pass it through;
    // the new strict guard catches it client-side BEFORE the HTTP
    // call and surfaces a typed error with a structured issues array.
    await expect(
      createTarifa({
        uuid_sucursal: '22222222-2222-2222-2222-222222222222',
        uuid_tipo_vehiculo: '33333333-3333-3333-3333-333333333333',
        uuid_tipo_tarifa: VALID_HORA_UUID,
        valor: '0',
        valor_plena: null,
      }),
    ).rejects.toThrow(TarifaValidationError);
    // No HTTP call should have been made (the schema rejected first).
    expect(mockedFetchRaw).not.toHaveBeenCalled();
  });

  it('TarifaValidationError exposes a structured issues array (path + message)', async () => {
    let caught: unknown;
    try {
      await createTarifa({
        uuid_sucursal: '22222222-2222-2222-2222-222222222222',
        uuid_tipo_vehiculo: '33333333-3333-3333-3333-333333333333',
        uuid_tipo_tarifa: VALID_HORA_UUID,
        valor: '0',
        valor_plena: null,
      });
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(TarifaValidationError);
    const ve = caught as TarifaValidationError;
    // The schema has TWO refines on `valor` (null+>0 chained). Both
    // fire when the input is a non-null decimal that fails the >0
    // check -- we accept >=1 issues here, the key contract is that
    // the path is `valor` and the message names the constraint.
    expect(ve.issues.length).toBeGreaterThanOrEqual(1);
    const valorIssue = ve.issues.find((i) => i.path === 'valor');
    expect(valorIssue).toBeDefined();
    expect(valorIssue?.message).toMatch(/mayor a 0/i);
    // Crucially: the error MESSAGE is the human-readable summary, NOT
    // the raw Zod JSON string. This is the fix for the chrome-devtools
    // bug where the operator saw
    //   ``[ { "code": "custom", "message": "...", "path": ["valor"] } ]``
    // in the alert.
    expect(ve.message).not.toContain('[ {');
    expect(ve.message).not.toContain('"code"');
  });
});

describe('createTarifaBatch (HU-tarifas-batch happy path + 409 mapping)', () => {
  it('parses the envelope { items, next_cursor } and returns items[]', async () => {
    const row1 = { ...SAMPLE, uuid_tipo_tarifa: VALID_HORA_UUID, valor: '1500.0000' };
    const row2 = {
      ...SAMPLE,
      uuid: 'cccc2222-2222-2222-2222-222222222222',
      uuid_tipo_tarifa: VALID_FRACCION_UUID,
      valor: '800.0000',
    };
    const row3 = {
      ...SAMPLE,
      uuid: 'cccc3333-3333-3333-3333-333333333333',
      uuid_tipo_tarifa: VALID_PLENA_UUID,
      valor: '2000.0000',
    };
    const row4 = {
      ...SAMPLE,
      uuid: 'cccc4444-4444-4444-4444-444444444444',
      uuid_tipo_tarifa: VALID_NOCTURNA_UUID,
      valor: '1000.0000',
    };
    mockedFetchRaw.mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [row1, row2, row3, row4], next_cursor: null }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const result = await createTarifaBatch({
      uuid_sucursal: SAMPLE.uuid_sucursal!,
      uuid_tipo_vehiculo: SAMPLE.uuid_tipo_vehiculo!,
      vigente_desde: '2026-01-01T00:00:00',
      items: [
        { uuid_tipo_tarifa: VALID_HORA_UUID, valor: '1500' },
        { uuid_tipo_tarifa: VALID_FRACCION_UUID, valor: '800' },
        { uuid_tipo_tarifa: VALID_PLENA_UUID, valor: '2000', valor_plena: '2000' },
        { uuid_tipo_tarifa: VALID_NOCTURNA_UUID, valor: '1000' },
      ],
    });
    expect(result).toHaveLength(4);
    expect(result.map((r) => r.uuid_tipo_tarifa).sort()).toEqual(
      [VALID_HORA_UUID, VALID_FRACCION_UUID, VALID_PLENA_UUID, VALID_NOCTURNA_UUID].sort(),
    );
  });

  it('throws TarifaConflictError on 409 tarifa_overlap with constraint name', async () => {
    // The PR1 backend returns the tarifa_overlap shape on 409 (both
    // the pre-check path and the DB race path). The FE distinguishes
    // them by the optional ``constraint`` field.
    mockedFetchRaw.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: {
            error: 'tarifa_overlap',
            conflicting_uuid: null,
            conflicting_vigente_desde: '2026-01-01T00:00:00',
            conflicting_vigente_hasta: null,
            constraint: 'tarifas_sucursal_uk01',
          },
        }),
        { status: 409, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    let caught: unknown;
    try {
      await createTarifaBatch({
        uuid_sucursal: SAMPLE.uuid_sucursal!,
        uuid_tipo_vehiculo: SAMPLE.uuid_tipo_vehiculo!,
        items: [{ uuid_tipo_tarifa: VALID_HORA_UUID, valor: '1500' }],
      });
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(TarifaConflictError);
    const ce = caught as TarifaConflictError;
    expect(ce.constraint).toBe('tarifas_sucursal_uk01');
    expect(ce.message).toContain('tarifas_sucursal_uk01');
  });
});
