"""Evidence must fail closed for ranking and never authorize or reprice orders."""
import copy,json,math,unittest
from dataclasses import replace
from unittest.mock import patch
from selection_evidence import SelectorEvidence,FEATURE_VERSION,FEATURE_NAMES,candidate_features,quality_text
from pending_portfolio import pending_priority
from settings import DEFAULT,load_config
from decision_brain import instant_review
from engine import Engine
from strategy import Quote,frame
from tests.fixtures import PendingCase


class SelectionEvidenceTests(PendingCase,unittest.TestCase):
    def model(self):
        now=self.clock()
        metrics={'paired_daily_bootstrap_ci95_r':[.01,.3],'double_cost_improvement_ci95_r':[.01,.3],
            'activation_delta':.1,'win_rate_delta':.1,'pairs':100,'days':28,
            'baseline':{'proposals':100,'activated':40,'activation_rate':.4,'win_rate_when_activated':.5,'mean_net_r_per_proposal':.1},
            'challenger':{'proposals':100,'activated':50,'activation_rate':.5,'win_rate_when_activated':.6,'mean_net_r_per_proposal':.2}}
        return {'weights':[.1]*len(FEATURE_NAMES),'strength':8,'promoted':True,'evaluation_passed':True,
            'validation_passed':True,'external_venue':True,'evaluation_days':28,'evaluation_pairs':100,
            'training_end':now-40*86400,'evaluation_start':now-30*86400,'evaluation_end':now-86400,
            'evaluation':metrics,'verdict':'Mejora en un estudio externo'}

    def evidence(self,model=None):
        document={'feature_version':FEATURE_VERSION,'feature_names':list(FEATURE_NAMES),
            'provider':'PROVEEDOR DE PRUEBA','models':{'BTCUSDm':self.model() if model is None else model}}
        path=self.root/'evidence.json';path.write_text(json.dumps(document))
        return SelectorEvidence(path)

    def test_missing_or_broken_file_keeps_baseline(self):
        e=SelectorEvidence(self.root/'missing.json');self.assertEqual(e.adjustment('BTCUSDm',[1]*24,self.clock()),0)
        path=self.root/'bad.json';path.write_text('{bad');self.assertEqual(SelectorEvidence(path).document,{})

    def test_nonobject_document_and_model_fail_closed(self):
        path=self.root/'bad.json';path.write_text('[]');self.assertEqual(SelectorEvidence(path).document,{})
        e=self.evidence(model=['invalid']);self.assertEqual(e.document,{})

    def test_promoted_evidence_can_only_apply_a_bounded_adjustment(self):
        e=self.evidence();a=e.adjustment('BTCUSDm',[1000]*24,self.clock())
        self.assertGreater(a,0);self.assertLessEqual(a,12);self.assertFalse(self.api.sent)

    def test_future_evaluation_never_influences_earlier_decisions(self):
        m=self.model();m['evaluation_end']=self.clock()+1
        self.assertEqual(self.evidence(m).adjustment('BTCUSDm',[1]*24,self.clock()),0)

    def test_training_and_test_must_be_chronological(self):
        m=self.model();m['training_end']=m['evaluation_start']
        self.assertIsNone(self.evidence(m).usable('BTCUSDm',self.clock()))

    def test_stale_prior_is_ignored_without_blocking_orders(self):
        self.assertIsNone(self.evidence().usable('BTCUSDm',self.clock()+100*86400))

    def test_evidence_is_specific_to_symbol(self):
        self.assertIsNone(self.evidence().usable('XAUUSDm',self.clock()))

    def test_small_number_of_independent_days_cannot_promote(self):
        m=self.model();m['evaluation_days']=8;m['evaluation_pairs']=5000
        self.assertIsNone(self.evidence(m).usable('BTCUSDm',self.clock()))

    def test_nonpositive_confidence_bound_cannot_promote(self):
        m=self.model();m['evaluation']['paired_daily_bootstrap_ci95_r'][0]=-.01
        self.assertIsNone(self.evidence(m).usable('BTCUSDm',self.clock()))

    def test_worse_activation_or_win_rate_cannot_promote(self):
        for key in ('activation_delta','win_rate_delta'):
            with self.subTest(key=key):
                m=self.model();m['evaluation'][key]=-.01
                self.assertIsNone(self.evidence(m).usable('BTCUSDm',self.clock()))

    def test_cost_stress_must_also_support_improvement(self):
        m=self.model();m['evaluation']['double_cost_improvement_ci95_r'][0]=0
        self.assertIsNone(self.evidence(m).usable('BTCUSDm',self.clock()))

    def test_malformed_interval_cannot_interrupt_analysis(self):
        m=self.model();m['evaluation']['paired_daily_bootstrap_ci95_r']=7
        e=self.evidence(m);self.assertIsNone(e.usable('BTCUSDm',self.clock()))
        self.assertIn('Sin intervalo',quality_text(e.summary()))

    def test_inverted_or_nonfinite_interval_cannot_promote(self):
        for interval in ([.2,.1],[.1,float('nan')],[.1,float('inf')]):
            m=self.model();m['evaluation']['paired_daily_bootstrap_ci95_r']=interval
            self.assertIsNone(self.evidence(m).usable('BTCUSDm',self.clock()))

    def test_failed_candidate_and_explicit_disable_have_no_adjustment(self):
        m=self.model();m['promoted']=False
        self.assertEqual(self.evidence(m).adjustment('BTCUSDm',[1]*24,self.clock()),0)
        self.assertEqual(self.evidence().adjustment('BTCUSDm',[1]*24,self.clock(),False),0)

    def test_nan_or_incompatible_weights_have_no_adjustment(self):
        for weights in ([float('nan')]*24,[1]*23,7):
            with self.subTest(weights=str(weights)):
                m=self.model();m['weights']=weights
                self.assertEqual(self.evidence(m).adjustment('BTCUSDm',[1]*24,self.clock()),0)

    def test_ranking_adjustment_never_changes_levels_or_risk(self):
        p=self.plan();before=self.g.plan_money(p);original=p.to_dict()
        new=replace(p,selection_adjustment=8,selection_feature_version=FEATURE_VERSION)
        self.assertGreater(pending_priority(new),pending_priority(p))
        self.assertEqual(self.g.plan_money(new),before)
        self.assertEqual((new.entry,new.sl,new.tp),(original['entry'],original['sl'],original['tp']))
        self.assertFalse(self.api.sent)

    def test_runner_and_unversioned_adjustments_are_ignored(self):
        p=self.plan();raw=pending_priority(p)
        self.assertEqual(pending_priority(replace(p,selection_adjustment=10)),raw)
        runner=replace(p,lane='RUNNER');self.assertEqual(pending_priority(replace(runner,selection_adjustment=10,selection_feature_version=FEATURE_VERSION)),pending_priority(runner))

    def test_features_use_same_quote_and_closed_source_frames_without_mt5(self):
        from market_cache import MarketCache
        frames={name:frame(name,MarketCache.bars(self.api.rates['BTCUSDm',tf])) for name,tf in [('M15',15),('H1',16385),('H4',16388)]}
        p=self.plan();q=Quote(60000,60001,self.clock(),1)
        with patch.object(self.api,'symbol_info_tick',side_effect=AssertionError('No extra broker lookup')):
            values=candidate_features(p,frames,q,self.clock())
        self.assertEqual(len(values),len(FEATURE_NAMES));self.assertTrue(all(math.isfinite(x) for x in values))
        self.assertFalse(self.api.sent)

    def test_report_and_chat_name_denominators_and_external_scope(self):
        summary=self.evidence().summary();text=quality_text(summary)
        self.assertIn('40/100',text);self.assertIn('50/100',text);self.assertIn('No confirmada',text)
        self.assertIn('40.0% → 50.0%',text)
        answer=instant_review('¿Ya comprobaste que da mejores pendientes en BTC?',{'selection_evidence':summary},now=self.clock())
        self.assertIn('Recomendaciones reales importadas',answer);self.assertNotIn('40.0% → 50.0%',answer);self.assertFalse(self.api.sent)

    def test_placing_request_keeps_execution_route(self):
        self.assertIsNone(instant_review('Coloca las mejores pendientes de BTC',{}))

    def test_config_migration_preserves_disable_and_risk_caps(self):
        raw=copy.deepcopy(DEFAULT);raw['schema_version']=1503;raw['risk']['max_trade_money']=2.17
        raw['quality_selection']={'enabled':False};cfg=load_config(raw)
        self.assertEqual(cfg['risk']['max_trade_money'],2.17);self.assertFalse(cfg['quality_selection']['enabled'])

    def test_report_does_not_call_broker_or_send_an_order(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close);e._last_view={'build':'TEST','connected':False}
        with patch.object(self.api,'account_info',side_effect=AssertionError('No broker read')):
            e.report_snapshot()
        self.assertFalse(self.api.sent)
