"""Read-only audit of Akira releases; NEVER removes files.

Usage: python auditar_versiones.py [--runtime C:/Users/.../.akira_runtime]
"""
from pathlib import Path
import argparse,json

def inspect(runtime):
    runtime=Path(runtime).expanduser().resolve()
    releases=runtime/'releases';pointer=runtime/'active_install.json'
    active=None
    try:active=Path(json.loads(pointer.read_text(encoding='utf-8-sig'))['root']).resolve()
    except (OSError,KeyError,TypeError,ValueError):pass
    rows=[]
    if releases.exists():
        for d in sorted(releases.iterdir()):
            if not d.is_dir() or d.is_symlink() or not d.name.startswith('Akira_'):continue
            count=0;size=0
            for path in d.rglob('*'):
                if not path.is_file() or path.is_symlink():continue
                try:size+=path.stat().st_size;count+=1
                except OSError:pass
            rows.append({'folder':str(d),'active':d.resolve()==active,'files':count,'size_mb':round(size/1048576,1)})
    return {'runtime':str(runtime),'active':str(active) if active else None,
            'releases':rows,'note':'Solo diagnóstico; no elimina carpetas. No limpiar sin copia y verificación de la versión activa.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',default=str(Path.home()/'.akira_runtime'))
    print(json.dumps(inspect(parser.parse_args().runtime),ensure_ascii=False,indent=2))
