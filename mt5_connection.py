"""Verified MT5 reconnect target. Called only by the financial actor thread."""
from __future__ import annotations

import json
import os
from pathlib import Path

CONNECT_TIMEOUT_MS = 60_000


class ConnectionProblem(RuntimeError):
    def __init__(self, code, message, action, detail=''):
        super().__init__(message)
        self.code, self.action, self.detail = code, action, str(detail)[:800]

    def status(self, retry_seconds=0):
        return {'code': self.code, 'message': str(self), 'next_action': self.action,
                'retry_seconds': retry_seconds}


def target_signature(cfg):
    return (str(cfg.get('terminal_path') or '').strip(), int(cfg.get('expected_login') or 0),
            str(cfg.get('expected_server') or '').strip().casefold())


def account_identity(account):
    if isinstance(account, dict):return int(account.get('login') or 0), str(account.get('server') or '').strip()
    return int(account.login), str(account.server).strip()


def confirmation_matches(confirmation, account):
    identity=account_identity(account)
    return (isinstance(confirmation,(tuple,list)) and len(confirmation)==2
            and tuple(confirmation)==identity and bool(identity[0] and identity[1]))


def running_terminals():
    """Only executable paths; never inspect terminal credentials or process arguments."""
    if os.name!='nt':return []
    import psutil
    paths={}
    for process in psutil.process_iter(['name','exe']):
        try:
            if str(process.info.get('name') or '').lower() not in ('terminal64.exe','metatrader64.exe'):continue
            path=terminal_executable(process.info.get('exe'))
            if path:paths[os.path.normcase(path)]=path
        except (OSError,ConnectionProblem,psutil.Error):continue
    return sorted(paths.values())


def terminal_executable(raw):
    value = os.path.expandvars(str(raw or '').strip().strip('"'))
    if not value:
        return ''
    path = Path(value).expanduser()
    if path.is_dir():
        path = next((path / name for name in ('terminal64.exe', 'terminal.exe',
                    'metatrader64.exe', 'metatrader.exe') if (path / name).is_file()), path)
    if not path.is_file() or path.suffix.lower() != '.exe':
        raise ConnectionProblem('TERMINAL_PATH', 'No se encuentra el programa MetaTrader 5 elegido.',
            'En Ajustes → Operación, selecciona terminal64.exe o borra la ruta para usar detección automática.')
    return str(path)


class MT5Connection:
    def __init__(self, api, root):
        self.api = api
        self.observed = {}
        self.path = Path(root) / 'state' / 'mt5_connection.json'
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            self.saved = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self.saved = {}

    def connect(self, cfg, verify_target=True, prefer_open=False):
        requested, login, server = target_signature(cfg)
        self.observed={}
        path = terminal_executable(requested)
        opened=running_terminals() if not requested else []
        if len(opened)==1:path=opened[0]
        elif len(opened)>1:
            remembered=self.saved.get('terminal_path','')
            if not prefer_open and remembered in opened:path=remembered
            else:raise ConnectionProblem('MULTIPLE_TERMINALS','Hay varios programas MetaTrader 5 abiertos.',
                'En Ajustes → Operación, selecciona el terminal64.exe de la cuenta que quieres usar y vuelve a pulsar Usar cuenta abierta en MT5.')
        if not requested and not path and self.saved.get('terminal_path'):
            try:
                path = terminal_executable(self.saved['terminal_path'])
            except ConnectionProblem:
                path = ''  # An uninstalled previous terminal must not disable autodetection.
        options = {'timeout': CONNECT_TIMEOUT_MS}
        # Attach to the account selected in MT5. Supplying the remembered login
        # or server here can silently switch MT5 back to the previous account.
        try:
            initialized = self.api.initialize(path, **options) if path else self.api.initialize(**options)
        except Exception as exc:
            raise ConnectionProblem('INITIALIZE', 'No se pudo abrir la conexión con MetaTrader 5.',
                'Abre MT5 con tu cuenta demo y pulsa Reconectar MT5. Si persiste, selecciona su programa en Ajustes → Operación.',
                type(exc).__name__ + ': ' + str(exc)) from exc
        if not initialized:
            error = self.api.last_error()
            code = error[0] if isinstance(error, (list, tuple)) and error else None
            if code == -6:
                raise ConnectionProblem('LOGIN', 'MetaTrader 5 no pudo iniciar la cuenta guardada.',
                    'Inicia sesión en esa cuenta desde MT5 y permite que MT5 recuerde sus datos. El número guardado en Akira no sustituye la contraseña del bróker.', error)
            raise ConnectionProblem('TIMEOUT' if code == -10005 else 'INITIALIZE',
                'MetaTrader 5 todavía no responde a Akira.',
                'Deja MT5 abierto con la cuenta demo conectada. Akira volverá a intentarlo automáticamente; también puedes pulsar Reconectar MT5.', error)
        account, terminal = self.api.account_info(), self.api.terminal_info()
        if account is None:
            raise ConnectionProblem('NO_ACCOUNT', 'MT5 abrió, pero aún no confirma una cuenta.',
                'Abre MT5 e inicia sesión en tu cuenta demo. Akira reintentará la conexión automáticamente.')
        if terminal is None or not getattr(terminal, 'connected', False):
            raise ConnectionProblem('BROKER_OFFLINE', 'MT5 está abierto, pero no está conectado al bróker.',
                'Revisa la conexión e inicia sesión en MT5. Akira volverá a intentarlo sin cambiar tu cuenta ni sus límites.')
        if verify_target and login and int(account.login) != login:
            raise ConnectionProblem('ACCOUNT_MISMATCH', 'La cuenta abierta en MT5 no coincide con la guardada en Akira.',
                'Para cambiar de cuenta, pulsa Usar cuenta abierta en MT5 en Ajustes → Operación. Después podrás autorizarla para operar.')
        # Old releases did not store the server in preferences. Preserve their
        # verified trading binding until the user explicitly adopts another one.
        guard_server=server
        if not guard_server and cfg.get('mode')=='trade' and self.saved.get('login')==login:
            guard_server=str(self.saved.get('server') or '').strip().casefold()
        if verify_target and guard_server and str(account.server).strip().casefold()!=guard_server:
            raise ConnectionProblem('SERVER_MISMATCH','El servidor de la cuenta abierta en MT5 es distinto del guardado.',
                'Pulsa Usar cuenta abierta en MT5 para guardar juntos el número y el servidor correctos. La operativa quedará en Solo análisis hasta que la autorices.')
        actual_path = path
        if getattr(terminal, 'path', ''):
            try:
                actual_path = terminal_executable(terminal.path)
            except ConnectionProblem:
                pass
        self.observed = {'terminal_path': actual_path, 'login': int(account.login),
                         'server': str(account.server).strip()}
        if not verify_target:return account
        self.saved=dict(self.observed)
        # A read-only folder must not tear down a healthy broker connection.
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.saved, ensure_ascii=False), encoding='utf-8')
            temporary.replace(self.path)
        except OSError:
            pass
        return account

