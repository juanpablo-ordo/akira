"""Give Windows CI a verified, isolated Tcl/Tk library before UI regressions.

Use the libraries supplied with the selected Python, never downloaded scripts.
Fail before pytest if files are missing, unreadable or fail native loading.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


def tree_hashes(folder):
    return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob('*')) if p.is_file()}


def copy_libraries(source,destination,tcl_version='8.6',tk_version='8.6'):
    source=Path(source).resolve();destination=Path(destination).absolute()
    if destination.exists():raise FileExistsError('El destino Tcl/Tk debe ser nuevo: '+str(destination))
    if destination.is_relative_to(source):raise ValueError('El destino no puede estar dentro de la biblioteca original')
    names=('tcl'+tcl_version,'tk'+tk_version)
    required=[names[0]+'/init.tcl',names[0]+'/auto.tcl',names[0]+'/tclIndex',
              names[1]+'/tk.tcl',names[1]+'/ttk/ttk.tcl',names[1]+'/ttk/progress.tcl']
    ttk=source/names[1]/'ttk/ttk.tcl'
    if ttk.is_file():
        for name in re.findall(r'\[file join \$::ttk::library ([A-Za-z0-9_.-]+\.tcl)\]',ttk.read_text(encoding='utf-8-sig')):
            required.append(names[1]+'/ttk/'+name)
    for name in required:
        path=source/name
        if not path.is_file() or not path.read_bytes():
            raise FileNotFoundError('Biblioteca Tcl/Tk de Python incompleta: '+str(path))
    expected={name:tree_hashes(source/name) for name in names}
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='AKIRA_TK_VERIFICAR_',dir=destination.parent))
    try:
        for name in names:
            shutil.copytree(source/name,stage/name)
            if tree_hashes(stage/name)!=expected[name]:
                raise RuntimeError('La copia Tcl/Tk no coincide con Python: '+name)
        os.replace(stage,destination)
    finally:
        if stage.exists():shutil.rmtree(stage)
    return {'source':str(source),'tcl_library':str(destination/names[0]),
            'tk_library':str(destination/names[1]),
            'verified_files':sum(len(v) for v in expected.values()),
            'library_sha256':{name:hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()
                              for name,values in expected.items()}}


def probe_libraries(info,trials=12):
    os.environ.update(TCL_LIBRARY=info['tcl_library'],TK_LIBRARY=info['tk_library'])
    import tkinter as tk
    from tkinter import ttk
    from tk_runtime import create_root
    for _ in range(trials):
        root=create_root()
        try:
            root.withdraw()
            if not Path(str(root.tk.call('info','library'))).samefile(info['tcl_library']):
                raise RuntimeError('Tcl no usa la biblioteca que se verificó')
            if not Path(str(root.tk.getvar('tk_library'))).samefile(info['tk_library']):
                raise RuntimeError('Tk no usa la biblioteca que se verificó')
            ttk.Progressbar(root,maximum=10,value=5).pack()
            tk.Button(root,text='Verificación nativa').pack()
            root.update()
            info['tcl_patchlevel']=str(root.tk.call('info','patchlevel'))
            info['tk_patchlevel']=str(root.tk.call('package','provide','Tk'))
            info['bootstrap']=root._akira_tk_bootstrap
        finally:root.destroy()
    info.update(status='PASSED',native_initializations=trials)
    return info


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--dest',required=True,type=Path)
    parser.add_argument('--report',required=True,type=Path);parser.add_argument('--github-env',type=Path)
    args=parser.parse_args(argv);args.report.parent.mkdir(parents=True,exist_ok=True)
    result={'status':'FAILED','python':sys.version,'platform':sys.platform}
    try:
        import _tkinter
        result.update(copy_libraries(Path(sys.base_prefix)/'tcl',args.dest,
                                     _tkinter.TCL_VERSION,_tkinter.TK_VERSION))
        probe_libraries(result)
        if args.github_env:
            with args.github_env.open('a',encoding='utf-8') as handle:
                for key in ('TCL_LIBRARY','TK_LIBRARY'):
                    handle.write(key+'='+result[key.lower()]+'\n')
    except Exception as exc:
        result.update(status='FAILED',error=type(exc).__name__+': '+str(exc))
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='PASSED' else 1


if __name__=='__main__':
    # Support both `python -m installer.check_tk_runtime` and the script path.
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())
