"""Known regular FOMC windows; no HTTP or forecasts in the trading loop.

Dates: Federal Reserve calendar, checked 2026-10-28. Future dates are tentative.
Regular statement/presser times use 14:00/14:30 America/New_York. Coverage is
explicitly limited; this is not a complete economic calendar or a profit signal.
"""
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo
SOURCE='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
MEETINGS={2026:((1,28),(3,18),(4,29),(6,17),(7,29),(9,16),(10,28),(12,9)),
          2027:((1,27),(3,17),(4,28),(6,9),(7,28),(9,15),(10,27),(12,8))}


@lru_cache(maxsize=1)
def schedule():
    zone=ZoneInfo('America/New_York')
    return tuple((datetime(year,month,day,14,minute,tzinfo=zone).timestamp(),kind)
        for year,dates in MEETINGS.items() for month,day in dates
        for minute,kind in ((0,'decisión FOMC'),(30,'conferencia FOMC')))


def fomc_window(policy,now):
    enabled=bool(policy['enabled'] and policy['fomc_pause'])
    result={'enabled':enabled,'allowed':True,'reason':'','paused_until':None,
        'source':SOURCE,'calendar_checked_on':'2026-10-28','coverage_years':list(MEETINGS),
        'coverage':'Reuniones FOMC ordinarias conocidas; no cubre otros anuncios ni reuniones no programadas. Fechas futuras tentativas.'}
    if not enabled:return result
    pad=policy['event_pause_minutes']*60
    active=[(when,kind) for when,kind in schedule() if when-pad<=now<when+pad]
    if active:
        end=max(when+pad for when,kind in active)
        for when,kind in sorted(schedule()):
            if now<when-pad<=end:end=max(end,when+pad)
        stamp=datetime.fromtimestamp(end,ZoneInfo('UTC')).strftime('%d/%m %H:%M UTC')
        result.update(allowed=False,paused_until=end,
            reason='Pausa FOMC programada: nuevas entradas y pendientes propias suspendidas hasta '+stamp+'. Las posiciones conservan sus SL/TP.')
    return result
