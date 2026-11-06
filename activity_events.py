"""Stable event categories shared by the activity filter and its presenter.

Classify structured fields once. Message contents must never decide the category:
an analysis about an ERROR must remain an analysis event.
"""
CATEGORIES = frozenset(('SISTEMA', 'TRADING', 'ANÁLISIS', 'AVISO', 'ERROR'))
TRADING_OPERATIONS = frozenset(('open', 'close', 'protect', 'confirmed_protect',
    'modify_order', 'cancel', 'confirmed_close', 'confirmed_open', 'confirmed_cancel',
    'pending', 'runner', 'order_send', 'order_check'))
ANALYSIS_STATES = ('ANÁLISIS', 'ANALISIS', 'MAPA', 'DATOS', 'REVISION', 'REVISIÓN',
                   'ESTUDIO', 'ESTRATEGIA', 'INDICADOR')
WARNING_STATES = ('AVISO', 'BLOQUEO', 'RECHAZO', 'RECHAZ', 'ALERTA', 'ADVERTENCIA')
ERROR_STATES = ('ERROR', 'FALLO', 'EXCEPCIÓN', 'EXCEPTION')


def category_for_event(row):
    """Return a canonical category using event metadata, never free-form text."""
    explicit = str(row.get('activity_category') or row.get('category') or '').strip().upper()
    if explicit in CATEGORIES:
        return explicit
    severity = str(row.get('severity') or row.get('level') or '').strip().upper()
    state = str(row.get('state') or '').strip().upper()
    operation = str(row.get('operation') or '').strip().lower()
    symbol = str(row.get('symbol') or '').strip().upper()
    if severity in ('ERROR', 'CRITICAL', 'FATAL') or symbol in ERROR_STATES or any(
            state.startswith(value) for value in ERROR_STATES):
        return 'ERROR'
    if severity in ('WARN', 'WARNING') or any(
            state.startswith(value) for value in WARNING_STATES):
        return 'AVISO'
    if any(state.startswith(value) for value in ANALYSIS_STATES):
        return 'ANÁLISIS'
    if operation in TRADING_OPERATIONS or any(
            state.startswith(value) for value in ('PENDIENTE', 'RUNNER', 'ORDEN',
                'OPERACIÓN', 'OPERACION', 'PROTECCIÓN', 'PROTECCION', 'OCO')):
        return 'TRADING'
    if state in ('SISTEMA', 'SYSTEM', 'INICIO', 'CONFIGURACIÓN', 'CONFIGURACION'):
        return 'SISTEMA'
    if symbol.startswith(('BTC', 'XAU')):
        return 'TRADING'
    return 'SISTEMA'
