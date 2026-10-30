"""Field regressions: public HTTPS, finite work and faithful trading evidence.

All market data here is synthetic. These tests do not measure account profits.
"""
import copy
import json
import ssl
import tempfile
import threading
import time
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.error import HTTPError

from settings import DEFAULT,load_config
from public_derivatives import bundle,normalize
from tests import test_studio_rev8_assets as fixtures

NOW=1800000000


def public_reply(url):
    stamp=str(NOW*1000)
    if 'okx.com' in url:
        if 'open-interest' in url:row={'oiCcy':'100','ts':stamp}
        elif 'funding-rate' in url:row={'fundingRate':'.0001','ts':stamp}
        elif 'books' in url:row={'bids':[['100','2','0','1']],'asks':[['101','1','0','1']],'ts':stamp}
        else:row=[stamp,'1.2']
        return {'code':'0','data':[row]}
    if 'bybit.com' in url:
        if 'tickers' in url:result={'list':[{'fundingRate':'.0002','markPrice':'100','indexPrice':'100','openInterest':'200'}]}
        elif 'orderbook' in url:result={'b':[['100','2']],'a':[['101','1']],'ts':int(stamp)}
        elif 'open-interest' in url:result={'list':[{'openInterest':'200','timestamp':stamp}]}
        else:result={'list':[{'buyRatio':'.6','sellRatio':'.4','timestamp':stamp}]}
        return {'retCode':0,'result':result,'time':int(stamp)}
    raise AssertionError('No se debía consultar este mercado')


class PublicMarketTests(unittest.TestCase):
    def test_complete_public_data_needs_no_key_or_paid_provider(self):
        fetch=Mock(side_effect=public_reply)
        row=bundle(fetch,clock=lambda:NOW)
        self.assertEqual(row['state'],'OK');self.assertEqual(row['source'],'OKX public')
        self.assertTrue({'open_interest','premium','depth'}<=set(row['coverage']))
        self.assertTrue(all('okx.com' in args.args[0] for args in fetch.call_args_list))
        self.assertIn('liquidation_heatmap',row['missing']);self.assertNotIn('COINGLASS',str(fetch.call_args_list))
    def test_access_denied_automatically_uses_a_different_public_exchange(self):
        def fetch(url):
            if 'okx.com' in url:raise HTTPError(url,403,'Forbidden',{},None)
            return public_reply(url)
        row=bundle(fetch,clock=lambda:NOW)
        self.assertEqual(row['state'],'OK');self.assertEqual(row['source'],'Bybit public')
        self.assertEqual(row['open_interest']['openInterest'],200)
        self.assertTrue(row['errors']['OKX']);self.assertNotIn('Binance',row['errors'])
    def test_explicit_partial_coverage_retains_successful_metrics(self):
        def fetch(url):
            if 'books' in url:raise TimeoutError('fixture')
            return public_reply(url)
        row=bundle(fetch,clock=lambda:NOW,venues=('OKX',))
        self.assertEqual(row['state'],'OK');self.assertNotIn('depth',row['coverage']);self.assertIn('depth',row['missing'])
    def test_all_failed_sources_are_terminal_and_not_fabricated_as_available(self):
        row=bundle(Mock(side_effect=ssl.SSLCertVerificationError('fixture bad chain')),clock=lambda:NOW)
        self.assertEqual(row['state'],'NO_DATA');self.assertNotIn('premium',row)
        self.assertEqual(set(row['errors']),{'OKX','Bybit','Binance'})
    def test_btc_derivatives_are_never_fabricated_for_gold(self):
        fetch=Mock();self.assertEqual(bundle(fetch,'XAU')['state'],'UNSUPPORTED');fetch.assert_not_called()
    def test_error_envelopes_empty_and_nonfinite_values_are_rejected(self):
        for raw in ({'code':'500','data':[]},{'code':'0','data':[]},{'code':'0','data':[{'oiCcy':'nan'}]},
                    {'code':'0','data':[{'oiCcy':'0'}]}):
            with self.subTest(raw=raw),self.assertRaises(ValueError):normalize('OKX','open_interest',raw,NOW)
    def test_old_or_future_exchange_timestamp_cannot_be_refreshed_by_retrieval(self):
        for delta in (-901,31):
            raw={'code':'0','data':[{'oiCcy':'100','ts':str((NOW+delta)*1000)}]}
            with self.subTest(delta=delta),self.assertRaises(ValueError):normalize('OKX','open_interest',raw,NOW)
    def test_oi_growth_alone_is_not_a_bullish_vote(self):
        from providers import public_derivatives_bias
        bias,confidence,_=public_derivatives_bias({'oi_history':[{'sumOpenInterest':100},{'sumOpenInterest':200}]})
        self.assertEqual((bias,confidence),(0,0))


class WorkerFieldTests(unittest.TestCase):
    setUp=fixtures.AssetReviewTests.setUp
    plan=fixtures.AssetReviewTests.plan
    restrict_to_reviews=fixtures.AssetReviewTests.restrict_to_reviews
    def test_new_and_upgraded_configuration_prefers_public_data(self):
        raw=copy.deepcopy(DEFAULT);raw['research'].pop('derivatives_provider',None)
        cfg=load_config(raw);self.assertEqual(cfg['research']['derivatives_provider'],'public')
        jobs=self.worker.jobs_for({},{});self.assertNotIn('coinglass:BTCUSDm',jobs);self.assertNotIn('coinglass:XAUUSDm',jobs)
        self.assertEqual(jobs['derivatives:BTCUSDm'][0],120)
    def test_manual_paid_choice_still_preserves_public_fallback(self):
        self.cfg['research']['derivatives_provider']='coinglass'
        jobs=self.worker.jobs_for({},{});self.assertIn('coinglass:BTCUSDm',jobs);self.assertIn('derivatives:BTCUSDm',jobs)
    def test_video_opinion_does_not_become_an_entry_vote(self):
        row={'topic':'BTCUSDm','status':'analyzed','complete':True,'summary':json.dumps({'bias':1,'confidence':1,'source_complete':True})}
        self.worker.sources={'youtube':{'updated':self.now,'data':{'rows':[row]}}}
        # Rev19 disables the source by default: even cached metadata must not
        # appear as an active research source or affect financial decisions.
        disabled=self.worker.read()
        self.assertEqual(disabled['fusion']['BTCUSDm']['confidence'],0)
        self.assertFalse(disabled['videos'])
        # An explicitly enabled educational source may show videos, but its
        # opinions still have zero weight as trading confirmations.
        self.cfg['research']['youtube']=True
        context=self.worker.read()
        self.assertEqual(context['fusion']['BTCUSDm']['confidence'],0)
        self.assertTrue(context['videos'])
    def test_stuck_request_stops_showing_loading_without_launching_duplicates(self):
        self.restrict_to_reviews();self.worker.tick();first=self.worker.jobs['local_ai:BTCUSDm']
        self.now+=301;self.worker.tick()
        state=self.worker.read()['sources']['local_ai:BTCUSDm']
        self.assertFalse(state['inflight']);self.assertTrue(state['waiting_for_worker']);self.assertIn('TimeoutError',state['error'])
        self.worker.refresh();self.worker.tick();self.assertIs(self.worker.jobs['local_ai:BTCUSDm'],first);self.assertEqual(len(self.pool.calls),1)
    def test_repeated_model_errors_lengthen_the_pause_instead_of_loading_forever(self):
        self.restrict_to_reviews();self.cfg['symbols']={'BTCUSDm':True};self.worker.submit({'symbols':{'BTCUSDm':{}}})
        for _ in range(3):
            self.worker.tick();self.pool.calls[-1][0].set_exception(TimeoutError('synthetic slow CPU'));self.now+=1;self.worker.tick()
            delay=self.worker.due['local_ai:BTCUSDm']-self.now
            if self.worker.failures['local_ai:BTCUSDm']<3:self.now+=delay
        self.assertGreaterEqual(delay,1800);self.assertTrue(self.worker.read()['sources']['local_ai:BTCUSDm']['automatic_pause'])
    def test_changed_scenario_ids_cannot_restart_a_failed_model_continuously(self):
        from pending_verification import identity
        from tests.test_studio_rev8_assets import ControlledPool
        self.worker.pool=ControlledPool();p=self.plan('XAUUSDm','first')
        self.worker.request_pending_reviews([p],{'symbols':{}});self.worker._pending_tick(self.now,{})
        self.worker.pending_future.set_exception(TimeoutError('fixture'));self.now+=1;self.worker._pending_tick(self.now,{})
        other=self.plan('XAUUSDm','second');self.assertEqual(self.worker.request_pending_reviews([other],{'symbols':{}}),[])
        self.assertTrue(self.worker.request_pending_reviews([other],{'symbols':{}},force=True));self.assertIn(identity(other),self.worker.pending_queue)


class SmallReviewTests(unittest.TestCase):
    setUp=fixtures.AssetReviewTests.setUp
    plan=fixtures.AssetReviewTests.plan
    def view(self):
        frames={tf:{'trend':.3,'rsi':52,'adx':24,'atr':2.5243123,'volume_ratio':1.1,
            'bos':1,'sweep':0,'macd':.5,'range_hi':3050,'range_lo':2950,'vwap':3001,'regime':'UPTREND',
            **{'unused_'+str(i):100+i for i in range(20)}} for tf in ('M1','M5','M15','M30','H1','H4','D1','W1')}
        return {'updated':self.now,'symbols':{'XAUUSDm':{'bid':3000,'ask':3000.1,'frames':frames}}}
    def test_small_prompt_preserves_every_timeframe_and_labels_omissions(self):
        v=self.view();before=copy.deepcopy(v);new,meta=self.worker._model_input(v,{})
        old,_=self.worker._review_input(v,{})
        self.assertLess(len(new),len(old)*.8);self.assertEqual(meta['digest_version'],2)
        self.assertEqual(set(json.loads(new)['symbols']['XAUUSDm']['frames']),set(v['symbols']['XAUUSDm']['frames']))
        self.assertEqual(v,before);self.assertGreater(meta['omitted_raw_indicator_values'],0)
    def test_summary_output_has_a_smaller_real_schema(self):
        answer=json.dumps({'XAUUSDm':{'bias':0,'confidence':0,'note':'Falta confirmación'}})
        with patch('research.ollama_status',return_value={'models':['Qwen3-4B-Q4_K_M.gguf']}),patch('research.ollama_chat',return_value=answer) as chat:
            row=self.worker._summary_impl(self.view(),{})
        self.assertEqual(row['XAUUSDm']['confidence'],0);self.assertEqual(row['_meta']['digest_version'],2)
        self.assertEqual(chat.call_args.kwargs['options']['num_predict'],140)
        self.assertEqual(set(chat.call_args.kwargs['response_format']['properties']['XAUUSDm']['required']),{'bias','confidence','note'})
    def test_short_wire_id_maps_back_to_the_exact_order_and_prices(self):
        from pending_verification import identity
        p=self.plan('XAUUSDm','exact-order');self.worker.request_pending_reviews([p],self.view())
        batch=[self.worker.pending_queue[identity(p)]]
        response={'p0':{'verdict':'ABSTAIN','strategy':'RANGE','reason':'Falta estructura','missing':['estructura']}}
        with patch('research.ollama_status',return_value={'models':['Qwen3-4B-Q4_K_M.gguf']}),patch('research.ollama_chat',return_value=json.dumps(response)) as chat:
            result=self.worker._pending_summary_impl(batch,{})
        self.assertEqual(set(result),{identity(p)});self.assertEqual(result[identity(p)]['data']['verdict'],'ABSTAIN')
        self.assertNotIn(identity(p),chat.call_args.args[0][-1]['content'])
        wire=json.loads(chat.call_args.args[0][-1]['content'].split('PENDIENTES EXACTAS:\n')[1])
        self.assertEqual({k:wire[0][k] for k in ('entry','sl','tp')},{k:p[k] for k in ('entry','sl','tp')})
    def test_general_ai_and_educational_updates_cannot_invalidate_their_own_review(self):
        from pending_verification import fingerprint
        v=self.view();p=self.plan('XAUUSDm','exact');v['research']={'sources':{}}
        a=fingerprint(v,p)
        v['research']['sources']={'local_ai:XAUUSDm':{'fresh':True,'usable':True},'youtube':{'fresh':True,'usable':True}}
        self.assertEqual(a,fingerprint(v,p))
        v['research']['sources']['global_news:FED']={'fresh':True,'usable':True};self.assertNotEqual(a,fingerprint(v,p))
    def test_review_display_uses_its_actual_running_deadline(self):
        from pending_verification import assess,fingerprint,identity
        v=self.view();p=self.plan('XAUUSDm','deadline');fp=fingerprint(v,p)
        row={'fingerprint':fp,'state':'RUNNING','started':self.now-70,'updated':self.now-70,'run_budget_seconds':95}
        report=assess(v,p,reviews={identity(p):row});ai=next(s for s in report['stages'] if s['name'].startswith('IA'))
        self.assertNotEqual(ai['state'],'TIEMPO AGOTADO')


class AutomaticWorkTests(unittest.TestCase):
    def view(self):
        rows=[]
        for key,risk,ready in [('over-budget',6,True),('waiting',1,False),('ready',1,True)]:
            rows.append({'key':key,'side':1,'kind':'LIMIT','entry':100+len(rows),'sl':90,'tp':120,'lane':'PENDING','risk_usd':risk,'sendable':ready})
        return {'symbols':{'XAUUSDm':{'scenario_book':rows}},'trade_risk_cap':2}
    def test_eco_does_not_spend_inference_on_automatic_individual_proposals(self):
        from compact_review import automatic_targets
        cfg=load_config(DEFAULT);cfg['desktop']['performance_profile']='Ahorro de energía'
        v=self.view();before=copy.deepcopy(v);self.assertEqual(automatic_targets(v,cfg),[]);self.assertEqual(v,before)
    def test_eco_preserves_the_users_explicit_ai_requirement(self):
        from compact_review import automatic_targets
        cfg=load_config(DEFAULT);cfg['desktop']['performance_profile']='Ahorro de energía'
        v=self.view();v['required_pending_reviews']=['XAUUSDm / ready']
        self.assertEqual([p['key'] for p in automatic_targets(v,cfg)],['ready'])
    def test_balanced_reviews_only_funded_sendable_proposals(self):
        from compact_review import automatic_targets
        cfg=load_config(DEFAULT);cfg['desktop']['performance_profile']='Equilibrado'
        self.assertEqual([p['key'] for p in automatic_targets(self.view(),cfg)],['ready'])
    def test_raw_candidate_cannot_hide_the_latest_scenario_funding_check(self):
        from compact_review import automatic_targets
        cfg=load_config(DEFAULT);cfg['desktop']['performance_profile']='Equilibrado';v=self.view()
        p=copy.deepcopy(v['symbols']['XAUUSDm']['scenario_book'][-1]);p.pop('risk_usd');p.pop('sendable')
        v['symbols']['XAUUSDm']['pending_book']=[p]
        self.assertEqual([p['key'] for p in automatic_targets(v,cfg)],['ready'])
    def test_explanation_never_overrides_a_closed_or_reconciling_market_with_old_budget_checks(self):
        from decision_status import decision_status
        for state in ('MERCADO CERRADO','MERCADO EN PAUSA','RECONCILIANDO','CARGANDO'):
            row=decision_status('XAUUSDm',[],[{'risk_usd':6}],[],[],[],{},{'state':state,'detail':'Causa actual'},2)
            self.assertEqual(row['state'],state);self.assertEqual(row['reason'],'Causa actual')


class LibraryFieldTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def test_redirected_catalog_page_is_cached_under_its_canonical_url(self):
        from reference_library import update_reference,CATALOG
        from knowledge import KnowledgeStore
        canonical=CATALOG[0][1];actual=canonical+'index.html'
        with patch('reference_library.read_web',return_value={'url':actual,'title':'Official','body':'Reference text','fetched':NOW}):update_reference(self.root,canonical)
        row=KnowledgeStore(self.root).get(canonical);self.assertEqual(row['resolved_url'],actual);self.assertEqual(row['fetched'],NOW)
    def test_tls_failure_is_readable_without_discarding_cached_content_or_blocking_trades(self):
        from knowledge_update import KnowledgeUpdater
        from knowledge import KnowledgeStore
        url='https://example.org/doc';KnowledgeStore(self.root).put({'url':url,'title':'Old reference','body':'Saved text','kind':'reference_web','fetched':1})
        events=[]
        with patch('knowledge_update.CATALOG',[('Documento',url,'Official')]):
            updater=KnowledgeUpdater(load_config(DEFAULT),self.root,events.append,clock=lambda:NOW,fetch=Mock(side_effect=ssl.SSLCertVerificationError('certificate verify failed')))
            updater.tick()
        row=updater.read();self.assertEqual(row['state'],'ACTUALIZACIÓN PARCIAL');self.assertTrue(row['sources'][0]['cached_content'])
        self.assertEqual(updater.next_due,NOW+3600);self.assertNotIn('SSLCertVerificationError',events[0]['detail'])
        self.assertEqual(KnowledgeStore(self.root).get(url)['body'],'Saved text')
    def test_library_has_a_finite_batch_deadline_and_a_terminal_status(self):
        from knowledge_update import KnowledgeUpdater
        release=threading.Event()
        def slow(*args):release.wait(2);return {'fetched':NOW,'characters':10}
        updater=KnowledgeUpdater(load_config(DEFAULT),self.root,fetch=slow);updater.batch_timeout_seconds=.03
        try:
            start=time.monotonic()
            with patch('knowledge_update.CATALOG',[('Documento','https://example.org/doc','Official')]):updater.tick()
            self.assertLess(time.monotonic()-start,1);self.assertNotEqual(updater.read()['state'],'ACTUALIZANDO')
        finally:release.set()
    def test_https_redirect_cannot_downgrade_to_unencrypted_http(self):
        from knowledge import PublicRedirect
        from urllib.request import Request
        with patch('knowledge.public_url',side_effect=lambda url:url),self.assertRaisesRegex(ValueError,'HTTPS'):
            PublicRedirect().redirect_request(Request('https://example.org'),None,302,'Found',{},'http://example.org')
    def test_source_countdown_is_a_duration_and_pause_has_a_plain_explanation(self):
        from studio_presenter import next_query
        from cyber_ui import source_presentation
        self.assertEqual(next_query({'retry_after_seconds':21197}),'En 6 h')
        self.assertEqual(next_query({'inflight':True}),'En curso')
        self.assertEqual(source_presentation('local_ai:XAUUSDm',{'automatic_pause':True,'error':'TimeoutError'})[1],'IA EN ESPERA')
    def test_hot_path_ledger_summary_does_not_reopen_sqlite_every_poll(self):
        from strategy_research import ResearchLedger
        ledger=ResearchLedger(self.root)
        with patch.object(ledger,'recent',wraps=ledger.recent) as query:
            for _ in range(20):ledger.summary()
            self.assertEqual(query.call_count,1)
            ledger.add(url='https://example.org/source',kind='news_read',body='New research '*100)
            self.assertEqual(ledger.summary()['sources'],1);self.assertEqual(query.call_count,2)


class CombinedStrategyTests(unittest.TestCase):
    def test_sources_create_a_separate_combined_hypothesis_without_live_permission(self):
        from strategy_adaptation import StrategyAdaptation,condition,candidate_decision
        with tempfile.TemporaryDirectory() as tmp:
            lab=StrategyAdaptation(tmp,load_config(DEFAULT),clock=lambda:NOW)
            for i,body in enumerate(('H1 tendencia ', 'volumen ', 'RSI recuperación ')):
                lab.ingest_source({'url':'https://youtube.com/watch?v=fixture'+str(i),'complete':True,'body':body*150,'title':'Synthetic education'})
            with lab.db() as db:profile=json.loads(db.execute("SELECT body FROM profiles WHERE id='CONFLUENCE'").fetchone()[0])
            self.assertEqual(len(profile['sources']),3);self.assertFalse(profile['auto_live_activation'])
            plan={'side':1,'symbol':'BTCUSDm','kind':'LIMIT','lane':'PENDING'}
            self.assertTrue(condition('CONFLUENCE',plan,{'H1':{'trend':.5},'M15':{'rsi':55,'volume_ratio':1.1}}))
            self.assertFalse(condition('CONFLUENCE',plan,{'H1':{'trend':.5},'M15':{'rsi':55,'volume_ratio':.3}}))
            self.assertIsNone(condition('CONFLUENCE',plan,{'H1':{'trend':.5}}))
            self.assertEqual(candidate_decision(plan,{}, {'strategy_lab':{'adaptation':{'profiles':[profile]}}},NOW),(True,''))
