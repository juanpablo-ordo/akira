import copy,unittest
from conversation_core import activity_presentation,needs_research
from settings import DEFAULT
from studio_presenter import risk_dashboard


class OrdinaryConversationTests(unittest.TestCase):
    def test_short_conversation_does_not_become_unsolicited_news(self):
        for question in ('arte abstracto','pintura al óleo','cuéntame algo bonito','astronomía','la fotosíntesis','un cuento corto','cuéntame una historia corta','escribe una historia inventada','historia','Invéntame una historia que ocurrió ayer'):
            with self.subTest(question=question):self.assertFalse(needs_research(question))
    def test_explicit_sources_and_current_facts_still_require_research(self):
        for question in ('Busca fuentes de astronomía','presidente actual de Guatemala','noticias de hoy','¿Qué acaba de lanzar Xbox?','historia de Guatemala','busca una historia real con fuentes','Cuéntame una historia que ocurrió ayer en Guatemala'):
            with self.subTest(question=question):self.assertTrue(needs_research(question))


class OverallActivityTests(unittest.TestCase):
    def setUp(self):
        self.state={'phase':'READY','active':False};self.model={'phase':'IDLE','ready':False}
        self.view={'connected':True,'symbols':{'BTCUSDm':{'checked_at':1},'XAUUSDm':{'checked_at':1}}}
    def shown(self,**kwargs):return activity_presentation(self.state,self.model,self.view,10,now=11,**kwargs)
    def test_fresh_market_activity_is_visible_without_a_chat(self):self.assertEqual(self.shown()['label'],'Analizando BTC y oro')
    def test_paused_management_is_not_presented_as_analysis(self):
        self.view['paused']=True;self.assertIn('pausada',self.shown()['label'])
    def test_old_received_snapshot_does_not_claim_current_analysis(self):
        self.assertEqual(activity_presentation(self.state,self.model,self.view,1,now=11)['label'],'Esperando datos de MT5')
    def test_current_chat_has_precedence(self):
        self.state.update(active=True,phase='RESPONDING');self.assertEqual(self.shown(chat_busy=True)['label'],'Respondiendo')
    def test_actual_model_error_remains_visible_during_analysis(self):
        self.model['phase']='MISSING';self.assertIn('IA por revisar',self.shown()['label'])
    def test_conversation_failure_is_not_hidden_by_market_activity(self):
        self.state['phase']='ERROR';self.assertIn('interrumpida',self.shown()['label'])
    def test_disconnected_market_does_not_claim_to_analyze(self):
        self.view['connected']=False;self.assertNotIn('Analizando',self.shown()['label'])


class VisibleRiskTests(unittest.TestCase):
    def setUp(self):
        self.cfg=copy.deepcopy(DEFAULT);self.cfg['risk'].update(max_trade_money=2.5,max_trade_pct=100,portfolio_money_cap=8,portfolio_capital_pct=50)
        self.view={'connected':True,'account':{'balance':40,'equity':40,'currency':'USD'},'reserved_risk':0,
            'portfolio_risk':{'reserved_usd':0,'risk_known':True,'pending_orders':0,'positions':0}}
    def test_main_value_reflects_effective_limit_even_with_no_orders(self):
        row=risk_dashboard(self.view,self.cfg);self.assertEqual(row['metric_value'],'2.50 USD');self.assertIn('En uso: 0.00',row['metric_caption'])
    def test_money_and_percentage_bind_separately(self):
        self.cfg['risk']['max_trade_pct']=1;row=risk_dashboard(self.view,self.cfg);self.assertEqual(row['metric_value'],'0.40 USD');self.assertIn('manda el porcentaje',row['configured'])
    def test_budget_labels_explain_configured_money_and_empty_usage(self):
        row=risk_dashboard(self.view,self.cfg);self.assertIn('8.00 USD',row['budget_format']);self.assertIn('0.00 USD en uso',row['usage_format']);self.assertEqual(row['budget_pct'],20)
    def test_exposure_does_not_replace_the_configured_limit(self):
        self.view['portfolio_risk'].update(reserved_usd=3,pending_orders=1)
        row=risk_dashboard(self.view,self.cfg);self.assertEqual(row['metric_value'],'2.50 USD');self.assertIn('En uso: 3.00',row['metric_caption'])
    def test_missing_account_is_waiting_instead_of_a_zero_limit(self):
        self.view['connected']=False;row=risk_dashboard(self.view,self.cfg);self.assertEqual(row['metric_value'],'—');self.assertIn('Esperando',row['budget_format'])
    def test_privacy_covers_the_new_limit_and_exposure_labels(self):
        row=risk_dashboard(self.view,self.cfg,True)
        for key in ('metric_value','metric_caption','budget_format','usage_format'):
            with self.subTest(field=key):self.assertNotIn('2.50',row[key]);self.assertNotIn('8.00',row[key])


class ActualQtUserFlowTests(unittest.TestCase):
    def test_mouse_keyboard_wheel_touchpad_save_actor_and_reopen(self):
        from qa_user_flow_rev16 import run_check
        self.assertEqual(run_check()['status'],'PASSED')


class InstallationIdentityTests(unittest.TestCase):
    def test_actual_entrypoint_identifies_existing_config_without_exposing_credentials(self):
        import json,subprocess,sys,tempfile
        from pathlib import Path
        from settings import save_config
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=copy.deepcopy(DEFAULT);cfg['risk']['max_trade_money']=3.5;cfg['mt5_password']='FIXTURE_PRIVATE_PASSWORD'
            cfg['assistant']['api_key']='FIXTURE_PRIVATE_API';save_config(cfg,root/'akira_config.json')
            report=root/'info.json';entry=Path(__file__).resolve().parents[1]/'Akira.py'
            result=subprocess.run([sys.executable,str(entry),'--installation-info',str(report),'--app-root',str(root)],capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr.decode('utf-8','replace'))
            text=report.read_text(encoding='utf-8');data=json.loads(text)
            self.assertEqual(data['application_data_root'],str(root.resolve()));self.assertEqual(data['preferences']['risk']['max_trade_money'],3.5)
            self.assertNotIn('FIXTURE_PRIVATE',text);self.assertFalse(data['broker_started']);self.assertFalse(data['model_started'])

class ReadableFormulaTests(unittest.TestCase):
    def test_actual_windows_formula_uses_readable_symbols(self):
        from studio_presenter import rich_text
        text=rich_text(r'La fórmula $ e^{i\pi} + 1 = 0 $ une $ e $, $ i $ y $ \pi $.')
        self.assertIn('e^(iπ) + 1 = 0',text);self.assertNotIn('$',text);self.assertNotIn(r'\pi',text)
    def test_money_and_source_urls_keep_their_dollar_signs(self):
        from studio_presenter import rich_text
        text=rich_text('Presupuesto $10 y coste $2.50. [Fuente](https://example.com/a?x=$value)')
        self.assertIn('$10',text);self.assertIn('$2.50',text);self.assertIn('https://example.com/a?x=$value',text)
        self.assertIn('$e$',rich_text('Código literal: `$e$` y ```$e$```'))
    def test_fraction_and_root_stay_inert_text(self):
        from studio_presenter import rich_text
        text=rich_text(r'$\frac{1}{\sqrt{x}}$ <script>alert(1)</script>')
        self.assertIn('(1)/(√(x))',text);self.assertNotIn('<script>',text)


if __name__=='__main__':unittest.main()
