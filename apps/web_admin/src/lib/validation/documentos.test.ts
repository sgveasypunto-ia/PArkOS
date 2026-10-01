/**
 * `documentos.test.ts` — unit tests para la validación de tamaño/formato
 * de `prod.documentos` (HU-F15.4, T2).
 */
import { describe, expect, it } from 'vitest';

import {
  MAX_DOCUMENTO_BYTES,
  base64ToText,
  fileToBase64,
  formatBytes,
  textToBase64,
  validarFormatoArchivo,
  validarLongitudBase64,
  validarTamanoArchivo,
  validarTamanoTexto,
} from './documentos';

function makeFile(sizeBytes: number, type: string, name = 'archivo'): File {
  const content = new Uint8Array(sizeBytes);
  return new File([content], name, { type });
}

describe('formatBytes', () => {
  it('formatea bytes, KB y MB', () => {
    expect(formatBytes(500)).toBe('500 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(MAX_DOCUMENTO_BYTES)).toBe('1.00 MB');
  });
});

describe('validarTamanoArchivo', () => {
  it('acepta un archivo exactamente en el límite (1 MiB)', () => {
    const file = makeFile(MAX_DOCUMENTO_BYTES, 'image/png');
    expect(validarTamanoArchivo(file).ok).toBe(true);
  });

  it('rechaza un archivo de más de 1 MiB', () => {
    const file = makeFile(MAX_DOCUMENTO_BYTES + 1, 'image/png');
    const r = validarTamanoArchivo(file);
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/1 MB/);
  });
});

describe('validarTamanoTexto', () => {
  it('acepta texto corto', () => {
    expect(validarTamanoTexto('observación corta').ok).toBe(true);
  });

  it('rechaza texto que excede 1MB de bytes UTF-8', () => {
    const texto = 'a'.repeat(MAX_DOCUMENTO_BYTES + 1);
    const r = validarTamanoTexto(texto);
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/1 MB/);
  });
});

describe('validarFormatoArchivo', () => {
  it('siempre ok para tipo observaciones (no es upload de archivo)', () => {
    const file = makeFile(10, '');
    expect(validarFormatoArchivo(file, 'observaciones').ok).toBe(true);
  });

  it('rechaza cuando el navegador no pudo determinar el MIME real', () => {
    const file = makeFile(10, '');
    const r = validarFormatoArchivo(file, 'logo');
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/no se pudo determinar/i);
  });

  it('acepta un formato permitido para logo', () => {
    const file = makeFile(10, 'image/png');
    expect(validarFormatoArchivo(file, 'logo').ok).toBe(true);
  });

  it('rechaza un formato no permitido para logo (ej. PDF)', () => {
    const file = makeFile(10, 'application/pdf');
    const r = validarFormatoArchivo(file, 'logo');
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/no permitido/i);
  });

  it('acepta PDF para certificado (BR2: PDF o imagen escaneada)', () => {
    const file = makeFile(10, 'application/pdf');
    expect(validarFormatoArchivo(file, 'certificado').ok).toBe(true);
  });

  it('acepta imagen escaneada para certificado (BR2)', () => {
    const file = makeFile(10, 'image/jpeg');
    expect(validarFormatoArchivo(file, 'certificado').ok).toBe(true);
  });
});

describe('validarLongitudBase64', () => {
  it('acepta una cadena corta', () => {
    expect(validarLongitudBase64('QUJD').ok).toBe(true);
  });

  it('rechaza una cadena que excede el cap del backend (REQ-OP-05)', () => {
    const r = validarLongitudBase64('a'.repeat(1_400_001));
    expect(r.ok).toBe(false);
  });
});

describe('fileToBase64', () => {
  it('convierte un File a base64 puro, sin el prefijo data:', async () => {
    const file = new File(['ABC'], 'a.txt', { type: 'text/plain' });
    const b64 = await fileToBase64(file);
    expect(b64).not.toMatch(/^data:/);
    expect(base64ToText(b64)).toBe('ABC');
  });
});

describe('textToBase64 / base64ToText', () => {
  it('hace round-trip de texto plano ASCII', () => {
    const texto = 'Observación de prueba';
    expect(base64ToText(textToBase64(texto))).toBe(texto);
  });

  it('hace round-trip de texto con acentos y ñ (UTF-8)', () => {
    const texto = 'Atención: sucursal cerrará mañana por mantenimiento.';
    expect(base64ToText(textToBase64(texto))).toBe(texto);
  });

  it('hace round-trip de string vacío', () => {
    expect(base64ToText(textToBase64(''))).toBe('');
  });
});
