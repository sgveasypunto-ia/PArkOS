"""PyInstaller entry point for the frozen `migrate.exe`.

Neither `api-sucursal.exe` nor `job-sync-sucursal.exe` expose an Alembic
CLI - each is a single-purpose PyInstaller onedir bundle tied to its own
entry script (uvicorn / the sync worker). The installer's migration step
(plan.md HU-F23.1, `alembic upgrade head`) needs its own frozen entry point
since there is no venv on the client machine to hold `alembic.exe`
(DEC-INST-02: standalone, no system Python).

This is a two-line passthrough to Alembic's own CLI `main()` - not business
logic. Run as `migrate.exe -c <path-to-alembic.ini> upgrade head`, same
argument contract as the real `alembic` console script.
"""
import sys

from alembic.config import main

if __name__ == "__main__":
    sys.exit(main())
