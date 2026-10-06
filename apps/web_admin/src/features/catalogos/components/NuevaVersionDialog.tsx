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
import { useForm, type UseFormRegisterReturn } from 'react-hook-form';
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

import { useCatalogList } from '../hooks/useCatalogList';
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

/**
 * `select` field: options are the vigente rows of `field.optionsResource`
 * (cached by SWR through `useCatalogList`); the empty option maps to "no value".
 */
function CatalogSelect({
  field,
  register,
  invalid,
  currentValue,
}: {
  field: CatalogField;
  register: UseFormRegisterReturn;
  invalid: boolean;
  /** Value stored on the row being edited (may point at a no-longer-vigente version). */
  currentValue: string;
}): JSX.Element {
  const { rows } = useCatalogList(field.optionsResource ?? 'tipos-vehiculo');
  const labelKey = field.optionsLabelKey ?? 'tipo';
  const vigentes = rows.filter((r) => r.vigente_hasta === null && r.estado === 'activo');
  // A row can reference an older version of the option (references keep the
  // uuid they had when saved): keep it selectable instead of silently
  // resetting the field to "no value".
  const stale =
    currentValue !== '' && !vigentes.some((r) => r.uuid === currentValue)
      ? (rows.find((r) => r.uuid === currentValue) ?? null)
      : null;
  const options = stale ? [...vigentes, stale] : vigentes;
  return (
    <select
      id={`field-${field.name}`}
      {...register}
      data-testid={`field-${field.name}`}
      aria-invalid={invalid ? 'true' : 'false'}
      aria-describedby={field.hint ? `field-${field.name}-hint` : undefined}
      className="border-input bg-transparent flex h-9 w-full rounded-md border px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      <option value="">{field.emptyOptionLabel ?? ''}</option>
      {options.map((r) => (
        <option key={r.uuid} value={r.uuid}>
          {String(r[labelKey] ?? r.uuid)}
        </option>
      ))}
    </select>
  );
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
        f.type === 'checkbox'
          ? z.boolean().optional()
          : f.type === 'number'
            ? f.required
              ? z.coerce.number({ invalid_type_error: t('catalogos.required', 'Requerido') })
              : z.coerce.number().optional()
            : f.required
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
            const isCheckbox = field.type === 'checkbox';
            return (
              <div key={field.name} className="grid gap-2">
                <Label
                  htmlFor={`field-${field.name}`}
                  className={isCheckbox ? 'flex items-center gap-2' : undefined}
                >
                  {isCheckbox ? (
                    <>
                      <input
                        id={`field-${field.name}`}
                        type="checkbox"
                        {...form.register(field.name)}
                        data-testid={`field-${field.name}`}
                        aria-invalid={error ? 'true' : 'false'}
                        className="border-input size-4 rounded"
                      />
                      <span>
                        {field.label}
                        {field.required && (
                          <span className="text-destructive" aria-hidden="true">
                            {' '}*
                          </span>
                        )}
                      </span>
                    </>
                  ) : (
                    <>
                      {field.label}
                      {field.required && (
                        <span className="text-destructive" aria-hidden="true">
                          {' '}*
                        </span>
                      )}
                    </>
                  )}
                </Label>
                {field.type === 'select' && (
                  <>
                    <CatalogSelect
                      field={field}
                      register={form.register(field.name)}
                      invalid={Boolean(error)}
                      currentValue={String(defaults[field.name] ?? '')}
                    />
                    {field.hint && (
                      <p id={`field-${field.name}-hint`} className="text-muted-foreground text-xs">
                        {field.hint}
                      </p>
                    )}
                  </>
                )}
                {!isCheckbox && field.type !== 'select' && (
                  <>
                    <Input
                      id={`field-${field.name}`}
                      type={field.type === 'number' ? 'number' : 'text'}
                      step={field.type === 'number' ? '0.0001' : undefined}
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
                  </>
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
