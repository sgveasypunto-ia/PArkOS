/**
 * `ForzarIngresoModal.tsx` — modal for forced-ingress with motivo
 * (HU-F6.1, CU-01, A-04 + KD-FORZADO-01, T6).
 *
 * Spec scenarios:
 *   - `cupo agotado → modal demands motivo with ≥10 chars`.
 *   - `motivo <10 chars → submit blocked inline, POST must NOT fire`.
 *
 * The retry POST sets `observaciones: '[FORZADO: ' + motivo + ']'` and
 * `forzado: true`. The prefix is the project's KD-FORZADO-01 convention
 * — backends and audit reports grep for `[FORZADO:` to flag forced
 * operations.
 *
 * Why `motivoSchema = z.string().min(10)`: per the design's force-flow
 * rationale (A-04), a motivo shorter than 10 chars is operationally
 * indistinguishable from a typo. The threshold is conservative on
 * purpose — the operator must justify the override.
 *
 * i18n keys added in T9:
 *   - `ingreso_forzar_title`   — modal title
 *   - `ingreso_motivo_label`   — motivo field label
 *   - `ingreso_forzar_confirmar` — confirm button
 *   - `ingreso_forzar_cancelar` — cancel button
 *   - `ingreso_motivo_minimo`  — inline error ("mínimo 10 caracteres")
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
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
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';

const motivoSchema = z.object({
  motivo: z
    .string()
    .trim()
    .min(10, 'ingreso_motivo_minimo'),
});

export type MotivoFormValues = z.infer<typeof motivoSchema>;

export interface ForzarIngresoModalProps {
  open: boolean;
  /** Already-typed placa — passed back in the retry payload for context. */
  placa: string;
  /** Fired with the formatted payload after Zod passes. */
  onConfirm: (payload: {
    placa: string;
    motivo: string;
    /** Already prepended with `[FORZADO: ` prefix per KD-FORZADO-01. */
    observaciones: string;
  }) => void;
  onCancel: () => void;
}

export function ForzarIngresoModal({
  open,
  placa,
  onConfirm,
  onCancel,
}: ForzarIngresoModalProps) {
  const { t } = useTranslation('operacion');
  const form = useForm<MotivoFormValues>({
    resolver: zodResolver(motivoSchema),
    defaultValues: { motivo: '' },
    mode: 'onChange',
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onCancel();
      }}
    >
      <DialogContent role="dialog" aria-describedby="forzar-descripcion">
        <DialogHeader>
          <DialogTitle>
            {t('ingreso_forzar_title', {
              defaultValue: 'Forzar ingreso',
            })}
          </DialogTitle>
          <DialogDescription id="forzar-descripcion">
            {t('ingreso_forzar_descripcion', {
              defaultValue:
                'El cupo está agotado. Ingresa un motivo de al menos 10 caracteres para continuar.',
            })}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((values) => {
              const trimmed = values.motivo.trim();
              const observaciones = `[FORZADO: ${trimmed}]`;
              onConfirm({ placa, motivo: trimmed, observaciones });
            })}
            className="space-y-4"
          >
            <FormField
              control={form.control}
              name="motivo"
              render={({ field }) => (
                <FormItem>
                  <FormLabel htmlFor="motivo">
                    {t('ingreso_motivo_label', {
                      defaultValue: 'Motivo',
                    })}
                  </FormLabel>
                  <FormControl>
                    <Input
                      id="motivo"
                      {...field}
                      placeholder={t('ingreso_motivo_placeholder', {
                        defaultValue: 'Describe el motivo (mín. 10 caracteres)',
                      })}
                      autoFocus
                      aria-describedby="motivo-help"
                    />
                  </FormControl>
                  <FormDescription id="motivo-help">
                    {t('ingreso_motivo_minimo', {
                      defaultValue: 'Mínimo 10 caracteres.',
                    })}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={onCancel}
              >
                {t('ingreso_forzar_cancelar', { defaultValue: 'Cancelar' })}
              </Button>
              <Button
                type="submit"
                disabled={!form.formState.isValid}
              >
                {t('ingreso_forzar_confirmar', { defaultValue: 'Confirmar' })}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
