import copy,unittest
from response_quality import answer_plan,complete_reply
from mathematical_reference import notes,issue


class CompleteGenerationTests(unittest.TestCase):
    def setUp(self):
        self.messages=[{'role':'system','content':'IA'},{'role':'user','content':'Explica la idea'}]
    def run_reply(self,outputs,clock=lambda:0):
        self.seen=[];self.info={};self.repairs=[]
        def invoke(messages,tokens,remaining):
            self.seen.append(copy.deepcopy(messages));text,reason=outputs.pop(0)
            self.info={'backend':'llama.cpp','finish_reason':reason,'truncated':reason=='length'};return text
        return complete_reply(self.messages,invoke,lambda:self.info,lambda:None,answer_plan('Una idea'),120,
                              on_repair=self.repairs.append,inspect=issue,clock=clock)
    def test_partial_is_regenerated_not_saved_or_treated_as_complete(self):
        text,data=self.run_reply([('Primera parte sin terminar','length'),('Explicación terminada.','stop')])
        self.assertEqual(text,'Explicación terminada.');self.assertTrue(data['repaired']);self.assertEqual(len(self.repairs),1)
        self.assertNotIn('Primera parte',str(self.seen[1]));self.assertFalse(data['truncated'])
    def test_two_incomplete_attempts_raise_instead_of_publishing_partial(self):
        with self.assertRaisesRegex(RuntimeError,'no terminó'):
            self.run_reply([('parcial','length'),('otra parcial','length')])
        self.assertEqual(len(self.seen),2)
    def test_known_definition_error_is_regenerated_not_silently_replaced(self):
        text,data=self.run_reply([('π es el número de Euler.','stop'),('π es la razón entre circunferencia y diámetro.','stop')])
        self.assertIn('razón',text);self.assertEqual(data['attempts'][0]['finish_reason'],'stop');self.assertTrue(data['repaired'])
    def test_absolute_deadline_is_not_extended_for_a_retry(self):
        times=iter([0,0,120])
        with self.assertRaises(TimeoutError):self.run_reply([('Parcial','length')],clock=lambda:next(times))
        self.assertEqual(len(self.seen),1)
    def test_cancellation_prevents_even_the_first_inference(self):
        def invoke(*a):raise AssertionError('cancelled request invoked')
        with self.assertRaises(RuntimeError):
            complete_reply(self.messages,invoke,lambda:{},lambda:None,answer_plan('hola'),120,cancelled=lambda:True)
    def test_invalid_empty_model_output_fails(self):
        with self.assertRaises(RuntimeError):self.run_reply([('','stop')])
    def test_budget_and_deadline_follow_requested_depth(self):
        small=answer_plan('Explícame el concepto');large=answer_plan('Explícalo paso a paso y con detalle')
        self.assertGreater(large['tokens'],small['tokens']);self.assertGreater(large['timeout'],small['timeout'])
        self.assertLessEqual(answer_plan('Detalladamente',maximum=256)['tokens'],256)


class MathematicalReferenceTests(unittest.TestCase):
    def test_notes_are_reference_data_not_a_canned_full_answer(self):
        n=notes('Explícame e^(i*pi)+1=0');self.assertEqual(n['source'],'https://dlmf.nist.gov/4.4')
        self.assertIn('diámetro',n['definitions']['pi']['definition']);self.assertIn('logaritmos',n['definitions']['e']['definition'])
        self.assertNotIn('answer',n)
    def test_unrelated_chat_is_not_loaded_with_mathematical_context(self):
        for q in ['Me siento triste','pintura al óleo','Mi perro se llama Pi','una receta de pie']:
            with self.subTest(q=q):self.assertIsNone(notes(q))
    def test_homonymous_physics_variables_do_not_receive_constant_definitions(self):
        for text in ['Explica E=mc²','Explícame e = m c^2','En física, E=mc2 expresa la energía','Explica la fórmula I=V/R']:
            with self.subTest(text=text):self.assertIsNone(notes(text))
        self.assertIsNotNone(notes('Explícame e^(i*pi)+1=0'))

    def test_correct_and_comparative_mentions_are_allowed(self):
        for text in ['π es el cociente entre circunferencia y diámetro.','e es el número de Euler, π es pi.','La fórmula de Euler usa e, π e i.']:
            with self.subTest(text=text):self.assertFalse(issue(text))
    def test_false_pi_alias_from_actual_model_trace_is_rejected(self):
        for text in ['π es el número de Euler.','**π** es el **número de Euler**, aproximadamente 3.14159.', 'pi: constante de Euler']:
            with self.subTest(text=text):self.assertTrue(issue(text))


class ResearchedCompletionTests(unittest.TestCase):
    def test_a_source_based_partial_is_not_saved_or_marked_ready(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from assistant_akira import AkiraAssistant
        from settings import DEFAULT
        cfg=copy.deepcopy(DEFAULT);cfg['assistant'].update(local_runtime_enabled=False,self_review=False,auto_youtube_research=False)
        source={'results':[{'title':'Python docs','url':'https://docs.python.org/3/','text':'Python documentation.'},{'title':'Python','url':'https://www.python.org/','text':'Python programming language.'}]}
        with tempfile.TemporaryDirectory() as root:
            bot=AkiraAssistant(cfg,Path(root))
            try:
                with patch('assistant_akira.ollama_status',return_value={'models':['qwen3:4b']}),patch.object(bot,'_source_tool',return_value=source),patch('assistant_akira.ollama_agent',return_value='Borrador incompleto'),patch('akira_local_ai.completion_info',return_value={'truncated':True,'finish_reason':'length'}):
                    with self.assertRaisesRegex(RuntimeError,'no terminó'):bot.local_llm_reply('Busca fuentes sobre programación en Python',{})
                self.assertNotIn('Borrador incompleto',str(bot.history));self.assertNotEqual(bot.conversation.snapshot()['phase'],'READY')
            finally:bot._managed_model.shutdown()
