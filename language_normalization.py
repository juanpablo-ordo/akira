"""Conservative Spanish input repair; numbers, URLs and order parameters stay exact."""
import re
import unicodedata

_WORDS={
    'presdiente':'presidente','presidete':'presidente','presindente':'presidente',
    'precidente':'presidente','predidente':'presidente',
    'guatemaala':'Guatemala','guatemla':'Guatemala','guatemal':'Guatemala',
    'acutal':'actual','actaul':'actual','actul':'actual','qien':'quien','qiuen':'quien',
    'interte':'internet','internte':'internet','intenet':'internet','interent':'internet',
    'enitende':'entiende','enitendes':'entiendes','entindes':'entiendes',
    'enitien':'entiende','pregutna':'pregunta','pregutno':'pregunto',
    'respueta':'respuesta','respondee':'responde','analsis':'análisis','anlisis':'análisis',
    'noticas':'noticias','noticicas':'noticias','ortografia':'ortografía',
    'funcona':'funciona','funcioan':'funciona','poneindo':'poniendo',
}
_WORDS.update({'esplicas':'explicas','esplicame':'explícame','diferncia':'diferencia','diferensia':'diferencia','memroia':'memoria','compuadora':'computadora','penditnes':'pendientes','runnners':'runners','ajutes':'ajustes'})
_PROTECTED=re.compile(r'```[\s\S]*?```|`[^`]*`|https?://\S+|[A-Za-z]:[\\/][^\n]+|\b(?:sk-|AIza)[\w-]+|\b[A-Za-z]+[A-Za-z_]*[0-9_][A-Za-z0-9_]*\b')
_TOKEN=re.compile(r'[^\W\d_]+',re.UNICODE)


def normalize_message(value):
    text=str(value or '');changes=[]
    def repair(part):
        def word(match):
            raw=match.group();key=unicodedata.normalize('NFC',raw).lower()
            corrected=_WORDS.get(key)
            if corrected is None:return raw
            # Identifiers/tickers and explicit uppercase protocol tokens are opaque.
            if raw.isupper() and len(raw)>2:return raw
            if raw.istitle():corrected=corrected[0].upper()+corrected[1:]
            if corrected!=raw:changes.append((raw,corrected))
            return corrected
        return _TOKEN.sub(word,part)
    parts=[];start=0
    for match in _PROTECTED.finditer(text):
        parts.extend((repair(text[start:match.start()]),match.group()));start=match.end()
    parts.append(repair(text[start:]))
    return ''.join(parts),tuple(changes)


def understood(value):
    return normalize_message(value)[0]
