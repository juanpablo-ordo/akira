"""Horario operativo ligero para AKIRA V186.

No intenta reemplazar al calendario del bróker. Evita ciclos inútiles conocidos
(XAU fin de semana/rollover) y deja que MT5/order_check sea la autoridad final.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except Exception:
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception

# Guatemala no usa horario de verano. En Windows, zoneinfo puede no incluir la
# base IANA si falta el paquete tzdata. El bot NO debe dejar de arrancar por eso.
def _guatemala_tz():
    if ZoneInfo is not None:
        try:
            return ZoneInfo("America/Guatemala")
        except (ZoneInfoNotFoundError, ModuleNotFoundError, OSError):
            pass
    return timezone(timedelta(hours=-6), name="America/Guatemala")

GT = _guatemala_tz()
UTC = timezone.utc

@dataclass(frozen=True)
class MarketState:
    open: bool
    state: str
    next_open_utc: datetime | None = None
    source: str = 'Exness / horario habitual; apertura estimada, sujeta al bróker'

    @property
    def next_open_guatemala(self):
        if not self.next_open_utc:
            return ""
        return self.next_open_utc.astimezone(GT).strftime("%a %d %b %H:%M Guatemala")


def _nth_weekday(year,month,weekday,n):
    d=datetime(year,month,1,tzinfo=UTC)
    delta=(weekday-d.weekday())%7
    return d+timedelta(days=delta+7*(n-1))


def _us_summer(dt):
    # Exness usa mayormente DST de EE.UU.: segundo domingo de marzo -> primer domingo de noviembre.
    start=_nth_weekday(dt.year,3,6,2)
    end=_nth_weekday(dt.year,11,6,1)
    return start.date() <= dt.date() < end.date()


def _next_sunday_open(dt, summer):
    hour,minute=(22,5) if summer else (23,5)
    days=(6-dt.weekday())%7
    candidate=(dt+timedelta(days=days)).replace(hour=hour,minute=minute,second=0,microsecond=0)
    if candidate<=dt:
        candidate+=timedelta(days=7)
    return candidate


def xau_state(now_utc=None):
    dt=(now_utc or datetime.now(UTC)).astimezone(UTC)
    summer=_us_summer(dt)
    open_h,open_m=(22,5) if summer else (23,5)
    close_h,close_m=(20,58) if summer else (21,58)
    resume_h,resume_m=(22,2) if summer else (23,2)
    wd=dt.weekday() # Mon=0 Sun=6
    mins=dt.hour*60+dt.minute
    close_mins=close_h*60+close_m
    resume_mins=resume_h*60+resume_m
    open_mins=open_h*60+open_m

    if wd==5:
        return MarketState(False,"CERRADO FIN DE SEMANA",_next_sunday_open(dt,summer))
    if wd==6 and mins<open_mins:
        nxt=dt.replace(hour=open_h,minute=open_m,second=0,microsecond=0)
        return MarketState(False,"CERRADO FIN DE SEMANA",nxt)
    if wd==4 and mins>=close_mins:
        return MarketState(False,"CERRADO FIN DE SEMANA",_next_sunday_open(dt,summer))
    # pausa diaria de XAU de lunes a jueves; el viernes ya se trata como cierre semanal.
    if wd in (0,1,2,3) and close_mins <= mins < resume_mins:
        nxt=dt.replace(hour=resume_h,minute=resume_m,second=0,microsecond=0)
        return MarketState(False,"PAUSA DIARIA XAU",nxt)
    return MarketState(True,"ABIERTO")


def state_for(symbol, now_utc=None, cfg=None):
    s=str(symbol or '').upper()
    dt=(now_utc or datetime.now(UTC)).astimezone(UTC)
    for row in (cfg or {}).get('market_hours',{}).get('closures',[]):
        if str(row.get('symbol','')).upper()!=s:continue
        start=datetime.fromisoformat(str(row['start']).replace('Z','+00:00')).astimezone(UTC)
        end=datetime.fromisoformat(str(row['end']).replace('Z','+00:00')).astimezone(UTC)
        if start<=dt<end:
            return MarketState(False,'CIERRE EXTRAORDINARIO · '+str(row.get('reason','Comunicado del bróker')),end,
                str(row.get('source') or 'Horario extraordinario configurado por el usuario; verifica el comunicado del bróker'))
    if s.startswith('XAU'):
        return xau_state(dt)
    return MarketState(True,"ABIERTO")
