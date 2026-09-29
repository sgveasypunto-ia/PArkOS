/**
 * `NuevaVersionDialog` — dialog react-hook-form + Zod para crear
 * una nueva versión bi-temporal (POST) o cerrar+insert (PUT) sobre
 * una fila vigente. El botón dice "Nueva versión", nunca "Editar",
 * porque la API nunca hace UPDATE físico: la "edición" cierra la
 * fila vigente e inserta una nueva.
 *
 * Reutiliza los primitives `Dialog`, `Button`, `Input`, `Label`,
 * `Form` (shadcn). El formulario se renderiza desde la lista de
 * campos del `config.fields` — el componente no conoce ningún
 * catálogo específico.
 */
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
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

import type { CatalogField } from '../lib/configTypes';

interface NuevaVersionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  fields: CatalogField[];
  defaults: Record<string, unknown>;
  onSubmit: (values: Record<string, unknown>) => Promise<void>;
  isSubmitting: boolean;
}

export function NuevaVersionDialog({
  open,
  onOpenChange,
  title,
  description,
  fields,
  defaults,
  onSubmit,
  isSubmitting,
}: NuevaVersionDialogProps): JSX.Element {
  const { t } = useTranslation();

  const schema = z.object(
    Object.fromEntries(
      fields.map((f) => [
        f.name,
        f.required
          ? z.string().min(1, t('catalogos.required', 'Requerido'))
          : z.string().optional(),
      ]),
    ),
  );

  type FormValues = z.infer<typeof schema>;

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaults as FormValues,
    mode: 'onBlur',
  });

  useEffect(() => {
    if (open) form.reset(defaults as FormValues);
  }, [open, defaults, form]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="nueva-version-dialog">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <form
          onSubmit={form.handleSubmit(async (values) => {
            await onSubmit(values as Record<string, unknown>);
          })}
          className="grid gap-4"
          data-testid="nueva-version-form"
        >
          {fields.map((field) => {
            const error = form.formState.errors[field.name];
            return (
              <div key={field.name} className="grid gap-2">
                <Label htmlFor={`field-${field.name}`}>
                  {field.label}
                  {field.required && (
                    <span className="text-destructive" aria-hidden="true">
                      {' '}*
                    </span>
                  )}
                </Label>
                <Input
                  id={`field-${field.name}`}
                  type={field.type ?? 'text'}
                  {...form.register(field.name)}
                  data-testid={`field-${field.name}`}
                  aria-invalid={error ? 'true' : 'false'}
                  aria-describedby={
                    error ? `field-${field.name}-error` : undefined
                  }
                />
                {error && (
                  <p
                    id={`field-${field.name}-error`}
                    role="alert"
                    className="text-destructive text-xs"
                  >
                    {error.message as string}
                  </p>
                )}
              </div>
            );
          })}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              {t('common.cancel', 'Cancelar')}
            </Button>
            <Button type="submit" disabled={isSubmitting} data-testid="submit-nueva-version">
              {isSubmitting
                ? t('common.saving', 'Guardando...')
                : t('catalogos.submit', 'Nueva versión')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
