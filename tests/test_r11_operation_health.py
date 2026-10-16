"""Regression contract: status never grants permission to send trades."""
import copy
import unittest
from operation_health import execution_gate,verification_job

class OperatorGateTests(unittest.TestCase):
    def test_first_run_observe_explains_manual_authorization(self):
        state=execution_gate('observe',False,account={'login':123})
        self.assertEqual(state['code'],'OBSERVE')
        self.assertFalse(state['execution_allowed'])
        self.assertIn('Ajustes',state['next_action'])
        self.assertFalse(state['risk_checks_skipped'])
    def test_recovery_does_not_activate_trading(self):
        self.assertEqual(execution_gate('observe',network_available=True)['code'],'OBSERVE')
        self.assertFalse(execution_gate('trade',paused=True)['execution_allowed'])
    def test_disconnected_trade_and_broker_block_are_distinct(self):
        self.assertEqual(execution_gate('trade',network_available=False)['code'],'OFFLINE')
        self.assertEqual(execution_gate('trade',runtime_block='Mercado cerrado')['code'],'BROKER_BLOCK')
    def test_authorized_is_not_order_approval(self):
        state=execution_gate('trade',account={'login':31})
        self.assertTrue(state['execution_allowed'])
        self.assertIn('todavía debe',state['reason'])
    def test_preview_disables_all_entries(self):
        self.assertEqual(execution_gate('trade',preview=True)['code'],'PREVIEW')

class FiniteReviewTests(unittest.TestCase):
    def setUp(self):
        self.now=200
        self.job={'id':'1','targets':['BTC / key'], 'fingerprints':{'BTC / key':'abc'},'deep':True,'requested':100}
        self.report={'BTC / key':{'fingerprint':'abc','critical_missing':[]}}
    def check(self, **kw):
        defaults={'job':self.job,'reports':self.report,'checks':{},'reviews':{},'now':self.now,'ai_available':True}
        defaults.update(kw)
        return verification_job(**defaults)
    def test_still_working_ends_as_timeout_not_infinite(self):
        self.assertEqual(self.check(now=120)['phase'],'REVISANDO')
        result=self.check(now=226)
        self.assertEqual(result['phase'],'TIEMPO AGOTADO')
        self.assertTrue(result['terminal'])
        self.assertFalse(result['authorizes_orders'])
    def test_missing_ai_reports_end_without_sending_orders(self):
        result=self.check(ai_available=False,now=105)
        self.assertEqual(result['phase'],'SIN SERVICIO DE IA')
        self.assertEqual(result['completed'],0)
    def test_changed_levels_are_terminal_and_not_reused(self):
        result=self.check(reports={'BTC / key':{'fingerprint':'new'}})
        self.assertEqual(result['phase'],'DATOS O NIVELES CAMBIADOS')
        self.assertEqual(result['changed'],['BTC / key'])
    def test_exact_current_revisions_complete(self):
        checks={'BTC / key':{'fingerprint':'abc','at':160,'risk_passed':True,'broker_checked':True}}
        reviews={'BTC / key':{'fingerprint':'abc','updated':170,'state':'COMPLETE','data':{'verdict':'APPROVE','reason':'Comprobación individual concluida','missing':[]}}}
        result=self.check(checks=checks,reviews=reviews)
        self.assertEqual(result['phase'],'REVISIÓN TERMINADA')
        self.assertEqual(result['completed'],2)
        self.assertFalse(result['authorizes_orders'])
    def test_incomplete_ai_answer_is_terminal_rejection(self):
        checks={'BTC / key':{'fingerprint':'abc','at':160,'risk_passed':True,'broker_checked':True}}
        for data in ({'verdict':'APPROVE'}, {'verdict':'MAYBE','reason':'x','missing':[]},
                     {'verdict':'APPROVE','reason':'','missing':[]},
                     {'verdict':'APPROVE','reason':'ok','missing':['risk']}):
            reviews={'BTC / key':{'fingerprint':'abc','updated':170,'state':'COMPLETE','data':data}}
            result=self.check(checks=checks,reviews=reviews)
            self.assertEqual(result['phase'],'REVISIÓN RECHAZADA O FALLIDA',data)
            self.assertFalse(result['authorizes_orders'])

    def test_missing_critical_data_cannot_finish_as_approved(self):
        checks={'BTC / key':{'fingerprint':'abc','at':160,'risk_passed':True,'broker_checked':True}}
        result=self.check(job={**self.job,'deep':False},checks=checks,
            reports={'BTC / key':{'fingerprint':'abc','critical_missing':['cotización no vigente']}})
        self.assertEqual(result['phase'],'REVISIÓN RECHAZADA O FALLIDA')
        self.assertIn('cotización no vigente',result['missing'])

    def test_old_or_other_candidate_review_cannot_finish(self):
        checks={'BTC / key':{'fingerprint':'wrong','at':201,'risk_passed':True}}
        reviews={'BTC / key':{'fingerprint':'abc','updated':90,'state':'COMPLETE'}}
        self.assertEqual(self.check(checks=checks,reviews=reviews)['completed'],0)
    def test_unfinished_broker_precheck_is_not_counted(self):
        checks={'BTC / key':{'fingerprint':'abc','at':201,'risk_passed':True,'broker_checked':False}}
        self.assertEqual(self.check(checks=checks)['completed'],0)
    def test_ai_abstention_is_rejection_even_if_request_finished(self):
        checks={'BTC / key':{'fingerprint':'abc','at':201,'risk_passed':True,'broker_checked':True}}
        reviews={'BTC / key':{'fingerprint':'abc','updated':170,'state':'COMPLETE',
                               'data':{'verdict':'ABSTAIN'}}}
        self.assertEqual(self.check(checks=checks,reviews=reviews)['phase'],'REVISIÓN RECHAZADA O FALLIDA')
    def test_risk_rejection_is_terminal_not_success(self):
        checks={'BTC / key':{'fingerprint':'abc','at':201,'risk_passed':False,'broker_checked':True,'error':'sin margen'}}
        result=self.check(checks=checks)
        self.assertEqual(result['phase'],'REVISIÓN RECHAZADA O FALLIDA')
    def test_original_job_is_immutable(self):
        original=copy.deepcopy(self.job)
        self.check(now=226)
        self.assertEqual(self.job,original)

if __name__=='__main__':unittest.main()
