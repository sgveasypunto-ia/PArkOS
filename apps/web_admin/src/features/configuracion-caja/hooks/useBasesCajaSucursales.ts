/**
 * `useBasesCajaSucursales()` — the base de caja of every branch in one place.
 *
 * `configuracion_caja` holds one open row per branch that has its own base
 * (override) plus, at most, one global default (`uuid_sucursal = null`) that
 * every branch without an override inherits. One list call feeds the whole
 * "Administrar" table, so a branch can carry more or less base than another.
 *
 * Saving is a close+insert on the backend (update) or a plain insert (first
 * value): history is kept, nothing is ever deleted.
 */
import useSWR from 'swr';

import {
  createConfiguracionCaja,
  listConfiguracionCaja,
  updateConfiguracionCaja,
} from '../api/configuracionCajaApi';
import type { ConfiguracionCaja, Redondeo } from '../api/configuracionCajaSchema';

const KEY = 'configuracion-caja-lista';

export type OrigenBase = 'propia' | 'global' | 'sin_configurar';

export interface BaseCajaDeSucursal {
  /** Base in COP as the backend sent it (decimal string) or null. */
  base: string | null;
  origen: OrigenBase;
}

export interface UseBasesCajaSucursalesReturn {
  isLoading: boolean;
  error: Error | undefined;
  /** Effective base of a branch: its own, else the global default, else nothing. */
  baseDe: (uuidSucursal: string) => BaseCajaDeSucursal;
  /** Global default base (`null` when none is configured). */
  baseGlobal: string | null;
  /** Set the base of a branch (`null` = the global default). */
  guardar: (uuidSucursal: string | null, base: number) => Promise<void>;
}

function aEntrada(row: ConfiguracionCaja | undefined, uuidSucursal: string | null, base: number) {
  return {
    uuid_sucursal: uuidSucursal,
    base_inicial_sugerida: String(base),
    // Rounding and denominations are not part of this screen: keep what exists.
    redondeo: (row?.redondeo ?? null) as Redondeo | null,
    denominaciones_permitidas: row?.denominaciones_permitidas?.map(String) ?? null,
  };
}

export function useBasesCajaSucursales(): UseBasesCajaSucursalesReturn {
  const { data, error, isLoading, mutate } = useSWR<ConfiguracionCaja[]>(
    KEY,
    () => listConfiguracionCaja({ limit: 200 }),
    { revalidateOnFocus: false },
  );

  const abiertas = (data ?? []).filter((r) => r.vigente_hasta === null);
  const propias = new Map<string, ConfiguracionCaja>();
  let global: ConfiguracionCaja | undefined;
  for (const row of abiertas) {
    if (row.uuid_sucursal === null) global = row;
    else propias.set(row.uuid_sucursal, row);
  }

  return {
    isLoading,
    error,
    baseGlobal: global?.base_inicial_sugerida ?? null,
    baseDe: (uuidSucursal) => {
      const propia = propias.get(uuidSucursal);
      if (propia?.base_inicial_sugerida != null) {
        return { base: propia.base_inicial_sugerida, origen: 'propia' };
      }
      if (global?.base_inicial_sugerida != null) {
        return { base: global.base_inicial_sugerida, origen: 'global' };
      }
      return { base: null, origen: 'sin_configurar' };
    },
    guardar: async (uuidSucursal, base) => {
      const existente = uuidSucursal === null ? global : propias.get(uuidSucursal);
      const entrada = aEntrada(existente, uuidSucursal, base);
      if (existente) {
        await updateConfiguracionCaja(existente.uuid, entrada);
      } else {
        await createConfiguracionCaja(entrada);
      }
      await mutate();
    },
  };
}
