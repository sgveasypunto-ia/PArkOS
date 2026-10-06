/**
 * `resumenCierrePdf` — PDF export of the post-close summary (PT-5).
 * jsPDF is mocked: the contract under test is WHAT gets drawn and saved.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const textMock = vi.fn();
const saveMock = vi.fn();

vi.mock('jspdf', () => ({
  jsPDF: class {
    internal = { pageSize: { getHeight: () => 297, getWidth: () => 210 } };
    setFont = vi.fn();
    setFontSize = vi.fn();
    setDrawColor = vi.fn();
    line = vi.fn();
    addPage = vi.fn();
    splitTextToSize = (t: string) => [t];
    text = textMock;
    save = saveMock;
  },
}));

import { descargarResumenCierrePdf, toLatin1 } from '../resumenCierrePdf';

beforeEach(() => {
  textMock.mockReset();
  saveMock.mockReset();
});

describe('toLatin1', () => {
  it('keeps accents/ñ, maps typographic glyphs and drops the rest', () => {
    expect(toLatin1('Datáfono — sesión “1” ñ')).toBe('Datáfono - sesión "1" ñ');
    expect(toLatin1('ok ✓')).toBe('ok ?');
  });
});

describe('descargarResumenCierrePdf', () => {
  it('draws title, headings, label/value rows and saves <fileName>.pdf', async () => {
    await descargarResumenCierrePdf({
      title: 'Resumen de cierre de turno',
      subtitle: 'Sesión abc',
      sections: [
        {
          heading: 'Cuadre de efectivo',
          rows: [
            { label: 'Efectivo esperado', value: '$ 90.000' },
            { label: 'Diferencia', value: '-$ 15.000' },
          ],
        },
      ],
      footer: 'pie',
      fileName: 'cierre-turno-abc',
    });

    const drawn = textMock.mock.calls.map((c) => (Array.isArray(c[0]) ? c[0].join(' ') : c[0]));
    expect(drawn).toEqual(
      expect.arrayContaining([
        'Resumen de cierre de turno',
        'Sesión abc',
        'Cuadre de efectivo',
        'Efectivo esperado',
        '$ 90.000',
        'Diferencia',
        '-$ 15.000',
        'pie',
      ]),
    );
    expect(saveMock).toHaveBeenCalledWith('cierre-turno-abc.pdf');
  });
});
