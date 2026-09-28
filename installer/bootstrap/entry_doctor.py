"""PyInstaller entry point for the frozen `doctor.exe` (HU-F24.4 gate).

Two-line passthrough to the real `parkos_core.cli.doctor:main` - not
reimplemented, so the installer's post-install gate checks exactly what
the real backend's own diagnostic CLI checks (env validity, DB
connectivity, JWT key file, sync JWT file, cloud reachability), never a
parallel PowerShell approximation that could drift from it.
"""
import sys

from parkos_core.cli.doctor import main

if __name__ == "__main__":
    sys.exit(main())
