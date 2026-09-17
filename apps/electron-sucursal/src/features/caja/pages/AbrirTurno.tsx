/**
 * `<AbrirTurno />` — container (F3.3 — T2, DEC-F3.3-01 verbatim).
 *
 * Orquesta RHF + Zod resolver + `useAuth` + `useNavigate` +
 * `sesionActivaApi.abrirSesion(payload)` con mapeo tipado de 409
 * (SesionAlreadyActiveError → UX "ya tenés un turno abierto" + botón
 * "Ir al turno").
 *
 * DEC-F3.3-08: validación local Zod (abrirTurnoSchema) ANTES del POST.
 * Defense in depth XR6 layer 4 — Zod local + backend Pydantic +
 * partial unique index 0023 (F1.3).
 *
 * DEC-F3.3-02: `<Input type="number" inputMode="decimal" step="0.01">`
 * en el presentational `<AbrirTurnoForm>` (teclado numérico mobile).
 *
 * WCAG 2.1 AA: shadcn Form primitives (form.tsx) proveen `aria-invalid`
 * + `aria-describedby` + `<FormMessage role="alert">` automático.
 * axe-core 0 violaciones verificado en vitest (REQ-OPS-124 S3).
 */
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '@parkos/ui-kit/hooks';

import {
  abrirSesion,
  SesionAlreadyActiveError,
  type SesionRead,
} from '../api/sesionActivaApi';
import {
  abrirTurnoSchema,
  type AbrirTurnoInput,
} from '../api/schemas/turnoSchema';
import {
  AbrirTurnoForm,
  type AbrirTurnoErrorState,
} from '../components/AbrirTurnoForm';

export function AbrirTurno(): JSX.Element {
  const navigate = useNavigate();
  const { user, sucursal } = useAuth();
  const [errorState, setErrorState] = useState<AbrirTurnoErrorState>(null);

  const form = useForm<AbrirTurnoInput>({
    resolver: zodResolver(abrirTurnoSchema),
    mode: 'onBlur',
    defaultValues: {
      uuid_sucursal: sucursal?.uuid ?? '',
      // REQ-OPS-131 (qa-2026-09-17 bug 1): backend canonical identity
      // is ``UserItem.uuid`` (renamed from legacy ``id``); reading
      // ``user?.uuid`` produces a non-empty UUID so Zod's
      // ``uuid_usuario: z.string().uuid()`` validation passes
      // (previously the legacy ``id`` field was either empty or a
      // non-UUID string, surfacing as a silent 422 with no inline
      // ``<FormMessage>``).
      uuid_usuario: user?.uuid ?? '',
      valor_inicial_efectivo: 0,
      valor_inicial_datafono: 0,
      observaciones: '',
    },
  });

  const onIrAlTurno = (): void => {
    navigate('/');
  };

  const onSubmit = form.handleSubmit(async (values) => {
    setErrorState(null);
    try {
      const sesion: SesionRead = await abrirSesion({
        uuid_sucursal: values.uuid_sucursal,
        uuid_usuario: values.uuid_usuario,
        valor_inicial_efectivo: values.valor_inicial_efectivo,
        valor_inicial_datafono: values.valor_inicial_datafono,
        ...(values.observaciones !== undefined && values.observaciones !== ''
          ? { observaciones: values.observaciones }
          : {}),
      });
      void sesion; // SWR re-fetch on next render via `useSesionActiva` key change.
      navigate('/');
    } catch (err) {
      if (err instanceof SesionAlreadyActiveError) {
        setErrorState({ kind: 'sesion_already_active' });
      } else {
        setErrorState({ kind: 'network' });
      }
    }
  });

  return (
    <AbrirTurnoForm
      form={form}
      onSubmit={onSubmit}
      isSubmitting={form.formState.isSubmitting}
      error={errorState}
      onIrAlTurno={onIrAlTurno}
    />
  );
}