"""Windows CI smoke for bundled llama.cpp + pinned Gemma 4 E2B GGUF.

Do not pass this check merely because /health is ready or a response contains
thinking tokens. Require a nonempty, finished assistant message visible to users.
Never connects to an MT5 account.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import sys
import threading
import tempfile
import traceback
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Direct script execution puts installer/, not the project, on sys.path.
# Resolve our own source before importing clients or starting/downloading AI.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from akira_local_ai import chat, owned_context
from language_normalization import understood

from bundled_model import MODEL_NAME,MODEL_SHA,MODEL_URL
URL = MODEL_URL
SHA = MODEL_SHA


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def get_model(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and sha256(path) == SHA:
        return path
    partial = path.with_suffix('.partial')
    partial.unlink(missing_ok=True)
    try:
        req = Request(URL, headers={'User-Agent': 'AKIRA-CI/16.4.0'})
        with urlopen(req, timeout=90) as response, partial.open('wb') as stream:
            for chunk in iter(lambda: response.read(2 * 1024 * 1024), b''):
                stream.write(chunk)
        if sha256(partial) != SHA:
            raise ValueError('GGUF SHA256 did not match the pinned model')
        partial.replace(path)
        return path
    finally:
        partial.unlink(missing_ok=True)


def make_chat_payload():
    # Qwen3 thinks by default. A 24-token budget can be exhausted by hidden
    # thinking before any visible text is emitted. Use its supported soft switch
    # and the llama.cpp chat-template option for a predictable chat smoke.
    return {
        'model': MODEL_NAME,
        'messages': [
            {'role': 'system', 'content': '/no_think\nResponde brevemente en espanol.'},
            {'role': 'user', 'content': 'Di hola en una sola palabra.'},
        ],
        'chat_template_kwargs': {'enable_thinking': False},
        'temperature': 0,
        'max_tokens': 256,
        'stream': False,
    }


def validate_completion(response):
    choices = response.get('choices') or []
    choice = choices[0] if choices else {}
    message = choice.get('message') or {}
    content = message.get('content')
    if not isinstance(content, str):
        content = ''
    # Do not count just an unterminated chain-of-thought as a valid answer.
    visible = re.sub(r'<think>.*?</think>', '', content, flags=re.I | re.S).strip()
    if re.match(r'^\s*<think>', visible, re.I) or visible.strip().lower() == '</think>':
        visible = ''
    reason = choice.get('finish_reason')
    if not visible or reason == 'length':
        usage = response.get('usage') or {}
        reasoning = message.get('reasoning_content') or ''
        details = {
            'finish_reason': reason,
            'visible_chars': len(visible),
            'reasoning_chars': len(str(reasoning)),
            'completion_tokens': usage.get('completion_tokens'),
            'total_tokens': usage.get('total_tokens'),
            'model': response.get('model'),
        }
        raise RuntimeError('Bundled model produced no complete visible answer: ' + json.dumps(details, ensure_ascii=True))
    return visible


def verify_chat_scenarios(endpoint):
    """Exercise the production client against the real bundled server."""
    original='quien es el acutal presdiente de guatemla'
    question=understood(original)
    answer=chat([{'role':'system','content':'/no_think\nResponde en español en una frase y utiliza solo la fuente de prueba.'},
        {'role':'user','content':question+'\nFUENTE DE PRUEBA (15/10/2026): El presidente de Guatemala es Bernardo Arévalo. No uses otros datos.'}],
        model=MODEL_NAME,endpoint=endpoint,timeout=90,think=False,options={'num_predict':192,'temperature':0})
    plain=''.join(c for c in unicodedata.normalize('NFKD',answer.lower()) if not unicodedata.combining(c))
    if 'bernardo' not in plain or 'arevalo' not in plain:raise RuntimeError('La IA no respondió a la pregunta con faltas usando la fuente de prueba: '+answer[:300])
    key='BTCUSDm:BUY:LIMIT:1'
    schema={'type':'object','properties':{key:{'type':'object','properties':{
        'verdict':{'type':'string','enum':['APPROVE','REVISE','ABSTAIN']},'reason':{'type':'string'},
        'missing':{'type':'array','items':{'type':'string'}}},'required':['verdict','reason','missing'],'additionalProperties':False}},
        'required':[key],'additionalProperties':False}
    raw=chat([{'role':'system','content':'/no_think\nDevuelve exclusivamente el JSON solicitado.'},
        {'role':'user','content':'Para '+key+' no hay precios ni riesgo. Devuelve verdict ABSTAIN, reason faltan datos y missing [precios, riesgo].'}],
        model=MODEL_NAME,endpoint=endpoint,timeout=90,think=False,
        options={'num_predict':256,'temperature':0},response_format=schema)
    parsed=json.loads(raw)
    if set(parsed)!={key} or parsed[key].get('verdict')!='ABSTAIN' or not parsed[key].get('missing'):
        raise RuntimeError('La revisión estructurada del motor no conserva el id y el dictamen esperado')
    cancel=threading.Event();started=threading.Event();errors=[]
    def background():
        started.set()
        try:
            chat([{'role':'user','content':'Cuenta del 1 al 1000 sin saltarte ningún número y sin resumir.'}],
                 model=MODEL_NAME,endpoint=endpoint,timeout=30,think=False,
                 cancel_event=cancel,options={'num_predict':1200,'temperature':0})
        except Exception as error:errors.append(str(error))
    thread=threading.Thread(target=background,daemon=True);thread.start();started.wait(1);time.sleep(.2)
    before=time.monotonic();cancel.set();thread.join(5);cancel_seconds=time.monotonic()-before
    if thread.is_alive() or not any('detenido' in error.lower() for error in errors):
        raise RuntimeError('La petición local no se interrumpió al cancelar antes de recibir cabeceras')
    foreground=chat([{'role':'user','content':'Di hola en una palabra.'}],model=MODEL_NAME,
                    endpoint=endpoint,timeout=90,think=False,options={'num_predict':128,'temperature':0})
    if not foreground.strip():raise RuntimeError('La IA no volvió a responder después de cancelar')
    return {'typo_question':True,'fixture_based_answer':answer,'structured_review':True,
            'cancel_before_headers':True,'cancel_seconds':round(cancel_seconds,3),'reply_after_cancel':True,
            'live_account_used':False,'fact_scope':'Recorded synthetic test context, not live web verification'}


def smoke(exe, model, *, log_path=None):
    exe = Path(exe).resolve()
    model = Path(model).resolve()
    if not (exe.is_file() and model.is_file()):
        raise FileNotFoundError('Missing CPU llama-server.exe or Qwen3 GGUF')
    cmd = [str(exe), '--model', str(model), '--host', '127.0.0.1', '--port', '18988',
           '--ctx-size', '2048', '--n-gpu-layers', '0', '--threads', '3', '--parallel', '1', '--jinja']
    if log_path is not None:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    with (log_path.open('wb') if log_path is not None else tempfile.TemporaryFile()) as sink:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=sink, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 170
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError('llama-server.exe quit before health was ready')
                try:
                    with urlopen('http://127.0.0.1:18988/health', timeout=2) as response:
                        if response.status == 200:
                            break
                except (OSError, ValueError):
                    pass
                time.sleep(1)
            else:
                raise TimeoutError('llama-server.exe did not reach /health within 170s')

            req = Request('http://127.0.0.1:18988/v1/chat/completions',
                          data=json.dumps(make_chat_payload()).encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
            try:
                with urlopen(req, timeout=180) as response:
                    result = json.load(response)
            except HTTPError as exc:
                detail = exc.read(2000).decode('utf-8', 'replace')
                raise RuntimeError(f'Local model HTTP {exc.code}: {detail}') from exc
            except URLError as exc:
                raise RuntimeError(f'Local model request failed: {exc.reason}') from exc

            visible = validate_completion(result)
            print('AKIRA llama.cpp/Qwen3 visible chat OK; characters:', len(visible))
            with owned_context(2048):scenarios=verify_chat_scenarios('http://127.0.0.1:18988/v1/chat/completions')
            print('AKIRA typo, structured review and cancellation scenarios PASSED')
            return {'status':'PASSED','visible_characters':len(visible),**scenarios}
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--check-imports', action='store_true', help='Validate production clients without network or inference')
    args = parser.parse_args(argv)
    if not args.check_imports and (args.exe is None or args.model is None):
        parser.error('--exe and --model are required unless --check-imports is used')
    log_path = args.report.with_suffix('.llama.log') if args.report and not args.check_imports else None
    try:
        if args.check_imports:
            report = {'status':'PASSED', 'production_client':chat.__module__,
                      'context_manager':owned_context.__module__, 'normalizer':understood.__module__,
                      'inference_run':False}
        else:
            if not args.exe.is_file():
                raise FileNotFoundError('Missing CPU llama-server.exe: '+str(args.exe))
            report = smoke(args.exe, get_model(args.model), log_path=log_path)
    except Exception as error:
        report = {'status':'FAILED', 'error':type(error).__name__+': '+str(error),
                  'traceback':traceback.format_exc()}
    if log_path:
        report['server_log'] = str(log_path.resolve())
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['status']=='PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
