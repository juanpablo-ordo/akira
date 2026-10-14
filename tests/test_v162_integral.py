"""Functional regressions. Fixtures validate behavior, never financial superiority."""
import copy,io,json,os,tempfile,time,unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from urllib.error import HTTPError
from settings import DEFAULT,load_config,save_config
from tests.fixtures import PendingCase
from execution import Blocked,DEAL,OWN_PENDING,OWN_RUNNER
from engine import Engine

class Execution162(PendingCase,unittest.TestCase):
    def test_default_rejects_direct_runner_without_sending_or_cancelling(self):
        p=replace(self.plan(),lane='RUNNER',kind='MARKET')
        self.assertTrue(self.cfg['execution']['pending_only'])
        with self.assertRaisesRegex(Blocked,'exclusivamente pendientes'):self.g.send_runner(p)
        self.assertFalse(self.api.sent)
    def test_default_engine_never_calls_market_runner_send(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close)
        with patch.object(self.g,'send_runner',side_effect=AssertionError('Market entry')):self.assertFalse(e.try_runner('BTCUSDm',self.g.quote('BTCUSDm')))
    def test_study_configuration_freezes_models_and_source_weights_without_credentials(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close)
        first=e.view()['selection_configuration'];model=first['model_configuration']['trading_model']
        self.cfg['assistant']['trading_model']='changed-model';self.cfg['research']['cloud_pick_bonus']=99
        second=e.view()['selection_configuration']
        self.assertEqual(first['model_configuration']['trading_model'],model)
        self.assertEqual(second['model_configuration']['trading_model'],'changed-model')
        self.assertNotEqual(first,second);self.assertNotIn('OPENAI_API_KEY',str(second))
    def test_receipt_distinguishes_risk_approval_from_real_broker_check(self):
        p=self.plan();self.g.validate_plan(p,self.g.snapshot())
        self.assertTrue(self.g.verification_receipts[p.key]['risk_passed']);self.assertFalse(self.g.verification_receipts[p.key]['broker_checked'])
        self.g.prepare(p);self.assertTrue(self.g.verification_receipts[p.key]['broker_checked']);self.assertFalse(self.api.sent)
    def test_receipt_records_rejection_and_does_not_claim_check_passed(self):
        p=self.plan();self.api.fail_check=10016
        with self.assertRaises(Blocked):self.g.prepare(p)
        self.assertFalse(self.g.verification_receipts[p.key]['broker_checked'])
    def test_setting_transaction_reaches_effective_motor_values(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close);c=copy.deepcopy(self.cfg);c['risk']['max_trade_money']=1.23
        r=e.handle_command({'action':'apply_settings','config':c,'changed_paths':['risk.max_trade_money']})
        self.assertTrue(r['settings_applied']);self.assertEqual(self.g.trade_cap(self.g.snapshot()),1.23)
    def test_delayed_setting_packet_cannot_restore_an_older_risk_limit(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close);new=copy.deepcopy(self.cfg);new['risk']['max_trade_money']=1.5
        e.handle_command({'action':'apply_settings','config':new,'changed_paths':['risk.max_trade_money'],'settings_revision':200})
        old=copy.deepcopy(self.cfg);old['risk']['max_trade_money']=3
        result=e.handle_command({'action':'apply_settings','config':old,'changed_paths':['risk.max_trade_money'],'settings_revision':100})
        self.assertTrue(result['stale_settings']);self.assertEqual(self.g.cfg['risk']['max_trade_money'],1.5)
    def test_pending_fill_can_close_structurally_and_external_position_cannot(self):
        self.g.send_immediate_plan(self.plan());p=self.plan();self.api.set_quote(p.symbol,p.entry-1,.1)
        self.g.reconcile(self.g.snapshot());position=self.api.positions[0]
        self.assertEqual(position.magic,OWN_PENDING);self.assertTrue(self.g.managed_runner(position))
        self.g.close_runner(position,'M15 invalidada');self.assertEqual(self.api.sent[-1]['action'],DEAL)
        external=NS(**{**vars(position),'magic':123});self.assertFalse(self.g.managed_runner(external))
    def test_tp_extension_requires_opt_in_and_never_widens_stop(self):
        p=self.plan();self.g.send_immediate_plan(p);self.api.set_quote(p.symbol,p.entry-1,.1);self.g.reconcile(self.g.snapshot());position=self.api.positions[0]
        self.assertFalse(self.g.update_stop(position,position.sl,tp=position.tp+100))
        self.cfg['management']['extend_targets']=True;old_sl=position.sl;old_tp=position.tp
        self.assertTrue(self.g.update_stop(position,position.sl,tp=position.tp+100));self.g.reconcile(self.g.snapshot())
        current=self.api.positions[0];self.assertEqual(current.sl,old_sl);self.assertGreater(current.tp,old_tp)
        self.assertFalse(self.g.update_stop(current,current.sl-1,tp=current.tp+100))
    def test_daily_limit_blocks_entry_but_not_protection_permission(self):
        self.g.snapshot();self.g.history_error='';self.cfg['risk']['daily_loss_money']=1;self.g.history_time=self.clock();self.g.history=[NS(time=self.clock(),type=1,profit=-2,commission=0,swap=0,fee=0)]
        with self.assertRaisesRegex(Blocked,'diaria alcanzado'):self.g.permissions(self.g.snapshot())
        self.g.permissions(self.g.snapshot(),entry=False)
    def test_daily_limit_requires_fresh_history(self):
        self.cfg['risk']['daily_loss_pct']=1
        with self.assertRaisesRegex(Blocked,'historial MT5 vigente'):self.g.prepare(self.plan())

class TempCase162(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

class Services162(TempCase162):
    def test_api_default_migration_preserves_custom_models_and_financial_limits(self):
        cfg=load_config(DEFAULT);risk=copy.deepcopy(cfg['risk'])
        cfg['assistant'].update(model='gpt-6.1-sol',general_model='gpt-6-luna',trading_model='gpt-user-selected')
        cfg['research']['model']='gpt-6.1-sol';out=load_config(cfg)
        self.assertEqual(out['assistant']['general_model'],'gpt-4.1')
        self.assertEqual(out['assistant']['model'],'gpt-4.1')
        self.assertEqual(out['research']['model'],'gpt-4.1')
        self.assertEqual(out['assistant']['trading_model'],'gpt-user-selected');self.assertEqual(out['risk'],risk)
    def test_explicit_knowledge_refresh_works_with_automatic_updates_disabled(self):
        from knowledge_update import KnowledgeUpdater
        cfg=load_config(DEFAULT);cfg['knowledge']['enabled']=False
        fetch=NS();events=[]
        with patch('knowledge_update.CATALOG',[('Doc','https://example.org/doc','Official')]),patch('knowledge_update.update_reference'):
            updater=KnowledgeUpdater(cfg,self.root,events.append,fetch=lambda *a:{'fetched':time.time(),'characters':12})
            with patch.object(updater,'fetch',wraps=updater.fetch) as call:
                updater.tick();self.assertEqual(call.call_count,0)
                updater.refresh();updater.tick();self.assertEqual(call.call_count,1)
                updater.next_due=0;updater.tick();self.assertEqual(call.call_count,1)
        self.assertFalse(cfg['knowledge']['enabled']);self.assertEqual(updater.read()['state'],'ACTUALIZADO')
    def test_cache_cleans_only_obsolete_actual_voice_download_temporaries(self):
        from cache_maintenance import candidates,clean
        folder=self.root/'state/voices';folder.mkdir(parents=True)
        for name in ('old.onnx.part','installed.onnx','installed.onnx.json'):
            p=folder/name;p.write_bytes(b'voice');os.utime(p,(1,1))
        preview=candidates(self.root);self.assertEqual([Path(p[0]).name for p in preview['files']],['old.onnx.part'])
        clean(self.root,preview);self.assertFalse((folder/'old.onnx.part').exists())
        self.assertTrue((folder/'installed.onnx').exists());self.assertTrue((folder/'installed.onnx.json').exists())
    def test_notification_history_survives_restart_and_masks_keys(self):
        from notification_center import NotificationCenter
        center=NotificationCenter(self.root);center.add('Rechazo MT5','API key: sk-dummy-secret',severity='error')
        other=NotificationCenter(self.root);self.assertEqual(other.unread(),1);self.assertNotIn('sk-dummy',str(other.list()))
        other.mark_read();self.assertEqual(center.unread(),0)
    def test_notification_retention_is_bounded(self):
        from notification_center import NotificationCenter
        center=NotificationCenter(self.root)
        for i in range(1005):center.add(str(i),'Aviso')
        self.assertEqual(len(center.list(limit=5000)),1000)
    def test_config_changes_report_only_changed_target_and_persist(self):
        from settings_effects import changes,validate_form
        c=load_config(DEFAULT);after=copy.deepcopy(c);after['desktop']['width']=1200
        rows=changes(c,validate_form(after));self.assertEqual([r['path'] for r in rows],['desktop.width'])
        save_config(after,self.root/'cfg.json');self.assertEqual(load_config(self.root/'cfg.json')['desktop']['width'],1200)
    def test_invalid_settings_are_rejected(self):
        from settings_effects import validate_form
        for path,value in [('desktop.width',100),('knowledge.mode','invalid'),('knowledge.interval_hours',float('nan')),('risk.daily_loss_pct',101)]:
            c=load_config(DEFAULT);a,b=path.split('.');c[a][b]=value
            with self.subTest(path=path),self.assertRaises(ValueError):validate_form(c)
    def test_cache_preview_and_delete_preserve_important_data_and_new_files(self):
        from cache_maintenance import candidates,clean
        from knowledge import KnowledgeStore
        old=self.root/'state/research_cache/old.tmp';old.parent.mkdir(parents=True);old.write_bytes(b'old cache');os.utime(old,(1,1))
        for f in ('state/chats.sqlite3','state/quality.sqlite','state/voices/live.onnx','AKIRA_SECRETS.json','akira_config.json','logs/audit.jsonl'):
            p=self.root/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'protected');os.utime(p,(1,1))
        store=KnowledgeStore(self.root);store.put({'url':'https://example.org/old','kind':'search','body':'Recoverable','fetched':1})
        store.put({'url':'akira://reference','kind':'reference','body':'Important reference','fetched':1})
        now=time.time();preview=candidates(self.root,14,clock=lambda:now);self.assertEqual(len(preview['files']),1)
        result=clean(self.root,preview);self.assertEqual(result['files_removed'],1);self.assertIsNone(store.get('https://example.org/old'));self.assertIsNotNone(store.get('akira://reference'))
        self.assertTrue((self.root/'state/voices/live.onnx').exists());self.assertTrue((self.root/'logs/audit.jsonl').exists())
    def test_cache_changed_after_preview_is_not_deleted(self):
        from cache_maintenance import candidates,clean
        old=self.root/'state/http_cache/old.tmp';old.parent.mkdir(parents=True);old.write_bytes(b'old');os.utime(old,(1,1))
        preview=candidates(self.root);old.write_bytes(b'new request');clean(self.root,preview);self.assertTrue(old.exists())
    def test_knowledge_request_mode_does_not_fetch_until_requested(self):
        from knowledge_update import KnowledgeUpdater
        c=load_config(DEFAULT);c['knowledge']['mode']='request';events=[];fetch=NS()
        with patch('knowledge_update.CATALOG',[('Doc','https://example.org/doc','Official')]):
            def update(root,url):return {'fetched':time.time(),'characters':100}
            updater=KnowledgeUpdater(c,self.root,events.append,fetch=update)
            with patch.object(updater,'fetch',wraps=update) as call:
                updater.tick();updater.tick();self.assertEqual(call.call_count,0);self.assertEqual(len(events),1)
                updater.refresh();updater.tick();self.assertEqual(call.call_count,1);self.assertEqual(updater.read()['state'],'ACTUALIZADO')
    def test_knowledge_automatic_update_indexes_dated_content_and_reuses_it(self):
        from knowledge_update import KnowledgeUpdater
        from knowledge import KnowledgeStore
        def fetch(root,url):
            stamp=time.time();KnowledgeStore(root).put({'url':url,'title':'Física','body':'Conservación del momentum','kind':'reference','fetched':stamp});return {'fetched':stamp,'characters':100}
        with patch('knowledge_update.CATALOG',[('Doc','https://example.org/doc','Official')]):
            updater=KnowledgeUpdater(load_config(DEFAULT),self.root,fetch=fetch);updater.tick();updater.refresh()
            with patch.object(updater,'fetch',side_effect=AssertionError('Fresh source was fetched again')):updater.tick()
        self.assertEqual(updater.read()['sources'][0]['state'],'EN CACHÉ');self.assertTrue(KnowledgeStore(self.root).search('momentum'))
    def test_full_text_index_updates_replaced_sources_without_ghost_matches(self):
        from knowledge import KnowledgeStore
        store=KnowledgeStore(self.root);store.put({'url':'https://example.org/a','title':'A','body':'Conservación del momentum'})
        self.assertTrue(store.search('momentum'));store.put({'url':'https://example.org/a','title':'A','body':'Órbitas planetarias'})
        self.assertFalse(store.search('momentum'));self.assertTrue(store.search('orbitas'))
    def test_chat_search_recovers_body_and_trash_restores_history(self):
        from chat_store import ChatStore
        store=ChatStore(self.root);cid=store.active;store.append('user','Estudiemos telescopios galácticos');self.assertTrue(store.list('telescopios'))
        store.delete(cid);self.assertFalse(store.list('telescopios'));self.assertEqual(store.trash()[0]['id'],cid)
        self.assertTrue(store.restore(cid));self.assertIn('telescopios',store.history()[0]['text'])

class Sources162(TempCase162):
    def worker(self):
        from research import ContextWorker
        w=ContextWorker(load_config(DEFAULT),self.root,clock=lambda:1000);self.addCleanup(w.close);return w
    def test_disabling_cached_sources_removes_their_fusion_and_content(self):
        w=self.worker();w.sources={'local_ai':{'updated':1000,'data':{'BTCUSDm':{'bias':1,'confidence':.35,'note':'old'}}},'model':{'updated':1000,'data':{'BTCUSDm':{'bias':1}}},'youtube':{'updated':1000,'data':{'rows':[{'url':'https://example.org/video','body':'private excerpt'}]}}}
        w.cfg['research']['local_model']=False;w.cfg['research']['youtube']=False;row=w.read()
        self.assertFalse(row['sources']['local_ai']['fresh']);self.assertFalse(row['videos']);self.assertFalse(row['deep_review']);self.assertFalse(row['models'])
        self.assertFalse(w.source_enabled('local_ai'))
    def test_jobs_honor_local_synthesis_setting(self):
        w=self.worker();w.cfg['research']['local_model']=False
        jobs=w.jobs_for({'symbols':{'BTCUSDm':{}}},{})
        self.assertNotIn('local_ai',jobs);self.assertNotIn('model',jobs)
    def test_empty_fresh_provider_is_not_presented_as_usable_evidence(self):
        from operation_verifier import verification
        w=self.worker();w.sources={'news':{'updated':1000,'data':{'items':[]}}};row=w.read()
        self.assertTrue(row['sources']['news']['fresh']);self.assertFalse(row['sources']['news']['usable'])
        result=verification({'symbols':{'BTCUSDm':{}},'research':row},'BTCUSDm')
        self.assertFalse(any(s['name']=='Noticias y macro' and s['state']=='DISPONIBLE' for s in result['stages']))
    def test_all_external_toggle_families_disable_cached_contributions(self):
        w=self.worker()
        for flag,name in [('global_markets','venue:OKX'),('global_news','global_news:SEC'),('investing','news'),('coinglass','coinglass:BTCUSDm'),('coinglass_public_fallback','derivatives:BTCUSDm'),('technical_search','technical:BTCUSDm')]:
            with self.subTest(flag=flag):w.cfg['research'][flag]=False;self.assertFalse(w.source_enabled(name))
    def test_public_research_cache_reuses_fresh_results_and_force_refreshes(self):
        from assistant_akira import AkiraAssistant
        assistant=AkiraAssistant(load_config(DEFAULT),self.root)
        with patch.object(assistant,'_research_public_web',return_value={'results':[{'url':'https://example.org/x'}]}) as lookup:
            assistant._source_tool('research_public_web',{'query':'Mars moons'});r=assistant._source_tool('research_public_web',{'query':'Mars moons'});self.assertTrue(r['cache_reused']);self.assertEqual(lookup.call_count,1)
            assistant._source_tool('research_public_web',{'query':'Mars moons','force':True});self.assertEqual(lookup.call_count,2)

class ChartsAndStudy162(TempCase162):
    def test_chart_indicators_match_same_closed_bar_calculations(self):
        from strategy import Bar,frame
        from chart_indicators import indicator_chart
        bars=[Bar(i*900,100+i*.1,102+i*.1,98+i*.1,101+i*.1,100+i) for i in range(80)]
        data=indicator_chart([b.to_dict() for b in bars]);f=frame('M15',bars)
        self.assertAlmostEqual(data['series']['RSI'][-1],f.rsi);self.assertAlmostEqual(data['series']['MACD'][-1],f.macd_hist);self.assertAlmostEqual(data['series']['ADX'][-1],f.extra['adx'])
    def test_chart_insufficient_history_has_no_invented_series(self):
        from chart_indicators import indicator_chart
        self.assertFalse(indicator_chart([])['series'])
    def test_verifier_does_not_convert_missing_checks_to_full_progress(self):
        from operation_verifier import verification
        result=verification({'symbols':{'BTCUSDm':{}},'research':{'sources':{}}},'BTCUSDm')
        self.assertLess(result['progress'],100);self.assertIsNone(result['activation_estimate']);self.assertFalse(result['risk_receipt'])
    def test_quality_study_refuses_preview_as_financial_evidence(self):
        from quality_study import QualityStudy
        study=QualityStudy(self.root)
        with self.assertRaises(ValueError):study.capture({'preview':True})
    def test_full_candidate_book_is_frozen_without_inflating_repeated_cycles(self):
        from quality_study import QualityStudy
        study=QualityStudy(self.root);p={'side':1,'kind':'LIMIT','entry':100,'sl':98,'tp':104,'quality_score':90,'activation_score':80}
        pool=[{**p,'key':str(i),'entry':100-i*.01} for i in range(20)]
        snapshot={'connected':True,'as_of_utc':1000,'account':{'login':1,'server':'fixture'},'symbols':{'BTCUSDm':{'bid':101,'ask':101.1,'quote_time':1000,'frames':{'M15':{'last_bar':900}},'scenario_book':[p]}},'audit':{'BTCUSDm':pool}}
        study.capture(snapshot);study.capture(snapshot)
        with study.db() as db:
            books=db.execute('SELECT plans FROM candidate_books').fetchall();self.assertEqual(len(books),1);self.assertEqual(len(json.loads(books[0][0])),20)
    def test_selectors_empty_data_cannot_claim_superiority_or_probabilities(self):
        from selection_trials import compare_selectors
        result=compare_selectors([],{});self.assertFalse(result['superiority_confirmed']);self.assertFalse(result['validated_probabilities'])
    def test_calibration_requires_chronological_holdout_and_beats_baseline(self):
        from selection_trials import calibrate,POLICIES
        def dataset(days,start):
            rows=[]
            for day in range(days):
                for i in range(20):
                    high=i<10;y=(i%10!=0) if high else (i%10==0)
                    rows.append({'start':start+day*86400+i*60,'baseline_plan':{'kind':'LIMIT','quality_score':90 if high else 60,'activation_score':75 if high else 25},'results':{POLICIES[0]:{'activated':y,'net_r':1 if y else 0}}})
            return rows
        self.assertFalse(calibrate(dataset(10,0),dataset(2,10*86400)))
        models=calibrate(dataset(70,0),dataset(40,70*86400));self.assertIn('activation',models)
        self.assertLess(models['activation']['brier'],models['activation']['baseline_brier'])
    def test_selector_comparison_uses_common_quotes_cost_and_excludes_gaps(self):
        from selection_trials import compare_selectors
        from paired_study import PROTOCOL
        cases=[];quotes=[]
        for day in range(10):
            start=1000+day*86400
            for key,q,a,entry,sl in [('q',95,30,100,98),('near',80,95,99,97)]:
                cases.append({'id':str(day)+key,'symbol':'BTCUSDm','at':start,'bar':start-100,'plan':{'side':1,'kind':'LIMIT','quality_score':q,'activation_score':a,'entry':entry,'sl':sl,'tp':104},'snapshot':{'quote_provider':'MT5 test','build':'TEST','configuration_fingerprint':'fixed','frames':{'H1':{'trend':1},'M15':{'adx':30}}}})
            quotes += [{'utc':start,'bid':101,'ask':101.1,'cost_r':.1},{'utc':start+30,'bid':99.9,'ask':100,'cost_r':.1},{'utc':start+60,'bid':104,'ask':104.1,'cost_r':.1}]
        protocol={**PROTOCOL,'horizon_seconds':120,'entry_expiry_seconds':60,'minimum_holdout_pairs':2,'minimum_holdout_days':2}
        result=compare_selectors(cases,{('BTCUSDm','MT5 test'):quotes},protocol);group=next(iter(result['groups'].values()))
        self.assertEqual(group['holdout_days'],3);self.assertAlmostEqual(group['policies']['Calidad técnica']['mean_net_r'],1.9);self.assertEqual(group['policies']['Cercanía']['activation_rate'],0)
        self.assertFalse(group['apply_automatically']);self.assertFalse(result['superiority_confirmed'])
        broken=[q for q in quotes if q['utc']%86400==1000]
        bad=compare_selectors(cases,{('BTCUSDm','MT5 test'):broken},protocol);self.assertFalse(bad['groups']);self.assertTrue(bad['discarded'])
    def test_evaluating_internal_profiles_does_not_need_invented_chatgpt_references(self):
        from quality_study import QualityStudy
        study=QualityStudy(self.root);r=study.evaluate_selectors(0);self.assertFalse(r['groups']);self.assertEqual(study.summary()['comparisons'],0);self.assertIn('selector_comparison',study.summary())

class Cloud162(TempCase162):
    def test_windows_dpapi_write_stores_ciphertext_and_roundtrips_credentials(self):
        import akira_secrets,sys
        value='sk-private-fixture';plain=json.dumps({'OPENAI_API_KEY':value}).encode();target=self.root/'protected.json'
        crypt=NS(CryptProtectData=lambda *a:b'ciphertext',CryptUnprotectData=lambda *a:('AKIRA',plain))
        fake_os=NS(name='nt',chmod=os.chmod,fsync=os.fsync)
        with patch.object(akira_secrets,'os',fake_os),patch.object(akira_secrets,'canonical_path',return_value=target),patch.dict(sys.modules,{'win32crypt':crypt}):
            akira_secrets.save_secrets({'OPENAI_API_KEY':value},merge=False)
            self.assertNotIn(value,target.read_text());self.assertEqual(akira_secrets._read(target)['OPENAI_API_KEY'],value)
    def test_failed_encryption_does_not_overwrite_existing_secret_store(self):
        import akira_secrets,sys
        target=self.root/'protected.json';target.write_bytes(b'previous protected credentials')
        def fail(*a):raise OSError('DPAPI unavailable')
        with patch.object(akira_secrets,'os',NS(name='nt')),patch.object(akira_secrets,'canonical_path',return_value=target),patch.dict(sys.modules,{'win32crypt':NS(CryptProtectData=fail)}):
            with self.assertRaises(OSError):akira_secrets.save_secrets({'OPENAI_API_KEY':'sk-new-fixture'},merge=False)
        self.assertEqual(target.read_bytes(),b'previous protected credentials')
    def test_cloud_auth_status_lists_real_response_models_without_echoing_key(self):
        from cloud_status import verify_cloud
        with patch('cloud_status.get_secret',return_value='sk-test-private'):
            result=verify_cloud(opener=lambda *a,**k:io.BytesIO(b'{"data":[{"id":"gpt-4.1-mini"}]}'))
        self.assertTrue(result['ok']);self.assertEqual(result['models'],['gpt-4.1-mini']);self.assertNotIn('sk-test',str(result))
    def test_cloud_credit_and_permission_errors_are_readable_and_redacted(self):
        from cloud_status import verify_cloud
        for code,error,word in [(401,'invalid_api_key','Clave'),(403,'denied','permisos'),(429,'insufficient_quota','Créditos')]:
            def opener(*args,**kwargs):raise HTTPError('https://api.openai.com',code,'sk-test-private',{},io.BytesIO(json.dumps({'error':{'code':error,'message':'sk-test-private'}}).encode()))
            with self.subTest(code=code),patch('cloud_status.get_secret',return_value='sk-test-private'):
                r=verify_cloud(opener=opener);self.assertFalse(r['ok']);self.assertIn(word,r['detail']);self.assertNotIn('sk-test',str(r))
    def test_selected_nonreasoning_model_does_not_receive_unsupported_reasoning(self):
        from assistant_akira import AkiraAssistant
        cfg=load_config(DEFAULT);cfg['assistant']['general_model']='gpt-4.1-mini';a=AkiraAssistant(cfg,self.root)
        response={'output':[{'type':'message','content':[{'type':'output_text','text':'Hola, soy AKIRA.'}]}]}
        with patch.object(a,'_post',return_value=response) as post:a.cloud_reply('Hola',{})
        payload=post.call_args[0][0];self.assertEqual(payload['model'],'gpt-4.1-mini');self.assertNotIn('reasoning',payload)

if __name__=='__main__':unittest.main()
