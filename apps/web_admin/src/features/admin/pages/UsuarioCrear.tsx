/**
 * `<UsuarioCrear />` — 3-step creation wizard (HU-F16.2), mounted inline
 * inside the "Crear nuevo usuario" modal in `UsuariosList.tsx`.
 *
 * Replaces the single-shot `AdminUsuarioForm` for the CREATE flow only
 * (decision already made for HU-F16.2): `DatosPersonalesStep` ->
 * `RolStep` -> `SucursalesStep`. EDITING an existing user is a
 * completely separate screen/component (`UsuarioDetalle.tsx` +
 * `UsuarioForm.tsx` under `features/usuarios/`, reachable at
 * `/usuarios/{uuid}`) and is untouched by this change.
 *
 * No external wizard library: `apps/web_admin` had no multi-step
 * pattern to follow (grepped for "wizard"/"step" before writing this),
 * so this uses plain `useState<Step>` for the current step + one
 * independent `useForm` + `zodResolver` per step (mirrors the
 * `AdminUsuarioForm` Container/Presentational precedent). Each step's
 * values are lifted into the parent's state on "Siguiente" so
 * navigating back preserves what was typed.
 *
 * The three step schemas (`datosPersonalesStepSchema`, `rolStepSchema`,
 * `sucursalesStepSchema`) all `.pick()` off `adminUsuarioCreateSchema`
 * (the schema already mirroring the backend's
 * `AdminUsuarioCreateRequest`), so the wizard can never validate a rule
 * that disagrees with the single POST the final step fires.
 *
 * Error handling (HU-F16.2 "errores inline en el paso correspondiente"):
 * the real backend (`repo/admin_usuarios.py::create_admin_usuario`) does
 * NOT implement a typed `cedula_duplicada` / `email_duplicado` 422 today
 * — there is no uniqueness check on `email` at all, and the `cedula`
 * unique constraint is keyed on `(cedula, vigente_desde)`, which a
 * same-millisecond duplicate almost never hits. `plan.md`'s described
 * error codes are therefore aspirational, not part of the real
 * contract. Rather than invent a per-field 422 parser against an
 * interface that does not exist, `submitError` renders as a single
 * generic alert on the SUCURSALES step (the step whose button actually
 * fires the request) — the same shape `UsuariosList.tsx` already used
 * for the previous single-step form's error state.
 */
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
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
  ROLES,
  datosPersonalesStepSchema,
  rolStepSchema,
  sucursalesStepSchema,
  type AdminUsuarioCreateInput,
  type DatosPersonalesStepInput,
  type RolStepInput,
  type SucursalesStepInput,
} from '../api/adminUsuarioSchema';

export interface UsuarioCrearProps {
  onSubmit: (values: AdminUsuarioCreateInput) => void;
  isSubmitting: boolean;
  availableBranches: { uuid: string; nombre: string | null }[];
  /** Generic submit error (see module docblock for why it is generic). */
  submitError: string | null;
}

type Step = 1 | 2 | 3;

const DATOS_DEFAULTS: DatosPersonalesStepInput = {
  email: '',
  password: '',
  nombre: '',
  apellido: '',
  cedula: '',
};

const ROL_DEFAULTS: RolStepInput = { rol: 'operador' };

const SUCURSALES_DEFAULTS: SucursalesStepInput = { sucursales_asignadas: [] };

export function UsuarioCrear({
  onSubmit,
  isSubmitting,
  availableBranches,
  submitError,
}: UsuarioCrearProps): JSX.Element {
  const { t } = useTranslation();
  const [step, setStep] = useState<Step>(1);
  const [datosPersonales, setDatosPersonales] =
    useState<DatosPersonalesStepInput>(DATOS_DEFAULTS);
  const [rol, setRol] = useState<RolStepInput>(ROL_DEFAULTS);

  function handleDatosNext(values: DatosPersonalesStepInput): void {
    setDatosPersonales(values);
    setStep(2);
  }

  function handleRolNext(values: RolStepInput): void {
    setRol(values);
    setStep(3);
  }

  function handleSucursalesSubmit(values: SucursalesStepInput): void {
    onSubmit({ ...datosPersonales, ...rol, ...values });
  }

  return (
    <div data-testid="usuario-crear-wizard">
      <ol
        className="mb-4 flex items-center gap-2 text-xs text-muted-foreground"
        aria-label={t('gestionUsuarios.wizard.progressLabel', 'Progreso del asistente')}
      >
        {[
          [1, t('gestionUsuarios.wizard.step1Title', 'Datos personales')],
          [2, t('gestionUsuarios.wizard.step2Title', 'Rol')],
          [3, t('gestionUsuarios.wizard.step3Title', 'Sucursales')],
        ].map(([n, label]) => (
          <li
            key={n}
            aria-current={step === n ? 'step' : undefined}
            className={
              step === n
                ? 'rounded-full bg-primary px-2 py-1 font-medium text-primary-foreground'
                : 'rounded-full bg-muted px-2 py-1'
            }
          >
            {n}. {label}
          </li>
        ))}
      </ol>

      {step === 1 && (
        <DatosPersonalesStep defaultValues={datosPersonales} onNext={handleDatosNext} />
      )}
      {step === 2 && (
        <RolStep
          defaultValues={rol}
          onBack={() => setStep(1)}
          onNext={handleRolNext}
        />
      )}
      {step === 3 && (
        <SucursalesStep
          availableBranches={availableBranches}
          isSubmitting={isSubmitting}
          submitError={submitError}
          onBack={() => setStep(2)}
          onSubmit={handleSucursalesSubmit}
        />
      )}
    </div>
  );
}

function DatosPersonalesStep({
  defaultValues,
  onNext,
}: {
  defaultValues: DatosPersonalesStepInput;
  onNext: (values: DatosPersonalesStepInput) => void;
}): JSX.Element {
  const { t } = useTranslation();
  const form = useForm<DatosPersonalesStepInput>({
    resolver: zodResolver(datosPersonalesStepSchema),
    defaultValues,
  });

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onNext)}
        className="space-y-4"
        noValidate
        data-testid="wizard-step-datos"
      >
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="wizard-email">{t('admin.email')}</FormLabel>
              <FormControl>
                <Input
                  id="wizard-email"
                  type="email"
                  autoComplete="username"
                  data-testid="wizard-field-email"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="wizard-password">{t('admin.password')}</FormLabel>
              <FormControl>
                <Input
                  id="wizard-password"
                  type="password"
                  autoComplete="new-password"
                  data-testid="wizard-field-password"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>{t('admin.passwordHelp')}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="nombre"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="wizard-nombre">{t('admin.nombre')}</FormLabel>
              <FormControl>
                <Input
                  id="wizard-nombre"
                  data-testid="wizard-field-nombre"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="apellido"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="wizard-apellido">{t('admin.apellido')}</FormLabel>
              <FormControl>
                <Input
                  id="wizard-apellido"
                  data-testid="wizard-field-apellido"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="cedula"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="wizard-cedula">{t('admin.cedula')}</FormLabel>
              <FormControl>
                <Input
                  id="wizard-cedula"
                  data-testid="wizard-field-cedula"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex justify-end">
          <Button type="submit" data-testid="wizard-step1-next">
            {t('gestionUsuarios.wizard.next', 'Siguiente')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

function RolStep({
  defaultValues,
  onBack,
  onNext,
}: {
  defaultValues: RolStepInput;
  onBack: () => void;
  onNext: (values: RolStepInput) => void;
}): JSX.Element {
  const { t } = useTranslation();
  const form = useForm<RolStepInput>({
    resolver: zodResolver(rolStepSchema),
    defaultValues,
  });

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onNext)}
        className="space-y-4"
        noValidate
        data-testid="wizard-step-rol"
      >
        <FormField
          control={form.control}
          name="rol"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="wizard-rol">{t('admin.rol')}</FormLabel>
              <FormControl>
                <select
                  id="wizard-rol"
                  data-testid="wizard-field-rol"
                  {...field}
                  value={field.value ?? 'operador'}
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {t(`admin.rol.${r}`)}
                    </option>
                  ))}
                </select>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex justify-between">
          <Button
            type="button"
            variant="outline"
            onClick={onBack}
            data-testid="wizard-step2-back"
          >
            {t('gestionUsuarios.wizard.back', 'Atrás')}
          </Button>
          <Button type="submit" data-testid="wizard-step2-next">
            {t('gestionUsuarios.wizard.next', 'Siguiente')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

function SucursalesStep({
  availableBranches,
  isSubmitting,
  submitError,
  onBack,
  onSubmit,
}: {
  availableBranches: { uuid: string; nombre: string | null }[];
  isSubmitting: boolean;
  submitError: string | null;
  onBack: () => void;
  onSubmit: (values: SucursalesStepInput) => void;
}): JSX.Element {
  const { t } = useTranslation();
  const form = useForm<SucursalesStepInput>({
    resolver: zodResolver(sucursalesStepSchema),
    defaultValues: SUCURSALES_DEFAULTS,
  });

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="wizard-step-sucursales"
      >
        {submitError !== null && (
          <p
            role="alert"
            aria-live="assertive"
            className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            data-testid="wizard-submit-error"
          >
            {submitError}
          </p>
        )}

        <FormDescription>
          {t(
            'gestionUsuarios.wizard.sucursalesHelp',
            'Opcional. Podés asignar sucursales después desde "Asignar sucursales".',
          )}
        </FormDescription>

        <fieldset disabled={isSubmitting} className="space-y-2">
          {availableBranches.length === 0 && (
            <p className="text-xs text-muted-foreground" data-testid="wizard-no-branches">
              {t('admin.noBranchesAvailable')}
            </p>
          )}
          {availableBranches.map((b) => (
            <FormField
              key={b.uuid}
              control={form.control}
              name="sucursales_asignadas"
              render={({ field }) => {
                const value: string[] = Array.isArray(field.value) ? field.value : [];
                const checked = value.includes(b.uuid);
                return (
                  <FormItem className="flex items-center gap-2 space-y-0">
                    <FormControl>
                      <Checkbox
                        id={`wizard-sucursal-${b.uuid}`}
                        data-testid={`wizard-sucursal-${b.uuid}`}
                        checked={checked}
                        onCheckedChange={(isChecked) => {
                          field.onChange(
                            isChecked
                              ? [...value, b.uuid]
                              : value.filter((u) => u !== b.uuid),
                          );
                        }}
                      />
                    </FormControl>
                    <FormLabel
                      htmlFor={`wizard-sucursal-${b.uuid}`}
                      className="cursor-pointer font-normal"
                    >
                      {b.nombre ?? b.uuid}
                    </FormLabel>
                  </FormItem>
                );
              }}
            />
          ))}
        </fieldset>

        <div className="flex justify-between">
          <Button
            type="button"
            variant="outline"
            onClick={onBack}
            disabled={isSubmitting}
            data-testid="wizard-step3-back"
          >
            {t('gestionUsuarios.wizard.back', 'Atrás')}
          </Button>
          <Button type="submit" disabled={isSubmitting} data-testid="wizard-submit">
            {isSubmitting
              ? t('gestionUsuarios.wizard.submitting', 'Creando...')
              : t('gestionUsuarios.wizard.submit', 'Crear usuario')}
          </Button>
        </div>
      </form>
    </Form>
  );
}
