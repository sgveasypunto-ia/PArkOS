/**
 * `<ThemeToggle />` — theme preference switcher (Fase 2+3 UI).
 *
 * Wraps the existing theme mechanism (`@/lib/theme`) with a shadcn
 * `DropdownMenu`. The trigger icon reflects the current PREFERENCE
 * (not the resolved theme) — Sun/Moon/Monitor for light/dark/system.
 * `setThemePreference` persists to localStorage and applies the
 * resolved theme to `<html>` synchronously, but it does not trigger a
 * React re-render anywhere — this component keeps its own local state
 * so the trigger icon updates immediately on selection.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Monitor, Moon, Sun, type LucideIcon } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
  {
    value: 'light',
    icon: Sun,
    labelKey: 'common:theme.light',
    defaultLabel: 'Claro',
    testId: 'theme-toggle-light',
  },
  {
    value: 'dark',
    icon: Moon,
    labelKey: 'common:theme.dark',
    defaultLabel: 'Oscuro',
    testId: 'theme-toggle-dark',
  },
  {
    value: 'system',
    icon: Monitor,
    labelKey: 'common:theme.system',
    defaultLabel: 'Sistema',
    testId: 'theme-toggle-system',
  },
];

export function ThemeToggle(): JSX.Element {
  const { t } = useTranslation(['common']);
  const [preference, setPreference] = useState<ThemePreference>(
    getStoredThemePreference(),
  );

  const TriggerIcon = TRIGGER_ICON[preference];

  function handleSelect(next: ThemePreference): void {
    setThemePreference(next);
    setPreference(next);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t('common:theme.toggle', { defaultValue: 'Cambiar tema' })}
          data-testid="theme-toggle-trigger"
        >
          <TriggerIcon className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {THEME_OPTIONS.map((option) => {
          const Icon = option.icon;
          const active = preference === option.value;
          return (
            <DropdownMenuItem
              key={option.value}
              data-testid={option.testId}
              onSelect={() => handleSelect(option.value)}
              className="gap-2"
            >
              <Icon className="h-4 w-4" aria-hidden />
              <span>{t(option.labelKey, { defaultValue: option.defaultLabel })}</span>
              {active && <Check className="ml-auto h-4 w-4" aria-hidden />}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default ThemeToggle;
