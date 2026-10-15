"""Verify UI wiring/data flow without a display server or a live MT5 session."""
import json,queue
import unittest
from contextlib import ExitStack
from unittest.mock import patch
import desktop
from engine import Engine
from tests.fixtures import PendingCase

class Variable:
    def __init__(self,value=None,**kw):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value

class Widget:
    def __init__(self,parent=None,**kw):
        self.parent=parent;self.options=kw;self.items={};self.text='';self.selected=();self.tags={};self.tabs=[];self.calls=[];self.expression='idle';self.children=[]
    def cget(self,key):return self.options.get(key,'#020712')
    def configure(self,*args,**kw):self.options.update(kw)
    config=configure
    def insert(self,*args,**kw):
        if 'values' in kw:
            key=kw.get('iid',str(len(self.items)));self.items[key]=kw;return key
        self.text+=str(args[1]);return ''
    def delete(self,*args):
        if args and args[0]=='1.0':self.text=''
        else:
            for key in args:self.items.pop(key,None)
    def get(self,*args):return self.text
    def get_children(self):return tuple(self.items)
    def selection(self):return self.selected
    def selection_set(self,key):self.selected=(key,)
    def exists(self,key):return key in self.items
    def tag_names(self):return tuple(self.tags)
    def tag_delete(self,key):self.tags.pop(key,None)
    def tag_add(self,key,*args):self.tags[key]=args
    def tag_configure(self,key,**kw):self.tags.setdefault(key,kw)
    def tag_bind(self,*args):pass
    def add(self,page,text=None,**kw):
        if text is not None:self.tabs.append(text)
        self.children.append(page)
    def panes(self):return tuple(self.children)
    def forget(self,page):self.children.remove(page)
    def winfo_screenwidth(self):return 1920
    def winfo_screenheight(self):return 1080
    def winfo_width(self):return 1000
    def winfo_height(self):return 600
    def sash_coord(self,index):return (400,300)
    def sash_place(self,*args):self.calls.append(('sash_place',args,{}))
    def yview(self,*args):return (0,1)
    def xview(self,*args):return (0,1)
    def bbox(self,*args):return (0,0,1000,600)
    def create_window(self,*args,**kw):return 1
    def select(self,page=None):
        if page is not None:self.active=page
        return getattr(self,'active',None)
    def update_data(self,data):self.data=data
    def set_expression(self,value):self.expression=value
    def __getattr__(self,name):
        if name in ('theme_use','map','layout','pack','pack_propagate','place','place_forget','grid','columnconfigure','rowconfigure','heading','column','bind','see','after','after_idle','after_cancel','title','geometry','minsize','iconbitmap','protocol','destroy','itemconfigure','focus_set','set','option_add','tag_remove','selection_set','selection_clear'):
            return lambda *args,**kw:self.calls.append((name,args,kw))
        raise AttributeError(name)

class DesktopFlowTests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();(self.root/'akira_config.json').write_text(json.dumps(self.cfg))
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.multiple(desktop.tk,Frame=Widget,Label=Widget,Button=Widget,Entry=Widget,Text=Widget,Listbox=Widget,Checkbutton=Widget,PanedWindow=Widget,Canvas=Widget,Scrollbar=Widget,StringVar=Variable,BooleanVar=Variable))
        stack.enter_context(patch.multiple(desktop.ttk,Style=Widget,Notebook=Widget,Treeview=Widget,Combobox=Widget,Scrollbar=Widget,Progressbar=Widget))
        stack.enter_context(patch('desktop.AkiraLive2D',Widget));stack.enter_context(patch('desktop.CandleChart',Widget))
        bases=desktop.SymbolPanel.__bases__;desktop.SymbolPanel.__bases__=(Widget,)
        stack.callback(setattr,desktop.SymbolPanel,'__bases__',bases)
        stack.enter_context(patch('desktop.threading.Thread.start'))
        self.window=Widget();self.app=desktop.Desktop(self.window,self.root,preview=True)
    def test_all_restored_panels_render_real_actor_snapshot_without_mt5_calls_in_tk(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close);view=e.step()
        with patch.object(self.api,'symbol_info_tick',side_effect=AssertionError('MT5 desde Tk')),patch('assistant_akira.ollama_status',side_effect=AssertionError('Red desde Tk')):
            self.app.render(view)
        self.assertEqual(tuple(self.app.book.tabs),desktop.TAB_TITLES)
        self.assertEqual(len(self.app.avatars),2);self.assertEqual(len(self.app.orders.items),4)
        self.assertGreaterEqual(len(self.app.frames.items),14);self.assertIn('BTCUSDm',self.app.sources.text)
        self.assertTrue(any(row['values'][0].startswith('#') for panel in self.app.panels.values() for row in panel.tree.items.values()))
    def test_pending_command_remains_available_during_long_conversation(self):
        self.app.chat_busy=True;self.app.chat_input.set('Pon las mejores pendientes de BTC y oro')
        with patch.object(self.app,'async_request') as submit,patch.object(self.app.assistant,'reply',side_effect=AssertionError('Modelo en el botón de pendientes')):
            self.app.ask()
        self.assertEqual(submit.call_args.args[0],{'action':'assistant_best_pending','symbol':'ALL'});self.assertTrue(self.app.chat_busy)
    def test_memory_result_and_export_do_not_release_an_active_conversation(self):
        self.app.chat_busy=True;self.app.replies.put({'memory':'Una fuente recuperada'});self.app.replies.put({'answer':'Archivo exportado','command':False})
        self.app.poll();self.assertIn('recuperada',self.app.memory_results.text);self.assertTrue(self.app.chat_busy)
        self.app.replies.put({'answer':'Respuesta final','conversation':True,'command':False});self.app.poll();self.assertFalse(self.app.chat_busy)

    def test_manual_pending_button_has_visible_progress_and_one_active_request(self):
        with patch.object(self.app,'async_request') as request:
            self.app.request_map('ALL');self.app.request_map('ALL')
        self.assertEqual(request.call_count,1);self.assertTrue(self.app.map_request_busy)
        self.assertIn('Analizando',self.app.map_result_label.options['text'])

    def test_blocked_button_result_is_visible_and_releases_button(self):
        self.app.map_request_busy=True
        result={'ok':False,'results':[{'symbol':'XAUUSDm','detail':'Riesgo 7.45 > 2.17'}]}
        self.app.replies.put({'answer':'Entry=2500 SL=2490 TP=2520','command':True,'map_result':result})
        self.app.poll()
        self.assertFalse(self.app.map_request_busy)
        self.assertIn('7.45',self.app.map_result_label.options['text'])
        self.assertIn('Entry=2500',self.app.chat.text)

    def test_initial_button_can_queue_before_first_connected_view(self):
        self.assertFalse(self.app.bridge.connected);self.assertTrue(self.app.bridge.starting)

    def test_chat_pause_is_reflected_in_management_button(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close)
        e.handle_command({'action':'pause','paused':True});self.app.render(e.step())
        self.assertTrue(self.app.paused)
        self.assertEqual(self.app.toggle.options['text'],'REANUDAR GESTIÓN')

    def test_write_guard_is_visible_while_market_connection_remains_available(self):
        self.g.runtime_execution_block='Otra Akira ocupa la cuenta'
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close)
        self.app.render(e.step())
        self.assertIn('ESCRITURAS BLOQUEADAS',self.app.connection.options['text'])
        self.assertTrue(all('EJECUCIÓN BLOQUEADA' in panel.status.options.get('text','') for panel in self.app.panels.values()))
        self.assertTrue(all('Otra Akira' in panel.detail.options.get('text','') for panel in self.app.panels.values()))

    def test_visible_chat_shortcut_opens_tab_and_requests_entry_focus(self):
        self.app.open_chat_button.options['command']()
        self.assertIs(self.app.book.active,self.app.pages[desktop.TAB_NAMES[5]])
        callback=self.window.calls[-1][1][0];callback()
        self.assertEqual(self.app.chat_entry.calls[-1][0],'focus_set')
        self.assertEqual(self.app.open_chat(object()),'break')

    def test_chat_composer_has_fixed_row_below_expandable_history(self):
        calls=self.app.chat_composer.calls
        self.assertTrue(any(name=='grid' and kw.get('row')==3 and kw.get('sticky')=='ew' for name,args,kw in calls))
        parent=self.app.chat_composer.parent
        self.assertTrue(any(name=='rowconfigure' and args==(2,) and kw.get('weight')==1 for name,args,kw in parent.calls))
        self.assertFalse(any(name=='rowconfigure' and args==(3,) and kw.get('weight')==1 for name,args,kw in parent.calls))
        self.assertEqual(self.app.chat_send_button.options['command'],self.app.ask)

    def test_key_panels_have_drag_handles_in_both_directions(self):
        expected={'dashboard_columns','dashboard_vertical','pending_symbols','account_book','analysis_sections','sources_sections','chat_columns'}
        self.assertTrue(expected.issubset(self.app.layout.widgets))
        self.assertTrue(all(p.options['showhandle'] and p.options['opaqueresize'] for p,o,r in self.app.layout.widgets.values()))

    def test_optional_details_can_be_reopened_without_rebuilding_data(self):
        self.app.toggle_analysis_details();self.assertIn(self.app.analysis_advanced,self.app.analysis_split.children)
        self.app.toggle_analysis_details();self.assertNotIn(self.app.analysis_advanced,self.app.analysis_split.children)
        self.app.toggle_source_details();self.assertIn(self.app.sources_detail,self.app.source_split.children)
        self.app.toggle_source_details();self.assertNotIn(self.app.sources_detail,self.app.source_split.children)

    def test_sidebar_switches_real_pages_and_preserves_model_configuration(self):
        original=self.app.cfg['assistant']['local_model']
        self.app.nav_buttons[3].options['command']()
        self.assertIs(self.app.book.active,self.app.pages[desktop.TAB_NAMES[3]])
        self.assertEqual(self.app.page_title.options['text'],'ANÁLISIS DE MERCADO')
        self.assertEqual(self.app.cfg['assistant']['local_model'],original)

    def test_bulk_voice_button_starts_one_background_job_without_io_in_tk(self):
        with patch('desktop.VoiceDownloadBatch') as factory,patch('desktop.voice_inventory',side_effect=AssertionError('Catalog I/O in Tk')):
            job=factory.return_value;job.job_id='download-test'
            self.app.download_all_voices();self.app.download_all_voices()
        factory.assert_called_once();job.start.assert_called_once();self.assertTrue(self.app._voice_download_busy)
        self.assertTrue(self.app.commands.empty(),'Downloading voices queued a trading command')

    def test_stale_voice_download_cannot_unlock_current_job(self):
        from unittest.mock import Mock
        self.app._voice_download_job=Mock(job_id='current');self.app._voice_download_busy=True
        self.app.handle_voice_download({'job_id':'old','finished':True,'state':'complete'})
        self.assertTrue(self.app._voice_download_busy)

    def test_finishing_bulk_download_preserves_active_call_and_refreshes_inventory(self):
        from unittest.mock import Mock
        self.app._voice_download_job=Mock(job_id='current');self.app._voice_download_busy=True;self.app.voice_call_active=True
        with patch.object(self.app,'load_voice_inventory') as refresh:
            self.app.handle_voice_download({'job_id':'current','finished':True,'state':'complete'})
        self.assertFalse(self.app._voice_download_busy);self.assertTrue(self.app.voice_call_active);refresh.assert_called_once_with(False)

if __name__=='__main__':unittest.main()
