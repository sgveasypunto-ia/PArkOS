/**
 * Design tokens — typed mirror of the CSS variables declared in
 * `apps/web_admin/src/index.css` (and replicated in
 * `apps/electron-sucursal/src/index.css`).
 *
 * Tokens are kept as a single typed object so consumers (Fase 3+) can
 * reference them via `tokens.colors.primary` instead of duplicating
 * HSL strings. Values themselves live in CSS — this module is a
 * typing-only surface.
 */

export interface DesignTokens {
  colors: {
    background: string;
    foreground: string;
    card: { DEFAULT: string; foreground: string };
    primary: { DEFAULT: string; foreground: string };
    secondary: { DEFAULT: string; foreground: string };
    muted: { DEFAULT: string; foreground: string };
    accent: { DEFAULT: string; foreground: string };
    destructive: { DEFAULT: string; foreground: string };
    border: string;
    input: string;
    ring: string;
  };
  radius: {
    lg: string;
    md: string;
    sm: string;
  };
}

export const tokens: DesignTokens = {
  colors: {
    background: 'hsl(var(--background))',
    foreground: 'hsl(var(--foreground))',
    card: {
      DEFAULT: 'hsl(var(--card))',
      foreground: 'hsl(var(--card-foreground))',
    },
    primary: {
      DEFAULT: 'hsl(var(--primary))',
      foreground: 'hsl(var(--primary-foreground))',
    },
    secondary: {
      DEFAULT: 'hsl(var(--secondary))',
      foreground: 'hsl(var(--secondary-foreground))',
    },
    muted: {
      DEFAULT: 'hsl(var(--muted))',
      foreground: 'hsl(var(--muted-foreground))',
    },
    accent: {
      DEFAULT: 'hsl(var(--accent))',
      foreground: 'hsl(var(--accent-foreground))',
    },
    destructive: {
      DEFAULT: 'hsl(var(--destructive))',
      foreground: 'hsl(var(--destructive-foreground))',
    },
    border: 'hsl(var(--border))',
    input: 'hsl(var(--input))',
    ring: 'hsl(var(--ring))',
  },
  radius: {
    lg: 'var(--radius)',
    md: 'calc(var(--radius) - 2px)',
    sm: 'calc(var(--radius) - 4px)',
  },
};

/**
 * Canonical real values — electron-sucursal (fix/web-admin-design-tokens,
 * 2026-10). `DesignTokens`/`tokens` above stay a CSS-var-reference typing
 * surface (unchanged, still what each app's `tailwind.config.ts` wraps as
 * `hsl(var(--x))`). These constants are the actual numbers behind those
 * variables in the app that originated the design system — documented
 * here as the single source of truth for a FUTURE consumer, since neither
 * `web_admin` nor `electron-sucursal` import this module at runtime yet
 * (both still read their own CSS variables directly; wiring either app to
 * import from here is a separate, later task — not done as part of this
 * one to keep this change additive-only).
 *
 * Color primitives use the same "H S% L%" triplet format (no `hsl()`
 * wrapper) as the CSS files, so a future consumer can wrap them the same
 * way: `` `hsl(${BRAND_ORANGE[500]})` ``.
 */
export const BRAND_ORANGE = {
  50: '24 100% 96%',
  100: '24 100% 91%',
  200: '25 100% 83%',
  300: '29 100% 75%', // #FFBC7D — marca (color de transición/loading)
  400: '21 90% 64%',
  500: '18 81% 53%', // #E85F24 — marca (primario/acento)
  600: '17 78% 45%',
  700: '16 75% 37%',
  800: '15 72% 29%',
  900: '14 70% 22%',
} as const;

export const BRAND_GRAY = {
  0: '0 0% 100%',
  50: '240 13% 97%', // #F6F6F8 — marca
  100: '220 14% 93%',
  200: '220 13% 91%',
  300: '220 9% 80%',
  400: '0 0% 41%', // #696969 — marca
  500: '0 0% 39%', // #636363 — marca
  600: '0 0% 33%',
  700: '0 0% 24%',
  800: '270 2% 20%', // #323133 — marca
  900: '0 0% 13%', // #222222 — marca
  darkSecondary: '0 0% 65%', // texto secundario legible en modo oscuro
} as const;

export const CANONICAL_RADIUS = {
  base: '0.875rem',
  xs: '0.25rem',
  pill: '9999px',
} as const;

export const CANONICAL_FONT_FAMILY_SANS =
  "'Poppins', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif";

/**
 * Semantic light/dark role mapping, as HSL triplets (same format as
 * `BRAND_ORANGE`/`BRAND_GRAY` above — wrap with `hsl()` to use as a CSS
 * color). Mirrors the `:root` / `.dark` blocks in both apps' `index.css`.
 */
export const CANONICAL_SEMANTIC_TOKENS = {
  light: {
    background: BRAND_GRAY[50],
    foreground: BRAND_GRAY[800],
    card: BRAND_GRAY[0],
    cardForeground: BRAND_GRAY[800],
    popover: BRAND_GRAY[0],
    popoverForeground: BRAND_GRAY[800],
    primary: BRAND_ORANGE[500],
    primaryForeground: BRAND_GRAY[900],
    secondary: BRAND_GRAY[100],
    secondaryForeground: BRAND_GRAY[800],
    muted: BRAND_GRAY[100],
    mutedForeground: BRAND_GRAY[500],
    accent: BRAND_GRAY[100],
    accentForeground: BRAND_GRAY[800],
    border: BRAND_GRAY[200],
    input: BRAND_GRAY[200],
    ring: BRAND_ORANGE[500],
  },
  dark: {
    background: BRAND_GRAY[900],
    foreground: BRAND_GRAY[50],
    card: BRAND_GRAY[800],
    cardForeground: BRAND_GRAY[50],
    popover: BRAND_GRAY[700],
    popoverForeground: BRAND_GRAY[50],
    primary: BRAND_ORANGE[400],
    primaryForeground: BRAND_GRAY[900],
    secondary: BRAND_GRAY[700],
    secondaryForeground: BRAND_GRAY[50],
    muted: BRAND_GRAY[700],
    mutedForeground: BRAND_GRAY.darkSecondary,
    accent: BRAND_GRAY[700],
    accentForeground: BRAND_GRAY[50],
    border: BRAND_GRAY[700],
    input: BRAND_GRAY[700],
    ring: BRAND_ORANGE[400],
  },
} as const;
