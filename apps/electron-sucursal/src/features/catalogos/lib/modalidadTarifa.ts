/**
 * `modalidadTarifa.ts` — unit label of a tariff row by its modalidad.
 *
 * `prod.tarifas_sucursal.valor` is expressed per the unit of its modalidad
 * (`tipo_tarifa`): the four modalidades have fixed uuids seeded by migration
 * `0071_seed_tipo_tarifa_modalidades`. The cotizar payload only carries
 * `tarifa_uuid`; the tariff row (`useTarifaByUuid`) carries `uuid_tipo_tarifa`.
 */
const UNIDAD_POR_MODALIDAD: Readonly<Record<string, string>> = {
  '12e3886a-7059-47ee-bdb2-aa5fb1272bea': '/hora', // hora
  'c41b6602-f7b2-437d-bcfc-0462cd385eda': '/fracción', // fraccion
  'd83ebff8-9546-43b3-91b1-bedffa57717f': '/día', // plena
  '9f8ba4a9-6fd9-4da7-8ddb-97ce323a8600': '/noche', // nocturna
};

/** "/hora" | "/fracción" | "/día" | "/noche", or '' when the modalidad is unknown. */
export function etiquetaUnidadTarifa(uuidTipoTarifa: string | null | undefined): string {
  if (typeof uuidTipoTarifa !== 'string') return '';
  return UNIDAD_POR_MODALIDAD[uuidTipoTarifa.trim().toLowerCase()] ?? '';
}
