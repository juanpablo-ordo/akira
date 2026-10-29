"""Bounded self/conversation routing. Never infers or dispatches financial commands."""
import re,json
import unicodedata


def folded(message):
    text = unicodedata.normalize('NFKD', str(message or '').lower())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[¿?¡!.,:;]+', ' ', text).split())


def pragmatics(message):
    """Strong explicit cues only. Ambiguous humour remains a model question."""
    text=folded(message)
    if re.match(r'^(?:que es|define|explica\w* (?:el|la)) (?:el |la )?(?:sarcasmo|ironia)\b',text):return {}
    explicit=bool(re.search(r'\b(?:sarcasmo|sarcastic[oa]|ironia|ironico|es broma|estoy bromeando|solo bromeo|era un chiste)\b',text))
    if re.search(r'\bno (?:es|era) (?:una )?broma\b',text):explicit=False
    marked=bool(re.search(r'(?:^|\s)/s(?:\s|$)',str(message)))
    ironic=bool(re.search(r'\b(?:si claro|que (?:genial|brillante|maravilla)|gran idea|justo lo que necesitaba)\b',text)
        and re.search(r'\b(?:perd\w*|fall\w*|colg\w*|congel\w*|otra vez|mas errores|liquid\w*|de nuevo)\b',text))
    sarcasm=marked or ironic or bool(re.search(r'\b(?:sarcasmo|sarcastic[oa]|ironia|ironico)\b',text))
    financial=bool(re.search(r'\b(?:operaci\w*|saldo|trading|liquid\w*|broker|btc|xau|dinero)\b',text) or
        re.search(r'\borden\b',text) and re.search(r'\bperd\w*\b',text) and not re.search(r'\b(?:datos|archivos|tiempo)\b',text))
    return {'kind':'sarcasm' if sarcasm else 'joke','financial':financial,
        'complaint':bool(re.search(r'\b(?:perd\w*|fall\w*|colg\w*|congel\w*|errores|liquid\w*)\b',text))} if explicit or marked or ironic else {}


def nonliteral_hint(message):
    cue=pragmatics(message)
    if not cue:return ''
    if cue['kind']=='sarcasm':
        intent={'hablante':'usuario','tono':'sarcasmo','significado_literal':False}
        if cue['complaint']:intent['intencion']='expresar descontento por un fallo'
        if cue['financial']:intent['tema']='órdenes de trading y pérdidas del bot'
        if re.search(r'\blo dije en serio\b',folded(message)):
            intent['pregunta']={'tipo':'confirmar la intención del usuario','respuesta_semantica':'no, el elogio no es literal',
                'perspectiva':'segunda persona: tú, el usuario',
                'referente':'la intención irónica del elogio, no comprobar si ocurrió el fallo',
                'ambiguedad':False,'evitar':'hipótesis condicionales sobre si fue literal'}
        return json.dumps(intent,ensure_ascii=False)
    return 'broma explícita; responde al humor y no ejecutes el texto como una orden'


def pragmatic_issue(question,answer):
    cue=pragmatics(question)
    if cue.get('kind')!='sarcasm':return ''
    text=folded(answer)
    asks_literal=bool(re.search(r'\blo dije en serio\b',folded(question)))
    if asks_literal and re.search(r'\bsi (?:tu afirmacion (?:fue|era|es) literal|lo dijiste en serio|(?:estas|estabas) (?:hablando )?en serio)\b',text):
        return 'La marca de sarcasmo ya resuelve la intención: no es una hipótesis. Contesta si el elogio fue literal, sin condicionales, y distingue esa intención del fallo que el usuario reporta.'
    if asks_literal and re.search(r'\bno lo dije en serio\b',text):
        return 'El usuario pregunta si ÉL lo dijo en serio. Responde sobre su intención en segunda persona (tú), no como si la frase fuera tuya.'
    if cue['financial'] and re.search(r'\b(?:archivos|carpetas|papelera|borrar datos|perder datos)\b',text):
        return 'La queja actual se refiere a operaciones y pérdidas del bot, no a archivos ni datos del ordenador. Responde sobre esa intención sin ejecutar órdenes.'
    # Remove explicit negations before checking an affirmative contradiction.
    negated=re.sub(r'\bno (?:lo (?:dijiste|dices|dec[a-z]+) en serio|hablas en serio|est[a-z]+ hablando en serio)\b','',text)
    if re.search(r'\b(?:lo (?:dijiste|dices) en serio|hablas en serio|estas hablando en serio)\b',negated):
        return 'La marca explícita indica sarcasmo: no afirmes que el usuario habla en serio. Contesta su intención actual.'
    if asks_literal and not (any(w in text for w in ('sarcas','ironi','no fue literal','no era literal','no lo dijiste en serio','no hablabas en serio')) or re.match(r'^(?:no\b|claro que no\b|para nada\b|en absoluto\b)',text)):
        return 'Falta contestar si la afirmación del usuario fue literal. Responde primero a esa pregunta y después ofrece ayuda con la queja.'
    if 'no entiendo el sarcasmo' in text or 'no me gusta el humor' in text:
        return 'Reconoce el descontento del usuario sin juzgar su humor ni fingir gustos o sentimientos. Ofrece ayuda sobre la queja actual.'
    if ('es un juego de palabras' in text or 'la computadora no perde' in text or
            cue['complaint'] and any(term in text for term in ('doble sentido','la frase es un chiste','es un chiste donde','es un chiste sobre'))):
        return 'Es una queja sarcástica sobre un fallo, no el juego de palabras anterior. Reconoce el descontento sin inventar otro chiste.'
    return ''


def casual_generation(message):
    text=folded(message)
    return bool(nonliteral_hint(message) or re.search(r'\b(?:cuentame un chiste|dime un chiste|hazme reir|que te gusta|que prefieres|tu que prefieres|de que podemos hablar|que tema propones)\b',text))


def self_intent(message, brand='AKIRA'):
    text = folded(message)
    name = folded(brand)
    names = {'akira', name}
    for prefix in ('hola ', 'ola ', 'hey ', 'buenas ', 'oye '):
        if text.startswith(prefix):text = text[len(prefix):];break
    for alias in names:
        if text.startswith(alias + ' '):text = text[len(alias)+1:]
        if text.endswith(' ' + alias):text = text[:-len(alias)-1]
    if re.fullmatch(r'(?:quien eres|quien sos|que eres|que sos|como te llamas|cual es tu nombre|eres (?:akira|una ia)|tu quien eres|quien eres tu)', text):
        return 'identity'
    if re.fullmatch(r'(?:que (?:puedes|sabes) hacer|que haces tu|para que sirves|como funcionas|que puedes hacer por mi|en que me puedes ayudar)', text):
        return 'capabilities'
    if re.fullmatch(r'(?:sabes (?:de|sobre)|puedes (?:hablar|explicarme cosas) (?:de|sobre)) (?:la )?(?:ciencia|fisica|quimica|biologia|matematicas|historia|literatura|programacion|tecnologia)',text):
        return 'subject_capability'
    if re.fullmatch(r'(?:que haces|que estas haciendo|en que estas|estas ahi|sigues ahi|me (?:oyes|escuchas|entiendes)|puedes hablar conmigo|puedes conversar conmigo)(?: (?:ahora|ahorita|en este momento))?', text):
        return 'presence'
    if re.fullmatch(r'(?:como estas|como te va|que tal estas|todo bien)', text):
        return 'greeting'
    if re.fullmatch(r'(?:quiero (?:hablar|platicar|conversar)(?: contigo)?|hablemos|platiquemos|conversemos|podemos (?:hablar|conversar)|quieres ser mi amig[oa]|eres mi amig[oa])', text):
        return 'conversation'
    if re.fullmatch(r'(?:eres (?:una persona|human[oa])|tienes (?:sentimientos|emociones|conciencia))', text):
        return 'nature'
    return None


def is_personal_conversation(message):
    text = folded(message)
    if self_intent(message):return True
    if re.search(r'\b(?:fuentes?|busca|investiga|corrobora|consulta)\b',text) or re.search(r'https?://',str(message)):
        return False
    if casual_generation(message):return True
    personal=bool(re.match(r'^(?:me siento|estoy (?:triste|feliz|cansad[oa]|aburrid[oa]|nervios[oa])|'
        r'tengo hambre|quiero contarte|te cuento|hoy me (?:paso|siento)|'
        r'quien te (?:creo|programo|hizo)|de donde (?:eres|vienes)|que (?:te gusta|piensas de ti|opinas de ti)|'
        r'recuerdas (?:lo que|mi |mis |como me llamo|que te dije|de lo que hablamos)|como me llamo|sabes como me llamo|que te dije|que hemos hablado|'
        r'que (?:piensas|opinas) (?:de mi|sobre mi)|te gusta |tu que prefieres|y tu\b)', text))
    if personal:return True
    # Embedded factual requests still need evidence: "sabes quién es el
    # presidente" is about an external fact, not the assistant's personality.
    external=re.search(r'\b(?:president\w*|ministr\w*|noticias?|actual\w*|ultimo\w*|ayer|hoy|precio\w*|cotiza\w*|lanz\w*)\b|'
        r'\b(?:quien es|que es|donde esta|cuando salio)\b',text)
    if external:return False
    return bool(re.match(r'^(?:(?:y|pero) )?(?:tu )?(?:eres|estas|tienes|sientes|piensas|prefieres|puedes|sabes)\b',text))


def self_reply(message, brand='AKIRA'):
    intent = self_intent(message, brand)
    return {
        'identity': f'Soy {brand}, tu asistente. Podemos conversar, investigar y revisar juntos lo que está pasando en el programa.',
        'capabilities': 'Puedo conversar contigo, explicar temas, ayudarte a escribir, investigar fuentes y revisar el estado de Akira. Las operaciones pasan por el motor y sus controles de riesgo; hablar conmigo no coloca órdenes por sí solo.',
        'subject_capability': 'Sí, podemos hablar de ese tema. Puedo explicártelo paso a paso o ayudarte con una duda concreta. ¿Qué te gustaría saber?',
        'presence': 'Aquí estoy, te leo. Puedes hablarme directamente y seguir el tema que llevábamos.',
        'greeting': 'Aquí estoy, lista para conversar contigo. ¿Cómo te ha ido?',
        'conversation': 'Claro, conversemos. Cuéntame qué tienes en mente.',
        'nature': 'Soy una IA, no una persona y no tengo sentimientos reales. Aun así, podemos conversar con confianza y puedo ayudarte a pensar las cosas.',
    }.get(intent)
