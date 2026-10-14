"""Only obsolete recoverable source content and inactive download temporaries."""
from pathlib import Path
import time,sqlite3

def candidates(root,days=14,clock=time.time):
    root=Path(root).resolve();cutoff=clock()-max(1,float(days))*86400;files=[]
    for folder in ('state/research_cache','state/http_cache','state/voice_models','state/voices'):
        parent=root/folder
        if parent.is_symlink():continue
        for path in parent.rglob('*') if parent.exists() else ():
            if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:continue
            if folder.endswith(('voice_models','voices')) and path.suffix not in ('.part','.tmp'):continue
            if path.stat().st_mtime<cutoff:files.append((str(path),path.stat().st_size,path.stat().st_mtime_ns))
    database=root/'state/knowledge.sqlite3';rows=[]
    if database.is_file():
        db=sqlite3.connect(database,timeout=2)
        try:rows=db.execute("SELECT url,fetched,length(CAST(body AS BLOB))+length(CAST(summary AS BLOB)) FROM sources WHERE kind IN ('web','research','news','search') AND fetched<?",(cutoff,)).fetchall()
        finally:db.close()
    return {'files':files,'sources':rows,'bytes':sum(p[1] for p in files)+sum(r[2] or 0 for r in rows),'days':days,'database':str(database),'scope':'Contenido web obsoleto y temporales inactivos. Conserva chats, recuerdos, credenciales, informes, historial y diario de trading. El espacio físico SQLite puede reutilizarse sin reducir el archivo.'}

def clean(root,preview):
    current=candidates(root,preview['days']);approved={(p[0],p[2]) for p in preview['files']};released=0;removed=0
    for path,size,mtime in current['files']:
        if (path,mtime) not in approved:continue
        p=Path(path)
        if p.is_symlink() or p.stat().st_mtime_ns!=mtime:continue
        p.unlink();released+=size;removed+=1
    count=0;approved_rows={(r[0],r[1]) for r in preview['sources']}
    if current['sources']:
        db=sqlite3.connect(current['database'],timeout=2)
        try:
            with db:
                for url,fetched,size in current['sources']:
                    if (url,fetched) in approved_rows:
                        count+=db.execute("DELETE FROM sources WHERE url=? AND fetched=? AND kind IN ('web','research','news','search')",(url,fetched)).rowcount
        finally:db.close()
    return {'files_removed':removed,'source_rows_removed':count,'file_bytes_released':released,'scope':preview['scope']}
