"""Offline regressions for the three completed Rev19 integration paths."""
import copy
import unittest
from types import SimpleNamespace as NS

from adaptive_route import route
from coinglass_heatmap import normalize_heatmap
from indicator_decision import indicator_evidence
from liquidation_heatmap import realized_liquidations_summary
from strategy import Plan


def frames():
    def f(close):
        return NS(atr=1.0,bars=[NS(close=close)],
                  extra={'supertrend':close-1,'supertrend_direction':1,
                         'hma20':close-.6,'ichimoku_kijun':close-.5,
                         'demarker14':64,'cmf20':.20,'fvg_last_three':1})
    return {'M15':f(101.0),'H1':f(103.0)}


def pending(kind='STOP'):
    return NS(key='TEST:BREAKOUT:H1',side=1,kind=kind,lane='PENDING',signal_timeframe='H1')


class IndependentIndicators(unittest.TestCase):
    def test_supported_trend_is_a_bounded_vote_not_six_correlated_votes(self):
        bullish=indicator_evidence(frames(),1)
        bearish=indicator_evidence(frames(),-1)
        self.assertEqual(bullish['status'],'RANKING_CONTEXT')
        self.assertGreater(bullish['adjustment'],0)
        self.assertLess(bearish['adjustment'],0)
        self.assertLessEqual(abs(bullish['adjustment']),2.4)
        self.assertEqual(len(bullish['families']),4)
        self.assertFalse(bullish['validated_probability'])

    def test_missing_higher_timeframe_cannot_rank(self):
        self.assertEqual(indicator_evidence({'M15':frames()['M15']},1)['adjustment'],0)
        self.assertEqual(indicator_evidence({},1)['status'],'INSUFFICIENT_DATA')


class AdaptiveRouting(unittest.TestCase):
    def setUp(self):
        self.cfg={'strategy_choice':{'selected':'AKIRA_ADAPTATIVA'}}

    def test_breakout_preferred_over_pullback_and_manual_is_respected(self):
        reg={'regime':'BREAKOUT','confidence':.95}
        stop=route(pending('STOP'),self.cfg,reg)
        limit=route(pending('LIMIT'),self.cfg,reg)
        self.assertGreater(stop['adjustment'],limit['adjustment'])
        self.assertTrue(stop['entry_allowed'])
        manual={'strategy_choice':{'selected':'PENDIENTE_RETROCESO'}}
        self.assertEqual(route(pending('STOP'),manual,reg)['adjustment'],0)

    def test_new_risk_during_strong_shock_is_not_authorized(self):
        reg={'regime':'NEWS_SHOCK','confidence':.91}
        self.assertFalse(route(pending(),self.cfg,reg)['entry_allowed'])
        self.assertTrue(route(pending(),self.cfg,{'regime':'NEWS_SHOCK','confidence':.40})['entry_allowed'])


class CoinGlassLevelProvenance(unittest.TestCase):
    def test_provider_schema_is_modelled_not_executed_and_keeps_price_levels(self):
        response={'y_axis':[100,110,120],
                  'price_candlesticks':[[1],[2],[3],[4]],
                  'liquidation_leverage_data':[[0,0,100],[1,1,200],[2,1,300],[3,2,400]]}
        x=normalize_heatmap(response,12345)
        self.assertEqual(x['status'],'PROVIDER_MODELLED')
        self.assertFalse(x['observed_executions'])
        self.assertFalse(x['trade_confirmation'])
        self.assertEqual(x['valid_points'],4)
        self.assertEqual(round(sum(v['current_exposure_usd']+v['historical_exposure_usd'] for v in x['bands'])),1000)
        self.assertEqual(x,normalize_heatmap(response,12345))

    def test_bad_or_wrong_asset_payload_never_fabricates_levels(self):
        source={'y_axis':[100,110],'price_candlesticks':[[1]],
                'liquidation_leverage_data':[[0,99,10]]}
        self.assertEqual(normalize_heatmap(source,123)['status'],'INVALID_DATA')
        self.assertEqual(normalize_heatmap(source,123,symbol='XAU')['status'],'INVALID_DATA')

    def test_invalid_provider_response_fails_closed(self):
        from unittest.mock import patch
        from coinglass_heatmap import fetch_heatmap
        with patch('providers.cg_get',return_value={'y_axis':[1,2],
                'liquidation_leverage_data':[], 'price_candlesticks':[[1]]}):
            with self.assertRaisesRegex(ValueError,'verificables'):
                fetch_heatmap()

    def test_aggregate_executed_volume_not_misattributed_to_price_bands(self):
        x=realized_liquidations_summary({'liquidations':[
            {'aggregated_long_liquidation_usd':300,'aggregated_short_liquidation_usd':120}]})
        self.assertEqual(x['status'],'PROVIDER_REPORTED_AGGREGATED_EXECUTIONS')
        self.assertFalse(x['per_price_level'])
        self.assertEqual(x['long_liquidations_usd'],300)
        self.assertEqual(realized_liquidations_summary({})['status'],'UNAVAILABLE')


if __name__=='__main__':unittest.main()
