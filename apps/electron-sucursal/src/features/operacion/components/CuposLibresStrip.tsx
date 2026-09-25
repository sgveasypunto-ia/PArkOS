/**
 * `<CuposLibresStrip />` — footer sticky de cupos del dashboard.
 *
 * **Operador 2026-09-22 (segunda pasada de reorganización) — SUPERADA
 * por la directiva 2026-09-24 de abajo, se deja como historial:**
 * la versión anterior renderizaba el `<OcupacionPanel />` completo
 * (lista vertical con dot + label + count + barra de progreso por
 * tipo) + un KPI grande. Resultado: footer visualmente pesado,
 * ~140px de alto, las barras de progreso robaban atención. Esa
 * iteración lo redujo a una sola fila angosta (`py-2`, ~40-48px,
 * `max-h-[80px]`) con solo un dot + texto.
 *
 * **Operador 2026-09-24 (rediseño, SUPERSEDE la iteración minimalista
 * de arriba):** el footer angosto pasaba desapercibido — directiva
 * explícita de que "llame la atención y tenga más espacio en la
 * pantalla". Nueva versión:
 *   - Una tarjeta individual por tipo de vehículo (grid, no una sola
 *     fila de texto corrido) — fondo + borde teñidos por el color de
 *     umbral (`classForPorcentaje`), ícono del tipo, y el número de
 *     cupos libres en tipografía grande (`text-3xl`) como dato
 *     protagonista; ocupados/total queda como dato secundario chico.
 *   - El bloque total agregado también crece en jerarquía visual
 *     (`text-4xl`, tarjeta propia) — es el dato más importante del
 *     footer.
 *   - Altura ya NO está topeada en 80px — crecer verticalmente está
 *     permitido y buscado. `Dashboard.tsx` reserva más alto para la
 *     lista de "Vehículos dentro" en consecuencia
 *     (`VehiculosDentroList`, `max-h-[calc(100vh-20rem)]`).
 *   - Sigue siendo `sticky bottom-0 z-10` dentro del mismo `<footer>`
 *     full-width del dashboard — NO se convierte en modal ni cambia
 *     de ubicación, solo gana presencia dentro de esa franja.
 *   - Mobile (`<sm`): grid de 2 columnas, altura mayor es aceptable
 *     (ya no se fuerza una sola fila angosta).
 *
 * Directivas que se mantienen sin cambio de la iteración anterior:
 *   - Un tipo con `cupo_maximo === 0` (no habilitado en la sucursal)
 *     NUNCA se muestra — ni en la grilla ni en el total agregado.
 *   - El número mostrado como protagonista es `disponible` (cupos
 *     libres), no `activos/cupo_maximo` a secas.
 *
 * **Reactividad:** cuando el operador ejecuta un ingreso/salida, el
 * backend hace `REFRESH MATERIALIZED VIEW CONCURRENTLY` y el SWR
 * poll (10s) repuebla `data.items`. El footer se actualiza solo.
 *
 * **Por qué NO reusa `<OcupacionPanel />`:** ese componente está
 * diseñado para vista vertical (right-sidebar del F11.x) con barras
 * de progreso + Tooltip con leyenda — shape distinto al de esta
 * grilla de tarjetas. Se reusa solo la lógica de color
 * (`classForPorcentaje`).
 */
import type { LucideIcon } from 'lucide-react';
import { Bike, Car, Truck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useOcupacion } from '../hooks/useOcupacion';
import { classForPorcentaje } from '../occupancyThresholds';

type ColorLevel = 'green' | 'yellow' | 'red';

// Tarjeta por tipo: fondo + borde teñidos por umbral (más presencia
// visual que el dot chico de la iteración anterior).
const CARD_CLASS: Record<ColorLevel, string> = {
  green:
    'border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/40',
  yellow:
    'border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40',
  red: 'border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/40',
};
const NUMBER_TEXT: Record<ColorLevel, string> = {
  green: 'text-emerald-700 dark:text-emerald-300',
  yellow: 'text-amber-700 dark:text-amber-300',
  red: 'text-red-700 dark:text-red-300',
};
const ICON_TEXT: Record<ColorLevel, string> = {
  green: 'text-emerald-500 dark:text-emerald-400',
  yellow: 'text-amber-500 dark:text-amber-400',
  red: 'text-red-500 dark:text-red-400',
};

/**
 * Ícono por tipo de vehículo — heurística simple por palabra clave
 * sobre `tipo` (catálogo abierto, no un enum cerrado). Sin match
 * conocido → `Car` genérico (fallback seguro, nunca queda sin ícono).
 */
function iconForTipo(tipo: string): LucideIcon {
  const normalized = tipo.toLowerCase();
  if (normalized.includes('moto') || normalized.includes('bici')) return Bike;
  if (normalized.includes('cami') || normalized.includes('truck')) return Truck;
  return Car;
}

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

  // Tipos con `cupo_maximo === 0` == la sucursal NO tiene ese tipo de
  // vehículo habilitado (mismo criterio que `OcupacionStrip.legendKeyFor`:
  // `cupoMaximo === 0` → "cupo no configurado"). Directiva del operador:
  // un tipo no habilitado NUNCA se muestra en el footer — ni en la
  // grilla ni en el agregado. Un solo filtro alimenta ambos usos para
  // que nunca queden desincronizados.
  const visibleItems = items.filter((it) => it.cupo_maximo > 0);

  // Sum del campo `disponible` server-side (DEC-SUC-11). El cliente
  // NUNCA lo re-deriva.
  const totalCuposLibres = visibleItems.reduce((acc, it) => acc + it.disponible, 0);
  const hasRealCupos = visibleItems.length > 0;

  return (
    <footer
      data-testid="cupos-libres-strip"
      aria-label={t('operacion:miTurno.kpis.cuposLibres', {
        defaultValue: 'Cupos libres',
      })}
      className="sticky bottom-0 z-10 col-span-1 border-t border-border/40 bg-card/95 px-4 py-3 shadow-apple-sm backdrop-blur-md lg:col-span-3 lg:row-start-3"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch">
        <ul
          role="list"
          data-testid="cupos-libres-strip-list"
          className="grid min-w-0 flex-1 grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6"
        >
          {visibleItems.length === 0 ? (
            <li
              className="col-span-full text-xs text-muted-foreground/70"
              data-testid="cupos-libres-strip-empty"
            >
              —
            </li>
          ) : (
            visibleItems.map((it) => {
              const color = classForPorcentaje(it.activos / it.cupo_maximo);
              const Icon = iconForTipo(it.tipo);
              return (
                <li
                  key={it.uuid_tipo_vehiculo}
                  data-testid={`cupos-libres-strip-row-${it.tipo}`}
                  data-color={color}
                  aria-live="polite"
                  aria-atomic="false"
                  className={`flex items-center gap-2 rounded-xl border-2 px-3 py-2 ${CARD_CLASS[color]}`}
                >
                  <Icon aria-hidden className={`h-6 w-6 shrink-0 ${ICON_TEXT[color]}`} />
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground/80">
                      {it.tipo}
                    </span>
                    {/* Dato primario: cupos libres explícitos, tipografía
                        grande — es el número que el operador necesita ver
                        de un vistazo. */}
                    <span className={`font-mono text-3xl font-extrabold leading-tight tabular-nums ${NUMBER_TEXT[color]}`}>
                      {it.disponible}
                      <span className="ml-1 text-xs font-medium normal-case text-muted-foreground/70">
                        {t('operacion:cuposLibresStrip.libres', { defaultValue: 'libres' })}
                      </span>
                    </span>
                    {/* Dato secundario: ocupados/total, como contexto. */}
                    <span className="font-mono text-[11px] tabular-nums text-muted-foreground/60">
                      {it.activos}/{it.cupo_maximo} {t('operacion:cuposLibresStrip.ocupados', { defaultValue: 'ocupados' })}
                    </span>
                  </div>
                </li>
              );
            })
          )}
        </ul>

        {/* KPI agregado — el dato más importante del footer, con la
            mayor jerarquía visual de toda la franja. */}
        <div
          className="flex shrink-0 items-center justify-center gap-3 rounded-xl border-2 border-primary/30 bg-primary/10 px-5 py-2 sm:flex-col sm:justify-center sm:gap-0"
          data-testid="cupos-libres-strip-total-block"
        >
          <span className="text-xs font-semibold uppercase tracking-[0.04em] text-muted-foreground/80">
            {t('operacion:miTurno.kpis.cuposLibres', {
              defaultValue: 'Libres',
            })}
          </span>
          <span
            data-testid="cupos-libres-strip-total"
            className="font-mono text-4xl font-extrabold tabular-nums text-primary"
          >
            {hasRealCupos ? totalCuposLibres : '—'}
          </span>
        </div>
      </div>
    </footer>
  );
}
