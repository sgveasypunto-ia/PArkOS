/**
 * `<ArqueoSheet />` — F10.1 right-side drawer for partial arqueo.
 *
 * Opens via `useDashboardDrawerStore.open('arqueo', anchorId)`.
 * The form collects efectivo_contado + datafono_contado and posts
 * via `useArqueo().submit({ tipo_arqueo: 'auditoria' })`.
 */
import { useEffect, useId } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';

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
import { useArqueo } from '../hooks/useArqueo';

const arqueoSchema = z.object({
  efectivo_contado_cop: z.coerce.number().int().nonnegative(),
  datafono_contado_cop: z.coerce.number().int().nonnegative(),
  observaciones: z.string().trim().optional(),
});
type ArqueoValues = z.infer<typeof arqueoSchema>;

export interface ArqueoSheetProps {
  uuid_sesion: string | null;
}

export function ArqueoSheet({ uuid_sesion }: ArqueoSheetProps): JSX.Element {
  const { t } = useTranslation('caja');
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const open = openDrawer === 'arqueo';

  const formId = useId();
  const form = useForm<ArqueoValues>({
    resolver: zodResolver(arqueoSchema),
    defaultValues: {
      efectivo_contado_cop: 0,
      datafono_contado_cop: 0,
      observaciones: '',
    },
    mode: 'onSubmit',
  });

  const { submit } = useArqueo();

  useEffect(() => {
    if (!open && lastAnchorId) {
      document.getElementById(lastAnchorId)?.focus();
    }
  }, [open, lastAnchorId]);

  const handleSubmit = form.handleSubmit(async (values) => {
    if (!uuid_sesion) return;
    await submit({
      uuid_sesion,
      tipo_arqueo: 'auditoria',
      efectivo_contado_cop: values.efectivo_contado_cop,
      datafono_contado_cop: values.datafono_contado_cop,
      observaciones: values.observaciones,
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
      <SheetContent side="right" data-testid="arqueo-sheet">
        <SheetHeader>
          <SheetTitle>{t('arqueoParcial', { defaultValue: 'Arqueo parcial' })}</SheetTitle>
          <SheetDescription>{t('arqueo', { defaultValue: 'Arqueo' })}</SheetDescription>
        </SheetHeader>

        <Form {...form}>
          <form id={formId} onSubmit={handleSubmit} className="space-y-4 py-4">
            <FormField
              control={form.control}
              name="efectivo_contado_cop"
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Input
                      type="number"
                      data-testid="arqueo-efectivo"
                      placeholder="Efectivo contado"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="datafono_contado_cop"
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Input
                      type="number"
                      data-testid="arqueo-datafono"
                      placeholder="Datáfono contado"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="observaciones"
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Input
                      data-testid="arqueo-observaciones"
                      placeholder="Observaciones"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </form>
        </Form>

        <SheetFooter>
          <Button type="button" variant="outline" onClick={() => close()}>
            Cancelar
          </Button>
          <Button
            type="submit"
            form={formId}
            disabled={!uuid_sesion || form.formState.isSubmitting}
            data-testid="arqueo-confirmar"
          >
            Confirmar
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}