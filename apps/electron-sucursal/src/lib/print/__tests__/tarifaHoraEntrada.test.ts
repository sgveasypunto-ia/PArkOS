/**
 * FB1 — the ingreso ticket printed "Tarifa: $ 0/hora" because the builders
 * hard-coded `tarifaAplicada: 0`. The hourly tariff of the vehicle type must be
 * printed; with no tariff the line is omitted.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { build } from '../escposBuilder';
import { renderEntradaTiqueteHtml } from '../fallbackBrowser';
import { buildEntradaPayloadFromResponse, buildReimpresionEntradaPayload } from '../printBuilder';
import {
  TIPO_TARIFA_HORA_UUID,
  resolverTarifaHoraDeIngreso,
  resolverTarifaHoraDeTipo,
  tarifaHoraDeTipo,
} from '../tarifaHoraEntrada';
import type { PostIngresoResponse } from '../../../features/operacion/lib/ingresoApi';
import type { Ingreso } from '../../../features/operacion/api/ingresoActivoApi';
import type { TarifaSucursalRead } from '../../../features/catalogos/api/tarifasSucursalApi';

const mocks = vi.hoisted(() => ({
  listTarifasSucursal: vi.fn(),
  getIngresoByUuid: vi.fn(),
}));
vi.mock('../../../features/catalogos/api/tarifasSucursalApi', () => ({
  listTarifasSucursal: mocks.listTarifasSucursal,
}));
vi.mock('../../../features/operacion/api/ingresoActivoApi', () => ({
  getIngresoByUuid: mocks.getIngresoByUuid,
}));

const CARRO = '52d92997-cee5-4978-a773-ad141786b24d';
const MOTO = '5cc84454-0000-4000-8000-000000000000';
const FRACCION = 'c41b6602-f7b2-437d-bcfc-0462cd385eda';

function t(tipoVeh: string, tipoTarifa: string, valor: number | string | null): TarifaSucursalRead {
  return {
    uuid: `${tipoVeh}-${tipoTarifa}`,
    uuid_sucursal: null,
    uuid_tipo_vehiculo: tipoVeh,
    uuid_tipo_tarifa: tipoTarifa,
    valor: valor as number | null,
    valor_plena: null,
    vigente_desde: '2026-10-05T14:35:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-10-05T19:37:36',
    created_by: null,
    sync_status: null,
  };
}
// The API serialises NUMERIC as strings ("1500.0000").
const ITEMS = [
  t(CARRO, FRACCION, '100.0000'),
  t(CARRO, TIPO_TARIFA_HORA_UUID, '1500.0000'),
  t(MOTO, TIPO_TARIFA_HORA_UUID, '2500.0000'),
];

const RESP: PostIngresoResponse = {
  uuid: '00000000-0000-4000-8000-000000000001',
  tipo_entrada: 'ROTACION',
  uuid_subscripcion_cliente: null,
  consecutivo: null,
};

beforeEach(() => {
  mocks.listTarifasSucursal.mockReset();
  mocks.getIngresoByUuid.mockReset();
});

describe('tarifaHoraDeTipo', () => {
  it('picks the "hora" modality (not fracción) of the vehicle type', () => {
    expect(tarifaHoraDeTipo(ITEMS, CARRO)).toBe(1500);
    expect(tarifaHoraDeTipo(ITEMS, MOTO)).toBe(2500);
  });
  it('is null without a tariff, without type, or with a nil uuid', () => {
    expect(tarifaHoraDeTipo(ITEMS, '99999999-0000-4000-8000-000000000000')).toBeNull();
    expect(tarifaHoraDeTipo(ITEMS, null)).toBeNull();
    expect(tarifaHoraDeTipo(ITEMS, '00000000-0000-0000-0000-000000000000')).toBeNull();
    expect(tarifaHoraDeTipo([t(CARRO, TIPO_TARIFA_HORA_UUID, null)], CARRO)).toBeNull();
  });
});

describe('resolvers never throw and never request a nil uuid', () => {
  it('resolverTarifaHoraDeTipo → value', async () => {
    mocks.listTarifasSucursal.mockResolvedValue({ items: ITEMS, next_cursor: null });
    expect(await resolverTarifaHoraDeTipo(CARRO)).toBe(1500);
  });
  it('resolverTarifaHoraDeTipo(nil/empty) does not hit the network', async () => {
    expect(await resolverTarifaHoraDeTipo(null)).toBeNull();
    expect(await resolverTarifaHoraDeTipo('')).toBeNull();
    expect(await resolverTarifaHoraDeTipo('00000000-0000-0000-0000-000000000000')).toBeNull();
    expect(mocks.listTarifasSucursal).not.toHaveBeenCalled();
  });
  it('resolverTarifaHoraDeIngreso reads the ingreso type then the tariff', async () => {
    mocks.getIngresoByUuid.mockResolvedValue({ uuid_tipo_vehiculo: MOTO });
    mocks.listTarifasSucursal.mockResolvedValue({ items: ITEMS, next_cursor: null });
    expect(await resolverTarifaHoraDeIngreso(RESP.uuid)).toBe(2500);
  });
  it('a failing fetch yields null', async () => {
    mocks.getIngresoByUuid.mockRejectedValue(new Error('boom'));
    expect(await resolverTarifaHoraDeIngreso(RESP.uuid)).toBeNull();
    mocks.listTarifasSucursal.mockRejectedValue(new Error('boom'));
    expect(await resolverTarifaHoraDeTipo(CARRO)).toBeNull();
  });
});

describe('payload builders carry the tariff', () => {
  it('entrada: tarifaHora 1500 → tarifaAplicada 1500; absent → undefined', () => {
    expect(buildEntradaPayloadFromResponse(RESP, 'ABC123', { tarifaHora: 1500 }).tarifaAplicada).toBe(1500);
    expect(buildEntradaPayloadFromResponse(RESP, 'ABC123', {}).tarifaAplicada).toBeUndefined();
    expect(buildEntradaPayloadFromResponse(RESP, 'ABC123', { tarifaHora: null }).tarifaAplicada).toBeUndefined();
  });
  it('reimpresión: same', () => {
    const ing: Ingreso = {
      uuid: RESP.uuid,
      uuid_sucursal: RESP.uuid,
      placa: 'ABC123',
      fecha_ingreso: '2026-10-07T21:07:00',
      uuid_subscripcion_cliente: null,
      consecutivo: null,
      uuid_tipo_vehiculo: CARRO,
    };
    expect(buildReimpresionEntradaPayload(ing, 'm', { tarifaHora: 1500 }).payload.tarifaAplicada).toBe(1500);
    expect(buildReimpresionEntradaPayload(ing, 'm').payload.tarifaAplicada).toBeUndefined();
  });
});

describe('entrada ticket output', () => {
  const con = buildEntradaPayloadFromResponse(RESP, 'ABC123', { tarifaHora: 1500 });
  const sin = buildEntradaPayloadFromResponse(RESP, 'ABC123', {});
  it('ESC/POS prints Tarifa: $ 1.500/hora', () => {
    expect(build('entrada', con).toString('utf8')).toMatch(/Tarifa: \$\s+1\.500\/hora/);
  });
  it('ESC/POS prints NO tariff line without a tariff (and never $ 0)', () => {
    const s = build('entrada', sin).toString('utf8');
    expect(s).not.toContain('Tarifa:');
    expect(s).toContain('Folio:');
    expect(s).toContain('Fecha:');
  });
  it('HTML mirrors both cases', () => {
    expect(renderEntradaTiqueteHtml(con)).toMatch(/>Tarifa: \$\s+1\.500\/hora<\/p>/);
    expect(renderEntradaTiqueteHtml(sin)).not.toContain('Tarifa:');
  });
});
