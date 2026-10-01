/**
 * ``ArqueoDetalle`` -- presentational detail panel for one arqueo row
 * (HU-F18.2).
 *
 * Mounted by ``ArqueosPage`` when the operator/admin clicks a row in
 * the list. Composes three signals:
 *
 *   - The row's metadata (timestamp, branch, tipo, sesion).
 *   - The ``DiferenciasPanel`` rendered from
 *     ``useArqueoDetalle().diferencias``.
 *   - The ``AlertaLink`` if the BE's ``alerta_uuid`` is present (the
 *     current list response doesn't carry ``alerta_uuid``; the
 *     container passes it once the row comes from the summary
 *     endpoint in F18.3). Today the link is hidden.
 */
import { useTranslation } from 'react-i18next';

import { HashChainStatus } from '@/components/HashChainStatus';

import type { ArqueoRead } from '../api/arqueosSchema';
import { DiferenciasPanel } from './DiferenciasPanel';

export interface ArqueoDetalleProps {
  arqueo: ArqueoRead | null;
  /** Optional pre-loaded alerta uuid (F18.3 will surface this). */
  uuidAlerta: string | null;
  diferenciasLoading: boolean;
  diferenciasError: Error | undefined;
  diferencias: import('../api/arqueosSchema').DiferenciasRead | null;
  onClose: () => void;
}

export function ArqueoDetalle({
  arqueo,
  uuidAlerta: _uuidAlerta,
  diferenciasLoading,
  diferenciasError,
  diferencias,
  onClose,
}: ArqueoDetalleProps): JSX.Element | null {
  const { t } = useTranslation();

  if (!arqueo) {
    return (
      <div
        role="status"
        data-testid="arqueo-detail-empty"
        className="rounded-md border border-dashed bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground"
      >
        {t('arqueos.detail.pickRow')}
      </div>
    );
  }

  return (
    <section
      data-testid={`arqueo-detail-${arqueo.uuid}`}
      aria-label={t('arqueos.detail.title')}
      className="space-y-4"
    >
      <header className="flex items-center justify-between gap-3 rounded-md border bg-card px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold">
            {t('arqueos.detail.title')}
          </h3>
          <p
            data-testid="arqueo-detail-meta"
            className="font-mono text-xs text-muted-foreground"
          >
            {arqueo.created_at} · {arqueo.uuid_sucursal ?? '—'}
          </p>
        </div>
        <button
          data-testid="arqueo-detail-close"
          type="button"
          onClick={onClose}
          className="rounded-md border bg-muted/40 px-3 py-1 text-xs hover:bg-muted/60"
        >
          {t('arqueos.detail.close')}
        </button>
      </header>

      <div
        data-testid="arqueo-detail-hash"
        className="rounded-md border bg-card px-4 py-2"
      >
        <HashChainStatus
          hashAnterior={null}
          hashActual={null}
        />
      </div>

      <DiferenciasPanel
        diferencias={diferencias}
        isLoading={diferenciasLoading}
        error={diferenciasError}
      />
    </section>
  );
}