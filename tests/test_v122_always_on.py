import copy,unittest
from pathlib import Path
from unittest.mock import patch

from settings import DEFAULT,load_config
from assistant_akira import AkiraAssistant
from tests.fixtures import PendingCase
from engine import Engine

ROOT=Path(__file__).resolve().parents[1]

class AlwaysOnV122Tests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.cfg=load_config(copy.deepcopy(DEFAULT));self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close);self.e.warmup()
    def test_defaults_keep_safe_map_alive_and_manage_stale_orders(self):
        self.assertEqual(self.cfg['schema_version'],1600)
        self.assertTrue(self.cfg['execution']['always_keep_pending_map'])
        self.assertTrue(self.cfg['execution']['pending_budget_fit_entry'])
        self.assertTrue(self.cfg['strategy']['pending_dynamic_structural_fallback'])
        self.assertLessEqual(self.cfg['pending']['orphan_cancel_seconds'],8.0)
        self.assertLessEqual(self.cfg['pending']['replace_confirm_seconds'],.6)
    def test_scan_adds_presence_candidate_for_missing_direction(self):
        q=self.g.quote('BTCUSDm');cache=self.e.planner.caches['BTCUSDm']
        strict=self.e.planner.proposed_pending_plans('BTCUSDm',cache.setups,q,all_candidates=True,presence=False)
        presence=self.e.planner.proposed_pending_plans('BTCUSDm',cache.setups,q,all_candidates=True,presence=True)
        with patch.object(self.e.planner,'proposed_pending_plans',side_effect=[strict,presence]):
            plans=self.e.scan_plans('BTCUSDm',q,force=True)
        strict_sides={p.side for p in strict};presence_sides={p.side for p in presence}
        for side in ({1,-1}-strict_sides)&presence_sides:
            self.assertTrue(any(p.side==side for p in plans))
    def test_presence_never_creates_market_lane(self):
        for symbol,cache in self.e.planner.caches.items():
            rows=self.e.planner.proposed_pending_plans(symbol,cache.setups,self.g.quote(symbol),all_candidates=True,presence=True)
            self.assertTrue(all(p.lane=='PENDING' and p.kind in ('LIMIT','STOP') for p in rows))

class ResearchAndUiV122Tests(unittest.TestCase):
    def test_local_ai_exposes_real_web_and_youtube_search(self):
        a=AkiraAssistant(load_config(copy.deepcopy(DEFAULT)),ROOT)
        names={x['function']['name'] for x in a._local_tools()}
        self.assertIn('research_public_web',names);self.assertIn('search_youtube',names);self.assertIn('read_youtube_transcript',names)
    def test_gui_has_no_raw_json_settings_or_duplicate_best_buttons(self):
        text=(ROOT/'desktop.py').read_text(encoding='utf-8')
        self.assertNotIn('self.config_text',text)
        self.assertNotIn('PONER MEJORES PENDIENTES',text)
        self.assertNotIn('MEJORES BTC + ORO',text)
        self.assertIn('Mantener siempre el mejor mapa pendiente disponible',text)
        self.assertIn('AUTO-MAPA ACTIVO',text)

if __name__=='__main__':unittest.main()
