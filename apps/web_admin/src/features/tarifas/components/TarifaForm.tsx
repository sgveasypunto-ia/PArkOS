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
  datetimeLocalToIso,
  isoToDatetimeLocal,
  utcNowPlusMinutesAsIso,
} from '@/lib/datetimeTz';

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
  // The submit button is disabled while the form is invalid (RHF
  // schema requires every ``valor_*`` > 0 and ``vigente_desde``
  // present). The operator's only escape hatch is Cancel -- the
  // chrome-devtools 2026-10-10 bug shipped a partial cell because
  // the button accepted an empty form and the page silently
  // converted nulls to ``'0'``. This is the first line of defense;
  // the schema refine + ``createTarifaBatch`` is the second.
  const { isValid } = form.formState;

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
                    required
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
                    required
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
                    required
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
                    required
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
                    required
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

  // ``vigente_desde`` defaults to "now" (real UTC) in CREATE and
  // "now + 1 minute" in EDIT (the canonical UX rule for /tarifas,
  // matching /cupos). Both go through ``@/lib/datetimeTz`` so the
  // wire format is the canonical ``+00:00`` suffix — never local
  // components mislabeled (the previous code did that for CREATE
  // and broke the boundary check in any non-UTC host).
  const defaultVigenteDesde =
    initial === null
      ? utcNowPlusMinutesAsIso(0)
      : utcNowPlusMinutesAsIso(1);
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
      valor_hora: initial?.hora.valor ?? null,
      valor_fraccion: initial?.fraccion.valor ?? null,
      valor_plena: initial?.plena.valor ?? null,
      valor_nocturna: initial?.nocturna.valor ?? null,
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