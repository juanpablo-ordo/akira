"""Explain when user-specified thresholds make automatic profit protection ineffective.

Never migrate or overwrite a user's saved risk preferences without consent.
"""
import math


def protection_config_warning(management):
    limits=(('breakeven_at_r',25.0,'breakeven'),
            ('trail_at_r',50.0,'trailing'),
            ('trail_atr',50.0,'distancia ATR'))
    problems=[]
    for key,maximum,label in limits:
        try:
            value=float(management[key])
            if not math.isfinite(value) or value>=maximum:
                problems.append(f'{label}={value:g}')
        except (TypeError,ValueError,KeyError,OverflowError):
            problems.append(f'{label}=inválido')
    if not problems:
        return ''
    return ('Protección de ganancias deshabilitada en la práctica por ajustes incompatibles: '
            + ', '.join(problems)
            + '. El SL actual de MT5 se conserva. Revisar Ajustes > Operación; no se cambian valores automáticamente.')
