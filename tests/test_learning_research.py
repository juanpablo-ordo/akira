import json,tempfile,unittest
from concurrent.futures import Future,ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from execution import OWN_PENDING
from learning import PendingLearner
from research import ContextWorker,finite_bias
from regime import regularize_metrics
from settings import load_config,DEFAULT
from tests.fixtures import PendingCase
from providers import lexical_bias,model_component

class LearningTests(PendingCase,unittest.TestCase):
    def closed_trade(self,profit=2,magic=OWN_PENDING,exit_magic=None,commission=0):
        p=self.api.add_position(magic=magic);entry=self.api.record_deal(p,0,p.volume)
        entry.commission=commission
        out=self.api.record_deal(p,1,p.volume,profit);self.api.positions.remove(p)
        if exit_magic is not None:out.magic=exit_magic
        return p,entry,out
    def test_closed_pending_outcome_is_learned(self):
        self.closed_trade();learner=PendingLearner(self.g);self.assertTrue(learner.update())
        self.assertEqual(learner.metrics('BTCUSDm')['samples'],1)
    def test_manual_close_is_linked_to_owned_entry(self):
        self.closed_trade(exit_magic=0);learner=PendingLearner(self.g);learner.update()
        self.assertEqual(learner.metrics('BTCUSDm')['samples'],1)
    def test_manual_entry_is_not_learned(self):
        self.closed_trade(magic=0);learner=PendingLearner(self.g);learner.update()
        self.assertEqual(learner.metrics('BTCUSDm')['samples'],0)
    def test_previous_market_lane_is_not_learned_as_pending(self):
        self.closed_trade(magic=170001);learner=PendingLearner(self.g);learner.update()
        self.assertEqual(learner.metrics('BTCUSDm')['samples'],0)
    def test_open_or_partially_closed_trade_is_not_a_complete_outcome(self):
        p=self.api.add_position(magic=OWN_PENDING);self.api.record_deal(p,0,p.volume);self.api.record_deal(p,1,.005,1)
        learner=PendingLearner(self.g);learner.update();self.assertEqual(learner.metrics(p.symbol)['samples'],0)
    def test_fees_and_swap_are_included(self):
        _,_,out=self.closed_trade(profit=2,commission=-.8);out.swap=-.3;out.fee=-.2
        learner=PendingLearner(self.g);learner.update();self.assertAlmostEqual(learner.metrics('BTCUSDm')['expectancy'],.7)
    def test_repeated_poll_does_not_duplicate_training_outcome(self):
        self.closed_trade();learner=PendingLearner(self.g);learner.update();self.clock.advance(2);learner.update()
        self.assertEqual(learner.metrics('BTCUSDm')['samples'],1)
    def test_history_failure_preserves_confirmed_samples(self):
        self.closed_trade();learner=PendingLearner(self.g);learner.update();self.api.fail_history=True;self.clock.advance(2);learner.update()
        self.assertEqual(learner.metrics('BTCUSDm')['samples'],1)
    def test_small_sample_is_not_a_calibrated_probability(self):
        self.closed_trade();learner=PendingLearner(self.g);learner.update()
        self.assertFalse(learner.metrics('BTCUSDm')['usable'])
    def test_all_losses_are_not_changed_into_neutral_win_rate(self):
        for _ in range(20):self.closed_trade(profit=-1)
        learner=PendingLearner(self.g);learner.update();m=learner.metrics('BTCUSDm')
        self.assertEqual(m['side_win_rate'][1],0);self.assertEqual(m['side_wilson_lower'][1],0)
        self.assertLess(regularize_metrics(m)['regularized_win_rate'],.5)
    def test_learning_survives_restart(self):
        self.closed_trade();PendingLearner(self.g).update()
        from execution import Journal,Gateway
        g=Gateway(self.api,self.cfg,Journal(self.root/'state.json'),self.g.log,self.clock)
        self.assertEqual(PendingLearner(g).metrics('BTCUSDm')['samples'],1)
    def test_mixed_manual_netting_entries_are_excluded(self):
        p=self.api.add_position(magic=OWN_PENDING);self.api.record_deal(p,0,.01)
        d=self.api.record_deal(p,0,.01);d.magic=0;self.api.record_deal(p,1,.02,2);self.api.positions.remove(p)
        learner=PendingLearner(self.g);learner.update();self.assertEqual(learner.metrics(p.symbol)['samples'],0)

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.now=1800000000.0
        self.cfg=load_config(DEFAULT);self.w=ContextWorker(self.cfg,self.tmp.name,lambda:self.now);self.addCleanup(self.w.close)
    def source(self,name,data,age=0):self.w.sources[name]={'updated':self.now-age,'data':data,'error':''}
    def test_no_sources_means_no_invented_external_confidence(self):
        r=self.w.read();self.assertEqual(r['fusion']['BTCUSDm']['confidence'],0)
    def test_assistant_receives_current_source_data_and_excludes_stale_facts(self):
        self.source('news',{'items':[{'title':'Dato actual','url':'https://example.org/news'}]})
        self.source('coinglass:BTCUSDm',{'funding':[{'close':.001}]})
        self.source('derivatives:BTCUSDm',{'premium':{'lastFundingRate':.002}})
        r=self.w.read();self.assertEqual(r['news'][0]['title'],'Dato actual')
        self.assertEqual(r['coinglass']['BTCUSDm']['funding'][0]['close'],.001)
        from assistant_akira import AkiraAssistant
        self.assertEqual(AkiraAssistant.compact({'research':r})['research']['derivatives']['BTCUSDm']['funding'],.002)
        self.now+=1000;r=self.w.read();self.assertEqual(r['news'],[]);self.assertEqual(r['coinglass'],{})
    def test_malformed_provider_data_does_not_stop_other_analysis(self):
        self.source('coinglass:BTCUSDm',{'funding':.001})
        self.source('news',{'items':[{'title':'Bitcoin breakout bullish','date':'20261006'}]})
        r=self.w.read();self.assertIn('Datos de fuente inválidos',r['sources']['coinglass:BTCUSDm']['error'])
        self.assertFalse(r['sources']['coinglass:BTCUSDm']['fresh']);self.assertNotIn('BTCUSDm',r['coinglass'])
        self.assertIn('BTCUSDm',r['fusion'])
    def test_new_source_is_used_without_waiting_for_other_sources(self):
        self.source('news',{'items':[{'title':'Bitcoin bullish breakout','date':'2026-10-06'}]})
        self.assertGreater(self.w.read()['fusion']['BTCUSDm']['bias'],0)
    def test_expired_news_loses_all_weight(self):
        self.source('news',{'items':[{'title':'Bitcoin bullish breakout','date':'2026-10-06'}]},age=1000)
        self.assertEqual(self.w.read()['fusion']['BTCUSDm']['confidence'],0)
    def test_failed_refresh_does_not_make_old_content_new(self):
        self.source('news',{'items':[]},age=100)
        future=Future();future.set_exception(RuntimeError('quota'))
        self.w.jobs['news']=future;self.w.pool=NS(submit=lambda fn:Future())
        self.cfg['research']['enabled']=False;old=self.w.sources['news']['updated'];self.w.tick()
        self.assertEqual(self.w.sources['news']['updated'],old);self.assertIn('quota',self.w.sources['news']['error'])
        self.w.pool=None
    def test_slow_youtube_job_does_not_block_fed_completion(self):
        slow=Future();fed=Future();fed.set_result([{'title':'Federal Reserve lower rates','date':'2026-10-06'}])
        self.w.jobs={'youtube':slow,'fed':fed};self.w.pool=NS(submit=lambda fn:Future());self.cfg['research']['enabled']=False
        self.w.tick();self.assertIn('fed',self.w.sources);self.assertIn('youtube',self.w.jobs);self.w.pool=None
    def test_youtube_without_captions_has_zero_vote(self):
        self.source('youtube',{'rows':[{'topic':'BTCUSDm','status':'captions_unavailable','title':'Bitcoin huge rally','published':'20261006'}]})
        self.assertEqual(self.w.read()['fusion']['BTCUSDm']['confidence'],0)
    def test_partial_captions_cannot_be_called_complete(self):
        row={'topic':'BTCUSDm','status':'analyzed','summary':json.dumps({'bias':1,'confidence':.9,'source_complete':False})}
        self.source('youtube',{'rows':[row]});self.assertEqual(self.w.read()['fusion']['BTCUSDm']['confidence'],0)
    def test_public_derivatives_are_not_fabricated_for_gold(self):
        jobs=self.w.jobs_for({},{});self.assertIn('derivatives:BTCUSDm',jobs);self.assertNotIn('derivatives:XAUUSDm',jobs)
    def test_provider_intervals_are_independent(self):
        jobs=self.w.jobs_for({},{});self.assertEqual(jobs['fed'][0],8);self.assertEqual(jobs['youtube'][0],25);self.assertEqual(jobs['coinglass:BTCUSDm'][0],12)
    def test_paid_cloud_is_not_automatically_enabled(self):
        self.assertNotIn('cloud',self.w.jobs_for({'symbols':{'BTCUSDm':{}}},{}))
    def test_ambiguous_local_model_abstains(self):
        report={'model_output':.51,'advantage':.2,'usable_signal':True};self.assertIsNone(model_component(report,'M5'))
    def test_remote_analysis_cannot_create_price_parameters(self):
        row=finite_bias({'bias':.9,'confidence':1,'entry':999999,'note':'buy'})
        self.assertNotIn('entry',row);self.assertLessEqual(row['confidence'],.35)
    def test_caption_analysis_reads_complete_text_not_title_only(self):
        self.cfg['symbols']={'BTCUSDm':True}
        with patch('research.youtube_search',return_value=[{'url':'https://youtube.com/watch?v=abc'}]),patch('research.read_youtube',return_value={'url':'https://youtube.com/watch?v=abc','title':'Bearish gold','body':'Bitcoin bullish breakout support holds. '*400,'status':'transcript','complete':True,'published':'20261006'}):
            result=self.w._youtube();a=json.loads(result['rows'][0]['summary'])
        self.assertTrue(a['source_complete']);self.assertGreater(a['chunks'],1);self.assertGreater(a['bias'],0)
    def test_transcript_is_reused_without_repeated_download(self):
        self.cfg['symbols']={'BTCUSDm':True}
        self.w.store.put({'url':'https://youtube.com/watch?v=abc','title':'BTC','topic':'BTCUSDm','status':'analyzed','body':'Bitcoin bullish','summary':'{}','published':'20261006'})
        with patch('research.youtube_search',return_value=[{'url':'https://youtube.com/watch?v=abc'}]),patch('research.read_youtube') as fetch:self.w._youtube()
        fetch.assert_not_called()
    def test_nonfinite_remote_values_are_rejected(self):
        for value in (float('nan'),float('inf')):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):finite_bias({'bias':value,'confidence':.3})
    def test_failed_rss_bundle_does_not_become_a_fresh_source(self):
        future=Future();future.set_result({'items':[],'errors':{'crypto':'timeout'}})
        self.w.jobs={'news':future};self.cfg['research']['enabled']=False;self.w.pool=NS(submit=lambda fn:Future())
        self.w.tick();self.assertFalse(self.w.sources['news'].get('updated'));self.assertIn('RSS sin datos',self.w.sources['news']['error']);self.w.pool=None

if __name__=='__main__':unittest.main()
