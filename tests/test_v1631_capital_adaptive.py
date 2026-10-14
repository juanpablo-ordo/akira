"""Pruebas con FakeMT5: no son rentabilidad, latencia ni calidad real de Exness."""
import unittest
from copy import deepcopy
from dataclasses import replace
from migrate_v11_settings import migrate
from settings import DEFAULT,load_config
from tests.fixtures import PendingCase
from execution import Blocked

class CapitalOnboardingTests(unittest.TestCase):
    def test_new_account_is_observe_and_adaptive_without_risk_override(self):
        cfg=migrate({})
        self.assertEqual(cfg['mode'],'observe')
        self.assertEqual(cfg['symbols'],{'BTCUSDm':True,'XAUUSDm':True})
        self.assertTrue(cfg['sizing']['scale_pending'])
        self.assertEqual(cfg['sizing']['risk_utilization'],.75)
        self.assertEqual(cfg['risk']['max_trade_pct'],2.)
        self.assertEqual(cfg['risk']['portfolio_capital_pct'],5.)
        self.assertFalse(cfg['risk']['min_lot_structural_override_enabled'])
    def test_existing_account_keeps_its_limits_and_sizing_off(self):
        existing=deepcopy(DEFAULT);existing['mode']='trade'
        existing['sizing'].update(scale_pending=False,boost_score=99.)
        existing['risk'].update(max_trade_money=.5,max_trade_pct=1.5)
        cfg=migrate(existing)
        self.assertEqual(cfg['mode'],'trade')
        self.assertFalse(cfg['sizing']['scale_pending'])
        self.assertEqual(cfg['sizing']['boost_score'],99.)
        self.assertEqual(cfg['risk']['max_trade_money'],.5)
        self.assertEqual(cfg['risk']['max_trade_pct'],1.5)
    def test_no_eurusd_can_be_added(self):
        with self.assertRaises(ValueError):
            load_config({'symbols':{'BTCUSDm':True,'XAUUSDm':True,'EURUSDm':True}})
    def test_invalid_scale_parameters_rejected(self):
        with self.assertRaises(ValueError):load_config({'sizing':{'scale_pending':'yes'}})
        with self.assertRaises(ValueError):load_config({'sizing':{'risk_utilization':1.1}})

class CapitalBrokerSizingTests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(migrate({}))
        self.cfg['mode']='observe'
        self.g.cfg=self.cfg

    def balance(self,value):
        self.api.account.balance=value
        self.api.account.equity=value
        self.api.account.margin_free=value
    def strong(self,symbol):
        return replace(self.plan(symbol),score=96,quality_score=96)
    def test_ten_dollars_cannot_force_the_minimum_lot(self):
        self.balance(10)
        p=self.strong('BTCUSDm')
        with self.assertRaisesRegex(Blocked,'Lote mínimo'):
            self.g.volume_for_plan(p)
        self.assertEqual(self.cfg['risk']['max_trade_pct'],2.)
    def test_lot_only_grows_as_capital_and_broker_allow(self):
        p=self.strong('BTCUSDm')
        self.balance(100);small=self.g.volume_for_plan(p)
        self.balance(500);larger=self.g.volume_for_plan(p)
        self.assertGreater(larger,small)
        self.assertLessEqual(larger,self.cfg['sizing']['max_lot'])
        risk,_=self.g.plan_money(p,larger)
        self.assertLessEqual(risk,self.g.trade_cap(self.g.snapshot())+1e-8)
    def test_gold_is_not_forced_by_btc_balance(self):
        self.balance(10)
        gold=self.strong('XAUUSDm')
        try:
            volume=self.g.volume_for_plan(gold)
        except Blocked as exc:
            self.assertIn('Lote mínimo',str(exc))
        else:
            risk,_=self.g.plan_money(gold,volume)
            self.assertLessEqual(risk,self.g.trade_cap(self.g.snapshot())+1e-8)
    def test_low_quality_remains_base_lot(self):
        self.balance(500)
        p=replace(self.plan('BTCUSDm'),score=75,quality_score=78)
        result=self.g.volume_for_plan(p)
        self.assertAlmostEqual(result,.01)
    def test_existing_user_does_not_scale_automatically(self):
        old=migrate(deepcopy(DEFAULT))
        old['sizing']['scale_pending']=False
        self.cfg.clear();self.cfg.update(old);self.g.cfg=self.cfg
        self.balance(500)
        self.assertAlmostEqual(self.g.volume_for_plan(self.strong('BTCUSDm')),.01)

if __name__=='__main__':unittest.main()
