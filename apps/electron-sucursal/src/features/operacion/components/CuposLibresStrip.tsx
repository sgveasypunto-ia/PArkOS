/**
 * `<CuposLibresStrip />` — full-width footer strip del dashboard
 * (operador 2026-09-22: directiva de reorganización visual).
 *
 * Renderiza:
 *   - Izquierda: `<OcupacionPanel />` (lista per-tipo, HU-F4.3) con el
 *     desglose `CARRO 3/10`, `MOTO 5/20`, etc. Mismo componente que
 *     antes vivía en el right-sidebar; cero cambio de markup interno.
 *   - Derecha: un KPI grande con el TOTAL de cupos libres en la
 *     sucursal (`OcupacionItem.disponible` sum, sólo items con
 *     `cupo_maximo > 0`).
 *
 * **Por qué existe este componente (vs. dejar `<OcupacionPanel />`
 * suelto en el footer):** el operador pidió explícitamente que el
 * inventario (per-tipo) Y los cupos libres (agregado) vivan juntos
 * abajo. Mantenerlos en un solo organism permite:
 *   1. Una sola suscripción SWR (`useOcupacion`) — el componente
 *      padre sólo pasa `uuid_sucursal` una vez y ambos bloques
 *      consumen la misma respuesta cacheada por SWR (dedupe 5s).
 *   2. Sticky-bottom uniforme en `lg+` (el footer queda siempre
 *      visible al fondo del kiosko, debajo del panel central que
 *      scrollea).
 *   3. Tests atómicos: el operador puede testear el strip total sin
 *      tener que re-renderizar la lista per-tipo.
 *
 * **Reactividad:** cuando el operador ejecuta un ingreso/salida, el
 * backend hace `REFRESH MATERIALIZED VIEW CONCURRENTLY` y el SWR
 * poll (10s) repuebla `data.items`. El KPI se actualiza solo.
 *
 * **Layout:**
 *   - `lg+` (>= 1024px): una franja horizontal full-width (col-span 3
 *     del grid del dashboard, row-start 3). El inventario per-tipo
 *     ocupa el ancho flexible y el KPI agregado queda a la derecha
 *     con `shrink-0`.
 *   - `< lg`: se apila (cada bloque en su propia fila); el KPI
 *     agregado queda arriba del inventario per-tipo para que sea lo
 *     primero que el operador ve en mobile.
 */
import { useTranslation } from 'react-i18next';

import { useOcupacion } from '../hooks/useOcupacion';
import { OcupacionPanel } from '../../caja/components/OcupacionPanel';

export interface CuposLibresStripProps {
  /** `null` cuando el operador aún no tiene branch context — el
   *  hook retorna `undefined` y el KPI renderiza `—` (load-state,
   *  no se inventa 0). */
  uuid_sucursal: string | null;
}

export function CuposLibresStrip({
  uuid_sucursal,
}: CuposLibresStripProps): JSX.Element {
  const { t } = useTranslation(['operacion', 'caja']);
  const { data } = useOcupacion(uuid_sucursal);

  // Sum del campo `disponible` server-side (DEC-SUC-11). El cliente
  // NUNCA lo re-deriva. Items con `cupo_maximo === 0` se excluyen del
  // sum (no son "cupos reales" — directriz consistente con el
  // `MiTurnoPanel.cuposLibres` que vivía antes en el right-sidebar).
  const totalCuposLibres =
    data?.items
      .filter((it) => it.cupo_maximo > 0)
      .reduce((acc, it) => acc + it.disponible, 0) ?? null;

  return (
    <footer
      data-testid="cupos-libres-strip"
      aria-label={t('operacion:miTurno.kpis.cuposLibres', {
        defaultValue: 'Cupos libres',
      })}
      className="col-span-1 border-t border-border/40 bg-card/40 px-4 py-2 backdrop-blur-md shadow-apple-sm lg:col-span-3 lg:row-start-3"
    >
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:gap-6">
        {/* Inventario per-tipo — re-uso del OcupacionPanel sin cambio
            de markup (mismo componente, misma suscripción SWR). */}
        <div className="flex-1 min-w-0">
          <OcupacionPanel uuid_sucursal={uuid_sucursal} />
        </div>

        {/* KPI agregado grande — `shrink-0` para que el número nunca
            se corte si la lista per-tipo es larga. Separador visual
            con `border-l` solo en `lg+` (mobile va apilado). */}
        <div className="flex items-baseline justify-between gap-2 lg:justify-start lg:border-l lg:border-border/40 lg:pl-6">
          <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
            {t('operacion:miTurno.kpis.cuposLibres', {
              defaultValue: 'Cupos libres',
            })}
          </span>
          <span
            data-testid="cupos-libres-strip-total"
            className="font-mono text-2xl font-semibold tabular-nums tracking-tight text-foreground"
          >
            {totalCuposLibres ?? '—'}
          </span>
        </div>
      </div>
    </footer>
  );
}
