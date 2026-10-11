/**
 * `modalidadMeta.ts` — UI metadata for the 4 canonical ``prod.tipo_tarifa``
 * modalidades (Hora / Fraccion / Plena / Nocturna).
 *
 * Centralises the icon, accent color, label, and helper text for each
 * so the form and the preview can iterate over a single lookup instead
 * of duplicating a 4-way switch in every place that needs to render a
 * modalidad. The keys match ``TIPO_TARIFA_UUIDS`` in ``tarifaAgrupada.ts``
 * so the caller can index by the tarifa row's ``uuid_tipo_tarifa``.
 *
 * Design choices (operator feedback 2026-10-11):
 * - Hora = blue (clock icon)        — "tiempo por hora"
 * - Fracción = violet (divide icon) — "fracción de hora"
 * - Plena = amber (sun icon)        — "día completo"
 * - Nocturna = indigo (moon icon)   — "tarifa nocturna"
 *
 * Tailwind accent classes are kept short to fit the es-CO "compact"
 * aesthetic the rest of the admin uses.
 */
import { Clock, Divide, Moon, Sun, type LucideIcon } from 'lucide-react';

import {
  TIPO_TARIFA_FRACCION,
  TIPO_TARIFA_HORA,
  TIPO_TARIFA_NOCTURNA,
  TIPO_TARIFA_PLENA,
} from '../api/tarifaAgrupada';

export type ModalidadKey = 'hora' | 'fraccion' | 'plena' | 'nocturna';

export interface ModalidadMeta {
  /** UUID string of the canonical modalidad (mirror of backend). */
  uuid: string;
  /** Human label in es-CO. */
  label: string;
  /** Lucide icon component for the card header. */
  icon: LucideIcon;
  /** Tailwind class for the icon + accent border. */
  accent: string;
  /** Placeholder for the numeric input (suggested price, whole pesos). */
  placeholder: string;
  /** One-line inline helper under the input (es-CO). */
  help: string;
}

export const MODALIDAD_META: Record<ModalidadKey, ModalidadMeta> = {
  hora: {
    uuid: TIPO_TARIFA_HORA,
    label: 'Hora',
    icon: Clock,
    accent: 'text-blue-500',
    placeholder: '1500',
    help: 'Por hora',
  },
  fraccion: {
    uuid: TIPO_TARIFA_FRACCION,
    label: 'Fracción',
    icon: Divide,
    accent: 'text-violet-500',
    placeholder: '800',
    help: 'Por fracción de hora',
  },
  plena: {
    uuid: TIPO_TARIFA_PLENA,
    label: 'Plena',
    icon: Sun,
    accent: 'text-amber-500',
    placeholder: '2000',
    help: 'Por día completo',
  },
  nocturna: {
    uuid: TIPO_TARIFA_NOCTURNA,
    label: 'Nocturna',
    icon: Moon,
    accent: 'text-indigo-500',
    placeholder: '1000',
    help: 'Por horario nocturno',
  },
};

/** Lookup the modalidad key (the map key) from a tarifa uuid.
 * Returns ``null`` for unknown UUIDs so callers can fall back to a
 * generic rendering instead of crashing. */
export function getModalidadKey(uuid: string | null | undefined): ModalidadKey | null {
  if (uuid === TIPO_TARIFA_HORA) return 'hora';
  if (uuid === TIPO_TARIFA_FRACCION) return 'fraccion';
  if (uuid === TIPO_TARIFA_PLENA) return 'plena';
  if (uuid === TIPO_TARIFA_NOCTURNA) return 'nocturna';
  return null;
}
