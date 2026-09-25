import type { Config } from 'tailwindcss';
import animate from 'tailwindcss-animate';

export default {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/renderer/**/*.{ts,tsx}',
    './src/features/**/*.{ts,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: '2rem',
      screens: { '2xl': '1400px' },
    },
    extend: {
      /* Fase 2+3: Poppins es la tipografía de marca. Referencia el
         primitivo --font-family-sans (tokens.css) en vez de duplicar
         la lista de fallbacks acá. */
      fontFamily: {
        sans: 'var(--font-family-sans)',
      },
      /* Fase 2+3: escala tipográfica modular fluida (clamp), definida
         en tokens.css. Se agrega SIN reemplazar la escala default de
         Tailwind (text-sm, text-3xl, etc. siguen intactas — ya las
         usan componentes existentes como Dashboard.tsx). */
      fontSize: {
        label: ['var(--font-size-label)', { lineHeight: 'var(--line-height-normal)' }],
        small: ['var(--font-size-small)', { lineHeight: 'var(--line-height-normal)' }],
        body: ['var(--font-size-body)', { lineHeight: 'var(--line-height-normal)' }],
        h6: ['var(--font-size-h6)', { lineHeight: 'var(--line-height-snug)' }],
        h5: ['var(--font-size-h5)', { lineHeight: 'var(--line-height-snug)' }],
        h4: ['var(--font-size-h4)', { lineHeight: 'var(--line-height-snug)' }],
        h3: ['var(--font-size-h3)', { lineHeight: 'var(--line-height-tight)' }],
        h2: ['var(--font-size-h2)', { lineHeight: 'var(--line-height-tight)' }],
        h1: ['var(--font-size-h1)', { lineHeight: 'var(--line-height-tight)' }],
        display: ['var(--font-size-display)', { lineHeight: 'var(--line-height-tight)' }],
      },
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
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
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        /* REGRESSION fix (2026-09-22): ``popover`` was missing from the
           Tailwind theme.extend.colors map. Without it, Tailwind does
           not emit ``.bg-popover`` / ``.text-popover-foreground`` utility
           classes — shadcn's ``SelectContent`` (and ``Dialog``,
           ``DropdownMenu``, ``HoverCard``, ``Tooltip``, ``Popover``)
           silently fall back to ``transparent``, making every
           popover-based component invisible. Pair with the new
           ``--popover`` / ``--popover-foreground`` CSS variables in
           ``renderer/index.css``. */
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        /* Fase 2+3: tokens de estado nuevos. Referencian directo la
           capa --color-* de index.css (ya resuelta con hsl() y con
           variante .dark propia) — no --color-x del bloque shadcn de
           arriba, que usa tripletas sin envolver. */
        success: {
          DEFAULT: 'var(--color-success)',
          foreground: 'var(--color-success-foreground)',
        },
        warning: {
          DEFAULT: 'var(--color-warning)',
          foreground: 'var(--color-warning-foreground)',
        },
        info: {
          DEFAULT: 'var(--color-info)',
          foreground: 'var(--color-info-foreground)',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 4px)',     // era - 2 → ahora 10px
        sm: 'calc(var(--radius) - 6px)',     // era - 4 → ahora 8px
        /* Fase 2+3: extremos que faltaban en la escala. Decisión
           propia (no son valores de marca) — ver tokens.css. */
        xl: 'calc(var(--radius) + 6px)',     // ~20px, contenedores grandes
        pill: 'var(--radius-pill)',          // full-round puntual (chips/badges), no el default de los botones
      },
    },
  },
  plugins: [animate],
} satisfies Config;
