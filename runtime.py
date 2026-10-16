"""Una sola sesión e hilo para MT5; interfaz y proveedores trabajan por mensajes."""
from pathlib import Path
import hashlib,os,queue,sys,time,traceback
from akira_version import BUILD_ID
from execution import Gateway,Journal,Blocked
from engine import Engine
from account_lock import AccountLock
from research import ContextWorker
from legacy_handoff import retire
from command_bridge import dispatch


def session_write_guard(g,account,lock):
    """Conservar el análisis si otro controlador bloquea escrituras en la cuenta."""
    try:
        if g.cfg['mode']=='trade' and lock is None:lock=AccountLock(account)
        retire(g)
        g.execution_lease_active=lock is not None
        return lock,''
    except Blocked as exc:
        g.execution_lease_active=False
        return lock,str(exc)


def run_session(cfg,root,log,stop,commands,publish,preview=False):
    root=Path(root);api=None;lock=None;context=None;engine=None;bound_identity=None
    started_utc=time.time();stage='INICIANDO';publish_callback=publish
    def publish(row):
        row={**row,'build':BUILD_ID,'runtime':{'application_root':str(root.resolve()),
            'python_executable':sys.executable,'process_id':os.getpid(),
            'started_utc':started_utc,'stage':stage,'preview':bool(preview)},
            'configured_execution':{k:cfg[k] for k in ('mode','symbols','risk','sizing','runner')}}
        publish_callback(row)
    try:
        if preview:
            from tests.fake_mt5 import Clock,FakeMT5
            clock=Clock();clock.now=time.time();api=FakeMT5(clock)
            cfg={**cfg,'mode':'observe'};api.account.server='VISTA PREVIA · DATOS SINTÉTICOS'
        else:
            if os.name!='nt':raise RuntimeError('La conexión MT5 requiere Windows; usa --preview sin cuenta')
            import MetaTrader5 as api
            clock=time.time
        while not stop.is_set():
            stage='CONECTANDO MT5'
            if not preview:
                kwargs={'timeout':10000}
                ok=api.initialize(cfg['terminal_path'],**kwargs) if cfg['terminal_path'] else api.initialize(**kwargs)
                if not ok or api.account_info() is None:
                    publish({'connected':False,'error':'Esperando MT5: '+str(api.last_error())});api.shutdown();stop.wait(3);continue
            account=api.account_info()
            identity_pair=(int(account.login),str(account.server))
            if bound_identity is None:bound_identity=identity_pair
            if identity_pair!=bound_identity:raise Blocked('La cuenta cambió al reconectar. Reinicia Akira en la cuenta elegida.')
            identity=hashlib.sha256(f'{account.server}:{account.login}'.encode()).hexdigest()[:16]
            journal=Journal(root/'state'/('preview.json' if preview else 'cuenta_'+identity+'.json'),read_only=preview)
            g=Gateway(api,cfg,journal,log,clock)
            g.requires_execution_lease=not preview;g.execution_lease_active=False
            for symbol,on in cfg['symbols'].items():
                if on and not api.symbol_select(symbol,True):raise RuntimeError('MT5 no tiene el símbolo '+symbol+'; revisa el nombre/sufijo en configuración')
            context=None
            if not preview:
                try:
                    context=ContextWorker(cfg,root);context.start()
                except Exception as exc:
                    log.report('IA','CONTEXTO AUXILIAR',type(exc).__name__+': '+str(exc))
                    if context:
                        try:context.close()
                        except Exception:pass
                    context=None
            engine=Engine(g,cfg,log,context)
            while not stop.is_set():
                began=time.monotonic()
                stage='RETIRANDO MOTOR ANTERIOR' if not preview else 'VISTA PREVIA'
                if not preview:
                    lock,g.runtime_execution_block=session_write_guard(g,account,lock)
                    if g.runtime_execution_block:
                        # La cuenta está conectada. Un EA anterior bloquea las
                        # escrituras, pero no debe apagar análisis, chat ni botón.
                        log.report('MT5','EJECUCIÓN BLOQUEADA',g.runtime_execution_block)
                try:
                    stage='COMANDOS'
                    for _ in range(8):
                        cmd=commands.get_nowait()
                        dispatch(engine,cmd)
                except queue.Empty:pass
                # A mode change delivered by a command must acquire ownership
                # before the first live cycle, even if this turn began in observe.
                if not preview and cfg['mode']=='trade' and lock is None:
                    lock,g.runtime_execution_block=session_write_guard(g,account,lock)
                try:
                    stage='CICLO'
                    if preview:
                        clock.advance(cfg['poll_seconds'])
                        for symbol in cfg['symbols']:
                            if symbol in api.ticks:api.set_quote(symbol,api.ticks[symbol].bid,fill=False)
                    view=engine.step();view['preview']=preview;publish(view)
                except Blocked as e:
                    log.report('MT5','ESPERANDO',str(e));publish({'connected':False,'error':str(e)})
                    if not preview and not bool(getattr(api.terminal_info(),'connected',False)):break
                except Exception as e:
                    log.event('ERROR',type(e).__name__+': '+str(e),traceback=traceback.format_exc())
                    publish({'connected':False,'error':type(e).__name__+': '+str(e)})
                stop.wait(max(.02,cfg['poll_seconds']-(time.monotonic()-began)))
            engine.close();engine=None
            if context:context.close();context=None
            if not preview:api.shutdown()
            if stop.is_set():break
            stop.wait(2)
    except Exception as e:
        log.event('ERROR',type(e).__name__+': '+str(e),traceback=traceback.format_exc())
        publish({'connected':False,'error':str(e)})
    finally:
        if engine:engine.close()
        if context:context.close()
        if api is not None and not preview:api.shutdown()
        if lock:lock.close()
