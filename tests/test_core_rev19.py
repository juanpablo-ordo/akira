import unittest,json,io,threading,socket
from unittest.mock import Mock,patch
from dataclasses import replace
from types import SimpleNamespace as NS
from datetime import datetime,timezone
from tests.fixtures import PendingCase
from tests.review_fixture import approve_exact
from engine import Engine
from execution import Blocked
from execution_review import request_id,validate,fingerprint
from chat_orchestrator import TurnBudget,AIHealthMonitor
from ai_providers import AIProviderManager,CloudAIProvider,validate_endpoint
from network_diagnostics import SourceHealthManager,classify_failure
from locale_time import LocaleTimeSettings
from runner_policy import RunnerExitPolicy
from risk_limits import configured_limits
from settings import DEFAULT,load_config
class ExactExecution(PendingCase,unittest.TestCase):
 live_review_guard=True
 def setUp(self):
  super().setUp();self.cfg['mode']='observe';self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close);self.e.step();self.cfg['mode']='trade';self.p=self.plan();self.volume=.01
 def test_no_approval_means_no_order(self):
  with self.assertRaisesRegex(Blocked,'IA obligatoria'):self.g.send_immediate_plan(self.p)
  self.assertFalse(self.api.sent)
 def test_no_reviewer_cannot_bypass(self):
  del self.g.pending_review_guard
  with self.assertRaisesRegex(Blocked,'IA obligatoria'):self.g.send_immediate_plan(self.p)
  self.assertFalse(self.api.sent)
 def test_exact_review_is_audited(self):
  approve_exact(self.e,self.p,self.volume);r=self.e.pending_review_guard(self.p,self.g.snapshot(),self.volume)
  self.assertIn(r['fingerprint'],self.g.journal.data['execution_reviews'])
 def test_approved_order_sends_once_and_reconciles(self):
  prepared=self.g.prepare(self.p);approve_exact(self.e,prepared.plan,prepared.request['volume'])
  self.assertTrue(self.g.send_immediate_plan(self.p));self.assertEqual(len(self.api.sent),1)
  with self.assertRaises(Blocked):self.g.send_immediate_plan(self.p)
  self.g.reconcile(self.g.snapshot());self.assertTrue(self.g.journal.data['orders']);self.assertEqual(len(self.api.sent),1)
 def test_changed_levels_volume_account_or_indicators_invalidate(self):
  for key in ('sl','tp','volume','account','indicators'):
   self.e.planner.research_context['pending_reviews']={};approve_exact(self.e,self.p,self.volume)
   p=replace(self.p,**{key:getattr(self.p,key)+.01}) if key in ('sl','tp') else self.p
   if key=='account':self.api.account.equity+=.1
   if key=='indicators':
    f=self.e.planner.caches[p.symbol].frames['H1'];self.e.planner.caches[p.symbol].frames['H1']=replace(f,rsi=f.rsi+.1)
   with self.subTest(key=key),self.assertRaises(Blocked):self.e.pending_review_guard(p,self.g.snapshot(),self.volume+.01 if key=='volume' else self.volume)
 def test_timeout_rejection_expiry_malformed_never_approve(self):
  for mode in ('expired','error','reject','malformed'):
   self.e.planner.research_context['pending_reviews']={};r,p,s=approve_exact(self.e,self.p,self.volume)
   if mode=='expired':r['updated']-=181
   elif mode=='error':r['state']='ERROR'
   elif mode=='reject':r['data']['verdict']='REJECT'
   else:r['data']['evidence']=['invented.fact']
   with self.subTest(mode=mode),self.assertRaises(Blocked):self.e.pending_review_guard(self.p,self.g.snapshot(),self.volume)
 def test_research_refresh_retains_review_account_and_evidence(self):
  r,p,s=approve_exact(self.e,self.p,self.volume);fresh=self.e.research_snapshot()
  self.assertEqual(fingerprint(p,s),fingerprint(p,fresh))
 def test_historical_and_demo_profile_enforcement(self):
  for profile,mode in [('HISTORICAL',0),('DEMO_EXPERIMENT',2)]:
   self.cfg['operation_profile']=profile;self.api.account.trade_mode=mode
   with self.subTest(profile=profile),self.assertRaises(Blocked):self.g.permissions(self.g.snapshot())
class ProvidersAndBudgets(unittest.TestCase):
 def setUp(self):self.cfg=load_config(DEFAULT)
 def test_phase_budgets_are_independent(self):
  now=[0];b=TurnBudget(clock=lambda:now[0]);b.remaining('prepare');now[0]=170
  self.assertEqual(b.remaining('sources'),35);self.assertEqual(b.remaining('conversation'),150)
  now[0]+=10;self.assertEqual(b.remaining('sources'),25)
 def test_cloud_mode_never_secretly_calls_local(self):
  self.cfg['assistant']['provider_mode']='cloud';local=Mock();self.assertEqual(AIProviderManager(self.cfg).run('conversation',local,lambda:'answer'),'answer');local.assert_not_called()
 def test_auto_fallback_records_real_provider(self):
  self.cfg['assistant'].update(provider_mode='auto',provider_primary='cloud');h=AIHealthMonitor()
  self.assertEqual(AIProviderManager(self.cfg,h).run('conversation',lambda:'local',Mock(side_effect=TimeoutError('cloud'))),'local');self.assertEqual(h.snapshot()['provider'],'local');self.assertTrue(h.snapshot()['ready'])
 def test_stream_emits_real_tokens_and_rejects_truncation(self):
  self.cfg['assistant'].update(cloud_endpoint='http://127.0.0.1/v1/chat/completions',general_model='fixture')
  for finish in ('stop','length'):
   raw='data: '+json.dumps({'choices':[{'delta':{'content':'hola'},'finish_reason':None}]})+'\n'
   raw+='data: '+json.dumps({'choices':[{'delta':{},'finish_reason':finish}]})+'\ndata: [DONE]\n';events=[]
   provider=CloudAIProvider(self.cfg,Mock(return_value=io.BytesIO(raw.encode())))
   if finish=='stop':self.assertEqual(provider.complete([],progress=events.append),'hola');self.assertEqual(events,['hola'])
   else:
    with self.assertRaises(ValueError):provider.complete([])
 def test_cancel_prevents_start_and_fallback(self):
  cancel=threading.Event();cancel.set();local=Mock();cloud=Mock()
  with self.assertRaises(RuntimeError):AIProviderManager(self.cfg).run('conversation',local,cloud,cancel)
  local.assert_not_called();cloud.assert_not_called()
 def test_endpoints_cannot_send_plaintext_or_inline_credentials(self):
  for url in ('http://example.org/v1/chat/completions','https://key:secret@x/v1/chat/completions','https://x/v1/chat/completions?key=x'):
   with self.assertRaises(ValueError):validate_endpoint(url)
 def test_contradictions_and_invented_proof_cannot_approve(self):
  for proof,conflict in [(['order.entry','H1.atr'],['SL invertido']),(['order.entry','H1.fake'],[])]:
   with self.assertRaises(ValueError):validate({'verdict':'APPROVE','reason':'test','contradictions':conflict,'evidence':proof,'missing':[]},{'order.entry':10,'H1.atr':1})
 def test_dns_backoff_does_not_block_another_domain(self):
  now=[0];h=SourceHealthManager(clock=lambda:now[0],jitter=lambda:1)
  for n in range(3):h.failure('a',socket.gaierror(11002,'getaddrinfo failed'),'https://a?token=secret')
  r=h.snapshot()['a'];self.assertEqual(r['kind'],'DNS_ERROR');self.assertTrue(r['circuit_open']);self.assertEqual(r['retry_after_seconds'],120);self.assertTrue(h.permitted('b'));self.assertFalse(h.permitted('a'));h.success('a');self.assertTrue(h.permitted('a'))
 def test_source_statuses_remain_distinct(self):
  from urllib.error import HTTPError
  for status,kind in [(401,'AUTH_ERROR'),(403,'ACCESS_DENIED'),(429,'QUOTA_EXCEEDED'),(500,'HTTP_ERROR')]:self.assertEqual(classify_failure(HTTPError('https://x',status,'bad',{},None))['kind'],kind)
 def test_automatic_youtube_is_disabled_even_with_old_opt_in(self):
  import tempfile
  from research import ContextWorker
  self.cfg['research']['youtube']=True
  with tempfile.TemporaryDirectory() as root:
   w=ContextWorker(self.cfg,root)
   try:self.assertFalse(w.source_enabled('youtube'));self.assertFalse(w.source_enabled('strategy_reference'))
   finally:w.close()
class RiskTimeRunner(unittest.TestCase):
 def test_risk_display_and_engine_arithmetic_agree(self):
  c=load_config(DEFAULT);c['capital_protection'].update(enabled=True,trade_pct=100);c['risk'].update(max_trade_money=11,max_trade_pct=6,min_lot_structural_override_enabled=False)
  r=configured_limits(c,{'balance':45.82,'equity':45.82});self.assertAlmostEqual(r['per_trade'],2.7492);self.assertEqual(r['explanation']['binding_rules'],['risk.max_trade_pct'])
 def test_dst_is_presentation_only(self):
  z=LocaleTimeSettings.from_config({'locale':{'timezone':'America/New_York'}});t=datetime(2026,11,1,5,30,tzinfo=timezone.utc).timestamp();self.assertEqual(z.format(t),z.format(t+3600));self.assertNotEqual(LocaleTimeSettings.from_config({'locale':{'timezone':'Europe/Madrid'}}).format(t),z.format(t))
 def test_h1_pending_requires_closed_h1_after_entry(self):
  cfg=load_config(DEFAULT);p={'lane':'PENDING','key':'SWING:1:LIMIT:H1:1','bar_time':0};bars=[NS(time=t,open=100,high=102,low=98,close=99) for t in (0,3600,7200,10800)];bars[-1].close=90;f=NS(bars=bars,atr=2,trend=-1)
  self.assertFalse(RunnerExitPolicy.evaluate(p,{'M15':f},1,-.5,cfg,entry_time=1,now=14400)['exit'])
  r=RunnerExitPolicy.evaluate(p,{'H1':f},1,-.5,cfg,entry_time=1,now=14400);self.assertTrue(r['exit']);self.assertEqual(r['timeframe'],'H1')
if __name__=='__main__':unittest.main()
