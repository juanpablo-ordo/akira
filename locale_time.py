"""IANA presentation time; broker ticks and candles always remain UTC."""
from dataclasses import dataclass
from datetime import datetime,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from contextvars import ContextVar
from contextlib import contextmanager
import os

@dataclass(frozen=True)
class LocaleTimeSettings:
    country:str='GT'
    region:str=''
    city:str='Ciudad de Guatemala'
    timezone:str='America/Guatemala'
    automatic:bool=False
    date_format:str='%d/%m/%Y'
    time_format:str='%H:%M:%S'
    @classmethod
    def from_config(cls,config=None):
        raw=(config or {}).get('locale',config or {})
        fields={k:raw[k] for k in cls.__dataclass_fields__ if k in raw}
        result=cls(**fields)
        if result.automatic:
            detected=os.environ.get('TZ') or getattr(datetime.now().astimezone().tzinfo,'key',None)
            if not detected:
                try:
                    from tzlocal import get_localzone_name
                    detected=get_localzone_name()
                except (ImportError,OSError,ValueError,ZoneInfoNotFoundError):pass
            if detected:
                try:ZoneInfo(detected);fields['timezone']=detected;result=cls(**fields)
                except (ZoneInfoNotFoundError,ValueError):pass
        try:ZoneInfo(result.timezone)
        except (ZoneInfoNotFoundError,ValueError,TypeError):raise ValueError('Zona horaria inválida: usa un identificador IANA, por ejemplo America/Guatemala')
        if result.date_format not in ('%d/%m/%Y','%Y-%m-%d','%m/%d/%Y'):raise ValueError('Formato de fecha no admitido')
        if result.time_format not in ('%H:%M:%S','%I:%M:%S %p'):raise ValueError('Formato de hora no admitido')
        return result
    def now(self):return datetime.now(ZoneInfo(self.timezone))
    def format(self,stamp,short=False):
        if stamp is None:return ''
        dt=datetime.fromisoformat(stamp.replace('Z','+00:00')) if isinstance(stamp,str) and '-' in stamp else datetime.fromtimestamp(float(stamp),timezone.utc)
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(self.timezone)).strftime(self.date_format+' '+self.time_format)
    def context(self):
        local=self.now()
        return {'local_time':local.isoformat(),'timezone':self.timezone,'country':self.country,'region':self.region,'city':self.city,'utc_time':local.astimezone(timezone.utc).isoformat()}

_REPORT_LOCALE=ContextVar('akira_report_locale',default=LocaleTimeSettings())
@contextmanager
def presentation_time(config):
    token=_REPORT_LOCALE.set(LocaleTimeSettings.from_config(config))
    try:yield _REPORT_LOCALE.get()
    finally:_REPORT_LOCALE.reset(token)
def current_locale():return _REPORT_LOCALE.get()
