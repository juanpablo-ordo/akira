"""Bounded prospective strategy experiments; never touches broker or live rules."""
from pathlib import Path
from contextlib import contextmanager
import copy,hashlib,json,math,sqlite3,threading,time
from trade_quality_gate import family,num
from strategy_research import ResearchLedger

REFERENCE_URL='https://www.youtube.com/watch?v=p579vzivHoc'
MAX_CASES=5000
MAX_RESULTS=300000
FAMILIES={
 'PENDIENTE_RETROCESO':('Retroceso estructural','LIMIT en soporte/resistencia observado; H1/M15 y colchón ATR; SL tras invalidación y TP observado.'),
 'PENDIENTE_RUPTURA':('Ruptura estructural','STOP fuera del rango confirmado; recorrido hasta el siguiente obstáculo, volumen y riesgo del broker.'),
 'RUNNER_CONTINUACION_M15':('Runner de continuación M15','Ruptura, retest o recuperación de EMA21 con H1 alineado; no perseguir velas extendidas.'),
 'RUNNER_RETEST_M5':('Runner de retest M5','Retest M5 confirmado dentro de la tesis M15/H1; la gestión conserva estructura M15.'),
 'REVERSION_CONFIRMADA':('Reversión confirmada','Barrido, recuperación y ruptura de estructura; el impulso H1 contrario requiere confirmación.'),
 'RANGO_RECHAZO':('Rechazo de rango','ADX bajo, rechazo de un extremo y objetivo dentro del rango; evitar rupturas fuertes.')}
TEMPLATES={
 'EMA_PULLBACK':('Retroceso a EMA21','EMA21 M15, tendencia H1, RSI, ATR y volumen','PENDIENTE_RETROCESO'),
 'BREAK_RETEST':('Ruptura y retest','Rango M15 de ocho velas, recuperación, EMA21, ATR y H1','PENDIENTE_RETROCESO'),
 'SWEEP_RECLAIM':('Barrido y recuperación','Extremo previo, mecha, cierre de recuperación, ATR y volumen','REVERSION_CONFIRMADA'),
 'RANGE_REJECTION':('Rechazo de extremo lateral','Rango de veinte velas, ADX, RSI, ATR y rechazo por cierre','RANGO_RECHAZO')}

def wilson(w,n,z=1.96):
 if not n:return None
 p=w/n;d=1+z*z/n;center=(p+z*z/(2*n))/d;delta=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
 return [max(0,center-delta),min(1,center+delta)]

def measured(rows,key='pnl'):
 rows=[r for r in rows if r.get(key) is not None and math.isfinite(float(r[key]))];n=len(rows)
 rows.sort(key=lambda r:num(r.get('closed_at',r.get('exit_at',0))))
 wins=sum(float(r[key])>0 for r in rows);net=sum(float(r[key]) for r in rows)
 curve=peak=dd=0
 for r in rows:curve+=float(r[key]);peak=max(peak,curve);dd=max(dd,peak-curve)
 return {'n':n,'wins':wins,'losses':sum(float(r[key])<0 for r in rows),'net':net if n else None,
  'win_rate':wins/n if n else None,'win_interval':wilson(wins,n),'expectancy':net/n if n else None,'drawdown':dd if n else None}

def definitions():
 out=[{'id':k,'name':v[0],'rules':v[1],'origin':'Motor operativo existente','mode':'OPERATIVA','version':1} for k,v in FAMILIES.items()]
 out.insert(0,{'id':'AKIRA_ADAPTATIVA','name':'Akira Adaptativa','rules':'Selector principal de las familias estructurales implementadas. Usa las reglas técnicas, contexto vigente, costes, autorización y riesgo existentes; conserva familia y versión por propuesta. Su posición en el catálogo no demuestra superioridad estadística.','origin':'Estrategia principal del producto','mode':'OPERATIVA','version':1})
 # Finite neighbors, fixed BEFORE seeing outcomes. Hypotheses, not a claim of
 # discovering a profitable strategy. No unrestricted model-generated code.
 for template,(name,indicators,base) in TEMPLATES.items():
  for buffer,min_rr in ((.15,1.8),(.25,2.0),(.35,2.2)):
   spec={'template':template,'buffer_atr':buffer,'min_rr':min_rr,'expiry_seconds':7200,'horizon_seconds':86400}
   sid='LAB_'+hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()[:12]
   out.append({'id':sid,'name':name+f' · colchón {buffer:g} ATR / R mínimo {min_rr:g}',
    'origin':'Hipótesis generada por AKIRA a partir de reglas estructurales acotadas','mode':'EXPERIMENTO',
    'rules':indicators+f'; invalidación tras extremo observado con colchón {buffer:g} ATR; objetivo en pivote H1/M15 y R:R mínimo {min_rr:g}. La pendiente experimental caduca a las 2 horas; observación máxima de 24 horas.',
    'spec':spec,'base_family':base,'version':1,'auto_live_activation':False})
 return out

def propose(definition,symbol,info,now):
 spec=definition.get('spec');frames=info.get('frames') or {};f=frames.get('M15') or {};h=frames.get('H1') or {}
 bars=(info.get('bars') or {}).get('M15') or (info.get('bars_by_timeframe') or {}).get('M15') or []
 if not spec or len(bars)<24 or num(f.get('atr'))<=0:return None
 last=bars[-1];atr=num(f['atr']);spread=num(info.get('spread'));bar=num(last['time'])
 if not 0<=now-(bar+900)<=960:return None
 b=spec['buffer_atr'];prior=bars[-21:-1];lo=min(num(x['low']) for x in prior);hi=max(num(x['high']) for x in prior)
 for side in (1,-1):
  close=num(last['close']);high=num(last['high']);low=num(last['low']);body=side*(close-num(last['open']))
  trend=side*num(h.get('trend'));key=spec['template'];entry=0;anchor=0
  if key=='EMA_PULLBACK':
   base=num(f.get('ema21'))
   if trend<=.18 or side*num(f.get('trend'))<=.12 or not 35<=num(f.get('rsi'),50)<=70:continue
   entry=base;anchor=min(num(x['low']) for x in bars[-8:]) if side==1 else max(num(x['high']) for x in bars[-8:])
  elif key=='BREAK_RETEST':
   window=bars[-10:-2];level=max(num(x['high']) for x in window) if side==1 else min(num(x['low']) for x in window)
   previous=bars[-2];touch=low<=level+atr*.2 if side==1 else high>=level-atr*.2
   if trend<=.18 or side*(num(previous['close'])-level)<=atr*.025 or not touch or side*(close-level)<=atr*.025:continue
   entry=level;anchor=min(num(x['low']) for x in bars[-3:]) if side==1 else max(num(x['high']) for x in bars[-3:])
  elif key=='SWEEP_RECLAIM':
   swept=low<lo and close>lo+atr*.05 if side==1 else high>hi and close<hi-atr*.05
   if not swept or body<=atr*.2 or num(f.get('volume_ratio'))<.7:continue
   entry=(close+(low if side==1 else high))/2;anchor=low if side==1 else high
  else:
   if num(f.get('adx'),99)>=18 or abs(num(h.get('trend')))>.25 or body<=atr*.15:continue
   rejection=low<=lo+atr*.1 and close>lo+atr*.2 if side==1 else high>=hi-atr*.1 and close<hi-atr*.2
   if not rejection:continue
   entry=lo if side==1 else hi;anchor=low if side==1 else high
  sl=anchor-side*max(atr*b,spread*2);risk=side*(entry-sl)
  if risk<atr*.35 or risk>atr*3 or risk<spread*3:continue
  ref=num(info.get('ask' if side==1 else 'bid'))
  if ref<=0 or side*(ref-entry)<max(spread,atr*.05):continue
  # Only observed past pivots/levels; no projection to manufacture R:R.
  periods={'M15':900,'H1':3600,'H4':14400}
  levels=[num(x['high' if side==1 else 'low']) for tf in ('M15','H1','H4') for x in ((info.get('bars') or {}).get(tf) or (info.get('bars_by_timeframe') or {}).get(tf) or [])[-64:]
   if num(x.get('time'))+periods[tf]<=now+2]
  ahead=[p for p in levels if side*(p-entry)>max(risk*spec['min_rr'],atr*.3)]
  if not ahead:continue
  tp=min(ahead,key=lambda p:side*(p-entry))-side*atr*.03
  if side*(tp-entry)/risk<spec['min_rr']:continue
  return {'symbol':symbol,'key':definition['id']+':'+str(side)+':'+str(int(bar)),'side':side,'kind':'LIMIT','lane':'PENDING',
   'entry':entry,'sl':sl,'tp':tp,'atr':atr,'horizon_atr':atr,'bar_time':bar,'signal_timeframe':'M15','target_observed':True,
   'reason':definition['rules'],'research_only':True}
 return None

def advance_case(case,bid,ask,stamp,fee_r=0):
 """Conservative sampled bid/ask replay. Gaps invalidate results, never win."""
 p=case['plan'];side=p['side'];risk=side*(p['entry']-p['sl']);row=copy.deepcopy(case)
 if stamp<=num(row.get('last_quote')):return row
 if risk<=0 or not all(math.isfinite(x) for x in (bid,ask,stamp,fee_r)) or bid<=0 or ask<bid:return row
 if row.get('state') not in ('WAITING','OPEN'):return row
 if num(row.get('last_quote')) and stamp-num(row['last_quote'])>60:row.update(state='GAP',net_r=None,exit_at=stamp);return row
 row['last_quote']=stamp
 if row['state']=='WAITING':
  if stamp>=row['created']+row['expiry_seconds']:row.update(state='EXPIRED',net_r=None,exit_at=stamp);return row
  touched=ask<=p['entry'] if side==1 else bid>=p['entry']
  if not touched:return row
  row.update(state='OPEN',entry_at=stamp)
 exit_price=bid if side==1 else ask;r=side*(exit_price-p['entry'])/risk
 row['mfe_r']=max(num(row.get('mfe_r')),r);row['mae_r']=max(num(row.get('mae_r')),-r)
 sl_hit=side*(exit_price-p['sl'])<=0;tp_hit=side*(exit_price-p['tp'])>=0
 if sl_hit:row.update(state='SL',exit_at=stamp,net_r=min(-1,r)-fee_r)
 elif tp_hit:row.update(state='TP',exit_at=stamp,net_r=side*(p['tp']-p['entry'])/risk-fee_r)
 elif stamp>=row['entry_at']+row['horizon_seconds']:row.update(state='TIMEOUT',exit_at=stamp,net_r=r-fee_r)
 if row['state'] in ('SL','TP','TIMEOUT'):row.update(exit_bid=bid,exit_ask=ask)
 return row

def chart_png(bars,plan,path,title):
 from PIL import Image,ImageDraw,ImageFont
 from datetime import datetime,timezone
 bars=bars[-64:];im=Image.new('RGB',(1100,620),'#061022');d=ImageDraw.Draw(im)
 try:
  import reportlab
  fonts=Path(reportlab.__file__).parent/'fonts'
  heading=ImageFont.truetype(str(fonts/'VeraBd.ttf'),20)
  text=ImageFont.truetype(str(fonts/'Vera.ttf'),17);small=ImageFont.truetype(str(fonts/'Vera.ttf'),14)
 except (ImportError,OSError):heading=text=small=ImageFont.load_default()
 d.text((25,18),title[:84],font=heading,fill='#23ddf4')
 d.text((25,50),'M15 cerradas · Caso observado / propuesta · EMA21 ilustrada',font=text,fill='#a4b5c6')
 if not bars:raise ValueError('No hay velas reales para dibujar la estrategia')
 values=[num(b[k]) for b in bars for k in ('low','high')]+[num(plan[k]) for k in ('entry','sl','tp')]
 low=min(values);high=max(values);span=max(high-low,1e-8);bottom=505;top=105;width=760/len(bars)
 def y(p):return bottom-(p-low)/span*(bottom-top)
 for i in range(5):
  price=low+span*i/4;yy=y(price)
  d.line((115,yy,885,yy),fill='#183248',width=1);d.text((20,yy-8),f'{price:,.2f}',font=small,fill='#a4b5c6')
 ema=None;points=[]
 for i,b in enumerate(bars):
  x=120+(i+.5)*width;o,c,h,l=[num(b[k]) for k in ('open','close','high','low')];color='#44e5b5' if c>=o else '#ff6d89'
  d.line((x,y(h),x,y(l)),fill=color,width=1);d.rectangle((x-width*.27,min(y(o),y(c)),x+width*.27,max(y(o),y(c))+1),fill=color)
  ema=c if ema is None else ema+(c-ema)*2/22;points.append((x,y(ema)))
 if len(points)>1:d.line(points,fill='#ffd265',width=2)
 for key,color in (('entry','#23ddf4'),('sl','#ff6d89'),('tp','#44e5b5')):
  yy=y(num(plan[key]));d.line((115,yy,885,yy),fill=color,width=2)
  name='ENTRADA' if key=='entry' else key.upper();d.text((895,yy-10),name+' '+f'{num(plan[key]):,.3f}',font=text,fill=color)
 for i in sorted({0,len(bars)//3,len(bars)*2//3,len(bars)-1}):
  when=datetime.fromtimestamp(num(bars[i]['time'])+900,timezone.utc).strftime('%d/%m %H:%M')
  d.text((120+i*width,529),when,font=small,fill='#a4b5c6')
 d.text((35,566),'Cierre de vela en UTC. Niveles exactos e indicadores completos en la ficha.',font=text,fill='#a4b5c6')
 d.text((35,591),'Una imagen describe el caso; su evaluación depende de resultados y costes.',font=small,fill='#a4b5c6')
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp.png');im.save(temp);temp.replace(path);return str(path)

class StrategyLab:
 def __init__(self,root,cfg,clock=time.time):
  self.root=Path(root);self.path=self.root/'state/strategy_lab.sqlite3';self.path.parent.mkdir(parents=True,exist_ok=True)
  self.cfg,self.clock=cfg,clock;self.lock=threading.RLock();self.wake=threading.Event();self.stop=threading.Event();self.snapshot={};self.thread=None
  self._summary={'state':'ESPERANDO DATOS','strategies':definitions(),'reference':{'url':REFERENCE_URL,'state':'CONTENIDO NO VERIFICADO'},'updated':0}
  self.reference=self._summary['reference']
  self.research_ledger=ResearchLedger(root)
  from strategy_adaptation import StrategyAdaptation
  self.adaptation=StrategyAdaptation(root,cfg,clock)
  with self.db() as db:
   db.execute('CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,strategy_id TEXT,symbol TEXT,created REAL,body TEXT)')
   db.execute('CREATE INDEX IF NOT EXISTS cases_created ON cases(created)')
   db.execute('CREATE TABLE IF NOT EXISTS evaluations(id TEXT PRIMARY KEY,selected_at REAL,body TEXT)')
   db.execute('CREATE TABLE IF NOT EXISTS reference(id TEXT PRIMARY KEY,body TEXT)')
   # Full bar/source snapshots are bounded separately from compact results.
   # Otherwise rapid strategies would erase their holdout before reaching 20 days.
   db.execute('CREATE TABLE IF NOT EXISTS results(id TEXT PRIMARY KEY,cohort TEXT,strategy_id TEXT,symbol TEXT,created REAL,exit_at REAL,state TEXT,net_r REAL,body TEXT)')
   db.execute('CREATE INDEX IF NOT EXISTS results_cohort ON results(cohort,strategy_id,symbol,created)')
   db.execute('CREATE INDEX IF NOT EXISTS results_exit ON results(exit_at)')
   old=db.execute('SELECT body FROM reference WHERE id=?',(REFERENCE_URL,)).fetchone()
   if old:self.reference=json.loads(old[0]);self._summary['reference']=copy.deepcopy(self.reference)
  self.last_signature=None
 @contextmanager
 def db(self):
  db=sqlite3.connect(self.path,timeout=2)
  try:
   with db:yield db
  finally:db.close()
 def start(self):
  if self.thread and self.thread.is_alive():return
  self.thread=threading.Thread(target=self.run,daemon=True,name='AkiraStrategies');self.thread.start()
 def submit(self,snapshot):
  with self.lock:self.snapshot=copy.deepcopy(snapshot)
  self.wake.set()
 def close(self):
  self.stop.set();self.wake.set()
  if self.thread and self.thread is not threading.current_thread() and self.thread.is_alive():self.thread.join(timeout=3)
 def read(self):
  with self.lock:result=copy.deepcopy(self._summary)
  result['research_ledger']=self.research_ledger.summary()
  result['adaptation']=self.adaptation.read()
  return result
 def ingest_source(self,row):
  profiles=self.adaptation.ingest_source(row)
  if row.get('complete'):
   self.research_ledger.add(url=row['url'],kind='youtube_transcript',title=row.get('title',''),author=row.get('author',''),body=row.get('body',''),status=row.get('status','transcript'),source_time=row.get('published'))
  return profiles
 def set_reference(self,row):
  from urllib.parse import urlsplit,parse_qs
  import re
  parts=urlsplit(str(row.get('url','')));vid=parse_qs(parts.query).get('v',[''])[0] if parts.hostname!='youtu.be' else parts.path.strip('/')
  if parts.hostname not in ('youtube.com','www.youtube.com','m.youtube.com','youtu.be') or vid!='p579vzivHoc' or row.get('status') not in ('transcript','analyzed') or not row.get('complete') or len(str(row.get('body') or ''))<1000:
   raise ValueError('No hay una transcripción completa del video compartido; no se afirma haber aprendido su estrategia')
  text=row['body'];data={'url':REFERENCE_URL,'state':'TRANSCRIPCIÓN RECUPERADA · REGLAS SIN VALIDAR',
   'title':row.get('title'),'author':row.get('author'),'fetched':row.get('fetched'),'caption_type':row.get('caption_type'),
   'transcript_sha256':hashlib.sha256(text.encode()).hexdigest(),
   'detected_terms':[t for t in ('temporalidad','ema','rsi','adx','ruptura','retroceso','riesgo','stop') if re.search(r'\b'+t+r'\b',text,re.I)],
   'note':'Subtítulos recuperados; no equivale a verificar precisión, replicar reglas ni validar rentabilidad. No cambia operaciones.'}
  with self.db() as db:db.execute('INSERT OR REPLACE INTO reference VALUES(?,?)',(REFERENCE_URL,json.dumps(data)))
  with self.lock:self.reference=data;self._summary['reference']=copy.deepcopy(data)
  return data
 def tick(self):
  with self.lock:snap=copy.deepcopy(self.snapshot)
  if not snap.get('symbols'):return
  self.adaptation.observe(snap)
  now=self.clock();defs=definitions();cases={};examples={};generation=0
  cohort=hashlib.sha256(json.dumps({'account':snap.get('learning_account'),'build':snap.get('build'),
   'configuration':snap.get('selection_configuration'),'costs':{s:{k:r.get(k) for k in ('lot','round_turn_fee','source')} for s,r in (snap.get('paper_costs') or {}).items()}},sort_keys=True,default=str).encode()).hexdigest()[:20]
  with self.db() as db:
   cases={r[0]:json.loads(r[1]) for r in db.execute('SELECT id,body FROM cases ORDER BY created DESC LIMIT ?',(MAX_CASES,))}
   for symbol,info in snap['symbols'].items():
    if snap.get('markets',{}).get(symbol,{}).get('scheduled_closed'):continue
    quote_stamp=num(info.get('quote_time'))
    if not 0<=now-quote_stamp<=10:continue
    for sid,row in list(cases.items()):
     if row.get('cohort')!=cohort or row['symbol']!=symbol or row['state'] not in ('WAITING','OPEN'):continue
     updated=advance_case(row,num(info.get('bid')),num(info.get('ask')),quote_stamp,row.get('estimated_fee_r',0))
     cases[sid]=updated;db.execute('UPDATE cases SET body=? WHERE id=?',(json.dumps(updated),sid))
    for definition in defs:
     if not definition.get('spec'):continue
     p=propose(definition,symbol,info,now)
     if not p:continue
     case_id=cohort+'/'+definition['id']+'/'+symbol+'/'+str(int(p['bar_time']))+'/'+str(p['side'])
     if case_id in cases or db.execute('SELECT id FROM cases WHERE id=? UNION ALL SELECT id FROM results WHERE id=? LIMIT 1',(case_id,case_id)).fetchone():continue
     terms=(snap.get('paper_costs') or {}).get(symbol) or {};risk=abs(p['entry']-p['sl']);unit=num(terms.get('profit_per_price_unit'))
     fee_r=num(terms.get('round_turn_fee'))/(unit*risk) if unit>0 and risk>0 else None
     row={'id':case_id,'cohort':cohort,'strategy_id':definition['id'],'symbol':symbol,'created':now,'bar':p['bar_time'],'plan':p,'state':'WAITING',
      'expiry_seconds':definition['spec']['expiry_seconds'],'horizon_seconds':definition['spec']['horizon_seconds'],
      'last_quote':quote_stamp,'net_r':None,'estimated_fee_r':fee_r or 0,'costs_available':fee_r is not None,
      'source':'MT5_QUOTES_SAMPLED','configuration':snap.get('selection_configuration'),
      'evidence':{'frames':info.get('frames'),'sources':snap.get('research_sources',{})}}
     db.execute('INSERT INTO cases VALUES(?,?,?,?,?)',(case_id,definition['id'],symbol,now,json.dumps(row)));cases[case_id]=row;generation+=1
     bars=(info.get('bars') or {}).get('M15') or (info.get('bars_by_timeframe') or {}).get('M15') or []
     examples[definition['id']+'/'+symbol]={'bars':bars[-64:],'plan':p,'created':now,'indicators':{tf:{k:v for k,v in (info.get('frames',{}).get(tf) or {}).items() if k in ('atr','rsi','adx','ema21','macd','volume_ratio','trend')} for tf in ('M15','H1')}}
   for c in cases.values():
    if c.get('archived') or c.get('state') not in ('SL','TP','TIMEOUT','GAP','EXPIRED') or not 0<c['created']<=num(c.get('exit_at'))<=now:continue
    detail={k:c.get(k) for k in ('plan','estimated_fee_r','costs_available','entry_at','exit_bid','exit_ask','mfe_r','mae_r','source')}
    db.execute('INSERT OR IGNORE INTO results VALUES(?,?,?,?,?,?,?,?,?)',(c['id'],c['cohort'],c['strategy_id'],c['symbol'],c['created'],c['exit_at'],c['state'],c.get('net_r') if c.get('costs_available') else None,json.dumps(detail)))
    c['archived']=True;db.execute('UPDATE cases SET body=? WHERE id=?',(json.dumps(c),c['id']))
   db.execute('DELETE FROM cases WHERE id NOT IN (SELECT id FROM cases ORDER BY created DESC LIMIT ?)',(MAX_CASES,))
   if db.execute('SELECT COUNT(*) FROM results').fetchone()[0]>MAX_RESULTS:
    db.execute('DELETE FROM results WHERE id NOT IN (SELECT id FROM results ORDER BY exit_at DESC LIMIT ?)',(MAX_RESULTS,))
   strategy_rows=[]
   outcomes=snap.get('confirmed_strategy_outcomes') or []
   for definition in defs:
    row=copy.deepcopy(definition);per={}
    for symbol in snap['symbols']:
     actual=[r for r in outcomes if r.get('symbol')==symbol and
      ((r.get('selector_id') or (r.get('plan') or {}).get('selector_id'))==row['id'] if row['id']=='AKIRA_ADAPTATIVA' else r.get('strategy_id')==row['id'])]
     paper=sorted([c for c in cases.values() if c.get('cohort')==cohort and c['symbol']==symbol and c['strategy_id']==row['id']],key=lambda c:c['created'])
     history=[{'created':c[0],'exit_at':c[1],'state':c[2],'net_r':c[3]} for c in db.execute(
      'SELECT created,exit_at,state,net_r FROM results WHERE cohort=? AND strategy_id=? AND symbol=? AND exit_at<=? ORDER BY created',(cohort,row['id'],symbol,now))]
     resolved=[c for c in history if c['state'] in ('SL','TP','TIMEOUT') and c['net_r'] is not None]
     eid=cohort+'/'+row['id']+'/'+symbol
     old=db.execute('SELECT selected_at,body FROM evaluations WHERE id=?',(eid,)).fetchone()
     # Freeze the experiment after its first 20 outcomes; all subsequent cases
     # are forward holdout. Never relabel earlier cases as unseen validation.
     if not old and len(resolved)>=20:
      selected=max(num(c.get('exit_at')) for c in resolved[:20]);training=measured(resolved[:20],'net_r')
      db.execute('INSERT INTO evaluations VALUES(?,?,?)',(eid,selected,json.dumps(training)));old=(selected,json.dumps(training))
     holdout=[c for c in resolved if old and c['created']>old[0]]
     test=measured(holdout,'net_r');days=len({int(c['created']//86400) for c in holdout})
     comparable=test['n']>=50 and days>=20 and test['expectancy']>0 and bool(old and json.loads(old[1]).get('expectancy',0)>0)
     per[symbol]={'cohort':cohort,'realized':measured(actual),'paper':measured(resolved,'net_r'),'holdout':test,'holdout_days':days,
      'selection_locked_at':old[0] if old else None,'state':'EVIDENCIA PROSPECTIVA DISPONIBLE' if comparable else 'EN ESTUDIO',
      'active_cases':sum(c['state'] in ('WAITING','OPEN') for c in paper),'invalid_gaps':sum(c['state']=='GAP' for c in history),
      'scope':'Realizado: cierres propios completos, costes reales. Paper: R normalizados en cotizaciones muestreadas, comisiones estimadas; no ganancias de cuenta ni probabilidad individual.'}
     candidate=examples.get(row['id']+'/'+symbol)
     if not candidate:
      p=next((p for p in (snap['symbols'][symbol].get('pending_book') or []) if family(p)==row['id']),None)
      if p:candidate={'plan':p,'bars':(snap['symbols'][symbol].get('bars') or {}).get('M15',[]),'created':now,'indicators':{tf:{k:v for k,v in (snap['symbols'][symbol].get('frames',{}).get(tf) or {}).items() if k in ('atr','rsi','adx','ema21','macd','volume_ratio','trend')} for tf in ('M15','H1')}}
     if candidate and candidate['bars']:
      image=self.root/'state/strategy_images'/((row['id']+'_'+symbol)+'.png')
      # Only rewrite on new bars/levels, never each quote.
      token=hashlib.sha256(json.dumps(candidate['plan'],sort_keys=True,default=str).encode()).hexdigest()
      previous=getattr(self,'image_tokens',{});self.image_tokens=previous
      if previous.get(str(image))!=token:
       chart_png(candidate['bars'],candidate['plan'],image,row['name']+' / '+symbol);previous[str(image)]=token
      per[symbol]['image_path']=str(image);per[symbol]['example']={k:v for k,v in candidate.items() if k!='bars'}
     elif (self.root/'state/strategy_images'/((row['id']+'_'+symbol)+'.png')).exists():per[symbol]['image_path']=str(self.root/'state/strategy_images'/((row['id']+'_'+symbol)+'.png'))
    row['symbols']=per;strategy_rows.append(row)
  summary={'state':'ACTUALIZADO','updated':now,'strategies':strategy_rows,'generated_hypotheses':12,'new_cases':generation,
   'reference':copy.deepcopy(self.reference),
   'scope':'Desarrollo y evaluación causal en segundo plano; experimentos sin ejecución automática. Ningún porcentaje se inventa.'}
  with self.lock:self._summary=summary
 def export_directory(self,destination):
  return export_html(self.read(),destination)
 def run(self):
  while not self.stop.is_set():
   try:self.tick()
   except Exception as exc:
    with self.lock:self._summary.update(state='ERROR',error=type(exc).__name__+': '+str(exc)[:300])
   self.wake.wait(8);self.wake.clear()

def strategy_text(row,symbol):
 m=(row.get('symbols') or {}).get(symbol) or {};actual=m.get('realized') or {};paper=m.get('paper') or {};test=m.get('holdout') or {}
 def rate(r):
  if not r.get('n'):return 'Sin muestra; no se calcula un porcentaje'
  ci=r['win_interval'];return f"{100*r['win_rate']:.1f}% observado en {r['n']} cierres; intervalo 95% {100*ci[0]:.1f}–{100*ci[1]:.1f}%"
 def amount(r,key):
  v=r.get(key)
  return 'Sin muestra' if v is None else f'{v:,.3f}' if isinstance(v,(int,float)) else str(v)
 example=m.get('example') or {};p=example.get('plan') or {};indicator_text=[]
 for tf,values in example.get('indicators',{}).items():indicator_text.append(tf+': '+', '.join(k+' '+str(round(v,3)) if isinstance(v,(int,float)) else k+' '+str(v) for k,v in values.items()))
 return '\n'.join([row['name']+' / '+symbol,row['origin'],row['rules'],
  'REALIZADO EN MT5 · '+rate(actual),'Resultado neto: '+amount(actual,'net')+'; media: '+amount(actual,'expectancy'),
  'EXPERIMENTO PAPER · '+rate(paper),'R netos estimados: '+amount(paper,'net')+'; drawdown R: '+amount(paper,'drawdown'),
  'FUERA DE MUESTRA · '+rate(test),'Días: '+str(m.get('holdout_days',0))+' · '+str(m.get('state','EN ESTUDIO')),
  m.get('scope','Aún no hay evidencia. Un índice técnico no es probabilidad de ganancias.'),
  ('EJEMPLO: '+('BUY' if p.get('side')==1 else 'SELL')+' '+str(p.get('kind'))+' · Entrada '+str(p.get('entry'))+' · SL '+str(p.get('sl'))+' · TP '+str(p.get('tp'))) if p else 'Sin ejemplo actual con niveles completos.',
  *indicator_text,
  'La activación automática de estrategias experimentales está deshabilitada. Las reglas operativas y los límites de cuenta se conservan.'])

def export_html(summary,destination):
 import html,shutil
 dest=Path(destination);dest.mkdir(parents=True,exist_ok=True);parts=[]
 from strategy_adaptation import report_text
 parts.append('<article><h2>Aprendizaje y filtros</h2><pre>'+html.escape(report_text(summary.get('adaptation') or {}))+'</pre></article>')
 for row in summary.get('strategies') or definitions():
  for symbol,metrics in (row.get('symbols') or {'BTCUSDm':{},'XAUUSDm':{}}).items():
   text=html.escape(strategy_text(row,symbol));image=metrics.get('image_path');tag=''
   if image and Path(image).is_file():
    filename=hashlib.sha256((row['id']+symbol).encode()).hexdigest()[:16]+'.png';shutil.copyfile(image,dest/filename)
    tag='<img alt="Velas e indicadores de la estrategia" src="'+filename+'">'
   parts.append('<article><h2>'+html.escape(row['name']+' / '+symbol)+'</h2><pre>'+text+'</pre>'+tag+'</article>')
 doc='<!doctype html><meta charset="utf-8"><title>AKIRA · Estrategias</title><style>body{background:#061022;color:#dceafa;font:16px sans-serif;max-width:1100px;margin:30px auto}article{border:1px solid #204960;padding:20px;margin:20px 0}h1,h2{color:#23ddf4}pre{white-space:pre-wrap;font:15px sans-serif;line-height:1.6}img{max-width:100%}</style><h1>AKIRA · Directorio de estrategias</h1><p>'+html.escape(summary.get('scope','Sin evidencia aún'))+'</p>'+''.join(parts)
 path=dest/'Estrategias_AKIRA.html';path.write_text(doc,encoding='utf-8');return str(path)
