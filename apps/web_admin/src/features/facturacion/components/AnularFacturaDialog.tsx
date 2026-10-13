/**
 * `<AnularFacturaDialog />` — REQ-OPS-201 admin action dialog.
 *
 * The admin enters a motivo (>= 10 chars to match the reimprimir
 * pattern and the bitácora's audit-trail readability) and submits;
 * the hook (`useAnularFactura`) POSTs the anulacion. On success, the
 * dialog closes and `onSuccess` is called with the new uuid_anulacion
 * so the page can navigate to the workflow detail
 * (`/anulaciones/{uuid}` — handled by the existing app route).
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

import { useAnularFactura } from '../hooks/useAnularFactura';

const formSchema = z.object({
  motivo: z
    .string()
    .min(10, 'Mínimo 10 caracteres')
    .max(500, 'Máximo 500 caracteres'),
});
type FormValues = z.infer<typeof formSchema>;

export interface AnularFacturaDialogProps {
  uuid_salida: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (uuid_anulacion: string) => void;
}

export function AnularFacturaDialog({
  uuid_salida,
  open,
  onOpenChange,
  onSuccess,
}: AnularFacturaDialogProps): JSX.Element {
  const { t } = useTranslation('facturacionAdmin');
  const { trigger, isMutating } = useAnularFactura();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { motivo: '' },
  });

  const onSubmit = async (values: FormValues): Promise<void> => {
    setError(null);
    try {
      const result = await trigger({
        uuid_salida,
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
            {t('dialogs.anularTitle', 'Anular factura')}
          </DialogTitle>
          <DialogDescription>
            {t(
              'dialogs.anularDescription',
              'Esta acción es irreversible. Crea una fila en prod.anulaciones que el operador debe aprobar y ejecutar.',
            )}
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="space-y-4"
          data-testid="anular-factura-dialog"
        >
          <div className="space-y-2">
            <Label htmlFor="anular-motivo">
              {t('dialogs.motivoLabel', 'Motivo')}
            </Label>
            <Input
              id="anular-motivo"
              data-testid="anular-motivo"
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
                data-testid="anular-motivo-error"
              >
                {form.formState.errors.motivo.message}
              </p>
            ) : null}
          </div>
          {error ? (
            <p
              role="alert"
              className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              data-testid="anular-error"
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
              data-testid="anular-cancelar"
            >
              {t('dialogs.cancelar', 'Cancelar')}
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={isMutating}
              data-testid="anular-confirmar"
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
