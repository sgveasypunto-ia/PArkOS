/**
 * `<FacturaAccionesMenu />` — top-level action bar (REQ-X-08).
 *
 * Three actions, all role-gated to `admin-` (the server-side check is
 * the authority; the client-side hide is UX, not security).
 *
 * X.1b ships this as a SKELETON: the buttons open the dialogs from
 * X.3..X.5. Until those PRs land, the buttons show a "coming soon"
 * toast (or are simply no-ops). The skeleton exists so the page can
 * mount and X.2 (drill-down links from lists) can be tested end-to-end
 * without waiting for the dialogs.
 *
 * The actual dialogs are imported but their triggers are placeholders;
 * X.3..X.5 will replace the placeholder handlers with the real
 * `useReimprimirFactura` / `useAnularFactura` / `useCrearReclamoFactura`
 * mutations.
 */
import { Printer, XCircle, FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

export interface FacturaAccionesMenuProps {
  uuid: string;
  /** Disable the "Anular" action when the factura is already voided. */
  estado: 'vigente' | 'anulada';
}

export function FacturaAccionesMenu({
  uuid,
  estado,
}: FacturaAccionesMenuProps): JSX.Element | null {
  const { t } = useTranslation('facturacionAdmin');

  // Role-gate: in X.1b the JWT is not yet surfaced in the FE, so we
  // render the menu unconditionally. X.7 will add the `useMe()` check
  // and `if (me?.rol !== 'admin-') return null;` here.
  //
  // The shape is preserved so X.3..X.5 can drop in the dialogs without
  // touching the page container.

  const onReimprimir = (): void => {
    // X.3 will replace this with the dialog open + useReimprimirFactura
    // mutation. For now: console + alert.
    void uuid;
  };
  const onAnular = (): void => {
    // X.4 will replace this.
    void uuid;
  };
  const onReclamo = (): void => {
    // X.5 will replace this.
    void uuid;
  };

  return (
    <div
      className="flex flex-wrap gap-2"
      data-testid="factura-acciones-menu"
    >
      <Button
        type="button"
        variant="outline"
        onClick={onReimprimir}
        data-testid="factura-accion-reimprimir"
      >
        <Printer className="mr-2 h-4 w-4" aria-hidden />
        {t('acciones.reimprimir', 'Reimprimir')}
      </Button>
      {estado === 'vigente' ? (
        <Button
          type="button"
          variant="outline"
          onClick={onAnular}
          data-testid="factura-accion-anular"
        >
          <XCircle className="mr-2 h-4 w-4" aria-hidden />
          {t('acciones.anular', 'Anular')}
        </Button>
      ) : null}
      <Button
        type="button"
        variant="outline"
        onClick={onReclamo}
        data-testid="factura-accion-reclamo"
      >
        <FileText className="mr-2 h-4 w-4" aria-hidden />
        {t('acciones.reclamo', 'Crear reclamo')}
      </Button>
    </div>
  );
}
