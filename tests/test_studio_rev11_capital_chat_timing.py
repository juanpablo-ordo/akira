"""Synthetic execution, conversation routing and export regressions. No live account."""
import copy
import json
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

from assistant_akira import AkiraAssistant
from akira_model_runtime import ManagedLlamaProcess, hardware_profile
from conversation_intent import is_personal_conversation, self_reply
from engine import Engine
from execution import Blocked, Gateway, OWN_RUNNER
from operation_report import HEADERS, NS as XMLNS, build_report, export_report, stamp
from order_timing import broker_seconds
from resource_optimizer import ui_poll_ms
from runner_protection import decision
from settings import DEFAULT, load_config
from tests.fixtures import PendingCase, optional_ollama_fixture
from tests.test_studio_rev9_execution import impulse_frames
from entry_momentum import adverse_impulse


class RunnerCapitalTests(PendingCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.cfg['execution']['pending_only'] = False

    def runner(self, symbol='BTCUSDm', side=1):
        plan = self.plan(symbol, side)
        quote = self.g.quote(symbol)
        entry = quote.ask if side == 1 else quote.bid
        distance = 50 if symbol.startswith('BTC') else 1
        return replace(plan, key=f'RUN:{symbol}:{side}:{int(self.clock())}',
            lane='RUNNER', kind='MARKET', entry=entry, sl=entry-side*distance,
            tp=entry+side*distance*2.4, atr=distance, score=94, quality_score=95,
            bar_time=int(self.clock()//900)*900-900, trigger=entry)

    def closure(self, ticket, net, symbol='BTCUSDm', age=30, lane='RUNNER', magic=OWN_RUNNER):
        plan = self.runner(symbol).to_dict()
        plan['lane'] = lane
        self.g.journal.data['positions'][str(ticket)] = {
            'magic':magic, 'lane':lane, 'plan':plan,
            'closure':{'state':'CONFIRMADO MT5','position_id':ticket,
                'deal_ids':[ticket*2,ticket*2+1],'symbol':symbol,
                'side':1,'net':net,'exit_time':self.clock()-age}}

    def test_runner_has_half_general_trade_cap_without_changing_pending_cap(self):
        snapshot = self.g.snapshot()
        self.assertAlmostEqual(self.g.entry_cap(self.runner(), snapshot), self.g.trade_cap(snapshot)*.5)
        self.assertAlmostEqual(self.g.entry_cap(self.plan(), snapshot), self.g.trade_cap(snapshot))

    def test_high_score_no_longer_boosts_runner_lot_by_default(self):
        plan = self.runner()
        self.g.send_runner(plan)
        self.assertEqual(self.api.sent[-1]['volume'], self.cfg['lot'])

    def test_explicit_lot_cannot_bypass_runner_budget_with_sizing_disabled(self):
        self.cfg['sizing']['enabled'] = False
        self.cfg['runner']['max_trade_budget_pct'] = 1
        with self.assertRaisesRegex(Blocked, 'límite estructural'):
            self.g.send_runner(self.runner())
        self.assertFalse(self.api.sent)

    def test_existing_pending_is_preserved_before_any_cancel_or_market_send(self):
        engine = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(engine.close)
        engine.warmup()
        self.api.add_pending(self.plan(side=-1))
        plan = self.runner()
        with patch('engine.runner_plan', return_value=(plan, 'synthetic')):
            self.assertFalse(engine.try_runner(plan.symbol, self.g.quote(plan.symbol)))
        self.assertFalse(self.api.sent)
        self.assertEqual(len(self.api.orders), 1)
        self.assertIn('Prioridad', engine.runner_views[plan.symbol]['detail'])

    def test_gateway_also_rejects_ignoring_a_protected_pending(self):
        order = self.api.add_pending(self.plan(side=-1))
        with self.assertRaisesRegex(Blocked, 'Prioridad'):
            self.g.validate_plan(self.runner(), self.g.snapshot(), ignore_orders=(order.ticket,))
        self.assertFalse(self.api.sent)

    def test_one_loss_pauses_only_new_runners_of_that_asset(self):
        self.closure(91, -.25)
        snapshot = self.g.snapshot()
        row = decision(self.g, self.runner(), snapshot)
        self.assertFalse(row['allowed'])
        self.assertGreater(row['resume_not_before'], self.clock())
        self.assertTrue(decision(self.g, self.runner('XAUUSDm'), snapshot)['allowed'])
        self.g.send_immediate_plan(self.plan('XAUUSDm'))
        self.assertTrue(self.api.orders)

    def test_gross_losses_of_both_assets_share_the_runner_loss_budget(self):
        self.closure(91, -1.7)
        self.closure(92, -1.7, 'XAUUSDm')
        self.closure(93, 6, age=10)
        row = decision(self.g, self.runner(), self.g.snapshot())
        self.assertFalse(row['allowed'])
        self.assertAlmostEqual(row['gross_loss_24h_usd'], 3.4)
        self.assertIn('24 h', row['reason'])

    def test_loss_budget_survives_restart_of_the_gateway(self):
        self.closure(91, -4)
        self.g.journal.save()
        from execution import Journal
        restored = Gateway(self.api, self.cfg, Journal(self.g.journal.path), self.g.log, self.clock)
        self.assertFalse(decision(restored, self.runner(), restored.snapshot())['allowed'])

    def test_pending_and_manual_losses_do_not_spend_direct_runner_budget(self):
        self.closure(91, -20, lane='PENDING', magic=170002)
        self.closure(92, -20, magic=0)
        row = decision(self.g, self.runner(), self.g.snapshot())
        self.assertTrue(row['allowed'])
        self.assertEqual(row['gross_loss_24h_usd'], 0)

    def test_24h_old_loss_and_future_receipts_are_not_used(self):
        self.closure(91, -20, age=86401)
        self.closure(92, -20, age=-300)
        self.assertTrue(decision(self.g, self.runner(), self.g.snapshot())['allowed'])

    def test_pause_expires_after_cooldown_if_loss_budget_not_exhausted(self):
        self.closure(91, -.25, age=3601)
        self.assertTrue(decision(self.g, self.runner(), self.g.snapshot())['allowed'])

    def test_pending_map_is_attempted_before_runner_for_each_asset(self):
        engine = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(engine.close)
        events = []
        with patch.object(engine, 'execute_pending_map', side_effect=lambda s,*a: events.append(('pending',s))), \
             patch.object(engine, 'try_runner', side_effect=lambda s,*a: events.append(('runner',s))):
            engine.step()
        for symbol in self.cfg['symbols']:
            self.assertLess(events.index(('pending',symbol)), events.index(('runner',symbol)))

    def test_closed_counter_impulse_also_applies_to_market_runners(self):
        now=1800000000
        for symbol,price,scale in [('BTCUSDm',70000,20),('XAUUSDm',3000,.5)]:
            for side in (-1,1):
                with self.subTest(symbol=symbol,side=side):
                    plan=NS(symbol=symbol,lane='RUNNER',kind='MARKET',side=side,
                        entry=price,sl=price-side*10*scale,tp=price+side*20*scale)
                    self.assertIsNotNone(adverse_impulse(plan,impulse_frames(now,price,side,scale),now))


class ConversationRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg=optional_ollama_fixture(load_config(DEFAULT))
        self.bot=AkiraAssistant(self.cfg,Path(self.tmp.name),trade_callback=Mock())
        self.addCleanup(self.bot._managed_model.shutdown)

    def test_common_direct_questions_need_neither_web_nor_a_model_boot(self):
        questions=['¿Quién eres?','¿Qué eres?','oye Akira, ¿qué puedes hacer?',
            '¿Para qué sirbes?','¿Me escuhas?','¿Estás ahí?',
            '¿Cómo funcionas?','Quiero comversar contigo','¿Qué estás haciendo?',
            'Hola Akira, ¿cómo estás?','¿Eres una IA?']
        with patch.object(self.bot,'local_llm_reply',side_effect=AssertionError('model boot')), \
             patch('assistant_akira.lookup_current_fact',side_effect=AssertionError('web lookup')):
            for question in questions:
                with self.subTest(question=question):
                    answer=self.bot.reply(question,{},False)
                    self.assertGreater(len(answer),12)
                    self.assertNotIn('No llegó una respuesta',answer)
        self.bot.trade_callback.assert_not_called()

    def test_custom_name_is_used_when_asked_about_identity(self):
        self.cfg['studio']['brand_name']='Luna'
        self.assertIn('Luna',self.bot.reply('Luna, ¿quién eres?',{},False))

    def test_natural_conversation_uses_model_without_web_and_keeps_saved_memory(self):
        message='Hoy me siento triste y quiero contarte lo que pasó.'
        snapshot={'conversation_memory':{'saved':['Mi perro se llama Nube'],'related_chats':[]}}
        def answer(messages,*args,**kwargs):
            self.assertEqual(messages[-1]['content'],message)
            self.assertIn('Nube',json.dumps(messages,ensure_ascii=False))
            self.assertIn('naturalidad',messages[0]['content'])
            return 'Te leo. Cuéntame qué pasó hoy.'
        with patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['qwen3:8b','qwen3:4b']}), \
             patch('assistant_akira.ollama_agent',side_effect=answer), \
             patch.object(self.bot,'_source_tool',side_effect=AssertionError('unwanted search')):
            self.assertEqual(self.bot._local_llm_reply_impl(message,snapshot),'Te leo. Cuéntame qué pasó hoy.')

    def test_weather_word_ola_is_not_rewritten_as_a_greeting(self):
        from language_normalization import understood
        self.assertEqual(understood('Hay una ola de calor'),'Hay una ola de calor')

    def test_own_identity_is_not_confused_with_current_factual_questions(self):
        for message in ('¿Quién es el presidente actual de Guatemala?','¿Qué anunció Xbox hoy?','Recuerdas quién es el presidente actual de Guatemala?'):
            self.assertIsNone(self_reply(message))
            self.assertFalse(is_personal_conversation(message))
            self.assertTrue(self.bot._should_research_fact(message))

    def test_conversation_is_not_reported_as_a_successful_model_if_it_failed(self):
        self.assertFalse(self.bot._should_research_fact('¿Tienes amigos?'))
        self.assertFalse(is_personal_conversation('¿Puedes darme otras fuentes?'))
        self.assertTrue(self.bot._should_research_fact('¿Sabes quién es el presidente actual de Guatemala?'))
        with patch.object(self.bot,'local_llm_reply',side_effect=TimeoutError('fixture timeout')):
            answer=self.bot.reply('jaja',{},False)
        self.assertNotIn('Te sigo. ',answer)

    def test_small_context_keeps_complete_source_constraint_and_response_locale(self):
        question='Xbox acaba de lanzar Nébula Azul: según la ficha, ¿cómo se llama?'
        fixture={'results':[{'title':'Xbox Wire · Nébula Azul',
            'url':'https://news.xbox.com/es-es/nebula-azul/',
            'text':'Ficha de prueba: Nébula Azul está anunciado, NO LANZADO. Nombre: Nébula Azul.'}],'errors':[]}
        self.cfg['assistant'].update(local_runtime_enabled=True,auto_research=True,self_review=False)
        self.cfg['studio']['language_chat']='en'
        def answer(messages,*args,**kwargs):
            system=messages[0]['content']
            self.assertIn('No publiques una salida que la evidencia niega.',system)
            self.assertIn('English',system)
            return 'Nébula Azul is announced, not released.'
        with patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['qwen3:8b','qwen3:4b']}), \
             patch('assistant_akira.lookup_current_fact',return_value=fixture), \
             patch('assistant_akira.lookup_verified_current_fact',return_value=fixture), \
             patch.object(self.bot,'_source_tool',return_value=fixture), \
             patch('akira_local_ai.owned_context_tokens',return_value=1024), \
             patch('assistant_akira.ollama_agent',side_effect=answer) as model:
            self.bot._local_llm_reply_impl(question,{})
        model.assert_called_once()

    def test_eco_status_does_not_load_the_model_just_to_check_an_idle_chat(self):
        self.cfg['assistant']['local_runtime_enabled']=True
        self.cfg['desktop']['performance_profile']='Ahorro de energía'
        with patch.object(self.bot._managed_model,'_paths',return_value=(Path('engine.exe'),Path('model.gguf'))), \
             patch.object(self.bot._managed_model,'session',side_effect=AssertionError('idle model boot')), \
             patch('assistant_akira.ollama_status',return_value={'ok':False,'models':[]}):
            self.bot._probe_local_status()
        self.assertFalse(self.bot._managed_model_boot_attempted)
        self.assertEqual(self.bot._status['phase'],'IDLE')


class TimingExportTests(PendingCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.engine=Engine(self.g,self.cfg,self.g.log)
        self.addCleanup(self.engine.close)
        self.engine.step()
        self.snapshot=self.engine.report_snapshot()

    def test_millisecond_broker_time_has_precedence_and_missing_is_not_now(self):
        row=NS(time_setup_msc=1800000000123,time_setup=1700000000)
        self.assertAlmostEqual(broker_seconds(row,'order'),1800000000.123)
        self.assertIsNone(broker_seconds({}))
        self.assertIsNone(broker_seconds({'time':float('nan')}))
        self.assertIsNone(broker_seconds({'time':0}))

    def test_fingerprint_and_snapshot_preserve_broker_order_time(self):
        order=self.api.orders[0]
        order.time_setup_msc=int((self.clock()-600)*1000)
        row=self.g.fingerprint(order,'order')
        self.assertEqual(row['time'],self.clock()-600)
        self.assertIn('order_journal',self.engine.report_snapshot())

    def model_with_times(self):
        snapshot=copy.deepcopy(self.snapshot)
        order=snapshot['orders'][0];created=self.clock()-600
        order['time']=created
        model=build_report(snapshot)
        row=next(r for r in model['tables']['Pendientes'] if r[0]==str(order['ticket']))
        return model,row,created

    def test_pending_report_uses_order_time_not_report_capture_time(self):
        model,row,created=self.model_with_times()
        self.assertEqual(row[12],stamp(created))
        self.assertEqual(row[13],'MT5: colocación')
        self.assertNotEqual(row[12],model['local_time'])

    def test_all_report_rows_match_their_headers(self):
        model=build_report(self.snapshot)
        invalid=[(name,index,len(row),len(HEADERS[name])) for name,rows in model['tables'].items()
                 for index,row in enumerate(rows) if len(row)!=len(HEADERS[name])]
        self.assertFalse(invalid,invalid[:10])

    def test_excel_has_labeled_typed_placement_dates(self):
        model,row,created=self.model_with_times()
        path=self.root/'Horas.xlsx'
        export_report(model,path,'xlsx',False)
        with zipfile.ZipFile(path) as archive:
            sheet=ET.fromstring(archive.read('xl/worksheets/sheet2.xml'))
            text=''.join(sheet.itertext())
            self.assertIn('Colocación local',text)
            # Find the row belonging to the same ticket, not an arbitrary proposal.
            for record in sheet.findall('{'+XMLNS+'}sheetData/{'+XMLNS+'}row'):
                values=list(record)
                if record.get('r') and int(record.get('r'))>=6 and ''.join(values[0].itertext())==row[0]:
                    date=record.find("{"+XMLNS+"}c[@r='M"+record.get('r')+"']")
                    self.assertIsNotNone(date)
                    self.assertIsNone(date.get('t'))
                    self.assertGreater(float(date.find('{'+XMLNS+'}v').text),40000)
                    break
            else:self.fail('Dated ticket missing from Excel')

    def test_pdf_contains_the_placement_timestamp_and_its_source(self):
        from pypdf import PdfReader
        model,row,created=self.model_with_times()
        path=self.root/'Horas.pdf'
        export_report(model,path,'pdf',False)
        text='\n'.join(page.extract_text() or '' for page in PdfReader(str(path)).pages)
        self.assertIn(stamp(created),text)
        self.assertIn('MT5: colocación',text)


class LowResourcePolicyTests(unittest.TestCase):
    def test_default_profile_detects_ram_and_available_cpu_instead_of_assuming_a_gaming_pc(self):
        with patch('psutil.virtual_memory',return_value=NS(total=8*1073741824)), \
             patch('psutil.Process') as process:
            process.return_value.cpu_affinity.return_value=[0,1]
            profile=hardware_profile()
        self.assertEqual(profile['detected_ram_gb'],8)
        self.assertEqual(profile['logical_cores'],2)
        self.assertEqual(profile['cpu_threads'],1)
        self.assertEqual(profile['gpu_layers'],0)

    def test_eco_limits_prompt_threads_and_disables_busy_polling(self):
        profile=hardware_profile(8,0,2)
        runtime=ManagedLlamaProcess({'local_runtime_enabled':True},profile=profile)
        with patch.object(runtime,'_paths',return_value=(Path('/cpu/llama-server.exe'),Path('/model.gguf'))):
            command=runtime.command('http://127.0.0.1:18987/v1/chat/completions',
                {'performance_profile':'Ahorro de energía','model_use_gpu':False,'model_context_tokens':2048})
        def flag(name):return command[command.index(name)+1]
        self.assertEqual(flag('--threads'),'1')
        self.assertEqual(flag('--threads-batch'),'1')
        self.assertEqual(flag('--poll'),'0')
        self.assertEqual(flag('--poll-batch'),'0')
        self.assertEqual(flag('--ubatch-size'),'64')
        self.assertEqual(flag('--load-mode'),'none')
        self.assertEqual(flag('--cache-ram'),'128')
        self.assertEqual(flag('--n-gpu-layers'),'0')

    def test_visual_timer_slows_while_hidden_but_chat_remains_responsive(self):
        cfg=load_config(DEFAULT)
        cfg['desktop']['performance_profile']='Ahorro de energía'
        self.assertEqual(ui_poll_ms(cfg),250)
        self.assertEqual(ui_poll_ms(cfg,hidden=True),750)
        self.assertEqual(ui_poll_ms(cfg,interactive=True),80)
        self.assertEqual(cfg['poll_seconds'],.2)

    def test_money_and_fraction_defaults_keep_decimal_precision_for_settings(self):
        cfg=load_config(DEFAULT)
        self.assertIsInstance(cfg['risk']['max_trade_money'],float)
        self.assertIsInstance(cfg['runner']['loss_budget_trades'],float)

    def test_ci_verifier_imports_from_an_unrelated_working_directory(self):
        import subprocess,sys
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='AKIRA verifier cwd ') as temporary:
            result=subprocess.run([sys.executable,str(root/'installer/summarize_revision.py'),'--manifest-only'],
                cwd=temporary,capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('SHA256 verified files:',result.stdout)

    def test_runner_policy_configuration_is_validated(self):
        for field,value in [('max_trade_budget_pct',0),('max_trade_budget_pct',101),
                            ('loss_cooldown_seconds',0),('loss_budget_trades',4),
                            ('preserve_pending_orders',1),('allow_size_boost','yes')]:
            cfg=copy.deepcopy(DEFAULT)
            cfg['runner'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                load_config(cfg)


class ReleaseGroundingTests(unittest.TestCase):
    def setUp(self):
        self.question='Estudio Aurora acaba de lanzar Nébula Azul: ¿cómo se llama y quiénes participan?'
        self.rows=[{'title':'Estudio Aurora · Nébula Azul','url':'https://example.org/nebula',
                    'text':'Nébula Azul es un título anunciado; todavía no se ha lanzado. Participan Cleo y Ari.'}]

    def test_wrong_release_premise_is_neutralized_without_losing_the_question(self):
        from answer_grounding import release_constraint,neutral_question
        constraint=release_constraint(self.question,self.rows)
        self.assertIsNotNone(constraint)
        question=neutral_question(self.question,constraint)
        self.assertNotIn('acaba de lanzar',question)
        self.assertIn('quiénes participan',question)

    def test_host_removes_contradicted_release_claim_and_preserves_independent_names(self):
        from answer_grounding import release_constraint,enforce_release_constraint
        constraint=release_constraint(self.question,self.rows)
        answer=enforce_release_constraint('Estudio Aurora acaba de lanzar Nébula Azul: se llama Nébula Azul y participan Cleo y Ari.',constraint)
        self.assertNotIn('acaba de lanzar',answer)
        self.assertIn('no se ha lanzado',answer)
        self.assertTrue(all(name in answer for name in ('Nébula Azul','Cleo','Ari')))

    def test_correct_negative_answer_is_kept_and_positive_evidence_is_not_overridden(self):
        from answer_grounding import release_constraint,enforce_release_constraint
        constraint=release_constraint(self.question,self.rows)
        correct='Nébula Azul todavía no se ha lanzado. Participan Cleo y Ari.'
        self.assertEqual(enforce_release_constraint(correct,constraint),correct)
        self.rows[0]['text']='Nébula Azul fue anunciado y ya está disponible.'
        self.assertIsNone(release_constraint(self.question,self.rows))

    def test_an_unrelated_unreleased_title_cannot_change_this_answer(self):
        from answer_grounding import release_constraint
        other=[{'title':'Luna Roja de Editorial Lago','text':'Luna Roja está anunciado, no lanzado.',
                'url':'https://example.org/other'}]
        self.assertIsNone(release_constraint(self.question,other))
