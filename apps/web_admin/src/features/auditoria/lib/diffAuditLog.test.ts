import { describe, expect, it } from 'vitest';

import { diffAuditFields, stringifyAuditValue } from './diffAuditLog';

describe('stringifyAuditValue', () => {
  it('renders undefined as an em dash', () => {
    expect(stringifyAuditValue(undefined)).toBe('—');
  });

  it('renders null as the literal string "null"', () => {
    expect(stringifyAuditValue(null)).toBe('null');
  });

  it('passes strings through unchanged', () => {
    expect(stringifyAuditValue('hola')).toBe('hola');
  });

  it('JSON-stringifies non-string values', () => {
    expect(stringifyAuditValue(42)).toBe('42');
    expect(stringifyAuditValue({ a: 1 })).toBe('{"a":1}');
    expect(stringifyAuditValue([1, 2])).toBe('[1,2]');
  });
});

describe('diffAuditFields', () => {
  it('returns an empty array when both sides are null', () => {
    expect(diffAuditFields(null, null)).toEqual([]);
  });

  it('builds one row per key in the union of both objects, sorted alphabetically', () => {
    const rows = diffAuditFields({ b: 1, a: 1 }, { a: 1, c: 2 });
    expect(rows.map((r) => r.key)).toEqual(['a', 'b', 'c']);
  });

  it('flags a row as changed when the values differ', () => {
    const rows = diffAuditFields({ estado: 'abierta' }, { estado: 'resuelta' });
    expect(rows).toEqual([
      { key: 'estado', before: 'abierta', after: 'resuelta', changed: true },
    ]);
  });

  it('flags a row as unchanged when the values are equal', () => {
    const rows = diffAuditFields({ placa: 'ABC123' }, { placa: 'ABC123' });
    expect(rows[0]).toMatchObject({ changed: false });
  });

  it('treats a key present on only one side as changed, with undefined on the other', () => {
    const rows = diffAuditFields({ nuevo_campo: 'x' }, null);
    expect(rows).toEqual([
      { key: 'nuevo_campo', before: 'x', after: undefined, changed: true },
    ]);
  });

  it('treats deep-equal nested objects as unchanged', () => {
    const rows = diffAuditFields({ meta: { a: 1 } }, { meta: { a: 1 } });
    expect(rows[0]).toMatchObject({ changed: false });
  });
});
