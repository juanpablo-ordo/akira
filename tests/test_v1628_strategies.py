"""Causal entry protection, complete outcomes and prospective strategy evidence."""
import copy,hashlib,json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from dataclasses import replace
from strategy import Plan
from execution import Blocked,OWN_PENDING,MODIFY,BUY_STOP
from engine import Engine
from learning import PendingLearner
from research import ContextWorker
from trade_quality_gate import evaluate,owned_outcomes,family
from strategy_lab import StrategyLab,definitions,propose,advance_case,measured,chart_png,export_html,strategy_text
from tests.fixtures import PendingCase
from tests import test_v1626_verification as previous
from tests import test_v1621_startup as ui_fixture
from tests.test_desktop_flow import Widget

def lab_snapshot(now=1800000000.):
 bar=now-900
 bars=[{'time':bar-(29-i)*900,'open':99.6,'high':100.5,'low':99.4,'close':100.,'tick_volume':100} for i in range(30)]
 info={'bid':100.1,'ask':100.2,'spread':.1,'quote_time':now,'frames':{
  'M15':{'atr':1.,'ema21':99.8,'trend':.5,'rsi':50.,'adx':25.,'volume_ratio':1.,'last_bar':bar},
  'H1':{'trend':.5,'atr':3.}},'bars':{'M15':bars,
   'H1':[{'time':now-3600*(i+1),'open':100.,'high':106.,'low':97.,'close':100.} for i in range(30)]}}
 return {'symbols':{'BTCUSDm':info},'learning_account':[123,'demo'],'build':'TEST_SYNTHETIC',
  'paper_costs':{'BTCUSDm':{'profit_per_price_unit':1.,'round_turn_fee':.01}},'selection_configuration':{'risk':{'max_trade_money':2.17}},'confirmed_strategy_outcomes':[]}

class GateTests(unittest.TestCase):
 def setUp(self):
  self.now=1800000000.;self.plan=NS(symbol='BTCUSDm',side=1,lane='PENDING',kind='LIMIT',key='SWING:TEST',entry=100,sl=99,tp=102,horizon_atr=1)
  bar=NS(time=self.now-900,open=100,close=100.3,high=100.5,low=99.8)
  self.frames={'M15':NS(atr=1,trend=.5,bars=[copy.copy(bar) for i in range(15)]),'H1':NS(trend=.5,bars=[NS(time=self.now-3600)])}
  self.loss={'position_id':50,'symbol':'BTCUSDm','side':1,'pnl':-2.,'closed_at':self.now-30}
 def test_same_side_loss_cannot_be_reset_with_another_candidate_key(self):
  r=evaluate(self.plan,self.frames,[self.loss],self.now);self.assertFalse(r['allowed'])
  self.plan.key='SWING:NEW_LABEL';self.assertFalse(evaluate(self.plan,self.frames,[self.loss],self.now)['allowed'])
 def test_opposite_side_and_other_symbol_do_not_borrow_loss_blocks(self):
  for changed in ({**self.loss,'side':-1},{**self.loss,'symbol':'XAUUSDm'}):self.assertTrue(evaluate(self.plan,self.frames,[changed],self.now)['allowed'])
 def test_fresh_full_structural_candle_can_reset_one_loss(self):
  self.loss['closed_at']=self.now-901
  self.assertTrue(evaluate(self.plan,self.frames,[self.loss],self.now)['allowed'])
 def test_two_same_side_losses_require_aligned_h1_and_m15(self):
  older={**self.loss,'position_id':49,'closed_at':self.now-2000};self.loss['closed_at']=self.now-1000;self.frames['H1'].trend=-.4
  self.assertFalse(evaluate(self.plan,self.frames,[older,self.loss],self.now)['allowed'])
 def test_positive_result_breaks_loss_streak_without_resetting_structure_rules(self):
  self.loss['closed_at']=self.now-1000;win={**self.loss,'position_id':51,'pnl':2,'closed_at':self.now-10}
  self.assertTrue(evaluate(self.plan,self.frames,[self.loss,win],self.now)['allowed'])
 def test_unknown_or_future_outcome_is_not_a_confirmed_loss(self):
  self.assertTrue(evaluate(self.plan,self.frames,[{**self.loss,'closed_at':self.now+1}],self.now)['allowed'])
 def test_missing_structural_data_cannot_have_a_high_quality_entry(self):
  self.assertFalse(evaluate(self.plan,{},[],self.now)['allowed'])
 def test_tiny_stop_is_rejected_without_moving_any_level(self):
  self.plan.sl=99.9;before=copy.deepcopy(vars(self.plan));r=evaluate(self.plan,self.frames,[],self.now)
  self.assertFalse(r['allowed']);self.assertEqual(vars(self.plan),before)
 def test_countertrend_limit_requires_observed_reversal_not_score(self):
  self.frames['H1'].trend=-.5;self.frames['M15'].bars[-1].close=100.05
  self.assertFalse(evaluate(self.plan,self.frames,[],self.now)['allowed'])
 def test_countertrend_future_stop_needs_a_trigger_outside_structure(self):
  self.frames['H1'].trend=-.5;self.frames['M15'].bars[-1].close=100.05;self.plan.kind='STOP'
  self.assertFalse(evaluate(self.plan,self.frames,[],self.now)['allowed']);self.plan.entry=100.6
  self.assertTrue(evaluate(self.plan,self.frames,[],self.now)['allowed'])

class ActorGateTests(PendingCase,unittest.TestCase):
 setUp=previous.EvidenceTests.setUp
 def loss(self,side=None):
  side=self.p['side'] if side is None else side
  self.g.journal.data['positions']['900']={'symbol':'BTCUSDm','side':side,'magic':OWN_PENDING,'lane':'PENDING','plan':{**self.p},
   'initial_sl':self.p['sl'],'closure':{'state':'CONFIRMADO MT5','position_id':900,'symbol':'BTCUSDm','side':side,
    'net':-2,'exit_time':self.clock()-30,'deal_ids':[901,902],'ticket':900,'id':'CLOSE:900:902','exit_deal_id':902,'entry_time':self.clock()-900}}
 def test_gate_blocks_the_actual_send_before_the_broker_request(self):
  self.cfg['mode']='trade';self.loss();p=self.plan();self.api.orders=[];p=replace(p,side=self.p['side'],key='SWING:NEW')
  if p.side!=1:p=replace(p,entry=self.api.ticks[p.symbol].bid+20,sl=self.api.ticks[p.symbol].bid+120,tp=self.api.ticks[p.symbol].bid-180)
  before=len(self.api.sent)
  with self.assertRaisesRegex(Blocked,'posterior al cierre'):self.g.send_immediate_plan(p)
  self.assertEqual(len(self.api.sent),before)
 def runner_after_loss(self):
  self.cfg['mode']='trade';self.cfg['execution']['pending_only']=False;self.loss()
  q=self.g.quote('BTCUSDm');side=self.p['side'];entry=q.ask if side==1 else q.bid
  return q,replace(self.plan(side=side),lane='RUNNER',kind='MARKET',key='RUN:BTCUSDm:NEW',entry=entry,sl=entry-side*100,tp=entry+side*200,bar_time=int(self.clock()-900),signal_timeframe='M15')
 def test_a_rejected_runner_cannot_remove_the_existing_pending_map(self):
  q,p=self.runner_after_loss();before=len(self.api.sent);tickets={o.ticket for o in self.api.orders}
  with patch('engine.runner_plan',return_value=(p,'Nueva tesis simulada')):self.assertFalse(self.e.try_runner(p.symbol,q))
  self.assertEqual({o.ticket for o in self.api.orders},tickets);self.assertEqual(len(self.api.sent),before)
  self.assertEqual(self.e.runner_views[p.symbol]['state'],'RUNNER BLOQUEADO')
  self.assertIn('posterior al cierre',self.e.runner_views[p.symbol]['detail'])
 def test_runner_preview_has_the_same_loss_rejection_as_the_actual_send(self):
  q,p=self.runner_after_loss();before=len(self.api.sent)
  with patch('engine.runner_plan',return_value=(p,'Nueva tesis simulada')):row=self.e.review_runner(p.symbol,q)
  self.assertEqual(row['state'],'RUNNER BLOQUEADO');self.assertIn('posterior al cierre',row['detail'])
  self.assertEqual(len(self.api.sent),before)
 def test_manual_outcomes_cannot_trigger_an_own_loss_guard(self):
  self.loss();self.g.journal.data['positions']['900']['magic']=0
  self.assertEqual(owned_outcomes(self.g),[])
 def test_a_disappeared_position_needs_confirmed_exit_before_reopening(self):
  self.g.journal.data['positions']['999']={'symbol':'BTCUSDm','lane':'PENDING','closed_observed_at':self.clock()-1}
  with self.assertRaisesRegex(Blocked,'aún sin confirmar'):self.e.entry_quality_guard(self.plan(),self.g.snapshot())
 def test_only_owned_same_side_pendings_are_cancelled_after_confirmed_loss(self):
  self.cfg['mode']='trade';self.loss();self.e._confirmed_outcomes=owned_outcomes(self.g);own=[o for o in self.api.orders if o.symbol=='BTCUSDm' and (1 if o.type%2==0 else -1)==self.p['side']]
  manual=copy.copy(own[0]);manual.ticket=777;manual.magic=0;self.api.orders.append(manual)
  before=len(self.api.sent);self.e.review_loss_pendings(self.g.snapshot())
  self.assertTrue(any(o.ticket==777 for o in self.api.orders));self.assertEqual(len(self.api.sent),before+1)
  self.assertFalse(any(o.ticket==own[0].ticket for o in self.api.orders))
 def test_pause_preserves_pending_orders_even_after_loss(self):
  self.cfg['mode']='trade';self.e.paused=True;self.loss();self.e._confirmed_outcomes=owned_outcomes(self.g);before=len(self.api.sent)
  self.e.review_loss_pendings(self.g.snapshot());self.assertEqual(len(self.api.sent),before)
 def test_read_only_verification_cannot_cancel_or_reopen_a_losing_thesis(self):
  self.loss();before=len(self.api.sent)
  self.e.handle_command({'action':'verify_pending','id':self.p['verification_id'],'deep':False});self.e.process_pending_verification()
  self.assertEqual(len(self.api.sent),before)
 def test_pending_only_setting_still_excludes_direct_runner_entries(self):
  self.cfg['execution']['pending_only']=True;self.assertFalse(self.e.try_runner('BTCUSDm',self.g.quote('BTCUSDm')))
  self.assertEqual(self.e.runner_views['BTCUSDm']['state'],'ENTRADAS SOLO PENDIENTES')
 def test_a_rejected_entry_never_has_a_sendable_label_in_its_map(self):
  self.cfg['mode']='trade';self.loss();self.e._confirmed_outcomes=owned_outcomes(self.g);self.api.orders=[]
  rows=self.e.directional_scenarios('BTCUSDm')
  losing=[r for r in rows if r['side']==self.p['side']];self.assertTrue(losing);self.assertTrue(all(not r['sendable'] for r in losing))
 def test_individual_report_shows_the_same_rejection_as_the_actual_entry_gate(self):
  from pending_verification import assess
  self.loss();self.e._confirmed_outcomes=owned_outcomes(self.g);p=Plan(**{k:v for k,v in self.p.items() if k in Plan.__dataclass_fields__})
  self.e.evaluate_entry_quality(p);v=self.e.view();r=assess(v,self.p)
  stage=next(s for s in r['stages'] if s['name']=='Estrategia y tesis');self.assertEqual(stage['state'],'BLOQUEADO');self.assertTrue(stage['critical'])

class CompleteLearningTests(PendingCase,unittest.TestCase):
 def closed(self,profit=2):
  p=self.api.add_position(magic=OWN_PENDING);self.api.record_deal(p,0,p.volume);out=self.api.record_deal(p,1,p.volume,profit);self.api.positions.remove(p)
  return p,out
 def test_associated_nontrade_charge_can_turn_a_small_profit_into_a_real_loss(self):
  p,out=self.closed(.2);fee=copy.copy(out);fee.ticket+=1000;fee.type=7;fee.entry=0;fee.volume=0;fee.profit=-.4;self.api.deals.append(fee)
  learner=PendingLearner(self.g);learner.update();self.assertAlmostEqual(learner.metrics('BTCUSDm')['expectancy'],-.2)
 def test_overclosed_volume_is_not_a_complete_training_case(self):
  p,out=self.closed();out.volume+=.01;learner=PendingLearner(self.g);learner.update()
  self.assertEqual(learner.metrics('BTCUSDm')['samples'],0)
 def test_training_keeps_entry_time_and_strategy_identity(self):
  p,out=self.closed();self.g.journal.data['positions'][str(p.identifier)]={'plan':{'key':'SWING:SNAP:TEST','lane':'PENDING','kind':'LIMIT'}}
  learner=PendingLearner(self.g);learner.update();r=list(learner.records.values())[0]
  self.assertEqual(r['strategy_id'],'PENDIENTE_RETROCESO');self.assertEqual(r['opened_at'],self.clock())

class PaperTests(unittest.TestCase):
 def setUp(self):
  self.case={'created':100,'expiry_seconds':120,'horizon_seconds':120,'state':'WAITING','last_quote':100,
    'plan':{'side':1,'entry':100.,'sl':99.,'tp':102.}}
 def test_buy_limit_requires_ask_touch_not_only_bid(self):
  r=advance_case(self.case,99.9,100.1,108);self.assertEqual(r['state'],'WAITING')
 def test_sell_limit_requires_bid_touch_not_only_ask(self):
  self.case['plan'].update(side=-1,sl=101,tp=98)
  self.assertEqual(advance_case(self.case,99.9,100.1,108)['state'],'WAITING')
 def test_fill_and_tp_are_separate_causal_events_including_costs(self):
  opened=advance_case(self.case,99.8,99.9,108);self.assertEqual(opened['state'],'OPEN')
  result=advance_case(opened,102.1,102.2,116,.05);self.assertEqual(result['state'],'TP');self.assertAlmostEqual(result['net_r'],1.95)
 def test_quote_gap_invalidates_paper_outcome_instead_of_counting_a_win(self):
  opened=advance_case(self.case,99.8,99.9,108)
  r=advance_case(opened,103,103.1,170);self.assertEqual(r['state'],'GAP');self.assertIsNone(r['net_r'])
 def test_adverse_gap_to_stop_is_not_an_optimistic_fixed_one_r_loss(self):
  opened=advance_case(self.case,99.8,99.9,108);r=advance_case(opened,98.5,98.6,116,.05)
  self.assertEqual(r['state'],'SL');self.assertAlmostEqual(r['net_r'],-1.55)
 def test_old_quote_cannot_rewrite_a_completed_result(self):
  opened=advance_case(self.case,99.8,99.9,108);done=advance_case(opened,102.1,102.2,116)
  self.assertEqual(advance_case(done,98,98.1,117),done)
 def test_expired_pending_case_is_not_counted_as_a_win_or_a_loss(self):
  self.case['expiry_seconds']=10;r=advance_case(self.case,100.1,100.2,111)
  self.assertEqual(r['state'],'EXPIRED');self.assertIsNone(r['net_r'])
 def test_no_sample_has_no_percentage(self):
  self.assertIsNone(measured([])['win_rate']);self.assertIsNone(measured([])['expectancy'])
 def test_observed_percentage_keeps_a_sample_and_an_uncertainty_interval(self):
  r=measured([{'pnl':2}]);self.assertEqual(r['win_rate'],1);self.assertEqual(r['n'],1);self.assertLess(r['win_interval'][0],.3)
 def test_drawdown_uses_exit_chronology(self):
  r=measured([{'pnl':-3,'closed_at':3},{'pnl':2,'closed_at':1},{'pnl':2,'closed_at':2}]);self.assertEqual(r['drawdown'],3)

class LabTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.now=1800000000.
  self.snap=lab_snapshot(self.now);self.lab=StrategyLab(self.root,{},lambda:self.now);self.addCleanup(self.lab.close)
 def tick(self):self.lab.submit(self.snap);self.lab.tick();return self.lab.read()
 def test_generated_hypotheses_are_finite_immutable_and_not_live_code(self):
  rows=[d for d in definitions() if d.get('spec')];self.assertEqual(len(rows),12);self.assertEqual(len({r['id'] for r in rows}),12)
  self.assertTrue(all(r['auto_live_activation'] is False for r in rows))
 def test_detection_retains_exact_levels_and_research_only_scope(self):
  p=propose(next(d for d in definitions() if d.get('spec')),'BTCUSDm',self.snap['symbols']['BTCUSDm'],self.now)
  self.assertIsNotNone(p);self.assertLess(p['sl'],p['entry']);self.assertGreater(p['tp'],p['entry']);self.assertTrue(p['research_only'])
 def test_generation_creates_real_case_charts_from_supplied_closed_bars(self):
  r=self.tick();self.assertEqual(r['generated_hypotheses'],12);self.assertEqual(len(r['strategies']),18)
  with self.lab.db() as db:self.assertGreater(db.execute('SELECT COUNT(*) FROM cases').fetchone()[0],0)
  from PIL import Image
  path=next((self.root/'state/strategy_images').glob('*.png'))
  with Image.open(path) as im:self.assertEqual(im.size,(1100,620))
 def test_same_bar_and_strategy_are_not_duplicated_by_quote_refresh(self):
  self.tick()
  with self.lab.db() as db:before=db.execute('SELECT COUNT(*) FROM cases').fetchone()[0]
  self.snap['symbols']['BTCUSDm']['quote_time']+=1;self.now+=1;self.tick()
  with self.lab.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM cases').fetchone()[0],before)
 def test_closed_gold_or_old_quotes_cannot_generate_cases(self):
  self.snap['markets']={'BTCUSDm':{'scheduled_closed':True}};self.tick()
  with self.lab.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM cases').fetchone()[0],0)
 def test_no_comparable_results_keeps_real_percentages_empty(self):
  r=self.tick()
  for row in r['strategies']:
   m=row['symbols']['BTCUSDm'];self.assertIsNone(m['realized']['win_rate']);self.assertEqual(m['state'],'EN ESTUDIO')
  from operation_report import build_report
  report=build_report({'as_of_utc':self.now,'symbols':self.snap['symbols'],'research':{'strategy_lab':r}})
  details=[d[4] for d in report['tables']['Decisiones'] if d[2]=='Estrategia y evidencia']
  self.assertTrue(details);self.assertTrue(all('neto Sin muestra' in d and 'None' not in d for d in details))
 def test_account_change_cannot_reuse_another_accounts_paper_results(self):
  r=self.tick();before=r['strategies'][0]['symbols']['BTCUSDm']['cohort'];self.snap['learning_account']=[999,'demo'];new=self.tick()
  self.assertNotEqual(before,new['strategies'][0]['symbols']['BTCUSDm']['cohort'])
 def test_realized_result_contains_actual_net_cost_not_a_technical_score(self):
  self.snap['confirmed_strategy_outcomes']=[{'symbol':'BTCUSDm','strategy_id':'PENDIENTE_RETROCESO','pnl':-.2,'closed_at':self.now-1}]
  r=self.tick();m=r['strategies'][0]['symbols']['BTCUSDm']['realized'];self.assertEqual(m['n'],1);self.assertAlmostEqual(m['net'],-.2);self.assertEqual(m['win_rate'],0)
 def test_direct_video_reference_is_not_falsely_claimed_as_verified(self):
  self.assertEqual(self.tick()['reference']['state'],'CONTENIDO NO VERIFICADO')
 def test_export_is_readable_and_keeps_case_images(self):
  self.tick();dest=self.root/'download';path=self.lab.export_directory(dest);text=Path(path).read_text()
  self.assertIn('EN ESTUDIO',text);self.assertIn('Sin muestra',text);self.assertTrue(list(dest.glob('*.png')))
 def test_export_escapes_source_names(self):
  r=self.tick();r['strategies'][0]['name']='<script>alert(1)</script>';path=export_html(r,self.root/'safe')
  text=Path(path).read_text();self.assertNotIn('<script>',text);self.assertIn('&lt;script&gt;',text)
 def seed(self,n,future=False):
  r=self.tick();definition=next(d for d in r['strategies'] if d.get('spec'));cohort=definition['symbols']['BTCUSDm']['cohort'];p=propose(definition,'BTCUSDm',self.snap['symbols']['BTCUSDm'],self.now)
  with self.lab.db() as db:
   for i in range(n):
    created=self.now-10000+i*10 if not future else self.now+10000+i*10
    row={'id':'seed'+str(i),'cohort':cohort,'strategy_id':definition['id'],'symbol':'BTCUSDm','created':created,'state':'TP',
     'exit_at':created+5,'plan':p,'net_r':1.,'costs_available':True}
    db.execute('INSERT INTO cases VALUES(?,?,?,?,?)',(row['id'],row['strategy_id'],'BTCUSDm',created,json.dumps(row)))
  return definition['id']
 def test_training_cases_are_never_relabelled_as_holdout(self):
  sid=self.seed(20);r=self.tick();m=next(d for d in r['strategies'] if d['id']==sid)['symbols']['BTCUSDm']
  self.assertEqual(m['holdout']['n'],0);self.assertIsNotNone(m['selection_locked_at']);self.assertEqual(m['state'],'EN ESTUDIO')
 def test_future_case_timestamps_cannot_create_a_validated_percentage(self):
  sid=self.seed(70,future=True);m=next(d for d in self.tick()['strategies'] if d['id']==sid)['symbols']['BTCUSDm']
  self.assertEqual(m['paper']['n'],0);self.assertEqual(m['state'],'EN ESTUDIO')
 def test_many_holdout_cases_in_one_day_do_not_create_twenty_days_of_evidence(self):
  sid=self.seed(70);r=self.tick();m=next(d for d in r['strategies'] if d['id']==sid)['symbols']['BTCUSDm']
  self.assertEqual(m['holdout']['n'],50);self.assertEqual(m['holdout_days'],1);self.assertEqual(m['state'],'EN ESTUDIO')
 def test_raw_chart_cache_pruning_cannot_erase_or_double_count_study_results(self):
  sid=self.seed(70);self.tick()
  with patch('strategy_lab.MAX_CASES',2):
   self.tick();r=self.tick()
  m=next(d for d in r['strategies'] if d['id']==sid)['symbols']['BTCUSDm']
  self.assertEqual(m['paper']['n'],70);self.assertEqual(m['holdout']['n'],50);self.assertEqual(m['paper']['net'],70)
  with self.lab.db() as db:
   self.assertLessEqual(db.execute('SELECT COUNT(*) FROM cases').fetchone()[0],2)
   detail=json.loads(db.execute('SELECT body FROM results WHERE id=?',('seed0',)).fetchone()[0])
  self.assertIn('entry',detail['plan']);self.assertIn('sl',detail['plan']);self.assertIn('tp',detail['plan'])
 def test_gap_and_unknown_cost_results_remain_auditable_without_becoming_wins(self):
  sid=self.seed(2)
  with self.lab.db() as db:
   for i in range(2):
    r=json.loads(db.execute('SELECT body FROM cases WHERE id=?',('seed'+str(i),)).fetchone()[0])
    if i==0:r['state']='GAP'
    else:r['costs_available']=False
    db.execute('UPDATE cases SET body=? WHERE id=?',(json.dumps(r),r['id']))
  m=next(d for d in self.tick()['strategies'] if d['id']==sid)['symbols']['BTCUSDm']
  self.assertEqual(m['paper']['n'],0);self.assertEqual(m['invalid_gaps'],1)
  with self.lab.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM results').fetchone()[0],2)
 def test_a_complete_caption_is_recovered_without_claiming_validated_video_rules(self):
  data=self.lab.set_reference({'url':'https://www.youtube.com/watch?v=p579vzivHoc','status':'transcript','complete':True,
   'body':('EMA RSI gestión de riesgo temporalidad stop. '*40),'caption_type':'automatic_captions','title':'Referencia de prueba'})
  self.assertIn('REGLAS SIN VALIDAR',data['state']);self.assertIn('ema',data['detected_terms'])
  self.assertEqual(self.tick()['reference']['state'],data['state'])
 def test_partial_or_wrong_site_cannot_claim_video_learning(self):
  for row in ({'url':'https://www.youtube.com/watch?v=p579vzivHoc','complete':False,'status':'transcript','body':'EMA '*1000},
      {'url':'https://fake.example/watch?v=p579vzivHoc','complete':True,'status':'transcript','body':'EMA '*1000}):
   with self.assertRaises(ValueError):self.lab.set_reference(row)

class DirectoryUITests(unittest.TestCase):
 setUp=ui_fixture.StartupUITests.setUp
 def test_undefined_strategy_results_remain_missing_in_user_text(self):
  text=strategy_text(definitions()[0],'BTCUSDm')
  self.assertIn('Resultado neto: Sin muestra; media: Sin muestra',text)
  self.assertNotIn('None',text)
  self.assertIn('Sin muestra; no se calcula un porcentaje',text)
 def test_directory_has_ordered_btc_and_gold_rows_without_a_fake_percentage(self):
  self.app.view={'symbols':{'BTCUSDm':{},'XAUUSDm':{}},'research':{}}
  with patch.object(self.app,'service_dialog',return_value=Widget()),patch.object(Widget,'winfo_exists',return_value=True,create=True),patch('strategy_directory.tk.PanedWindow',Widget),patch('strategy_directory.ttk.Treeview',Widget):self.app.open_strategy_directory()
  self.assertEqual(len(self.app.strategy_tree.items),36);self.assertIn('Sin muestra',self.app.strategy_details.text)
 def test_strategy_export_result_never_releases_an_active_conversation(self):
  self.app.chat_busy=True;self.app.strategy_export_button=Widget()
  self.app.replies.put({'strategy_export_result':{'ok':True,'path':'example.html'}});self.app.poll()
  self.assertTrue(self.app.chat_busy);self.assertEqual(self.app.strategy_export_button.options['state'],'normal')
