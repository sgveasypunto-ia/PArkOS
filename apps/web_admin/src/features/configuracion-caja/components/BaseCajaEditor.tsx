/**
 * `<BaseCajaEditor />` — shows a base de caja and lets an admin change it inline.
 *
 * Used per branch row ("Administrar" table) and for the global default. The
 * value is what every operator of that branch receives when opening a shift;
 * it never changes a shift that is already open.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

import type { OrigenBase } from '../hooks/useBasesCajaSucursales';

const COP = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  maximumFractionDigits: 0,
});

export function formatBase(base: string | null): string {
  if (base === null) return '—';
  const n = Number(base);
  return Number.isFinite(n) ? COP.format(n) : '—';
}

export interface BaseCajaEditorProps {
  /** Decimal string as the backend sent it, or null when nothing is configured. */
  base: string | null;
  origen: OrigenBase;
  /** Persists the new base (COP, whole pesos). Rejects with a message on failure. */
  onGuardar: (base: number) => Promise<void>;
  testId: string;
}

export function BaseCajaEditor({
  base,
  origen,
  onGuardar,
  testId,
}: BaseCajaEditorProps): JSX.Element {
  const { t } = useTranslation();
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function abrir(): void {
    setTexto(base !== null ? String(Math.round(Number(base))) : '');
    setError(null);
    setEditando(true);
  }

  async function guardar(): Promise<void> {
    const valor = Number(texto);
    if (texto.trim() === '' || !Number.isInteger(valor) || valor < 0) {
      setError(
        t('baseCaja.invalida', 'Escribe un valor en pesos, entero y mayor o igual a 0.'),
      );
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      await onGuardar(valor);
      setEditando(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
    } finally {
      setGuardando(false);
    }
  }

  if (!editando) {
    return (
      <div className="flex items-center gap-2" data-testid={`${testId}-vista`}>
        <span className="font-mono tabular-nums" data-testid={`${testId}-valor`}>
          {formatBase(base)}
        </span>
        <span className="text-xs text-muted-foreground" data-testid={`${testId}-origen`}>
          {origen === 'propia' && t('baseCaja.origen.propia', 'propia')}
          {origen === 'global' && t('baseCaja.origen.global', 'por defecto')}
          {origen === 'sin_configurar' && t('baseCaja.origen.sin', 'sin configurar')}
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={abrir}
          data-testid={`${testId}-cambiar`}
        >
          {base === null ? t('baseCaja.configurar', 'Configurar') : t('baseCaja.cambiar', 'Cambiar')}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1" data-testid={`${testId}-edicion`}>
      <div className="flex items-center gap-2">
        <Input
          type="number"
          min={0}
          step={1}
          inputMode="numeric"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          aria-label={t('baseCaja.aria', 'Base de caja por turno (COP)')}
          className="h-8 w-36"
          data-testid={`${testId}-input`}
          autoFocus
        />
        <Button
          type="button"
          size="sm"
          disabled={guardando}
          onClick={() => void guardar()}
          data-testid={`${testId}-guardar`}
        >
          {guardando ? t('baseCaja.guardando', 'Guardando…') : t('baseCaja.guardar', 'Guardar')}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={guardando}
          onClick={() => setEditando(false)}
          data-testid={`${testId}-cancelar`}
        >
          {t('baseCaja.cancelar', 'Cancelar')}
        </Button>
      </div>
      {error !== null && (
        <p role="alert" className="text-xs text-destructive" data-testid={`${testId}-error`}>
          {error}
        </p>
      )}
    </div>
  );
}
