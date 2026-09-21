/**
 * `DrillDownButton.tsx` — per-`tipo_alerta` drill-down link (HU-F11.2,
 * REQ-OPS-178 + DA-F11.2-4). Renders an `<a>` element whose `href` is
 * read from the canonical router map at `lib/alertas/router.ts`.
 *
 * The button is a plain anchor (NOT a `react-router-dom` `<Link />`)
 * so the href is observable from RTL tests via `getAttribute('href')`
 * without needing the router's match path; navigation through
 * `<MemoryRouter>` works either way.
 */
import { useTranslation } from 'react-i18next';

import type { MergedAlerta } from '../../../lib/api/schemas/alertas';

import { drillDownHref } from '../../../lib/alertas/router';

export interface DrillDownButtonProps {
  alert: MergedAlerta;
}

export function DrillDownButton({ alert }: DrillDownButtonProps): JSX.Element {
  const { t } = useTranslation();
  const href = drillDownHref(alert);
  return (
    <a
      href={href}
      data-testid="drilldown-button"
      data-tipo-alerta={alert.tipo_alerta ?? 'desconocido'}
      aria-label={`drilldown-${alert.tipo_alerta ?? 'desconocido'}`}
      className="text-sm font-medium text-primary underline-offset-2 hover:underline"
    >
      {t('alertas:dashboard.drillDown', { defaultValue: 'Ver detalle' })}
    </a>
  );
}
