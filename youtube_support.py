"""One explicit session/runtime configuration for discovery, captions and video.

Never reads a browser profile. A session is used only after the user imports it.
"""
from pathlib import Path
import http.cookiejar
import importlib.util
import os
import re
import subprocess
import sys
import time

from akira_secrets import get_secret, canonical_path, save_secrets


class YouTubeError(RuntimeError):
    def __init__(self, state, detail):
        self.state = state
        super().__init__(state + ': ' + detail)


def classify_error(error):
    text = str(error).lower()
    if isinstance(error, YouTubeError):
        return error.state
    if any(s in text for s in ('sign in', 'not a bot', 'confirm your age', 'login required', 'cookies', 'authentication')):
        return 'AUTH_REQUIRED'
    if any(s in text for s in ('429', 'too many requests', 'rate limit')):
        return 'RATE_LIMITED'
    if any(s in text for s in ('javascript runtime', 'js runtime', 'challenge solver', 'ejs', 'deno')):
        return 'MISSING_RUNTIME'
    if any(s in text for s in ('unavailable', 'private video', 'removed', 'not available')):
        return 'UNAVAILABLE'
    return 'NETWORK_ERROR'


def explained(error):
    state = classify_error(error)
    messages = {
        'AUTH_REQUIRED': 'YouTube exige una sesión para esta consulta. Ajustes → FUENTES → IMPORTAR SESIÓN YOUTUBE. No se ha analizado el video.',
        'RATE_LIMITED': 'YouTube limita las peticiones. Se pausarán los reintentos.',
        'MISSING_RUNTIME': 'Falta el componente JavaScript de YouTube. Instala el paquete completo R7.',
        'UNAVAILABLE': 'El video es privado, fue retirado o no está disponible para esta sesión.',
        'NETWORK_ERROR': 'No se pudo consultar YouTube. Revisa la conexión y vuelve a comprobar las fuentes.',
    }
    return YouTubeError(state, messages[state])


def app_root():
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


class Quiet:
    def debug(self, *args): pass
    def info(self, *args): pass
    def warning(self, *args): pass
    def error(self, *args): pass


def options(**overrides):
    result = {'quiet': True, 'no_warnings': True, 'logger': Quiet(), 'skip_download': True,
              'noplaylist': True, 'socket_timeout': 10, 'retries': 1, 'extractor_retries': 1}
    deno = app_root() / 'bin' / ('deno.exe' if os.name == 'nt' else 'deno')
    if deno.is_file():
        result['js_runtimes'] = {'deno': {'path': str(deno)}}
    cookies = get_secret('YOUTUBE_COOKIES_FILE')
    if cookies and Path(cookies).is_file():
        result['cookiefile'] = cookies
    result.update(overrides)
    return result


def import_session(source):
    """Keep only nonexpired YouTube cookies in the private AKIRA user folder."""
    source = Path(source)
    if source.stat().st_size > 2000000:
        raise ValueError('El archivo de sesión es demasiado grande.')
    jar = http.cookiejar.MozillaCookieJar(str(source))
    jar.load(ignore_discard=True, ignore_expires=False)
    destination = canonical_path().parent / 'youtube_session.txt'
    destination.parent.mkdir(parents=True, exist_ok=True)
    filtered = http.cookiejar.MozillaCookieJar(str(destination))
    for cookie in jar:
        domain = cookie.domain.lower().lstrip('.')
        if (domain == 'youtube.com' or domain.endswith('.youtube.com')) and not cookie.is_expired(time.time()):
            filtered.set_cookie(cookie)
    if not list(filtered):
        raise ValueError('No hay cookies vigentes de youtube.com en el archivo Netscape seleccionado.')
    temporary = destination.with_suffix('.tmp')
    filtered.save(str(temporary), ignore_discard=True, ignore_expires=False)
    os.chmod(temporary, 0o600)
    temporary.replace(destination)
    save_secrets({'YOUTUBE_COOKIES_FILE': str(destination)})
    return destination


def diagnostic(check_runtime=False):
    deno = app_root() / 'bin' / ('deno.exe' if os.name == 'nt' else 'deno')
    spec = importlib.util.find_spec('yt_dlp_ejs')
    roots = list(spec.submodule_search_locations or []) if spec else []
    bundles = [p for root in roots for p in Path(root).rglob('*.min.js') if p.name in ('core.min.js', 'lib.min.js') and p.stat().st_size > 1000]
    result = {'deno_present': deno.is_file(), 'ejs_present': {p.name for p in bundles} >= {'core.min.js', 'lib.min.js'},
              'session_configured': bool(get_secret('YOUTUBE_COOKIES_FILE')), 'version': ''}
    if check_runtime and deno.is_file():
        run = subprocess.run([str(deno), '--version'], capture_output=True, text=True, timeout=15,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        match = re.search(r'deno (\d+)\.(\d+)\.(\d+)', run.stdout)
        result['version'] = match.group(0) if match else ''
        result['runtime_verified'] = bool(run.returncode == 0 and match and tuple(map(int, match.groups())) >= (2, 3, 0))
    return result
