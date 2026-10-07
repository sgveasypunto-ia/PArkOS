/**
 * Static guard: `bridge.imprimir` only accepts ONE object argument
 * (`{ buffer, ticketId, cut }`). The retired `imprimir('arqueo', payload)`
 * (tipo, payload) signature is rejected by the IPC and silently printed
 * nothing, so no source file may call `imprimir(` with a string first argument.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

const SRC = join(__dirname, '..', '..', '..');

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === 'node_modules' || name === '__tests__') continue;
      walk(full, out);
    } else if (/\.(ts|tsx)$/.test(name) && !/\.(test|spec)\.(ts|tsx)$/.test(name)) {
      out.push(full);
    }
  }
  return out;
}

/** Strip comments so prose describing the old convention does not trip the guard. */
function sinComentarios(code: string): string {
  return code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

describe('firma antigua de imprimir(tipo, payload)', () => {
  it('ningún archivo fuente llama imprimir( con un string como primer argumento', () => {
    const ofensores: string[] = [];
    for (const file of walk(SRC)) {
      const code = sinComentarios(readFileSync(file, 'utf8'));
      if (/\bimprimir\s*\(\s*['"`]/.test(code)) ofensores.push(relative(SRC, file));
      // Tipos de la firma antigua `imprimir(kind: string, payload...)`.
      if (/\bimprimir\s*\(\s*kind\s*:\s*string/.test(code)) ofensores.push(relative(SRC, file));
    }
    expect(ofensores).toEqual([]);
  });
});
