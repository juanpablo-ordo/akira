"""Regressions reproduced from stuck exact-order reviews and partial sources."""
import copy,io,json,threading,time,unittest
from concurrent.futures import Future
from unittest.mock import Mock,patch
from datetime import datetime,timezone
from tests import test_v1626_verification as previous
from tests import test_v1621_startup as ui_fixture
from tests.fixtures import PendingCase
from pending_verification import fingerprint,broker_fingerprint,identity,targets,assess
from research import ContextWorker
from providers import parse_rss,coinglass_bundle
from global_sources import news_feed,BLS_NEWS_FEEDS
from akira_local_ai import _post,chat
from frozen_ui_contract import UI_MODULES

class ExactEvidenceTests(PendingCase,unittest.TestCase):
    setUp=previous.EvidenceTests.setUp
    def prepare(self):
        self.view['research']['sources']={'news':{'fresh':True,'usable':True,'updated':self.clock(),'error':''}}
        self.p=next(p for p in targets(self.view) if identity(p)==identity(self.p))
        self.e.queue_pending_verification([self.p],self.view,deep=False,force=True);self.e.process_pending_verification()
        self.review={identity(self.p):{'fingerprint':fingerprint(self.view,self.p),'state':'COMPLETE',
            'updated':self.clock(),'data':{'verdict':'APPROVE','reason':'Niveles revisados individualmente','missing':[]}}}
    def stage(self,snapshot,name):
        return next(s for s in assess(snapshot,self.p,self.e.pending_checks,self.review)['stages'] if name in s['name'])
    def test_reception_timestamp_does_not_invalidate_exact_order(self):
        self.prepare();later=copy.deepcopy(self.view);later['research']['sources']['news']['updated']+=1
        self.assertEqual(fingerprint(later,self.p),fingerprint(self.view,self.p))
        self.assertEqual(self.stage(later,'Riesgo')['state'],'COMPROBADO')
        self.assertEqual(self.stage(later,'Restricciones')['state'],'YA VIGENTE')
        self.assertEqual(self.stage(later,'IA:')['state'],'REVISADA')
    def test_repeated_source_refreshes_never_erase_broker_checks(self):
        self.prepare()
        for i in range(200):
            self.view['research']['sources']['news']['updated']=self.clock()+i/20
            self.assertEqual(self.stage(self.view,'Restricciones')['state'],'YA VIGENTE')
    def test_failed_source_invalidates_ai_but_not_a_read_only_broker_check(self):
        self.prepare();self.view['research']['sources']['news'].update(error='HTTP 503',fresh=False,usable=False)
        self.assertEqual(self.stage(self.view,'IA:')['state'],'DESACTUALIZADA')
        self.assertEqual(self.stage(self.view,'Riesgo')['state'],'COMPROBADO')
    def test_a_new_bitcoin_venue_cannot_invalidate_gold_review(self):
        self.prepare();gold=next(p for p in targets(self.view) if p['symbol']=='XAUUSDm');before=fingerprint(self.view,gold)
        self.view['research']['sources']['venue:OKX']={'fresh':True,'usable':True,'updated':self.clock()}
        self.assertEqual(before,fingerprint(self.view,gold));self.assertNotEqual(self.review[identity(self.p)]['fingerprint'],fingerprint(self.view,self.p))
    def test_another_asset_source_cannot_invalidate_bitcoin_review(self):
        self.prepare();before=fingerprint(self.view,self.p)
        self.view['research']['sources']['technical:XAUUSDm']={'fresh':True,'usable':True,'updated':self.clock()}
        self.assertEqual(before,fingerprint(self.view,self.p))
    def test_closed_candle_changes_invalidate_ai_without_erasing_broker_check(self):
        self.prepare();self.view['symbols'][self.p['symbol']]['frames']['M15']['rsi']+=2
        self.assertEqual(self.stage(self.view,'IA:')['state'],'DESACTUALIZADA')
        self.assertEqual(self.stage(self.view,'Restricciones')['state'],'YA VIGENTE')
    def test_changed_stop_still_invalidates_broker_check(self):
        self.prepare();self.p['sl']-=.01
        self.assertEqual(self.stage(self.view,'Riesgo')['state'],'PENDIENTE')
    def test_risk_setting_change_still_invalidates_broker_check(self):
        self.prepare();self.view['selection_configuration']['risk']['max_trade_money']+=1
        self.assertEqual(self.stage(self.view,'Riesgo')['state'],'PENDIENTE')
    def test_changed_account_book_invalidates_broker_check(self):
        self.prepare();self.view['positions'].append({'ticket':999,'symbol':'XAUUSDm','entry':4000,'sl':3900,'volume':.01})
        self.assertEqual(self.stage(self.view,'Riesgo')['state'],'PENDIENTE')
    def test_verification_expiration_cannot_be_refreshed_by_news(self):
        self.prepare();self.view['updated']+=181;self.view['research']['sources']['news']['updated']+=181
        self.assertEqual(self.stage(self.view,'Restricciones')['state'],'PENDIENTE')
        self.assertEqual(self.stage(self.view,'IA:')['state'],'DESACTUALIZADA')

class ReviewQueueTests(PendingCase,unittest.TestCase):
    setUp=previous.PendingReviewTests.setUp
    def test_timestamp_refresh_does_not_replace_an_inflight_review(self):
        self.w.request_pending_reviews(self.plans,self.view)
        self.view['research']['sources']={'news':{'fresh':True,'usable':True,'updated':self.clock()}}
        self.w.request_pending_reviews(self.plans,self.view)
        before=copy.deepcopy(self.w.pending_reviews);self.view['research']['sources']['news']['updated']+=20
        self.assertEqual(self.w.request_pending_reviews(self.plans,self.view),[])
        self.assertEqual(self.w.pending_reviews,before)
    def test_completed_result_survives_source_reception_poll(self):
        self.view['research']['sources']={'news':{'fresh':True,'usable':True,'updated':self.clock()}}
        self.w.request_pending_reviews(self.plans,self.view)
        self.w.pending_batch=list(self.w.pending_queue.values());self.w.pending_queue.clear()
        f=Future();f.set_result({identity(p):{'data':self.answer[identity(p)]} for p in self.plans});self.w.pending_future=f
        self.view['research']['sources']['news']['updated']+=10
        self.w.request_pending_reviews(self.plans,self.view);self.w.pool=Mock()
        self.w._pending_tick(self.clock(),{})
        self.assertTrue(all(self.w.pending_reviews[identity(p)]['state']=='COMPLETE' for p in self.plans))
        self.w.pool.submit.assert_not_called()
    def test_cpu_batch_is_bounded_without_losing_other_orders(self):
        plans=targets(self.view);self.assertGreater(len(plans),2)
        self.w.request_pending_reviews(plans,self.view);count=len(self.w.pending_queue)
        self.w.pool=Mock();self.w.pool.submit.return_value=Future();self.w._pending_tick(self.clock(),{})
        self.assertEqual(len(self.w.pending_batch),2);self.assertEqual(len(self.w.pending_queue),count-2)
    def test_timeout_can_retry_installed_lighter_model_without_download(self):
        response=json.dumps(self.answer)
        with patch('research.ollama_status',return_value={'ok':True,'models':['qwen3:8b','qwen3:4b']}),patch('research.ollama_chat',side_effect=[TimeoutError('timed out'),response]) as model:
            result=self.w._pending_summary(self.batch,{})
        self.assertEqual(model.call_count,2);self.assertEqual(model.call_args.kwargs['model'],'qwen3:4b')
        self.assertLessEqual(model.call_args.kwargs['options']['num_predict'],500)
        self.assertEqual(set(model.call_args.kwargs['response_format']['required']),set(self.answer))
        self.assertTrue(all('ligero' in r['recovery'] for r in result.values()))
    def test_timeout_does_not_invent_an_uninstalled_fallback(self):
        with patch('research.ollama_status',return_value={'ok':True,'models':['qwen3:8b']}),patch('research.ollama_chat',side_effect=TimeoutError('timed out')) as model:
            with self.assertRaises(TimeoutError):self.w._pending_summary(self.batch,{})
        self.assertEqual(model.call_count,1)
    def test_waiting_review_has_visible_queue_position(self):
        self.w.request_pending_reviews(self.plans,self.view)
        status=self.w.read();rows=status['pending_reviews'];self.assertEqual(rows[identity(self.plans[0])]['queue_ahead'],0)
        self.assertEqual(rows[identity(self.plans[1])]['queue_ahead'],1)

class FeedsTests(unittest.TestCase):
    def test_atom_link_date_and_nested_title_are_read(self):
        body=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>CPI <b>publication</b></title><link rel="self" href="wrong"/><link href="https://www.bls.gov/news.release/cpi.htm"/><published>2026-10-12T10:00:00Z</published></entry></feed>'
        with patch('providers.download',return_value=body):rows=parse_rss('https://www.bls.gov/feed/cpi.rss')
        self.assertEqual(rows[0]['title'],'CPI publication');self.assertTrue(rows[0]['url'].endswith('cpi.htm'))
        self.assertEqual(rows[0]['date'],'2026-10-12T10:00:00Z')
    def test_rss_titles_links_and_dates_remain_compatible(self):
        with patch('providers.download',return_value=b'<rss><channel><item><title>Fed</title><link>https://fed.example</link><pubDate>Mon, 12 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'):
            self.assertEqual(parse_rss('test')[0]['url'],'https://fed.example')
    def test_html_challenge_is_not_accepted_as_an_empty_news_feed(self):
        with patch('providers.download',return_value=b'<html><body>Access denied</body></html>'):
            with self.assertRaisesRegex(ValueError,'RSS o Atom'):parse_rss('test')
    def test_bls_uses_documented_program_feeds_and_keeps_partial_evidence(self):
        seen=[]
        def fetch(url,*args,**kw):
            seen.append(url)
            if url.endswith('cpi.rss'):raise RuntimeError('HTTP 403')
            return [{'title':'Payrolls','url':'https://www.bls.gov/news.release/empsit.htm','date':'2026-10-12T10:00:00Z'}]
        now=datetime(2026,10,12,12,tzinfo=timezone.utc).timestamp()
        with patch('global_sources.parse_rss',side_effect=fetch),patch('global_sources.time.time',return_value=now):rows=news_feed('BLS')
        self.assertEqual(set(seen),set(BLS_NEWS_FEEDS));self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['verified_publication']);self.assertIn('HTTP 403',rows[0]['feed_warnings'][0])
        self.assertNotIn('news_release/rss.xml',' '.join(seen))
    def test_bls_complete_failure_stays_an_error(self):
        with patch('global_sources.parse_rss',side_effect=RuntimeError('HTTP 503')):
            with self.assertRaisesRegex(RuntimeError,'BLS no disponible'):news_feed('BLS')
    def test_gold_plan_limit_cannot_claim_bitcoin_fallback_as_gold_evidence(self):
        with patch('providers.coinglass_auth_probe',return_value={'state':'plan_limited'}):row=coinglass_bundle('XAU')
        self.assertEqual(row['state'],'PLAN_LIMITED');self.assertIn('No hay derivados XAU confirmados',row['detail'])

class NotificationsTests(unittest.TestCase):
    setUp=ui_fixture.StartupUITests.setUp
    def view(self,source,review):
        return {'research':{'sources':{'local_ai':source},'deep_review':review},'symbols':{'BTCUSDm':{},'XAUUSDm':{}}}
    def test_a_cached_timeout_never_announces_completed_analysis(self):
        v=self.view({'updated':100,'fresh':False,'error':'TimeoutError: timed out'},{});self.app._last_deep_stamp=0
        with patch.object(self.app,'desktop_toast') as notify:self.app.maybe_notify(v)
        notify.assert_not_called()
    def test_partial_asset_review_never_announces_completed_analysis(self):
        v=self.view({'updated':100,'fresh':True},{'BTCUSDm':{'confidence':.2}});self.app._last_deep_stamp=0
        with patch.object(self.app,'desktop_toast') as notify:self.app.maybe_notify(v)
        notify.assert_not_called()
    def test_complete_context_does_not_claim_exact_order_verification(self):
        v=self.view({'updated':100,'fresh':True,'usable':True},{s:{'confidence':.2} for s in ('BTCUSDm','XAUUSDm')});self.app._last_deep_stamp=0
        with patch.object(self.app,'desktop_toast') as notify:self.app.maybe_notify(v)
        title,body=notify.call_args.args;self.assertIn('revisión general',title)
        self.assertIn('comprobación individual',body);self.assertNotIn('mapa fue recalculado',body)
    def test_missing_module_names_the_dependency_and_release(self):
        exc=ModuleNotFoundError("No module named 'pending_verification'",name='pending_verification')
        self.app.record_ui_error('Paneles de mercado',exc)
        row=self.app.notice_center.list()[0];self.assertIn('pending_verification',row['body']);self.assertIn('Versión AKIRA_',row['body'])
        self.assertIn('no terminó',row['body'])
    def test_freezer_explicitly_includes_runtime_verification_dependencies(self):
        for name in ('pending_verification','selection_trials','paired_study','quality_study'):self.assertIn(name,UI_MODULES)

class ModelTransportTests(unittest.TestCase):
    def test_slow_nonstreaming_read_is_actually_interrupted_at_deadline(self):
        stopped=threading.Event()
        class SlowResponse:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):stopped.wait(2);return b'{"message":{"content":"late"}}'
            def close(self):stopped.set()
        with patch('akira_local_ai.urlopen',return_value=SlowResponse()):
            start=time.monotonic()
            with self.assertRaises(TimeoutError):_post('http://127.0.0.1/api/chat',{},timeout=.05)
            self.assertLess(time.monotonic()-start,1);self.assertTrue(stopped.is_set())
    def test_structured_chat_sends_format_without_changing_ordinary_chat(self):
        with patch('akira_local_ai._post',return_value={'done':True,'message':{'content':'{}'}}) as post:
            chat([{'role':'user','content':'JSON'}],response_format='json');self.assertEqual(post.call_args.args[1]['format'],'json')
            chat([{'role':'user','content':'Hola'}]);self.assertNotIn('format',post.call_args.args[1])
    def test_truncated_structured_response_is_never_approved(self):
        with patch('akira_local_ai._post',return_value={'done':False,'message':{'content':'{}'}}):
            with self.assertRaisesRegex(RuntimeError,'incompleta'):chat([],response_format='json')
