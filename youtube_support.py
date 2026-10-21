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
    for state in ('CERTIFICATE_ERROR','AUTH_REQUIRED','RATE_LIMITED','MISSING_RUNTIME','ACCESS_DENIED','NETWORK_ERROR'):
        if state.lower() in text:return state
    if any(s in text for s in ('certificate_verify_failed','certificate verify failed','local issuer certificate')):
        return 'CERTIFICATE_ERROR'
    if any(s in text for s in ('sign in', 'not a bot', 'confirm your age', 'login required', 'cookies', 'authentication')):
        return 'AUTH_REQUIRED'
    if any(s in text for s in ('429', 'too many requests', 'rate limit')):
        return 'RATE_LIMITED'
    if any(s in text for s in ('javascript runtime', 'js runtime', 'challenge solver', 'ejs', 'deno')):
        return 'MISSING_RUNTIME'
    if any(s in text for s in ('403','forbidden')):
        return 'ACCESS_DENIED'
    if any(s in text for s in ('unavailable', 'private video', 'removed', 'not available')):
        return 'UNAVAILABLE'
    return 'NETWORK_ERROR'


def explained(error):
    state = classify_error(error)
    messages = {
        'AUTH_REQUIRED': 'YouTube exige una sesión para esta consulta. Ajustes → FUENTES → IMPORTAR SESIÓN YOUTUBE. No se ha analizado el video.',
        'RATE_LIMITED': 'YouTube limita las peticiones. Se pausarán los reintentos.',
        'MISSING_RUNTIME': 'Falta el componente JavaScript de YouTube. Instala el paquete completo de AKIRA.',
        'UNAVAILABLE': 'El video es privado, fue retirado o no está disponible para esta sesión.',
        'NETWORK_ERROR': 'No se pudo consultar YouTube. Revisa la conexión y vuelve a comprobar las fuentes.',
        'CERTIFICATE_ERROR': 'No se pudo verificar el certificado al leer YouTube. Comprueba la fecha y los certificados de Windows. No se ha leído el video.',
        'ACCESS_DENIED': 'YouTube denegó el acceso. Puedes probar otro video o importar tu sesión desde Fuentes; no se ha leído este video.',
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
SESSION_GUIDE_HTML='''<h2>¿Para qué sirve?</h2>
<p>Es opcional. Algunos vídeos piden iniciar sesión. Akira puede usar un archivo de sesión que tú prepares; no necesita tu contraseña.</p>
<h3>1. Prepara el archivo en tu navegador</h3>
<p>Abre YouTube e inicia sesión. Una herramienta de exportación de cookies del navegador puede guardar la sesión como un archivo <b>.txt en formato Netscape</b>. Exporta únicamente <b>youtube.com</b>. Este paso se hace fuera de Akira.</p>
<p>Si no conoces estas herramientas, puedes omitir este paso y seguir usando los vídeos públicos y las demás fuentes. No hace falta crear una cuenta nueva ni enviar tu usuario a nadie.</p>
<h3>2. Selecciónalo aquí</h3>
<p>Pulsa <b>Ya tengo el archivo</b> y elige el .txt. Un enlace a YouTube, una captura o un archivo JSON no son archivos de sesión válidos. Akira comprueba el formato y la fecha antes de guardarlo en tu perfil de Windows.</p>
<h3>3. Qué ocurre después</h3>
<p>La siguiente consulta usará la sesión guardada. Si ha vencido, tendrás que exportarla de nuevo. Una sesión no elimina los límites de YouTube ni crea subtítulos donde no los hay. Akira solo indica que ha leído un vídeo cuando obtiene su transcripción completa.</p>
<p>El archivo permite acceder a tu sesión: guárdalo como un dato privado y no lo compartas en chats, GitHub ni con otras personas.</p>'''

