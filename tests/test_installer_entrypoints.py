"""Exercise installer entrypoints without inheriting pytest's project imports.

The subprocess smoke uses synthetic HTTP/process fixtures and the real chat
client. It does not claim to run a native model; Windows CI still must do that.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def probe_smoke(script, report, mode):
    # Match python installer/smoke_local_ai.py, with no project in sys.path.
    sys.path.insert(0, str(script.parent))
    calls = []

    class Response(io.BytesIO):
        status = 200

    def reply(data):
        return Response(json.dumps(data).encode('utf-8'))

    def completion(text):
        return {'choices':[{'finish_reason':'stop','message':{'content':text}}]}

    def network(request, **kwargs):
        url = request if isinstance(request, str) else request.full_url
        payload = json.loads(request.data) if not isinstance(request, str) and request.data else {}
        calls.append({'path':url.split('18988')[-1], 'payload':payload})
        if url.endswith('/health'):
            return reply({'status':'ok'})
        if url.endswith('/apply-template'):
            return reply({'prompt':'synthetic tokenization fixture'})
        if url.endswith('/tokenize'):
            return reply({'tokens':[1,2,3]})
        if not url.endswith('/v1/chat/completions'):
            raise AssertionError('Unexpected network access: '+url)
        user = payload['messages'][-1]['content']
        if 'FUENTE DE PRUEBA' in user:
            assert 'actual presidente de Guatemala' in user, user
            return reply(completion('No lo sé' if mode=='wrong_answer' else 'Bernardo Arévalo.'))
        if 'BTCUSDm:BUY:LIMIT:1' in user:
            result = {'BTCUSDm:BUY:LIMIT:1':{'verdict':'APPROVE' if mode=='wrong_json' else 'ABSTAIN',
                                          'reason':'faltan datos','missing':['precios','riesgo']}}
            return reply(completion(json.dumps(result)))
        return reply(completion('Hola'))

    class Process:
        def __init__(self, command, **kwargs):
            assert Path(command[0]).is_absolute()
            self.code = 1 if mode=='server_exit' else None
            kwargs['stdout'].write(b'synthetic llama process log\n')
            self.stopped = False
        def poll(self): return self.code
        def terminate(self): self.code=0;self.stopped=True
        def kill(self): self.code=-1;self.stopped=True
        def wait(self, **kwargs): return self.code

    class Connection:
        def __init__(self, *args, **kwargs):
            self.sock=self;self.closed=threading.Event()
        def request(self, method, path, body, headers):
            calls.append({'path':path,'cancellable':True,'payload':json.loads(body)})
        def getresponse(self):
            if not self.closed.wait(3):raise TimeoutError('fixture was not cancelled')
            raise OSError('synthetic socket closed')
        def shutdown(self, *args):self.closed.set()
        def close(self):self.closed.set()

    spec=importlib.util.spec_from_file_location('standalone_smoke',script)
    module=importlib.util.module_from_spec(spec)
    with patch('urllib.request.urlopen',side_effect=network), \
         patch('http.client.HTTPConnection',Connection), patch('subprocess.Popen',Process):
        spec.loader.exec_module(module)
        exe=report.parent/'llama-server.exe';exe.write_bytes(b'MZsynthetic fixture')
        model=report.parent/'fixture.gguf';model.write_bytes(b'GGUFsynthetic model fixture')
        module.SHA=hashlib.sha256(model.read_bytes()).hexdigest()
        result=module.main(['--exe',str(exe),'--model',str(model),'--report',str(report)])
    report.with_suffix('.requests.json').write_text(json.dumps(calls),encoding='utf-8')
    return result


class InstallerEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.folder=Path(self.temporary.name)
        self.env={key:value for key,value in os.environ.items() if key not in ('PYTHONPATH','PYTHONHOME')}

    def run_child(self, arguments, cwd=None):
        return subprocess.run([sys.executable,*arguments],cwd=cwd or self.folder,
                              env=self.env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)

    def test_direct_and_module_preflight_resolve_real_production_imports(self):
        for name in ('smoke_local_ai','check_installed_ai'):
            for direct in (True,False):
                with self.subTest(name=name,direct=direct):
                    arguments=['-I',str(ROOT/'installer'/f'{name}.py')] if direct else ['-m','installer.'+name]
                    result=self.run_child([*arguments,'--check-imports'],None if direct else ROOT)
                    self.assertEqual(result.returncode,0,result.stderr)
                    report=json.loads(result.stdout)
                    self.assertEqual(report['status'],'PASSED')
                    self.assertFalse(report.get('inference_run',report.get('installation_run')))

    def test_every_installer_cli_starts_as_a_script_and_module(self):
        for name in ('smoke_local_ai','check_installed_ai','check_tk_runtime','prepare_sprite_ai','prepare_licenses'):
            for direct in (True,False):
                with self.subTest(name=name,direct=direct):
                    arguments=['-I',str(ROOT/'installer'/f'{name}.py')] if direct else ['-m','installer.'+name]
                    result=self.run_child([*arguments,'--help'],None if direct else ROOT)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertIn('usage:',result.stdout)

    def run_smoke(self, mode):
        report=self.folder/'report.json'
        result=self.run_child(['-I',str(Path(__file__).resolve()),'--probe',str(ROOT/'installer/smoke_local_ai.py'),str(report),mode])
        self.assertTrue(report.is_file(),result.stderr)
        return result,json.loads(report.read_text(encoding='utf-8')),json.loads(report.with_suffix('.requests.json').read_text(encoding='utf-8'))

    def test_standalone_smoke_reaches_real_context_client_scenarios_and_cancellation(self):
        result,report,calls=self.run_smoke('success')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        for key in ('typo_question','structured_review','cancel_before_headers','reply_after_cancel'):
            self.assertIs(report[key],True)
        self.assertFalse(report['live_account_used'])
        self.assertGreaterEqual(sum(row['path']=='/apply-template' for row in calls),3)
        self.assertGreaterEqual(sum(row['path']=='/tokenize' for row in calls),3)
        self.assertEqual(sum(bool(row.get('cancellable')) for row in calls),1)
        self.assertIn('synthetic llama',Path(report['server_log']).read_text(encoding='utf-8'))

    def test_incorrect_answers_and_verdicts_still_fail_after_visible_greeting(self):
        for mode in ('wrong_answer','wrong_json'):
            with self.subTest(mode=mode):
                result,report,calls=self.run_smoke(mode)
                self.assertEqual(result.returncode,1,result.stderr)
                self.assertEqual(report['status'],'FAILED')
                self.assertIn('RuntimeError',report['error'])
                self.assertNotIn('ModuleNotFoundError',report['error'])
                self.assertTrue(calls)

    def test_failed_native_server_leaves_a_failed_report_and_its_log(self):
        result,report,calls=self.run_smoke('server_exit')
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertEqual(report['status'],'FAILED')
        self.assertIn('quit before health',report['error'])
        self.assertEqual(calls,[])
        self.assertIn('synthetic llama',Path(report['server_log']).read_text(encoding='utf-8'))

    def test_missing_engine_fails_without_downloading_a_model(self):
        report=self.folder/'missing.json';model=self.folder/'not-downloaded.gguf'
        result=self.run_child(['-I',str(ROOT/'installer/smoke_local_ai.py'),'--exe',str(self.folder/'absent.exe'),
                               '--model',str(model),'--report',str(report)])
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('FileNotFoundError',json.loads(report.read_text(encoding='utf-8'))['error'])
        self.assertFalse(model.exists())


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--probe':
        raise SystemExit(probe_smoke(Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4]))
    unittest.main()
