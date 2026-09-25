/**
 * `<CuposLibresStrip />` — footer sticky de cupos del dashboard.
 *
 * **Operador 2026-09-22 (minimalista):** una sola fila angosta
 * (`py-2`, ~40-48px, `max-h-[80px]`) con dot + texto por tipo.
 *
 * **Operador 2026-09-24 (rediseño "grande y llamativo") — REVERTIDO
 * el 2026-09-25, se deja como historial de lo que NO hacer:** se
 * probó una tarjeta individual grande por tipo (`text-3xl`/`text-4xl`,
 * mucho padding, altura sin tope) porque la fila angosta "pasaba
 * desapercibida". El operador lo rechazó explícitamente: "rompe
 * totalmente el diseño" / "el tamaño es exageradamente grande".
 *
 * **Operador 2026-09-25 (corrección de escala, vigente):** vuelve a
 * la densidad compacta de la iteración minimalista — chips pequeños
 * en una sola fila (`inline-flex`, `rounded-full`, `text-sm`/`text-[11px]`),
 * alineados a la misma escala tipográfica que el resto del dashboard
 * (botones del sidebar `h-11 text-sm`, chip `turno-activo-toggle`
 * `h-8 text-xs`, chips `hotkey-*` `h-7 text-[11px]`) — el footer tiene
 * que sentirse parte de la misma familia visual, no un elemento
 * aparte con su propia escala. `max-h-[80px]` vuelve a estar activo;
 * `Dashboard.tsx` vuelve a reservar `max-h-[calc(100vh-14rem)]` para
 * "Vehículos dentro" (ya no hace falta el `20rem` de la iteración
 * grande).
 *
 * Directivas que se MANTIENEN de ambas iteraciones anteriores (no
 * son parte de lo rechazado, son fixes funcionales correctos):
 *   - Un tipo con `cupo_maximo === 0` (no habilitado en la sucursal)
 *     NUNCA se muestra — ni en la lista ni en el total agregado.
 *   - El número mostrado como protagonista de cada chip es
 *     `disponible` (cupos libres), no `activos/cupo_maximo` a secas
 *     (ese dato queda como texto secundario chico entre paréntesis).
 *   - Ícono heurístico por tipo (`iconForTipo`) y color por umbral
 *     (`classForPorcentaje`) se mantienen, pero como tinte sutil de
 *     un chip pequeño, no como fondo protagonista de una tarjeta.
 *
 * **Reactividad:** cuando el operador ejecuta un ingreso/salida, el
 * backend hace `REFRESH MATERIALIZED VIEW CONCURRENTLY` y el SWR
 * poll (10s) repuebla `data.items`. El footer se actualiza solo.
 *
 * **Por qué NO reusa `<OcupacionPanel />`:** ese componente está
 * diseñado para vista vertical (right-sidebar del F11.x) con barras
 * de progreso + Tooltip con leyenda — shape distinto al de esta fila
 * de chips. Se reusa solo la lógica de color (`classForPorcentaje`).
 */
import type { LucideIcon } from 'lucide-react';
import { Bike, Car, Truck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useOcupacion } from '../hooks/useOcupacion';
import { classForPorcentaje } from '../occupancyThresholds';

type ColorLevel = 'green' | 'yellow' | 'red';

// Chip compacto por tipo: tinte sutil de fondo/borde por umbral — ya
// NO una tarjeta grande, solo un matiz que distingue el estado.
const CHIP_CLASS: Record<ColorLevel, string> = {
  green: 'bg-success',
  yellow: 'bg-warning',
  red: 'bg-destructive',
};
const NUMBER_TEXT: Record<ColorLevel, string> = {
  green: 'text-success-foreground',
  yellow: 'text-warning-foreground',
  red: 'text-destructive-foreground',
};
const ICON_TEXT: Record<ColorLevel, string> = {
  green: 'text-success-foreground/80',
  yellow: 'text-warning-foreground/80',
  red: 'text-destructive-foreground/80',
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
      // F31.3 rediseño: `lg:col-span-3` era un bug preexistente — el grid
      // raíz de Dashboard.tsx solo tiene 2 columnas reales
      // (`grid-cols-[240px_1fr]`), nunca 3. Se corrige a `md:col-span-2`,
      // alineado además con el nuevo breakpoint del sidebar (md en vez de
      // lg — ver Dashboard.tsx). `overflow-y-auto` es la red de
      // seguridad: si algún día hay muchos tipos de vehículo (catálogo
      // abierto) y los chips envuelven a más líneas de las que caben en
      // `max-h-[80px]`, el footer scrollea internamente en vez de
      // desbordarse visualmente sobre la tarjeta de arriba.
      className="sticky bottom-0 z-10 col-span-1 max-h-[80px] overflow-y-auto border-t border-border/40 bg-card/80 px-4 py-2 shadow-apple-sm backdrop-blur-md md:col-span-2 md:row-start-3"
    >
      <div className="flex flex-wrap items-center gap-2 md:flex-nowrap">
        <ul
          role="list"
          data-testid="cupos-libres-strip-list"
          className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5"
        >
          {visibleItems.length === 0 ? (
            <li
              className="text-xs text-muted-foreground/70"
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
                  className={`inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 ${CHIP_CLASS[color]}`}
                >
                  <Icon aria-hidden className={`h-3.5 w-3.5 shrink-0 ${ICON_TEXT[color]}`} />
                  <span className={`text-[11px] font-semibold uppercase tracking-[0.04em] ${NUMBER_TEXT[color]}/80`}>
                    {it.tipo}
                  </span>
                  {/* Dato primario: cupos libres explícitos. */}
                  <span className={`font-mono text-sm font-semibold tabular-nums ${NUMBER_TEXT[color]}`}>
                    {it.disponible}
                  </span>
                  <span className={`text-[10px] font-medium normal-case ${NUMBER_TEXT[color]}/70`}>
                    {t('operacion:cuposLibresStrip.libres', { defaultValue: 'libres' })}
                  </span>
                  {/* Dato secundario: ocupados/total, como contexto chico. */}
                  <span className={`font-mono text-[10px] tabular-nums ${NUMBER_TEXT[color]}/60`}>
                    ({it.activos}/{it.cupo_maximo})
                  </span>
                </li>
              );
            })
          )}
        </ul>

        {/* KPI agregado — sigue siendo el dato más importante del
            footer, con algo más de jerarquía que los chips por tipo,
            pero en la misma escala del resto de la UI (no text-4xl). */}
        <div
          className="flex h-7 shrink-0 items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 lg:ml-2"
          data-testid="cupos-libres-strip-total-block"
        >
          <span className="text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground/80">
            {t('operacion:miTurno.kpis.cuposLibres', {
              defaultValue: 'Libres',
            })}
          </span>
          <span
            data-testid="cupos-libres-strip-total"
            className="font-mono text-base font-bold tabular-nums text-primary"
          >
            {hasRealCupos ? totalCuposLibres : '—'}
          </span>
        </div>
      </div>
    </footer>
  );
}
