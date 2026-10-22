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
    return str(cfg.get('terminal_path') or '').strip(), int(cfg.get('expected_login') or 0)


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
        self.path = Path(root) / 'state' / 'mt5_connection.json'
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            self.saved = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self.saved = {}

    def connect(self, cfg):
        requested, login = target_signature(cfg)
        path = terminal_executable(requested)
        if not requested and self.saved.get('terminal_path'):
            try:
                path = terminal_executable(self.saved['terminal_path'])
            except ConnectionProblem:
                path = ''  # An uninstalled previous terminal must not disable autodetection.
        options = {'timeout': CONNECT_TIMEOUT_MS}
        if login:
            options['login'] = login
            # Only reuse the server of this verified account and terminal.
            if (self.saved.get('login') == login and self.saved.get('server')
                    and path and path == self.saved.get('terminal_path')):
                options['server'] = self.saved['server']
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
        if login and int(account.login) != login:
            raise ConnectionProblem('ACCOUNT_MISMATCH', 'La cuenta abierta en MT5 no coincide con la guardada en Akira.',
                'Selecciona la cuenta correcta en MT5. No se enviarán órdenes a otra cuenta.')
        actual_path = path
        if getattr(terminal, 'path', ''):
            try:
                actual_path = terminal_executable(terminal.path)
            except ConnectionProblem:
                pass
        self.saved = {'terminal_path': actual_path, 'login': int(account.login),
                      'server': str(account.server)}
        # A read-only folder must not tear down a healthy broker connection.
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.saved, ensure_ascii=False), encoding='utf-8')
            temporary.replace(self.path)
        except OSError:
            pass
        return account
