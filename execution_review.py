"""Strict neural verdict receipts bound to exact orders and causal evidence."""
import hashlib,json,math
from market_state import value

SCHEMA_VERSION=1

def facts(plan,snapshot):
    out={}
    for k in ('side','entry','sl','tp','volume','risk_usd','reward_usd','margin','net_rr'):
        v=plan.get(k)
        if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v):out['order.'+k]=v
    info=(snapshot.get('symbols') or {}).get(plan['symbol'],{})
    for tf,row in (info.get('frames') or {}).items():
        if tf not in ('M15','H1','H4','D1'):continue
        for k in ('last_bar','atr','trend','rsi','adx','bos','sweep','range_hi','range_lo','volume_ratio'):
            v=row.get(k)
            if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v):out[tf+'.'+k]=v
    for k in ('balance','equity','margin_free'):
        v=(snapshot.get('account') or {}).get(k)
        if isinstance(v,(int,float)) and math.isfinite(v):out['account.'+k]=v
    return out

def fingerprint(plan,snapshot):
    payload={'order':{k:plan.get(k) for k in ('symbol','side','lane','kind','entry','sl','tp','volume','risk_usd','reward_usd','net_rr')},
        'account':{k:(snapshot.get('account') or {}).get(k) for k in ('login','server','currency','balance','equity')},
        'facts':facts(plan,snapshot),'configuration':snapshot.get('selection_configuration',{}),
        'source_evidence':{k:{f:r.get(f) for f in ('fresh','usable','error','enabled','content_digest')} for k,r in (snapshot.get('research') or {}).get('sources',{}).items()
                           if isinstance(r,dict) and not k.startswith(('local_ai','technical_review','pending_ai','youtube','strategy_reference')) and (not plan['symbol'].startswith('XAU') or not k.startswith(('venue:','derivatives:','search:BTC','technical:BTC')))}}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False,default=str).encode()).hexdigest()

def schema(evidence):
    return {'type':'object','properties':{
        'verdict':{'type':'string','enum':['APPROVE','REJECT','INSUFFICIENT_DATA']},
        'reason':{'type':'string','minLength':1,'maxLength':240},
        'contradictions':{'type':'array','items':{'type':'string'},'maxItems':4},
        'evidence':{'type':'array','items':{'type':'string','enum':list(evidence) or ['NO_DATA']},'maxItems':6},
        'missing':{'type':'array','items':{'type':'string'},'maxItems':6}},
        'required':['verdict','reason','contradictions','evidence','missing'],'additionalProperties':False}

def validate(raw,evidence):
    data=json.loads(raw) if isinstance(raw,str) else raw
    if not isinstance(data,dict) or set(data)!={'verdict','reason','contradictions','evidence','missing'}:raise ValueError('Dictamen IA no cumple el esquema estricto')
    if data['verdict'] not in ('APPROVE','REJECT','INSUFFICIENT_DATA'):raise ValueError('Veredicto IA desconocido')
    if not isinstance(data['reason'],str) or not data['reason'].strip() or len(data['reason'])>240:raise ValueError('Razón IA inválida')
    for k,limit in [('contradictions',4),('evidence',6),('missing',6)]:
        if not isinstance(data[k],list) or len(data[k])>limit or any(not isinstance(s,str) or len(s)>300 for s in data[k]):raise ValueError('Evidencia IA inválida: '+k)
    if len(set(data['evidence']))!=len(data['evidence']) or any(s not in evidence for s in data['evidence']):raise ValueError('La IA citó una evidencia que no recibió')
    if data['verdict']=='APPROVE':
        if data['missing'] or data['contradictions'] or not any(k.startswith('order.') for k in data['evidence']) or not any(k.startswith(('M15.','H1.','H4.','D1.','W1.')) for k in data['evidence']):raise ValueError('Aprobación sin geometría y evidencia técnica suficientes')
    return {**data,'schema_version':SCHEMA_VERSION,'verified_facts':{k:evidence[k] for k in data['evidence']}}

def valid_receipt(row,expected,now):
    if not isinstance(row,dict) or row.get('state')!='COMPLETE' or row.get('fingerprint')!=expected:return False
    try:
        if not 0<=now-float(row['updated'])<=180:return False
        data=row['data']
        if data.get('schema_version')!=SCHEMA_VERSION:return False
        verified=validate({k:data[k] for k in ('verdict','reason','contradictions','evidence','missing')},data['verified_facts'])
        return verified['verdict']=='APPROVE'
    except (ValueError,KeyError,TypeError):return False

def request_id(plan):
    return str(plan['symbol'])+' / EXEC / '+str(plan.get('key') or plan.get('ticket'))
