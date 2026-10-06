/**
 * `<CerrarTurnoForm />` — presentational puro (F3.3 — T3, DEC-F3.3-06 verbatim).
 *
 * Recibe props `{ form, onSubmit, isSubmitting, error, sesion, onCancel }`
 * (DEC-F3.1-02 verbatim + DEC-F3.3-06 placeholder arqueo). Lee `sesion`
 * via props — NO consume `useSesionActiva` (presentational puro).
 *
 * HU-F10.2 (REQ-OPS-157, REQ-OPS-158) — el form extiende el F3.3 stub
 * con los campos del `POST /caja/arqueo` (HU-F1.13):
 *   - `valor_efectivo_reportado` y `observaciones_cierre`. PT-4: no hay
 *     campo "Justificación" en la UI; el motivo del descuadre va en
 *     Observaciones y es REQUERIDO (min(3), en strict-mode) solo cuando el
 *     pre-flight del backend indica diferencia de efectivo (plan.md HU-F10.2
 *     línea 2273: "obligatoria SI HAY diferencia", no incondicional).
 *     PT-6: sin campo de datáfono. El monto esperado y la diferencia NUNCA
 *     se renderizan antes del envío — conteo ciego.
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
 *   - 2 inputs: efectivo contado + observaciones (`cerrar-turno-observaciones`),
 *     que alimentan `POST /caja/arqueo` y `PUT /caja-sesion/{uuid}/cerrar`.
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
import { MoneyInput } from '@/components/ui/money-input';
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

import {
  OBSERVACIONES_CIERRE_MAX,
  type CerrarTurnoInput,
} from '../api/schemas/turnoSchema';
import type { SesionRead } from '../api/sesionActivaApi';
import { formatCOP, formatTiempoTranscurrido } from '../lib/format';
import { useMiTurno } from '../../operacion/hooks/useMiTurno';
import { useRequiereJustificacion } from '../hooks/useRequiereJustificacion';

/** Mínimo de caracteres del motivo del descuadre (REQ-OPS-158). */
const MOTIVO_MIN_CHARS = 3;

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
  | { kind: 'catalogo_no_disponible' }
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
   * `'cierre_turno'` or `'cierre_dia'`, the motivo in Observaciones is
   * required (`min(3)`) whenever the backend pre-flight reports a cash
   * difference, and the Confirmar button stays disabled while it is
   * shorter than that. F10.1 ArqueoParcial-style lenient path uses
   * `undefined`.
   */
  requiredMode?: 'parcial' | 'cierre_turno' | 'cierre_dia';
  /**
   * Sticky flag set by `<CerrarTurno>` when the backend rejected a prior
   * attempt with `justificacion_requerida` (HU-F10.2 "conteo ciego" —
   * the real expected total is server-side only, so the pre-flight can
   * race with the POST). Forces Observaciones to be required regardless
   * of the pre-flight verdict.
   */
  forceRequireMotivo?: boolean;
}

export function CerrarTurnoForm({
  form,
  onSubmit,
  isSubmitting,
  error,
  sesion,
  onCancel,
  requiredMode,
  forceRequireMotivo = false,
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
  // el motivo del descuadre es obligatorio SOLO "si hay diferencia" — no
  // incondicionalmente.
  //
  // PT-4: la UI ya no tiene un campo "Justificación" aparte. El motivo del
  // descuadre se escribe en "Observaciones" (mín. 3 caracteres cuando hay
  // diferencia); `cerrarTurnoChain.ts` lo reenvía como `justificacion` del
  // POST /caja/arqueo para satisfacer el gate del backend sin tocarlo.
  // PT-6: el datáfono no se cuenta ni participa del pre-flight.
  //
  // REGRESSION fix (2026-10-01): el pre-flight corre en el backend
  // (`useRequiereJustificacion`) porque el esperado real es
  // `inicial + SUM(factura_pagos)`, solo conocido server-side
  // (DEC-ARQUEO-10). Devuelve ÚNICAMENTE el veredicto booleano — el monto
  // esperado NUNCA viaja al cliente (conteo ciego: ni se renderiza, ni se
  // transmite).
  const watchEfectivoReportado = form.watch('valor_efectivo_reportado');
  const { requiereJustificacion: requiereMotivoServer } = useRequiereJustificacion(
    sesion.uuid,
    watchEfectivoReportado ?? 0,
  );
  // Conservador mientras el backend no respondió todavía (debounce +
  // round-trip): asumir que SÍ hay diferencia, nunca `false` por
  // default — lo contrario reintroduciría la misma ventana de falso
  // negativo que este hook existe para cerrar. `forceRequireMotivo`
  // (seteado por `<CerrarTurno>` tras un rechazo real del backend) sigue
  // OR-eado por las dudas de una condición de carrera entre este
  // pre-flight y el POST real.
  const requiereMotivo = (requiereMotivoServer ?? true) || forceRequireMotivo;

  // REQ-OPS-158 — strict-mode gate: botón deshabilitado mientras el motivo
  // (Observaciones) tenga < 3 caracteres, pero SOLO cuando una diferencia
  // realmente lo exige. Además `handleValid` re-chequea al enviar, porque
  // con `zodResolver` las `rules` de RHF no se ejecutan.
  const watchObservaciones = form.watch('observaciones_cierre') ?? '';
  const motivoMuyCorto = watchObservaciones.trim().length < MOTIVO_MIN_CHARS;
  const strictModeButtonDisabled = isStrictMode && requiereMotivo && motivoMuyCorto;

  const handleValid = async (data: CerrarTurnoInput): Promise<void> => {
    if (
      isStrictMode &&
      requiereMotivo &&
      (data.observaciones_cierre ?? '').trim().length < MOTIVO_MIN_CHARS
    ) {
      form.setError('observaciones_cierre', {
        type: 'validate',
        message: t('caja:cerrarTurno.observacionesRequeridas', {
          defaultValue: 'Escribe el motivo del descuadre (mínimo 3 caracteres).',
        }),
      });
      return;
    }
    await onSubmit(data);
  };

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(handleValid)}
        noValidate
        data-testid="cerrar-turno-form"
        // F31.3 rediseño: el form no tenía NINGÚN spacing entre el Card
        // resumen, cada FormField, los banners de error y los botones —
        // todos eran hijos directos sin `space-y`, quedaban pegados sin
        // aire entre sí. `space-y-4` es el mismo ritmo vertical que ya
        // usa el resto de los forms del dominio (CierreDiarioForm,
        // AbrirTurnoForm).
        className="space-y-4"
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
                <MoneyInput
                  value={field.value}
                  onChange={(raw) => field.onChange(raw === '' ? 0 : Number(raw))}
                  onBlur={field.onBlur}
                  name={field.name}
                  ref={field.ref}
                  inputTestId="cerrar-turno-valor-efectivo-reportado"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* PT-4: único campo de texto libre del cierre. Cuando hay
            diferencia de efectivo (conteo ciego: el veredicto viene del
            backend, nunca el monto) aquí va el motivo del descuadre y es
            obligatorio; sin diferencia es opcional. */}
        <FormField
          control={form.control}
          name="observaciones_cierre"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                {requiereMotivo
                  ? t('caja:cerrarTurno.observacionesLabelMotivo', {
                      defaultValue: 'Observaciones (motivo del descuadre)',
                    })
                  : t('caja:observaciones')}
              </FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="text"
                  maxLength={OBSERVACIONES_CIERRE_MAX}
                  data-testid="cerrar-turno-observaciones"
                  aria-required={isStrictMode && requiereMotivo}
                  placeholder={
                    requiereMotivo
                      ? t('caja:cerrarTurno.observacionesPlaceholderMotivo', {
                          defaultValue: 'Describe brevemente el motivo (mín. 3 caracteres).',
                        })
                      : undefined
                  }
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription data-testid="cerrar-turno-observaciones-ayuda">
                {requiereMotivo
                  ? t('caja:cerrarTurno.observacionesDescripcionMotivo', {
                      defaultValue:
                        'Si hay diferencia entre el efectivo contado y lo esperado, escribe aquí el motivo del descuadre (obligatorio, mínimo 3 caracteres).',
                    })
                  : t('caja:cerrarTurno.observacionesDescripcionOpcional', {
                      defaultValue: 'Opcional',
                    })}
              </FormDescription>
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
        {error?.kind === 'catalogo_no_disponible' && (
          <FormMessage
            role="alert"
            data-testid="cerrar-turno-error-catalogo-no-disponible"
          >
            {t('caja:cerrarTurno.errorCatalogoNoDisponible', {
              defaultValue:
                'Catálogo de tipos de arqueo no disponible — reintente en unos segundos.',
            })}
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

        {/* Bugfix (2026-10-01): el botón quedaba disabled sin ninguna
            pista visible de por qué — el operador tipeaba valores y
            "no pasaba nada". Este banner SOLO explica la condición
            genérica (coincidir con lo esperado, o justificar) — nunca
            el monto esperado ni la diferencia (conteo ciego). */}
        {strictModeButtonDisabled && (
          <FormMessage
            role="alert"
            data-testid="cerrar-turno-boton-disabled-motivo"
          >
            {t('caja:cerrarTurno.botonDisabledMotivo', {
              defaultValue:
                'El botón se habilita cuando el valor contado coincide con lo esperado, o cuando escribes el motivo del descuadre en Observaciones (mínimo 3 caracteres).',
            })}
          </FormMessage>
        )}

        {/* F31.3 rediseño: los 2 botones no tenían contenedor propio —
            `<Button>` es `inline-flex` (button.tsx), así que quedaban
            pegados sin gap y podían solaparse/cortarse en 320px. Mismo
            patrón `flex flex-wrap gap-2` ya usado en CierreDiarioForm. */}
        <div className="flex flex-wrap gap-2 pt-2">
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
        </div>
      </form>
    </Form>
  );
}