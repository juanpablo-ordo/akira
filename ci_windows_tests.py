"""Verify ALL Akira tests in Windows with one Tcl interpreter per GUI case.

Each GUI test node runs in its own Python process and uses its own complete,
SHA256-verified copy of Tcl/Tk. A failing or skipped test fails the build.
The regular suite also runs in full; no xfail/skip/ignore for GUI cases.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DIR = ROOT / "tests"
DIAGNOSTICS = ROOT / "diagnostics"

GUI_MODULES = (
    "test_r11_pending_ui.py", "test_r12_theme_boot.py", "test_r13_chart_dpi.py",
    "test_r6_expressions_layout.py", "test_r7_avatar_sync.py",
    "test_r8_ui_reactions.py", "test_v1632_resource_and_wheel.py",
    "test_v1633_startup_notice_regressions.py",
)


def _creates_tk(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return any(isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute)
               and node.func.attr == "Tk"
               and isinstance(node.func.value, ast.Name)
               and node.func.value.id in {"tk", "tkinter"}
               for node in ast.walk(tree))


def test_plan(root: Path = ROOT) -> tuple[list[str], list[str]]:
    test_dir = root / "tests"
    files = {p.name: p for p in test_dir.glob("test_*.py")}
    if not files:
        raise RuntimeError("No se encontraron pruebas de AKIRA")
    missing = set(GUI_MODULES) - set(files)
    if missing:
        raise RuntimeError("Faltan módulos GUI: " + ", ".join(sorted(missing)))
    unexpected = sorted(n for n,p in files.items() if n not in GUI_MODULES and _creates_tk(p))
    if unexpected:
        raise RuntimeError("Nuevas pruebas Tk sin proceso aislado: " + ", ".join(unexpected))
    regular = sorted(set(files) - set(GUI_MODULES))
    if not regular:
        raise RuntimeError("No hay pruebas regulares")
    return regular, list(GUI_MODULES)


def commands(root: Path = ROOT) -> list[tuple[str,list[str]]]:
    _, gui = test_plan(root)
    ignore = ["--ignore=tests/"+name for name in gui]
    cmds = [("REGRESSION_TESTS",["-m","pytest","-q","tests","-ra",*ignore,
                     "--junitxml=diagnostics/REGRESSION_TESTS.xml"])]
    for name in gui:
        stem = Path(name).stem
        cmds.append((stem,["-m","pytest","-q",f"tests/{name}","-ra",
                           f"--junitxml=diagnostics/GUI_{stem}.xml"]))
    return cmds


def parse_collected_nodes(output: str, module: str) -> list[str]:
    """Fail closed if pytest output is incomplete or the collected count mismatches."""
    prefix = "tests/" + module + "::"
    nodes = [line.strip().replace("\\", "/") for line in output.splitlines()
             if line.strip().replace("\\", "/").startswith(prefix)]
    matches = re.findall(r"(?m)^\s*(\d+) tests? collected\b", output)
    if not matches or int(matches[-1]) != len(nodes) or len(nodes) == 0 or len(set(nodes)) != len(nodes):
        raise RuntimeError("Colección incompleta de "+module+": "+output[-1500:])
    return nodes


def collect_nodes(module: str) -> list[str]:
    process = subprocess.run([sys.executable,"-m","pytest","--collect-only","-q",
                              "tests/"+module], cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=120)
    if process.returncode != 0:
        raise RuntimeError("No se pudo recopilar "+module+": "+(process.stdout+process.stderr)[-2000:])
    return parse_collected_nodes(process.stdout,module)


def _env_for_isolated_tk(master: Path, private: Path) -> dict[str,str]:
    """Copy *all* Tcl/Tk resources for each individual GUI test."""
    from ci_tcltk import verify_snapshot
    verify_snapshot(master)
    private.mkdir(parents=True)
    for folder in ("tcl8.6","tk8.6"):
        shutil.copytree(master/folder,private/folder)
    shutil.copy2(master/"AKIRA_CI_TCLTK_MANIFEST.json",private/"AKIRA_CI_TCLTK_MANIFEST.json")
    verify_snapshot(private)
    env = os.environ.copy()
    env["TCL_LIBRARY"] = str(private/"tcl8.6")
    env["TK_LIBRARY"] = str(private/"tk8.6")
    env["AKIRA_CI_TCLTK_ROOT"] = str(private)
    return env


def _verify_junit(file: Path) -> int:
    root=ET.parse(file).getroot()
    suites=list(root.iter("testsuite"))
    if not suites: raise RuntimeError("JUnit sin testsuite: "+str(file))
    total=sum(int(s.attrib.get("tests","0")) for s in suites)
    skipped=sum(int(s.attrib.get("skipped","0")) for s in suites)
    failed=sum(int(s.attrib.get("failures","0"))+int(s.attrib.get("errors","0")) for s in suites)
    if total < 1 or skipped or failed:
        raise RuntimeError(f"Test omitido o incompleto en {file}: tests={total}, skips={skipped}, fallos={failed}")
    return total


def main(argv: list[str] | None=None) -> int:
    args=list(sys.argv[1:] if argv is None else argv)
    if args not in ([],["--dry-run"]):
        print("Uso: python ci_windows_tests.py [--dry-run]",file=sys.stderr);return 2
    try:
        plan=commands()
        details={module:collect_nodes(module) for module in GUI_MODULES}
    except Exception as exc:
        print("ERROR: plan incompleto: "+str(exc),file=sys.stderr,flush=True);return 2
    DIAGNOSTICS.mkdir(exist_ok=True)
    (DIAGNOSTICS/"CI_TEST_MANIFEST.json").write_text(json.dumps({
        "interpreter":sys.executable,
        "regular":plan[0][1],
        "gui_cases":details,
        "gui_count":sum(len(v) for v in details.values()),
        "model":"fresh interpreter and private Tcl/Tk tree per GUI case",
    },indent=2,ensure_ascii=False),encoding="utf-8")
    print("AKIRA CI: "+str(sum(map(len,details.values())))+" casos GUI independientes",flush=True)
    if args==["--dry-run"]: return 0
    master_string=os.environ.get("AKIRA_CI_TCLTK_ROOT","")
    if sys.platform=="win32" and os.environ.get("GITHUB_ACTIONS")=="true" and not master_string:
        print("FALLO: Windows CI sin árbol Tcl/Tk verificado",file=sys.stderr);return 1
    master=Path(master_string) if master_string else None
    regular=plan[0][1]
    print("AKIRA CI > REGRESSION_TESTS: "+" ".join(regular),flush=True)
    p=subprocess.run([sys.executable,*regular],cwd=ROOT,check=False)
    if p.returncode:
        print("FALLO de pruebas regulares; NO publicar instalador",file=sys.stderr);return 1
    successful=0
    for module,nodes in details.items():
        for i,node in enumerate(nodes):
            stem=Path(module).stem
            report=DIAGNOSTICS/f"GUI_{stem}_{i:03d}.xml"
            cmd=[sys.executable,"-m","pytest","-q",node,"-ra",f"--junitxml={report}"]
            print(f"AKIRA CI > GUI [{successful+1}/{sum(map(len,details.values()))}]: {node}",flush=True)
            if master:
                with tempfile.TemporaryDirectory(prefix="akira_tk_case_") as temp:
                    private=Path(temp)/"tcltk"
                    try:
                        env=_env_for_isolated_tk(master,private)
                        from ci_tcltk import verify_window,verify_snapshot
                        verify_window(private)
                        result=subprocess.run(cmd,cwd=ROOT,check=False,env=env)
                        verify_snapshot(private)
                    except Exception as exc:
                        print("FALLO de Tcl/Tk aislado en "+node+": "+str(exc),file=sys.stderr,flush=True)
                        return 1
            else:
                result=subprocess.run(cmd,cwd=ROOT,check=False)
            if result.returncode:
                print("FALLO de GUI en "+node+". No publicar instalador",file=sys.stderr,flush=True)
                return 1
            try:_verify_junit(report)
            except Exception as exc:
                print("FALLO de evidencia de prueba: "+str(exc),file=sys.stderr);return 1
            successful+=1
    print(f"AKIRA CI: pruebas regulares y {successful} pruebas GUI completas y verificadas",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
