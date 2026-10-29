"""Production Qt/controller lifecycle with a labelled transport stub, no real LLM.

The separate REAL_CHAT_REV15 report requires actual GGUF generation for every
question. This fast check isolates loading/stream/retry behavior in the EXE.
"""
import tempfile,threading,time
from contextlib import contextmanager
from pathlib import Path
from bundled_model import MODEL_NAME
from unittest.mock import patch


def run_check():
    from PySide6.QtWidgets import QApplication
    from desktop_qt import StudioWindow
    from settings import DEFAULT,load_config,save_config
    from akira_version import BUILD_ID
    app=QApplication.instance() or QApplication([]);checks={};window=None
    loading=threading.Event();thinking=threading.Event();stream=threading.Event()
    load_go=threading.Event();think_go=threading.Event();stream_go=threading.Event();fail=[False]
    with tempfile.TemporaryDirectory(prefix='AKIRA_CHAT_STATES_') as tmp:
        cfg=load_config(DEFAULT);cfg['assistant'].update(local_runtime_enabled=False,auto_research=False,auto_youtube_research=False)
        save_config(cfg,Path(tmp)/'akira_config.json')
        def wait_for(predicate):
            end=time.monotonic()+5
            while time.monotonic()<end:
                app.processEvents();window.poll()
                if predicate():return
                time.sleep(.005)
            raise RuntimeError('La interfaz no confirmó la transición esperada de conversación')
        try:
            window=StudioWindow(tmp,preview=True,start_actor=False);window.show();window.navigate(5)
            window._model_status={'phase':'IDLE','ready':False};window._ai_due=time.monotonic()+60
            bot=window.controller.assistant
            @contextmanager
            def session(*args,**kwargs):
                loading.set()
                if not load_go.wait(5):raise TimeoutError('QA loading gate')
                yield
            def generate(*args,**kwargs):
                if fail[0]:raise TimeoutError('labelled transport fixture')
                thinking.set()
                if not think_go.wait(5):raise TimeoutError('QA thinking gate')
                bot._progress('RESPONDIENDO','Respuesta de transporte sintético; no es una inferencia neuronal.')
                stream.set()
                if not stream_go.wait(5):raise TimeoutError('QA stream gate')
                return 'Respuesta de transporte sintético; no es una inferencia neuronal.'
            with patch.object(bot._managed_model,'session',session), \
                 patch('assistant_akira.ollama_status',return_value={'ok':True,'models':[MODEL_NAME]}), \
                 patch('assistant_akira.ollama_agent',side_effect=generate):
                window.chat_entry.setText('que piensas de la ciencia');window.send_chat();wait_for(lambda:loading.is_set() and 'Cargando' in window.ai_label.text())
                checks['loading_is_visible']=window.director.loading and 'Cargando' in window.ai_label.text()
                load_go.set();wait_for(lambda:thinking.is_set() and window.director.expression=='thinking')
                checks['thinking_is_visible']=window.director.expression=='thinking'
                think_go.set();wait_for(lambda:stream.is_set() and 'Respondiendo' in window.chat_status.text())
                checks['stream_overrides_idle']=window.director.expression=='talking' and not window.director.loading and 'Respondiendo' in window.chat_status.text()
                checks['current_question_stays_visible']='que piensas de la ciencia' in window.chat_view.toPlainText()
                stream_go.set();wait_for(lambda:not window.controller.chat_busy)
                checks['answer_is_recorded']=bot.chats.history()[-1]['text'].startswith('Respuesta de transporte sintético')
                fail[0]=True;window.chat_entry.setText('dime cual es la formula mas elegante de las matematicas');window.send_chat()
                wait_for(lambda:not window.controller.chat_busy and window.chat_retry.isVisible())
                checks['failure_has_a_retry_action']=window.director.expression=='alert' and 'Reintentar' in window.chat_view.toPlainText()
                checks['failure_does_not_paste_headlines']='news.google.com' not in window.chat_view.toPlainText()
                fail[0]=False;window.retry_chat();wait_for(lambda:not window.controller.chat_busy and not window.chat_retry.isVisible())
                checks['retry_uses_the_same_question']=bot.chats.history()[-2]['text']=='dime cual es la formula mas elegante de las matematicas'
                checks['retry_produces_a_new_response']=bot.chats.history()[-1]['text'].startswith('Respuesta de transporte sintético')
                checks['no_broker_actor']=window.controller.actor is None
        finally:
            load_go.set();think_go.set();stream_go.set()
            if window:window.controller.cancel_chat();window.close();app.processEvents()
        if not all(checks.values()):raise RuntimeError('Conversation lifecycle failed: '+str(checks))
    return {'status':'PASSED','build':BUILD_ID,'checks':checks,'transport':'EXPLICIT SYNTHETIC STUB',
        'real_model_in_this_check':False,'live_account_used':False}


if __name__=='__main__':
    import json
    print(json.dumps(run_check(),ensure_ascii=False))
