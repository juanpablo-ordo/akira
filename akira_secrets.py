"""Credenciales canónicas de AKIRA V186.

Una sola fuente de verdad evita que una key antigua de V181/V184 pise la nueva.
Canónico: %LOCALAPPDATA%/Akira/AKIRA_SECRETS.json.
"""
from __future__ import annotations
import hashlib, json, os,base64,threading,uuid
from pathlib import Path

NAMES=("OPENAI_API_KEY","COINGLASS_API_KEY","YOUTUBE_API_KEY","YOUTUBE_COOKIES_FILE")
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
    if name in ('OPENAI_API_KEY','COINGLASS_API_KEY','YOUTUBE_API_KEY'): v="".join(v.split())
    # Nunca usar la representación enmascarada que muestra un dashboard.
    if "*" in v or "…" in v: return ""
    return v

def _read(p):
    try:
        row=json.loads(Path(p).read_text(encoding="utf-8-sig"))
        if isinstance(row,dict) and row.get('_format')=='AKIRA_DPAPI_1':
            import win32crypt
            raw=win32crypt.CryptUnprotectData(base64.b64decode(row['protected']),None,None,None,1)[1]
            row=json.loads(raw.decode('utf-8'))
        return row if isinstance(row,dict) else {}
    except Exception: return {}

def _legacy_paths():
    out=[]
    for p in (Path.cwd()/"AKIRA_SECRETS.json", Path(__file__).resolve().parent/"AKIRA_SECRETS.json"):
        out.append(p)
    home=Path.home()
    for ver in ("Akira_V184","Akira_V183","Akira_V182","Akira_V181","Akira_V180"):
        out.append(Path(os.getenv("LOCALAPPDATA",home))/ver/"AKIRA_SECRETS.json")
    return out

def load_secrets():
    can=canonical_path(); row=_read(can); data={}
    for k in NAMES:
        v=_clean(k,row.get(k,""))
        if v: data[k]=v
    # Migración sólo para valores que todavía no existen en el archivo canónico.
    if len(data)<len(NAMES):
        for p in _legacy_paths():
            old=_read(p)
            for k in NAMES:
                if k not in data:
                    v=_clean(k,old.get(k,""))
                    if v: data[k]=v
    for k in NAMES:
        if k not in data:
            v=_clean(k,os.getenv(k,""))
            if v: data[k]=v
    return data

def save_secrets(values, merge=True):
    with _WRITE_LOCK:return _save_secrets(values,merge)


def _save_secrets(values, merge=True):
    path=canonical_path(); path.parent.mkdir(parents=True,exist_ok=True)
    data=load_secrets() if merge else {}
    for k,v in (values or {}).items():
        if k in NAMES:
            cleaned=_clean(k,v)
            if cleaned: data[k]=cleaned
            elif v=="": data.pop(k,None)
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
    v=_clean(name,_read(canonical_path()).get(name,""))
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
