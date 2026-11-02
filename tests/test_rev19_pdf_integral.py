"""PDF integral Rev19: deterministic, no-network/no-real-account contracts."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from activity_event_schema import normalize_event
from execution import Reporter
from indicators import enrich
from liquidation_heatmap import estimate_bands,heatmap_is_execution_evidence
from settings import DEFAULT,load_config
from strategy import Bar,frame
from technical_indicator_extensions import context_indicators,indicator_provenance,sma,wma,hma
from tests.fixtures import PendingCase


def candles(n=140):
    out=[]
    for i in range(n):
        base=100+i*.06
        out.append(Bar(1700000000+900*i,base-.12,base+.5,base-.55,
                       base+.17+math.sin(i/7)*.05,70+i%10))
    return tuple(out)


class IndicatorAudit(unittest.TestCase):
    def test_known_constant_reference_values(self):
        a=[8.0]*70
        self.assertAlmostEqual(sma(a,20),8.0)
        self.assertAlmostEqual(wma(a,20),8.0)
        self.assertAlmostEqual(hma(a,20),8.0)

    def test_extended_closed_bar_values_are_finite_and_context_only(self):
        bars=candles()
        ext=context_indicators(bars,1.2)
        self.assertGreater(len(ext),20)
        self.assertTrue(all(isinstance(v,(int,float)) and math.isfinite(v) for v in ext.values()))
        self.assertEqual(indicator_provenance()['decision_use'],'CONTEXT_ONLY')
        self.assertFalse(indicator_provenance()['independent_confirmation'])
        base=enrich(bars,1.2)
        self.assertEqual(base['sma20'],ext['sma20'])
        self.assertIn('ema200',base)

    def test_no_unconfirmed_future_bar_necessary(self):
        bars=candles()
        old=context_indicators(bars[:-1],1.2)
        self.assertEqual(old,context_indicators(tuple(bars[:-1]),1.2))
        self.assertNotEqual(old['sma20'],context_indicators(bars,1.2)['sma20'])


class HeatmapEvidence(unittest.TestCase):
    def test_estimated_not_observed_liquidations_and_never_trade_verdict(self):
        b=candles()
        f=NS(name='M15',bars=b)
        result=estimate_bands('BTCUSDm',{'M15':f},b[-1].time+900)
        self.assertEqual(result['status'],'ESTIMATED')
        self.assertFalse(result['observed_liquidations'])
        self.assertFalse(result['trade_confirmation'])
        self.assertFalse(heatmap_is_execution_evidence(result))
        self.assertEqual(len(result['bands']),16)
        self.assertTrue(all(0<=r['current_intensity']<=100 and
                            0<=r['historical_intensity']<=100 for r in result['bands']))
        self.assertEqual(result,estimate_bands('BTCUSDm',{'M15':f},b[-1].time+900))
        self.assertEqual(estimate_bands('XAUUSDm',{},123)['status'],'INSUFFICIENT_DATA')


class EventSchema(unittest.TestCase):
    def test_records_have_full_schema_without_inventing_mt5_confirmation(self):
        event=normalize_event({'utc':'2026-11-01T18:00:00+00:00',
                               'symbol':'XAUUSDm','operation':'protect','message':'SL solicitado'})
        for key in ('event_id','timestamp_utc','category','severity','symbol','ticket',
                    'action','message','technical_details','correlation_id','confirmation'):
            self.assertIn(key,event)
        self.assertEqual(event['category'],'TRADING')
        self.assertNotEqual(event['confirmation'],'CONFIRMED_MT5')
        done=normalize_event({'utc':'2026-11-01T18:00:00+00:00',
                              'operation':'confirmed_protect','ticket':234,'symbol':'XAUUSDm'})
        self.assertEqual(done['confirmation'],'CONFIRMED_MT5')

    def test_diagnostic_without_operation_remains_visible_and_auditable(self):
        with tempfile.TemporaryDirectory() as td:
            log=Reporter(Path(td),console=False)
            log.report('BTCUSDm','DATOS','H1 ausente')
            self.assertEqual(len(log.recent_events),1)
            self.assertEqual(log.recent_events[0]['category'],'ANÁLISIS')


class NeuralPolicy(PendingCase,unittest.TestCase):
    def test_technical_mode_is_explicitly_not_neural(self):
        from engine import Engine
        self.cfg['execution']['review_policy']='technical'
        engine=Engine(self.g,self.cfg,self.g.log)
        self.addCleanup(engine.close)
        receipt=engine.pending_review_guard(self.plan(),self.g.snapshot(),.01)
        self.assertEqual(receipt['verdict'],'TECHNICAL_ONLY')
        self.assertFalse(receipt['neural_review'])

    def test_user_config_preserved_and_invalid_review_mode_rejected(self):
        from settings import load_config
        draft=copy.deepcopy(DEFAULT)
        draft['management'].update(breakeven_at_r=10000000,
                                   trail_at_r=100000000,trail_atr=10000)
        migrated=load_config(draft)
        self.assertEqual(migrated['management']['breakeven_at_r'],10000000)
        self.assertEqual(migrated['management']['trail_at_r'],100000000)
        self.assertAlmostEqual(DEFAULT['management']['breakeven_at_r'],.95)
        self.assertEqual(DEFAULT['execution']['review_policy'],'required')
        draft['execution']['review_policy']='bypass_all'
        with self.assertRaises(ValueError):load_config(draft)


if __name__=='__main__':unittest.main()
