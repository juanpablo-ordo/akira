"""Run all Akira tests in Windows without sharing mutable Tk interpreters.

Tk's Tcl interpreter is process-global in practice and several desktop tests
create/destroy roots or patch environment variables. Keep *all* tests, but run
each GUI test module in its own interpreter. No skip or xfail is used.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DIR = ROOT / "tests"
DIAGNOSTICS = ROOT / "diagnostics"

# GUI tests use a Tcl interpreter. They must not share a Python interpreter
# with unrelated suites that change environment / Tk state.
GUI_MODULES = (
    "test_r11_pending_ui.py",
    "test_r12_theme_boot.py",
    "test_r6_expressions_layout.py",
    "test_r7_avatar_sync.py",
    "test_r8_ui_reactions.py",
    "test_v1632_resource_and_wheel.py",
    "test_v1633_startup_notice_regressions.py",
)
def _creates_tk(path: Path) -> bool:
    # AST inspection avoids treating code snippets in tests/docstrings as calls.
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return any(isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute)
               and node.func.attr == "Tk"
               and isinstance(node.func.value, ast.Name)
               and node.func.value.id in {"tk", "tkinter"}
               for node in ast.walk(tree))


def test_plan(root: Path = ROOT) -> tuple[list[str], list[str]]:
    """Return complete partition. Fail closed if a new Tk test lacks isolation."""
    test_dir = root / "tests"
    test_files = {p.name: p for p in test_dir.glob("test_*.py")}
    if not test_files:
        raise RuntimeError("No se encontraron pruebas de AKIRA")
    missing = set(GUI_MODULES).difference(test_files)
    if missing:
        raise RuntimeError(f"Faltan módulos gráficos declarados: {sorted(missing)}")
    gui = set(GUI_MODULES)
    undiscovered = [name for name, path in test_files.items()
                    if name not in gui and _creates_tk(path)]
    if undiscovered:
        raise RuntimeError("Nuevas pruebas Tk sin proceso aislado: " + ", ".join(sorted(undiscovered)))
    regular = sorted(set(test_files) - gui)
    if not regular:
        raise RuntimeError("No hay pruebas no gráficas")
    return regular, list(GUI_MODULES)


def commands(root: Path = ROOT) -> list[tuple[str, list[str]]]:
    regular, gui = test_plan(root)
    ignore = [f"--ignore=tests/{name}" for name in gui]
    # Run the non-GUI suite in one worker and ALL Tk files in separate processes.
    plan = [("REGRESSION_TESTS", ["-m", "pytest", "-q", "tests", "-ra", *ignore,
                                   "--junitxml=diagnostics/REGRESSION_TESTS.xml"])]
    for name in gui:
        stem = Path(name).stem
        plan.append((stem, ["-m", "pytest", "-q", f"tests/{name}", "-ra",
                            f"--junitxml=diagnostics/GUI_{stem}.xml"]))
    return plan


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ["--dry-run"]):
        print("Uso: python ci_windows_tests.py [--dry-run]", file=sys.stderr)
        return 2
    try:
        plan = commands()
    except (RuntimeError, OSError) as exc:
        print(f"ERROR de cobertura de pruebas: {exc}", file=sys.stderr)
        return 2
    DIAGNOSTICS.mkdir(exist_ok=True)
    manifest = {"interpreter": sys.executable, "commands": [
        {"name": name, "args": cmd} for name, cmd in plan]}
    (DIAGNOSTICS / "CI_TEST_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, cmd in plan:
        print(f"AKIRA CI > {name}: {sys.executable} {' '.join(cmd)}", flush=True)
        if args == ["--dry-run"]:
            continue
        result = subprocess.run([sys.executable, *cmd], cwd=ROOT, check=False)
        if result.returncode != 0:
            print(f"FALLO: {name} (salida {result.returncode}); el instalador NO se publica.",
                  file=sys.stderr, flush=True)
            return result.returncode if result.returncode > 0 else 1
    print("Todas las pruebas regulares y GUI completadas sin omitir módulos.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
