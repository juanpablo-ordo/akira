"""Real bundled-model acceptance through the production assistant; synthetic news only."""
from pathlib import Path
import argparse,json,subprocess,tempfile,time,traceback
from urllib.request import urlopen
from unittest.mock import patch
from settings import DEFAULT,load_config
from assistant_akira import AkiraAssistant
from akira_local_ai import chat,owned_context


def run(exe,model,report):
    report=Path(report);report.parent.mkdir(parents=True,exist_ok=True);rows=[];endpoint='http://127.0.0.1:18997/v1/chat/completions';proc=None;bot=None
    result={'status':'FAILED','scenarios':rows,'news_data':'SYNTHETIC; not a real Xbox announcement','live_account_used':False}
    with report.with_suffix('.llama.log').open('wb') as log,tempfile.TemporaryDirectory(prefix='AKIRA_REAL_REV6_') as tmp:
        try:
            proc=subprocess.Popen([str(Path(exe).resolve()),'--model',str(Path(model).resolve()),'--host','127.0.0.1','--port','18997','--ctx-size','4096','--n-gpu-layers','0','--threads','4','--parallel','1','--jinja'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
            until=time.monotonic()+170
            while time.monotonic()<until:
                if proc.poll() is not None:raise RuntimeError('Bundled server exited before health')
                try:
                    with urlopen('http://127.0.0.1:18997/health',timeout=2) as response:
                        if response.status==200:break
                except Exception:time.sleep(.2)
            else:raise TimeoutError('Server health deadline')
            cfg=load_config(DEFAULT);cfg['assistant'].update(local_runtime_enabled=False,local_endpoint=endpoint,local_model='Qwen3-4B-Q4_K_M.gguf',local_primary=True,local_fallback=True,cloud=False,auto_research=False,auto_youtube_research=False,self_review=False,fast_chat_timeout_seconds=90)
            progress=[];bot=AkiraAssistant(cfg,Path(tmp),auto_prepare=False,progress_callback=lambda row:progress.append((time.monotonic(),row)))
            def ask(name,question,check):
                progress.clear();start=time.monotonic()
                with owned_context(4096):answer=bot.reply(question,{},use_cloud=False)
                low=answer.casefold()
                first=next((t-start for t,r in progress if r.get('stage')=='RESPONDIENDO'),None)
                row={'name':name,'question':question,'answer':answer,'seconds':round(time.monotonic()-start,3),'first_visible_seconds':round(first,3) if first is not None else None};rows.append(row);print(name+' '+str(row['seconds'])+' s '+answer[:150],flush=True);check(low)
            def require(value,message):
                if not value:raise AssertionError(message)
            ask('typos_and_new_topic','Me esplicas la diferncia entre la memroia RAM y el disco de una compuadora?',lambda a:require('ram' in a and any(x in a for x in ('disco','ssd','almacenamiento')),'RAM/disk answer irrelevant'))
            ask('follow_up','¿Cuál de las dos pierde los datos cuando apago la computadora?',lambda a:require('ram' in a and any(x in a for x in ('volátil','volatil','borra','pierde','apaga','apagado')),'Follow-up did not preserve topic'))
            ask('topic_change','Cambiemos de tema: tengo 3 manzanas y regalo 1. ¿Cuántas me quedan?',lambda a:require('dos' in a or '2' in a,'New-topic arithmetic wrong'))
            bot.switch_chat(new=True);cfg['assistant']['auto_research']=True
            fixture={'query':'Xbox Gears prueba','results':[{'title':'Xbox Wire · ficha sintética de prueba','url':'https://news.xbox.com/es-es/gears-prueba/','text':'FICHA SINTÉTICA DE QA. NO ES UNA NOTICIA REAL. Xbox anunció el videojuego ficticio Gears Prueba; sus protagonistas son Mara y Sol. Se anunció, pero no se ha lanzado. No se ha publicado una fecha de salida. No es una película.','read_status':'qa_fixture'}],'errors':[]}
            def news_check(a):
                require(all(x in a for x in ('mara','sol','gears prueba')),'Did not answer using supplied evidence')
                require(not any(x in a for x in ('guillermo del toro','kig-yar','gears 6')),'Imported unrelated lore')
            with patch('assistant_akira.lookup_current_fact',return_value=fixture),patch('assistant_akira.lookup_verified_current_fact',return_value=fixture),patch.object(bot,'_source_tool',return_value=fixture):
                ask('current_news_evidence','Xbox acaba de lanzar el nuevo Gears: según la ficha de prueba, ¿cómo se llama y quiénes son sus protagonistas?',news_check)
            schema={'type':'object','properties':{'bias':{'type':'number','minimum':-1,'maximum':1}},'required':['bias'],'additionalProperties':False}
            with owned_context(4096):structured=chat([{'role':'system','content':'/no_think\nDevuelve solo el JSON requerido. Sin datos ni evidencia el sesgo bias es 0.'},{'role':'user','content':'No hay evidencia de mercado. Devuelve bias cero.'}],model='Qwen3-4B-Q4_K_M.gguf',endpoint=endpoint,timeout=90,think=False,response_format=schema,options={'num_predict':256,'temperature':0})
            if json.loads(structured)!={'bias':0}:raise AssertionError('Structured review not exact')
            rows.append({'name':'strict_json','answer':structured});result['status']='PASSED';return result
        except Exception as error:
            result.update(error=type(error).__name__+': '+str(error),traceback=traceback.format_exc());raise
        finally:
            if bot:bot._managed_model.shutdown()
            if proc and proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=8)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=4)
            report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',required=True);p.add_argument('--model',required=True);p.add_argument('--report',required=True);a=p.parse_args();print(json.dumps(run(a.exe,a.model,a.report),ensure_ascii=False))
