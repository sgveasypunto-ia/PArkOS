/**
 * `<TarifaBadge>` — presentational component que muestra la tarifa
 * aplicable al tipo de vehículo detectado (HU-F4.2 — T5).
 *
 * Recibe `{tarifa, fetchedAt, isStale}` ya calculados por
 * `useTarifasVigentes`. NO depende directamente de F4.1 (`<PlacaInput>`);
 * la composición TarifaBadge ← useTarifasVigentes ← tarifa values es
 * single-direction (DEC-F4.2-07 — no F4.1 import).
 *
 * Reglas de render:
 *   - `tarifa === null` → retorna `null` (badge oculto). El hook garantiza
 *     que durante la primera fase de hidratación `tarifa === null` (badge
 *     hidden por design.md §Data Flow — no mostrar número sin corroborar).
 *   - `isStale === true` → renderiza:
 *       1. El valor formateado con `formatCOP` (F3.3 — `caja/lib/format`).
 *       2. Una línea stale-mark con `role="status"` (es-CO literal, no i18n).
 *       3. Un `<span class="sr-only">` con `id="tarifa-stale-help"` cuyo
 *          texto es la ayuda WCAG; el wrapper recibe `aria-describedby`
 *          para que screen readers anuncien la advertencia.
 *   - `isStale === false` → renderiza solo el valor formateado.
 *
 * WCAG 2.1 AA wiring (DEC-SUC-10): stale-mark es texto audible vía
 * `role="status"` (aria-live="polite" implícito). El wrapper NO usa
 * `role="status"` para evitar doble anuncio del valor numérico.
 *
 * DEC-SUC-12: el cliente MUESTRA el valor, nunca lo calcula.
 * `formatCOP` es la ÚNICA función de formato; `Number(tarifa.valor)`
 * convierte NUMERIC(18,4) → number JS antes de delegar a Intl.
 */
import { formatCOP } from '../../caja/lib/format';
import type { TarifaVigente } from '../hooks/useTarifasVigentes';

const STALE_HELP_ID = 'tarifa-stale-help';

export interface TarifaBadgeProps {
  /** Tariga para el `uuid_tipo_vehiculo` activo; `null` durante hidratación. */
  tarifa: TarifaVigente | null;
  /** Epoch ms del último fetch; `null` si nunca se fetcheó. */
  fetchedAt: number | null;
  /** `true` cuando el cache tiene >1h de antigüedad. */
  isStale: boolean;
}

/**
 * Renderiza la tarifa vigente aplicable al tipo de vehículo detectado.
 * Retorna `null` durante la fase de hidratación del cache (primera
 * fase del two-phase render, DEC-F4.2-02).
 */
export function TarifaBadge({ tarifa, fetchedAt, isStale }: TarifaBadgeProps): JSX.Element | null {
  // fetchedAt presente solo para depuración / futuro tooltip F4.x+;
  // el flag `isStale` ya encapsula la decisión de UI.
  void fetchedAt;

  if (tarifa === null) return null;

  const ariaProps = isStale ? { 'aria-describedby': STALE_HELP_ID } : {};

  // F31.3 rediseño — el componente NO tenía ninguna regla CSS asociada
  // (grep confirma cero matches de `.tarifa-badge*` en todo el repo, el
  // mismo patrón huérfano que StatusBar antes de su rediseño): se
  // renderizaba como texto plano sin estilos. Se reemplaza por un chip
  // con tokens — superficie `bg-card`/`border-border` en el estado
  // normal, y el chip "warning" (mismo token semántico que el resto de
  // la app, AA verificado en tokens.css) cuando `isStale` — refuerza
  // visualmente la advertencia, no solo el texto.
  return (
    <div
      data-testid="tarifa-badge"
      className="inline-flex max-w-full flex-col items-start gap-1 rounded-xl border border-border/60 bg-card px-3 py-2 shadow-apple-sm"
      {...ariaProps}
    >
      <span
        data-testid="tarifa-badge-value"
        className="text-sm font-semibold tabular-nums text-foreground"
      >
        {formatCOP(Number(tarifa.valor))}
      </span>
      {isStale && (
        <span
          data-testid="tarifa-badge-stale-mark"
          role="status"
          className="inline-flex max-w-full items-center rounded-full bg-warning px-2 py-0.5 text-[11px] font-medium leading-snug text-warning-foreground"
        >
          Tarifa cacheada — verifica con el supervisor
        </span>
      )}
      {isStale && (
        <span id={STALE_HELP_ID} className="sr-only">
          La tarifa mostrada fue obtenida hace más de una hora y el sistema no ha
          podido confirmar el valor actual. Pida al supervisor que confirme el
          monto antes de cobrar.
        </span>
      )}
    </div>
  );
}
