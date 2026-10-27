"""Owner's science/math recording, request lifecycle and offline avatar ownership."""
import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from settings import DEFAULT,load_config
from tests.fixtures import optional_ollama_fixture
from conversation_core import needs_research,messages_for,presentation,ConversationState


class ConversationPolicy(unittest.TestCase):
    def test_science_question_from_recording_is_a_conversation(self):
        self.assertFalse(needs_research('que piensas de la ciencia'))
    def test_mathematics_question_from_recording_does_not_fetch_headlines(self):
        self.assertFalse(needs_research('dime cual es la formula mas elegante de las matematicas'))
    def test_personal_today_is_not_a_news_request(self):
        self.assertFalse(needs_research('Hoy me siento nervioso por una entrevista'))
    def test_actual_public_office_is_still_verified(self):
        self.assertTrue(needs_research('¿Quién es el presidente actual de Guatemala?'))
    def test_explicit_sources_are_not_silently_skipped(self):
        self.assertTrue(needs_research('Busca fuentes sobre la identidad de Euler'))
    def test_supplied_url_keeps_the_research_path(self):
        self.assertTrue(needs_research('Resume https://example.com/lecture'))
    def test_current_releases_still_require_evidence(self):
        self.assertTrue(needs_research('¿Qué anunció Xbox hoy?'))
    def test_science_followup_is_not_a_news_search(self):
        self.assertFalse(needs_research('¿Por qué es útil ese método?'))
    def test_specific_external_occurrences_keep_source_verification(self):
        self.assertTrue(needs_research('¿Qué sustancia usó el personaje en esa escena?'))
        self.assertFalse(needs_research('¿Cómo funciona la memoria RAM?'))
    def test_current_question_and_numbers_are_never_cut(self):
        text='No ejecutes órdenes. Explica por qué −1 y 0.01 son diferentes. '+'α'*12000
        self.assertEqual(messages_for(text)[-1],{'role':'user','content':text})
    def test_small_stable_prompt_does_not_change_with_the_clock(self):
        a=messages_for('¿Qué es la ciencia?')[0];b=messages_for('¿Qué es la ciencia?')[0]
        self.assertEqual(a,b);self.assertLess(len(a['content']),900)
    def test_failed_headlines_are_removed_together_with_the_failed_turn(self):
        rows=[{'role':'user','text':'ciencia'},{'role':'assistant','text':'La IA conversacional local todavía no respondió, pero investigué la web pública. Titular ajeno.'},
            {'role':'user','text':'La unidad imaginaria es i'},{'role':'assistant','text':'i al cuadrado es −1.'}]
        out=json.dumps(messages_for('¿Y su cuadrado?',rows),ensure_ascii=False)
        self.assertNotIn('Titular ajeno',out);self.assertIn('cuadrado es −1',out)
    def test_saved_memories_and_chosen_language_are_preserved(self):
        rows=messages_for('What is my dog called?',memories={'saved':['Mi perro se llama Nube']},brand='Luna',language='en')
        self.assertIn('Luna',rows[0]['content']);self.assertIn('en.',rows[0]['content']);self.assertIn('Nube',json.dumps(rows))
    def test_old_history_is_bounded(self):
        history=[r for i in range(20) for r in ({'role':'user','text':str(i)+'?'+('x'*900)},{'role':'assistant','text':'a'*900})]
        result=messages_for('mi pregunta actual',history)
        self.assertLessEqual(len(result),8);self.assertEqual(result[-1]['content'],'mi pregunta actual')
    def test_short_turns_keep_a_contiguous_prefix_for_the_model_cache(self):
        history=[r for i in range(5) for r in ({'role':'user','text':str(i)+' pregunta'},{'role':'assistant','text':str(i)+' respuesta'})]
        prompts=messages_for('otra pregunta',history)
        self.assertEqual(len(prompts),12);self.assertEqual(prompts[1]['content'],'0 pregunta')
    def test_explicit_topic_change_does_not_resend_the_old_topic(self):
        history=[{'role':'user','text':'tema viejo'},{'role':'assistant','text':'respuesta vieja'},
            {'role':'user','text':'Cambiemos de tema: tengo 17 manzanas'},{'role':'assistant','text':'Hablemos de las manzanas.'}]
        prompts=messages_for('¿Y si regalo cinco?',history)
        self.assertNotIn('viejo',json.dumps(prompts));self.assertIn('17 manzanas',json.dumps(prompts))


class LifecyclePolicy(unittest.TestCase):
    def test_active_response_wins_over_a_stale_idle_poll(self):
        p=presentation({'phase':'RESPONDING','active':True},{'phase':'IDLE'},True)
        self.assertEqual(p['expression'],'talking');self.assertFalse(p['loading']);self.assertEqual(p['label'],'Respondiendo')
    def test_loading_wins_over_an_old_failed_boot(self):
        p=presentation({'phase':'LOADING','active':True},{'phase':'FAILED'},True)
        self.assertEqual(p['expression'],'loading');self.assertTrue(p['loading'])
    def test_successful_generation_invalidates_a_stale_error_presentation(self):
        self.assertEqual(presentation({'phase':'READY','generated':True},{'phase':'FAILED'})['label'],'Lista para conversar')
    def test_missing_components_remain_actionable_after_an_old_success(self):
        self.assertEqual(presentation({'phase':'READY','generated':True},{'phase':'MISSING'})['expression'],'alert')
    def test_failure_is_not_presented_as_an_idle_success(self):
        p=presentation({'phase':'ERROR'},{'ready':True})
        self.assertEqual(p['expression'],'alert');self.assertIn('reintentar',p['label'])
    def test_idle_memory_release_has_a_user_friendly_label(self):
        label=presentation({}, {'phase':'IDLE'})['label']
        self.assertIn('se activa al conversar',label);self.assertNotIn('reposo',label)
    def test_lifecycle_stops_loading_after_failure(self):
        state=ConversationState();state.begin('pregunta');state.update('LOADING');state.finish(error=True)
        self.assertFalse(state.snapshot()['active']);self.assertEqual(state.snapshot()['phase'],'ERROR')


class ProductionRouting(unittest.TestCase):
    def setUp(self):
        from assistant_akira import AkiraAssistant
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cfg=optional_ollama_fixture(load_config(DEFAULT));self.cfg['assistant'].update(auto_research=True,self_review=True)
        self.bot=AkiraAssistant(self.cfg,Path(self.tmp.name));self.addCleanup(self.bot._managed_model.shutdown)
    def answer(self,question):
        with patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['Qwen3-4B-Q4_K_M.gguf']}), \
             patch('assistant_akira.ollama_agent',return_value='Respuesta de prueba del transporte, no una inferencia real.') as model, \
             patch('assistant_akira.lookup_current_fact',side_effect=AssertionError('unwanted news lookup')), \
             patch.object(self.bot,'_source_tool',side_effect=AssertionError('unwanted source request')):
            answer=self.bot._local_llm_reply_impl(question,{})
        self.assertEqual(model.call_count,1);self.assertEqual(model.call_args.args[0][-1]['content'],question)
        self.assertEqual(model.call_args.args[1],[]);self.assertFalse(model.call_args.kwargs['reasoning'])
        return answer
    def test_science_recording_reaches_one_generation_request(self):
        self.assertIn('transporte',self.answer('que piensas de la ciencia'))
    def test_math_recording_reaches_one_generation_request(self):
        self.assertIn('transporte',self.answer('dime cual es la formula mas elegante de las matematicas'))
    def test_a_failed_science_model_never_pastes_search_results(self):
        with patch.object(self.bot,'local_llm_reply',side_effect=TimeoutError('fixture')), \
             patch('assistant_akira.lookup_current_fact',side_effect=AssertionError('unwanted search')):
            answer=self.bot.reply('que piensas de la ciencia',{},False)
        self.assertNotIn('referencias',answer);self.assertNotIn('http',answer);self.assertIn('Reintentar',answer)
        self.assertEqual(self.bot.conversation.snapshot()['phase'],'ERROR')
    def test_streaming_still_emits_when_verbose_research_trace_is_disabled(self):
        events=[];self.bot.progress_callback=events.append;self.cfg['assistant']['show_research_trace']=False
        self.bot._progress('RESPONDIENDO','Texto generado')
        self.assertEqual(events[0]['detail'],'Texto generado');self.assertEqual(self.bot.conversation.snapshot()['phase'],'RESPONDING')


class ConversationWarmth(unittest.TestCase):
    def setUp(self):
        from akira_model_runtime import ManagedLlamaProcess,hardware_profile
        self.now=[100.];self.runtime=ManagedLlamaProcess({'local_runtime_enabled':True},profile=hardware_profile(8,0,4),clock=lambda:self.now[0])
        self.runtime.proc=Mock();self.runtime.proc.poll.return_value=None
    def test_warm_lease_is_bounded_and_does_not_change_the_saved_idle_policy(self):
        self.runtime._idle_override=0;self.assertTrue(self.runtime.keep_warm(30))
        self.assertEqual(self.runtime._warm_until,130);self.assertEqual(self.runtime._idle_override,0)
        self.runtime.keep_warm(10000);self.assertEqual(self.runtime._warm_until,160)
    def test_zero_warmth_releases_the_conversation_lease(self):
        self.runtime.keep_warm(30);self.runtime.keep_warm(0);self.assertEqual(self.runtime._warm_until,100)
    def test_closed_runtime_is_not_resurrected_to_keep_a_chat_warm(self):
        self.runtime._closed=True;self.assertFalse(self.runtime.keep_warm(30))


class StreamCompletion(unittest.TestCase):
    def response(self,lines):
        response=Mock(status=200);response.readline.side_effect=lines
        connection=Mock();connection.getresponse.return_value=response
        return connection
    def test_eof_without_a_completion_marker_is_not_a_complete_answer(self):
        import threading
        from akira_local_ai import _post_direct_cancellable
        connection=self.response([b'data: {"choices":[{"delta":{"content":"partial"}}]}\n',b''])
        with patch('akira_local_ai.HTTPConnection',return_value=connection),self.assertRaisesRegex(RuntimeError,'interrumpi'):
            _post_direct_cancellable('http://127.0.0.1:18996/v1/chat/completions',{'stream':True},5,threading.Event())
    def test_a_real_terminal_marker_preserves_the_visible_text(self):
        import threading
        from akira_local_ai import _post_direct_cancellable
        connection=self.response([b'data: {"choices":[{"delta":{"content":"1.375"}}]}\n',b'data: [DONE]\n'])
        with patch('akira_local_ai.HTTPConnection',return_value=connection):
            result=_post_direct_cancellable('http://127.0.0.1:18996/v1/chat/completions',{'stream':True},5,threading.Event())
        self.assertEqual(result['choices'][0]['message']['content'],'1.375');self.assertEqual(result['choices'][0]['finish_reason'],'stop')


class WindowActivity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def test_active_stream_updates_header_and_avatar_instead_of_idle(self):
        from desktop_qt import StudioWindow
        with tempfile.TemporaryDirectory() as tmp:
            w=StudioWindow(tmp,preview=True,start_actor=False)
            try:
                w.controller.chat_busy=True;w._model_status={'phase':'IDLE'}
                w.controller.assistant.conversation.begin('pregunta');w.controller.assistant.conversation.update('RESPONDING')
                w.sync_chat_activity()
                self.assertEqual(w.director.expression,'talking');self.assertIn('Respondiendo',w.ai_label.text());self.assertFalse(w.director.loading)
            finally:w.controller.chat_busy=False;w.close();self.app.processEvents()
    def test_local_conversation_can_react_offline_without_faking_connectivity(self):
        from desktop_qt import StudioWindow
        with tempfile.TemporaryDirectory() as tmp:
            w=StudioWindow(tmp,preview=True,start_actor=False)
            try:
                w.director.network(False);w.controller.chat_busy=True;w.controller.assistant.conversation.begin('ciencia')
                w.controller.assistant.conversation.update('RESPONDING');w.sync_chat_activity()
                self.assertFalse(w.director.online);self.assertEqual(w.director.expression,'talking')
                w.controller.chat_busy=False;w.controller.assistant.conversation.finish();w._avatar_reaction_until=0;w.sync_chat_activity()
                self.assertEqual(w.director.expression,'sleeping')
            finally:w.controller.chat_busy=False;w.close();self.app.processEvents()
    def test_checked_market_does_not_need_a_candidate_to_animate_analysis(self):
        from desktop_qt import StudioWindow
        with tempfile.TemporaryDirectory() as tmp:
            w=StudioWindow(tmp,preview=True,start_actor=False)
            try:
                w.react_snapshot({'connected':True,'symbols':{'BTCUSDm':{'checked_at':time.time()}},'candidates':{}})
                self.assertEqual(w.director.expression,'analyzing')
            finally:w.close();self.app.processEvents()
    def test_question_stays_visible_during_stream(self):
        from desktop_qt import StudioWindow
        with tempfile.TemporaryDirectory() as tmp:
            w=StudioWindow(tmp,preview=True,start_actor=False)
            try:
                w.controller.chat_busy=True;w.render_chat('pregunta de ciencia');w._stream_text='La ciencia permite';w.render_chat()
                self.assertIn('pregunta de ciencia',w.chat_view.toPlainText());self.assertIn('La ciencia permite',w.chat_view.toPlainText())
            finally:w.controller.chat_busy=False;w.close();self.app.processEvents()
    def test_native_controller_exercises_loading_stream_failure_and_retry(self):
        from qa_chat_lifecycle_rev15 import run_check
        result=run_check();self.assertEqual(result['status'],'PASSED');self.assertTrue(all(result['checks'].values()))
    def test_a_token_limited_response_offers_continue(self):
        from desktop_qt import StudioWindow
        with tempfile.TemporaryDirectory() as tmp:
            w=StudioWindow(tmp,preview=True,start_actor=False)
            try:
                w.handle_event({'kind':'chat_reply','data':{'text':'Respuesta parcial','truncated':True}})
                self.assertFalse(w.chat_continue.isHidden());self.assertTrue(w.chat_retry.isHidden())
            finally:w.close();self.app.processEvents()


if __name__=='__main__':unittest.main()
