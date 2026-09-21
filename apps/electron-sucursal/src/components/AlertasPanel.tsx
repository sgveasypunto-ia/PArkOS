/**
 * `<AlertasPanel />` — orchestrator for the branch-side alertas
 * dashboard (HU-F11.2, REQ-OPS-178 + REQ-OPS-181 + REQ-OPS-182).
 *
 * Promoted from the F11.1 placeholder stub at
 * `features/sync/components/AlertasPanel.tsx:17`. The stub never
 * shipped to users — this rewrite is authorised by
 * R-F11.1-CARRY-2 (F11.1 verify-report). The stub file is deleted
 * in C6.
 *
 * Composition:
 *   - `useAlertas(uuid_sucursal)` — supplies `mergedAlertas` (post
 *     `alert_types` merge) + `openAlertsCount` derived selector.
 *   - `<AlertaFilterChips>` — client-side filter (severidad +
 *     tipo_alerta); chip state is local; no `parkosFetch`
 *     re-validation.
 *   - `<AlertaCard>` × N — one per surviving business alert (the
 *     8 technical codes are dropped SILENTLY inside `useAlertas`
 *     per ABIERTO-06).
 *   - Empty state — `role="status"` copy when no business alerts
 *     remain after filter.
 *   - Error state — `role="alert"` copy when the SWR fetcher errors.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAlertas } from '../features/alertas/hooks/useAlertas';
import { AlertaCard } from '../features/alertas/components/AlertaCard';
import {
  AlertaFilterChips,
  type SeverityFilter,
} from '../features/alertas/components/AlertaFilterChips';

export interface AlertasPanelProps {
  uuid_sucursal: string | null;
}

export function AlertasPanel({ uuid_sucursal }: AlertasPanelProps): JSX.Element | null {
  const { t } = useTranslation();
  const { mergedAlertas, openAlertsCount, error } = useAlertas(uuid_sucursal);

  const [activeSeveridad, setActiveSeveridad] = useState<Set<SeverityFilter>>(
    () => new Set<SeverityFilter>(),
  );
  const [activeTipoAlerta, setActiveTipoAlerta] = useState<Set<string>>(() => new Set<string>());

  const filtered = useMemo(() => {
    return mergedAlertas.filter((a) => {
      if (activeSeveridad.size > 0 && !activeSeveridad.has(a.severidad)) return false;
      if (activeTipoAlerta.size > 0) {
        const code = a.tipo_alerta;
        if (!code || !activeTipoAlerta.has(code)) return false;
      }
      return true;
    });
  }, [mergedAlertas, activeSeveridad, activeTipoAlerta]);

  const toggleSeveridad = (sev: SeverityFilter): void => {
    setActiveSeveridad((prev) => {
      const next = new Set(prev);
      if (next.has(sev)) next.delete(sev);
      else next.add(sev);
      return next;
    });
  };

  const toggleTipoAlerta = (tipo: string): void => {
    setActiveTipoAlerta((prev) => {
      const next = new Set(prev);
      if (next.has(tipo)) next.delete(tipo);
      else next.add(tipo);
      return next;
    });
  };

  // F11.2 (REQ-OPS-178) — render gate: do not paint the panel before the
  // operator has a branch context. The SWR inside `useAlertas` already
  // null-keys on `!uuid_sucursal` so no fetch fires on /login — but the
  // section markup (header, filter chips, empty state) must also stay out
  // of the pre-auth surface, otherwise the auditor sees operational state
  // they should not see yet. Sits AFTER all hooks (React rules of hooks).
  if (!uuid_sucursal) return null;

  return (
    <section
      aria-labelledby="alertas-panel-title"
      className="space-y-4"
      data-testid="alertas-panel"
    >
      <header className="flex items-center justify-between gap-2">
        <h2 id="alertas-panel-title" className="text-lg font-semibold">
          {t('alertas:dashboard.title', { defaultValue: 'Alertas de la sucursal' })}
        </h2>
        <span
          className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold text-muted-foreground"
          data-testid="open-alerts-count"
          aria-live="polite"
        >
          {openAlertsCount}
        </span>
      </header>

      {error && (
        <p role="alert" className="text-sm text-destructive" data-testid="alertas-error">
          {t('alertas:dashboard.error', { defaultValue: 'Error al cargar alertas' })}
        </p>
      )}

      <AlertaFilterChips
        alerts={mergedAlertas}
        activeSeveridad={activeSeveridad}
        activeTipoAlerta={activeTipoAlerta}
        onToggleSeveridad={toggleSeveridad}
        onToggleTipoAlerta={toggleTipoAlerta}
      />

      {filtered.length === 0 ? (
        <p role="status" className="text-sm text-muted-foreground" data-testid="alertas-empty">
          {t('alertas:dashboard.empty', { defaultValue: 'Sin alertas activas para los filtros seleccionados.' })}
        </p>
      ) : (
        <ul className="space-y-2" data-testid="alertas-list">
          {filtered.map((a) => (
            <AlertaCard key={a.uuid} alert={a} />
          ))}
        </ul>
      )}
    </section>
  );
}
