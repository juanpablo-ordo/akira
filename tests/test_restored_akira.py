import copy,json,queue,tempfile,threading,time,unittest,zipfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from assistant_akira import AkiraAssistant
from command_bridge import CommandBridge,dispatch
from engine import Engine
from evolution import FEATURE_VERSION,DailyLearner,EvolutionWorker,campaign_rows,train_candidate
from execution import PENDING,OWN_PENDING,Blocked
from knowledge import KnowledgeStore,public_url,parse_captions,transcript_chunks
from learning import PendingLearner
from tests.fixtures import PendingCase
from settings import DEFAULT,load_config
from migrate_v11_settings import migrate,find_restore_root,restore_user_data

class AssistantRestorationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.cfg=load_config(DEFAULT);self.calls=[]
        # Tests below mock the legacy endpoint; new installations select llama.cpp.
        self.cfg['assistant']['local_runtime_enabled']=False
        def execute(cmd):
            self.calls.append(cmd);return {'results':[{'symbol':'BTCUSDm','levels':[{'ticket':123,'confirmed':True,'side':'BUY','kind':'LIMIT','entry':59000,'sl':58900,'tp':59200}]}]}
        self.bot=AkiraAssistant(self.cfg,self.root,execute)
    def test_confirmed_best_map_skips_models_and_preserves_conversation(self):
        with patch.object(self.bot,'local_llm_reply',side_effect=AssertionError('No esperar al modelo')),patch.object(self.bot,'cloud_reply',side_effect=AssertionError('No esperar cloud')):
            answer=self.bot.reply('Pon las mejores pendientes de BTC y oro',{})
        self.assertEqual(self.calls[0]['symbol'],'ALL');self.assertIn('#123',answer)
        restored=AkiraAssistant(self.cfg,self.root);self.assertEqual(restored.history,[])
    def test_exact_limit_command_skips_models(self):
        with patch.object(self.bot,'local_llm_reply',side_effect=AssertionError('No esperar al modelo')):
            self.bot.reply('Coloca una orden BTC BUY LIMIT entrada 59000 SL 58900 TP 59200',{})
        self.assertEqual(self.calls[0]['action'],'assistant_plan');self.assertEqual(self.calls[0]['sl'],58900)
    def test_denial_and_analysis_only_never_execute(self):
        messages=('No pongas pendientes','Dame solo parámetros de pendientes','Dame pendientes sin ejecutar','No las pongas, analiza pendientes','¿Por qué no colocas pendientes?','No quiero órdenes pendientes')
        with patch.object(self.bot,'local_llm_reply',return_value='Análisis sin ejecución'):
            for message in messages:self.bot.reply(message,{})
        self.assertTrue(all(c['action'] in ('assistant_snapshot','assistant_analyze_pending') for c in self.calls))
    def test_accepted_ticket_without_observation_is_not_claimed_confirmed(self):
        result={'results':[{'symbol':'BTCUSDm','levels':[{'ticket':123,'entry':1,'sl':.5,'tp':2}],'detail':'Sin evidencia final'}]}
        answer=self.bot._trade_result_text(result);self.assertNotIn('MT5 confirmado',answer);self.assertIn('Sin evidencia',answer)
    def test_no_ticket_is_not_a_confirmed_order(self):
        answer=self.bot._trade_result_text({'results':[{'symbol':'BTCUSDm','levels':[{'ticket':0,'confirmed':True}],'detail':'No enviada'}]})
        self.assertNotIn('MT5 confirmado',answer)
    def test_fallback_diagnosis_uses_pending_blocks(self):
        answer=self.bot.local_reply('¿Por qué no pone pendientes?',{'status':{'BTCUSDm':{'state':'ESPERANDO','detail':'Margen proyectado insuficiente'}}})
        self.assertIn('Margen',answer);self.assertNotIn('scalp',answer.lower())
    def test_fallback_answers_also_persist_without_duplicate_turns(self):
        with patch.object(self.bot,'local_llm_reply',side_effect=RuntimeError('modelo no disponible')):
            answer=self.bot.reply('Revisa dirección del oro',{'status':{}},use_cloud=False)
        again=AkiraAssistant(self.cfg,self.root);self.assertEqual(len(again.history),2);self.assertEqual(again.history[-1]['text'],answer)
        with patch.object(self.bot,'local_llm_reply',return_value='Respuesta local'):self.bot.reply('Revisa dirección del oro',{},use_cloud=False)
        self.assertEqual(len(AkiraAssistant(self.cfg,self.root).history),4)
    def test_snapshot_contains_live_indicators_and_only_pending_context(self):
        snap={'symbols':{'BTCUSDm':{'frames':{'M15':{'adx':30,'ema200':58000,'vwap':58900}},'live':{'tick_balance':.3},'broker_book':{'imbalance':.4}}}}
        compact=self.bot.compact(snap);self.assertEqual(compact['symbols']['BTCUSDm']['frames']['M15']['adx'],30)
        self.assertNotIn('scalp',json.dumps(compact).lower())
    def test_chat_source_memory_survives_restart(self):
        self.bot.memory.put({'url':'https://example.org/a','title':'Oro soporte','topic':'XAUUSDm','body':'Datos','summary':'Estructura del oro'})
        self.bot._remember_turn('Investiga el oro','Tesis con fuente')
        restarted=AkiraAssistant(self.cfg,self.root);self.assertEqual(restarted.history[-1]['text'],'Tesis con fuente')
        self.assertEqual(restarted.memory.search('oro')[0]['url'],'https://example.org/a')
    def test_video_vision_analysis_persists_without_overwriting_full_captions(self):
        url='https://youtube.com/watch?v=abc';self.bot.memory.put({'url':url,'body':'Subtítulos completos','title':'BTC','topic':'BTCUSDm'})
        result={'url':url,'title':'BTC','frames_analyzed':6,'analysis':'Mecánica observada','note':'Frames muestreados'}
        with patch('assistant_akira.analyze_youtube_video',return_value=result):self.bot._source_tool('analyze_youtube_video',{'url':url,'topic':'BTCUSDm'})
        self.assertEqual(self.bot.memory.get(url)['body'],'Subtítulos completos')
        self.assertEqual(self.bot.memory.get(url+'#akira-vision')['status'],'vision_sampled')
    def test_tools_restore_memory_web_video_and_file_generation(self):
        names={t['function']['name'] for t in self.bot._local_tools()}
        self.assertTrue({'research_public_web','read_public_source','read_youtube_transcript','analyze_youtube_video','search_source_memory','create_local_file','create_project_zip'}.issubset(names))
        self.assertFalse({'queue_trade_plan','execute_best_pending_map'} & names)
    def test_generated_code_and_project_zip_stay_in_exports(self):
        file=self.bot._create_local_file({'filename':'../archivo.py','content':'print(1)\n'})
        self.assertEqual(Path(file['path']).parent,self.root/'exports')
        archive=self.bot._create_project_zip({'filename':'proyecto.zip','files':[{'path':'src/main.py','content':'print(2)'}]})
        with zipfile.ZipFile(archive['path']) as z:self.assertEqual(z.read('src/main.py'),b'print(2)')
    def test_ui_status_never_waits_for_slow_ollama(self):
        started=threading.Event();release=threading.Event()
        def slow(*args,**kwargs):started.set();release.wait(2);return {'ok':True,'models':['qwen3:4b']}
        with patch('assistant_akira.ollama_status',side_effect=slow) as status:
            before=time.monotonic();row=self.bot.local_ai_status();elapsed=time.monotonic()-before
            self.assertLess(elapsed,.15);self.assertFalse(row['ready']);self.assertTrue(started.wait(.5))
            for _ in range(10):self.bot.local_ai_status()
            self.assertEqual(status.call_count,1);release.set()
            for _ in range(100):
                if not self.bot._status_loading:break
                time.sleep(.002)
            self.assertTrue(self.bot.local_ai_status()['ready'])
    def test_empty_model_list_cannot_claim_ia_ready(self):
        with patch('assistant_akira.ollama_status',return_value={'ok':True,'models':[]}):self.bot._probe_local_status()
        self.assertFalse(self.bot.local_ai_status()['ready'])
    def test_public_reader_rejects_private_network_and_credentials(self):
        with patch('knowledge.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',80))]):
            with self.assertRaises(ValueError):public_url('https://example.org/')
        with self.assertRaises(ValueError):public_url('https://user:password@example.org/')

class PendingChatIntegrationTests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)
    def test_chat_places_both_symbols_on_a_valid_first_map(self):
        result=self.e.handle_command({'action':'assistant_best_pending','symbol':'ALL'})
        self.assertTrue(result['ok']);self.assertEqual(len(self.api.sent),4)
        self.assertEqual({r['symbol'] for r in result['results']},{'BTCUSDm','XAUUSDm'})
        self.assertTrue(all(r['levels'][0]['confirmed'] for r in result['results']));self.assertTrue(all(r['action']==PENDING for r in self.api.sent))
    def test_accepted_without_visible_order_remains_unconfirmed(self):
        self.api.no_effect=True
        result=self.e.handle_command({'action':'assistant_best_pending','symbol':'BTCUSDm'})
        self.assertTrue(result['unconfirmed']);self.assertFalse(result['ok']);self.assertEqual(result['results'][0]['levels'],[])
        before=len(self.api.sent);self.e.handle_command({'action':'assistant_best_pending','symbol':'BTCUSDm'});self.assertEqual(len(self.api.sent),before)
    def test_manual_orders_are_not_claimed_as_akira_in_chat(self):
        self.api.add_pending(self.plan(),magic=0)
        self.assertEqual(self.e.confirmed_levels('BTCUSDm'),[])
    def test_exact_pending_passes_geometry_and_transport(self):
        p=self.plan();result=self.e.handle_command({'action':'assistant_plan','symbol':p.symbol,'side':'BUY','kind':p.kind,'entry':p.entry,'sl':p.sl,'tp':p.tp})
        self.assertTrue(result['ok']);self.assertAlmostEqual(self.api.sent[0]['price'],round(p.entry/.01)*.01,places=7);self.assertEqual(self.api.sent[0]['action'],PENDING)
    def test_market_cannot_be_reintroduced_through_chat(self):
        p=self.plan();result=self.e.handle_command({'action':'assistant_plan','symbol':p.symbol,'side':'BUY','kind':'MARKET','entry':p.entry,'sl':p.sl,'tp':p.tp})
        self.assertFalse(result['ok']);self.assertFalse(self.api.sent)
    def test_observe_or_pause_blocks_chat_orders(self):
        self.e.paused=True;self.assertFalse(self.e.handle_command({'action':'assistant_best_pending'})['ok']);self.assertFalse(self.api.sent)
        self.e.paused=False;self.cfg['mode']='observe';self.assertFalse(self.e.handle_command({'action':'assistant_best_pending'})['ok']);self.assertFalse(self.api.sent)
    def test_interface_cancel_cannot_touch_manual_ticket(self):
        o=self.api.add_pending(self.plan(),magic=0);result=self.e.handle_command({'action':'cancel_pending','ticket':o.ticket})
        self.assertFalse(result['ok']);self.assertFalse(self.api.sent);self.assertIn(o,self.api.orders)
    def test_initial_history_and_llm_do_not_precede_first_entries(self):
        with patch.object(self.e.learner,'update',side_effect=AssertionError('Historial antes del primer envío')):
            view=self.e.step()
        self.assertEqual(len(self.api.sent),4);self.assertIsNone(view['account']['daily_net'])
        self.assertTrue(view['symbols']['BTCUSDm']['frames']['H1']['ema200']>0)
    def test_failed_context_aggregator_does_not_block_first_valid_technical_entries(self):
        def failed():raise ValueError('Proveedor con respuesta inválida')
        self.e.context=NS(read=failed,submit=lambda snapshot:None)
        view=self.e.step();self.assertEqual(len(self.api.sent),4)
        self.assertIn('context_worker',view['research']['sources'])
    def test_candidate_scan_is_cached_between_small_tick_changes(self):
        self.e.warmup();q=self.g.quote('BTCUSDm')
        with patch.object(self.e.planner,'proposed_pending_plans',wraps=self.e.planner.proposed_pending_plans) as scan:
            self.e.scan_plans('BTCUSDm',q);self.clock.advance(.02);self.e.scan_plans('BTCUSDm',q)
            first=scan.call_count;self.assertIn(first,(1,2))
            self.clock.advance(.6);self.e.scan_plans('BTCUSDm',q);self.assertEqual(scan.call_count,first*2)
    def test_final_negative_context_cannot_leave_below_threshold_orders_executable(self):
        def bad_context(symbol,plans):return [replace(p,quality_score=0) for p in plans]
        with patch.object(self.e.planner,'fuse_pending_context',side_effect=bad_context):self.e.step()
        self.assertFalse(self.api.sent)
        self.assertTrue(any('Confluencia final' in r for reasons in self.e.planner.pending_filter_reasons.values() for r in reasons.values()))
    def test_cold_mt5_fallback_discards_live_bar_before_first_orders(self):
        original=self.api.copy_rates_from_pos;waiting={s:True for s in self.cfg['symbols']}
        def cold(symbol,tf,start,count):
            if tf==1 and start==1 and waiting[symbol]:waiting[symbol]=False;return None
            if start==0:
                rows=list(self.api.rates[symbol,tf][-count+1:]);last=dict(rows[-1]);last['time']=int(self.clock()//60)*60
                return rows+[last]
            return original(symbol,tf,start,count)
        with patch.object(self.api,'copy_rates_from_pos',side_effect=cold):self.e.step()
        self.assertEqual(len(self.api.sent),4)
        for cache in self.e.planner.caches.values():self.assertLess(cache.frames['M1'].bars[-1].time,int(self.clock()//60)*60)
    def test_new_pending_records_decision_features(self):
        self.e.step();self.g.reconcile(self.g.snapshot());meta=next(iter(self.g.journal.data['orders'].values()))['plan']
        self.assertEqual(meta['learning_feature_version'],FEATURE_VERSION);self.assertEqual(len(meta['learning_features']),10)
    def test_complete_pending_close_reaches_feature_learner(self):
        self.e.handle_command({'action':'assistant_best_pending','symbol':'BTCUSDm'});o=self.api.orders[0];self.api.fill_order(o)
        self.g.reconcile(self.g.snapshot());p=self.api.positions[0];self.clock.advance(100)
        self.api.record_deal(p,1,p.volume,2);self.api.positions.remove(p);self.e.learner.update()
        records=list(self.e.learner.records.values());self.assertEqual(len(records),1);self.assertEqual(records[0]['feature_version'],FEATURE_VERSION)
        self.assertEqual(records[0]['lane'],'PENDING');self.assertEqual(len(campaign_rows(records,p.symbol)),1)
    def test_command_bridge_delivers_confirmed_actor_result(self):
        commands=queue.Queue();bridge=CommandBridge(commands,timeout=2);bridge.connected=True;out=[]
        thread=threading.Thread(target=lambda:out.append(bridge.request({'action':'assistant_best_pending','symbol':'BTCUSDm'})))
        thread.start();cmd=commands.get(timeout=1);dispatch(self.e,cmd);thread.join(2)
        self.assertTrue(out[0]['ok']);self.assertTrue(out[0]['results'][0]['levels'][0]['confirmed'])
    def test_timed_out_unstarted_command_is_removed(self):
        commands=queue.Queue();bridge=CommandBridge(commands,timeout=.001);bridge.connected=True
        result=bridge.request({'action':'assistant_best_pending'});self.assertFalse(result['ok'])
        dispatch(self.e,commands.get_nowait());self.assertFalse(self.api.sent)
    def test_promoted_model_only_affects_matching_account_and_feature_schema(self):
        self.e.warmup();p=self.plan();self.g.snapshot();base=self.e.planner.fuse_pending_context(p.symbol,[p])[0]
        champion={'promoted':True,'feature_version':FEATURE_VERSION,'test_samples':40,'weights':[3]+[0]*10,'base_rate':.5}
        from akira_version import BUILD_ID
        from strategy_choice import selected,STRATEGY_VERSION,SELECTOR_VERSION
        from trade_quality_gate import family
        self.e.planner.research_context={'daily_learning':{'account':list(self.g.identity),
            'execution_build':BUILD_ID,'strategy_version':STRATEGY_VERSION,'selector_version':SELECTOR_VERSION,
            'selector_id':selected(self.cfg),'family_champions':{p.symbol:{family(p):champion}}}}
        learned=self.e.planner.fuse_pending_context(p.symbol,[p])[0];self.assertGreater(learned.quality_score,base.quality_score)
        self.e.planner.research_context['daily_learning']['account']=[999,'OTHER']
        other=self.e.planner.fuse_pending_context(p.symbol,[p])[0];self.assertEqual(other.quality_score,base.quality_score)
        self.e.planner.research_context['daily_learning']['account']=list(self.g.identity);champion['feature_version']=1
        old=self.e.planner.fuse_pending_context(p.symbol,[p])[0];self.assertEqual(old.quality_score,base.quality_score)
        champion['feature_version']=FEATURE_VERSION
        self.e.planner.research_context['daily_learning']['execution_build']='ARCHIVED_BUILD'
        archived=self.e.planner.fuse_pending_context(p.symbol,[p])[0];self.assertEqual(archived.quality_score,base.quality_score)

class EvolutionRestorationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.cfg=load_config(DEFAULT)
    def training_rows(self,losing=False):
        return [{'campaign_id':str(i),'features':[1 if i%2 else -1]+[0]*9,'net':-.5 if losing else 1 if i%2 else -.8,
                 'opened_at':1700000000+i*7200,'closed_at':1700000025+i*7200} for i in range(140)]
    def test_model_promotion_requires_chronological_positive_edge(self):
        row=train_candidate(self.training_rows());self.assertTrue(row['promoted']);self.assertLess(row['train_end'],row['test_start'])
        self.assertFalse(train_candidate(self.training_rows(losing=True))['promoted'])
        self.assertFalse(train_candidate(self.training_rows(),row)['promoted'])
    def test_legacy_learning_is_preserved_but_not_mislabelled_pending(self):
        state=self.root/'state';state.mkdir();old={'champions':{'BTCUSDm':{'weights':[3]+[0]*10,'feature_version':1}}}
        (state/'daily_learning.json').write_text(json.dumps(old))
        daily=DailyLearner(self.root);self.assertEqual(daily.state['champions'],{});self.assertEqual(json.loads((state/'daily_learning.json').read_text()),old)
        rows=[{'symbol':'BTCUSDm','confirmed':True,'feature_version':1,'features':[0]*10,'net':1,'campaign_id':'old','opened_at':1,'closed_at':2,'campaign_complete':True}]
        self.assertEqual(campaign_rows(rows,'BTCUSDm'),[])
    def test_semantic_transcript_analysis_covers_all_retained_chunks(self):
        worker=EvolutionWorker(self.cfg,self.root);self.addCleanup(worker.close);row={'url':'https://youtube.com/watch?v=abc','title':'Oro','body':'a'*23000,'complete':True}
        result={'bias':.5,'confidence':.2,'thesis':'Condición de ruptura','invalidation':'Pierde soporte','horizon':'H1','limitations':'Opinión del autor'}
        with patch('evolution.local_chat',return_value=json.dumps(result)) as model:
            analysis=json.loads(worker.summarize(row,self.cfg['knowledge']))
        self.assertEqual(analysis['method'],'semantic_full_transcript');self.assertEqual(analysis['parts_analyzed'],analysis['parts_total']);self.assertGreater(model.call_count,1)
        self.assertTrue(analysis['source_complete']);self.assertLessEqual(analysis['confidence'],.3)
    def test_lexical_caption_cache_is_upgraded_to_semantic_analysis(self):
        worker=EvolutionWorker(self.cfg,self.root);self.addCleanup(worker.close);url='https://youtube.com/watch?v=abc'
        worker.store.put({'url':url,'title':'Oro','topic':'XAUUSDm','body':'Tesis del oro','complete':True,'status':'analyzed','summary':json.dumps({'method':'lexical_full_transcript'})})
        worker.submit({},[{'url':url,'symbol':'XAUUSDm'}])
        # SQLite stores completeness in summary, not as a separate column.
        with patch('evolution.read_youtube',return_value={'url':url,'title':'Oro','body':'Tesis','complete':True,'status':'transcript'}),patch.object(worker,'summarize',return_value=json.dumps({'method':'semantic_full_transcript','source_complete':True})) as model:
            worker.cycle()
        model.assert_called_once();self.assertEqual(json.loads(worker.store.get(url)['summary'])['method'],'semantic_full_transcript')
    def test_caption_parser_preserves_full_text(self):
        raw=json.dumps({'events':[{'segs':[{'utf8':'Hola &amp; mundo'}]},{'segs':[{'utf8':'Otro tramo'}]}]})
        self.assertEqual(parse_captions(raw,'json3'),'Hola & mundo\nOtro tramo');body='x'*37001;self.assertEqual(''.join(transcript_chunks(body)),body)

class FullMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.current=self.root/'Akira';self.current.mkdir();self.backup=self.root/'Akira.backup.pre10.20261004';self.backup.mkdir();self.dest=self.root/'candidate'
        self.old=copy.deepcopy(DEFAULT);self.old['schema_version']=194;self.old['assistant']['local_model']='qwen3:14b';self.old['desktop']['width']=1700
        (self.backup/'akira_config.json').write_text(json.dumps(self.old))
        self.raw=copy.deepcopy(DEFAULT);self.raw['schema_version']=1000;self.raw.pop('assistant');self.raw.pop('desktop');self.raw.pop('final_v6')
        self.raw.update(mode='observe',expected_login=123456789);self.raw['risk']['max_trade_money']=1.8;self.raw['risk']['portfolio_money_cap']=7
        (self.current/'akira_config.json').write_text(json.dumps(self.raw))
    def test_latest_complete_backup_restores_ai_preferences_and_current_limits(self):
        restored=find_restore_root(self.current);self.assertEqual(restored,self.backup)
        cfg=migrate(self.raw,self.old);self.assertEqual(cfg['assistant']['local_model'],'qwen3:14b');self.assertEqual(cfg['desktop']['width'],1700)
        self.assertEqual((cfg['mode'],cfg['expected_login'],cfg['risk']['max_trade_money'],cfg['risk']['portfolio_money_cap']),('observe',123456789,1.8,7))
        self.assertEqual(cfg['schema_version'],1600);self.assertLessEqual(cfg['poll_seconds'],.25)
    def test_current_full_ai_preferences_take_priority_over_old_backup(self):
        self.raw['assistant']=copy.deepcopy(DEFAULT['assistant']);self.raw['assistant']['local_model']='qwen3:4b'
        cfg=migrate(self.raw,self.old);self.assertEqual(cfg['assistant']['local_model'],'qwen3:4b')
    def test_missing_backups_do_not_remove_complete_default_ai(self):
        cfg=migrate(self.raw);self.assertTrue(cfg['assistant']['source_memory']);self.assertTrue(cfg['assistant']['local_tools']);self.assertTrue(cfg['knowledge']['enabled'])
    def test_state_exports_and_secrets_survive_without_restoring_old_intents(self):
        (self.current/'state').mkdir();(self.current/'state'/'cuenta_active.json').write_text('{"intents":{"CURRENT":{}}}')
        (self.backup/'state').mkdir();(self.backup/'state'/'cuenta_old.json').write_text('{"intents":{"OLD":{}}}')
        (self.backup/'state'/'daily_learning.json').write_text('{"history":"saved"}');(self.backup/'exports').mkdir();(self.backup/'exports'/'mi_codigo.py').write_text('print(1)')
        (self.current/'AKIRA_SECRETS.json').write_text('{"local":"current"}')
        restore_user_data(self.current,self.backup,self.dest)
        self.assertTrue((self.dest/'state'/'cuenta_active.json').is_file());self.assertFalse((self.dest/'state'/'cuenta_old.json').exists())
        self.assertTrue((self.dest/'state'/'daily_learning.json').is_file());self.assertTrue((self.dest/'exports'/'mi_codigo.py').is_file())
        self.assertEqual((self.dest/'AKIRA_SECRETS.json').read_text(),'{"local":"current"}')
    def test_memories_merge_without_duplicate_turns_and_new_sources_win(self):
        old=KnowledgeStore(self.backup);current=KnowledgeStore(self.current)
        old.remember('user','historia previa');current.remember('user','consulta actual')
        row={'url':'https://example.org/a','title':'Oro','topic':'oro','body':'viejo','summary':'viejo','fetched':1};old.put(row);current.put({**row,'body':'nuevo','summary':'nuevo','fetched':2})
        restore_user_data(self.current,self.backup,self.dest);restore_user_data(self.current,self.backup,self.dest)
        store=KnowledgeStore(self.dest);self.assertEqual(len(store.history()),2);self.assertEqual(store.get(row['url'])['summary'],'nuevo')
        self.assertEqual(store.history()[0]['text'],'historia previa')
    def test_without_current_installation_original_limits_are_restored(self):
        cfg=migrate({},self.old);self.assertEqual(cfg['assistant']['local_model'],'qwen3:14b');self.assertNotIn('scalp',json.dumps(cfg).lower())
