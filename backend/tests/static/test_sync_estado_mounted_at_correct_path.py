"""test_sync_estado_mounted_at_correct_path.py — REGRESSION (2026-09-24).

Bug reproducido en vivo: ``GET /api/v1/sync/estado`` devolvía 404 en el
navegador aunque ``sync_estado.py::get_sync_estado`` esté correctamente
implementado y cubierto por ``tests/unit/test_sync_estado.py``. Causa raíz:
``api/v1/caja.py`` monta ``sync_estado.router`` (que declara su propio
``prefix="/sync"``) DENTRO de ``caja.router`` (que declara
``prefix="/caja"``) — FastAPI concatena ambos prefijos, publicando el
endpoint real en ``/api/v1/caja/sync/estado`` en vez de
``/api/v1/sync/estado`` (el path que documentan plan.md HU-F1.14, el
docstring de ``sync_estado.py``, y el frontend
``useSyncEstado.ts``/``SyncBanner.tsx``).

Este bug nunca lo agarró ``tests/unit/test_sync_estado.py`` porque ese
archivo ejercita el handler ``get_sync_estado`` DIRECTAMENTE como función
Python (``no FastAPI app / no httpx``, ver su propio docstring) —
bypaseando por completo la capa de montaje de rutas donde vivía el bug.

Este test es puramente de introspección de rutas (no toca la DB, no
levanta un cliente HTTP real) — construye un ``FastAPI`` efímero sobre el
router ya ensamblado (``parkos_core.api.v1.router``) y lee su esquema
OpenAPI, que resuelve el path EFECTIVO de cada ruta (incluida la
concatenación de prefijos anidados) exactamente como lo hace uvicorn en
producción. Starlette representa el árbol de sub-routers incluidos con
objetos internos (``_IncludedRouter``) que no exponen ``.path``
directamente, así que inspeccionar ``router.routes`` a mano no sirve para
este caso.
"""
from __future__ import annotations

from fastapi import FastAPI

from parkos_core.api.v1 import router


def _registered_paths() -> set[str]:
    app = FastAPI()
    app.include_router(router)
    return set(app.openapi()["paths"].keys())


def test_sync_estado_mounted_at_api_v1_sync_estado() -> None:
    """``GET /api/v1/sync/estado`` MUST be a registered route path.

    Antes del fix (mount dentro de ``caja.router``), esta ruta no existe
    y el test falla mostrando el path real registrado (con el prefijo
    ``/caja`` colado).
    """
    paths = _registered_paths()
    assert "/api/v1/sync/estado" in paths, (
        f"GET /api/v1/sync/estado no está registrado; rutas de sync "
        f"encontradas: {sorted(p for p in paths if 'sync' in p)}"
    )


def test_sync_estado_not_double_mounted_under_caja() -> None:
    """REGRESSION: ``/api/v1/caja/sync/estado`` NO debe existir.

    Ese era el path real bugueado (doble prefijo ``/caja`` + ``/sync``
    por anidar ``sync_estado.router`` dentro de ``caja.router``).
    """
    paths = _registered_paths()
    assert "/api/v1/caja/sync/estado" not in paths, (
        "sync_estado sigue montado con doble prefijo bajo /caja "
        "(regresión del bug de mounting corregido 2026-09-24)"
    )


__all__ = [
    "test_sync_estado_mounted_at_api_v1_sync_estado",
    "test_sync_estado_not_double_mounted_under_caja",
]
