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


class ModelMigrationAndTemplate(unittest.TestCase):
    def test_bundled_gemma_on_small_cpu_avoids_a_duplicate_mapping_and_keeps_cpu_kernels(self):
        from akira_model_runtime import ManagedLlamaProcess,hardware_profile
        from bundled_model import MODEL_NAME
        runtime=ManagedLlamaProcess({'local_runtime_enabled':True},profile=hardware_profile(8,0,4))
        with patch.object(runtime,'_paths',return_value=(Path('/cpu/llama-server.exe'),Path('/models')/MODEL_NAME)):
            command=runtime.command('http://127.0.0.1:18987/v1/chat/completions',{'performance_profile':'Ahorro de energía','model_use_gpu':False})
        self.assertEqual(command[command.index('--load-mode')+1],'dio');self.assertNotIn('--no-repack',command)
        self.assertEqual(command[command.index('--cache-ram')+1],'0')

    def test_relative_bundled_model_migrates_without_rewriting_custom_gguf_or_money(self):
        from bundled_model import MODEL_NAME,MODEL_PATH,LEGACY_MODEL_NAME,LEGACY_MODEL_PATH
        raw=copy.deepcopy(DEFAULT);raw['assistant'].update(local_model=LEGACY_MODEL_NAME,local_runtime_model=LEGACY_MODEL_PATH)
        raw['capital_protection'].update(trade_pct=100,portfolio_pct=100,symbol_pct=100,daily_loss_pct=100,max_drawdown_pct=100)
        before=copy.deepcopy(raw);migrated=load_config(raw)
        self.assertEqual(migrated['assistant']['local_runtime_model'],MODEL_PATH);self.assertEqual(migrated['assistant']['local_model'],MODEL_NAME)
        self.assertEqual(migrated['capital_protection'],raw['capital_protection']);self.assertEqual(raw,before)
        for custom in ('my-model.gguf','C:/private/models/'+LEGACY_MODEL_NAME):
            with self.subTest(custom=custom):
                raw['assistant']['local_runtime_model']=custom
                self.assertEqual(load_config(raw)['assistant']['local_runtime_model'],custom)

    def test_strict_template_receives_one_system_role_and_an_unchanged_question(self):
        from akira_local_ai import chat
        question='Se volvió a congelar /s. ¿Lo dije en serio?'
        messages=[{'role':'system','content':'/no_think\nbase'},{'role':'user','content':'anterior'},
                  {'role':'assistant','content':'respuesta'},{'role':'system','content':'intención'},
                  {'role':'system','content':'longitud'},{'role':'user','content':question}]
        original=copy.deepcopy(messages)
        def strict_server(endpoint,payload,**kwargs):
            self.assertEqual([i for i,m in enumerate(payload['messages']) if m['role']=='system'],[0])
            self.assertIn('intención',payload['messages'][0]['content']);self.assertIn('longitud',payload['messages'][0]['content'])
            self.assertEqual(payload['messages'][1:3],messages[1:3]);self.assertEqual(payload['messages'][-1]['content'],question)
            self.assertEqual(payload['top_k'],64);self.assertEqual(payload['seed'],42)
            if payload['model'].startswith('gemma'):self.assertNotIn('/no_think',payload['messages'][0]['content'])
            return {'choices':[{'message':{'role':'assistant','content':'Respuesta generada'},'finish_reason':'stop'}]}
        for model in ('Qwen3-4B-Q4_K_M.gguf','gemma-4-E2B-it-Q4_K_M.gguf'):
            with self.subTest(model=model),patch('akira_local_ai._post',side_effect=strict_server):
                self.assertEqual(chat(messages,model=model,endpoint='http://127.0.0.1:18996/v1/chat/completions',options={'top_k':64,'seed':42}),'Respuesta generada')
        self.assertEqual(messages,original)

    def test_failed_sarcasm_reply_does_not_claim_the_user_requested_an_old_joke_again(self):
        from assistant_akira import AkiraAssistant
        with tempfile.TemporaryDirectory() as tmp:
            bot=AkiraAssistant(load_config(DEFAULT),Path(tmp))
            try:
                bot._remember_turn('Explícame el juego de palabras de espacio.','El chiste del ordenador.')
                with patch.object(bot,'local_llm_reply',side_effect=TimeoutError('fixture')):
                    answer=bot.reply('Sí claro, se volvió a congelar /s. ¿Lo dije en serio?',{},False)
                self.assertIn('Reintentar',answer);self.assertNotIn('juego de palabras',answer)
                self.assertNotIn('Me estás reclamando la respuesta a',answer)
            finally:bot._managed_model.shutdown()


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
        self.assertTrue(pragmatic_issue(question,'No lo dije en serio.'))
        self.assertFalse(pragmatic_issue(question,'No, no lo dijiste literalmente. Tu tono sarcástico indica que estás descontento por un fallo.'))
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
