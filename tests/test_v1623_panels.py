"""The live header must not hide an empty remainder of the desktop."""
import builtins
import unittest
from unittest.mock import patch

import desktop
from engine import Engine
from tests import test_v1621_startup as fixture
from frozen_ui_contract import UI_MODULES,UI_CHECK_VERSION,require_render_check
from build_windows import build_command
from pathlib import Path


class PanelsTests(unittest.TestCase):
    setUp=fixture.StartupUITests.setUp

    def snapshot(self):
        engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(engine.close)
        view=engine.step()
        view['research']['sources']={'news':{'fresh':True,'usable':True,'age_seconds':1}}
        return view

    def test_security_dependency_failure_does_not_leave_orders_charts_analysis_and_sources_empty(self):
        view=self.snapshot();self.app.messages.put(view)
        original=builtins.__import__
        def missing(name,*args,**kwargs):
            if name=='security_details':raise ModuleNotFoundError("No module named 'security_details'")
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=missing):self.app.poll()
        self.assertEqual(len(self.app.orders.items),len(view['orders']))
        self.assertTrue(next(iter(self.app.charts.values()))[0].data['bars'])
        self.assertIn('BITCOIN',self.app.analysis_summary.text)
        self.assertEqual(self.app.source_status['mt5'].options['text'],'ACTIVO')
        self.assertTrue(self.app.analysis_sources.items)

    def test_privacy_is_applied_before_any_optional_security_panel_failure(self):
        view=self.snapshot();self.app.cfg['desktop']['privacy']=True;self.app._account_revealed=False
        self.app.messages.put(view);original=builtins.__import__
        def missing(name,*args,**kwargs):
            if name=='security_details':raise ModuleNotFoundError("No module named 'security_details'")
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=missing):self.app.poll()
        self.assertIn(self.app.metrics['balance'].options['text'],('******','••••••'))
        self.assertIn(self.app.budget_value.options['text'],('******','••••••'))

    def test_security_render_failure_is_logged_and_does_not_block_other_sections(self):
        view=self.snapshot();self.app.cfg['desktop']['privacy']=False
        with patch('desktop.security_text',side_effect=ModuleNotFoundError('security dependency unavailable')):
            self.app.render(view)
        self.assertEqual(len(self.app.orders.items),4)
        self.assertTrue(self.app.charts['BTCUSDm'][0].data['bars'])
        self.assertIn('BITCOIN',self.app.analysis_summary.text)
        self.assertIn('BITCOIN',self.app.sources_summary.text)
        self.assertIn('Seguridad',self.app._render_health['errors'])
        self.assertFalse(self.app._render_health['complete'])
        self.assertIn('Seguridad',self.app.connection.options['text'])
        self.assertTrue((self.root/'logs/INTERFAZ_ERRORES.log').is_file())
        self.app.render(view)
        self.assertTrue(self.app._render_health['complete'])

    def test_failed_budget_details_cannot_block_orders_sources_or_analysis(self):
        view=self.snapshot()
        with patch.object(self.app,'render_account_budget',side_effect=ValueError('bad auxiliary detail')):
            self.app.render(view)
        self.assertEqual(len(self.app.orders.items),4);self.assertTrue(self.app.analysis_sources.items)
        self.assertIn('BITCOIN',self.app.analysis_summary.text)
        self.assertIn('Presupuesto',self.app._render_health['errors'])

    def test_failed_source_card_render_cannot_block_prices_or_orders(self):
        view=self.snapshot()
        with patch.object(self.app,'render_source_cards',side_effect=desktop.tk.TclError('bad source widget')):
            self.app.render(view)
        self.assertEqual(len(self.app.orders.items),4)
        self.assertTrue(self.app.charts['BTCUSDm'][0].data['bars'])
        self.assertIn('BITCOIN',self.app.analysis_summary.text)

    def test_disconnected_snapshot_reports_connection_cause_on_the_source_card(self):
        self.app.render({'connected':False,'error':'No se pudo conectar MT5'})
        self.assertEqual(self.app.source_status['mt5'].options['text'],'SIN CONEXIÓN')
        self.assertEqual(self.app.friendly_source_cards['mt5'][1].options['text'],'Sin conexión')
        self.assertIn('MT5',self.app.connection.options['text'])

    def test_self_check_cannot_disable_the_live_actor(self):
        with self.assertRaises(ValueError):desktop.Desktop(self.window,self.root,preview=False,start_actor=False)


class FrozenContractTests(unittest.TestCase):
    def test_native_builder_explicitly_collects_every_render_dependency(self):
        root=Path(__file__).resolve().parents[1]
        args=build_command(root,root/'native',root/'build')
        imports=[args[i+1] for i,x in enumerate(args[:-1]) if x=='--hidden-import']
        self.assertIn('security_details',imports)
        for module in UI_MODULES:self.assertIn(module,imports)

    def test_installer_refuses_old_dependency_only_self_check(self):
        with self.assertRaises(RuntimeError):require_render_check({'status':'PASSED','frozen':True,'window_icon':True})

    def test_installer_refuses_partial_render_even_with_imports_present(self):
        from frozen_ui_contract import REQUIRED_RENDER_CHECKS
        keys=REQUIRED_RENDER_CHECKS
        base={'version':UI_CHECK_VERSION,'status':'PASSED',**{k:True for k in keys}}
        for key in keys:
            with self.subTest(key=key),self.assertRaises(RuntimeError):
                require_render_check({'render_check':{**base,key:False}})
        self.assertEqual(require_render_check({'render_check':base}),base)


if __name__=='__main__':unittest.main()
