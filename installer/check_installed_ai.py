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
import traceback

from installer.smoke_local_ai import SHA, sha256, smoke

MODEL_NAME = 'Qwen3-4B-Q4_K_M.gguf'


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


def check_installed_ai(root):
    files = validate_installed_payload(root)
    # Call smoke directly: get_model would conceal a missing installed file by
    # downloading another copy. A health check alone cannot pass this test.
    smoke(files['cpu_server'], files['model'])
    return {'status': 'PASSED', 'model_sha256': SHA, 'model_present_after_setup': True,
            'visible_chat_verified': True, 'model_downloaded_by_check': False,
            'live_account_used': False, 'root': str(Path(root).resolve())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--setup', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    try:
        if os.name != 'nt':
            raise RuntimeError('La instalación completa se comprueba en Windows.')
        run_installer(args.setup, args.root, report.with_suffix('.log'))
        result = check_installed_ai(args.root)
    except Exception as error:
        result = {'status': 'FAILED', 'error': type(error).__name__ + ': ' + str(error),
                  'traceback': traceback.format_exc()}
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
