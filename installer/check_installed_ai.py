"""Install the finished Windows setup, then verify its actual local AI payload.

The model must already be installed. This check never downloads a replacement
and never connects to MT5. Only the bundled CPU server on loopback is launched.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import tempfile

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from installer.smoke_local_ai import SHA, sha256, smoke
from native_studio_check import require_studio_check

from bundled_model import MODEL_NAME


def run_installer(setup, root, log):
    setup, root, log = Path(setup).resolve(), Path(root).resolve(), Path(log).resolve()
    if not setup.is_file():
        raise FileNotFoundError('No existe el instalador terminado: ' + str(setup))
    if root.exists():
        raise FileExistsError('La prueba requiere una carpeta nueva; no reemplaza datos existentes: ' + str(root))
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [str(setup), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-',
               '/NOICONS', '/TASKS=', '/DIR=' + str(root), '/LOG=' + str(log)]
    process = subprocess.run(command, timeout=600, check=False)
    if process.returncode != 0:
        detail = log.read_text(encoding='utf-8-sig', errors='replace')[-4000:] if log.is_file() else 'Sin registro del instalador.'
        raise RuntimeError('El instalador terminó con código ' + str(process.returncode) + ': ' + detail)


def validate_installed_payload(root):
    root = Path(root).resolve()
    files = {
        'application': root / 'AKIRA.exe',
        'gpu_server': root / 'local_ai/bin/llama-server.exe',
        'cpu_server': root / 'local_ai/cpu/llama-server.exe',
        'uninstaller': root / 'unins000.exe',
        'youtube_runtime': root / 'bin/deno.exe',
        'model': root / 'local_ai/models' / MODEL_NAME,
    }
    for name, path in files.items():
        if not path.is_file():
            raise FileNotFoundError('Falta un archivo después de instalar (' + name + '): ' + str(path))
        with path.open('rb') as stream:
            signature = stream.read(4 if name == 'model' else 2)
        if signature != (b'GGUF' if name == 'model' else b'MZ'):
            raise ValueError('Archivo instalado incompleto o inválido: ' + str(path))
    if sha256(files['model']) != SHA:
        raise ValueError('El modelo instalado no coincide con el SHA-256 oficial.')
    return files


def check_installed_ai(root, *, log_path=None):
    files = validate_installed_payload(root)
    with tempfile.TemporaryDirectory(prefix='akira-installed-components-') as temporary:
        report=Path(temporary)/'components.json'
        result=subprocess.run([str(files['application']),'--local-components-check',str(report),'--app-root',temporary],
            timeout=45,capture_output=True,text=True,encoding='utf-8',errors='replace')
        components=json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}
        if result.returncode or components.get('status')!='PASSED':
            raise RuntimeError('Componentes instalados sin verificar: '+str(components.get('error') or result.stderr[-500:]))
        if Path(components.get('model','')).resolve()!=files['model'].resolve():
            raise RuntimeError('La aplicación no encontró su propio modelo instalado.')
        studio_report=Path(temporary)/'studio.json'
        result=subprocess.run([str(files['application']),'--self-check',str(studio_report),'--app-root',temporary],timeout=120,capture_output=True,text=True,encoding='utf-8',errors='replace')
        actual=json.loads(studio_report.read_text(encoding='utf-8')) if studio_report.is_file() else {}
        if result.returncode or actual.get('status')!='PASSED':raise RuntimeError('La interfaz del programa instalado no pasó: '+str(actual.get('error') or result.stderr[-500:]))
        require_studio_check(actual)
        visual_report=Path(temporary)/'sprites.json'
        result=subprocess.run([str(files['application']),'--sprite-ai-check',str(visual_report),'--app-root',temporary],timeout=90,capture_output=True,text=True,encoding='utf-8',errors='replace')
        visual=json.loads(visual_report.read_text(encoding='utf-8')) if visual_report.is_file() else {}
        if result.returncode or visual.get('status')!='PASSED':raise RuntimeError('El componente visual instalado no pasó: '+str(visual.get('error') or result.stderr[-500:]))
    # Call smoke directly: get_model would conceal a missing installed file by
    # downloading another copy. A health check alone cannot pass this test.
    if log_path is None:
        smoke(files['cpu_server'], files['model'])
    else:
        smoke(files['cpu_server'], files['model'], log_path=log_path)
    return {'status': 'PASSED', 'model_sha256': SHA, 'model_present_after_setup': True,
            'visible_chat_verified': True, 'model_downloaded_by_check': False,
            'installed_components_verified': True, 'installed_studio_verified':True,'installed_sprite_ai_verified':True,'live_account_used': False, 'root': str(Path(root).resolve())}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--setup', type=Path)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--check-imports', action='store_true', help='Validate installer clients without installing or downloading')
    args = parser.parse_args(argv)
    if args.check_imports:
        print(json.dumps({'status':'PASSED', 'smoke_client':smoke.__module__,
                          'studio_validator':require_studio_check.__module__, 'installation_run':False}))
        return 0
    if args.setup is None or args.root is None or args.report is None:
        parser.error('--setup, --root and --report are required unless --check-imports is used')
    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    try:
        if os.name != 'nt':
            raise RuntimeError('La instalación completa se comprueba en Windows.')
        run_installer(args.setup, args.root, report.with_suffix('.log'))
        result = check_installed_ai(args.root, log_path=report.with_suffix('.llama.log'))
    except Exception as error:
        result = {'status': 'FAILED', 'error': type(error).__name__ + ': ' + str(error),
                  'traceback': traceback.format_exc()}
    result['server_log'] = str(report.with_suffix('.llama.log'))
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
