"""Account evidence and prospective case capture. No synthetic data becomes live evidence."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timezone
import copy,csv,hashlib,json,math,queue,sqlite3,threading,time
from operation_report import closed_trades

def performance(rows):
 values=[float(r['net_usd']) for r in rows if r.get('net_usd') is not None and math.isfinite(float(r['net_usd']))]
 gain=sum(x for x in values if x>0);loss=-sum(x for x in values if x<0);curve=0;peak=0;drawdown=0
 for row in sorted(rows,key=lambda r:r.get('exit_time',0)):
  curve+=float(row['net_usd']);peak=max(peak,curve);drawdown=max(drawdown,peak-curve)
 return {'closed':len(values),'win_rate':sum(x>0 for x in values)/len(values) if values else None,
  'net_usd':sum(values) if values else None,'profit_factor':gain/loss if loss>0 else None,'drawdown_usd':drawdown if values else None,
  'mfe_recorded':sum(r.get('mfe_r') is not None for r in rows),'definition':'Cierres propios completos con comisión, swap y fee. Drawdown de cierres; no drawdown intradía de equity.'}

def scope_metrics(snapshot,cutoff=0):
 rows=closed_trades(snapshot,cutoff);out={}
 symbols=tuple((snapshot.get('symbols') or {}).keys()) or ('BTCUSDm','XAUUSDm')
 for symbol in symbols:
  own=[r for r in rows if r['symbol']==symbol and r['lane'] in ('PENDING','RUNNER')]
  out[symbol]={lane:performance([r for r in own if r['lane']==lane]) for lane in ('PENDING','RUNNER')}
 return out

def quality_text(snapshot):
 study=(snapshot or {}).get('quality_study') or {};metrics=study.get('account') or scope_metrics(snapshot or {})
 lines=['AKIRA · RESULTADOS Y ALCANCE']
 for symbol,lanes in metrics.items():
  if (snapshot.get('markets') or {}).get(symbol,{}).get('scheduled_closed'):continue
  lines.append(symbol)
  for lane,row in lanes.items():
   n=row['closed'];rate=row.get('win_rate');net=row.get('net_usd')
   lines.append(f'  {lane}: {n} cierres completos · neto '+(f'{net:+.2f} USD' if net is not None else 'sin historial completo')+(f' · ganadoras históricas {rate*100:.1f}%' if rate is not None else ''))
  count=(study.get('cases') or {}).get(symbol,0);lines.append(f'  Casos prospectivos capturados: {count}')
  lines.append('  Libros completos del selector congelados: '+str((study.get('candidate_books') or {}).get(symbol,0)))
  quotes=(study.get('recorded_quotes') or {}).get(symbol,0);lines.append(f'  Cotizaciones MT5 observadas y registradas: {quotes} · muestreo cada 30 s, no historial de cada tick')
 pairs=study.get('comparisons',0)
 replay=study.get('quote_comparison') or {}
 for name,row in replay.get('groups',{}).items():
  stats=row['holdout'];lines.append(name+' · '+row['status']+f' · {stats["pairs"]} pares de validación / {row["holdout_days"]} días')
  for selector,title in (('akira','AKIRA'),('reference','Referencia real')):
   item=stats[selector];rate=item['activation_rate'];positive=item['positive_after_activation']
   mean=item['mean_net_r']
   lines.append('  '+title+' · activación '+(f'{rate*100:.1f}%' if rate is not None else 'sin muestra')+' · resultado positivo tras activar '+(f'{positive*100:.1f}%' if positive is not None else 'sin muestra')+' · media neta R '+(f'{mean:+.3f}' if mean is not None else 'sin muestra'))
 if replay:lines += ['ESTUDIO BID/ASK · '+replay['scope'],replay['source_provenance']]
 lines+= [f'Recomendaciones reales importadas para comparar: {pairs}',
  'Cada referencia se vincula a una captura inmutable con el mismo símbolo, horario, cotización, análisis y límites. Una referencia tardía no cuenta como prospectiva.',
  'La captura y el historial permiten medir este sistema. Una ganadora pasada no demuestra la probabilidad de la próxima orden. Para confirmar superioridad hacen falta resultados posteriores de pares comparables; el sistema conserva los datos y señala lo que falta.']
 if study.get('selector_comparison'):
  from selection_trials import text
  lines+=['',text(study['selector_comparison'])]
 return '\n'.join(lines)

class QualityStudy:
 def __init__(self,root):
  self.path=Path(root)/'state'/'quality.sqlite';self.path.parent.mkdir(parents=True,exist_ok=True)
  self.stop=threading.Event();self.queue=queue.Queue(maxsize=2);self.lock=threading.RLock();self.cached={'cases':{},'comparisons':0,'account':{},'state':'Capturando casos prospectivos MT5'}
  self.auto_due=0
  with self.db() as db:
   db.executescript('CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,symbol TEXT,at REAL,bar REAL,plan TEXT,snapshot TEXT); CREATE TABLE IF NOT EXISTS references_imported(id INTEGER PRIMARY KEY,case_id TEXT,source TEXT,at REAL,plan TEXT,prospective INTEGER); CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE IF NOT EXISTS quotes(symbol TEXT,utc REAL,provider TEXT,bid REAL,ask REAL,PRIMARY KEY(symbol,utc,provider)); CREATE INDEX IF NOT EXISTS quotes_time ON quotes(utc); CREATE INDEX IF NOT EXISTS quotes_source ON quotes(provider,utc); CREATE INDEX IF NOT EXISTS cases_symbol ON cases(symbol); CREATE INDEX IF NOT EXISTS cases_time ON cases(at); CREATE INDEX IF NOT EXISTS references_case ON references_imported(case_id,source);')
   db.execute('CREATE TABLE IF NOT EXISTS candidate_books(id TEXT PRIMARY KEY,symbol TEXT,at REAL,bar REAL,plans TEXT,snapshot TEXT)')
   old=db.execute("SELECT value FROM meta WHERE key='summary'").fetchone()
   if old:
    try:self.cached=json.loads(old[0])
    except ValueError:pass
  self.thread=threading.Thread(target=self.run,name='AkiraStudy',daemon=True)
 @contextmanager
 def db(self):
  db=sqlite3.connect(self.path,timeout=5)
  try:
   with db:yield db
  finally:db.close()
 def start(self):self.thread.start()
 def close(self):
  self.stop.set()
  if self.thread.is_alive() and self.thread is not threading.current_thread():self.thread.join(timeout=5)
 def submit(self,snapshot):
  if snapshot.get('preview'):return
  row=copy.deepcopy(snapshot)
  try:self.queue.put_nowait(row)
  except queue.Full:
   try:self.queue.get_nowait();self.queue.put_nowait(row)
   except queue.Empty:pass
 def run(self):
  while not self.stop.is_set():
   try:row=self.queue.get(timeout=.25)
   except queue.Empty:continue
   try:
    self.capture(row)
    if time.monotonic()>=self.auto_due:
     self.auto_due=time.monotonic()+900
     with self.db() as db:cost=db.execute("SELECT value FROM meta WHERE key='recorded_cost_r'").fetchone()
     if cost:
      self.evaluate_selectors(float(cost[0]))
      if self.cached.get('comparisons'):self.evaluate_recorded(float(cost[0]))
   except Exception as exc:
    with self.lock:self.cached={**self.cached,'error':type(exc).__name__+': '+str(exc)[:150]}
 def summary(self):
  with self.lock:return copy.deepcopy(self.cached)
 @staticmethod
 def provider(snapshot):
  account=snapshot.get('account') or {};server=str(account.get('server') or '').strip()
  if not server or account.get('login') is None:return None
  identity=hashlib.sha256(str(account['login']).encode()).hexdigest()[:10]
  return 'MT5 · '+server[:120]+' · cuenta '+identity
 def record_quotes(self,db,snapshot,as_of):
  provider=self.provider(snapshot);valid=set()
  if not provider or snapshot.get('execution_block'):return valid
  for symbol,info in (snapshot.get('symbols') or {}).items():
   if (snapshot.get('markets') or {}).get(symbol,{}).get('scheduled_closed'):continue
   try:bid,ask,stamp=(float(info[k]) for k in ('bid','ask','quote_time'))
   except (ValueError,TypeError,KeyError):continue
   if not all(math.isfinite(x) for x in (bid,ask,stamp)) or bid<=0 or ask<bid or not -3<=as_of-stamp<=30:continue
   valid.add(symbol)
   db.execute('INSERT OR IGNORE INTO quotes VALUES (?,?,?,?,?)',(symbol,as_of,provider,bid,ask))
  # 120 days permits a chronological development period plus 20 holdout days.
  db.execute('DELETE FROM quotes WHERE utc<?',(as_of-120*86400,))
  return valid
 def capture(self,snapshot):
  if snapshot.get('preview'):raise ValueError('La vista previa no se registra como evidencia financiera')
  as_of=float(snapshot.get('as_of_utc') or 0)
  if not math.isfinite(as_of) or as_of<=0 or not snapshot.get('connected'):return
  with self.db() as db:
   valid_quotes=self.record_quotes(db,snapshot,as_of)
   for symbol,info in (snapshot.get('symbols') or {}).items():
    if (snapshot.get('markets') or {}).get(symbol,{}).get('scheduled_closed'):continue
    if self.provider(snapshot) and symbol not in valid_quotes:continue
    bar=(info.get('frames') or {}).get('M15',{}).get('last_bar')
    if not bar or float(bar)>as_of:continue
    plans=info.get('scenario_book') or [];evidence=None
    for p in plans:
     geometry=[p.get(k) for k in ('entry','sl','tp')]
     if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in geometry):continue
     # One immutable geometry/case per closed M15 bar. Repeated cycles do not inflate samples.
     identity=[symbol,bar,p.get('side'),p.get('kind')]
     if self.provider(snapshot):identity.append(self.provider(snapshot))
     configuration=snapshot.get('selection_configuration') or {}
     fingerprint=hashlib.sha256(json.dumps(configuration,sort_keys=True,default=str).encode()).hexdigest()[:16]
     identity.append(fingerprint)
     cid=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:24]
     evidence={'symbol':symbol,'as_of_utc':as_of,'bid':info.get('bid'),'ask':info.get('ask'),'frames':info.get('frames'),
      'analysis':(snapshot.get('analysis') or {}).get(symbol),'trade_risk_cap':snapshot.get('trade_risk_cap'),
      'portfolio_risk':{k:(snapshot.get('portfolio_risk') or {}).get(k) for k in ('cap_usd','reserved_usd','available_usd')},'build':snapshot.get('build')}
     evidence['quote_provider']=self.provider(snapshot)
     evidence['configuration_fingerprint']=fingerprint
     evidence['selection_configuration']=configuration
     db.execute('INSERT OR IGNORE INTO cases VALUES (?,?,?,?,?,?)',(cid,symbol,as_of,bar,json.dumps(p,default=str),json.dumps(evidence,default=str)))
    if evidence:
     pool=(snapshot.get('audit') or {}).get(symbol) or plans
     universe=[{**p,'lane':'PENDING'} for p in pool if p.get('kind') in ('LIMIT','STOP') and p.get('quality_score') is not None and all(isinstance(p.get(k),(int,float)) and math.isfinite(p[k]) and p[k]>0 for k in ('entry','sl','tp'))]
     bid=hashlib.sha256(json.dumps([symbol,bar,evidence['quote_provider'],evidence['configuration_fingerprint'],snapshot.get('build')],sort_keys=True).encode()).hexdigest()[:24]
     if universe and not db.execute('SELECT 1 FROM candidate_books WHERE id=?',(bid,)).fetchone():
      db.execute('INSERT INTO candidate_books VALUES (?,?,?,?,?,?)',(bid,symbol,as_of,bar,json.dumps(universe,default=str),json.dumps(evidence,default=str)))
   counts=dict(db.execute('SELECT symbol,count(*) FROM cases GROUP BY symbol').fetchall())
   recorded=dict(db.execute('SELECT symbol,count(*) FROM quotes GROUP BY symbol').fetchall())
   comparisons=db.execute('SELECT count(*) FROM references_imported').fetchone()[0]
   books=dict(db.execute('SELECT symbol,count(*) FROM candidate_books GROUP BY symbol').fetchall())
   stored=db.execute("SELECT value FROM meta WHERE key='paired_result'").fetchone()
   comparison={k:v for k,v in json.loads(stored[0]).items() if k not in ('paired','discarded')} if stored else {}
   summary={'state':'Casos y cotizaciones observadas capturados; seguimiento de resultados de cuenta','cases':counts,'candidate_books':books,'recorded_quotes':recorded,'comparisons':comparisons,'quote_comparison':comparison,
    'account':scope_metrics(snapshot),'updated':as_of,'historical_source':'MT5 / historial disponible','superiority_confirmed':False,
    'missing_for_superiority':'Resultados posteriores comparables de ambos selectores y validación fuera de muestra. Importar una recomendación no demuestra superioridad.'}
   selectors=db.execute("SELECT value FROM meta WHERE key='selector_result'").fetchone()
   if selectors:
    summary['selector_comparison']=json.loads(selectors[0]);summary['validated_probabilities']=summary['selector_comparison'].get('validated_probabilities',{})
   db.execute("INSERT OR REPLACE INTO meta VALUES ('summary',?)",(json.dumps(summary),))
  with self.lock:self.cached=summary
 def evaluate_recorded(self,roundtrip_cost_r):
  from paired_study import compare,PROTOCOL
  try:cost=float(roundtrip_cost_r)
  except (ValueError,TypeError):raise ValueError('Indica los costes adicionales en R; el spread ya está en bid/ask')
  if not math.isfinite(cost) or cost<0:raise ValueError('Costes en R inválidos')
  with self.db() as db:
   latest=db.execute('SELECT provider FROM quotes ORDER BY utc DESC LIMIT 1').fetchone()
   if not latest:raise ValueError('Todavía no hay cotizaciones propias registradas. AKIRA las recoge en segundo plano mientras el mercado está activo.')
   provider=latest[0];cases={};references=[]
   rows=db.execute('SELECT r.id,r.case_id,r.source,r.at,r.plan,r.prospective,c.symbol,c.at,c.bar,c.plan,c.snapshot FROM references_imported r JOIN cases c ON c.id=r.case_id').fetchall()
   for row in rows:
    if json.loads(row[10]).get('quote_provider')!=provider:continue
    cases[row[1]]={'symbol':row[6],'at':row[7],'bar':row[8],'plan':json.loads(row[9])}
    references.append({'id':row[0],'case_id':row[1],'source':row[2],'at':row[3],'plan':json.loads(row[4]),'prospective':bool(row[5])})
   if not references:raise ValueError('Importa recomendaciones reales vinculadas a capturas del mismo bróker/cuenta para comparar. No se inventa una recomendación de ChatGPT.')
   start=min(r['at'] for r in references);end=max(r['at'] for r in references)+PROTOCOL['horizon_seconds'];quotes={}
   for symbol,utc,bid,ask in db.execute('SELECT symbol,utc,bid,ask FROM quotes WHERE provider=? AND utc BETWEEN ? AND ? ORDER BY utc',(provider,start-60,end)):
    quotes.setdefault(symbol,[]).append({'symbol':symbol,'utc':utc,'bid':bid,'ask':ask,'source':provider,'cost_r':cost})
   result=compare(cases,references,quotes);result['recorded_cost_r']=cost
   result['source_provenance']='Cotizaciones observadas por AKIRA en MT5; '+provider+'. Muestras cada 30 s; no son todos los ticks ni ejecuciones del bróker.'
   result['scope']+=' Muestreo propio: puede omitir cruces entre observaciones. Costes adicionales en R elegidos por el usuario; no se deducen comisiones o swap futuros.'
   db.execute("INSERT OR REPLACE INTO meta VALUES ('recorded_cost_r',?)",(str(cost),))
   db.execute("INSERT OR REPLACE INTO meta VALUES ('paired_result',?)",(json.dumps(result),))
   with self.lock:self.cached['quote_comparison']={k:v for k,v in result.items() if k not in ('paired','discarded')};summary=copy.deepcopy(self.cached)
   db.execute("INSERT OR REPLACE INTO meta VALUES ('summary',?)",(json.dumps(summary),))
  return result
 def evaluate_selectors(self,roundtrip_cost_r):
  from selection_trials import compare_selectors
  cost=float(roundtrip_cost_r)
  if not math.isfinite(cost) or cost<0:raise ValueError('Costes adicionales en R inválidos; el spread ya está en bid/ask')
  with self.db() as db:
   rows=db.execute('SELECT id,symbol,at,bar,plan,snapshot FROM cases WHERE at>=(SELECT COALESCE(max(at),0)-120*86400 FROM cases) ORDER BY at').fetchall()
   cases=[{'id':r[0],'symbol':r[1],'at':r[2],'bar':r[3],'plan':json.loads(r[4]),'snapshot':json.loads(r[5])} for r in rows]
   books=db.execute('SELECT id,symbol,at,bar,plans,snapshot FROM candidate_books WHERE at>=(SELECT COALESCE(max(at),0)-120*86400 FROM candidate_books) ORDER BY at').fetchall()
   if books:
    cases=[{'id':r[0]+':'+str(i),'symbol':r[1],'at':r[2],'bar':r[3],'plan':p,'snapshot':json.loads(r[5])} for r in books for i,p in enumerate(json.loads(r[4]))]
   quotes={}
   for symbol,utc,provider,bid,ask in db.execute('SELECT symbol,utc,provider,bid,ask FROM quotes ORDER BY utc'):
    quotes.setdefault((symbol,provider),[]).append({'utc':utc,'bid':bid,'ask':ask,'cost_r':cost})
   result=compare_selectors(cases,quotes);result['recorded_cost_r']=cost;result['candidate_universe']='Libros completos disponibles en el audit del selector, congelados por vela M15' if books else 'Escenarios del mapa congelados; no hay aún libros completos'
   db.execute("INSERT OR REPLACE INTO meta VALUES ('recorded_cost_r',?)",(str(cost),))
   db.execute("INSERT OR REPLACE INTO meta VALUES ('selector_result',?)",(json.dumps(result),))
   with self.lock:
    self.cached['selector_comparison']=result;self.cached['validated_probabilities']=result['validated_probabilities'];summary=copy.deepcopy(self.cached)
   db.execute("INSERT OR REPLACE INTO meta VALUES ('summary',?)",(json.dumps(summary),))
  return result
 def cases(self,limit=30):
  with self.db() as db:return [{'id':r[0],'symbol':r[1],'at':r[2],'plan':json.loads(r[3])} for r in db.execute('SELECT id,symbol,at,plan FROM cases ORDER BY at DESC LIMIT ?',(int(limit),))]
 def import_references(self,path):
  count=0
  with Path(path).open(encoding='utf-8-sig',newline='') as stream,self.db() as db:
   for row in csv.DictReader(stream):
    case=db.execute('SELECT symbol,at FROM cases WHERE id=?',(str(row.get('case_id','')),)).fetchone()
    if not case:raise ValueError('Referencia sin una captura existente: '+str(row.get('case_id','')))
    if row.get('symbol')!=case[0]:raise ValueError('La referencia no corresponde al símbolo de la captura')
    source=str(row.get('source') or '').strip()
    if not source:raise ValueError('Indica la fuente real de la recomendación')
    raw_time=str(row.get('created_utc') or '').strip()
    try:at=float(raw_time)
    except ValueError:
     try:
      date=datetime.fromisoformat(raw_time.replace('Z','+00:00'))
      if date.tzinfo is None:raise ValueError('Sin zona horaria')
      at=date.timestamp()
     except ValueError:raise ValueError('created_utc debe contener la fecha real de la recomendación, con zona UTC (2026-10-10T12:00:00Z) o segundos UTC')
    side=str(row['side']).upper();kind=str(row['kind']).upper()
    entry,sl,tp=(float(row[k]) for k in ('entry','sl','tp'))
    if not all(math.isfinite(v) and v>0 for v in (entry,sl,tp,at)):raise ValueError('Referencia con números inválidos')
    if side not in ('BUY','SELL') or kind not in ('LIMIT','STOP'):raise ValueError('Tipo de referencia inválido')
    if not (sl<entry<tp if side=='BUY' else tp<entry<sl):raise ValueError('Geometría de referencia inválida')
    plan={'side':side,'kind':kind,'entry':entry,'sl':sl,'tp':tp,'source_assertion':'Recomendación importada por el usuario; origen declarado, no autenticado automáticamente'}
    existing=db.execute('SELECT 1 FROM references_imported WHERE case_id=? AND source=?',(row['case_id'],source)).fetchone()
    if existing:continue
    # A delayed reference is recorded as retrospective and cannot pass a prospective comparison.
    prospective=int(case[1]<=at<=case[1]+120)
    db.execute('INSERT INTO references_imported(case_id,source,at,plan,prospective) VALUES (?,?,?,?,?)',(row['case_id'],source,at,json.dumps(plan),prospective));count+=1
   with self.lock:
    self.cached['comparisons']=db.execute('SELECT count(*) FROM references_imported').fetchone()[0]
    summary=copy.deepcopy(self.cached)
   db.execute("INSERT OR REPLACE INTO meta VALUES ('summary',?)",(json.dumps(summary),))
  return {'imported':count,'detail':'Referencias vinculadas a sus capturas. Falta medir los resultados posteriores bajo el mismo protocolo antes de afirmar una mejora.'}
 def evaluate_quotes(self,path):
  from paired_study import load_quotes,compare
  quotes,digest=load_quotes(path)
  with self.db() as db:
   cases={r[0]:{'symbol':r[1],'at':r[2],'bar':r[3],'plan':json.loads(r[4])} for r in db.execute('SELECT id,symbol,at,bar,plan FROM cases')}
   references=[{'id':r[0],'case_id':r[1],'source':r[2],'at':r[3],'plan':json.loads(r[4]),'prospective':bool(r[5])} for r in db.execute('SELECT id,case_id,source,at,plan,prospective FROM references_imported')]
   result=compare(cases,references,quotes);result['quote_file_sha256']=digest
   db.execute("INSERT OR REPLACE INTO meta VALUES ('paired_result',?)",(json.dumps(result),))
   with self.lock:self.cached['quote_comparison']={k:v for k,v in result.items() if k not in ('paired','discarded')};summary=copy.deepcopy(self.cached)
   db.execute("INSERT OR REPLACE INTO meta VALUES ('summary',?)",(json.dumps(summary),))
  return result
 def export_comparison(self,path):
  from paired_study import write_comparison_csv
  with self.db() as db:row=db.execute("SELECT value FROM meta WHERE key='paired_result'").fetchone()
  if not row:raise ValueError('Mide los datos registrados o importa cotizaciones para comparar antes de descargar resultados')
  write_comparison_csv(json.loads(row[0]),path)
 def reference_template(self,path):
  fields=('case_id','symbol','captured_utc','source','created_utc','side','kind','entry','sl','tp')
  with Path(path).open('w',encoding='utf-8-sig',newline='') as stream:
   writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
   for row in self.cases():writer.writerow({'case_id':row['id'],'symbol':row['symbol'],'captured_utc':datetime.fromtimestamp(row['at'],timezone.utc).isoformat()})
