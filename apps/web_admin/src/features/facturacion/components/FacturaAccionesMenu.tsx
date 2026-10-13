/**
 * `<FacturaAccionesMenu />` — top-level action bar (REQ-X-08).
 *
 * Three actions, all role-gated to `admin-` (the server-side check is
 * the authority; the client-side hide is UX, not security).
 *
 * X.3 wires the Reimprimir dialog. X.4 wires Anular. X.5 wires Reclamo.
 */
import { useState } from 'react';
import { Printer, XCircle, FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

import { AnularFacturaDialog } from './AnularFacturaDialog';
import { ReclamoFacturaDialog } from './ReclamoFacturaDialog';
import { ReimprimirFacturaDialog } from './ReimprimirFacturaDialog';

export interface FacturaAccionesMenuProps {
  uuid: string;
  uuid_ingreso: string | null;
  uuid_salida: string | null;
  estado: 'vigente' | 'anulada';
  onAnularSuccess?: (uuid_anulacion: string) => void;
  onReimprimirSuccess?: (uuid_reimpresion: string) => void;
  onReclamoSuccess?: (uuid_reclamo: string) => void;
}

export function FacturaAccionesMenu({
  uuid,
  uuid_ingreso,
  uuid_salida,
  estado,
  onAnularSuccess,
  onReimprimirSuccess,
  onReclamoSuccess,
}: FacturaAccionesMenuProps): JSX.Element | null {
  const { t } = useTranslation('facturacionAdmin');
  const [reimprimirOpen, setReimprimirOpen] = useState(false);
  const [anularOpen, setAnularOpen] = useState(false);
  const [reclamoOpen, setReclamoOpen] = useState(false);

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
        onClick={() => setReclamoOpen(true)}
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
      <ReclamoFacturaDialog
        uuid_factura={uuid}
        open={reclamoOpen}
        onOpenChange={setReclamoOpen}
        onSuccess={onReclamoSuccess}
      />
    </div>
  );
}
