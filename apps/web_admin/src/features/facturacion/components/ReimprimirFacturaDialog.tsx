/**
 * `<ReimprimirFacturaDialog />` — REQ-OPS-200 admin action dialog.
 *
 * The admin enters a motivo (>= 10 chars) and submits; the hook
 * (`useReimprimirFactura`) POSTs the reimpresion. On success, the
 * dialog closes and `onSuccess` is called with the new uuid so the
 * page can decide to show a toast / link to the bitácora.
 *
 * Errors surface inline: 409 `reimpresion_already_pending` and
 * 409 `ingreso_ya_tiene_salida` are pre-checked by the BE; we show
 * the message verbatim.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import { useReimprimirFactura } from '../hooks/useReimprimirFactura';

const formSchema = z.object({
  motivo: z
    .string()
    .min(10, 'Mínimo 10 caracteres')
    .max(500, 'Máximo 500 caracteres'),
});
type FormValues = z.infer<typeof formSchema>;

export interface ReimprimirFacturaDialogProps {
  uuid_factura: string;
  uuid_ingreso: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (uuid_reimpresion: string) => void;
}

export function ReimprimirFacturaDialog({
  uuid_factura,
  uuid_ingreso,
  open,
  onOpenChange,
  onSuccess,
}: ReimprimirFacturaDialogProps): JSX.Element {
  const { t } = useTranslation('facturacionAdmin');
  const { trigger, isMutating } = useReimprimirFactura();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { motivo: '' },
  });

  const onSubmit = async (values: FormValues): Promise<void> => {
    setError(null);
    try {
      const result = await trigger({
        uuid_ingreso,
        uuid_factura,
        motivo: values.motivo,
      });
      onSuccess?.(result.uuid);
      form.reset();
      onOpenChange(false);
    } catch (err) {
      const e = err as Error & { status?: number; body?: string };
      setError(
        e.body && e.body.length < 200
          ? e.body
          : e.message || t('errors.actionFail', 'No se pudo completar la acción.'),
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('dialogs.reimprimirTitle', 'Reimprimir factura')}
          </DialogTitle>
          <DialogDescription>
            {t(
              'dialogs.reimprimirDescription',
              'Crea una nueva reimpresión del tiquete. El operador debe aprobarla en la sucursal antes de imprimirla.',
            )}
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="space-y-4"
          data-testid="reimprimir-factura-dialog"
        >
          <div className="space-y-2">
            <Label htmlFor="reimprimir-motivo">
              {t('dialogs.motivoLabel', 'Motivo')}
            </Label>
            <Input
              id="reimprimir-motivo"
              data-testid="reimprimir-motivo"
              placeholder={t(
                'dialogs.motivoPlaceholder',
                'Explicá el motivo (mínimo 10 caracteres)',
              )}
              {...form.register('motivo')}
            />
            {form.formState.errors.motivo ? (
              <p
                role="alert"
                className="text-sm text-destructive"
                data-testid="reimprimir-motivo-error"
              >
                {form.formState.errors.motivo.message}
              </p>
            ) : null}
          </div>
          {error ? (
            <p
              role="alert"
              className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              data-testid="reimprimir-error"
            >
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={isMutating}
              data-testid="reimprimir-cancelar"
            >
              {t('dialogs.cancelar', 'Cancelar')}
            </Button>
            <Button
              type="submit"
              disabled={isMutating}
              data-testid="reimprimir-confirmar"
            >
              {isMutating
                ? t('dialogs.submitting', 'Enviando…')
                : t('dialogs.confirmar', 'Confirmar')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
