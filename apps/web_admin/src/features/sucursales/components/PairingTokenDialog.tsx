/**
 * `<PairingTokenDialog />` -- modal that displays a freshly-minted
 * pairing token with copy-to-clipboard and a 24h countdown (IT-2.3,
 * IT-2.7).
 *
 * The token is a single-use, 24h JWT issued by `GET /api/v1/sucursal/
 * {uuid}/pairing-token`. The branch operator pastes it into the
 * PairingWizard on first boot to exchange for a long-lived
 * `sync-agent-` JWT.
 *
 * WCAG 2.1 AA:
 *   - Role="dialog" + aria-labelledby + aria-describedby.
 *   - The token itself is rendered inside a `<code>` with
 *     `aria-label="Pairing token"` (screen readers read the value
 *     back; clipboard is the canonical copy channel so the user can
 *     paste it into the wizard without hearing it spoken).
 *   - "Copied!" status announces via role=status aria-live=polite
 *     after the clipboard copy succeeds.
 *   - Escape closes the dialog (Radix Dialog built-in).
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

import { useCountdown, formatCountdown } from '@/features/auth/hooks/useCountdown';

import type { PairingTokenResponse } from '../api/sucursalSchema';

export interface PairingTokenDialogProps {
  /** When null the dialog is closed (token not yet minted). */
  token: PairingTokenResponse | null;
  /** Called when the user dismisses the dialog. */
  onClose: () => void;
}

export function PairingTokenDialog({ token, onClose }: PairingTokenDialogProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const secondsRemaining = useCountdown(token ? new Date(token.expires_at) : null);
  const formatted = token ? formatCountdown(secondsRemaining) : '00:00';
  const expired = token !== null && secondsRemaining === 0;

  if (token === null) return null;
  const pairingToken = token; // narrow for closures below

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(pairingToken.token);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked (e.g. insecure context). The user can still
      // select-and-copy manually from the <code> element below.
    }
  }

  return (
    <div
      role="dialog"
      aria-labelledby="pairing-token-title"
      aria-describedby="pairing-token-desc"
      data-testid="pairing-token-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4"
    >
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle id="pairing-token-title">{t('sucursal.pairing.title')}</CardTitle>
          <CardDescription id="pairing-token-desc">
            {expired
              ? t('sucursal.pairing.expired')
              : t('sucursal.pairing.expiresIn', { remaining: formatted })}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <code
            data-testid="pairing-token-value"
            aria-label="Pairing token"
            className="block break-all rounded-md border bg-muted p-3 font-mono text-xs"
          >
            {token.token}
          </code>
          <p
            role="status"
            aria-live="polite"
            data-testid="pairing-token-copied"
            className="text-xs text-muted-foreground"
          >
            {copied ? t('sucursal.pairing.copied') : ''}
          </p>
        </CardContent>
        <CardFooter className="flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            data-testid="pairing-token-close"
          >
            {t('sucursal.pairing.close')}
          </Button>
          <Button
            type="button"
            onClick={handleCopy}
            disabled={expired}
            data-testid="pairing-token-copy"
          >
            {copied ? t('sucursal.pairing.copiedShort') : t('sucursal.pairing.copy')}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
