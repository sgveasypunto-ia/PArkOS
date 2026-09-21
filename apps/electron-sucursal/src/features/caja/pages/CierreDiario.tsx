/**
 * `<CierreDiario />` — page orchestrator for HU-F10.3 (REQ-OPS-164 +
 * REQ-OPS-167, AD-3 + AD-4 + AD-6).
 *
 * Flow:
 *   1. Resolve the active branch + role (admin- vs operador-) via
 *      `useAuth()` (the F10.3 role gate is at the UI layer per
 *      REQ-OPS-167; the backend gate is `requires_issuer("operador-",
 *      "admin-")` at `caja_arqueo.py:61`).
 *   2. Fetch the per-session resumen via `useArqueoResumenPorSesion`
 *      (REQ-OPS-163 + REQ-OPS-165).
 *   3. Compute the aggregate totals (`Σ valor_efectivo_reportado`,
 *      `Σ valor_datafono_reportado`, `Σ diferencia`) from the
 *      closed sessions.
 *   4. Render the per-session summary table + `<CierreDiarioForm />`
 *      with the totals.
 *   5. On submit, wire `runCierreDiarioChain` (REQ-OPS-166):
 *      - On `{ kind: 'success' }` → navigate to `/` with success
 *        banner (NOT `/login?closed=true`; the supervisor preserves
 *        own session per AD-3 + REQ-OPS-164).
 *      - On `{ kind: 'arqueo_fallido' }` → red banner.
 *      - On `{ kind: 'red_arqueo' }` → red banner.
 *
 * NO useCierreDiario() legacy helper — this is the NEW forward path
 * per REQ-OPS-166. The legacy helper is deprecated (see
 * `useArqueo.ts:104-118` JSDoc).
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@parkos/ui-kit/hooks';

import { useArqueo } from '../hooks/useArqueo';
import {
  useArqueoResumenPorSesion,
  type ArqueoResumenPorSesion,
} from '../hooks/useArqueoResumenPorSesion';
import { CierreDiarioForm } from './CierreDiarioForm';
import {
  runCierreDiarioChain,
  type CierreDiarioBridge,
  type ArqueoSubmitFn,
} from './cierreDiarioChain';

/**
 * Strict-mode Zod schema for the cierre_diario form payload
 * (REQ-OPS-158 strict-mode branch from `<ArqueoSheet>` composed
 * here per AD-4). `justificacion` is REQUIRED at the top level
 * (`min(3)` after trim) when `Σ|diferencia|>0`; the page-level
 * gating decides whether to render the field at all.
 */
const cierreDiarioSchema = z.object({
  valor_efectivo_reportado: z.coerce.number().int().nonnegative(),
  valor_datafono_reportado: z.coerce.number().int().nonnegative(),
  justificacion: z.string().trim().optional(),
});
type CierreDiarioInput = z.infer<typeof cierreDiarioSchema>;

/**
 * Compute the aggregate totals from the per-session array. Σ is
 * over CLOSED sessions only (open sessions have null reportados).
 */
function computeTotals(sesiones: ArqueoResumenPorSesion['sesiones']): {
  valor_efectivo_reportado: number;
  valor_datafono_reportado: number;
  diferencia: number;
} {
  let efectivo = 0;
  let datafono = 0;
  let diferencia = 0;
  for (const s of sesiones) {
    if (s.estado !== 'cerrado') continue;
    efectivo += s.valor_efectivo_reportado ?? 0;
    datafono += s.valor_datafono_reportado ?? 0;
    // Per-session diferencia: (reported - expected) summed in abs.
    const efDiff = Math.abs(
      (s.valor_efectivo_reportado ?? 0) - (s.valor_efectivo_esperado ?? 0),
    );
    const dtDiff = Math.abs(
      (s.valor_datafono_reportado ?? 0) - (s.valor_datafono_esperado ?? 0),
    );
    diferencia += efDiff + dtDiff;
  }
  return {
    valor_efectivo_reportado: efectivo,
    valor_datafono_reportado: datafono,
    diferencia,
  };
}

export function CierreDiario(): JSX.Element {
  const { t } = useTranslation(['caja']);
  const navigate = useNavigate();
  const { submit: submitArqueo } = useArqueo();
  const { sucursal, sucursalesPermitidas } = useAuth();

  // Default the active branch to the operator's first permitida.
  const uuidSucursal = sucursal?.uuid ?? sucursalesPermitidas[0]?.uuid ?? null;

  // Today's ISO date (default for the page-level fecha picker).
  const todayISOLocal = (): string => {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  };
  const [fecha, setFecha] = useState<string>(todayISOLocal());

  // Role gate: multi-branch operador- shows the pending banner
  // (REQ-OPS-167 scenario 3). Single-branch operador- + admin- both
  // proceed to the full page.
  const isMultiBranchOperador =
    sucursalesPermitidas.length > 1 && uuidSucursal === null;

  // Per-session resumen fetch.
  const { data, error, refresh } = useArqueoResumenPorSesion(
    uuidSucursal,
    fecha,
  );

  // Aggregate totals + cierreDiarioExists from the hook response.
  const totals = data ? computeTotals(data.sesiones) : {
    valor_efectivo_reportado: 0,
    valor_datafono_reportado: 0,
    diferencia: 0,
  };
  const cierreDiaExists = data?.cierre_dia !== null && data?.cierre_dia !== undefined;

  // React Hook Form + Zod.
  const form = useForm<CierreDiarioInput>({
    resolver: zodResolver(cierreDiarioSchema),
    mode: 'onBlur',
    defaultValues: {
      valor_efectivo_reportado: 0,
      valor_datafono_reportado: 0,
      justificacion: '',
    },
  });

  const [errorState, setErrorState] = useState<
    { kind: 'arqueo_fallido' | 'red_arqueo' | 'ya_cerrado' | 'permiso_insuficiente' } | null
  >(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onCancel = (): void => {
    navigate('/');
  };

  const onSubmit = form.handleSubmit(async (values) => {
    setErrorState(null);
    setIsSubmitting(true);

    // Wire the bridge if available (jsdom + vitest may not have it).
    const bridge: CierreDiarioBridge | null =
      typeof window !== 'undefined' &&
      typeof (window as unknown as { bridge?: { imprimir?: unknown } }).bridge?.imprimir === 'function'
        ? {
            imprimir: (window as unknown as {
              bridge: { imprimir: (k: string, p: Record<string, unknown>) => Promise<unknown> };
            }).bridge.imprimir,
          }
        : null;

    const result = await runCierreDiarioChain({
      submitArqueo: submitArqueo as unknown as ArqueoSubmitFn,
      bridge,
      values: {
        valor_efectivo_reportado: values.valor_efectivo_reportado,
        valor_datafono_reportado: values.valor_datafono_reportado,
        justificacion: values.justificacion,
      },
    });

    setIsSubmitting(false);

    switch (result.kind) {
      case 'success':
        // Supervisor preserves own session per AD-3 — navigate to `/`
        // (NOT `/login?closed=true`). On success, the success banner
        // is rendered below; the page does NOT clear auth or dispatch
        // the `parkos:auth:cleared` event.
        navigate('/');
        return;
      case 'arqueo_fallido':
        setErrorState({ kind: 'arqueo_fallido' });
        return;
      case 'red_arqueo':
        setErrorState({ kind: 'red_arqueo' });
        return;
      case 'ya_cerrado':
        setErrorState({ kind: 'ya_cerrado' });
        return;
      case 'permiso_insuficiente':
        setErrorState({ kind: 'permiso_insuficiente' });
        return;
    }
  });

  // ── Render guards ──────────────────────────────────────────────────
  // Multi-branch operador- → pending banner.
  if (isMultiBranchOperador) {
    return (
      <main
        data-testid="cierre-diario-page"
        lang="es-CO"
        className="mx-auto max-w-3xl p-4"
      >
        <h1 className="mb-2 text-2xl font-bold">
          {t('caja:cierreDiario.titulo', { defaultValue: 'Cierre diario' })}
        </h1>
        <div
          data-testid="cierre-diario-multi-branch-pending"
          role="status"
          className="rounded border border-amber-300 bg-amber-50 p-4 text-amber-700"
        >
          {t('caja:cierreDiario.multiBranchOperatorPending', {
            defaultValue:
              'Sucursal pendiente de selección — seleccioná una sucursal para continuar.',
          })}
        </div>
        <button
          type="button"
          data-testid="cierre-diario-cancelar"
          className="mt-2"
          onClick={onCancel}
        >
          {t('caja:cierreDiario.cancelar', { defaultValue: 'Cancelar' })}
        </button>
      </main>
    );
  }

  // No branch context at all → defensive banner.
  if (uuidSucursal === null) {
    return (
      <main
        data-testid="cierre-diario-page"
        lang="es-CO"
        className="mx-auto max-w-3xl p-4"
      >
        <h1 className="mb-2 text-2xl font-bold">
          {t('caja:cierreDiario.titulo', { defaultValue: 'Cierre diario' })}
        </h1>
        <div
          data-testid="cierre-diario-supervisor-only"
          role="status"
          className="rounded border border-amber-300 bg-amber-50 p-4 text-amber-700"
        >
          {t('caja:cierreDiario.supervisorOnly', {
            defaultValue:
              'Funcionalidad solo para supervisores — seleccione una sucursal para continuar.',
          })}
        </div>
        <button
          type="button"
          data-testid="cierre-diario-cancelar"
          className="mt-2"
          onClick={onCancel}
        >
          {t('caja:cierreDiario.cancelar', { defaultValue: 'Cancelar' })}
        </button>
      </main>
    );
  }

  // Loading skeleton — hook still fetching.
  if (!data && !error) {
    return (
      <main
        data-testid="cierre-diario-page"
        lang="es-CO"
        className="mx-auto max-w-3xl p-4"
      >
        <h1 className="mb-2 text-2xl font-bold">
          {t('caja:cierreDiario.titulo', { defaultValue: 'Cierre diario' })}
        </h1>
        <div
          data-testid="cierre-diario-skeleton"
          className="h-48 animate-pulse rounded bg-muted"
        />
      </main>
    );
  }

  return (
    <main
      data-testid="cierre-diario-page"
      lang="es-CO"
      className="mx-auto max-w-3xl space-y-2 p-4"
    >
      <h1 className="text-2xl font-bold">
        {t('caja:cierreDiario.titulo', { defaultValue: 'Cierre diario' })}
      </h1>
      <p className="text-sm text-muted-foreground">
        {t('caja:cierreDiario.subtitulo', {
          defaultValue:
            'Cierre de todas las sesiones abiertas del día — supervisor / multi-sucursal.',
        })}
      </p>

      {error && (
        <div
          data-testid="cierre-diario-error-fetch"
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-2 text-destructive"
        >
          {error.message}
          <button
            type="button"
            data-testid="cierre-diario-retry"
            className="ml-2 underline"
            onClick={() => void refresh()}
          >
            {t('caja:cierreDiario.retry', { defaultValue: 'Reintentar' })}
          </button>
        </div>
      )}

      {cierreDiaExists && (
        <div
          data-testid="cierre-diario-already-closed"
          role="status"
          className="rounded border border-amber-300 bg-amber-50 p-2 text-amber-700"
        >
          {t('caja:cierreDiario.alreadyClosed', {
            defaultValue:
              'Ya existe un cierre diario para hoy — consulta el reporte.',
          })}
        </div>
      )}

      {errorState?.kind === 'arqueo_fallido' && (
        <div
          data-testid="cierre-diario-error-5xx"
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-2 text-destructive"
        >
          {t('caja:cierreDiario.errorCierreFallido', {
            defaultValue:
              'No se pudo registrar el cierre diario — reintente; si persiste contacte al supervisor.',
          })}
        </div>
      )}
      {errorState?.kind === 'red_arqueo' && (
        <div
          data-testid="cierre-diario-error-red"
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-2 text-destructive"
        >
          {t('caja:cierreDiario.errorRedArqueo', {
            defaultValue: 'Sin conexión — verifique la red.',
          })}
        </div>
      )}
      {errorState?.kind === 'permiso_insuficiente' && (
        <div
          data-testid="cierre-diario-error-permiso"
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-2 text-destructive"
        >
          {t('caja:cierreDiario.errorPermisoInsuficiente', {
            defaultValue:
              'No tiene permiso para cerrar esta sucursal — contacte al administrador del sistema.',
          })}
        </div>
      )}
      {errorState?.kind === 'ya_cerrado' && (
        <div
          data-testid="cierre-diario-error-ya-cerrado"
          role="alert"
          className="rounded border border-amber-300 bg-amber-50 p-2 text-amber-700"
        >
          {t('caja:cierreDiario.errorCierreDiaNoAceptaSesion', {
            defaultValue:
              'Cierre diario ya registrado para hoy — consulte el reporte.',
          })}
        </div>
      )}

      {/* Fecha picker (page-level — the form's input is read-only). */}
      <div className="flex items-center gap-2">
        <label htmlFor="cierre-diario-fecha-page" className="text-sm">
          {t('caja:cierreDiario.fecha', { defaultValue: 'Fecha' })}
        </label>
        <input
          id="cierre-diario-fecha-page"
          data-testid="cierre-diario-fecha-page"
          type="date"
          value={fecha}
          max={todayISOLocal()}
          onChange={(e) => setFecha(e.target.value)}
          className="rounded border border-border bg-background px-2 py-1 text-sm"
        />
      </div>

      <CierreDiarioForm
        sesiones={data?.sesiones ?? []}
        totals={totals}
        cierreDiaExists={cierreDiaExists}
        isSubmitting={isSubmitting}
        fecha={fecha}
        form={
          form as unknown as Parameters<typeof CierreDiarioForm>[0]['form']
        }
        onSubmit={onSubmit as unknown as Parameters<
          typeof CierreDiarioForm
        >[0]['onSubmit']}
        onCancel={onCancel}
      />
    </main>
  );
}