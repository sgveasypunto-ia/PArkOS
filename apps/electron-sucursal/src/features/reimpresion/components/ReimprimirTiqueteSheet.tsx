/**
 * `<ReimprimirTiqueteSheet />` — F8.3 right-side drawer for reprint.
 *
 * Mounts via `useDashboardDrawerStore.open('reimpresion', anchorId)`.
 * Composes plate search (`useTicketsBuscar`) + motivo (≥10 chars
 * per plan.md:1983 — consequence of cobro) + reintentar submit.
 */
import { useEffect, useId } from 'react';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import {
  useTicketsBuscar,
  useReimpresion,
} from '../hooks/useTicketsBuscar';

const reimpresionSchema = z.object({
  placa: z.string().trim().min(5, 'placa_formato_invalido'),
  motivo: z.string().trim().min(10, 'motivo_minimo'),
});
type ReimpresionValues = z.infer<typeof reimpresionSchema>;

export function ReimprimirTiqueteSheet(): JSX.Element {
  const { t } = useTranslation(['reimpresion', 'facturacion']);
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const open = openDrawer === 'reimpresion';

  const formId = useId();
  const form = useForm<ReimpresionValues>({
    resolver: zodResolver(reimpresionSchema),
    defaultValues: { placa: '', motivo: '' },
    mode: 'onSubmit',
  });

  const placa = form.watch('placa');
  const { data: tickets } = useTicketsBuscar(placa || null);
  const { submit } = useReimpresion();

  useEffect(() => {
    if (!open && lastAnchorId) {
      const anchor = document.getElementById(lastAnchorId);
      anchor?.focus();
    }
  }, [open, lastAnchorId]);

  const handleSubmit = form.handleSubmit(async (values) => {
    const first = tickets?.[0];
    if (!first) return;
    await submit({
      placa: values.placa,
      uuid_ingreso: first.uuid_ingreso,
      motivo: values.motivo,
    });
    close();
  });

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      {/* F31.3 — mismo tope que PagoSheet: `sm:max-w-md` evita que el
          sheet (base `md:w-1/2`) se estire absurdamente en pantallas
          anchas (2560/3840/ultrawide) para un formulario de 2 campos. */}
      <SheetContent side="right" data-testid="reimprimir-sheet" className="overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>
            {t('facturacion:reimprimir.titulo', { defaultValue: 'Reimprimir tiquete' })}
          </SheetTitle>
          <SheetDescription>
            {t('facturacion:reimprimir.motivoLabel', {
              defaultValue: 'Motivo (mín. 10 caracteres)',
            })}
          </SheetDescription>
        </SheetHeader>

        <Form {...form}>
          <form id={formId} onSubmit={handleSubmit} className="space-y-4 py-4">
            <FormField
              control={form.control}
              name="placa"
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Input
                      data-testid="reimprimir-placa"
                      placeholder="ABC123"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="motivo"
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Input
                      data-testid="reimprimir-motivo"
                      placeholder={t('facturacion:reimprimir.motivoPlaceholder', {
                        defaultValue: 'Describe el motivo',
                      })}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {tickets && tickets.length > 0 && (
              <p className="text-sm text-muted-foreground" role="status">
                {tickets.length} tiquete(s) encontrado(s).
              </p>
            )}
          </form>
        </Form>

        <SheetFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => close()}
            data-testid="reimprimir-cancelar"
          >
            Cancelar
          </Button>
          <Button
            type="submit"
            form={formId}
            disabled={!tickets || tickets.length === 0 || form.formState.isSubmitting}
            data-testid="reimprimir-confirmar"
          >
            {t('facturacion:reimprimir.confirmar', { defaultValue: 'Reimprimir' })}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}