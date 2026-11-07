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
    for i,event in enumerate((snapshot.get('research') or {}).get('events',[])[:3]):
        if plan['symbol'] not in event.get('symbols',[]):continue
        out[f'event.{i}.headline']=str(event.get('title',''))[:240]
        out[f'event.{i}.published_utc']=event.get('published_utc')
        out[f'event.{i}.verification']=str(event.get('verification','UNVERIFIED'))
    return out

def fingerprint(plan,snapshot):
    # Financial facts are audited with the verdict, but floating P/L and spread
    # change every tick. Gateway recomputes affordability before EVERY send.
    # A language-model round trip cannot be keyed to those moving observations.
    stable_facts={k:v for k,v in facts(plan,snapshot).items() if not k.startswith(('order.','account.'))}
    payload={'order':{k:plan.get(k) for k in ('symbol','side','lane','kind','entry','sl','tp','volume')},
        'account':{k:(snapshot.get('account') or {}).get(k) for k in ('login','server','currency','trade_mode')},
        'facts':stable_facts,'configuration':snapshot.get('selection_configuration',{})}
    # Bind the evidence actually delivered to this exact-order reviewer.
    # Unrelated API reception times, live books and derivatives digests were
    # never in its prompt and can refresh faster than a CPU review completes.
    # Dated relevant events ARE in facts; new ones still invalidate a receipt.
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

def progress(row,now,expected=None):
    state=row.get('state','WAITING');data=row.get('data') or {}
    if expected and row and row.get('fingerprint')!=expected:state='CHANGED_EVIDENCE'
    if state=='COMPLETE':
        state='APPROVED' if valid_receipt(row,expected or row.get('fingerprint'),now) else ('EXPIRED' if now-float(row.get('updated',0))>180 else data.get('verdict','INVALID'))
    return {'state':state,'phase':row.get('phase',''),'provider':row.get('provider') or row.get('model_mode') or '',
        'model':row.get('model',''),'elapsed_seconds':round(max(0,now-float(row.get('started') or row.get('requested') or now)),1),
        'queue_ahead':int(row.get('queue_ahead',0)),'retry_seconds':round(max(0,float(row.get('retry_at',0))-now),1),
        'reason':str(row.get('error') or data.get('reason') or ('Cambiaron los niveles o la evidencia técnica; preparando revisión actual.' if state=='CHANGED_EVIDENCE' else 'Esperando revisión de la propuesta exacta.'))[:240],
        'review_seconds':row.get('review_seconds'),'reviewed_at':row.get('created') or row.get('updated')}
