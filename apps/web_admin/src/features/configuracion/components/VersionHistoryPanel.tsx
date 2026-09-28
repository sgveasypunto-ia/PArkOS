/**
 * `VersionHistoryPanel.tsx` — renderiza la cadena bi-temporal de
 * versiones (tarifas o cupos) como una lista colapsable, DESC por
 * ``vigente_desde``. La primera fila lleva badge "vigente" cuando su
 * ``estado === 'activo' && vigente_hasta === null``.
 *
 * Usado por las páginas de tarifas y cupos (PR-D-ui-tarifas-cupos) para
 * el panel "Ver histórico" que se abre al click en una card. Cierra el
 * gap que el factory ``GET /{uuid}/history`` no puede cubrir cuando
 * ``close_and_insert`` emite un UUID nuevo en el PUT.
 *
 * Render: cada fila muestra el valor (o cantidad para cupos), la
 * ventana temporal (``vigente_desde → vigente_hasta`` o "abierta"), y
 * el estado. La fila vigente tiene fondo tenue + badge; las cerradas
 * quedan más apagadas.
 */
import * as React from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';

import { cn } from '@/lib/utils';

export interface VersionHistoryItem {
  uuid: string;
  /** Display value: tarifa ``valor`` or cupos ``cantidad``. */
  display: string;
  /** ISO-8601 string. */
  vigente_desde: string;
  /** ISO-8601 string or null (open-ended). */
  vigente_hasta: string | null;
  estado: string;
}

export interface VersionHistoryPanelProps {
  versions: readonly VersionHistoryItem[];
  /** Label for the display column, e.g. "Valor" or "Cantidad". */
  displayLabel: string;
  /**
   * If true, the panel is expanded by default. The page can pass the
   * `open` state of the parent so the panel mirrors the toggle.
   */
  defaultExpanded?: boolean;
  /**
   * Spread onto the outer container for `data-testid` etc.
   */
  contentProps?: React.HTMLAttributes<HTMLDivElement> & {
    'data-testid'?: string;
  };
}

/** Format an ISO timestamp as a short es-CO date+time. Best-effort: falls
 * back to the raw string if the value does not parse. The page wires
 * `i18n` if it needs locale-specific formatting; this helper stays
 * dependency-free so the panel renders even before i18n init. */
function formatEsCo(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number): string => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

export function VersionHistoryPanel({
  versions,
  displayLabel,
  defaultExpanded = true,
  contentProps,
}: VersionHistoryPanelProps): JSX.Element {
  const [expanded, setExpanded] = React.useState(defaultExpanded);

  if (versions.length === 0) {
    return (
      <Card data-testid={contentProps?.['data-testid']}>
        <CardContent className="py-4 text-sm text-muted-foreground">
          Sin versiones registradas.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-testid={contentProps?.['data-testid'] ?? 'version-history-panel'}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium"
        data-testid="version-history-toggle"
      >
        <span>
          Histórico ({versions.length} versión{versions.length === 1 ? '' : 'es'})
        </span>
        <span aria-hidden="true">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded && (
        <CardContent className="border-t p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="px-3 py-2">{displayLabel}</th>
                <th className="px-3 py-2">Vigente desde</th>
                <th className="px-3 py-2">Vigente hasta</th>
                <th className="px-3 py-2">Estado</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v, i) => {
                const isCurrent = v.vigente_hasta === null && v.estado === 'activo';
                return (
                  <tr
                    key={v.uuid}
                    data-testid={`version-history-row-${i}`}
                    className={cn('border-b last:border-b-0', isCurrent && 'bg-accent/40')}
                  >
                    <td className="px-3 py-2 font-mono text-sm">{v.display}</td>
                    <td className="px-3 py-2 text-xs">{formatEsCo(v.vigente_desde)}</td>
                    <td className="px-3 py-2 text-xs">
                      {v.vigente_hasta === null ? (
                        <span className="text-muted-foreground">abierta</span>
                      ) : (
                        formatEsCo(v.vigente_hasta)
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isCurrent ? (
                        <Badge variant="default" data-testid="version-history-current">
                          vigente
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground text-xs">
                          {v.estado}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      )}
    </Card>
  );
}
