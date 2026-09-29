/**
 * `<TarifaForm />` — presentational form for create + edit tarifa.
 *
 * DEC-F3.1-02 mirror: container/presentational split. The parent
 * (`<Tarifas />`) owns submit state, the SWR mutations, the error
 * mapping from typed error classes (`TarifaOverlapError`,
 * `TarifaSucursalInmutableError`), and the SWR revalidation.
 *
 * Renders a complete `<form>` so it can be slotted inside any
 * `FormModal` without producing nested forms. The submit button is
 * part of the form; the FormModal shell no longer renders its own.
 *
 * Fields:
 *   - `uuid_sucursal` (read-only display) — the tarifa belongs to the
 *     branch selected in the topbar. The form no longer lets the
 *     operator change it; the page pins the value via
 *     ``onSubmit`` to defend against any caller-side drift.
 *   - `uuid_tipo_vehiculo` (select on CREATE, readonly on EDIT) — NULL
 *     is gone from the public CREATE surface (the operator must pick
 *     one of the 5 canonical tipos). The sentinel
 *     ``TIPO_NULL_SENTINEL_VEHICULO`` still participates in the
 *     per-branch used-set check so the operator never tries to open
 *     a second version for a cell that already has one open. The
 *     harness pre-selects the first available catalog entry on CREATE
 *     so the operator never submits null by forgetting to pick one.
 *   - `uuid_tipo_tarifa` (select on CREATE, readonly on EDIT) — same
 *     rule, sentinel ``TIPO_NULL_SENTINEL_TARIFA``.
 *   - `valor_hora`, `valor_fraccion`, `valor_plena`, `valor_nocturna`
 *     — four inputs for the 4 canonical modalidades. The page-side
 *     ``onSubmit`` splits this into one POST per modality to the
 *     dedicated single-row handler, producing 4 ``tarifas_sucursal``
 *     rows per (sucursal, tipo_vehiculo) cell. Each field is
 *     REQUIRED (no nulls) — a tarifa cell always has all four
 *     modalities priced. `valor_*` > 0; `valor_plena` >= 0.
 *   - `vigente_desde` (datetime-local, REQUIRED). The operator cannot
 *     clear it. CREATE defaults to "now" (current minute in the
 *     operator's local TZ); EDIT defaults to "now + 1 minute" per the
 *     canonical UX rule shipped 2026-09-29 for this screen.
 */
import { useEffect } from 'react';
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
  tarifaCreateSchema,
  type Tarifa,
  type TarifaCreateInput,
} from '../api/tarifaSchema';
import type { TipoVehiculo } from '@/features/tipos-vehiculo/api/tiposVehiculoApi';
import { useTiposVehiculo } from '@/features/tipos-vehiculo/hooks/useTiposVehiculo';

export const TIPO_NULL_SENTINEL_VEHICULO = '__VEHICULO_NULL__';

export interface TarifaFormProps {
  form: UseFormReturn<TarifaCreateInput>;
  onSubmit: (values: TarifaCreateInput) => void;
  isSubmitting: boolean;
  /** Update mode renders "Actualizar" + PUT semantics in the parent. */
  isUpdate?: boolean;
  /** Optional prefill from the row being edited (PUT). */
  initialTarifa?: Tarifa | null;
  /** Close the parent modal (e.g. cancel button). */
  onCancel: () => void;
  /** Display label for the branch shown in the readonly field. */
  sucursalActivaNombre: string;
  /** Catalog of tipos_vehiculo (full set, not filtered). The harness
   *  pre-picks the first available entry for CREATE defaults; the
   *  form filters it by ``tiposVehiculoEnUsoEnSucursal`` before
   *  rendering the CREATE select. */
  tiposVehiculo: TipoVehiculo[];
  /** Set of uuid_tipo_vehiculo already in use by an open tarifa for
   * the active branch. CREATE hides these from the select; EDIT ignores
   * them (field is locked anyway). */
  tiposVehiculoEnUsoEnSucursal: Set<string>;
}

/** Props only the harness consumes — never reaches the presentational
 *  form. Lets the harness default ``uuid_sucursal`` to the active
 *  branch without leaking that wiring into the form's signature. */
interface TarifaFormHarnessExtraProps {
  /** Branch selected in the topbar. The harness uses it as the
   *  default for ``uuid_sucursal``; the form never picks it (the
   *  parent page pins it again on submit as defense in depth). */
  sucursalActivaUuid: string | null;
}

function isoToDatetimeLocal(iso: string | null | undefined): string {
  if (!iso) return '';
  return iso.slice(0, 16);
}

function datetimeLocalToIso(local: string): string {
  return `${local}:00+00:00`;
}

function localNowAsDatetimeLocal(): string {
  /** Return the current local datetime as ``YYYY-MM-DDTHH:mm`` for the
   * ``<input type="datetime-local">`` default. Naive local time so the
   * operator sees "right now" in their own timezone when creating a new
   * tarifa. The conversion back to UTC for the wire is the handler's
   * job (``_to_naive_utc`` in backend). */
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
   * default: when the operator opens an existing tarifa for editing, the
   * boundary is pre-set to "now + 1 minute" so submitting without
   * touching the field opens a new version one minute ahead of the
   * current boundary — strictly forward in time, no overlap risk on
   * the same exact instant.
   *
   * CREATE keeps its own default ("now", current minute) — see
   * ``TarifaFormHarness``. Per the UX rule shipped 2026-09-29, CREATE
   * and EDIT differ on this default. */
  const now = new Date();
  now.setMinutes(now.getMinutes() + minutes);
  const pad = (n: number): string => String(n).padStart(2, '0');
  return (
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
    `T${pad(now.getHours())}:${pad(now.getMinutes())}:00+00:00`
  );
}

export function TarifaForm({
  form,
  onSubmit,
  isSubmitting,
  isUpdate = false,
  initialTarifa = null,
  onCancel,
  sucursalActivaNombre,
  tiposVehiculo,
  tiposVehiculoEnUsoEnSucursal,
}: TarifaFormProps) {
  const { t } = useTranslation();

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="tarifa-form"
      >
        <div className="space-y-2">
          <FormLabel>{t('tarifas.field.sucursal', 'Sucursal')}</FormLabel>
          <p
            className="rounded-md border bg-muted/40 px-3 py-2 text-sm"
            data-testid="tarifa-field-sucursal-readonly"
          >
            {sucursalActivaNombre || '—'}
          </p>
          <FormDescription>
            {t(
              'tarifas.field.sucursalHelp',
              'La tarifa pertenece a la sucursal activa seleccionada en el topbar.',
            )}
          </FormDescription>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="uuid_tipo_vehiculo"
            render={({ field }) => {
              // EDIT: lock the tipo. The (sucursal, tipo_vehiculo,
              // tipo_tarifa) cell is the tarifa's identity — once a
              // tarifa is created, those three columns are fixed. The
              // operator edits valor / valor_plena / vigente_desde;
              // switching tipo_vehiculo would open a new version in a
              // different cell, which is outside the scope of "edit".
              const tipoFijo = initialTarifa !== null;
              const tipoActualLabel = (() => {
                if (!tipoFijo) return null;
                const actual = initialTarifa?.uuid_tipo_vehiculo;
                if (actual === null || actual === undefined) {
                  return t('tarifas.tipoVehiculoAny', 'Cualquiera');
                }
                return (
                  tiposVehiculo.find((tv) => tv.uuid === actual)?.tipo ??
                  actual
                );
              })();
              // CREATE: hide tipos already in use by an open tarifa
              // for this branch. CREATE no longer offers the NULL
              // cell (uuid_tipo_vehiculo = null) — every tarifa must
              // target a specific tipo from the catalog.
              const disponibles = tiposVehiculo.filter(
                (tv) => !tiposVehiculoEnUsoEnSucursal.has(tv.uuid),
              );
              return (
                <FormItem>
                  <FormLabel htmlFor="uuid_tipo_vehiculo">
                    {t('tarifas.field.tipoVehiculo', 'Tipo de vehículo')}
                  </FormLabel>
                  <FormControl>
                    {tipoFijo ? (
                      <div className="flex flex-col gap-2">
                        <input
                          id="uuid_tipo_vehiculo"
                          data-testid="tarifa-field-tipo-vehiculo"
                          readOnly
                          aria-readonly="true"
                          className="block w-full rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
                          value={tipoActualLabel ?? ''}
                        />
                        <p
                          className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
                          data-testid="tarifa-field-tipo-vehiculo-locked"
                        >
                          {t(
                            'tarifas.field.tipoVehiculoLocked',
                            'Tarifa fija — el tipo de vehículo no se puede cambiar después de creada.',
                          )}
                        </p>
                      </div>
                    ) : (
                      <select
                        id="uuid_tipo_vehiculo"
                        data-testid="tarifa-field-tipo-vehiculo"
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
                    )}
                  </FormControl>
                  <FormMessage />
                </FormItem>
              );
            }}
          />

          <FormField
            control={form.control}
            name="valor_hora"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="valor_hora">
                  {t('tarifas.field.valorHora', 'Valor hora')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="valor_hora"
                    data-testid="tarifa-field-valor-hora"
                    type="number"
                    step="0.0001"
                    min="0"
                    placeholder="1500"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                  />
                </FormControl>
                <FormDescription>
                  {t('tarifas.field.valorHoraHelp', 'Debe ser > 0. Cuatro decimales.')}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="valor_fraccion"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="valor_fraccion">
                  {t('tarifas.field.valorFraccion', 'Valor fracción')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="valor_fraccion"
                    data-testid="tarifa-field-valor-fraccion"
                    type="number"
                    step="0.0001"
                    min="0"
                    placeholder="800"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                  />
                </FormControl>
                <FormDescription>
                  {t('tarifas.field.valorFraccionHelp', 'Debe ser > 0. Cuatro decimales.')}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="valor_plena"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="valor_plena">
                  {t('tarifas.field.valorPlena', 'Valor plena')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="valor_plena"
                    data-testid="tarifa-field-valor-plena"
                    type="number"
                    step="0.0001"
                    min="0"
                    placeholder="2000"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                  />
                </FormControl>
                <FormDescription>
                  {t('tarifas.field.valorPlenaHelp', 'Debe ser >= 0. Cuatro decimales.')}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="valor_nocturna"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="valor_nocturna">
                  {t('tarifas.field.valorNocturna', 'Valor nocturna')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="valor_nocturna"
                    data-testid="tarifa-field-valor-nocturna"
                    type="number"
                    step="0.0001"
                    min="0"
                    placeholder="1000"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                  />
                </FormControl>
                <FormDescription>
                  {t('tarifas.field.valorNocturnaHelp', 'Debe ser > 0. Cuatro decimales.')}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="vigente_desde"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="vigente_desde">
                {t('tarifas.field.vigenteDesde', 'Vigente desde')}
              </FormLabel>
              <FormControl>
                <Input
                  id="vigente_desde"
                  data-testid="tarifa-field-vigente-desde"
                  type="datetime-local"
                  {...field}
                  value={isoToDatetimeLocal(field.value)}
                  onChange={(e) => {
                    // The field is required (see Zod schema
                    // ``tarifaCreateSchema`` in ``api/tarifaSchema.ts``).
                    // Clearing is intentionally a no-op — the operator
                    // must pick a valid datetime.
                    const raw = e.target.value;
                    if (raw === '') return;
                    field.onChange(datetimeLocalToIso(raw));
                  }}
                />
              </FormControl>
              <FormDescription>
                {t(
                  'tarifas.field.vigenteDesdeHelp',
                  'Una fecha futura programa un cambio de tarifa.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {initialTarifa !== null && (
          <p
            className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
            data-testid="tarifa-form-editing"
          >
            {t(
              'tarifas.form.editingNotice',
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
            data-testid="tarifa-cancel"
          >
            {t('common.cancel', 'Cancelar')}
          </Button>
          <Button
            type="submit"
            disabled={isSubmitting}
            data-testid="tarifa-submit"
          >
            {isSubmitting
              ? t('tarifas.form.submitting', 'Guardando…')
              : isUpdate
                ? t('tarifas.form.update', 'Actualizar')
                : t('tarifas.form.create', 'Crear')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

export function TarifaFormHarness(
  props: Omit<TarifaFormProps, 'form'> & TarifaFormHarnessExtraProps,
): JSX.Element {
  const initial = props.initialTarifa;
  // The wiring layer owns the catalog reads — moving them here lets
  // the harness default the tipo select in CREATE before the operator
  // submits, so an operator who forgets to interact with the select
  // still has the form pre-populated (and the backend's
  // strict-required rule never fires for a UI submit).
  const { tipos: tiposVehiculoCatalog } = useTiposVehiculo();

  // Per the canonical UX rule shipped 2026-09-29, the tarifa is a
  // single-tenant resource. The harness receives ``sucursalActivaUuid``
  // from the page (already bound to the topbar selection) and uses it as
  // the default for ``uuid_sucursal``. If the operator is editing a
  // tarifa whose sucursal differs from the active one, the page's
  // ``sucursal_inmutable`` backend guard (422) refuses the PUT — the
  // form surface should never expose that case in practice (the list
  // is filtered to the active branch).
  //
  // ``vigente_desde`` defaults to "now" in CREATE and "now + 1 minute"
  // in EDIT (the canonical UX rule for /tarifas, matching /cupos).
  const defaultVigenteDesde =
    initial === null
      ? localNowAsDatetimeLocal() + ':00+00:00'
      : localNowPlusMinutesAsIso(1);
  // Strip the harness-only prop before forwarding to the presentational
  // form — keeps the form's interface focused on what it actually
  // renders (the readonly name, not the uuid). The used-sets are
  // passed through to the form unchanged (it filters the CREATE
  // selects with them).
  const { sucursalActivaUuid, ...formProps } = props;
  const tiposVehiculoEnUsoEnSucursal = formProps.tiposVehiculoEnUsoEnSucursal;
  // The tarifa cell-key is now (sucursal, tipo_vehiculo) only — the
  // 4 modalities (hora, fraccion, plena, nocturna) are configured in a
  // single CREATE via 4 separate value inputs, producing 4 rows on
  // submit. ``tiposTarifaEnUsoEnSucursal`` is intentionally ignored
  // here: a (sucursal, tipo_vehiculo) cell already having tarifa rows
  // is fine — the page-side split just closes-and-inserts each
  // modality in the back end.
  const form = useForm<TarifaCreateInput>({
    resolver: zodResolver(tarifaCreateSchema) as never,
    defaultValues: {
      uuid_sucursal: sucursalActivaUuid ?? initial?.uuid_sucursal ?? null,
      uuid_tipo_vehiculo: initial?.uuid_tipo_vehiculo ?? null,
      valor_hora: null,
      valor_fraccion: null,
      valor_plena: null,
      valor_nocturna: null,
      vigente_desde: defaultVigenteDesde,
    },
  });

  // CREATE-only default-pre-population. The backend (post-2026-09-29)
  // rejects null ``uuid_tipo_vehiculo`` with 422, so we must default
  // the select to the first available entry filtered by per-branch
  // in-use set. The ``useEffect`` runs after the catalog loads so the
  // first render (with empty catalog) doesn't race with a later
  // ``setValue``. The idempotent guard (``=== null``) avoids overwriting
  // an operator's manual selection if they picked a tipo before the
  // catalog finished loading.
  useEffect(() => {
    if (initial !== null) return; // EDIT: tipos locked from initialTarifa
    const current = form.getValues();
    if (
      current.uuid_tipo_vehiculo === null
      && tiposVehiculoCatalog.length > 0
    ) {
      const primero = tiposVehiculoCatalog.find(
        (tv) => !tiposVehiculoEnUsoEnSucursal.has(tv.uuid),
      );
      if (primero) {
        form.setValue('uuid_tipo_vehiculo', primero.uuid, { shouldDirty: false });
      }
    }
  }, [
    tiposVehiculoCatalog,
    tiposVehiculoEnUsoEnSucursal,
    initial,
    form,
  ]);

  return <TarifaForm {...formProps} form={form} />;
}