"""Fixed-protocol, chronological paired quote replay. Never labels replay as live P/L."""
from collections import defaultdict
from datetime import datetime,timezone
import csv,hashlib,json,math,random,statistics
from pathlib import Path
from bisect import bisect_left,bisect_right

PROTOCOL={'version':2,'entry_expiry_seconds':14400,'horizon_seconds':86400,
 'maximum_quote_gap_seconds':60,'holdout_fraction':.30,'minimum_holdout_pairs':50,
 'minimum_holdout_days':20,'meaning':'Simulación de cotizaciones bid/ask aportadas, por par y con riesgo normalizado. No rentabilidad MT5 ni probabilidad de la siguiente orden.'}

def plan_values(plan):
 side=str(plan.get('side','')).upper();side='BUY' if side in ('1','BUY') else 'SELL' if side in ('-1','SELL') else ''
 kind=str(plan.get('kind','')).upper().replace('BUY_','').replace('SELL_','')
 values=[float(plan[k]) for k in ('entry','sl','tp')]
 if not side or kind not in ('LIMIT','STOP','MARKET') or not all(math.isfinite(v) and v>0 for v in values):raise ValueError('Parámetros incompletos o inválidos')
 entry,sl,tp=values
 if not (sl<entry<tp if side=='BUY' else tp<entry<sl):raise ValueError('SL/entrada/TP fuera de orden')
 return side,kind,entry,sl,tp

def load_quotes(path):
 out=[];source=None
 if Path(path).stat().st_size>100_000_000:raise ValueError('Archivo de cotizaciones demasiado grande (máximo 100 MB)')
 with Path(path).open(encoding='utf-8-sig',newline='') as stream:
  for index,row in enumerate(csv.DictReader(stream),2):
   try:
    stamp,bid,ask=(float(row[k]) for k in ('utc','bid','ask'));provider=str(row['source']).strip();symbol=str(row['symbol']).strip()
    cost=float(row.get('roundtrip_cost_r') or 0)
    if not all(math.isfinite(x) for x in (stamp,bid,ask,cost)) or stamp<=0 or bid<=0 or ask<bid or cost<0 or not provider or not symbol:raise ValueError()
   except (ValueError,KeyError,TypeError):raise ValueError(f'Cotización inválida en fila {index}')
   # Multiple symbols are allowed, multiple providers for one symbol are not.
   out.append({'utc':stamp,'bid':bid,'ask':ask,'source':provider,'symbol':symbol,'cost_r':cost})
 if not out:raise ValueError('No hay cotizaciones para evaluar')
 grouped=defaultdict(list)
 for row in out:grouped[row['symbol']].append(row)
 for symbol,rows in grouped.items():
  if len({r['source'] for r in rows})!=1:raise ValueError('No mezcles brókers o mercados en '+symbol)
  rows.sort(key=lambda r:r['utc'])
  if any(a['utc']>=b['utc'] for a,b in zip(rows,rows[1:])):raise ValueError('Cotizaciones repetidas: '+symbol)
 return dict(grouped),hashlib.sha256(Path(path).read_bytes()).hexdigest()

def replay(plan,quotes,start,protocol=PROTOCOL):
 side,kind,entry,sl,tp=plan_values(plan);end=start+protocol['horizon_seconds'];expiry=start+protocol['entry_expiry_seconds']
 rows=[r for r in quotes if start<=r['utc']<=end]
 gap=protocol['maximum_quote_gap_seconds']
 if len(rows)<2 or rows[0]['utc']-start>gap:
  return {'state':'SIN COBERTURA COMPLETA','complete':False}
 direction=1 if side=='BUY' else -1;unit=abs(entry-sl);fill=None;activated=None;mfe=0;mae=0;previous=start
 for row in rows:
  stamp=row['utc'];quote=row['ask'] if side=='BUY' else row['bid'];exit_quote=row['bid'] if side=='BUY' else row['ask']
  # Require uninterrupted observations only while this outcome is unresolved.
  # A later gold rollover must not erase a TP/SL or an expired entry already observed.
  if fill is None and stamp>expiry and expiry-previous<=gap:
   return {'state':'NO ACTIVADA','complete':True,'activated':False,'net_r':0,'mfe_r':0,'mae_r':0}
  if stamp-previous>gap:return {'state':'HUECOS EN COTIZACIONES','complete':False}
  previous=stamp
  if fill is None:
   eligible=(kind=='MARKET' or (quote<=entry if side=='BUY' else quote>=entry)) if kind!='STOP' else (quote>=entry if side=='BUY' else quote<=entry)
   if stamp>expiry:
    return {'state':'NO ACTIVADA','complete':True,'activated':False,'net_r':0,'mfe_r':0,'mae_r':0}
   if not eligible:continue
   fill=quote;activated=stamp
  gross=direction*(exit_quote-fill)/unit;mfe=max(mfe,gross);mae=max(mae,-gross)
  hit_sl=(exit_quote<=sl if side=='BUY' else exit_quote>=sl)
  hit_tp=(exit_quote>=tp if side=='BUY' else exit_quote<=tp)
  if hit_sl or hit_tp:
   # A stop can slip; a limit target cannot claim a better gap fill.
   exit_price=exit_quote if hit_sl else tp
   return {'state':'SL' if hit_sl else 'TP','complete':True,'activated':True,'activated_utc':activated,'exit_utc':stamp,
    'fill':fill,'exit':exit_price,'net_r':direction*(exit_price-fill)/unit-row['cost_r'],'mfe_r':mfe,'mae_r':mae}
 if fill is None:
  if expiry-previous>gap:return {'state':'SIN COBERTURA COMPLETA','complete':False}
  return {'state':'NO ACTIVADA','complete':True,'activated':False,'net_r':0,'mfe_r':0,'mae_r':0}
 if end-rows[-1]['utc']>gap:return {'state':'SIN COBERTURA COMPLETA','complete':False}
 last=rows[-1]
 return {'state':'FIN DE HORIZONTE','complete':True,'activated':True,'activated_utc':activated,'exit_utc':last['utc'],
  'net_r':direction*((last['bid'] if side=='BUY' else last['ask'])-fill)/unit-last['cost_r'],'mfe_r':mfe,'mae_r':mae}

def confidence_by_day(pairs):
 days=defaultdict(list)
 for p in pairs:days[datetime.fromtimestamp(p['start'],timezone.utc).strftime('%Y-%m-%d')].append(p['delta_r'])
 daily=[statistics.mean(v) for v in days.values()]
 if len(daily)<2:return None
 rng=random.Random(1600);means=sorted(statistics.mean(rng.choices(daily,k=len(daily))) for _ in range(2000))
 return [means[49],means[1949]]

def statistics_for(pairs):
 rows=[p for p in pairs if p['complete']];out={'pairs':len(rows)}
 for name in ('akira','reference'):
  values=[p[name]['net_r'] for p in rows];active=[p[name] for p in rows if p[name]['activated']]
  loss=-sum(v for v in values if v<0);gain=sum(v for v in values if v>0)
  out[name]={'activation_rate':len(active)/len(rows) if rows else None,
   'positive_after_activation':sum(p['net_r']>0 for p in active)/len(active) if active else None,
   'mean_net_r':statistics.mean(values) if values else None,'profit_factor':gain/loss if loss else None,
   'mfe_r':statistics.mean(p['mfe_r'] for p in active) if active else None,'mae_r':statistics.mean(p['mae_r'] for p in active) if active else None}
 out['delta_r']=statistics.mean(p['delta_r'] for p in rows) if rows else None
 out['confidence_95_by_day']=confidence_by_day(rows)
 return out

def compare(cases,references,quotes,protocol=PROTOCOL):
 paired=[];discarded=[]
 # Slice each case's fixed horizon once; long account histories must not be
 # scanned again for every reference in the background study.
 ordered={symbol:sorted(rows,key=lambda r:r['utc']) for symbol,rows in quotes.items()}
 stamps={symbol:[r['utc'] for r in rows] for symbol,rows in ordered.items()}
 for ref in references:
  case=cases.get(ref['case_id'])
  if not case:continue
  symbol=case['symbol'];start=max(case['at'],ref['at'])
  if not ref.get('prospective'):
   discarded.append({'case_id':ref['case_id'],'reason':'Referencia retrospectiva; no entra en comparación prospectiva'});continue
  try:
   # Freeze AKIRA and the real reference. Both begin at the same reference time;
   # account outcomes and these fixed-parameter hypothetical outcomes stay apart.
   rows=ordered.get(symbol,[]);times=stamps.get(symbol,[])
   window=rows[bisect_left(times,start):bisect_right(times,start+protocol['horizon_seconds'])]
   akira=replay(case['plan'],window,start,protocol);reference=replay(ref['plan'],window,start,protocol)
  except ValueError as exc:
   discarded.append({'case_id':ref['case_id'],'reason':str(exc)});continue
  complete=akira['complete'] and reference['complete']
  paired.append({'case_id':ref['case_id'],'reference_id':ref['id'],'source':ref['source'],'symbol':symbol,
   'lane':case['plan'].get('lane','PENDING'),'start':start,'akira':akira,'reference':reference,'complete':complete,
   'delta_r':akira['net_r']-reference['net_r'] if complete else None})
 groups={}
 for symbol in sorted({p['symbol'] for p in paired}):
  for lane in sorted({p['lane'] for p in paired if p['symbol']==symbol}):
   # One pair per original bar avoids inflating evidence with four quadrants.
   unique={}
   for p in sorted((p for p in paired if p['symbol']==symbol and p['lane']==lane and p['complete']),key=lambda p:(p['start'],p['reference_id'])):
    unique.setdefault(cases[p['case_id']].get('bar',p['start']),p)
   rows=sorted(unique.values(),key=lambda p:p['start']);cut=max(1,int(len(rows)*(1-protocol['holdout_fraction']))) if rows else 0
   holdout=rows[cut:];days={int(p['start']//86400) for p in holdout};stats=statistics_for(holdout);ci=stats['confidence_95_by_day']
   enough=len(holdout)>=protocol['minimum_holdout_pairs'] and len(days)>=protocol['minimum_holdout_days']
   groups[symbol+' / '+lane]={'all_pairs':len(rows),'development_pairs':cut,'holdout_days':len(days),'holdout':stats,
    'advantage_in_quote_replay':bool(enough and ci and ci[0]>0),
    'status':'Ventaja en esta simulación fuera de muestra' if enough and ci and ci[0]>0 else ('Sin evidencia de ventaja' if enough else 'Muestra de validación insuficiente')}
 return {'protocol':dict(protocol),'groups':groups,'paired':paired,'discarded':discarded,
  'superiority_confirmed':False,'source_provenance':'Proveedor declarado en CSV; autenticidad y continuidad de ticks no verificadas automáticamente',
  'scope':'Parámetros congelados; inicio común, bid/ask, deslizamiento observado, costes R aportados y horizonte fijo. Cobertura continua hasta resolución, caducidad o final del horizonte. Sin modificación/trailing del bot. La ventaja de replay no confirma superioridad de ejecución real.'}

def write_comparison_csv(result,path):
 fields=('symbol','lane','case_id','source','start','complete','akira_state','reference_state','akira_net_r','reference_net_r','delta_r')
 with Path(path).open('w',encoding='utf-8-sig',newline='') as stream:
  writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
  for p in result['paired']:
   safe={k:("'"+p[k] if isinstance(p.get(k),str) and p[k].startswith(('=','+','-','@')) else p.get(k)) for k in fields[:6]}
   writer.writerow({**safe,'akira_state':p['akira']['state'],'reference_state':p['reference']['state'],
    'akira_net_r':p['akira'].get('net_r'),'reference_net_r':p['reference'].get('net_r'),'delta_r':p['delta_r']})
