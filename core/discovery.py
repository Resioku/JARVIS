"""
Generic "drop a file in a folder and it shows up" loader.
Any .py file in the target folder that defines the required names gets
picked up automatically. Files starting with "_" are ignored, so you can
keep helper files in the same folder without them appearing as items.

Sections and games need NAME + create_widget (the default).
Voice commands need NAME + TRIGGERS + handle (see voice/router.py).
"""
import importlib.util
from pathlib import Path


# ---------- Functions ----------

def load_plugins(folder: Path, required_attrs=("NAME", "create_widget")):
    """Scans `folder` for valid plugin files and returns their modules,
    sorted alphabetically by filename."""
    plugins = []
    if not folder.exists():
        return plugins

    for file in sorted(folder.glob("*.py")):
        if file.name.startswith("_"):
            continue

        module_name = f"_plugin_{folder.name}_{file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file)
        module = importlib.util.module_from_spec(spec)

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"[discovery] Failed to load {file.name}: {e}")
            continue

        # the "contract" every plugin file must follow
        if all(hasattr(module, attr) for attr in required_attrs):
            plugins.append(module)
        else:
            print(f"[discovery] Skipped {file.name} (missing one of {required_attrs})")

    return plugins