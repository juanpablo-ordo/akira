"""Owner regressions: an AI failure on BTC must not hide or starve gold."""
import copy,json,tempfile,threading,unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

import research
from research import ContextWorker
from settings import DEFAULT,load_config
from pending_verification import identity


class ControlledPool:
    def __init__(self):self.calls=[]
    def submit(self,fn,*args):
        future=Future();self.calls.append((future,fn,args));return future
    def shutdown(self,**kwargs):pass


def reply(symbol,stamp=1000):
    return {symbol:{'bias':.1,'confidence':.2,'preferred':[],'avoid':[],'thesis':'Contexto','note':'Prueba sintética'},
        '_meta':{'active_symbols':[symbol],'created':stamp,'input_scope':'COMPLETE_INDICATORS_SUMMARIZED_EXTERNAL'}}


class AssetReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.cfg=load_config(DEFAULT);self.cfg['assistant']['local_runtime_enabled']=True
        self.cfg['desktop']['performance_profile']='Ahorro de energía';self.now=1000
        self.worker=ContextWorker(self.cfg,self.root,lambda:self.now);self.addCleanup(self.worker.close)
    def restrict_to_reviews(self):
        self.pool=ControlledPool();self.worker.pool=self.pool
        original=self.worker.jobs_for
        self.worker.jobs_for=lambda view,sources:{k:v for k,v in original(view,sources).items() if k.startswith('local_ai:')}
        self.worker.submit({'symbols':{'BTCUSDm':{},'XAUUSDm':{}}})
    def plan(self,symbol,key):
        return {'symbol':symbol,'key':key,'side':1,'kind':'LIMIT','entry':100,'sl':90,'tp':120}
    def test_btc_timeout_leaves_gold_eligible_and_gold_result_visible(self):
        self.restrict_to_reviews();self.worker.tick()
        self.assertEqual(list(self.worker.jobs),['local_ai:BTCUSDm']);self.assertEqual(len(self.pool.calls),1)
        self.pool.calls[0][0].set_exception(TimeoutError('synthetic slow CPU'))
        self.now+=1;self.worker.tick()
        self.assertEqual(list(self.worker.jobs),['local_ai:XAUUSDm'])
        self.pool.calls[1][0].set_result(reply('XAUUSDm',self.now));self.now+=1;self.worker.tick()
        state=self.worker.read()
        self.assertIn('TimeoutError',state['sources']['local_ai:BTCUSDm']['error'])
        self.assertTrue(state['sources']['local_ai:XAUUSDm']['fresh'])
        self.assertEqual(set(state['deep_review']),{'XAUUSDm'})
        self.assertEqual(state['deep_review_meta']['active_symbols'],['XAUUSDm'])
        self.assertTrue(state['deep_review_meta']['partial'])
    def test_one_local_inference_is_submitted_while_its_peer_is_running(self):
        self.restrict_to_reviews();self.worker.tick()
        for _ in range(5):self.now+=1;self.worker.tick()
        self.assertEqual(len(self.pool.calls),1)
    def test_slow_summary_cools_down_after_completion_instead_of_restarting(self):
        self.restrict_to_reviews();self.worker.tick();self.now+=100
        self.pool.calls[0][0].set_result(reply('BTCUSDm',self.now));self.worker.tick()
        self.assertEqual(self.worker.due['local_ai:BTCUSDm'],self.now+600)
        self.assertEqual(list(self.worker.jobs),['local_ai:XAUUSDm'])
    def test_deferral_for_chat_is_not_counted_as_an_inference_failure(self):
        from local_inference import BackgroundDeferred
        self.restrict_to_reviews();self.worker.tick();self.now+=1
        self.pool.calls[0][0].set_exception(BackgroundDeferred('chat'));self.worker.tick()
        self.assertEqual(self.worker.due['local_ai:BTCUSDm'],self.now+3)
        self.assertFalse(self.worker.sources['local_ai:BTCUSDm'].get('error'))
    def test_old_combined_cache_migrates_without_refreshing_gold_timestamp(self):
        self.worker.close();saved={'data':{**reply('BTCUSDm'),**reply('XAUUSDm')},'updated':100,'error':''}
        path=self.root/'state/pending_research.json';path.write_text(json.dumps({'sources':{'local_ai':saved}}))
        self.worker=ContextWorker(self.cfg,self.root,lambda:self.now)
        self.addCleanup(self.worker.close)
        self.worker.sources['local_ai:BTCUSDm']={'data':reply('BTCUSDm'),'updated':self.now,'error':''}
        self.worker._merge_local_ai_sources();state=self.worker.read()
        self.assertEqual(state['sources']['local_ai:XAUUSDm']['updated'],100)
        self.assertFalse(state['sources']['local_ai:XAUUSDm']['fresh'])
        self.assertNotIn('XAUUSDm',state['deep_review'])
        self.assertIn('BTCUSDm',state['deep_review'])
    def test_combined_metadata_cannot_claim_gold_verification_for_bitcoin(self):
        btc=reply('BTCUSDm');gold=reply('XAUUSDm')
        btc['_meta'].update(verified_twice=False,timeframe_count=7,input_scope='COMPACT_INDICATORS_COMPLETE_TIMEFRAMES')
        gold['_meta'].update(verified_twice=True,timeframe_count=7)
        self.worker.sources.update({'local_ai:BTCUSDm':{'data':btc,'updated':self.now},'local_ai:XAUUSDm':{'data':gold,'updated':self.now}})
        self.worker._merge_local_ai_sources();meta=self.worker.sources['local_ai']['data']['_meta']
        self.assertFalse(meta['verified_twice']);self.assertEqual(meta['timeframe_count'],14)
        self.assertEqual(meta['input_scope'],'COMPACT_INDICATORS_COMPLETE_TIMEFRAMES')
        self.assertTrue(meta['symbol_reviews']['XAUUSDm']['meta']['verified_twice'])
    def test_required_order_defers_only_the_auxiliary_summary(self):
        event=threading.Event();self.worker._summary_cancel=event
        p=self.plan('XAUUSDm','required');self.worker.request_pending_reviews([p],{'symbols':{},'required_pending_reviews':[identity(p)]})
        self.assertTrue(event.is_set());self.assertEqual(self.worker.pending_reviews[identity(p)]['state'],'QUEUED')
    def test_automatic_request_does_not_cancel_a_running_summary(self):
        event=threading.Event();self.worker._summary_cancel=event
        self.worker.request_pending_reviews([self.plan('XAUUSDm','automatic')],{'symbols':{}})
        self.assertFalse(event.is_set())
    def test_closing_cancels_only_this_workers_two_background_requests(self):
        own=[threading.Event(),threading.Event()];other=threading.Event()
        self.worker._summary_cancel,self.worker._pending_cancel=own
        self.worker.close()
        self.assertTrue(all(event.is_set() for event in own));self.assertFalse(other.is_set())
    def test_pending_turns_alternate_assets_within_the_same_priority(self):
        self.worker.pool=ControlledPool()
        plans=[self.plan('BTCUSDm','b1'),self.plan('BTCUSDm','b2'),self.plan('XAUUSDm','g1')]
        self.worker.request_pending_reviews(plans,{'symbols':{}});self.worker._pending_tick(self.now,{})
        self.assertEqual([r['plan']['symbol'] for r in self.worker.pending_batch],['BTCUSDm'])
        request=self.worker.pending_batch[0];self.worker.pending_future.set_result({identity(request['plan']):{'data':{'verdict':'ABSTAIN'}}})
        self.now+=1;self.worker._pending_tick(self.now,{})
        self.assertEqual([r['plan']['symbol'] for r in self.worker.pending_batch],['XAUUSDm'])
    def test_waiting_gold_does_not_expire_before_a_slow_local_peer_gets_its_turn(self):
        self.worker.pool=ControlledPool();plans=[self.plan('BTCUSDm','b1'),self.plan('XAUUSDm','g1'),self.plan('BTCUSDm','b2')]
        self.worker.request_pending_reviews(plans,{'symbols':{}});self.worker._pending_tick(self.now,{})
        self.now+=110
        self.assertEqual(self.worker.expire_pending_reviews(),[])
        request=self.worker.pending_batch[0];self.worker.pending_future.set_result({identity(request['plan']):{'data':{'verdict':'ABSTAIN'}}})
        self.worker._pending_tick(self.now,{})
        self.assertEqual(self.worker.pending_batch[0]['plan']['symbol'],'XAUUSDm')
        self.assertEqual(self.worker.pending_reviews[identity(plans[2])]['state'],'QUEUED')
        self.now+=301;self.worker.expire_pending_reviews()
        self.assertEqual(self.worker.pending_reviews[identity(plans[2])]['state'],'ERROR')
    def test_required_order_keeps_priority_over_other_asset_automatic_work(self):
        self.worker.pool=ControlledPool();gold=self.plan('XAUUSDm','auto');btc=self.plan('BTCUSDm','required')
        self.worker._pending_turns['BTCUSDm']=99
        self.worker.request_pending_reviews([gold,btc],{'symbols':{},'required_pending_reviews':[identity(btc)]})
        self.worker._pending_tick(self.now,{})
        self.assertEqual(identity(self.worker.pending_batch[0]['plan']),identity(btc))
    def test_loading_budget_does_not_expire_at_the_old_65_second_limit(self):
        self.worker.pool=ControlledPool();p=self.plan('XAUUSDm','a')
        self.worker.request_pending_reviews([p],{'symbols':{}});self.worker._pending_tick(self.now,{})
        self.now+=70;self.assertEqual(self.worker.expire_pending_reviews(),[])
        self.now+=121;self.assertEqual(self.worker.expire_pending_reviews(),[identity(p)])
        self.assertEqual(self.worker.pending_reviews[identity(p)]['state'],'ERROR')
    def test_deferral_cannot_revive_an_expired_attempt(self):
        from local_inference import BackgroundDeferred
        self.worker.pool=ControlledPool();p=self.plan('XAUUSDm','expired')
        self.worker.request_pending_reviews([p],{'symbols':{}});self.worker._pending_tick(self.now,{})
        self.now+=191;self.worker.expire_pending_reviews()
        self.worker.pending_future.set_exception(BackgroundDeferred('chat'))
        self.worker._pending_tick(self.now,{})
        self.assertEqual(self.worker.pending_reviews[identity(p)]['state'],'ERROR')
        self.assertNotIn(identity(p),self.worker.pending_queue)
    def test_managed_individual_review_uses_its_actual_inference_budget(self):
        p=self.plan('XAUUSDm','real-levels');self.worker.request_pending_reviews([p],{'symbols':{'XAUUSDm':{}}})
        batch=[self.worker.pending_queue[identity(p)]]
        answer={identity(p):{'verdict':'ABSTAIN','strategy':'RANGE','reason':'Falta confirmación de estructura','missing':['estructura']}}
        with patch('research.ollama_status',return_value={'models':['Qwen3-4B-Q4_K_M.gguf']}),patch('research.ollama_chat',return_value=json.dumps(answer)) as chat:
            self.worker._pending_summary_impl(batch,{})
        self.assertEqual(chat.call_args.kwargs['timeout'],90)
        self.assertEqual(self.worker.pending_reviews[identity(p)]['run_budget_seconds'],95)
        self.assertEqual(self.worker.pending_reviews[identity(p)]['phase'],'REVIEWING')
    def test_closed_gold_is_not_queued_as_if_its_market_were_open(self):
        jobs=self.worker.jobs_for({'symbols':{'BTCUSDm':{},'XAUUSDm':{}},'markets':{'XAUUSDm':{'scheduled_closed':True}}},{})
        self.assertIn('local_ai:BTCUSDm',jobs);self.assertNotIn('local_ai:XAUUSDm',jobs)
    def test_large_balanced_input_fits_small_owned_context_without_changing_engine(self):
        self.cfg['desktop'].update(performance_profile='Equilibrado',model_context_tokens=8192)
        frames={tf:{'rsi':50,'atr':3,**{'indicator_'+str(i):12345.1234+i for i in range(60)}} for tf in ('M1','M5','M15','M30','H1','H4','D1')}
        view={'symbols':{'XAUUSDm':{'frames':frames}}};before=copy.deepcopy(view)
        from akira_local_ai import owned_context
        with owned_context(2048):payload,meta=self.worker._review_input(view,{})
        self.assertEqual(meta['input_scope'],'COMPACT_INDICATORS_COMPLETE_TIMEFRAMES')
        self.assertEqual(set(json.loads(payload)['symbols']['XAUUSDm']['frames']),set(frames))
        self.assertLess(len(payload),2600);self.assertEqual(view,before)
        self.assertEqual(self.cfg['desktop']['model_context_tokens'],8192)
    def test_gold_review_does_not_receive_bitcoin_derivatives_or_venue_book(self):
        sources={name:{'updated':self.now,'data':{'detail':'Only BTC evidence'},'error':''} for name in ('coinglass:BTCUSDm','derivatives:BTCUSDm','venue:OKX')}
        sources['fed']={'updated':self.now,'data':[{'title':'Macro context'}],'error':''}
        payload,_=self.worker._review_input({'symbols':{'XAUUSDm':{'frames':{'H1':{'rsi':50}}}}},sources)
        received=json.loads(payload)['sources'];self.assertEqual(set(received),{'fed'})
    def test_shared_prefix_reuses_evidence_without_reusing_prices_or_source_age(self):
        sources={'news':{'updated':self.now,'data':{'items':[{'title':'Dato sintético común'}]},'error':''}}
        def view(symbol,price):return {'updated':self.now,'symbols':{symbol:{'bid':price,'ask':price+.1,'frames':{'M15':{'rsi':50}}}}}
        btc,_=self.worker._review_input(view('BTCUSDm',100),sources);self.now+=10
        gold,_=self.worker._review_input(view('XAUUSDm',200),sources)
        self.assertEqual(btc.split(',"symbols":')[0],gold.split(',"symbols":')[0])
        a,b=json.loads(btc),json.loads(gold)
        self.assertEqual(a['symbols']['BTCUSDm']['bid'],100);self.assertEqual(b['symbols']['XAUUSDm']['bid'],200)
        self.assertEqual(a['source_ages_seconds']['news'],0);self.assertEqual(b['source_ages_seconds']['news'],10)


class AssetPresentationTests(unittest.TestCase):
    def test_each_asset_explains_its_own_activity_and_risk_block(self):
        from studio_presenter import market_activity
        view={'connected':True,'updated':1000,'symbols':{'BTCUSDm':{'checked_at':999,'decision':{'state':'GESTIONANDO','confirmed_pending_orders':1}},'XAUUSDm':{'checked_at':998,'decision':{'state':'ESPERANDO','reason':'El riesgo mínimo supera el presupuesto'}}}}
        btc=market_activity(view,'BTCUSDm');gold=market_activity(view,'XAUUSDm')
        self.assertIn('Oro',gold['text']);self.assertIn('presupuesto',gold['detail']);self.assertIn('2 s',gold['checked'])
        self.assertIn('1 pendiente',btc['text']);self.assertIn('0 pendiente',gold['text'])
    def test_a_quote_does_not_fabricate_a_completed_evaluation(self):
        from studio_presenter import market_activity
        row=market_activity({'connected':True,'symbols':{'XAUUSDm':{'bid':4184}}},'XAUUSDm')
        self.assertEqual(row['checked'],'Esperando la primera evaluación')
    def test_empty_bulletin_and_blocked_access_are_different_states(self):
        from cyber_ui import source_presentation
        title,state,detail=source_presentation('global_news:BLS',{'usable':False,'fresh':True})
        self.assertEqual(title,'BLS · noticias');self.assertEqual(state,'SIN NOVEDADES')
        self.assertIn('MT5',detail)
        self.assertEqual(source_presentation('global_news:BLS',{'error':'HTTP Error 403: Forbidden'})[1],'ACCESO DENEGADO')
    def test_educational_reference_does_not_masquerade_as_a_live_price(self):
        from cyber_ui import source_presentation
        row={'reference_only':True,'usable':True,'fresh':False,'age_seconds':4000}
        self.assertEqual(source_presentation('strategy_reference',row)[1],'REFERENCIA EDUCATIVA')
        self.assertFalse(row['fresh'])
    def test_ai_titles_distinguish_gold_from_bitcoin(self):
        from cyber_ui import source_presentation
        self.assertEqual(source_presentation('local_ai:XAUUSDm',{})[0],'AKIRA · Oro')
        self.assertEqual(source_presentation('local_ai:BTCUSDm',{})[0],'AKIRA · Bitcoin')


class NativeAssetVisibility(unittest.TestCase):
    def test_gold_state_is_visible_without_scrolling_the_source_table(self):
        from PySide6.QtWidgets import QApplication
        from desktop_qt import StudioWindow
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            window=StudioWindow(Path(tmp),preview=True,start_actor=False)
            try:
                view={'connected':True,'mode':'observe','updated':1000,'symbols':{'XAUUSDm':{'checked_at':1000,'decision':{'state':'ESPERANDO','reason':'Riesgo por encima del presupuesto'}}},'research':{'sources':{'local_ai':{'display_hidden':True},'local_ai:XAUUSDm':{'inflight':True}}}}
                window.controller.view=view;window.navigate(3);window.render(view);window.show();app.processEvents()
                self.assertIn('presupuesto',window.asset_activity_labels['XAUUSDm'].text())
                self.assertFalse(window.asset_activity_labels['XAUUSDm'].isHidden())
                self.assertNotIn('local_ai',window.analysis_sources.rows)
                self.assertIn('local_ai:XAUUSDm',window.analysis_sources.rows)
            finally:window.close();app.processEvents()


class CaptionConnectionTests(unittest.TestCase):
    def fixture(self):
        return {'title':'Fuente sintética','subtitles':{'es':[{'ext':'json3','url':'https://www.youtube.com/caption-'+str(i)} for i in range(6)]}}
    def test_caption_certificate_failure_is_not_reported_as_missing_captions(self):
        import ssl
        from urllib.error import URLError
        from knowledge import read_youtube
        from youtube_support import YouTubeError
        error=URLError(ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED'))
        with patch('knowledge.read_public',side_effect=error) as fetch:
            with self.assertRaises(YouTubeError) as caught:read_youtube('https://youtube.com/watch?v=fixture',extractor=lambda url:self.fixture())
        self.assertEqual(caught.exception.state,'CERTIFICATE_ERROR');self.assertEqual(fetch.call_count,1)
    def test_actual_absence_of_tracks_still_is_not_a_completed_analysis(self):
        from knowledge import read_youtube
        with patch('knowledge.read_public') as fetch:
            row=read_youtube('https://youtube.com/watch?v=fixture',extractor=lambda url:{'title':'No tracks'})
        self.assertEqual(row['status'],'captions_unavailable');self.assertFalse(row['complete']);fetch.assert_not_called()
    def test_old_incomplete_analysis_is_retried_without_claiming_complete_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=load_config(DEFAULT);cfg['symbols']={'BTCUSDm':True};worker=ContextWorker(cfg,tmp)
            url='https://youtube.com/watch?v=legacy-fixture'
            try:
                worker.store.put({'url':url,'status':'analyzed','title':'Caché antigua','body':'Título sin transcripción','summary':'{}'})
                missing={'url':url,'status':'captions_unavailable','body':'','complete':False}
                with patch('research.youtube_search',return_value=[{'url':url}]),patch('research.read_youtube',return_value=missing) as read:
                    result=worker._youtube()
                read.assert_called_once();self.assertEqual(result['state'],'NO_CAPTIONS')
                self.assertFalse(result['rows'][0]['complete'])
            finally:worker.close()
    def test_aggregated_session_errors_remain_actionable(self):
        from youtube_support import classify_error
        self.assertEqual(classify_error(RuntimeError('XAUUSDm: AUTH_REQUIRED: sesión pendiente')),'AUTH_REQUIRED')
        self.assertEqual(classify_error(RuntimeError('HTTP Error 403: Forbidden')),'ACCESS_DENIED')
    def test_public_reader_still_rejects_private_addresses_before_opening(self):
        from knowledge import read_public
        with patch('knowledge.public_opener') as opener:
            with self.assertRaisesRegex(ValueError,'locales o privadas'):read_public('https://127.0.0.1/example')
        opener.assert_not_called()
    def test_bundled_tls_checks_cover_the_actual_caption_and_page_transport(self):
        from installer.check_https import run
        result=run()
        self.assertTrue(result['public_reader_trusted_https'])
        self.assertTrue(result['public_reader_bad_host_rejected'])
        self.assertTrue(result['public_reader_bad_chain_rejected'])


from tests.fixtures import PendingCase

class ActorAssetHeartbeat(PendingCase,unittest.TestCase):
    def test_eco_spares_optional_deep_work_while_market_cycles_continue(self):
        from engine import Engine
        self.cfg['mode']='observe';self.cfg['desktop']['performance_profile']='Ahorro de energía';poll=self.cfg['poll_seconds']
        engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(engine.close)
        with patch.object(engine,'queue_pending_verification') as optional:
            engine.step();self.assertEqual(optional.call_count,1)
            self.clock.advance(180)
            for symbol in self.cfg['symbols']:self.api.set_quote(symbol,self.api.ticks[symbol].bid,fill=False)
            engine.step();self.assertEqual(optional.call_count,1)
            self.clock.advance(421)
            for symbol in self.cfg['symbols']:self.api.set_quote(symbol,self.api.ticks[symbol].bid,fill=False)
            engine.step();self.assertEqual(optional.call_count,2)
        self.assertEqual(engine.cycle,3);self.assertEqual(self.cfg['poll_seconds'],poll)
    def test_both_assets_publish_actual_actor_evaluation_times(self):
        from engine import Engine
        engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(engine.close)
        view=engine.step()
        self.assertTrue(all(view['symbols'][s]['checked_at']==self.clock() for s in ('BTCUSDm','XAUUSDm')))
        self.assertTrue(all(view['symbols'][s]['last_analysis_at'] for s in ('BTCUSDm','XAUUSDm')))
    def test_stale_gold_keeps_its_explanation_and_does_not_stop_btc(self):
        from engine import Engine
        from studio_presenter import market_activity
        self.clock.advance(60);self.api.set_quote('BTCUSDm',self.api.ticks['BTCUSDm'].bid,fill=False)
        engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(engine.close)
        view=engine.step();gold=market_activity(view,'XAUUSDm')
        self.assertIn('cotización',gold['detail']);self.assertIn('0 s',gold['checked'])
        self.assertFalse(any(row['symbol']=='XAUUSDm' for row in self.api.sent))
        self.assertTrue(any(row['symbol']=='BTCUSDm' for row in self.api.sent))

