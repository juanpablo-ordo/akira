"""Decisiones rápidas, señales cerradas, fuente de niveles y confirmación real."""
import copy
from collections import Counter
from dataclasses import replace
import json
import threading
import unittest
from unittest.mock import patch

from assistant_akira import AkiraAssistant
from akira_local_ai import agent,choose_text_model
from decision_brain import fast_command,trade_result_text,stars
from engine import Engine
from execution import Blocked,DEAL,PENDING,REMOVE
from runner import runner_plan,runner_exit
from settings import DEFAULT,load_config
from strategy import Bar,build_intraday_structural_pendings
from tests.fixtures import PendingCase


class Jarvis150Tests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.cfg['execution']['pending_only']=False;self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)

    def signal_frames(self,side=1):
        self.e.warmup();f=self.e.planner.caches['BTCUSDm'].frames['M15']
        end=int(self.clock()//900)*900-900
        bars=tuple(Bar(end-(13-i)*900,100,105,97,101,100) for i in range(14))
        m15=replace(f,name='M15',bars=bars,atr=5,slow=99.5,fast=101,trend=.8,rsi=60,
                    highs=(),lows=(),volume_ratio=1.6)
        end5=int(self.clock()//300)*300-300
        five=[Bar(end5-(13-i)*300,103,104,102.5,103.5,100) for i in range(14)]
        five[-4:-1]=[Bar(five[-4].time,102,103,100.7,101.6,100),
                      Bar(five[-3].time,101.6,102.1,100.8,101.5,100),
                      Bar(five[-2].time,101.5,102,101,101.7,100)]
        five[-1]=Bar(end5,101.7,103.7,101.5,103.5,160)
        m5=replace(m15,name='M5',bars=tuple(five),atr=2,slow=101,fast=102,volume_ratio=1.6)
        h1=replace(m15,name='H1',bars=tuple(replace(b,time=int(self.clock()//3600)*3600-3600-(13-i)*3600) for i,b in enumerate(m15.bars)))
        frames={'M5':m5,'M15':m15,'H1':h1}
        if side==-1:
            for tf,frame in list(frames.items()):
                transformed=tuple(Bar(b.time,200-b.open,200-b.low,200-b.high,200-b.close,b.volume) for b in frame.bars)
                frames[tf]=replace(frame,bars=transformed,slow=200-frame.slow,fast=200-frame.fast,trend=-.8,rsi=40)
        return frames

    def zone_frames(self,side=1):
        frames=self.signal_frames(1);m5=frames['M5'];end=m5.bars[-1].time
        bars=[Bar(end-(13-i)*300,101,101.1,100.9,101,100) for i in range(14)]
        bars[7]=Bar(bars[7].time,100.2,100.3,98,100,100)
        m5=replace(m5,bars=tuple(bars),atr=2,lows=((98,bars[7].time),),highs=((104,bars[3].time),))
        frames['M5']=m5
        frames['M1']=replace(m5,name='M1',atr=.2,lows=(),highs=())
        frames['M15']=replace(frames['M15'],lows=(),highs=())
        frames['H1']=replace(frames['H1'],lows=(),highs=())
        if side==-1:
            for tf,frame in list(frames.items()):
                bars=tuple(Bar(b.time,200-b.open,200-b.low,200-b.high,200-b.close,b.volume) for b in frame.bars)
                frames[tf]=replace(frame,bars=bars,slow=200-frame.slow,fast=200-frame.fast,trend=-.8,rsi=40,
                    highs=tuple((200-v,t) for v,t in frame.lows),lows=tuple((200-v,t) for v,t in frame.highs))
        return frames

    def install_frames(self,frames,close=103.5):
        for symbol,scale,base,spread in (('BTCUSDm',10,60000,1),('XAUUSDm',.2,2500,.02)):
            def price(v):return base+(v-100)*scale
            cache=self.e.planner.caches[symbol]
            for tf,f in frames.items():
                bars=tuple(Bar(b.time,price(b.open),price(b.high),price(b.low),price(b.close),b.volume) for b in f.bars)
                cache.frames[tf]=replace(f,bars=bars,atr=f.atr*scale,slow=price(f.slow),fast=price(f.fast),
                    highs=tuple((price(v),t) for v,t in f.highs),lows=tuple((price(v),t) for v,t in f.lows))
            for tf in cache.PERIODS:cache.due[tf]=self.clock()+60
            self.api.set_quote(symbol,price(close),spread=spread,fill=False)

    def test_star_followup_is_read_only_and_recovers_gold_topic(self):
        cmd=fast_command('Dámelas con estrellas como antes','Pon las mejores pendientes de oro')
        self.assertEqual(cmd,{'action':'assistant_analyze_pending','symbol':'XAUUSDm'})

    def test_runner_followup_does_not_replay_market_request(self):
        self.assertEqual(fast_command('Dámelos con estrellas','Abre runners BTC')['action'],'assistant_analyze_runner')

    def test_symbol_followup_updates_gold_parameters_without_replaying(self):
        self.assertEqual(fast_command('Y en oro','Pon pendientes BTC'),{'action':'assistant_analyze_pending','symbol':'XAUUSDm'})

    def test_named_short_does_not_open_long_or_retire_own_pending(self):
        self.install_frames(self.signal_frames());self.api.add_pending(self.plan())
        command=fast_command('Abre shorts de BTC');self.assertEqual(command['runner_side'],'SELL')
        result=self.e.handle_command(command)
        self.assertFalse(self.api.sent);self.assertEqual(len(self.api.orders),1)
        self.assertIn('SHORT',result['results'][0]['detail']);self.assertFalse(result['results'][0]['runner']['plan'])

    def test_source_horizon_noise_rejects_an_unsafe_m5_zone(self):
        frames=self.zone_frames();f=frames['M5']
        frames['M5']=replace(f,bars=tuple(replace(b,low=min(b.low,b.open-2)) for b in f.bars))
        self.assertFalse(build_intraday_structural_pendings(frames,self.cfg['strategy'],Counter()))

    def test_explicit_combined_request_uses_engine_trade_policy(self):
        self.assertEqual(fast_command('Mete pendientes y runners BTC y oro',pending_execution=True),
            {'action':'assistant_best_trade','symbol':'ALL'})

    def test_normal_long_and_short_commands_route_to_runners(self):
        for message in ('Abre longs de BTC','Mete shorts de oro','Coloca órdenes normales BTC'):
            self.assertEqual(fast_command(message)['action'],'assistant_best_runner')

    def test_negated_market_commands_are_read_only(self):
        for message in ('No abras runners de oro','No quiero que metas runners BTC','Solo parámetros de shorts de oro',
                        'Analiza runners sin enviar','No me pongas runners BTC'):
            self.assertEqual(fast_command(message)['action'],'assistant_analyze_runner',message)

    def test_star_followup_without_trading_context_uses_conversation(self):
        self.assertIsNone(fast_command('Pon estrellas a esto','Mejores hoteles'))

    def test_exact_levels_are_not_replaced_by_generated_map(self):
        self.assertIsNone(fast_command('Pon pendiente oro BUY LIMIT Entry 2490 SL 2480 TP 2520',pending_execution=True))

    def test_explicit_pending_stars_can_place_but_format_alone_cannot(self):
        self.assertEqual(fast_command('Pon pendientes de oro con estrellas',pending_execution=True)['action'],'assistant_best_pending')
        self.assertEqual(fast_command('Con estrellas','Pon pendientes de oro')['action'],'assistant_analyze_pending')

    def test_gold_star_followup_uses_actor_without_network_or_model(self):
        bot=AkiraAssistant(self.cfg,self.root,trade_callback=self.e.handle_command)
        bot.remember_execution('Pon pendientes de oro','Resultado de oro',{})
        with patch('assistant_akira.ollama_agent',side_effect=AssertionError('No usar modelo')),patch.object(bot,'_source_tool',side_effect=AssertionError('No usar red')):
            answer=bot.reply('Dámelas con estrellas',{},use_cloud=False)
        self.assertIn('XAUUSDm',answer);self.assertNotIn('BTCUSDm',answer)
        self.assertIn('Entry=',answer);self.assertFalse(self.api.sent)

    def test_direct_fast_request_can_execute_while_general_model_is_busy(self):
        bot=AkiraAssistant(self.cfg,self.root,trade_callback=self.e.handle_command)
        entered=threading.Event();release=threading.Event();answers=[]
        def slow(*args,**kwargs):entered.set();release.wait(3);return 'Código de una calculadora'
        with patch('assistant_akira.ollama_status',return_value={'models':['qwen3:8b']}),patch('assistant_akira.ollama_agent',side_effect=slow):
            general=threading.Thread(target=lambda:bot.reply('¿Cómo hago una calculadora en Python?',{},use_cloud=False),daemon=True)
            general.start();self.assertTrue(entered.wait(1))
            command=threading.Thread(target=lambda:answers.append(bot.reply('Pon pendientes BTC y oro',{},use_cloud=False)),daemon=True)
            try:
                command.start();command.join(1)
                self.assertFalse(command.is_alive());self.assertEqual(len(self.api.orders),4)
                self.assertFalse(release.is_set());self.assertTrue(answers)
            finally:release.set();general.join(2);command.join(2)

    def test_organizing_ideas_does_not_route_to_pending_orders(self):
        self.assertIsNone(fast_command('Ordena mis ideas para mañana'))

    def test_fast_pending_placement_returns_actual_tickets_and_stars(self):
        bot=AkiraAssistant(self.cfg,self.root,trade_callback=self.e.handle_command)
        with patch('assistant_akira.ollama_status',side_effect=AssertionError('No usar Ollama')):
            answer=bot.reply('Pon las mejores pendientes BTC y oro con estrellas',{},use_cloud=False)
        self.assertEqual(len(self.api.orders),4);self.assertIn('⭐',answer)
        for order in self.api.orders:self.assertIn('#'+str(order.ticket),answer)

    def test_stars_do_not_fabricate_grade_for_unvalidated_plan(self):
        self.assertEqual(stars({'quality_score':None,'score':98}),'sin calificación validada')
        text=trade_result_text({'results':[{'symbol':'XAUUSDm','scenarios':[{'side':1,'kind':'LIMIT','entry':2500,'sl':2490,'tp':2520,'quality_score':None}]}]})
        self.assertIn('sin calificación validada',text);self.assertNotIn('⭐⭐⭐⭐⭐',text)

    def test_format_prioritizes_sendable_plan_over_blocked_high_score(self):
        scenarios=[{'side':1,'kind':'LIMIT','entry':10,'sl':9,'tp':12,'quality_score':99,'sendable':False},
                   {'side':1,'kind':'STOP','entry':11,'sl':10,'tp':13,'quality_score':90,'sendable':True}]
        text=trade_result_text({'results':[{'symbol':'BTCUSDm','scenarios':scenarios}]})
        self.assertIn('BUY STOP',text);self.assertNotIn('BUY LIMIT',text)

    def test_risk_blocked_gold_keeps_parameters_and_money_diagnostic(self):
        self.cfg['risk']['max_trade_money']=.01
        text=trade_result_text(self.e.handle_command({'action':'assistant_best_pending','symbol':'XAUUSDm'}))
        self.assertIn('Entry=',text);self.assertIn('límite $0.01',text);self.assertFalse(self.api.sent)

    def test_m5_confirmed_long_and_short_keep_m15_invalidation(self):
        for side,bid in ((1,103.5),(-1,96.5)):
            self.api.set_quote('BTCUSDm',bid,spread=.1,fill=False)
            plan,reason=runner_plan('BTCUSDm',self.signal_frames(side),self.g.quote('BTCUSDm'),self.cfg)
            self.assertIsNotNone(plan,reason);self.assertEqual(plan.signal_timeframe,'M5')
            self.assertEqual(plan.atr,5);self.assertEqual(plan.signal_atr,2)
            self.assertGreaterEqual(abs(plan.entry-plan.sl),5*self.cfg['runner']['min_stop_atr'])

    def test_m5_open_candle_does_not_enter(self):
        frames=self.signal_frames();f=frames['M5']
        frames['M5']=replace(f,bars=f.bars[:-1]+(replace(f.bars[-1],time=int(self.clock())),))
        self.assertIsNone(runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)[0])

    def test_m5_stale_candle_does_not_enter(self):
        frames=self.signal_frames();f=frames['M5']
        frames['M5']=replace(f,bars=tuple(replace(b,time=b.time-1200) for b in f.bars))
        self.assertIsNone(runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)[0])

    def test_m5_requires_actual_pullback(self):
        frames=self.signal_frames();f=frames['M5'];bars=list(f.bars)
        for i in (-4,-3,-2):bars[i]=replace(bars[i],low=102.3,open=102.5,close=102.7,high=102.9)
        frames['M5']=replace(f,bars=tuple(bars))
        self.assertIsNone(runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)[0])

    def test_m5_h1_contradiction_does_not_enter(self):
        frames=self.signal_frames();frames['H1']=replace(frames['H1'],trend=-.8)
        self.assertIsNone(runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)[0])

    def test_gateway_rechecks_m5_age_and_signal_drift(self):
        self.api.set_quote('BTCUSDm',103.5,spread=.1,fill=False)
        plan,reason=runner_plan('BTCUSDm',self.signal_frames(),self.g.quote('BTCUSDm'),self.cfg)
        self.assertIsNotNone(plan,reason)
        with self.assertRaisesRegex(Blocked,'caducada'):self.g.send_runner(replace(plan,bar_time=plan.bar_time-900))
        self.api.set_quote('BTCUSDm',plan.entry+1.5,spread=.1,fill=False)
        with self.assertRaisesRegex(Blocked,'ventana'):self.g.send_runner(plan)
        self.assertFalse(self.api.sent)

    def test_new_m5_entry_is_not_closed_by_an_older_m15_bar(self):
        frames=self.signal_frames();m=frames['M15'];last=m.bars[-1]
        frames['M15']=replace(m,bars=m.bars[:-1]+(replace(last,low=80,close=81),))
        plan={'bar_time':frames['M5'].bars[-1].time,'signal_timeframe':'M5'}
        self.assertEqual(runner_exit(plan,frames,1,.9,self.cfg),'')
        frames['M15']=replace(frames['M15'],bars=frames['M15'].bars[:-1]+(replace(frames['M15'].bars[-1],time=last.time+900),))
        self.assertIn('estructura',runner_exit(plan,frames,1,.9,self.cfg))

    def test_auto_cycle_uses_m5_runner_for_btc_and_gold(self):
        self.install_frames(self.signal_frames())
        view=self.e.step()
        self.assertEqual({r['symbol'] for r in self.api.sent if r['action']==DEAL},{'BTCUSDm','XAUUSDm'})
        self.assertTrue(all(row['runner']['plan']['signal_timeframe']=='M5' for row in view['symbols'].values()))

    def test_runner_button_confirms_positions_without_pending_labels(self):
        self.install_frames(self.signal_frames())
        result=self.e.handle_command({'action':'assistant_best_runner','symbol':'ALL'})
        self.assertTrue(result['ok']);self.assertEqual(len(self.api.positions),2)
        self.assertTrue(all(r['positions'] and not r['levels'] for r in result['results']))
        text=trade_result_text(result);self.assertIn('LONG',text);self.assertNotIn('BUY LIMIT',text)
        for position in self.api.positions:self.assertIn('#'+str(position.ticket),text)

    def test_runner_analysis_leaves_existing_pending_untouched(self):
        self.install_frames(self.signal_frames());self.api.add_pending(self.plan())
        result=self.e.handle_command({'action':'assistant_analyze_runner','symbol':'ALL'})
        self.assertTrue(all(r['runner']['plan'] for r in result['results']))
        self.assertFalse(self.api.sent);self.assertEqual(len(self.api.orders),1)

    def test_runner_button_respects_pause_and_observation(self):
        self.install_frames(self.signal_frames());self.e.paused=True
        result=self.e.handle_command({'action':'assistant_best_runner','symbol':'ALL'})
        self.assertTrue(all(r['runner']['plan'] for r in result['results']));self.assertFalse(self.api.sent)
        self.e.paused=False;self.cfg['mode']='observe'
        self.e.handle_command({'action':'assistant_best_runner','symbol':'ALL'});self.assertFalse(self.api.sent)

    def test_runner_button_fill_during_cancel_does_not_double_entry(self):
        self.cfg['runner']['preserve_pending_orders']=False  # explicit replacement policy for the race fixture
        self.install_frames(self.signal_frames());self.api.add_pending(self.plan());self.api.fill_on_cancel=True
        self.e.handle_command({'action':'assistant_best_runner','symbol':'BTCUSDm'})
        self.assertFalse(any(r['action']==DEAL for r in self.api.sent));self.assertEqual(len(self.api.positions),1)

    def test_intraday_parameters_come_from_observed_gold_and_btc_zone(self):
        for side in (1,-1):
            frames=self.zone_frames(side)
            plans=build_intraday_structural_pendings(frames,self.cfg['strategy'],Counter())
            self.assertEqual(len(plans),1)
            plan=plans[0];self.assertEqual(plan.side,side)
            self.assertEqual(plan.timeframe,'M5');self.assertIn('SWING:INTRADAY:',plan.key)
            self.assertAlmostEqual(plan.level,99 if side==1 else 101)
            self.assertLess(plan.stop,98) if side==1 else self.assertGreater(plan.stop,102)
            self.assertIn('primer objetivo observado',plan.reason)

    def test_intraday_plan_requires_m15_h1_confirmation(self):
        frames=self.zone_frames();frames['H1']=replace(frames['H1'],trend=-.8)
        self.assertFalse(build_intraday_structural_pendings(frames,self.cfg['strategy'],Counter()))

    def test_intraday_retested_or_broken_zone_is_discarded(self):
        frames=self.zone_frames();m=frames['M5'];bars=list(m.bars);bars[-1]=replace(bars[-1],low=96,close=97,open=98,high=98.1)
        frames['M5']=replace(m,bars=tuple(bars))
        self.assertFalse(build_intraday_structural_pendings(frames,self.cfg['strategy'],Counter()))

    def test_intraday_missing_or_nearby_target_cannot_project_profit(self):
        frames=self.zone_frames();f=frames['M5']
        frames['M5']=replace(f,highs=())
        self.assertFalse(build_intraday_structural_pendings(frames,self.cfg['strategy'],Counter()))
        frames['M5']=replace(f,highs=((100,f.bars[-3].time),))
        self.assertFalse(build_intraday_structural_pendings(frames,self.cfg['strategy'],Counter()))

    def test_intraday_fake_swing_not_in_bars_is_discarded(self):
        frames=self.zone_frames();f=frames['M5'];frames['M5']=replace(f,lows=((97,f.lows[0][1]),))
        self.assertFalse(build_intraday_structural_pendings(frames,self.cfg['strategy'],Counter()))

    def test_production_planner_accepts_observed_m5_without_generic_ema_bypass(self):
        frames=self.zone_frames();self.install_frames(frames,close=101)
        self.cfg['execution'].update(require_primary_structural_engine=True,require_observed_target=True,minimum_structural_grade='A')
        for symbol,cache in self.e.planner.caches.items():
            setups=build_intraday_structural_pendings(cache.frames,self.cfg['strategy'],Counter())
            q=self.g.quote(symbol)
            rows=self.e.planner.proposed_pending_plans(symbol,setups,q,all_candidates=True,financial_gate=False)
            self.assertTrue(rows,self.e.planner.pending_filter_reasons.get(symbol))
            generic=replace(setups[0],key='MAP:EMA:1:M5:fake')
            self.assertFalse(self.e.planner.proposed_pending_plans(symbol,[generic],q,all_candidates=True,financial_gate=False))

    def test_observed_intraday_gold_and_btc_plans_reach_broker_with_same_sl(self):
        self.install_frames(self.zone_frames(),close=101)
        self.cfg['execution'].update(require_primary_structural_engine=True,require_observed_target=True,minimum_structural_grade='A')
        for symbol,cache in self.e.planner.caches.items():
            setups=build_intraday_structural_pendings(cache.frames,self.cfg['strategy'],Counter())
            q=self.g.quote(symbol)
            plans=self.e.planner.proposed_pending_plans(symbol,setups,q,all_candidates=True,financial_gate=True)
            self.assertTrue(plans,self.e.planner.pending_filter_reasons.get(symbol))
            self.e.candidates[symbol]=plans
            result=self.e.execute_pending_map(symbol,plans,q)
            self.assertTrue(result['accepted'],result)
            request=next(r for r in self.api.sent if r['symbol']==symbol and r['action']==PENDING)
            self.assertAlmostEqual(request['sl'],round(plans[0].sl,2),places=2)
            self.assertLessEqual(self.g.plan_money(plans[0],request['volume'])[0],self.g.trade_cap(self.g.snapshot()))
        self.assertEqual(len(self.api.orders),2)

    def test_migration_preserves_money_and_user_operating_mode(self):
        old=copy.deepcopy(DEFAULT);old['schema_version']=1400;old['mode']='observe';old['risk']['max_trade_money']=2.17
        old['runner']['enabled']=False
        cfg=load_config(old)
        self.assertEqual(cfg['risk']['max_trade_money'],2.17);self.assertEqual(cfg['mode'],'observe')
        self.assertFalse(cfg['runner']['enabled']);self.assertTrue(cfg['strategy']['intraday_structural_map'])


class Language150Tests(PendingCase,unittest.TestCase):
    def test_small_conversation_uses_fast_installed_model_and_single_pass(self):
        bot=AkiraAssistant(self.cfg,self.root)
        with patch('assistant_akira.ollama_status',return_value={'models':['qwen3:8b','qwen3:14b']}),patch.object(bot,'_source_tool',side_effect=AssertionError('No investigar conversación')),patch('assistant_akira.ollama_agent',return_value='Podemos organizarlo así.') as call:
            answer=bot.reply('Ayúdame a organizar mis ideas para mañana',{},use_cloud=False)
        self.assertIn('Podemos',answer);self.assertEqual(call.call_args.kwargs['model'],'qwen3:8b')
        self.assertEqual(call.call_args.kwargs['max_rounds'],1);self.assertFalse(call.call_args.kwargs['reasoning'])
        self.assertFalse(call.call_args.args[1]);self.assertGreater(call.call_args.kwargs['timeout'],119);self.assertLessEqual(call.call_args.kwargs['timeout'],120)

    def test_fast_model_selection_keeps_strong_model_for_research(self):
        models=['qwen3:8b','qwen3:14b']
        self.assertEqual(choose_text_model(models,prefer_fast=True),'qwen3:8b')
        self.assertEqual(choose_text_model(models),'qwen3:14b')
        self.assertEqual(choose_text_model(['qwen3:14b'],prefer_fast=True),'qwen3:14b')

    def test_normal_factual_search_does_not_start_youtube_batch(self):
        bot=AkiraAssistant(self.cfg,self.root);calls=[]
        def source(name,args):
            calls.append(name);return {'results':[{'title':'Dato','url':'https://example.org/dato','text':'Dato encontrado'}]}
        with patch('assistant_akira.ollama_status',return_value={'models':['qwen3:8b']}),patch.object(bot,'_source_tool',side_effect=source),patch('assistant_akira.ollama_agent',return_value='Dato encontrado'):
            bot.reply('Explica la historia de la imprenta',{},use_cloud=False)
        self.assertEqual(calls.count('research_public_web'),2);self.assertNotIn('search_youtube',calls)

    def test_model_deadline_applies_to_whole_tool_loop(self):
        now=[10.0];timeouts=[]
        tools=[{'function':{'name':'research_public_web'}}]
        def fake_chat(*args,**kwargs):
            timeouts.append(kwargs['timeout']);now[0]+=6
            return {'message':{'content':'','tool_calls':[{'function':{'name':'research_public_web','arguments':{}}}]}}
        with patch('akira_local_ai.time.monotonic',side_effect=lambda:now[0]),patch('akira_local_ai.chat',side_effect=fake_chat):
            with self.assertRaises(TimeoutError):agent([],tools,lambda *a:{},timeout=10,max_rounds=4)
        self.assertEqual(timeouts,[10,4])

    def test_model_cannot_execute_tools_not_offered_for_this_request(self):
        calls=[];replies=[{'message':{'tool_calls':[{'function':{'name':'execute_best_pending_map','arguments':{}}}]}},
                          {'message':{'content':'Respuesta'}}]
        with patch('akira_local_ai.chat',side_effect=replies):
            text=agent([],[],lambda *args:calls.append(args),max_rounds=2)
        self.assertEqual(text,'Respuesta');self.assertFalse(calls)

    def test_model_tool_context_is_bounded_and_preserves_user_question(self):
        seen=[];responses=[{'message':{'tool_calls':[{'function':{'name':'read_public_source','arguments':{}}}]}},
                          {'message':{'content':'Respuesta'}}]
        def fake_chat(messages,**kw):seen.append(copy.deepcopy(messages));return responses.pop(0)
        with patch('akira_local_ai.chat',side_effect=fake_chat):
            agent([{'role':'user','content':'Pregunta original'}],[{'function':{'name':'read_public_source'}}],
                  lambda *a:{'body':'x'*100000},max_rounds=2,context_char_budget=1500)
        self.assertLessEqual(sum(len(r.get('content','')) for r in seen[-1]),1500)
        self.assertEqual(seen[-1][0]['content'],'Pregunta original')

    def test_cancellation_remains_active_in_fast_model_path(self):
        cancel=threading.Event();cancel.set()
        with patch('akira_local_ai.chat',side_effect=AssertionError('No iniciar inferencia')):
            with self.assertRaisesRegex(RuntimeError,'detenido'):agent([],[],lambda *a:{},cancel_event=cancel)
