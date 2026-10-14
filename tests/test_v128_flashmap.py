import unittest
from engine import Engine
from strategy import build_snap_analyst_pendings
from tests.fixtures import PendingCase


class FlashMapV128Tests(PendingCase, unittest.TestCase):
    def test_flashmap_defaults_prioritize_fast_parameters_without_forcing_risk(self):
        self.assertEqual(self.cfg['schema_version'],1600)
        self.assertGreaterEqual(float(self.cfg['execution']['rapid_parameter_map_refresh_seconds']),.15)
        self.assertFalse(self.cfg['execution']['suspend_new_map_while_position_open'])
        self.assertTrue(self.cfg['execution']['instant_four_quadrant_book'])
        self.assertFalse(self.cfg['risk']['min_lot_structural_override_enabled'])

    def test_snap_analyst_builds_limit_and_stop_for_both_directions(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close);e.warmup()
        for symbol,cache in e.planner.caches.items():
            rows=build_snap_analyst_pendings(cache.frames,self.cfg['symbol_profiles'][symbol],{})
            self.assertTrue(rows)
            self.assertTrue(any(x.kind=='STOP' for x in rows))
            current=cache.frames['M1'].bars[-1].close
            for x in rows:
                if x.kind=='LIMIT':self.assertGreater(x.side*(current-x.level),0)
                else:self.assertGreater(x.side*(x.level-current),0)
                self.assertGreater(x.side*(x.level-x.stop),0)
                self.assertGreater(x.side*(x.target-x.level),0)

    def test_first_view_exposes_four_parameter_quadrants(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close)
        view=e.step()
        for symbol in ('BTCUSDm','XAUUSDm'):
            rows=view['symbols'][symbol]['scenario_book']
            self.assertEqual({(int(x['side']),x['kind']) for x in rows},
                             {(-1,'LIMIT'),(-1,'STOP'),(1,'LIMIT'),(1,'STOP')})

    def test_first_cycle_still_sends_best_buy_and_sell_for_each_symbol(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close);e.step()
        self.assertEqual(len(self.api.sent),4)
        for symbol in ('BTCUSDm','XAUUSDm'):
            rows=[x for x in self.api.sent if x['symbol']==symbol]
            self.assertEqual(len(rows),2)
            self.assertEqual({1 if int(x['type']) in (2,4) else -1 for x in rows},{1,-1})

if __name__=='__main__':unittest.main()
