"""Bounded self/conversation routing. Never infers or dispatches financial commands."""
import re
import unicodedata


def folded(message):
    text = unicodedata.normalize('NFKD', str(message or '').lower())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[¿?¡!.,:;]+', ' ', text).split())


def self_intent(message, brand='AKIRA'):
    text = folded(message)
    name = folded(brand)
    names = {'akira', name}
    for prefix in ('hola ', 'ola ', 'hey ', 'buenas ', 'oye '):
        if text.startswith(prefix):text = text[len(prefix):];break
    for alias in names:
        if text.startswith(alias + ' '):text = text[len(alias)+1:]
        if text.endswith(' ' + alias):text = text[:-len(alias)-1]
    if re.fullmatch(r'(?:quien eres|quien sos|como te llamas|cual es tu nombre|eres (?:akira|una ia)|tu quien eres|quien eres tu)', text):
        return 'identity'
    if re.fullmatch(r'(?:que (?:puedes|sabes) hacer|que haces tu|para que sirves|como funcionas|que puedes hacer por mi|en que me puedes ayudar)', text):
        return 'capabilities'
    if re.fullmatch(r'(?:que haces|que estas haciendo|en que estas|estas ahi|sigues ahi|me (?:oyes|escuchas|entiendes)|puedes hablar conmigo|puedes conversar conmigo)', text):
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
    # Do not send feelings, a personal account or a question to the assistant
    # itself into the short-entity web-search heuristic.
    return bool(re.match(r'^(?:me siento|estoy (?:triste|feliz|cansad[oa]|aburrid[oa]|nervios[oa])|'
        r'tengo hambre|quiero contarte|te cuento|hoy me (?:paso|siento)|'
        r'recuerdas (?:lo que|mi |mis |como me llamo|que te dije|de lo que hablamos)|como me llamo|sabes como me llamo|que te dije|que hemos hablado|'
        r'que (?:piensas|opinas) (?:de mi|sobre mi)|te gusta |tu que prefieres|y tu\b)', text))


def self_reply(message, brand='AKIRA'):
    intent = self_intent(message, brand)
    return {
        'identity': f'Soy {brand}, tu asistente. Podemos conversar, investigar y revisar juntos lo que está pasando en el programa.',
        'capabilities': 'Puedo conversar contigo, explicar temas, ayudarte a escribir, investigar fuentes y revisar el estado de Akira. Las operaciones pasan por el motor y sus controles de riesgo; hablar conmigo no coloca órdenes por sí solo.',
        'presence': 'Aquí estoy, te leo. Puedes hablarme directamente y seguir el tema que llevábamos.',
        'greeting': 'Aquí estoy, lista para conversar contigo. ¿Cómo te ha ido?',
        'conversation': 'Claro, conversemos. Cuéntame qué tienes en mente.',
        'nature': 'Soy una IA, no una persona y no tengo sentimientos reales. Aun así, podemos conversar con confianza y puedo ayudarte a pensar las cosas.',
    }.get(intent)
