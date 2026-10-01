/**
 * `SucursalGeneralForm` — tab "General" de `SucursalDetalle.tsx` (HU-F15.1).
 *
 * Container/presentational split, mirror exacto de
 * `features/empresa/components/EmpresaDatosTab.tsx` (RHF + Zod +
 * shadcn `<Form>`, `useEffect` para re-seedear el form cuando resuelve la
 * sucursal, submit -> `updateSucursal` -> `refresh()`).
 *
 * BR1: los 8 campos editables son EXACTAMENTE las columnas reales del ORM
 * (`models/V/sucursal.py`) -- `nombre`, `direccion`, `telefono`,
 * `prefijo_nombre`, `ciudad`, `horario`, `uuid_tipo_sucursal`,
 * `uuid_empresa`. `uuid_empresa` se auto-completa desde el singleton
 * Empresa (`useEmpresa()`) -- no hay más de una empresa para elegir, así
 * que exponer un selector sería un catálogo de un solo valor. El schema
 * Zod reusado (`sucursalUpdateSchema`) YA es la fuente de verdad del
 * resto de reglas (prefijo UK regex, nombre requerido).
 *
 * `telefono`: BR1 pide formato colombiano básico como aviso NO
 * bloqueante -- a diferencia del NIT de Empresa (que si bloquea el
 * submit), el botón de guardar NUNCA se deshabilita por este campo.
 *
 * BR2/BR3: el botón "Deshabilitar" abre un `<Dialog>` de confirmación
 * (texto explícito de la consecuencia -- no acepta nuevos ingresos,
 * permite salidas) y mapea el 409 tipado
 * (`SucursalDeshabilitarBloqueadoError`) a un mensaje legible en vez de
 * un 409 genérico.
 */
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { Loader2, TriangleAlert } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';

import { useEmpresa } from '@/features/empresa/hooks/useEmpresa';
import { useTipoSucursal } from '@/features/tipo-sucursal/hooks/useTipoSucursal';

import {
  SucursalDeshabilitarBloqueadoError,
  disableSucursal,
  updateSucursal,
} from '../../sucursales/api/sucursalesApi';
import {
  sucursalUpdateSchema,
  type Sucursal,
  type SucursalUpdateInput,
} from '../../sucursales/api/sucursalSchema';

// BR1: "formato colombiano básico" -- móvil (10 dígitos, arranca en 3) o
// fijo (7-8 dígitos), con o sin +57. Aviso NO bloqueante (ver docstring).
const TELEFONO_CO_REGEX = /^(\+?57)?[\s-]?(3\d{9}|[1-8]\d{6,7})$/;

export interface SucursalGeneralFormProps {
  sucursal: Sucursal;
  onUpdated: () => Promise<unknown>;
  /** Called after a successful disable (204) so the parent can refresh
   * and/or redirect. */
  onDeshabilitada: () => Promise<unknown>;
}

export function SucursalGeneralForm({
  sucursal,
  onUpdated,
  onDeshabilitada,
}: SucursalGeneralFormProps): JSX.Element {
  const { t } = useTranslation();
  const { empresa } = useEmpresa();
  const { tipos: tiposSucursal } = useTipoSucursal();

  const [saveError, setSaveError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [disabling, setDisabling] = useState(false);
  const [disableError, setDisableError] = useState<string | null>(null);

  const form = useForm<SucursalUpdateInput>({
    resolver: zodResolver(sucursalUpdateSchema),
    defaultValues: {
      nombre: sucursal.nombre ?? '',
      direccion: sucursal.direccion ?? '',
      telefono: sucursal.telefono ?? '',
      prefijo_nombre: sucursal.prefijo_nombre ?? '',
      ciudad: sucursal.ciudad ?? '',
      horario: sucursal.horario ?? '',
      uuid_tipo_sucursal: sucursal.uuid_tipo_sucursal ?? null,
      uuid_empresa: sucursal.uuid_empresa ?? empresa?.uuid ?? null,
    },
  });

  // Re-seed when the uuid changes (navigating between two branch detail
  // pages reuses the same mounted form in some router setups).
  useEffect(() => {
    form.reset({
      nombre: sucursal.nombre ?? '',
      direccion: sucursal.direccion ?? '',
      telefono: sucursal.telefono ?? '',
      prefijo_nombre: sucursal.prefijo_nombre ?? '',
      ciudad: sucursal.ciudad ?? '',
      horario: sucursal.horario ?? '',
      uuid_tipo_sucursal: sucursal.uuid_tipo_sucursal ?? null,
      uuid_empresa: sucursal.uuid_empresa ?? empresa?.uuid ?? null,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sucursal.uuid]);

  const telefonoValue = form.watch('telefono');
  const telefonoNormalizado = (telefonoValue ?? '').trim();
  const telefonoShowWarning =
    telefonoNormalizado.length > 0 && !TELEFONO_CO_REGEX.test(telefonoNormalizado);

  async function onSubmit(values: SucursalUpdateInput): Promise<void> {
    setSaveError(null);
    try {
      await updateSucursal(sucursal.uuid, {
        ...values,
        uuid_empresa: values.uuid_empresa ?? empresa?.uuid ?? null,
      });
      await onUpdated();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Error desconocido');
    }
  }

  async function handleConfirmDeshabilitar(): Promise<void> {
    setDisabling(true);
    setDisableError(null);
    try {
      await disableSucursal(sucursal.uuid);
      setConfirmOpen(false);
      await onDeshabilitada();
    } catch (err) {
      if (err instanceof SucursalDeshabilitarBloqueadoError) {
        setDisableError(err.message);
      } else {
        setDisableError(err instanceof Error ? err.message : 'Error desconocido');
      }
    } finally {
      setDisabling(false);
    }
  }

  const isSubmitting = form.formState.isSubmitting;

  return (
    <div className="space-y-6" data-testid="sucursal-general-form-root">
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="space-y-4"
          noValidate
          aria-busy={isSubmitting}
          data-testid="sucursal-general-form"
        >
          <FormField
            control={form.control}
            name="nombre"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="sucursal-nombre">
                  {t('sucursal.general.nombre', 'Nombre')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="sucursal-nombre"
                    data-testid="sucursal-general-nombre"
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
            name="prefijo_nombre"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="sucursal-prefijo">
                  {t('sucursal.general.prefijo', 'Prefijo (clave única)')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="sucursal-prefijo"
                    data-testid="sucursal-general-prefijo"
                    placeholder="BOG-CEN"
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
            name="direccion"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="sucursal-direccion">
                  {t('sucursal.general.direccion', 'Dirección')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="sucursal-direccion"
                    data-testid="sucursal-general-direccion"
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
            name="telefono"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="sucursal-telefono">
                  {t('sucursal.general.telefono', 'Teléfono')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="sucursal-telefono"
                    data-testid="sucursal-general-telefono"
                    placeholder="+57 300 1234567"
                    {...field}
                    value={field.value ?? ''}
                  />
                </FormControl>
                {telefonoShowWarning && (
                  <p
                    role="status"
                    data-testid="sucursal-general-telefono-warning"
                    className="flex items-center gap-1.5 text-xs text-amber-600"
                  >
                    <TriangleAlert className="size-3.5 shrink-0" aria-hidden="true" />
                    {t(
                      'sucursal.general.telefonoWarning',
                      'No parece un teléfono colombiano válido. Podés guardar igual.',
                    )}
                  </p>
                )}
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="ciudad"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="sucursal-ciudad">
                  {t('sucursal.general.ciudad', 'Ciudad')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="sucursal-ciudad"
                    data-testid="sucursal-general-ciudad"
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
            name="horario"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="sucursal-horario">
                  {t('sucursal.general.horario', 'Horario')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="sucursal-horario"
                    data-testid="sucursal-general-horario"
                    placeholder="24/7"
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
            name="uuid_tipo_sucursal"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="sucursal-tipo">
                  {t('sucursal.general.tipoSucursal', 'Tipo de sucursal')}
                </FormLabel>
                <FormControl>
                  <select
                    id="sucursal-tipo"
                    data-testid="sucursal-general-tipo"
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) => field.onChange(e.target.value || null)}
                  >
                    <option value="">
                      {t('sucursal.general.tipoSucursalNinguno', 'Sin asignar')}
                    </option>
                    {tiposSucursal.map((tipo) => (
                      <option key={tipo.uuid} value={tipo.uuid}>
                        {tipo.nombre ?? tipo.codigo ?? tipo.uuid}
                      </option>
                    ))}
                  </select>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {saveError && (
            <p
              role="alert"
              data-testid="sucursal-general-save-error"
              className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {saveError}
            </p>
          )}

          <div className="flex items-center justify-between gap-2 pt-2">
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={() => {
                setDisableError(null);
                setConfirmOpen(true);
              }}
              data-testid="sucursal-general-deshabilitar-btn"
            >
              {t('sucursal.general.deshabilitar', 'Deshabilitar sucursal')}
            </Button>

            <Button
              type="submit"
              disabled={isSubmitting}
              data-testid="sucursal-general-submit"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  {t('sucursal.general.submitting', 'Guardando…')}
                </>
              ) : (
                t('sucursal.general.submit', 'Guardar cambios')
              )}
            </Button>
          </div>
        </form>
      </Form>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent data-testid="sucursal-deshabilitar-dialog">
          <DialogHeader>
            <DialogTitle>
              {t('sucursal.deshabilitar.title', '¿Deshabilitar esta sucursal?')}
            </DialogTitle>
            <DialogDescription>
              {t(
                'sucursal.deshabilitar.consecuencia',
                'Una sucursal deshabilitada deja de aceptar NUEVOS ingresos de inmediato. Las salidas de vehículos que ya estén adentro se siguen permitiendo con normalidad. Esta acción no se puede deshacer desde esta pantalla.',
              )}
            </DialogDescription>
          </DialogHeader>

          {disableError && (
            <p
              role="alert"
              data-testid="sucursal-deshabilitar-error"
              className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {disableError}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setConfirmOpen(false)}
              disabled={disabling}
              data-testid="sucursal-deshabilitar-cancelar"
            >
              {t('common.cancel', 'Cancelar')}
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => {
                void handleConfirmDeshabilitar();
              }}
              disabled={disabling}
              data-testid="sucursal-deshabilitar-confirmar"
            >
              {disabling ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  {t('sucursal.deshabilitar.submitting', 'Deshabilitando…')}
                </>
              ) : (
                t('sucursal.deshabilitar.confirmar', 'Sí, deshabilitar')
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
