/**
 * `<CupoForm />` — presentational form for create + edit cupo.
 *
 * Fields:
 *   - `uuid_sucursal` (read-only, shows current branch name).
 *   - `uuid_tipo_vehiculo` (select on CREATE, readonly on EDIT) —
 *     NULL for "any vehicle type" (the cell-key with
 *     ``uuid_tipo_vehiculo IS NULL``). On CREATE the select hides
 *     tipos already in use by an OPEN cupo for the current branch
 *     (each ``(sucursal, uuid_tipo_vehiculo)`` cell can hold at most
 *     one open version — the backend's overlap guard already enforces
 *     this with 409; we hide the conflict from the UI). On EDIT the
 *     field is locked to the existing row's tipo (the operator can
 *     still change ``cantidad`` and ``vigente_desde``). When the
 *     catalog is empty or the operator wants a brand-new tipo, an
 *     inline "+ Nuevo tipo" sub-form calls ``createTipoVehiculo``
 *     and refreshes the cache so the new entry appears in the select
 *     immediately.
 *   - `cantidad` (integer, >= 0). The backend Pydantic constraint is
 *     ``z.number().int().min(0)``; we coerce to string in the schema
 *     to match the wire format the api layer expects, but the form
 *     input is a plain number.
 *   - `vigente_desde` (datetime-local, optional). CREATE pre-fills
 *     with ``new Date()``; EDIT preserves the existing row's value.
 *
 * The error message for the ``capacidad_insuficiente`` guard (BR2,
 * HU-F14.4) lives in the page (Cupos.tsx) — it carries the
 * operator-readable detail with ``tipo`` and ``ocupadoActual`` /
 * ``solicitado`` to make the rejection actionable. The form only
 * knows about the lower-level Zod validation.
 */
import { useEffect, useMemo, useState } from 'react';
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

export const TIPO_NULL_SENTINEL = '__NULL__';

export interface CupoFormProps {
  form: UseFormReturn<CupoCreateInput>;
  onSubmit: (values: CupoCreateInput) => void;
  isSubmitting: boolean;
  isUpdate?: boolean;
  initialCupo?: Cupo | null;
  onCancel: () => void;
  sucursalNombre: string;
  tiposVehiculo: TipoVehiculo[];
  /** Set of ``uuid_tipo_vehiculo`` (or ``TIPO_NULL_SENTINEL`` for NULL)
   *  already in use by an OPEN cupo for the current branch. CREATE
   *  filters these out of the select; EDIT locks the field instead. */
  tiposEnUsoEnSucursal: Set<string>;
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
  tiposEnUsoEnSucursal,
  onTipoCreated,
  isCreatingTipo = false,
}: CupoFormProps) {
  const { t } = useTranslation();
  const [showNuevoTipo, setShowNuevoTipo] = useState(false);
  const [nuevoTipo, setNuevoTipo] = useState('');
  const [nuevoTipoError, setNuevoTipoError] = useState<string | null>(null);

  // CREATE: filter tipos already in use by an open cupo on this
  // branch. CREATE no longer offers the "Cualquiera" cell
  // (uuid_tipo_vehiculo = null) — every cupo must target a specific
  // tipo from the catalog. The NULL sentinel still matters for the
  // empty-state check below: if every one of the 5 tipos is taken AND
  // the NULL cell is also taken, there is literally nothing to create.
  // Memoized so the auto-select effect below can read a stable
  // reference (otherwise the effect would re-run on every parent
  // render and risk a loop).
  const disponibles = useMemo(
    () => tiposVehiculo.filter((tv) => !tiposEnUsoEnSucursal.has(tv.uuid)),
    [tiposVehiculo, tiposEnUsoEnSucursal],
  );
  const cualquierTomada = tiposEnUsoEnSucursal.has(TIPO_NULL_SENTINEL);
  const todoEnUso = cualquierTomada && disponibles.length === 0;

  // Auto-select the first available tipo on CREATE when the form
  // state still has no selection. The browser visually auto-picks
  // the first <option> when ``field.value`` is nullish and no
  // ``<option value="">`` exists, but RHF state stays null — the
  // submitted payload would then carry ``uuid_tipo_vehiculo: null``
  // and the cupo would persist as the "Cualquiera" cell instead of
  // the tipo the operator thinks they picked. Re-stated: the visual
  // selection in the <select> and the form state are decoupled when
  // the value is null and there is no empty-string option, so we
  // sync them here. EDIT is left alone: the field is locked to the
  // existing row's tipo (see ``tipoFijo`` below).
  useEffect(() => {
    if (initialCupo !== null) return;
    if (disponibles.length === 0) return;
    const current = form.getValues('uuid_tipo_vehiculo');
    if (current !== null && current !== undefined && current !== '') return;
    form.setValue('uuid_tipo_vehiculo', disponibles[0].uuid, {
      shouldDirty: false,
      shouldTouch: false,
    });
  }, [initialCupo, disponibles, form]);

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
          render={({ field }) => {
            // EDIT: tipo is locked. The cell (sucursal, uuid_tipo_vehiculo)
            // can only hold one open cupo; if the operator wants a different
            // tipo they must edit a different cupo (or wait for the current
            // one's version to close). The form still submits the existing
            // uuid, so backend overlap-check sees no change.
            const tipoFijo = initialCupo !== null;
            const tipoActualLabel = (() => {
              if (!tipoFijo) return null;
              const actual = initialCupo?.uuid_tipo_vehiculo;
              if (actual === null || actual === undefined) {
                return t('cupos.field.tipoVehiculoAny', 'Cualquiera');
              }
              return (
                tiposVehiculo.find((tv) => tv.uuid === actual)?.tipo ??
                actual
              );
            })();
            // CREATE: ``disponibles``, ``cualquierTomada`` and ``todoEnUso``
            // are computed at the component scope (see the useMemo /
            // useEffect above) so the auto-select effect can react to
            // them without re-rendering through the render-prop.
            return (
            <FormItem>
              <FormLabel htmlFor="uuid_tipo_vehiculo">
                {t('cupos.field.tipoVehiculo', 'Tipo de vehículo (opcional)')}
              </FormLabel>
              <FormControl>
                {tipoFijo ? (
                  <div className="flex flex-col gap-2">
                    <input
                      id="uuid_tipo_vehiculo"
                      data-testid="cupo-field-tipo-vehiculo"
                      readOnly
                      aria-readonly="true"
                      className="block w-full rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
                      value={tipoActualLabel ?? ''}
                    />
                    <p
                      className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
                      data-testid="cupo-field-tipo-vehiculo-locked"
                    >
                      {t(
                        'cupos.field.tipoVehiculoLocked',
                        'Tipo fijo — ya existe un cupo con este tipo en esta sucursal. Solo se puede editar la cantidad y la vigencia.',
                      )}
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    {todoEnUso ? (
                      <p
                        role="status"
                        className="rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
                        data-testid="cupo-field-tipo-vehiculo-all-used"
                      >
                        {t(
                          'cupos.field.tipoVehiculoAllUsed',
                          'Todos los tipos de vehículo están en uso para esta sucursal. Editá o cerrá un cupo existente antes de crear uno nuevo.',
                        )}
                      </p>
                    ) : (
                      <div className="flex gap-2">
                        <select
                          id="uuid_tipo_vehiculo"
                          data-testid="cupo-field-tipo-vehiculo"
                          {...field}
                          value={field.value ?? ''}
                          onChange={(e) =>
                            field.onChange(
                              e.target.value === '' ? null : e.target.value,
                            )
                          }
                          className="block w-full rounded-md border bg-background px-3 py-2 text-sm"
                        >
                          {disponibles.map((tv) => (
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
                    )}
                  </div>
                )}
              </FormControl>
              <FormDescription>
                {t(
                  'cupos.field.tipoVehiculoHelp',
                  'Elegí uno de los tipos existentes o creá uno nuevo.',
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
            );
          }}
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
                {t('cupos.field.vigenteDesde', 'Vigente desde')}
              </FormLabel>
              <FormControl>
                <Input
                  id="vigente_desde"
                  data-testid="cupo-field-vigente-desde"
                  type="datetime-local"
                  {...field}
                  value={isoToDatetimeLocal(field.value)}
                  onChange={(e) => {
                    // The field is required (see Zod schema ``cupoCreateSchema``
                    // in ``api/cupoSchema.ts``). Clearing is intentionally
                    // a no-op — the operator must pick a valid datetime.
                    const raw = e.target.value;
                    if (raw === '') return;
                    field.onChange(datetimeLocalToIso(raw));
                  }}
                />
              </FormControl>
              <FormDescription>
                {t(
                  'cupos.field.vigenteDesdeHelp',
                  'Una fecha futura programa un cambio de cupo.',
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


function localNowPlusMinutesAsIso(minutes: number): string {
  /** Return the current local datetime shifted by ``minutes`` minutes,
   * formatted as ``YYYY-MM-DDTHH:mm:00+00:00`` (the wire format the
   * form submits for ``vigente_desde``). Used by the EDIT modal as a
   * default: when the operator opens an existing cupo for editing, the
   * boundary is pre-set to "now + 1 minute" so submitting without
   * touching the field opens a new version one minute ahead of the
   * current boundary — strictly forward in time, no overlap risk on
   * the same exact instant.
   *
   * CREATE keeps its own default ("now", current minute) — see
   * ``CupoFormHarness``. Per the UX rule shipped 2026-09-29, CREATE
   * and EDIT differ on this default.
   */
  const now = new Date();
  now.setMinutes(now.getMinutes() + minutes);
  const pad = (n: number): string => String(n).padStart(2, '0');
  return (
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
    `T${pad(now.getHours())}:${pad(now.getMinutes())}:00+00:00`
  );
}


export function CupoFormHarness(props: Omit<CupoFormProps, 'form'>): JSX.Element {
  const initial = props.initialCupo;
  // Per-mode default for ``vigente_desde``:
  //   - CREATE (no initialCupo): "now" (current minute in the operator's
  //     local TZ). The new cupo opens at the current instant if
  //     submitted without changes.
  //   - EDIT (initialCupo !== null): "now + 1 minute". The 1-minute shift
  //     keeps the new boundary strictly forward of the prior version's
  //     cierre (Carril B: ``close_and_insert`` closes the previous row
  //     at the boundary the new one opens) and matches the canonical
  //     UX rule shipped 2026-09-29.
  // The field is required (see ``cupoCreateSchema`` — drop
  // ``.nullable().optional()``) so the form never ships ``null`` on
  // submit. Operators can still edit the value freely.
  const defaultVigenteDesde =
    initial === null
      ? localNowAsDatetimeLocal() + ':00+00:00'
      : localNowPlusMinutesAsIso(1);
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