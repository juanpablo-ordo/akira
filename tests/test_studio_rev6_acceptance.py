"""Regression cases from the owner's hands-on Studio report. No live orders."""
import copy,hashlib,io,json,os,tempfile,threading,time,unittest,zipfile
from pathlib import Path
from unittest.mock import Mock,patch
from settings import DEFAULT,load_config,save_config
from tests.test_studio_rev5 import wait_for

_APP=None
class PreferenceAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _APP
        from PySide6.QtWidgets import QApplication
        _APP=QApplication.instance() or QApplication([])
    def setUp(self):
        from desktop_qt import StudioWindow
        self.tmp=tempfile.TemporaryDirectory();self.w=StudioWindow(self.tmp.name,preview=True,start_actor=False)
    def tearDown(self):
        self.w.close();_APP.processEvents();self.assertTrue(wait_for(lambda:not self.w.controller._jobs));self.tmp.cleanup()
    def settle(self,seconds=.04):
        end=time.monotonic()+seconds
        while time.monotonic()<end:_APP.processEvents();time.sleep(.002)
    def test_two_stale_forms_merge_different_fields_and_last_same_field_wins(self):
        c=self.w.controller;a=copy.deepcopy(c.cfg);b=copy.deepcopy(c.cfg);d=copy.deepcopy(c.cfg)
        a['studio']['secondary']='#a012b3';b['risk']['max_trade_pct']=2.3;d['studio']['secondary']='#091827'
        self.assertTrue(c.save(a));self.assertTrue(c.save(b));self.assertTrue(c.save(d));self.assertTrue(wait_for(lambda:not c._jobs))
        saved=load_config(Path(self.tmp.name)/'akira_config.json');self.assertEqual(saved['risk']['max_trade_pct'],2.3);self.assertEqual(saved['studio']['secondary'],'#091827')
    def test_general_form_does_not_undo_risk_changed_elsewhere(self):
        panel=self.w.settings_panel;c=self.w.controller;draft=copy.deepcopy(c.cfg);draft['risk']['max_trade_pct']=2.4;c.save(draft);self.assertTrue(wait_for(lambda:not c._jobs))
        panel.saved({'config':c.cfg,'submitted':draft});self.assertEqual(panel.draft()['risk']['max_trade_pct'],2.4)
        panel.fields['studio.brand_name'][0].setText('Mi Akira');c.save(panel.draft());self.assertTrue(wait_for(lambda:not c._jobs));self.assertEqual(c.cfg['risk']['max_trade_pct'],2.4)
    def test_appearance_autosaves_secondary_and_negative_offsets(self):
        panel=self.w.settings_panel
        from studio_settings_qt import put
        panel.fields['studio.secondary'][0].setValue('#c031a1');panel.extra.update({'studio.wallpaper.offset_x':-34,'studio.wallpaper.rotation':-27})
        panel.schedule_preview();self.settle(1.2);self.assertTrue(wait_for(lambda:not self.w.controller._jobs))
        saved=load_config(Path(self.tmp.name)/'akira_config.json')['studio'];self.assertEqual(saved['secondary'],'#c031a1');self.assertEqual(saved['wallpaper']['offset_x'],-34);self.assertEqual(saved['wallpaper']['rotation'],-27)
    def test_named_languages_are_visible_and_not_editable(self):
        for path in ('studio.language_ui','studio.language_chat','studio.language_voice_in','studio.language_voice_out'):
            box=self.w.settings_panel.fields[path][0];self.assertFalse(box.isEditable());self.assertGreaterEqual(box.count(),18);self.assertTrue(any('Espa' in box.itemText(i) for i in range(box.count())))
    def test_removed_duplicate_actions_stay_out_of_settings_and_call_is_in_chat(self):
        from PySide6.QtWidgets import QPushButton
        settings=[b.text().casefold() for b in self.w.settings_panel.findChildren(QPushButton)]
        for banned in ('traducir textos restantes','voz y llamada','copiar','descargar directorio','generar y evaluar ahora'):
            self.assertFalse(any(banned in t for t in settings),banned)
        self.assertTrue(any('llamar' in b.text().casefold() for b in self.w.pages[5].findChildren(QPushButton)))
    def test_source_context_has_no_internal_json_tooltip(self):
        from PySide6.QtWidgets import QTextBrowser
        for browser in self.w.pages[4].findChildren(QTextBrowser):self.assertEqual(browser.toolTip(),'')
    def test_eco_caps_wallpaper_work_without_overwriting_user_fps(self):
        self.w.controller.cfg['studio']['wallpaper']['fps']=120;studio=copy.deepcopy(self.w.controller.cfg['studio'])
        self.w.controller.cfg['desktop']['performance_profile']='Ahorro de energía';self.w.apply_visual(studio)
        self.assertEqual(self.w.controller.cfg['studio']['wallpaper']['fps'],120)
        # The visual draft keeps the requested setting while the owned worker is capped.
        self.assertLessEqual(self.w.surface.config.get('fps',120),12)
    def test_reading_chat_does_not_jump_to_latest_on_refresh(self):
        from studio_presenter import set_document
        from PySide6.QtWidgets import QTextBrowser
        b=QTextBrowser();b.resize(450,180);b.show()
        try:
            set_document(b,'<br/>'.join(str(i) for i in range(100)));self.settle();bar=b.verticalScrollBar();bar.setValue(bar.maximum()//3);old=bar.value()
            set_document(b,'<br/>'.join(str(i) for i in range(110)),follow=True);self.settle();self.assertLessEqual(abs(bar.value()-old),2)
        finally:b.close()
    def test_sprite_profile_duration_and_flags_survive_reopening(self):
        from studio_settings_qt import SpriteEditor
        image=Path(self.tmp.name)/'happy.png'
        from PIL import Image
        Image.new('RGBA',(32,32),'white').save(image)
        avatar={'active':True,'entries':[{'id':'frame-a','path':str(image),'state':'happy','order':0,'duration_ms':731}], 'sequences':{},'animate':False,'repeat':False,'profile':'default'}
        dialog=SpriteEditor(self.w,avatar)
        try:
            value=dialog.result_avatar();self.assertFalse(value['animate']);self.assertFalse(value['repeat']);self.assertEqual(value['entries'][0]['duration_ms'],731)
        finally:dialog.close()

    def test_required_ai_checkbox_survives_old_snapshot_and_navigation_until_ack(self):
        from execution import Gateway,Journal,Reporter
        from engine import Engine
        from tests.fake_mt5 import Clock,FakeMT5
        root=Path(self.tmp.name);clock=Clock();api=FakeMT5(clock);cfg=load_config(DEFAULT)
        gateway=Gateway(api,cfg,Journal(root/'journal.json'),Reporter(root/'logs',console=False),clock);engine=Engine(gateway,cfg,gateway.log)
        try:
            view=engine.step();self.w.controller.view=view;self.w.render(view);self.w.navigate(1);self.w.render_pending();self.w.pending_table.selectRow(0);self.w.pending_selected()
            self.assertIsNotNone(self.w.pending_table.selected_key());self.w.controller.request=Mock(return_value=True);self.w.require_ai.setChecked(True);key=self.w.pending_table.selected_key()
            self.w.controller.view=copy.deepcopy(view);self.w.navigate(2);self.w.navigate(1);self.w.render_pending();self.w.pending_selected();self.assertTrue(self.w.require_ai.isChecked());self.assertTrue(self.w._review_overrides[key])
            self.assertTrue(self.w.controller.request.call_args.args[0]['require'])
        finally:engine.close()

class DataAndChatAcceptance(unittest.TestCase):
    def test_budget_uses_reserved_fraction_instead_of_constant_zero(self):
        from studio_presenter import budget_summary
        text,percent=budget_summary({'cap_usd':100,'reserved_usd':25,'available_usd':75});self.assertEqual(percent,25);self.assertIn('75.00',text)
    def test_preferences_survive_validated_round_trip(self):
        cfg=copy.deepcopy(DEFAULT);cfg['studio']={'font_bold':True,'theme_profiles':{'Personalizado':{'theme':'Nebulosa','accent':'#123abc'}},'wallpaper':{'rotation':-27,'offset_x':-56,'offset_y':37,'loop':False,'vsync':False,'zoom':135},'avatar':{'animate':False,'repeat':False}}
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'cfg.json';save_config(load_config(cfg),p);a=load_config(p)['studio'];self.assertTrue(a['font_bold']);self.assertIn('Personalizado',a['theme_profiles']);self.assertEqual(a['wallpaper']['offset_x'],-56);self.assertFalse(a['avatar']['animate'])
    def test_account_is_hidden_by_default_but_explicit_choice_is_retained(self):
        self.assertTrue(load_config({})['desktop']['privacy'])
        cfg=copy.deepcopy(DEFAULT);cfg['desktop']['privacy']=False;self.assertFalse(load_config(cfg)['desktop']['privacy'])
    def test_named_hyperlinks_escape_markup_and_never_activate_script_urls(self):
        from studio_presenter import rich_text
        result=rich_text('Ver [Xbox Wire](https://news.xbox.com/es-es/gears/) <script>alert(1)</script> https://www.reuters.com/test')
        self.assertIn('>Xbox Wire</a>',result);self.assertIn('>Reuters</a>',result);self.assertNotIn('<script>',result);self.assertNotIn('href="javascript:',rich_text('[x](javascript:bad)'))
    def test_typo_repair_preserves_identifiers_numbers_and_negation(self):
        from language_normalization import normalize_message
        raw='No abras BTCUSDm; esplicame la memroia RAM y diferncia, SL=60234.5 https://site.test/esplicas `memroia` AKIRA_01'
        answer,changes=normalize_message(raw);self.assertTrue(answer.startswith('No abras BTCUSDm'));self.assertIn('memoria RAM',answer);self.assertIn('SL=60234.5',answer);self.assertIn('https://site.test/esplicas `memroia` AKIRA_01',answer);self.assertGreaterEqual(len(changes),3)
    def test_current_product_query_keeps_gears_in_every_expansion(self):
        from web_facts import _expanded_queries,needs_web_verification
        q='Xbox acaba de lanzar el nuevo Gears';self.assertTrue(needs_web_verification(q));self.assertTrue(all('gears' in v.lower() for v in _expanded_queries(q)))
    def test_failed_download_does_not_destroy_previous_model(self):
        from local_ai_repair import download_verified
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'model.gguf';p.write_bytes(b'previous')
            with self.assertRaises(ValueError):download_verified('https://test.invalid/model',p,'0'*64,100,opener=lambda *a,**kw:io.BytesIO(b'corrupt'))
            self.assertEqual(p.read_bytes(),b'previous');self.assertFalse(p.with_name(p.name+'.repair.part').exists())
    def test_verified_download_replaces_previous_model_atomically(self):
        from local_ai_repair import download_verified
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'model.gguf';p.write_bytes(b'previous');good=b'new model';download_verified('https://test.invalid/model',p,hashlib.sha256(good).hexdigest(),100,opener=lambda *a,**kw:io.BytesIO(good));self.assertEqual(p.read_bytes(),good)
    def test_repair_archive_cannot_escape_installation(self):
        from local_ai_repair import extract_cpu
        with tempfile.TemporaryDirectory() as t:
            archive=Path(t)/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape.exe','bad');z.writestr('llama-server.exe','bad')
            with self.assertRaises(ValueError):extract_cpu(archive,Path(t)/'cpu')
            self.assertFalse((Path(t)/'escape.exe').exists())
    def test_uninstaller_closes_only_processes_owned_by_this_installation(self):
        from application_management import prepare_native_uninstall
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'AKIRA';root.mkdir();ps=[]
            for i,p in enumerate((root/'AKIRA.exe',root/'local_ai/cpu/llama-server.exe',root/'terminal64.exe',root.parent/'elsewhere/llama-server.exe')):
                proc=Mock();proc.pid=10000+i;proc.info={'pid':proc.pid,'exe':str(p)};proc.is_running.return_value=True;proc.terminate.side_effect=lambda p=proc:setattr(p.is_running,'return_value',False);ps.append(proc)
            close=Mock();result=prepare_native_uninstall(root,timeout=0,processes=ps,close_windows=close);self.assertEqual(result['status'],'READY');self.assertEqual(close.call_args.args[0],{10000,10001});ps[2].terminate.assert_not_called();ps[3].terminate.assert_not_called()
