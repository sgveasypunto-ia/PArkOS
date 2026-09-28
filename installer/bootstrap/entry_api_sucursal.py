"""PyInstaller entry point for the frozen `api-sucursal.exe`.

Not business logic — a thin shim so PyInstaller has a concrete script to
analyze. The real app factory + uvicorn entrypoint live in
`api_sucursal_main.app` (backend/packages/api_sucursal); this file must
stay a two-line passthrough so the frozen binary's behavior never drifts
from `python -m api_sucursal_main.app`.
"""
from api_sucursal_main.app import main

if __name__ == "__main__":
    main()
