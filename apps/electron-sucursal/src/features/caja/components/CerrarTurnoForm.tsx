/**
 * `<CerrarTurnoForm />` — presentational puro (F3.3 — T3, DEC-F3.3-06 verbatim).
 *
 * Recibe props `{ form, onSubmit, isSubmitting, error, sesion, onCancel }`
 * (DEC-F3.1-02 verbatim + DEC-F3.3-06 placeholder arqueo). Lee `sesion`
 * via props — NO consume `useSesionActiva` (presentational puro).
 *
 * HU-F10.2 (REQ-OPS-157, REQ-OPS-158) — el form extiende el F3.3 stub
 * con los campos del `POST /caja/arqueo` (HU-F1.13):
 *   - `valor_efectivo_reportado`, `valor_datafono_reportado`,
 *     `justificacion` — SOLO aparece en el DOM (y es REQUERIDA, min(3),
 *     en strict-mode) cuando el conteo del operador difiere de
 *     `sesion.valor_inicial_*` (plan.md HU-F10.2 línea 2273: "obligatoria
 *     SI HAY diferencia", no incondicional). El monto esperado y la
 *     diferencia NUNCA se renderizan — conteo ciego.
 *
 * El strict-mode del form (top-level `min(3)`) se activa cuando el
 * padre pasa `requiredMode` con uno de los discriminadores estrictos.
 * El F10.1 `<ArqueoSheet requiredMode={undefined}>` default sigue
 * siendo el comportamiento bit-identical (sin cambios).
 *
 * Renderiza:
 *   - Resumen del turno arriba del form (uuid, timestamp apertura vía
 *     `formatTiempoTranscurrido`, valores iniciales vía `formatCOP`,
 *     observaciones si truthy).
 *   - 3 inputs para los campos del `POST /caja/arqueo` (REPORTADO):
 *     efectivo, datafono, justificacion (con `data-testid="cerrar-turno-required-justificacion"`
 *     en strict-mode).
 *   - 3 inputs F3.3 stub para los campos del `PUT /caja-sesion/{uuid}/cerrar`
 *     (FINAL): efectivo, datafono, observaciones_cierre.
 *   - Banner HU-F10.2 (REQ-OPS-159 cases 5-7): `data-testid="cerrar-turno-orphan-uuid"`
 *     con `Ref: <uuid_arqueo>` literal cuando el POST 201 succeedió
 *     pero el PUT falló.
 *   - Banner HU-F10.2 (REQ-OPS-159 case 3): arqueo POST falló
 *     (`errorArqueoFallido` o `errorRedArqueo`).
 *   - Banner HU-F10.2 (REQ-OPS-159 case 5/6): sesion already closed.
 *   - Botones "Confirmar cierre" + "Cancelar" (`variant="ghost"`).
 *
 * Accesibilidad (RNF-022 WCAG 2.1 AA — REQ-OPS-122 + REQ-OPS-124):
 *   - `<Form {...form}>` wrap con FormProvider (form.tsx:33).
 *   - `<FormLabel htmlFor>` + `<FormControl id>` via `useFormField()`.
 *   - `<Input type="number" inputMode="decimal" step="0.01">` (DEC-F3.3-02).
 *   - `<FormMessage role="alert">` para 404 `sesion_not_found` UX.
 *   - Botones `aria-disabled={isSubmitting}` + `data-testid` para tests.
 *   - Banners `role="alert"` con `data-testid` para tests + axe-core.
 *
 * DEC-F3.3-06 placeholder: F3.3 NO implementa arqueo completo (tolerancia +
 * justificación + alerta `descuadre_critico`) — Fase 10 HU-F10.x entrega
 * el flujo completo con `POST /caja/arqueo` + `tipo_arqueo='cierre_turno'`.
 */
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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

import type { CerrarTurnoInput } from '../api/schemas/turnoSchema';
import type { SesionRead } from '../api/sesionActivaApi';
import { formatCOP, formatTiempoTranscurrido } from '../lib/format';
import { useMiTurno } from '../../operacion/hooks/useMiTurno';

/**
 * Estado de error que `<CerrarTurno>` pasa a `<CerrarTurnoForm />`.
 *  - sesion_already_closed → <FormMessage role="alert">{t('sesionYaCerrada')}</FormMessage>
 *  - network              → <FormMessage role="alert">{t('errors:serverError')}</FormMessage>
 *  - arqueo_fallido       → banner REQ-OPS-159 case 3 (POST 5xx).
 *  - red_arqueo           → banner REQ-OPS-159 case 4 (POST network).
 *  - cierre_ya_cerrado    → banner REQ-OPS-159 case 5/6 (PUT 404/409).
 *  - cierre_fallido       → banner REQ-OPS-159 case 7 (PUT 5xx/network).
 */
export type CerrarTurnoErrorState =
  | { kind: 'sesion_already_closed' }
  | { kind: 'network' }
  | { kind: 'arqueo_fallido' }
  | { kind: 'red_arqueo' }
  | { kind: 'cierre_ya_cerrado'; uuid_arqueo?: string }
  | { kind: 'cierre_fallido'; uuid_arqueo?: string }
  | null;

export interface CerrarTurnoFormProps {
  form: UseFormReturn<CerrarTurnoInput>;
  onSubmit: (data: CerrarTurnoInput) => Promise<void>;
  isSubmitting: boolean;
  error: CerrarTurnoErrorState;
  sesion: SesionRead;
  onCancel: () => void;
  /**
   * HU-F10.2 (REQ-OPS-158) — strict-mode discriminator. When
   * `'cierre_turno'` or `'cierre_dia'`, `justificacion` is required
   * at the top level (`min(3)`) and the Confirmar button stays
   * disabled on initial render while `justificacion.length < 3`.
   * F10.1 ArqueoParcial-style lenient path uses `undefined`.
   */
  requiredMode?: 'parcial' | 'cierre_turno' | 'cierre_dia';
}

export function CerrarTurnoForm({
  form,
  onSubmit,
  isSubmitting,
  error,
  sesion,
  onCancel,
  requiredMode,
}: CerrarTurnoFormProps): JSX.Element {
  const { t } = useTranslation(['caja', 'common', 'operacion']);
  // Resumen visual del turno (directiva operador — Sheet más gráfico):
  // ingresos/salidas del turno vienen del mismo HU-F12.1 KPI aggregate
  // que ya consumen `<ResumenTurno>` / `<MiTurnoPanel>`. Zero-state
  // seguro (`useMiTurno` nunca retorna undefined — DA-F12.1-4).
  const { data: miTurno } = useMiTurno(sesion.uuid);

  const isStrictMode =
    requiredMode === 'cierre_turno' || requiredMode === 'cierre_dia';

  // plan.md HU-F10.2 (línea 2273) + sequence diagram (líneas 2296-2326):
  // la justificación es obligatoria SOLO "si hay diferencia" — no
  // incondicionalmente. `difTotal` se calcula client-side, igual que
  // `ArqueoParcial.tsx` (`hasDifferenceError`), únicamente para decidir
  // si el campo se muestra/exige — el monto NUNCA se renderiza (conteo
  // ciego: el operador no debe ver esperado ni diferencia).
  const watchEfectivoReportado = form.watch('valor_efectivo_reportado');
  const watchDatafonoReportado = form.watch('valor_datafono_reportado');
  const difTotal =
    Math.abs((watchEfectivoReportado ?? 0) - sesion.valor_inicial_efectivo) +
    Math.abs((watchDatafonoReportado ?? 0) - sesion.valor_inicial_datafono);
  const hayDiferencia = difTotal > 0;

  // REQ-OPS-158 — strict-mode gate: button disabled while
  // justificacion is empty / below 3 chars, but ONLY when a difference
  // actually requires it. The Zod schema (via the resolver) is
  // enforced at submit time; the visual gate is here.
  const watchJustificacion = form.watch('justificacion') ?? '';
  const strictModeButtonDisabled =
    isStrictMode && hayDiferencia && (watchJustificacion ?? '').trim().length < 3;

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        noValidate
        data-testid="cerrar-turno-form"
      >
        {/* El título + descripción ya los provee `<SheetHeader>` en
            `CerrarTurnoSheet.tsx` (Radix Dialog los expone como
            aria-labelledby/aria-describedby del propio diálogo) — un
            `<h1>` acá duplicaba visualmente "Cerrar turno" dos veces
            (mismo anti-patrón ya corregido en `ArqueoParcial.tsx`). */}

        {/* Resumen del turno — lista tipo tabla, mismo lenguaje visual
            que `<ResumenTurno>` (TurnoActivoToggle) / `<MiTurnoPanel>`.
            Info puramente operativa (apertura, ingresos, salidas) —
            NUNCA esperado/diferencia de caja (conteo ciego). */}
        <Card data-testid="cerrar-turno-resumen" aria-label="Resumen del turno">
          <CardHeader className="px-4 pt-3 pb-2">
            <CardTitle className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
              {t('caja:cerrarTurno.resumenTitulo', {
                defaultValue: 'Resumen del turno',
              })}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3">
            <ul role="list" className="divide-y divide-border/40 text-sm">
              <li className="flex items-center justify-between gap-2 py-1.5">
                <span className="text-muted-foreground/90">UUID</span>
                <span
                  className="truncate font-mono text-xs"
                  title={sesion.uuid}
                  data-testid="cerrar-turno-resumen-uuid"
                >
                  {sesion.uuid}
                </span>
              </li>
              <li className="flex items-center justify-between py-1.5">
                <span className="text-muted-foreground/90">
                  {t('caja:valorInicialEfectivo')}
                </span>
                <span className="font-mono font-semibold tabular-nums">
                  {formatCOP(sesion.valor_inicial_efectivo)}
                </span>
              </li>
              <li className="flex items-center justify-between py-1.5">
                <span className="text-muted-foreground/90">
                  {t('caja:valorInicialDatafono')}
                </span>
                <span className="font-mono font-semibold tabular-nums">
                  {formatCOP(sesion.valor_inicial_datafono)}
                </span>
              </li>
              <li
                className="flex items-center justify-between py-1.5"
                data-testid="cerrar-turno-apertura"
              >
                <span className="text-muted-foreground/90">Apertura</span>
                <span className="font-mono font-semibold tabular-nums">
                  {formatTiempoTranscurrido(sesion.timestamp_apertura)}
                </span>
              </li>
              <li
                className="flex items-center justify-between py-1.5"
                data-testid="cerrar-turno-resumen-row-ingresos"
              >
                <span className="text-muted-foreground/90">
                  {t('operacion:miTurno.kpis.ingresos', {
                    defaultValue: 'Ingresos en mi turno',
                  })}
                </span>
                <span className="font-mono font-semibold tabular-nums">
                  {miTurno.ingresos_count}
                </span>
              </li>
              <li
                className="flex items-center justify-between py-1.5"
                data-testid="cerrar-turno-resumen-row-salidas"
              >
                <span className="text-muted-foreground/90">
                  {t('operacion:miTurno.kpis.salidas', {
                    defaultValue: 'Salidas en mi turno',
                  })}
                </span>
                <span className="font-mono font-semibold tabular-nums">
                  {miTurno.salidas_count}
                </span>
              </li>
              {sesion.observaciones !== null &&
                sesion.observaciones !== undefined &&
                sesion.observaciones !== '' && (
                  <li className="flex items-center justify-between gap-2 py-1.5">
                    <span className="text-muted-foreground/90">
                      {t('caja:observaciones')}
                    </span>
                    <span className="text-right text-xs">{sesion.observaciones}</span>
                  </li>
                )}
            </ul>
          </CardContent>
        </Card>

        {/* ── HU-F10.2: POST /caja/arqueo fields (REPORTADO). ──────── */}
        <FormField
          control={form.control}
          name="valor_efectivo_reportado"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                {t('caja:valorEfectivoReportado', {
                  defaultValue: 'Efectivo contado',
                })}
              </FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="number"
                  inputMode="decimal"
                  step="0.01"
                  min="0"
                  data-testid="cerrar-turno-valor-efectivo-reportado"
                  value={field.value ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value;
                    field.onChange(raw === '' ? 0 : Number(raw));
                  }}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="valor_datafono_reportado"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                {t('caja:valorDatafonoReportado', {
                  defaultValue: 'Datáfono contado',
                })}
              </FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="number"
                  inputMode="decimal"
                  step="0.01"
                  min="0"
                  data-testid="cerrar-turno-valor-datafono-reportado"
                  value={field.value ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value;
                    field.onChange(raw === '' ? 0 : Number(raw));
                  }}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Conteo ciego (HU-F10.2): este campo solo existe en el DOM
            cuando `hayDiferencia` es true — nunca se expone el monto
            esperado ni la diferencia, ni siquiera oculto. */}
        {hayDiferencia && (
          <FormField
            control={form.control}
            name="justificacion"
            rules={
              isStrictMode
                ? {
                    validate: (value: unknown) => {
                      const v = typeof value === 'string' ? value.trim() : '';
                      return v.length >= 3 || 'justificacion_requerida';
                    },
                  }
                : undefined
            }
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  {t('caja:justificacion', { defaultValue: 'Justificación' })}
                </FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="text"
                    data-testid={
                      isStrictMode
                        ? 'cerrar-turno-required-justificacion'
                        : 'cerrar-turno-justificacion'
                    }
                    placeholder={t('caja:justificacionPlaceholder', {
                      defaultValue: 'Describí brevemente el motivo (mín. 3 caracteres).',
                    })}
                    value={field.value ?? ''}
                  />
                </FormControl>
                <FormDescription>
                  {t('caja:justificacionDescripcion', {
                    defaultValue:
                      'Hay una diferencia respecto a lo esperado. Por favor justificá.',
                  })}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        <FormField
          control={form.control}
          name="observaciones_cierre"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('caja:observaciones')}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="text"
                  data-testid="cerrar-turno-observaciones"
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>Opcional</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* ── HU-F10.2 banners (REQ-OPS-159 cases 3-7). ─────────────── */}
        {error?.kind === 'arqueo_fallido' && (
          <FormMessage
            role="alert"
            data-testid="cerrar-turno-error-arqueo-fallido"
          >
            {t('caja:cerrarTurno.errorArqueoFallido', {
              defaultValue:
                'Arqueo no registrado — reintente. Si persiste contacte al supervisor.',
            })}
          </FormMessage>
        )}
        {error?.kind === 'red_arqueo' && (
          <FormMessage role="alert" data-testid="cerrar-turno-error-red-arqueo">
            {t('caja:cerrarTurno.errorRedArqueo', {
              defaultValue: 'Sin conexión — verifique la red.',
            })}
          </FormMessage>
        )}
        {error?.kind === 'cierre_ya_cerrado' && (
          <FormMessage
            role="alert"
            data-testid="cerrar-turno-error-cierre-ya-cerrado"
          >
            {t('caja:cerrarTurno.errorCierreYaCerrado', {
              defaultValue:
                'La sesión ya estaba cerrada — contacte al supervisor.',
            })}
          </FormMessage>
        )}
        {error?.kind === 'sesion_already_closed' && (
          <FormMessage role="alert" data-testid="cerrar-turno-error-sesion-ya-cerrada">
            {t('caja:sesionYaCerrada')}
          </FormMessage>
        )}
        {/* REQ-OPS-159 cases 5-7 — orphan uuid banner. The supervisor
            uses the `data-testid="cerrar-turno-orphan-uuid"` element to
            quote the uuid to the ABBC-F10.2-BE-1 reconciler. */}
        {(error?.kind === 'cierre_ya_cerrado' || error?.kind === 'cierre_fallido') &&
          error.uuid_arqueo !== undefined &&
          error.uuid_arqueo !== '' && (
            <aside
              role="alert"
              data-testid="cerrar-turno-orphan-uuid"
              className="rounded border border-destructive bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              <p>
                {error.kind === 'cierre_ya_cerrado'
                  ? t('caja:cerrarTurno.errorCierreYaCerrado', {
                      defaultValue:
                        'Arqueo registrado pero la sesión ya estaba cerrada — contacte al supervisor',
                    })
                  : t('caja:cerrarTurno.errorCierreFallido', {
                      defaultValue:
                        'Arqueo registrado pero no se pudo cerrar sesión — contacte al supervisor',
                    })}
              </p>
              <p className="font-mono">
                Ref: {error.uuid_arqueo}
              </p>
              <p>
                {t('caja:cerrarTurno.orphanContactSupervisor', {
                  defaultValue:
                    'Conserve este UUID y contacte al supervisor para remediación manual.',
                })}
              </p>
            </aside>
          )}

        <Button
          type="submit"
          disabled={isSubmitting || strictModeButtonDisabled}
          aria-disabled={isSubmitting || strictModeButtonDisabled}
          data-testid="cerrar-turno-confirmar"
        >
          {isSubmitting ? t('common:loading') : t('caja:confirmarCierre')}
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={isSubmitting}
          aria-disabled={isSubmitting}
          data-testid="cerrar-turno-cancelar"
        >
          {t('common:cancel')}
        </Button>
      </form>
    </Form>
  );
}