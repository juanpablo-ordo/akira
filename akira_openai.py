"""Cliente OpenAI compartido por AKIRA V193.

- Serializa llamadas de IA para no competir por CPU/red.
- Respeta Retry-After.
- Si una key recibe 401, la deshabilita temporalmente para que el chat caiga a
  Ollama de inmediato en lugar de repetir el mismo error en cada mensaje.
- La IA nunca está en la ruta crítica de order_send.
"""
from __future__ import annotations
import hashlib, json, random, threading, time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

_LOCK=threading.Lock()
_BACKGROUND_LOCK=threading.Lock()
_LAST_CALL=0.0
_BAD_KEY_UNTIL=0.0
_BAD_KEY_FP=""
_BAD_KEY_DETAIL=""
_QUOTA_UNTIL=0.0
_QUOTA_FP=""
_QUOTA_DETAIL=""


def _fp(key: str) -> str:
    return hashlib.sha256((key or "").encode()).hexdigest()[:10] if key else ""


def _error_detail(exc: HTTPError):
    try:
        raw=exc.read(300_000).decode("utf-8","replace")
        data=json.loads(raw) if raw else {}
        err=(data.get("error") or {}) if isinstance(data,dict) else {}
        return str(err.get("message") or raw or exc), str(err.get("code") or ""), str(err.get("type") or "")
    except Exception:
        return str(exc),"",""


def auth_status(key, timeout=8):
    """Valida autenticación sin consumir una respuesta de modelo."""
    if not key:
        return {"ok":False,"status":0,"detail":"falta OPENAI_API_KEY"}
    req=Request("https://api.openai.com/v1/models",
                headers={"Authorization":"Bearer "+key,"User-Agent":"AkiraV193Auth/1.0"},
                method="GET")
    try:
        with urlopen(req,timeout=timeout) as response:
            response.read(200_000)
        return {"ok":True,"status":200,"detail":"autenticación aceptada"}
    except HTTPError as exc:
        detail,code,etype=_error_detail(exc)
        return {"ok":False,"status":exc.code,"detail":detail[:500],"code":code,"type":etype}
    except Exception as exc:
        return {"ok":False,"status":0,"detail":f"{type(exc).__name__}: {exc}"}


def responses(payload,key,timeout=65,attempts=3,min_interval=1.25,user_agent="AkiraV193/1.0",lock_timeout=None,background=False):
    global _LAST_CALL,_BAD_KEY_UNTIL,_BAD_KEY_FP,_BAD_KEY_DETAIL,_QUOTA_UNTIL,_QUOTA_FP,_QUOTA_DETAIL
    if not key:
        raise RuntimeError("falta OPENAI_API_KEY")
    fp=_fp(key); now=time.monotonic()
    if _BAD_KEY_FP==fp and now<_BAD_KEY_UNTIL:
        left=max(1,int(_BAD_KEY_UNTIL-now))
        raise RuntimeError(f"OpenAI 401 cacheado ({left}s): {_BAD_KEY_DETAIL or 'la clave fue rechazada'}")
    if _QUOTA_FP==fp and now<_QUOTA_UNTIL:
        raise RuntimeError(f"OpenAI sin saldo/cuota API ({int(_QUOTA_UNTIL-now)}s); usando IA local. {_QUOTA_DETAIL}")
    # Si el usuario cambió la key, se limpia el bloqueo inmediatamente.
    if _BAD_KEY_FP and _BAD_KEY_FP!=fp:
        _BAD_KEY_FP=""; _BAD_KEY_UNTIL=0.0; _BAD_KEY_DETAIL=""
    if _QUOTA_FP and _QUOTA_FP!=fp:
        _QUOTA_FP=""; _QUOTA_UNTIL=0.0; _QUOTA_DETAIL=""
    attempts=max(1,min(int(attempts),4))
    # A long transcript/web request cannot occupy the interactive chat lock.
    # At most one background and one chat request run concurrently. Shared quota
    # rejection/backoff still applies to both, and background yields to active chat.
    if background and _LOCK.locked():raise RuntimeError('Chat activo; investigación aplazada')
    call_lock=_BACKGROUND_LOCK if background else _LOCK
    acquired=call_lock.acquire() if lock_timeout is None else call_lock.acquire(timeout=max(0.0,float(lock_timeout)))
    if not acquired:
        raise RuntimeError("OpenAI ocupado por investigación; usar IA local sin esperar")
    try:
            wait=max(0.0,float(min_interval)-(time.monotonic()-_LAST_CALL))
            if wait: time.sleep(wait)
            last=None
            for attempt in range(attempts):
                req=Request("https://api.openai.com/v1/responses",
                            data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
                            headers={"Authorization":"Bearer "+key,"Content-Type":"application/json","User-Agent":user_agent},
                            method="POST")
                try:
                    with urlopen(req,timeout=timeout) as response:
                        raw=response.read(8_000_001)
                        _LAST_CALL=time.monotonic()
                        if len(raw)>8_000_000: raise RuntimeError("respuesta IA demasiado grande")
                        return json.loads(raw)
                except HTTPError as exc:
                    _LAST_CALL=time.monotonic(); last=exc
                    detail,code,etype=_error_detail(exc)
                    low=(detail+" "+code+" "+etype).lower()
                    if exc.code==401:
                        _BAD_KEY_FP=fp; _BAD_KEY_UNTIL=time.monotonic()+300.0; _BAD_KEY_DETAIL=detail[:260]
                        raise RuntimeError("OpenAI HTTP 401: la clave exacta enviada fue rechazada. Akira usará Ollama local; revisa la huella/canonical secret y reemplaza la key si hace falta.")
                    if exc.code!=429:
                        raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail[:500]}")
                    quota_terms=("credit_balance_exhausted","insufficient_quota","spend_limit","usage_limit_exceeded")
                    if any(x in low for x in quota_terms):
                        tag=code or etype or "quota"
                        _QUOTA_FP=fp; _QUOTA_UNTIL=time.monotonic()+300.0; _QUOTA_DETAIL=detail[:180]
                        raise RuntimeError(f"OpenAI 429 [{tag}] por saldo/cuota/límite de gasto. Revisa Billing/Limits del proyecto API; reintentar no lo corrige.")
                    if attempt+1>=attempts:
                        raise RuntimeError("OpenAI 429 por límite temporal de solicitudes/tokens. Akira redujo la frecuencia; espera unos segundos y vuelve a intentar.")
                    retry=exc.headers.get("Retry-After") if getattr(exc,"headers",None) else None
                    try: delay=max(.5,min(12.0,float(retry))) if retry else min(8.0,1.2*(2**attempt)+random.random()*.6)
                    except Exception: delay=min(8.0,1.2*(2**attempt)+random.random()*.6)
                    time.sleep(delay)
            raise RuntimeError(str(last) if last else "OpenAI no respondió")
    finally:
        call_lock.release()
