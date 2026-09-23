/**
 * `<CuposLibresStrip />` — footer sticky minimalista del dashboard.
 *
 * **Operador 2026-09-22 (segunda pasada de reorganización):**
 * la versión anterior renderizaba el `<OcupacionPanel />` completo
 * (lista vertical con dot + label + count + barra de progreso por
 * tipo) + un KPI grande. Resultado: footer visualmente pesado,
 * ~140px de alto, las barras de progreso robaban atención.
 *
 * Nueva versión minimalista:
 *   - Una SOLA fila horizontal.
 *   - Sin barras de progreso (eran el ruido visual principal).
 *   - Por cada tipo: dot de color + label uppercase + count
 *     `X/Y` en font-mono.
 *   - A la derecha: el agregado "76 libres" en font-mono, mismo
 *     tamaño visual que los counts por tipo (no más grande).
 *   - Padding `py-2` → alto real ~40-48px (siempre < 80px).
 *   - `sticky bottom-0 z-10` → queda FIJO abajo de la pantalla
 *     aunque el operador scrollee la lista de vehículos dentro.
 *   - `bg-card/95 backdrop-blur-md` → flotante sobre el contenido
 *     cuando hay scroll debajo (sensación "footer glass").
 *
 * **Reactividad:** cuando el operador ejecuta un ingreso/salida, el
 * backend hace `REFRESH MATERIALIZED VIEW CONCURRENTLY` y el SWR
 * poll (10s) repuebla `data.items`. El footer se actualiza solo.
 *
 * **Por qué NO reusa `<OcupacionPanel />`:** ese componente está
 * diseñado para vista vertical (right-sidebar del F11.x) con barras
 * de progreso + Tooltip con leyenda. Para el footer minimalista
 * hacemos render inline — control total del markup, cero markup
 * inflado, y la lógica del color se reusa via `classForPorcentaje`.
 *
 * **Layout responsive:**
 *   - `lg+` (>= 1024px): una fila horizontal. Items per-tipo a la
 *     izquierda con `flex-1` y `flex-wrap` (no rompe si hay 6+ tipos).
 *     KPI total a la derecha con `shrink-0` y `border-l`.
 *   - `< lg`: los items hacen wrap a 2 filas (los 3-4 tipos típicos
 *     entran cómodos en 360-400px).
 */
import { useTranslation } from 'react-i18next';

import { useOcupacion } from '../hooks/useOcupacion';
import { classForPorcentaje } from '../occupancyThresholds';

// Dot color → utility class (mismo mapa semántico que `<OcupacionPanel />`
// para que el operador vea el mismo código de color en footer y en el
// detalle del drawer si lo abrimos desde el sidebar F5 Inventario).
const DOT_BG: Record<'green' | 'yellow' | 'red', string> = {
  green: 'bg-emerald-500',
  yellow: 'bg-amber-500',
  red: 'bg-red-500',
};
const DOT_TEXT: Record<'green' | 'yellow' | 'red', string> = {
  green: 'text-emerald-700 dark:text-emerald-300',
  yellow: 'text-amber-700 dark:text-amber-300',
  red: 'text-red-700 dark:text-red-300',
};

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

  const items = data?.items ?? [];

  // Sum del campo `disponible` server-side (DEC-SUC-11). El cliente
  // NUNCA lo re-deriva. Items con `cupo_maximo === 0` se excluyen del
  // sum (no son "cupos reales" — directriz consistente con el
  // `MiTurnoPanel.cuposLibres` que vivía antes en el right-sidebar
  // y con el KPI del popover del navbar toggle).
  const totalCuposLibres = items
    .filter((it) => it.cupo_maximo > 0)
    .reduce((acc, it) => acc + it.disponible, 0);
  const hasRealCupos = items.some((it) => it.cupo_maximo > 0);

  return (
    <footer
      data-testid="cupos-libres-strip"
      aria-label={t('operacion:miTurno.kpis.cuposLibres', {
        defaultValue: 'Cupos libres',
      })}
      className="sticky bottom-0 z-10 col-span-1 max-h-[80px] border-t border-border/40 bg-card/95 px-4 py-2 shadow-apple-sm backdrop-blur-md lg:col-span-3 lg:row-start-3"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 lg:flex-nowrap">
        {/* Inventario per-tipo minimalista — dot + label + count.
            Sin barras de progreso. Sin tooltips (el operador ya conoce
            la convención de colores desde el drawer F5 Inventario). */}
        <ul
          role="list"
          data-testid="cupos-libres-strip-list"
          className="flex min-w-0 flex-1 flex-wrap items-center gap-x-4 gap-y-1.5 text-sm"
        >
          {items.length === 0 ? (
            <li
              className="text-muted-foreground/70 text-xs"
              data-testid="cupos-libres-strip-empty"
            >
              —
            </li>
          ) : (
            items.map((it) => {
              const ratio =
                it.cupo_maximo === 0
                  ? Number.POSITIVE_INFINITY
                  : it.activos / it.cupo_maximo;
              const color = classForPorcentaje(ratio);
              return (
                <li
                  key={it.uuid_tipo_vehiculo}
                  className="inline-flex items-center gap-1.5"
                  data-testid={`cupos-libres-strip-row-${it.tipo}`}
                  data-color={color}
                  aria-live="polite"
                  aria-atomic="false"
                >
                  <span
                    aria-hidden
                    className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${DOT_BG[color]}`}
                  />
                  <span className="text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground/80">
                    {it.tipo}
                  </span>
                  <span
                    className={`font-mono text-xs font-semibold tabular-nums ${DOT_TEXT[color]}`}
                  >
                    {it.activos}
                    <span className="mx-0.5 text-muted-foreground/60">/</span>
                    {it.cupo_maximo}
                  </span>
                </li>
              );
            })
          )}
        </ul>

        {/* KPI agregado. Mismo tamaño que los counts por tipo (text-xs)
            para que el footer se lea como UNA sola fila de datos,
            no como "label chico + número grande". Separador visual
            con `border-l` solo en lg+ (mobile ya hace wrap). */}
        <div
          className="flex shrink-0 items-center gap-1.5 lg:border-l lg:border-border/40 lg:pl-4"
          data-testid="cupos-libres-strip-total-block"
        >
          <span className="text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground/80">
            {t('operacion:miTurno.kpis.cuposLibres', {
              defaultValue: 'Libres',
            })}
          </span>
          <span
            data-testid="cupos-libres-strip-total"
            className="font-mono text-xs font-semibold tabular-nums text-foreground"
          >
            {hasRealCupos ? totalCuposLibres : '—'}
          </span>
        </div>
      </div>
    </footer>
  );
}
