"""Regressions from the user's misspelled question and failed local reviews."""
import copy,json,tempfile,threading,unittest,time
from pathlib import Path
from unittest.mock import Mock,patch

from assistant_akira import AkiraAssistant
from akira_local_ai import chat,_post
from language_normalization import understood
from local_inference import InferencePriority,BackgroundDeferred
from settings import DEFAULT
from web_facts import _dedupe_diverse,needs_web_verification


class Understanding(unittest.TestCase):
    def test_user_president_question_with_transpositions_keeps_the_topic(self):
        question=understood('quien es el acutal presdiente de guatemla?')
        self.assertIn('actual presidente de Guatemala',question)
        self.assertTrue(needs_web_verification(question))
        self.assertTrue(AkiraAssistant._strict_current_fact(question))

    def test_numbers_negation_urls_code_and_valid_words_are_preserved(self):
        text='No compres BTCUSDm; Entry 82345.71 SL 82200.15 TP 83000.50 lote 0.01. Él presiente algo. https://example.com/presdiente `presdiente`'
        self.assertEqual(understood(text),text)

    def test_irrelevant_official_google_and_guatemala_banks_are_rejected(self):
        rows=[{'title':'Google Translate Community','url':'https://support.google.com/translate','text':'AI powered language learning'},
              {'title':'Banco G&T Guatemala','url':'https://gtcontinental.com.gt','text':'Productos bancarios para Guatemala.'},
              {'title':'Presidencia de Guatemala','url':'https://presidencia.gob.gt/presidente','text':'El presidente Bernardo Arévalo dirige el Gobierno de Guatemala.'}]
        result=_dedupe_diverse('quien es el actual presdiente de guatemala',rows,strict=True)
        self.assertEqual([r['url'] for r in result],[rows[2]['url']])

    def test_current_fact_search_has_a_total_budget_when_an_index_hangs(self):
        from web_facts import lookup_verified_current_fact
        release=threading.Event()
        def slow(*args):release.wait(2);return []
        started=time.monotonic()
        try:
            with patch('web_facts._official_presidency',side_effect=slow),patch('web_facts._duck_html',side_effect=slow),patch('web_facts._bing_rss',side_effect=slow):
                result=lookup_verified_current_fact('presidente actual de Guatemala',timeout=.05)
            elapsed=time.monotonic()-started
        finally:release.set()
        self.assertLess(elapsed,1);self.assertFalse(result['results']);self.assertIn('search:total_time_budget',result['errors'])

    def test_current_office_can_read_an_official_source_without_a_working_index(self):
        from web_facts import lookup_verified_current_fact
        official={'title':'Presidencia de Guatemala','url':'https://presidencia.gob.gt/','text':'El presidente Bernardo Arévalo dirige el Gobierno de Guatemala.','engine':'official-direct'}
        with patch('web_facts._official_presidency',return_value=[official]),patch('web_facts._duck_html',side_effect=OSError('index down')),patch('web_facts._bing_rss',side_effect=OSError('index down')):
            result=lookup_verified_current_fact('quien es el actual presidente de guatemala')
        self.assertTrue(result['verified']);self.assertEqual(result['results'][0]['url'],official['url'])

    def test_official_page_parser_uses_the_page_content_and_rejects_scripts(self):
        from web_facts import _official_presidency
        body=b'<html><title>Presidencia de Guatemala</title><script>presidente WRONG</script><p>El presidente Bernardo Ar\xc3\xa9valo dirige el Gobierno de Guatemala.</p></html>'
        class Page:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def geturl(self):return 'https://current.presidencia.gob.gt/'
            def read(self,limit):return body
        with patch('web_facts.urllib.request.urlopen',return_value=Page()):rows=_official_presidency('presidente actual de Guatemala',1)
        self.assertIn('Bernardo Arévalo',rows[0]['text']);self.assertNotIn('WRONG',rows[0]['text'])

    def test_model_outage_answers_the_actual_question_from_an_official_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            cfg=copy.deepcopy(DEFAULT);cfg['assistant']['local_runtime_enabled']=False
            bot=AkiraAssistant(cfg,Path(temporary))
            evidence={'results':[{'title':'Presidencia de Guatemala','url':'https://presidencia.gob.gt/presidente','text':'El presidente Bernardo Arévalo dirige el Gobierno de Guatemala.'}]}
            with patch.object(bot,'local_llm_reply',side_effect=TimeoutError('modelo ocupado')),patch('assistant_akira.lookup_verified_current_fact',return_value=evidence) as lookup:
                answer=bot.reply('quien es el acutal presdiente de guatemala',{},use_cloud=False)
            self.assertIn('El presidente de Guatemala es Bernardo Arévalo',answer)
            self.assertIn('modelo local no terminó',answer)
            self.assertIn('presidente',lookup.call_args.args[0]);self.assertNotIn('presdiente',lookup.call_args.args[0])
            self.assertNotIn('Translate',answer);self.assertNotIn('Banco',answer)

    def test_stop_does_not_start_web_research_after_model_cancellation(self):
        with tempfile.TemporaryDirectory() as temporary:
            cfg=copy.deepcopy(DEFAULT);cfg['assistant']['local_runtime_enabled']=False
            bot=AkiraAssistant(cfg,Path(temporary))
            def stopped(*args):bot.cancel_current_reply();raise RuntimeError('detenido')
            with patch.object(bot,'local_llm_reply',side_effect=stopped),patch('assistant_akira.lookup_verified_current_fact') as lookup:
                answer=bot.reply('quien es el presidente de Guatemala',{},use_cloud=False)
            self.assertIn('detenido',answer);lookup.assert_not_called()

    def test_known_offline_state_explains_current_fact_limit_without_waiting_for_web(self):
        with tempfile.TemporaryDirectory() as temporary:
            cfg=copy.deepcopy(DEFAULT);cfg['assistant']['local_runtime_enabled']=False
            bot=AkiraAssistant(cfg,Path(temporary))
            with patch.object(bot,'local_llm_reply') as model,patch('assistant_akira.lookup_verified_current_fact') as lookup:
                answer=bot.reply('quien es el actual presdiente de Guatemala',{'network_available':False},use_cloud=False)
            self.assertIn('sin Internet',answer);model.assert_not_called();lookup.assert_not_called()


class Protocol(unittest.TestCase):
    def test_llama_cpp_receives_the_schema_inside_its_supported_format(self):
        schema={'type':'object','properties':{'verdict':{'type':'string','enum':['ABSTAIN']}},'required':['verdict']}
        response={'choices':[{'finish_reason':'stop','message':{'content':'{"verdict":"ABSTAIN"}'}}]}
        with patch('akira_local_ai._post',return_value=response) as post:
            result=chat([{'role':'user','content':'Revisa'}],model='fixture.gguf',endpoint='http://127.0.0.1:18987/v1/chat/completions',think=False,response_format=schema)
        self.assertEqual(json.loads(result),{'verdict':'ABSTAIN'})
        self.assertEqual(post.call_args.args[1]['response_format'],{'type':'json_object','schema':schema})

    def test_cancel_interrupts_a_request_waiting_for_response_headers(self):
        started=threading.Event();closed=threading.Event();cancel=threading.Event();observed=[]
        class Connection:
            sock=None
            def request(self,*args):started.set()
            def getresponse(self):
                if not closed.wait(2):raise AssertionError('Model connection was never closed')
                raise OSError('cancelled before headers')
            def close(self):closed.set()
        def run():
            try:_post('http://127.0.0.1:18987/v1/chat/completions',{},timeout=10,cancel_event=cancel)
            except Exception as error:observed.append(str(error))
        with patch('akira_local_ai.HTTPConnection',return_value=Connection()):
            thread=threading.Thread(target=run,daemon=True);thread.start()
            self.assertTrue(started.wait(1));cancel.set();thread.join(1)
        self.assertFalse(thread.is_alive());self.assertTrue(closed.is_set());self.assertIn('detenido',observed[0])

    def test_interactive_chat_interrupts_background_and_does_not_lose_its_queue(self):
        priority=InferencePriority();entered=threading.Event();ended=threading.Event();result=[]
        def work():
            try:
                with priority.auxiliary() as event:entered.set();event.wait(1)
            except BackgroundDeferred:result.append('deferred')
            finally:ended.set()
        thread=threading.Thread(target=work,daemon=True);thread.start();self.assertTrue(entered.wait(1))
        with priority.interactive():
            self.assertTrue(ended.wait(1))
            with self.assertRaises(BackgroundDeferred):
                with priority.auxiliary():pass
        thread.join(1);self.assertEqual(result,['deferred']);self.assertEqual(priority.users,0)
        with priority.auxiliary() as event:self.assertFalse(event.is_set())


if __name__=='__main__':unittest.main()
