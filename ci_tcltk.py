"""Isolate the actual Tcl/Tk data used by a Windows build.

The hosted Python toolcache may lose tcl8.6/init.tcl or tk8.6/button.tcl
later in a long CI job even after a successful initial Tk() probe. Take a
complete, checked snapshot outside sys.prefix and point all child interpreters
at that snapshot. Never skip a GUI test when its resources are missing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REQUIRED = {
    "tcl8.6": ("init.tcl",),
    "tk8.6": ("tk.tcl", "button.tcl", "entry.tcl", "listbox.tcl", "menu.tcl"),
}
MANIFEST = "AKIRA_CI_TCLTK_MANIFEST.json"
TK_PROBE = (
    "import tkinter as tk; "
    "root=tk.Tk(); root.withdraw(); root.update_idletasks(); "
    "assert root.tk.eval('info patchlevel'); root.destroy()"
)


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while data := f.read(1024 * 1024):
            h.update(data)
    return h.hexdigest()


def _ensure_required(root: Path) -> None:
    for folder, names in REQUIRED.items():
        for name in names:
            path = root / folder / name
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"Recurso esencial Tcl/Tk ausente o vacío: {path}")


def _scan(root: Path) -> dict[str, str]:
    _ensure_required(root)
    files: dict[str, str] = {}
    for folder in REQUIRED:
        for file in sorted((root / folder).rglob("*")):
            if file.is_file():
                files[file.relative_to(root).as_posix()] = _file_digest(file)
    if len(files) < 15:
        raise RuntimeError(f"Bibliotecas Tcl/Tk aparentemente incompletas: {len(files)} archivos")
    return files


def verify_snapshot(root: Path) -> int:
    root = Path(root)
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    actual = _scan(root)
    if actual != manifest["files"]:
        changed = sorted({*actual, *manifest["files"]} - {
            p for p in actual.keys() & manifest["files"].keys()
            if actual[p] == manifest["files"][p]
        })
        raise RuntimeError("Tcl/Tk se modificó tras preparar la copia aislada: " + ", ".join(changed[:15]))
    return len(actual)


def _environment(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["TCL_LIBRARY"] = str(root / "tcl8.6")
    env["TK_LIBRARY"] = str(root / "tk8.6")
    env["AKIRA_CI_TCLTK_ROOT"] = str(root)
    return env


def verify_window(root: Path) -> None:
    verify_snapshot(root)
    probe = subprocess.run(
        [sys.executable, "-c", TK_PROBE], env=_environment(root),
        check=False, capture_output=True, text=True, timeout=45,
    )
    if probe.returncode:
        raise RuntimeError("Tk no pudo abrir con bibliotecas aisladas: " + (probe.stderr or probe.stdout)[-1800:])


def stage_snapshot(root: Path) -> int:
    """Copy *whole* Tcl/Tk libraries from the working interpreter, not a few files."""
    import tkinter as tk

    root = Path(root).resolve()
    if root.exists():
        raise RuntimeError(f"No sobrescribir copia de Tcl/Tk ya existente: {root}")
    window = tk.Tk()
    try:
        tcl_source = Path(window.tk.eval("info library")).resolve()
        tk_source = Path(window.tk.eval("set tk_library")).resolve()
    finally:
        window.destroy()
    sources = {"tcl8.6": tcl_source, "tk8.6": tk_source}
    for label, source in sources.items():
        if not source.is_dir():
            raise RuntimeError(f"No existe biblioteca {label} del Python en ejecución: {source}")
    root.mkdir(parents=True)
    try:
        for label, source in sources.items():
            shutil.copytree(source, root / label)
        files = _scan(root)
        (root / MANIFEST).write_text(json.dumps({"schema": 1, "files": files}, indent=2), encoding="utf-8")
        verify_window(root)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("stage", "verify"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--window", action="store_true")
    args = parser.parse_args()
    try:
        if args.mode == "stage":
            n = stage_snapshot(args.root)
        else:
            n = verify_snapshot(args.root)
            if args.window:
                verify_window(args.root)
        print(f"Tcl/Tk aislado y verificable: {n} archivos; {args.root}", flush=True)
        return 0
    except Exception as exc:
        print(f"ERROR de recursos Tcl/Tk: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
