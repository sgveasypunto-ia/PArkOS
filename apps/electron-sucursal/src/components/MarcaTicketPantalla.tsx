/**
 * `<MarcaTicketPantalla />` — easypunto logo for the on-screen ticket previews, so
 * what the operator sees matches what the printer emits (header + smaller footer,
 * see `lib/print/marcaTicket.ts`).
 *
 * - Colour: previews are white "paper", so it uses the BLACK vector (`logoDataUri()`,
 *   the same asset the printed HTML uses; the recolouring is not duplicated here).
 *   Do not mount it on a themed (dark) background.
 * - Size: proportional to the printable width (72 mm): header 60 mm, footer 30 mm,
 *   expressed as percentages of the preview so it scales with it.
 * - A11y: the header is informative (`alt="easypunto"`: the brand is not in the
 *   preview title). The footer repeats it, so it is decorative (`alt=""`) and the
 *   name is not announced twice.
 * - If the image fails to load it is removed (no broken-image icon, no layout gap).
 */
import { useState, type JSX } from 'react';

import {
  ANCHO_LOGO_ENCABEZADO,
  ANCHO_LOGO_PIE,
  logoDataUri,
} from '../lib/print/marcaTicket';
import { TICKET_ANCHO_IMPRIMIBLE_MM } from '../lib/print/ticketBase';

export interface MarcaTicketPantallaProps {
  posicion: 'encabezado' | 'pie';
}

export function MarcaTicketPantalla({ posicion }: MarcaTicketPantallaProps): JSX.Element | null {
  const [fallo, setFallo] = useState(false);
  if (fallo) return null;
  const esPie = posicion === 'pie';
  const mm = (esPie ? ANCHO_LOGO_PIE : ANCHO_LOGO_ENCABEZADO) / 8;
  return (
    <p className={`flex justify-center ${esPie ? 'mt-2' : 'mb-2'}`} data-testid={`marca-ticket-${posicion}-fila`}>
      <img
        data-testid={`marca-ticket-${posicion}`}
        src={logoDataUri()}
        alt={esPie ? '' : 'easypunto'}
        style={{ width: `${(mm / TICKET_ANCHO_IMPRIMIBLE_MM) * 100}%`, height: 'auto' }}
        onError={() => setFallo(true)}
      />
    </p>
  );
}
