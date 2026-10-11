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
 *     ``onSubmit`` splits this into one POST per modalidad (only the
 *     ones the operator filled in; 1..4 from the canonical set --
 *     HU-tarifas-N-modalidades, 2026-10-11). At least one valor_X
 *     must be non-null -- the form's RHF schema enforces this via a
 *     ``superRefine`` (one row, four ``Ingresá al menos un valor``
 *     issues so the operator sees the same message on every input).
 *     When non-null, each ``valor_*`` > 0 (and ``valor_plena`` >= 0);
 *     null means "I am not configuring this modalidad" (allowed on
 *     both CREATE and EDIT; the page-side submit filter then skips
 *     the modality). The 4-input UX is preserved for ergonomic
 *     reasons (the operator can see all 4 at once) but the contract
 *     is "fill 1 to 4".
 *   - `vigente_desde` (datetime-local, REQUIRED). The operator cannot
 *     clear it. Both CREATE and EDIT default to "now" (current
 *     instant in the operator's local TZ) -- HU-tarifas-N-modalidades
 *     unified the previous EDIT default of "now + 1 minute" to fix
 *     the chrome-devtools bug where the new row landed in the future
 *     and the list endpoint (which evaluates the bi-temporal
 *     predicate with server-now) hid it for 60s.
 */
import { useEffect } from 'react';
import { useForm, useWatch, type UseFormReturn } from 'react-hook-form';
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
  datetimeLocalToIso,
  isoToDatetimeLocal,
  utcNowPlusMinutesAsIso,
} from '@/lib/datetimeTz';
import { formatTarifaValor } from '../lib/formatTarifaValor';

import {
  tarifaCreateSchema,
  tarifaEditSchema,
  type TarifaCreateInput,
} from '../api/tarifaSchema';
import type { TarifaAgrupada } from '../api/tarifaAgrupada';
import type { TipoVehiculo } from '@/features/tipos-vehiculo/api/tiposVehiculoApi';
import { useTiposVehiculo } from '@/features/tipos-vehiculo/hooks/useTiposVehiculo';

export const TIPO_NULL_SENTINEL_VEHICULO = '__VEHICULO_NULL__';

export interface TarifaFormProps {
  form: UseFormReturn<TarifaCreateInput>;
  onSubmit: (values: TarifaCreateInput) => void;
  isSubmitting: boolean;
  /** Update mode renders "Actualizar" + PUT semantics in the parent. */
  isUpdate?: boolean;
  /** Optional prefill from the grouped row being edited (PUT). The
   * page passes this to pre-fill the 4 valor_* inputs from the 4
   * per-modalidad rows in the cell. */
  initialTarifaAgrupada?: TarifaAgrupada | null;
  /** Close the parent modal (e.g. cancel button). */
  onCancel: () => void;
  /** Display label for the branch shown in the readonly field. */
  sucursalActivaNombre: string;
  /** Catalog of tipos_vehiculo (full set, not filtered). */
  tiposVehiculo: TipoVehiculo[];
  /** Set of uuid_tipo_vehiculo already in use by an open tarifa for
   * the active branch. */
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

export function TarifaForm({
  form,
  onSubmit,
  isSubmitting,
  isUpdate = false,
  initialTarifaAgrupada = null,
  onCancel,
  sucursalActivaNombre,
  tiposVehiculo,
  tiposVehiculoEnUsoEnSucursal,
}: TarifaFormProps) {
  const { t } = useTranslation();
  // The submit button is disabled while the form has zero non-null
  // ``valor_*`` inputs. We compute this via ``useWatch`` (subscribed
  // to the 4 valor_* fields) so the button reflects the typed-in
  // value on the SAME render the input change commits -- no stale
  // ``isValid=false`` from the initial mount, no async re-validation
  // race. The schema-level superRefine (al menos 1 non-null) is the
  // defense in depth: even if the operator bypasses this UI guard,
  // the batch endpoint would 422.
  const watchedValors = useWatch({
    control: form.control,
    name: [
      'valor_hora',
      'valor_fraccion',
      'valor_plena',
      'valor_nocturna',
    ],
  });
  // ``useWatch`` returns a fresh array each render with the current
  // value of each watched field. A field that has not been registered
  // or has no value yet comes through as ``undefined`` -- the harness
  // mounts before the form fields register, so on the first render
  // the array is empty and ``hasAnyValor`` is correctly false. As
  // soon as the operator types (or an EDIT pre-populates a value),
  // the array carries the new string and the button enables.
  const safeValors: ReadonlyArray<unknown> = Array.isArray(watchedValors)
    ? watchedValors
    : [];
  const hasAnyValor = safeValors.some(
    (v) => typeof v === 'string' && v.length > 0,
  );
  const isValid = hasAnyValor;

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
              const tipoFijo = initialTarifaAgrupada !== null;
              const tipoActualLabel = (() => {
                if (!tipoFijo) return null;
                const actual = initialTarifaAgrupada?.uuid_tipo_vehiculo;
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
                          aria-label={t(
                            'tarifas.field.tipoVehiculoAriaLabel',
                            'Tipo de vehículo (no editable)',
                          )}
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

                    aria-required="true"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                  />
                </FormControl>
                <FormDescription>
                  {t('tarifas.field.valorHoraHelp', 'Debe ser > 0. Cuatro decimales. Obligatorio.')}
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

                    aria-required="true"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                  />
                </FormControl>
                <FormDescription>
                  {t('tarifas.field.valorFraccionHelp', 'Debe ser > 0. Cuatro decimales. Obligatorio.')}
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

                    aria-required="true"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                  />
                </FormControl>
                <FormDescription>
                  {t('tarifas.field.valorPlenaHelp', 'Debe ser >= 0. Cuatro decimales. Obligatorio.')}
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

                    aria-required="true"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                  />
                </FormControl>
                <FormDescription>
                  {t('tarifas.field.valorNocturnaHelp', 'Debe ser > 0. Cuatro decimales. Obligatorio.')}
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

                    aria-required="true"
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

        {initialTarifaAgrupada !== null && (
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
            disabled={isSubmitting || !isValid}
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
  const initial = props.initialTarifaAgrupada;
  // The wiring layer owns the catalog reads — moving them here lets
  // the harness default the tipo select in CREATE before the operator
  // submits, so an operator who forgets to interact with the select
  // still has the form pre-populated (and the backend's
  // strict-required rule never fires for a UI submit).
  const { tipos: tiposVehiculoCatalog } = useTiposVehiculo();

  // ``vigente_desde`` defaults to "now" (real UTC) for BOTH CREATE
  // and EDIT (HU-tarifas-N-modalidades, operator feedback 2026-10-11).
  // The previous EDIT default of "now + 1 minute" was intended as
  // buffer against client/server clock skew, but it had a critical
  // side-effect: the new row landed in the future, invisible to
  // the list endpoint (which evaluates the bi-temporal predicate
  // with ``datetime.now(UTC)`` server-side) until the wall clock
  // crossed the +1min boundary. The user perceived this as "the
  // record disappeared and only came back on refresh". The fix:
  // unified ``now+0`` for both modes. The backend still has a
  // monotonicity guard (``empresa.py:895-904`` rejects
  // ``nueva_desde < current.vigente_desde`` with 409) and
  // ``close_and_insert`` closes the old row with
  // ``vigente_hasta = nueva_desde`` and opens the new one at the
  // same instant -- no gap, no phantom future row. Both go through
  // ``@/lib/datetimeTz`` so the wire format is the canonical
  // ``+00:00`` suffix.
  const defaultVigenteDesde = utcNowPlusMinutesAsIso(0);
  const { sucursalActivaUuid, isUpdate = false, ...formProps } = props;
  const tiposVehiculoEnUsoEnSucursal = formProps.tiposVehiculoEnUsoEnSucursal;
  // Pre-fill the 4 valor_* inputs from the grouped row's per-modalidad
  // entries in EDIT. In CREATE they're null and the operator types
  // them. The page splits the single submit into 4 POSTs/PUTs.
  //
  // Schema switch: CREATE uses the strict ``tarifaCreateSchema``
  // (every valor_* required + > 0). EDIT uses the lenient
  // ``tarifaEditSchema`` (valor_* optional; > 0 still applies when
  // present). The strictness is the chrome-devtools 2026-10-10 fix --
  // CREATE can't ship a partial cell -- but EDIT must keep accepting
  // "operator didn't touch this modalidad" (the form pre-populates
  // existing values, leaves the rest blank, and submits per-row PUTs
  // only for the present ones).
  const form = useForm<TarifaCreateInput>({
    resolver: zodResolver(
      isUpdate ? tarifaEditSchema : tarifaCreateSchema,
    ) as never,
    defaultValues: {
      uuid_sucursal: sucursalActivaUuid ?? initial?.uuid_sucursal ?? null,
      uuid_tipo_vehiculo: initial?.uuid_tipo_vehiculo ?? null,
      // EDIT pre-populates the valor_* inputs with the wire values
      // (``"3000.0000"`` etc.) but the operator perceives a
      // fractional amount. Re-format to es-CO without decimals so
      // the input shows ``"3.000"`` (operator feedback 2026-10-11).
      // The backend accepts the formatted string the same way (the
      // Zod ``decimalString`` refine matches ``^-?\d+(\.\d+)?$`` and
      // the Pydantic ``Decimal`` parser rounds to 4 decimals on
      // commit), so no information is lost. CREATE keeps the raw
      // ``null`` defaults -- the operator types the fresh value.
      //
      // CRITICAL: the value is the formatted string when the cell has
      // a valor, OR ``null`` when it does not. We do NOT pass
      // ``formatTarifaValor(null)`` (= ``'—'``) as the default -- the
      // ``'—'`` placeholder is a DISPLAY concern, not a form value, and
      // sending it through the schema would fail the
      // ``^-?\d+(\.\d+)?$`` regex. The display layer (``field.value
      // ?? ''``) keeps rendering ``''`` for the empty inputs, which
      // shows the placeholder text and is what the operator expects.
      valor_hora:
        initial?.hora.valor != null
          ? formatTarifaValor(initial.hora.valor)
          : null,
      valor_fraccion:
        initial?.fraccion.valor != null
          ? formatTarifaValor(initial.fraccion.valor)
          : null,
      valor_plena:
        initial?.plena.valor != null
          ? formatTarifaValor(initial.plena.valor)
          : null,
      valor_nocturna:
        initial?.nocturna.valor != null
          ? formatTarifaValor(initial.nocturna.valor)
          : null,
      vigente_desde: defaultVigenteDesde,
    },
  });

  // CREATE-only default-pre-population. The backend rejects null
  // ``uuid_tipo_vehiculo`` with 422, so we must default the select to
  // the first available entry filtered by per-branch in-use set.
  useEffect(() => {
    if (initial !== null) return; // EDIT: tipo locked from initialTarifaAgrupada
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
