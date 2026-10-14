"""Frozen candidate selectors and filter ablation, evaluated without touching orders.

One decision per symbol/bar/cohort; common observed bid/ask, cost and horizon.
Policies are fixed before evaluation. Recommendations never modify live settings.
"""
from bisect import bisect_left,bisect_right
from collections import defaultdict
import hashlib,json,math,random,statistics
from paired_study import replay,PROTOCOL

POLICIES=('Calidad técnica','Calidad y cercanía','Cercanía','Calidad + estructura H1','Calidad + ADX')

def number(value,default=0):
    try:value=float(value)
    except (TypeError,ValueError):return default
    return value if math.isfinite(value) else default

def select(rows,policy):
    candidates=[]
    for row in rows:
        p=row['plan'];frames=(row.get('snapshot') or {}).get('frames') or {};f=frames.get('M15') or {};h=frames.get('H1') or {}
        if p.get('quality_score') is None:continue
        if policy=='Calidad + ADX' and number(f.get('adx'))<25:continue
        side=1 if p.get('side') in (1,'BUY') else -1
        if policy=='Calidad + estructura H1' and side*number(h.get('trend'))<=0:continue
        q=number(p.get('quality_score'));a=number(p.get('activation_score'))
        score=a if policy=='Cercanía' else .75*q+.25*a if policy=='Calidad y cercanía' else q
        candidates.append((score,str(row['id']),row))
    return max(candidates,key=lambda x:(x[0],x[1]))[2] if candidates else None

def interval(deltas,alpha=.05):
    by_day=defaultdict(list)
    for stamp,value in deltas:by_day[int(stamp//86400)].append(value)
    daily=[statistics.mean(v) for v in by_day.values()]
    if len(daily)<2:return None
    rng=random.Random(1620);samples=sorted(statistics.mean(rng.choices(daily,k=len(daily))) for _ in range(4000))
    return [samples[int(len(samples)*alpha/2)],samples[min(len(samples)-1,int(len(samples)*(1-alpha/2)))]]

def metrics(rows):
    active=[r for r in rows if r['activated']];values=[r['net_r'] for r in rows]
    return {'decisions':len(rows),'activated':len(active),'activation_rate':len(active)/len(rows) if rows else None,
      'positive_after_activation':sum(r['net_r']>0 for r in active)/len(active) if active else None,
      'mean_net_r':statistics.mean(values) if values else None,
      'mean_mfe_r':statistics.mean(r['mfe_r'] for r in active) if active else None,
      'mean_mae_r':statistics.mean(r['mae_r'] for r in active) if active else None}

def cell(plan):
    return str(plan.get('kind'))+':'+str(int(number(plan.get('quality_score'))//10))+':'+str(int(number(plan.get('activation_score'))//25))

def calibrate(development,holdout):
    models={};base=POLICIES[0]
    for target in ('activation','favorable_given_activation'):
        def samples(rows):
            out=[]
            for row in rows:
                result=row['results'][base]
                if target=='favorable_given_activation' and not result['activated']:continue
                y=int(result['activated']) if target=='activation' else int(result['net_r']>0)
                out.append((cell(row['baseline_plan']),y,row['start']))
            return out
        train=samples(development);test=samples(holdout);bins=defaultdict(list)
        for key,y,stamp in train:bins[key].append(y)
        trained={key:(sum(v)+1)/(len(v)+2) for key,v in bins.items() if len(v)>=40 and min(sum(v),len(v)-sum(v))>=5}
        if not train or len(test)<200:continue
        baseline=statistics.mean(y for _,y,_ in train);covered=[(key,y,stamp) for key,y,stamp in test if key in trained]
        days={int(stamp//86400) for _,_,stamp in covered}
        if len(covered)<200 or len(days)<30 or len(covered)/len(test)<.8:continue
        improvement=[(stamp,(baseline-y)**2-(trained[key]-y)**2) for key,y,stamp in covered]
        ci=interval(improvement,.025)
        groups=defaultdict(list)
        for key,y,stamp in covered:groups[key].append(y)
        calibration=sum(len(v)*abs(trained[key]-statistics.mean(v)) for key,v in groups.items())/len(covered)
        if not ci or ci[0]<=0 or calibration>.1:continue
        models[target]={'bins':trained,'train_counts':{k:len(v) for k,v in bins.items() if k in trained},
            'holdout_cases':len(covered),'holdout_days':len(days),'brier':statistics.mean((trained[k]-y)**2 for k,y,_ in covered),
            'baseline_brier':statistics.mean((baseline-y)**2 for _,y,_ in covered),'brier_improvement_interval':ci,
            'calibration_error':calibration,'scope':'Estimación de replay con parámetros congelados, mismo proveedor y costes; no probabilidad de ejecución ni ganancia de cuenta.'}
    return models

def compare_selectors(cases,quotes,protocol=PROTOCOL):
    grouped=defaultdict(list)
    for row in cases:
        evidence=row.get('snapshot') or {};provider=evidence.get('quote_provider')
        if not provider:continue
        config=evidence.get('configuration_fingerprint','legacy');build=evidence.get('build','legacy')
        grouped[(row['symbol'],provider,build,config,row['bar'])].append(row)
    quotes={key:sorted(value,key=lambda r:r['utc']) for key,value in quotes.items()}
    times={key:[q['utc'] for q in value] for key,value in quotes.items()}
    outcomes=defaultdict(list);discarded=defaultdict(int)
    for (symbol,provider,build,config,bar),rows in grouped.items():
        cohort=' / '.join((symbol,provider,str(build),str(config)));start=min(r['at'] for r in rows)
        selected={p:select(rows,p) for p in POLICIES}
        if not selected[POLICIES[0]]:discarded['Sin candidata con índice técnico']+=1;continue
        key=(symbol,provider);all_quotes=quotes.get(key,[]);stamps=times.get(key,[])
        window=all_quotes[bisect_left(stamps,start):bisect_right(stamps,start+protocol['horizon_seconds'])]
        results={};cache={};complete=True
        for policy,row in selected.items():
            if row is None:results[policy]={'complete':True,'activated':False,'net_r':0,'mfe_r':0,'mae_r':0,'state':'FILTRO: SIN OPERACIÓN'};continue
            try:
                if row['id'] not in cache:cache[row['id']]=replay(row['plan'],window,start,protocol)
                results[policy]=cache[row['id']]
                complete=complete and bool(results[policy]['complete'])
            except (KeyError,ValueError,TypeError):complete=False
        if not complete:discarded['Cobertura incompleta o geometría inválida']+=1;continue
        outcomes[cohort].append({'start':start,'bar':bar,'results':results,'baseline_plan':selected[POLICIES[0]]['plan']})
    groups={}
    for cohort,rows in outcomes.items():
        rows.sort(key=lambda r:r['start']);days=sorted({int(r['start']//86400) for r in rows})
        cut=max(1,int(len(days)*(1-protocol['holdout_fraction'])))
        development=set(days[:cut]);training=[r for r in rows if int(r['start']//86400) in development];holdout=[r for r in rows if int(r['start']//86400) not in development]
        n_days=len({int(r['start']//86400) for r in holdout})
        enough=len(holdout)>=protocol['minimum_holdout_pairs'] and n_days>=protocol['minimum_holdout_days']
        policies={};base=POLICIES[0]
        for policy in POLICIES:
            stats=metrics([r['results'][policy] for r in holdout])
            delta=[(r['start'],r['results'][policy]['net_r']-r['results'][base]['net_r']) for r in holdout]
            ci=interval(delta,.05/(len(POLICIES)-1)) if policy!=base else None
            advantage=bool(enough and ci and ci[0]>0)
            daily=defaultdict(list)
            for stamp,value in delta:daily[int(stamp//86400)].append(value)
            policies[policy]={**stats,'delta_net_r':statistics.mean(statistics.mean(v) for v in daily.values()) if daily else None,
                'simultaneous_interval':ci,'advantage':advantage,
                'status':'Ventaja en este replay fuera de muestra' if advantage else 'Sin ventaja demostrada' if enough else 'Muestra insuficiente'}
        better=[p for p in POLICIES[1:] if policies[p]['advantage']]
        recommendation=max(better,key=lambda p:policies[p]['delta_net_r']) if better else None
        groups[cohort]={'observed_decisions':len(rows),'development_days':len(development),'holdout_days':n_days,
            'holdout_decisions':len(holdout),'policies':policies,'recommendation':recommendation,'calibrated_models':calibrate(training,holdout),
            'apply_automatically':False,'status':'Propuesta para revisar; no cambia trading' if recommendation else 'Conservar configuración; falta evidencia de mejora'}
    digest=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest()
    return {'protocol':dict(protocol),'protocol_sha256':digest,'groups':groups,'discarded':dict(discarded),
        'validated_probabilities':{cohort:row['calibrated_models'] for cohort,row in groups.items() if row['calibrated_models']},'superiority_confirmed':False,
        'scope':'Selectores y ablación de filtros sobre el mismo libro congelado. División cronológica por días, costes aportados, bid/ask observado y riesgo R. Intervalos agrupados por día y ajuste por cuatro comparaciones. No estima ganancias de una orden individual ni ejecución MT5.',
        'missing':'Los escenarios de análisis pueden no ser enviables. Comparar selectores en replay no confirma el mejor sistema posible, ni sustituye recomendaciones reales de ChatGPT, latencia, trailing o ejecución del bróker.'}

def text(result):
    lines=['SELECTORES Y APORTE DE FILTROS · FUERA DE MUESTRA',result.get('scope','')]
    if not result.get('groups'):lines.append('Aún no hay decisiones con cobertura bid/ask completa y costes definidos. La captura continúa en segundo plano.')
    for cohort,row in result.get('groups',{}).items():
        lines.append(cohort+'\n  Validación: '+str(row['holdout_decisions'])+' decisiones / '+str(row['holdout_days'])+' días.')
        for name,value in row['policies'].items():
            mean=value['mean_net_r'];lines.append('  '+name+': '+(f'{mean:+.3f} R' if mean is not None else 'sin muestra')+' · '+value['status'])
        lines.append('  '+row['status']+(' · '+row['recommendation'] if row['recommendation'] else ''))
    if result.get('discarded'):lines.append('Descartes: '+str(result['discarded']))
    lines.append(result.get('missing',''));return '\n'.join(lines)
