"""Account loss circuits use confirmed receipts across both symbols and lanes."""
import copy,unittest
from dataclasses import replace
from entry_safety import loss_pause
from settings import DEFAULT,load_config
from execution import Gateway,Journal,Blocked,REMOVE,OWN_PENDING
from engine import Engine
from tests.fixtures import PendingCase


def outcome(pid,when,pnl,symbol='BTCUSDm',side=1):
    return {'position_id':pid,'closed_at':when,'pnl':pnl,'symbol':symbol,'side':side,
            'state':'CONFIRMADO MT5','deal_ids':[pid*2,pid*2+1],'lane':'PENDING'}


class LossPause(unittest.TestCase):
    def setUp(self):self.cfg=load_config(DEFAULT);self.now=1800000000
    def rows(self):return [outcome(1,self.now-300,-1),outcome(2,self.now-200,-2,'XAUUSDm',-1),outcome(3,self.now-100,-1,'BTCUSDm',-1)]
    def test_three_verified_losses_across_assets_and_sides_pause_new_entries(self):
        r=loss_pause(self.cfg,self.rows(),self.now)
        self.assertFalse(r['allowed']);self.assertEqual(r['loss_streak'],3);self.assertEqual(r['closed_ids'],['1','2','3'])
    def test_one_or_two_losses_do_not_trip_the_new_circuit(self):
        for n in (0,1,2):
            with self.subTest(n=n):self.assertTrue(loss_pause(self.cfg,self.rows()[:n],self.now)['allowed'])
    def test_verified_win_before_threshold_breaks_the_streak(self):
        rows=self.rows();rows[1]['pnl']=1
        self.assertTrue(loss_pause(self.cfg,rows,self.now)['allowed'])
    def test_win_from_an_already_open_trade_does_not_unlock_a_tripped_circuit(self):
        rows=self.rows()+[outcome(4,self.now-1,2)]
        self.assertFalse(loss_pause(self.cfg,rows,self.now)['allowed'])
    def test_duplicate_receipt_cannot_inflate_loss_count(self):
        row=self.rows()[0]
        self.assertTrue(loss_pause(self.cfg,[row,copy.deepcopy(row),copy.deepcopy(row)],self.now)['allowed'])
    def test_unverified_future_or_nonfinite_rows_cannot_trip(self):
        rows=self.rows();rows[0]['deal_ids']=[];rows[1]['closed_at']=self.now+1;rows[2]['pnl']=float('nan')
        self.assertTrue(loss_pause(self.cfg,rows,self.now)['allowed'])
    def test_cooldown_expires_on_the_actual_boundary(self):
        rows=self.rows();end=rows[-1]['closed_at']+24*3600
        self.assertFalse(loss_pause(self.cfg,rows,end-.01)['allowed']);self.assertTrue(loss_pause(self.cfg,rows,end)['allowed'])
    def test_new_evidence_survives_midnight_without_resetting_the_pause(self):
        self.assertFalse(loss_pause(self.cfg,self.rows(),self.now+12*3600)['allowed'])
    def test_high_money_limits_do_not_erase_loss_evidence_or_get_rewritten(self):
        self.cfg['capital_protection'].update(trade_pct=100,portfolio_pct=100,symbol_pct=100,daily_loss_pct=100,max_drawdown_pct=100)
        before=copy.deepcopy(self.cfg)
        self.assertFalse(loss_pause(self.cfg,self.rows(),self.now)['allowed']);self.assertEqual(self.cfg,before)
    def test_explicitly_disabled_policy_is_respected(self):
        self.cfg['capital_protection']['enabled']=False
        self.assertTrue(loss_pause(self.cfg,self.rows(),self.now)['allowed'])
    def test_settings_reject_invalid_loss_circuit_values(self):
        for field,v in (('loss_streak_limit',0),('loss_streak_limit',True),('loss_streak_limit',2.5),('loss_pause_hours',0),('loss_pause_hours',float('nan'))):
            with self.subTest(field=field,value=v):
                c=copy.deepcopy(DEFAULT);c['capital_protection'][field]=v
                with self.assertRaises(ValueError):load_config(c)


class ExecutionLossPause(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.cfg['capital_protection'].update(enabled=True,strict_pending_quality=False,trade_pct=100,portfolio_pct=100,symbol_pct=100,daily_loss_pct=100,max_drawdown_pct=100)
        self.g.refresh_history(force=True)
    def losses(self):
        self.g.journal.data['pending_outcomes']={str(i):outcome(i,self.clock()-400+i*60,-1,'XAUUSDm' if i==2 else 'BTCUSDm',-1 if i==3 else 1) for i in (1,2,3)}
        self.g.journal.save()
    def test_pending_cannot_bypass_the_circuit_even_with_a_new_key(self):
        self.losses()
        with self.assertRaisesRegex(Blocked,'Pausa de nuevas entradas'):self.g.send_immediate_plan(replace(self.plan(),key='SWING:NEW:unrelated'))
        self.assertFalse(self.api.sent)
    def test_direct_runner_cannot_bypass_the_same_account_circuit(self):
        self.losses();p=replace(self.plan(),lane='RUNNER',kind='MARKET',key='RUN:NEW')
        with self.assertRaisesRegex(Blocked,'Pausa de nuevas entradas'):self.g.send_runner(p)
        self.assertFalse(self.api.sent)
    def test_prepared_request_rechecks_losses_before_order_send(self):
        prepared=self.g.prepare(self.plan());self.losses()
        with self.assertRaisesRegex(Blocked,'Pausa de nuevas entradas'):self.g.send(prepared)
        self.assertFalse(self.api.sent)
    def test_restarting_the_gateway_keeps_the_verified_pause(self):
        self.losses();g=Gateway(self.api,self.cfg,Journal(self.g.journal.path),self.g.log,self.clock);g.refresh_history(force=True)
        with self.assertRaisesRegex(Blocked,'Pausa de nuevas entradas'):g.prepare(self.plan())
        self.assertFalse(self.api.sent)
    def test_own_pendings_are_withdrawn_without_touching_manual_orders_or_position_stops(self):
        self.losses();owned=self.api.add_pending(self.plan());manual=self.api.add_pending(self.plan('XAUUSDm'),magic=0)
        position=self.api.add_position('XAUUSDm',entry=2500,sl=2490,tp=2520,magic=0)
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close)
        from trade_quality_gate import owned_outcomes
        e._confirmed_outcomes=owned_outcomes(self.g);e.paused=True
        e.enforce_capital_protection(self.g.snapshot())
        self.assertEqual(self.api.orders,[manual]);self.assertEqual((position.sl,position.tp),(2490,2520))
        self.assertTrue(self.api.sent);self.assertTrue(all(r['action']==REMOVE and r['order']==owned.ticket for r in self.api.sent))
    def test_unacknowledged_withdrawal_preserves_the_intent(self):
        self.losses();self.api.add_pending(self.plan());self.api.drop_ack=True
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close)
        from trade_quality_gate import owned_outcomes
        e._confirmed_outcomes=owned_outcomes(self.g);e.enforce_capital_protection(self.g.snapshot())
        self.assertIn('BTCUSDm',self.g.journal.data['intents'])
        with self.assertRaises(Blocked):self.g.prepare(self.plan())


if __name__=='__main__':unittest.main()
