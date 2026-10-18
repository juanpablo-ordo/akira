"""Configuración estricta y migración desde instalaciones anteriores."""
import copy
import json
import math
import sys
from pathlib import Path

DEFAULT=json.loads((Path(__file__).parent/'default_config.json').read_text(encoding='utf-8'))


def ensure_user_config(folder):
    """Create a safe observe-only configuration on the FIRST run.

    Never overwrite an existing configuration, even if it cannot be parsed:
    user data and risk preferences must not be silently reset.
    """
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/'akira_config.json'
    if not path.exists():
        cfg=copy.deepcopy(DEFAULT)
        cfg['mode']='observe'
        cfg['expected_login']=0
        # Exclusive create: another AKIRA startup must not overwrite this one.
        try:
            with path.open('x',encoding='utf-8') as handle:
                json.dump(cfg,handle,ensure_ascii=False,indent=2)
                handle.write('\n')
        except FileExistsError:
            pass
    return path


def merge(base,source):
    out=copy.deepcopy(base)
    if not isinstance(source,dict):return out
    for k,v in source.items():
        if k in out:
            out[k]=merge(out[k],v) if isinstance(out[k],dict) else copy.deepcopy(v)
    return out


def load_config(path):
    raw=copy.deepcopy(path) if isinstance(path,dict) else json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(raw,dict):raise ValueError('Configuración: se requiere un objeto JSON')
    cfg=merge(DEFAULT,raw)
    from akira_studio import safe_studio
    cfg['studio']=safe_studio(raw)
    # Migrate only the legacy default Ollama endpoint when a complete, local
    # llama.cpp runtime is actually bundled alongside AKIRA.exe. This does not
    # download programs or change an explicitly selected custom endpoint.
    previous_assistant=raw.get('assistant') or {}
    if isinstance(previous_assistant,dict):
        previous_endpoint=str(previous_assistant.get('local_endpoint') or '')
        legacy_default=previous_endpoint in ('http://127.0.0.1:11434/api/chat','http://localhost:11434/api/chat')
        if legacy_default and not bool(previous_assistant.get('legacy_ollama_opt_in',False)) and getattr(sys,'frozen',False):
            app_dir=Path(sys.executable).resolve().parent
            if (app_dir/'local_ai/bin/llama-server.exe').is_file() and (app_dir/'local_ai/models/Qwen3-4B-Q4_K_M.gguf').is_file():
                for key in ('local_endpoint','local_model','local_model_lite','fast_chat_model',
                            'local_runtime_enabled','local_runtime_exe','local_runtime_model',
                            'auto_install_local_ai'):
                    cfg['assistant'][key]=copy.deepcopy(DEFAULT['assistant'][key])
    # This update makes amounts visible. Later explicit privacy choices persist.
    if 'privacy' not in (raw.get('desktop') or {}):cfg['desktop']['privacy']=True
    cfg['desktop']['visibility_preference_saved']=True
    # Legacy defaults were Work Mode aliases, not documented public API IDs.
    # Preserve every other explicitly selected model and every trading limit.
    api_aliases={'gpt-6-luna':'gpt-4.1','gpt-6.1-sol':'gpt-4.1'}
    for section,keys in (('assistant',('model','general_model','trading_model')),
                         ('research',('model',)),('evolution',('analysis_model',))):
        for key in keys:
            if cfg.get(section,{}).get(key) in api_aliases:
                cfg[section][key]=api_aliases[cfg[section][key]]
    if 'symbols' in raw:cfg['symbols']=copy.deepcopy(raw['symbols'])
    if 'symbol_profiles' in raw:
        cfg['symbol_profiles']={s:merge(DEFAULT['symbol_profiles'].get(s,{}),v) for s,v in raw['symbol_profiles'].items() if s in cfg['symbols']}
    if int(raw.get('schema_version',0))<1000:
        # Preserve the effective prior portfolio limit, not an inactive warning.
        t=raw.get('ticket_control',{})
        r=raw.get('risk',{})
        if t.get('enabled',False):
            cfg['risk']['portfolio_capital_pct']=float(t.get('reserved_capital_pct',100.0))
            cfg['risk']['portfolio_money_cap']=0.0
        else:
            cfg['risk']['portfolio_capital_pct']=float(r.get('max_total_pct',DEFAULT['risk']['portfolio_capital_pct']))
            cfg['risk']['portfolio_money_cap']=float(r.get('max_total_money',0.0))
        # The new instruction explicitly enables continuous public context.
        for k in ('enabled','youtube','investing','coinglass','coinglass_public_fallback','local_model','local_ai_summary'):
            cfg['research'][k]=True
    cfg['schema_version']=1600
    from datetime import datetime
    for closure in cfg.get('market_hours',{}).get('closures',[]):
        if closure.get('symbol') not in cfg['symbols']:raise ValueError('Cierre extraordinario para símbolo desconocido')
        try:
            start=datetime.fromisoformat(str(closure['start']).replace('Z','+00:00'));end=datetime.fromisoformat(str(closure['end']).replace('Z','+00:00'))
            if start.tzinfo is None or end.tzinfo is None or end<=start:raise ValueError()
        except (KeyError,TypeError,ValueError):raise ValueError('Horario extraordinario inválido: usa UTC con zona y fin posterior al inicio')
    # Las pendientes permanecen activas junto a la vía runner estructural.
    cfg['pending_policy']['enabled']=True
    cfg['pending']['never_auto_cancel']=False
    # V12.1 no distorsiona una zona para que 0.01 lote quepa en presupuesto.
    # En configuraciones antiguas se migra a QUALITY-FIRST; el usuario puede observar
    # candidatas no ejecutables, pero el motor no comprime riesgo moviendo Entry.
    if int(raw.get('schema_version',0))<1211:
        cfg['execution']['pending_budget_fit_entry']=False
        cfg['execution']['structural_only_pending']=True
        cfg['execution']['require_primary_structural_engine']=True
        cfg['execution']['require_observed_target']=True
        cfg['execution']['minimum_structural_grade']='A'
        cfg['pending']['one_order_per_direction']=True
        cfg['pending']['max_same_side_orders']=1
        cfg['pending']['max_own_map_orders']=2
        # V12.0 ya usaba schema 1210. Al subir a 1211 reforzamos también
        # perfiles guardados para que una instalación anterior no conserve
        # los umbrales más permisivos que produjeron pendientes mediocres.
        for _symbol,_quality,_activation in (('BTCUSDm',85.0,16.0),('XAUUSDm',86.0,18.0)):
            if _symbol in cfg.get('symbol_profiles',{}):
                _profile=cfg['symbol_profiles'][_symbol]
                _profile['pending_structural_quality_min']=max(_quality,float(_profile.get('pending_structural_quality_min',0) or 0))
                _profile['pending_structural_activation_min']=max(_activation,float(_profile.get('pending_structural_activation_min',0) or 0))

    # V12.2 ALWAYS-ON MAP: el modo estricto sigue siendo la primera opción, pero
    # si un lado queda vacío Akira puede usar la mejor tesis HTF segura disponible.
    # Nunca se saltan geometría, SL, margen ni presupuesto real del Gateway.
    if int(raw.get('schema_version',0))<1220:
        cfg['execution']['always_keep_pending_map']=True
        cfg['execution']['pending_budget_fit_entry']=True
        cfg['execution']['presence_allow_projected_target']=True
        cfg['execution']['presence_minimum_structural_grade']='B'
        cfg['execution']['presence_allow_dynamic_structural']=True
        cfg['strategy']['pending_dynamic_structural_fallback']=True
        cfg['pending']['replace_confirm_seconds']=.6
        cfg['pending']['sticky_min_seconds']=2.5
        cfg['pending']['orphan_cancel_seconds']=8.0
        cfg['pending']['replace_score_advantage']=2.0
        cfg.setdefault('assistant',{})['auto_research']=True
        cfg['assistant']['auto_youtube_research']=True

    # V12.3 ATLAS: mantiene un mapa futuro de presencia por símbolo. La prioridad
    # sigue siendo A/A+; cuando falta un lado, se usan únicamente swings H1/H4
    # observados como reserva. Los límites duros de MT5, margen y riesgo no se
    # desactivan. La IA local usa investigación agresiva y varias rondas de tools.
    if int(raw.get('schema_version',0))<1230:
        cfg['execution']['always_keep_pending_map']=True
        cfg['execution']['presence_structural_reserve']=True
        cfg['execution']['presence_allow_projected_target']=True
        cfg['execution']['presence_minimum_structural_grade']='B'
        cfg['pending']['replace_confirm_seconds']=.55
        cfg['pending']['orphan_cancel_seconds']=7.0
        cfg['pending']['replace_score_advantage']=1.5
        cfg['assistant']['auto_research']=True
        cfg['assistant']['auto_youtube_research']=True
        cfg['assistant']['aggressive_research']=True
        cfg['assistant']['research_query_variants']=3
        cfg['assistant']['local_agent_rounds']=7

    # V12.4 REFLEX: el mapa estricto sigue ganando, pero la ausencia de una
    # calificación perfecta ya no deja MT5 vacío. El fallback solo relaja scores;
    # geometría, SL, riesgo, margen, lotaje y order_check siguen siendo duros.
    if int(raw.get('schema_version',0))<1240:
        cfg['execution']['always_keep_pending_map']=True
        cfg['execution']['pending_candidates_per_quadrant']=6
        cfg['strategy']['presence_structural_reserve']=True
        cfg['strategy']['fast_future_map']=True
        cfg['strategy']['fast_map_projected_rr']=1.85
        for _symbol in ('BTCUSDm','XAUUSDm'):
            if _symbol in cfg.get('symbol_profiles',{}):
                cfg['symbol_profiles'][_symbol]['pending_fallback_structural_quality']=0.0
                cfg['symbol_profiles'][_symbol]['pending_fallback_structural_activation']=0.0
        cfg['pending']['replace_confirm_seconds']=.35
        cfg['pending']['orphan_cancel_seconds']=8.0
        cfg['pending']['sticky_min_seconds']=1.5
        cfg['pending']['replace_score_advantage']=1.0
        cfg['execution']['presence_final_context_floor']=18.0
        cfg['assistant']['local_reasoning']=True
        cfg['assistant']['research_query_variants']=4
        cfg['assistant']['research_youtube_results']=8
        cfg['assistant']['local_agent_rounds']=8

    # V12.5 SENTINEL: calidad primero, mapa dual visible y telemetría continua.
    # El motor puede mostrar siempre un escenario BUY y SELL por símbolo, pero
    # nunca eleva silenciosamente el riesgo real para forzar 0.01. Si el usuario
    # desea permitir el mínimo estructural por encima del cap normal debe marcar
    # explícitamente el override en Ajustes.
    if int(raw.get('schema_version',0))<1250:
        cfg['execution']['always_show_dual_scenarios']=True
        cfg['execution']['prefer_one_best_per_direction']=True
        cfg['execution']['risk_blocked_scenario_visible']=True
        cfg['pending']['oco_cancel_opposite_on_fill']=True
        cfg['risk']['min_lot_structural_override_enabled']=False
        cfg['risk']['min_lot_structural_override_max_pct']=8.0
        cfg['risk']['min_lot_structural_override_money_cap']=3.0
        for _symbol in ('BTCUSDm','XAUUSDm'):
            if _symbol in cfg.get('symbol_profiles',{}):
                _p=cfg['symbol_profiles'][_symbol]
                _p['pending_budget_fit_max_shift_source_atr']=0.28 if _symbol.startswith('BTC') else 0.22
                _p['pending_budget_fit_min_risk_ratio']=0.72
                _p['pending_hard_max_rr']=4.4 if _symbol.startswith('BTC') else 4.0
                _p['pending_preferred_max_rr']=3.2
                _p['pending_source_ratio_min_quality']=max(float(_p.get('pending_source_ratio_min_quality',0) or 0),0.58 if _symbol.startswith('BTC') else 0.62)
        cfg['assistant']['persona_mode']='sentinel'
        cfg['assistant']['self_review']=True
        cfg['assistant']['self_review_factual']=True
        cfg['assistant']['refuse_stale_fresh_answer']=True
        cfg['assistant']['minimum_fresh_sources']=2
        cfg['assistant']['proactive_status']=True
        cfg['desktop']['terminal_heartbeat_seconds']=2.0

    # V12.6 HUNTER: ejecución técnica inmediata. H1/H4 siguen siendo la primera
    # opción, pero M15/M30 pueden originar una pendiente si están alineados con
    # contexto superior. M5 solo afina Entry/SL y jamás origina una orden por sí
    # solo. Internet y la IA enriquecen/revisan después; no bloquean el primer mapa.
    if int(raw.get('schema_version',0))<1260:
        cfg['execution']['allow_m15_m30_pending_origin']=True
        cfg['execution']['allow_m5_pending_origin']=False
        cfg['execution']['technical_first_immediate']=True
        cfg['execution']['fill_all_available_directions_same_cycle']=True
        cfg['execution']['presence_final_context_floor']=12.0
        cfg['desktop']['terminal_heartbeat_seconds']=.75
        for _symbol,_q,_a,_fq,_fa,_shift,_ratio in (
                ('BTCUSDm',84.0,14.0,70.0,18.0,.36,.62),
                ('XAUUSDm',85.0,16.0,72.0,18.0,.32,.62)):
            if _symbol in cfg.get('symbol_profiles',{}):
                _p=cfg['symbol_profiles'][_symbol]
                _p['pending_structural_quality_min']=_q
                _p['pending_structural_activation_min']=_a
                _p['pending_fallback_structural_quality']=_fq
                _p['pending_fallback_structural_activation']=_fa
                _p['pending_fallback_tactical_quality']=_fq
                _p['pending_fallback_tactical_activation']=_fa
                _p['pending_tactical_activation_min']=30.0
                _p['pending_budget_fit_max_shift_source_atr']=_shift
                _p['pending_budget_fit_min_risk_ratio']=_ratio
                _p['pending_reversal_stop_quality_min']=48.0 if _symbol.startswith('BTC') else 49.0
                _p['pending_reversal_stop_activation_min']=20.0
                _p['pending_reversal_break_confirmation_bonus']=7.0

    # V12.7 SNAPMAP: el mapa rápido no es un simple fallback. Todas las
    # alternativas estructurales/tácticas ya validadas compiten en la misma vuelta,
    # de modo que una candidata estricta bloqueada por riesgo no impida probar la
    # siguiente LIMIT/STOP ejecutable. Se permiten dos rutas del mismo lado
    # (retroceso + ruptura) dentro del presupuesto conjunto; al activarse una
    # posición propia se retiran las pendientes hermanas y se suspende un mapa
    # nuevo para ese símbolo hasta que la posición cierre.
    if int(raw.get('schema_version',0))<1270:
        cfg['execution']['presence_all_alternatives']=True
        cfg['execution']['technical_first_immediate']=True
        cfg['execution']['fill_all_available_directions_same_cycle']=True
        cfg['execution']['suspend_new_map_while_position_open']=True
        cfg['execution']['rapid_parameter_map']=True
        cfg['execution']['rapid_parameter_map_refresh_seconds']=.12
        cfg['execution']['presence_final_context_floor']=10.0
        cfg['pending']['one_order_per_direction']=True
        cfg['pending']['max_same_side_orders']=1
        cfg['pending']['max_own_map_orders']=2
        cfg['pending']['oco_cancel_opposite_on_fill']=True
        cfg['desktop']['terminal_heartbeat_seconds']=.5
        cfg['research']['pending_score_weight']=10.0
        cfg['research']['pending_activation_weight']=12.0


    # V12.8 FLASHMAP: parámetros primero. M15/H1 se cargan para BTC y XAU antes
    # de H4/D1, el mapa visible expone LIMIT/STOP de ambos lados y el motor no
    # congela la preparación de nuevas pendientes solo porque una posición propia
    # esté abierta. Riesgo, margen y lote mínimo siguen siendo puertas duras.
    if int(raw.get('schema_version',0))<1280:
        cfg['execution']['rapid_parameter_map']=True
        cfg['execution']['rapid_parameter_map_refresh_seconds']=.05
        cfg['execution']['suspend_new_map_while_position_open']=False
        cfg['execution']['instant_four_quadrant_book']=True
        cfg['execution']['fast_warmup_m15_h1_first']=True
        cfg['pending']['replace_confirm_seconds']=.20
        cfg['pending']['sticky_min_seconds']=.75
        cfg['pending']['orphan_cancel_seconds']=8.0
        cfg['desktop']['terminal_heartbeat_seconds']=.30
        cfg['strategy']['snap_projected_rr']=2.05
        for _symbol in ('BTCUSDm','XAUUSDm'):
            if _symbol in cfg.get('symbol_profiles',{}):
                _p=cfg['symbol_profiles'][_symbol]
                _p['pending_snap_quality_min']=66.0 if _symbol.startswith('BTC') else 68.0
                _p['pending_snap_activation_min']=14.0
        # Nunca activar a escondidas el override de lote mínimo.
        cfg['risk']['min_lot_structural_override_enabled']=bool(cfg['risk'].get('min_lot_structural_override_enabled',False))

    # V12.9 ORACLE: dos etapas. El mapa técnico inmediato sigue sin esperar red/LLM;
    # una revisión profunda local (con verificador cuando el equipo lo permite)
    # vuelve a rankear tipos de escenario en ~1–2 min. Nuevas fuentes provocan
    # recálculo aunque el sesgo fusionado redondee al mismo valor.
    if int(raw.get('schema_version',0))<1290:
        cfg['research']['pending_score_weight']=12.0
        cfg['research']['local_ai_summary_seconds']=60.0
        cfg['research']['local_ai_double_check']=True
        cfg['research']['local_ai_reasoning']=True
        cfg['research']['deep_review_target_seconds']=90.0
        cfg['research']['technical_search_seconds']=20.0
        cfg['research']['youtube_discovery_seconds']=25.0
        cfg['research']['model_refresh_seconds']=30.0
        cfg['research']['youtube_videos_per_symbol']=5
        cfg['assistant']['show_research_trace']=True
        cfg['assistant']['local_agent_rounds']=8
        cfg['assistant']['self_review']=True
        cfg['assistant']['self_review_factual']=True
        cfg['desktop']['notifications']=True
        cfg['desktop']['notify_deep_analysis']=True
        cfg['desktop']['notify_pending_change']=True
        cfg['desktop']['notify_chat_research_progress']=True
        cfg['desktop']['toast_seconds']=6.0
        cfg.setdefault('final_architecture',{})['human_scenario_ranker']=True
        cfg['final_architecture']['deep_review_scenario_bonus']=5.0
        cfg['final_architecture']['deep_review_scenario_penalty']=6.5


    # V13.0 ASTRA: interfaz humana + chat con trazas visibles y mapa técnico fugaz.
    # Los ajustes se aplican en vivo porque Desktop muta el mismo diccionario de
    # configuración que usan Engine/Gateway/ContextWorker. El override de lote
    # mínimo sigue APAGADO por defecto; solo ampliamos el rango configurable para
    # que el interruptor realmente pueda cubrir XAU en cuentas pequeñas si la
    # usuaria decide aceptar explícitamente ese riesgo.
    if int(raw.get('schema_version',0))<1300:
        cfg['desktop']['friendly_ui']=True
        cfg['desktop']['chat_research_animation']=True
        cfg['desktop']['chat_elapsed_timer']=True
        cfg['desktop']['chat_stop_button']=True
        cfg['desktop']['terminal_heartbeat_seconds']=.4
        cfg['assistant']['show_research_trace']=True
        cfg['assistant']['friendly_followup_question']=True
        cfg['assistant']['auto_research']=True
        cfg['assistant']['auto_youtube_research']=True
        cfg['assistant']['local_agent_rounds']=8
        cfg['assistant']['self_review']=True
        cfg['assistant']['self_review_factual']=True
        cfg['execution']['rapid_parameter_map']=True
        cfg['execution']['rapid_parameter_map_refresh_seconds']=.05
        cfg['execution']['fill_all_available_directions_same_cycle']=True
        cfg['execution']['always_keep_pending_map']=True
        cfg['execution']['instant_four_quadrant_book']=True
        cfg['execution']['presence_all_alternatives']=True
        cfg['execution']['prefer_one_best_per_direction']=True
        cfg['risk']['min_lot_structural_override_max_pct']=float(cfg['risk'].get('min_lot_structural_override_max_pct',8.0) or 8.0)
        cfg['risk']['min_lot_structural_override_money_cap']=float(cfg['risk'].get('min_lot_structural_override_money_cap',3.0) or 3.0)

    # V15 habilita exclusivamente el motor de zonas M5 observadas; conserva
    # límites de dinero, modo de cuenta y autorizaciones del usuario.
    if int(raw.get('schema_version',0))<1500:
        cfg['execution']['allow_m5_pending_origin']=True
        cfg['strategy']['intraday_structural_map']=True

    cfg['assistant']['friendly_followup_question']=False

    if int(raw.get('schema_version',0))<1360 and float(cfg['runner']['max_signal_age_seconds'])==300.0:
        cfg['runner']['max_signal_age_seconds']=900.0

    # Revisa quotes en décimas de segundo; nunca espera a un modelo ni a internet.
    requested=float(cfg.get('poll_seconds',.10))
    if int(raw.get('schema_version',0))<1200 and requested>.25:requested=.10
    cfg['poll_seconds']=min(.35,max(.15,requested))
    if int(raw.get('schema_version',0))<1360:
        cfg['poll_seconds']=min(.20,cfg['poll_seconds'])
        cfg['execution']['rapid_parameter_map_refresh_seconds']=min(.20,float(cfg['execution']['rapid_parameter_map_refresh_seconds']))
    cfg['execution']['rapid_parameter_map_refresh_seconds']=max(.15,float(cfg['execution'].get('rapid_parameter_map_refresh_seconds',.20)))
    def finite(value,name):
        if isinstance(value,dict):
            for k,v in value.items():finite(v,name+'.'+k)
        elif isinstance(value,(int,float)) and not isinstance(value,bool):
            if not math.isfinite(value) or value<0:raise ValueError(name+' debe ser número finito no negativo')
    finite({k:v for k,v in cfg.items() if k!='studio'},'config')
    attempts=cfg['execution']['pending_attempts_per_cycle']
    if type(attempts) is not int or not 1<=attempts<=16:raise ValueError('Intentos por ciclo deben ser entero entre 1 y 16')
    if cfg['execution']['pending_rejection_retry_seconds']<1:raise ValueError('Reintento de pendiente rechazada debe esperar al menos 1 segundo')
    if cfg['mode'] not in ('trade','observe'):raise ValueError('mode debe ser trade u observe')
    if cfg['lot']<=0 or cfg['lot']>cfg['sizing']['max_lot']:raise ValueError('Lote base debe ser positivo y no superar el máximo de dimensionado')
    if not 0 < cfg['sizing']['risk_utilization'] <= 1:raise ValueError('Uso del presupuesto debe estar entre 0 y 1')
    for key in ('boost_score','boost_quality'):
        if not 0<=cfg['sizing'][key]<=100:raise ValueError('Umbral de escalado '+key+' debe estar entre 0 y 100')
    if type(cfg['sizing']['scale_pending']) is not bool:raise ValueError('Escalado de pendientes debe ser booleano')
    if type(cfg['assistant'].get('local_runtime_enabled')) is not bool:raise ValueError('IA local gestionada debe ser booleana')
    if not 0<=int(cfg['assistant'].get('local_runtime_idle_seconds',30))<=900:raise ValueError('Tiempo de liberación de IA debe ser 0–900 s')
    if type(cfg['pending'].get('auto_replace_valid_pending')) is not bool:raise ValueError('Sustitución automática de pendientes debe ser booleano')
    if not 1<=cfg['runner']['m5_signal_max_age_seconds']<=600:raise ValueError('Ventana del retest M5 debe ser 1–600 segundos')
    if not .4<=cfg['runner']['m5_min_body_fraction']<=1:raise ValueError('Cuerpo mínimo M5 debe estar entre 0.4 y 1')
    if not 5<=cfg['assistant']['fast_chat_timeout_seconds']<=120:raise ValueError('Tiempo del chat rápido debe ser 5–120 segundos')
    if not 256<=cfg['assistant']['fast_chat_max_tokens']<=4096:raise ValueError('Longitud del chat rápido debe ser 256–4096 tokens')
    if cfg['runner']['max_signal_age_seconds']<=0 or cfg['runner']['entry_cooldown_seconds']<=0:raise ValueError('Ventanas runner deben ser positivas')
    if cfg['runner']['min_stop_atr']<=0 or cfg['runner']['max_stop_atr']<cfg['runner']['min_stop_atr']:raise ValueError('Distancia estructural runner inválida')
    if cfg['runner']['min_rr']<1:raise ValueError('R:R runner debe ser >=1')
    if not cfg['symbols'] or not any(cfg['symbols'].values()):raise ValueError('Activa BTC y/o XAU')
    for s,on in cfg['symbols'].items():
        if not isinstance(s,str) or not s.upper().startswith(('BTC','XAU')) or type(on) is not bool:raise ValueError('Solo símbolos BTC/XAU de MT5 y true/false')
    if int(cfg['expected_login'])!=cfg['expected_login']:raise ValueError('expected_login debe ser entero')
    for k in ('max_trade_money','max_trade_pct','minimum_margin_level_pct'):
        if cfg['risk'][k]<=0:raise ValueError('risk.'+k+' debe ser positivo')
    if cfg['risk'].get('min_lot_structural_override_enabled',False):
        if not 0 < float(cfg['risk'].get('min_lot_structural_override_max_pct',0)) <= 40:
            raise ValueError('El override de lote mínimo debe estar entre 0 y 40%')
        if float(cfg['risk'].get('min_lot_structural_override_money_cap',0))<=0:
            raise ValueError('El cap USD del override de lote mínimo debe ser positivo')
    if not 0<cfg['risk']['portfolio_capital_pct']<=100:raise ValueError('portfolio_capital_pct debe estar entre 0 y 100')
    for k in ('max_own_map_orders','max_same_side_orders','replace_min_ticks'):
        v=cfg['pending'][k]
        if v<1 or int(v)!=v:raise ValueError('pending.'+k+' debe ser entero positivo')
    if cfg['pending']['replace_min_ticks']<2:raise ValueError('Se necesitan al menos dos ticks distintos para retirar/sustituir')
    if cfg['management']['trail_at_r']<cfg['management']['breakeven_at_r']:raise ValueError('El trailing debe empezar después del breakeven')
    if cfg['strategy']['pending_hard_min_rr']<1:raise ValueError('R:R duro debe ser >=1')
    if cfg['strategy']['max_tick_age_seconds']<=0:raise ValueError('La edad máxima de tick debe ser positiva')
    for k in ('news_refresh_seconds','coinglass_refresh_seconds','youtube_discovery_seconds','model_refresh_seconds'):
        if cfg['research'][k]<5:raise ValueError('Intervalo de fuente inválido: '+k)
    from akira_studio import validate_studio,safe_studio
    cfg['studio']=validate_studio(safe_studio(cfg))
    return cfg


def save_config(cfg,path):
    cfg=load_config(cfg);path=Path(path);temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temp.replace(path)
    return cfg
