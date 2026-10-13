/**
 * `<FacturaAccionesMenu />` — top-level action bar (REQ-X-08).
 *
 * Three actions, all role-gated to `admin-` (the server-side check is
 * the authority; the client-side hide is UX, not security).
 *
 * X.1b ships the SKELETON (no dialogs). X.3 wires the Reimprimir
 * dialog. X.4..X.5 will wire Anular and Reclamo.
 *
 * The shape is preserved so X.4..X.5 can drop in the dialogs without
 * touching the page container.
 */
import { useState } from 'react';
import { Printer, XCircle, FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

import { ReimprimirFacturaDialog } from './ReimprimirFacturaDialog';

export interface FacturaAccionesMenuProps {
  /** Factura uuid (sent to /facturacion/:uuid BE endpoint). */
  uuid: string;
  /** The uuid_ingreso linked to the factura (X.3 reimprimir requires it). */
  uuid_ingreso: string | null;
  /** Disable the "Anular" action when the factura is already voided. */
  estado: 'vigente' | 'anulada';
}

export function FacturaAccionesMenu({
  uuid,
  uuid_ingreso,
  estado,
}: FacturaAccionesMenuProps): JSX.Element | null {
  const { t } = useTranslation('facturacionAdmin');
  const [reimprimirOpen, setReimprimirOpen] = useState(false);
  // X.4 / X.5 will add their own `useState` and dialog mounts.

  // Role-gate: in X.3 the JWT is not yet surfaced in the FE, so we
  // render the menu unconditionally. X.7 will add the `useMe()` check
  // and `if (me?.rol !== 'admin-') return null;` here.

  return (
    <div
      className="flex flex-wrap gap-2"
      data-testid="factura-acciones-menu"
    >
      <Button
        type="button"
        variant="outline"
        onClick={() => setReimprimirOpen(true)}
        disabled={uuid_ingreso === null}
        data-testid="factura-accion-reimprimir"
      >
        <Printer className="mr-2 h-4 w-4" aria-hidden />
        {t('acciones.reimprimir', 'Reimprimir')}
      </Button>
      {estado === 'vigente' ? (
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            // X.4 will replace this with the Anular dialog open.
            void uuid;
          }}
          data-testid="factura-accion-anular"
        >
          <XCircle className="mr-2 h-4 w-4" aria-hidden />
          {t('acciones.anular', 'Anular')}
        </Button>
      ) : null}
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          // X.5 will replace this with the Reclamo dialog open.
          void uuid;
        }}
        data-testid="factura-accion-reclamo"
      >
        <FileText className="mr-2 h-4 w-4" aria-hidden />
        {t('acciones.reclamo', 'Crear reclamo')}
      </Button>
      {uuid_ingreso !== null ? (
        <ReimprimirFacturaDialog
          uuid_factura={uuid}
          uuid_ingreso={uuid_ingreso}
          open={reimprimirOpen}
          onOpenChange={setReimprimirOpen}
        />
      ) : null}
    </div>
  );
}
