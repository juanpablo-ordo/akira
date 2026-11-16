"""Filter one account's report in UTC using calendar dates selected in AKIRA."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ReportFilter:
    start_utc: float
    end_utc: float
    symbol: str = ''
    strategy: str = ''
    side: str = ''
    operation: str = ''
    state: str = ''

    @classmethod
    def dates(cls, first, last, zone, **fields):
        since=date.fromisoformat(first)
        until=date.fromisoformat(last)
        if since>until:
            raise ValueError('La fecha inicial debe preceder a la fecha final.')
        local=ZoneInfo(zone)
        start=datetime.combine(since,time.min,tzinfo=local).timestamp()
        end=datetime.combine(until+timedelta(days=1),time.min,tzinfo=local).timestamp()
        return cls(start,end,**fields)

    def matches(self,row,*,stamp=None):
        if stamp is not None and not self.start_utc<=stamp<self.end_utc:return False
        side=row.get('side')
        side='BUY' if side==1 else 'SELL' if side==-1 else str(side or '').split(' ',1)[0]
        fields={'symbol':row.get('symbol'),'strategy':row.get('strategy_id') or row.get('strategy') or row.get('lane'),
                'side':side,'operation':row.get('operation')}
        if self.state and self.state.casefold() not in {str(row.get(key)).casefold() for key in ('state','confirmation')}:
            return False
        return all(not getattr(self,key) or str(value).casefold()==getattr(self,key).casefold()
                   for key,value in fields.items())
