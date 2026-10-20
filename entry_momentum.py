"""Causal near-entry impulse checks shared by new and resting LIMIT orders.

This is a bounded execution rule, not a predictor of future returns. Only two
contiguous, fully closed M1 bars can suspend a fading LIMIT near its entry.
"""
import math


def get(row, key, default=0):
    return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def adverse_impulse(plan, frames, now, quote=None):
    """Return evidence only; never query MT5, change protection or send orders."""
    side = number(get(plan, 'side'))
    if side not in (-1, 1) or get(plan, 'kind', '') != 'LIMIT':
        return None
    frame = frames.get('M1')
    atr = number(get(frame, 'atr'))
    entry = number(get(plan, 'entry')); sl = number(get(plan, 'sl'))
    risk = side * (entry - sl)
    if atr <= 0 or entry <= 0 or risk <= 0:
        return None
    # Cached frames are chronological. Two closed candles plus a possible
    # forming candle suffice; do not rescan the entire history per candidate.
    closed = [b for b in (get(frame, 'bars', ()) or ())[-3:] if 0 < number(get(b, 'time')) + 60 <= now]
    if len(closed) < 2:
        return None
    first, last = closed[-2:]
    times = [number(get(b, 'time')) for b in (first, last)]
    if times[1] - times[0] != 60 or not 0 <= now - (times[1] + 60) <= 90:
        return None
    adverse = -side
    for bar in (first, last):
        o, h, l, c = [number(get(bar, key)) for key in ('open', 'high', 'low', 'close')]
        if not 0 < l <= min(o, c) <= max(o, c) <= h or h <= l:
            return None
        body = adverse * (c - o)
        if body < atr * .25 or body / (h - l) < .55:
            return None
    close = number(get(last, 'close'))
    move = adverse * (close - number(get(first, 'open')))
    advance = adverse * (close - number(get(first, 'close')))
    h, l = number(get(last, 'high')), number(get(last, 'low'))
    extreme = (close - l) / (h - l) if adverse == 1 else (h - close) / (h - l)
    # Candle OHLC is BID for both sides. ASK decides BUY activation, but its
    # spread must not masquerade as a price recovery against a falling BID.
    ref = number(get(quote, 'bid')) if quote is not None else close
    activation = number(get(quote, 'ask' if side == 1 else 'bid')) if quote is not None else close
    # Both the observed close and the live quote must be near the same zone.
    # A distant map, a completed rejection, or a single red/green bar is not enough.
    reach = max(atr, risk * .35)
    if (move < max(atr * 1.15, risk * .5) or advance < atr * .25 or extreme < .70
            or abs(close - entry) > reach or ref <= 0 or activation <= 0 or abs(activation - entry) > reach
            or adverse * (ref - close) < -atr * .25):
        return None
    return {'reason': 'Dos velas M1 cerradas muestran un impulso fuerte contra esta LIMIT cerca de su entrada; esperar una nueva confirmación de rechazo.',
            'timeframe': 'M1', 'closed_bar_time': times[1], 'move_atr': round(move / atr, 3),
            'rule_version': 1, 'scope': 'Filtro de ejecución causal; sin estimación de ganancias.'}
