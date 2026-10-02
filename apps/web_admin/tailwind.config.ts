import type { Config } from 'tailwindcss';
import animate from 'tailwindcss-animate';

export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: {
      center: true,
      padding: '2rem',
      screens: { '2xl': '1400px' },
    },
    extend: {
      /* Fase 1: Poppins es la tipografía de marca — referencia el
         primitivo --font-family-sans (styles/tokens.css) en vez de
         duplicar la lista de fallbacks acá. */
      fontFamily: {
        sans: 'var(--font-family-sans)',
      },
      /* Fase 1: escala tipográfica modular fluida (clamp), definida en
         styles/tokens.css. Se agrega SIN reemplazar la escala default de
         Tailwind (text-sm, text-3xl, etc. siguen intactas). */
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
        success: {
          DEFAULT: 'hsl(var(--success))',
          foreground: 'hsl(var(--success-foreground))',
        },
        warning: {
          DEFAULT: 'hsl(var(--warning))',
          foreground: 'hsl(var(--warning-foreground))',
        },
        /* Fase 1: tercer estado que faltaba (alineación con
           electron-sucursal). Mismo patrón que success/warning de arriba. */
        info: {
          DEFAULT: 'hsl(var(--info))',
          foreground: 'hsl(var(--info-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        /* Fase 1: faltaba en el tema de Tailwind — sin esto, `bg-popover`
           / `text-popover-foreground` (ya usados en HeatmapOcupacion,
           ChartLine y BranchSelector) no generan utilidad y el popover
           queda transparente. Pair con --popover/--popover-foreground en
           index.css. */
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 4px)',
        sm: 'calc(var(--radius) - 6px)',
        xl: 'calc(var(--radius) + 6px)',
        '2xl': 'calc(var(--radius) + 8px)',
        pill: 'var(--radius-pill)',
      },
      /* Many faint layers read as a lifted surface; one dark drop shadow
         reads as a smudge. */
      boxShadow: {
        'elevation-1': 'var(--shadow-elevation-1)',
        'elevation-2': 'var(--shadow-elevation-2)',
        'elevation-3': 'var(--shadow-elevation-3)',
        glass:
          'var(--shadow-elevation-2), inset 0 0 0 0.5px rgb(255 255 255 / 0.12)',
      },
      backdropBlur: {
        macos: '20px',
      },
      transitionTimingFunction: {
        macos: 'var(--ease-macos)',
      },
      transitionDuration: {
        fast: 'var(--duration-fast)',
        base: 'var(--duration-base)',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.96) translateY(8px)' },
          to: { opacity: '1', transform: 'scale(1) translateY(0)' },
        },
        'slide-in-from-right': {
          from: { opacity: '0', transform: 'translateX(100%)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in var(--duration-base) var(--ease-macos)',
        'scale-in': 'scale-in var(--duration-base) var(--ease-macos)',
        'slide-in-from-right':
          'slide-in-from-right var(--duration-base) var(--ease-macos)',
      },
    },
  },
  plugins: [animate],
} satisfies Config;
