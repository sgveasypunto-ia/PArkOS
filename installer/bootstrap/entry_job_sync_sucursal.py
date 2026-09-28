"""PyInstaller entry point for the frozen `job-sync-sucursal.exe`.

Not business logic — a thin shim so PyInstaller has a concrete script to
analyze. The real worker + its `main() -> int` entrypoint (env-driven,
exit 0/1/2 per plan.md §21.7) live in `parkos_core.jobs.sync_sucursal`;
this file must stay a two-line passthrough so the frozen binary's
behavior never drifts from `python -m parkos_core.jobs.sync_sucursal`.
"""
import sys

from parkos_core.jobs.sync_sucursal import main

if __name__ == "__main__":
    sys.exit(main())
