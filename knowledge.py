"""Persistent, attributed research. Public text is data, never instructions."""
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
from html import unescape
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
import sqlite3
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler,HTTPSHandler


class KnowledgeStore:
    def __init__(self,root):
        self.path=Path(root)/'state'/'knowledge.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS sources (url TEXT PRIMARY KEY,title TEXT,topic TEXT,kind TEXT,published TEXT,fetched REAL,digest TEXT,body TEXT,summary TEXT,status TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS conversation (id INTEGER PRIMARY KEY,at REAL,role TEXT,body TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS source_metadata(url TEXT PRIMARY KEY,body TEXT)')
            self._fts=False
            try:
                exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='source_index'").fetchone()
                db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS source_index USING fts5(url UNINDEXED,title,topic,summary,body,tokenize='unicode61 remove_diacritics 2')")
                db.executescript('CREATE TRIGGER IF NOT EXISTS source_index_insert AFTER INSERT ON sources BEGIN DELETE FROM source_index WHERE url=NEW.url; INSERT INTO source_index VALUES (NEW.url,NEW.title,NEW.topic,NEW.summary,NEW.body); END; CREATE TRIGGER IF NOT EXISTS source_index_delete AFTER DELETE ON sources BEGIN DELETE FROM source_index WHERE url=OLD.url; END;')
                if not exists:db.execute('INSERT INTO source_index SELECT url,title,topic,summary,body FROM sources')
                self._fts=True
            except sqlite3.OperationalError:pass

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=3)
        db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def put(self,row):
        body=str(row.get('body',''))[:240000]
        digest=hashlib.sha256(body.encode()).hexdigest()
        values=(str(row['url']),str(row.get('title',''))[:600],str(row.get('topic',''))[:160],
                str(row.get('kind','web')),str(row.get('published','')),float(row.get('fetched',time.time())),
                digest,body,str(row.get('summary',''))[:18000],str(row.get('status','read')))
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?,?,?,?,?)',values)
            metadata={k:row[k] for k in ('author','complete','caption_type','language','evidence_origin','resolved_url') if k in row}
            db.execute('INSERT OR REPLACE INTO source_metadata VALUES (?,?)',(str(row['url']),json.dumps(metadata,ensure_ascii=False)))
        return digest

    def get(self,url):
        with self.db() as db:
            row=db.execute('SELECT * FROM sources WHERE url=?',(url,)).fetchone()
            metadata=db.execute('SELECT body FROM source_metadata WHERE url=?',(url,)).fetchone()
        if not row:return None
        result=dict(row)
        try:result['complete']=json.loads(result.get('summary') or '{}').get('source_complete',False) is True
        except (TypeError,ValueError):result['complete']=False
        if metadata:result.update(json.loads(metadata[0]))
        return result

    def search(self,query,limit=6):
        terms=list(dict.fromkeys(re.findall(r'[^\W_]{3,}',str(query).lower())))[:12]
        if not terms:return []
        if self._fts:
            query=' OR '.join('"'+term+'"' for term in terms)
            try:
                with self.db() as db:
                    rows=db.execute('SELECT s.*,snippet(source_index,4,"",""," … ",48) AS passage FROM source_index JOIN sources s ON s.url=source_index.url WHERE source_index MATCH ? ORDER BY bm25(source_index,0,8,5,3,1) LIMIT ?',(query,max(1,min(int(limit),10)))).fetchall()
                return [{**{k:r[k] for k in ('url','title','topic','kind','published','fetched','summary','status')},'retrieved_passage':r['passage'],'retrieval':'índice BM25 de texto completo'} for r in rows]
            except sqlite3.OperationalError:pass
        # Bound both retrieval and context; never send the entire database to GPT.
        where=' OR '.join('lower(title||" "||topic||" "||summary||" "||substr(body,1,40000)) LIKE ?' for _ in terms)
        with self.db() as db:
            rows=db.execute('SELECT * FROM sources WHERE '+where+' ORDER BY fetched DESC LIMIT 60',
                            ['%'+t+'%' for t in terms]).fetchall()
        ranked=sorted(rows,key=lambda r:sum(t in (r['title']+' '+r['topic']+' '+r['summary']+' '+r['body'][:40000]).lower() for t in terms),reverse=True)
        return [{k:r[k] for k in ('url','title','topic','kind','published','fetched','summary','status')}
                for r in ranked[:max(1,min(int(limit),10))]]

    def stats(self):
        with self.db() as db:
            n=db.execute('SELECT count(*) FROM sources').fetchone()[0]
            analyzed=db.execute("SELECT count(*) FROM sources WHERE status='analyzed'").fetchone()[0]
        return {'sources':n,'analyzed':analyzed,'storage':'memoria local con fuentes y fechas'}

    def remember(self,role,body):
        with self.db() as db:
            db.execute('INSERT INTO conversation(at,role,body) VALUES (?,?,?)',(time.time(),role,str(body)[:16000]))
            db.execute('DELETE FROM conversation WHERE id NOT IN (SELECT id FROM conversation ORDER BY id DESC LIMIT 100)')

    def history(self,limit=24):
        with self.db() as db:
            rows=db.execute('SELECT role,body FROM conversation ORDER BY id DESC LIMIT ?',(int(limit),)).fetchall()
        return [{'role':r['role'],'text':r['body']} for r in reversed(rows)]


def public_url(url):
    parts=urlsplit(str(url))
    if parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password:
        raise ValueError('Solo URLs públicas HTTP/HTTPS sin credenciales')
    if parts.port and parts.port not in (80,443):raise ValueError('Puerto no público')
    try: addresses=socket.getaddrinfo(parts.hostname,parts.port or (443 if parts.scheme=='https' else 80),type=socket.SOCK_STREAM)
    except OSError as exc:raise ValueError('No se pudo resolver la fuente pública') from exc
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise ValueError('No se permite acceder a direcciones locales o privadas')
    return str(url)


class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        public_url(newurl)
        if urlsplit(req.full_url).scheme=='https' and urlsplit(newurl).scheme!='https':
            raise ValueError('La fuente intentó abandonar la conexión HTTPS segura')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def public_opener(cookiejar=None):
    from network_tls import https_context
    from urllib.request import HTTPCookieProcessor
    handlers=[PublicRedirect(),HTTPSHandler(context=https_context())]
    if cookiejar is not None:handlers.append(HTTPCookieProcessor(cookiejar))
    return build_opener(*handlers)


def read_public(url,timeout=10,max_bytes=1500000,headers=None,cookiejar=None):
    url=public_url(url)
    safe_headers={'User-Agent':'AkiraResearch/2.0','Accept':'text/html,application/json,text/plain,text/vtt'}
    safe_headers.update({k:v for k,v in (headers or {}).items() if k.lower() in ('user-agent','accept-language','referer')})
    req=Request(url,headers=safe_headers)
    with public_opener(cookiejar).open(req,timeout=timeout) as res:
        kind=str(res.headers.get('Content-Type','')).lower()
        if kind and not any(t in kind for t in ('text/','json','xml')):
            raise ValueError('La fuente no ofrece texto público legible')
        data=res.read(max_bytes+1)
        if len(data)>max_bytes:raise ValueError('Texto de fuente demasiado grande')
        final=public_url(res.geturl())
        charset=res.headers.get_content_charset() or 'utf-8'
    return data.decode(charset,'replace'),final


class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip=0; self.parts=[]; self.title=[]; self.in_title=False
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','nav','footer','noscript','svg'):self.skip+=1
        if tag=='title':self.in_title=True
    def handle_endtag(self,tag):
        if tag in ('script','style','nav','footer','noscript','svg'):self.skip=max(0,self.skip-1)
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if self.in_title:self.title.append(data)
        if not self.skip and data.strip():self.parts.append(data.strip())


def read_web(url):
    raw,final=read_public(url)
    parser=TextHTML(); parser.feed(raw)
    body='\n'.join(parser.parts) if '<html' in raw.lower() or '<body' in raw.lower() else raw
    return {'url':final,'title':' '.join(parser.title) or urlsplit(final).hostname,'body':body[:120000],
            'kind':'web','fetched':time.time(),'status':'read','summary':body[:2500]}


def parse_captions(raw,ext):
    if ext=='json3':
        data=json.loads(raw)
        lines=[''.join(str(s.get('utf8','')) for s in e.get('segs',[])).strip() for e in data.get('events',[])]
    else:
        lines=[]
        for line in raw.splitlines():
            line=line.strip()
            if not line or '-->' in line or line.isdigit() or line.startswith(('WEBVTT','Kind:','Language:','NOTE')):continue
            lines.append(re.sub(r'<[^>]+>','',line))
    out=[]
    for line in lines:
        line=' '.join(unescape(line).split())
        if line and (not out or line!=out[-1]):out.append(line)
    return '\n'.join(out)


def read_youtube(url,extractor=None):
    parts=urlsplit(str(url)); host=(parts.hostname or '').lower()
    if host not in ('youtube.com','www.youtube.com','m.youtube.com','youtu.be'):
        raise ValueError('Usa una URL de vídeo de YouTube')
    cookiejar=None;headers={}
    if extractor is None:
        import yt_dlp
        from youtube_support import options, explained
        try:
            with yt_dlp.YoutubeDL(options()) as ydl:
                info=ydl.extract_info(url,download=False);cookiejar=ydl.cookiejar
                headers=info.get('http_headers') or {}
        except Exception as error:raise explained(error) from error
    else:info=extractor(url)
    tracks=info.get('subtitles') or {}; automatic=info.get('automatic_captions') or {}
    candidates=[]
    for source,name in ((tracks,'author_captions'),(automatic,'automatic_captions')):
        langs=sorted(source,key=lambda lang:(0 if lang.startswith('es') else 1 if lang.startswith('en') else 2,lang))
        for lang in langs:
            for track in sorted(source[lang],key=lambda x:0 if x.get('ext')=='json3' else 1):
                if track.get('ext') in ('json3','vtt','srt') and track.get('url'):
                    candidates.append((lang,name,track))
    row={'url':info.get('webpage_url') or url,'title':info.get('title') or url,'kind':'youtube',
         'published':info.get('upload_date') or '', 'fetched':time.time(), 'author':info.get('uploader','')}
    errors=[]
    for lang,name,track in candidates[:6]:
        try:
            raw,_=read_public(track['url'],headers=headers,cookiejar=cookiejar)
            body=parse_captions(raw,track['ext'])
            if len(body)<40:continue
            truncated=len(body)>160000
            row.update(body=body[:160000],status='transcript_partial' if truncated else 'transcript',
                       language=lang,caption_type=name,complete=not truncated,summary='')
            return row
        except Exception as exc:
            from youtube_support import classify_error,explained
            if classify_error(exc) in ('AUTH_REQUIRED','RATE_LIMITED','CERTIFICATE_ERROR'):raise explained(exc) from exc
            errors.append(exc)
    if errors:
        from youtube_support import explained
        raise explained(errors[0]) from errors[0]
    row.update(body='',summary='',status='captions_unavailable',complete=False,
               error='No hay subtítulos completos utilizables; el título no sustituye al vídeo')
    return row


def transcript_chunks(text,size=11000):
    lines=str(text).splitlines(); chunks=[]; current=''
    for line in lines:
        if len(current)+len(line)>size and current:chunks.append(current); current=''
        # Captions can be one long line; cover every byte once, without truncation.
        while len(line)>size:
            if current:chunks.append(current);current=''
            chunks.append(line[:size]);line=line[size:]
        current+=(('\n' if current else '')+line)
    if current:chunks.append(current)
    return chunks
