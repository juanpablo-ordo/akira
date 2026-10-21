"""Compare actual memory policies with identical production conversation and actor."""
import argparse
import json
from pathlib import Path

from akira_model_runtime import ManagedLlamaProcess
from qa_conversation_rev11 import run


def probe(exe, model, folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    original=ManagedLlamaProcess.command
    variants={
        'current':{},
        'cache0_flash_f16':{'--cache-ram':'0','--flash-attn':'on'},
        'cache0_flash_q8':{'--cache-ram':'0','--flash-attn':'on','--cache-type-k':'q8_0','--cache-type-v':'q8_0'},
    }
    result={'status':'FAILED','variants':{},'same_model_and_questions':True,
            'same_source':'0bdbd8fb2ea167ed2df4dc97894afe039427f495','live_account_used':False,'source_sprite_component_prepared':True}
    try:
        for name,overrides in variants.items():
            launched=[]
            def command(self,endpoint,desktop=None,changes=overrides):
                args=original(self,endpoint,desktop)
                for flag,value in changes.items():
                    if flag in args:
                        index=args.index(flag)
                        if value is not None:args[index+1]=value
                    else:
                        args.append(flag)
                        if value is not None:args.append(value)
                launched[:]=args
                return args
            ManagedLlamaProcess.command=command
            row=run(exe,model,folder/(name+'.json'))
            row['overrides']=overrides;row['launched_command']=launched
            result['variants'][name]=row
            print('MEMORY_FINAL_VARIANT='+json.dumps({'name':name,**row},ensure_ascii=False,separators=(',',':')),flush=True)
        acceptable=[name for name,row in result['variants'].items() if row['status']=='PASSED']
        result.update(status='PASSED' if acceptable else 'FAILED',acceptable_low_memory_variants=acceptable)
        baseline=result['variants']['current']
        for row in result['variants'].values():
            row['elapsed_ratio_to_current']=round(row['wall_seconds']/baseline['wall_seconds'],3)
    finally:
        ManagedLlamaProcess.command=original
        (folder/'MEMORY_FINAL_COMPARISON.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('AKIRA_MEMORY_FINAL_COMPARISON_JSON='+json.dumps(result,ensure_ascii=False,separators=(',',':')),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--exe',required=True);parser.add_argument('--model',required=True);parser.add_argument('--reports',required=True)
    args=parser.parse_args();out=probe(args.exe,args.model,args.reports)
    raise SystemExit(0 if out['status']=='PASSED' else 1)
