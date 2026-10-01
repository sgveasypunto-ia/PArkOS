/**
 * `<SucursalCaja />` — tab "Caja" de `SucursalDetalle.tsx` (HU-F15.5,
 * CU-13 completo).
 *
 * Una pantalla, DOS secciones/formularios independientes:
 *   1. "Base y redondeo" — `configuracion_caja` (HU-F13.3). Fuente:
 *      `GET .../configuracion-caja/efectiva?uuid_sucursal=…`, la ruta
 *      real que ya resuelve override-por-sucursal U default global
 *      server-side (ver `configuracionCajaApi.ts`).
 *   2. "Tolerancias de arqueo" — `configuracion_tolerancias`. Fuente:
 *      el hook y el cliente API YA EXISTENTES de
 *      `features/configuracion-tolerancias/` (no hay ruta
 *      `.../efectiva` para esta tabla — se reutiliza el mismo patrón de
 *      resolución client-side que ya usa `ConfiguracionTolerancias.tsx`).
 *
 * BR4 (enlace a "ver/editar el default global" cuando la sucursal no
 * tiene override propio):
 *   - Tolerancias: link real a `/configuracion-tolerancias` (la pantalla
 *     admin ya existe y ya edita la fila global).
 *   - Caja: NO existe todavía una pantalla admin para el default global
 *     de esta tabla (HU-F13.3 entregó la tabla + endpoints, sin UI).
 *     Crear una pantalla/ruta nueva es alcance fuera de esta HU (la
 *     tabla de tareas solo pide `SucursalCaja.tsx`), así que BR4 se
 *     resuelve acá con un toggle inline que cambia el MISMO formulario
 *     entre editar el override de esta sucursal y editar el default
 *     global (`uuid_sucursal: null`), sin salir de la pestaña.
 *
 * BR1: "base inicial sugerida" prellena la apertura de turno en
 * `web_sucursal` (otra app) — esta pantalla no toca
 * `sesion.valor_inicial_efectivo` / `valor_inicial_datafono`.
 * BR2: cambiar la base con una jornada activa está permitido; el PUT
 * hace close+insert bi-temporal en el backend (mismo patrón que
 * tarifas/tolerancias) — nada especial que hacer acá.
 * BR3: un umbral inválido se rechaza con 422 backend + Zod frontend
 * (`>= 0` en los dos montos, enteros positivos en denominaciones).
 */
import { useState } from 'react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
  createConfiguracionCaja,
  updateConfiguracionCaja,
} from '@/features/configuracion-caja/api/configuracionCajaApi';
import {
  configuracionCajaCreateSchema,
  type ConfiguracionCaja,
  type ConfiguracionCajaCreateInput,
  type Redondeo,
} from '@/features/configuracion-caja/api/configuracionCajaSchema';
import { useConfiguracionCajaEfectiva } from '@/features/configuracion-caja/hooks/useConfiguracionCajaEfectiva';

import {
  createConfiguracionTolerancias,
  updateConfiguracionTolerancias,
} from '@/features/configuracion-tolerancias/api/configuracionToleranciasApi';
import {
  configuracionToleranciasCreateSchema,
  type ConfiguracionToleranciasCreateInput,
} from '@/features/configuracion-tolerancias/api/configuracionToleranciasSchema';
import { useConfiguracionTolerancias } from '@/features/configuracion-tolerancias/hooks/useConfiguracionTolerancias';

export interface SucursalCajaProps {
  uuidSucursal: string;
}

// ---------------------------------------------------------------------
// Sección 1 — "Base y redondeo" (configuracion_caja)
// ---------------------------------------------------------------------

type CajaEditTarget = 'override' | 'global';

function cajaDefaultsFromRow(
  row: ConfiguracionCaja | null,
  uuidSucursalDestino: string | null,
): ConfiguracionCajaCreateInput {
  return {
    uuid_sucursal: uuidSucursalDestino,
    base_inicial_sugerida: row?.base_inicial_sugerida ?? null,
    redondeo: (row?.redondeo ?? null) as Redondeo | null,
    denominaciones_permitidas: row?.denominaciones_permitidas?.map(String) ?? null,
  };
}

function DenominacionesInput({
  field,
}: {
  field: {
    value: string[] | null;
    onChange: (value: string[] | null) => void;
  };
}): JSX.Element {
  const [text, setText] = useState<string>(field.value?.join(', ') ?? '');
  return (
    <Input
      id="caja-denominaciones"
      data-testid="sucursal-caja-base-field-denominaciones"
      placeholder="1000, 2000, 5000, 10000"
      value={text}
      onChange={(e) => {
        const raw = e.target.value;
        setText(raw);
        const tokens = raw
          .split(',')
          .map((token) => token.trim())
          .filter((token) => token.length > 0);
        field.onChange(tokens.length > 0 ? tokens : null);
      }}
    />
  );
}

interface CajaBaseRedondeoFormProps {
  defaultValues: ConfiguracionCajaCreateInput;
  isUpdate: boolean;
  isSubmitting: boolean;
  onSubmit: (values: ConfiguracionCajaCreateInput) => void;
}

function CajaBaseRedondeoForm({
  defaultValues,
  isUpdate,
  isSubmitting,
  onSubmit,
}: CajaBaseRedondeoFormProps): JSX.Element {
  const { t } = useTranslation();
  const form: UseFormReturn<ConfiguracionCajaCreateInput> = useForm<ConfiguracionCajaCreateInput>({
    resolver: zodResolver(configuracionCajaCreateSchema) as never,
    defaultValues,
  });

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="sucursal-caja-base-form"
      >
        <FormField
          control={form.control}
          name="base_inicial_sugerida"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="caja-base-inicial">
                {t('sucursalCaja.base.field.baseInicial', 'Base inicial sugerida (COP)')}
              </FormLabel>
              <FormControl>
                <Input
                  id="caja-base-inicial"
                  data-testid="sucursal-caja-base-field-base-inicial"
                  type="number"
                  step="0.0001"
                  min="0"
                  placeholder="100000"
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) =>
                    field.onChange(e.target.value === '' ? null : e.target.value)
                  }
                />
              </FormControl>
              <FormDescription>
                {t(
                  'sucursalCaja.base.field.baseInicialHelp',
                  'Valor sugerido que web_sucursal prellena al abrir un turno. No modifica sesiones ya abiertas (BR1). Debe ser >= 0.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="redondeo"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="caja-redondeo">
                {t('sucursalCaja.base.field.redondeo', 'Redondeo')}
              </FormLabel>
              <FormControl>
                <select
                  id="caja-redondeo"
                  data-testid="sucursal-caja-base-field-redondeo"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  value={field.value ?? ''}
                  onChange={(e) => field.onChange(e.target.value === '' ? null : e.target.value)}
                >
                  <option value="">
                    {t('sucursalCaja.base.redondeo.sinConfigurar', 'Sin configurar')}
                  </option>
                  <option value="ninguno">
                    {t('sucursalCaja.base.redondeo.ninguno', 'Ninguno')}
                  </option>
                  <option value="100">100</option>
                  <option value="500">500</option>
                  <option value="1000">1000</option>
                </select>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="denominaciones_permitidas"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="caja-denominaciones">
                {t('sucursalCaja.base.field.denominaciones', 'Denominaciones permitidas')}
              </FormLabel>
              <FormControl>
                <DenominacionesInput field={field} />
              </FormControl>
              <FormDescription>
                {t(
                  'sucursalCaja.base.field.denominacionesHelp',
                  'Enteros positivos separados por coma.',
                )}
              </FormDescription>
              <FormMessage data-testid="sucursal-caja-base-denominaciones-error" />
            </FormItem>
          )}
        />

        {isUpdate && (
          <p
            className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
            data-testid="sucursal-caja-base-form-editing-notice"
          >
            {t(
              'sucursalCaja.base.editingNotice',
              'Estás editando una configuración existente. El cambio publica una nueva versión; la anterior se cierra automáticamente (BR2).',
            )}
          </p>
        )}

        <div className="flex items-center justify-end gap-2 pt-2">
          <Button type="submit" disabled={isSubmitting} data-testid="sucursal-caja-base-submit">
            {isSubmitting
              ? t('sucursalCaja.form.submitting', 'Guardando…')
              : isUpdate
                ? t('sucursalCaja.form.update', 'Actualizar')
                : t('sucursalCaja.form.create', 'Crear')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

function SucursalCajaBaseSection({ uuidSucursal }: { uuidSucursal: string }): JSX.Element {
  const { t } = useTranslation();
  const { data, isLoading, error, refresh } = useConfiguracionCajaEfectiva(uuidSucursal);
  const [editTarget, setEditTarget] = useState<CajaEditTarget>('override');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  if (isLoading) {
    return (
      <p
        role="status"
        data-testid="sucursal-caja-base-loading"
        className="text-sm text-muted-foreground"
      >
        {t('sucursalCaja.base.loading', 'Cargando configuración de caja…')}
      </p>
    );
  }

  if (error) {
    return (
      <p
        role="alert"
        data-testid="sucursal-caja-base-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {t('sucursalCaja.base.loadError', 'No se pudo cargar la configuración de caja.')}
      </p>
    );
  }

  // `data` ya es el resultado de `.../efectiva`: override de ESTA
  // sucursal, o el default global, o `null` si ninguno existe.
  const tieneOverridePropio = data !== null && data !== undefined && data.uuid_sucursal === uuidSucursal;
  const existeGlobal = data !== null && data !== undefined && data.uuid_sucursal === null;
  // El toggle solo tiene sentido cuando esta sucursal NO tiene override
  // propio todavía (BR4); si ya lo tiene, siempre se edita el override.
  const effectiveEditTarget: CajaEditTarget = tieneOverridePropio ? 'override' : editTarget;
  const isUpdate = effectiveEditTarget === 'override' ? tieneOverridePropio : existeGlobal;
  const targetUuid =
    effectiveEditTarget === 'override'
      ? (tieneOverridePropio ? (data as ConfiguracionCaja).uuid : null)
      : (existeGlobal ? (data as ConfiguracionCaja).uuid : null);

  const defaultValues = cajaDefaultsFromRow(
    data ?? null,
    effectiveEditTarget === 'override' ? uuidSucursal : null,
  );

  async function onSubmit(values: ConfiguracionCajaCreateInput): Promise<void> {
    setSubmitting(true);
    setSubmitError(null);
    // Defense in depth (mismo patrón que TarifaForm/CupoForm): el scope
    // se fija acá, no se confía en lo que el formulario haya cargado.
    const payload: ConfiguracionCajaCreateInput = {
      ...values,
      uuid_sucursal: effectiveEditTarget === 'override' ? uuidSucursal : null,
    };
    try {
      if (isUpdate && targetUuid) {
        await updateConfiguracionCaja(targetUuid, payload);
      } else {
        await createConfiguracionCaja(payload);
      }
      await refresh();
      if (effectiveEditTarget === 'global') {
        setEditTarget('override');
      }
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Error desconocido');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-3" data-testid="sucursal-caja-base-root">
      {data === null && (
        <p
          role="status"
          data-testid="sucursal-caja-base-sin-configurar"
          className="rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
        >
          {t(
            'sucursalCaja.base.sinConfigurar',
            'Todavía no hay una configuración de caja para esta sucursal (ni override propio ni default global). Configurá primero el default global.',
          )}
        </p>
      )}

      {data !== null && !tieneOverridePropio && (
        <p
          role="status"
          data-testid="sucursal-caja-base-sin-override"
          className="rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
        >
          {t(
            'sucursalCaja.base.sinOverride',
            'Esta sucursal no tiene override propio. Mostrando el default global efectivo.',
          )}
        </p>
      )}

      {tieneOverridePropio && (
        <p
          data-testid="sucursal-caja-base-editing-override"
          className="text-xs text-muted-foreground"
        >
          {t('sucursalCaja.base.editingOverride', 'Editando el override de esta sucursal.')}
        </p>
      )}

      {!tieneOverridePropio && effectiveEditTarget === 'global' && (
        <p
          data-testid="sucursal-caja-base-editing-global"
          className="text-xs text-muted-foreground"
        >
          {t(
            'sucursalCaja.base.editingGlobal',
            'Editando el default global — aplica a toda sucursal sin override propio.',
          )}
        </p>
      )}

      {!tieneOverridePropio && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          data-testid={
            editTarget === 'override'
              ? 'sucursal-caja-base-toggle-global'
              : 'sucursal-caja-base-toggle-override'
          }
          onClick={() => setEditTarget(editTarget === 'override' ? 'global' : 'override')}
        >
          {editTarget === 'override'
            ? t('sucursalCaja.base.toggleGlobal', 'Ver/editar el default global')
            : t('sucursalCaja.base.toggleOverride', 'Volver al override de esta sucursal')}
        </Button>
      )}

      <CajaBaseRedondeoForm
        key={`${effectiveEditTarget}-${targetUuid ?? 'create'}`}
        defaultValues={defaultValues}
        isUpdate={isUpdate}
        isSubmitting={submitting}
        onSubmit={onSubmit}
      />

      {submitError && (
        <p
          role="alert"
          data-testid="sucursal-caja-base-submit-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {submitError}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
// Sección 2 — "Tolerancias de arqueo" (configuracion_tolerancias)
// ---------------------------------------------------------------------

interface CajaToleranciasFormProps {
  defaultValues: ConfiguracionToleranciasCreateInput;
  isUpdate: boolean;
  isSubmitting: boolean;
  onSubmit: (values: ConfiguracionToleranciasCreateInput) => void;
}

function CajaToleranciasForm({
  defaultValues,
  isUpdate,
  isSubmitting,
  onSubmit,
}: CajaToleranciasFormProps): JSX.Element {
  const { t } = useTranslation();
  const form = useForm<ConfiguracionToleranciasCreateInput>({
    resolver: zodResolver(configuracionToleranciasCreateSchema) as never,
    defaultValues,
  });

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="sucursal-caja-tolerancias-form"
      >
        <FormField
          control={form.control}
          name="tolerancia_efectivo"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="caja-tolerancia-efectivo">
                {t('sucursalCaja.tolerancias.field.efectivo', 'Tolerancia de efectivo (COP)')}
              </FormLabel>
              <FormControl>
                <Input
                  id="caja-tolerancia-efectivo"
                  data-testid="sucursal-caja-tolerancias-field-efectivo"
                  type="number"
                  step="0.0001"
                  min="0"
                  placeholder="100"
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) =>
                    field.onChange(e.target.value === '' ? null : e.target.value)
                  }
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="tolerancia_datafono"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="caja-tolerancia-datafono">
                {t('sucursalCaja.tolerancias.field.datafono', 'Tolerancia de datáfono (COP)')}
              </FormLabel>
              <FormControl>
                <Input
                  id="caja-tolerancia-datafono"
                  data-testid="sucursal-caja-tolerancias-field-datafono"
                  type="number"
                  step="0.0001"
                  min="0"
                  placeholder="200"
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) =>
                    field.onChange(e.target.value === '' ? null : e.target.value)
                  }
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {isUpdate && (
          <p
            className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
            data-testid="sucursal-caja-tolerancias-form-editing-notice"
          >
            {t(
              'sucursalCaja.tolerancias.editingNotice',
              'Estás editando una configuración existente. El cambio publica una nueva versión; la anterior se cierra automáticamente.',
            )}
          </p>
        )}

        <div className="flex items-center justify-end gap-2 pt-2">
          <Button
            type="submit"
            disabled={isSubmitting}
            data-testid="sucursal-caja-tolerancias-submit"
          >
            {isSubmitting
              ? t('sucursalCaja.form.submitting', 'Guardando…')
              : isUpdate
                ? t('sucursalCaja.form.update', 'Actualizar')
                : t('sucursalCaja.form.create', 'Crear')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

function SucursalCajaToleranciasSection({ uuidSucursal }: { uuidSucursal: string }): JSX.Element {
  const { t } = useTranslation();
  const { rows, isLoading, error, refresh } = useConfiguracionTolerancias();
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  if (isLoading && rows.length === 0) {
    return (
      <p
        role="status"
        data-testid="sucursal-caja-tolerancias-loading"
        className="text-sm text-muted-foreground"
      >
        {t('sucursalCaja.tolerancias.loading', 'Cargando tolerancias…')}
      </p>
    );
  }

  if (error) {
    return (
      <p
        role="alert"
        data-testid="sucursal-caja-tolerancias-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {t('sucursalCaja.tolerancias.loadError', 'No se pudieron cargar las tolerancias.')}
      </p>
    );
  }

  const globalRow = rows.find((r) => r.uuid_sucursal === null) ?? null;
  const overrideRow = rows.find((r) => r.uuid_sucursal === uuidSucursal) ?? null;
  const efectivo = overrideRow ?? globalRow;
  const isUpdate = overrideRow !== null;

  const defaultValues: ConfiguracionToleranciasCreateInput = {
    uuid_sucursal: uuidSucursal,
    tolerancia_efectivo: efectivo?.tolerancia_efectivo ?? null,
    tolerancia_datafono: efectivo?.tolerancia_datafono ?? null,
  };

  async function onSubmit(values: ConfiguracionToleranciasCreateInput): Promise<void> {
    setSubmitting(true);
    setSubmitError(null);
    const payload: ConfiguracionToleranciasCreateInput = { ...values, uuid_sucursal: uuidSucursal };
    try {
      if (overrideRow !== null) {
        await updateConfiguracionTolerancias(overrideRow.uuid, payload);
      } else {
        await createConfiguracionTolerancias(payload);
      }
      await refresh();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Error desconocido');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-3" data-testid="sucursal-caja-tolerancias-root">
      {efectivo === null && (
        <p
          role="status"
          data-testid="sucursal-caja-tolerancias-sin-configurar"
          className="rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
        >
          {t(
            'sucursalCaja.tolerancias.sinConfigurar',
            'Todavía no hay tolerancias para esta sucursal (ni override propio ni default global).',
          )}
        </p>
      )}

      {efectivo !== null && !isUpdate && (
        <p
          role="status"
          data-testid="sucursal-caja-tolerancias-sin-override"
          className="rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
        >
          {t(
            'sucursalCaja.tolerancias.sinOverride',
            'Esta sucursal no tiene override propio. Mostrando el default global efectivo.',
          )}
        </p>
      )}

      {isUpdate && (
        <p
          data-testid="sucursal-caja-tolerancias-editing-override"
          className="text-xs text-muted-foreground"
        >
          {t('sucursalCaja.tolerancias.editingOverride', 'Editando el override de esta sucursal.')}
        </p>
      )}

      {!isUpdate && (
        <Link
          to="/configuracion-tolerancias"
          data-testid="sucursal-caja-tolerancias-link-global"
          className="inline-block text-sm text-primary underline underline-offset-2"
        >
          {t('sucursalCaja.tolerancias.linkGlobal', 'Ver/editar el default global')}
        </Link>
      )}

      <CajaToleranciasForm
        key={isUpdate ? (overrideRow as NonNullable<typeof overrideRow>).uuid : 'create'}
        defaultValues={defaultValues}
        isUpdate={isUpdate}
        isSubmitting={submitting}
        onSubmit={onSubmit}
      />

      {submitError && (
        <p
          role="alert"
          data-testid="sucursal-caja-tolerancias-submit-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {submitError}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
// Pantalla
// ---------------------------------------------------------------------

export function SucursalCaja({ uuidSucursal }: SucursalCajaProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <div className="space-y-6" data-testid="sucursal-caja-root">
      <Card data-testid="sucursal-caja-base-card">
        <CardHeader>
          <CardTitle>{t('sucursalCaja.base.title', 'Base y redondeo')}</CardTitle>
        </CardHeader>
        <CardContent>
          <SucursalCajaBaseSection uuidSucursal={uuidSucursal} />
        </CardContent>
      </Card>

      <Card data-testid="sucursal-caja-tolerancias-card">
        <CardHeader>
          <CardTitle>{t('sucursalCaja.tolerancias.title', 'Tolerancias de arqueo')}</CardTitle>
        </CardHeader>
        <CardContent>
          <SucursalCajaToleranciasSection uuidSucursal={uuidSucursal} />
        </CardContent>
      </Card>
    </div>
  );
}

export default SucursalCaja;
