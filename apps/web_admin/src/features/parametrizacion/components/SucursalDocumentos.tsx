/**
 * `SucursalDocumentos` — tab "Documentos" de `SucursalDetalle.tsx`
 * (HU-F15.4): logo, póliza de responsabilidad civil (`certificado`),
 * plantilla de ticket y observaciones, los 4 `tipo` de `prod.documentos`
 * que esta pantalla gestiona.
 *
 * BR1: el logo se sube UNA vez por sucursal (`tipo='logo'`) y se imprime
 * en tickets + FE.
 * BR2: la póliza de responsabilidad civil no tiene columna propia en el
 * ER — se guarda como `tipo='certificado'`, con `formato` reflejando el
 * MIME real del archivo (PDF o imagen escaneada), nunca la extensión del
 * nombre (ver `lib/validation/documentos.ts::validarFormatoArchivo`).
 * BR3: `tipo='observaciones'` es texto plano codificado en base64 — NO
 * es un upload de archivo, es un textarea.
 *
 * Decisión de scope (distinta de `<Tarifas />`/`<Cupos />` en este mismo
 * shell): aquellas dos pantallas son PRE-EXISTENTES y leen el contexto
 * global del selector de sucursal (`useSucursal().selected`) sin aceptar
 * un scope explícito — por eso el shell les agrega un
 * `<ScopeMismatchNotice>` meramente informativo. Este componente es
 * NUEVO (construido para esta HU), así que puede — y debe — scopearse
 * de forma explícita al `uuidSucursal` de la ruta. Pero el backend NO
 * da una forma confiable de pedir "documentos de ESTA sucursal
 * puntual" por query param (ver docstring de `documentosApi.ts`): el
 * único filtro real de servidor es el header ambient
 * `X-Sucursal-Context`, que refleja la sucursal ACTIVA del topbar, no la
 * de esta URL. Si esas dos sucursales difieren, el listado que devuelve
 * el servidor queda acotado a la ACTIVA y el filtrado client-side jamás
 * podría "recuperar" filas de la sucursal de la ruta — mostraría un
 * falso "sin documentos" y, peor, un POST posterior podría crear una
 * SEGUNDA fila activa del mismo tipo (la tabla no tiene UK que lo
 * prevenga), violando BR1.
 *
 * Por eso, a diferencia de Tarifas/Capacidad, acá el mismatch NO es solo
 * una advertencia informativa: bloquea el fetch y la UI de gestión por
 * completo hasta que el admin seleccione esta sucursal como ACTIVA. El
 * caso `selected === null` (sin sucursal activa — esta ruta vive FUERA
 * de `<RequireSucursal>`, ver `App.tsx`) SÍ se permite: sin header, el
 * backend corre en modo "global" (todas las sucursales combinadas) y el
 * filtrado client-side por `uuid_sucursal` es entonces 100% correcto.
 */
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';
import { Loader2, TriangleAlert } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useSucursal } from '@/lib/sucursal-context';
import {
  ACCEPTED_MIME_BY_TIPO,
  DOCUMENTO_TIPOS,
  base64ToText,
  fileToBase64,
  formatBytes,
  textToBase64,
  validarFormatoArchivo,
  validarLongitudBase64,
  validarTamanoArchivo,
  validarTamanoTexto,
  type DocumentoTipo,
} from '@/lib/validation/documentos';

import { listDocumentosPorSucursal, upsertDocumento } from '../api/documentosApi';
import type { Documento } from '../api/documentosSchema';

export interface SucursalDocumentosProps {
  uuidSucursal: string;
}

const TIPO_META: Record<DocumentoTipo, { titleKey: string; title: string; descKey: string; desc: string }> = {
  logo: {
    titleKey: 'sucursal.documentos.logo.title',
    title: 'Logo',
    descKey: 'sucursal.documentos.logo.desc',
    desc: 'Se imprime en todos los tickets y en la factura electrónica. Se sube una vez por sucursal.',
  },
  certificado: {
    titleKey: 'sucursal.documentos.certificado.title',
    title: 'Póliza de responsabilidad civil',
    descKey: 'sucursal.documentos.certificado.desc',
    desc: 'PDF o imagen escaneada del certificado vigente.',
  },
  plantilla_ticket: {
    titleKey: 'sucursal.documentos.plantillaTicket.title',
    title: 'Plantilla de ticket',
    descKey: 'sucursal.documentos.plantillaTicket.desc',
    desc: 'Diseño o plantilla usada para imprimir los tickets de esta sucursal.',
  },
  observaciones: {
    titleKey: 'sucursal.documentos.observaciones.title',
    title: 'Observaciones',
    descKey: 'sucursal.documentos.observaciones.desc',
    desc: 'Notas internas en texto plano para esta sucursal (no se imprimen).',
  },
};

function dataUrl(formato: string | null, b64: string): string {
  return `data:${formato ?? 'application/octet-stream'};base64,${b64}`;
}

export function SucursalDocumentos({ uuidSucursal }: SucursalDocumentosProps): JSX.Element {
  const { t } = useTranslation();
  const { selected } = useSucursal();
  const scopeOk = selected === null || selected === uuidSucursal;

  const swrKey = scopeOk ? `sucursal-documentos-${uuidSucursal}` : null;
  const { data, error, isLoading, mutate } = useSWR<Documento[]>(
    swrKey,
    () => listDocumentosPorSucursal(uuidSucursal),
    { revalidateOnFocus: false },
  );

  if (!scopeOk) {
    return (
      <div
        role="alert"
        data-testid="sucursal-documentos-scope-blocked"
        className="flex items-start gap-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-3 text-sm text-amber-800"
      >
        <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>
          {t(
            'sucursal.documentos.scopeBloqueado',
            'Para gestionar los documentos de esta sucursal, primero seleccionala como sucursal ACTIVA en el selector superior. Esto evita confundir documentos entre dos sucursales distintas.',
          )}
        </span>
      </div>
    );
  }

  if (isLoading) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="sucursal-documentos-loading"
        className="text-sm text-muted-foreground"
      >
        {t('common.loading', 'Cargando…')}
      </p>
    );
  }

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="sucursal-documentos-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {error instanceof Error ? error.message : String(error)}
      </p>
    );
  }

  return (
    <div className="space-y-6" data-testid="sucursal-documentos-root">
      <p
        className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
        data-testid="sucursal-documentos-info"
      >
        {t(
          'sucursal.documentos.info',
          'Cada documento se guarda embebido en base64. Tamaño máximo por archivo: 1 MB.',
        )}
      </p>

      {DOCUMENTO_TIPOS.map((tipo) => (
        <DocumentoCard
          key={tipo}
          tipo={tipo}
          uuidSucursal={uuidSucursal}
          current={data?.find((d) => d.tipo === tipo)}
          onSaved={() => void mutate()}
        />
      ))}
    </div>
  );
}

interface DocumentoCardProps {
  tipo: DocumentoTipo;
  uuidSucursal: string;
  current: Documento | undefined;
  onSaved: () => void;
}

function DocumentoCard({ tipo, uuidSucursal, current, onSaved }: DocumentoCardProps): JSX.Element {
  const { t } = useTranslation();
  const meta = TIPO_META[tipo];
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [texto, setTexto] = useState<string>(() =>
    tipo === 'observaciones' && current?.documento_b64 ? base64ToText(current.documento_b64) : '',
  );
  const [localError, setLocalError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleFileSubmit(): Promise<void> {
    setLocalError(null);
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      setLocalError('Seleccioná un archivo primero.');
      return;
    }
    const sizeCheck = validarTamanoArchivo(file);
    if (!sizeCheck.ok) {
      setLocalError(sizeCheck.message ?? 'Archivo demasiado pesado.');
      return;
    }
    const formatCheck = validarFormatoArchivo(file, tipo);
    if (!formatCheck.ok) {
      setLocalError(formatCheck.message ?? 'Formato no permitido.');
      return;
    }
    setSubmitting(true);
    try {
      const b64 = await fileToBase64(file);
      const b64Check = validarLongitudBase64(b64);
      if (!b64Check.ok) {
        setLocalError(b64Check.message ?? 'Documento demasiado pesado.');
        return;
      }
      await upsertDocumento(current, {
        uuid_sucursal: uuidSucursal,
        tipo,
        formato: file.type,
        documento_b64: b64,
      });
      if (fileInputRef.current) fileInputRef.current.value = '';
      onSaved();
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : 'Error desconocido al guardar.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTextoSubmit(): Promise<void> {
    setLocalError(null);
    const sizeCheck = validarTamanoTexto(texto);
    if (!sizeCheck.ok) {
      setLocalError(sizeCheck.message ?? 'Texto demasiado pesado.');
      return;
    }
    setSubmitting(true);
    try {
      const b64 = textToBase64(texto);
      const b64Check = validarLongitudBase64(b64);
      if (!b64Check.ok) {
        setLocalError(b64Check.message ?? 'Documento demasiado pesado.');
        return;
      }
      await upsertDocumento(current, {
        uuid_sucursal: uuidSucursal,
        tipo: 'observaciones',
        formato: 'text/plain',
        documento_b64: b64,
      });
      onSaved();
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : 'Error desconocido al guardar.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section
      className="space-y-3 rounded-lg border bg-card p-4"
      data-testid={`sucursal-documentos-card-${tipo}`}
    >
      <header>
        <h3 className="text-sm font-semibold">{t(meta.titleKey, meta.title)}</h3>
        <p className="text-xs text-muted-foreground">{t(meta.descKey, meta.desc)}</p>
      </header>

      {tipo === 'observaciones' ? (
        <div className="space-y-2">
          <textarea
            data-testid="sucursal-documentos-textarea-observaciones"
            rows={4}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            placeholder={t(
              'sucursal.documentos.observaciones.placeholder',
              'Notas internas para esta sucursal…',
            )}
          />
          <Button
            type="button"
            size="sm"
            disabled={submitting}
            onClick={() => void handleTextoSubmit()}
            data-testid="sucursal-documentos-submit-observaciones"
          >
            {submitting ? (
              <>
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                {t('sucursal.documentos.guardando', 'Guardando…')}
              </>
            ) : (
              t('sucursal.documentos.guardar', 'Guardar')
            )}
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          {current?.documento_b64 ? (
            <DocumentoPreview tipo={tipo} documento={current} />
          ) : (
            <p
              className="text-xs text-muted-foreground"
              data-testid={`sucursal-documentos-empty-${tipo}`}
            >
              {t('sucursal.documentos.sinCargar', 'Sin documento cargado todavía.')}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_MIME_BY_TIPO[tipo]?.join(',')}
              data-testid={`sucursal-documentos-file-${tipo}`}
              className="text-xs"
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={submitting}
              onClick={() => void handleFileSubmit()}
              data-testid={`sucursal-documentos-submit-${tipo}`}
            >
              {submitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  {t('sucursal.documentos.subiendo', 'Subiendo…')}
                </>
              ) : (
                t('sucursal.documentos.subir', 'Subir')
              )}
            </Button>
          </div>
        </div>
      )}

      {localError && (
        <p
          role="alert"
          data-testid={`sucursal-documentos-local-error-${tipo}`}
          className="text-xs font-medium text-destructive"
        >
          {localError}
        </p>
      )}
    </section>
  );
}

function DocumentoPreview({
  tipo,
  documento,
}: {
  tipo: DocumentoTipo;
  documento: Documento;
}): JSX.Element {
  const { t } = useTranslation();
  const b64 = documento.documento_b64 ?? '';
  const formato = documento.formato;
  const href = dataUrl(formato, b64);
  // ~0.75 porque base64 infla el tamaño original en 4/3.
  const approxBytes = Math.floor((b64.length * 3) / 4);

  if (formato?.startsWith('image/')) {
    return (
      <div data-testid={`sucursal-documentos-preview-${tipo}`} className="space-y-1">
        <img
          src={href}
          alt={t('sucursal.documentos.previewAlt', 'Vista previa del documento cargado')}
          className="max-h-28 rounded border object-contain"
        />
        <p className="text-xs text-muted-foreground">
          {formato} · {formatBytes(approxBytes)}
        </p>
      </div>
    );
  }

  return (
    <div data-testid={`sucursal-documentos-preview-${tipo}`} className="space-y-1">
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        download={`${tipo}`}
        className="text-sm font-medium text-primary underline underline-offset-2"
      >
        {t('sucursal.documentos.verDocumento', 'Ver documento cargado')}
      </a>
      <p className="text-xs text-muted-foreground">
        {formato ?? '—'} · {formatBytes(approxBytes)}
      </p>
    </div>
  );
}
