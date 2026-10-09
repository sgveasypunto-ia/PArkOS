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

export type CatalogFieldType = 'text' | 'number' | 'checkbox' | 'select' | 'textarea';

export interface CatalogFieldOption {
  value: string;
  label: string;
}

export interface CatalogField {
  name: string;
  label: string;
  type?: CatalogFieldType;
  required?: boolean;
  /**
   * `select` only: catalog whose vigente rows feed the options.
   * Mutually exclusive with `options` (literal list).
   */
  optionsResource?: CatalogResource;
  /** `select` only: row key used as the option label. */
  optionsLabelKey?: string;
  /**
   * `select` only: row key used as the option `value`. Defaults to `uuid`.
   * Set to a non-uuid key (e.g. `tipo`) when the backend field is a free
   * string keyed by the option's `tipo` (e.g. `tipo_cliente_permitido`).
   */
  optionsValueKey?: string;
  /** `select` only: label of the empty option (value ''). */
  emptyOptionLabel?: string;
  /**
   * `select` only: when `false`, the empty option is NOT rendered and the
   * user must pick one of the offered values. Defaults to `true` (the
   * historical behavior). Use `false` for fields where "no value" is not
   * a legal UI state (e.g. `uuid_tipo_vehiculo` once a plan is assigned).
   */
  allowEmpty?: boolean;
  /**
   * `select` only: literal option list. Use when the values are a fixed
   * enum not driven by another catalog (e.g. `tipo_calculo` ∈
   * {'', 'porcentaje', 'fijo'}).
   */
  options?: CatalogFieldOption[];
  /** `text` / `textarea`: placeholder text for empty input. */
  placeholder?: string;
  /** Render a multi-line textarea instead of a single-line input. */
  multiline?: boolean;
  /**
   * Optional row-value → form-value transform used to populate the field
   * when editing. The default is identity (or `''` when the row has no value).
   * Use for fields whose row type and form type differ (e.g. JSONB dicts
   * stored on the row, edited as a JSON string in the textarea).
   */
  formatForEdit?: (rowValue: unknown) => unknown;
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
  /**
   * Optional pre-flight check on the form values before any POST/PUT.
   * Use for cross-field or format validation (e.g. JSON syntax) that
   * Zod's per-field schema can't express. Return a message to block
   * the submit, or `null` to continue. The message is shown inline in
   * the dialog next to the offending field name when possible, else
   * in the dialog's submit error region.
   */
  validateForm?: (values: Record<string, unknown>) => string | null;
}
