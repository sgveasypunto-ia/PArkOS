/**
 * `<LineasTicket />` — on-screen "thermal paper" rendering of the SAME
 * channel-neutral lines (`FacturaLinea`) the printer receives (ESC/POS and
 * HTML are built from them too), so the preview can never drift from the
 * printed ticket: one model, three renderers.
 *
 * - White paper / black ink on purpose (not theme tokens): it simulates the
 *   physical receipt and must look the same in light and dark mode, exactly
 *   like the `TiqueteModal` preview.
 * - `marca` lines render `<MarcaTicketPantalla />` (black logo, header + footer).
 * - Rows are already wrapped to 48 columns by the line builders; `pre-wrap`
 *   keeps their spacing and `break-words` is only a safety net on narrow drawers.
 */
import type { JSX } from 'react';

import type { FacturaLinea } from '../lib/print/facturaPrint';
import { MarcaTicketPantalla } from './MarcaTicketPantalla';

export interface LineasTicketProps {
  lineas: FacturaLinea[];
  /** `data-testid` of the paper container. */
  testId: string;
  /** Accessible name of the preview (e.g. "Vista previa del tiquete reimpreso"). */
  etiqueta: string;
}

export function LineasTicket({ lineas, testId, etiqueta }: LineasTicketProps): JSX.Element {
  return (
    <div
      role="group"
      aria-label={etiqueta}
      data-testid={testId}
      className="mx-auto w-full max-w-sm rounded border border-dashed border-muted-foreground/40 bg-white p-3 font-mono text-xs leading-relaxed text-neutral-900 shadow-inner"
    >
      {lineas.map((linea, i) => {
        if (linea.tipo === 'marca') {
          return <MarcaTicketPantalla key={i} posicion={linea.posicion} />;
        }
        if (linea.tipo === 'sep') {
          return <hr key={i} className="my-1 border-0 border-t border-dashed border-neutral-400" />;
        }
        if (linea.tipo === 'fila') {
          return (
            <div
              key={i}
              className={`flex justify-between gap-2${linea.sangria ? ' pl-3' : ''}${linea.negrita ? ' font-bold' : ''}`}
            >
              <span className="whitespace-pre-wrap break-words">{linea.izq}</span>
              <span className="whitespace-nowrap">{linea.der}</span>
            </div>
          );
        }
        return (
          <p
            key={i}
            data-testid="linea-ticket"
            className={`m-0 whitespace-pre-wrap break-words${linea.centro ? ' text-center' : ''}${linea.negrita ? ' font-bold' : ''}`}
          >
            {linea.texto}
          </p>
        );
      })}
    </div>
  );
}
