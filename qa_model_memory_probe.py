"""Compare RAM/speed with the identical real conversation and market workload."""
import argparse,json
from pathlib import Path
from qa_conversation_rev11 import run
from akira_model_runtime import ManagedLlamaProcess

def probe(exe,model,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    original=ManagedLlamaProcess.command
    variants={'baseline':[],'no_mmap_cache128':['--load-mode','none','--cache-ram','128'],
              'no_repack_cache128':['--no-repack','--cache-ram','128']}
    result={'status':'FAILED','variants':{},'same_model_and_questions':True,'live_account_used':False}
    try:
        for name,extra in variants.items():
            def command(self,endpoint,desktop=None,flags=extra):
                return original(self,endpoint,desktop)+flags
            ManagedLlamaProcess.command=command
            row=run(exe,model,folder/(name+'.json'))
            row['extra_flags']=extra
            result['variants'][name]=row
            print('MEMORY_VARIANT_JSON='+json.dumps({'name':name,**row},ensure_ascii=False,separators=(',',':')),flush=True)
        baseline=result['variants']['baseline']
        acceptable=[name for name,row in result['variants'].items() if name!='baseline' and row['status']=='PASSED'
            and row['peak_app_and_model_mb']<=3200 and row['wall_seconds']<=baseline['wall_seconds']*1.3]
        result.update(status='PASSED' if acceptable else 'FAILED',acceptable_low_memory_variants=acceptable)
    finally:
        ManagedLlamaProcess.command=original
        (folder/'MEMORY_COMPARISON.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('AKIRA_MEMORY_COMPARISON_JSON='+json.dumps(result,ensure_ascii=False,separators=(',',':')),flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',required=True);p.add_argument('--model',required=True);p.add_argument('--reports',required=True)
    a=p.parse_args();r=probe(a.exe,a.model,a.reports);raise SystemExit(0 if r['status']=='PASSED' else 1)
