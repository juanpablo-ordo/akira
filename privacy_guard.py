"""PIN-gated display and shared redaction for AKIRA records and exports."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class PrivacyPin:
    def __init__(self, path, clock=time.time):
        self.path=Path(path)
        self.clock=clock

    def configured(self):
        return self.path.is_file()

    @staticmethod
    def verifier(pin,salt):
        return hashlib.scrypt(pin.encode('utf-8'),salt=salt,n=2**15,r=8,p=1,
                              maxmem=64*1024**2,dklen=32)

    def write(self,row):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp')
        with temp.open('w',encoding='utf-8') as stream:
            json.dump(row,stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp,self.path)

    def set_pin(self,pin,confirmation,*,windows_verified=False):
        if self.configured() and not windows_verified:
            raise PermissionError('Windows debe verificar tu identidad para restablecer el PIN.')
        if not re.fullmatch(r'[0-9]{6,12}',pin) or pin!=confirmation:
            raise ValueError('El PIN debe tener entre 6 y 12 dígitos y coincidir con la confirmación.')
        salt=secrets.token_bytes(24)
        self.write({'format':1,'salt':base64.b64encode(salt).decode('ascii'),
                    'verifier':self.verifier(pin,salt).hex(),'failures':0,'retry_after':0})

    def verify(self,pin):
        row=json.loads(self.path.read_text(encoding='utf-8'))
        if row.get('format')!=1:
            raise ValueError('El formato del PIN guardado es incompatible.')
        now=self.clock()
        if row['retry_after']>now:
            raise PermissionError(f"Intenta en {math.ceil(row['retry_after']-now)} segundos.")
        salt=base64.b64decode(row['salt'],validate=True)
        result=self.verifier(pin,salt).hex() if re.fullmatch(r'[0-9]{6,12}',pin) else ''
        if hmac.compare_digest(result,row['verifier']):
            if row['failures']:self.write({**row,'failures':0,'retry_after':0})
            return True
        failures=min(20,row['failures']+1)
        delay=0 if failures<3 else min(3600,2**failures)
        self.write({**row,'failures':failures,'retry_after':now+delay})
        return False


_SECRET_FIELD=re.compile(r'password|secret|api.?key|access.?token|authorization|credential|cookie',re.I)
_ACCOUNT_FIELD={'login','server','company','expected_login','expected_server','account_login',
                'account_number','broker_server','terminal_path','python_executable','application_root',
                'account_identity','authorized_identity'}
_AMOUNT_FIELD=re.compile(r'(^|_)(balance|equity|profit|commission|swap|margin|pnl|patrimonio|net|usd|money)(_|$)',re.I)
_PATH=re.compile(r"""(?i)(?<![\w:/])[a-z]:[\\/][^"<>\r\n;,·|]{1,240}""")
_URL=re.compile(r'https?://[^\s<>\]\)]+',re.I)
_TOKEN=re.compile(r'(?i)\b(?:bearer\s+|sk-(?:proj-)?|cg-api-key\s*[:=]\s*)[a-z0-9_.-]{8,}')


def redacted_record(value, account=None, *, hide_amounts=False, reveal_account=False):
    account=account or {}
    identifiers={str(v) for k,v in account.items() if k in _ACCOUNT_FIELD and v and len(str(v))>=4}
    identifiers=sorted(identifiers,key=len,reverse=True)

    def safe_url(match):
        parts=urlsplit(match[0])
        if not parts.hostname:return 'URL privada'
        if parts.hostname in ('www.youtube.com','youtube.com') and parts.path=='/watch':
            from urllib.parse import parse_qs
            video=parse_qs(parts.query).get('v',[''])[0]
            if re.fullmatch('[A-Za-z0-9_-]{11}',video):
                return 'https://youtu.be/'+video
        return urlunsplit((parts.scheme,parts.hostname,parts.path,'',''))

    def walk(item):
        if isinstance(item,dict):
            return {str(key):walk(child) for key,child in item.items()
                    if not _SECRET_FIELD.search(str(key))
                    and (reveal_account or str(key).lower() not in _ACCOUNT_FIELD)
                    and (not hide_amounts or not _AMOUNT_FIELD.search(str(key)))}
        if isinstance(item,(tuple,list)):
            return [walk(child) for child in item]
        if isinstance(item,str):
            item=_TOKEN.sub('[privado]',item)
            item=_PATH.sub('[ruta privada]',item)
            try:item=_URL.sub(safe_url,item)
            except ValueError:item=_URL.sub('[URL privada]',item)
            if not reveal_account:
                for identifier in identifiers:
                    item=re.sub(r'(?<!\w)'+re.escape(identifier)+r'(?!\w)','[cuenta privada]',item,flags=re.I)
            return item
        if isinstance(item,float) and not math.isfinite(item):return None
        if item is None or isinstance(item,(int,float,bool)):return item
        return walk(str(item))

    return walk(value)


def windows_identity_verified(hwnd):
    if os.name!='nt' or not getattr(sys,'frozen',False):
        return False
    from ctypes import WinDLL, c_int, c_void_p
    library=Path(sys._MEIPASS)/'akira_windows_hello.dll'
    if not library.is_file():
        return False
    verify=WinDLL(str(library)).AkiraVerifyIdentity
    verify.argtypes=[c_void_p]
    verify.restype=c_int
    return verify(hwnd)==1
