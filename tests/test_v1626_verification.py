"""Exact-order evidence, read-only broker checks and bounded recovery."""
import copy,hashlib,json,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from concurrent.futures import Future
from engine import Engine
from pending_verification import targets,identity,levels,fingerprint,assess,reports
from research import ContextWorker
from operation_report import build_report,export_report
from tests.fixtures import PendingCase
from tests import test_v1625_recovery as recovery_fixture
from tests import test_v1621_startup as ui_fixture
from tests.test_desktop_flow import Widget

class RecoveryTests(unittest.TestCase):
    setUp=recovery_fixture.RecoveryTests.setUp
    def enabled(self):
        self.now=[1000];self.s.clock=lambda:self.now[0];self.s.enabled=True
        self.cfg['assistant']['auto_install_local_ai']=True  # explicit opt-in; default is optional
        self.new.poll.return_value=1
        self.s.local_profile.parent.mkdir(parents=True,exist_ok=True)
        self.s.local_profile.write_text(json.dumps({'phase':'FAILED','error':'error de prueba','heartbeat':999}))
        self.s.attempted=True;self.s.process=self.new
    def test_failed_preparation_schedules_a_delayed_automatic_retry(self):
        self.enabled();r=self.s.observe({'ok':False,'ready':False})
        self.assertEqual(r['retry_after_seconds'],30);self.launch.assert_not_called()
        self.now[0]=1030;r=self.s.observe({'ok':False,'ready':False})
        self.assertTrue(r['auto_repair']);self.assertEqual(self.s.auto_retries,1);self.launch.assert_called_once()
    def test_automatic_repair_stops_after_three_attempts(self):
        self.enabled()
        for t in (1000,1030,1090,1210,1500,1900):self.now[0]=t;self.s.observe({'ok':False,'ready':False})
        self.assertEqual(self.launch.call_count,3);self.assertEqual(self.s.auto_retries,3)
    def test_disabled_auto_install_does_not_restart_a_process(self):
        self.enabled();self.cfg['assistant']['auto_install_local_ai']=False
        for t in (1000,2000):self.now[0]=t;self.s.observe({'ok':False,'ready':False})
        self.launch.assert_not_called()
    def test_external_endpoint_is_never_repaired_as_a_local_service(self):
        self.enabled();self.cfg['assistant']['local_endpoint']='https://external.example/api/chat'
        self.s.observe({'ok':False,'ready':False});self.now[0]=3000;self.s.observe({'ok':False,'ready':False})
        self.launch.assert_not_called()
    def test_manual_retry_resets_the_automatic_limit(self):
        self.enabled();self.s.auto_retries=3;self.s.auto_due=2000
        self.assertTrue(self.s.retry()['accepted']);self.assertEqual(self.s.auto_retries,0)
    def test_successful_availability_clears_retry_state(self):
        self.enabled();self.s.auto_retries=2;self.s.auto_due=1200
        self.s.local_profile.write_text('{}')
        self.assertTrue(self.s.observe({'ok':True,'ready':True,'models':['qwen3:4b']})['ready'])
        self.assertEqual(self.s.auto_retries,0);self.assertEqual(self.s.auto_due,0)
    def test_other_platforms_do_not_launch_windows_repair(self):
        self.enabled();self.s.platform='posix'
        self.s.observe({'ok':False,'ready':False});self.now[0]=2000;self.s.observe({'ok':False,'ready':False})
        self.launch.assert_not_called()
    def test_progress_replacement_has_a_real_windows_installation_check(self):
        root=Path(__file__).resolve().parents[1];script=root/'PREPARAR_OLLAMA.ps1'
        text=script.read_text(encoding='utf-8-sig')
        self.assertIn('[System.Management.Automation.Language.NullString]::Value',text)
        self.assertNotIn('[IO.File]::Replace($tmp,$path,$null)',text)
        self.assertIn('-SelfTestProgress',(root/'INSTALL_AKIRA.ps1').read_text(encoding='utf-8-sig'))
        if sys.platform=='win32':
            r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),'-SelfTestProgress'],capture_output=True,text=True,encoding='utf-8',timeout=20)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('"status":"PASSED"',r.stdout)

class EvidenceTests(PendingCase,unittest.TestCase):
    def setUp(self):
        PendingCase.setUp(self);self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close);self.view=self.e.step()
        self.cfg['mode']='observe';self.e.pending_check_queue=[];self.plans=targets(self.view);self.p=next(p for p in self.plans if p.get('confirmed') and p['symbol']=='BTCUSDm')
    def stage(self,r,name):return next(s for s in r['stages'] if name in s['name'])
    def test_each_owned_order_has_its_own_report_and_no_duplicates(self):
        rows=reports(self.view)
        ids=[identity(p) for p in self.plans];self.assertEqual(len(ids),len(set(ids)))
        for o in self.view['orders']:
            if o['owned']:self.assertTrue(any(r['ticket']==o['ticket'] for r in rows.values()))
    def test_same_symbol_cannot_borrow_another_orders_broker_receipt(self):
        other=next(p for p in self.plans if p['symbol']=='BTCUSDm' and identity(p)!=identity(self.p))
        check={identity(other):{'levels':levels(other),'fingerprint':fingerprint(self.view,other),'at':self.clock(),'risk_passed':True,'broker_checked':True}}
        r=assess(self.view,self.p,check)
        self.assertEqual(self.stage(r,'Riesgo')['state'],'PENDIENTE');self.assertEqual(self.stage(r,'Restricciones')['state'],'PENDIENTE')
    def test_changed_stop_invalidates_the_exact_level_review(self):
        fp=fingerprint(self.view,self.p);changed={**self.p,'sl':self.p['sl']-.01}
        self.assertNotEqual(fp,fingerprint(self.view,changed))
        r=assess(self.view,changed,reviews={identity(changed):{'fingerprint':fp,'state':'COMPLETE','updated':self.clock(),'data':{'verdict':'APPROVE','reason':'antiguo'}}})
        self.assertEqual(self.stage(r,'IA:')['state'],'DESACTUALIZADA')
    def test_changed_indicators_or_risk_configuration_invalidate_review(self):
        fp=fingerprint(self.view,self.p);v=copy.deepcopy(self.view);v['symbols']['BTCUSDm']['frames']['M15']['rsi']+=1
        self.assertNotEqual(fp,fingerprint(v,self.p));v=copy.deepcopy(self.view);v['selection_configuration']['risk']['max_trade_money']+=1
        self.assertNotEqual(fp,fingerprint(v,self.p))
    def test_inverted_stop_is_a_critical_failure(self):
        r=assess(self.view,{**self.p,'sl':self.p['entry']+100})
        self.assertEqual(self.stage(r,'Entrada,')['state'],'BLOQUEADO');self.assertEqual(r['state'],'REVISAR')
    def test_available_gold_never_uses_bitcoin_venue_as_its_evidence(self):
        p=next(p for p in self.plans if p['symbol']=='XAUUSDm')
        self.view['research']['sources']={'venue:OKX':{'fresh':True,'usable':True},'derivatives:BTCUSDm':{'fresh':True,'usable':True}}
        r=assess(self.view,p);self.assertEqual(self.stage(r,'Fuentes')['state'],'SIN APORTE')
    def test_ai_approval_with_missing_confirmation_is_not_full_approval(self):
        self.p['quality_score']=90
        r=assess(self.view,self.p,reviews={identity(self.p):{'fingerprint':fingerprint(self.view,self.p),'state':'COMPLETE','updated':self.clock(),'data':{'verdict':'APPROVE','reason':'compatible','missing':['confirmación que falta']}}})
        self.assertEqual(r['state'],'REVISAR');self.assertIn('confirmación que falta',self.stage(r,'IA:')['detail'])
    def test_unvalidated_statistics_never_become_a_profit_percentage(self):
        r=assess(self.view,self.p)
        self.assertEqual(self.stage(r,'Estudio')['state'],'EN ESTUDIO');self.assertEqual(r['calibration'],{})

class BrokerTests(PendingCase,unittest.TestCase):
    setUp=EvidenceTests.setUp

    def test_verification_command_returns_before_any_broker_check(self):
        before=len(self.api.sent)
        with patch.object(self.api,'order_check',wraps=self.api.order_check) as check:
            r=self.e.handle_command({'action':'verify_pending','id':identity(self.p),'deep':False})
            self.assertTrue(r['accepted']);check.assert_not_called()
        self.assertEqual(len(self.api.sent),before)

    def test_existing_pending_is_checked_once_without_sending_or_editing(self):
        before=copy.deepcopy(self.api.orders);sent=len(self.api.sent)
        self.e.handle_command({'action':'verify_pending','id':identity(self.p),'deep':False})
        with patch.object(self.api,'order_check',wraps=self.api.order_check) as check:self.e.process_pending_verification()
        self.assertEqual(check.call_count,0);row=self.e.pending_checks[identity(self.p)];self.assertTrue(row['broker_checked']);self.assertTrue(row['risk_passed']);self.assertTrue(row['unchanged_confirmed'])
        self.assertEqual(len(self.api.sent),sent);self.assertEqual([vars(o) for o in self.api.orders],[vars(o) for o in before])

    def test_a_request_for_all_does_not_check_every_order_in_one_cycle(self):
        self.e.handle_command({'action':'verify_pending','deep':False})
        queued=len(self.e.pending_check_queue);self.e.process_pending_verification()
        self.assertEqual(len(self.e.pending_check_queue),queued-1);self.assertEqual(len(self.e.pending_checks),1)

    def test_broker_rejection_is_reported_without_a_send(self):
        self.api.fail_check=10016;sent=len(self.api.sent)
        # Force the broker rejection branch; unchanged confirmed levels now
        # intentionally skip a redundant MODIFY that MT5 rejects with 10025.
        with patch.object(self.g,'pending_parameters_unchanged',return_value=False):
            self.e.handle_command({'action':'verify_pending','id':identity(self.p),'deep':False});self.e.process_pending_verification()
        self.assertIn('order_check',self.e.pending_checks[identity(self.p)]['broker_error']);self.assertEqual(len(self.api.sent),sent)

    def test_no_quote_from_old_prices_is_checked_with_mt5(self):
        self.clock.advance(100);self.e.handle_command({'action':'verify_pending','id':identity(self.p),'deep':False})
        with patch.object(self.api,'order_check') as check:self.e.process_pending_verification();check.assert_not_called()
        self.assertTrue(self.e.pending_checks[identity(self.p)].get('error'))

    def test_changed_live_levels_do_not_receive_an_old_geometry_check(self):
        self.e.handle_command({'action':'verify_pending','id':identity(self.p),'deep':False})
        o=next(o for o in self.api.orders if o.ticket==self.p['ticket']);o.sl-=.01
        with patch.object(self.api,'order_check') as check:self.e.process_pending_verification();check.assert_not_called()
        self.assertIn('niveles cambiaron',self.e.pending_checks[identity(self.p)]['error'])

    def test_filled_or_deleted_order_is_not_rechecked_as_an_existing_pending(self):
        self.e.handle_command({'action':'verify_pending','id':identity(self.p),'deep':False});self.api.orders=[o for o in self.api.orders if o.ticket!=self.p['ticket']]
        with patch.object(self.api,'order_check') as check:self.e.process_pending_verification();check.assert_not_called()
        self.assertIn('desapareció',self.e.pending_checks[identity(self.p)]['error'])

    def test_missing_model_service_is_an_explicit_request_result(self):
        r=self.e.handle_command({'action':'verify_pending','id':identity(self.p),'deep':True})
        self.assertEqual(self.e.view()['pending_verification_requests'][r['job']]['phase'],'SIN SERVICIO DE IA')

    def required(self,verdict=None):
        from execution import order_plan
        r=self.e.handle_command({'action':'verify_pending','id':identity(self.p),'deep':True,'require':True})
        o=next(o for o in self.api.orders if o.ticket==self.p['ticket'])
        plan=order_plan(o,self.g.journal.data['orders'][str(o.ticket)]['plan'])
        if verdict:
            self.e.planner.research_context['pending_reviews']={identity(self.p):{'levels':levels(self.p),'fingerprint':fingerprint(self.view,self.p),
                'state':'COMPLETE','updated':self.clock(),'data':{'verdict':verdict,'reason':'Dictamen de prueba','missing':[]}}}
        return o,plan
    def test_demanded_review_blocks_before_any_order_send(self):
        from execution import MODIFY,Blocked
        o,plan=self.required();self.cfg['mode']='trade';before=len(self.api.sent)
        req={'action':MODIFY,'order':o.ticket,'symbol':o.symbol,'price':o.price_open,'sl':o.sl,'tp':o.tp}
        with self.assertRaisesRegex(Blocked,'IA exigida'):self.g._send(o.symbol,req,'modify_order',plan,before=self.g.fingerprint(o,'order'))
        self.assertEqual(len(self.api.sent),before)
    def test_matching_approved_review_allows_the_user_demanded_gate(self):
        o,p=self.required('APPROVE')
        self.e.pending_review_guard(p,self.g.snapshot(),o.volume_current,o.ticket)
    def test_rejected_review_cannot_satisfy_a_user_demand(self):
        from execution import Blocked
        o,p=self.required('REVISE')
        with self.assertRaisesRegex(Blocked,'IA exigida'):self.e.pending_review_guard(p,self.g.snapshot(),o.volume_current,o.ticket)
    def test_old_review_does_not_approve_new_levels_at_send(self):
        from execution import Blocked
        from dataclasses import replace
        o,p=self.required('APPROVE')
        with self.assertRaisesRegex(Blocked,'IA exigida'):self.e.pending_review_guard(replace(p,sl=p.sl-.01),self.g.snapshot(),o.volume_current,o.ticket)
    def test_user_requirement_is_saved_and_can_be_disabled_explicitly(self):
        o,p=self.required();self.assertTrue(self.e.review_preferences.is_file())
        self.e.handle_command({'action':'verify_pending','id':identity(self.p),'deep':False,'require':False})
        self.assertFalse(self.e.review_requirements)

    def test_new_proposal_approval_can_verify_a_required_existing_order_change(self):
        from dataclasses import replace
        o,p=self.required();proposed=replace(p,tp=p.tp+10)
        data={**proposed.to_dict(),'volume':None}
        self.e.planner.research_context['pending_reviews']={identity(data):{'levels':levels(data),'fingerprint':fingerprint(self.view,data),
            'state':'COMPLETE','updated':self.clock(),'data':{'verdict':'APPROVE','reason':'Nuevo objetivo revisado','missing':[]}}}
        self.e.pending_review_guard(proposed,self.g.snapshot(),o.volume_current,o.ticket)
    def test_required_review_never_prevents_cancelling_an_invalid_own_order(self):
        o,p=self.required();self.cfg['mode']='trade'
        with patch.object(self.g,'pending_review_guard',side_effect=AssertionError('IA gate on cancellation')):
            self.assertTrue(self.g.cancel(o,'Cancelar pendiente propia de prueba'))

    def test_required_proposal_keeps_its_policy_after_receiving_a_broker_ticket(self):
        prototype={k:v for k,v in self.p.items() if k not in ('ticket','confirmed')}
        self.e.review_account=list(self.g.identity);self.e.review_requirements={identity(prototype):{'symbol':self.p['symbol'],'key':self.p['key'],'ticket':None}}
        before=len(self.api.sent);v=self.e.view()
        self.assertIn(identity(self.p),v['required_pending_reviews']);self.assertNotIn(identity(prototype),self.e.review_requirements)
        self.assertEqual(len(self.api.sent),before)

class PendingReviewTests(PendingCase,unittest.TestCase):
    def setUp(self):
        PendingCase.setUp(self);self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close);self.view=self.e.step()
        self.w=ContextWorker(self.cfg,self.root,self.clock);self.addCleanup(self.w.close);self.plans=targets(self.view)[:2]
        self.batch=[{'plan':p,'snapshot':self.view,'fingerprint':fingerprint(self.view,p)} for p in self.plans]
        self.answer={identity(p):{'verdict':'APPROVE','strategy':'TREND_PULLBACK','reason':'estructura compatible','missing':[]} for p in self.plans}
    def test_engine_submits_the_same_complete_indicators_that_it_displays(self):
        context=self.e.research_snapshot()
        for s in context['symbols']:
            self.assertEqual(context['symbols'][s]['frames'],self.view['symbols'][s]['frames'])
            self.assertEqual(context['symbols'][s]['bid'],self.view['symbols'][s]['bid'])
    def test_enqueue_does_not_call_a_model_on_the_actor(self):
        with patch('research.ollama_chat',side_effect=AssertionError('model on caller')):
            queued=self.w.request_pending_reviews(self.plans,self.view)
        self.assertEqual(len(queued),2);self.assertTrue(self.w.pending_queue)
    def test_one_batch_produces_a_separate_verdict_for_every_exact_pending(self):
        with patch('research.ollama_status',return_value={'ok':True,'models':['qwen3:4b']}),patch('research.ollama_chat',return_value=json.dumps(self.answer)) as model:
            result=self.w._pending_summary(self.batch,{})
        self.assertEqual(set(result),set(self.answer));self.assertEqual(model.call_count,1)
        self.assertFalse(model.call_args.kwargs['think'])
        for p in self.plans:self.assertIn(str(p['entry']),model.call_args.args[0][1]['content'])
    def test_partial_model_reply_cannot_claim_all_orders_were_reviewed(self):
        partial={next(iter(self.answer)):next(iter(self.answer.values()))}
        with patch('research.ollama_status',return_value={'ok':True,'models':['qwen3:4b']}),patch('research.ollama_chat',return_value=json.dumps(partial)):
            with self.assertRaisesRegex(ValueError,'incompleta'):self.w._pending_summary(self.batch,{})
    def test_missing_local_model_does_not_secretly_enable_openai(self):
        self.cfg['assistant']['cloud']=False
        with patch('research.ollama_status',return_value={'ok':False,'models':[]}),patch('research.openai_responses',side_effect=AssertionError('unauthorized OpenAI')):
            with self.assertRaisesRegex(RuntimeError,'recuperar su asistente'):self.w._pending_summary(self.batch,{})
    def test_stale_batch_cannot_overwrite_a_new_level_request(self):
        self.w.request_pending_reviews(self.plans,self.view);old=self.batch
        future=Future();future.set_result({identity(p):{'data':self.answer[identity(p)]} for p in self.plans})
        self.w.pending_future=future;self.w.pending_batch=old
        changed={**self.plans[0],'sl':self.plans[0]['sl']-.1};self.w.request_pending_reviews([changed],self.view)
        self.w.pool=Mock();self.w.pool.submit.return_value=Future()
        with self.w.lock:self.w._pending_tick(self.clock(),{})
        row=self.w.pending_reviews[identity(changed)];self.assertEqual(row['fingerprint'],fingerprint(self.view,changed));self.assertNotIn('data',row)
    def test_model_failure_has_a_terminal_error_and_no_approval(self):
        self.w.request_pending_reviews(self.plans,self.view);future=Future();future.set_exception(RuntimeError('memoria insuficiente'))
        self.w.pending_future=future;self.w.pending_batch=self.batch;self.w.pending_queue.clear()
        with self.w.lock:self.w._pending_tick(self.clock(),{})
        for p in self.plans:
            row=self.w.pending_reviews[identity(p)];self.assertEqual(row['state'],'ERROR');self.assertIn('memoria insuficiente',row['error']);self.assertNotIn('data',row)
    def test_fresh_completed_review_is_reused_and_manual_demand_refreshes_it(self):
        self.w.request_pending_reviews(self.plans,self.view);self.w.pending_queue.clear()
        for p in self.plans:self.w.pending_reviews[identity(p)].update(state='COMPLETE',updated=self.clock())
        self.assertFalse(self.w.request_pending_reviews(self.plans,self.view));self.assertEqual(len(self.w.request_pending_reviews(self.plans,self.view,force=True)),2)

class UserFlowTests(unittest.TestCase):
    setUp=ui_fixture.StartupUITests.setUp
    def snapshot(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close);v=e.step();self.app.view=v;self.app.render(v);return v
    def test_bar_and_stage_cells_both_display_measured_coverage(self):
        v=self.snapshot();panel=self.app.panels['BTCUSDm']
        self.assertEqual(panel.verify_bar.options['maximum'],100);self.assertGreater(panel.verify_bar.options['value'],0)
        self.assertLess(panel.verify_bar.options['value'],100);self.assertEqual(len(panel.verify_stages.cells),12)
    def test_selected_pending_button_requests_the_exact_selected_order(self):
        self.snapshot();panel=self.app.panels['BTCUSDm'];panel.tree.selection_set('0');p=panel.rows[0]
        with patch.object(self.app,'open_verification') as show,patch.object(self.app,'request_pending_verification') as request:panel.verify_selected()
        pid=identity({**p,'symbol':'BTCUSDm'});show.assert_called_once_with('BTCUSDm',pid);request.assert_called_once_with('BTCUSDm',pid,True)
    def test_verification_result_does_not_release_an_active_conversation(self):
        self.app.chat_busy=True;self.app._pending_verification_loading=True
        self.app.replies.put({'pending_verification_result':{'ok':True,'job':'x','detail':'Solicitada'}});self.app.poll()
        self.assertTrue(self.app.chat_busy);self.assertFalse(self.app._pending_verification_loading)
    def test_dialog_filters_orders_by_symbol(self):
        v=self.snapshot()
        with patch.object(self.app,'service_dialog',return_value=Widget()),patch.object(Widget,'winfo_exists',return_value=True,create=True):self.app.open_verification('BTCUSDm')
        rows=self.app.pending_verification_tree.items
        self.assertTrue(rows);self.assertTrue(all(row['values'][1]=='BTCUSDm' for row in rows.values()))
    def test_deep_request_is_sent_through_the_actor_bridge(self):
        self.app.chat_busy=True
        with patch.object(self.app.bridge,'request',return_value={'ok':True,'job':'one','detail':'Aceptada'}) as bridge:
            self.app.request_pending_verification('BTCUSDm','BTCUSDm / MT5 #1',True)
            import time
            deadline=time.monotonic()+1
            while not bridge.called and time.monotonic()<deadline:time.sleep(.005)
        self.assertEqual(bridge.call_args.args[0],{'action':'verify_pending','symbol':'BTCUSDm','id':'BTCUSDm / MT5 #1','deep':True})
        self.assertTrue(self.app.chat_busy)
    def test_report_has_stage_evidence_for_every_pending(self):
        v=self.snapshot();m=build_report(v)
        self.assertEqual(len(m['verifications']),len(v['pending_verifications']))
        self.assertTrue(any(str(row[2]).startswith('Verificar') for row in m['tables']['Decisiones']))
    def test_pdf_and_excel_export_include_individual_verification(self):
        v=self.snapshot();m=build_report(v)
        for fmt,suffix in [('pdf','.pdf'),('xlsx','.xlsx')]:
            path=self.root/('verificacion'+suffix);export_report(m,path,fmt,False);self.assertGreater(path.stat().st_size,1000)
        import zipfile
        with zipfile.ZipFile(self.root/'verificacion.xlsx') as z:self.assertTrue(any(b'Verificar' in z.read(n) for n in z.namelist() if n.startswith('xl/worksheets/')))
    def test_closed_gold_is_excluded_from_active_report_verifications(self):
        v=self.snapshot();v['markets']['XAUUSDm']['scheduled_closed']=True;m=build_report(v)
        self.assertTrue(m['verifications']);self.assertTrue(all(r['symbol']=='BTCUSDm' for r in m['verifications']))
