/**
 * `mensajeIdentificacion()` — traduce los códigos de validación del
 * bloque de identificación del cliente (FE / venta de suscripción) y de los
 * pasos de placas / cantidad del wizard y de los formularios de ingreso y
 * salida (AUD3) a
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
  email_formato_invalido: 'El correo electrónico no tiene un formato válido.',
  placa_formato_invalido:
    'Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D).',
  placa_tipo_incompatible: 'La placa no corresponde al tipo de vehículo elegido.',
  placas_cantidad_invalida: 'Ingresá todas las placas de la suscripción.',
  placas_min_1: 'Ingresá al menos una placa.',
  placas_max_2: 'Se permiten como máximo dos placas.',
  'validation.number.required': 'Ingresá la cantidad de vehículos.',
  'validation.cantidad.min_1': 'La cantidad de vehículos debe ser al menos 1.',
  'validation.cantidad.max_excedida': 'La cantidad supera el máximo de vehículos del plan.',
  ingreso_sin_placa_tipo_requerido: 'Seleccioná un tipo de vehículo.',
};

export function mensajeIdentificacion(codigo: string): string;
export function mensajeIdentificacion(codigo: string | null | undefined): string | undefined;
export function mensajeIdentificacion(
  codigo: string | null | undefined,
): string | undefined {
  if (!codigo) return undefined;
  return MENSAJES[codigo] ?? codigo;
}
