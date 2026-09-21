/**
 * `AlertaCard.tsx` — single-alert card (HU-F11.2, REQ-OPS-178 +
 * DA-F11.2-4). Composes:
 *   - severity badge (alta / media / baja)
 *   - `mensaje` (post-merge display copy)
 *   - `descripcion` (small caption)
 *   - `DrillDownButton` (per-`tipo_alerta` route)
 *   - `ResolverAlertaButton` (append-only POST)
 *
 * The card carries `data-testid="alerta-card"` and `data-tipo-alerta`
 * so the e2e S2 (drill-down) and S4 (technical codes excluded)
 * scenarios can target individual rows.
 */
import { useTranslation } from 'react-i18next';

import type { MergedAlerta } from '../../../lib/api/schemas/alertas';

import { DrillDownButton } from './DrillDownButton';
import { ResolverAlertaButton } from './ResolverAlertaButton';

const SEVERITY_VARIANT: Record<'alta' | 'media' | 'baja', string> = {
  alta: 'bg-destructive text-destructive-foreground',
  media: 'bg-amber-500 text-white',
  baja: 'bg-slate-200 text-slate-700',
};

export interface AlertaCardProps {
  alert: MergedAlerta;
}

export function AlertaCard({ alert }: AlertaCardProps): JSX.Element {
  const { t } = useTranslation();
  const sev = alert.severidad;
  const variant = SEVERITY_VARIANT[sev];
  return (
    <li
      data-testid="alerta-card"
      data-tipo-alerta={alert.tipo_alerta ?? 'desconocido'}
      data-severidad={sev}
      className="flex flex-col gap-2 rounded-md border border-border bg-card p-3 text-card-foreground"
    >
      <div className="flex items-center gap-2">
        <span
          className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-semibold ${variant}`}
          aria-label={`severidad-${sev}`}
        >
          {t(`alertas:severidad.${sev}`, { defaultValue: sev })}
        </span>
        <span className="text-xs uppercase tracking-wide text-muted-foreground">
          {alert.tipo_alerta ?? 'desconocido'}
        </span>
      </div>
      <p className="text-sm font-medium">{alert.mensaje}</p>
      <p className="text-xs text-muted-foreground">{alert.descripcion}</p>
      <div className="flex items-center gap-2 pt-1">
        <DrillDownButton alert={alert} />
        <ResolverAlertaButton alert={alert} />
      </div>
    </li>
  );
}
