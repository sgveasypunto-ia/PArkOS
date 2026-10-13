/**
 * `<FacturaHeaderCard />` — presentational header card for the drill-down
 * page (REQ-X-02 of `facturacion-admin/spec.md`).
 *
 * Renders:
 *   - UUID (truncated 8 chars + copy-to-clipboard).
 *   - `created_at` (formatted with `formatBackendTimestampLocal`).
 *   - Subtotal / descuento / total (es-CO money format).
 *   - Estado badge (via `<FacturaEstadoBadge>`).
 *   - Numero completo (prefijo+consecutivo) from the FE fetch — "—" when
 *     the FE row is missing (post-creation pending FE numbering, or no
 *     active resolucion in the branch).
 *   - Hash actual from the most recent `log_transaccional` row
 *     (copy-to-clipboard, mono font). Missing → "—".
 *
 * Section-level error/loading is rendered inline (REQ-X-11) so a hash
 * fetch failure does not block the rest of the page.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Check } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

import { formatBackendTimestampLocal } from '@/features/reporteria/components/dateRange';
import type { FacturaDetailRead } from '../api/facturacionAdminApi';
import type { FacturaElectronicaRead } from '../api/facturacionAdminSchema';
import { FacturaEstadoBadge } from './FacturaEstadoBadge';
import type { FacturaEstado } from '../lib/estadoFactura';

export interface FacturaHeaderCardProps {
  header: FacturaDetailRead;
  estado: FacturaEstado;
  fe: FacturaElectronicaRead | undefined;
  feLoading: boolean;
  feError: Error | null | undefined;
  hash: string | null;
  hashLoading: boolean;
  hashError: Error | null | undefined;
  onRetryFe: () => void;
  onRetryHash: () => void;
}

function formatMoney(value: number): string {
  return value.toLocaleString('es-CO', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

function CopyButton({ value, testId }: { value: string; testId: string }): JSX.Element {
  const { t } = useTranslation('facturacionAdmin');
  const [copied, setCopied] = useState(false);
  const onCopy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API not available in some browsers — silently no-op.
    }
  };
  return (
    <Button
      type="button"
      size="icon"
      variant="ghost"
      onClick={onCopy}
      aria-label={t('header.copyTooltip', 'Copiar')}
      data-testid={testId}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden />
      )}
    </Button>
  );
}

export function FacturaHeaderCard({
  header,
  estado,
  fe,
  feLoading,
  feError,
  hash,
  hashLoading,
  hashError,
  onRetryFe,
  onRetryHash,
}: FacturaHeaderCardProps): JSX.Element {
  const { t } = useTranslation('facturacionAdmin');
  const numeroCompleto =
    fe?.prefijo && fe?.consecutivo !== null && fe?.consecutivo !== undefined
      ? `${fe.prefijo}-${fe.consecutivo}`
      : '—';

  return (
    <Card data-testid="factura-header-card">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-2xl">
              {t('header.title', 'Detalle de factura')}
            </CardTitle>
            <CardDescription>
              {t('header.subtitle', 'Investigación transaccional y acciones de admin.')}
            </CardDescription>
          </div>
          <FacturaEstadoBadge estado={estado} />
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-3">
        <div className="space-y-1">
          <p className="text-xs uppercase text-muted-foreground">
            {t('header.uuidLabel', 'UUID')}
          </p>
          <div className="flex items-center gap-1">
            <code className="font-mono text-sm" data-testid="factura-uuid">
              {header.uuid}
            </code>
            <CopyButton value={header.uuid} testId="factura-uuid-copy" />
          </div>
        </div>
        <div className="space-y-1">
          <p className="text-xs uppercase text-muted-foreground">
            {t('header.fechaLabel', 'Fecha de emisión')}
          </p>
          <p className="text-sm tabular-nums" data-testid="factura-fecha">
            {formatBackendTimestampLocal(header.created_at)}
          </p>
        </div>
        <div className="space-y-1">
          <p className="text-xs uppercase text-muted-foreground">
            {t('header.numeroCompletoLabel', 'Número')}
          </p>
          {feLoading ? (
            <p className="text-sm text-muted-foreground" data-testid="factura-numero-completo-loading">
              {t('errors.sectionFail', 'Cargando…')}
            </p>
          ) : feError ? (
            <p className="text-sm text-destructive" data-testid="factura-numero-completo-error">
              — <button type="button" onClick={onRetryFe} className="underline">
                {t('errors.retry', 'Reintentar')}
              </button>
            </p>
          ) : (
            <p className="font-mono text-sm" data-testid="factura-numero-completo">
              {numeroCompleto}
            </p>
          )}
        </div>
        <div className="space-y-1">
          <p className="text-xs uppercase text-muted-foreground">
            {t('header.subtotalLabel', 'Subtotal')}
          </p>
          <p className="text-sm tabular-nums" data-testid="factura-subtotal">
            {formatMoney(header.subtotal)}
          </p>
        </div>
        <div className="space-y-1">
          <p className="text-xs uppercase text-muted-foreground">
            {t('header.descuentoLabel', 'Descuento')}
          </p>
          <p className="text-sm tabular-nums" data-testid="factura-descuento">
            {formatMoney(header.descuento)}
          </p>
        </div>
        <div className="space-y-1">
          <p className="text-xs uppercase text-muted-foreground">
            {t('header.totalLabel', 'Total')}
          </p>
          <p className="text-base font-semibold tabular-nums" data-testid="factura-total">
            {formatMoney(header.total)}
          </p>
        </div>
        <div className="space-y-1 md:col-span-3">
          <p className="text-xs uppercase text-muted-foreground">
            {t('header.hashLabel', 'Hash actual')}
          </p>
          {hashLoading ? (
            <p className="font-mono text-xs text-muted-foreground">…</p>
          ) : hashError ? (
            <p className="text-sm text-destructive" data-testid="factura-hash-error">
              — <button type="button" onClick={onRetryHash} className="underline">
                {t('errors.retry', 'Reintentar')}
              </button>
            </p>
          ) : (
            <div className="flex items-center gap-1">
              <code
                className="font-mono text-xs break-all"
                data-testid="factura-hash"
              >
                {hash ?? '—'}
              </code>
              {hash ? <CopyButton value={hash} testId="factura-hash-copy" /> : null}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
