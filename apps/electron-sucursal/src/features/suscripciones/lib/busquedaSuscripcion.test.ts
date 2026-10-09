import { describe, expect, it } from 'vitest';
import { coincideBusqueda, normalizarBusqueda } from './busquedaSuscripcion';

const cli = (nombre: string | null, apellido: string | null = null, id: string | null = '1') => ({
  nombre,
  apellido,
  numero_identificacion: id,
});

describe('busquedaSuscripcion: casos borde de nombres colombianos', () => {
  it.each([
    ['jose', 'José'],
    ['JOSE', 'José'],
    ['josé', 'Jose'],
    ['maria', 'María'],
    ['María', 'MARIA'],
  ])('tildes: "%s" encuentra "%s"', (q, nombre) => {
    expect(coincideBusqueda(cli(nombre), q)).toBe(true);
  });

  it('decision enie: la enie se pliega a n, asi "munoz" y "muñoz" encuentran "Muñoz"', () => {
    const c = cli('José', 'Muñoz');
    expect(coincideBusqueda(c, 'munoz')).toBe(true);
    expect(coincideBusqueda(c, 'muñoz')).toBe(true);
    expect(coincideBusqueda(c, 'MUÑOZ')).toBe(true);
    expect(coincideBusqueda(cli('Jose', 'Munoz'), 'muñoz')).toBe(true);
    expect(coincideBusqueda(c, 'munos')).toBe(false);
  });

  it('mayuscula acentuada: "ÁNGEL" y "ángel" y "angel" se encuentran entre si', () => {
    expect(coincideBusqueda(cli('ÁNGEL'), 'angel')).toBe(true);
    expect(coincideBusqueda(cli('Ángel'), 'ÁNGEL')).toBe(true);
    expect(coincideBusqueda(cli('angel'), 'ÁNGEL')).toBe(true);
    expect(coincideBusqueda(cli('ÑANDÚ'), 'nandu')).toBe(true);
  });

  it('dieresis: "Güiza" y "Pingüino"', () => {
    expect(coincideBusqueda(cli('Luis', 'Güiza'), 'guiza')).toBe(true);
    expect(coincideBusqueda(cli('Ana', 'Pingüino'), 'pinguino')).toBe(true);
    expect(coincideBusqueda(cli('Ana', 'Pinguino'), 'pingüino')).toBe(true);
  });

  it('nombre compuesto cruzando nombre y apellido', () => {
    const c = cli('José Ángel', 'Muñoz Peña');
    expect(coincideBusqueda(c, 'jose angel')).toBe(true);
    expect(coincideBusqueda(c, 'angel munoz')).toBe(true);
    expect(coincideBusqueda(c, 'jose angel munoz pena')).toBe(true);
    expect(coincideBusqueda(c, 'pena')).toBe(true);
    expect(coincideBusqueda(c, 'peña')).toBe(true);
    expect(coincideBusqueda(c, 'angel pena')).toBe(false);
  });

  it('razon social de empresa (en cliente.nombre, sin apellido)', () => {
    const c = cli('Inversiones Muñoz & Peña S.A.S.', null, '900123456');
    expect(coincideBusqueda(c, 'inversiones munoz')).toBe(true);
    expect(coincideBusqueda(c, 'MUÑOZ & PEÑA')).toBe(true);
    expect(coincideBusqueda(c, 's.a.s')).toBe(true);
    expect(coincideBusqueda(c, '900123')).toBe(true);
    expect(coincideBusqueda(cli('Cafetería Águila Ltda.', null), 'cafeteria aguila')).toBe(true);
  });

  it('espacios multiples, tabs, NBSP y bordes en consulta y en dato', () => {
    const c = cli('José   Ángel', 'Muñoz');
    expect(coincideBusqueda(c, '  jose    angel  ')).toBe(true);
    expect(coincideBusqueda(c, 'jose\tangel')).toBe(true);
    expect(coincideBusqueda(c, 'jose\u00a0angel')).toBe(true);
    expect(coincideBusqueda(cli('José\u00a0Ángel'), 'jose angel')).toBe(true);
    expect(coincideBusqueda(cli('José\u2009Ángel'), 'jose angel')).toBe(true);
  });

  it('caracteres invisibles (zero-width, BOM, soft hyphen) no rompen la coincidencia', () => {
    expect(normalizarBusqueda('Jo\u200bsé')).toBe('jose');
    expect(normalizarBusqueda('\ufeffJosé')).toBe('jose');
    expect(normalizarBusqueda('Jo\u00adsé')).toBe('jose');
    expect(coincideBusqueda(cli('Jo\u200bsé'), 'jose')).toBe(true);
  });

  it('NFC vs NFD: el texto de la base y la consulta pueden venir en cualquier forma', () => {
    const nfc = 'José Muñoz'.normalize('NFC');
    const nfd = 'José Muñoz'.normalize('NFD');
    expect(nfc).not.toBe(nfd);
    for (const dato of [nfc, nfd]) {
      for (const q of [nfc, nfd, 'jose munoz', 'JOSÉ MUÑOZ']) {
        expect(coincideBusqueda(cli(dato), q)).toBe(true);
      }
    }
    expect(normalizarBusqueda(nfc)).toBe(normalizarBusqueda(nfd));
  });

  it('apostrofes: recto, tipografico y ausente son equivalentes', () => {
    const variantes = ["O'Brien", 'O’Brien', 'O‘Brien', 'O`Brien', 'O´Brien', 'OBrien'];
    for (const dato of variantes) {
      for (const q of variantes) {
        expect(coincideBusqueda(cli("D'Ángelo", null), "d'angelo")).toBe(true);
        expect(coincideBusqueda(cli(dato), q)).toBe(true);
      }
    }
    expect(coincideBusqueda(cli('D’Ángelo'), "d'angelo")).toBe(true);
    expect(coincideBusqueda(cli('Carlos'), "o'brien")).toBe(false);
  });

  it('guion en apellidos compuestos equivale a espacio', () => {
    expect(coincideBusqueda(cli('María', 'Pérez-Gómez'), 'perez gomez')).toBe(true);
    expect(coincideBusqueda(cli('María', 'Pérez Gómez'), 'perez-gomez')).toBe(true);
    expect(coincideBusqueda(cli('Ana-María'), 'ana maria')).toBe(true);
  });

  it('identificacion: no se ve afectada por acentos y sigue buscando por subcadena', () => {
    expect(coincideBusqueda(cli('X', null, '1020304050'), '0304')).toBe(true);
    expect(coincideBusqueda(cli('X', null, 'CE-123A'), 'ce-123a')).toBe(true);
  });

  it('no produce falsos positivos entre letras distintas', () => {
    expect(coincideBusqueda(cli('José'), 'josa')).toBe(false);
    expect(coincideBusqueda(cli('Muñoz'), 'muz')).toBe(false);
  });
});
