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
from mt5_connection import MT5Connection,ConnectionProblem,target_signature


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


def _mt5_api():
    if os.name!='nt':raise RuntimeError('La conexión MT5 requiere Windows; usa --preview sin cuenta')
    import MetaTrader5
    return MetaTrader5


def run_session(cfg,root,log,stop,commands,publish,preview=False):
    root=Path(root);api=None;lock=None;context=None;engine=None;bound_identity=None
    started_utc=time.time();stage='INICIANDO';publish_callback=publish
    reconnect=False;paused=False;network_available=True;failures=0
    def publish(row):
        row={**row,'build':BUILD_ID,'runtime':{'application_root':str(root.resolve()),
            'python_executable':sys.executable,'process_id':os.getpid(),
            'started_utc':started_utc,'stage':stage,'preview':bool(preview)},
            'configured_execution':{k:cfg[k] for k in ('mode','symbols','risk','sizing','runner')}}
        publish_callback(row)
    def disconnected(problem,delay=0):
        status=problem.status(delay)
        publish({'connected':False,'mode':cfg['mode'],'paused':paused,
            'error':status['message'],'mt5_connection':status,'execution_allowed':False,
            'execution_gate':{'code':'MT5_DISCONNECTED','execution_allowed':False,
                'reason':status['message'],'next_action':status['next_action']}})
    def handle(cmd):
        nonlocal reconnect,network_available,bound_identity
        action=cmd.get('action')
        if action=='reconnect_mt5':
            reconnect=True
            return {'ok':True,'detail':'Reconexión MT5 solicitada. Se comprobará la cuenta antes de operar.'}
        before=target_signature(cfg)
        if engine is not None:
            result=engine.handle_command(cmd)
        elif action=='apply_settings':
            from settings_effects import validate_form
            saved=validate_form(cmd['config']);cfg.update(saved)
            result={'ok':True,'settings_applied':True}
        elif action=='network_state' and type(cmd.get('online')) is bool:
            result={'ok':True}
        else:return {'ok':False,'error':'MT5 aún no está conectado. Las solicitudes de órdenes no se conservan para enviarlas después.'}
        if result.get('ok') and action=='network_state':network_available=cmd['online']
        if result.get('ok') and before!=target_signature(cfg):
            reconnect=True
            # An explicit target change in observe mode starts a fresh journal
            # and requires separate confirmation before any new trading.
            if cfg['mode']=='observe':bound_identity=None
        return result
    def drain():
        for _ in range(128):
            try:cmd=commands.get_nowait()
            except queue.Empty:break
            dispatch(None,cmd,handle)
    def wait_retry(seconds):
        deadline=time.monotonic()+seconds
        while not stop.is_set() and not reconnect:
            left=deadline-time.monotonic()
            if left<=0:break
            try:cmd=commands.get(timeout=min(.2,left))
            except queue.Empty:continue
            dispatch(None,cmd,handle)
    def release():
        nonlocal engine,context,lock,paused
        if engine:paused=engine.paused
        owned=(engine,context,lock);engine=context=lock=None
        for item in owned:
            if item is not None:
                try:item.close()
                except Exception as exc:log.report('MT5','CIERRE DE COMPONENTE',type(exc).__name__+': '+str(exc))
        if api is not None and not preview:
            try:api.shutdown()
            except Exception as exc:log.report('MT5','CIERRE DE CONEXIÓN',type(exc).__name__+': '+str(exc))
    try:
        if preview:
            from tests.fake_mt5 import Clock,FakeMT5
            clock=Clock();clock.now=time.time();api=FakeMT5(clock)
            cfg={**cfg,'mode':'observe'};api.account.server='VISTA PREVIA · DATOS SINTÉTICOS'
            connector=None
        else:
            api=_mt5_api();clock=time.time;connector=MT5Connection(api,root)
        while not stop.is_set():
            try:
                drain();reconnect=False
                if stop.is_set():break
                stage='CONECTANDO MT5'
                if not preview:
                    disconnected(ConnectionProblem('CONNECTING','Conectando con MetaTrader 5…',
                        'El primer inicio puede tardar hasta 60 segundos. Se usará la cuenta guardada en Ajustes.'))
                    signature=target_signature(cfg)
                    account=connector.connect(cfg)
                    # Saves made while initialize() was waiting must apply before
                    # binding a journal or allowing the first financial cycle.
                    drain()
                    if stop.is_set():break
                    if reconnect or signature!=target_signature(cfg):continue
                else:account=api.account_info()
                identity_pair=(int(account.login),str(account.server))
                if bound_identity is None:bound_identity=identity_pair
                if identity_pair!=bound_identity:
                    raise ConnectionProblem('ACCOUNT_CHANGED','La cuenta cambió mientras Akira estaba abierto.',
                        'Vuelve a seleccionar la cuenta original en MT5. Para usar otra, reinicia Akira y autorízala; no se enviarán órdenes a una cuenta distinta.')
                identity=hashlib.sha256(f'{account.server}:{account.login}'.encode()).hexdigest()[:16]
                journal=Journal(root/'state'/('preview.json' if preview else 'cuenta_'+identity+'.json'),read_only=preview)
                g=Gateway(api,cfg,journal,log,clock)
                g.requires_execution_lease=not preview;g.execution_lease_active=False;g.network_available=network_available
                for symbol,on in cfg['symbols'].items():
                    if on and not api.symbol_select(symbol,True):
                        raise ConnectionProblem('SYMBOL','MT5 no tiene disponible el símbolo '+symbol+'.',
                            'Revisa el nombre y sufijo del símbolo en Ajustes → Operación y en Observación del mercado de MT5.')
                if not preview:
                    try:context=ContextWorker(cfg,root);context.start()
                    except Exception as exc:
                        log.report('IA','CONTEXTO AUXILIAR',type(exc).__name__+': '+str(exc))
                        if context:context.close()
                        context=None
                engine=Engine(g,cfg,log,context);engine.paused=paused
                while not stop.is_set():
                    began=time.monotonic()
                    stage='RETIRANDO MOTOR ANTERIOR' if not preview else 'VISTA PREVIA'
                    if not preview:
                        lock,g.runtime_execution_block=session_write_guard(g,account,lock)
                        if g.runtime_execution_block:log.report('MT5','EJECUCIÓN BLOQUEADA',g.runtime_execution_block)
                    stage='COMANDOS';drain()
                    if stop.is_set() or reconnect:break
                    if not preview and cfg['mode']=='trade' and lock is None:
                        lock,g.runtime_execution_block=session_write_guard(g,account,lock)
                    try:
                        stage='CICLO'
                        if not preview:
                            terminal=api.terminal_info()
                            if terminal is None or not getattr(terminal,'connected',False):
                                raise ConnectionProblem('BROKER_OFFLINE','Se perdió la conexión de MT5 con el bróker.',
                                    'Akira intentará reconectar y comprobará órdenes y posiciones antes de continuar.')
                        if preview:
                            clock.advance(cfg['poll_seconds'])
                            for symbol in cfg['symbols']:
                                if symbol in api.ticks:api.set_quote(symbol,api.ticks[symbol].bid,fill=False)
                        view=engine.step();view['preview']=preview
                        if not preview:
                            view['mt5_connection']={'code':'CONNECTED','message':'MT5 conectado y cuenta comprobada.',
                                'account_type':'demo' if int(getattr(account,'trade_mode',-1))==0 else 'real' if int(getattr(account,'trade_mode',-1))==2 else 'otra',
                                'terminal_path':connector.saved.get('terminal_path',''),'next_action':''}
                        publish(view);failures=0
                    except Blocked as exc:
                        log.report('MT5','ESPERANDO',str(exc))
                        terminal=api.terminal_info()
                        if not preview and (terminal is None or not getattr(terminal,'connected',False) or api.account_info() is None):
                            raise ConnectionProblem('BROKER_OFFLINE','Se perdió la conexión de MT5 con el bróker.',
                                'Akira intentará reconectar y comprobará órdenes y posiciones antes de continuar.',str(exc)) from exc
                        disconnected(ConnectionProblem('ACCOUNT_STATE',str(exc),'Revisa el estado de tu cuenta en MT5.'))
                    stop.wait(max(.02,cfg['poll_seconds']-(time.monotonic()-began)))
            except Exception as exc:
                failures+=1;stage='ESPERANDO RECONEXIÓN MT5'
                problem=exc if isinstance(exc,ConnectionProblem) else ConnectionProblem('SESSION',
                    'No se completó la conexión con MT5. Se volverá a intentar.',
                    'Mantén MT5 abierto con tu cuenta demo; si persiste, revisa Terminal → Diagnóstico.',type(exc).__name__+': '+str(exc))
                delay=min(30,3*2**min(failures-1,4))
                log.event('MT5','RECONEXIÓN: '+str(problem),detail=problem.detail,traceback=traceback.format_exc())
                disconnected(problem,delay)
            finally:
                release()
            if stop.is_set():break
            if not reconnect:wait_retry(min(30,3*2**min(max(0,failures-1),4)))
    except Exception as exc:
        log.event('ERROR',type(exc).__name__+': '+str(exc),traceback=traceback.format_exc())
        disconnected(ConnectionProblem('RUNTIME_UNAVAILABLE','No se pudo iniciar el componente de conexión MT5.',
            'Comprueba que estás usando Windows y el instalador completo de esta versión. Consulta Terminal → Diagnóstico.',str(exc)))
