/**
 * `<CierreDiarioDialog />` — F10.3 full-day cierre dialog.
 *
 * Opens via `useDashboardDrawerStore.open('cierre-diario', anchorId)`
 * (mounted as a `<Dialog>` rather than a `<Sheet>` because it requires
 * explicit confirmation and stays visible until the operator reviews
 * the resumen).
 *
 * Polls `useArqueoResumen` (REQ-OPS-132 fetcher-closure) for the
 * live resumen. On confirm, posts `tipo_arqueo: 'cierre_dia'` via
 * `useArqueo().submit(...)`.
 */
import { useEffect, useId } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { useArqueo, useArqueoResumen } from '../hooks/useArqueo';

const cierreSchema = z.object({
  efectivo_contado_cop: z.coerce.number().int().nonnegative(),
  datafono_contado_cop: z.coerce.number().int().nonnegative(),
  observaciones: z.string().trim().optional(),
});
type CierreValues = z.infer<typeof cierreSchema>;

export interface CierreDiarioDialogProps {
  uuid_sucursal: string | null;
  uuid_sesion: string | null;
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export function CierreDiarioDialog({
  uuid_sucursal,
  uuid_sesion,
}: CierreDiarioDialogProps): JSX.Element {
  const { t } = useTranslation('caja');
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const open = openDrawer === 'cierre-diario';

  const formId = useId();
  const form = useForm<CierreValues>({
    resolver: zodResolver(cierreSchema),
    defaultValues: {
      efectivo_contado_cop: 0,
      datafono_contado_cop: 0,
      observaciones: '',
    },
    mode: 'onSubmit',
  });

  const fecha = todayISO();
  const { data: resumen } = useArqueoResumen(uuid_sucursal, open ? fecha : null);
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
      tipo_arqueo: 'cierre_dia',
      efectivo_contado_cop: values.efectivo_contado_cop,
      datafono_contado_cop: values.datafono_contado_cop,
      observaciones: values.observaciones,
    });
    close();
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <DialogContent data-testid="cierre-diario-dialog">
        <DialogHeader>
          <DialogTitle>{t('cierreDiario', { defaultValue: 'Cierre diario' })}</DialogTitle>
          <DialogDescription>{t('cierreDiario', { defaultValue: 'Cierre diario' })}</DialogDescription>
        </DialogHeader>

        {resumen && (
          <dl className="grid grid-cols-2 gap-y-1 text-sm" data-testid="cierre-diario-resumen">
            <dt>Sesiones cerradas</dt>
            <dd>{resumen.sesiones_cerradas}</dd>
            <dt>Total efectivo</dt>
            <dd>${resumen.total_efectivo_cop.toLocaleString('es-CO')}</dd>
            <dt>Total datáfono</dt>
            <dd>${resumen.total_datafono_cop.toLocaleString('es-CO')}</dd>
            <dt>Diferencia</dt>
            <dd>${resumen.diferencia_cop.toLocaleString('es-CO')}</dd>
          </dl>
        )}

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
                      data-testid="cierre-efectivo"
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
                      data-testid="cierre-datafono"
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
                      data-testid="cierre-observaciones"
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

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => close()}>
            Cancelar
          </Button>
          <Button
            type="submit"
            form={formId}
            disabled={!uuid_sesion || form.formState.isSubmitting}
            data-testid="cierre-confirmar"
          >
            Confirmar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}