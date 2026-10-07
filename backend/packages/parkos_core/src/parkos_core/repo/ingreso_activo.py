"""Single SQL definition of "this ingreso still has a live exit".

``V_INGRESO_ESTADO``, ``GET /ingresos/{uuid}/estado``,
``repo/salida.py::buscar_ingreso_activo_por_uuid`` and the V8
duplicate-plate guard (``repo/ingreso.py::existe_ingreso_activo``) must
agree on what "active" means. A salida whose ``anulaciones`` row is
``ejecutada`` never happened (HU-F8.1), so the vehicle is still inside.

Read-only fragment; no writes live here.
"""
from __future__ import annotations


def salida_vigente_exists_sql(ingreso_ref: str) -> str:
    """Return ``EXISTS(...)`` SQL true when ``ingreso_ref`` has a non-annulled salida.

    ``ingreso_ref`` is a trusted SQL expression (a column or bind
    parameter written in code, never user input), e.g. ``"i.uuid"`` or
    ``"CAST(:uuid_ingreso AS uuid)"``.
    """
    return f"""EXISTS (
              SELECT 1 FROM prod.salidas s
              WHERE s.uuid_ingreso = {ingreso_ref}
                AND NOT EXISTS (
                  SELECT 1 FROM prod.anulaciones a
                  WHERE a.uuid_salida = s.uuid
                    AND a.tipo_anulable = 'salida'
                    AND a.estado = 'ejecutada'
                )
            )"""
