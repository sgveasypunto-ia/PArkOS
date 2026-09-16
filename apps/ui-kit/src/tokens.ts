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
