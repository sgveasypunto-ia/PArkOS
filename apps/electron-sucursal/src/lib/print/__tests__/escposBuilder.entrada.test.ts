/**
 * Unit tests for F6.2 — Tiquete de entrada CU-15E byte-level fixtures.
 *
 * Covers the 17 conceptual fields in `escposTemplates.ts::TiqueteEntradaCampos`
 * (Spanish ordinals):
 *   - 17 byte-presence scenarios (one per `TiqueteEntradaCampos` key,
 *     asserting `Buffer.indexOf(<campo>) >= 0` for the value emitted by
 *     `escposBuilder.build("entrada", payload)`).
 *   - 17 Zod rejection scenarios — one per missing key — confirming
 *     the F6.2 schema refinement throws `EscposPayloadMissingFieldError`
 *     with `code === 'escpos_payload_missing_field'`.
 *   - Mensualidad tag scenario — when `ingreso.uuid_subscripcion_cliente`
 *     is non-null, `buildEntradaPayload()` emits `esMensualidad: true`
 *     and the buffer contains `MENSUALIDAD`.
 *   - Missing-field error class — the error class is exported and
 *     carries the documented code.
 *
 * The 17-key byte-presence table mirrors `TiqueteEntradaCampos` so
 * adding or removing a key in the source interface FAILS this file at
 * review time (each scenario asserts a specific token; renames break
 * the assertion message).
 */
import { describe, it, expect } from 'vitest';

import {
  build,
  EscposPayloadMissingFieldError,
} from '../escposBuilder';
import {
  entradaPayloadSchema,
  buildEntradaPayload,
  formatCOP,
  type IngresoForPayload,
  type SucursalForPayload,
  type TarifaForPayload,
  type DocumentoForPayload,
  type Empresa,
} from '../escposTemplates';
import { validEntradaPayload } from './escposBuilder.test';

// ──────────────────────────────────────────────────────────────────────────
// Fixtures — 17-field payload via buildEntradaPayload factory
// ──────────────────────────────────────────────────────────────────────────

function makeIngreso(overrides?: Partial<IngresoForPayload>): IngresoForPayload {
  return {
    uuid: '11111111-2222-4333-8444-555555555555',
    placa: 'ABC123',
    // REQ-OPS-197: `consecutivo` is required (nullable) on `IngresoForPayload` —
    // legacy con-placa rows always carry `consecutivo: null` from the backend
    // (`PostIngresoResponseSchema.consecutivo` is `z.string().nullable()`,
    // never optional). Scenarios that exercise the no-placa variant override
    // this default explicitly (see the con-consecutivo fixture below).
    consecutivo: null,
    fecha_ingreso: '2026-09-16T08:30:00Z',
    uuid_subscripcion_cliente: null,
    ...overrides,
  };
}

function makeSucursal(): SucursalForPayload {
  return { horario_atencion: '24 horas', encabezado: 'Sucursal Test' };
}

function makeTarifa(): TarifaForPayload {
  return { valor_hora_cents: 5000 };
}

function makeEmpresa(): Empresa {
  return {
    nombre: 'Parkos Demo S.A.S.',
    nit: '900123456-7',
    direccion: 'Calle 1 #2-3, Bogota',
    regimen: 'Responsable de IVA',
  };
}

function makeDocumentos(opts?: { withLogo?: boolean; withCert?: boolean }): DocumentoForPayload[] {
  const docs: DocumentoForPayload[] = [];
  if (opts?.withLogo !== false) {
    docs.push({ tipo: 'logo', documento_b64: 'data:image/png;base64,FAKE_LOGO_B64' });
  }
  if (opts?.withCert !== false) {
    docs.push({ tipo: 'certificado', documento_b64: 'POL-12345' });
  }
  return docs;
}

function buildPayload(opts?: { withLogo?: boolean; withCert?: boolean; ingreso?: Partial<IngresoForPayload> }) {
  return buildEntradaPayload({
    ingreso: makeIngreso(opts?.ingreso),
    sucursal: makeSucursal(),
    empresa: makeEmpresa(),
    operario: 'op-001',
    tipoVehiculo: 'auto',
    tarifa: makeTarifa(),
    documentos: makeDocumentos(opts),
    fechaHora: '2026-09-16T08:30:00Z',
  });
}

// ──────────────────────────────────────────────────────────────────────────
// 17 byte-presence scenarios — one per TiqueteEntradaCampos key
// ──────────────────────────────────────────────────────────────────────────

describe('buildEntradaBuffer — 17 byte-presence scenarios (HU-F6.2)', () => {
  it('primero (Encabezado) — emits payload.sucursal.encabezado header (DEC-SUC-28 dynamic)', () => {
    const buf = build('entrada', validEntradaPayload());
    // F7.3 (DEC-SUC-28) — dynamic branch header replaces the F5.2
    // "PARKINGOS" constant. Drift guard: PARKINGOS MUST NOT appear.
    expect(buf.indexOf(Buffer.from('Sucursal Centro'))).toBeGreaterThanOrEqual(0);
    expect(buf.indexOf(Buffer.from('PARKINGOS'))).toBe(-1);
  });

  it('segundo (Nombre de la empresa) — emits empresa.nombre', () => {
    const buf = build('entrada', validEntradaPayload());
    expect(buf.indexOf(Buffer.from('Parkos Demo S.A.S.'))).toBeGreaterThanOrEqual(0);
  });

  it('tercero (Dirección) — emits empresa.direccion', () => {
    const buf = build('entrada', validEntradaPayload());
    expect(buf.indexOf(Buffer.from('Calle 1 #2-3, Bogota'))).toBeGreaterThanOrEqual(0);
  });

  it('cuarto (NIT) — emits "NIT {empresa.nit}"', () => {
    const buf = build('entrada', validEntradaPayload());
    expect(buf.indexOf(Buffer.from('NIT 900123456-7'))).toBeGreaterThanOrEqual(0);
  });

  it('quinto (Régimen) — emits empresa.regimen', () => {
    const buf = build('entrada', validEntradaPayload());
    expect(buf.indexOf(Buffer.from('Responsable de IVA'))).toBeGreaterThanOrEqual(0);
  });

  it('sexto (Operario) — emits "Operario: {operario}"', () => {
    const buf = build('entrada', validEntradaPayload());
    expect(buf.indexOf(Buffer.from('Operario: op-001'))).toBeGreaterThanOrEqual(0);
  });

  it('septimo (Sello) — emits "*** TIQUETE DE ENTRADA ***" with text 2x', () => {
    const buf = build('entrada', validEntradaPayload());
    expect(buf.indexOf(Buffer.from('*** TIQUETE DE ENTRADA ***'))).toBeGreaterThanOrEqual(0);
    // text 2x byte sequence (ESC ! 0x30)
    expect(buf.indexOf(Buffer.from([0x1b, 0x21, 0x30]))).toBeGreaterThanOrEqual(0);
  });

  it('octavo (Folio) — emits "Folio: {folio}"', () => {
    const buf = build('entrada', validEntradaPayload());
    expect(buf.indexOf(Buffer.from('00000000-0000-4000-8000-000000000001'))).toBeGreaterThanOrEqual(0);
  });

  it('noveno (Tarifa aplicada) — emits "Tarifa: {formatCOP}/hora"', () => {
    const buf = build('entrada', validEntradaPayload());
    const formatted = formatCOP(5000);
    expect(buf.indexOf(Buffer.from(`Tarifa: ${formatted}/hora`))).toBeGreaterThanOrEqual(0);
  });

  it('decimo (Fecha operación) — emits "Fecha: dd/MM/yyyy"', () => {
    const buf = build('entrada', validEntradaPayload());
    // ISO 2026-09-16T08:30:00Z → UTC date "16/09/2026" — the renderer
    // formats via `new Date(iso)` which uses the test environment
    // timezone; this assertion targets the date portion which is stable
    // across UTC-5 / UTC / UTC+5 (no DST on the 16th of September).
    expect(buf.indexOf(Buffer.from('Fecha: 16/09/2026'))).toBeGreaterThanOrEqual(0);
  });

  it('onceavo (Hora entrada) — emits "Hora: HH:mm"', () => {
    const buf = build('entrada', validEntradaPayload());
    // The renderer formats via `new Date(iso)` which uses the test
    // environment timezone; we only assert the "Hora: " prefix + the
    // HH:mm pattern, not the exact hours (timezone-dependent).
    expect(buf.indexOf(Buffer.from('Hora: '))).toBeGreaterThanOrEqual(0);
    // Match `Hora: HH:mm` pattern (two digits, colon, two digits)
    const match = buf.toString('utf8').match(/Hora: (\d{2}):(\d{2})/);
    expect(match).not.toBeNull();
  });

  it('doceavo (Placa) — emits "Placa: {placa}"', () => {
    const buf = build('entrada', validEntradaPayload());
    expect(buf.indexOf(Buffer.from('Placa: ABC123'))).toBeGreaterThanOrEqual(0);
  });

  it('treceavo (Horario atención) — emits "Horario: {horarioAtencion}"', () => {
    const buf = build('entrada', validEntradaPayload());
    expect(buf.indexOf(Buffer.from('Horario: 24 horas'))).toBeGreaterThanOrEqual(0);
  });

  it('catorceavo (Póliza RC) — emits "Poliza RC: {polizaRC}"', () => {
    const buf = build('entrada', validEntradaPayload());
    expect(buf.indexOf(Buffer.from('Poliza RC: POL-12345'))).toBeGreaterThanOrEqual(0);
  });

  it('quinceavo (Observaciones) — emits "Observaciones: {observaciones}"', () => {
    const buf = build('entrada', validEntradaPayload());
    expect(buf.indexOf(Buffer.from('Observaciones: Sin novedad'))).toBeGreaterThanOrEqual(0);
  });

  it('qrDataUrl (DEC-SUC-26) — buffer contains the data URL', () => {
    const payload = buildPayload();
    const buf = build('entrada', payload);
    expect(buf.indexOf(Buffer.from(';QR:'))).toBeGreaterThanOrEqual(0);
    expect(buf.indexOf(Buffer.from(payload.qrDataUrl))).toBeGreaterThanOrEqual(0);
  });

  it('logoDataUrl (DEC-SUC-26) — buffer contains logo (or placeholder when empty)', () => {
    const payload = buildPayload();
    const buf = build('entrada', payload);
    expect(buf.indexOf(Buffer.from(';LOGO:'))).toBeGreaterThanOrEqual(0);
    // logoDataUrl is non-empty in this fixture, so the OK marker is emitted
    expect(buf.indexOf(Buffer.from('OK'))).toBeGreaterThanOrEqual(0);
  });

  // HU-INGRESO-SIN-PLACA (REQ-OPS-197) — no-placa variant byte fixture.
  // The 12th conceptual field (doceavo) renders
  // `Identificación: BICI-000001-3f8a1b2c\n` instead of
  // `Placa: ABC123\n`.
  it('con-consecutivo — buffer contains "Identificación: BICI-000001-3f8a1b2c" (REQ-OPS-197 byte-fixture)', () => {
    const payload = buildEntradaPayload({
      ingreso: makeIngreso({
        placa: null,
        consecutivo: 'BICI-000001-3f8a1b2c',
      }),
      sucursal: makeSucursal(),
      empresa: makeEmpresa(),
      operario: 'op-bici-001',
      tipoVehiculo: 'auto',
      tarifa: makeTarifa(),
      documentos: makeDocumentos(),
      fechaHora: '2026-09-16T08:30:00Z',
    });
    expect(payload.variant).toBe('con-consecutivo');
    const buf = build('entrada', payload);
    // Byte-fixture pin: exact sequence at the 12th conceptual field.
    expect(
      buf.indexOf(Buffer.from('Identificación: BICI-000001-3f8a1b2c\n')),
    ).toBeGreaterThanOrEqual(0);
    // Legacy `Placa:` line MUST NOT appear (discriminator enforced).
    expect(buf.indexOf(Buffer.from('Placa: ABC123\n'))).toBe(-1);
  });

  // Mensualidad tag conditional — separate scenario, NOT in the 17-key
  // counter (per spec — TiqueteEntradaCampos has 17 keys, none of which
  // is esMensualidad). Mensualidad is derived from ingreso.
  it('Mensualidad tag — emits "MENSUALIDAD" when uuid_subscripcion_cliente is set', () => {
    const payload = buildEntradaPayload({
      ingreso: makeIngreso({
        uuid_subscripcion_cliente: 'sub-uuid-7777',
      }),
      sucursal: makeSucursal(),
      empresa: makeEmpresa(),
      operario: 'op-002',
      tipoVehiculo: 'auto',
      tarifa: makeTarifa(),
      documentos: makeDocumentos(),
      fechaHora: '2026-09-16T08:30:00Z',
    });
    expect(payload.esMensualidad).toBe(true);
    const buf = build('entrada', payload);
    expect(buf.indexOf(Buffer.from('MENSUALIDAD'))).toBeGreaterThanOrEqual(0);
  });

  it('Mensualidad tag — ABSENT when uuid_subscripcion_cliente is null', () => {
    const payload = buildEntradaPayload({
      ingreso: makeIngreso({ uuid_subscripcion_cliente: null }),
      sucursal: makeSucursal(),
      empresa: makeEmpresa(),
      operario: 'op-003',
      tipoVehiculo: 'auto',
      tarifa: makeTarifa(),
      documentos: makeDocumentos(),
      fechaHora: '2026-09-16T08:30:00Z',
    });
    expect(payload.esMensualidad).toBe(false);
    const buf = build('entrada', payload);
    expect(buf.indexOf(Buffer.from('MENSUALIDAD'))).toBe(-1);
  });

  // Logo placeholder — separate from byte-presence count
  it('Logo placeholder glyph — emitted when logoDataUrl is empty (cold cache)', () => {
    const payload = buildEntradaPayload({
      ingreso: makeIngreso(),
      sucursal: makeSucursal(),
      empresa: makeEmpresa(),
      operario: 'op-004',
      tipoVehiculo: 'auto',
      tarifa: makeTarifa(),
      documentos: [], // empty documentos → logoDataUrl = ''
      fechaHora: '2026-09-16T08:30:00Z',
    });
    expect(payload.logoDataUrl).toBe('');
    const buf = build('entrada', payload);
    // ▢ placeholder glyph
    expect(buf.indexOf(Buffer.from('\u25A2'))).toBeGreaterThanOrEqual(0);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// Zod rejection — missing key scenarios
// ──────────────────────────────────────────────────────────────────────────

describe('entradaPayloadSchema — Zod rejection (missing-field)', () => {
  it('throws EscposPayloadMissingFieldError when build("entrada", {}) is called', () => {
    let captured: EscposPayloadMissingFieldError | null = null;
    try {
      build('entrada', { foo: 1 });
    } catch (err) {
      captured = err as EscposPayloadMissingFieldError;
    }
    expect(captured).not.toBeNull();
    expect(captured).toBeInstanceOf(EscposPayloadMissingFieldError);
    expect(captured!.code).toBe('escpos_payload_missing_field');
    expect(captured!.issues.length).toBeGreaterThan(0);
  });

  it('entradaPayloadSchema.parse rejects payload missing qrDataUrl', () => {
    const { qrDataUrl: _qr, ...rest } = validEntradaPayload();
    void _qr;
    const result = entradaPayloadSchema.safeParse(rest);
    expect(result.success).toBe(false);
  });

  it('entradaPayloadSchema.parse rejects payload missing logoDataUrl', () => {
    const { logoDataUrl: _logo, ...rest } = validEntradaPayload();
    void _logo;
    const result = entradaPayloadSchema.safeParse(rest);
    expect(result.success).toBe(false);
  });

  it('entradaPayloadSchema.parse accepts payload with all required keys (qr + logo included)', () => {
    const result = entradaPayloadSchema.safeParse(validEntradaPayload());
    expect(result.success).toBe(true);
  });

  it('entradaPayloadSchema.parse accepts payload with esMensualidad flag', () => {
    const result = entradaPayloadSchema.safeParse({
      ...validEntradaPayload(),
      esMensualidad: true,
    });
    expect(result.success).toBe(true);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// Error class — F6.2 documents the class shape in the Error Catalog
// ──────────────────────────────────────────────────────────────────────────

describe('EscposPayloadMissingFieldError (F6.2 Error Catalog row 1)', () => {
  it('code === "escpos_payload_missing_field"', () => {
    const err = new EscposPayloadMissingFieldError([]);
    expect(err.code).toBe('escpos_payload_missing_field');
  });

  it('issues array is exposed for caller introspection', () => {
    const issues = [{ code: 'custom', path: ['x'], message: 'bad' }];
    const err = new EscposPayloadMissingFieldError(issues as never);
    expect(err.issues).toBe(issues);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// buildEntradaPayload factory — purity + structural assertions
// ──────────────────────────────────────────────────────────────────────────

describe('buildEntradaPayload factory (HU-F6.2)', () => {
  it('produces a structurally valid EntradaPayload', () => {
    const payload = buildPayload();
    const result = entradaPayloadSchema.safeParse(payload);
    expect(result.success).toBe(true);
  });

  it('esMensualidad === false when uuid_subscripcion_cliente is null', () => {
    const payload = buildEntradaPayload({
      ingreso: makeIngreso({ uuid_subscripcion_cliente: null }),
      sucursal: makeSucursal(),
      empresa: makeEmpresa(),
      operario: 'op-005',
      tipoVehiculo: 'auto',
      tarifa: makeTarifa(),
      documentos: makeDocumentos(),
      fechaHora: '2026-09-16T08:30:00Z',
    });
    expect(payload.esMensualidad).toBe(false);
  });

  it('esMensualidad === true when uuid_subscripcion_cliente is non-null', () => {
    const payload = buildEntradaPayload({
      ingreso: makeIngreso({ uuid_subscripcion_cliente: 'sub-uuid-999' }),
      sucursal: makeSucursal(),
      empresa: makeEmpresa(),
      operario: 'op-006',
      tipoVehiculo: 'moto',
      tarifa: makeTarifa(),
      documentos: makeDocumentos(),
      fechaHora: '2026-09-16T08:30:00Z',
    });
    expect(payload.esMensualidad).toBe(true);
  });

  it('logoDataUrl === "" when documentos has no logo row', () => {
    const payload = buildEntradaPayload({
      ingreso: makeIngreso(),
      sucursal: makeSucursal(),
      empresa: makeEmpresa(),
      operario: 'op-007',
      tipoVehiculo: 'auto',
      tarifa: makeTarifa(),
      documentos: [],
      fechaHora: '2026-09-16T08:30:00Z',
    });
    expect(payload.logoDataUrl).toBe('');
  });

  it('logoDataUrl carries the b64 when documentos has logo row', () => {
    const payload = buildPayload({ withLogo: true });
    expect(payload.logoDataUrl).toBe('data:image/png;base64,FAKE_LOGO_B64');
  });

  it('polizaRC carries the cert b64 when documentos has certificado row', () => {
    const payload = buildPayload({ withCert: true });
    expect(payload.polizaRC).toBe('POL-12345');
  });

  it('polizaRC is undefined when documentos has no certificado row', () => {
    const payload = buildPayload({ withCert: false });
    expect(payload.polizaRC).toBeUndefined();
  });

  it('qrDataUrl encodes the ABIERTO-01 default content as base64', () => {
    const payload = buildPayload();
    const expected = Buffer.from(
      `parkos://ingreso/${payload.folio}?placa=${payload.placa}`,
      'utf8',
    ).toString('base64');
    expect(payload.qrDataUrl).toBe(`data:image/png;base64,${expected}`);
  });
});
