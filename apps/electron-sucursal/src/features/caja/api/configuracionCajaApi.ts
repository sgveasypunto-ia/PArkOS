/**
 * `configuracionCajaApi.ts` — base de caja efectiva de la sucursal.
 *
 * La base es un parámetro de la sucursal (override por sucursal o default
 * global, configurado desde web_admin y replicado a la sucursal por sync): el
 * operador no la digita. GET /configuracion/configuracion-caja/efectiva
 * resuelve el valor vigente; 404 (nada configurado) retorna `null`.
 */
import { ParkosHttpError, parkosFetch } from '@parkos/ui-kit/fetch';

const EFECTIVA_PATH = '/api/v1/configuracion/configuracion-caja/efectiva';

/** Subconjunto de `ConfiguracionCajaRead` que usa el turno. */
interface ConfiguracionCajaEfectivaWire {
  // Pydantic serializa Decimal como string ("100000.0000").
  base_inicial_sugerida: string | number | null;
}

/**
 * Base de caja efectiva en pesos enteros, o `null` si la sucursal no tiene
 * base configurada (404 o valor nulo). Cualquier otro error se propaga.
 */
export async function getBaseCajaEfectiva(uuidSucursal: string): Promise<number | null> {
  try {
    const wire = await parkosFetch<ConfiguracionCajaEfectivaWire>(
      `${EFECTIVA_PATH}?uuid_sucursal=${encodeURIComponent(uuidSucursal)}`,
    );
    if (wire.base_inicial_sugerida === null) return null;
    const base = Number(wire.base_inicial_sugerida);
    return Number.isFinite(base) && base >= 0 ? Math.round(base) : null;
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 404) return null;
    throw err;
  }
}
