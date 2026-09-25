/**
 * `<ClienteIdentificacionFields />` — presentational, controlled
 * component for the persona natural/empresa identification block
 * (HU-F8.1 base, extendido a HU-F9.1 venta de suscripción).
 *
 * Deliberately NOT coupled to React Hook Form: takes a plain
 * `value`/`onChange` pair (like a native `<input>`), so it works both
 * inside RHF-driven forms (via a small adapter reading `useWatch` /
 * writing `form.setValue`, see `<PagoModal>`) and inside plain
 * `useState`-driven wizards (see `<Venta>` step 1, which validates
 * per-step with `safeParse` instead of a single RHF form). Error
 * strings are supplied by the caller via `errors` — this component
 * has no opinion on WHERE the error comes from (Zod `superRefine`,
 * a plain `safeParse`, a server 422), only on how to render it.
 *
 * Design note (directiva del operador, ajuste identificación persona/
 * empresa): un solo módulo de identificación reutilizado en todos los
 * flujos de facturación, para no reimplementar el selector persona/
 * empresa + documento condicional en cada call-site.
 */
import { useTranslation } from 'react-i18next';

import { Input } from '@/components/ui/input';
import type { TipoIdentificador } from '../../../lib/validation/identificacion';

export type TipoPersonaCliente = 'persona' | 'empresa';

export interface ClienteIdentificacionValue {
  tipo_persona: TipoPersonaCliente;
  tipo_identificador: TipoIdentificador;
  numero_identificacion: string;
  /** Solo aplica (y solo se renderiza) cuando `tipo_identificador==='NIT'`. */
  dv: string;
  /** "Nombres" para persona natural, "Razón social" para empresa. */
  nombre: string;
  /** Solo aplica (y solo se renderiza) para persona natural. */
  apellido: string;
}

/** Placeholder de ejemplo por tipo de documento — puramente cosmético.
 * Nunca es un valor precargado real (BUGFIX 2026-09-25, directiva del
 * operador: "si se selecciona se debe tener placeholders no valores"). */
const NUMERO_PLACEHOLDER: Record<TipoIdentificador, string> = {
  NIT: '900123456-7',
  CC: '1020304050',
  CE: '1020304050',
  pasaporte: 'AB1234567',
};

export interface ClienteIdentificacionFieldsProps {
  value: ClienteIdentificacionValue;
  onChange: (patch: Partial<ClienteIdentificacionValue>) => void;
  errors?: Partial<
    Record<'numero_identificacion' | 'dv' | 'nombre' | 'apellido', string | null | undefined>
  >;
  /** Prefijo de `data-testid` por caller (ej. `pago`, `venta-cliente`). */
  testIdPrefix: string;
}

export function ClienteIdentificacionFields({
  value,
  onChange,
  errors,
  testIdPrefix,
}: ClienteIdentificacionFieldsProps): JSX.Element {
  const { t } = useTranslation(['facturacion', 'common']);

  return (
    <div className="space-y-2">
      <div>
        <label className="text-sm font-medium leading-none" htmlFor={`${testIdPrefix}-tipo-persona`}>
          {t('facturacion:pago.tipo_persona_label', { defaultValue: 'Tipo de cliente' })}
        </label>
        <select
          id={`${testIdPrefix}-tipo-persona`}
          data-testid={`${testIdPrefix}-tipo-persona`}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background transition-colors hover:border-ring/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          value={value.tipo_persona}
          onChange={(event) => {
            const next = event.target.value as TipoPersonaCliente;
            // Empresa siempre factura con NIT; persona natural elige su
            // documento (por defecto CC al cambiar desde empresa, para
            // no dejar el select de tipo de documento en un valor huérfano).
            if (next === 'empresa') {
              onChange({ tipo_persona: next, tipo_identificador: 'NIT' });
            } else if (value.tipo_identificador === 'NIT') {
              onChange({ tipo_persona: next, tipo_identificador: 'CC' });
            } else {
              onChange({ tipo_persona: next });
            }
          }}
        >
          <option value="empresa">{t('facturacion:pago.tipo_persona_empresa', { defaultValue: 'Empresa' })}</option>
          <option value="persona">{t('facturacion:pago.tipo_persona_natural', { defaultValue: 'Persona natural' })}</option>
        </select>
      </div>

      {value.tipo_persona === 'persona' && (
        <div>
          <label className="text-sm font-medium leading-none" htmlFor={`${testIdPrefix}-tipo-documento`}>
            {t('facturacion:pago.tipo_documento_label', { defaultValue: 'Tipo de documento' })}
          </label>
          <select
            id={`${testIdPrefix}-tipo-documento`}
            data-testid={`${testIdPrefix}-tipo-documento`}
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background transition-colors hover:border-ring/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            value={value.tipo_identificador}
            onChange={(event) => onChange({ tipo_identificador: event.target.value as TipoIdentificador })}
          >
            <option value="CC">{t('facturacion:pago.tipo_documento_cc', { defaultValue: 'Cédula de ciudadanía' })}</option>
            <option value="CE">{t('facturacion:pago.tipo_documento_ce', { defaultValue: 'Cédula de extranjería' })}</option>
            <option value="pasaporte">{t('facturacion:pago.tipo_documento_pasaporte', { defaultValue: 'Pasaporte' })}</option>
          </select>
        </div>
      )}

      <div>
        <label className="text-sm font-medium leading-none" htmlFor={`${testIdPrefix}-numero`}>
          {value.tipo_identificador === 'NIT'
            ? t('facturacion:pago.fe_nit', { defaultValue: 'NIT del cliente' })
            : t('facturacion:pago.fe_numero_identificacion', { defaultValue: 'Número de identificación' })}
        </label>
        <Input
          id={`${testIdPrefix}-numero`}
          data-testid={`${testIdPrefix}-numero`}
          placeholder={NUMERO_PLACEHOLDER[value.tipo_identificador]}
          value={value.numero_identificacion}
          onChange={(event) => onChange({ numero_identificacion: event.target.value })}
        />
        {errors?.numero_identificacion && (
          <p className="text-sm font-medium text-destructive" data-testid={`${testIdPrefix}-numero-error`}>
            {errors.numero_identificacion}
          </p>
        )}
      </div>

      {value.tipo_identificador === 'NIT' && (
        <div>
          <label className="text-sm font-medium leading-none" htmlFor={`${testIdPrefix}-dv`}>
            {t('facturacion:pago.fe_dv', { defaultValue: 'DV (módulo 11)' })}
          </label>
          <Input
            id={`${testIdPrefix}-dv`}
            data-testid={`${testIdPrefix}-dv`}
            inputMode="numeric"
            maxLength={1}
            placeholder="0-9"
            value={value.dv}
            onChange={(event) => onChange({ dv: event.target.value })}
          />
          {errors?.dv && (
            <p className="text-sm font-medium text-destructive" data-testid={`${testIdPrefix}-dv-error`}>
              {errors.dv}
            </p>
          )}
        </div>
      )}

      <div>
        <label className="text-sm font-medium leading-none" htmlFor={`${testIdPrefix}-nombre`}>
          {value.tipo_persona === 'persona'
            ? t('facturacion:pago.fe_nombres', { defaultValue: 'Nombres' })
            : t('facturacion:pago.fe_razon_social', { defaultValue: 'Razón social' })}
        </label>
        <Input
          id={`${testIdPrefix}-nombre`}
          data-testid={`${testIdPrefix}-nombre`}
          placeholder={
            value.tipo_persona === 'persona'
              ? t('facturacion:pago.fe_nombres_placeholder', { defaultValue: 'Ej: Juan Pérez' })
              : t('facturacion:pago.fe_razon_social_placeholder', { defaultValue: 'Ej: Comercializadora S.A.S.' })
          }
          value={value.nombre}
          onChange={(event) => onChange({ nombre: event.target.value })}
        />
        {errors?.nombre && (
          <p className="text-sm font-medium text-destructive" data-testid={`${testIdPrefix}-nombre-error`}>
            {errors.nombre}
          </p>
        )}
      </div>

      {value.tipo_persona === 'persona' && (
        <div>
          <label className="text-sm font-medium leading-none" htmlFor={`${testIdPrefix}-apellido`}>
            {t('facturacion:pago.fe_apellidos', { defaultValue: 'Apellidos' })}
          </label>
          <Input
            id={`${testIdPrefix}-apellido`}
            data-testid={`${testIdPrefix}-apellido`}
            placeholder={t('facturacion:pago.fe_apellidos_placeholder', { defaultValue: 'Ej: Gómez' })}
            value={value.apellido}
            onChange={(event) => onChange({ apellido: event.target.value })}
          />
          {errors?.apellido && (
            <p className="text-sm font-medium text-destructive" data-testid={`${testIdPrefix}-apellido-error`}>
              {errors.apellido}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
