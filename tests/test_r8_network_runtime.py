"""Offline recovery pauses entries without changing manual pause, risk or tickets."""
import copy,unittest
from unittest.mock import Mock,patch
from connectivity import ConnectivityMonitor,recently_connected
from engine import Engine
from execution import Blocked
from tests.fixtures import PendingCase


class NetworkState(unittest.TestCase):
    def test_two_failures_pause_and_a_success_recovers_automatically(self):
        events=[];checks=iter([True,False,False,False,True])
        monitor=ConnectivityMonitor(events.append,check=lambda:next(checks),clock=lambda:100)
        delays=[monitor.sample() for _ in range(5)]
        self.assertEqual([e['online'] for e in events],[True,False,True])
        self.assertGreater(delays[3],delays[2]);self.assertEqual(delays[-1],5)

    def test_an_isolated_provider_failure_does_not_report_an_outage(self):
        events=[];checks=iter([True,False,True])
        monitor=ConnectivityMonitor(events.append,check=lambda:next(checks))
        for _ in range(3):monitor.sample()
        self.assertEqual([row['online'] for row in events],[True])

    def test_real_fresh_mt5_and_source_receipts_override_blocked_probe_domains(self):
        self.assertTrue(recently_connected({'connected':True,'symbols':{'BTCUSDm':{'quote_time':99}}},now=100))
        self.assertTrue(recently_connected({'research':{'sources':{'venue:OKX':{'updated':99,'usable':True}}}},now=100))
        self.assertFalse(recently_connected({'connected':True,'symbols':{'BTCUSDm':{'quote_time':90}},'research':{'sources':{'local_ai':{'updated':100}}}},now=100))


class RuntimeNetwork(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)

    def test_offline_blocks_new_entries_but_keeps_protection_permission(self):
        before=copy.deepcopy(self.cfg);order=self.api.add_pending(self.plan())
        self.e.handle_command({'action':'network_state','online':False})
        with self.assertRaisesRegex(Blocked,'Sin Internet'):self.g.permissions(self.g.snapshot())
        self.g.permissions(self.g.snapshot(),entry=False)
        self.assertEqual(self.cfg,before);self.assertEqual([o.ticket for o in self.api.orders],[order.ticket]);self.assertFalse(self.api.sent)

    def test_recovery_does_not_clear_manual_pause_or_activate_observe_mode(self):
        self.cfg['mode']='observe';self.e.paused=True
        self.e.handle_command({'action':'network_state','online':False})
        self.e.handle_command({'action':'network_state','online':True})
        self.assertTrue(self.e.paused);self.assertEqual(self.cfg['mode'],'observe')
        self.assertTrue(self.g.network_available)

    def test_mode_transition_cannot_write_before_the_actor_owns_the_account(self):
        from runtime import session_write_guard
        self.g.requires_execution_lease=True;self.g.execution_lease_active=False
        with self.assertRaisesRegex(Blocked,'bloqueo exclusivo'):self.g.permissions(self.g.snapshot())
        account_lock=object()
        with patch('runtime.AccountLock',return_value=account_lock),patch('runtime.retire'):
            held,error=session_write_guard(self.g,self.api.account,None)
        self.assertIs(held,account_lock);self.assertFalse(error);self.g.permissions(self.g.snapshot())

    def test_observe_is_explicit_and_first_valid_trade_cycle_remains_independent_of_web(self):
        self.cfg['mode']='observe';view=self.e.step();self.assertFalse(self.api.sent)
        self.assertTrue(all('Solo análisis' in row['detail'] for row in view['status'].values()))
        enabled=copy.deepcopy(self.cfg);enabled['mode']='trade'
        self.e.handle_command({'action':'apply_settings','config':enabled,'changed_paths':['mode']})
        self.clock.advance(1)
        for symbol in self.cfg['symbols']:self.api.set_quote(symbol,self.api.ticks[symbol].bid,fill=False)
        self.e.step()
        self.assertEqual({r['symbol'] for r in self.api.sent},{'BTCUSDm','XAUUSDm'})


if __name__=='__main__':unittest.main()
