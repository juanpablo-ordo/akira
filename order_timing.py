"""Broker timestamps and request receipts; never replace a missing time with now."""
import math


def value(row, key, default=None):
    return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def positive(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def broker_seconds(row, kind='position'):
    millis = ('time_setup_msc', 'time_msc') if kind == 'order' else ('time_msc',)
    seconds = ('time_setup', 'time') if kind == 'order' else ('time', 'opened_at')
    for key in millis:
        stamp = positive(value(row, key))
        if stamp is not None:return stamp / 1000.0
    for key in seconds:
        stamp = positive(value(row, key))
        if stamp is not None:return stamp
    return None


def pending_times(snapshot):
    journal = snapshot.get('order_journal') or {}
    result = {}
    for order in snapshot.get('orders') or []:
        ticket = str(order.get('ticket') or '')
        if not ticket:continue
        meta = journal.get(ticket) or {}
        broker = broker_seconds(order, 'order')
        request = positive(meta.get('created'))
        result[ticket] = {'placed_at': broker or request,
                          'source': 'MT5: colocación' if broker else 'Akira: solicitud registrada' if request else 'Sin registro de hora',
                          'requested_at': request, 'broker_setup_at': broker}
    for ticket, meta in journal.items():
        if str(ticket) not in result:
            broker = positive(meta.get('broker_setup_at'))
            request = positive(meta.get('created'))
            result[str(ticket)] = {'placed_at': broker or request,
                                   'source': 'MT5: colocación' if broker else 'Akira: solicitud registrada' if request else 'Sin registro de hora',
                                   'requested_at': request, 'broker_setup_at': broker}
    return result
