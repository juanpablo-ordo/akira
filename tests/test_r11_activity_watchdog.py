"""A six-hour monitor can diagnose but never execute, even when a plan is ready."""
import unittest
from activity_watchdog import SessionWatchdog

class SessionDiagnosticTests(unittest.TestCase):
    def payload(self,mode='TRADE_ENABLED',viable=False,tickets=()):
        return {'execution_gate':{'code':mode,'reason':'Solo análisis' if mode=='OBSERVE' else 'Conexión activa'},
                'markets':{'BTCUSDm':{'open':True}},
                'orders':[{'ticket':k,'owned':True} for k in tickets],
                'positions':[], 'candidates':{'BTCUSDm':[{'key':'test'}]},
                'symbols':{'BTCUSDm':{'scenario_book':[{'sendable':viable,'confirmed':False}]}}}
    def test_candidate_without_orders_reports_block_not_fake_execution(self):
        w=SessionWatchdog(100)
        w.inspect(self.payload(),100)
        row=w.inspect(self.payload(viable=True),100+6*3600)
        self.assertEqual(row['state'],'SIX_HOURS')
        self.assertEqual(row['forced_orders'],0)
        self.assertFalse(row['risk_limits_modified'])
        self.assertEqual(row['owned_active_tickets'],0)
        self.assertEqual(row['viable_count'],1)
    def test_new_confirmed_ticket_resets_idle_counter(self):
        w=SessionWatchdog(100)
        w.inspect(self.payload(tickets=(22,)),100)
        row=w.inspect(self.payload(tickets=(22,23)),21000)
        self.assertEqual(row['seconds_since_confirmed_ticket'],0)
        self.assertEqual(row['owned_active_tickets'],2)
    def test_existing_ticket_at_start_does_not_pretend_new_trade(self):
        w=SessionWatchdog(100)
        w.inspect(self.payload(tickets=(22,)),100)
        row=w.inspect(self.payload(tickets=(22,)),5000)
        self.assertGreater(row['seconds_since_confirmed_ticket'],4000)
    def test_reappearing_old_ticket_does_not_reset_inactivity(self):
        w=SessionWatchdog(100)
        w.inspect(self.payload(tickets=(42,)),100)
        w.inspect(self.payload(tickets=()),200)
        row=w.inspect(self.payload(tickets=(42,)),3600)
        self.assertEqual(row['seconds_since_confirmed_ticket'],3500)

    def test_observe_reasons_are_explicit(self):
        w=SessionWatchdog(100)
        row=w.inspect(self.payload(mode='OBSERVE'),1000)
        self.assertIn('Solo análisis',row['reasons'][0])
        self.assertEqual(row['state'],'INFO')
    def test_unconfirmed_intent_not_counted_as_ticket(self):
        w=SessionWatchdog(100)
        snap=self.payload();snap['unconfirmed']=['BTCUSDm:pending']
        w.inspect(snap,100)
        row=w.inspect(snap,200)
        self.assertEqual(row['owned_active_tickets'],0)
        self.assertTrue(any('incierto' in r for r in row['reasons']))

if __name__=='__main__':unittest.main()
