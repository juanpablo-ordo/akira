"""Persistent topic conversations and explicitly saved memories, stored separately."""
from pathlib import Path
from contextlib import contextmanager
import sqlite3,threading,time,uuid,re

class ChatStore:
 def __init__(self,root,seed=()):
  self.root=Path(root);self.path=self.root/'state'/'chats.sqlite';self.path.parent.mkdir(parents=True,exist_ok=True)
  self.lock=threading.RLock()
  with self.db() as db:
   db.executescript('CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY,title TEXT,created REAL,updated REAL); CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,chat TEXT,role TEXT,body TEXT,at REAL); CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY,body TEXT,at REAL); CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);')
   row=db.execute("SELECT value FROM meta WHERE key='active'").fetchone()
   if 'archived' not in [r[1] for r in db.execute('PRAGMA table_info(chats)')]:db.execute('ALTER TABLE chats ADD COLUMN archived INTEGER DEFAULT 0')
   self.active=row[0] if row else ''
   exists=db.execute('SELECT 1 FROM chats WHERE id=? AND archived=0',(self.active,)).fetchone()
   migrated=db.execute("SELECT value FROM meta WHERE key='legacy_migrated'").fetchone()
   total=db.execute('SELECT count(*) FROM messages').fetchone()[0]
   chats=db.execute('SELECT count(*) FROM chats').fetchone()[0]
  if not exists:
   self.active=self.create('Conversación anterior' if seed else 'Nuevo chat',initial=True)
  if seed and not migrated and not total and chats<=1:
   for row in seed:self.append(row.get('role','user'),row.get('text',''))
   with self.db() as db:db.execute("INSERT OR REPLACE INTO meta VALUES ('legacy_migrated','1')")
 @contextmanager
 def db(self):
  db=sqlite3.connect(self.path,timeout=5)
  try:
   db.row_factory=sqlite3.Row
   with db:yield db
  finally:db.close()
 def create(self,title='Nuevo chat',initial=False):
  cid=uuid.uuid4().hex;now=time.time()
  with self.lock,self.db() as db:
   db.execute('INSERT INTO chats(id,title,created,updated) VALUES (?,?,?,?)',(cid,str(title)[:100],now,now));self.active=cid
   db.execute("INSERT OR REPLACE INTO meta VALUES ('active',?)",(cid,))
   if not initial:db.execute("INSERT OR REPLACE INTO meta VALUES ('legacy_migrated','1')")
  return cid
 def select(self,cid):
  with self.lock,self.db() as db:
   if not db.execute('SELECT 1 FROM chats WHERE id=? AND archived=0',(cid,)).fetchone():raise ValueError('El chat ya no existe')
   self.active=cid;db.execute("INSERT OR REPLACE INTO meta VALUES ('active',?)",(cid,))
 def list(self,query=''):
  with self.db() as db:return [dict(r) for r in db.execute('SELECT * FROM chats WHERE archived=0 AND (title LIKE ? OR EXISTS (SELECT 1 FROM messages WHERE messages.chat=chats.id AND messages.body LIKE ?)) ORDER BY updated DESC LIMIT 200',('%'+str(query)+'%','%'+str(query)+'%'))]
 def history(self,limit=48,cid=None):
  with self.db() as db:rows=db.execute('SELECT role,body FROM messages WHERE chat=? ORDER BY id DESC LIMIT ?',(cid or self.active,min(100,max(1,int(limit))))).fetchall()
  return [{'role':r['role'],'text':r['body']} for r in reversed(rows)]
 def append(self,role,body,cid=None):
  if role not in ('user','assistant'):return
  cid=cid or self.active;now=time.time()
  with self.lock,self.db() as db:
   row=db.execute('SELECT title FROM chats WHERE id=?',(cid,)).fetchone()
   if not row:return
   db.execute('INSERT INTO messages(chat,role,body,at) VALUES (?,?,?,?)',(cid,role,str(body)[:16000],now))
   title=' '.join(str(body).split())[:60] if role=='user' and row['title']=='Nuevo chat' else row['title']
   db.execute('UPDATE chats SET title=?,updated=? WHERE id=?',(title,now,cid))
   db.execute('DELETE FROM messages WHERE chat=? AND id NOT IN (SELECT id FROM messages WHERE chat=? ORDER BY id DESC LIMIT 1000)',(cid,cid))
 def rename(self,cid,title):
  if not str(title).strip():raise ValueError('Escribe un nombre para el chat')
  with self.lock,self.db() as db:db.execute('UPDATE chats SET title=? WHERE id=?',(str(title).strip()[:100],cid))
 def clear(self,cid=None):
  cid=cid or self.active
  with self.lock,self.db() as db:
   db.execute('DELETE FROM messages WHERE chat=?',(cid,))
   db.execute("INSERT OR REPLACE INTO meta VALUES ('legacy_migrated','1')")
  # Remove this conversation's temporary continuity file, never source knowledge or saved memories.
  path=self.root/'state'/'chat_contexts'/cid/'state'/'conversation_context.json'
  path.unlink(missing_ok=True)
 def delete(self,cid):
  with self.lock,self.db() as db:db.execute('UPDATE chats SET archived=1 WHERE id=?',(cid,))
  if cid==self.active:
   rows=self.list();self.select(rows[0]['id']) if rows else self.create()
 def trash(self):
  with self.db() as db:return [dict(r) for r in db.execute('SELECT * FROM chats WHERE archived=1 ORDER BY updated DESC LIMIT 200')]
 def restore(self,cid):
  with self.lock,self.db() as db:db.execute('UPDATE chats SET archived=0 WHERE id=?',(cid,))
  self.select(cid);return True
 def remember(self,body):
  body=' '.join(str(body).split())[:1500]
  if not body:raise ValueError('El recuerdo está vacío')
  with self.lock,self.db() as db:
   if not db.execute('SELECT 1 FROM memories WHERE body=?',(body,)).fetchone():db.execute('INSERT INTO memories(body,at) VALUES (?,?)',(body,time.time()))
 def memories(self,query=''):
  with self.db() as db:return [dict(r) for r in db.execute('SELECT * FROM memories WHERE body LIKE ? ORDER BY at DESC LIMIT 30',('%'+str(query)+'%',))]
 def forget(self,mid):
  with self.lock,self.db() as db:db.execute('DELETE FROM memories WHERE id=?',(int(mid),))
 def related(self,query):
  terms=list(dict.fromkeys(re.findall(r'[^\W_]{4,}',str(query).casefold())))[:6]
  if not terms:return []
  sql=' OR '.join('lower(body) LIKE ?' for _ in terms)
  with self.db() as db:
   rows=db.execute('SELECT chat,role,body FROM messages WHERE chat IN (SELECT id FROM chats WHERE archived=0) AND chat!=? AND ('+sql+') ORDER BY id DESC LIMIT 6',[self.active]+['%'+t+'%' for t in terms]).fetchall()
  return [{'chat':r['chat'],'role':r['role'],'text':r['body'][:900]} for r in rows]
