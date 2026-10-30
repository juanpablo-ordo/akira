"""Credenciales canónicas de AKIRA V186.

Una sola fuente de verdad evita que una key antigua de V181/V184 pise la nueva.
Canónico: %LOCALAPPDATA%/Akira/AKIRA_SECRETS.json.
"""
from __future__ import annotations
import hashlib, json, os,base64,threading,uuid
from pathlib import Path

NAMES=("OPENAI_API_KEY","CUSTOM_AI_API_KEY","COINGLASS_API_KEY","YOUTUBE_API_KEY","YOUTUBE_COOKIES_FILE")
_WRITE_LOCK=threading.RLock()

def canonical_path():
    base=Path(os.getenv("LOCALAPPDATA", Path.home()/"AppData"/"Local"))
    return base/"Akira"/"AKIRA_SECRETS.json"

def _clean(name,value):
    v=str(value or "").replace("\ufeff","").replace("\u200b","").strip()
    if len(v)>=2 and v[0]==v[-1] and v[0] in ('"',"'"):
        v=v[1:-1].strip()
    low=v.lower()
    if name=="OPENAI_API_KEY" and low.startswith("bearer "): v=v[7:].strip()
    if name=="COINGLASS_API_KEY" and low.startswith("cg-api-key:"): v=v.split(":",1)[1].strip()
    if name=="YOUTUBE_API_KEY" and low.startswith("key="): v=v.split("=",1)[1].strip()
    if name in ('OPENAI_API_KEY','CUSTOM_AI_API_KEY','COINGLASS_API_KEY','YOUTUBE_API_KEY'): v="".join(v.split())
    # Nunca usar la representación enmascarada que muestra un dashboard.
    if "*" in v or "…" in v: return ""
    return v

def _read_checked(p):
    path=Path(p)
    if not path.exists():return {}
    row=json.loads(path.read_text(encoding='utf-8-sig'))
    if isinstance(row,dict) and '_format' in row and row['_format']!='AKIRA_DPAPI_1':raise ValueError('Formato de almacén no compatible; se conserva')
    if isinstance(row,dict) and row.get('_format')=='AKIRA_DPAPI_1':
        import win32crypt
        raw=win32crypt.CryptUnprotectData(base64.b64decode(row['protected'],validate=True),None,None,None,1)[1]
        row=json.loads(raw.decode('utf-8'))
    if not isinstance(row,dict):raise ValueError('Almacén de claves no válido')
    if '_deleted' in row and (not isinstance(row['_deleted'],list) or any(k not in NAMES for k in row['_deleted'])):raise ValueError('Índice de claves eliminadas no válido')
    return row

def _read(p):
    try:return _read_checked(p)
    except Exception:return {}

def credential_health():
    try:
        path=canonical_path();row=_read_checked(path)
        return {'state':'SAVED' if row else 'EMPTY','exists':path.exists(),'readable':True}
    except Exception as error:
        return {'state':'UNREADABLE','exists':True,'readable':False,'error':type(error).__name__,
                'detail':'No se pudo leer o descifrar el almacén. Se conserva el archivo y no se sobrescribe.'}

def _legacy_paths():
    out=[]
    for p in (Path.cwd()/"AKIRA_SECRETS.json", Path(__file__).resolve().parent/"AKIRA_SECRETS.json"):
        out.append(p)
    home=Path.home()
    for ver in ("Akira_V184","Akira_V183","Akira_V182","Akira_V181","Akira_V180"):
        out.append(Path(os.getenv("LOCALAPPDATA",home))/ver/"AKIRA_SECRETS.json")
    return out

def load_secrets():
    can=canonical_path()
    try:row=_read_checked(can)
    except Exception:return {}
    data={}
    deleted=set(row.get('_deleted') or [])
    for k in NAMES:
        v=_clean(k,row.get(k,""))
        if v and k not in deleted: data[k]=v
    # Migración sólo para valores que todavía no existen en el archivo canónico.
    if len(data)<len(NAMES):
        for p in _legacy_paths():
            old=_read(p)
            for k in NAMES:
                if k not in data and k not in deleted:
                    v=_clean(k,old.get(k,""))
                    if v: data[k]=v
    for k in NAMES:
        if k not in data and k not in deleted:
            v=_clean(k,os.getenv(k,""))
            if v: data[k]=v
    return data

def canonical_values():
    row=_read_checked(canonical_path());deleted=set(row.get('_deleted') or [])
    return {k:_clean(k,row[k]) for k in NAMES if k in row and k not in deleted and _clean(k,row[k])}

def save_secrets(values, merge=True):
    with _WRITE_LOCK:return _save_secrets(values,merge)


def _save_secrets(values, merge=True):
    path=canonical_path(); path.parent.mkdir(parents=True,exist_ok=True)
    try:previous=_read_checked(path)
    except Exception as error:raise RuntimeError('El almacén guardado no se puede leer; se conserva sin sobrescribir. Revisa el perfil de Windows.') from error
    deleted=set(previous.get('_deleted') or [])
    data=load_secrets() if merge else {}
    if not merge:deleted.update(k for k in NAMES if k in previous and k not in (values or {}))
    for k,v in (values or {}).items():
        if k in NAMES:
            cleaned=_clean(k,v)
            if cleaned:data[k]=cleaned;deleted.discard(k)
            elif v=="":data.pop(k,None);deleted.add(k)
    if deleted:data['_deleted']=sorted(deleted)
    if os.name=='nt':
        import win32crypt
        blob=win32crypt.CryptProtectData(json.dumps(data).encode('utf-8'),'AKIRA',None,None,None,1)
        output={'_format':'AKIRA_DPAPI_1','protected':base64.b64encode(blob).decode('ascii')}
    else:output=data
    temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('x',encoding='utf-8') as stream:
            os.chmod(temp,0o600);stream.write(json.dumps(output,ensure_ascii=False,indent=2));stream.flush();os.fsync(stream.fileno())
        if _read(temp)!=data:raise RuntimeError('Windows no confirmó la lectura de las claves guardadas; revisa el perfil de usuario.')
        temp.replace(path)
    finally:temp.unlink(missing_ok=True)
    return path

def protect_existing():
    with _WRITE_LOCK:
        path=canonical_path()
        if os.name=='nt' and path.is_file():
            raw=json.loads(path.read_text(encoding='utf-8-sig'))
            if raw.get('_format')!='AKIRA_DPAPI_1':save_secrets(load_secrets())

def get_secret(name,default=""):
    return str(load_secrets().get(name,default) or default).strip()

def secret_source(name):
    row=_read(canonical_path())
    if name in (row.get('_deleted') or []):return 'eliminada por el usuario'
    v=_clean(name,row.get(name,""))
    if v: return f"canónico:{canonical_path()}"
    for p in _legacy_paths():
        if _clean(name,_read(p).get(name,"")): return f"migrada:{p}"
    if _clean(name,os.getenv(name,"")): return "entorno Windows"
    return "no configurada"

def secret_fingerprint(name):
    v=get_secret(name)
    return hashlib.sha256(v.encode()).hexdigest()[:10] if v else "-"

def secret_shape(name):
    v=get_secret(name)
    if not v: return "SIN CLAVE"
    if name=="OPENAI_API_KEY" and not v.startswith("sk-"): return "FORMATO OPENAI SOSPECHOSO"
    if name=="YOUTUBE_API_KEY" and not v.startswith("AIza"): return "FORMATO YOUTUBE SOSPECHOSO"
    return "OK"

def status():
    return {"openai":bool(get_secret("OPENAI_API_KEY")),"coinglass":bool(get_secret("COINGLASS_API_KEY")),"youtube":bool(get_secret("YOUTUBE_API_KEY"))}
