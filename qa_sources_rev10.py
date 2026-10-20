"""Live public read probes; no account, secrets, MT5 connection or broker sends."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import tempfile
import time


def run(report):
    from akira_version import BUILD_ID
    from network_tls import connection_message
    from knowledge import read_web
    from providers import public_derivatives_bundle
    from reference_library import CATALOG
    result={'build':BUILD_ID,'status':'FAILED','live_account_used':False,'broker_requests':0,
        'public_network_data':True,'references':[]}
    started=time.monotonic()
    # Different CA chains and real redirects, through the SAME library reader
    # used by the installed application. A site's access policy is not a TLS pass.
    selected=[row for row in CATALOG if row[0] in ('Programación Python','Astronomía','Economía y series')]
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(read_web,url):(name,url) for name,url,_ in selected}
        for future in as_completed(jobs):
            name,url=jobs[future]
            try:
                data=future.result()
                if len(data.get('body') or '')<100:raise ValueError('No se recibió contenido de referencia suficiente')
                result['references'].append({'name':name,'url':url,'resolved_url':data['url'],'read':True,'characters':len(data['body'])})
            except Exception as exc:
                state,detail=connection_message(exc)
                result['references'].append({'name':name,'url':url,'read':False,'state':state,'detail':detail,'diagnostic':type(exc).__name__+': '+str(exc)[:220]})
    derivatives=public_derivatives_bundle('BTC')
    result['derivatives']={k:derivatives.get(k) for k in ('state','source','coverage','missing','errors','detail','metric_timestamps','retrieved_at')}
    result['reference_successes']=sum(r['read'] for r in result['references'])
    result['status']='PASSED' if result['reference_successes']>=2 and derivatives.get('state')=='OK' else 'FAILED'
    result['scope']='Lecturas públicas reales desde el equipo de prueba; disponibilidad regional variable. Datos de derivados BTC, sin simular cobertura del oro ni un mapa de liquidaciones.'
    result['seconds']=round(time.monotonic()-started,3)
    Path(report).parent.mkdir(parents=True,exist_ok=True);Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    row=run(args.report);print(json.dumps(row,ensure_ascii=False,indent=2));raise SystemExit(0 if row['status']=='PASSED' else 1)
