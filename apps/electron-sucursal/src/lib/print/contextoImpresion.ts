/**
 * `contextoImpresion.ts` — FC1: the REAL header data of every printed ticket.
 *
 * The ticket builders used to hard-code a placeholder company ("Parkos S.A.S.",
 * NIT 900.000.000-1, operator "Operador"). This helper hydrates the
 * `PrintContext` once, from:
 *   - `GET /empresa/empresa`  → the open empresa (nombre, NIT with its DV,
 *     régimen). The list is the same one the invoice emisor falls back to when
 *     `sucursal.uuid_empresa` is NULL, so the first open row is the right one.
 *   - `GET /empresa/sucursal` → the operator's branch (nombre, dirección,
 *     horario), matched by the `sucursal.uuid` of `auth/me`.
 *   - `GET /auth/me`          → the logged-in operator's name.
 *
 * Cached for `TTL_MS` with in-flight de-duplication (SWR-like). Failures are
 * never cached: the context degrades to `{}` (the builders then use their
 * placeholder defaults) and a console warning is emitted.
 */
import { parkosFetch } from '@parkos/ui-kit/fetch';

import type { Empresa } from './escposTemplates';
import type { PrintContext } from './printBuilder';

const TTL_MS = 5 * 60 * 1000;
/** A hung API must never block printing the ticket. */
const PLAZO_MS = 4_000;
const SIN_DIRECCION = 'Sin direccion registrada';
const NO_REGISTRADO = 'No registrado';

export interface EmpresaApi {
  nombre: string | null;
  nit: string | null;
  regimen: string | null;
  vigente_hasta?: string | null;
  estado?: string;
}

export interface SucursalApi {
  uuid: string;
  nombre: string | null;
  direccion: string | null;
  prefijo_nombre: string | null;
  horario: string | null;
  vigente_hasta?: string | null;
  estado?: string;
}

export interface MeApi {
  user?: { email?: string | null; nombre?: string | null; apellido?: string | null } | null;
  sucursal?: { uuid?: string | null; nombre?: string | null; prefijo_nombre?: string | null } | null;
}

function texto(v: string | null | undefined): string | null {
  return typeof v === 'string' && v.trim() !== '' ? v.trim() : null;
}

function capitalizar(v: string): string {
  return v.charAt(0).toUpperCase() + v.slice(1);
}

/** Operator display name: "nombre apellido", else the e-mail, else null. */
export function nombreOperador(user: MeApi['user']): string | null {
  if (!user) return null;
  const nombre = [user.nombre, user.apellido]
    .map(texto)
    .filter((p): p is string => p !== null)
    .join(' ');
  return nombre !== '' ? nombre : texto(user.email);
}

export interface DatosContexto {
  empresa: EmpresaApi | null;
  sucursal: SucursalApi | null;
  me: MeApi | null;
}

/** Pure mapper API rows → `PrintContext` (only fields with real data are set). */
export function construirContextoImpresion({ empresa, sucursal, me }: DatosContexto): PrintContext {
  const ctx: {
    -readonly [K in keyof PrintContext]: PrintContext[K];
  } = {};

  if (empresa) {
    const nombre = texto(empresa.nombre);
    const regimen = texto(empresa.regimen);
    const real: Empresa = {
      nombre: nombre ?? NO_REGISTRADO,
      nit: texto(empresa.nit) ?? NO_REGISTRADO,
      direccion: texto(sucursal?.direccion) ?? SIN_DIRECCION,
      regimen: regimen !== null ? capitalizar(regimen) : NO_REGISTRADO,
    };
    ctx.empresa = real;
  }

  const encabezado =
    texto(sucursal?.nombre) ??
    texto(sucursal?.prefijo_nombre) ??
    texto(me?.sucursal?.nombre) ??
    texto(me?.sucursal?.prefijo_nombre);
  if (encabezado !== null) ctx.sucursalEncabezado = encabezado;

  const horario = texto(sucursal?.horario);
  if (horario !== null) ctx.horarioAtencion = horario;

  const operario = nombreOperador(me?.user);
  if (operario !== null) ctx.operario = operario;

  return ctx;
}

function abierta<T extends { vigente_hasta?: string | null; estado?: string }>(items: readonly T[]): T[] {
  const vivas = items.filter((i) => (i.vigente_hasta ?? null) === null && (i.estado ?? 'activo') === 'activo');
  return vivas.length > 0 ? vivas : [...items];
}

async function cargar(): Promise<PrintContext> {
  const [empresas, sucursales, me] = await Promise.all([
    parkosFetch<{ items: EmpresaApi[] }>('/api/v1/empresa/empresa'),
    parkosFetch<{ items: SucursalApi[] }>('/api/v1/empresa/sucursal'),
    parkosFetch<MeApi>('/api/v1/auth/me'),
  ]);
  const empresa = abierta(empresas.items)[0] ?? null;
  const propias = abierta(sucursales.items);
  const uuidSucursal = me.sucursal?.uuid ?? null;
  const sucursal =
    (uuidSucursal !== null ? propias.find((s) => s.uuid === uuidSucursal) : undefined) ??
    (propias.length === 1 ? propias[0] : undefined) ??
    null;
  return construirContextoImpresion({ empresa, sucursal: sucursal ?? null, me });
}

function conPlazo<T>(p: Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error('contexto de impresión: plazo agotado')), PLAZO_MS);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e: unknown) => {
        clearTimeout(t);
        reject(e instanceof Error ? e : new Error(String(e)));
      },
    );
  });
}

let cache: { en: number; valor: Promise<PrintContext> } | null = null;

export function limpiarCacheContextoImpresion(): void {
  cache = null;
}

/**
 * Resolve the print context (cached ~5 min, concurrent callers share one
 * request). Never throws: on any failure it returns `{}` so the builders use
 * their placeholder defaults, and warns in the console.
 */
export function resolverContextoImpresion(): Promise<PrintContext> {
  const ahora = Date.now();
  if (cache !== null && ahora - cache.en < TTL_MS) return cache.valor;
  const valor = conPlazo(cargar()).catch((err: unknown) => {
    console.warn('[contextoImpresion] no se pudo leer empresa/sucursal/operador; se usa el encabezado por defecto', err);
    if (cache?.valor === valor) cache = null;
    return {} as PrintContext;
  });
  cache = { en: ahora, valor };
  return valor;
}
