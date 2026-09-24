/**
 * `useIngresosActivos(uuid_sucursal)` — polling hook for the currently
 * active ingresos at a branch.
 *
 * Extracted from `Dashboard.tsx` (HU-F7.1, T5 — búsqueda sin placa) so
 * `<SalidaPanel />` can reuse the SAME live "vehículos dentro" snapshot
 * to power its own placa/consecutivo autocomplete, instead of
 * duplicating the polling logic. `<VehiculosDentroList />` (inside
 * `Dashboard.tsx`) keeps consuming this hook unchanged.
 *
 * `GET /api/v1/operacion/ingresos?uuid_sucursal=X&activo=true` returns
 * currently-active ingresos (timestamp_salida IS NULL).
 *
 * Refresh cadence: 10s (unchanged from the pre-extraction Dashboard.tsx
 * implementation — kept in sync with `<OcupacionPanel />`).
 *
 * Robust to React StrictMode (effects run twice in dev): the return value
 * is always either `null` (loading/error) or an array (possibly empty).
 * Never returns `undefined` so the consumer's `items.length` is always safe.
 */
import { useEffect, useState } from 'react';

import { parkosFetch } from '@parkos/ui-kit/fetch';

const INGRESOS_REFRESH_MS = 10_000;

export interface IngresoActivo {
  uuid: string;
  placa: string | null;
  /**
   * Hora del ingreso. El backend puede devolver `null` para filas creadas
   * antes de que el handler populase la columna (seeds / ingresos de
   * pruebas viejos). En ese caso caemos a `created_at`, que SÍ trae
   * timestamp real del INSERT.
   */
  fecha_ingreso: string | null;
  /**
   * Identificador legible para ingresos sin placa (REQ-OPS-197).
   * Formato `<TIPO>-NNNNNN-<uuid8>` (ej. `PATINETA-000003-34a24bae`).
   * `null` para ingresos con placa — esos muestran la placa.
   */
  consecutivo: string | null;
  /** Timestamp del INSERT — fallback cuando `fecha_ingreso` viene null. */
  created_at: string;
  uuid_tipo_vehiculo: string;
  uuid_sucursal: string;
  /**
   * Cobros pendientes del ingreso activo. Monto en COP que aún no fue
   * pagado. `null`/ausente/`0` → la fila NO muestra la columna de cobros
   * pendientes (ver `<VehiculosDentroList />`).
   */
  cobros_pendientes?: number | null;
}

/**
 * SWR-style polling hook returning ALL currently-active ingresos for a
 * branch. `null` = loading/error, `[]` = no active ingresos, otherwise
 * the live list.
 */
export function useIngresosActivos(
  uuid_sucursal: string | null,
): IngresoActivo[] | null {
  const [items, setItems] = useState<IngresoActivo[] | null>(null);

  useEffect(() => {
    if (uuid_sucursal === null) {
      setItems([]);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    async function pull(): Promise<void> {
      try {
        // Endpoint returns IngresoActivo[] DIRECTLY (not wrapped in
        // { items: ... } as many list endpoints do). Coerce defensively
        // in case the backend shape changes.
        const json = (await parkosFetch<unknown>(
          `/api/v1/operacion/ingresos?uuid_sucursal=${uuid_sucursal}&activo=true`,
        )) as IngresoActivo[] | { items?: IngresoActivo[] };
        if (cancelled) return;
        const list = Array.isArray(json)
          ? json
          : Array.isArray(json?.items)
            ? json.items
            : [];
        setItems(list);
      } catch {
        if (!cancelled) setItems([]);
      }
    }

    void pull();
    timer = setInterval(() => void pull(), INGRESOS_REFRESH_MS);

    return () => {
      cancelled = true;
      if (timer !== null) clearInterval(timer);
    };
  }, [uuid_sucursal]);

  return items;
}
