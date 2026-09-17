/**
 * `<SalidaPanel />` — F7.1+F7.2 dashboard section for vehicle-exit.
 *
 * Composes:
 *   - Plate input that reuses `useCotizacion(uuid_ingreso)` polling.
 *   - Cotización breakdown rendered as semantic `<dl>` per plan.md:1677.
 *   - `<PagoSheet />` trigger that opens the right-side drawer.
 *
 * REQ-OPS-138 (single-drawer): the panel does NOT maintain its own
 * drawer state — it calls `useDashboardDrawerStore.open('pago', anchorId)`
 * on demand. The PagoSheet subscribes to the same store and renders
 * exactly one drawer at a time.
 *
 * REQ-OPS-139 (lazy-mount): until the operator types a plate and the
 * server returns an active `uuid_ingreso`, `useCotizacion` key is
 * `null` and no `/cotizar` fetch is issued.
 */
import { useCallback, useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';

import { useCotizacion } from '../hooks/useCotizacion';
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

const placaSchema = z.object({
  placa: z.string().trim().min(5, 'placa_formato_invalido'),
});
type PlacaValues = z.infer<typeof placaSchema>;

export interface SalidaPanelProps {
  /**
   * The active ingreso UUID selected by the operator (Path 1 result
   * from `useIngresoActivo(placa)` on the parent). `null` keeps the
   * panel in idle mode (REQ-OPS-139).
   */
  uuid_ingreso: string | null;
  /**
   * Callback fired once the cotizacion is ready and the operator
   * confirms payment. PR-3 wires this to `POST /facturacion/factura`
   * + `POST /facturacion/factura-pagos`.
   */
  onPagoSubmit: (payload: {
    uuid_ingreso: string;
    medio_pago: 'efectivo' | 'datafono';
    monto_recibido_cop: number;
    nit_cliente: string;
    voucher?: string;
  }) => Promise<void>;
  /**
   * Optional plate pre-fill from the dashboard's PlacaInputHero. When
   * provided, the panel's placa form is pre-filled on mount so the
   * operator only has to press Enter to cotizar. We DO NOT auto-submit.
   */
  initialPlaca?: string | null;
}

export function SalidaPanel({
  uuid_ingreso,
  onPagoSubmit,
  initialPlaca = null,
}: SalidaPanelProps): JSX.Element {
  const { t } = useTranslation(['operacion', 'facturacion']);
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const open = useDashboardDrawerStore((s) => s.open);
  const pagoAnchorId = useId();

  const [placa, setPlaca] = useState<string | null>(null);

  const form = useForm<PlacaValues>({
    resolver: zodResolver(placaSchema),
    defaultValues: { placa: '' },
    mode: 'onSubmit',
  });

  // Pre-fill placa on mount so the operator only has to press Enter
  // to trigger the cotizacion flow. We do not auto-submit.
  useEffect(() => {
    if (!initialPlaca) return;
    form.setValue('placa', initialPlaca.toUpperCase().replace(/\s+/g, ''), {
      shouldValidate: false,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPlaca]);

  const { data: cotizacion, error: cotError } = useCotizacion(uuid_ingreso);

  const handlePlacaSubmit = form.handleSubmit((values) => {
    setPlaca(values.placa);
  });

  const handleOpenPago = useCallback(() => {
    open('pago', pagoAnchorId);
  }, [open, pagoAnchorId]);

  return (
    <div className="space-y-4" data-testid="salida-panel">
      <header className="space-y-1">
        <h3 className="text-lg font-semibold">
          {t('operacion:salida', { defaultValue: 'Salida' })}
        </h3>
        <p className="text-sm text-muted-foreground">
          {t('operacion:salidaSubtitulo', {
            defaultValue: 'Digita la placa para cotizar y cobrar.',
          })}
        </p>
      </header>

      <Form {...form}>
        <form onSubmit={handlePlacaSubmit} className="space-y-2">
          <FormField
            control={form.control}
            name="placa"
            render={({ field }) => (
              <FormItem>
                <label htmlFor="salida-placa" className="text-sm font-medium">
                  {t('operacion:placa', { defaultValue: 'Placa' })}
                </label>
                <FormControl>
                  <Input
                    id="salida-placa"
                    data-testid="salida-placa"
                    placeholder="ABC123"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" variant="outline" data-testid="salida-cotizar">
            {t('operacion:cotizar', { defaultValue: 'Cotizar' })}
          </Button>
        </form>
      </Form>

      {cotError && (
        <p role="alert" className="text-sm text-destructive">
          {t('operacion:error_network_error', { defaultValue: 'Sin conexión' })}
        </p>
      )}

      {cotizacion && uuid_ingreso && (
        <Card>
          <CardHeader>
            <CardTitle>
              {t('operacion:cotizar.titulo', { defaultValue: 'Cotización' })}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-y-1 text-sm" data-testid="cotizacion-dl">
              <dt>{t('operacion:cotizar.minutos', { defaultValue: 'Minutos' })}</dt>
              <dd>{cotizacion.minutos_transcurridos}</dd>
              <dt>{t('operacion:cotizar.base', { defaultValue: 'Base' })}</dt>
              <dd>${cotizacion.base_cop.toLocaleString('es-CO')}</dd>
              <dt>{t('operacion:cotizar.fraccion', { defaultValue: 'Fracción' })}</dt>
              <dd>${cotizacion.fraccion_cop.toLocaleString('es-CO')}</dd>
              <dt className="font-semibold">{t('operacion:cotizar.total', { defaultValue: 'Total' })}</dt>
              <dd className="font-semibold" data-testid="cotizacion-total">
                ${cotizacion.total_cop.toLocaleString('es-CO')}
              </dd>
            </dl>

            <div className="mt-4">
              <Button
                type="button"
                id={pagoAnchorId}
                data-anchor-for="pago"
                onClick={handleOpenPago}
                data-testid="salida-cobrar"
              >
                {t('facturacion:pago.titulo', { defaultValue: 'Cobrar' })}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {placa && !cotizacion && (
        <p className="text-sm text-muted-foreground" role="status">
          {t('operacion:cotizando', {
            defaultValue: 'Cotizando…',
          })}
        </p>
      )}

      {/* The drawer is mounted by <DrawerHost />; this panel just opens it. */}
      <input
        type="hidden"
        data-testid="salida-open-drawer-state"
        value={openDrawer === 'pago' ? 'open' : 'closed'}
      />
    </div>
  );
}