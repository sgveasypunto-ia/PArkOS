/**
 * `tarifaHoraEntrada.ts` — the hourly tariff printed on the ingreso ticket
 * (FB1: it used to print a hard-coded "$ 0/hora").
 *
 * `GET /empresa/tarifas-sucursal` returns one row per vehicle type AND
 * modalidad (hora / fracción / plena / nocturna, fixed UUIDs seeded by
 * migration 0071); the ticket shows the `hora` one. Every resolver is
 * best-effort: any failure or missing tariff yields `null` and the ticket
 * simply omits the tariff line. A nil/empty vehicle-type uuid is never
 * requested.
 */
import { listTarifasSucursal, type TarifaSucursalRead } from '../../features/catalogos/api/tarifasSucursalApi';
import { getIngresoByUuid } from '../../features/operacion/api/ingresoActivoApi';

/** Fixed `tipo_tarifa` uuid of the "hora" modalidad (migration 0071_seed_tipo_tarifa_modalidades). */
export const TIPO_TARIFA_HORA_UUID = '12e3886a-7059-47ee-bdb2-aa5fb1272bea';

const NIL_UUID = '00000000-0000-0000-0000-000000000000';

function tipoUsable(uuid: string | null | undefined): uuid is string {
  return typeof uuid === 'string' && uuid !== '' && uuid !== NIL_UUID;
}

/** Hourly tariff of `uuidTipoVehiculo` among `items`, or null. */
export function tarifaHoraDeTipo(
  items: readonly TarifaSucursalRead[],
  uuidTipoVehiculo: string | null | undefined,
): number | null {
  if (!tipoUsable(uuidTipoVehiculo)) return null;
  const fila = items.find(
    (t) =>
      t.uuid_tipo_vehiculo === uuidTipoVehiculo &&
      t.uuid_tipo_tarifa === TIPO_TARIFA_HORA_UUID &&
      t.vigente_hasta === null,
  );
  if (!fila || fila.valor === null || fila.valor === undefined) return null;
  const valor = Number(fila.valor);
  return Number.isFinite(valor) ? valor : null;
}

export async function resolverTarifaHoraDeTipo(
  uuidTipoVehiculo: string | null | undefined,
): Promise<number | null> {
  if (!tipoUsable(uuidTipoVehiculo)) return null;
  try {
    const { items } = await listTarifasSucursal();
    return tarifaHoraDeTipo(items, uuidTipoVehiculo);
  } catch (err) {
    console.warn('[tarifaHoraEntrada] no se pudo leer la tarifa', err);
    return null;
  }
}

/** Resolve through the persisted ingreso (its `uuid_tipo_vehiculo`). */
export async function resolverTarifaHoraDeIngreso(uuidIngreso: string): Promise<number | null> {
  try {
    const ingreso = await getIngresoByUuid(uuidIngreso);
    return await resolverTarifaHoraDeTipo(ingreso.uuid_tipo_vehiculo);
  } catch (err) {
    console.warn('[tarifaHoraEntrada] no se pudo leer el ingreso', err);
    return null;
  }
}
