/**
 * `<PagoSheet />` — F8.1 right-side drawer for the payment flow
 * (REQ-OPS-138 single-drawer invariant + REQ-OPS-139 lazy-mount).
 *
 * Composes:
 *   - `<Sheet>` (shadcn Drawer primitive) — opens via
 *     `useDashboardDrawerStore.open('pago', anchorId)`.
 *   - Form fields: medio de pago (efectivo | datáfono), NIT, voucher.
 *   - FE always defaults to consumidor final (NIT `222222222222222`).
 *   - Idempotency-Key header (parkosFetch handles this for POSTs).
 *
 * The component receives `uuid_ingreso` from the store context
 * (`drawerContext.uuid_ingreso`) and posts `POST /facturacion/factura`
 * + `POST /facturacion/factura-pagos`. On success, the sheet closes
 * and `useFacturaElectronica` (PR-4) takes over for FE status polling.
 */
import { useEffect, useId } from 'react';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Input } from '@/components/ui/input';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

/**
 * FE always defaults to consumidor final per plan.md:1828-1922
 * (NIT `222222222222222`).
 */
const NIT_CONSUMIDOR_FINAL = '222222222222222';

const pagoSchema = z.object({
  medio_pago: z.enum(['efectivo', 'datafono']),
  monto_recibido_cop: z.coerce.number().int().positive(),
  nit_cliente: z
    .string()
    .trim()
    .default(NIT_CONSUMIDOR_FINAL),
  voucher: z.string().trim().optional(),
});
export type PagoFormValues = z.infer<typeof pagoSchema>;

export interface PagoSheetProps {
  /**
   * UUID del ingreso activo que se está pagando. The store consumer
   * threads this through the `drawerContext` payload; the sheet reads
   * it from props because the form needs it for the POST body.
   */
  uuid_ingreso: string | null;
  total_cop: number;
  /**
   * Called when the operator submits the payment form. The parent
   * (`<SalidaPanel />`) wires this to the actual `POST /facturacion/*`.
   */
  onSubmit: (values: PagoFormValues) => Promise<void>;
}

export function PagoSheet({
  uuid_ingreso,
  total_cop,
  onSubmit,
}: PagoSheetProps): JSX.Element {
  const { t } = useTranslation(['facturacion', 'common']);
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);

  const open = openDrawer === 'pago';
  const formId = useId();

  const form = useForm<PagoFormValues>({
    resolver: zodResolver(pagoSchema),
    defaultValues: {
      medio_pago: 'efectivo',
      monto_recibido_cop: total_cop,
      nit_cliente: NIT_CONSUMIDOR_FINAL,
      voucher: '',
    },
    mode: 'onSubmit',
  });

  // Reset defaults when total changes (e.g. operator re-cotiza).
  useEffect(() => {
    form.reset({
      medio_pago: 'efectivo',
      monto_recibido_cop: total_cop,
      nit_cliente: NIT_CONSUMIDOR_FINAL,
      voucher: '',
    });
  }, [total_cop, form]);

  // Focus restore per REQ-OPS-138 §Esc.
  useEffect(() => {
    if (!open && lastAnchorId) {
      const anchor = document.getElementById(lastAnchorId);
      anchor?.focus();
    }
  }, [open, lastAnchorId]);

  const handleSubmit = form.handleSubmit(async (values) => {
    if (!uuid_ingreso) return;
    await onSubmit(values);
    close();
  });

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <SheetContent side="right" data-testid="pago-sheet">
        <SheetHeader>
          <SheetTitle>{t('facturacion:pago.titulo', { defaultValue: 'Cobrar' })}</SheetTitle>
          <SheetDescription>
            {t('facturacion:pago.descripcion', {
              defaultValue: 'Registra el pago y emite la factura.',
            })}
          </SheetDescription>
        </SheetHeader>

        <Form {...form}>
          <form id={formId} onSubmit={handleSubmit} className="space-y-4 py-4">
            <FormField
              control={form.control}
              name="medio_pago"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('facturacion:pago.medioPago', { defaultValue: 'Medio de pago' })}</FormLabel>
                  <FormControl>
                    <select
                      data-testid="pago-medio-pago"
                      className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                      value={field.value}
                      onChange={field.onChange}
                      onBlur={field.onBlur}
                    >
                      <option value="efectivo">Efectivo</option>
                      <option value="datafono">Datáfono</option>
                    </select>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="monto_recibido_cop"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('facturacion:pago.montoRecibido', { defaultValue: 'Monto recibido' })}</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      inputMode="numeric"
                      data-testid="pago-monto-recibido"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="nit_cliente"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('facturacion:pago.nit', { defaultValue: 'NIT del cliente' })}</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="pago-nit"
                      placeholder={NIT_CONSUMIDOR_FINAL}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="voucher"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('facturacion:pago.voucher', { defaultValue: 'Voucher (datáfono)' })}</FormLabel>
                  <FormControl>
                    <Input data-testid="pago-voucher" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </form>
        </Form>

        <SheetFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => close()}
            data-testid="pago-cancelar"
          >
            {t('common:cancel', { defaultValue: 'Cancelar' })}
          </Button>
          <Button
            type="submit"
            form={formId}
            disabled={!uuid_ingreso || form.formState.isSubmitting}
            data-testid="pago-confirmar"
          >
            {t('facturacion:pago.confirmar', { defaultValue: 'Confirmar pago' })}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}