"""Bounded conversational generation. No broker, network or model imports.

A token-limited answer is a draft, never a successful completed turn. At most one
regeneration is allowed within the same absolute deadline; nothing is executed.
"""
import re,time
from conversation_core import folded


def answer_plan(question,style='natural',maximum=1200):
    detailed=style=='detailed' or bool(re.search(r'\b(?:detall\w*|paso a paso|demostraci\w*|extens\w*|completo|completa|a fondo)\b',folded(question)))
    return {'tokens':max(128,min(int(maximum),1024 if detailed else 512)),
            'words':260 if detailed else 110,'timeout':210 if detailed else 120,
            'detail':detailed}


def complete_reply(messages,invoke,receipt,clear,plan,timeout,on_repair=lambda reason:None,
                   inspect=lambda text:'',cancelled=lambda:False,clock=time.monotonic):
    deadline=clock()+float(timeout);attempts=[]
    base=list(messages);previous_issue=''
    for attempt in range(2):
        if cancelled():raise RuntimeError('Análisis detenido por el usuario')
        remaining=deadline-clock()
        if remaining<=1:raise TimeoutError('No quedó tiempo para terminar y comprobar la respuesta')
        words=plan['words'] if attempt==0 else min(90,plan['words'])
        instruction=(f'Redacta una respuesta completa en hasta {words} palabras. '
            'Resuelve lo preguntado y termina la explicación antes de añadir más ejemplos. '
            'No añadas otras preguntas o temas si ya contestaste. '
            'Si explicas una fórmula, define sus símbolos y la relación; usa las notas de referencia si las hay.')
        if previous_issue:instruction+=' Revisión requerida: '+previous_issue
        prompts=[*base[:-1],{'role':'system','content':instruction},base[-1]]
        clear()
        text=invoke(prompts,plan['tokens'] if attempt==0 else min(plan['tokens'],384),remaining)
        info=receipt()
        if not isinstance(text,str) or not text.strip():raise RuntimeError('El modelo no produjo texto visible')
        issue=('La generación alcanzó el límite antes de terminar.' if info.get('truncated') or info.get('finish_reason')=='length' else inspect(text))
        attempts.append({'finish_reason':info.get('finish_reason'),'issue':issue or None})
        if not issue:return text,{**info,'attempts':attempts,'repaired':attempt>0}
        if attempt==0:previous_issue=issue;on_repair(issue)
    raise RuntimeError('La respuesta no terminó o contradijo la referencia después de la revisión; no se guardó como respuesta completa.')
