/**
 * `buildClienteFePayload(values)` — single source of truth for mapping
 * `PagoFormValues` (owned by `<PagoModal>`) to the `{fe_con_datos,
 * fe_datos_cliente}` block every `POST /facturacion/factura*` call-site
 * spreads into its request body.
 *
 * Design note (2026-09-25, directiva del operador — desacoplar el
 * módulo de identificación para que los flujos 2/3 casi no necesiten
 * tocar su propia lógica). Antes cada call-site (`PagoSheet.tsx`,
 * `ReimprimirTiquete.tsx`) reconstruía este bloque a mano — los 3
 * hardcodeaban `tipo_identificador: 'NIT'` (bug encontrado en Flujo 1,
 * validación en vivo). Centralizar el armado acá significa que
 * cualquier consumidor futuro de `<PagoModal>` (venta de suscripción,
 * paso de cobro) NO necesita repetir esta lógica de mapeo — solo llama
 * esta función y spreadea el resultado.
 *
 * Lives in `lib/` (not co-located in `PagoModal.tsx`) so exporting it
 * doesn't trip `react-refresh/only-export-components` (component files
 * must only export components/types for Fast Refresh) — same
 * convention as `lib/resolverIngresoReimpresion.ts`.
 */
import type { PagoFormValues } from '../components/PagoModal';
import type { FacturaClienteDatosPost } from '../api/facturaApi';

/**
 * Returns `{}` (nothing to spread) when `fe===false` — cliente
 * genérico, exactamente el mismo contrato de wire que antes (el
 * backend nunca ve `fe_con_datos`/`fe_datos_cliente` en ese caso).
 */
export function buildClienteFePayload(
  values: PagoFormValues,
): { fe_con_datos: true; fe_datos_cliente: FacturaClienteDatosPost } | Record<string, never> {
  if (!values.fe) return {};
  return {
    fe_con_datos: true,
    fe_datos_cliente: {
      tipo_identificador: values.tipo_identificador,
      numero_identificacion: values.nit ?? '',
      dv: values.tipo_identificador === 'NIT' ? values.dv || null : null,
      nombre: values.nombre_cliente ?? 'Consumidor final',
      apellido: values.tipo_persona === 'persona' ? values.apellido || null : null,
      email: values.email_cliente || null,
      telefono: null,
    },
  };
}
