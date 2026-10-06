/**
 * Tipos compartidos por las configs de los 9 catálogos.
 *
 * Cada config declara: el `resource` (slug de la URL), el label,
 * la lista de campos editables, y los `defaults` del formulario.
 * El `CatalogEditor` consume esta config para renderizar la tabla
 * + el dialog sin saber nada del catálogo concreto.
 *
 * `fieldTypes` mirror los Pydantic types del backend:
 *   - `text`    → str (max length por config)
 *   - `number`  → Decimal/int en backend; el form manda float, Pydantic coerca
 *   - `checkbox` → bool (true/false en JSON, nativo)
 *
 * El shape del form field DEBE matchear el schema `*Create` del backend
 * (`extra="forbid"` rechaza lo que no esté declarado). Ver
 * `backend/.../schemas/{tipo_persona,impuestos,...}.py`.
 */
import type { z } from 'zod';
import type { CatalogResource } from '../api/catalogApi';

export type CatalogFieldType = 'text' | 'number' | 'checkbox' | 'select';

export interface CatalogField {
  name: string;
  label: string;
  type?: CatalogFieldType;
  required?: boolean;
  /** `select` only: catalog whose vigente rows feed the options (value = row uuid). */
  optionsResource?: CatalogResource;
  /** `select` only: row key used as the option label. */
  optionsLabelKey?: string;
  /** `select` only: label of the empty option (value ''). */
  emptyOptionLabel?: string;
  /** Helper text rendered under the control (referenced by aria-describedby). */
  hint?: string;
}

export interface CatalogColumn {
  key: string;
  label: string;
  render?: (value: unknown, row: Record<string, unknown>) => React.ReactNode;
}

export interface CatalogConfig {
  resource: CatalogResource;
  tabKey: string;
  singularLabel: string;
  pluralLabel: string;
  fields: CatalogField[];
  columns: CatalogColumn[];
  defaults: Record<string, unknown>;
  /**
   * Mapea el form values al payload que acepta `*Create` del backend.
   * Por default es un identity spread. Usar override para convertir
   * strings a JSON (ej. `caracteristicas`) o filtrar campos vacios.
   */
  toCreatePayload: (form: Record<string, unknown>) => Record<string, unknown>;
  schema?: z.ZodTypeAny;
  /**
   * Optional pre-flight check when saving a new version over an existing row.
   * Return a message to block the submit, or `null` to continue.
   */
  validateUpdate?: (
    previous: Record<string, unknown>,
    next: Record<string, unknown>,
  ) => string | null;
}
