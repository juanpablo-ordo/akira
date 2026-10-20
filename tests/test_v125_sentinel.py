from tests.fixtures import optional_ollama_fixture
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akira_version import BUILD_ID
from assistant_akira import AkiraAssistant
from engine import Engine
from execution import OWN_PENDING
from settings import DEFAULT, load_config
from tests.fixtures import PendingCase


class SentinelV125EngineTests(PendingCase, unittest.TestCase):
    def test_schema_build_and_safe_risk_override_defaults(self):
        self.assertEqual(self.cfg['schema_version'], 1600)
        self.assertEqual(BUILD_ID, 'AKIRA_16_4_6_STUDIO_REV11')
        self.assertTrue(self.cfg['execution']['always_show_dual_scenarios'])
        self.assertFalse(self.cfg['risk']['min_lot_structural_override_enabled'])
        self.assertLessEqual(self.cfg['symbol_profiles']['BTCUSDm']['pending_hard_max_rr'], 4.4)
        self.assertLessEqual(self.cfg['symbol_profiles']['XAUUSDm']['pending_hard_max_rr'], 4.0)

    def test_minimum_lot_risk_override_is_explicit_and_never_silent(self):
        self.api.account.balance = self.api.account.equity = self.api.account.margin_free = 30.47
        snap = self.g.snapshot()
        base = self.g.trade_cap(snap)
        self.assertAlmostEqual(base, 30.47 * .06, places=4)
        self.cfg['risk']['min_lot_structural_override_enabled'] = True
        raised = self.g.trade_cap(self.g.snapshot())
        self.assertAlmostEqual(raised, 30.47 * .08, places=4)
        self.assertGreater(raised, base)

    def test_dual_scenario_book_always_exposes_buy_and_sell_parameters(self):
        engine = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(engine.close)
        engine.step()
        snap = self.g.snapshot()
        for symbol in ('BTCUSDm', 'XAUUSDm'):
            rows = engine.directional_scenarios(symbol, snap)
            self.assertEqual({int(r['side']) for r in rows}, {1, -1})
            self.assertGreaterEqual(len(rows), 2)
            # Either it is a real/sendable scenario or a visible thesis with a reason.
            for row in rows:
                self.assertIn('scenario_state', row)
                if float(row.get('entry') or 0) <= 0:
                    self.assertTrue(row.get('block_reason'))
                else:
                    self.assertGreater(float(row['sl']), 0)
                    self.assertGreater(float(row['tp']), 0)

    def test_terminal_heartbeat_proves_analysis_is_alive(self):
        engine = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(engine.close)
        engine.step()
        self.clock.advance(2.1)
        engine.step()
        files = list((self.root/'logs').glob('eventos_*.jsonl'))
        self.assertTrue(files)
        body = '\n'.join(x.read_text(encoding='utf-8') for x in files)
        self.assertIn('CICLO 1 · 4 escenarios con parámetros', body)
        self.assertIn('técnicas BUY', body)
        self.assertIn('enviables', body)
        self.assertIn('MT5 confirmadas', body)
        self.assertIn('SELL', body)

    def test_oco_removes_only_opposite_akira_pending_after_fill(self):
        engine = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(engine.close)
        p = self.api.add_position('BTCUSDm', side=0, magic=OWN_PENDING)
        own_sell = self.api.add_pending(self.plan('BTCUSDm', side=-1), magic=OWN_PENDING)
        manual_sell = self.api.add_pending(self.plan('BTCUSDm', side=-1, key='MANUAL'), magic=0)
        engine.positions.step(self.g.snapshot())
        tickets = {int(o.ticket) for o in self.api.orders}
        self.assertNotIn(int(own_sell.ticket), tickets)
        self.assertIn(int(manual_sell.ticket), tickets)
        self.assertIn(int(p.ticket), {int(x.ticket) for x in self.api.positions})


class SentinelV125AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = optional_ollama_fixture(load_config(DEFAULT))

    def test_short_entity_followup_forces_research(self):
        self.assertTrue(AkiraAssistant._should_research_fact('hbo'))
        self.assertTrue(AkiraAssistant._should_research_fact('DC Studios'))
        self.assertFalse(AkiraAssistant._should_research_fact('hola'))

    def test_fresh_question_refuses_stale_model_memory_when_sources_are_insufficient(self):
        bot = AkiraAssistant(self.cfg, self.root)
        one = {'results':[{'title':'One','url':'https://example.com/current','text':'dato actual'}]}
        def source(name,args):
            if name == 'research_public_web': return one
            if name == 'search_youtube': return {'results':[]}
            return {}
        with patch.object(bot,'_source_tool',side_effect=source), \
             patch('assistant_akira.lookup_current_fact',return_value=one), \
             patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['qwen3:14b']}), \
             patch('assistant_akira.ollama_agent',side_effect=AssertionError('no debe contestar desde memoria vieja')):
            answer = bot.reply('¿Cuál es la última serie que lanzó DC en 2026?', {}, use_cloud=False)
        self.assertIn('no pude confirmar el dato exacto', answer)
        self.assertIn('DC en 2026', answer)
        self.assertNotIn('¿Quieres que profundice',answer)

    def test_capable_local_model_self_reviews_against_two_current_sources(self):
        bot = AkiraAssistant(self.cfg, self.root)
        rows = {'results':[
            {'title':'Studio','url':'https://dc.com/news/current','text':'dato verificado 2026'},
            {'title':'Trade','url':'https://variety.com/current','text':'dato corroborado 2026'},
        ]}
        def source(name,args):
            if name == 'research_public_web': return rows
            if name == 'search_youtube': return {'results':[]}
            return {}
        with patch.object(bot,'_source_tool',side_effect=source), \
             patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['qwen3:14b']}), \
             patch('assistant_akira.ollama_agent',return_value='Borrador incorrecto'), \
             patch('assistant_akira.ollama_chat',return_value='Respuesta corregida con evidencia.') as reviewer:
            answer = bot.reply('¿Cuál es la última serie que lanzó DC en 2026?', {}, use_cloud=False)
        self.assertTrue(reviewer.called)
        self.assertIn('Respuesta corregida con evidencia.', answer)
        self.assertIn('dc.com', answer)
        self.assertIn('variety.com', answer)

    def test_research_variants_are_date_aware_and_independent(self):
        rows = AkiraAssistant._research_variants('última serie de DC', trading=False, limit=6)
        joined = ' '.join(rows).lower()
        self.assertGreaterEqual(len(rows), 4)
        self.assertIn(str(__import__('datetime').datetime.now().year), joined)
        self.assertIn('official', joined)
        self.assertTrue('variety' in joined or 'deadline' in joined)


if __name__ == '__main__':
    unittest.main()
