import unittest
from pathlib import Path

import desktop
from akira_version import BUILD_ID
from engine import Engine
from execution import PENDING
from settings import DEFAULT, load_config
from strategy import build_fast_future_map_pendings
from tests.fixtures import PendingCase


class HunterV126Tests(PendingCase, unittest.TestCase):
    def test_schema_build_and_hunter_defaults(self):
        self.assertEqual(self.cfg['schema_version'], 1600)
        self.assertEqual(BUILD_ID, 'AKIRA_16_3_5_R8')
        self.assertTrue(self.cfg['execution']['allow_m15_m30_pending_origin'])
        self.assertTrue(self.cfg['execution']['allow_m5_pending_origin'])
        self.assertTrue(self.cfg['strategy']['intraday_structural_map'])
        self.assertTrue(self.cfg['execution']['technical_first_immediate'])
        self.assertTrue(self.cfg['execution']['fill_all_available_directions_same_cycle'])
        self.assertFalse(self.cfg['risk']['min_lot_structural_override_enabled'])

    def test_first_cycle_can_place_buy_and_sell_future_orders_for_both_symbols(self):
        engine = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(engine.close)
        engine.step()
        self.assertEqual(len(self.api.sent), 4)
        self.assertTrue(all(row['action'] == PENDING for row in self.api.sent))
        for symbol in ('BTCUSDm', 'XAUUSDm'):
            orders = [o for o in self.api.orders if o.symbol == symbol]
            self.assertEqual(len(orders), 2)
            sides = {1 if int(o.type) in (2,4) else -1 for o in orders}
            self.assertEqual(sides, {1, -1})

    def test_hunter_builds_near_m15_breakout_cover_for_missing_direction(self):
        engine = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(engine.close)
        engine.warmup()
        for symbol, cache in engine.planner.caches.items():
            rows = build_fast_future_map_pendings(cache.frames, self.cfg['symbol_profiles'][symbol], {})
            m15_stops = [x for x in rows if x.kind == 'STOP' and x.timeframe == 'M15']
            self.assertEqual({int(x.side) for x in m15_stops}, {1, -1})
            current = cache.frames['M1'].bars[-1].close
            for row in m15_stops:
                self.assertGreater(row.side * (row.level - current), 0)
                self.assertGreater(row.side * (row.level - row.stop), 0)
                self.assertGreater(row.side * (row.target - row.level), 0)

    def test_engine_exposes_all_loaded_timeframes_to_each_chart(self):
        engine = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(engine.close)
        view = engine.step()
        for symbol in ('BTCUSDm', 'XAUUSDm'):
            frames = view['symbols'][symbol]['bars_by_timeframe']
            for tf in ('M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'):
                self.assertIn(tf, frames)
                self.assertTrue(frames[tf])

    def test_desktop_contains_real_multitimeframe_selectors(self):
        source = Path(desktop.__file__).read_text(encoding='utf-8')
        self.assertIn("ttk.Combobox", source)
        self.assertIn("('M1','M5','M15','M30','H1','H4','D1')", source)
        self.assertIn("bars_by_timeframe", source)

    def test_reversal_coverage_does_not_bypass_gateway_risk(self):
        # A tiny account cap still wins over the desire to keep both directions.
        self.api.account.balance = self.api.account.equity = self.api.account.margin_free = 1.0
        engine = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(engine.close)
        engine.step()
        self.assertFalse(self.api.sent)
        self.assertFalse(self.cfg['risk']['min_lot_structural_override_enabled'])

    def test_terminal_heartbeat_is_subsecond_configured(self):
        self.assertLessEqual(float(self.cfg['desktop']['terminal_heartbeat_seconds']), .75)


if __name__ == '__main__':
    unittest.main()
