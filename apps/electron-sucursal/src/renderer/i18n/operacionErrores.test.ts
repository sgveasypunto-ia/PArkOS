/**
 * AUD3 — every `setSubmitError('<codigo>')` of the ingreso / salida forms is
 * rendered with `t('error_<codigo>')`: a missing key shows the raw snake_case
 * code to the operator.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import operacion from './locales/operacion.json';

const RAIZ = join(__dirname, '..', '..', 'features', 'operacion');
const ARCHIVOS = [
  'components/IngresoPanel.tsx',
  'components/IngresoSinPlacaPanel.tsx',
  'pages/Principal.tsx',
];

describe('errores de ingreso: ningún código crudo llega a la UI', () => {
  const codigos = new Set<string>();
  for (const archivo of ARCHIVOS) {
    const fuente = readFileSync(join(RAIZ, archivo), 'utf-8');
    for (const m of fuente.matchAll(/setSubmitError\('([a-z0-9_]+)'\)/g)) codigos.add(m[1]);
  }

  it('encuentra los códigos usados por los formularios', () => {
    expect(codigos.size).toBeGreaterThan(5);
  });

  it.each([...codigos])('error_%s tiene traducción en español', (codigo) => {
    const texto = (operacion as Record<string, string>)[`error_${codigo}`];
    expect(texto, `falta error_${codigo} en operacion.json`).toBeTruthy();
    expect(texto).not.toMatch(/^[a-z0-9_]+$/);
  });
});
