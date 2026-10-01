/**
 * `documentos.ts` — validación de tamaño/formato en cliente para
 * `prod.documentos` (HU-F15.4, T2).
 *
 * Contrato real confirmado contra `backend/.../schemas/empresa.py`:
 *   - `DocumentosCreate.documento_b64` usa
 *     `StringConstraints(max_length=1_400_000)` (REQ-OP-05) — ~1MB en
 *     base64. El backend YA valida esto (422 genérico de Pydantic,
 *     `type: "string_too_long"`) — doble defensa real, aunque NO existe
 *     un código de error custom `documento_demasiado_pesado` en el
 *     backend (se buscó explícitamente, no aparece en ningún handler).
 *   - `DocumentosCreate.formato` es un `string` libre (`max_length=32`),
 *     SIN validación de MIME/enum en el servidor — no existe tampoco un
 *     código `formato_invalido` backend. La coherencia "formato real del
 *     archivo" (BR2) es, hoy, una responsabilidad 100% del cliente.
 *
 * `MAX_DOCUMENTO_BYTES` (1 MiB = 1_048_576 bytes) se eligió porque su
 * base64 resultante (`ceil(n/3)*4` = 1_398_104 caracteres) queda bajo el
 * límite real del backend (1_400_000) con margen — así el chequeo
 * "¿pesa menos de 1MB?" en el cliente nunca deja pasar un archivo que el
 * server vaya a rechazar.
 */

/** Tipos de documento soportados por esta pantalla (BR1/BR2/BR3 de HU-F15.4). */
export const DOCUMENTO_TIPOS = [
  'logo',
  'certificado',
  'plantilla_ticket',
  'observaciones',
] as const;

export type DocumentoTipo = (typeof DOCUMENTO_TIPOS)[number];

/** 1 MiB. Ver docstring del módulo para el cálculo del margen de base64. */
export const MAX_DOCUMENTO_BYTES = 1_048_576;

/** Espejo del `StringConstraints(max_length=...)` de `DocumentosCreate` (REQ-OP-05). */
export const MAX_DOCUMENTO_B64_CHARS = 1_400_000;

/**
 * MIME types reales aceptados por tipo de documento (BR2: "puede ser PDF
 * o imagen escaneada" para `certificado`; `logo` se imprime en tickets y
 * FE así que se restringe a formatos de imagen razonables;
 * `plantilla_ticket` admite texto, PDF o imagen). `observaciones` no
 * tiene entrada acá porque no es un upload de archivo (BR3: texto plano).
 */
export const ACCEPTED_MIME_BY_TIPO: Partial<Record<DocumentoTipo, readonly string[]>> = {
  logo: ['image/png', 'image/jpeg', 'image/webp', 'image/svg+xml'],
  certificado: ['application/pdf', 'image/png', 'image/jpeg', 'image/webp'],
  plantilla_ticket: ['text/plain', 'application/pdf', 'image/png', 'image/jpeg'],
};

export interface ValidacionResultado {
  ok: boolean;
  message?: string;
}

/** Formatea bytes en una unidad legible (B/KB/MB), en español. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(2)} MB`;
}

/** BR: tamaño ≤ 1MB, validado en cliente ANTES de codificar a base64. */
export function validarTamanoArchivo(file: File): ValidacionResultado {
  if (file.size > MAX_DOCUMENTO_BYTES) {
    return {
      ok: false,
      message: `El archivo pesa ${formatBytes(file.size)}; el máximo permitido es 1 MB (${formatBytes(MAX_DOCUMENTO_BYTES)}).`,
    };
  }
  return { ok: true };
}

/** Mismo límite que `validarTamanoArchivo`, pero para el textarea de `observaciones`. */
export function validarTamanoTexto(texto: string): ValidacionResultado {
  const bytes = new TextEncoder().encode(texto).length;
  if (bytes > MAX_DOCUMENTO_BYTES) {
    return {
      ok: false,
      message: `El texto pesa ${formatBytes(bytes)}; el máximo permitido es 1 MB (${formatBytes(MAX_DOCUMENTO_BYTES)}).`,
    };
  }
  return { ok: true };
}

/**
 * BR2: `formato` debe reflejar el tipo MIME REAL del archivo, nunca la
 * extensión del nombre — por eso esta función usa `file.type` (el
 * navegador ya detecta el tipo real por contenido/magic bytes, no por
 * el nombre) y rechaza explícitamente cuando el navegador no pudo
 * determinarlo (`file.type === ''`), en vez de dejar pasar un `formato`
 * vacío o inventado.
 */
export function validarFormatoArchivo(file: File, tipo: DocumentoTipo): ValidacionResultado {
  if (tipo === 'observaciones') return { ok: true };
  if (!file.type) {
    return {
      ok: false,
      message: 'No se pudo determinar el tipo real del archivo. Probá con otro archivo.',
    };
  }
  const accepted = ACCEPTED_MIME_BY_TIPO[tipo];
  if (accepted && !accepted.includes(file.type)) {
    return {
      ok: false,
      message: `Formato "${file.type}" no permitido para este documento. Formatos aceptados: ${accepted.join(', ')}.`,
    };
  }
  return { ok: true };
}

/** Red de seguridad final, espejo exacto del cap real del backend (REQ-OP-05). */
export function validarLongitudBase64(b64: string): ValidacionResultado {
  if (b64.length > MAX_DOCUMENTO_B64_CHARS) {
    return {
      ok: false,
      message: 'El contenido codificado excede el límite permitido por el servidor.',
    };
  }
  return { ok: true };
}

/**
 * Convierte un `File` del browser a base64 puro (sin el prefijo
 * `data:<mime>;base64,` que agrega `FileReader.readAsDataURL`).
 */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error('No se pudo leer el archivo.'));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== 'string') {
        reject(new Error('Lectura de archivo inválida.'));
        return;
      }
      const commaIdx = result.indexOf(',');
      resolve(commaIdx >= 0 ? result.slice(commaIdx + 1) : result);
    };
    reader.readAsDataURL(file);
  });
}

/**
 * Codifica texto plano a base64 (BR3: `observaciones`), UTF-8 safe
 * (evita el patrón deprecado `btoa(unescape(encodeURIComponent(...)))`).
 */
export function textToBase64(texto: string): string {
  const bytes = new TextEncoder().encode(texto);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]!);
  }
  return btoa(binary);
}

/** Inverso de {@link textToBase64}. */
export function base64ToText(b64: string): string {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new TextDecoder().decode(bytes);
}
