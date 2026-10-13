/**
 * `<FacturaClienteCard />` — presentational client card (REQ-X-03).
 *
 * MVP decision: this card shows "Consumidor final" by default because
 * the BE drill-down endpoint `GET /api/v1/facturacion/facturas/{uuid}`
 * returns the raw `prod.facturas` row without a JOIN to `prod.clientes`.
 * Building a dedicated `GET /admin/facturacion/facturas/{uuid}/display`
 * endpoint that returns the enriched F8.4 shape (with `cliente`,
 * `datos_sucursal`, `datos_vehiculo`) is a follow-up.
 *
 * The `cliente` prop is OPTIONAL — when a future enhancement supplies
 * the real cliente, the card switches to a labeled card automatically.
 */
import { useTranslation } from 'react-i18next';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

export interface FacturaClienteCardProps {
  /** Optional enriched cliente; null = consumidor final. */
  cliente?: {
    tipo_identificador: string;
    numero_identificacion: string;
    nombre: string;
    apellido?: string | null;
  } | null;
}

export function FacturaClienteCard({ cliente }: FacturaClienteCardProps): JSX.Element {
  const { t } = useTranslation('facturacionAdmin');
  return (
    <Card data-testid="factura-cliente-card">
      <CardHeader>
        <CardTitle className="text-base">{t('cliente.title', 'Cliente')}</CardTitle>
        <CardDescription>
          {cliente
            ? `${cliente.tipo_identificador} ${cliente.numero_identificacion} — ${cliente.nombre}${cliente.apellido ? ' ' + cliente.apellido : ''}`
            : t('cliente.consumidorFinal', 'Consumidor final')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p
          className="text-sm text-muted-foreground"
          data-testid="factura-cliente-empty"
        >
          {cliente
            ? t('cliente.consumidorFinal', 'Consumidor final')
            : t(
                'cliente.consumidorFinal',
                'Consumidor final',
              )}
        </p>
      </CardContent>
    </Card>
  );
}
