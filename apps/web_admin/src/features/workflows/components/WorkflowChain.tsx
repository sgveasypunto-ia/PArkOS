/**
 * `<WorkflowChain />` -- GENERIC timeline for an `[L-W]` workflow's
 * transition chain (`repo.workflow.append_transition` /
 * `STATE_MACHINES`).
 *
 * Deliberately NOT coupled to `prod.alerta` (or any other resource):
 * HU-F19.5 is its first consumer (`alertas/pages/AlertaDetalle.tsx`),
 * but HU-F19.6 and Fase 20 (`anulaciones` / `reclamos`) are expected to
 * reuse this SAME component for their own chains -- those tables share
 * the exact `[L-W]` shape (`estado`, `timestamp_evento`, an actor
 * column, parent-chain FK) per `schemas/workflows.py`. Coupling this to
 * `alerta`'s field names would force a rewrite the moment the second
 * consumer shows up, so every alerta-specific concern (uuid lookup,
 * `EstadoAlertaBadge`, the "walk `uuid_alerta_padre`" gap workaround)
 * stays in `features/alertas/` and ONLY the generic
 * `WorkflowTransition` shape crosses this boundary.
 *
 * `renderStatusBadge` is an injection point so each domain can plug in
 * its own status badge (`EstadoAlertaBadge` for alerta, something else
 * for anulaciones/reclamos later) without this component importing
 * domain code. Omit it and the raw `status` string renders instead.
 */
import { useTranslation } from 'react-i18next';
import type { ReactNode } from 'react';

export interface WorkflowTransition {
  /** Stable React key -- typically the row's own uuid. */
  id: string;
  /** Generic workflow state at this transition (e.g. `estado`). */
  status: string;
  /** ISO-8601 timestamp, or `null` when the BE didn't carry one. */
  timestamp: string | null;
  /** Raw actor identifier (uuid) or a resolved display name; caller's choice. */
  actor: string | null;
  /** Free-text note attached to this transition, or `null` when the BE doesn't expose it for this resource. */
  observaciones: string | null;
}

export interface WorkflowChainProps {
  transitions: WorkflowTransition[];
  isLoading?: boolean;
  error?: Error | null;
  /** Per-domain status badge injection; falls back to the raw `status` string. */
  renderStatusBadge?: (status: string) => ReactNode;
}

export function WorkflowChain({
  transitions,
  isLoading = false,
  error = null,
  renderStatusBadge,
}: WorkflowChainProps): JSX.Element {
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <p role="status" aria-live="polite" data-testid="workflow-chain-loading" className="text-sm text-muted-foreground">
        {t('workflowChain.loading', 'Cargando historial…')}
      </p>
    );
  }

  if (error !== null) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="workflow-chain-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {t('workflowChain.error', 'No se pudo cargar el historial de transiciones.')}
      </p>
    );
  }

  if (transitions.length === 0) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="workflow-chain-empty"
        className="text-sm text-muted-foreground"
      >
        {t('workflowChain.empty', 'Sin transiciones registradas.')}
      </p>
    );
  }

  return (
    <ol data-testid="workflow-chain" className="space-y-3 border-l pl-4">
      {transitions.map((tr) => (
        <li key={tr.id} data-testid={`workflow-chain-item-${tr.id}`} className="relative">
          <span
            aria-hidden="true"
            className="absolute -left-[1.1rem] top-1.5 size-2 rounded-full bg-primary"
          />
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {renderStatusBadge ? renderStatusBadge(tr.status) : <span className="font-medium">{tr.status}</span>}
            <span className="font-mono text-xs text-muted-foreground">
              {tr.timestamp ?? t('workflowChain.noTimestamp', 'Sin fecha')}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {t('workflowChain.actor', 'Actor')}: {tr.actor ?? '—'}
          </p>
          {tr.observaciones !== null && tr.observaciones.length > 0 && (
            <p className="mt-1 text-sm">{tr.observaciones}</p>
          )}
        </li>
      ))}
    </ol>
  );
}
