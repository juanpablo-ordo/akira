"""Create a verifiable, source-only archive from the exact tested Git commit.

Only Git-tracked bytes from HEAD are archived. Untracked local state, installed
models, private account files, developer caches and build diagnostics never
enter the archive. Public test-only TLS fixtures are not personal credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def execute(output: Path, report: Path, expected_commit: str, expected_version: str):
    from akira_version import RELEASE_VERSION

    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or commit != expected_commit:
        raise ValueError('El código fuente no corresponde al commit comprobado.')
    if RELEASE_VERSION != expected_version:
        raise ValueError('La versión visible no coincide con la compilación actual.')
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['git', 'archive', '--format=zip', '--output='+str(output.resolve()), 'HEAD'],
        check=True, timeout=240,
    )
    required = {
        'README.md', 'requirements.txt', 'requirements-windows-x64.lock',
        'akira_version.py', 'build_windows.py', 'installer/akira.iss',
        'mobile/build.ps1', 'docs/AKIRA_20_PAGINAS_CONTROL.md',
        'PACKAGE_SHA256.json', 'tools/source_archive.py',
    }
    with ZipFile(output) as archive:
        names = set(archive.namelist())
        if required - names:
            raise ValueError('Faltan fuentes esenciales: '+', '.join(sorted(required-names)))
        if any(name.startswith('/') or '..' in Path(name).parts or '\\' in name
               for name in names):
            raise ValueError('El ZIP tiene una ruta insegura.')
        # Preserve only public test fixture keys, never actual user credentials.
        for name in names:
            lower=name.lower()
            if (lower in ('.env','secrets.json','credentials.json')
                    or lower.endswith(('.p12','.pfx','.ppk'))
                    or (lower.endswith(('.key','.pem')) and
                        not lower.startswith('tests/tls_fixture/'))):
                raise ValueError('Archivo sensible en el ZIP: '+name)
        manifest=json.loads(archive.read('PACKAGE_SHA256.json'))
        verified=0
        for name,digest in manifest.items():
            if name not in names:
                raise ValueError('Falta archivo verificado en código fuente: '+name)
            if sha256(archive.read(name)) != digest:
                raise ValueError('Huella de fuente incorrecta: '+name)
            verified+=1
        damaged=archive.testzip()
        if damaged:
            raise ValueError('El ZIP está dañado: '+damaged)
        count=len(names)
    report.parent.mkdir(parents=True,exist_ok=True)
    result={'status':'PASSED','source_commit':commit,'release_version':RELEASE_VERSION,
            'source_zip':output.name,'size':output.stat().st_size,
            'sha256':sha256(output.read_bytes()),'verified_paths':verified,
            'archive_entries':count,'no_private_user_files':True}
    report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--report',required=True,type=Path)
    parser.add_argument('--expected-commit',required=True)
    parser.add_argument('--expected-version',required=True)
    args=parser.parse_args()
    execute(args.output,args.report,args.expected_commit,args.expected_version)


if __name__=='__main__':
    main()
