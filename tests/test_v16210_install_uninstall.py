"""Installer's strict Tk result and userdata recovery after a standalone uninstall."""
import json,shutil,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch

from application_management import launch_uninstaller
from frozen_ui_contract import UI_CHECK_VERSION,REQUIRED_RENDER_CHECKS,require_render_check
from native_ui_check import strategy_directory_rendered
from install_release import current_install
from migrate_v11_settings import restore_user_data,migrate
from settings import DEFAULT,load_config,save_config
from tests import test_v1621_startup as ui_fixture


class ExecutableContractTests(unittest.TestCase):
    def sample(self,rows=36,refresh=1,export=1):
        return NS(strategy_tree=NS(get_children=lambda:tuple(range(rows))),
            strategy_refresh_button=NS(winfo_ismapped=lambda:refresh),
            strategy_export_button=NS(winfo_ismapped=lambda:export))

    def test_real_tk_integer_visible_buttons_pass_exact_installer_contract_as_boolean(self):
        app=self.sample();value=strategy_directory_rendered(app)
        self.assertIs(value,True)
        report={'status':'PASSED','version':UI_CHECK_VERSION,**dict.fromkeys(REQUIRED_RENDER_CHECKS,True)}
        report['strategy_directory']=value
        self.assertEqual(require_render_check({'render_check':json.loads(json.dumps(report))}),report)

    def test_unconverted_previous_tk_result_reproduces_the_reported_error(self):
        app=self.sample()
        previous=len(app.strategy_tree.get_children())>=18 and app.strategy_refresh_button.winfo_ismapped() and app.strategy_export_button.winfo_ismapped()
        self.assertEqual(type(previous),int)
        report={'status':'PASSED','version':UI_CHECK_VERSION,**dict.fromkeys(REQUIRED_RENDER_CHECKS,True),'strategy_directory':previous}
        with self.assertRaisesRegex(RuntimeError,'strategy_directory'):require_render_check({'render_check':report})

    def test_hidden_controls_or_missing_strategies_still_block_installation(self):
        for args in ({'rows':0},{'rows':17},{'refresh':0},{'export':0}):
            with self.subTest(args=args):self.assertIs(strategy_directory_rendered(self.sample(**args)),False)

    def test_a_missing_uninstall_button_cannot_satisfy_the_new_contract(self):
        report={'status':'PASSED','version':UI_CHECK_VERSION,**dict.fromkeys(REQUIRED_RENDER_CHECKS,True)}
        report.pop('uninstall_control')
        with self.assertRaisesRegex(RuntimeError,'uninstall_control'):require_render_check({'render_check':report})


class PrivacyRedrawRegressionTests(unittest.TestCase):
    setUp=ui_fixture.StartupUITests.setUp

    def test_changing_privacy_from_settings_invalidates_hidden_amounts_without_rebuilding_charts(self):
        from engine import Engine
        from unittest.mock import patch
        engine=Engine(self.g,self.cfg,self.g.log)
        self.addCleanup(engine.close)
        view=engine.step()
        self.app.cfg['desktop']['privacy']=False
        self.app.render(view)
        self.app.navigate(6)  # Settings: budget and charts are no longer visible
        self.app.render(view)
        self.assertIn('CAPITAL ',self.app.dashboard_stats.cget('text'))
        self.app.cfg['desktop']['privacy']=True
        self.app._account_revealed=False
        with patch.object(self.app,'render_live_charts') as heavyweight:
            self.app.render(view)
            heavyweight.assert_not_called()
        self.assertIn(self.app.budget_value.cget('text'),('******','••••••'))
        self.assertIn(self.app.metrics['balance'].cget('text'),('******','••••••'))
        self.assertIn('CAPITAL PRIVADO',self.app.dashboard_stats.cget('text'))
        self.assertIn('Importes privados',self.app.portfolio_help.cget('text'))


class DetachedMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.app=self.root/'app';self.app.mkdir()
        self.script=self.app/'DESINSTALAR_AKIRA.ps1';self.script.write_bytes(b'# synthetic maintenance script')

    def test_worker_uses_a_detached_script_without_loading_the_application_or_broker(self):
        launch=Mock(return_value='WORKER')
        self.assertEqual(launch_uninstaller(self.app,platform='nt',launch=launch),'WORKER')
        args=launch.call_args.args[0];staging=Path(launch.call_args.kwargs['cwd'])
        self.addCleanup(shutil.rmtree,staging,True)
        self.assertEqual(args[:4],['powershell.exe','-NoLogo','-NoProfile','-STA'])
        detached=Path(args[-1]);self.assertEqual(detached.parent,staging)
        self.assertFalse(detached.is_relative_to(self.app));self.assertEqual(detached.read_bytes(),self.script.read_bytes())
        self.assertNotIn('python',str(args).casefold());self.assertTrue(self.app.is_dir())

    def test_worker_launch_failure_cleans_only_its_temporary_script(self):
        seen=[]
        def failed(*args,**kwargs):
            seen.append(Path(kwargs['cwd']));raise OSError('Synthetic launch failure')
        with self.assertRaisesRegex(OSError,'Synthetic'):launch_uninstaller(self.app,platform='nt',launch=failed)
        self.assertFalse(seen[0].exists());self.assertTrue(self.script.is_file())

    def test_missing_script_does_not_launch_or_close_akira(self):
        self.script.unlink();launch=Mock()
        with self.assertRaises(FileNotFoundError):launch_uninstaller(self.app,platform='nt',launch=launch)
        launch.assert_not_called();self.assertTrue(self.app.is_dir())

    def test_uninstaller_is_not_executed_on_an_unsupported_platform(self):
        launch=Mock()
        with self.assertRaisesRegex(RuntimeError,'Windows'):launch_uninstaller(self.app,platform='posix',launch=launch)
        launch.assert_not_called()


class PreservedDataRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name);self.runtime=self.home/'.akira_runtime';self.runtime.mkdir()
        self.snapshot=self.home/'Akira_Datos_Conservados/TEST.123/versiones/002';self.snapshot.mkdir(parents=True)
        self.cfg=load_config(DEFAULT);self.cfg['expected_login']=123;self.cfg['mode']='observe';self.cfg['risk']['max_trade_money']=2.17
        save_config(self.cfg,self.snapshot/'akira_config.json')
        self.pointer=self.runtime/'preserved_userdata.json'
        self.write_pointer()

    def write_pointer(self,**changes):
        data={'status':'UNINSTALLED_DATA_PRESERVED','root':str(self.snapshot),'backup':str(self.snapshot.parent.parent),**changes}
        self.pointer.write_text(json.dumps(data))

    def test_reinstallation_finds_the_preserved_current_data_after_code_was_removed(self):
        saved=current_install(self.runtime,self.home/'Local/Akira')
        self.assertEqual(saved,self.snapshot);self.assertEqual(migrate(load_config(saved/'akira_config.json'))['risk'],self.cfg['risk'])

    def test_restoration_keeps_current_chat_risk_credentials_and_uncertain_order_journal(self):
        from chat_store import ChatStore
        chats=ChatStore(self.snapshot);cid=chats.active;chats.append('user','Continuidad guardada',cid)
        state=self.snapshot/'state';state.mkdir(exist_ok=True)
        for name,body in [('account.json',b'{"uncertain_request":123}'),('desktop_layout.json',b'{"panels":{"chat_columns":[0.4]}}')]:
            (state/name).write_bytes(body)
        (self.snapshot/'AKIRA_SECRETS.json').write_bytes(b'{"protected":"synthetic"}')
        export=self.snapshot/'exports';export.mkdir();(export/'informe.txt').write_text('informe conservado')
        destination=self.home/'NewInstall';source=current_install(self.runtime,self.home/'Local/Akira')
        restore_user_data(source,None,destination);save_config(migrate(load_config(source/'akira_config.json')),destination/'akira_config.json')
        recovered=ChatStore(destination)
        self.assertIn('Continuidad guardada',str(recovered.history(cid=cid)))
        self.assertEqual((destination/'state/account.json').read_bytes(),(state/'account.json').read_bytes())
        self.assertEqual((destination/'AKIRA_SECRETS.json').read_bytes(),b'{"protected":"synthetic"}')
        self.assertEqual((destination/'exports/informe.txt').read_text(),'informe conservado')
        self.assertEqual(load_config(destination/'akira_config.json')['risk'],self.cfg['risk'])

    def test_preserved_pointer_outside_the_backup_tree_cannot_override_user_configuration(self):
        outside=self.home/'OtherProgram';outside.mkdir();save_config(self.cfg,outside/'akira_config.json')
        self.write_pointer(root=str(outside))
        with self.assertRaisesRegex(ValueError,'copia conservada'):current_install(self.runtime,self.home/'Local/Akira')
        self.assertTrue(outside.is_dir())

    def test_missing_or_partial_snapshot_is_not_silently_replaced_with_defaults(self):
        for data in ({'status':'BACKUP_STARTED'},{'backup':str(self.home/'wrong')},{'root':str(self.snapshot/'missing')}):
            with self.subTest(data=data):
                self.write_pointer(**data)
                with self.assertRaises(ValueError):current_install(self.runtime,self.home/'Local/Akira')
        self.assertTrue((self.snapshot/'akira_config.json').is_file())

    def test_active_install_takes_priority_over_an_old_uninstall_snapshot(self):
        active=self.runtime/'releases/Akira_ACTIVE';active.mkdir(parents=True)
        save_config(self.cfg,active/'akira_config.json')
        (self.runtime/'active_install.json').write_text(json.dumps({'root':str(active)}))
        self.assertEqual(current_install(self.runtime,self.home/'Local/Akira'),active)


class UninstallButtonTests(unittest.TestCase):
    setUp=ui_fixture.StartupUITests.setUp

    def test_visible_setting_control_opens_detached_maintenance_without_broker_or_model_work(self):
        callback=self.app.uninstall_button.cget('command')
        self.assertEqual(self.app.uninstall_button.cget('text'),'DESINSTALAR AKIRA')
        with patch('application_management.launch_uninstaller') as launch,patch.object(self.app,'show_message') as message:
            callback()
        launch.assert_called_once_with(self.root);self.assertIn('desinstalador',message.call_args.args[1])
        self.assertFalse(self.api.sent)

    def test_failed_worker_launch_is_shown_and_does_not_close_the_running_application(self):
        with patch('application_management.launch_uninstaller',side_effect=OSError('No disponible')),patch.object(self.app,'show_message') as message:
            self.app.open_uninstaller()
        self.assertEqual(message.call_args.args[2],True)
        self.assertIn('No disponible',message.call_args.args[1]);self.assertTrue(self.root.is_dir());self.assertFalse(self.api.sent)


if __name__=='__main__':unittest.main()
