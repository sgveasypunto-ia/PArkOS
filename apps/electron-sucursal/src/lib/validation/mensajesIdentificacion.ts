/**
 * `mensajeIdentificacion()` — traduce los códigos de validación del
 * bloque de identificación del cliente (FE / venta de suscripción) a
 * mensajes en español para el operador. Los códigos (`dv_invalido`,
 * `cc_formato_invalido`, ...) son contratos internos de los esquemas Zod;
 * nunca deben llegar crudos a la UI.
 */
const MENSAJES: Record<string, string> = {
  dv_invalido: 'El dígito de verificación (DV) no corresponde al NIT.',
  dv_requerido: 'Ingresá el dígito de verificación (DV) del NIT (un número de 0 a 9).',
  numero_identificacion_requerido: 'Ingresá el número de identificación.',
  documento_min_5: 'El número de identificación debe tener al menos 5 caracteres.',
  cc_formato_invalido: 'La cédula debe tener entre 6 y 10 dígitos.',
  documento_formato_invalido:
    'El documento debe ser alfanumérico, de 5 a 20 caracteres.',
  nombre_requerido: 'Ingresá el nombre o la razón social.',
  apellido_requerido: 'Ingresá los apellidos.',
};

export function mensajeIdentificacion(codigo: string): string;
export function mensajeIdentificacion(codigo: string | null | undefined): string | undefined;
export function mensajeIdentificacion(
  codigo: string | null | undefined,
): string | undefined {
  if (!codigo) return undefined;
  return MENSAJES[codigo] ?? codigo;
}
