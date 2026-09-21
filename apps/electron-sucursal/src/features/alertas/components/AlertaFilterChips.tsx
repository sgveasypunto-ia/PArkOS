/**
 * `AlertaFilterChips.tsx` — client-side filter chips for severity +
 * tipo_alerta (HU-F11.2, REQ-OPS-178 + DA-F11.2-3).
 *
 * Filter state lives in the parent `<AlertasPanel />` — this component
 * is purely presentational. Clicking a chip toggles its `aria-pressed`
 * state via the `onToggle` callback. The panel filters the
 * `mergedAlertas` array client-side; no `parkosFetch` re-validation
 * fires (REQ-OPS-178 client-side-only).
 */
import { useTranslation } from 'react-i18next';

import type { MergedAlerta } from '../../../lib/api/schemas/alertas';

export type SeverityFilter = 'alta' | 'media' | 'baja';

export interface AlertaFilterChipsProps {
  alerts: MergedAlerta[];
  activeSeveridad: ReadonlySet<SeverityFilter>;
  activeTipoAlerta: ReadonlySet<string>;
  onToggleSeveridad: (sev: SeverityFilter) => void;
  onToggleTipoAlerta: (tipo: string) => void;
}

const SEVERIDADES: SeverityFilter[] = ['alta', 'media', 'baja'];

export function AlertaFilterChips({
  alerts,
  activeSeveridad,
  activeTipoAlerta,
  onToggleSeveridad,
  onToggleTipoAlerta,
}: AlertaFilterChipsProps): JSX.Element {
  const { t } = useTranslation();

  // Derive the set of distinct tipo_alerta values present in the
  // current payload — chip population tracks the data, not the
  // hardcoded whitelist (which is enforced upstream in useAlertas).
  const tipos = Array.from(new Set(alerts.map((a) => a.tipo_alerta).filter((v): v is string => !!v)));

  return (
    <div
      role="group"
      aria-label={t('alertas:dashboard.filters.label', { defaultValue: 'Filtros de alertas' })}
      className="flex flex-wrap items-center gap-2"
      data-testid="alerta-filter-chips"
    >
      {SEVERIDADES.map((sev) => {
        const pressed = activeSeveridad.has(sev);
        return (
          <button
            key={sev}
            type="button"
            role="switch"
            aria-checked={pressed}
            aria-pressed={pressed}
            aria-label={`severidad-${sev}`}
            data-testid={`chip-severidad-${sev}`}
            onClick={() => onToggleSeveridad(sev)}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
              pressed
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border bg-background text-foreground hover:bg-muted'
            }`}
          >
            {t(`alertas:severidad.${sev}`, { defaultValue: sev })}
          </button>
        );
      })}
      {tipos.map((tipo) => {
        const pressed = activeTipoAlerta.has(tipo);
        return (
          <button
            key={tipo}
            type="button"
            role="switch"
            aria-checked={pressed}
            aria-pressed={pressed}
            aria-label={`tipo-${tipo}`}
            data-testid={`chip-tipo-${tipo}`}
            onClick={() => onToggleTipoAlerta(tipo)}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
              pressed
                ? 'border-secondary bg-secondary text-secondary-foreground'
                : 'border-border bg-background text-foreground hover:bg-muted'
            }`}
          >
            {tipo}
          </button>
        );
      })}
    </div>
  );
}
