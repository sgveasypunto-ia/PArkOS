/**
 * `DianRetryHistory` -- HU-F20.5 retry-chain view for one envio_dian
 * tip, walking `uuid_envio_padre` client-side (`useEnvioDianChain`, see
 * that hook's docblock for why -- no `/history` endpoint or single-item
 * GET exists for this table). Reuses the GENERIC `<WorkflowChain />`
 * (`features/workflows/components/WorkflowChain.tsx`), same as
 * `alertas/pages/AlertaDetalle.tsx` does for `prod.alerta` -- this is
 * exactly the second consumer that component's docblock anticipated.
 */
import { useTranslation } from 'react-i18next';

import { WorkflowChain, type WorkflowTransition } from '@/features/workflows/components/WorkflowChain';

import { useEnvioDianChain } from '../hooks/useEnvioDianChain';
import type { EnvioDianRead } from '../api/envioDianSchema';
import { EstadoEnvioDianBadge } from './EstadoEnvioDianBadge';

export interface DianRetryHistoryProps {
  tip: EnvioDianRead | null;
}

export function DianRetryHistory({ tip }: DianRetryHistoryProps): JSX.Element {
  const { t } = useTranslation();
  const { chain, isLoading, error } = useEnvioDianChain(tip);

  const transitions: WorkflowTransition[] = chain.map((row) => ({
    id: row.uuid,
    status: row.estado ?? t('dian.estado.none', '—'),
    timestamp: row.timestamp_evento ?? row.vigente_desde,
    actor: row.created_by,
    // `EnvioDianRead` carries no free-text observation field (cufe /
    // respuesta_proveedor.motivo_rechazo are shown separately in
    // `<DianDetalle />`'s own payload/respuesta_proveedor panes).
    observaciones: null,
  }));

  return (
    <WorkflowChain
      transitions={transitions}
      isLoading={isLoading}
      error={error ?? null}
      renderStatusBadge={(status) => <EstadoEnvioDianBadge estado={status} />}
    />
  );
}
