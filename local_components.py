"""Executable installed-payload check, without MT5, downloads or credentials."""
from pathlib import Path
import json
import traceback


def check_components(report, user_root):
    try:
        from settings import DEFAULT
        from akira_model_runtime import ManagedLlamaProcess
        from youtube_support import diagnostic
        runtime=ManagedLlamaProcess(DEFAULT['assistant'],log_root=user_root)
        paths=runtime._paths()
        youtube=diagnostic(check_runtime=True)
        if paths is None:raise RuntimeError('Faltan motor local o GGUF en la instalación.')
        if not (youtube['ejs_present'] and youtube.get('runtime_verified')):
            raise RuntimeError('YouTube: faltan EJS o un Deno ejecutable compatible.')
        result={'status':'PASSED','engine':str(paths[0]),'model':str(paths[1]),'youtube':youtube,
                'network_used':False,'live_account_used':False}
    except Exception as error:
        result={'status':'FAILED','error':type(error).__name__+': '+str(error),'traceback':traceback.format_exc()}
    Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['status']=='PASSED' else 1
