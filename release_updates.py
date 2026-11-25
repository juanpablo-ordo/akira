"""Verify signed release metadata and stage only the exact official installer."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

from akira_version import LEGACY_REVISION, RELEASE_VERSION


class UpdateError(RuntimeError):
    pass


def canonical_json(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def json_object(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Campo JSON duplicado')
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError('Se esperaba un objeto JSON')
    return value


def version_tuple(value):
    if not re.fullmatch(r'(?:0|[1-9][0-9]{0,5})(?:\.(?:0|[1-9][0-9]{0,5})){2}', value):
        raise UpdateError('La versión publicada es inválida.')
    return tuple(map(int, value.split('.')))


def official_url(url, origins):
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None, 443)
            or not parts.hostname or not any(
                parts.hostname == host and parts.path.startswith(prefix)
                for host, prefix in origins
            ) or any(segment in ('.', '..') for segment in parts.path.split('/'))
            or re.search(r'%2e|%2f|%5c|\\', parts.path, re.I)):
        raise UpdateError('La dirección de actualización no pertenece al canal oficial.')
    return url


@dataclass(frozen=True)
class ReleaseTrust:
    manifest_url: str
    public_key: bytes
    publisher: str
    certificate_sha256: str
    origins: tuple[tuple[str, str], ...]

    @classmethod
    def load(cls, path=None):
        if path is None:
            path=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'release_trust.json'
        try:
            data = json_object(Path(path).read_bytes())
            key = base64.b64decode(data['public_key'], validate=True)
            fingerprint = data['certificate_sha256'].lower()
            origins = tuple(tuple(origin) for origin in data['origins'])
            if (len(key)!=32 or not re.fullmatch('[0-9a-f]{64}', fingerprint)
                    or not data['publisher'] or not origins or
                    any(len(origin)!=2 or not origin[1].startswith('/') for origin in origins)):
                raise ValueError('Identidad de firma no válida')
            return cls(official_url(data['manifest_url'], origins), key, data['publisher'], fingerprint, origins)
        except FileNotFoundError as exc:
            raise UpdateError('El canal estable todavía no tiene una identidad de firma configurada.') from exc
        except (KeyError, ValueError, TypeError) as exc:
            raise UpdateError('La identidad de confianza de esta compilación es inválida.') from exc


@dataclass(frozen=True)
class Release:
    metadata: dict
    envelope: bytes

    @property
    def version(self):
        return self.metadata['version']


def verified_release(raw, trust, installed=RELEASE_VERSION, clock=None, *, allow_same=False):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        envelope = json_object(raw)
        payload = envelope['release']
        signature = base64.b64decode(envelope['signature'], validate=True)
        Ed25519PublicKey.from_public_bytes(trust.public_key).verify(signature, canonical_json(payload))
        published = datetime.fromisoformat(payload['published_utc'].replace('Z','+00:00'))
        expires = datetime.fromisoformat(payload['expires_utc'].replace('Z','+00:00'))
        now = clock or datetime.now(timezone.utc)
        if not published.tzinfo or not expires.tzinfo or not published <= now < expires:
            raise UpdateError('El manifiesto está fuera de su período de vigencia.')
        if (payload['channel']!='stable' or payload['architecture']!='windows-x64'
                or not re.fullmatch('[0-9a-f]{40}', payload['commit'])
                or not re.fullmatch('[0-9a-f]{64}', payload['sha256'])
                or type(payload['size']) is not int or not 1 <= payload['size'] <= 12*1024**3):
            raise ValueError('Atributos del instalador no admitidos')
        official_url(payload['url'], trust.origins)
        if not urlsplit(payload['url']).path.lower().endswith('.exe'):
            raise ValueError('El activo oficial debe ser un instalador de Windows .exe')
        candidate = version_tuple(payload['version'])
        minimum = version_tuple(payload['minimum_version'])
        legacy_base = installed==LEGACY_REVISION and payload.get('upgrade_from_rev23') is True
        current = (0,0,0) if installed==LEGACY_REVISION else version_tuple(installed)
        if (installed==LEGACY_REVISION and not legacy_base) or minimum>candidate or (current<minimum and not legacy_base):
            raise UpdateError('Esta actualización requiere otra versión de AKIRA.')
        if candidate<current or (candidate==current and not allow_same):
            raise UpdateError('La versión publicada ya está instalada o es anterior.')
    except InvalidSignature as exc:
        raise UpdateError('La firma del manifiesto de actualización no es válida.') from exc
    except (KeyError, ValueError, TypeError) as exc:
        raise UpdateError('El manifiesto de actualización tiene un formato inválido.') from exc
    return Release(payload, raw)


class OfficialRedirects(HTTPRedirectHandler):
    def __init__(self, origins):
        self.origins = origins

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official_url(newurl, self.origins)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def trusted_open(trust, url, headers=None):
    from network_tls import https_context
    opener = build_opener(HTTPSHandler(context=https_context()), OfficialRedirects(trust.origins))
    return opener.open(Request(official_url(url, trust.origins), headers=headers or {}), timeout=15)


def check_channel(trust, installed=RELEASE_VERSION):
    with trusted_open(trust, trust.manifest_url, {'Accept':'application/json'}) as response:
        raw = response.read(65_537)
    if len(raw)>65_536:
        raise UpdateError('El manifiesto supera el tamaño admitido.')
    release = verified_release(raw, trust, installed, allow_same=True)
    return None if release.version == installed else release


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def authenticode(path, trust):
    if os.name!='nt':
        raise UpdateError('La firma del instalador debe verificarse en Windows.')
    script = """
    $s=Get-AuthenticodeSignature -LiteralPath $env:AKIRA_UPDATE_VERIFY_FILE
    if ($s.Status -ne 'Valid' -or $null -eq $s.SignerCertificate) { exit 9 }
    $cert=$s.SignerCertificate
    $sha=[Security.Cryptography.SHA256]::Create()
    $fingerprint=[BitConverter]::ToString($sha.ComputeHash($cert.RawData)).Replace('-','').ToLowerInvariant()
    if ($fingerprint -cne $env:AKIRA_UPDATE_VERIFY_CERT -or $cert.Subject -cne $env:AKIRA_UPDATE_VERIFY_PUBLISHER) { exit 10 }
    """
    shell=Path(os.environ['SystemRoot'])/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
    encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    result=subprocess.run([str(shell),'-NoProfile','-NonInteractive','-EncodedCommand',encoded],
        env={**os.environ,'AKIRA_UPDATE_VERIFY_FILE':str(Path(path).resolve()),
             'AKIRA_UPDATE_VERIFY_CERT':trust.certificate_sha256,'AKIRA_UPDATE_VERIFY_PUBLISHER':trust.publisher},
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,timeout=45,check=False)
    if result.returncode:
        raise UpdateError('Windows rechazó la firma Authenticode o el editor del instalador.')


def verify_installer(path, release, trust):
    path=Path(path)
    if path.stat().st_size!=release.metadata['size'] or sha256_file(path)!=release.metadata['sha256']:
        raise UpdateError('El instalador no coincide con el tamaño y SHA-256 firmados.')
    authenticode(path, trust)


def download_installer(root, release, trust, cancelled, progress=lambda downloaded,size:None):
    """Resume exactly one content hash. A full hash and publisher check are mandatory."""
    root=Path(root)
    root.mkdir(parents=True, exist_ok=True)
    metadata=release.metadata
    stem='AKIRA-'+release.version+'-'+metadata['sha256']
    partial,target=root/(stem+'.pending.exe'),root/(stem+'.exe')
    size=metadata['size']
    if target.is_file():
        verify_installer(target,release,trust)
        return target
    offset=partial.stat().st_size if partial.is_file() else 0
    if offset>size:
        partial.unlink()
        offset=0
    if offset<size:
        headers={'Accept-Encoding':'identity'}
        if offset:headers['Range']=f'bytes={offset}-'
        with trusted_open(trust,metadata['url'],headers) as response:
            if response.status==206:
                expected=f'bytes {offset}-{size-1}/{size}'
                if response.headers.get('Content-Range')!=expected:
                    raise UpdateError('El servidor devolvió un segmento incompatible.')
            elif response.status==200:
                offset=0
            else:
                raise UpdateError('El servidor no pudo descargar el instalador.')
            with partial.open('ab' if offset else 'wb') as stream:
                while offset<size:
                    if cancelled():
                        raise UpdateError('Descarga pausada. Puedes reanudarla.')
                    chunk=response.read(min(1024*1024,size-offset+1))
                    if not chunk:break
                    if offset+len(chunk)>size:raise UpdateError('La descarga supera el tamaño firmado.')
                    stream.write(chunk)
                    offset+=len(chunk)
                    progress(offset,size)
                if offset==size and response.read(1):
                    raise UpdateError('La descarga supera el tamaño firmado.')
                stream.flush()
                os.fsync(stream.fileno())
    if cancelled():raise UpdateError('Descarga pausada. Puedes reanudarla.')
    if offset<size:
        raise UpdateError('La descarga quedó incompleta. Puedes reanudarla.')
    if sha256_file(partial)!=metadata['sha256']:
        partial.unlink()
        raise UpdateError('La descarga no coincide con el SHA-256 oficial.')
    verify_installer(partial,release,trust)
    os.replace(partial,target)
    return target
