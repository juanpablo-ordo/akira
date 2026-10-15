"""Citable research ledger for strategy hypotheses. Never executes, approves or changes live MT5 orders."""
import hashlib,json,sqlite3,time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

@contextmanager
def _database(path, *, timeout):
    """Commit/rollback and CLOSE SQLite before removing a temporary directory.

    sqlite3.Connection.__exit__ commits or rolls back but does NOT close the
    connection; this matters on Windows, where open files cannot be unlinked.
    """
    connection = sqlite3.connect(path, timeout=timeout)
    try:
        with connection:
            yield connection
    finally:
        connection.close()

ALLOWED_SYMBOLS=('BTCUSDm','XAUUSDm')
MAX_BODY=24000

def _normalise_url(url):
    url=str(url or '').strip()
    parts=urlsplit(url)
    if parts.scheme not in ('https','http') or not parts.hostname or parts.username or parts.password:
        raise ValueError('Fuente web no válida')
    if parts.hostname.lower() in ('localhost','127.0.0.1','::1'):
        raise ValueError('Fuente local excluida')
    return url[:2048]

class ResearchLedger:
    """Keep evidence and hypotheses separate. A YouTube search snippet is NOT an analyzed video."""
    def __init__(self,root,clock=time.time):
        self.path=Path(root)/'state'/'research_sources.sqlite3';self.clock=clock
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with _database(self.path, timeout=2) as db:
            db.execute('CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY,url TEXT,kind TEXT,seen REAL,body TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS research_seen ON sources(seen)')
    def add(self,*,url,kind,title='',author='',body='',status='',source_time=None,symbols=(),claims=()):
        url=_normalise_url(url)
        if kind not in ('youtube_discovered','youtube_transcript','youtube_vision','news_discovered','news_read'):
            raise ValueError('Tipo de fuente desconocido')
        if kind.startswith('youtube') and (urlsplit(url).hostname or '').lower() not in ('youtube.com','www.youtube.com','m.youtube.com','youtu.be'):
            raise ValueError('No es YouTube')
        filtered=[s for s in symbols if s in ALLOWED_SYMBOLS]
        text=str(body or '')[:MAX_BODY]
        # A title or search snippet is not enough to infer a trading strategy.
        complete=kind in ('youtube_transcript','youtube_vision','news_read') and len(text)>=600 and status not in ('discovered','search_excerpt','partial','transcript_partial','transcript_fallback','captions_unavailable','vision_sampled')
        claims=[str(c)[:280] for c in claims][:12] if complete else []
        record={'url':url,'kind':kind,'title':str(title)[:240],'author':str(author)[:120],
                'observed_at':self.clock(),'source_time':source_time,'symbols':filtered,
                'status':status,'content_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest() if text else '',
                'length':len(text),'excerpt':text[:3000],'complete_evidence':complete,
                'hypotheses':claims,'experiment_only':True,'live_authorized':False,
                'note':'Una fuente no verifica reglas, rentabilidad ni autoriza operar.'}
        key=hashlib.sha256((kind+'|'+url).encode()).hexdigest()[:24]
        with _database(self.path, timeout=3) as db:
            db.execute('INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?)',(key,url,kind,record['observed_at'],json.dumps(record,ensure_ascii=False)))
            db.execute('DELETE FROM sources WHERE id NOT IN (SELECT id FROM sources ORDER BY seen DESC LIMIT 1000)')
        return record
    def recent(self,limit=30):
        with _database(self.path, timeout=3) as db:
            rows=db.execute('SELECT body FROM sources ORDER BY seen DESC LIMIT ?',(max(1,min(int(limit),100)),)).fetchall()
        return [json.loads(r[0]) for r in rows]
    def summary(self):
        rows=self.recent(100)
        return {'sources':len(rows),'youtube':sum(x['kind'].startswith('youtube') for x in rows),
                'news':sum(x['kind'].startswith('news') for x in rows),
                'reviewable':sum(x['complete_evidence'] for x in rows),'recent':rows[:8],
                'live_trading_from_sources':False,'status':'FUENTES PARA HIPÓTESIS Y BACKTEST; NO OPERACIONES REALES'}
