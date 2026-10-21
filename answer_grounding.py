"""Conservative release-status grounding; no market data or execution side effects."""
import re
import unicodedata


def folded(value):
    text=unicodedata.normalize('NFKD',str(value or '').lower())
    return ''.join(c for c in text if not unicodedata.combining(c))


NEGATIVE=re.compile(r'\bno\s+(?:(?:se\s+)?ha\s+(?:sido\s+)?|esta\s+|se\s+)?(?:lanzad[oa]|estrenad[oa]|disponible)\b|'
    r'\b(?:aun|todavia)\s+no\s+(?:ha\s+salido|salio|se\s+ha\s+lanzado)\b',re.I)
CLAIM=re.compile(r'\b(?:acaba\s+de\s+lanzar|ya\s+(?:(?:se\s+)?ha\s+)?lanzad[oa]|'
    r'fue\s+lanzad[oa]|ha\s+sido\s+lanzad[oa]|ya\s+esta\s+disponible|ya\s+salio)\b',re.I)
STOP={'quien','quienes','como','cual','cuales','cuando','donde','para','segun','fuente','fuentes',
      'nuevo','nueva','nombre','protagonistas','lanzar','lanzado','lanzada','lanzamiento',
      'acaba','ahora','puedes','dime','sobre','ficha','titulo','llama','esta','disponible','anunciado'}


def tokens(value):
    return {word for word in re.findall(r'[a-z0-9]+',folded(value)) if len(word)>=4 and word not in STOP}


def release_constraint(question,rows):
    query=folded(question)
    if not re.search(r'lanz|estren|disponib|anunci|nuevo|nueva|salio',query):return None
    topic=tokens(question)
    if not topic:return None
    relevant=[]
    for row in rows or []:
        text=str(row.get('text') or row.get('body') or '')
        if len(topic & tokens(str(row.get('title') or '')+' '+text))<min(2,len(topic)):continue
        plain=folded(text)
        if NEGATIVE.search(plain) and re.search(r'\banunciad[oa]\b|\banuncio\b|\bprevist[oa]\b',plain):
            relevant.append(str(row.get('url') or ''))
    if not relevant:return None
    return {'kind':'release_not_confirmed','sources':relevant,
        'instruction':'La fuente dice: anunciado, NO lanzado. Corrige la premisa de salida y responde los nombres o detalles pedidos. '
            'No publiques una salida que la evidencia niega.'}


def neutral_question(question,constraint):
    if not constraint:return str(question)
    text=str(question);prefix,colon,tail=text.partition(':')
    if colon and CLAIM.search(folded(prefix)) and tail.strip():
        return 'Según las fuentes recibidas: '+tail.strip()
    return CLAIM.sub('anunció',text)


def _affirmative(text):
    plain=folded(text)
    for match in CLAIM.finditer(plain):
        preceding=plain[max(0,match.start()-45):match.start()]
        if not re.search(r'\b(?:no|nunca|sin)\b[^.!?;:]*$',preceding):return True
    return False


def enforce_release_constraint(answer,constraint):
    """Do not publish an affirmative release claim explicitly denied by evidence.

    Keep independent answer sentences (e.g. names) when possible. If none remain,
    say what the evidence supports, instead of inventing the missing answer.
    """
    if not constraint:return str(answer)
    text=str(answer).strip()
    if not _affirmative(text):
        if NEGATIVE.search(folded(text)):return text
        return 'La fuente lo presenta como anunciado; todavía no se ha lanzado.\n\n'+text
    keep=[]
    for sentence in re.split(r'(?<=[.!?])\s+|\n+',text):
        if not sentence.strip():continue
        if not _affirmative(sentence):keep.append(sentence);continue
        prefix,colon,tail=sentence.partition(':')
        if colon and _affirmative(prefix) and tail.strip() and not _affirmative(tail):
            keep.append(tail.strip())
    remainder=' '.join(keep).strip()
    intro='La fuente lo presenta como anunciado; todavía no se ha lanzado.'
    if not remainder:return intro+' No puedo respaldar el resto de esa respuesta con los datos disponibles.'
    return intro+'\n\n'+remainder
