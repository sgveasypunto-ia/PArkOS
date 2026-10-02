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
 *
 * HU-F18.4 adds the "Exportar PDF firmado" action: the same two rows
 * ``DiferenciasPanel`` renders (Efectivo / Datáfono -- esperado,
 * reportado, diferencia) are serialized and hashed (BR1) via
 * ``lib/export/pdf.ts``, with the arqueo's sucursal logo as an optional
 * header (BR2, via ``fetchSucursalLogoDataUrl``).
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { HashChainStatus } from '@/components/HashChainStatus';
import { Button } from '@/components/ui/button';
import { exportSignedPdf } from '@/lib/export/pdf';
import type { CsvColumn } from '@/lib/export/csv';

import type { ArqueoRead, DiferenciasRead } from '../api/arqueosSchema';
import { fetchSucursalLogoDataUrl } from '../lib/sucursalLogo';
import { DiferenciasPanel } from './DiferenciasPanel';

export interface ArqueoDetalleProps {
  arqueo: ArqueoRead | null;
  /** Optional pre-loaded alerta uuid (F18.3 will surface this). */
  uuidAlerta: string | null;
  diferenciasLoading: boolean;
  diferenciasError: Error | undefined;
  diferencias: DiferenciasRead | null;
  onClose: () => void;
}

interface DiferenciaExportRow {
  medio: string;
  esperado: number;
  reportado: number;
  diferencia: number;
}

/** Mirrors `DiferenciasPanel`'s `fmt` — the exported table shows the same
 * values, formatted the same way, as what's on screen. */
function fmtNumber(value: number): string {
  return new Intl.NumberFormat('es-CO', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

const EXPORT_COLUMNS: CsvColumn<DiferenciaExportRow>[] = [
  { header: 'Medio', accessor: (r) => r.medio },
  { header: 'Esperado', accessor: (r) => fmtNumber(r.esperado) },
  { header: 'Reportado', accessor: (r) => fmtNumber(r.reportado) },
  { header: 'Diferencia', accessor: (r) => fmtNumber(r.diferencia) },
];

function buildExportRows(diferencias: DiferenciasRead): DiferenciaExportRow[] {
  return [
    {
      medio: 'Efectivo',
      esperado: diferencias.valor_efectivo_esperado,
      reportado: diferencias.valor_efectivo_reportado,
      diferencia: diferencias.diferencia_efectivo,
    },
    {
      medio: 'Datáfono',
      esperado: diferencias.valor_datafono_esperado,
      reportado: diferencias.valor_datafono_reportado,
      diferencia: diferencias.diferencia_datafono,
    },
  ];
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
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  async function handleExportPdf(): Promise<void> {
    if (!arqueo || !diferencias) return;
    setExportError(null);
    setIsExportingPdf(true);
    try {
      const logoDataUrl = await fetchSucursalLogoDataUrl(arqueo.uuid_sucursal);
      await exportSignedPdf(
        `arqueo-${arqueo.uuid}.pdf`,
        EXPORT_COLUMNS,
        buildExportRows(diferencias),
        {
          title: t('arqueos.detail.title', 'Detalle de arqueo'),
          subtitle: `${arqueo.created_at} · ${arqueo.uuid_sucursal ?? '—'}`,
          logoDataUrl,
        },
      );
    } catch (err) {
      setExportError(
        err instanceof Error
          ? err.message
          : t('arqueos.detail.exportPdfError', 'No se pudo generar el PDF. Intenta de nuevo.'),
      );
    } finally {
      setIsExportingPdf(false);
    }
  }

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
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void handleExportPdf()}
            disabled={!diferencias || diferenciasLoading || diferenciasError !== undefined || isExportingPdf}
            data-testid="arqueo-detail-export-pdf"
          >
            {isExportingPdf
              ? t('arqueos.detail.exportingPdf', 'Generando…')
              : t('arqueos.detail.exportPdf', 'Exportar PDF firmado')}
          </Button>
          <button
            data-testid="arqueo-detail-close"
            type="button"
            onClick={onClose}
            className="rounded-md border bg-muted/40 px-3 py-1 text-xs hover:bg-muted/60"
          >
            {t('arqueos.detail.close')}
          </button>
        </div>
      </header>

      {exportError && (
        <p
          role="alert"
          data-testid="arqueo-detail-export-pdf-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {exportError}
        </p>
      )}

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