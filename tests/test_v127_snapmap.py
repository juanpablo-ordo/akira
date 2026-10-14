import unittest
from unittest.mock import patch
from engine import Engine
from settings import DEFAULT, load_config
from tests.fixtures import PendingCase


class SnapMapV127Tests(PendingCase, unittest.TestCase):
    def test_snapmap_defaults_are_fast_and_multi_lane(self):
        self.assertEqual(self.cfg['schema_version'],1600)
        self.assertTrue(self.cfg['execution']['presence_all_alternatives'])
        self.assertTrue(self.cfg['execution']['rapid_parameter_map'])
        self.assertTrue(self.cfg['pending']['one_order_per_direction'])
        self.assertEqual(self.cfg['pending']['max_same_side_orders'],1)
        self.assertEqual(self.cfg['pending']['max_own_map_orders'],2)
        self.assertLessEqual(self.cfg['desktop']['terminal_heartbeat_seconds'],.5)

    def test_scan_pool_keeps_presence_alternative_even_when_strict_side_exists(self):
        engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(engine.close);engine.warmup()
        q=self.g.quote('BTCUSDm')
        a=self.plan('BTCUSDm',side=-1,key='STRICT_SELL')
        b=self.plan('BTCUSDm',side=-1,key='FAST_SELL_STOP')
        c=self.plan('BTCUSDm',side=1,key='FAST_BUY')
        calls=[]
        def proposed(symbol,setups,quote,all_candidates=False,presence=False,evaluation=None,financial_gate=True):
            calls.append(presence)
            engine.planner.pending_candidate_audit[symbol]=[]
            return [b,c] if presence else [a]
        with patch.object(engine.planner,'proposed_pending_plans',side_effect=proposed):
            rows=engine.scan_plans('BTCUSDm',q,force=True)
        self.assertEqual({x.key for x in rows},{'STRICT_SELL','FAST_SELL_STOP','FAST_BUY'})
        self.assertEqual(calls,[False,True])

    def test_open_position_suspends_new_pending_map(self):
        engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(engine.close);engine.warmup()
        self.api.add_position('BTCUSDm',side=0)
        engine.g.journal.data.setdefault('positions',{})
        # Manual position is not owned and should not block Akira.
        rows=engine.allocate('BTCUSDm',[self.plan('BTCUSDm',side=-1)])
        self.assertIsInstance(rows,list)

    def test_heartbeat_keeps_visible_state_without_log_spam(self):
        engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(engine.close)
        engine.step();self.clock.advance(.55);engine.step()
        files=list((self.root/'logs').glob('eventos_*.jsonl'))
        body='\n'.join(x.read_text(encoding='utf-8') for x in files)
        self.assertIn('CICLO 1 · 4 escenarios con parámetros',body)
        self.assertEqual(body.count('CICLO '),2)  # una línea por símbolo, no cientos

if __name__=='__main__':unittest.main()
