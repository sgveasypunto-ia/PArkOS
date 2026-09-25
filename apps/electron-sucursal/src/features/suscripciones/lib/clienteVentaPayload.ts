/**
 * `buildClienteVentaPayload(value)` — single source of truth for mapping
 * `<Venta />` paso 1 identification state (`ClienteIdentificacionValue`,
 * the same shape `<PagoModal>` uses via `<ClienteIdentificacionFields>`)
 * to `VentaSuscripcionCreate['cliente']`.
 *
 * Mirrors `features/facturacion/lib/clienteFePayload.ts` (Flujo 1):
 * centralizing the mapping here means `<Venta />` never re-derives
 * `tipo_identificador`/`apellido`/`dv` handling inline. Unlike
 * `PagoModal`, step 1 has NO "cliente genérico" escape hatch — a
 * venta de suscripción always requires a real, identified cliente.
 */
import type { ClienteIdentificacionValue } from '../../facturacion/components/ClienteIdentificacionFields';
import type { VentaSuscripcionCreate } from '../hooks/useVentaSuscripcion';

export function buildClienteVentaPayload(
  value: ClienteIdentificacionValue,
): VentaSuscripcionCreate['cliente'] {
  return {
    tipo_identificador: value.tipo_identificador,
    numero_identificacion: value.numero_identificacion.trim(),
    dv: value.tipo_identificador === 'NIT' ? value.dv.trim() || undefined : undefined,
    nombre: value.nombre.trim(),
    apellido: value.tipo_persona === 'persona' ? value.apellido.trim() || undefined : undefined,
    email: null,
  };
}
