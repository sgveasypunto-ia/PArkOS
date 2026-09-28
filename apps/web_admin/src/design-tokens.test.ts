import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Contract test for the design tokens in `index.css`.
 *
 * Two failure modes motivated this file, and both fail *silently* at build
 * time rather than loudly:
 *
 * 1. `hsl(var(--typo))` for a variable nobody defined compiles fine and
 *    renders as an invalid color, i.e. transparent. The only symptom is a
 *    UI element that quietly loses its background.
 * 2. macOS system colors are vivid by default. #007AFF is 4.02:1 on white
 *    and #34C759 is ~2.2:1, so copying the palette verbatim puts 14px
 *    button labels below WCAG AA without any tool complaining.
 *
 * So this asserts the wiring (every referenced variable is defined in both
 * light and dark) and the contrast (every text-on-fill pair clears 4.5:1).
 */

// vitest runs with cwd pinned to the app root, and `import.meta.url` is an
// http: URL under jsdom, so it cannot be handed to fileURLToPath.
const appRoot = process.cwd();
// Strip `/* ... */` first, otherwise a comment spanning lines before a
// declaration gets swallowed into the previous token's value.
const css = readFileSync(path.join(appRoot, 'src/index.css'), 'utf8').replace(
  /\/\*[\s\S]*?\*\//g,
  '',
);
const tailwindConfig = readFileSync(
  path.join(appRoot, 'tailwind.config.ts'),
  'utf8',
);

type Tokens = Record<string, string>;

function blockTokens(selector: string): Tokens {
  // `:root` also matches inside `.dark`? No -- but `.dark` appears once.
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\n\\s*\\}`).exec(css);
  if (!match) throw new Error(`no \`${selector}\` block found in index.css`);

  const tokens: Tokens = {};
  for (const [, name, value] of match[1].matchAll(
    /(--[a-z0-9-]+)\s*:\s*([^;]+);/g,
  )) {
    tokens[name] = value.trim();
  }
  return tokens;
}

const root = blockTokens(':root');
const dark = blockTokens('.dark');

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hPrime = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hPrime % 2) - 1));
  const m = l - c / 2;
  const sector = Math.floor(hPrime) % 6;
  const table: [number, number, number][] = [
    [c, x, 0],
    [x, c, 0],
    [0, c, x],
    [0, x, c],
    [x, 0, c],
    [c, 0, x],
  ];
  const [r, g, b] = table[sector] ?? [0, 0, 0];
  return [r + m, g + m, b + m];
}

function relativeLuminance(rgb: [number, number, number]): number {
  const [r, g, b] = rgb.map((channel) => {
    const v = Math.min(Math.max(channel, 0), 1);
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * (r as number) + 0.7152 * (g as number) + 0.0722 * (b as number);
}

/** Resolve an `211 100% 45%` style token into linear RGB. */
function tokenToRgb(token: string): [number, number, number] {
  const parts = token.trim().split(/\s+/);
  if (parts.length !== 3) {
    throw new Error(`\`${token}\` is not a space-separated HSL triple`);
  }
  const [h, s, l] = parts as [string, string, string];
  return hslToRgb(
    parseFloat(h),
    parseFloat(s) / 100,
    parseFloat(l) / 100,
  );
}

function contrast(a: [number, number, number], b: [number, number, number]) {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** Contrast of `foreground` text painted on `background` in one scope. */
function contrastIn(scope: Tokens, foreground: string, background: string) {
  const fg = scope[foreground];
  const bg = scope[background];
  if (!fg) throw new Error(`${foreground} is not defined`);
  if (!bg) throw new Error(`${background} is not defined`);
  return contrast(tokenToRgb(fg), tokenToRgb(bg));
}

describe('tailwind color wiring', () => {
  const referenced = [
    ...new Set(
      [...tailwindConfig.matchAll(/hsl\(var\(--([a-z0-9-]+)\)\)/g)].map(
        (match) => `--${match[1]}`,
      ),
    ),
  ].sort();

  it('finds the color variables in tailwind.config.ts', () => {
    // Guards against this test silently passing on an empty match set.
    expect(referenced.length).toBeGreaterThanOrEqual(15);
  });

  it.each([':root', '.dark'] as const)(
    'defines every variable tailwind.config.ts references in %s',
    (scopeName) => {
      const scope = scopeName === ':root' ? root : dark;
      const missing = referenced.filter((name) => !(name in scope));
      expect(missing).toEqual([]);
    },
  );
});

describe('macOS design tokens', () => {
  // Custom properties inherit, so `.dark` only has to redeclare what must
  // change. Motion curves and blur radius are identical in both scopes.
  it.each([
    '--ease-macos',
    '--duration-fast',
    '--duration-base',
    '--backdrop-filter',
    '--surface-translucent',
    '--surface-translucent-alpha',
  ])('declares %s in :root', (token) => {
    expect(root, `${token} missing`).toHaveProperty(token);
  });

  it.each(['--shadow-elevation-1', '--shadow-elevation-2', '--shadow-elevation-3'])(
    're-declares %s for .dark, because shadows need more opacity on a dark page',
    (token) => {
      expect(dark, `${token} not overridden for dark`).toHaveProperty(token);
      expect(dark[token]).not.toBe(root[token]);
    },
  );

  it('uses the real macOS deceleration curve, not a stock cubic-bezier', () => {
    expect(root['--ease-macos']).toBe('cubic-bezier(0.32, 0.72, 0, 1)');
  });

  it('exposes the vibrancy utility as a component-layer class', () => {
    // It is purged until PR-B's shell renders a sidebar, so assert on source.
    // Collapse whitespace first: the rgb() call is written across lines.
    const flat = css.replace(/\s+/g, ' ');
    expect(flat).toContain('.surface-translucent');
    expect(flat).toContain(
      'rgb( var(--surface-translucent) / var(--surface-translucent-alpha) )',
    );
    expect(flat).toContain('backdrop-filter: var(--backdrop-filter)');
  });
});

describe('WCAG 2.1 AA contrast', () => {
  const AA = 4.5;

  const pairs: [string, string, string][] = [
    ['body text', '--foreground', '--background'],
    ['card text', '--card-foreground', '--card'],
    ['primary button', '--primary-foreground', '--primary'],
    ['destructive button', '--destructive-foreground', '--destructive'],
    ['success button', '--success-foreground', '--success'],
    ['warning button', '--warning-foreground', '--warning'],
    ['secondary button', '--secondary-foreground', '--secondary'],
    ['muted text', '--muted-foreground', '--background'],
    ['link text', '--primary', '--background'],
  ];

  it.each(pairs)('light: %s clears 4.5:1', (_label, fg, bg) => {
    expect(contrastIn(root, fg, bg)).toBeGreaterThanOrEqual(AA);
  });

  it.each(pairs)('dark: %s clears 4.5:1', (_label, fg, bg) => {
    expect(contrastIn(dark, fg, bg)).toBeGreaterThanOrEqual(AA);
  });

  it('keeps the focus ring at 3:1 against the page', () => {
    // Non-text contrast: a focus indicator only has to reach 3:1.
    const fg = tokenToRgb(root['--ring']);
    const bg = tokenToRgb(root['--background']);
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(3);
  });
});
