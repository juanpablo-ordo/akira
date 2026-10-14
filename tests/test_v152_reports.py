"""Informes y valoración con evidencia; cero bróker o Internet reales."""
import copy,json,tempfile,unittest,zipfile
from pathlib import Path
from datetime import datetime,timezone
from xml.etree import ElementTree as ET
from unittest.mock import patch
from dataclasses import replace
from contextlib import ExitStack

from engine import Engine
from execution import Journal,OWN_RUNNER,order_plan
from assistant_akira import AkiraAssistant
from decision_brain import instant_review,stars
from operation_report import build_report,closed_trades,export_report,read_recent_events,source_rows,NS
from trade_review import assess_plan
from settings import load_config
from tests.fixtures import PendingCase
from tests.test_desktop_flow import Widget,Variable
import desktop


class ReviewTests(unittest.TestCase):
    def row(self,**kw):
        return dict(side=1,entry=4185.194,sl=4182.431,tp=4192.812,quality_score=97,
            activation_score=93,horizon_atr=10,timeframe='M15',target_observed=True,**kw)
    def test_user_gold_order_rr_and_tight_sl_explained(self):
        result=assess_plan(self.row(),{'H1':{'trend':.8}})
        self.assertAlmostEqual(result['rr'],2.7571480275)
        self.assertEqual(result['stars'],4)
        self.assertTrue(any('SL ajustado' in x for x in result['warnings']))
    def test_projected_target_cannot_receive_five_stars(self):
        row=self.row();row['target_observed']=False
        self.assertLessEqual(assess_plan(row)['stars'],3)
    def test_missing_atr_and_quality_do_not_invent_confidence(self):
        row=self.row();row.update(horizon_atr=0,quality_score=None)
        self.assertEqual(assess_plan(row)['stars'],0)
        self.assertIn('Falta ATR',' '.join(assess_plan(row)['warnings']))
    def test_stale_horizon_and_spread_lower_rating(self):
        row=self.row();row['sl']=row['entry']-.2
        a=assess_plan(row,{'M15':{'last_bar':100}},now=10000,quote={'spread':.1})
        self.assertLessEqual(a['stars'],2)
        self.assertEqual(a['freshness'],'velas desactualizadas')
    def test_chat_displays_the_assessed_stars(self):
        row=self.row();row['assessment']=assess_plan(row)
        self.assertEqual(stars(row).count('⭐'),4)
    def test_missing_sell_tp_is_unknown_not_a_target_at_zero(self):
        row=self.row();row.update(side=-1,sl=4242,tp=None)
        a=assess_plan(row)
        self.assertIsNone(a['rr']);self.assertIsNone(a['reward_distance']);self.assertEqual(a['stars'],0)
    def test_observed_entry_does_not_prove_observed_target(self):
        row=self.row();row.pop('target_observed');row['reason']='LIMIT swing H1 observado; SNAP objetivo mínimo 1.60R'
        a=assess_plan(row);self.assertFalse(a['target_observed']);self.assertLessEqual(a['stars'],3)
        row['reason']='LIMIT swing H1 observado; target swing H4'
        self.assertTrue(assess_plan(row)['target_observed'])


class ReportTests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)
        self.e.step();self.snapshot=self.e.report_snapshot()
    def test_report_snapshot_has_zero_mt5_calls_and_no_mutation(self):
        with ExitStack() as stack:
            for name in ('account_info','terminal_info','positions_get','orders_get','symbol_info','symbol_info_tick','order_send','history_deals_get','order_calc_profit','order_calc_margin'):
                stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('MT5 durante informe')))
            result=self.e.handle_command({'action':'export_report_snapshot'})
            self.assertTrue(result['ok']);model=build_report(result['snapshot'])
        self.assertEqual(sum(bool(r.get('confirmed')) for r in model['pendings']),4)
        result['snapshot']['account']['balance']=99999
        self.assertNotEqual(self.e._last_view['account']['balance'],99999)
    def test_report_includes_all_manual_risk_without_broker_writes(self):
        p=self.plan('XAUUSDm',side=-1);manual=self.api.add_pending(p,magic=0)
        self.e.step();before=copy.deepcopy(self.api.sent);model=build_report(self.e.report_snapshot())
        row=next(r for r in model['tables']['Riesgo'] if r[0]==str(manual.ticket))
        self.assertEqual(row[3],'Manual / externa');self.assertGreater(row[7],0)
        self.assertTrue(any(r[0]==str(manual.ticket) and r[3]=='Manual / externa' for r in model['tables']['Pendientes']))
        self.assertEqual(before,self.api.sent)
    def test_confirmed_risk_rating_consistent_in_map_chat_report(self):
        for symbol,info in self.snapshot['symbols'].items():
            live=[r for r in info['scenario_book'] if r['confirmed']]
            chat=self.e.confirmed_levels(symbol)
            for row in live:
                match=next(c for c in chat if c['ticket']==row['ticket'])
                self.assertEqual(row['assessment'],match['assessment'])
                self.assertGreater(row['risk_usd'],0)
        model=build_report(self.snapshot)
        self.assertTrue(all(r[8]>0 for r in model['tables']['Pendientes'] if r[0]!='Propuesta'))
        # El mapa de cuatro cuadrantes no debe borrar evidencia de otro ticket
        # confirmado si el usuario permite varios del mismo tipo.
        extra=copy.deepcopy(self.snapshot['symbols']['XAUUSDm']['pending_book'][0]);extra.update(ticket=8888,confirmed=True,quality_score=88)
        self.snapshot['symbols']['XAUUSDm']['pending_book'].append(extra)
        self.snapshot['orders'].append({'ticket':8888,'symbol':'XAUUSDm','type':2,'owned':True,'entry':extra['entry'],'sl':extra['sl'],'tp':extra['tp']})
        all_rows=build_report(self.snapshot)['pendings']
        self.assertEqual(next(r['quality_score'] for r in all_rows if r.get('ticket')==8888),88)
    def test_order_plan_retains_origin_and_empirical_evidence(self):
        p=replace(self.plan(),empirical_samples=25,empirical_win_rate=.6,signal_timeframe='M5')
        o=self.api.orders[0];copy_plan=order_plan(o,p.to_dict())
        self.assertEqual(copy_plan.empirical_samples,25);self.assertEqual(copy_plan.signal_timeframe,'M5')
    def test_redaction_and_unknown_history_remain_explicit(self):
        self.snapshot['configured_execution']={'api_key':'secret','risk':{'max_trade_money':2.17}}
        self.snapshot['history_state']={'error':'No disponible'}
        self.snapshot['account']['equity']=None
        model=build_report(self.snapshot)
        self.assertNotIn('secret',json.dumps(model));self.assertEqual(model['snapshot']['account']['login'],'***123')
        self.assertTrue(any('Historial' in w for w in model['warnings']))
        self.assertIsNone(next(r[2] for r in model['tables']['Resumen'] if r[1]=='Patrimonio USD'))
    def test_empty_history_and_current_only_are_not_fake_losses(self):
        model=build_report(self.snapshot,0)
        self.assertFalse(model['closed'])
        self.assertIsNone(next(r[2] for r in model['tables']['Resumen'] if r[1]=='Neto de esos cierres USD'))
    def test_excel_numeric_values_formulas_and_text_injection(self):
        model=build_report(self.snapshot);model['tables']['Fuentes'][0][-1]='=HYPERLINK("https://example.invalid")'
        path=self.root/'Informe.xlsx';export_report(model,path,'xlsx',False)
        with zipfile.ZipFile(path) as z:
            self.assertIsNone(z.testzip());root=ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
            e=root.find('.//{'+NS+'}c[@r="E6"]');ratio=root.find('.//{'+NS+'}c[@r="H6"]')
            self.assertIsNone(e.get('t'));self.assertGreater(float(e.find('{'+NS+'}v').text),0)
            self.assertIn('ABS(G6-E6)',ratio.find('{'+NS+'}f').text)
            sources=ET.fromstring(z.read('xl/worksheets/sheet6.xml'));c=sources.find('.//{'+NS+'}c[@r="E6"]')
            self.assertEqual(c.get('t'),'inlineStr');self.assertIsNone(c.find('{'+NS+'}f'))
            summary=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            self.assertIn('SUM(Riesgo!',summary.find('.//{'+NS+'}c[@r="C10"]/{'+NS+'}f').text)
    def test_excel_real_close_dates_are_typed_dates(self):
        snapshot=dict(self.snapshot,history_deals=self.deals())
        model=build_report(snapshot);path=self.root/'Fechas.xlsx';export_report(model,path,'xlsx',False)
        with zipfile.ZipFile(path) as z:
            root=ET.fromstring(z.read('xl/worksheets/sheet4.xml'));c=root.find('.//{'+NS+'}c[@r="D6"]')
            self.assertIsNone(c.get('t'));self.assertGreater(float(c.find('{'+NS+'}v').text),40000)
    def test_pdf_contains_actual_prices_and_masked_support_json(self):
        model=build_report(self.snapshot);out=export_report(model,self.root/'Informe.pdf','pdf')
        content=Path(out['path']).read_bytes()
        self.assertTrue(content.startswith(b'%PDF-'));self.assertIn(b'/Type /Page',content)
        self.assertGreater(len(content),4000)
        data=json.loads(Path(out['diagnostic_path']).read_text())
        self.assertEqual(data['snapshot']['account']['login'],'***123')
    def test_failed_export_keeps_previous_file_and_removes_temp(self):
        path=self.root/'Informe.pdf';path.write_bytes(b'previous')
        with patch('operation_report.write_pdf',side_effect=RuntimeError('fallo concreto')):
            with self.assertRaisesRegex(RuntimeError,'concreto'):export_report(build_report(self.snapshot),path)
        self.assertEqual(path.read_bytes(),b'previous');self.assertFalse(list(self.root.glob('.akira_report_*')))
    def deals(self):
        now=self.clock();base={'position_id':55,'symbol':'BTCUSDm','magic':OWN_RUNNER,'volume':.01,'swap':0,'fee':0}
        return [{**base,'time':now-600,'entry':0,'type':0,'price':60000,'profit':0,'commission':-.1},
            {**base,'time':now,'entry':1,'type':1,'price':60200,'profit':2,'commission':-.1,'swap':-.05,'fee':-.02,'reason':4}]
    def test_closed_trades_include_both_sides_fees_and_real_sl_reason(self):
        result=closed_trades({'history_deals':self.deals()},0)[0]
        self.assertAlmostEqual(result['net_usd'],1.73);self.assertEqual(result['cause'],'Stop Loss')
        self.assertEqual(result['duration_minutes'],10);self.assertIsNone(result['initial_sl'])
        self.assertIn('no se puede juzgar',result['review'])
    def test_partial_close_is_not_counted_as_complete(self):
        deals=self.deals();deals[1]['volume']=.005
        self.assertFalse(closed_trades({'history_deals':deals},0))
    def test_netting_reversal_is_not_fabricated_as_simple_trade(self):
        deals=self.deals();deals[1]['entry']=2
        self.assertFalse(closed_trades({'history_deals':deals},0))
    def test_mfe_profit_giveback_is_visible_without_future_claims(self):
        row={'identifier':55,'initial_sl':59900,'max_favorable_r':3,'max_favorable_usd':10,'tracking_started_at':self.clock()-600}
        result=closed_trades({'history_deals':self.deals(),'position_journal':{'77':row}},0)[0]
        self.assertEqual(result['ticket'],'77');self.assertAlmostEqual(result['capture'],.173)
        self.assertIn('devolver',result['review']);self.assertIn('no demuestra',result['review'])
    def test_source_publication_date_is_not_fetch_freshness(self):
        rows=source_rows({'sources':{'YouTube':{'fresh':True,'updated':self.clock()}},'videos':[{'title':'Antiguo','published':'2024-03-01'}]},self.clock())
        self.assertEqual(rows[0][1],'Vigente según proveedor');self.assertIn('antigua',rows[1][1])
    def test_bounded_event_read_keeps_operational_records_only(self):
        when=datetime.fromtimestamp(self.clock(),timezone.utc);folder=self.root/'events';folder.mkdir()
        path=folder/('eventos_'+when.strftime('%Y-%m-%d')+'.jsonl')
        normal={'utc':when.isoformat(),'symbol':'XAUUSDm','message':'CICLO'}
        path.write_text('\n'.join(json.dumps(r) for r in [normal]*100+[dict(normal,operation='modify_order')]))
        rows,truncated=read_recent_events(folder,24,self.clock(),max_bytes=400)
        self.assertTrue(truncated);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['operation'],'modify_order')
    def test_instant_review_does_not_use_model_web_or_actor(self):
        a=AkiraAssistant(self.cfg,self.root,trade_callback=lambda c:(_ for _ in ()).throw(AssertionError('Actor')))
        with patch.object(a,'_reply',side_effect=AssertionError('Modelo')),patch('assistant_akira.time.time',return_value=self.clock()):
            answer=a.reply('Valora la calidad de la pendiente de oro',self.snapshot)
        self.assertIn('XAUUSDm',answer);self.assertIn('R:R',answer);self.assertIn('no envía',answer)
        self.assertEqual(a.dialogue.previous_question(),'Valora la calidad de la pendiente de oro')
    def test_stale_instant_review_warns_and_explicit_order_is_not_intercepted(self):
        self.assertIn('15 segundos',instant_review('Valora la pendiente oro',self.snapshot,now=self.clock()+20))
        self.assertIsNone(instant_review('Valora y coloca las mejores pendientes oro',self.snapshot,now=self.clock()))


class ReportWidget(Widget):
    def winfo_exists(self):return True
    def yview(self,*args):pass
    def set(self,*args):pass
    def lift(self):pass


class ReportUITests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();(self.root/'akira_config.json').write_text(json.dumps(self.cfg))
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.multiple(desktop.tk,Frame=ReportWidget,Label=ReportWidget,Button=ReportWidget,Entry=ReportWidget,Text=ReportWidget,Listbox=ReportWidget,Checkbutton=ReportWidget,Toplevel=ReportWidget,PanedWindow=ReportWidget,Canvas=ReportWidget,Scrollbar=ReportWidget,StringVar=Variable,BooleanVar=Variable))
        stack.enter_context(patch.multiple(desktop.ttk,Style=ReportWidget,Notebook=ReportWidget,Treeview=ReportWidget,Combobox=ReportWidget,Scrollbar=ReportWidget,Checkbutton=ReportWidget,Progressbar=ReportWidget))
        stack.enter_context(patch('desktop.AkiraLive2D',ReportWidget));stack.enter_context(patch('desktop.CandleChart',ReportWidget))
        bases=desktop.SymbolPanel.__bases__;desktop.SymbolPanel.__bases__=(ReportWidget,);stack.callback(setattr,desktop.SymbolPanel,'__bases__',bases)
        stack.enter_context(patch('desktop.threading.Thread.start'));self.buttons=[];original=desktop.button
        def record(*args,**kw):
            obj=original(*args,**kw);self.buttons.append(obj);return obj
        stack.enter_context(patch('desktop.button',side_effect=record))
        stack.enter_context(patch('desktop.messagebox.showerror'));self.app=desktop.Desktop(ReportWidget(),self.root,preview=True)
        self.app.open_report_dialog()
    def test_visible_buttons_and_format_choice_are_wired(self):
        buttons=[b for b in self.buttons if 'DESCARGAR INFORME' in b.options.get('text','') and b.options.get('command')==self.app.open_report_dialog]
        self.assertEqual(len(buttons),1)
        self.assertTrue(all(b.options['command']==self.app.open_report_dialog for b in buttons))
        self.assertEqual(self.app.report_format.get(),'PDF');self.assertFalse(self.app.report_support.get())
        pdf=next(b for b in self.buttons if b.options.get('text')=='DESCARGAR INFORME · PDF')
        excel=next(b for b in self.buttons if b.options.get('text')=='DESCARGAR INFORME · EXCEL')
        excel.options['command']();self.assertEqual(self.app.report_format.get(),'Excel')
        pdf.options['command']();self.assertEqual(self.app.report_format.get(),'PDF')
    def test_reader_worker_uses_read_only_actor_and_no_tk(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close);e.step();self.app.report_busy=False;self.app.bridge.connected=True
        with patch.object(self.app.bridge,'request',return_value={'ok':True,'snapshot':e.report_snapshot()}) as request,patch('desktop.threading.Thread') as thread:
            self.app.request_report();target=thread.call_args.kwargs['target']
            with patch.object(self.app.report_status,'configure',side_effect=AssertionError('Tk desde worker')):target()
        self.assertEqual(request.call_args.args[0],{'action':'export_report_snapshot'})
        self.assertIn('report_ready',self.app.replies.get_nowait())
    def test_report_completion_does_not_release_active_chat(self):
        self.app.chat_busy=True;model=build_report({'as_of_utc':self.clock(),'symbols':{}})
        self.app.replies.put({'report_ready':model,'report_generation':self.app.report_generation});self.app.poll()
        self.assertTrue(self.app.chat_busy);self.assertFalse(self.app.report_busy)
        self.assertIn('INFORME OPERATIVO',self.app.report_preview.text)
    def test_excel_choice_passes_format_and_support_choice_to_worker(self):
        self.app.report_busy=False;self.app.report_format.set('Excel');self.app.report_support.set(False)
        self.app.report_model=build_report({'as_of_utc':self.clock()});path=self.root/'Elegido.xlsx'
        with patch('desktop.filedialog.asksaveasfilename',return_value=str(path)),patch('desktop.threading.Thread') as thread,patch('desktop.export_report',return_value={'path':str(path)}) as export:
            self.app.save_report();thread.call_args.kwargs['target']()
        self.assertEqual(export.call_args.args[1:],(str(path),'xlsx',False))
    def test_reader_error_is_visible_and_does_not_disable_trading(self):
        self.app.handle_report_reply({'report_error':'Historial incompleto','report_generation':self.app.report_generation})
        self.assertFalse(self.app.report_busy);self.assertIn('Historial incompleto',self.app.report_status.options['text'])
        self.assertFalse(self.app.paused)
    def test_gui_quick_review_during_long_chat_uses_cached_evidence_without_actor(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close);self.app.view=e.step()
        self.app.chat_busy=True;self.app.chat_input.set('Valora la calidad de la pendiente de oro')
        with patch.object(self.app,'async_request',side_effect=AssertionError('Actor')),patch.object(self.app.assistant,'reply',side_effect=AssertionError('LLM')):
            self.app.ask()
        self.assertTrue(self.app.chat_busy);self.assertIn('XAUUSDm',self.app.chat.text);self.assertIn('R:R',self.app.chat.text)
