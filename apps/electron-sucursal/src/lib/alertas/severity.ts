/**
 * `severity.ts` -- UNICO punto de traduccion de severidad de alertas en
 * sucursal.
 *
 * Vocabulario canonico (BD `prod.alert_types.severity`, el que consume
 * web_admin): `critical | warning | info`. El endpoint
 * `GET /workflows/alert-types` conserva el vocabulario legado de esta app
 * (`alta | media | baja`) para no romper su contrato; esta tabla espeja
 * `repo/alert_types.py::severity_to_severidad` del backend.
 */
export const ALERT_SEVERITIES = ['critical', 'warning', 'info'] as const;
export type AlertSeverity = (typeof ALERT_SEVERITIES)[number];

export const SEVERIDADES = ['alta', 'media', 'baja'] as const;
export type Severidad = (typeof SEVERIDADES)[number];

const SEVERITY_TO_SEVERIDAD: Readonly<Record<AlertSeverity, Severidad>> = {
  critical: 'alta',
  warning: 'media',
  info: 'baja',
};

export function severityToSeveridad(severity: AlertSeverity): Severidad {
  return SEVERITY_TO_SEVERIDAD[severity];
}

/** Severidad neutra cuando no se conoce ninguna (equivale a `warning`). */
export const SEVERIDAD_NEUTRA: Severidad = severityToSeveridad('warning');
