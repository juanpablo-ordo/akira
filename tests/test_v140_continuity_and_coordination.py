"""Reproducir reclamos del chat y coordinación del actor, sin red ni MT5 real."""
import copy
from concurrent.futures import Future
from contextlib import ExitStack
import json
import queue
import threading
import time
import unittest
from unittest.mock import patch

from assistant_akira import AkiraAssistant
from command_bridge import CommandBridge,dispatch
from conversation_state import ConversationState,is_repair,prompt_messages
from engine import Engine
from execution import Blocked,PENDING
from knowledge import KnowledgeStore
from runtime import session_write_guard
from settings import DEFAULT,load_config
from tests.fixtures import PendingCase


class Conversation140Tests(PendingCase,unittest.TestCase):
    def bot(self,callback=None):
        self.cfg['assistant']['self_review']=False
        return AkiraAssistant(self.cfg,self.root,trade_callback=callback)

    def local_model(self,answer='Respuesta siguiendo el hilo.'):
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['qwen3:8b']}))
        stack.enter_context(patch('assistant_akira.get_secret',return_value=''))
        return stack.enter_context(patch('assistant_akira.ollama_agent',return_value=answer))

    def test_exact_complaint_recovers_original_question_in_model_messages(self):
        bot=self.bot();original='¿Cómo hago una calculadora en Python?'
        bot._remember_turn(original,'No llegó una respuesta útil.')
        model=self.local_model('Para tu calculadora, convierte con float() y elige la operación.')
        with patch.object(bot,'_source_tool',side_effect=AssertionError('Un reclamo no debe buscarse literalmente')):
            answer=bot.reply('ni me has respondido',{},use_cloud=False)
        messages=model.call_args.args[0]
        self.assertIn(original,messages[-1]['content'])
        self.assertIn('Ahora reclamo: ni me has respondido',messages[-1]['content'])
        self.assertTrue(any(r['role']=='user' and r['content']==original for r in messages[:-1]))
        self.assertIn('float()',answer)

    def test_search_outage_followup_never_searches_literal_complaint(self):
        bot=self.bot();self.local_model();queries=[]
        def source(name,args):
            queries.append(args.get('query',''));return {'results':[]}
        with patch.object(bot,'_source_tool',side_effect=source),patch('assistant_akira.lookup_current_fact',return_value={'results':[]}):
            first=bot.reply('¿Qué anunció Xbox este mes?',{},use_cloud=False)
            count=len(queries)
            second=bot.reply('ni me has respondido',{},use_cloud=False)
        self.assertGreater(count,0);self.assertEqual(len(queries),count)
        self.assertIn('Xbox',first);self.assertIn('Xbox',second)
        self.assertNotIn('La frase',second);self.assertNotIn('ACTUALIZAR FUENTES',second)
        self.assertNotIn('¿Quieres que',second)

    def test_literal_bad_model_answer_gets_one_context_correction(self):
        bot=self.bot();bot._remember_turn('¿Cómo hago una calculadora en Python?','Respuesta incompleta.')
        self.local_model('La frase "ni me has respondido" sugiere que alguien no respondió.')
        with patch('assistant_akira.ollama_chat',return_value='Para la calculadora usa float() y funciones.') as corrected:
            answer=bot.reply('ni me has respondido',{},use_cloud=False)
        self.assertEqual(corrected.call_count,1);self.assertFalse(corrected.call_args.kwargs['think'])
        self.assertIn('calculadora',corrected.call_args.args[0][-1]['content']);self.assertIn('float()',answer)

    def test_real_phrase_definition_is_not_misclassified_as_a_reclaim(self):
        self.assertFalse(is_repair('¿Qué significa "ni me has respondido"?'))
        self.assertTrue(is_repair('ni me has respondido'))

    def test_topic_survives_several_short_followups_and_restart(self):
        state=ConversationState(self.root)
        state.record('Explícame una calculadora en Python','Ejemplo inicial.')
        state.record('más corto','Versión corta.')
        state.record('ni me has respondido','Explicación corregida.')
        restored=ConversationState(self.root)
        self.assertEqual(restored.resolve('sigue el hilo')['question'],'Explícame una calculadora en Python')
        self.assertEqual(len(restored.history()),6)

    def test_old_trading_turns_seed_model_continuity_even_if_visual_chat_is_clean(self):
        store=KnowledgeStore(self.root)
        store.remember('user','Pon las mejores pendientes de BTC y oro')
        store.remember('assistant','MT5 rechazó por riesgo 7.45 > 2.17.')
        bot=self.bot()
        self.assertFalse(bot.history)
        self.assertIn('BTC',bot.dialogue.previous_question())
        self.assertIn('7.45',bot.dialogue.history()[-1]['text'])

    def test_execution_result_survives_restart_separately_from_visual_chat(self):
        bot=self.bot();bot.remember_execution('Pon pendientes BTC y oro','BTC #123; oro bloqueado 7.45 > 2.17.',{'unconfirmed':False})
        restored=self.bot()
        self.assertFalse(restored.history)
        self.assertIn('#123',restored.dialogue.last_action['answer'])
        self.assertIn('oro',restored.dialogue.resolve('ni me has respondido')['question'])

    def test_corrupt_context_uses_sqlite_history_without_erasing_it(self):
        self.root.joinpath('state').mkdir()
        (self.root/'state'/'conversation_context.json').write_text('{bad json',encoding='utf-8')
        bot=self.bot();bot.memory.remember('user','Tema recuperable de la memoria')
        restored=self.bot()
        self.assertEqual(restored.dialogue.previous_question(),'Tema recuperable de la memoria')
        self.assertTrue(restored.dialogue.error)

    def test_valid_json_with_wrong_shape_also_recovers_seed_history(self):
        self.root.joinpath('state').mkdir()
        (self.root/'state'/'conversation_context.json').write_text('[]',encoding='utf-8')
        state=ConversationState(self.root,[{'role':'user','text':'Pregunta recuperada','at':'hora inválida'}])
        self.assertEqual(state.previous_question(),'Pregunta recuperada');self.assertTrue(state.error)

    def test_unwritable_context_does_not_break_the_response(self):
        state=ConversationState(self.root);(self.root/'state').write_text('archivo en lugar de carpeta')
        self.assertEqual(state.record('Pregunta','Respuesta'),'Respuesta')
        self.assertTrue(state.error);self.assertEqual(state.previous_question(),'Pregunta')

    def test_long_evidence_never_evicts_recent_dialogue_or_overflows_budget(self):
        for budget in (12000,28000,48000):
            history=[{'role':'user','text':'LA_PREGUNTA_ANTERIOR '+('h'*2500)},
                     {'role':'assistant','text':'LA_RESPUESTA_ANTERIOR '+('h'*2500)}]
            messages=prompt_messages('i'*20000,'RECLAMO_ACTUAL '+('q'*10000),history,
                state={'bars':'s'*30000},evidence='e'*100000,continuity={'previous':'p'*10000},budget=budget)
            self.assertLessEqual(sum(len(m['content']) for m in messages),budget)
            self.assertIn('RECLAMO_ACTUAL',messages[-1]['content'])
            joined='\n'.join(m['content'] for m in messages)
            self.assertIn('LA_PREGUNTA_ANTERIOR',joined);self.assertIn('LA_RESPUESTA_ANTERIOR',joined)

    def test_stock_followup_is_removed_even_if_the_model_adds_it(self):
        bot=self.bot();self.local_model('Usa float().\n\n¿Quieres que profundice en alguna parte o que investigue algo relacionado?')
        answer=bot.reply('¿Cómo hago una calculadora en Python?',{},use_cloud=False)
        self.assertEqual(answer,'Usa float().')

    def test_one_primary_source_can_answer_without_artificial_two_site_quorum(self):
        bot=self.bot();self.local_model('El anuncio oficial describe lo siguiente.')
        source={'url':'https://news.xbox.com/announcement','title':'Anuncio oficial','text':'Información del anuncio publicado.'}
        with patch.object(bot,'_source_tool',return_value={'results':[source]}),patch('assistant_akira.lookup_current_fact',return_value={'results':[]}):
            answer=bot.reply('¿Qué anunció Xbox este mes?',{},use_cloud=False)
        self.assertIn('news.xbox.com',answer);self.assertIn('El anuncio oficial',answer)

    def test_extra_sources_are_retained_for_followup_without_second_web_search(self):
        bot=self.bot();self.local_model('Los dos anuncios coinciden.')
        first={'url':'https://example.com/first','title':'Xbox','text':'Anuncio de Xbox.'}
        extra={'url':'https://example.org/second','title':'Xbox','text':'Anuncio independiente de Xbox.'}
        with patch.object(bot,'_source_tool',return_value={'results':[first]}) as tools,patch('assistant_akira.lookup_current_fact',return_value={'results':[extra]}) as search:
            bot.reply('¿Qué anunció Xbox este mes?',{},use_cloud=False)
            count=tools.call_count;search_count=search.call_count
            answer=bot.reply('ni me has respondido',{},use_cloud=False)
        self.assertEqual(tools.call_count,count);self.assertEqual(search.call_count,search_count)
        self.assertIn('example.org/second',answer)

    def test_offline_model_reclaim_reports_original_question_and_model_failure(self):
        bot=self.bot();bot._remember_turn('¿Cómo hago una calculadora en Python?','Sin respuesta.')
        with patch('assistant_akira.ollama_status',return_value={'models':[]}):
            answer=bot.reply('ni me has respondido',{},use_cloud=False)
        self.assertIn('calculadora',answer);self.assertIn('modelo conversacional no respondió',answer)
        self.assertNotIn('La frase',answer)

    def test_factual_second_review_uses_original_question_after_a_reclaim(self):
        bot=self.bot();bot.cfg['assistant']['self_review']=True;question='¿Qué anunció Xbox este mes?'
        source={'url':'https://news.xbox.com/announcement','text':'Texto del anuncio publicado.'}
        with patch('assistant_akira.ollama_status',return_value={'models':['qwen3:14b']}),patch.object(bot,'_source_tool',return_value={'results':[source]}),patch('assistant_akira.lookup_current_fact',return_value={'results':[]}),patch('assistant_akira.ollama_agent',return_value='Respuesta al anuncio.'),patch('assistant_akira.ollama_chat',return_value='Respuesta revisada al anuncio.') as review:
            bot.reply(question,{},use_cloud=False);answer=bot.reply('ni me has respondido',{},use_cloud=False)
        self.assertEqual(review.call_count,2)
        self.assertIn('PREGUNTA:\n'+question,review.call_args.args[0][-1]['content'])
        self.assertFalse(review.call_args.kwargs['think']);self.assertIn('Respuesta revisada',answer)


class Coordination140Tests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.cfg=load_config(DEFAULT);self.g.cfg=self.cfg
        self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)

    def bot(self):return AkiraAssistant(self.cfg,self.root,trade_callback=self.e.handle_command)

    def test_operational_complaint_returns_current_parameters_without_model_or_orders(self):
        self.cfg['risk']['max_trade_money']=.01;view=self.e.step()
        bot=self.bot()
        with patch('assistant_akira.ollama_agent',side_effect=AssertionError('No requiere modelo')),patch.object(bot,'_source_tool',side_effect=AssertionError('No requiere web')):
            answer=bot.reply('sigue sin meter pendientes BTC y oro',view,use_cloud=False)
        self.assertIn('Entry=',answer);self.assertIn('BLOQUEO DE RIESGO',answer)
        self.assertIn('BTCUSDm',answer);self.assertIn('XAUUSDm',answer);self.assertFalse(self.api.sent)

    def test_starting_actor_reports_actual_read_error_instead_of_empty_answer(self):
        bot=AkiraAssistant(self.cfg,self.root,trade_callback=lambda cmd:{'ok':False,'error':'MT5 sigue iniciando'})
        answer=bot.reply('no pone pendientes BTC y oro',{},use_cloud=False)
        self.assertIn('MT5 sigue iniciando',answer);self.assertFalse(self.api.sent)

    def test_decision_funnel_separates_proposals_and_real_confirmed_orders(self):
        self.cfg['risk']['max_trade_money']=.01;blocked=self.e.step()
        for row in blocked['symbols'].values():
            d=row['decision'];self.assertGreater(d['technical_candidates'],0)
            self.assertEqual(d['visible_parameters'],4);self.assertEqual(d['currently_sendable'],0)
            self.assertEqual(d['confirmed_pending_orders'],0)
        self.cfg['risk']['max_trade_money']=3;sent=self.e.step()
        for row in sent['symbols'].values():
            d=row['decision'];self.assertEqual(d['confirmed_pending_orders'],1)
            self.assertEqual(d['last_cycle_new_orders'],1)

    def test_explicit_best_pending_command_places_both_without_external_dependencies(self):
        bot=self.bot()
        with patch('assistant_akira.ollama_status',side_effect=AssertionError('No debe esperar al modelo')):
            answer=bot.reply('Pon las mejores pendientes de BTC y oro',{},use_cloud=False)
        self.assertEqual(len(self.api.orders),2)
        self.assertEqual({r['symbol'] for r in self.api.sent},{'BTCUSDm','XAUUSDm'})
        self.assertIn('MT5',answer);self.assertIn('BTC',bot.dialogue.previous_question())

    def test_contextual_trading_followup_never_repeats_execution(self):
        bot=self.bot();bot.reply('Pon las mejores pendientes de BTC y oro',{},use_cloud=False)
        count=len(self.api.sent)
        for message in ('y BTC','ni me has respondido','sigue igual'):
            answer=bot.reply(message,self.e.view(),use_cloud=False)
            self.assertIn('Entry=',answer)
        self.assertEqual(len(self.api.sent),count)

    def test_analysis_only_returns_both_maps_without_mt5_mutations_in_trade_mode(self):
        bot=self.bot();answer=bot.reply('Analiza y dame parámetros de BTC y oro, no pongas órdenes',{},use_cloud=False)
        self.assertFalse(self.api.sent);self.assertIn('BTCUSDm',answer);self.assertIn('XAUUSDm',answer)
        self.assertGreaterEqual(answer.count('Entry='),4)
        self.assertEqual(sum(len(row['scenario_book']) for row in self.e.view()['symbols'].values()),8)

    def test_stale_state_never_labels_old_order_as_current_confirmation(self):
        view=self.e.step();view['as_of_utc']=time.time()-90
        bot=AkiraAssistant(self.cfg,self.root)
        answer=bot.reply('no pone pendientes BTC y oro',view,use_cloud=False)
        self.assertIn('última foto guardada',answer);self.assertNotIn('· MT5 #',answer)

    def test_legacy_guard_keeps_analysis_and_button_connected_but_blocks_all_writes(self):
        self.g.runtime_execution_block='EA anterior pendiente de retirar'
        view=self.e.step()
        self.assertTrue(view['connected']);self.assertFalse(view['execution_allowed']);self.assertFalse(self.api.sent)
        result=self.e.handle_command({'action':'assistant_best_pending','symbol':'ALL'})
        self.assertEqual(len(result['results']),2);self.assertFalse(self.api.sent)
        for row in result['results']:
            self.assertEqual(len(row['scenarios']),4);self.assertIn('EA anterior',row['detail'])
        self.assertTrue(self.e.handle_command({'action':'export_diagnostic'})['ok'])
        for entry in (True,False):
            with self.assertRaises(Blocked):self.g.permissions(self.g.snapshot(),entry=entry)
        self.assertFalse(self.api.sent)

    def test_cleared_legacy_guard_resumes_automatic_pending_on_next_cycle(self):
        self.g.runtime_execution_block='EA anterior';self.e.step()
        self.g.runtime_execution_block='';self.e.step()
        self.assertEqual(len(self.api.orders),2);self.assertTrue(all(r['action']==PENDING for r in self.api.sent))

    def test_second_controller_lock_does_not_retire_first_controller(self):
        with patch('runtime.AccountLock',side_effect=Blocked('otra Akira')),patch('runtime.retire') as retire:
            lock,reason=session_write_guard(self.g,self.api.account,None)
        self.assertIsNone(lock);self.assertIn('otra Akira',reason);retire.assert_not_called()

    def test_handoff_block_keeps_lock_and_can_resume_without_reacquiring_it(self):
        lock=object()
        with patch('runtime.AccountLock') as acquire,patch('runtime.retire',side_effect=[Blocked('esperando ack'),None]):
            current,reason=session_write_guard(self.g,self.api.account,lock)
            self.assertIs(current,lock);self.assertIn('ack',reason)
            current,reason=session_write_guard(self.g,self.api.account,current)
        self.assertIs(current,lock);self.assertEqual(reason,'');acquire.assert_not_called()

    def test_optional_context_errors_do_not_block_first_orders(self):
        class BrokenContext:
            def submit(self,*args):raise RuntimeError('proveedor caído')
            def read(self):raise RuntimeError('modelo caído')
        self.e.context=BrokenContext();view=self.e.step()
        self.assertEqual(len(self.api.orders),2);self.assertTrue(view['connected'])

    def test_inflight_analysis_is_rebuilt_when_deep_frames_change(self):
        self.e.warmup(fast=True);cache=self.e.planner.caches['BTCUSDm'];cache.analysis_executor=None
        old=cache.frames['M1'];future=Future()
        future.set_result((old,[],{}));cache.analysis_future=future;cache.analysis_name='M1'
        cache.analysis_signature=tuple((k,f.bars[-1].time) for k,f in cache.frames.items() if k!='M1')
        cache.prime_deep_structural(self.clock())
        with patch('market_cache.build_setups',return_value=(['fresh-map'],{})) as rebuild:
            cache.poll_analysis()
        self.assertIn('H4',rebuild.call_args.args[0]);self.assertIn('D1',rebuild.call_args.args[0])
        self.assertEqual(cache.setups,['fresh-map'])

    def test_startup_button_waits_for_actor_then_places_both(self):
        commands=queue.Queue();bridge=CommandBridge(commands,timeout=1);bridge.starting=True;results=[]
        worker=threading.Thread(target=lambda:results.append(bridge.request({'action':'assistant_best_pending','symbol':'ALL'})))
        worker.start();cmd=commands.get(timeout=1);dispatch(self.e,cmd);worker.join(1)
        self.assertFalse(worker.is_alive());self.assertTrue(results[0]['ok']);self.assertEqual(len(self.api.orders),2)

    def test_timed_out_startup_request_is_removed_before_actor_and_cannot_trade(self):
        commands=queue.Queue();bridge=CommandBridge(commands,timeout=.01);bridge.starting=True
        result=bridge.request({'action':'assistant_best_pending','symbol':'ALL'})
        dispatch(self.e,commands.get_nowait())
        self.assertIn('retiró de la cola',result['error']);self.assertFalse(self.api.sent)

    def test_long_model_does_not_hold_engine_or_execution_memory_lock(self):
        bot=self.bot();entered=threading.Event();release=threading.Event();answers=[]
        def slow(*args,**kwargs):
            entered.set();release.wait(2);return 'Usa funciones de Python.'
        with patch('assistant_akira.ollama_status',return_value={'models':['qwen3:8b']}),patch('assistant_akira.ollama_agent',side_effect=slow):
            worker=threading.Thread(target=lambda:answers.append(bot.reply('¿Cómo hago una calculadora en Python?',{},use_cloud=False)),daemon=True)
            worker.start()
            try:
                self.assertTrue(entered.wait(1));view=self.e.step()
                self.assertEqual(len(self.api.orders),2);self.assertFalse(release.is_set())
                bot.remember_execution('Pon las pendientes BTC + oro','Cuatro órdenes confirmadas.',{'ok':True})
                self.assertIn('confirmadas',bot.dialogue.last_action['answer']);self.assertTrue(view['connected'])
            finally:release.set();worker.join(2)
        self.assertFalse(worker.is_alive());self.assertTrue(answers)
        # La respuesta lenta comenzó antes del botón. Al terminar no debe
        # convertir su pregunta vieja en el último tema de la conversación.
        self.assertIn('pendientes',bot.dialogue.previous_question())

    def test_chat_pause_and_resume_change_real_engine_state_without_orders(self):
        bot=self.bot();self.assertIn('pausada',bot.reply('pausa el bot',{},use_cloud=False))
        self.assertTrue(self.e.paused);self.e.step();self.assertFalse(self.api.sent)
        self.assertIn('reanudada',bot.reply('reanuda el bot',{},use_cloud=False));self.assertFalse(self.e.paused)
        self.e.step();self.assertEqual(len(self.api.orders),2)

    def test_observation_mode_survives_resume_and_config_migration(self):
        raw=copy.deepcopy(DEFAULT);raw['schema_version']=1360;raw['mode']='observe'
        raw['risk']['max_trade_money']=2.17;raw['assistant']['friendly_followup_question']=True
        cfg=load_config(raw)
        self.assertEqual(cfg['mode'],'observe');self.assertEqual(cfg['risk']['max_trade_money'],2.17)
        self.assertFalse(cfg['assistant']['friendly_followup_question']);self.assertEqual(cfg['schema_version'],1600)
        self.cfg['mode']='observe';bot=self.bot();bot.reply('reanuda el bot',{},use_cloud=False)
        self.e.step();self.assertFalse(self.api.sent);self.assertEqual(self.cfg['mode'],'observe')


if __name__=='__main__':unittest.main()
