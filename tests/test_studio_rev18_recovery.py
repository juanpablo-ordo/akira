"""Reproduce stale busy, stalled DNS, lost YouTube discovery and tactical bypasses."""
import copy,json,tempfile,threading,time,unittest
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from settings import DEFAULT,load_config
from strategy import Plan
from local_inference import InferencePriority,BackgroundDeferred,PRIORITY
from source_recovery import SourceDeadline,alternatives
from trade_quality_gate import pending_admission,evaluate
from tests.fixtures import PendingCase
from execution import Blocked


class PriorityRecovery(unittest.TestCase):
    def test_interactive_waits_for_actual_background_release(self):
        priority=InferencePriority();entered=threading.Event();released=threading.Event()
        def background():
            try:
                with priority.auxiliary() as cancel:entered.set();cancel.wait(2)
            except BackgroundDeferred:pass
            finally:released.set()
        thread=threading.Thread(target=background,daemon=True);thread.start();self.assertTrue(entered.wait(1))
        with priority.interactive():
            self.assertFalse(priority.background);self.assertTrue(released.wait(1))
        thread.join(1);self.assertEqual(priority.users,0)

    def test_queued_interactive_cancel_does_not_leak_priority(self):
        priority=InferencePriority();cancel=threading.Event();result=[];entered=threading.Event()
        with priority.interactive():
            def queued():
                entered.set()
                try:
                    with priority.interactive(cancel_event=cancel):result.append('unexpected')
                except RuntimeError:result.append('cancelled')
            thread=threading.Thread(target=queued);thread.start();self.assertTrue(entered.wait(1));cancel.set();thread.join(1)
            self.assertEqual(result,['cancelled']);self.assertEqual(priority.users,1)
        self.assertEqual(priority.users,0)

    def test_background_does_not_queue_another_background_request(self):
        priority=InferencePriority()
        with priority.auxiliary():
            with self.assertRaises(BackgroundDeferred):
                with priority.auxiliary():self.fail('Parallel background lease')

    def test_repair_preempts_background_and_keeps_priority_through_generation(self):
        from assistant_akira import AkiraAssistant
        with tempfile.TemporaryDirectory() as tmp:
            cfg=load_config(DEFAULT);bot=AkiraAssistant(cfg,Path(tmp));runtime=bot._managed_model
            entered=threading.Event();verified=threading.Event()
            def background():
                try:
                    with PRIORITY.auxiliary() as cancel:
                        runtime.active+=1;entered.set()
                        try:cancel.wait(2)
                        finally:runtime.active-=1
                except BackgroundDeferred:pass
            def verify(*args,**kwargs):
                self.assertGreater(PRIORITY.users,0);self.assertFalse(PRIORITY.background);verified.set();return 'Hola'
            from contextlib import nullcontext
            thread=threading.Thread(target=background);thread.start();self.assertTrue(entered.wait(1))
            try:
                with patch.object(runtime,'_paths',return_value=(Path(tmp)/'server',Path(tmp)/'custom.gguf')),patch.object(runtime,'session',return_value=nullcontext()),patch.object(bot,'_verify_local_generation',side_effect=verify):
                    bot.retry_local_preparation();self.assertTrue(verified.wait(2))
                    until=time.monotonic()+1
                    while bot._repair_loading and time.monotonic()<until:time.sleep(.005)
                    self.assertTrue(bot._status['ready'],bot._status)
                    self.assertNotIn('conversación',bot._status.get('error',''))
                    self.assertFalse(bot.conversation.snapshot()['active'])
            finally:thread.join(2);runtime.shutdown()


class BoundedSources(unittest.TestCase):
    def test_blocked_dns_cannot_hold_the_source_pool_or_duplicate_requests(self):
        jobs=SourceDeadline();release=threading.Event();entered=threading.Event();calls=[]
        def stalled():calls.append(1);entered.set();release.wait(2);return {'stale':True}
        try:
            with self.assertRaises(TimeoutError):jobs.run('bad',stalled,.03)
            self.assertTrue(entered.is_set())
            with self.assertRaisesRegex(TimeoutError,'no se duplicará'):jobs.run('bad',stalled,.03)
            self.assertEqual(jobs.run('good',lambda:{'current':True},.3),{'current':True})
            self.assertEqual(calls,[1])
        finally:release.set()

    def test_late_result_is_never_reused_as_the_next_current_result(self):
        jobs=SourceDeadline();release=threading.Event();done=threading.Event()
        def old():release.wait(2);done.set();return 'OLD'
        with self.assertRaises(TimeoutError):jobs.run('feed',old,.02)
        release.set();self.assertTrue(done.wait(1))
        self.assertEqual(jobs.run('feed',lambda:'NEW',.3),'NEW')

    def test_alternative_keeps_original_error_age_and_provider_identity(self):
        rows={'global_news:Federal Reserve':{'enabled':True,'error':'DNS failed','updated':10},
              'global_news:CFTC':{'enabled':True,'fresh':True,'usable':True,'updated':99},
              'global_news:SEC':{'enabled':True,'fresh':False,'usable':True,'updated':5}}
        alternatives(rows);failed=rows['global_news:Federal Reserve']
        self.assertEqual(failed['fallback_sources'],['global_news:CFTC']);self.assertEqual(failed['updated'],10);self.assertEqual(failed['error'],'DNS failed')

    def test_repeated_provider_errors_open_circuit(self):
        from research import ContextWorker
        with tempfile.TemporaryDirectory() as tmp:
            worker=ContextWorker(load_config(DEFAULT),Path(tmp),clock=lambda:1000)
            try:
                with patch.object(worker,'jobs_for',return_value={}):
                    for _ in range(3):
                        f=Future();f.set_exception(OSError('getaddrinfo failed'));worker.jobs['venue:Bybit']=f;worker.tick()
                self.assertTrue(worker.sources['venue:Bybit']['circuit_open']);self.assertGreaterEqual(worker.due['venue:Bybit'],4600)
            finally:worker.close()


class YouTubeRecovery(unittest.TestCase):
    def test_caption_limit_keeps_discovered_videos_and_does_not_repeat_extraction(self):
        from research import ContextWorker
        from youtube_support import YouTubeError
        with tempfile.TemporaryDirectory() as tmp:
            cfg=load_config(DEFAULT);worker=ContextWorker(cfg,Path(tmp),clock=lambda:1000)
            try:
                with patch('research.youtube_search',return_value=[{'url':'https://youtube.com/watch?v=abc','title':'Discovered video'}]),patch('research.read_youtube',side_effect=YouTubeError('RATE_LIMITED','429')) as captions:
                    result=worker._youtube()
                    self.assertEqual(result['state'],'METADATA_ONLY');self.assertTrue(result['rows'])
                    self.assertTrue(all(not r['complete'] for r in result['rows']));self.assertEqual(captions.call_count,1)
                    again=worker._youtube();self.assertEqual(captions.call_count,1);self.assertTrue(again['rows'])
                    self.assertEqual(worker._strategy_reference()['state'],'NO_CAPTIONS')
                saved=worker.store.get('https://youtube.com/watch?v=abc');self.assertGreater(saved['caption_retry_after'],1000)
            finally:worker.close()

    def test_a_changed_api_key_is_not_subject_to_the_old_key_cooldown(self):
        import providers
        key=['old'];providers.reset_youtube_access()
        def api(query,credential):
            if credential=='old':raise RuntimeError('YouTube API HTTP 403 quotaExceeded')
            return [{'url':'https://youtube.com/watch?v=new'}]
        try:
            with patch('providers.get_secret',side_effect=lambda name:key[0]),patch('providers._youtube_api_search',side_effect=api) as request,patch('providers._youtube_ytdlp_search',return_value=[]):
                providers.youtube_search('one');self.assertGreater(providers._YT_API_BLOCK_UNTIL,time.monotonic())
                key[0]='new';rows=providers.youtube_search('two')
                self.assertTrue(rows);self.assertEqual(request.call_count,2);self.assertTrue(providers.youtube_access_status()['api_available'])
        finally:providers.reset_youtube_access()


class FinalAdmission(unittest.TestCase):
    def setUp(self):self.cfg=load_config(DEFAULT)
    def plan(self,**kwargs):
        p=Plan('BTCUSDm','SWING:SNAP:S:-1:M15:1',-1,'PENDING','STOP',80487.96,80581.13,80350.04,39.79,74.9,'Mapa táctico',1,activation_score=83.61,quality_score=75.92)
        return replace(p,**kwargs)
    def test_captured_tactical_b_plus_is_not_promoted_by_presence(self):
        r=pending_admission(self.cfg,self.plan());self.assertFalse(r['allowed']);self.assertEqual(r['grade'],'B+')
    def test_captured_gold_geometry_respects_configured_rr(self):
        p=self.plan(symbol='XAUUSDm',side=1,kind='LIMIT',entry=4050.62,sl=4046.952,tp=4058.096,quality_score=94.6,activation_score=86.4)
        r=pending_admission(self.cfg,p);self.assertFalse(r['allowed']);self.assertIn('R:R',r['reason'])
    def test_external_score_boost_cannot_rescue_a_weak_technical_baseline(self):
        p=self.plan(quality_score=99,activation_score=99,tp=80000,base_quality_score=60,base_activation_score=99)
        self.assertFalse(pending_admission(self.cfg,p)['allowed'])
    def test_qualified_tactical_entry_can_still_pass(self):
        p=self.plan(quality_score=95,activation_score=90,tp=80000)
        self.assertTrue(pending_admission(self.cfg,p)['allowed'])
    def test_high_money_limits_do_not_disable_quality(self):
        self.cfg['capital_protection'].update(trade_pct=100,portfolio_pct=100,symbol_pct=100,max_drawdown_pct=100,daily_loss_pct=100)
        self.assertFalse(pending_admission(self.cfg,self.plan())['allowed'])


class GatewayAdmission(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.cfg['capital_protection'].update(enabled=True,trade_pct=100,portfolio_pct=100,symbol_pct=100)
        self.cfg['execution']['minimum_structural_grade']='A';self.g.refresh_history(force=True)
    def test_direct_gateway_cannot_send_a_low_grade_tactical_candidate(self):
        p=replace(self.plan(),key='SWING:SNAP:L:1:M15:1',reason='Mapa táctico',quality_score=76,activation_score=85,tp=self.plan().entry+300)
        with self.assertRaisesRegex(Blocked,'Calidad estricta'):self.g.send_immediate_plan(p)
        self.assertFalse(self.api.sent)
    def test_prepared_request_rechecks_a_changed_rr_policy(self):
        p=self.plan();p=replace(p,tp=p.entry+400,quality_score=95,activation_score=95)
        prepared=self.g.prepare(p);self.cfg['strategy']['min_rr_pending']=5
        with self.assertRaisesRegex(Blocked,'R:R'):self.g.send(prepared)
        self.assertFalse(self.api.sent)


class ConversationalIntent(unittest.TestCase):
    def test_a_current_complaint_does_not_inherit_the_previous_fiction(self):
        from conversation_core import messages_for
        history=[{'role':'user','text':'Recuerda que prefiero explicaciones breves.'},{'role':'assistant','text':'Lo tendré presente.'},
            {'role':'user','text':'Cuéntame un chiste de computadora.'},{'role':'assistant','text':'Un ordenador se fue de vacaciones.'}]
        prompts=messages_for('Sí claro, qué brillante, volvió a congelarse /s',history)
        data=json.dumps(prompts,ensure_ascii=False)
        self.assertNotIn('vacaciones',data);self.assertIn('explicaciones breves',data)
        self.assertEqual(prompts[-2]['role'],'system');self.assertIn('turno actual',prompts[-2]['content'])
    def test_negative_response_is_not_confused_with_the_observed_affirmative_error(self):
        from conversation_intent import pragmatic_issue,nonliteral_hint
        question='Qué brillante, volvió a fallar /s. ¿Lo dije en serio?'
        self.assertTrue(pragmatic_issue(question,'¡Jaja! Lo dijiste en serio, pero es una ironía.'))
        self.assertTrue(pragmatic_issue(question,'No lo dijiste en serio. Es un chiste donde congelar tiene doble sentido.'))
        self.assertFalse(pragmatic_issue(question,'No, no lo dijiste en serio; es sarcasmo.'))
        self.assertFalse(nonliteral_hint('¿Qué es el sarcasmo?'))
        self.assertFalse(nonliteral_hint('No es broma: pon las mejores pendientes.'))
        self.assertTrue(pragmatic_issue('Gran idea, pon otra orden para perder otra vez /s','Mejor mueve los archivos a la papelera.'))
    def test_humour_goes_to_generation_without_web_lookup(self):
        from conversation_core import messages_for,needs_research
        from response_quality import answer_plan
        for question in ('qué te gusta hacer','Cuéntame un chiste','Sí claro, gran idea: perder otra vez /s'):
            with self.subTest(question=question):
                self.assertFalse(needs_research(question));self.assertEqual(messages_for(question)[-1]['content'],question)
                self.assertLessEqual(answer_plan(question)['tokens'],256)
    def test_sarcastic_financial_imperative_does_not_dispatch(self):
        from assistant_akira import AkiraAssistant
        with tempfile.TemporaryDirectory() as tmp:
            calls=[];bot=AkiraAssistant(load_config(DEFAULT),Path(tmp),trade_callback=lambda x:calls.append(x))
            try:
                question='Sí claro, gran idea: pon otra orden para perder otra vez /s'
                with patch.object(bot,'local_llm_reply',return_value='Entiendo la ironía; estás señalando el fallo.'):
                    answer=bot.reply(question,{},False)
                self.assertFalse(calls);self.assertIn('ironía',answer);self.assertFalse(bot.is_trade_control_message(question))
            finally:bot._managed_model.shutdown()
    def test_active_market_remains_visible_after_a_failed_chat(self):
        from conversation_core import activity_presentation
        result=activity_presentation({'phase':'ERROR','active':False},{'phase':'IDLE'},
            {'connected':True,'symbols':{'BTCUSDm':{'checked_at':100}}},100,now=101)
        self.assertIn('Analizando BTC',result['label']);self.assertIn('interrumpida',result['label'])


class LimitRecovery(unittest.TestCase):
    def frames(self,recovered):
        now=1800000000
        closed=now//900*900-900;hour=now//3600*3600-3600;five=now//300*300-300
        bar=lambda t,o,c,h=103,l=97:{'time':t,'open':o,'close':c,'high':h,'low':l}
        return now,{'M15':{'trend':-.8,'atr':5,'bars':[bar(closed-900,102,100),bar(closed,101,98)]},
            'H1':{'trend':.5,'atr':10,'bars':[bar(hour,98,101)]},
            'M5':{'trend':.2,'atr':2,'bars':[bar(five-300,99,100,h=101),bar(five,100,102 if recovered else 100.1)]}}
    def test_h1_alone_does_not_confirm_a_limit_rebound_against_m15(self):
        now,frames=self.frames(False)
        p=Plan('XAUUSDm','test',1,'PENDING','LIMIT',100,95,115,2,95,'',0,horizon_atr=5)
        r=evaluate(p,frames,[],now,strict=True)
        self.assertFalse(r['allowed']);self.assertTrue(any(c['name']=='Recuperación antes de LIMIT contra M15' and not c['passed'] for c in r['checks']))
    def test_closed_fresh_m5_reclaim_can_confirm_that_rebound(self):
        now,frames=self.frames(True)
        p=Plan('XAUUSDm','test',1,'PENDING','LIMIT',100,95,115,2,95,'',0,horizon_atr=5)
        r=evaluate(p,frames,[],now,strict=True)
        self.assertTrue(any(c['name']=='Recuperación antes de LIMIT contra M15' and c['passed'] for c in r['checks']))


if __name__=='__main__':unittest.main()
