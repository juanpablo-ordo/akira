"""User-visible budgets, persisted risk settings and bounded laptop rendering."""
import copy,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from settings import DEFAULT,load_config,save_config
from risk_limits import configured_limits
from studio_presenter import risk_dashboard
from resource_optimizer import effective_desktop


def screenshot_config():
    cfg=load_config(DEFAULT)
    cfg['risk'].update(max_trade_money=10000000,max_trade_pct=100,portfolio_money_cap=100000000,portfolio_capital_pct=100,daily_loss_money=100000000,daily_loss_pct=100,minimum_margin_level_pct=300)
    cfg['runner']['max_trade_budget_pct']=100
    return cfg


def screenshot_view(cfg):
    return {'connected':True,'mode':'observe','account':{'login':123,'server':'TEST','balance':37.89,'equity':37.89,'currency':'USD'},
        'configured_execution':{'risk':copy.deepcopy(cfg['risk']),'runner':copy.deepcopy(cfg['runner'])},
        'reserved_risk':0,'orders':[],'positions':[],'portfolio_risk':{'cap_usd':37.89,'reserved_usd':0,'available_usd':37.89,'pending_orders':0,'positions':0,'risk_known':True}}


class RiskMeaningTests(unittest.TestCase):
    def setUp(self):self.cfg=screenshot_config();self.view=screenshot_view(self.cfg)
    def test_empty_demo_has_full_configured_budget_and_zero_used(self):
        row=risk_dashboard(self.view,self.cfg)
        self.assertEqual(row['budget_pct'],100);self.assertEqual(row['used_pct'],0)
        self.assertIn('Sin órdenes',row['usage']);self.assertIn('10,000,000',row['configured'])
        self.assertEqual(row['limits']['per_trade'],37.89);self.assertIn('Aplicado',row['state'])
    def test_increasing_a_dollar_ceiling_does_not_fabricate_exposure(self):
        self.cfg['risk']['max_trade_money']=50000000
        row=risk_dashboard(self.view,self.cfg)
        self.assertEqual(row['used_pct'],0);self.assertEqual(row['limits']['per_trade'],37.89)
        self.assertIn('50,000,000',row['configured']);self.assertIn('actualización',row['state'])
    def test_lower_dollar_and_percentage_limits_have_a_visible_effect(self):
        self.cfg['risk'].update(max_trade_money=2.5,max_trade_pct=10,portfolio_money_cap=5,portfolio_capital_pct=25)
        self.cfg['runner']['max_trade_budget_pct']=50
        row=risk_dashboard(self.view,self.cfg)
        self.assertEqual(row['limits']['per_trade'],2.5);self.assertEqual(row['limits']['portfolio'],5)
        self.assertEqual(row['limits']['runner'],1.25);self.assertEqual(row['budget_pct'],13);self.assertEqual(row['used_pct'],0)
    def test_book_reservations_change_usage_independently_of_settings(self):
        self.view['portfolio_risk'].update(reserved_usd=3.789,available_usd=34.101,pending_orders=1)
        self.view['orders']=[{'ticket':1}]
        row=risk_dashboard(self.view,self.cfg)
        self.assertEqual(row['used_pct'],10);self.assertEqual(row['budget_pct'],100);self.assertIn('3.79',row['usage'])
    def test_unknown_reservations_are_described_as_provisional(self):
        for known in (False,True):
            self.view['portfolio_risk'].update(reserved_usd=37.89,risk_known=known,unconfirmed_requests=1)
            row=risk_dashboard(self.view,self.cfg)
            self.assertEqual(row['used_pct'],100);self.assertIn('provisional',row['usage'])
            self.assertNotIn('Reserva confirmada',row['usage'])
    def test_lowering_budget_below_existing_risk_reports_no_capacity(self):
        self.cfg['risk']['portfolio_money_cap']=1
        self.view['portfolio_risk'].update(reserved_usd=2,pending_orders=1)
        row=risk_dashboard(self.view,self.cfg)
        self.assertEqual(row['used_pct'],100);self.assertIn('supera',row['usage']);self.assertIn('0.00',row['usage'])
    def test_no_account_is_not_presented_as_a_zero_dollar_limit(self):
        self.view['connected']=False
        row=risk_dashboard(self.view,self.cfg)
        self.assertFalse(row['ready']);self.assertIn('pendiente',row['state']);self.assertNotIn('0.00',row['configured'])
    def test_privacy_hides_effective_and_selected_money_limits(self):
        row=risk_dashboard(self.view,self.cfg,private=True)
        for field in ('configured','usage','caption'):
            self.assertNotIn('37.89',row[field]);self.assertNotIn('10,000,000',row[field])
    def test_portfolio_uses_the_lower_of_balance_and_equity(self):
        self.view['account']['equity']=30
        row=configured_limits(self.cfg,self.view['account'])
        self.assertEqual(row['capital_basis'],30);self.assertEqual(row['portfolio'],30);self.assertEqual(row['per_trade'],30)
    def test_structural_minimum_override_remains_explicit(self):
        self.cfg['risk'].update(max_trade_money=1,max_trade_pct=1,min_lot_structural_override_enabled=True,
            min_lot_structural_override_money_cap=3,min_lot_structural_override_max_pct=8)
        row=configured_limits(self.cfg,self.view['account'])
        self.assertTrue(row['override']);self.assertEqual(row['per_trade'],3)


class LaptopPolicyTests(unittest.TestCase):
    def setUp(self):
        self.desktop=copy.deepcopy(DEFAULT['desktop']);self.hardware={'ram_gb':8,'physical_cores':2,'logical_cores':4}
    def test_dell_class_automatically_uses_a_small_cpu_profile_without_mutating_preferences(self):
        before=copy.deepcopy(self.desktop);row=effective_desktop(self.desktop,self.hardware)
        self.assertEqual(row['performance_profile'],'Ahorro de energía');self.assertFalse(row['model_use_gpu'])
        self.assertEqual(row['model_context_tokens'],2048);self.assertEqual(row['model_keep_alive_seconds'],0);self.assertEqual(self.desktop,before)
    def test_manual_opt_out_respects_user_preferences(self):
        self.desktop['adaptive_resources']=False
        self.assertEqual(effective_desktop(self.desktop,self.hardware),self.desktop)
    def test_powerful_and_unknown_hardware_are_not_forced_to_eco(self):
        for hardware in ({'ram_gb':32,'physical_cores':8,'logical_cores':16},{'ram_gb':0,'physical_cores':0,'logical_cores':0}):
            self.assertEqual(effective_desktop(self.desktop,hardware),self.desktop)
    def test_a_known_dedicated_gpu_is_not_silently_disabled(self):
        self.hardware['dedicated_gpu']=True
        self.assertEqual(effective_desktop(self.desktop,self.hardware),self.desktop)
    def test_four_logical_laptop_threads_do_not_occupy_both_physical_cores(self):
        from akira_model_runtime import ManagedLlamaProcess,hardware_profile
        managed=ManagedLlamaProcess({'local_runtime_enabled':True},profile=hardware_profile(8,0,4))
        with patch.object(managed,'_paths',return_value=(Path('/cpu/llama-server.exe'),Path('/model.gguf'))):
            command=managed.command('http://127.0.0.1:18987/v1/chat/completions',self.desktop)
        flag=lambda key:command[command.index(key)+1]
        self.assertEqual(flag('--threads'),'1');self.assertEqual(flag('--threads-batch'),'1')
        self.assertEqual(flag('--ctx-size'),'2048');self.assertEqual(flag('--n-gpu-layers'),'0');self.assertEqual(flag('--cache-ram'),'0')
    def test_laptop_session_does_not_keep_the_model_resident_after_use(self):
        from akira_model_runtime import ManagedLlamaProcess,hardware_profile
        managed=ManagedLlamaProcess({'local_runtime_enabled':True},profile=hardware_profile(8,0,4))
        with patch.object(managed,'start',return_value=True),patch.object(managed,'_health',return_value=True):
            with managed.session('http://127.0.0.1:18987/v1/chat/completions',self.desktop):pass
        self.assertEqual(managed._idle_override,0);self.assertEqual(managed.active,0)


class BudgetWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def window(self,folder):
        from desktop_qt import StudioWindow
        cfg=screenshot_config();cfg['desktop']['privacy']=False;save_config(cfg,Path(folder)/'akira_config.json')
        window=StudioWindow(folder,preview=True,start_actor=False);self.addCleanup(window.close)
        window.controller.view=screenshot_view(cfg);window.render(window.controller.view)
        return window
    def test_main_header_and_account_explain_configured_limits_and_empty_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            window=self.window(tmp)
            self.assertIn('37.89',window.metrics['reserved_risk'].caption.text())
            self.assertEqual(window.budget_limit_bar.value(),100);self.assertEqual(window.budget_bar.value(),0)
            self.assertIn('Sin órdenes',window.budget_text.text());self.assertIn('100,000,000',window.budget_config.text())
    def test_risk_fields_keep_precision_without_programmer_style_zeroes(self):
        with tempfile.TemporaryDirectory() as tmp:
            window=self.window(tmp);widget=window.settings_panel.fields['risk.max_trade_money'][0]
            widget.setValue(1.375)
            self.assertAlmostEqual(widget.value(),1.375);self.assertIn('1.375',widget.text());self.assertNotIn('1.3750',widget.text())
    def test_risk_preview_does_not_add_controls_or_reset_runner_edits(self):
        from PySide6.QtWidgets import QWidget
        with tempfile.TemporaryDirectory() as tmp:
            window=self.window(tmp);panel=window.settings_panel
            controls=len(panel.findChildren(QWidget));widget=panel.fields['management.breakeven_at_r'][0]
            widget.setValue(.75)
            for _ in range(40):panel.refresh_risk_preview(force=True)
            self.assertEqual(len(panel.findChildren(QWidget)),controls)
            self.assertIs(panel.fields['management.breakeven_at_r'][0],widget)
            self.assertEqual(widget.value(),.75);self.assertEqual(panel.risk_draft()['management']['breakeven_at_r'],.75)
            self.assertIn('management.breakeven_at_r',panel.risk_draft().dirty_paths)
    def test_saved_risk_updates_main_window_before_another_market_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            window=self.window(tmp);window.settings_panel.fields['risk.max_trade_money'][0].setValue(5)
            with patch.object(window,'apply_visual') as style,patch.object(window,'set_avatar') as avatar:
                window.save_risk_limits();end=time.monotonic()+4
                while window.controller._jobs and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
                for event in window.controller.poll():window.handle_event(event)
                self.assertFalse(window.controller._jobs);style.assert_not_called();avatar.assert_not_called()
            self.assertIn('5.00',window.metrics['reserved_risk'].value.text());self.assertEqual(window.budget_bar.value(),0)
            self.assertEqual(load_config(Path(tmp)/'akira_config.json')['risk']['max_trade_money'],5)
    def test_source_text_is_rebuilt_when_content_changes_and_not_for_ages(self):
        with tempfile.TemporaryDirectory() as tmp:
            window=self.window(tmp);view=window.controller.view
            view['research']={'news':[{'title':'A source','url':'https://example.com','text':'alpha'}],'sources':{}}
            import desktop_qt
            with patch('desktop_qt.source_abstract',wraps=desktop_qt.source_abstract) as abstract:
                window.render_sources();view['updated']=5;window.render_sources()
                self.assertEqual(abstract.call_count,1)
                view['research']['news'][0]['text']='beta';window.render_sources()
                self.assertEqual(abstract.call_count,2);self.assertIn('beta',window.source_content.toPlainText())
    def test_repainting_a_chart_keeps_data_and_responds_to_a_real_change(self):
        from studio_widgets import CandleChart
        chart=CandleChart();chart.resize(400,160);self.addCleanup(chart.close)
        rows=[{'open':10,'high':12,'low':8,'close':11}]
        chart.set_data(rows);first=chart.grab().toImage();count=chart._raster_count
        for _ in range(5):self.assertEqual(chart.grab().toImage(),first)
        self.assertEqual(chart._raster_count,count)
        chart.set_data([{'open':10,'high':12,'low':8,'close':9}]);second=chart.grab().toImage()
        self.assertNotEqual(first,second);self.assertEqual(chart._raster_count,count+1)
    def test_close_releases_native_widgets_on_the_ui_thread(self):
        import threading
        from PySide6.QtCore import QCoreApplication,QEvent
        from shiboken6 import isValid
        from desktop_qt import StudioWindow
        with tempfile.TemporaryDirectory() as tmp:
            window=StudioWindow(tmp,preview=True,start_actor=False);destroyed=[]
            window.destroyed.connect(lambda:destroyed.append(threading.get_ident()))
            window.close();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            self.assertFalse(isValid(window));self.assertEqual(destroyed,[threading.get_ident()])
            self.assertTrue(window.controller.closed)
    def test_real_controller_and_actor_apply_risk_and_observe_broker_reservations(self):
        from qa_risk_resources_rev14 import run_check
        result=run_check();self.assertEqual(result['status'],'PASSED');self.assertTrue(all(result['checks'].values()))
        self.assertFalse(result['live_account_used']);self.assertFalse(result['real_laptop_tested'])


if __name__=='__main__':unittest.main()
