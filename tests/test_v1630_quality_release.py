"""16.3.0: prove the safety/quality deltas without a live MT5 account."""
import unittest
from copy import deepcopy
from pathlib import Path
from settings import DEFAULT
from migrate_v11_settings import migrate
from resource_optimizer import PROFILES
from pending_edge import PendingEdge
from pending_verification import assess,identity,levels,broker_fingerprint
from tests.fixtures import PendingCase

class QualityReleaseTests(unittest.TestCase):
    def test_fresh_accounts_start_observe_with_conservative_sizing(self):
        c=migrate({});self.assertEqual(c['mode'],'observe')
        self.assertLessEqual(c['risk']['max_trade_pct'],2.)
        self.assertLessEqual(c['risk']['portfolio_capital_pct'],5.)
        self.assertGreater(c['risk']['daily_loss_pct'],0)

    def test_previous_live_risk_settings_are_never_silently_overwritten(self):
        existing=deepcopy(DEFAULT);existing['mode']='trade'
        existing['risk'].update(max_trade_pct=4.75,portfolio_capital_pct=30.,daily_loss_pct=1.5)
        old=migrate(existing)
        self.assertEqual(old['mode'],'trade');self.assertEqual(old['risk']['max_trade_pct'],4.75)
        self.assertEqual(old['risk']['portfolio_capital_pct'],30.)
        self.assertEqual(old['risk']['daily_loss_pct'],1.5)

    def test_selection_proxy_is_not_claimed_as_true_probability(self):
        from types import SimpleNamespace
        plan=SimpleNamespace(rr=2.5,key='MAP:H1:1',reason='STRUCTURAL')
        s=PendingEdge({}).pending_edge(plan,90,65,{'samples':0}, {},0)
        self.assertFalse(s['calibrated']);self.assertIn('SIN PROBABILIDAD',s['evidence_state'])
        self.assertIn('fuera de muestra',s['disclosure'])

    def test_profiles_change_actual_ui_frame_intervals_not_trading_rules(self):
        self.assertLess(PROFILES['Rendimiento']['render_seconds'],PROFILES['Equilibrado']['render_seconds'])
        self.assertLess(PROFILES['Equilibrado']['render_seconds'],PROFILES['Ahorro de energía']['render_seconds'])
        self.assertTrue(all('mt5' not in str(p).lower() for p in PROFILES.values()))

if __name__=='__main__':unittest.main()

class ExternalStatusTests(unittest.TestCase):
    def test_timeout_and_denied_news_are_not_reported_as_subscription_plans(self):
        from cyber_ui import source_presentation
        self.assertEqual(source_presentation('local_ai',{'error':'TimeoutError: timed out'})[1],'TIEMPO AGOTADO')
        self.assertEqual(source_presentation('global_news:test',{'error':'HTTP Error 403: Forbidden'})[1],'ACCESO DENEGADO')
        self.assertEqual(source_presentation('coinglass:BTCUSDm',{'error':'PLAN_LIMITED'})[1],'PLAN LIMITADO')
