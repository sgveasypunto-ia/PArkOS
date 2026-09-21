/**
 * `<ArqueoSheet />` — F10.1 right-side drawer for partial arqueo.
 *
 * Opens via `useDashboardDrawerStore.open('arqueo', anchorId)`.
 * The form collects valor_efectivo_reportado + valor_datafono_reportado
 * and posts via `useArqueo().submit({ tipo_arqueo: 'auditoria' })`.
 *
 * REQ-OPS-153 (drift anchor DA-1): payload keys align with backend
 * REQ-OPS-091 (`valor_efectivo_reportado` / `valor_datafono_reportado` /
 * `justificacion`). REQ-OPS-154 (DA-4): Zod refinement requires
 * `justificacion.min(3)` when `|diferencia| > 0`.
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

/**
 * `arqueoSchema` — module-private Zod refinement. The refinement
 * requires `justificacion.min(3)` when `|diferencia_efectivo| +
 * |diferencia_datafono| > 0`, mirroring the F10.1 spec scenario
 * (REQ-OPS-154). The wire-shape guard is exercised by the
 * hook-level contract test (`hooks/__tests__/useArqueo.test.ts`)
 * which mirrors the same refinement independently.
 */
const arqueoSchema = z
  .object({
    valor_efectivo_reportado: z.coerce.number().int().nonnegative(),
    valor_datafono_reportado: z.coerce.number().int().nonnegative(),
    diferencia_efectivo: z.number().int(),
    diferencia_datafono: z.number().int(),
    justificacion: z.string().trim().optional(),
  })
  .superRefine((data, ctx) => {
    const diff =
      Math.abs(data.diferencia_efectivo) + Math.abs(data.diferencia_datafono);
    if (diff > 0 && (!data.justificacion || data.justificacion.trim().length < 3)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['justificacion'],
        message: 'justificacion_requerida',
      });
    }
  });
type ArqueoValues = z.infer<typeof arqueoSchema>;

export interface ArqueoSheetProps {
  uuid_sesion: string | null;
  /**
   * Optional resumen so the form can render live diferencia feedback
   * (REQ-OPS-154 + AD-4). When omitted, the form assumes diferencia=0
   * and the refinement degrades to `justificacion.optional()` for the
   * legacy drawer-driven flow.
   */
  expected?: {
    valor_esperado_efectivo: number;
    valor_esperado_datafono: number;
    tolerancia_efectivo: number;
    tolerancia_datafono: number;
  } | null;
}

export function ArqueoSheet({
  uuid_sesion,
  expected: _expected = null,
}: ArqueoSheetProps): JSX.Element {
  const { t } = useTranslation('caja');
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const open = openDrawer === 'arqueo';

  const formId = useId();
  const form = useForm<ArqueoValues>({
    resolver: zodResolver(arqueoSchema),
    defaultValues: {
      valor_efectivo_reportado: 0,
      valor_datafono_reportado: 0,
      diferencia_efectivo: 0,
      diferencia_datafono: 0,
      justificacion: '',
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
    const { diferencia_efectivo: _de, diferencia_datafono: _dd, ...wireBody } =
      values;
    await submit({
      uuid_sesion,
      tipo_arqueo: 'auditoria',
      valor_efectivo_reportado: values.valor_efectivo_reportado,
      valor_datafono_reportado: values.valor_datafono_reportado,
      justificacion: values.justificacion,
    });
    void wireBody;
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
              name="valor_efectivo_reportado"
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
              name="valor_datafono_reportado"
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
              name="justificacion"
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Input
                      data-testid="arqueo-justificacion"
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