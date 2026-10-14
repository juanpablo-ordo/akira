"""Medir arranque técnico con FakeMT5 y defaults de producción; nunca opera en vivo."""
import argparse
from collections import Counter
from functools import wraps
import json
from pathlib import Path
import socket
import statistics
import sys
import tempfile
import time
from unittest.mock import patch


def denied(*args,**kwargs):
    raise PermissionError('Benchmark sin red ni cuenta real')


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--source',type=Path,default=Path(__file__).resolve().parent)
    cli.add_argument('--report',type=Path,required=True)
    cli.add_argument('--samples',type=int,default=3)
    cli.add_argument('--ipc-ms',type=float,default=0.0)
    cli.add_argument('--warm-cycles',type=int,default=0)
    cli.add_argument('--clock-mode',choices=('fixed','advancing'),default='fixed')
    args=cli.parse_args()
    if not 1<=args.samples<=20 or not 0<=args.ipc_ms<=10:cli.error('samples 1..20; ipc-ms 0..10')
    if not 0<=args.warm_cycles<=30:cli.error('warm-cycles 0..30')
    sys.path.insert(0,str(args.source.resolve()))
    from akira_version import BUILD_ID
    from engine import Engine
    from execution import Gateway,Journal,Reporter,PENDING
    from settings import DEFAULT,load_config
    from tests.fake_mt5 import Clock,FakeMT5
    class AdvancingClock(Clock):
        def __init__(self):super().__init__();self.anchor=time.perf_counter()
        def __call__(self):return self.now+time.perf_counter()-self.anchor
    rows=[]
    with patch.object(socket,'getaddrinfo',denied),patch.object(socket.socket,'connect',denied),patch.object(socket.socket,'connect_ex',denied),patch.object(socket,'create_connection',denied):
        for _ in range(args.samples):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);clock=(AdvancingClock() if args.clock_mode=='advancing' else Clock());api=FakeMT5(clock);cfg=load_config(DEFAULT)
                calls=Counter();first={};timer={'start':None}
                def instrument(name,method):
                    @wraps(method)
                    def invoke(*a,**kw):
                        calls[name]+=1
                        if name=='order_send':
                            first.setdefault(a[0]['symbol'],round((time.perf_counter()-timer['start'])*1000,3))
                        if args.ipc_ms:time.sleep(args.ipc_ms/1000.0)
                        return method(*a,**kw)
                    return invoke
                for name in ('account_info','terminal_info','positions_get','orders_get','symbol_info','symbol_info_tick',
                             'symbol_select','copy_rates_from_pos','order_calc_profit','order_calc_margin','order_check',
                             'order_send','history_deals_get','history_orders_get'):
                    setattr(api,name,instrument(name,getattr(api,name)))
                g=Gateway(api,cfg,Journal(root/'journal.json'),Reporter(root/'logs',console=False),clock)
                engine=Engine(g,cfg,g.log)
                try:
                    timer['start']=time.perf_counter();view=engine.step()
                    elapsed=(time.perf_counter()-timer['start'])*1000
                    assert set(first)=={'BTCUSDm','XAUUSDm'},'No hubo intento para ambos símbolos'
                    assert len(api.orders)==2 and all(r['action']==PENDING for r in api.sent),'No confirmó una pendiente por símbolo en FakeMT5'
                    row={'first_request_ms':first,'both_symbols_attempted_ms':max(first.values()),
                        'cycle_with_view_ms':round(elapsed,3),'api_calls':dict(calls),'api_calls_total':sum(calls.values()),
                        'confirmed_pending_orders':len(api.orders),'states':view['status'],
                        'confirmed_levels':sorted((g.fingerprint(o,'order') for o in api.orders),key=lambda o:(o['symbol'],o['type']))}
                    warm=[]
                    for _ in range(args.warm_cycles):
                        clock.advance(.2)
                        for symbol in cfg['symbols']:
                            api.set_quote(symbol,api.ticks[symbol].bid,fill=False)
                        before=calls.copy();sent_before=len(api.sent);begin=time.perf_counter()
                        warm_view=engine.step()
                        warm.append({'cycle_ms':round((time.perf_counter()-begin)*1000,3),
                            'api_calls_total':sum((calls-before).values()),'new_broker_requests':len(api.sent)-sent_before,
                            'confirmed_pending_orders':len(api.orders),'states':warm_view['status']})
                        assert len(api.orders)==2 and len(api.sent)==sent_before,'El mapa inalterado no debe reenviarse'
                    row['warm_cycles']=warm;rows.append(row)
                finally:engine.close()
    result={'build':BUILD_ID,'environment':'Linux, FakeMT5, defaults de producción, cuenta sintética de 100 USD',
            'live_trading':False,'network':'blocked','simulated_ipc_ms_per_call':args.ipc_ms,'samples':rows,
            'clock_mode':args.clock_mode,
            'median_both_symbols_attempted_ms':round(statistics.median(r['both_symbols_attempted_ms'] for r in rows),3),
            'median_cycle_with_view_ms':round(statistics.median(r['cycle_with_view_ms'] for r in rows),3),
            'median_api_calls':statistics.median(r['api_calls_total'] for r in rows),
            'limits':'Datos sintéticos. No mide latencia de Exness, Windows, noticias/LLM ni ganancias.'}
    if args.warm_cycles:
        result['median_warm_cycle_ms']=round(statistics.median(w['cycle_ms'] for r in rows for w in r['warm_cycles']),3)
        result['median_warm_api_calls']=statistics.median(w['api_calls_total'] for r in rows for w in r['warm_cycles'])
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('samples',)},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
