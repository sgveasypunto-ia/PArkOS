/**
 * `<LogoMarca />` — easypunto logo for THEMED surfaces (cards, headers, sheets).
 *
 * Same mechanism as the dashboard header and the login: two images swapped with
 * the `.dark` class on `<html>` (`dark:hidden` / `hidden dark:block`), no React
 * state and no flash. White wordmark (`logo-horizontal-light.svg`, the only real
 * vector) on dark backgrounds; the dark wordmark on light ones.
 *
 * Do NOT use it on the white "paper" ticket previews: those use
 * `<MarcaTicketPantalla />` (black ink, theme independent).
 *
 * `alt` defaults to empty (decorative) because the screens that mount it already
 * carry a visible title; pass `alt="EasyPunto"` where the logo is the only brand cue.
 */
import type { JSX } from 'react';

import logoLight from '../assets/brand/logos/logo-horizontal-light.svg';
import logoDark from '../assets/brand/logos/logo-horizontal-dark--REQUIERE-VECTOR.png';

export interface LogoMarcaProps {
  /** Tailwind height/size classes; the width follows the aspect ratio. */
  className?: string;
  alt?: string;
}

export function LogoMarca({ className = 'h-8 w-auto', alt = '' }: LogoMarcaProps): JSX.Element {
  return (
    <>
      <img
        data-testid="logo-marca-claro"
        src={logoDark}
        alt={alt}
        className={`${className} shrink-0 dark:hidden`}
      />
      <img
        data-testid="logo-marca-oscuro"
        src={logoLight}
        alt={alt}
        className={`hidden ${className} shrink-0 dark:block`}
      />
    </>
  );
}
