"""R7 regressions: actual failure paths and prospective selection boundaries."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from strategy_adaptation import (StrategyAdaptation, advance, measured, holdout_passes,
    candidate_decision, execution_identity, digest)


SOURCE={'url':'https://www.youtube.com/watch?v=p579vzivHoc','title':'Reglas de prueba',
        'author':'Autor de prueba','complete':True,'status':'transcript',
        'body':('Confirmar tendencia H1, volumen y RSI; no inventar rentabilidad. ' * 40)}


class SourceAccess(unittest.TestCase):
    def test_application_shutdown_prevents_a_background_restart(self):
        from akira_model_runtime import ManagedLlamaProcess
        runtime=ManagedLlamaProcess({'local_runtime_enabled':True})
        runtime.shutdown()
        with patch('akira_model_runtime.subprocess.Popen') as launch,self.assertRaisesRegex(RuntimeError,'cerró'):
            runtime.start('http://127.0.0.1:18987/v1/chat/completions')
        launch.assert_not_called()

    def test_stale_configured_paths_recover_installed_model_and_cpu(self):
        import akira_model_runtime as module
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            exe=root/'local_ai/cpu/llama-server.exe';model=root/'local_ai/models/Qwen3-4B-Q4_K_M.gguf'
            exe.parent.mkdir(parents=True);model.parent.mkdir(parents=True)
            exe.write_bytes(b'MZtest');model.write_bytes(b'GGUFtest')
            runtime=module.ManagedLlamaProcess({'local_runtime_exe':'/old/llama-server.exe','local_runtime_model':'/old/Qwen3-4B-Q4_K_M.gguf'})
            with patch.object(module.sys,'frozen',True,create=True),patch.object(module.sys,'executable',str(root/'AKIRA.exe')):
                self.assertEqual(runtime._paths(),(exe.resolve(),model.resolve()))
                command=runtime.command('http://127.0.0.1:8080/v1/chat/completions')
                self.assertEqual(command[command.index('--n-gpu-layers')+1],'0')

    def test_child_output_is_written_to_the_diagnostic_log(self):
        import akira_model_runtime as module
        with tempfile.TemporaryDirectory() as temporary:
            runtime=module.ManagedLlamaProcess({'local_runtime_enabled':True},log_root=temporary)
            def launch(*args,**kwargs):
                kwargs['stdout'].write(b'failed to load model: diagnostic fixture\n')
                return Mock(poll=lambda:0)
            with patch.object(runtime,'command',return_value=['fixture']),patch.object(runtime,'_health',return_value=False),patch.object(module.subprocess,'Popen',side_effect=launch),patch.object(module.threading,'Thread'):
                runtime.start('http://127.0.0.1:8080/v1/chat/completions')
            self.assertIn('failed to load model',runtime.log_path.read_text(encoding='utf-8'))

    def test_youtube_session_is_explicit_and_preserves_spaces_in_path(self):
        from youtube_support import import_session,options
        from akira_secrets import get_secret
        with tempfile.TemporaryDirectory(prefix='Akira session ') as temporary,patch.dict(os.environ,{'LOCALAPPDATA':temporary}):
            path=Path(temporary)/'cookies.txt'
            path.write_text('# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tfixture\n.example.com\tTRUE\t/\tTRUE\t2147483647\tPRIVATE\tnot-imported\n',encoding='utf-8')
            saved=import_session(path)
            self.assertEqual(get_secret('YOUTUBE_COOKIES_FILE'),str(saved))
            self.assertIn('youtube.com',saved.read_text(encoding='utf-8'))
            self.assertNotIn('example.com',saved.read_text(encoding='utf-8'))
            self.assertEqual(options()['cookiefile'],str(saved))
            self.assertNotIn('cookiesfrombrowser',options())

    def test_authentication_and_optional_key_have_actionable_distinct_states(self):
        from youtube_support import explained
        from cyber_ui import source_presentation
        error=explained(RuntimeError("Sign in to confirm you're not a bot"))
        self.assertEqual(error.state,'AUTH_REQUIRED')
        self.assertEqual(source_presentation('youtube',{'error':str(error)})[1],'REQUIERE SESIÓN')
        self.assertEqual(source_presentation('coinglass:BTC',{'data':{'state':'CONFIG_REQUIRED'}})[1],'CLAVE OPCIONAL')

    def test_gold_never_uses_bitcoin_coinglass_data(self):
        from providers import coinglass_bundle
        with patch('providers.coinglass_auth_probe') as probe:
            self.assertEqual(coinglass_bundle('XAU')['state'],'UNSUPPORTED')
        probe.assert_not_called()

    def test_complete_caption_metadata_survives_restart(self):
        from knowledge import KnowledgeStore
        with tempfile.TemporaryDirectory() as temporary:
            store=KnowledgeStore(temporary);store.put(SOURCE)
            recovered=KnowledgeStore(temporary).get(SOURCE['url'])
            self.assertTrue(recovered['complete']);self.assertEqual(recovered['author'],SOURCE['author'])

    def test_partial_analysis_is_never_complete_evidence(self):
        from strategy_research import ResearchLedger
        with tempfile.TemporaryDirectory() as temporary:
            ledger=ResearchLedger(temporary)
            for status in ('partial','transcript_partial','vision_sampled'):
                self.assertFalse(ledger.add(url=SOURCE['url'],kind='youtube_vision',body=SOURCE['body'],status=status)['complete_evidence'])


class TextVideoAnalysis(unittest.TestCase):
    def test_bundled_text_model_analyzes_captions_without_video_download(self):
        import video_vision as module
        with patch.object(module,'local_status',return_value={'models':['Qwen3-4B-Q4_K_M.gguf']}),patch.object(module,'read_youtube',return_value=SOURCE),patch.object(module,'text_chat',return_value='Reglas observadas; hipótesis por validar.') as chat,patch.object(module,'_extract_video') as download:
            row=module.analyze_youtube_video(SOURCE['url'],local_text_model='Qwen3-4B-Q4_K_M.gguf',allow_cloud=False)
        download.assert_not_called();chat.assert_called()
        self.assertTrue(row['analysis_complete']);self.assertEqual(row['frames_analyzed'],0)
        self.assertEqual(row['_transcript']['body'],SOURCE['body'])

    def test_no_captions_never_reports_successful_analysis(self):
        import video_vision as module
        with patch.object(module,'local_status',return_value={'models':[]}),patch.object(module,'read_youtube',return_value={**SOURCE,'body':'','complete':False}),patch.object(module,'text_chat') as chat,patch.object(module,'_extract_video') as download:
            row=module.analyze_youtube_video(SOURCE['url'],allow_cloud=False)
        self.assertFalse(row['ok']);self.assertEqual(row['state'],'NO_CAPTIONS')
        chat.assert_not_called();download.assert_not_called()


class RepairedAssistantState(unittest.TestCase):
    def test_chat_and_research_share_one_supervisor_and_background_can_wake_it(self):
        from contextlib import nullcontext
        from akira_model_runtime import shared_runtime
        from research import ContextWorker,local_research_endpoint
        from settings import DEFAULT,load_config
        with tempfile.TemporaryDirectory() as temporary:
            cfg=load_config(DEFAULT)
            self.assertEqual(local_research_endpoint(cfg),cfg['assistant']['local_endpoint'])
            custom=copy.deepcopy(cfg);custom['research']['local_ai_endpoint']='http://127.0.0.1:19999/v1/chat/completions'
            self.assertEqual(local_research_endpoint(custom),custom['research']['local_ai_endpoint'])
            runtime=shared_runtime(cfg['assistant'],temporary)
            self.assertIs(runtime,shared_runtime(copy.deepcopy(cfg['assistant']),temporary))
            worker=ContextWorker(cfg,Path(temporary));self.addCleanup(worker.close)
            with patch.object(runtime,'_paths',return_value=(Path('engine.exe'),Path('model.gguf'))),patch.object(runtime,'session',side_effect=lambda *a,**k:nullcontext()) as session,patch.object(worker,'_pending_summary_impl',return_value={'verified':'fixture'}) as analysis:
                self.assertEqual(worker._pending_summary([],{}),{'verified':'fixture'})
                session.assert_called_once();analysis.assert_called_once()

    def test_failed_boot_is_not_reported_as_normal_idle(self):
        from tests.test_r5_user_video_regressions import AssistantStatusIsNotFaked
        for verified in (False,True):
            assistant=AssistantStatusIsNotFaked.assistant()
            assistant._managed_model_boot_attempted=True;assistant._model_inference_verified=verified
            assistant._model_inference_error='Error de arranque real de prueba'
            with self.subTest(verified=verified),patch('assistant_akira.ollama_status',return_value={'ok':False}):
                assistant._probe_local_status(0)
                self.assertEqual(assistant._status['phase'],'IDLE' if verified else 'FAILED')

    def test_repair_is_ready_only_after_visible_generation(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from assistant_akira import AkiraAssistant
        from settings import DEFAULT,load_config
        for text in ('Hola.',''):
            with self.subTest(text=text),tempfile.TemporaryDirectory() as temporary:
                assistant=AkiraAssistant(load_config(DEFAULT),Path(temporary))
                assistant._managed_model=Mock()
                import threading
                assistant._managed_model.lock=threading.RLock();assistant._managed_model.active=0
                assistant._managed_model.enabled.return_value=True
                assistant._managed_model._paths.return_value=(Path('engine.exe'),Path('model.gguf'))
                assistant._managed_model.session.return_value=nullcontext()
                assistant._model_inference_verified=True  # a prior success cannot mask a failed repair
                def immediate(target,**kwargs):return SimpleNamespace(start=target)
                with patch('assistant_akira.threading.Thread',side_effect=immediate),patch('akira_local_ai.chat',return_value=text):
                    assistant.retry_local_preparation()
                self.assertEqual(assistant._status['ready'],bool(text))
                self.assertEqual(assistant._status['phase'],'READY' if text else 'FAILED')


class ProspectiveLearning(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.now=1800000000.;self.lab=StrategyAdaptation(self.temporary.name,{},clock=lambda:self.now)
        self.profiles=self.lab.ingest_source(SOURCE)
        self.group=['PENDIENTE_RETROCESO','BTCUSDm',1]

    def insert_closed(self,start,n,spacing=1):
        with self.lab.db() as db:
            for i in range(n):
                created=start+i*spacing;passed=i%2==0
                row={'id':str(created),'group':self.group,'code':'H1_ALIGNMENT','rule_version':1,
                     'created':created,'closed_at':created+1,'passed':passed,'net_r':1.0 if passed else -1.0,
                     'sources':[{'url':SOURCE['url'],'sha256':hashlib.sha256(SOURCE['body'].encode()).hexdigest()}]}
                db.execute('INSERT INTO trials VALUES (?,?,?,?,?,?)',(str(created),'cohort',json.dumps([*self.group,'H1_ALIGNMENT']),'CLOSED',created,json.dumps(row)))

    def test_missing_or_partial_source_cannot_create_profiles(self):
        self.assertEqual(self.lab.ingest_source({**SOURCE,'complete':False}),[])
        self.assertEqual(self.lab.ingest_source({**SOURCE,'body':'RSI'}),[])
        self.assertEqual(set(self.profiles),{'H1_ALIGNMENT','VOLUME','RSI','CONFLUENCE'})

    def test_training_cannot_activate_a_filter_and_late_results_do_not_rewrite_it(self):
        self.insert_closed(self.now-100,40)
        self.lab.evaluate('cohort','identity',[],self.now)
        first=self.lab.read();self.assertFalse(first['policies']);self.assertTrue(first['studies'][0]['train_passed'])
        frozen=first['studies'][0]['train_ids']
        self.insert_closed(self.now-1000,5)
        self.lab.evaluate('cohort','identity',[],self.now+100)
        self.assertEqual(self.lab.read()['studies'][0]['train_ids'],frozen)
        self.assertEqual(self.lab.read()['studies'][0]['holdout']['n'],0)

    def test_independent_forward_evidence_can_reach_selection_and_expires(self):
        self.insert_closed(self.now-100,40)
        self.lab.evaluate('cohort','identity',[],self.now)
        frozen_at=self.now
        self.insert_closed(frozen_at+86400,100,spacing=86400/5)
        self.now=frozen_at+22*86400
        self.lab.evaluate('cohort','identity',[],self.now)
        summary=self.lab.read();self.assertEqual(len(summary['policies']),1)
        context={'strategy_lab':{'adaptation':summary},'execution_identity':'identity'}
        plan={'symbol':'BTCUSDm','side':1,'lane':'PENDING','kind':'LIMIT','key':'test'}
        self.assertFalse(candidate_decision(plan,{'H1':{'trend':.2}},context,self.now)[0])
        self.assertTrue(candidate_decision(plan,{'H1':{'trend':.8}},context,self.now)[0])
        self.assertTrue(candidate_decision(plan,{'H1':{'trend':.2}},context,self.now+121)[0])
        context['execution_identity']='different account'
        self.assertTrue(candidate_decision(plan,{'H1':{'trend':.2}},context,self.now)[0])

    def test_large_sample_without_twenty_distinct_days_is_not_validated(self):
        rows=[{'created':self.now+i,'passed':i%2==0,'net_r':1 if i%2==0 else -1} for i in range(200)]
        self.assertFalse(holdout_passes(measured(rows)))

    def test_stop_trigger_and_gap_cannot_manufacture_a_winner(self):
        case={'state':'WAITING','last_quote':self.now,'created':self.now,'risk':10,'fee_r':.1,
              'plan':{'side':1,'entry':100,'sl':90,'tp':120,'kind':'STOP'}}
        untouched=advance(case,98,99,self.now+1);self.assertEqual(untouched['state'],'WAITING')
        filled=advance(untouched,100,101,self.now+2);self.assertEqual(filled['fill'],101)
        closed=advance(filled,121,122,self.now+3);self.assertAlmostEqual(closed['net_r'],1.8)
        self.assertEqual(advance(case,121,122,self.now+61)['state'],'GAP')
        self.assertEqual(advance(case,121,122,self.now+1)['state'],'INVALID_FILL')

    def test_missing_costs_cannot_enter_a_study(self):
        plan={'symbol':'BTCUSDm','side':1,'entry':100,'sl':90,'tp':120,'bar_time':self.now-900,'lane':'RUNNER','kind':'MARKET'}
        snapshot={'symbols':{'BTCUSDm':{'bid':99,'ask':100,'quote_time':self.now,'frames':{'H1':{'trend':.4}},'adaptation_candidates':[plan]}}}
        self.lab.observe(snapshot)
        with self.lab.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM trials').fetchone()[0],0)


if __name__=='__main__':unittest.main()
