import ast,copy,json,tempfile,unittest
from pathlib import Path
from settings import DEFAULT,load_config,save_config
from validate_install import validate
from legacy_handoff import retire,STATUS
from tests.fixtures import PendingCase
from execution import Blocked

ROOT=Path(__file__).resolve().parents[1]

class InstallationTests(unittest.TestCase):
    def test_payload_validates_offline(self):self.assertEqual(validate(ROOT)['schema_version'],1600)
    def test_installer_scripts_match_the_actual_manifest(self):
        self.assertEqual({p.name for p in ROOT.glob('*.bat')},{'VALIDAR_AKIRA.bat','DIAGNOSTICO_AKIRA.bat'})
    def test_old_strategy_keys_are_removed_in_migration(self):
        old=copy.deepcopy(DEFAULT);old['schema_version']=194;old['scalp_flow']={'enabled':True};old['native']={'enabled':True};old['ticket_control']={'enabled':True,'reserved_capital_pct':100}
        cfg=load_config(old);text=json.dumps(cfg).lower()
        self.assertNotIn('scalp',text);self.assertNotIn('ticket_control',text);self.assertNotIn('native',cfg)
    def test_previous_effective_ticket_cap_is_preserved(self):
        old=copy.deepcopy(DEFAULT);old['schema_version']=194;old['ticket_control']={'enabled':True,'reserved_capital_pct':65}
        old['risk'].update(max_total_money=5,max_total_pct=10)
        self.assertEqual(load_config(old)['risk']['portfolio_capital_pct'],65)
        self.assertEqual(load_config(old)['risk']['portfolio_money_cap'],0)
    def test_previous_actual_aggregate_cap_is_preserved_without_ticket_policy(self):
        old=copy.deepcopy(DEFAULT);old['schema_version']=194;old['risk'].update(max_total_money=7,max_total_pct=8)
        cfg=load_config(old);self.assertEqual(cfg['risk']['portfolio_money_cap'],7);self.assertEqual(cfg['risk']['portfolio_capital_pct'],8)
    def test_account_mode_and_individual_risk_survive_update(self):
        old=copy.deepcopy(DEFAULT);old['schema_version']=194;old.update(mode='observe',expected_login=123456789)
        old['risk']['max_trade_money']=1.8;cfg=load_config(old)
        self.assertEqual((cfg['mode'],cfg['expected_login'],cfg['risk']['max_trade_money']),('observe',123456789,1.8))
    def test_migration_enables_continuous_public_context(self):
        old=copy.deepcopy(DEFAULT);old['schema_version']=194;old['research']['enabled']=False
        self.assertTrue(load_config(old)['research']['enabled'])
    def test_current_explicit_observe_mode_is_preserved(self):
        cfg=copy.deepcopy(DEFAULT);cfg['mode']='observe';self.assertEqual(load_config(cfg)['mode'],'observe')
    def test_no_root_module_for_market_strategy_exists(self):
        self.assertFalse(any('scalp' in p.name.lower() for p in ROOT.iterdir()))
        tree=ast.parse((ROOT/'strategy.py').read_text());self.assertFalse(any(isinstance(n,ast.Constant) and n.value=='SCALP' for n in ast.walk(tree)))
    def test_validation_precedes_release_activation(self):
        text=(ROOT/'INSTALL_AKIRA.ps1').read_text(encoding='utf-8-sig')
        self.assertLess(text.index('install_checks.py'),text.index("@('activate','--runtime-root'"))
        self.assertNotIn('Move-Item -LiteralPath $app',text)
        self.assertIn('$testExit=$LASTEXITCODE',text)
        self.assertNotIn('$process.ExitCode',text)
        self.assertIn("$report.status -ne 'PASSED'",text)
    def test_powershell_installer_build_follows_its_own_manifest(self):
        from akira_version import BUILD_ID
        manifest=json.loads((ROOT/'VALIDACION_V12.json').read_text(encoding='utf-8-sig'))
        script=(ROOT/'INSTALL_AKIRA.ps1').read_text(encoding='utf-8-sig')
        self.assertEqual(manifest['build'],BUILD_ID)
        self.assertIn("$expectedBuild=[string]$packageManifest.build",script)
        self.assertIn('$report.build -ne $expectedBuild',script)
        self.assertNotIn('AKIRA_13_2_ASTRA_MIC_DIRECT_CANCEL_CPU_PENDING_ONLY',script)
        self.assertIn('build=$expectedBuild',script)

    def test_windows_store_runtime_is_outside_the_app(self):
        text=(ROOT/'INSTALL_AKIRA.ps1').read_text(encoding='utf-8-sig');self.assertIn("Join-Path $env:USERPROFILE '.akira_runtime'",text)
        self.assertIn('--copies $venv',text)
    def test_upgrade_keeps_journal_and_knowledge(self):
        text=(ROOT/'INSTALL_AKIRA.ps1').read_text(encoding='utf-8-sig');self.assertIn("@('state','logs','exports','AKIRA_SECRETS.json')",text)
        self.assertIn('Akira.backup.pre11.',text)
    def test_failed_activation_calls_transactional_rollback(self):
        text=(ROOT/'INSTALL_AKIRA.ps1').read_text(encoding='utf-8-sig');self.assertIn("@('rollback','--runtime-root'",text)
        self.assertIn('$originalError=$_',text)
        self.assertIn('$originalError.Exception.ToString()',text)
        self.assertIn('INSTALL_HOST_RESULT.json',text)
    def test_new_installer_does_not_run_obsolete_tests(self):
        text=(ROOT/'INSTALL_AKIRA.ps1').read_text(encoding='utf-8-sig');self.assertNotIn('test_v189_core',text);self.assertNotIn('validate_final_v9',text)
    def test_invalid_portfolio_percent_is_rejected(self):
        cfg=copy.deepcopy(DEFAULT);cfg['risk']['portfolio_capital_pct']=101
        with self.assertRaises(ValueError):load_config(cfg)
    def test_nonfinite_config_is_rejected(self):
        cfg=copy.deepcopy(DEFAULT);cfg['risk']['max_trade_money']=float('inf')
        with self.assertRaises(ValueError):load_config(cfg)
    def test_pending_rule_cannot_be_reenabled_by_old_config(self):
        cfg=copy.deepcopy(DEFAULT);cfg['pending_policy']['enabled']=False;cfg['pending']['never_auto_cancel']=True
        migrated=load_config(cfg);self.assertTrue(migrated['pending_policy']['enabled']);self.assertFalse(migrated['pending']['never_auto_cancel'])
    def test_other_instruments_are_rejected(self):
        cfg=copy.deepcopy(DEFAULT);cfg['symbols']={'EURUSD':True}
        with self.assertRaises(ValueError):load_config(cfg)

class LegacyTransitionTests(PendingCase,unittest.TestCase):
    def control(self,active=True):
        folder=self.root/'common'/'Files'/'AkiraNativeV3'/'123_TEST'/'BTCUSDm';folder.mkdir(parents=True)
        self.api.terminal.commondata_path=str(self.root/'common')
        rows=['0']*37;rows[0]='AKIRA_NATIVE_V3';rows[1]='old_session';rows[2]='123';rows[3]='TEST';rows[4]='BTCUSDm';rows[5]=str(int(self.clock()*1000));rows[6]=rows[7]='1';rows[-1]='END'
        (folder/'control.txt').write_text('|'.join(rows)+'\n')
        status={k:'0' for k in STATUS};status.update(protocol='AKIRA_STATUS_V3',login='123',server='TEST',symbol='BTCUSDm',updated_ms=str(int(self.clock()*1000)),state='ACTIVE' if active else 'OBSERVE',end='END')
        (folder/'status.txt').write_text('|'.join(status[k] for k in STATUS)+'\n')
        return folder
    def test_previous_controller_is_paused_before_new_execution(self):
        folder=self.control()
        with self.assertRaises(Blocked):retire(self.g)
        fields=(folder/'control.txt').read_text().split('|');self.assertEqual(fields[6:8],['0','0'])
        self.assertFalse(self.api.sent)
    def test_observe_acknowledgement_releases_transition(self):
        self.control(active=False);retire(self.g);self.assertFalse(self.api.sent)
    def test_transition_does_not_create_an_ea_if_none_existed(self):
        self.api.terminal.commondata_path=str(self.root/'common');retire(self.g)
        self.assertFalse((self.root/'common'/'Files').exists())
    def test_active_old_ea_without_control_blocks_new_execution(self):
        folder=self.control();(folder/'control.txt').unlink()
        with self.assertRaises(Blocked):retire(self.g)
