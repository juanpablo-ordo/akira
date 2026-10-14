import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

from settings import DEFAULT,load_config
from research import finite_bias,ContextWorker
from assistant_akira import AkiraAssistant
from engine import Engine
from tests.fixtures import PendingCase


class OracleV129Tests(unittest.TestCase):
    def test_defaults_enable_dual_stage_trace_and_notifications(self):
        cfg=load_config(copy.deepcopy(DEFAULT))
        self.assertEqual(cfg['schema_version'],1600)
        self.assertLessEqual(float(cfg['research']['local_ai_summary_seconds']),60.0)
        self.assertTrue(cfg['research']['local_ai_double_check'])
        self.assertTrue(cfg['assistant']['show_research_trace'])
        self.assertTrue(cfg['desktop']['notifications'])
        self.assertTrue(cfg['desktop']['notify_deep_analysis'])

    def test_finite_bias_keeps_only_known_scenario_tokens(self):
        row=finite_bias({'bias':-.5,'confidence':.3,'preferred':['SELL_LIMIT','BOGUS'],'avoid':['BUY_STOP'],'note':'x','thesis':'y'})
        self.assertEqual(row['preferred'],['SELL_LIMIT'])
        self.assertEqual(row['avoid'],['BUY_STOP'])
        self.assertEqual(row['thesis'],'y')

    def test_chat_progress_callback_exposes_search_stage(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        cfg=load_config(copy.deepcopy(DEFAULT));events=[]
        bot=AkiraAssistant(cfg,Path(tmp.name),progress_callback=events.append)
        fake={'results':[{'title':'A','url':'https://a.example/x','text':'dato'}]}
        with patch('assistant_akira.lookup_current_fact',return_value=fake), patch('assistant_akira.read_web',return_value={'title':'A','body':'contenido'}):
            bot._source_tool('research_public_web',{'query':'oro hoy'})
        self.assertTrue(any('BUSCANDO' in e.get('stage','') for e in events))
        self.assertTrue(any('LEYENDO' in e.get('stage','') for e in events))
        self.assertTrue(any('ENCONTRADO' in e.get('stage','') for e in events))

    def test_context_read_exposes_deep_review_and_real_source_timestamp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        cfg=load_config(copy.deepcopy(DEFAULT));w=ContextWorker(cfg,Path(tmp.name),clock=lambda:200.0)
        w.sources={'local_ai':{'data':{'XAUUSDm':{'bias':-.4,'confidence':.2,'preferred':['SELL_LIMIT'],'avoid':[],'note':'n','thesis':'t'},'_meta':{'model':'qwen3:14b'}},'updated':150.0,'error':''}}
        out=w.read()
        self.assertIn('XAUUSDm',out['deep_review'])
        self.assertIn('1970-01-01T00:02:30',out['updated'])
        self.assertEqual(out['deep_review_meta']['model'],'qwen3:14b')


class OracleEngineV129Tests(PendingCase,unittest.TestCase):
    def test_new_source_revision_rebuilds_map_even_when_fused_bias_is_unchanged(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close);e.warmup()
        symbol='BTCUSDm';q=self.g.quote(symbol)
        e.planner.research_context={'fusion':{symbol:{'bias':0,'confidence':0}},'sources':{'news':{'updated':10}}}
        first=e.scan_plans(symbol,q,force=True)
        marker1=e.map_cache[symbol]['marker']
        e.planner.research_context={'fusion':{symbol:{'bias':0,'confidence':0}},'sources':{'news':{'updated':11}}}
        second=e.scan_plans(symbol,q,force=False)
        marker2=e.map_cache[symbol]['marker']
        self.assertNotEqual(marker1,marker2)
        self.assertIsInstance(first,list);self.assertIsInstance(second,list)

if __name__=='__main__':unittest.main()
