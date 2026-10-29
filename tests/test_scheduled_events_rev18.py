"""UTC event windows use the New York DST calendar, not the PC timezone."""
import copy,unittest
from datetime import datetime,timezone
from dataclasses import replace
from settings import DEFAULT,load_config
from capital_guard import rules
from scheduled_events import fomc_window
from entry_safety import entry_policy
from execution import Blocked,REMOVE
from engine import Engine
from tests.fixtures import PendingCase


def utc(text):return datetime.fromisoformat(text.replace('Z','+00:00')).timestamp()


class ScheduledWindows(unittest.TestCase):
    def setUp(self):self.cfg=load_config(DEFAULT)
    def check(self,stamp):return fomc_window(rules(self.cfg),utc(stamp))
    def test_october_statement_and_press_conference_share_a_known_window(self):
        self.assertTrue(self.check('2026-10-28T16:59:59Z')['allowed'])
        r=self.check('2026-10-28T17:00:00Z');self.assertFalse(r['allowed'])
        self.assertEqual(r['paused_until'],utc('2026-10-28T19:30:00Z'))
        self.assertFalse(self.check('2026-10-28T19:03:00Z')['allowed'])
        self.assertTrue(self.check('2026-10-28T19:30:00Z')['allowed'])
    def test_winter_announcement_is_1900_utc(self):
        self.assertTrue(self.check('2026-12-09T17:59:59Z')['allowed'])
        r=self.check('2026-12-09T18:00:00Z');self.assertFalse(r['allowed'])
        self.assertEqual(r['paused_until'],utc('2026-12-09T20:30:00Z'))
    def test_ordinary_days_are_not_blanket_blocked(self):self.assertTrue(self.check('2026-10-29T18:00:00Z')['allowed'])
    def test_other_news_is_not_claimed_covered(self):
        r=self.check('2026-10-29T18:00:00Z');self.assertIn('no cubre otros anuncios',r['coverage'])
    def test_explicit_control_does_not_change_money_settings(self):
        self.cfg['capital_protection']['fomc_pause']=False;before=copy.deepcopy(self.cfg)
        self.assertTrue(self.check('2026-10-28T18:00:00Z')['allowed']);self.assertEqual(before,self.cfg)
    def test_active_event_also_blocks_an_account_with_no_losses(self):
        self.assertFalse(entry_policy(self.cfg,[],utc('2026-10-28T17:19:00Z'))['allowed'])


class ScheduledExecution(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.cfg['capital_protection'].update(enabled=True,strict_pending_quality=False,trade_pct=100,portfolio_pct=100,symbol_pct=100)
        self.clock.now=utc('2026-10-28T17:19:00Z')
        for symbol,tick in list(self.api.ticks.items()):self.api.set_quote(symbol,tick.bid,fill=False)
        self.g.refresh_history(force=True)
    def test_gateway_does_not_send_a_new_pending_or_runner_in_the_window(self):
        for p in (self.plan(),replace(self.plan(),lane='RUNNER',kind='MARKET',key='RUN:event')):
            with self.subTest(lane=p.lane),self.assertRaisesRegex(Blocked,'FOMC'):
                (self.g.send_runner if p.lane=='RUNNER' else self.g.prepare)(p)
        self.assertFalse(self.api.sent)
    def test_existing_owned_pending_is_withdrawn_without_changing_position_protection(self):
        self.api.add_pending(self.plan());manual=self.api.add_pending(self.plan('XAUUSDm'),magic=0)
        p=self.api.add_position('XAUUSDm',entry=2500,sl=2490,tp=2520,magic=0)
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close)
        e.enforce_capital_protection(self.g.snapshot())
        self.assertEqual(self.api.orders,[manual]);self.assertEqual((p.sl,p.tp),(2490,2520))
        self.assertTrue(all(r['action']==REMOVE for r in self.api.sent))


if __name__=='__main__':unittest.main()
