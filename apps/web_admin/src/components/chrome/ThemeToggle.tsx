/**
 * `<ThemeToggle />` — theme preference switcher (Fase 1, alineación con
 * electron-sucursal). Adaptado al primitivo `DropdownMenu` propio de
 * web_admin (hand-rolled, no Radix — ver `components/ui/dropdown-menu.tsx`):
 * usa `onClick` (no `onSelect`) y no depende de `asChild`, que ese
 * primitivo ignora.
 *
 * El trigger refleja la PREFERENCIA actual (no el tema resuelto) —
 * Sun/Moon/Monitor para light/dark/system. `setThemePreference` persiste
 * en localStorage y aplica el tema resuelto a `<html>` de forma síncrona,
 * pero no dispara un re-render de React en ningún lado — este componente
 * mantiene su propio estado local para que el ícono del trigger se
 * actualice de inmediato al seleccionar.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Monitor, Moon, Sun, type LucideIcon } from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  getStoredThemePreference,
  setThemePreference,
  type ThemePreference,
} from '@/lib/theme';

const TRIGGER_ICON: Record<ThemePreference, LucideIcon> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
};

interface ThemeOption {
  value: ThemePreference;
  icon: LucideIcon;
  labelKey: string;
  defaultLabel: string;
  testId: string;
}

const THEME_OPTIONS: ThemeOption[] = [
  { value: 'light', icon: Sun, labelKey: 'theme.light', defaultLabel: 'Claro', testId: 'theme-toggle-light' },
  { value: 'dark', icon: Moon, labelKey: 'theme.dark', defaultLabel: 'Oscuro', testId: 'theme-toggle-dark' },
  { value: 'system', icon: Monitor, labelKey: 'theme.system', defaultLabel: 'Sistema', testId: 'theme-toggle-system' },
];

export interface ThemeMenuItemsProps {
  /** Notifica al padre (ej.: `<ThemeToggle />`) para que pueda actualizar
   * su propio ícono de trigger. Opcional: el menú "más acciones" de
   * `TopNav` no necesita sincronizar nada más, así que lo omite. */
  onSelect?: (next: ThemePreference) => void;
}

/**
 * Items reutilizables del selector de tema. Se usan tanto dentro del
 * `<ThemeToggle />` (icon button, visible en >= sm) como dentro del menú
 * "más acciones" de `TopNav` para pantallas angostas (< sm). Cada
 * instancia que monta este componente arranca su checkmark desde
 * `getStoredThemePreference()` — como `DropdownMenuContent` desmonta su
 * contenido al cerrarse, siempre refleja el valor más reciente la
 * próxima vez que se abre.
 */
export function ThemeMenuItems({ onSelect }: ThemeMenuItemsProps): JSX.Element {
  const { t } = useTranslation();
  const [preference, setPreference] = useState<ThemePreference>(getStoredThemePreference());

  function handleSelect(next: ThemePreference): void {
    setThemePreference(next);
    setPreference(next);
    onSelect?.(next);
  }

  return (
    <>
      {THEME_OPTIONS.map((option) => {
        const Icon = option.icon;
        const active = preference === option.value;
        return (
          <DropdownMenuItem
            key={option.value}
            data-testid={option.testId}
            onClick={() => handleSelect(option.value)}
            className="gap-2"
          >
            <Icon className="size-4" aria-hidden="true" />
            <span>{t(option.labelKey, option.defaultLabel)}</span>
            {active && <Check className="ml-auto size-4" aria-hidden="true" />}
          </DropdownMenuItem>
        );
      })}
    </>
  );
}

export function ThemeToggle(): JSX.Element {
  const { t } = useTranslation();
  const [preference, setPreference] = useState<ThemePreference>(getStoredThemePreference());
  const TriggerIcon = TRIGGER_ICON[preference];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(buttonVariants({ variant: 'ghost', size: 'icon' }), 'shrink-0')}
        aria-label={t('topnav.themeToggle', 'Cambiar tema')}
        data-testid="theme-toggle-trigger"
      >
        <TriggerIcon className="size-4" aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <ThemeMenuItems onSelect={setPreference} />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default ThemeToggle;
