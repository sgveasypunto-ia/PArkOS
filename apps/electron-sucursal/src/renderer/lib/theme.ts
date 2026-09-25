/**
 * Theme mechanism — Fase 2+3 (design tokens + modo claro/oscuro).
 *
 * Fuente de verdad única: `localStorage[THEME_STORAGE_KEY]`. Valores
 * posibles: 'light' | 'dark' | 'system'. 'system' delega a
 * `prefers-color-scheme` y se mantiene sincronizado en vivo mientras la
 * app está abierta (ver `initTheme`).
 *
 * El anti-flash real vive en `index.html` (script inline, sin módulos,
 * para poder correr ANTES de que Vite/React pinten nada). Ese script
 * duplica a propósito la lógica mínima de acá (misma clave de
 * localStorage, mismo criterio de resolución) porque no puede depender
 * de un bundle JS. Si cambiás `THEME_STORAGE_KEY` o el criterio de
 * resolución, actualizá también el script inline de `index.html`.
 *
 * Esta fase NO agrega un botón de toggle visible en la UI — el
 * mecanismo queda funcional y testeable para que la fase de
 * componentes lo consuma (ej.: `setThemePreference('dark')`).
 */

export type ThemePreference = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

/** Debe coincidir EXACTO con la clave usada en el script inline de index.html. */
export const THEME_STORAGE_KEY = 'parkos.sucursal.theme';

function isThemePreference(value: string | null): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system';
}

/** Lee la preferencia guardada por el usuario. Default: 'system'. */
export function getStoredThemePreference(): ThemePreference {
  if (typeof window === 'undefined') return 'system';
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(raw) ? raw : 'system';
  } catch {
    // localStorage puede no estar disponible (modo privado, cuota, SSR).
    return 'system';
  }
}

/** Lee la preferencia del sistema operativo vía prefers-color-scheme. */
export function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** Resuelve una preferencia ('system' incluido) a un tema concreto. */
export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  return preference === 'system' ? getSystemTheme() : preference;
}

/** Aplica un tema YA resuelto al DOM: clase, data-attribute y color-scheme. */
export function applyResolvedTheme(resolved: ResolvedTheme): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.classList.toggle('dark', resolved === 'dark');
  root.classList.toggle('light', resolved === 'light');
  root.setAttribute('data-theme', resolved);
  root.style.colorScheme = resolved;
}

/** Persiste la preferencia del usuario y aplica el tema resultante de inmediato. */
export function setThemePreference(preference: ThemePreference): void {
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, preference);
    } catch {
      // La preferencia igual se aplica para la sesión actual en memoria.
    }
  }
  applyResolvedTheme(resolveTheme(preference));
}

/**
 * Inicializa el mecanismo: re-aplica el tema resuelto (idempotente con
 * el script anti-flash de index.html) y se suscribe a cambios en vivo
 * de `prefers-color-scheme` mientras la preferencia sea 'system'.
 *
 * Devuelve una función de cleanup (remueve el listener); no es
 * obligatorio llamarla ya que vive durante todo el ciclo de vida de la
 * app, pero queda expuesta para tests / hot-reload.
 */
export function initTheme(): () => void {
  applyResolvedTheme(resolveTheme(getStoredThemePreference()));

  if (typeof window === 'undefined' || !window.matchMedia) return () => {};

  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const handleSystemChange = (): void => {
    if (getStoredThemePreference() === 'system') {
      applyResolvedTheme(getSystemTheme());
    }
  };
  media.addEventListener('change', handleSystemChange);
  return () => media.removeEventListener('change', handleSystemChange);
}
