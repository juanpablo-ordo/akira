"""Regression cases derived from small-account failure modes, not fitted prices."""
import copy,json,tempfile,time,unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from capital_guard import history_metrics,status
from execution import Gateway,Journal,Blocked,REMOVE,PENDING,SLTP,OWN_PENDING
from tests.fixtures import PendingCase
from engine import Engine
from settings import DEFAULT,load_config
from risk_limits import configured_limits
from mentor_context import performance,inspect_state,diagnostic_reply
from akira_local_ai import agent,validated_tool_args


def deal(ticket,when,pnl,typ=1):
    return NS(ticket=ticket,time=when,time_msc=int(when*1000),type=typ,profit=pnl,commission=0,swap=0,fee=0)


class CapitalMetricsTests(unittest.TestCase):
    def test_small_account_curve_with_four_gold_stops(self):
        now=1800000000;values=[39,5.49,-8.33,-9.99,-9.70,-8.60,-3.02]
        rows=[deal(i+1,now-1000+i,p,2 if i==0 else 1) for i,p in enumerate(values)]
        m=history_metrics(rows,4.85,4.85,now)
        self.assertAlmostEqual(m['balance_peak'],44.49);self.assertAlmostEqual(m['daily_net'],-34.15)
        self.assertAlmostEqual(m['daily_loss'],34.15)
    def test_deposit_is_not_a_trading_profit_and_withdrawal_is_not_drawdown(self):
        now=1800000000
        m=history_metrics([deal(1,now-400,100,2),deal(2,now-300,10),deal(3,now-200,-50,2)],60,60,now)
        self.assertEqual(m['balance_peak'],60);self.assertEqual(m['daily_net'],10);self.assertEqual(m['daily_loss'],0)
    def test_day_boundary_does_not_change_denominator_after_losing(self):
        now=1800000000;day=now//86400*86400
        m=history_metrics([deal(1,day-1,-20),deal(2,day+1,-5)],75,73,now)
        self.assertEqual(m['day_basis'],80);self.assertEqual(m['daily_loss'],7)
    def test_missing_or_nonfinite_money_cannot_be_a_valid_reference(self):
        with self.assertRaises(ValueError):history_metrics([deal(1,1,float('nan'))],100,100,2)
    def test_limits_scale_without_using_score_or_lot_boost(self):
        c=copy.deepcopy(DEFAULT);c['risk'].update(max_trade_money=1e7,max_trade_pct=100,portfolio_money_cap=1e8,portfolio_capital_pct=100)
        for capital in (4.85,39,500):
            x=configured_limits(c,dict(balance=capital,equity=capital,currency='USD'))
            self.assertAlmostEqual(x['per_trade'],capital*.02);self.assertAlmostEqual(x['portfolio'],capital*.06)
    def test_protection_can_be_explicitly_disabled_without_resetting_custom_limits(self):
        c=copy.deepcopy(DEFAULT);c['capital_protection']['enabled']=False
        x=configured_limits(c,dict(balance=40,equity=40,currency='USD'));self.assertEqual(x['per_trade'],2.4)
    def test_legacy_config_gains_visible_protection_without_erasing_saved_risk(self):
        c=copy.deepcopy(DEFAULT);c.pop('capital_protection');c['risk']['max_trade_pct']=100
        result=load_config(c);self.assertEqual(result['risk']['max_trade_pct'],100);self.assertTrue(result['capital_protection']['enabled'])
    def test_guard_config_validates_boolean_and_percentage(self):
        for bad in ({'enabled':'yes'},{'trade_pct':0},{'max_drawdown_pct':101}):
            c=copy.deepcopy(DEFAULT);c['capital_protection'].update(bad)
            with self.assertRaises(ValueError):load_config(c)


class CapitalExecutionTests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.cfg['capital_protection']['enabled']=True
        self.cfg['risk'].update(max_trade_money=1e7,max_trade_pct=100,portfolio_money_cap=1e8,portfolio_capital_pct=100)
        self.g.snapshot();self.g.refresh_history(force=True)
    def engine(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close);return e
    def test_39_dollars_cannot_admit_an_8_dollar_gold_stop(self):
        self.api.account.balance=self.api.account.equity=39
        p=self.plan('XAUUSDm');p=replace(p,sl=p.entry-8.33,tp=p.entry+18)
        with self.assertRaisesRegex(Blocked,'Lote mínimo'):self.g.send_immediate_plan(p)
        self.assertFalse(self.api.sent);self.assertEqual(p.sl,p.entry-8.33)
    def test_500_account_can_admit_the_same_structural_stop(self):
        self.api.account.balance=self.api.account.equity=500
        p=self.plan('XAUUSDm');p=replace(p,sl=p.entry-8.33,tp=p.entry+18)
        self.assertTrue(self.g.send_immediate_plan(p));self.assertEqual(self.api.sent[-1]['volume'],.01)
    def test_current_risk_is_rechecked_after_prepare_before_send(self):
        p=self.plan();ready=self.g.prepare(p);self.api.account.balance=self.api.account.equity=39
        with self.assertRaises(Blocked):self.g.send(ready)
        self.assertFalse(self.api.sent)
    def test_drawdown_survives_restart(self):
        self.g.capital_status(self.g.snapshot());self.api.account.balance=self.api.account.equity=84
        reopened=Gateway(self.api,self.cfg,Journal(self.root/'state.json'),self.g.log,self.clock)
        reopened.refresh_history(force=True)
        with self.assertRaisesRegex(Blocked,'caída'):reopened.permissions(reopened.snapshot())
    def test_new_deposit_adjusts_persisted_reference_exactly_once(self):
        self.g.capital_status(self.g.snapshot());self.api.deals.append(deal(1,self.clock(),100,2));self.api.account.balance=self.api.account.equity=200
        self.g.refresh_history(force=True)
        a=self.g.capital_status(self.g.snapshot());b=self.g.capital_status(self.g.snapshot())
        self.assertEqual(a['peak'],200);self.assertEqual(b['peak'],200);self.assertTrue(b['allowed'])
    def test_missing_history_blocks_entry_but_not_protection_permission(self):
        self.g.history_time=0;self.api.fail_history=True
        with self.assertRaises(Blocked):self.g.permissions(self.g.snapshot())
        self.g.permissions(self.g.snapshot(),entry=False)
    def test_insufficient_balance_with_existing_pendings_is_reduced(self):
        self.api.account.balance=self.api.account.equity=4.85
        self.api.add_pending(self.plan());manual=self.api.add_pending(self.plan('XAUUSDm'),magic=0)
        self.engine().enforce_capital_protection(self.g.snapshot())
        self.assertEqual(len(self.api.orders),1);self.assertIs(self.api.orders[0],manual);self.assertEqual(self.api.sent[-1]['action'],REMOVE)
    def test_fixed_daily_limit_retires_pending_even_when_guard_disabled(self):
        self.cfg['capital_protection']['enabled']=False;self.cfg['risk']['daily_loss_money']=5
        self.api.deals.append(deal(1,self.clock()-1,-6));self.api.account.balance=self.api.account.equity=94
        self.api.add_pending(self.plan());self.g.refresh_history(force=True)
        self.engine().enforce_capital_protection(self.g.snapshot());self.assertFalse(self.api.orders)
    def test_unconfirmed_cancellation_keeps_intent_and_does_not_open(self):
        self.api.account.balance=self.api.account.equity=4.85;self.api.add_pending(self.plan());self.api.drop_ack=True
        e=self.engine();e.enforce_capital_protection(self.g.snapshot())
        self.assertIn('BTCUSDm',self.g.journal.data['intents']);self.assertTrue(all(r['action']==REMOVE for r in self.api.sent))
    def test_one_position_per_symbol_blocks_a_distinct_new_zone(self):
        self.api.add_position('BTCUSDm',entry=59000,sl=58999,tp=60000,magic=OWN_PENDING)
        with self.assertRaisesRegex(Blocked,'posición'):self.g.send_immediate_plan(self.plan())
        self.assertFalse(self.api.sent)
    def test_two_sides_cannot_bypass_the_symbol_budget(self):
        self.api.add_pending(self.plan())
        p=self.plan(side=-1,kind='STOP',key='SWING:second');p=replace(p,sl=p.entry+250,tp=p.entry-600)
        with self.assertRaises(Blocked):self.g.send_immediate_plan(p)
        self.assertFalse(self.api.sent)
    def test_capital_pause_never_closes_positions_or_widens_stops(self):
        p=self.api.add_position('XAUUSDm',entry=2500,sl=2499,tp=2504,magic=OWN_PENDING)
        self.g.capital_status(self.g.snapshot());self.api.account.equity=80
        self.engine().enforce_capital_protection(self.g.snapshot())
        self.assertEqual((p.sl,p.tp),(2499,2504));self.assertFalse(self.api.sent)
    def test_current_thesis_is_reviewed_without_waiting_for_a_loss(self):
        e=self.engine();e.warmup();self.api.add_pending(self.plan())
        with patch('trade_quality_gate.evaluate',return_value={'allowed':False,'reason':'Nuevo impulso contrario confirmado'}):
            e.review_loss_pendings(self.g.snapshot())
        self.assertFalse(self.api.orders);self.assertEqual(self.api.sent[-1]['action'],REMOVE)
    def test_history_metrics_are_not_resorted_for_each_candidate(self):
        with patch('capital_guard.history_metrics',wraps=history_metrics) as compute:
            for _ in range(20):self.g.capital_status(self.g.snapshot())
            self.assertEqual(compute.call_count,1)
            self.g.refresh_history(force=True);self.g.capital_status(self.g.snapshot())
            self.assertEqual(compute.call_count,2)
    def test_guard_is_visible_in_the_engine_snapshot(self):
        v=self.engine().view();self.assertIn('capital_protection',v);self.assertTrue(v['capital_protection']['enabled'])


class MentorTests(unittest.TestCase):
    def snapshot(self):
        c=dict(position_id=1,state='CONFIRMADO MT5',deal_ids=[1,2],pnl=-8.33,symbol='XAUUSDm',lane='PENDING',exit_time=99)
        return dict(connected=True,as_of_utc=100,account=dict(balance=39,equity=39,currency='USD'),confirmed_strategy_outcomes=[c,c],portfolio_risk=dict(reserved_usd=3))
    def test_counts_unique_broker_closures_and_never_invents_runners(self):
        s=self.snapshot();s['confirmed_strategy_outcomes'].append(dict(position_id=2,pnl=100))
        p=performance(s);self.assertEqual((p['closed'],p['net'],p['ignored']),(1,-8.33,1));self.assertEqual(p['groups'][0]['lane'],'PENDING')
    def test_account_tool_strips_login_secrets_and_other_payloads(self):
        s=self.snapshot();s['account']['login']='secret';s['secret']='password'
        r=inspect_state(s,'account',101);self.assertTrue(r['read_only']);self.assertNotIn('secret',str(r))
    def test_stale_snapshot_and_unknown_sections_fail_closed(self):
        self.assertFalse(inspect_state(self.snapshot(),'account',116)['ok']);self.assertFalse(inspect_state(self.snapshot(),'execute',101)['ok'])
    def test_diagnosis_uses_data_without_llm_or_broker_commands(self):
        r=diagnostic_reply('Por que Akira pierde en mi cuenta?',self.snapshot(),101)
        self.assertIn('-8.33',r);self.assertIn('1 cierres',r);self.assertNotIn('RUNNER',r)
        self.assertIsNone(diagnostic_reply('Coloca una orden en mi cuenta que pierde',self.snapshot(),101))
    def test_detailed_mentor_prompt_does_not_claim_consciousness(self):
        from conversation_core import messages_for
        p=messages_for('Explícalo paso a paso',style='mentor')[0]['content']
        self.assertIn('mentor',p);self.assertIn('No finjas conciencia',p);self.assertNotIn('hasta 70 palabras',p)
    def test_state_tool_only_dispatches_read_only_actor_snapshot(self):
        from assistant_akira import AkiraAssistant
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            def callback(command):calls.append(command);return {'snapshot':self.snapshot()}
            bot=AkiraAssistant(copy.deepcopy(DEFAULT),Path(d),trade_callback=callback)
            try:
                with patch('assistant_akira.time.time',return_value=101):r=bot._execute_local_tool('inspect_akira_state',{'section':'risk'})
                self.assertTrue(r['ok']);self.assertEqual(calls,[{'action':'assistant_snapshot'}])
                bot._execute_local_tool('inspect_akira_state',{'section':'trade'});self.assertEqual(len(calls),1)
            finally:bot._managed_model.shutdown()


class ToolValidationTests(unittest.TestCase):
    def tools(self):return [{'type':'function','function':dict(name='read_state',parameters=dict(type='object',properties=dict(section=dict(type='string',enum=['risk'])),required=['section'],additionalProperties=False))}]
    def test_malformed_unknown_and_extra_arguments_do_not_execute(self):
        for args in ('{bad','{}','{"section":"trade"}','{"section":"risk","cmd":"go"}','[]'):
            with self.subTest(args=args),self.assertRaises((ValueError,TypeError)):
                validated_tool_args({'function':{'name':'read_state','arguments':args}},self.tools())
    def test_valid_arguments_are_preserved(self):
        self.assertEqual(validated_tool_args({'function':{'name':'read_state','arguments':'{"section":"risk"}'}},self.tools()),('read_state',{'section':'risk'}))
    def test_invalid_json_is_reported_to_model_without_executing(self):
        call={'id':'x','function':{'name':'read_state','arguments':'{bad'}};seen=[]
        def model(messages,**kw):
            seen.append(copy.deepcopy(messages));return {'message':{'tool_calls':[call]}} if len(seen)==1 else {'message':{'content':'Faltan datos'}}
        with patch('akira_local_ai.chat',side_effect=model),patch('akira_local_ai._direct_local_engine',return_value=True):
            run=[];text=agent([],self.tools(),lambda *a:run.append(a),max_rounds=2)
        self.assertFalse(run);self.assertEqual(text,'Faltan datos');self.assertFalse(json.loads(seen[-1][-1]['content'])['ok'])


class SelectedModelTests(unittest.TestCase):
    def test_missing_custom_model_does_not_silently_use_a_different_model(self):
        from akira_model_runtime import ManagedLlamaProcess
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'local_ai/models').mkdir(parents=True);(root/'local_ai/bin').mkdir(parents=True)
            (root/'local_ai/models/Qwen3-4B-Q4_K_M.gguf').write_bytes(b'GGUF')
            (root/'local_ai/bin/llama-server.exe').write_bytes(b'MZ')
            runtime=ManagedLlamaProcess({'local_runtime_enabled':True,'local_runtime_exe':str(root/'local_ai/bin/llama-server.exe'),'local_runtime_model':str(root/'missing-8B.gguf')})
            self.assertIsNone(runtime._paths())
