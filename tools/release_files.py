"""Create reproducible build metadata from a tested Windows installer."""
import argparse
import base64
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akira_version import RELEASE_VERSION
from release_updates import (ReleaseTrust, authenticode, canonical_json, official_url,
                             sha256_file, verified_release)


def validate_build_run(run, expected_commit, repository):
    if (run.get('status')!='completed' or run.get('conclusion')!='success'
            or run.get('head_sha')!=expected_commit
            or run.get('head_branch')!='akira-0.3-web-voz-recuperacion'
            or run.get('path')!='.github/workflows/build-windows.yml'
            or run.get('repository',{}).get('full_name')!=repository
            or run.get('head_repository',{}).get('full_name')!=repository
            or run.get('event') not in ('push','workflow_dispatch')):
        raise ValueError('Se requiere una compilación completa aprobada del mismo repositorio, rama y commit.')


def create_manifest(installer, evidence, trust, key, url, minimum, notes, expected_commit):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if (evidence.get('status')!='PASSED' or evidence.get('release_version')!=RELEASE_VERSION
            or evidence.get('source_commit')!=expected_commit
            or not re.fullmatch('[0-9a-f]{40}',expected_commit)):
        raise ValueError('Se requiere la verificación aprobada del commit exacto.')
    authenticode(installer,trust)
    digest=sha256_file(installer)
    if evidence.get('installer_sha256')!=digest or evidence.get('installer_bytes')!=installer.stat().st_size:
        raise ValueError('El instalador firmado debe ser el mismo archivo que pasó la verificación.')
    if not isinstance(key,Ed25519PrivateKey) or key.public_key().public_bytes_raw()!=trust.public_key:
        raise ValueError('La clave Ed25519 no corresponde al canal configurado.')
    issued=datetime.now(timezone.utc).replace(microsecond=0)
    release={'version':RELEASE_VERSION,'minimum_version':minimum,
             'upgrade_from_rev23':RELEASE_VERSION=='0.1.0','channel':'stable',
             'architecture':'windows-x64','commit':expected_commit,
             'url':official_url(url,trust.origins),'size':installer.stat().st_size,
             'sha256':digest,'published_utc':issued.isoformat(),
             'expires_utc':(issued+timedelta(days=30)).isoformat(),'notes':notes[:2000]}
    envelope=canonical_json({'release':release,
        'signature':base64.b64encode(key.sign(canonical_json(release))).decode('ascii')})
    verified_release(envelope,trust,minimum,allow_same=True)
    return envelope


def write_lock(report, target):
    packages = json.loads(report.read_text(encoding='utf-8'))['install']
    lines = []
    for package in sorted(packages,key=lambda row:row['metadata']['name'].lower()):
        name=package['metadata']['name']
        version=package['metadata']['version']
        digest=package['download_info']['archive_info']['hashes']['sha256']
        if not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Falta un hash SHA-256 válido para '+name)
        lines.append(f'{name}=={version} --hash=sha256:{digest}')
    target.write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    commands=parser.add_subparsers(dest='command',required=True)
    lock=commands.add_parser('lock')
    lock.add_argument('report',type=Path)
    lock.add_argument('output',type=Path)
    publish=commands.add_parser('manifest')
    publish.add_argument('--installer',type=Path,required=True)
    publish.add_argument('--verification',type=Path,required=True)
    publish.add_argument('--trust',type=Path,required=True)
    publish.add_argument('--signing-key',type=Path,required=True)
    publish.add_argument('--url',required=True)
    publish.add_argument('--minimum-version',required=True)
    publish.add_argument('--notes',type=Path,required=True)
    publish.add_argument('--output',type=Path,required=True)
    publish.add_argument('--expected-commit',required=True)
    validate=commands.add_parser('validate-run')
    validate.add_argument('--run',type=Path,required=True)
    validate.add_argument('--expected-commit',required=True)
    validate.add_argument('--repository',required=True)
    args=parser.parse_args()
    if args.command=='lock':
        write_lock(args.report,args.output)
        return
    if args.command=='validate-run':
        validate_build_run(json.loads(args.run.read_text(encoding='utf-8-sig')),
                           args.expected_commit,args.repository)
        return
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    trust=ReleaseTrust.load(args.trust)
    evidence=json.loads(args.verification.read_text(encoding='utf-8'))
    key=load_pem_private_key(args.signing_key.read_bytes(),password=None)
    args.output.write_bytes(create_manifest(args.installer,evidence,trust,key,args.url,
        args.minimum_version,args.notes.read_text(encoding='utf-8'),args.expected_commit))


if __name__=='__main__':
    main()
