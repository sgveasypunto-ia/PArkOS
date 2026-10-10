/**
 * Contraste del texto de error (`text-destructive`) en tema oscuro.
 *
 * `--destructive` en oscuro es un rojo oscuro pensado como RELLENO (boton con
 * texto claro encima); usado como color de texto sobre las superficies
 * oscuras da ~1.6:1. El texto usa `--destructive-text`, calculado aqui contra
 * las tres superficies reales (--background, --card, --gray-700 de
 * popover/muted) con el minimo AA de 4.5:1.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const css = (f: string): string => readFileSync(resolve(__dirname, '..', f), 'utf-8');
const tokens = readFileSync(resolve(__dirname, 'tokens.css'), 'utf-8');
const indexCss = css('index.css');

type Hsl = [number, number, number];

function parseHsl(value: string): Hsl {
  const m = /^\s*(-?[\d.]+)\s+([\d.]+)%\s+([\d.]+)%/.exec(value);
  if (!m) throw new Error(`hsl no parseable: ${value}`);
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

function luminance([h, s, l]: Hsl): number {
  const sat = s / 100;
  const lig = l / 100;
  const a = sat * Math.min(lig, 1 - lig);
  const f = (n: number): number => {
    const k = (n + h / 30) % 12;
    return lig - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  };
  const lin = (v: number): number => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(f(0)) + 0.7152 * lin(f(8)) + 0.0722 * lin(f(4));
}

function contraste(a: Hsl, b: Hsl): number {
  const [la, lb] = [luminance(a), luminance(b)];
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

const token = (src: string, name: string): string => {
  const m = new RegExp(`${name}:\\s*([^;]+);`).exec(src);
  if (!m) throw new Error(`token ausente: ${name}`);
  return m[1] ?? '';
};

const darkBlock = /\n {2}\.dark \{[\s\S]*?\n {2}\}/.exec(indexCss)?.[0] ?? '';

describe('texto de error en tema oscuro', () => {
  const texto = parseHsl(token(darkBlock, '--destructive-text'));
  const superficies: Array<[string, Hsl]> = [
    ['--background (gray-900)', parseHsl(token(tokens, '--gray-900'))],
    ['--card (gray-800)', parseHsl(token(tokens, '--gray-800'))],
    ['popover/muted (gray-700)', parseHsl(token(tokens, '--gray-700'))],
  ];

  it.each(superficies)('--destructive-text >= 4.5:1 sobre %s', (_n, fondo) => {
    expect(contraste(texto, fondo)).toBeGreaterThanOrEqual(4.5);
  });

  it('text-destructive usa --destructive-text en oscuro (no el relleno --destructive)', () => {
    expect(indexCss).toMatch(
      /\.dark \.text-destructive\s*\{\s*color:\s*hsl\(var\(--destructive-text\)\)/,
    );
  });

  it('el relleno --destructive no se toca (texto claro encima sigue >= 4.5:1)', () => {
    const relleno = parseHsl(token(darkBlock, '--destructive'));
    const encima = parseHsl(token(darkBlock, '--destructive-foreground'));
    expect(contraste(encima, relleno)).toBeGreaterThanOrEqual(4.5);
  });
});

describe('texto secundario (--muted-foreground) en tema oscuro', () => {
  // --muted-foreground resuelve a --gray-dark-secondary en oscuro. Se mide
  // contra las tres superficies reales: el popover (gray-700) es la mas
  // clara y la que fallaba (4.46:1 con 65% L, medido en el navegador).
  const texto = parseHsl(token(tokens, '--gray-dark-secondary'));
  const superficies: Array<[string, Hsl]> = [
    ['--background (gray-900)', parseHsl(token(tokens, '--gray-900'))],
    ['--card (gray-800)', parseHsl(token(tokens, '--gray-800'))],
    ['popover/muted (gray-700)', parseHsl(token(tokens, '--gray-700'))],
  ];

  it('en oscuro --muted-foreground resuelve a --gray-dark-secondary', () => {
    expect(token(darkBlock, '--muted-foreground')).toContain('--gray-dark-secondary');
  });

  it.each(superficies)('--gray-dark-secondary >= 4.5:1 sobre %s', (_n, fondo) => {
    expect(contraste(texto, fondo)).toBeGreaterThanOrEqual(4.5);
  });
});
