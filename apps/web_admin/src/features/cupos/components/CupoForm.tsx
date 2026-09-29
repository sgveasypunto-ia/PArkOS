/**
 * `<CupoForm />` — presentational form for create + edit cupo.
 *
 * Fields:
 *   - `uuid_sucursal` (read-only, shows current branch name).
 *   - `uuid_tipo_vehiculo` (select, optional) — NULL for "any vehicle
 *     type" (the cell-key with ``uuid_tipo_vehiculo IS NULL``). When the
 *     catalog is empty or the operator wants a brand-new tipo, an
 *     inline "+ Nuevo tipo" sub-form calls
 *     ``createTipoVehiculo`` and refreshes the cache so the new entry
 *     appears in the select immediately.
 *   - `cantidad` (integer, >= 0). The backend Pydantic constraint is
 *     ``z.number().int().min(0)``; we coerce to string in the schema
 *     to match the wire format the api layer expects, but the form
 *     input is a plain number.
 *   - `vigente_desde` (datetime-local, optional).
 *
 * The error message for the ``cantidad_bajo_ingresos_activos`` guard
 * lives in the page (Cupos.tsx) — it carries the operator-readable
 * detail with ``activos`` and ``solicitada`` to make the rejection
 * actionable. The form only knows about the lower-level Zod
 * validation.
 */
import { useState } from 'react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
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

import {
  cupoCreateSchema,
  type Cupo,
  type CupoCreateInput,
} from '../api/cupoSchema';
import type { TipoVehiculo } from '@/features/tipos-vehiculo/api/tiposVehiculoApi';

export interface CupoFormProps {
  form: UseFormReturn<CupoCreateInput>;
  onSubmit: (values: CupoCreateInput) => void;
  isSubmitting: boolean;
  isUpdate?: boolean;
  initialCupo?: Cupo | null;
  onCancel: () => void;
  sucursalNombre: string;
  tiposVehiculo: TipoVehiculo[];
  onTipoCreated: (
    nombre: string,
  ) => Promise<{ uuid: string } | void> | { uuid: string } | void;
  isCreatingTipo?: boolean;
}

function isoToDatetimeLocal(iso: string | null | undefined): string {
  if (!iso) return '';
  return iso.slice(0, 16);
}

function datetimeLocalToIso(local: string): string {
  return `${local}:00+00:00`;
}

export function CupoForm({
  form,
  onSubmit,
  isSubmitting,
  isUpdate = false,
  initialCupo = null,
  onCancel,
  sucursalNombre,
  tiposVehiculo,
  onTipoCreated,
  isCreatingTipo = false,
}: CupoFormProps) {
  const { t } = useTranslation();
  const [showNuevoTipo, setShowNuevoTipo] = useState(false);
  const [nuevoTipo, setNuevoTipo] = useState('');
  const [nuevoTipoError, setNuevoTipoError] = useState<string | null>(null);

  async function handleCrearNuevoTipo(): Promise<void> {
    const trimmed = nuevoTipo.trim();
    if (trimmed.length === 0) {
      setNuevoTipoError(
        t('cupos.field.tipoVehiculoNombreRequired', 'Ingresá un nombre.'),
      );
      return;
    }
    setNuevoTipoError(null);
    try {
      const creado = await onTipoCreated(trimmed);
      if (creado && typeof creado.uuid === 'string' && creado.uuid.length > 0) {
        form.setValue('uuid_tipo_vehiculo', creado.uuid);
      }
      setNuevoTipo('');
      setShowNuevoTipo(false);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : t('cupos.field.tipoVehiculoCreateError', 'No se pudo crear el tipo.');
      setNuevoTipoError(message);
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="cupo-form"
      >
        <div className="space-y-2">
          <FormLabel>{t('cupos.field.sucursal', 'Sucursal')}</FormLabel>
          <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
            {sucursalNombre}
          </p>
          <FormDescription>
            {t('cupos.field.sucursalHelp', 'El cupo pertenece a esta sucursal.')}
          </FormDescription>
        </div>

        <FormField
          control={form.control}
          name="uuid_tipo_vehiculo"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="uuid_tipo_vehiculo">
                {t('cupos.field.tipoVehiculo', 'Tipo de vehículo (opcional)')}
              </FormLabel>
              <FormControl>
                <div className="flex gap-2">
                  <select
                    id="uuid_tipo_vehiculo"
                    data-testid="cupo-field-tipo-vehiculo"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                    className="block w-full rounded-md border bg-background px-3 py-2 text-sm"
                  >
                    <option value="">
                      {t('cupos.field.tipoVehiculoAny', 'Cualquiera')}
                    </option>
                    {tiposVehiculo.map((tv) => (
                      <option key={tv.uuid} value={tv.uuid}>
                        {tv.tipo ?? tv.uuid}
                      </option>
                    ))}
                  </select>
                  {/* Cap of 5 active tipos is enforced server-side (409
                      ``tipos_vehiculo_max_reached``); hiding the toggle
                      keeps the UX consistent with the cap. */}
                  {tiposVehiculo.length < 5 && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setShowNuevoTipo((s) => !s);
                        setNuevoTipoError(null);
                      }}
                      data-testid="cupo-new-tipo-toggle"
                      disabled={isSubmitting}
                    >
                      {showNuevoTipo
                        ? t('cupos.field.tipoVehiculoCancelNew', 'Cancelar')
                        : t('cupos.field.tipoVehiculoNew', '+ Nuevo tipo')}
                    </Button>
                  )}
                </div>
              </FormControl>
              <FormDescription>
                {t(
                  'cupos.field.tipoVehiculoHelp',
                  'Vacío = aplica a cualquier tipo. Elegí uno o creá uno nuevo.',
                )}
              </FormDescription>
              <FormMessage />
              {showNuevoTipo && (
                <div
                  className="mt-2 space-y-2 rounded-md border bg-muted/40 p-3"
                  data-testid="cupo-new-tipo-panel"
                >
                  <FormLabel htmlFor="cupo-new-tipo-input">
                    {t('cupos.field.tipoVehiculoNombre', 'Nombre del nuevo tipo')}
                  </FormLabel>
                  <div className="flex gap-2">
                    <Input
                      id="cupo-new-tipo-input"
                      data-testid="cupo-new-tipo-input"
                      value={nuevoTipo}
                      onChange={(e) => setNuevoTipo(e.target.value)}
                      placeholder={t(
                        'cupos.field.tipoVehiculoNombrePlaceholder',
                        'ej. bicicleta',
                      )}
                      disabled={isCreatingTipo}
                    />
                    <Button
                      type="button"
                      size="sm"
                      onClick={handleCrearNuevoTipo}
                      data-testid="cupo-new-tipo-submit"
                      disabled={isCreatingTipo || nuevoTipo.trim().length === 0}
                    >
                      {isCreatingTipo
                        ? t('cupos.field.tipoVehiculoCreating', 'Creando…')
                        : t('cupos.field.tipoVehiculoSaveNew', 'Guardar')}
                    </Button>
                  </div>
                  {nuevoTipoError !== null && (
                    <p
                      role="alert"
                      className="text-xs text-destructive"
                      data-testid="cupo-new-tipo-error"
                    >
                      {nuevoTipoError}
                    </p>
                  )}
                </div>
              )}
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="cantidad"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="cantidad">
                {t('cupos.field.cantidad', 'Cantidad máxima de vehículos')}
              </FormLabel>
              <FormControl>
                <Input
                  id="cantidad"
                  data-testid="cupo-field-cantidad"
                  type="number"
                  step="1"
                  min="0"
                  placeholder="50"
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) =>
                    field.onChange(
                      e.target.value === '' ? null : Number(e.target.value),
                    )
                  }
                />
              </FormControl>
              <FormDescription>
                {t(
                  'cupos.field.cantidadHelp',
                  'Debe ser >= 0. Una cantidad menor que los ingresos activos es rechazada.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="vigente_desde"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="vigente_desde">
                {t('cupos.field.vigenteDesde', 'Vigente desde (opcional)')}
              </FormLabel>
              <FormControl>
                <Input
                  id="vigente_desde"
                  data-testid="cupo-field-vigente-desde"
                  type="datetime-local"
                  {...field}
                  value={isoToDatetimeLocal(field.value)}
                  onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === '') {
                      field.onChange(null);
                      return;
                    }
                    field.onChange(datetimeLocalToIso(raw));
                  }}
                />
              </FormControl>
              <FormDescription>
                {t(
                  'cupos.field.vigenteDesdeHelp',
                  'Vacío = ahora. Una fecha futura programa un cambio de cupo.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {initialCupo !== null && (
          <p
            className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
            data-testid="cupo-form-editing"
          >
            {t(
              'cupos.form.editingNotice',
              'Estás editando una versión existente. El cambio publica una nueva versión; la anterior se cierra automáticamente.',
            )}
          </p>
        )}

        <div className="mt-2 flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={onCancel}
            disabled={isSubmitting}
            data-testid="cupo-cancel"
          >
            {t('common.cancel', 'Cancelar')}
          </Button>
          <Button
            type="submit"
            disabled={isSubmitting}
            data-testid="cupo-submit"
          >
            {isSubmitting
              ? t('cupos.form.submitting', 'Guardando…')
              : isUpdate
                ? t('cupos.form.update', 'Actualizar')
                : t('cupos.form.create', 'Crear')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

function localNowAsDatetimeLocal(): string {
  /** Return the current local datetime as ``YYYY-MM-DDTHH:mm`` for the
   * ``<input type="datetime-local">`` default. Naive local time so the
   * operator sees "right now" in their own timezone when creating a new
   * cupo. The conversion back to UTC for the wire is the handler's job
   * (``_to_naive_utc`` in backend).
   */
  const now = new Date();
  const pad = (n: number): string => String(n).padStart(2, '0');
  return (
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
    `T${pad(now.getHours())}:${pad(now.getMinutes())}`
  );
}


export function CupoFormHarness(props: Omit<CupoFormProps, 'form'>): JSX.Element {
  const initial = props.initialCupo;
  // For CREATE (no initialCupo), default ``vigente_desde`` to "now" so the
  // operator has a sensible starting point — they can clear or override
  // before submit. For UPDATE, preserve the existing row's vigente_desde
  // (an accidental overwrite would silently re-open the version at
  // today, eating any scheduled-future change the operator was relying
  // on).
  const defaultVigenteDesde =
    initial?.vigente_desde ?? localNowAsDatetimeLocal() + ':00+00:00';
  const form = useForm<CupoCreateInput>({
    resolver: zodResolver(cupoCreateSchema) as never,
    defaultValues: {
      uuid_sucursal: initial?.uuid_sucursal ?? null,
      uuid_tipo_vehiculo: initial?.uuid_tipo_vehiculo ?? null,
      cantidad: initial?.cantidad ?? null,
      vigente_desde: defaultVigenteDesde,
    },
  });
  return <CupoForm {...props} form={form} />;
}