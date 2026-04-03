#!/usr/bin/env python3
# BACKWARD-COMPAT SHIM
# Stop notification logic moved to scripts/stop_notifier/
# This file is invoked directly by Claude Code hooks.
import importlib.util as _ilu
from pathlib import Path as _Path

_PACKAGE_DIR = _Path(__file__).resolve().parent / "stop_notifier"
_CORE_PATH = _PACKAGE_DIR / "core.py"

_core_spec = _ilu.spec_from_file_location(
    "_stop_notifier_core",
    str(_CORE_PATH),
    submodule_search_locations=[str(_PACKAGE_DIR)],
)
_core_mod = _ilu.module_from_spec(_core_spec)
_core_spec.loader.exec_module(_core_mod)

main = _core_mod.main

for _name in dir(_core_mod):
    if _name.startswith("__") and _name.endswith("__"):
        continue
    globals()[_name] = getattr(_core_mod, _name)

if __name__ == "__main__":
    main()
