"""Install beside the old application; switch only the launcher and a small pointer."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import traceback
import uuid

from akira_version import BUILD_ID

MUTABLE_PREFIXES=('state/','logs/','exports/','studio/')
# Evidence from earlier releases belongs in developer sources, not every installed
# copy.  Never exclude actual runtime modules, state, logs or downloaded models.
NON_RUNTIME_PREFIXES=('VALIDACIONES_ANTERIORES/', 'INTERFAZ/',
    'INTERFAZ_16_2_1/', 'INTERFAZ_16_2_3/', 'INTERFAZ_16_2_7/',
    'EJEMPLOS_INFORMES/', 'EJEMPLOS_INFORME_16_2_1/',
    'EJEMPLOS_INFORME_16_2_3/')


def excluded_from_release(name):
    value=str(name).replace('\\','/').lstrip('./')
    return any(value.startswith(prefix) for prefix in NON_RUNTIME_PREFIXES)

MUTABLE_FILES={'akira_config.json','AKIRA_SECRETS.json','RECUPERACION_AKIRA.json','RELEASE_READY.json'}

def runtime_mutable(name):
    value=str(name).replace('\\','/').lstrip('./')
    return value in MUTABLE_FILES or any(value.startswith(prefix) for prefix in MUTABLE_PREFIXES)
from migrate_v11_settings import restore_user_data
from settings import load_config

PROCESS_PATTERN = r'(?i)(?:^|\s)(?:"[^"\r\n]*[\\/](?:Akira|Akira_FINAL_V[0-9]+|Akira_V[0-9]+)\.py"|[^\s"]*[\\/](?:Akira|Akira_FINAL_V[0-9]+|Akira_V[0-9]+)\.py|"?Akira\.py"?)(?=\s|$)'


def atomic_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex[:10] + '.tmp')
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def json_bytes(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def current_install(runtime, legacy):
    runtime = Path(runtime).resolve()
    pointer = runtime / 'active_install.json'
    if pointer.exists():
        active = Path(read_json(pointer)['root']).resolve()
        if active.parent != (runtime / 'releases').resolve() or not (active / 'akira_config.json').is_file():
            raise ValueError('La instalación activa registrada no es válida; se conserva su estado para diagnóstico.')
        return active
    # A standalone uninstall keeps userdata outside the removed code directories.
    # Treat that verified snapshot as the migration source on the next install.
    preserved = runtime / 'preserved_userdata.json'
    if preserved.is_file():
        record = read_json(preserved)
        saved = Path(record.get('root', '')).resolve()
        backups = (runtime.parent / 'Akira_Datos_Conservados').resolve()
        if (record.get('status') != 'UNINSTALLED_DATA_PRESERVED'
                or saved.parent.name != 'versiones' or saved.parent.parent.parent != backups
                or Path(record.get('backup', '')).resolve() != saved.parent.parent
                or not (saved / 'akira_config.json').is_file()):
            raise ValueError('La copia conservada de AKIRA no es válida; no se sustituye tu configuración.')
        return saved
    legacy = Path(legacy)
    if (legacy / 'akira_config.json').is_file():
        return legacy.resolve()
    parent = legacy.parent
    # Recover the current installation if a previous folder swap left it in backup.
    backups = [p for p in parent.glob('Akira.backup.pre11.*') if (p / 'akira_config.json').is_file()]
    if backups:
        return max(backups, key=lambda p: p.stat().st_mtime).resolve()
    for name in ('AKIRA_FINAL_V7', 'AKIRA_FINAL_V6', 'AKIRA_FINAL_V5', 'AKIRA_FINAL_V4',
                 'AKIRA_FINAL_V3', 'AKIRA_V207', 'AKIRA_V193', 'AKIRA_V191', 'AKIRA_V186'):
        path = parent / name
        if (path / 'akira_config.json').is_file():
            return path.resolve()
    return None


def checked_manifest(source, installed=False):
    source = Path(source).resolve()
    manifest = read_json(source / 'PACKAGE_SHA256.json')
    if not isinstance(manifest, dict) or not {'Akira.py', 'akira_version.py'}.issubset(manifest):
        raise ValueError('Manifiesto del paquete incompleto')
    for name, expected in manifest.items():
        if runtime_mutable(name) or (installed and excluded_from_release(name)):
            continue
        path = (source / name).resolve()
        if not path.is_relative_to(source) or not path.is_file():
            raise ValueError('Ruta inválida en el paquete: ' + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Archivo de paquete alterado: ' + name)
    return manifest


def prepare_release(source, runtime, config, diagnostic, current=None, restored=None):
    source = Path(source).resolve()
    runtime = Path(runtime).resolve()
    diagnostic = Path(diagnostic).resolve()
    validation = read_json(diagnostic / 'INSTALL_RESULT_AKIRA.json')
    validation_manifest = read_json(source / 'VALIDACION_V12.json')
    expected = validation_manifest['tests']
    expected_skipped = validation_manifest.get('skipped', 0)
    if not (validation.get('build') == BUILD_ID and validation.get('status') == 'PASSED'
            and validation.get('exit_code') == 0 and validation.get('child_exit_code') == 0
            and validation.get('collected') == expected and validation.get('tests_run') == expected
            and validation.get('failures') == 0 and validation.get('errors') == 0
            and validation.get('skipped') == expected_skipped):
        raise ValueError('No existe una validación completa aprobada para esta instalación.')
    manifest = checked_manifest(source)
    load_config(config)
    release = runtime / 'releases' / ('Akira_16_1_' + uuid.uuid4().hex[:10])
    release.mkdir(parents=True, exist_ok=False)
    for name in manifest:
        if runtime_mutable(name) or excluded_from_release(name):
            continue
        target = release / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    shutil.copy2(source / 'PACKAGE_SHA256.json', release / 'PACKAGE_SHA256.json')
    # Source content has already been SHA-256 validated; the installed copy
    # intentionally omits historical documentation and example outputs.
    checked_manifest(release, installed=True)
    shutil.copy2(config, release / 'akira_config.json')
    recovery = restore_user_data(current, restored, release)
    (release / 'RECUPERACION_AKIRA.json').write_bytes(json_bytes(recovery))
    ready = {'build': BUILD_ID, 'root': str(release), 'previous_root': str(current or ''),
             'config_sha256': hashlib.sha256((release / 'akira_config.json').read_bytes()).hexdigest(),
             'created': datetime.now(timezone.utc).isoformat()}
    (release / 'RELEASE_READY.json').write_bytes(json_bytes(ready))
    atomic_bytes(diagnostic / 'INSTALL_RELEASE_RESULT.json', json_bytes({'status': 'PREPARED', **ready}))
    return ready


def check_ready(runtime, release):
    runtime = Path(runtime).resolve()
    release = Path(release).resolve()
    if release.parent != (runtime / 'releases').resolve():
        raise ValueError('La versión nueva debe estar dentro del directorio de versiones de Akira.')
    ready = read_json(release / 'RELEASE_READY.json')
    if ready['build'] != BUILD_ID or ready['root'] != str(release):
        raise ValueError('La versión nueva no terminó su preparación.')
    if hashlib.sha256((release / 'akira_config.json').read_bytes()).hexdigest() != ready['config_sha256']:
        raise ValueError('La configuración cambió después de preparar la instalación.')
    # Runtime data/config are mutable and therefore never belong to PACKAGE_SHA256.
    # Every entry that remains in the manifest is immutable tested code/assets.
    for name, expected in read_json(release / 'PACKAGE_SHA256.json').items():
        if runtime_mutable(name) or excluded_from_release(name):
            continue
        path = (release / name).resolve()
        if not path.is_relative_to(release) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('La versión preparada tiene un archivo alterado: ' + name)
    load_config(release / 'akira_config.json')
    return ready


def rollback_release(runtime, diagnostic):
    runtime = Path(runtime).resolve()
    diagnostic = Path(diagnostic).resolve()
    transaction = read_json(diagnostic / 'INSTALL_ACTIVATION.json')
    if transaction['runtime'] != str(runtime):
        raise ValueError('La recuperación pertenece a otra instalación.')
    errors = []
    for item in reversed(transaction['files']):
        path = Path(item['path'])
        before = (diagnostic / item['before_file']).read_bytes() if item['before_exists'] else None
        after = (diagnostic / item['after_file']).read_bytes()
        try:
            current = path.read_bytes() if path.exists() else None
            if current == before:
                continue
            if current != after:
                raise RuntimeError('El archivo cambió fuera de esta instalación; no se sobrescribe: ' + str(path))
            if before is None:
                path.unlink(missing_ok=True)
            else:
                atomic_bytes(path, before)
        except Exception as error:
            errors.append(type(error).__name__ + ': ' + str(error))
    transaction['status'] = 'ROLLBACK_FAILED' if errors else 'ROLLED_BACK'
    transaction['rollback_errors'] = errors
    atomic_bytes(diagnostic / 'INSTALL_ACTIVATION.json', json_bytes(transaction))
    if errors:
        raise RuntimeError('; '.join(errors))
    return {'status': 'ROLLED_BACK', 'old_application_untouched': True}


def activate_release(runtime, release, diagnostic, shortcut, new_shortcut):
    runtime = Path(runtime).resolve()
    diagnostic = Path(diagnostic).resolve()
    diagnostic.mkdir(parents=True, exist_ok=True)
    ready = check_ready(runtime, release)
    # Snapshot both small files before changing either. Never rename the old application directory.
    files = []
    changes = ((Path(shortcut).resolve(), Path(new_shortcut).read_bytes()),
               (runtime / 'active_install.json', json_bytes(ready)))
    for index, (path, content) in enumerate(changes):
        exists = path.exists()
        before_file = f'ACTIVACION_ANTES_{index}.bin'
        after_file = f'ACTIVACION_NUEVA_{index}.bin'
        if exists:
            atomic_bytes(diagnostic / before_file, path.read_bytes())
        atomic_bytes(diagnostic / after_file, content)
        files.append({'path': str(path), 'before_exists': exists, 'before_file': before_file, 'after_file': after_file})
    transaction = {'build': BUILD_ID, 'runtime': str(runtime), 'root': ready['root'],
                   'status': 'ACTIVATING', 'files': files}
    atomic_bytes(diagnostic / 'INSTALL_ACTIVATION.json', json_bytes(transaction))
    try:
        for path, content in changes:
            atomic_bytes(path, content)
        transaction['status'] = 'ACTIVATED'
        atomic_bytes(diagnostic / 'INSTALL_ACTIVATION.json', json_bytes(transaction))
    except Exception as original:
        try:
            rollback_release(runtime, diagnostic)
        except Exception as recovery:
            raise RuntimeError('Activación: ' + repr(original) + '; recuperación: ' + repr(recovery)) from original
        raise
    return {'status': 'ACTIVATED', **ready}


def inspect_old_releases(runtime):
    """Report legacy releases without touching active code or any user data."""
    runtime=Path(runtime).resolve()
    pointer=runtime/'active_install.json'
    active=Path(read_json(pointer)['root']).resolve() if pointer.is_file() else None
    releases=runtime/'releases'
    if not releases.is_dir():
        return {'status':'INSPECTED','active':str(active or ''),'old_releases':[]}
    result=[]
    for candidate in sorted(releases.iterdir()):
        if not candidate.is_dir() or candidate.is_symlink() or candidate.resolve()==active:
            continue
        if candidate.name.startswith('Akira_') and all((candidate/name).is_file() for name in
                ('Akira.py','akira_config.json','akira_version.py')):
            result.append(str(candidate.resolve()))
    return {'status':'INSPECTED','active':str(active or ''),'old_releases':result}


def cleanup_old_releases(runtime, backup_root):
    """Remove only verified inactive releases after successful activation and backup.

    Never removes the active release, unknown files, other applications, or a
    legacy user's data prior to migration. Hash-verifies each preserved file.
    """
    runtime=Path(runtime).resolve()
    backup_root=Path(backup_root).resolve()
    pointer=runtime/'active_install.json'
    if not pointer.is_file():
        raise ValueError('No hay versión activada: no se limpia ninguna carpeta.')
    active=Path(read_json(pointer)['root']).resolve()
    if active.parent!=(runtime/'releases').resolve() or not (active/'RELEASE_READY.json').is_file():
        raise ValueError('No se ha verificado la versión activa; limpieza cancelada.')
    report={'status':'CLEANED','kept_active':str(active),'removed':[],'skipped':[],'deferred':[]}
    for raw in inspect_old_releases(runtime)['old_releases']:
        old=Path(raw)
        if old==active or old.parent!=(runtime/'releases').resolve():
            report['skipped'].append(str(old));continue
        if any(item.is_symlink() for item in old.rglob('*')):
            report['skipped'].append(str(old)+' (enlace detectado)');continue
        backup=backup_root/(datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])/old.name
        try:
            for name in ('akira_config.json','AKIRA_SECRETS.json','state','logs','exports','studio'):
                source=old/name
                if not source.exists():continue
                dest=backup/name
                if source.is_dir():
                    for original in source.rglob('*'):
                        if not original.is_file():continue
                        target=dest/original.relative_to(source)
                        target.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(original,target)
                        if hashlib.sha256(original.read_bytes()).digest()!=hashlib.sha256(target.read_bytes()).digest():
                            raise RuntimeError('Copia de datos no verificada; se conserva '+str(old))
                elif source.is_file():
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,dest)
                    if hashlib.sha256(source.read_bytes()).digest()!=hashlib.sha256(dest.read_bytes()).digest():
                        raise RuntimeError('Copia no verificada; se conserva '+str(old))
        except (OSError, RuntimeError) as error:
            # Backup failed or a file is in use: keep the old release unchanged.
            report['deferred'].append({'release':str(old),'stage':'backup','error':str(error)})
            continue
        quarantine=old.with_name('.akira_cleanup_'+uuid.uuid4().hex[:12])
        try:
            old.rename(quarantine)
        except OSError as error:
            report['deferred'].append({'release':str(old),'stage':'rename','error':str(error)})
            continue
        try:
            shutil.rmtree(quarantine)
        except OSError as error:
            # Directory deletion may already be partial; NEVER rename that
            # incomplete tree back as an apparently valid old release.
            report['deferred'].append({'release':str(old),'quarantine':str(quarantine),
                                       'stage':'delete','error':str(error)})
            continue
        report['removed'].append({'release':str(old),'backup':str(backup)})
    if report['deferred']:
        report['status']='PARTIAL_CLEANUP'
    return report



DIAGNOSTIC_PATTERN=re.compile(r'^\d{8}_\d{6}\.[0-9a-fA-F]{8}$')
PROTECTED_DIAGNOSTIC_NAMES={'AKIRA_SECRETS.json', 'state', 'logs', 'exports'}


def inspect_install_diagnostics(runtime, current=None):
    """Identify old installer-generated diagnostics; never inspect/deleting account data.

    Only folders in this exact, dedicated location with a generated name and no
    links are eligible. Existing user files or inconclusive folders are kept.
    """
    runtime=Path(runtime).resolve()
    base=runtime.parent/'Akira_Diagnostico_Instalacion'
    if not base.exists():
        return {'status':'INSPECTED','base':str(base),'keep':[],'removable':[]}
    if base.is_symlink() or not base.is_dir() or base.resolve()!=base:
        raise ValueError('Carpeta de diagnósticos redirigida; limpieza cancelada.')
    current=Path(current).resolve() if current else None
    entries=[]
    for candidate in base.iterdir():
        if not candidate.is_dir() or candidate.is_symlink() or not DIAGNOSTIC_PATTERN.fullmatch(candidate.name):
            continue
        if candidate.resolve()!=candidate:
            continue
        if current is not None and candidate == current:
            continue
        if any(child.is_symlink() for child in candidate.rglob('*')):
            continue
        if any((candidate/name).exists() for name in PROTECTED_DIAGNOSTIC_NAMES):
            continue
        # Unrecognized payloads are not automatically deleted.
        if any(child.is_file() and child.suffix.lower() not in
               ('.json','.log','.txt','.bin','.lnk','.png','.jpg','.csv')
               for child in candidate.rglob('*')):
            continue
        result_file=candidate/'INSTALL_HOST_RESULT.json'
        try:
            state=str(read_json(result_file).get('status','')).upper() if result_file.is_file() else 'INCOMPLETE'
        except (ValueError,OSError,TypeError):
            state='INCOMPLETE'
        group='success' if state=='INSTALLED' else ('failure' if state=='FAILED' else 'incomplete')
        entries.append({'path':str(candidate),'group':group,'last_modified':candidate.stat().st_mtime})
    entries.sort(key=lambda x:(x['last_modified'],x['path']),reverse=True)
    # Latest two of each category are retained; failures can be useful when
    # investigating bugs.  All other recognized diagnostics are candidates.
    kept={'success':0,'failure':0,'incomplete':0}
    keep=[];removable=[]
    for entry in entries:
        group=entry['group']
        if kept[group]<2:
            kept[group]+=1;keep.append(entry)
        else:
            removable.append(entry)
    return {'status':'INSPECTED','base':str(base),'keep':keep,
            'removable':removable,'protected_current':str(current or '')}


def cleanup_install_diagnostics(runtime, current):
    """Prune only older generated installer logs after a confirmed installation.

    Data back-ups, current diagnostic and any unfamiliar folders are untouched.
    """
    runtime=Path(runtime).resolve()
    pointer=runtime/'active_install.json'
    if not pointer.is_file():
        raise ValueError('No hay instalación activada; no se retiran diagnósticos.')
    active=Path(read_json(pointer)['root']).resolve()
    if active.parent!=(runtime/'releases').resolve() or not (active/'RELEASE_READY.json').is_file():
        raise ValueError('La instalación activa no está verificada.')
    info=inspect_install_diagnostics(runtime,current)
    removed=[];deferred=[]
    for item in info['removable']:
        folder=Path(item['path'])
        try:
            # Re-inspect for TOCTOU and symlinks, so adding personal data or
            # a link after preview makes the deletion fail closed.
            if folder.is_symlink() or any(part.is_symlink() for part in folder.rglob('*')):
                raise ValueError('Enlace detectado')
            if any((folder/name).exists() for name in PROTECTED_DIAGNOSTIC_NAMES):
                raise ValueError('Datos protegidos')
            if folder.parent.resolve()!=Path(info['base']).resolve() or not DIAGNOSTIC_PATTERN.fullmatch(folder.name):
                raise ValueError('Fuera de diagnósticos gestionados')
            shutil.rmtree(folder)
            removed.append(str(folder))
        except (OSError,ValueError) as error:
            deferred.append({'path':str(folder),'error':str(error)})
    return {'status':'PARTIAL_CLEANUP' if deferred else 'CLEANED',
            'removed':removed,'deferred':deferred,'preserved':info['keep'],
            'protected_current':str(current)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('current', 'prepare', 'activate', 'rollback', 'process-pattern', 'inspect', 'cleanup', 'inspect-maintenance', 'cleanup-maintenance'))
    parser.add_argument('--runtime-root', type=Path)
    parser.add_argument('--legacy-root', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--diagnostic', type=Path)
    parser.add_argument('--current', type=Path)
    parser.add_argument('--restore-info', type=Path)
    parser.add_argument('--release', type=Path)
    parser.add_argument('--shortcut', type=Path)
    parser.add_argument('--new-shortcut', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'process-pattern':
            print(PROCESS_PATTERN)
            return 0
        if args.action == 'current':
            current = current_install(args.runtime_root, args.legacy_root)
            result = {'root': str(current or '')}
        elif args.action == 'prepare':
            restored = read_json(args.restore_info).get('restored') if args.restore_info else None
            result = prepare_release(args.source, args.runtime_root, args.config, args.diagnostic, args.current, restored or None)
        elif args.action == 'activate':
            result = activate_release(args.runtime_root, args.release, args.diagnostic, args.shortcut, args.new_shortcut)
        elif args.action == 'inspect':
            result = inspect_old_releases(args.runtime_root)
        elif args.action == 'cleanup':
            result = cleanup_old_releases(args.runtime_root, args.runtime_root.parent/'Akira_Datos_Conservados')
        elif args.action == 'inspect-maintenance':
            result = inspect_install_diagnostics(args.runtime_root, args.diagnostic)
        elif args.action == 'cleanup-maintenance':
            if not args.diagnostic:
                raise ValueError('Se requiere el diagnóstico actual para protegerlo.')
            result = cleanup_install_diagnostics(args.runtime_root, args.diagnostic)
        else:
            result = rollback_release(args.runtime_root, args.diagnostic)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        result = {'status': 'FAILED', 'action': args.action, 'build': BUILD_ID,
                  'error': type(error).__name__ + ': ' + str(error), 'traceback': traceback.format_exc()}
        if args.diagnostic:
            atomic_bytes(args.diagnostic / ('INSTALL_' + args.action.upper() + '_ERROR.json'), json_bytes(result))
        # Python errors go through stdout so PowerShell preserves the structured original message.
        print(json.dumps(result, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
