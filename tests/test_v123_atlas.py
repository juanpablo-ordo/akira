import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import install_release
from assistant_akira import AkiraAssistant
from settings import DEFAULT
from strategy import Bar, Frame, build_presence_reserve_pendings
from collections import Counter


def frame(name, closes, atr, lows=(), highs=(), trend=0.0):
    bars=[]
    for i,c in enumerate(closes):
        bars.append(Bar(1000+i*60,c,c+atr*.35,c-atr*.35,c,1.0))
    return Frame(name,tuple(bars),atr,closes[-1],closes[-1],trend,1.0,tuple(lows),tuple(highs),50.0,0.0,closes[-1],closes[-1]-atr,closes[-1]+atr,'range',{'ema50':closes[-1],'ema200':closes[-1],'adx':18.0})


class AtlasV123Tests(unittest.TestCase):
    def test_runtime_mutable_files_do_not_block_activation_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'source'; source.mkdir(); runtime=root/'runtime'; diag=root/'diag'; diag.mkdir(); legacy=root/'legacy'; legacy.mkdir()
            cfg=copy.deepcopy(DEFAULT); cfg['mode']='observe'; cfgpath=root/'cfg.json'; cfgpath.write_text(json.dumps(cfg),encoding='utf-8')
            (legacy/'akira_config.json').write_text(json.dumps(cfg),encoding='utf-8')
            (legacy/'logs').mkdir(); (legacy/'logs'/'eventos_2026-10-07.jsonl').write_text('old\n',encoding='utf-8')
            (source/'Akira.py').write_text('# app\n',encoding='utf-8')
            (source/'akira_version.py').write_text('BUILD_ID='+repr(install_release.BUILD_ID),encoding='utf-8')
            (source/'akira_config.json').write_text(json.dumps(cfg),encoding='utf-8')
            (source/'logs').mkdir(); (source/'logs'/'eventos_2026-10-07.jsonl').write_text('packaged\n',encoding='utf-8')
            (source/'VALIDACION_V12.json').write_text(json.dumps({'build':install_release.BUILD_ID,'tests':1}),encoding='utf-8')
            manifest={}
            for f in source.rglob('*'):
                if f.is_file() and f.name!='PACKAGE_SHA256.json': manifest[f.relative_to(source).as_posix()]=hashlib.sha256(f.read_bytes()).hexdigest()
            (source/'PACKAGE_SHA256.json').write_text(json.dumps(manifest),encoding='utf-8')
            (diag/'INSTALL_RESULT_AKIRA.json').write_text(json.dumps({'build':install_release.BUILD_ID,'status':'PASSED','exit_code':0,'child_exit_code':0,'collected':1,'tests_run':1,'failures':0,'errors':0,'skipped':0}),encoding='utf-8')
            ready=install_release.prepare_release(source,runtime,cfgpath,diag,legacy)
            release=Path(ready['root'])
            # restored logs are intentionally different from packaged bytes
            self.assertEqual((release/'logs'/'eventos_2026-10-07.jsonl').read_text(encoding='utf-8'),'old\n')
            # activation integrity ignores mutable runtime data but still checks code
            install_release.check_ready(runtime,release)
            (release/'Akira.py').write_text('tampered',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'alterado'):
                install_release.check_ready(runtime,release)

    def test_presence_reserve_comes_from_observed_h1_h4_swings(self):
        current=100.0
        frames={
            'M1':frame('M1',[99.6,99.8,100.0],.4,trend=.1),
            'M15':frame('M15',[99.0,99.5,100.0],1.0,trend=.1),
            'H1':frame('H1',[96,98,100],2.0,lows=((94.0,900),(96.0,940)),highs=((104.0,920),(106.0,960)),trend=.1),
            'H4':frame('H4',[94,97,100],4.0,lows=((90.0,800),(93.0,850)),highs=((108.0,820),(112.0,870)),trend=.0),
        }
        rows=build_presence_reserve_pendings(frames,{'presence_structural_reserve':True},Counter())
        self.assertTrue(rows)
        self.assertTrue(all(x.key.startswith('SWING:PRESENCE:') for x in rows))
        self.assertTrue(any(x.side==1 and x.level<current for x in rows))
        self.assertTrue(any(x.side==-1 and x.level>current for x in rows))
        self.assertTrue(all('PRESENCE RESERVE' in x.reason for x in rows))

    def test_aggressive_research_uses_multiple_web_queries_and_youtube(self):
        with tempfile.TemporaryDirectory() as td:
            cfg=copy.deepcopy(DEFAULT); bot=AkiraAssistant(cfg,Path(td)); calls=[]
            def source(name,args):
                calls.append((name,args.get('query','')))
                if name=='research_public_web': return {'results':[{'title':'Web','url':'https://example.com/'+str(len(calls)),'text':'dato'}]}
                if name=='search_youtube': return {'results':[{'title':'Video','url':'https://youtube.com/watch?v='+str(len(calls)),'description':'dato'}]}
                return {}
            with patch.object(bot,'_source_tool',side_effect=source), patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['qwen3:8b']}), patch('assistant_akira.ollama_agent',return_value='Respuesta investigada'):
                answer=bot.reply('Analiza el mercado de oro y dime qué contexto hay',{'symbols':{},'account':{},'orders':[],'positions':[],'status':{},'research':{},'as_of_utc':__import__('time').time()},use_cloud=False)
            self.assertIn('Respuesta investigada',answer)
            self.assertGreaterEqual(sum(1 for n,_ in calls if n=='research_public_web'),2)
            self.assertGreaterEqual(sum(1 for n,_ in calls if n=='search_youtube'),1)

    def test_project_builder_can_write_read_and_zip_without_touching_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            bot=AkiraAssistant(copy.deepcopy(DEFAULT),Path(td))
            w=bot._write_project({'project':'demo_bot','path':'main.py','content':'print("hola")\n'})
            self.assertTrue(w['ok'])
            r=bot._read_project({'project':'demo_bot','path':'main.py'})
            self.assertIn('print',r['content'])
            z=bot._zip_project({'project':'demo_bot'})
            self.assertTrue(Path(z['path']).is_file())
            self.assertFalse((Path(td)/'Akira.py').exists())


if __name__=='__main__':
    unittest.main()
