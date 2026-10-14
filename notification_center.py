"""Persistent, bounded event history; popup and sound preferences never erase it."""
from pathlib import Path
from contextlib import contextmanager
import sqlite3,time,re

def safe_text(value):
    text=str(value)
    text=re.sub(r'\bsk-[\w-]+','[clave oculta]',text)
    text=re.sub(r'(?i)(authorization|api[_ -]?key|bearer)\s*[:= ]\s*[^\s,;]+',r'\1 [oculto]',text)
    text=re.sub(r'(?i)([?&](?:key|api[_-]?key|token)=)[^&\s]+',r'\1[oculto]',text)
    return text[:4000]

class NotificationCenter:
    def __init__(self,root,clock=time.time):
        self.path=Path(root)/'state/notifications.sqlite3';self.path.parent.mkdir(parents=True,exist_ok=True);self.clock=clock
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS notices(id INTEGER PRIMARY KEY,at REAL,title TEXT,body TEXT,severity TEXT,category TEXT,read INTEGER DEFAULT 0)')
            columns={r[1] for r in db.execute('PRAGMA table_info(notices)')}
            if 'event_key' not in columns:db.execute('ALTER TABLE notices ADD COLUMN event_key TEXT')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS notices_event_key ON notices(event_key)')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=2);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def add(self,title,body,severity='info',category='system'):
        with self.db() as db:
            cur=db.execute('INSERT INTO notices(at,title,body,severity,category) VALUES (?,?,?,?,?)',(self.clock(),safe_text(title),safe_text(body),severity,category))
            db.execute('DELETE FROM notices WHERE id NOT IN (SELECT id FROM notices ORDER BY id DESC LIMIT 1000)')
            return cur.lastrowid
    def list(self,query='',limit=200):
        with self.db() as db:return [dict(r) for r in db.execute('SELECT * FROM notices WHERE title LIKE ? OR body LIKE ? ORDER BY id DESC LIMIT ?',('%'+query+'%','%'+query+'%',min(1000,max(1,limit))))]
    def add_once(self,title,body,event_key,severity='info',category='trading'):
        with self.db() as db:
            cur=db.execute('INSERT OR IGNORE INTO notices(at,title,body,severity,category,event_key) VALUES (?,?,?,?,?,?)',
                (self.clock(),safe_text(title),safe_text(body),severity,category,str(event_key)))
            if not cur.rowcount:return None
            db.execute('DELETE FROM notices WHERE id NOT IN (SELECT id FROM notices ORDER BY id DESC LIMIT 1000)')
            return cur.lastrowid
    def mark_read(self):
        with self.db() as db:db.execute('UPDATE notices SET read=1')
    def event_keys(self,prefix):
        with self.db() as db:return {r[0] for r in db.execute('SELECT event_key FROM notices WHERE event_key LIKE ?',(str(prefix)+'%',))}
    def unread(self):
        with self.db() as db:return db.execute('SELECT count(*) FROM notices WHERE read=0').fetchone()[0]
