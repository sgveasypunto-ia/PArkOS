/**
 * Tipos compartidos por las configs de los 9 catálogos.
 *
 * Cada config declara: el `resource` (slug de la URL), el label,
 * la lista de campos editables, y los `defaults` del formulario.
 * El `CatalogEditor` consume esta config para renderizar la tabla
 * + el dialog sin saber nada del catálogo concreto.
 */
import type { z } from 'zod';
import type { CatalogResource } from '../api/catalogApi';

export type CatalogFieldType = 'text' | 'number' | 'email';

export interface CatalogField {
  name: string;
  label: string;
  type?: CatalogFieldType;
  required?: boolean;
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
  toCreatePayload: (form: Record<string, unknown>) => Record<string, unknown>;
  schema?: z.ZodTypeAny;
}

export const NUMERIC_FIELDS = new Set<string>([
  'porcentaje',
  'valor',
  'valor_plena',
  'tolerancia_efectivo',
  'tolerancia_datafono',
]);
