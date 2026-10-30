"""Behavioral checks for account safety, usable downloads, persistence and new feeds."""
import copy,csv,hashlib,io,json,queue,tempfile,threading,time,unittest
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from settings import DEFAULT,load_config
from tests.fixtures import PendingCase
from tests import test_v152_reports as reports
from engine import Engine
from execution import Blocked,MarketPaused
from market_calendar import state_for
from operation_report import build_report
from assistant_akira import AkiraAssistant
from chat_store import ChatStore
from global_sources import market_feed,market_consensus,fred_macro,news_feed
from quality_study import QualityStudy
from paired_study import PROTOCOL,replay,compare,load_quotes
from reference_library import import_document,seed_library
from voice_session import VoiceSession,install_voice
from build_windows import build_command

class ChatPersistenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.cfg=load_config(DEFAULT)
 def test_topics_survive_switch_and_restart(self):
  bot=AkiraAssistant(self.cfg,self.root);first=bot.chats.active;bot._remember_turn('Explícame la novela','Una novela es narrativa extensa.');bot.switch_chat(new=True)
  bot._remember_turn('Programemos un cliente HTTP','Utilicemos un cliente con timeout.');second=bot.chats.active
  bot.switch_chat(first);self.assertIn('novela',bot.history[0]['text']);self.assertNotIn('HTTP',str(bot.history))
  restored=AkiraAssistant(self.cfg,self.root);self.assertEqual(restored.chats.active,first);restored.switch_chat(second);self.assertIn('HTTP',restored.history[0]['text'])
 def test_clear_never_resurrects_legacy_context_or_erases_memories(self):
  bot=AkiraAssistant(self.cfg,self.root);bot._remember_turn('Mi tema es astronomía','Estudiamos estrellas.');bot.chats.remember('Me interesa astronomía');bot.clear_chat()
  restored=AkiraAssistant(self.cfg,self.root);self.assertEqual(restored.history,[]);self.assertEqual(restored.dialogue.previous_question(),'');self.assertEqual(len(restored.chats.memories()),1)
 def test_delete_only_removes_selected_topic(self):
  store=ChatStore(self.root);first=store.active;store.append('user','Tema A');second=store.create();store.append('user','Tema B');store.delete(first)
  self.assertEqual(store.history(cid=second)[0]['text'],'Tema B');self.assertNotIn(first,[r['id'] for r in store.list()])
 def test_related_context_is_bounded_and_excludes_active_chat(self):
  store=ChatStore(self.root);store.append('user','Astronomía estrellas galaxias');store.create();store.append('user','Astronomía en el tema actual')
  rows=store.related('Astronomía estrellas');self.assertEqual(len(rows),1);self.assertNotEqual(rows[0]['chat'],store.active)
 def test_casual_queries_never_research_or_use_paid_api(self):
  bot=AkiraAssistant(self.cfg,self.root)
  with patch.object(bot,'_reply',side_effect=AssertionError('Investigación casual')):
   for text in ('hola','cómo estás','cómo te llamas','quién eres'):
    answer=bot.reply(text,{});self.assertTrue(answer);self.assertLess(len(answer),400)
 def test_explicit_memory_is_removable(self):
  bot=AkiraAssistant(self.cfg,self.root);bot.reply('recuerda que prefiero respuestas en español',{})
  row=bot.chats.memories()[0];self.assertIn('español',row['body']);bot.chats.forget(row['id']);self.assertFalse(bot.chats.memories())
 def test_general_model_receives_authorized_cross_chat_memory(self):
  bot=AkiraAssistant(self.cfg,self.root);bot.chats.remember('Prefiero poemas breves');bot._remember_turn('Estudiemos poesía','Analicemos verso.');bot.switch_chat(new=True)
  captured=[]
  def reply(message,snapshot,use_cloud):captured.append(snapshot);return 'Continuamos con poesía.'
  with patch.object(bot,'_reply',side_effect=reply):bot.reply('Seguimos con poesía',{})
  self.assertIn('Prefiero poemas breves',captured[0]['conversation_memory']['saved']);self.assertTrue(captured[0]['conversation_memory']['related_chats'])
 def test_document_chunks_retrieve_actual_content(self):
  path=self.root/'apuntes.txt';path.write_text('El ritmo musical organiza duraciones y acentos.');result=import_document(self.root,path)
  rows=seed_library(self.root).search('ritmo musical');self.assertTrue(any('acentos' in r['summary'] and r['kind']=='document' for r in rows));self.assertEqual(result['chunks'],1)
 def test_reference_notes_are_not_current_source_evidence(self):
  store=seed_library(self.root);row=store.search('probabilidad')[0];self.assertEqual(row['kind'],'reference');self.assertIn('no hechos actuales',row['published'])

class MarketAndRiskTests(PendingCase,unittest.TestCase):
 def test_saturday_only_btc_is_evaluated_and_printed(self):
  self.clock.now=datetime(2026,10,10,14,tzinfo=timezone.utc).timestamp()
  self.api.set_quote('BTCUSDm',self.api.ticks['BTCUSDm'].bid,fill=False)  # no fresh gold tick during weekend
  engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(engine.close)
  original=self.api.copy_rates_from_pos;requests=[]
  def rates(symbol,*args):requests.append(symbol);return original(symbol,*args)
  with patch.object(self.api,'copy_rates_from_pos',side_effect=rates):view=engine.step()
  self.assertTrue(view['markets']['XAUUSDm']['scheduled_closed']);self.assertEqual(view['status']['XAUUSDm']['state'],'MERCADO CERRADO');self.assertNotIn('XAUUSDm',requests)
  self.assertTrue(all(r['symbol']!='XAUUSDm' for r in self.api.sent));self.assertFalse(view['markets']['BTCUSDm']['scheduled_closed'])
 def test_extraordinary_broker_closure_is_applied_at_gateway(self):
  now=datetime.fromtimestamp(self.clock(),timezone.utc);self.cfg['market_hours']={'closures':[{'symbol':'BTCUSDm','start':now.isoformat(),'end':datetime.fromtimestamp(self.clock()+3600,timezone.utc).isoformat(),'reason':'Mantenimiento anunciado','source':'Comunicado del bróker'}]}
  with self.assertRaisesRegex(MarketPaused,'Mantenimiento anunciado'):self.g.quote('BTCUSDm')
  self.assertFalse(self.api.sent)
 def test_weekend_does_not_drop_existing_gold_reserved_risk(self):
  self.api.add_pending(self.plan('XAUUSDm'));self.clock.now=datetime(2026,10,10,14,tzinfo=timezone.utc).timestamp()
  ledger=self.g.reservation_ledger(self.g.snapshot());self.assertGreater(ledger['reserved_usd'],0)
  engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(engine.close);view=engine.step();model=build_report(view)
  self.assertGreater(model['snapshot']['portfolio_risk']['reserved_usd'],0);self.assertTrue(all(r[1]!='XAUUSDm' for r in model['tables']['Pendientes']))
 def test_risk_ack_invalidates_cached_allocation_and_changes_send(self):
  engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(engine.close);engine.map_cache['old']={};engine.allocation_cache['old']={}
  self.cfg['risk']['max_trade_money']=.01;self.cfg['risk']['min_lot_structural_override_enabled']=False
  result=engine.handle_command({'action':'risk_settings'});self.assertAlmostEqual(result['trade_risk_cap'],.01);self.assertFalse(engine.map_cache);self.assertFalse(engine.allocation_cache)
  with self.assertRaises(Blocked):self.g.send_immediate_plan(self.plan())
  self.assertFalse(self.api.sent)
 def test_weekday_stale_tick_is_connection_pause_not_weekend(self):
  self.clock.advance(1000)
  with self.assertRaisesRegex(MarketPaused,'Sin cotización nueva'):self.g.quote('XAUUSDm')
 def test_holiday_configuration_rejects_naive_dates(self):
  cfg=copy.deepcopy(DEFAULT);cfg['market_hours']={'closures':[{'symbol':'XAUUSDm','start':'2026-12-25T00:00','end':'2026-12-26T00:00'}]}
  with self.assertRaisesRegex(ValueError,'Horario extraordinario'):load_config(cfg)

class PublicFeedsTests(unittest.TestCase):
 def test_coinbase_uses_spot_usd_and_keeps_missing_provider_timestamp_explicit(self):
  row=market_feed('Coinbase',lambda url:{'bids':[['100','2','1']],'asks':[['101','1','1']]},lambda:1000)
  self.assertEqual(row['quote'],'USD');self.assertIsNone(row['market_time']);self.assertIn('sin timestamp',row['timestamp_quality']);self.assertGreater(row['imbalance'],0)
 def test_okx_funding_and_interest_are_typed(self):
  def fetch(url):
   if 'market/books' in url:return {'code':'0','data':[{'bids':[['100','1']],'asks':[['101','1']],'ts':'1000000'}]}
   return {'code':'0','data':[{'fundingRate':'0.0001','oiUsd':'2000000'}]}
  row=market_feed('OKX',fetch,lambda:1000);self.assertAlmostEqual(row['funding'],.0001);self.assertEqual(row['open_interest_usd'],2000000)
 def test_crossed_and_old_orderbooks_are_rejected(self):
  with self.assertRaises(ValueError):market_feed('Coinbase',lambda u:{'bids':[['102','1']],'asks':[['101','1']]})
  with self.assertRaises(ValueError):market_feed('Bybit',lambda u:{'retCode':0,'result':{'b':[['100','1']],'a':[['101','1']],'ts':'1000'}},lambda:1000)
 def test_correlated_venues_are_one_bounded_component(self):
  rows=[{'asset':'BTC','updated':1000,'imbalance':.9} for _ in range(4)];bias,weight,_=market_consensus(rows,1000)
  self.assertAlmostEqual(bias,.9);self.assertLessEqual(weight,.12)
  self.assertEqual(market_consensus(rows[:1],1000)[1],0);self.assertEqual(market_consensus(rows,2000)[1],0)
 def test_fred_observation_dates_and_daily_frequency_are_preserved(self):
  def fetch(url):
   series='DGS10' if 'DGS10' in url else 'DFII10' if 'DFII10' in url else 'DTWEXBGS'
   return 'observation_date,'+series+'\n2026-10-08,3.5\n2026-10-09,3.6\n'
  now=datetime(2026,10,10,tzinfo=timezone.utc).timestamp();result=fred_macro(fetch,lambda:now)
  self.assertEqual(len(result['rows']),3);self.assertEqual(result['rows'][0]['date'],'2026-10-09');self.assertIn('retraso',result['rows'][0]['frequency'])
 def test_news_duplicates_and_future_dates_do_not_vote(self):
  items=[{'title':'A','date':'Sat, 10 Oct 2026 01:00:00 GMT'},{'title':'A','date':'Sat, 10 Oct 2026 01:00:00 GMT'},{'title':'Futuro','date':'Fri, 10 Oct 2030 01:00:00 GMT'},{'title':'Sin fecha'}]
  with patch('global_sources.parse_rss',return_value=items),patch('global_sources.time.time',return_value=datetime(2026,10,10,2,tzinfo=timezone.utc).timestamp()):rows=news_feed('SEC')
  self.assertEqual(len(rows),2);self.assertFalse(next(r for r in rows if r['title']=='Sin fecha')['verified_publication'])
 def test_cloud_permission_gates_background_research(self):
  from research import ContextWorker
  with tempfile.TemporaryDirectory() as tmp:
   cfg=load_config(DEFAULT);cfg['research']['cloud']=True;cfg['assistant']['cloud']=False;worker=ContextWorker(cfg,Path(tmp));self.addCleanup(worker.close)
   self.assertNotIn('cloud',worker.jobs_for({'symbols':{'BTCUSDm':{}}},{}))
   with patch('research.openai_responses',side_effect=AssertionError('Paid API')):
    with self.assertRaisesRegex(RuntimeError,'OpenAI desactivado'):worker._summary({}, {},True)

class ComparisonTests(unittest.TestCase):
 def setUp(self):
  self.protocol={**PROTOCOL,'horizon_seconds':100,'entry_expiry_seconds':40,'maximum_quote_gap_seconds':10}
  self.plan={'side':'BUY','kind':'LIMIT','entry':100,'sl':98,'tp':104,'lane':'PENDING'}
  self.quotes=[{'utc':t,'bid':100,'ask':101,'cost_r':.01} for t in range(1000,1101,5)]
 def test_limit_activation_requires_ask_touch_not_bid_touch(self):
  result=replay(self.plan,self.quotes,1000,self.protocol);self.assertEqual(result['state'],'NO ACTIVADA');self.assertEqual(result['net_r'],0)
 def test_long_exit_uses_bid_and_deducts_supplied_cost(self):
  self.quotes[1].update(bid=99.8,ask=100);self.quotes[2].update(bid=104,ask=104.2)
  result=replay(self.plan,self.quotes,1000,self.protocol);self.assertEqual(result['state'],'TP');self.assertAlmostEqual(result['net_r'],1.99)
 def test_stop_gap_can_lose_more_than_one_r(self):
  self.quotes[1].update(bid=99.8,ask=100);self.quotes[2].update(bid=96,ask=96.2)
  result=replay(self.plan,self.quotes,1000,self.protocol);self.assertLess(result['net_r'],-1)
 def test_quotes_with_a_gap_never_produce_comparable_result(self):
  rows=self.quotes[:3]+self.quotes[10:];self.assertFalse(replay(self.plan,rows,1000,self.protocol)['complete'])
 def test_completed_gold_trade_survives_later_market_pause(self):
  rows=copy.deepcopy(self.quotes[:3]);rows[1].update(bid=99.8,ask=100);rows[2].update(bid=104,ask=104.2)
  rows.append({**self.quotes[-1],'utc':1100})
  result=replay(self.plan,rows,1000,self.protocol);self.assertTrue(result['complete']);self.assertEqual(result['state'],'TP')
 def test_pending_expiry_does_not_require_unused_future_horizon(self):
  result=replay(self.plan,self.quotes[:9],1000,self.protocol)
  self.assertTrue(result['complete']);self.assertEqual(result['state'],'NO ACTIVADA')
 def test_unresolved_active_trade_requires_complete_future_horizon(self):
  rows=copy.deepcopy(self.quotes[:9]);rows[1].update(bid=99.8,ask=100)
  self.assertFalse(replay(self.plan,rows,1000,self.protocol)['complete'])
 def test_references_imported_after_decision_window_are_excluded(self):
  cases={'c':{'symbol':'BTCUSDm','at':1000,'bar':900,'plan':self.plan}}
  refs=[{'id':1,'case_id':'c','source':'ChatGPT proporcionado','at':1200,'plan':self.plan,'prospective':False}]
  result=compare(cases,refs,{'BTCUSDm':self.quotes},self.protocol);self.assertFalse(result['paired']);self.assertEqual(len(result['discarded']),1)
 def test_small_sample_never_confirms_superiority(self):
  cases={'c':{'symbol':'BTCUSDm','at':1000,'bar':900,'plan':self.plan}}
  refs=[{'id':1,'case_id':'c','source':'Recomendación real','at':1000,'plan':self.plan,'prospective':True}]
  result=compare(cases,refs,{'BTCUSDm':self.quotes},self.protocol);self.assertFalse(result['superiority_confirmed']);self.assertFalse(result['groups']['BTCUSDm / PENDING']['advantage_in_quote_replay'])
 def test_live_capture_deduplicates_same_bar_and_rejects_preview(self):
  with tempfile.TemporaryDirectory() as tmp:
   study=QualityStudy(tmp);snapshot={'connected':True,'as_of_utc':1000,'symbols':{'BTCUSDm':{'frames':{'M15':{'last_bar':900}},'scenario_book':[self.plan]}}}
   study.capture(snapshot);study.capture({**snapshot,'as_of_utc':1001});self.assertEqual(study.summary()['cases']['BTCUSDm'],1)
   with self.assertRaises(ValueError):study.capture({**snapshot,'preview':True})
 def test_import_rolls_back_whole_file_on_invalid_geometry(self):
  with tempfile.TemporaryDirectory() as tmp:
   study=QualityStudy(tmp);study.capture({'connected':True,'as_of_utc':1000,'symbols':{'BTCUSDm':{'frames':{'M15':{'last_bar':900}},'scenario_book':[self.plan]}}});cid=study.cases()[0]['id'];path=Path(tmp)/'refs.csv'
   path.write_text('case_id,symbol,source,created_utc,side,kind,entry,sl,tp\n'+cid+',BTCUSDm,ChatGPT,1001,BUY,LIMIT,100,98,104\n'+cid+',BTCUSDm,Otro,1002,BUY,LIMIT,100,102,104\n')
   with self.assertRaises(ValueError):study.import_references(path)
   with study.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM references_imported').fetchone()[0],0)

class RecordedStudyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.study=QualityStudy(self.tmp.name)
  self.plan={'side':1,'kind':'LIMIT','lane':'PENDING','entry':100,'sl':98,'tp':104}
  self.snapshot={'connected':True,'as_of_utc':1000,'account':{'login':123,'server':'Broker de prueba'},'symbols':{'BTCUSDm':{'bid':101,'ask':101.1,'quote_time':999,'frames':{'M15':{'last_bar':900}},'scenario_book':[self.plan]}}}
 def test_recording_is_immutable_and_does_not_inflate_repeated_snapshot(self):
  self.study.capture(self.snapshot);self.study.capture(self.snapshot)
  self.assertEqual(self.study.summary()['recorded_quotes'],{'BTCUSDm':1});self.assertEqual(len(self.study.cases()),1)
 def test_stale_future_or_crossed_quotes_cannot_enter_recorded_evidence(self):
  for change in ({'quote_time':900},{'quote_time':1010},{'ask':100}):
   snap=copy.deepcopy(self.snapshot);snap['symbols']['BTCUSDm'].update(change);self.study.capture(snap)
  self.assertFalse(self.study.summary()['recorded_quotes']);self.assertFalse(self.study.cases())
 def test_closed_gold_and_execution_guard_do_not_create_quotes(self):
  snap=copy.deepcopy(self.snapshot);snap['symbols']['XAUUSDm']=snap['symbols']['BTCUSDm'];snap['markets']={'XAUUSDm':{'scheduled_closed':True}}
  self.study.capture(snap);self.assertEqual(self.study.summary()['recorded_quotes'],{'BTCUSDm':1})
  snap['as_of_utc']=1001;snap['execution_block']='Cuenta cambió';self.study.capture(snap);self.assertEqual(self.study.summary()['recorded_quotes'],{'BTCUSDm':1})
 def test_accounts_keep_separate_case_provenance(self):
  self.study.capture(self.snapshot);other=copy.deepcopy(self.snapshot);other['account']['login']=456;self.study.capture(other)
  self.assertEqual(len(self.study.cases()),2)
  with self.study.db() as db:self.assertEqual(db.execute('SELECT count(DISTINCT provider) FROM quotes').fetchone()[0],2)
 def test_recorded_replay_uses_real_reference_and_declared_cost_without_csv_ticks(self):
  self.study.capture(self.snapshot);cid=self.study.cases()[0]['id'];provider=self.study.provider(self.snapshot)
  reference=Path(self.tmp.name)/'reference.csv';reference.write_text('case_id,symbol,source,created_utc,side,kind,entry,sl,tp\n'+cid+',BTCUSDm,ChatGPT,1000,BUY,LIMIT,100,98,104\n')
  self.study.import_references(reference)
  with self.study.db() as db:
   db.executemany('INSERT INTO quotes VALUES (?,?,?,?,?)',[('BTCUSDm',at,provider,99.9 if at==1060 else 104,100 if at==1060 else 104.1) for at in range(1060,87401,60)])
  result=self.study.evaluate_recorded(.1);self.assertTrue(result['paired'][0]['complete']);self.assertAlmostEqual(result['paired'][0]['akira']['net_r'],1.9)
  self.assertFalse(result['superiority_confirmed']);self.assertIn('Muestras cada 30 s',result['source_provenance']);self.assertIn('puede omitir',result['scope'])
 def test_costs_and_original_quote_provenance_are_required(self):
  for cost in (None,-1,float('nan')):
   with self.assertRaises(ValueError):self.study.evaluate_recorded(cost)
  with self.assertRaisesRegex(ValueError,'Todavía no hay'):self.study.evaluate_recorded(0)
 def test_template_does_not_invent_when_chatgpt_created_its_recommendation(self):
  self.study.capture(self.snapshot);path=Path(self.tmp.name)/'template.csv';self.study.reference_template(path)
  with path.open(encoding='utf-8-sig') as stream:row=next(csv.DictReader(stream))
  self.assertEqual(row['created_utc'],'');self.assertEqual(row['captured_utc'],'1970-01-01T00:16:40+00:00')
 def test_imported_reference_count_is_visible_to_a_new_report_reader(self):
  self.study.capture(self.snapshot);cid=self.study.cases()[0]['id'];path=Path(self.tmp.name)/'refs.csv'
  path.write_text('case_id,symbol,source,created_utc,side,kind,entry,sl,tp\n'+cid+',BTCUSDm,ChatGPT,1000,BUY,LIMIT,100,98,104\n')
  self.study.import_references(path);self.study.import_references(path)
  self.assertEqual(QualityStudy(self.tmp.name).summary()['comparisons'],1)
 def test_real_iso_date_requires_timezone_and_matches_prospective_case(self):
  self.study.capture(self.snapshot);cid=self.study.cases()[0]['id'];path=Path(self.tmp.name)/'reference.csv'
  header='case_id,symbol,source,created_utc,side,kind,entry,sl,tp\n'
  path.write_text(header+cid+',BTCUSDm,ChatGPT,1970-01-01T00:16:40,BUY,LIMIT,100,98,104\n')
  with self.assertRaisesRegex(ValueError,'zona UTC'):self.study.import_references(path)
  path.write_text(header+cid+',BTCUSDm,ChatGPT,1970-01-01T00:16:40Z,BUY,LIMIT,100,98,104\n');self.study.import_references(path)
  with self.study.db() as db:self.assertEqual(db.execute('SELECT prospective FROM references_imported').fetchone()[0],1)

class VoiceLifecycleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.events=[];self.session=VoiceSession(self.tmp.name,self.events.append,{}, {'engine':'system','id':'system:test'})
 def test_call_does_not_open_microphone_until_start_is_chosen(self):
  self.assertFalse(self.session.started);self.assertIsNone(self.session.stream);self.assertFalse(self.session._threads)
 def test_pause_and_cancel_clear_pending_audio_and_invalidate_recognition(self):
  self.session.audio.put('audio');before=self.session._revision;self.session.pause();self.assertTrue(self.session.audio.empty());self.assertGreater(self.session._revision,before)
  self.session.last_text='mensaje';self.session.cancel_message();self.assertEqual(self.session.last_text,'');self.assertTrue(any(e['kind']=='partial' and not e['text'] for e in self.events))
 def test_stop_releases_input_and_interrupts_speech(self):
  stream=NS(abort=lambda:self.events.append({'kind':'aborted'}));process=NS(poll=lambda:None,terminate=lambda:self.events.append({'kind':'terminated'}))
  self.session.stream=stream;self.session.process=process;self.session.stop();self.assertTrue(self.session.stop_event.is_set());self.assertTrue(any(e['kind']=='aborted' for e in self.events));self.assertTrue(any(e['kind']=='terminated' for e in self.events))
 def test_second_speech_cannot_start_over_first(self):
  self.session.speaking.set()
  with patch('voice_session.subprocess.Popen',side_effect=AssertionError('Overlapping speech')):self.session.speak('Otra respuesta')
  self.assertFalse(self.session._threads)
 def test_old_call_event_cannot_send_a_message_in_new_call(self):
  from desktop import Desktop
  app=Desktop.__new__(Desktop);app.voice_session=self.session;app.voice_call_active=True;app.chat_busy=False
  previous=VoiceSession(self.tmp.name,self.events.append,{}, {'engine':'system','id':'system:test'})
  with patch.object(app,'ask',side_effect=AssertionError('Old session sent a message')):
   app.handle_voice_event({'kind':'final','session_id':previous.session_id,'text':'Mensaje antiguo'})
  self.session.event('partial',text='En directo');self.assertEqual(self.events[-1]['session_id'],self.session.session_id)
 def test_download_can_finish_after_voice_window_was_closed(self):
  from desktop import Desktop
  app=Desktop.__new__(Desktop);app.voice_window=None;app._voice_download_busy=True
  app.handle_voice_event({'kind':'installed','text':'Voz instalada'})
  self.assertFalse(app._voice_download_busy)
 def test_manual_submit_invalidates_inflight_recognition_and_mutes_input(self):
  before=self.session._revision;self.session.audio.put('audio');self.session.submit_message()
  self.assertTrue(self.session.awaiting.is_set());self.assertTrue(self.session.audio.empty());self.assertGreater(self.session._revision,before)
 def test_pause_stops_physical_stream_and_resume_restarts_it(self):
  import numpy as np
  session=self.session
  class Stream:
   def __init__(self):self.running=False;self.starts=0;self.closed=False
   def start(self):self.running=True;self.starts+=1
   def stop(self):self.running=False
   def close(self):self.closed=True;self.running=False
   def abort(self):self.running=False
   def read(self,count):session.stop_event.wait(.015);return np.zeros((count,1),dtype='float32'),False
  stream=Stream();sdk=NS(check_input_settings=lambda **k:None,InputStream=lambda **k:stream)
  worker=threading.Thread(target=session._capture,args=(sdk,None));worker.start();self.addCleanup(session.stop)
  deadline=time.monotonic()+1
  while not stream.running and time.monotonic()<deadline:time.sleep(.005)
  session.pause();time.sleep(.06);self.assertFalse(stream.running)
  session.resume();time.sleep(.08);self.assertTrue(stream.running);self.assertGreaterEqual(stream.starts,2)
  session.stop();worker.join(1);self.assertFalse(worker.is_alive());self.assertTrue(stream.closed)
 def test_native_samplerate_is_converted_for_transcription(self):
  import numpy as np
  session=self.session
  class Stream:
   def start(self):pass
   def stop(self):pass
   def close(self):pass
   def abort(self):pass
   def read(self,count):session.stop_event.wait(.01);return np.ones((count,1),dtype='float32')*.02,False
  def unsupported(**kw):raise RuntimeError('16 kHz not supported')
  sdk=NS(check_input_settings=unsupported,query_devices=lambda *a:{'default_samplerate':48000},InputStream=lambda **k:Stream())
  worker=threading.Thread(target=session._capture,args=(sdk,None));worker.start()
  try:chunk=session.audio.get(timeout=1);self.assertEqual(len(chunk),1600);self.assertAlmostEqual(float(chunk.mean()),.02,places=4)
  finally:session.stop();worker.join(1)
 def test_corrupt_voice_download_is_rejected_without_replacing_existing_voice(self):
  folder=Path(self.tmp.name)/'state/voices';folder.mkdir(parents=True);target=folder/'voice.onnx';target.write_bytes(b'original')
  row={'engine':'piper','files':['es/voice.onnx'],'file_metadata':{'es/voice.onnx':{'md5_digest':hashlib.md5(b'correcto').hexdigest()}}}
  with patch('urllib.request.urlopen',return_value=io.BytesIO(b'corrupto')):
   with self.assertRaisesRegex(ValueError,'integridad'):install_voice(self.tmp.name,row)
  self.assertEqual(target.read_bytes(),b'original');self.assertFalse(list(folder.glob('*.download')))
 def test_voice_config_failure_does_not_partially_replace_model(self):
  folder=Path(self.tmp.name)/'state/voices';folder.mkdir(parents=True);model=folder/'voice.onnx';config=folder/'voice.onnx.json'
  model.write_bytes(b'original');config.write_bytes(b'{}');row={'engine':'piper','files':['es/voice.onnx','es/voice.onnx.json']}
  with patch('urllib.request.urlopen',side_effect=[io.BytesIO(b'new model'),io.BytesIO(b'not json')]):
   with self.assertRaisesRegex(ValueError,'Configuración'):install_voice(self.tmp.name,row)
  self.assertEqual(model.read_bytes(),b'original');self.assertEqual(config.read_bytes(),b'{}');self.assertFalse(list(folder.glob('install_*')))
 def test_windows_builder_sets_icon_and_uses_windowed_native_entry(self):
  command=build_command(Path(self.tmp.name),Path(self.tmp.name)/'native',Path(self.tmp.name)/'work')
  self.assertIn('--windowed',command);self.assertIn('--icon',command);self.assertIn('AKIRA',command);self.assertIn('pyttsx3.drivers.sapi5',command)

class ReportDownloadTests(reports.ReportUITests):
 def test_report_retains_real_macro_dates_changes_and_venue_spread(self):
  from operation_report import source_rows
  research={'macro':{'rows':[{'name':'Tipos reales','value':2.1,'date':'2026-10-08','last_change':.2,'used_for':'Serie diaria para contraste'}]},
   'global_markets':{'OKX':{'updated':self.clock(),'quote':'USDT','bid':80000,'ask':80001,'imbalance':.15}}}
  rows=source_rows(research,self.clock());macro=next(r for r in rows if r[0].startswith('FRED'))
  self.assertEqual(macro[2],'2026-10-08');self.assertIn('variación 0.2',macro[4]);self.assertIn('Serie diaria',macro[3]);self.assertIn('80001',next(r for r in rows if r[0]=='OKX')[4])
 def test_first_click_queues_destination_while_reader_is_busy(self):
  self.app.report_busy=True;path=self.root/'informe.pdf'
  with patch('desktop.filedialog.asksaveasfilename',return_value=str(path)):
   self.app.save_report()
  self.assertEqual(self.app._report_download['path'],str(path));self.assertIn('Destino elegido',self.app.report_status.options['text'])
  model=build_report({'as_of_utc':self.clock()},24)
  with patch.object(self.app,'_perform_report_download') as download:self.app.handle_report_reply({'report_ready':model,'report_generation':self.app.report_generation});download.assert_called_once()
 def test_changed_period_triggers_fresh_model_before_download(self):
  self.app.report_busy=False;self.app.report_model=build_report({'as_of_utc':self.clock()},24);self.app.report_period.set('Últimos 7 días')
  with patch('desktop.filedialog.asksaveasfilename',return_value=str(self.root/'week.xlsx')),patch.object(self.app,'request_report') as read,patch.object(self.app,'_perform_report_download') as download:
   self.app.save_report();read.assert_called_once();download.assert_not_called()
  self.assertEqual(self.app._report_download['hours'],168)
 def test_disconnected_reader_uses_available_capture_without_actor_timeout(self):
  self.app.report_busy=False;self.app.bridge.connected=False;self.app.view={'as_of_utc':self.clock(),'symbols':{'BTCUSDm':{}}}
  with patch.object(self.app.bridge,'request',side_effect=AssertionError('Disconnected actor')),patch('desktop.threading.Thread') as thread:
   self.app.request_report();thread.call_args.kwargs['target']()
  self.assertIn('report_ready',self.app.replies.get_nowait())
 def test_old_window_reply_cannot_release_new_reader(self):
  self.app.report_busy=True;generation=self.app.report_generation
  self.app.handle_report_reply({'report_error':'Old','report_generation':generation-1});self.assertTrue(self.app.report_busy)

if __name__=='__main__':unittest.main()
