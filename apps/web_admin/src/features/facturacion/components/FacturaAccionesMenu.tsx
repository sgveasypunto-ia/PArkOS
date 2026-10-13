/**
 * `<FacturaAccionesMenu />` — top-level action bar (REQ-X-08).
 *
 * Three actions, all role-gated to `admin-` (the server-side check is
 * the authority; the client-side hide is UX, not security).
 *
 * X.1b ships the SKELETON (no dialogs). X.3 wires the Reimprimir
 * dialog. X.4 wires Anular. X.5 will wire Reclamo.
 */
import { useState } from 'react';
import { Printer, XCircle, FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

import { AnularFacturaDialog } from './AnularFacturaDialog';
import { ReimprimirFacturaDialog } from './ReimprimirFacturaDialog';

export interface FacturaAccionesMenuProps {
  /** Factura uuid (sent to /facturacion/:uuid BE endpoint). */
  uuid: string;
  /** The uuid_ingreso linked to the factura (X.3 reimprimir requires it). */
  uuid_ingreso: string | null;
  /** The uuid_salida linked to the factura (X.4 anular uses it). */
  uuid_salida: string | null;
  /** Disable the "Anular" action when the factura is already voided. */
  estado: 'vigente' | 'anulada';
  onAnularSuccess?: (uuid_anulacion: string) => void;
  onReimprimirSuccess?: (uuid_reimpresion: string) => void;
}

export function FacturaAccionesMenu({
  uuid,
  uuid_ingreso,
  uuid_salida,
  estado,
  onAnularSuccess,
  onReimprimirSuccess,
}: FacturaAccionesMenuProps): JSX.Element | null {
  const { t } = useTranslation('facturacionAdmin');
  const [reimprimirOpen, setReimprimirOpen] = useState(false);
  const [anularOpen, setAnularOpen] = useState(false);
  // X.5 will add its own `useState` and dialog mount.

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
          onClick={() => setAnularOpen(true)}
          disabled={uuid_salida === null}
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
          onSuccess={onReimprimirSuccess}
        />
      ) : null}
      {uuid_salida !== null ? (
        <AnularFacturaDialog
          uuid_salida={uuid_salida}
          open={anularOpen}
          onOpenChange={setAnularOpen}
          onSuccess={onAnularSuccess}
        />
      ) : null}
    </div>
  );
}
