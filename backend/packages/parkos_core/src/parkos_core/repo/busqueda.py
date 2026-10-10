"""Helper de busqueda de texto insensible a mayusculas y espacios (defecto 7.7).

Los documentos alfanumericos (CE, pasaporte, NIT con letras) y los nombres se
guardan tal como se digitaron; comparar con ``==`` hace que ``ab123`` no
encuentre ``AB123``. Este modulo centraliza la regla: el termino se recorta y
se pasa a minusculas en Python, y la columna se compara como
``lower(trim(columna))``.

Solo para BUSQUEDA/consulta. Las llaves naturales (find-or-create) conservan
su semantica exacta -- ver ``sync/catalog/normalizers.py``.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, func
from sqlalchemy.orm import InstrumentedAttribute


def normalizar_termino(valor: str | None) -> str:
    """Recorta espacios y pasa a minusculas (``casefold``). ``None`` -> ``""``."""
    return (valor or "").strip().casefold()


def _columna_normalizada(columna: InstrumentedAttribute | ColumnElement):
    return func.lower(func.trim(columna))


def coincide_ci(columna: InstrumentedAttribute | ColumnElement, termino: str | None):
    """``lower(trim(columna)) = <termino normalizado>`` (igualdad exacta)."""
    return _columna_normalizada(columna) == normalizar_termino(termino)


def contiene_ci(columna: InstrumentedAttribute | ColumnElement, termino: str | None):
    """``lower(trim(columna)) LIKE %termino%`` con ``%``/``_``/``\`` escapados."""
    return _columna_normalizada(columna).contains(normalizar_termino(termino), autoescape=True)
