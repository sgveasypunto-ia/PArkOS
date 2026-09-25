/**
 * `<CierreDiarioDialog />` — F10.3 full-day cierre dialog.
 *
 * Opens via `useDashboardDrawerStore.open('cierre-diario', anchorId)`
 * (mounted as a `<Dialog>` rather than a `<Sheet>` because it requires
 * explicit confirmation and stays visible until the operator reviews
 * the resumen).
 *
 * Polls `useArqueoResumen` (REQ-OPS-132 fetcher-closure) for the
 * live resumen. On confirm, resolves the `'cierre_dia'` codigo to its
 * UUID via `useTipoArqueoPorCodigo` (F11.3) and posts
 * `uuid_tipo_arqueo` via `useArqueo().submit(...)`.
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
import { useTipoArqueoPorCodigo } from '../hooks/useTipoArqueoPorCodigo';

const cierreSchema = z.object({
  valor_efectivo_reportado: z.coerce.number().int().nonnegative(),
  valor_datafono_reportado: z.coerce.number().int().nonnegative(),
  justificacion: z.string().trim().optional(),
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
      valor_efectivo_reportado: 0,
      valor_datafono_reportado: 0,
      justificacion: '',
    },
    mode: 'onSubmit',
  });

  const fecha = todayISO();
  const { data: resumen } = useArqueoResumen(uuid_sucursal, open ? fecha : null);
  const { submit } = useArqueo();
  // F11.3: the BE arqueo POST requires `uuid_tipo_arqueo` (UUID), not
  // the legacy `tipo_arqueo` codigo string — resolve it via the catalog
  // SWR hook (mirrors `CerrarTurno.tsx` / `ArqueoParcial.tsx`, HU-F10.1).
  const { uuid: uuidTipoArqueo } = useTipoArqueoPorCodigo(open ? 'cierre_dia' : null);

  useEffect(() => {
    if (!open && lastAnchorId) {
      document.getElementById(lastAnchorId)?.focus();
    }
  }, [open, lastAnchorId]);

  const handleSubmit = form.handleSubmit(async (values) => {
    if (!uuid_sesion || !uuidTipoArqueo) return;
    await submit({
      uuid_sesion,
      uuid_tipo_arqueo: uuidTipoArqueo,
      valor_efectivo_reportado: values.valor_efectivo_reportado,
      valor_datafono_reportado: values.valor_datafono_reportado,
      justificacion: values.justificacion,
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
      <DialogContent
        // F31.3 rediseño: la primitiva ya cappea a `max-w-lg` (no se
        // estira en 3840/ultrawide) — acá solo se ajusta el padding
        // fijo `p-6` a fluido (`p-4 sm:p-6`, recupera ~16px útiles en
        // 320px) y se agrega scroll interno vertical por si el resumen
        // + 3 campos + footer exceden una ventana baja.
        className="max-h-[85vh] overflow-y-auto p-4 sm:p-6"
        data-testid="cierre-diario-dialog"
      >
        <DialogHeader>
          {/* F31.3 rediseño: bug preexistente — ambos llamaban a
              `t('cierreDiario', ...)`, la clave RAÍZ del namespace
              (un objeto anidado: `{ titulo, subtitulo, ... }`, ver
              caja.json:95-97), no un string. i18next devolvía el
              objeto y renderizaba el mensaje de error de la librería
              ("key 'cierreDiario (es-CO)' returned an object instead
              of string") en vez del título — visible en vivo al abrir
              el diálogo. Se apunta a las claves hoja correctas,
              mismas que ya usa `<CierreDiario />` (la página
              routeada) para el mismo texto. */}
          <DialogTitle>{t('cierreDiario.titulo', { defaultValue: 'Cierre diario' })}</DialogTitle>
          <DialogDescription>
            {t('cierreDiario.subtitulo', {
              defaultValue:
                'Cierre de todas las sesiones abiertas del día — supervisor / multi-sucursal.',
            })}
          </DialogDescription>
        </DialogHeader>

        {resumen && (
          <dl
            // Antes era un grid-cols-2 sin tokens (texto sin color
            // semántico, sin contenedor). Se alinea al mismo lenguaje
            // visual que el resumen de `<CerrarTurnoForm />` (tarjeta
            // sutil + dt en muted-foreground + dd tabular-nums) y se
            // mantiene en 2 columnas en todo el rango de breakpoints
            // — "Sesiones cerradas" (el label más largo) entra cómodo
            // incluso en 320px porque cada columna del grid tiene
            // ancho flexible (1fr), no un valor fijo.
            className="grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-xl border border-border/40 bg-muted/30 p-3 text-sm"
            data-testid="cierre-diario-resumen"
          >
            <dt className="text-muted-foreground">Sesiones cerradas</dt>
            <dd className="text-right font-mono font-semibold tabular-nums">
              {resumen.sesiones_cerradas}
            </dd>
            <dt className="text-muted-foreground">Total efectivo</dt>
            <dd className="text-right font-mono font-semibold tabular-nums">
              ${resumen.total_efectivo_cop.toLocaleString('es-CO')}
            </dd>
            <dt className="text-muted-foreground">Total datáfono</dt>
            <dd className="text-right font-mono font-semibold tabular-nums">
              ${resumen.total_datafono_cop.toLocaleString('es-CO')}
            </dd>
            <dt className="text-muted-foreground">Diferencia</dt>
            <dd
              className={
                'text-right font-mono font-semibold tabular-nums' +
                (resumen.diferencia_cop !== 0 ? ' text-destructive' : '')
              }
            >
              ${resumen.diferencia_cop.toLocaleString('es-CO')}
            </dd>
          </dl>
        )}

        <Form {...form}>
          <form id={formId} onSubmit={handleSubmit} className="space-y-4 py-4">
            <FormField
              control={form.control}
              name="valor_efectivo_reportado"
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
              name="valor_datafono_reportado"
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
              name="justificacion"
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Input
                      data-testid="cierre-justificacion"
                      placeholder="Justificación (requerida si hay diferencia)"
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
            disabled={!uuid_sesion || !uuidTipoArqueo || form.formState.isSubmitting}
            data-testid="cierre-confirmar"
          >
            Confirmar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}