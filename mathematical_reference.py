"""Small sourced glossary for symbols, not canned answers to QA questions.

Definitions: NIST DLMF 4.2 and 4.4. A local reference is not a live web lookup.
No claim of universal mathematical verification is made by this module.
"""
import json,re
from conversation_core import folded

SOURCE='https://dlmf.nist.gov/4.4'
GLOSSARY={
 'pi':{'symbols':['π','pi'],'value':'3.141592653589793...','definition':'Cociente entre la longitud de una circunferencia y su diámetro.'},
 'e':{'symbols':['e'],'value':'2.718281828459045...','definition':'Base de los logaritmos naturales; se conoce también como número de Euler.'},
 'i':{'symbols':['i'],'definition':'Unidad imaginaria: i al cuadrado vale -1.'},
}


def notes(question):
    text=folded(question)
    cue=bool(re.search(r'\b(?:matematic\w*|formul\w*|ecuacion\w*|trigonometr\w*|logaritm\w*|constante\w*|euler|imaginari\w*)\b|[=^]|[π√]',text))
    if not cue:return None
    original=str(question)
    # E in E=mc² and I as current are variables, not the constants e and i.
    if re.search(r'(?i)\be\s*=\s*m\s*\*?\s*c',original):return None
    selected=[key for key,row in GLOSSARY.items() if any(re.search(r'(?<!\w)'+re.escape(symbol)+r'(?!\w)',original,0 if symbol in ('e','i') else re.I) for symbol in row['symbols'])]
    if not selected and not re.search(r'[=^]',original) and re.search(r'\b(?:matematic\w*|euler|imaginari\w*)\b',text):selected=list(GLOSSARY)
    if not selected:return None
    # Nearby definitions avoid confusing e, pi and Euler's gamma in a single
    # explanation. The model still generates the actual requested answer.
    return {'source':SOURCE,'kind':'glosario local de referencia; no consulta web en vivo',
        'definitions':{k:GLOSSARY[k] for k in GLOSSARY},
        'instruction':'Usa estas definiciones al explicar esos símbolos. Corrige un error previo del hilo si contradice esta referencia.'}


def issue(answer):
    text=folded(answer);text=re.sub(r'[*_`$]','',text)
    if re.search(r'(?:π|\bpi\b)\s*\([^)]{0,40}(?:numero|constante)(?:\s+de)?\s+euler',text) or re.search(r'(?:π|\bpi\b)\s*(?:\([^)]{0,50}\))?\s*(?:es|:|=)\s*(?:(?:el|la|un|una)\s+)?(?:numero|constante)(?:\s+de)?\s+euler',text):
        return 'La definición de pi contradice la referencia: pi es circunferencia dividida entre diámetro; e es la base del logaritmo natural.'
    return ''
