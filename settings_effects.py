"""Describe and validate settings transactions, independent from a Tk form."""
import copy,math
from settings import load_config

TARGETS={'mode':'Modo de operación','desktop':'Interfaz, rendimiento y notificaciones','risk':'Gateway: riesgo y margen','sizing':'Gateway: lote',
 'lot':'Gateway: lote base','pending':'Motor: vigencia y sustitución','execution':'Motor: ejecución',
 'strategy':'Selector técnico','symbol_profiles':'Selector por símbolo','research':'Fuentes en segundo plano',
 'assistant':'Conversación y permisos','management':'Gestión de posiciones','runner':'Gestión de continuidad',
 'studio':'Personalización de interfaz (no opera MT5)','knowledge':'Actualización de conocimiento','charts':'Representación de indicadores'}

def value_at(cfg,path):
    value=cfg
    for key in path.split('.'):value=value[key]
    return value

def changes(before,after):
    rows=[]
    def compare(a,b,prefix=''):
        for key,value in b.items():
            path=prefix+key;old=a.get(key)
            if isinstance(value,dict):compare(old if isinstance(old,dict) else {},value,path+'.')
            elif old!=value:rows.append({'path':path,'before':old,'after':value,'target':TARGETS.get(path.split('.')[0],'Configuración del motor')})
    compare(before,after);return rows

def validate_form(cfg):
    cfg=load_config(copy.deepcopy(cfg))
    from strategy_choice import ADAPTIVE,known
    if not known((cfg.get('strategy_choice') or {}).get('selected',ADAPTIVE)):
        raise ValueError('La estrategia elegida no corresponde a una familia implementada.')
    for key in ('width','height'):
        value=cfg['desktop'][key]
        if type(value) is not int or not 600<=value<=8000:raise ValueError('Dimensión inválida: '+key)
    from resource_optimizer import PROFILES
    if cfg['desktop'].get('performance_profile') not in PROFILES:
        raise ValueError('Selecciona un modo de optimización válido')
    from resource_optimizer import LIMITS
    for key,(minimum,maximum) in LIMITS.items():
        value=cfg['desktop'].get(key)
        if isinstance(value,bool) or not isinstance(value,int) or not minimum<=value<=maximum:
            raise ValueError('Optimizador: '+key+' debe estar entre '+str(minimum)+' y '+str(maximum))
    k=cfg.get('knowledge',{})
    for key in ('max_trade_pct','portfolio_capital_pct','daily_loss_pct'):
        if not 0<=cfg['risk'].get(key,0)<=100:raise ValueError('Riesgo: '+key+' debe estar entre 0 y 100')
    for symbol,profile in cfg.get('symbol_profiles',{}).items():
        for key,value in profile.items():
            if any(part in key for part in ('quality_min','activation_min')) and not 0<=value<=100:raise ValueError(symbol+': '+key+' debe estar entre 0 y 100')
    if k.get('mode','automatic') not in ('automatic','request'):raise ValueError('Actualización de conocimiento inválida')
    for key,lo,hi in [('interval_hours',1,168),('cache_days',1,365)]:
        value=k.get(key,24 if key=='interval_hours' else 14)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError('Conocimiento: '+key+' fuera de rango')
    return cfg

def change_message(rows):
    if not rows:return 'No había cambios pendientes.'
    return '\n'.join(('Entradas: pendientes únicamente; las posiciones activadas se gestionan como runners.' if r['after'] else
        'Entradas: pendientes y runners directos con confirmación estructural. Conservan los límites de riesgo y la validación del broker.')
        if r['path']=='execution.pending_only' else r['path']+': '+str(r['before'])+' → '+str(r['after'])+' · '+r['target'] for r in rows)
