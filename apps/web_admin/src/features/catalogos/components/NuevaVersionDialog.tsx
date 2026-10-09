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
 *
 * El `submitError` se renderiza DENTRO del dialog (no en el Card
 * padre) para que el usuario lo vea cuando el dialog está abierto
 * — el dialog es modal y portaleado, un error afuera queda tapado
 * por el overlay.
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
  onSubmit: (
    values: Record<string, unknown>,
    config: { validateForm?: (v: Record<string, unknown>) => string | null },
  ) => Promise<void>;
  isSubmitting: boolean;
  /**
   * Optional pre-submit validator, run by the dialog before calling `onSubmit`.
   * Lets the config validate cross-field/format rules (e.g. JSON syntax) that
   * Zod's per-field schema can't express.
   */
  validateForm?: (values: Record<string, unknown>) => string | null;
  /** Error from the last failed submit. Rendered inside the dialog. */
  submitError?: string | null;
}

/**
 * `select` field with two modes:
 *  - `field.options` is set → render those literal options (e.g. enum-like
 *    fields such as `tipo_calculo`).
 *  - `field.optionsResource` is set → pull vigente rows from the named
 *    catalog (the common FK case).
 *
 * `optionsValueKey` controls which row key is used as the option `value`
 * (default `uuid`). Set it to e.g. `tipo` when the backend field is a
 * free string keyed by the option's `tipo` (e.g. `tipo_cliente_permitido`,
 * which the backend stores as a `str` not a FK).
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
  const hasLiteral = Array.isArray(field.options);
  const { rows } = useCatalogList(field.optionsResource ?? 'tipos-vehiculo');
  const labelKey = field.optionsLabelKey ?? 'tipo';
  const valueKey = field.optionsValueKey ?? 'uuid';

  const literalOptions = field.options ?? [];
  const resourceOptions = useResourceOptions({
    rows,
    valueKey,
    labelKey,
    currentValue,
  });

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
      {(hasLiteral ? literalOptions : resourceOptions).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

interface SelectOption {
  value: string;
  label: string;
}

/**
 * Build the `<option>` list for a resource-driven select. The `value` is
 * the row's `optionsValueKey` (default `uuid`). When the current row
 * references a no-longer-vigente version, keep that option selectable
 * so the field doesn't silently reset to "no value".
 */
function useResourceOptions({
  rows,
  valueKey,
  labelKey,
  currentValue,
}: {
  rows: { uuid: string; vigente_hasta: string | null; estado: string }[];
  valueKey: string;
  labelKey: string;
  currentValue: string;
}): SelectOption[] {
  const vigentes = rows.filter((r) => r.vigente_hasta === null && r.estado === 'activo');
  const stale =
    currentValue !== '' && !vigentes.some((r) => r.uuid === currentValue)
      ? (rows.find((r) => r.uuid === currentValue) ?? null)
      : null;
  const list = stale ? [...vigentes, stale] : vigentes;
  return list.map((r) => {
    const v = (r as unknown as Record<string, unknown>)[valueKey];
    return {
      value: v === undefined || v === null ? '' : String(v),
      label: String((r as unknown as Record<string, unknown>)[labelKey] ?? v ?? r.uuid),
    };
  });
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
  validateForm,
  submitError,
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
            if (validateForm) {
              const blocked = validateForm(values as Record<string, unknown>);
              if (blocked !== null) {
                form.setError('root' as never, { type: 'manual', message: blocked });
                return;
              }
            }
            await onSubmit(values as Record<string, unknown>, { validateForm });
          })}
          className="grid gap-4"
          data-testid="nueva-version-form"
        >
          {fields.map((field) => {
            const error = form.formState.errors[field.name];
            const isCheckbox = field.type === 'checkbox';
            const isTextarea = field.type === 'textarea' || (field.type === undefined && field.multiline === true);
            const errorId = `field-${field.name}-error`;
            const hintId = `field-${field.name}-hint`;
            const describedBy = [error ? errorId : null, field.hint ? hintId : null]
              .filter(Boolean)
              .join(' ');
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
                      <p id={hintId} className="text-muted-foreground text-xs">
                        {field.hint}
                      </p>
                    )}
                  </>
                )}
                {!isCheckbox && field.type !== 'select' && (
                  <>
                    {isTextarea ? (
                      <textarea
                        id={`field-${field.name}`}
                        {...form.register(field.name)}
                        data-testid={`field-${field.name}`}
                        aria-invalid={error ? 'true' : 'false'}
                        aria-describedby={describedBy || undefined}
                        placeholder={field.placeholder}
                        rows={4}
                        className="border-input bg-transparent flex w-full rounded-md border px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      />
                    ) : (
                      <Input
                        id={`field-${field.name}`}
                        type={field.type === 'number' ? 'number' : 'text'}
                        step={field.type === 'number' ? '0.0001' : undefined}
                        placeholder={field.placeholder}
                        {...form.register(field.name)}
                        data-testid={`field-${field.name}`}
                        aria-invalid={error ? 'true' : 'false'}
                        aria-describedby={describedBy || undefined}
                      />
                    )}
                    {field.hint && (
                      <p id={hintId} className="text-muted-foreground text-xs">
                        {field.hint}
                      </p>
                    )}
                    {error && (
                      <p
                        id={errorId}
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

          {(form.formState.errors.root || submitError) && (
            <p
              role="alert"
              aria-live="assertive"
              className="border-destructive/50 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm"
              data-testid="nueva-version-submit-error"
            >
              {((form.formState.errors.root as { message?: string } | undefined)?.message as string) ??
                submitError}
            </p>
          )}

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
