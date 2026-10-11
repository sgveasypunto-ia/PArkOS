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
 * Layout (HU-tarifas-popup-redesign, operator feedback 2026-10-11):
 *
 *   1. Contexto: Sucursal (read-only) + Tipo de vehículo
 *      (select / read-only en EDIT).
 *   2. 4 cards en grid 2x2 — una por modalidad canónica
 *      (Hora / Fracción / Plena / Nocturna). Cada card tiene icono +
 *      color de acento + label + input numérico + help text compacto
 *      + dot de validez. La grid colapsa a 1x4 en mobile.
 *   3. Vigente desde (datetime-local).
 *   4. Preview de la celda resultante en vivo: ``{tipo}: Hora 3.000 ·
 *      Fracción — · Plena — · Nocturna —``. ``aria-live="polite"`` para
 *      screen readers. Si todos los valores están vacíos, muestra un
 *      helper "Ingresá al menos un valor".
 *   5. Editing notice (sólo en EDIT).
 *   6. Footer: Cancelar / submit (Crear o Actualizar).
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
 *     the modalidad). The 4-input UX is preserved for ergonomic
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
  MODALIDAD_META,
  type ModalidadKey,
} from '../lib/modalidadMeta';

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
        {/* Contexto: sucursal y tipo de vehículo, no editables. */}
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

        {/* 4 cards en grid 2x2, una por modalidad (Hora / Fracción /
            Plena / Nocturna). Cada card tiene icono + color de acento +
            label + input numérico + help text compacto. La grid colapsa
            a 1x4 en mobile. Los data-testid ``tarifa-field-valor-*`` se
            mantienen en el <Input> interno para que los tests
            preexistentes no se rompan. */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {(Object.keys(MODALIDAD_META) as ModalidadKey[]).map((key) => (
            <ValorModalidadCard key={key} form={form} modalidadKey={key} />
          ))}
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

        {/* Preview de la celda resultante (HU-tarifas-popup-redesign,
            operator feedback 2026-10-11). El operador ve la celda
            que va a quedar ANTES de hacer click en Crear/Actualizar.
            ``aria-live="polite"`` anuncia los cambios al tipear para
            usuarios de screen reader. Si todos los valores están
            vacíos, muestra el mensaje "Ingresá al menos un valor" para
            explicar por qué el preview está vacío. */}
        <TarifaCellPreview form={form} tiposVehiculo={tiposVehiculo} />

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

/**
 * Internal presentational card for one ``valor_*`` input.
 *
 * Renders the metadata for one of the 4 canonical modalidades (icon
 * + accent color + label + placeholder + help text) and wires the
 * numeric input to the form. Internal to this file because it has
 * no other consumer; if a sibling page ever needs the same card
 * (e.g. cupos for some "valor" field), extract it then.
 */
function ValorModalidadCard({
  form,
  modalidadKey,
}: {
  form: UseFormReturn<TarifaCreateInput>;
  modalidadKey: ModalidadKey;
}): JSX.Element {
  // No i18n needed for the card header (the modalidad labels are
  // already localised in MODALIDAD_META itself).
  const meta = MODALIDAD_META[modalidadKey];
  const Icon = meta.icon;
  // ``fieldName`` maps the modalidad key to the form field name.
  // The form schema has 4 ``valor_*`` fields, one per key.
  const fieldName = (
    {
      hora: 'valor_hora',
      fraccion: 'valor_fraccion',
      plena: 'valor_plena',
      nocturna: 'valor_nocturna',
    } as const
  )[modalidadKey];
  const inputId = fieldName;
  return (
    <FormField
      control={form.control}
      name={fieldName}
      render={({ field, fieldState }) => {
        const raw = field.value;
        const filled = typeof raw === 'string' && raw.length > 0;
        const num = filled ? Number(raw) : NaN;
        const isValid = filled && Number.isFinite(num) && num > 0;
        // Indicate validity via the left border color + the dot next
        // to the label. Invalid (0 / negative / non-numeric) is
        // amber, filled+valid is green, empty is muted.
        const borderClass = !filled
          ? 'border-l-muted-foreground/30'
          : isValid
            ? 'border-l-emerald-500'
            : 'border-l-amber-500';
        const dotClass = !filled
          ? 'bg-muted-foreground/40'
          : isValid
            ? 'bg-emerald-500'
            : 'bg-amber-500';
        return (
          <FormItem>
            <div
              className={`flex flex-col gap-2 rounded-md border border-l-4 bg-card p-3 ${borderClass}`}
              data-testid={`tarifa-card-${modalidadKey}`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded-md ${meta.accent}`}
                  aria-hidden="true"
                >
                  <Icon className="h-4 w-4" />
                </span>
                <FormLabel
                  htmlFor={inputId}
                  className="flex-1 text-sm font-medium"
                >
                  {meta.label}
                </FormLabel>
                <span
                  className={`h-2 w-2 rounded-full ${dotClass}`}
                  aria-hidden="true"
                />
              </div>
              <FormControl>
                <Input
                  id={inputId}
                  data-testid={`tarifa-field-valor-${modalidadKey}`}
                  type="number"
                  step="0.0001"
                  min="0"
                  placeholder={meta.placeholder}
                  aria-required="true"
                  className="font-mono"
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) =>
                    field.onChange(
                      e.target.value === '' ? null : e.target.value,
                    )
                  }
                />
              </FormControl>
              <FormDescription className="text-xs">
                {meta.help}
                {fieldState.error?.message && (
                  <span className="text-destructive">
                    {' '}
                    · {fieldState.error.message}
                  </span>
                )}
              </FormDescription>
            </div>
            <FormMessage />
          </FormItem>
        );
      }}
    />
  );
}

/**
 * Internal presentational block that shows the cell the operator is
 * about to commit: ``{tipo_vehiculo_label}: Hora 3.000 · Fracción — · Plena — · Nocturna —``.
 *
 * Uses ``useWatch`` on the 4 valor_* fields and the
 * uuid_tipo_vehiculo so the preview updates live as the operator
 * types. Empty modalidad values render as ``—`` (the existing
 * display sentinel). When ALL 4 are empty, shows a helper message
 * instead of a bare row of dashes.
 */
function TarifaCellPreview({
  form,
  tiposVehiculo,
}: {
  form: UseFormReturn<TarifaCreateInput>;
  tiposVehiculo: TipoVehiculo[];
}): JSX.Element {
  const { t } = useTranslation();
  const watchedValores = useWatch({
    control: form.control,
    name: [
      'valor_hora',
      'valor_fraccion',
      'valor_plena',
      'valor_nocturna',
    ],
  });
  const watchedTipoVehiculoUuid = useWatch({
    control: form.control,
    name: 'uuid_tipo_vehiculo',
  });
  const [vh, vfr, vpl, vno] = Array.isArray(watchedValores)
    ? watchedValores
    : [null, null, null, null];
  const tipoLabel =
    tiposVehiculo.find((tv) => tv.uuid === watchedTipoVehiculoUuid)?.tipo ??
    watchedTipoVehiculoUuid ??
    '';
  const items: Array<{ key: ModalidadKey; raw: unknown }> = [
    { key: 'hora', raw: vh },
    { key: 'fraccion', raw: vfr },
    { key: 'plena', raw: vpl },
    { key: 'nocturna', raw: vno },
  ];
  const anyFilled = items.some(
    ({ raw }) => typeof raw === 'string' && raw.length > 0,
  );
  return (
    <div
      className="rounded-md border bg-muted/30 p-3"
      data-testid="tarifa-form-preview"
      aria-live="polite"
    >
      <div className="mb-1.5 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <span>{t('tarifas.form.previewTitle', 'Resultado')}</span>
        {tipoLabel && (
          <span className="rounded bg-background px-1.5 py-0.5 text-foreground normal-case tracking-normal">
            {tipoLabel}
          </span>
        )}
      </div>
      {anyFilled ? (
        <ul
          className="flex flex-wrap gap-x-3 gap-y-1 text-sm"
          data-testid="tarifa-form-preview-items"
        >
          {items.map(({ key, raw }) => {
            const meta = MODALIDAD_META[key];
            const filled = typeof raw === 'string' && raw.length > 0;
            return (
              <li
                key={key}
                className="flex items-center gap-1.5"
                data-testid={`tarifa-form-preview-${key}`}
              >
                <span className={`${meta.accent} font-medium`}>
                  {meta.label}:
                </span>
                <span
                  className={
                    filled
                      ? 'font-mono font-medium'
                      : 'text-muted-foreground'
                  }
                >
                  {filled ? formatTarifaValor(raw as string) : '—'}
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p
          className="text-xs text-muted-foreground"
          data-testid="tarifa-form-preview-empty"
        >
          {t(
            'tarifas.form.previewEmpty',
            'Ingresá al menos un valor para ver el resultado.',
          )}
        </p>
      )}
    </div>
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
  // with server-now) for ~60s. The fix: unified ``now+0`` for both
  // modes. The backend still has a monotonicity guard (rejects
  // ``nueva_desde < current.vigente_desde`` with 409) and
  // ``close_and_insert`` closes the old row with
  // ``vigente_hasta = nueva_desde`` and opens the new one at the
  // same instant -- no gap, no phantom future row.
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
