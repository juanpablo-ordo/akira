"""Offline contract for llama.cpp's OpenAI-compatible loopback backend."""
import io,json,unittest
from unittest.mock import patch
from akira_local_ai import chat,status,agent,choose_text_model
class FakeResponse(io.BytesIO):
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
class DirectBackendTests(unittest.TestCase):
    endpoint='http://127.0.0.1:8080/v1/chat/completions'
    def test_status_and_text(self):
        with patch('akira_local_ai.urlopen',return_value=FakeResponse(json.dumps({'data':[{'id':'akiramodel.gguf'}]}).encode('utf8'))):
            row=status(self.endpoint,force=True)
        self.assertEqual(row['models'],['akiramodel.gguf'])
        self.assertEqual(choose_text_model(row['models']),'akiramodel.gguf')
        answer={'choices':[{'message':{'content':'Hola, soy AKIRA'},'finish_reason':'stop'}]}
        with patch('akira_local_ai._post',return_value=answer) as post:
            reply=chat([{'role':'user','content':'Hola'}],model='akiramodel.gguf',endpoint=self.endpoint)
        self.assertIn('Hola',reply)
        self.assertEqual(post.call_args.args[1]['max_tokens'],3000)
        self.assertFalse(post.call_args.kwargs['stream_on_cancel'])
    def test_tool_cycle_preserves_openai_tool_id(self):
        call={'id':'tc_1','type':'function','function':{'name':'search','arguments':'{"q":"algo"}'}}
        events=[{'choices':[{'message':{'role':'assistant','tool_calls':[call]},'finish_reason':'tool_calls'}]},
                {'choices':[{'message':{'role':'assistant','content':'Comprobé las fuentes.'},'finish_reason':'stop'}]}]
        with patch('akira_local_ai._post',side_effect=events) as post:
            reply=agent([{'role':'user','content':'Busca algo'}],tools=[{'type':'function','function':{'name':'search','parameters':{'type':'object'}}}],executor=lambda name,args:{'ok':True},endpoint=self.endpoint,model='akiramodel.gguf')
        self.assertIn('Comprobé',reply)
        self.assertEqual(post.call_args.args[1]['messages'][-1]['tool_call_id'],'tc_1')
    def test_remote_endpoint_is_disallowed(self):
        with self.assertRaisesRegex(ValueError,'solo admite'):
            status('https://remote.example.com/v1/chat/completions',force=True)
if __name__=='__main__':unittest.main()
