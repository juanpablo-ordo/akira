import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akira_version import BUILD_ID
from assistant_akira import AkiraAssistant
from akira_local_ai import choose_text_model
from engine import Engine
from execution import PENDING
from settings import DEFAULT, load_config
from strategy import build_fast_future_map_pendings
from tests.fixtures import PendingCase


class ReflexV124EngineTests(PendingCase, unittest.TestCase):
    def test_schema_build_and_reflex_defaults_are_active(self):
        self.assertEqual(self.cfg['schema_version'], 1600)
        self.assertEqual(BUILD_ID, 'AKIRA_16_5_4_STUDIO_REV19')
        self.assertTrue(self.cfg['strategy']['fast_future_map'])
        self.assertTrue(self.cfg['execution']['always_keep_pending_map'])
        self.assertGreaterEqual(self.cfg['poll_seconds'], .15)
        self.assertGreaterEqual(self.cfg['pending']['orphan_cancel_seconds'], 8.0)

    def test_small_account_first_cycle_still_produces_pending_map_when_transport_allows(self):
        # Regression for the real complaint: a small account must not be left empty
        # merely because strict A/A+ ranking found no candidate. Gateway still owns
        # the risk/margin decision and all sends remain pending orders.
        self.api.account.balance = 30.47
        self.api.account.equity = 30.47
        self.api.account.margin_free = 30.47
        engine = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(engine.close)
        engine.step()
        self.assertEqual({row['symbol'] for row in self.api.sent}, {'BTCUSDm', 'XAUUSDm'})
        self.assertTrue(all(row['action'] == PENDING for row in self.api.sent))

    def test_fast_future_map_is_pending_only_and_on_future_side_of_price(self):
        engine = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(engine.close)
        engine.warmup()
        total = 0
        for symbol, cache in engine.planner.caches.items():
            rows = build_fast_future_map_pendings(cache.frames, self.cfg['strategy'], {})
            current = cache.frames['M1'].bars[-1].close
            self.assertTrue(rows)
            total += len(rows)
            for row in rows:
                self.assertEqual(row.lane, 'PENDING')
                self.assertIn(row.kind, ('LIMIT', 'STOP'))
                if row.kind == 'LIMIT':
                    self.assertGreater(row.side * (current - row.level), 0)
                else:
                    self.assertGreater(row.side * (row.level - current), 0)
                self.assertGreater(row.side * (row.level - row.stop), 0)
                self.assertGreater(row.side * (row.target - row.level), 0)
        self.assertGreater(total, 0)

    def test_extreme_negative_final_context_is_still_a_veto(self):
        engine = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(engine.close)
        with patch.object(engine.planner, 'fuse_pending_context', side_effect=lambda symbol, plans: [p.__class__(**{**p.__dict__, 'quality_score': 0.0}) for p in plans]):
            engine.step()
        self.assertFalse(self.api.sent)


class ReflexV124AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = load_config(DEFAULT)

    def test_old_trade_command_spam_is_hidden_and_new_commands_are_not_persisted(self):
        store_bot = AkiraAssistant(self.cfg, self.root)
        store_bot.memory.remember('user', 'Dame las mejores pendientes de BTC y oro')
        store_bot.memory.remember('assistant', 'Pendientes colocadas')
        store_bot.memory.remember('user', 'Explícame qué es VWAP')
        store_bot.memory.remember('assistant', 'VWAP es un promedio ponderado por volumen.')
        bot = AkiraAssistant(self.cfg, self.root)
        joined = json.dumps(bot.history, ensure_ascii=False).lower()
        self.assertNotIn('dame las mejores pendientes', joined)
        self.assertIn('vwap', joined)
        bot._remember_turn('Pon las mejores pendientes de BTC y oro', 'Resultado real del motor')
        restarted = AkiraAssistant(self.cfg, self.root)
        self.assertNotIn('pon las mejores pendientes', json.dumps(restarted.history, ensure_ascii=False).lower())

    def test_installed_stronger_local_model_is_preferred(self):
        self.assertEqual(choose_text_model(['qwen3:8b', 'qwen3:14b', 'qwen3:30b-a3b'], 'qwen3:8b', 'qwen3:4b'), 'qwen3:30b-a3b')
        self.assertEqual(choose_text_model(['qwen3:8b', 'qwen3:14b'], 'qwen3:8b', 'qwen3:4b'), 'qwen3:14b')

    def test_reasoning_and_aggressive_research_are_enabled_by_default(self):
        self.assertTrue(self.cfg['assistant']['local_reasoning'])
        self.assertTrue(self.cfg['assistant']['aggressive_research'])
        self.assertGreaterEqual(self.cfg['assistant']['research_query_variants'], 4)
        self.assertGreaterEqual(self.cfg['assistant']['local_agent_rounds'], 4)


if __name__ == '__main__':
    unittest.main()
