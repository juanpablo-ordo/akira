"""Akira completa: paneles ajustables, memoria, chat, pendientes y runners."""
from pathlib import Path
import copy,json,os,queue,re,sys,threading,time,tkinter as tk,webbrowser
from urllib.parse import urlparse
from voice_akira import listen_once, microphone_devices, speak_async
from tkinter import ttk,messagebox,filedialog,simpledialog
from execution import Reporter
from runtime import run_session
from settings import load_config,save_config
from akira_version import BUILD_ID
from assistant_akira import AkiraAssistant
from decision_brain import fast_command as route_fast_request, stars,instant_review
from akira_live2d import AkiraLive2D,vtuber_available,expression_for_reply,expression_for_dialogue,expression_for_voice_event
from command_bridge import CommandBridge
from trade_review import assessment_text
from operation_report import build_report,report_text,export_report,read_recent_events
from desktop_layout import PanelLayout,fitted_geometry,scroll_frame,wheel_over_panel
from analysis_details import analysis_text
from voice_session import VoiceSession,audio_inventory,voice_inventory,install_voice,VoiceDownloadBatch
from cyber_ui import (BG,PANEL,CARD,LINE,CYAN,BLUE,PINK,AMBER,GREEN,RED,MUTED,TEXT,FONT,MONO,
    label,button,text_box,neon_card,configure_style as cyber_style,toggle,brand_status,public_status,ask_text)
from windows_identity import apply_window_icon,set_identity,apply_dark_titlebar
from security_details import security_text
from strategy_directory import StrategyDirectory
from resource_optimizer import get_intervals, PROFILES

TAB_NAMES=('⚡ TRADING CYBER','PENDIENTES FUTURAS','CUENTA Y ÓRDENES','ANÁLISIS','FUENTES / CONTEXTO','AKIRA · CHAT','AJUSTES','TERMINAL')
TAB_TITLES=('TRADING','PENDIENTES','CUENTA','ANÁLISIS','FUENTES','CHAT · AKIRA','AJUSTES','TERMINAL')
PAGE_TITLES=('CENTRO DE OPERACIONES','PENDIENTES AUTOMÁTICAS','CUENTA Y OPERACIONES','ANÁLISIS DE MERCADO','FUENTES E INVESTIGACIÓN','CHAT CON AKIRA','CONFIGURACIÓN','TERMINAL Y REGISTROS')
PAGE_DETAILS=('Control, contexto y mapa de BTC y oro','Propuestas, órdenes confirmadas y seguimiento de su validez','Pendientes y posiciones con sus propietarios','Estructura, indicadores y motivos de cada decisión','Estado y antigüedad de las fuentes realmente recibidas','Conversaciones, memoria, archivos y llamada','Cambios aplicados en vivo, sin editar archivos','Registros y descarga de informes en PDF o Excel')

def available_chart_frame(info,requested):
    """Use real published bars and label their actual timeframe during startup."""
    frames=info.get('bars_by_timeframe') or {}
    if not frames and info.get('bars'):frames={info.get('timeframe','M1'):info['bars']}
    if frames.get(requested):return requested,frames[requested]
    for candidate in ('M15','M5','H1','M1','M30','H4','D1','W1'):
        if frames.get(candidate):return candidate,frames[candidate]
    return requested,[]

def number(value,digits=2):
    try:return f'{float(value):,.{digits}f}'
    except (TypeError,ValueError):return '—'

def path_get(data,path,default=None):
    cur=data
    for part in path.split('.'):
        if not isinstance(cur,dict):return default
        cur=cur.get(part,default)
    return cur

def path_set(data,path,value):
    parts=path.split('.');cur=data
    for part in parts[:-1]:cur=cur.setdefault(part,{})
    cur[parts[-1]]=value

def replace_text(widget,value,preserve_scroll=True):
    value=str(value)
    if getattr(widget,'_akira_text',None)==value:return False
    try:top=widget.yview()[0]
    except Exception:top=0.0
    try:at_end=widget.yview()[1]>.985
    except Exception:at_end=False
    widget._akira_text=value;widget.configure(state='normal');widget.delete('1.0','end');widget.insert('1.0',value);widget.configure(state='disabled');link_urls(widget)
    # Las fuentes cambian de edad continuamente. Antes cada refresh devolvía el
    # scroll al inicio, haciendo imposible leer hacia abajo. Conservamos la vista.
    try:
        if preserve_scroll:
            widget.yview_moveto(max(0.0,min(1.0,top)))
        elif at_end:
            widget.see('end')
    except Exception:pass
    return True

def link_urls(widget):
    # Los enlaces requieren un clic; jamás se abren por contenido externo o por la IA.
    for name in widget.tag_names():
        if name.startswith('url_'):widget.tag_delete(name)
    body=widget.get('1.0','end-1c')
    for i,match in enumerate(re.finditer(r'https?://[^\s<>]+',body)):
        url=match.group(0).rstrip('.,)');tag='url_'+str(i)
        widget.tag_add(tag,'1.0+'+str(match.start())+'c','1.0+'+str(match.start()+len(url))+'c')
        widget.tag_configure(tag,foreground=CYAN,underline=True)
        widget.tag_bind(tag,'<Button-1>',lambda event,address=url:webbrowser.open(address))

class CandleChart(tk.Canvas):
    def __init__(self,parent,height=180):
        super().__init__(parent,bg=BG,highlightthickness=1,highlightbackground=LINE,height=height)
        self.data={};self._resize_job=None;self.bind('<Configure>',self._on_resize)
    def _on_resize(self,event=None):
        # Multiple configure events while resizing can otherwise rasterize charts
        # hundreds of times per second (CPU, GPU compositor and laptop battery).
        if self._resize_job is not None:
            try:self.after_cancel(self._resize_job)
            except tk.TclError:pass
        self._resize_job=self.after(175,self._flush_resize)

    def _flush_resize(self):
        self._resize_job=None
        self.redraw()

    def update_data(self,data):
        signature=(data.get('indicator'),data.get('timeframe'),data.get('bid'),data.get('selected_key'),data.get('market_closed'),
            tuple((b.get('time'),b.get('open'),b.get('high'),b.get('low'),b.get('close')) for b in data.get('bars',[])),
            tuple((p.get('key'),p.get('entry'),p.get('sl'),p.get('tp')) for p in data.get('scenario_book',[])),
            tuple((p.get('ticket'),p.get('entry')) for p in data.get('pending_book',[]) if p.get('confirmed')),
            repr((data.get('runner') or {}).get('plan')))
        self.data=data
        if signature==getattr(self,'signature',None):return
        self.signature=signature
        try:self.redraw()
        except Exception:
            self.signature=None
            raise
    def redraw(self):
        from chart_render import render
        try:render(self)
        except Exception:
            self.signature=None
            raise

class SymbolPanel(tk.Frame):
    def __init__(self,parent,app,symbol):
        super().__init__(parent,bg=PANEL,padx=14,pady=12,bd=0,highlightthickness=1,highlightbackground=LINE);self.symbol=symbol;self.app=app
        self.panel_shell,self.panel_content=scroll_frame(self,PANEL);self.panel_shell.pack(fill='both',expand=True)
        head=tk.Frame(self.panel_content,bg=PANEL);head.pack(fill='x');label(head,'ORO · '+symbol if symbol.startswith('XAU') else 'BITCOIN · '+symbol,TEXT,12,True).pack(side='left')
        self.price=label(head,size=9,color=MUTED,anchor='e');self.price.pack(side='right');self.status=label(self.panel_content,'CARGANDO MT5...',AMBER,9,True,anchor='w');self.status.pack(fill='x',pady=4)
        self.detail=label(self.panel_content,color=MUTED,size=8,justify='left',anchor='w',height=3);self.detail.pack(fill='x')
        controls=tk.Frame(self.panel_content,bg=PANEL);controls.pack(fill='x',pady=6)
        self.auto_map=label(controls,'AUTO-MAPA ACTIVO',CYAN,8,True,anchor='w');self.auto_map.pack(side='left',fill='x',expand=True)
        copy_button=button(controls,'COPIAR',self.copy_selected_levels,MUTED);copy_button.configure(padx=7,pady=5,font=(FONT,8,'bold'));copy_button.pack(side='right',padx=(6,0))
        self.tf_var=tk.StringVar(value='M15')
        self.tf_combo=ttk.Combobox(controls,textvariable=self.tf_var,values=('M1','M5','M15','M30','H1','H4','D1'),state='readonly',width=6,style='Akira.TCombobox')
        self.tf_combo.pack(side='right',padx=(8,0));self.tf_combo.bind('<<ComboboxSelected>>',lambda e:self.render(self.app.view))
        extra=tk.Frame(self.panel_content,bg=PANEL);extra.pack(fill='x',pady=(0,4));self.more_controls=extra
        from chart_indicators import OPTIONS
        self.indicator_var=tk.StringVar(value=app.cfg.get('charts',{}).get('indicator','Medias y Bollinger'))
        self.indicator_combo=ttk.Combobox(extra,textvariable=self.indicator_var,values=OPTIONS,state='readonly',style='Akira.TCombobox',width=21);self.indicator_combo.pack(side='left')
        self.indicator_combo.bind('<<ComboboxSelected>>',lambda e:self.render(app.view))
        b=button(extra,'INDICADORES',lambda:app.open_chart_details(symbol,self.tf_var.get()),MUTED);b.configure(padx=7,pady=5,font=(FONT,8));b.pack(side='right')
        self.verify_label=label(self.panel_content,'COBERTURA · esperando datos del motor',MUTED,8,anchor='w',justify='left',wraplength=650);self.verify_label.pack(fill='x')
        self.verify_label.bind('<Button-1>',lambda event:app.open_verification(self.symbol));self.verify_label.configure(cursor='hand2')
        self.verify_bar=ttk.Progressbar(self.panel_content,style='Cyber.Horizontal.TProgressbar',maximum=100);self.verify_bar.pack(fill='x',pady=(2,3))
        from cyber_ui import VerificationStages
        self.verify_stages=VerificationStages(self.panel_content,lambda:app.open_verification(self.symbol));self.verify_stages.pack(fill='x',pady=(0,3))
        # Keep coverage visible when the user's panels are short. Controls and
        # charts retain their own movable split below this small status group.
        self.verify_label.pack(before=self.detail,fill='x')
        self.verify_bar.pack(before=self.detail,fill='x',pady=(2,3))
        self.verify_stages.pack(before=self.detail,fill='x',pady=(0,3))
        self.verify_pending_button=button(controls,'VERIFICAR',self.verify_selected,CYAN);self.verify_pending_button.configure(padx=6,pady=5,font=(FONT,8,'bold'));self.verify_pending_button.pack(side='right',padx=3)
        split=app.layout.pane(self.panel_content,'symbol_'+symbol,tk.VERTICAL,(.53,.84));split.pack(fill='both',expand=True,pady=6);self.split=split
        self.chart=CandleChart(split,height=205);split.add(self.chart,minsize=70,stretch='always')
        split.configure(height=390)
        table=tk.Frame(split,bg=PANEL);split.add(table,minsize=80,stretch='always')
        cols=('ticket','type','entry','sl','tp','quality','activation','risk')
        self.tree=ttk.Treeview(table,columns=cols,show='headings',height=5)
        for key,title,width in zip(cols,('MT5 / PROPUESTA','TIPO','ENTRADA','SL','TP','ESTRELLAS','CERCANÍA','RIESGO'),(130,106,100,100,100,85,95,80)):
            self.tree.heading(key,text=title);self.tree.column(key,width=width,minwidth=60,anchor='center',stretch=True)
        self.tree.tag_configure('confirmed',foreground=GREEN);self.tree.tag_configure('candidate',foreground=CYAN);self.tree.tag_configure('analysis',foreground=BLUE);self.tree.tag_configure('blocked',foreground=AMBER)
        scrollbar=ttk.Scrollbar(table,orient='horizontal',command=self.tree.xview);scrollbar.pack(side='bottom',fill='x');self.tree.configure(xscrollcommand=scrollbar.set)
        vertical=ttk.Scrollbar(table,orient='vertical',command=self.tree.yview,style='Akira.Vertical.TScrollbar');vertical.pack(side='right',fill='y');self.tree.configure(yscrollcommand=vertical.set)
        self.tree.pack(side='left',fill='both',expand=True);self.tree.bind('<<TreeviewSelect>>',self.show_reason)
        self.reason=text_box(split,3);self.reason_visible=False;self.rows=[];self.signature=None
        self.bind('<Configure>',self.fit_verification)

    def fit_verification(self,event):
        compact=event.height<400
        self.detail.configure(wraplength=max(200,event.width-30),height=1 if compact else 3)
        self.verify_label.configure(wraplength=max(200,event.width-30),height=2 if compact else 3)
        if compact!=getattr(self,'_verification_compact',None):
            self._verification_compact=compact
            if compact:
                self.detail.pack_forget();self.more_controls.pack_forget();self.verify_stages.frame.pack_forget()
            else:
                self.detail.pack(before=self.verify_pending_button.master,fill='x')
                self.more_controls.pack(before=self.split,fill='x',pady=(0,4))
                self.verify_stages.pack(before=self.detail,fill='x',pady=(0,3))
            self.split.paneconfigure(self.chart,minsize=40 if compact else 70)
            self.split.paneconfigure(self.tree.master,minsize=45 if compact else 80)
    def render(self,view):
        info=view.get('symbols',{}).get(self.symbol,{});state=view.get('status',{}).get(self.symbol,{})
        from operation_verifier import verification
        check=verification(view,self.symbol)
        from datetime import datetime,timezone
        stamp=datetime.fromtimestamp(check['updated'],timezone.utc).strftime('%H:%M:%S UTC') if check['updated'] else 'sin actualización'
        detail=check['execution_block'] or ('Faltan: '+', '.join(check['missing'][:2]) if check['missing'] else 'Datos vigentes; cada nuevo envío se revalida con MT5.')
        self.verify_label.configure(text=check['activity']+' · ciclo '+str(check['cycle'] or '—')+' · '+stamp+'\nCOBERTURA '+str(check['completed'])+'/'+str(check['total'])+' · '+detail[:170]+' · pulsa para ver detalles',fg=AMBER if check['execution_block'] or 'SIN ACTUALIZACIÓN' in check['activity'] else CYAN)
        individual=view.get('pending_verifications') or {}
        chosen=next((r for r in individual.values() if r.get('symbol')==self.symbol and r.get('key')==getattr(self,'selected_key',None)),None)
        relevant=[r for r in individual.values() if r.get('symbol')==self.symbol and r.get('confirmed')]
        coverage=chosen or (min(relevant,key=lambda r:r['progress']) if relevant else None)
        self.verify_bar.configure(value=coverage['progress'] if coverage else check['progress'])
        if coverage:self.verify_label.configure(text=coverage['id']+' · VERIFICACIÓN · COBERTURA '+str(coverage['completed'])+'/'+str(coverage['total'])+' · ciclo '+str(check['cycle'])+' · '+coverage['state']+'\n'+('Falta: '+', '.join(coverage['missing'][:2]) if coverage['missing'] else 'Revisión vigente; pulsa para ver su evidencia.'))
        self.verify_stages.render({**check,'stages':coverage['stages'] if coverage else check['stages']})
        self.price.configure(text=number(info.get('bid'))+' / '+number(info.get('ask')))
        self.status.configure(text=state.get('state','CARGANDO'),fg=GREEN if 'CONFIRM' in state.get('state','') else AMBER)
        runner=info.get('runner') or {}
        runner_text='\nRunner: '+str(runner.get('state',''))+' · '+str(runner.get('detail','')) if runner else ''
        self.detail.configure(text=state.get('detail','Esperando datos')+runner_text)
        requested=self.tf_var.get() if hasattr(self,'tf_var') else 'M1'
        tf,bars=available_chart_frame(info,requested)
        if tf!=requested and hasattr(self,'tf_var'):self.tf_var.set(tf)
        chart_info=dict(info);chart_info['timeframe']=tf;chart_info['bars']=bars
        closed=bool((view.get('markets') or {}).get(self.symbol,{}).get('scheduled_closed'))
        chart_info['market_closed']=closed;chart_info['indicator']=self.indicator_var.get();chart_info['engine_frame']=info.get('frames',{}).get(tf,{});chart_info['runner_levels']=[{**p,'kind':'position','side':1 if p.get('type')==0 else -1} for p in view.get('positions',[]) if p.get('symbol')==self.symbol]
        self.auto_map.configure(text='MERCADO CERRADO' if closed else 'AUTO-MAPA ACTIVO',fg=AMBER if closed else CYAN)
        chart_info['selected_key']=getattr(self,'selected_key',None)
        self.chart.update_data(chart_info);rows=info.get('scenario_book') or info.get('pending_book',[])
        rows=sorted(rows,key=lambda p:(not p.get('confirmed'),not p.get('sendable'),-float(p.get('quality_score') or 0)))
        signature=json.dumps(rows,sort_keys=True,default=str)
        if signature==self.signature:return
        self.signature=signature;self.rows=rows;selected=self.tree.selection();selected=selected[0] if selected else None
        self.tree.delete(*self.tree.get_children());audit=view.get('audit',{}).get(self.symbol,[])
        for i,p in enumerate(rows):
            record=next((r for r in audit if r.get('key')==p.get('key')),{});live=p.get('confirmed',False);sendable=bool(p.get('sendable',not p.get('scenario_state','').startswith('BLOQUEADA')))
            scenario_state=str(p.get('scenario_state') or '')
            analysis_only=not sendable and not live
            tag='confirmed' if live else 'candidate' if sendable else 'analysis' if analysis_only else 'blocked'
            first=('#'+str(p.get('ticket'))) if live else ('LISTA' if sendable else 'PROPUESTA · REVISAR')
            self.tree.insert('','end',iid=str(i),tags=(tag,),values=(
                first,('BUY' if p['side']==1 else 'SELL')+' '+str(p.get('kind','—')),
                number(p.get('entry'),3),number(p.get('sl'),3),number(p.get('tp'),3),
                stars(p).replace('⭐','★') if p.get('quality_score') else '—',number(p.get('activation_score'),0),number(p.get('risk_usd',record.get('risk_usd')))))
        if selected and self.tree.exists(selected):self.tree.selection_set(selected)
    def show_reason(self,event=None):
        sel=self.tree.selection()
        if sel and int(sel[0])<len(self.rows):
            if not self.reason_visible:
                self.split.add(self.reason,minsize=65,stretch='always');self.reason_visible=True
                self.app.root.after_idle(lambda:self.app.layout.restore('symbol_'+self.symbol))
            p=self.rows[int(sel[0])];detail=p.get('block_reason') or p.get('reason','')
            self.selected_key=p.get('key');self.chart.update_data({**self.chart.data,'selected_key':self.selected_key})
            extra=''
            if p.get('required_risk_usd') is not None:
                extra=f" · riesgo mínimo aprox {number(p.get('required_risk_usd'))} USD / cap {number(p.get('risk_cap_usd'))} USD"
            replace_text(self.reason,assessment_text(p)+'\n'+str(p.get('scenario_state') or p.get('state',''))+' · '+str(detail)+extra)
            equity=float((self.app.view.get('account') or {}).get('equity') or 0)
            risk=float(p.get('required_risk_usd') or p.get('risk_usd') or 0)
            if equity>0 and risk>0:self.reason.configure(state='normal');self.reason.insert('end',f'\nEsto equivale aproximadamente al {risk/equity*100:.1f}% de tu cuenta si alcanza el SL.');self.reason.configure(state='disabled')

    def copy_selected_levels(self):
        selected=self.tree.selection()
        if not selected:
            messagebox.showinfo('Akira','Selecciona primero un escenario de la tabla.',parent=self.app.root);return
        p=self.rows[int(selected[0])]
        side='BUY' if int(p.get('side',1))==1 else 'SELL'
        text=f"{self.symbol} | {side} {p.get('kind')} | Entry {p.get('entry')} | SL {p.get('sl')} | TP {p.get('tp')} | {p.get('scenario_state','Propuesta')}"
        self.clipboard_clear();self.clipboard_append(text)
        messagebox.showinfo('Akira','Parámetros copiados. Es una propuesta técnica; no implica una orden colocada.',parent=self.app.root)

    def verify_selected(self):
        from pending_verification import identity
        selection=self.tree.selection();pid=None
        if selection and int(selection[0])<len(self.rows):pid=identity({**self.rows[int(selection[0])],'symbol':self.symbol})
        self.app.open_verification(self.symbol,pid)
        if pid:self.app.request_pending_verification(self.symbol,pid,True)

from desktop_services import DesktopServices

class Desktop(DesktopServices,StrategyDirectory):
    def __init__(self,root,folder,preview=False,start_actor=True):
        if not start_actor and not preview:raise ValueError('El modo sin actor solo se permite en la autocomprobación con datos sintéticos.')
        self.root,self.folder,self.preview=root,Path(folder),preview;self.cfg=load_config(self.folder/'akira_config.json')
        from akira_studio import UserCatalog
        from akira_expressions import get_catalog
        from akira_live2d import _root as _asset_root
        from studio_theme import apply_theme
        apply_theme(self.cfg['studio'],root)
        avatar_cfg=self.cfg['studio']['avatar']
        if avatar_cfg.get('active') and avatar_cfg.get('entries'):
            self.root._akira_user_catalog=UserCatalog(get_catalog(_asset_root()),avatar_cfg)
        self.stop=threading.Event();self.commands=queue.Queue();self.messages=queue.Queue(maxsize=2);self.events=queue.Queue(maxsize=1000);self.replies=queue.Queue();self.chat_progress=queue.Queue(maxsize=250)
        self.paused=False;self.view={};self.chat_busy=False;self.display_due=0.0;self.panels={};self.charts={};self.avatars=[];self.chat_started=0.0;self.chat_stage='LISTO';self.chat_stage_detail='';self.chat_source_names=[];self._chat_anim_phase=0
        self._last_deep_stamp=0.0;self._last_pending_signature=None;self._toast_windows=[]
        self.map_request_busy=False
        self._voice_download_job=None;self._voice_download_busy=False;self._voice_download_last={};self._voice_single_cancel=None
        self.voice_window=None;self.voice_call_active=False;self.voice_session=None;self.voice_awaiting=False;self._voice_catalog=[];self._voice_devices={'inputs':[],'outputs':[]}
        self.report_busy=False;self.report_window=None;self.report_model=None;self.report_generation=0
        self.bridge=CommandBridge(self.commands);self.bridge.starting=True;self.assistant=AkiraAssistant(self.cfg,self.folder,self.bridge.request,self.progress_event,auto_prepare=False)
        self._ui_error_times={};self._assistant_display_due=0.0;self._performance=get_intervals(self.cfg)
        from collections import deque
        self._terminal_pending=deque(maxlen=500)
        set_identity();root.title('AKIRA · 16.3.5 · R8 Studio');root.title(self.cfg['studio']['brand_name']+' · 16.3.5 · R8 Studio Rev4');root.configure(bg=BG)
        width,height,min_width,min_height=fitted_geometry(self.cfg['desktop']['width'],self.cfg['desktop']['height'],root.winfo_screenwidth(),root.winfo_screenheight())
        root.geometry(f'{width}x{height}');root.minsize(min_width,min_height)
        self.layout=PanelLayout(root,self.folder/'state'/'desktop_layout.json')
        apply_window_icon(root,self.folder)
        root.after(120,lambda:apply_dark_titlebar(root))
        self.configure_style();self.init_services();self.build_shell();self.build_header()
        self.book=ttk.Notebook(self.main,style='Cyber.TNotebook');self.book.pack(fill='both',expand=True,padx=10,pady=(2,8))
        self.pages={}
        for name,title in zip(TAB_NAMES,TAB_TITLES):
            frame=tk.Frame(self.book,bg=BG);self.book.add(frame,text=title);self.pages[name]=frame
        self.build_dashboard(self.pages[TAB_NAMES[0]]);self.build_pending(self.pages[TAB_NAMES[1]])
        self.build_account(self.pages[TAB_NAMES[2]]);self.build_analysis(self.pages[TAB_NAMES[3]])
        self.build_sources(self.pages[TAB_NAMES[4]]);self.build_chat(self.pages[TAB_NAMES[5]])
        self.build_settings(self.pages[TAB_NAMES[6]]);self.build_terminal(self.pages[TAB_NAMES[7]])
        from akira_studio import apply_language_pack
        if self.cfg['studio'].get('language_pack'):
            self.root.after_idle(lambda:apply_language_pack(self.root,
                self.cfg['studio'].get('language_pack',''),self.cfg['studio']['language_ui']))
        from desktop_layout import add_table_scrollbars
        add_table_scrollbars(self.root)
        self.root.after_idle(self._apply_responsive_shell)
        for avatar in self.avatars:
            if hasattr(avatar,'set_refresh_interval'):avatar.set_refresh_interval(self._performance['avatar_ms'])
        self.book.bind('<<NotebookTabChanged>>',lambda e:self._sync_navigation())
        self.navigate(1)
        root.bind('<Control-l>',self.open_chat)
        root.bind('<Control-L>',self.open_chat)
        # Wheel events are registered once for all Tk Toplevels by scroll_frame.
        # Binding here as well would double-scroll the main window.
        self.log=Reporter(self.folder/'logs',callback=self.event,console=False)
        root.report_callback_exception=self.ui_callback_error
        self.thread=None
        if start_actor:
            self.thread=threading.Thread(target=run_session,args=(self.cfg,self.folder,self.log,self.stop,self.commands,self.publish,self.preview),daemon=True,name='AkiraMT5Actor');self.thread.start()
        root.protocol('WM_DELETE_WINDOW',self.close);self._poll_after_id=root.after(self._performance["poll_ms"],self.poll)
        if self.use_cloud.get() and not preview:root.after(2500,self.check_cloud)  # defer noncritical web status until UI is responsive

    def configure_style(self):
        global FONT,MONO
        FONT,MONO=cyber_style(self.root)
        import desktop_services
        desktop_services.FONT=FONT

    def build_shell(self):
        shell=tk.Frame(self.root,bg=BG);shell.pack(fill='both',expand=True)
        self.sidebar=tk.Frame(shell,bg=BG,width=208,padx=12,pady=12)
        self.sidebar.pack(side='left',fill='y');self.sidebar.pack_propagate(False)
        tk.Frame(shell,bg=LINE,width=1).pack(side='left',fill='y')
        self.main=tk.Frame(shell,bg=BG);self.main.pack(side='left',fill='both',expand=True)
        self.brand_title=label(self.sidebar,self.cfg['studio']['brand_name'],CYAN,24,True,anchor='w');self.brand_title.pack(fill='x',padx=6)
        label(self.sidebar,'ASISTENTE · MT5',MUTED,8,anchor='w',wraplength=135,justify='left').pack(fill='x',padx=7,pady=(0,10))
        tk.Frame(self.sidebar,bg=LINE,height=1).pack(fill='x',pady=(0,10))
        outer,inner=neon_card(self.sidebar,'',CYAN,padx=4,pady=4)
        self.sidebar_avatar=outer;outer.pack(fill='x',pady=(0,10))
        self.sidebar_avatar_image=self.avatar(inner,170,115);self.sidebar_avatar_image.pack(fill='x')
        self.sidebar_status=label(inner,'AKIRA · preparando',MUTED,8,anchor='center',wraplength=145);self.sidebar_status.pack(fill='x',pady=(2,4))
        self.side_footer=tk.Frame(self.sidebar,bg=BG);self.side_footer.pack(side='bottom',fill='x',pady=(8,0))
        tk.Frame(self.side_footer,bg=LINE,height=1).pack(fill='x',pady=(0,9))
        self.side_connection=label(self.side_footer,'MT5 · conectando',MUTED,8,anchor='w');self.side_connection.pack(fill='x')
        label(self.side_footer,'AKIRA · 16.3.5',CYAN,8,anchor='w').pack(fill='x',pady=(4,0))
        label(self.sidebar,'MÓDULOS',MUTED,8,anchor='w').pack(fill='x',padx=4,pady=(0,5))
        nav_shell,nav_content=scroll_frame(self.sidebar,BG);nav_shell.pack(fill='both',expand=True)
        self.nav_buttons=[]
        for i,(glyph,title) in enumerate(zip(('□','≡','▥','⌁','◎','◇','⚙','▤'),TAB_TITLES)):
            from akira_studio import UI_LABELS
            locale=self.cfg['studio']['language_ui']
            shown=UI_LABELS.get(locale,UI_LABELS['es'])[i]
            nav=button(nav_content,shown,lambda index=i:self.navigate(index),MUTED)
            nav.configure(anchor='w',padx=14,pady=9);nav.pack(fill='x',pady=3);self.nav_buttons.append(nav)
        self.root.bind('<Configure>',self._responsive_shell,add='+')

    def navigate(self,index):
        self.book.select(self.pages[TAB_NAMES[index]]);self._sync_navigation(index)
        if index==5:self.root.after_idle(self.chat_entry.focus_set)

    def _sync_navigation(self,index=None):
        if index is None:
            try:index=next(i for i,key in enumerate(TAB_NAMES) if str(self.pages[key])==str(self.book.select()))
            except (TypeError,StopIteration):return
        self.current_page_index=index
        ambient=getattr(self,'_ambient_wallpaper',None)
        if ambient is not None:
            if index!=0:ambient.stop()
            elif not ambient.running:self.root.after(180,ambient.start)
        self.display_due=0.0  # Draw newly selected page on next poll, not every hidden page
        for i,nav in enumerate(self.nav_buttons):
            nav.configure(bg=CARD if i==index else BG,fg=TEXT if i==index else MUTED,
                highlightbackground=CYAN if i==index else BG)
        self.page_crumb.configure(text='AKIRA / '+TAB_TITLES[index])
        from akira_studio import UI_LABELS
        from localized_navigation import heading,subtitle
        locale=self.cfg['studio']['language_ui']
        self.page_title.configure(text=heading(locale,index,PAGE_TITLES))
        self.page_detail.configure(text=subtitle(locale,index,PAGE_DETAILS))
        self.page_index.configure(text='AKIRA // COMMAND SYSTEM · '+f'{index+1:02d}')
        metrics=index in (0,1,2,3)
        if metrics!=getattr(self,'_metrics_visible',True):
            self._metrics_visible=metrics
            if metrics:self.metric_strip.pack(fill='x',padx=15,pady=(0,4),before=self._page_heading)
            else:self.metric_strip.pack_forget()

    def _responsive_shell(self,event):
        if event.widget is not self.root:return
        size=(event.width,event.height)
        if getattr(self,'_last_shell_event_size',None)==size:return
        self._last_shell_event_size=size
        if getattr(self,'_responsive_job',None) is not None:
            self.root.after_cancel(self._responsive_job)
        self._responsive_job=self.root.after(75,self._apply_responsive_shell)

    def _apply_responsive_shell(self):
        self._responsive_job=None
        if not hasattr(self,'page_detail'):return
        width,height=self.root.winfo_width(),self.root.winfo_height()
        compact=width<1250 or height<780
        short=height<780
        if compact!=getattr(self,'_compact_shell',None):
            self._compact_shell=compact;self.sidebar.configure(width=158 if compact else 208)
            self.sidebar_avatar_image.configure(height=90 if compact else 150)
            self.sidebar_avatar_image.pack_propagate(False)
            for nav in self.nav_buttons:nav.configure(pady=5 if compact else 9,padx=8 if compact else 14,font=(FONT,8 if compact else 9,'bold'))
            self.page_title.configure(font=(FONT,15 if compact else 21,'bold'))
            from tkinter import font as tkfont
            for size in range(24,11,-1):
                if tkfont.Font(self.root,family=FONT,size=size,weight='bold').measure('AKIRA')<=((158 if compact else 208)-30):break
            self.brand_title.configure(font=(FONT,size,'bold'))
        # A second row of metrics used to take the space needed by the page.
        # Keep six compact values on short laptop screens instead.
        columns=6 if short or width>=1180 else 3
        if columns!=getattr(self,'_metric_columns',None):
            self._metric_columns=columns
            for i,card in enumerate(self.metric_cards):card.grid(row=i//columns,column=i%columns,sticky='nsew',padx=3,pady=2)
            for i in range(6):self.metric_strip.columnconfigure(i,weight=1 if i<columns else 0,uniform='metrics' if i<columns else '')
        if short!=getattr(self,'_short_shell',None):
            self._short_shell=short
            for widget in (self.page_index,self.page_detail):
                if short:widget.pack_forget()
                else:widget.pack(fill='x',pady=(2,0))
        available=max(250,width-(158 if compact else 208)-48)
        self.connection.configure(wraplength=available);self.map_result_label.configure(wraplength=available)
        self.page_detail.configure(wraplength=available)
        self._fit_header_actions(available)
        self._fit_metrics()

    def _fit_header_actions(self,width):
        # Grid reserves every button's space; pack(side=right) silently clipped
        # the first controls when the available width got smaller.
        for item in self._toolbar_buttons:
            item.configure(padx=5,pady=5,font=(FONT,8,'bold'))
        # The same point size occupies different pixels across Windows fonts
        # and DPI settings. Reserve enough space for the widest button label.
        unit=max(item.winfo_reqwidth() for item in self._toolbar_buttons)+6
        columns=max(1,min(3,int(width//unit)))
        if columns!=getattr(self,'_toolbar_columns',None):
            self._toolbar_columns=columns
            for i,item in enumerate(self._toolbar_buttons):
                item.grid(row=i//columns,column=i%columns,sticky='ew',padx=3,pady=2)
            for i in range(4):self._toolbar.columnconfigure(i,weight=1 if i<columns else 0,uniform='actions' if i<columns else '')
        if columns<3:
            self.account_label.grid(row=1,column=0,columnspan=3,sticky='w',pady=(3,0))
        else:self.account_label.grid(row=0,column=3,columnspan=1,sticky='e',padx=(10,0))

    def _fit_metrics(self):
        if not getattr(self,'_metrics_visible',True):return
        try:
            from tkinter import font
            if not hasattr(self,'_metric_font'):self._metric_font=font.Font(self.root,family=FONT,size=16,weight='bold')
            for metric in self.metrics.values():
                width=max(70,metric.winfo_width()-3);text=str(metric.cget('text'))
                signature=(text,width)
                if getattr(metric,'_fit_signature',None)==signature:continue
                metric._fit_signature=signature
                for size in range(16,9,-1):
                    self._metric_font.configure(size=size)
                    if self._metric_font.measure(text)<=width:break
                long=self._metric_font.measure(text)>width
                metric.configure(font=(FONT,9 if long else size,'bold'),wraplength=width if long else 0,height=2 if long else 1)
        except (AttributeError,tk.TclError):pass

    def build_header(self):
        head=tk.Frame(self.main,bg=BG);head.pack(fill='x',padx=12,pady=(8,3));head.columnconfigure(0,weight=1)
        self.page_crumb=label(head,'AKIRA / PENDIENTES',TEXT,10,True,anchor='w');self.page_crumb.grid(row=0,column=0,sticky='w')
        self.account_label=label(head,'Conectando a MT5...',MUTED,9,anchor='w')
        self.privacy_button=button(head,'OCULTAR IMPORTES',self.toggle_account_privacy,MUTED);self.privacy_button.configure(padx=5,pady=3,font=(FONT,8));self.privacy_button.grid(row=0,column=2,padx=4)
        self.notice_button=button(head,'AVISOS 0',self.open_notifications,CYAN);self.notice_button.configure(padx=7,pady=3,font=(FONT,8));self.notice_button.grid(row=0,column=1,padx=4)
        tk.Frame(self.main,bg=LINE,height=1).pack(fill='x',padx=12,pady=(0,3))
        toolbar=tk.Frame(self.main,bg=BG);self._toolbar=toolbar;toolbar.pack(fill='x',padx=9,pady=(0,3))
        self.reset_layout_button=button(toolbar,'RESTABLECER PANELES',self.layout.reset,MUTED)
        self.toggle=button(toolbar,'PAUSAR CONTROL',self.pause,AMBER)
        report=button(toolbar,'DESCARGAR INFORME',self.open_report_dialog,BLUE)
        self._toolbar_buttons=(self.reset_layout_button,report,self.toggle)
        statebar=tk.Frame(self.main,bg=BG);statebar.pack(fill='x',padx=14,pady=(0,3))
        self.mode_button=button(statebar,'ACTIVAR OPERATIVA',self.toggle_execution_mode,AMBER)
        self.mode_button.configure(font=(FONT,8,'bold'),padx=7,pady=4);self.mode_button.pack(side='right',padx=(8,0))
        self.connection=label(statebar,'Preparando conexión y niveles de MT5',MUTED,8,anchor='w',justify='left',wraplength=700);self.connection.pack(side='left',fill='x',expand=True)
        self.map_result_label=label(self.main,'Akira revisa pendientes y runners en segundo plano.',MUTED,8,anchor='w',justify='left')
        self.map_result_label.pack(side='bottom',fill='x',padx=20,pady=(0,4))
        self.metrics={};self.metric_cards=[];self.metric_strip=tk.Frame(self.main,bg=BG);self.metric_strip.pack(fill='x',padx=15,pady=(0,4))
        for i,(key,title,accent) in enumerate((('balance','BALANCE',TEXT),('equity','PATRIMONIO',CYAN),('floating','FLOTANTE',PINK),('daily','P/L DEL DÍA',RED),('risk','RIESGO',AMBER),('cycle','CICLO',BLUE))):
            self.metric_strip.columnconfigure(i,weight=1,uniform='metrics')
            outer,inner=neon_card(self.metric_strip,'',accent,padx=11,pady=6);outer.grid(row=0,column=i,sticky='nsew',padx=4,pady=3);self.metric_cards.append(outer)
            label(inner,title,MUTED,8,True,anchor='w').pack(fill='x',pady=(0,4))
            value=label(inner,'—',accent,16,True,anchor='w');value.pack(fill='x');self.metrics[key]=value
        heading=tk.Frame(self.main,bg=BG);self._page_heading=heading;heading.pack(fill='x',padx=12,pady=(2,3))
        self.page_index=label(heading,'AKIRA // COMMAND SYSTEM · 02',CYAN,8,True,anchor='w');self.page_index.pack(fill='x')
        self.page_title=label(heading,'PENDIENTES AUTOMÁTICAS',TEXT,21,True,anchor='w');self.page_title.pack(fill='x',pady=(2,0))
        self.page_detail=label(heading,PAGE_DETAILS[1],MUTED,9,anchor='w',justify='left');self.page_detail.pack(fill='x',pady=(2,0))
    def avatar(self,parent,width=270,height=250):
        frame=AkiraLive2D(parent,width=width,height=height,bg=PANEL,director=getattr(self,'avatar_director',None));self.avatar_director=frame.director;self.avatars.append(frame);return frame
    def build_dashboard(self,page):
        """Neon control center: real activity, avatar/alerts and BTC/XAU charts.

        A native Tk layout, not a fake screenshot or duplicate trade executor.
        All actions route through the existing application methods and broker.
        """
        split=self.layout.pane(page,'dashboard_vertical',tk.VERTICAL,(.40,))
        split.pack(fill='both',expand=True,pady=4)
        top=self.layout.pane(split,'dashboard_columns',tk.HORIZONTAL,(.69,))
        # High-DPI Windows spends much of a 768 px display on headers. Reserve
        # room for visible, genuinely painted BTC/XAU candles before activity.
        # The upper pane remains draggable; the other pages retain full logs.
        split.add(top,minsize=150,stretch='always')
        outer,activity=neon_card(top,'ACTIVIDAD EN TIEMPO REAL',CYAN,padx=10,pady=7)
        top.add(outer,minsize=360,stretch='always')
        tools=tk.Frame(activity,bg=PANEL);tools.pack(fill='x',pady=(0,6))
        label(tools,'Eventos del motor, revisiones y decisiones confirmadas',MUTED,8,anchor='w').pack(side='left',fill='x',expand=True)
        button(tools,'ABRIR REGISTROS',lambda:self.navigate(7),CYAN).pack(side='right',padx=3)
        events_body=tk.Frame(activity,bg=PANEL);events_body.pack(fill='both',expand=True)
        columns=('time','level','module','symbol','message')
        self.dashboard_activity=ttk.Treeview(events_body,columns=columns,show='headings',height=6,selectmode='browse')
        for key,title,width in zip(columns,('HORA','NIVEL','MÓDULO','SÍMBOLO','ACTIVIDAD'),(75,95,100,95,420)):
            self.dashboard_activity.heading(key,text=title)
            self.dashboard_activity.column(key,width=width,minwidth=55,stretch=key=='message',anchor='w')
        self.dashboard_activity.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(events_body,orient='vertical',command=self.dashboard_activity.yview)
        scroll.pack(side='right',fill='y');self.dashboard_activity.configure(yscrollcommand=scroll.set)
        self.dashboard_activity.tag_configure('warning',foreground=AMBER)
        self.dashboard_activity.tag_configure('blocked',foreground=RED)
        self.dashboard_activity.tag_configure('normal',foreground=TEXT)
        summary=tk.Frame(activity,bg=PANEL);summary.pack(fill='x',pady=(5,0))
        label(summary,'RESUMEN DE AKIRA',CYAN,9,True,anchor='w').pack(fill='x')
        self.brain_status=text_box(summary,3);self.brain_status.configure(font=(FONT,9),pady=5,padx=8)
        self.brain_status.pack(fill='x',pady=(3,0))

        # Right status and actions; avatar only animates in the visible page.
        right=self.layout.pane(top,'dashboard_neon_right',tk.VERTICAL,(.58,))
        top.add(right,minsize=190,stretch='always')
        outer,state=neon_card(right,'AKIRA · ESTADO DEL SISTEMA',GREEN,padx=9,pady=6)
        right.add(outer,minsize=145,stretch='always')
        self.dashboard_avatar=self.avatar(state,240,120);self.dashboard_avatar.pack(fill='x',pady=(0,4))
        self.brain_label=label(state,'AKIRA · Preparando respuesta...',CYAN,9,True,
            justify='left',wraplength=370,anchor='w');self.brain_label.pack(fill='x',pady=3)
        self.dashboard_stats=label(state,'Esperando conexión',MUTED,8,anchor='w',justify='left',wraplength=360)
        self.dashboard_stats.pack(fill='x',pady=(1,4))
        source_board=tk.Frame(state,bg=PANEL);source_board.pack(fill='x',pady=(0,2))
        self.source_status={}
        for i,(key,title) in enumerate((('mt5','MT5'),('local','IA'),('web','NOTICIAS'),('youtube','VIDEO'),('coinglass','DATOS'),('investing','INVESTING'))):
            tile=tk.Frame(source_board,bg=CARD,padx=4,pady=3);tile.grid(row=i//3,column=i%3,sticky='ew',padx=2,pady=2)
            source_board.columnconfigure(i%3,weight=1,uniform='sources')
            label(tile,title,MUTED,7,True,anchor='w').pack(fill='x')
            self.source_status[key]=label(tile,'...',AMBER,8,True,anchor='w');self.source_status[key].pack(fill='x')
        outer,actions=neon_card(right,'ACCIONES RÁPIDAS / AVISOS',BLUE,padx=7,pady=6)
        right.add(outer,minsize=120,stretch='always')
        quick=tk.Frame(actions,bg=PANEL);quick.pack(fill='x')
        for i,(title,func) in enumerate((('INFORMES · PDF / EXCEL',self.open_report_dialog),('NUEVA REVISIÓN',lambda:self.request_map('ALL')),
            ('CHAT',self.open_chat),('PAUSAR GESTIÓN',self.pause))):
            quick.columnconfigure(i%2,weight=1)
            button(quick,title,func,CYAN if i%2==0 else MUTED).grid(row=i//2,column=i%2,sticky='ew',padx=3,pady=3)
        self.dashboard_alerts=label(actions,'Comprobando avisos...',MUTED,8,
            justify='left',anchor='w',wraplength=360)
        self.dashboard_alerts.pack(fill='x',pady=(6,0))

        lower=self.layout.pane(split,'dashboard_neon_lower',tk.VERTICAL,(.87,))
        split.add(lower,minsize=245,stretch='always')
        outer,market=neon_card(lower,'COBERTURA DE MERCADO · BTC + ORO',CYAN,padx=7,pady=5)
        # Allocate room for candles *and* Tk's DPI-scaled card headings.
        # Below 70 px the real chart renderer correctly refuses to draw.
        lower.add(outer,minsize=210,stretch='always')
        charts=tk.Frame(market,bg=PANEL);charts.pack(fill='both',expand=True)
        self.charts={}
        enabled=[symbol for symbol,on in self.cfg['symbols'].items() if on]
        for i,symbol in enumerate(enabled):
            charts.columnconfigure(i,weight=1,uniform='markets')
            card=tk.Frame(charts,bg=CARD,highlightthickness=1,highlightbackground=LINE,padx=5,pady=3)
            card.grid(row=0,column=i,sticky='nsew',padx=3,pady=1)
            charts.rowconfigure(0,weight=1)
            head=tk.Frame(card,bg=CARD);head.pack(fill='x')
            title=label(head,symbol,CYAN,10,True,anchor='w');title.pack(side='left',fill='x',expand=True)
            tf_var=tk.StringVar(value='M5')
            combo=ttk.Combobox(head,textvariable=tf_var,values=('M1','M5','M15','M30','H1','H4','D1'),
                state='readonly',width=5,style='Akira.TCombobox');combo.pack(side='right')
            chart=CandleChart(card,height=105);chart.pack(fill='both',expand=True,pady=2)
            info=label(card,'Esperando precio vigente',MUTED,8,anchor='w',wraplength=450)
            info.pack(fill='x');self.charts[symbol]=(chart,title,info,tf_var)
            card.bind('<Configure>',lambda event,w=info:w.configure(wraplength=max(100,event.width-22)))

        outer,bottom=neon_card(lower,'PENDIENTES CONFIRMADAS Y CANDIDATAS · CONSULTA',GREEN,padx=6,pady=3)
        lower.add(outer,minsize=45,stretch='always')
        columns=('symbol','side','kind','entry','sl','tp','quality','activation','state')
        self.dashboard_pending=ttk.Treeview(bottom,columns=columns,show='headings',height=2)
        for key,cap,w in zip(columns,('SÍMBOLO','LADO','TIPO','ENTRADA','SL','TP','CALIDAD','ACTIVACIÓN','ESTADO'),
            (85,55,75,100,100,100,70,80,230)):
            self.dashboard_pending.heading(key,text=cap)
            self.dashboard_pending.column(key,width=w,minwidth=50,anchor='center',stretch=True)
        self.dashboard_pending.pack(fill='both',expand=True)
        self._ambient_wallpaper=None
        # The user wallpaper is rendered inside a dedicated background preview
        # on the personalisation page. Tk does not support native translucent
        # child panels; never claim it composites behind every window.

    def render_dashboard_activity(self,row):
        """Presentation of actual actor states. No invented completed trades."""
        tree=getattr(self,'dashboard_activity',None)
        if tree is None:return
        statuses=row.get('status') or {}
        stamp=time.strftime('%H:%M:%S',time.localtime(float(row.get('updated') or time.time())))
        records=[]
        gate=row.get('execution_gate') or {}
        if gate and gate.get('code')!='TRADE_ENABLED':
            reason=str(gate.get('reason') or '')+' '+str(gate.get('next_action') or '')
            records.append(('SISTEMA','MODO '+str(gate['code']),reason,'warning'))
        watch=row.get('session_activity') or {}
        if watch.get('state') in ('ATTENTION','SIX_HOURS'):
            records.append(('SESION','SIN CONFIRMACIONES',
                str(round(float(watch.get('seconds_since_confirmed_ticket') or 0)/60))+' min · '+'; '.join(watch.get('reasons') or [])[:220],'warning'))
        for jid,job in (row.get('pending_verification_requests') or {}).items():
            if job.get('phase') in ('TIEMPO AGOTADO','REVISIÓN RECHAZADA O FALLIDA','DATOS O NIVELES CAMBIADOS','SIN SERVICIO DE IA'):
                records.append(('VERIFICACIÓN','REVISIÓN '+str(job['phase']),
                    str(job.get('completed',0))+'/'+str(job.get('total',0))+' · '+', '.join(job.get('missing',[])[:2]),'warning'))
        for symbol,state in statuses.items():
            if not isinstance(state,dict):continue
            status=str(state.get('state') or 'ESPERANDO')
            reason=str(state.get('detail') or '')
            risk_error=any(k in status.upper() for k in ('BLOQUE','ERROR','RECHAZ'))
            warn=risk_error or any(k in status.upper() for k in ('PAUSA','ESPERA','OBSERV'))
            records.append((symbol,status,reason,'blocked' if risk_error else 'warning' if warn else 'normal'))
        for symbol,info in row.get('symbols',{}).items():
            decision=info.get('decision') or {}
            if isinstance(decision,dict):
                msg=str(decision.get('reason') or decision.get('detail') or '')
                if msg:records.append((symbol,'DECISIÓN',msg,'normal'))
        signature=tuple(records)
        if getattr(self,'_dashboard_event_signature',None)==signature:return
        self._dashboard_event_signature=signature
        selected=tree.selection()
        tree.delete(*tree.get_children())
        for i,(symbol,status,reason,tag) in enumerate(records[:50]):
            tree.insert('','end',iid=str(i),values=(stamp,status,'MERCADO',symbol,reason[:250]),tags=(tag,))
        if selected and selected[0] in tree.get_children():tree.selection_set(selected[0])
        alerts=[]
        for sym,status,reason,tag in records:
            if tag!='normal':alerts.append(f'{sym}: {status} · {reason[:110]}')
        self.dashboard_alerts.configure(text='\n'.join(alerts[:3]) if alerts else
            'Sin bloqueos destacados. Las operaciones requieren confirmación real de MT5.')

    def build_pending(self,page):
        page.columnconfigure(0,weight=1);page.rowconfigure(1,weight=1)
        # Candidate list is read-only and represents broker confirmations
        # separately; selecting a row never submits an MT5 request.
        board,holder=neon_card(page,'IDEAS Y ÓRDENES PENDIENTES · ESTADO REAL',CYAN,padx=7,pady=5)
        board.grid(row=0,column=0,sticky='ew',pady=(2,4))
        self.pending_overview_summary=label(holder,'Esperando candidatos técnicos...',MUTED,9,anchor='w')
        self.pending_overview_summary.pack(fill='x',pady=(0,4))
        inside=tk.Frame(holder,bg=PANEL);inside.pack(fill='x')
        cols=('symbol','type','entry','sl','tp','quality','activation','state')
        self.pending_overview=ttk.Treeview(inside,columns=cols,show='headings',height=3,selectmode='browse')
        for key,heading,width in zip(cols,('SÍMBOLO','TIPO','ENTRADA','SL','TP','CALIDAD','ACTIVACIÓN','ESTADO'),
                                     (96,85,108,108,108,83,90,210)):
            self.pending_overview.heading(key,text=heading)
            self.pending_overview.column(key,width=width,minwidth=57,anchor='center',stretch=True)
        self.pending_overview.pack(side='left',fill='x',expand=True)
        scrolling=ttk.Scrollbar(inside,orient='vertical',command=self.pending_overview.yview)
        scrolling.pack(side='right',fill='y');self.pending_overview.configure(yscrollcommand=scrolling.set)
        self.pending_overview.bind('<<TreeviewSelect>>',self._show_pending_overview_detail)
        self.pending_overview_detail=label(holder,'Selecciona una tesis para ver sus niveles, restricciones y confirmación real.',
                                           MUTED,8,anchor='w',justify='left',wraplength=1250)
        self.pending_overview_detail.pack(fill='x',pady=(4,0))
        self._pending_overview_descriptions={}
        panes=self.layout.pane(page,'pending_symbols',tk.HORIZONTAL,(.5,));panes.grid(row=1,column=0,sticky='nsew',pady=(2,5))
        for symbol,on in self.cfg['symbols'].items():
            if not on:continue
            panel=SymbolPanel(panes,self,symbol);panes.add(panel,minsize=280,stretch='always');self.panels[symbol]=panel
        outer,controls=neon_card(page,'RIESGO CONJUNTO RESERVADO',AMBER,padx=12,pady=6);outer.grid(row=2,column=0,sticky='ew')
        risk_header=tk.Frame(controls,bg=PANEL);risk_header.pack(fill='x',pady=(0,5))
        self.pending_risk_help=label(risk_header,'Calculando presupuesto y reservas del libro MT5...',MUTED,8,wraplength=850,anchor='w',justify='left');self.pending_risk_help.pack(side='left',fill='x',expand=True)
        self.verify_all_pending_button=button(risk_header,'VERIFICAR PENDIENTES',self.open_verification,CYAN)
        self.verify_all_pending_button.configure(padx=8,pady=5);self.verify_all_pending_button.pack(side='right',padx=(8,0))
        actions=tk.Frame(controls,bg=PANEL);actions.pack(fill='x')
        button(actions,'COLOCAR PENDIENTES · BTC + ORO',lambda:self.request_map('ALL'),GREEN).pack(side='left',fill='x',expand=True,padx=(0,5))
        button(actions,'ABRIR RUNNERS CONFIRMADOS',lambda:self.request_runners('ALL'),CYAN).pack(side='left',fill='x',expand=True,padx=5)
        button(actions,'AJUSTAR RIESGO',self.set_trade_risk_cap,AMBER).pack(side='left',padx=(5,0))

    def _show_pending_overview_detail(self,event=None):
        tree=getattr(self,'pending_overview',None)
        if tree is None:return
        selected=tree.selection()
        if not selected:return
        detail=self._pending_overview_descriptions.get(selected[0],
            'Propuesta sin confirmación. Selecciona Verificar para comprobar sus niveles.')
        self.pending_overview_detail.configure(text=detail)

    def render_pending_overview(self,row):
        tree=getattr(self,'pending_overview',None)
        if tree is None:return
        from ui_updates import sync_table
        from pending_verification import identity
        records=[];details={};confirmed=0;sendable=0;proposed=0
        # A scenario-book flag is not evidence of an active broker order.
        # Reconcile with the current MT5 orders snapshot before labeling it.
        broker_orders={(str(o.get('ticket')),str(o.get('symbol'))):o
            for o in (row.get('orders') or []) if isinstance(o,dict) and o.get('ticket')}
        for symbol,info in (row.get('symbols') or {}).items():
            book=(info.get('scenario_book') or info.get('pending_book') or [])
            for i,p in enumerate(book[:24]):
                if not isinstance(p,dict):continue
                pid=identity({**p,'symbol':symbol})
                had_ticket=bool(p.get('confirmed') and p.get('ticket'))
                is_confirmed=had_ticket and (str(p['ticket']),str(symbol)) in broker_orders
                if is_confirmed:state='CONFIRMADA MT5 #'+str(p['ticket']);confirmed+=1
                elif had_ticket:state='RECONCILIAR CON MT5';proposed+=1
                elif p.get('sendable'):state='CANDIDATA VIABLE';sendable+=1
                else:state=str(p.get('scenario_state') or 'NO EJECUTABLE');proposed+=1
                category='BUY' if p.get('side')==1 else 'SELL'
                kind=str(p.get('kind') or 'LIMIT').upper()
                rid=symbol+':'+str(p.get('key') or p.get('ticket') or i)+':'+str(i)
                records.append((rid,(symbol,category+' '+kind,number(p.get('entry'),3),
                    number(p.get('sl'),3),number(p.get('tp'),3),
                    number(p.get('quality_score'),0),number(p.get('activation_score'),0),state),()))
                review=(row.get('pending_verifications') or {}).get(pid) or {}
                details[rid]=(symbol+' · '+category+' '+kind+' · '+state+' · '+
                    str(p.get('reason') or 'Motivo técnico no disponible.')[:220]+' · '+
                    'Comprobación: '+str(review.get('state') or p.get('block_reason') or 'pendiente')[:160]+
                    (' · MT5 #'+str(p['ticket']) if is_confirmed else ' · NO CONFIRMADA EN EL LIBRO ACTUAL DE MT5'))
        summary=f'{len(records)} IDEAS MOSTRADAS   ·   {confirmed} CONFIRMADAS EN MT5   ·   {sendable} CANDIDATAS VIABLES   ·   {proposed} EN ESPERA/RECONCILIACIÓN'
        self.pending_overview_summary.configure(text=summary)
        self._pending_overview_descriptions=details
        selection=tree.selection()
        sync_table(tree,records)
        if selection and selection[0] in details:
            try:tree.selection_set(selection[0]);self._show_pending_overview_detail()
            except tk.TclError:pass
        elif records:
            try:tree.selection_set(records[0][0]);self._show_pending_overview_detail()
            except tk.TclError:pass

    def build_account(self,page):
        columns=self.layout.pane(page,'account_columns',tk.HORIZONTAL,(.71,));columns.pack(fill='both',expand=True,pady=3)
        panes=self.layout.pane(columns,'account_book',tk.VERTICAL,(.57,));columns.add(panes,minsize=330,stretch='always')
        cols=('ticket','symbol','type','volume','entry','sl','tp','profit','owner')
        for attr,title in (('orders','PENDIENTES CONFIRMADAS EN MT5'),('positions','POSICIONES ACTIVADAS / ABIERTAS')):
            outer,box=neon_card(panes,title,CYAN);panes.add(outer,minsize=120,stretch='always')
            if attr=='orders':
                label(box,'Las manuales y de otros asesores se muestran con su autor.',MUTED,8,anchor='w').pack(fill='x',pady=(0,5))
            table=tk.Frame(box,bg=PANEL);table.pack(fill='both',expand=True)
            tree=ttk.Treeview(table,columns=cols,show='headings',height=3);setattr(self,attr,tree)
            for key,caption,width in zip(cols,('TICKET','SÍMBOLO','TIPO','LOTE','ENTRADA','SL','TP','P/L','AUTOR'),(95,105,95,55,100,100,100,75,110)):
                tree.heading(key,text=caption);tree.column(key,width=width,minwidth=45,anchor='center',stretch=True)
            scrollbar=ttk.Scrollbar(table,orient='horizontal',command=tree.xview);scrollbar.pack(side='bottom',fill='x');tree.configure(xscrollcommand=scrollbar.set)
            tree.pack(fill='both',expand=True)
            if attr=='orders':button(box,'RETIRAR PENDIENTE AKIRA SELECCIONADA',self.cancel_selected,AMBER).pack(fill='x',pady=(8,0))
        side=self.layout.pane(columns,'account_budget',tk.VERTICAL,(.56,));columns.add(side,minsize=210,stretch='always')
        outer,body=neon_card(side,'PRESUPUESTO Y LÍMITES',AMBER);side.add(outer,minsize=140,stretch='always')
        self.budget_value=label(body,'— USD',AMBER,22,True,anchor='w');self.budget_value.pack(fill='x',pady=(5,8))
        self.budget_bar=ttk.Progressbar(body,style='Cyber.Horizontal.TProgressbar');self.budget_bar.pack(fill='x',pady=(0,10))
        self.portfolio_help=label(body,'Esperando reservas MT5...',MUTED,9,wraplength=330,justify='left',anchor='w');self.portfolio_help.pack(fill='both',expand=True)
        button(body,'CONFIGURAR RIESGO MÁXIMO',self.set_trade_risk_cap,AMBER).pack(fill='x',pady=(12,0))
        outer,body=neon_card(side,'SEGURIDAD DE OPERACIONES',GREEN);side.add(outer,minsize=110,stretch='always')
        shell,body=scroll_frame(body,PANEL);shell.pack(fill='both',expand=True)
        self.account_safety=label(body,'Esperando confirmación del bróker.',MUTED,10,wraplength=330,anchor='nw',justify='left');self.account_safety.pack(fill='both',expand=True,pady=6)
        label(body,'Los cambios de órdenes se aplican únicamente a tickets propios de AKIRA.',MUTED,8,wraplength=320,anchor='w',justify='left').pack(fill='x')

    def set_trade_risk_cap(self):
        from cyber_ui import ask_text,confirm_dialog
        import math
        equity=float((self.view.get('account') or {}).get('equity') or 0)
        if equity<=0:
            self.show_message('Riesgo','Esperando el patrimonio confirmado desde MT5.',True);return
        current=min(float(self.cfg['risk']['max_trade_money']),equity*float(self.cfg['risk']['max_trade_pct'])/100)
        value=ask_text(self.root,'Riesgo real por operación',
            f'Patrimonio: ${equity:.2f}. Límite actual: ${current:.2f}. Máxima pérdida autorizada por operación en USD. El límite conjunto permanece independiente.',initial=str(round(current,2)),numeric=True)
        if value is None:return
        if not math.isfinite(value) or not .01<=value<=equity*.40:
            self.show_message('Riesgo no aplicado','Usa un importe finito entre $0.01 y el 40% del patrimonio.',True);return
        pct=value/equity*100
        if not confirm_dialog(self.root,'Confirmar riesgo',f'Una operación podría perder ${value:.2f} ({pct:.2f}% de la cuenta), y más con deslizamiento. El tope total no aumenta. ¿Aplicar estos límites a nuevas órdenes?'):return
        if pct>=10 and not confirm_dialog(self.root,'Riesgo elevado','Supera el 10% de tu patrimonio en una sola idea. Confirma este límite individual elevado.'):return
        updates={'risk.max_trade_money':value,'risk.max_trade_pct':min(40.0,pct+.01),'risk.min_lot_structural_override_enabled':False}
        for path,value in updates.items():
            if path not in self.setting_vars:
                self.setting_vars[path]=tk.BooleanVar(value=value) if isinstance(value,bool) else tk.StringVar(value=str(value))
                self.setting_types[path]='bool' if isinstance(value,bool) else 'float'
            else:self.setting_vars[path].set(value if isinstance(value,bool) else str(value))
        self.apply_settings_form()
    def build_analysis(self,page):
        row=tk.Frame(page,bg=BG);row.pack(side='bottom',fill='x',padx=12,pady=(0,4))
        button(row,'VER DETALLES DE VERIFICACIÓN',self.open_verification,CYAN).pack(side='left',padx=4)
        self.analysis_advanced_visible=tk.BooleanVar(value=False)
        button(row,'VER / OCULTAR DETALLE TÉCNICO',self.toggle_analysis_details,MUTED).pack(side='left')
        button(row,'ESTUDIO Y COMPARACIÓN',self.open_study,BLUE).pack(side='right')
        self.strategy_directory_button=button(row,'ESTRATEGIAS',self.open_strategy_directory,CYAN);self.strategy_directory_button.pack(side='right',padx=4)
        columns=self.layout.pane(page,'analysis_columns',tk.HORIZONTAL,(.57,));columns.pack(fill='both',expand=True,pady=5)
        self.analysis_split=self.layout.pane(columns,'analysis_sections',tk.VERTICAL,(.55,));columns.add(self.analysis_split,minsize=310,stretch='always')
        outer,body=neon_card(self.analysis_split,'LECTURA DEL MERCADO',CYAN);self.analysis_split.add(outer,minsize=130,stretch='always')
        self.analysis_summary=text_box(body,4);self.analysis_summary.pack(fill='both',expand=True)
        self.analysis_summary.configure(font=(FONT,10),spacing1=3,spacing3=5)
        for name,color in [('section',CYAN),('bull',GREEN),('bear',PINK),('closed',AMBER)]:self.analysis_summary.tag_configure(name,foreground=color,font=(FONT,11,'bold'))
        analysis_scroll=ttk.Scrollbar(self.analysis_summary,orient='vertical',command=self.analysis_summary.yview,style='Akira.Vertical.TScrollbar')
        analysis_scroll.pack(side='right',fill='y');self.analysis_summary.configure(yscrollcommand=analysis_scroll.set)
        self.analysis_advanced=self.layout.pane(self.analysis_split,'analysis_details',tk.VERTICAL,(.6,))
        cols=('symbol','tf','trend','rsi','atr','ema9','ema21','ema50','ema200','adx','macd','vwap','regime')
        self.frames=ttk.Treeview(self.analysis_advanced,columns=cols,show='headings',height=10)
        for key in cols:self.frames.heading(key,text=key.upper());self.frames.column(key,width=100,anchor='center')
        self.analysis_advanced.add(self.frames,minsize=60,stretch='always');self.audit=text_box(self.analysis_advanced,3);self.analysis_advanced.add(self.audit,minsize=50,stretch='always')
        side=self.layout.pane(columns,'analysis_context',tk.VERTICAL,(.61,));columns.add(side,minsize=250,stretch='always')
        outer,body=neon_card(side,'ESTADO Y ANTIGÜEDAD DE LOS DATOS',AMBER);side.add(outer,minsize=100,stretch='always')
        table=tk.Frame(body,bg=PANEL);table.pack(fill='both',expand=True)
        self.analysis_sources=ttk.Treeview(table,columns=('source','state','age','detail'),show='headings',height=5)
        for key,title,width in [('source','FUENTE',205),('state','ESTADO',120),('age','ANTIGÜEDAD',95),('detail','APORTE O MOTIVO',470)]:
            self.analysis_sources.heading(key,text=title);self.analysis_sources.column(key,width=width,minwidth=60,anchor='w')
        bar=ttk.Scrollbar(table,orient='vertical',command=self.analysis_sources.yview);bar.pack(side='right',fill='y');self.analysis_sources.configure(yscrollcommand=bar.set);self.analysis_sources.pack(fill='both',expand=True)
        self.analysis_sources.tag_configure('fresh',foreground=GREEN);self.analysis_sources.tag_configure('wait',foreground=AMBER)
        horizontal=ttk.Scrollbar(table,orient='horizontal',command=self.analysis_sources.xview);horizontal.pack(side='bottom',fill='x');self.analysis_sources.configure(xscrollcommand=horizontal.set)
        self.analysis_source_detail=label(page,'Selecciona una fuente para ver su aporte o motivo.',MUTED,9,anchor='w',justify='left',wraplength=850,height=2);self.analysis_source_detail.pack(before=columns,fill='x',padx=12,pady=3)
        self.analysis_sources.bind('<<TreeviewSelect>>',self.show_source_reason)
        label(body,'La lista muestra datos realmente recibidos. Las referencias no son precios de ejecución.',MUTED,8,wraplength=450,anchor='w',justify='left').pack(fill='x',pady=(8,0))
        outer,body=neon_card(side,'PROCESO DE DECISIÓN',CYAN);side.add(outer,minsize=95,stretch='always')
        shell,body=scroll_frame(body,PANEL);shell.pack(fill='both',expand=True)
        label(body,'1 · MERCADO   2 · ESTRUCTURA   3 · RIESGO',CYAN,8,True,anchor='w').pack(fill='x',pady=5)
        self.decision_summary=label(body,'Esperando lectura del motor.',MUTED,10,wraplength=440,anchor='nw',justify='left');self.decision_summary.pack(fill='both',expand=True,pady=8)
        button(body,'REVISAR MAPA',lambda:self.request_map('ALL'),GREEN).pack(fill='x')


    def toggle_analysis_details(self):
        if self.analysis_advanced_visible.get():
            self.analysis_split.forget(self.analysis_advanced);self.analysis_advanced_visible.set(False)
        else:
            self.analysis_split.add(self.analysis_advanced,minsize=100,stretch='always');self.analysis_advanced_visible.set(True)
            self.root.after_idle(lambda:self.layout.restore('analysis_sections'))

    def open_study(self):
        from quality_study import QualityStudy,quality_text as study_text
        win=tk.Toplevel(self.root);win.title('AKIRA · Resultados y comparación');win.configure(bg=PANEL);win.geometry('900x650');win.minsize(720,520)
        label(win,'RESULTADOS Y CAPTURAS REALES',CYAN,17,True).pack(pady=12)
        box=text_box(win,10);box.pack(fill='both',expand=True,padx=12,pady=8)
        scroll=ttk.Scrollbar(box,orient='vertical',command=box.yview,style='Akira.Vertical.TScrollbar');scroll.pack(side='right',fill='y');box.configure(yscrollcommand=scroll.set)
        study=QualityStudy(self.folder);view={**self.view,'quality_study':study.summary()}
        replace_text(box,study_text(view)+'\n\nCAPTURAS DISPONIBLES\n'+'\n'.join(r['id']+' · '+r['symbol']+' · '+str(r['at']) for r in study.cases()))
        bar=tk.Frame(win,bg=PANEL);bar.pack(fill='x',padx=12,pady=4)
        bar.columnconfigure(0,weight=1);bar.columnconfigure(1,weight=1)
        def template():
            path=filedialog.asksaveasfilename(parent=win,title='Plantilla de referencias reales',initialfile='Comparacion_AKIRA.csv',defaultextension='.csv',filetypes=[('CSV / Excel','*.csv')])
            if path:study.reference_template(path);messagebox.showinfo('AKIRA','Plantilla guardada. Completa los parámetros de la recomendación real y conserva el identificador de su captura.',parent=win)
        def import_reference():
            path=filedialog.askopenfilename(parent=win,title='Importar recomendaciones reales',filetypes=[('CSV / Excel','*.csv')])
            if not path:return
            try:
                result=study.import_references(path);replace_text(box,study_text({**self.view,'quality_study':study.summary()}));messagebox.showinfo('AKIRA',str(result['imported'])+' referencias importadas. '+result['detail'],parent=win)
            except Exception as exc:messagebox.showerror('Comparación',str(exc),parent=win)
        button(bar,'PLANTILLA PARA COMPARAR',template,BLUE).grid(row=0,column=0,sticky='ew',padx=(0,4),pady=3)
        button(bar,'IMPORTAR RECOMENDACIÓN REAL',import_reference,GREEN).grid(row=0,column=1,sticky='ew',padx=(4,0),pady=3)
        button(bar,'DESCARGAR INFORME',self.open_report_dialog,AMBER).grid(row=2,column=1,sticky='ew',padx=(4,0),pady=3)
        def evaluate():
            path=filedialog.askopenfilename(parent=win,title='Cotizaciones completas del mismo bróker: utc,symbol,bid,ask,source,roundtrip_cost_r',filetypes=[('Cotizaciones CSV','*.csv')])
            if not path:return
            evaluate_button.configure(state='disabled');replace_text(box,'Evaluando pares en segundo plano. El motor de órdenes continúa.')
            def work():
                try:study.evaluate_quotes(path);result={'text':study_text({**self.view,'quality_study':study.summary()})}
                except Exception as exc:result={'error':str(exc)}
                self.replies.put({'study_result':result,'study_window':win,'study_box':box,'study_button':evaluate_button})
            threading.Thread(target=work,daemon=True,name='AkiraPairedStudy').start()
        def evaluate_recorded():
            cost=simpledialog.askfloat('AKIRA · Costes del estudio','Coste adicional por operación, expresado en R (comisión y financiación).\nEl spread ya está incluido en bid/ask. Usa 0 solo si corresponde.\nLas observaciones son muestras cada 30 s; no todos los ticks.',parent=win,minvalue=0,initialvalue=0)
            if cost is None:return
            recorded_button.configure(state='disabled');replace_text(box,'Midiendo con las cotizaciones registradas por AKIRA. Las órdenes continúan; no se consulta MT5 para este trabajo.')
            def work():
                try:study.evaluate_recorded(cost);result={'text':study_text({**self.view,'quality_study':study.summary()})}
                except Exception as exc:result={'error':str(exc)}
                self.replies.put({'study_result':result,'study_window':win,'study_box':box,'study_button':recorded_button})
            threading.Thread(target=work,daemon=True,name='AkiraRecordedStudy').start()
        def save_pairs():
            path=filedialog.asksaveasfilename(parent=win,title='Descargar comparación',initialfile='Comparacion_AKIRA_resultados.csv',defaultextension='.csv',filetypes=[('CSV / Excel','*.csv')])
            if not path:return
            try:study.export_comparison(path);messagebox.showinfo('AKIRA','Comparación guardada en '+path,parent=win)
            except Exception as exc:messagebox.showerror('Comparación',str(exc),parent=win)
        recorded_button=button(bar,'MEDIR DATOS REGISTRADOS',evaluate_recorded,GREEN);recorded_button.grid(row=1,column=0,sticky='ew',padx=(0,4),pady=3)
        evaluate_button=button(bar,'IMPORTAR COTIZACIONES',evaluate,CYAN);evaluate_button.grid(row=1,column=1,sticky='ew',padx=(4,0),pady=3)
        button(bar,'DESCARGAR COMPARACIÓN',save_pairs,AMBER).grid(row=2,column=0,sticky='ew',padx=(0,4),pady=3)
        def evaluate_selectors():
            from cyber_ui import ask_text
            raw=ask_text(win,'Costes del estudio','Comisión y financiación adicionales en R. El spread ya está en bid/ask. Usa 0 solamente si corresponde a tu cuenta.',initial='0',numeric=True)
            if raw is None:return
            try:
                cost=float(raw)
                if not __import__('math').isfinite(cost) or cost<0:raise ValueError()
            except (TypeError,ValueError):self.show_message('Coste inválido','Indica un coste adicional finito mayor o igual que cero.',True);return
            selectors_button.configure(state='disabled');replace_text(box,'Comparando perfiles y aporte de filtros en segundo plano; el trading continúa.')
            def work():
                try:study.evaluate_selectors(cost);result={'text':study_text({**self.view,'quality_study':study.summary()})}
                except Exception as exc:result={'error':str(exc)}
                self.replies.put({'study_result':result,'study_window':win,'study_box':box,'study_button':selectors_button})
            threading.Thread(target=work,daemon=True,name='AkiraSelectorStudy').start()
        selectors_button=button(bar,'COMPARAR PERFILES Y FILTROS',evaluate_selectors,CYAN);selectors_button.grid(row=3,column=0,columnspan=2,sticky='ew',pady=3)
    def build_sources(self,page):
        # Vista humana: primero qué está haciendo Akira, luego las fuentes. Los
        # detalles técnicos siguen disponibles, pero no dominan la pantalla.
        toolbar=tk.Frame(page,bg=BG);toolbar.pack(fill='x',padx=12,pady=(10,4))
        self.source_refresh_state=label(toolbar,'LISTO',GREEN,10,True,anchor='w');self.source_refresh_state.pack(side='left',padx=(0,12))
        button(toolbar,'ACTUALIZAR AHORA',self.refresh,BLUE).pack(side='left')
        label(toolbar,'Akira actualiza automáticamente. Este botón solo fuerza una nueva ronda.',MUTED,9,anchor='w').pack(side='left',padx=12)

        row=tk.Frame(page,bg=BG);row.pack(side='bottom',fill='x',padx=12,pady=(2,4))
        self.sources_detail_visible=tk.BooleanVar(value=False)
        button(row,'VER / OCULTAR DETALLE TÉCNICO',self.toggle_source_details,MUTED).pack(side='left')
        self.source_query=tk.StringVar();tk.Entry(row,textvariable=self.source_query,bg=CARD,fg=TEXT,insertbackground=CYAN,font=(FONT,10)).pack(side='left',fill='x',expand=True,padx=8)
        button(row,'BUSCAR EN MEMORIA',self.search_memory,AMBER).pack(side='right')
        button(toolbar,'CONOCIMIENTO ACTUALIZADO',self.open_knowledge,CYAN).pack(side='right')
        self.source_split=self.layout.pane(page,'sources_sections',tk.HORIZONTAL,(.54,.8));self.source_split.pack(fill='both',expand=True,padx=12,pady=6)
        outer,main=neon_card(self.source_split,'FUENTES EN VIVO',CYAN);self.source_split.add(outer,minsize=290,stretch='always')
        shell,main=scroll_frame(main,PANEL);shell.pack(fill='both',expand=True)
        self.friendly_source_cards={}
        for key,title,desc in (
            ('mt5','Mercado / MT5','Precios, velas, spread y órdenes reales del bróker.'),
            ('web','Noticias y web','Noticias actuales y análisis públicos contrastados.'),
            ('venues','Mercados globales BTC','Binance, OKX, Coinbase, Bybit y Kraken; libros USD/USDT separados de MT5.'),
            ('macro','Dólar y tipos de interés','FRED: Tesoro nominal y real, dólar amplio. Datos diarios fechados, con retraso.'),
            ('global_news','Noticias globales','Fed, BLS, SEC, ECB, CFTC y CNBC; publicaciones fechadas y duplicados eliminados.'),
            ('youtube','YouTube','Análisis recientes; sirve como contexto, no como señal única.'),
            ('coinglass','CoinGlass / derivados','Open interest, funding, liquidaciones y contexto de derivados.'),
            ('investing','Calendario / macro','Eventos y noticias macro que pueden mover BTC u oro.'),
            ('local','AKIRA','Sintetiza toda la evidencia y revisa el mapa técnico.')):
            row=tk.Frame(main,bg=CARD,padx=10,pady=7);row.pack(fill='x',pady=3)
            dot=label(row,'●',MUTED,13,True);dot.pack(side='left',padx=(0,8))
            textcol=tk.Frame(row,bg=CARD);textcol.pack(side='left',fill='x',expand=True)
            label(textcol,title,TEXT,10,True,anchor='w').pack(fill='x')
            description=label(textcol,desc,MUTED,8,anchor='w',justify='left',wraplength=460);description.pack(fill='x')
            textcol.bind('<Configure>',lambda e,w=description:w.configure(wraplength=max(120,e.width-6)))
            state=label(row,'Esperando',MUTED,9,True,anchor='e');state.pack(side='right',padx=(8,0))
            self.friendly_source_cards[key]=(dot,state)

        outer,summary=neon_card(self.source_split,'QUÉ ESTÁ HACIENDO AKIRA',PINK);self.source_split.add(outer,minsize=260,stretch='always')
        self.sources_summary=text_box(summary,3);self.sources_summary.pack(fill='both',expand=True)
        replace_text(self.sources_summary,'Conectando con MT5 y preparando las fuentes externas. El asistente se comprueba por separado; su estado aparece en Chat · AKIRA.')
        # El detalle crudo queda aparte y conserva el scroll aunque las edades cambien.
        self.sources_detail=self.layout.pane(self.source_split,'sources_details',tk.VERTICAL,(.65,))
        self.sources=text_box(self.sources_detail,3);self.sources_detail.add(self.sources,minsize=40,stretch='always')
        self.memory_results=text_box(self.sources_detail,3);self.sources_detail.add(self.memory_results,minsize=40,stretch='always')

    def toggle_source_details(self):
        if self.sources_detail_visible.get():
            self.source_split.forget(self.sources_detail);self.sources_detail_visible.set(False)
        else:
            self.source_split.add(self.sources_detail,minsize=100,stretch='always');self.sources_detail_visible.set(True)
            self.root.after_idle(lambda:self.layout.restore('sources_sections'))
    def build_chat(self,page):
        split=self.layout.pane(page,'chat_columns',tk.HORIZONTAL,(.26,));split.pack(fill='both',expand=True,pady=4)
        shell,rail=scroll_frame(split,PANEL);split.add(shell,minsize=160,stretch='always')
        outer,chats=neon_card(rail,'CONVERSACIONES',CYAN,padx=10,pady=8);outer.pack(fill='x',pady=(0,8))
        button(chats,'+ NUEVO CHAT',self.new_chat,GREEN).pack(fill='x',pady=(0,7))
        self.chat_search=tk.StringVar();search=tk.Entry(chats,textvariable=self.chat_search,font=(FONT,9));search.pack(fill='x',ipady=7,pady=4)
        search.bind('<KeyRelease>',lambda e:self.refresh_chat_list())
        self.chat_list=tk.Listbox(chats,height=5,bg=PANEL,fg=TEXT,selectbackground='#14405b',selectforeground=CYAN,relief='flat',bd=0,highlightthickness=0,exportselection=False,font=(FONT,10))
        self.chat_list.pack(fill='x',pady=7);self.chat_list.bind('<<ListboxSelect>>',self.select_chat)
        self.chat_rows=[];self.refresh_chat_list()
        actions=tk.Frame(chats,bg=PANEL);actions.pack(fill='x')
        for i,(text,fn) in enumerate([('RENOMBRAR',self.rename_chat),('ELIMINAR',self.delete_chat),('LIMPIAR CHAT',self.clear_chat_visual),('MIS RECUERDOS',self.open_memories),('PAPELERA',self.open_chat_trash)]):
            actions.columnconfigure(i%2,weight=1);b=button(actions,text,fn,MUTED);b.configure(padx=6,pady=6,font=(FONT,8,'bold'));b.grid(row=i//2,column=i%2,sticky='ew',padx=2,pady=3)
        outer,akira=neon_card(rail,'AKIRA',PINK,padx=10,pady=8);outer.pack(fill='x')
        self.avatar(akira,190,100).pack(fill='x',pady=3)
        self.chat_model=label(akira,'AKIRA · preparando',AMBER,9,wraplength=260,justify='left',anchor='w');self.chat_model.pack(fill='x',pady=4)
        self.assistant_detail=label(akira,'Comprobando el asistente...',MUTED,8,wraplength=260,justify='left',anchor='w');self.assistant_detail.pack(fill='x',pady=4)
        self.assistant_repair_button=button(akira,'REPARAR ASISTENTE',self.prepare_local,AMBER);self.assistant_repair_button.pack(fill='x',pady=(2,6))
        self.assistant_reason_button=button(akira,'VER MOTIVO Y REGISTRO',self.open_assistant_diagnostics,MUTED);self.assistant_reason_button.pack(fill='x',pady=(0,6))
        label(akira,'Memoria · web · visión · archivos',MUTED,8,anchor='w').pack(fill='x',pady=(0,6))
        self.use_cloud=tk.BooleanVar(value=bool(self.cfg['assistant'].get('cloud',False)))
        tk.Checkbutton(akira,text='Permitir OpenAI opcional',variable=self.use_cloud,command=self.toggle_cloud,bg=PANEL,fg=TEXT,selectcolor=CARD,activebackground=PANEL,font=(FONT,9),bd=0,highlightthickness=0).pack(anchor='w',pady=3)
        self.cloud_status=label(akira,'OpenAI desactivado' if not self.use_cloud.get() else 'OpenAI · pendiente de comprobar',MUTED,8,wraplength=260,justify='left',anchor='w');self.cloud_status.pack(fill='x')
        button(akira,'CONFIGURAR OPENAI',self.configure_cloud,MUTED).pack(fill='x',pady=5)
        self.speak_answers=tk.BooleanVar(value=False)
        self.voice_button=button(akira,'INICIAR LLAMADA',self.start_voice,CYAN);


        pane=tk.Frame(split,bg=BG);split.add(pane,minsize=340,stretch='always')
        pane.columnconfigure(0,weight=1);pane.rowconfigure(2,weight=1)
        # Barra de pensamiento tipo asistente: no inunda el chat con cada evento.
        status=tk.Frame(pane,bg=PANEL,padx=10,pady=6);status.grid(row=0,column=0,sticky='ew',pady=(0,4))
        self.chat_spinner=label(status,'○ ○ ○',CYAN,12,True);self.chat_spinner.pack(side='left')
        self.chat_status=label(status,'Listo',TEXT,10,True,anchor='w');self.chat_status.pack(side='left',padx=10,fill='x',expand=True)
        self.chat_elapsed=label(status,'',MUTED,9,anchor='e');self.chat_elapsed.pack(side='right',padx=8)
        self.stop_thinking_btn=button(status,'DETENER',self.stop_thinking,RED);self.stop_thinking_btn.pack(side='right');self.stop_thinking_btn.configure(state='disabled')
        self.chat_repair_button=button(status,'REPARAR ASISTENTE',self.prepare_local,AMBER);self.chat_repair_button.pack(side='right',padx=4)
        self.chat_source_strip=tk.Frame(pane,bg=BG);self.chat_source_strip.grid(row=1,column=0,sticky='ew',pady=(0,4))

        history=tk.Frame(pane,bg=CARD);history.grid(row=2,column=0,sticky='nsew',pady=(0,6))
        history.rowconfigure(0,weight=1);history.columnconfigure(0,weight=1)
        self.chat=text_box(history,4);self.chat.configure(font=(FONT,11),spacing1=2,spacing3=6);self.chat.grid(row=0,column=0,sticky='nsew')
        scrollbar=ttk.Scrollbar(history,orient='vertical',command=self.chat.yview);scrollbar.grid(row=0,column=1,sticky='ns');self.chat.configure(yscrollcommand=scrollbar.set)
        self.chat.tag_configure('user',foreground='#9bf4ff',lmargin1=54,lmargin2=54,rmargin=22,spacing1=3,spacing3=5);self.chat.tag_configure('assistant',foreground=TEXT,lmargin1=14,lmargin2=14,rmargin=34,spacing1=3,spacing3=5);self.chat.tag_configure('system',foreground=AMBER);self.chat.tag_configure('chat_author',foreground=CYAN,font=(FONT,9,'bold'));self.chat.tag_configure('chat_user_author',foreground=GREEN,font=(FONT,9,'bold'))
        for turn in self.assistant.history:self.append_chat('TÚ' if turn['role']=='user' else 'AKIRA',turn.get('text',''))
        self.chat_welcome=tk.Frame(history,bg=PANEL,padx=12,pady=12)
        self.chat_welcome_glyph=label(self.chat_welcome,'◇',CYAN,38);self.chat_welcome_glyph.pack(pady=(0,12))
        self.chat_welcome_title=label(self.chat_welcome,'¿Qué necesitas?',TEXT,19,True,wraplength=320);self.chat_welcome_title.pack()
        self.chat_welcome_help=label(self.chat_welcome,'Conversa, investiga o revisa tu mapa de órdenes.',MUTED,9,wraplength=300,justify='center');self.chat_welcome_help.pack(pady=10)
        self.chat_welcome_action=button(self.chat_welcome,'REVISAR BTC Y ORO',lambda:self.chat_suggestion('Revisa el mapa de BTC y oro'),CYAN);self.chat_welcome_action.pack(pady=5)
        if not self.assistant.history:self.chat_welcome.place(relx=.5,rely=.48,anchor='center',width=350)
        history.bind('<Configure>',self._fit_chat_welcome,add='+')
        self.chat_composer=tk.Frame(pane,bg=PANEL,padx=8,pady=6);self.chat_composer.grid(row=3,column=0,sticky='ew')
        self.chat_composer.columnconfigure(0,weight=1)
        label(self.chat_composer,'ESCRIBE A AKIRA · Enter para enviar · Ctrl+L abre el chat',MUTED,9,anchor='w').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,4))
        self.chat_input=tk.StringVar();self.chat_entry=tk.Entry(self.chat_composer,textvariable=self.chat_input,bg=CARD,fg=TEXT,insertbackground=CYAN,font=(FONT,12),relief='flat')
        self.chat_entry.grid(row=1,column=0,sticky='ew',ipady=8);self.chat_entry.bind('<Return>',lambda e:self.ask())
        if hasattr(self.chat_input,'trace_add'):self.chat_input.trace_add('write',lambda *_:self.avatar_typing())
        self.call_icon=button(self.chat_composer,'☎',self.start_voice,CYAN);self.call_icon.configure(padx=10,pady=6);self.call_icon.grid(row=1,column=2,sticky='ns',padx=(6,0))
        self.chat_send_button=button(self.chat_composer,'ENVIAR',self.ask,CYAN);self.chat_send_button.grid(row=1,column=1,sticky='ns',padx=(8,0))
        pane.bind('<Configure>',lambda e:self.chat_status.configure(wraplength=max(150,e.width-220)))

    def _fit_chat_welcome(self,event):
        if self.chat_welcome.winfo_manager()!='place':return
        width=max(180,min(400,event.width-24));self.chat_welcome.place_configure(width=width)
        self.chat_welcome_title.configure(wraplength=max(140,width-28),font=(FONT,16 if event.height<260 else 19,'bold'))
        self.chat_welcome_help.configure(wraplength=max(140,width-28))
        if event.height<260:self.chat_welcome_glyph.pack_forget()
        elif not self.chat_welcome_glyph.winfo_manager():self.chat_welcome_glyph.pack(before=self.chat_welcome_title,pady=(0,12))
        if event.height<180:self.chat_welcome_help.pack_forget()
        elif not self.chat_welcome_help.winfo_manager():self.chat_welcome_help.pack(before=self.chat_welcome_action,pady=10)

    def chat_suggestion(self,text):
        self.chat_input.set(text);self.chat_entry.focus_set()

    def open_chat(self,event=None):
        self.navigate(5)
        return 'break' if event is not None else None

    def stop_thinking(self):
        if not self.chat_busy:return
        self.assistant.cancel_current_reply();self.chat_stage='DETENIENDO';self.chat_stage_detail='Cerrando ahora la conexión con el modelo...'
        self.chat_status.configure(text='Interrumpiendo respuesta...',fg=AMBER);self.stop_thinking_btn.configure(state='disabled')

    def avatar_typing(self):
        if not self.chat_input.get().strip() or self.chat_busy or not self.avatars:return
        self.avatars[0].director.publish('listening','Escribiendo al chat')
        self._avatar_reaction_until=time.monotonic()+1.5
        old=getattr(self,'_typing_avatar_job',None)
        if old is not None:
            try:self.root.after_cancel(old)
            except tk.TclError:pass
        def done():
            self._typing_avatar_job=None
            if not self.chat_busy:self.reset_avatar()
        self._typing_avatar_job=self.root.after(1600,done)

    def _render_chat_progress(self):
        if not hasattr(self,'chat_status'):return
        if self.avatars:self.avatars[0].director.busy(self.chat_busy)
        if self.chat_busy:
            elapsed=max(0.0,time.monotonic()-self.chat_started);self.chat_elapsed.configure(text=f'{elapsed:.0f} s')
            glyphs=('● ○ ○','○ ● ○','○ ○ ●','○ ● ○');self._chat_anim_phase=(self._chat_anim_phase+1)%len(glyphs);self.chat_spinner.configure(text=glyphs[self._chat_anim_phase],fg=CYAN)
            detail=(' · '+self.chat_stage_detail) if self.chat_stage_detail else ''
            self.chat_status.configure(text=self.chat_stage+detail,fg=TEXT)
        else:
            local=getattr(self,'_assistant_display_status',{})
            failed=local.get('phase') in ('FAILED','STALLED')
            text=public_status(local.get('error') or local.get('detail') or 'Reparación pendiente')[:65] if failed else 'Listo'
            self.chat_spinner.configure(text='●',fg=RED if failed else GREEN);self.chat_elapsed.configure(text='')
            self.chat_status.configure(text=text,fg=RED if failed else GREEN,wraplength=230 if failed else 0)
        try:
            children=self.chat_source_strip.winfo_children()
        except Exception:
            children=[]
        for w in children:
            try:w.destroy()
            except Exception:pass
        if hasattr(self.chat_source_strip,'winfo_children'):
            for name in self.chat_source_names[-6:]:
                try:
                    pill=tk.Label(self.chat_source_strip,text='● '+name,bg=CARD,fg=CYAN,font=(FONT,8,'bold'),padx=8,pady=3);pill.pack(side='left',padx=(0,5))
                except Exception:break
    def clear_chat_visual(self):
        if self.chat_busy:
            self.desktop_toast('Chat ocupado','Detén la respuesta antes de limpiar este chat.');return
        self.assistant.clear_chat()
        self.chat.configure(state='normal');self.chat.delete('1.0','end');self.chat.configure(state='disabled')
        self.append_chat('AKIRA','Chat limpio y contexto temporal liberado. Tus recuerdos guardados y fuentes permanecen disponibles.')

    def refresh_chat_list(self):
        self.chat_rows=self.assistant.chats.list(self.chat_search.get())
        self.chat_list.delete(0,'end')
        for i,row in enumerate(self.chat_rows):
            self.chat_list.insert('end',row['title'])
            if row['id']==self.assistant.chats.active:self.chat_list.selection_set(i)

    def reload_chat(self):
        self.chat.configure(state='normal');self.chat.delete('1.0','end');self.chat.configure(state='disabled')
        for row in self.assistant.history:self.append_chat('TÚ' if row['role']=='user' else 'AKIRA',row['text'])
        self.refresh_chat_list()
        if not self.assistant.history:self.chat_welcome.place(relx=.5,rely=.48,anchor='center',width=350)
        history.bind('<Configure>',self._fit_chat_welcome,add='+')

    def select_chat(self,event=None):
        selected=self.chat_list.curselection()
        if not selected:return
        cid=self.chat_rows[int(selected[0])]['id']
        if cid==self.assistant.chats.active:return
        if self.chat_busy or getattr(self,'voice_call_active',False):
            self.desktop_toast('Conversación activa','Detén la respuesta o finaliza la llamada antes de cambiar de chat.');return
        self.assistant.switch_chat(cid);self.reload_chat()

    def new_chat(self):
        if self.chat_busy or getattr(self,'voice_call_active',False):return
        self.assistant.switch_chat(new=True);self.reload_chat();self.chat_entry.focus_set()

    def rename_chat(self):
        from tkinter import simpledialog
        name=ask_text(self.root,'Renombrar chat','Nombre del tema:')
        if name:self.assistant.chats.rename(self.assistant.chats.active,name);self.refresh_chat_list()

    def delete_chat(self):
        if self.chat_busy or getattr(self,'voice_call_active',False):return
        if not messagebox.askyesno('Eliminar chat','¿Eliminar este chat y su contexto temporal? Los recuerdos que guardaste por separado permanecen.',parent=self.root):return
        self.assistant.chats.delete(self.assistant.chats.active);self.assistant.switch_chat(self.assistant.chats.active);self.reload_chat()

    def open_memories(self):
        win=tk.Toplevel(self.root);win.title('AKIRA · Recuerdos');win.configure(bg=PANEL);win.geometry('650x450')
        label(win,'RECUERDOS GUARDADOS',CYAN,16,True).pack(pady=10)
        box=tk.Listbox(win,bg=CARD,fg=TEXT,selectbackground=LINE,exportselection=False,font=(FONT,11));box.pack(fill='both',expand=True,padx=12,pady=8)
        rows=[]
        def refresh():
            rows[:]=self.assistant.chats.memories();box.delete(0,'end')
            for row in rows:box.insert('end',row['body'])
        text=tk.StringVar();entry=tk.Entry(win,textvariable=text,bg=CARD,fg=TEXT,insertbackground=CYAN);entry.pack(fill='x',padx=12,pady=6)
        bar=tk.Frame(win,bg=PANEL);bar.pack(fill='x',padx=12,pady=10)
        def save():
            if text.get().strip():self.assistant.chats.remember(text.get());text.set('');refresh()
        def forget():
            selection=box.curselection()
            if selection:self.assistant.chats.forget(rows[int(selection[0])]['id']);refresh()
        button(bar,'GUARDAR RECUERDO',save,GREEN).pack(side='left');button(bar,'OLVIDAR SELECCIONADO',forget,RED).pack(side='right');refresh()

    def toggle_cloud(self):
        from cloud_status import verify_cloud
        enabled=bool(self.use_cloud.get());cfg=copy.deepcopy(self.cfg);cfg['assistant']['cloud']=enabled
        try:
            saved=save_config(cfg,self.folder/'akira_config.json');self.cfg.update(saved)
        except Exception as exc:
            self.use_cloud.set(not enabled);self.cloud_status.configure(text='No se guardó el cambio: '+str(exc),fg=RED);return
        self.cloud_status.configure(text='Comprobando conexión...' if enabled else 'OpenAI desactivado. AKIRA continúa sin este servicio.',fg=AMBER if enabled else MUTED)
        if enabled:
            self.check_cloud()

    def check_cloud(self):
        if not self.use_cloud.get():return
        from cloud_status import verify_cloud
        self.cloud_status.configure(text='Comprobando permiso y conexión de OpenAI...',fg=AMBER)
        def work():self.replies.put({'cloud_check':verify_cloud(),'cloud_enabled':True})
        threading.Thread(target=work,name='AkiraCloudCheck',daemon=True).start()

    def configure_cloud(self):
        self.open_cloud_settings()

    def open_library(self):
        self.open_knowledge()

    def build_settings(self,page):
        label(page,'Ajusta tus preferencias y pulsa GUARDAR para aplicarlas en vivo.',MUTED,10,anchor='w').pack(fill='x',padx=12,pady=(8,6))
        self.setting_vars={};self.setting_types={};self.settings_cards={}
        self.settings_titles=[];self.settings_pages=[]
        button(page,'GUARDAR AJUSTES',self.save_settings,GREEN).pack(side='bottom',anchor='e',padx=20,pady=(4,14))
        book=ttk.Notebook(page,style='Cyber.TNotebook');self.settings_notebook=book;book.pack(fill='both',expand=True,padx=12,pady=6)
        def tab(title):
            shell,frame=scroll_frame(book,BG);book.add(shell,text=title)
            self.settings_titles.append(title);self.settings_pages.append(shell)
            if title=='INTERFAZ':self.settings_interface_tab=shell
            if title=='FUENTES':self.settings_sources_tab=shell
            if title=='RENDIMIENTO':self.settings_resources_tab=shell
            if title=='MANTENIMIENTO':self.settings_maintenance_tab=shell
            self.settings_cards[frame]=[]
            def arrange(event,parent=frame,section=title):
                density=max(1,float(self.root.tk.call('tk','scaling'))/1.333)
                columns=2 if section!='INTERFAZ' and event.width>=1180*density else 1
                if getattr(parent,'_settings_columns',None)==columns:return
                parent._settings_columns=columns
                parent.columnconfigure(0,weight=1);parent.columnconfigure(1,weight=1 if columns==2 else 0,minsize=0)
                for i,card in enumerate(self.settings_cards[parent]):card.grid(row=i//columns,column=i%columns,sticky='nsew',padx=6,pady=6)
            shell._scroll_canvas.bind('<Configure>',arrange,add='+');return frame
        def card(parent,title,accent=CYAN):
            o,i=neon_card(parent,title,accent);idx=len(self.settings_cards[parent]);self.settings_cards[parent].append(o);parent.columnconfigure(0,weight=1);o.grid(row=idx,column=0,sticky='nsew',padx=6,pady=6);return i
        def field(parent,path,title,kind='float',hint=''):
            row=tk.Frame(parent,bg=PANEL);row.pack(fill='x',pady=5)
            left=tk.Frame(row,bg=PANEL);left.pack(side='left',fill='x',expand=True)
            caption=label(left,title,TEXT,10,True,anchor='w',justify='left',wraplength=600);caption.pack(fill='x')
            left.bind('<Configure>',lambda e,w=caption:w.configure(wraplength=max(150,e.width-4)))
            if hint:label(left,hint,MUTED,8,anchor='w',wraplength=620,justify='left').pack(fill='x')
            var=tk.StringVar(value=str(path_get(self.cfg,path,'')));self.setting_vars[path]=var;self.setting_types[path]=kind
            ent=tk.Entry(row,textvariable=var,bg=CARD,fg=TEXT,insertbackground=CYAN,relief='flat',font=(FONT,10),width=16,justify='center');ent.pack(side='right',ipady=6,padx=(10,0));__import__('cyber_ui').attach_tooltip(ent,hint or title)
        def check(parent,path,title,hint=''):
            row=tk.Frame(parent,bg=PANEL);row.pack(fill='x',pady=5)
            var=tk.BooleanVar(value=bool(path_get(self.cfg,path,False)));self.setting_vars[path]=var;self.setting_types[path]='bool'
            toggle(row,var,title,hint)
        # Pendientes
        t=tab('OPERACIÓN')
        c=card(t,'MODO AUTOMÁTICO',GREEN)
        label(c,'Solo análisis prepara candidatas sin enviar órdenes. Operativa automática permite enviarlas tras las comprobaciones de MT5 y riesgo.',MUTED,9,wraplength=620,justify='left',anchor='w').pack(fill='x',pady=6)
        mode_var=tk.StringVar(value='Operativa automática' if self.cfg['mode']=='trade' else 'Solo análisis')
        self.setting_vars['mode']=mode_var;self.setting_types['mode']='str'
        ttk.Combobox(c,textvariable=mode_var,values=('Solo análisis','Operativa automática'),state='readonly',style='Akira.TCombobox').pack(fill='x',pady=6)
        check(c,'execution.pending_only','Entradas únicamente mediante pendientes','Marcado: gestiona las posiciones activadas como runners. Desmarcado: también permite runners directos a mercado con confirmación M15/M5 y H1. Se conservan los límites de riesgo y las comprobaciones del broker.')
        check(c,'execution.always_keep_pending_map','Mantener siempre el mejor mapa pendiente disponible','Genera parámetros técnicos inmediatos y luego los mejora con H4/D1, fuentes e IA; riesgo y broker siguen mandando.')
        check(c,'execution.allow_m15_m30_pending_origin','Permitir pendientes rápidas desde estructura M15/M30','H1/H4 siguen teniendo prioridad. Las zonas M5 observadas solo compiten con confirmación M15/H1 y sus propios filtros.')
        check(c,'pending.preserve_opposite_map','Permitir BUY y SELL simultáneos cuando ambas tesis sean válidas')
        check(c,'strategy.pending_dynamic_structural_fallback','Usar EMA/Fibonacci H1/H4 como respaldo estructural','Solo como respaldo; siguen pasando SL, R:R, riesgo, MTF y Gateway.')
        check(c,'execution.pending_budget_fit_entry','Buscar un fill LIMIT más profundo si 0.01 no cabe','Conserva el SL estructural; no lo acerca para forzar presupuesto.')
        c=card(t,'CONTROL DE VIGENCIA',CYAN)
        field(c,'pending.orphan_cancel_seconds','Retirar si la tesis desaparece durante (segundos)','float','Akira cancela una pendiente propia si deja de existir en el mapa por este tiempo.')
        field(c,'pending.replace_confirm_seconds','Confirmar mejora durante (segundos)','float')
        field(c,'pending.sticky_min_seconds','Tiempo mínimo antes de modificar una orden (segundos)','float')
        # Riesgo
        t=tab('RIESGO')
        c=card(t,'LÍMITES REALES',AMBER)
        field(c,'risk.max_trade_money','Máximo USD por operación','float','El Gateway nunca debe superar este límite.')
        field(c,'risk.max_trade_pct','Máximo % del patrimonio por operación','float')
        field(c,'risk.daily_loss_money','Máxima pérdida neta diaria USD (0 = desactivado)','float','Bloquea entradas nuevas al alcanzar la pérdida realizada de operaciones del día UTC. Conserva gestión y protecciones.')
        field(c,'risk.daily_loss_pct','Máxima pérdida neta diaria % (0 = desactivado)','float','Se aplica el menor de los límites diarios activos, usando el patrimonio MT5 actual. Requiere historial vigente.')
        field(c,'risk.portfolio_capital_pct','Máximo % de capital reservado por todas las pendientes','float')
        field(c,'risk.portfolio_money_cap','Tope conjunto absoluto de riesgo (USD; 0 = sin tope en USD)','float',
              'Es independiente del máximo por operación. Si está por debajo del riesgo individual, ninguna pendiente podrá entrar.')
        field(c,'risk.minimum_margin_level_pct','Margen mínimo requerido (%)','float')
        check(c,'sizing.enabled','Ajustar lote al SL y al presupuesto real','Calcula volumen con order_calc_profit, SL estructural, límite de riesgo y margen MT5.')
        check(c,'sizing.scale_pending','Escalar lotaje de pendientes de calidad según capital','Solo aumenta cuando la señal supera los umbrales configurados y el riesgo monetario, margen y lote del bróker lo permiten. No fuerza entradas con $10.')
        field(c,'sizing.boost_score','Puntuación mínima para escalar lote','float')
        field(c,'sizing.boost_quality','Calidad mínima para escalar lote','float')
        field(c,'sizing.risk_utilization','Fracción máxima del presupuesto utilizable (0–1)','float','Ejemplo: 0.75 reserva al menos 25% del cap por operación al dimensionar una señal escalable.')
        field(c,'lot','Lote base','float')
        field(c,'sizing.max_lot','Máximo lote permitido','float')
        check(c,'management.pending_fills_as_runners','Gestionar las pendientes activadas como runners','Protección por pivotes M15 confirmados; no abre entradas directas a mercado.')
        field(c,'management.breakeven_at_r','Iniciar protección desde R','float')
        field(c,'management.trail_atr','Margen de protección ATR','float')
        field(c,'management.minimum_hold_seconds','Espera mínima de gestión (s)','float')
        check(c,'management.extend_targets','Extender TP hacia el siguiente objetivo observado','Solo con continuación M15/H1, ADX y avance suficiente. Conserva el SL y respeta MT5; apagado por defecto.')
        field(c,'management.extension_min_r','Avance mínimo para estudiar extensión (R)','float')
        c=card(t,'COBERTURA CON LOTE MÍNIMO · OPCIONAL',RED)
        check(c,'risk.min_lot_structural_override_enabled','Permitir que una estructura válida use más del cap normal si 0.01 no cabe','APAGADO por defecto. Si lo activas, 0.01 puede usar hasta el % y cap USD que definas cuando una estructura real no cabe. Puede implicar riesgo alto; Akira nunca lo activa sola.')
        field(c,'risk.min_lot_structural_override_max_pct','Máximo % por operación con override','float')
        field(c,'risk.min_lot_structural_override_money_cap','Cap USD absoluto del override','float')
        self.risk_override_help=label(c,'',MUTED,8,anchor='w',wraplength=760,justify='left');self.risk_override_help.pack(fill='x',pady=(6,0))
        # Calidad
        t=tab('ESTRATEGIAS')
        for sym in ('BTCUSDm','XAUUSDm'):
            if sym not in self.cfg.get('symbol_profiles',{}):continue
            c=card(t,sym,PINK if sym.startswith('XAU') else BLUE)
            field(c,f'symbol_profiles.{sym}.pending_structural_quality_min','Calidad mínima estricta A/A+','float')
            field(c,f'symbol_profiles.{sym}.pending_structural_activation_min','Activación mínima estricta','float')
            field(c,f'symbol_profiles.{sym}.pending_fallback_structural_quality','Calidad mínima del mejor respaldo','float','Solo se usa si el mapa estricto deja un lado vacío.')
            field(c,f'symbol_profiles.{sym}.pending_fallback_structural_activation','Activación mínima del respaldo','float')
        c=card(t,'ESTABILIDAD DE ÓRDENES · ANTI BUCLE',CYAN)
        check(c,'pending.auto_replace_valid_pending','Permitir reemplazo automático de una pendiente aún válida',
              'DESACTIVADO por defecto. Solo con evidencia nueva, edad >= 15 min y diferencia de calidad significativa. Evita crear/cancelar la misma tesis cada segundo.')
        label(c,'Si una pendiente válida no mejora materialmente, Akira la mantiene. Las invalidaciones reales por precio/vela siguen protegidas por el motor y MT5.',
              MUTED,9,anchor='w',justify='left',wraplength=650).pack(fill='x',pady=(4,8))
        # IA/Fuentes
        t=tab('FUENTES')
        self.settings_sources_body=t
        self.build_source_access(t,card)
        t=tab('ASISTENTE')
        c=card(t,'CONOCIMIENTO ACTUALIZADO',CYAN)
        check(c,'knowledge.enabled','Mantener fuentes de conocimiento actualizadas')
        mode_row=tk.Frame(c,bg=PANEL);mode_row.pack(fill='x',pady=8);label(mode_row,'Actualización del conocimiento',TEXT,10,True).pack(side='left');mode=tk.StringVar(value='Automática' if self.cfg['knowledge']['mode']=='automatic' else 'Bajo solicitud');self.setting_vars['knowledge.mode']=mode;self.setting_types['knowledge.mode']='str';ttk.Combobox(mode_row,textvariable=mode,values=('Automática','Bajo solicitud'),state='readonly',style='Akira.TCombobox',width=18).pack(side='right')
        field(c,'knowledge.interval_hours','Actualizar cada (horas)','float')
        check(c,'knowledge.automatic_cache','Limpiar automáticamente las consultas obsoletas')
        field(c,'knowledge.cache_days','Conservar consultas temporales (días)','float')
        button(c,'VER ESTADO DEL CONOCIMIENTO',self.open_knowledge,CYAN).pack(fill='x',pady=5)
        button(c,'CONFIGURAR OPENAI',self.configure_cloud,BLUE).pack(fill='x',pady=5)
        c=card(t,'INVESTIGACIÓN AUTOMÁTICA',BLUE)
        field(c,'assistant.local_endpoint','Motor local (URL de Ollama o llama.cpp)','str',
              'Ollama: http://127.0.0.1:11434/api/chat · llama.cpp: http://127.0.0.1:8080/v1/chat/completions. Solo localhost; llama.cpp necesita su binario y modelo GGUF.')
        check(c,'assistant.local_runtime_enabled','Usar la IA incluida bajo demanda',
              'El instalador completo incluye motor y modelo. Las rutas vacías o antiguas se recuperan desde la instalación. Akira cierra solo su propio proceso.')
        field(c,'assistant.local_runtime_exe','Ruta de llama-server.exe (local)','str')
        field(c,'assistant.local_runtime_model','Ruta del modelo GGUF (local)','str')
        field(c,'assistant.local_runtime_idle_seconds','Liberar IA de memoria tras (s)','int')
        check(c,'assistant.auto_install_local_ai','Permitir instalar/reparar Ollama (opcional)',
              'Desactivado por defecto en nuevas instalaciones. No instala una IA integrada diferente.')
        check(c,'assistant.auto_research','Investigar la web automáticamente antes de responder hechos/análisis')
        check(c,'assistant.auto_youtube_research','Buscar YouTube automáticamente en trading y consultas de vídeos')
        check(c,'research.youtube','YouTube para contexto de trading')
        check(c,'research.coinglass','CoinGlass / derivados')
        check(c,'research.investing','Investing / noticias')
        check(c,'research.technical_search','Búsqueda técnica pública por símbolo')
        check(c,'research.local_model','Síntesis de AKIRA')
        check(c,'research.local_ai_double_check','Doble revisión local del análisis profundo','Analista + verificador fuera del hot-loop; puede tardar hasta ~1–2 minutos según tu PC.')
        check(c,'assistant.show_research_trace','Mostrar en el chat dónde está buscando Akira')
        check(c,'assistant.cross_chat_memory','Usar contexto relevante de otros chats','Consulta una parte acotada de otros temas; puedes desactivarlo. Los recuerdos guardados se administran aparte.')
        field(c,'research.local_ai_summary_seconds','Repetir síntesis profunda cada (segundos)','float','El mapa técnico no espera este ciclo; cuando termina, puede mejorar/reemplazar pendientes.')
        label(c,'AKIRA selecciona automáticamente la capacidad disponible.',MUTED,9,anchor='w').pack(fill='x',pady=8)
        # Interfaz
        t=tab('RENDIMIENTO')
        c=card(t,'OPTIMIZADOR DE RECURSOS',CYAN)
        button(c,'MOSTRAR / OCULTAR LIMITADOR DE RECURSOS  ◈',self.open_resource_panel,CYAN).pack(fill='x',pady=(0,8))
        self._resource_host=tk.Frame(c,bg=PANEL);self._resource_host.pack(fill='x',pady=(0,4))
        label(c,'Reduce redibujados, animaciones y actividad de interfaz, sin detener el motor MT5.',MUTED,9,
              anchor='w',justify='left',wraplength=620).pack(fill='x',pady=(2,10))
        profile=tk.StringVar(value=self.cfg['desktop'].get('performance_profile','Equilibrado'))
        self.setting_vars['desktop.performance_profile']=profile
        self.setting_types['desktop.performance_profile']='str'
        ttk.Combobox(c,textvariable=profile,values=tuple(PROFILES),state='readonly',
                     style='Akira.TCombobox',width=26).pack(fill='x',pady=6)
        from resource_optimizer import profile_budget
        profile_values=label(c,'',CYAN,9,anchor='w',wraplength=620,justify='left')
        profile_values.pack(fill='x',pady=5)
        def show_profile_values(*_):
            b=profile_budget(profile.get())
            profile_values.configure(text=(f"{profile.get()} · presupuesto IA {b['memory_budget_mb']} MB (orientativo) "
                f"· contexto {b['model_context_tokens']} tokens · descarga IA tras {b['model_keep_alive_seconds']} s "
                f"· GPU {'permitida' if b['model_use_gpu'] else 'desactivada para IA'}"))
        if hasattr(profile,'trace_add'):profile.trace_add('write',show_profile_values)
        show_profile_values()
        label(c,'GPU y consumo de energía también dependen del sistema gráfico, el modelo de IA y otros procesos. '
              'Este ajuste no promete limitar el consumo total de la GPU.',MUTED,8,anchor='w',
              wraplength=600,justify='left').pack(fill='x',pady=6)
        t=tab('INTERFAZ')
        c=card(t,'VENTANA',PINK)
        field(c,'desktop.width','Ancho','int');field(c,'desktop.height','Alto','int')
        button(c,'BORRAR CACHÉ',self.open_cache_cleaner,CYAN).pack(fill='x',pady=8)
        button(c,'DESCARGAS E INFORMES',lambda:self.open_folder('exports'),MUTED).pack(fill='x',pady=5)
        button(c,'RESTABLECER PREFERENCIAS',self.restore_preferences,MUTED).pack(fill='x',pady=5)
        c=card(t,'NOTIFICACIONES',AMBER)
        check(c,'desktop.notifications','Activar notificaciones de escritorio')
        check(c,'desktop.notification_sound','Sonido de notificaciones')
        check(c,'desktop.notification_popup','Mostrar notificaciones en pantalla')
        check(c,'desktop.notify_deep_analysis','Avisar cuando termina una revisión profunda de mercado')
        check(c,'desktop.notify_pending_change','Avisar cuando Akira coloca, modifica o retira pendientes')
        field(c,'desktop.toast_seconds','Duración de la notificación (segundos)','float')
        label(c,'Las notificaciones no cambian órdenes; solo muestran el resultado del análisis/control.',MUTED,9,anchor='w').pack(fill='x',pady=6)
        from akira_studio_ui import StudioControls
        self.studio_controls=StudioControls(self,tab,card,field,check)
        t=tab('MANTENIMIENTO')
        c=card(t,'APLICACIÓN',RED)
        self.uninstall_button=button(c,'DESINSTALAR AKIRA',self.open_uninstaller,RED);self.uninstall_button.pack(fill='x',pady=6)
        label(c,'Retira el programa y permite conservar tus datos desde el desinstalador de Windows.',MUTED,9,anchor='w',justify='left',wraplength=620).pack(fill='x',pady=6)
        # Every section remains reachable even when high DPI clips notebook tabs.
        chooser=tk.Frame(page,bg=BG);chooser.pack(fill='x',padx=18,pady=(0,4),before=book)
        label(chooser,'SECCIÓN',MUTED,9,True).pack(side='left',padx=(0,10))
        titles=list(self.settings_titles)
        section=tk.StringVar(value=titles[0]);self.settings_section=section
        selector=ttk.Combobox(chooser,textvariable=section,values=titles,state='readonly',style='Akira.TCombobox')
        selector.pack(side='left',fill='x',expand=True)
        selector.bind('<<ComboboxSelected>>',lambda e:book.select(self.settings_pages[titles.index(section.get())]))
        book.bind('<<NotebookTabChanged>>',lambda e:section.set(book.tab(book.select(),'text')),add='+')
    def build_terminal(self,page):
        columns=self.layout.pane(page,'terminal_columns',tk.HORIZONTAL,(.68,));columns.pack(fill='both',expand=True,pady=3)
        outer,body=neon_card(columns,'REGISTROS EN TIEMPO REAL',CYAN);columns.add(outer,minsize=320,stretch='always')
        row=tk.Frame(body,bg=PANEL);row.pack(fill='x',pady=(0,7))
        label(row,'MT5 · MAPAS · RUNNERS · AVISOS',CYAN,8,True,anchor='w').pack(side='left')
        button(row,'ABRIR REGISTROS',lambda:self.open_folder('logs'),MUTED).pack(side='right')
        self.terminal=text_box(body,20);self.terminal.configure(font=(MONO,9),state='disabled');self.terminal_rows=0
        bar=ttk.Scrollbar(body,orient='vertical',command=self.terminal.yview);bar.pack(side='right',fill='y');self.terminal.configure(yscrollcommand=bar.set);self.terminal.pack(fill='both',expand=True)
        for key,color in [('info',MUTED),('confirmed',GREEN),('warning',AMBER),('error',RED)]:self.terminal.tag_configure(key,foreground=color)
        side=self.layout.pane(columns,'terminal_summary',tk.VERTICAL,(.65,));columns.add(side,minsize=235,stretch='always')
        outer,body=neon_card(side,'INFORMES',PINK);side.add(outer,minsize=170,stretch='always')
        shell,body=scroll_frame(body,PANEL);shell.pack(fill='both',expand=True)
        label(body,'Descargar informe',TEXT,17,True,anchor='w').pack(fill='x',pady=7)
        label(body,'Elige el período y dónde guardarlo. Incluye cuenta, órdenes, indicadores, riesgo y fuentes disponibles.',MUTED,9,wraplength=340,justify='left',anchor='w').pack(fill='both',expand=True,pady=8)
        button(body,'DESCARGAR INFORME · PDF',lambda:self.open_report_dialog('PDF'),GREEN).pack(fill='x',pady=5)
        button(body,'DESCARGAR INFORME · EXCEL',lambda:self.open_report_dialog('Excel'),PINK).pack(fill='x',pady=5)
        button(body,'ABRIR ARCHIVOS DESCARGADOS',lambda:self.open_folder('exports'),MUTED).pack(fill='x',pady=5)
        outer,body=neon_card(side,'ESTADO DEL MOTOR',CYAN);side.add(outer,minsize=65,stretch='always')
        shell,body=scroll_frame(body,PANEL);shell.pack(fill='both',expand=True)
        self.terminal_motor=label(body,'Esperando el primer ciclo.',MUTED,10,wraplength=350,anchor='nw',justify='left');self.terminal_motor.pack(fill='both',expand=True,pady=6)

    def progress_event(self,row):
        try:self.chat_progress.put_nowait(dict(row or {}))
        except queue.Full:
            try:self.chat_progress.get_nowait();self.chat_progress.put_nowait(dict(row or {}))
            except Exception:pass

    def desktop_toast(self,title,body,severity='info',event_key=None,category='system'):
        from notification_center import safe_text
        title=safe_text(title)[:90];body=safe_text(body)
        if event_key:
            if self.notice_center.add_once(title,body,event_key,severity,category) is None:return
        else:self.notice_center.add(title,body,severity,category)
        self.update_notice_badge()
        settings=self.cfg.get('desktop') or {}
        if not settings.get('notifications',True) or not settings.get('notification_popup',True):return
        def show():
            try:
                win=tk.Toplevel(self.root);win.overrideredirect(True);win.configure(bg=RED if severity=='error' else AMBER if severity=='warning' else CYAN);win.attributes('-topmost',True)
                inner=tk.Frame(win,bg=PANEL,padx=12,pady=10);inner.pack(fill='both',expand=True,padx=1,pady=1)
                head=tk.Frame(inner,bg=PANEL);head.pack(fill='x')
                label(head,title,CYAN,10,True,anchor='w',wraplength=255).pack(side='left',fill='x',expand=True)
                def dismiss():
                    def step(i=0):
                        try:
                            win.attributes('-alpha',max(0,1-i/8))
                            if i<8:win.after(16,lambda:step(i+1))
                            else:
                                win.destroy()
                                if win in self._toast_windows:self._toast_windows.remove(win)
                        except tk.TclError:pass
                    step()
                for text,fn in [('×',dismiss),('⊘',lambda:self.mute_notifications(True)),('♪',lambda:self.mute_notifications(False))]:
                    b=button(head,text,fn,MUTED);b.configure(padx=5,pady=2,font=(FONT,11));b.pack(side='right',padx=2)
                label(inner,body[:520],TEXT,10,justify='left',anchor='w',wraplength=390).pack(fill='x',pady=(6,0))
                win.update_idletasks();sw=win.winfo_screenwidth();sh=win.winfo_screenheight();w=min(460,sw-30);h=min(sh-100,win.winfo_reqheight()+8)
                x=max(10,sw-w-26);y=max(10,sh-h-70);win.geometry(f'{w}x{h}+{x}+{y+12}')
                for old in list(self._toast_windows):
                    try:old.destroy()
                    except tk.TclError:pass
                self._toast_windows=[win]
                def animate(i=0):
                    try:
                        win.attributes('-alpha',min(1,i/10));win.geometry(f'{w}x{h}+{x}+{y+round(12*(1-i/10))}')
                        if i<10:win.after(16,lambda:animate(i+1))
                    except tk.TclError:pass
                animate();win.lift()
                if settings.get('notification_sound',True):self.root.bell()
                win.after(int(max(2,float(settings.get('toast_seconds',6)))*1000),dismiss)
            except (tk.TclError,AttributeError):pass
        self.root.after(0,show)

    def mute_notifications(self,all=False):
        cfg=copy.deepcopy(self.cfg);cfg['desktop']['notification_sound']=False
        if all:cfg['desktop']['notification_popup']=False
        try:self.cfg.update(save_config(cfg,self.folder/'akira_config.json'))
        except Exception as exc:messagebox.showerror('Notificaciones',str(exc),parent=self.root);return
        for path in ('desktop.notification_sound','desktop.notification_popup'):
            if path in self.setting_vars:self.setting_vars[path].set(path_get(self.cfg,path))
        if all:
            for win in list(self._toast_windows):
                try:win.destroy()
                except tk.TclError:pass
            self._toast_windows.clear()

    def _pending_notification_text(self,row):
        parts=[]
        for symbol,info in (row.get('symbols') or {}).items():
            live=[p for p in (info.get('scenario_book') or []) if p.get('confirmed')]
            if live:
                parts.append(symbol+': '+', '.join(('BUY' if p.get('side')==1 else 'SELL')+' '+str(p.get('kind'))+' '+number(p.get('entry'),2) for p in live[:2]))
        return ' | '.join(parts) or 'Mapa sin pendientes confirmadas en este instante.'

    def maybe_notify(self,row):
        dcfg=self.cfg.get('desktop') or {}
        # Outcomes remain in AVISOS even if popups and sound are muted.
        for close in row.get('position_closures') or []:
            if close.get('state')!='CONFIRMADO MT5':continue
            seen=getattr(self,'_closure_notifications_seen',set());self._closure_notifications_seen=seen
            if close.get('id') in seen:continue
            net=float(close['net']);currency=close.get('currency') or (row.get('account') or {}).get('currency','')
            body=f"{'BUY' if close.get('side')==1 else 'SELL'} #{close['ticket']} · resultado neto {net:+.2f} {currency}\nMotivo: {close['cause']}"
            if close.get('decision_reason') and close.get('initiator')!='AKIRA':body+='\nDecisión registrada por AKIRA: '+close['decision_reason']
            self.desktop_toast(close['symbol']+' · operación cerrada',body,
                severity='warning' if net<0 else 'info',event_key=close['id'],category='trading')
            seen.add(close['id'])
        ledger=row.get('portfolio_risk') or {}
        unknown=tuple(sorted((r.get('symbol'),r.get('ticket')) for r in ledger.get('rows',[]) if not r.get('risk_known',True)))
        if unknown and unknown!=getattr(self,'_notified_unknown_risk',None):
            self.desktop_toast('AKIRA · nuevas entradas bloqueadas',
                'Hay riesgo sin calcular en '+', '.join(str(s)+' #'+str(t) for s,t in unknown)+'. Revisa su SL y sus niveles en MT5. El límite conjunto se comparte entre BTC y oro; los datos técnicos siguen analizándose.',severity='warning',category='trading')
        self._notified_unknown_risk=unknown
        if not bool(dcfg.get('notifications',True)):return
        sources=(row.get('research') or {}).get('sources') or {}
        local_ai=sources.get('local_ai') or {}
        stamp=float(local_ai.get('updated',0) or 0)
        if bool(dcfg.get('notify_deep_analysis',True)) and stamp>0 and stamp!=self._last_deep_stamp:
            self._last_deep_stamp=stamp
            review=(row.get('research') or {}).get('deep_review') or {}
            bits=[]
            active=[s for s in row.get('symbols',{}) if not row.get('markets',{}).get(s,{}).get('scheduled_closed')]
            valid=local_ai.get('fresh') and local_ai.get('usable',True) and not local_ai.get('error') and bool(active) and all(review.get(s) for s in active)
            for symbol in active if valid else []:
                r=review.get(symbol) or {}
                if r:
                    pref='/'.join(r.get('preferred') or []) or 'sin preferencia única'
                    bits.append(symbol+': '+pref+' · conf '+number(float(r.get('confidence',0))*100,0)+'/35')
            if bits:self.desktop_toast('AKIRA · revisión general disponible',' | '.join(bits)+' · Contexto general; cada pendiente conserva su comprobación individual en VERIFICAR.')
        sig=tuple(sorted((str(o.get('symbol')),int(o.get('type',-1)),round(float(o.get('entry',0) or 0),5),round(float(o.get('sl',0) or 0),5),round(float(o.get('tp',0) or 0),5))
                         for o in (row.get('orders') or []) if o.get('owned')))
        if self._last_pending_signature is None:self._last_pending_signature=sig
        elif sig!=self._last_pending_signature:
            self._last_pending_signature=sig
            if bool(dcfg.get('notify_pending_change',True)):
                self.desktop_toast('Akira actualizó sus pendientes',self._pending_notification_text(row))

    def event(self,row):
        try:self.events.put_nowait(row)
        except queue.Full:pass
    def publish(self,row):
        try:self.messages.put_nowait(row)
        except queue.Full:
            try:self.messages.get_nowait()
            except queue.Empty:pass
            try:self.messages.put_nowait(row)
            except queue.Full:pass
    def pause(self):
        self.paused=not self.paused;self.toggle.configure(text='REANUDAR GESTIÓN' if self.paused else 'PAUSAR GESTIÓN')
        self.commands.put({'action':'pause','paused':self.paused})
    def refresh(self):
        self.commands.put({'action':'refresh'})
        if hasattr(self,'source_refresh_state'):
            self.source_refresh_state.configure(text='ACTUALIZANDO...',fg=AMBER)
            self.root.after(3500,lambda:self.source_refresh_state.configure(text='ACTUALIZACIÓN SOLICITADA',fg=GREEN) if hasattr(self,'source_refresh_state') else None)
        self.desktop_toast('Akira actualiza fuentes','Solicité una nueva ronda de web, YouTube, CoinGlass y contexto macro. El mapa técnico sigue funcionando mientras tanto.')
    def async_request(self,cmd,message=None):
        if message:self.append_chat('TÚ',message)
        def work():
            try:result=self.bridge.request(cmd)
            except Exception as exc:result={'ok':False,'error':type(exc).__name__+': '+str(exc)}
            answer=AkiraAssistant._trade_result_text(result)
            self.assistant.remember_execution(message or str(cmd.get('action'))+' '+str(cmd.get('symbol') or 'ALL'),answer,result)
            reply={'answer':answer,'command':True,'message':message}
            if cmd.get('action') in ('assistant_best_pending','assistant_best_runner','assistant_best_trade'):reply['map_result']=result
            self.replies.put(reply)
        threading.Thread(target=work,name='AkiraPendingCommand',daemon=True).start()
    def request_map(self,symbol):
        if self.map_request_busy:return
        self.map_request_busy=True
        self.map_result_label.configure(text='Analizando y comprobando pendientes '+symbol+' en MT5...',fg=AMBER)
        self.async_request({'action':'assistant_best_pending','symbol':symbol},None)
    def request_runners(self,symbol):
        if self.map_request_busy:return
        self.map_request_busy=True
        self.map_result_label.configure(text='Comprobando runners confirmados '+symbol+' en MT5...',fg=AMBER)
        self.async_request({'action':'assistant_best_runner','symbol':symbol},None)
    def cancel_selected(self):
        selection=self.orders.selection()
        if not selection:return
        ticket=int(selection[0]);row=next((o for o in self.view.get('orders',[]) if o['ticket']==ticket),{})
        if not row.get('owned'):messagebox.showinfo('Akira','Esta pendiente es manual o de otro EA.',parent=self.root);return
        self.async_request({'action':'cancel_pending','ticket':ticket},'Retira mi pendiente Akira #'+str(ticket))
    def append_chat(self,who,text):
        if hasattr(self,'chat_welcome'):self.chat_welcome.place_forget()
        """Render source titles as links without dumping URL paragraphs in the chat."""
        tag='user' if who=='TÚ' else 'assistant' if who=='AKIRA' else 'system'
        self.chat.configure(state='normal')
        self.chat.insert('end',('  TÚ' if who=='TÚ' else '✧  AKIRA' if who=='AKIRA' else '  '+who)+'  ·  '+time.strftime('%H:%M')+'\n','chat_user_author' if who=='TÚ' else 'chat_author' if who=='AKIRA' else 'system')
        body=str(text)
        # Keep exact URLs as tag targets, not visible 200-character strings.
        parts=re.compile(r'\[([^\]\n]{1,160})\]\((https?://[^\s)]+)\)|https?://[^\s<>]+')
        last=0
        for i,m in enumerate(parts.finditer(body)):
            self.chat.insert('end',body[last:m.start()],tag)
            url=(m.group(2) or m.group(0)).rstrip('.,)')
            title=m.group(1) or ('↗ '+(urlparse(url).hostname or 'fuente').removeprefix('www.'))
            start_pos=self.chat.index('end-1c');self.chat.insert('end',title,tag)
            end_pos=self.chat.index('end-1c')
            linktag='source_'+str(time.time_ns())+'_'+str(i)
            self.chat.tag_add(linktag,start_pos,end_pos)
            self.chat.tag_configure(linktag,foreground=CYAN,underline=True)
            self.chat.tag_bind(linktag,'<Button-1>',lambda event,link=url:webbrowser.open(link))
            last=m.end()
        self.chat.insert('end',body[last:],tag)
        self.chat.insert('end','\n\n')
        self.chat.see('end');self.chat.configure(state='disabled')
        if who=='AKIRA' and self.voice_awaiting and self.voice_call_active and self.voice_session:
            self.voice_awaiting=False;self.voice_session.speak(str(text))
        # Avoid link_urls(): the source tags above already own the clickable range.
    def ask(self):
        message=self.chat_input.get().strip()
        if not message:return
        self._last_user_question=message
        snapshot=copy.deepcopy(self.view)
        if getattr(self,'_network_status',{}).get('online') is False:snapshot['network_available']=False
        casual=self.assistant._instant_general_reply(message,snapshot)
        if casual and not self.chat_busy:
            self.chat_input.set('');self.append_chat('TÚ',message);self.assistant._remember_turn(message,casual);self.append_chat('AKIRA',casual);self.refresh_chat_list()
            if self.avatars:self.avatars[0].director.publish('happy','Saludo del usuario')
            self._avatar_reaction_until=time.monotonic()+4;self.root.after(4200,self.reset_avatar);return
        exact=AkiraAssistant._named_pending(message,snapshot)
        if exact is not None:
            self.chat_input.set('');self.async_request({'action':'assistant_plan',**exact},message);return
        dialogue=getattr(self.assistant,'dialogue',None)
        previous=dialogue.previous_question(getattr(self.assistant,'history',())) if dialogue else ''
        quick=instant_review(message,snapshot,previous,time.time())
        if quick is not None:
            self.chat_input.set('');self.append_chat('TÚ',message);self.append_chat('AKIRA',quick)
            self.assistant._remember_turn(message,quick);self.refresh_chat_list()
            return
        command=route_fast_request(message,previous,analysis_only=AkiraAssistant._analysis_only(message),
            pending_execution=AkiraAssistant._best_pending_request(message))
        if command is not None:
            self.chat_input.set('');self.async_request(command,message);return
        if self.chat_busy:
            self.append_chat('ESTADO','Akira sigue respondiendo tu consulta anterior. Los controles de pendientes siguen disponibles.');return
        self.chat_busy=True;self.chat_started=time.monotonic();self.chat_stage='PENSANDO';self.chat_stage_detail='Entendiendo tu pregunta';self.chat_source_names=[]
        self.stop_thinking_btn.configure(state='normal');self.chat_input.set('');self.append_chat('TÚ',message);self.assistant.reset_cancel()
        for a in self.avatars:a.set_expression('thinking')
        allow_cloud=self.use_cloud.get()
        def work():
            try:answer=self.assistant.reply(message,snapshot,use_cloud=allow_cloud)
            except Exception as exc:
                if self.assistant.cancelled():answer='Análisis detenido por ti.'
                else:answer='No llegó una respuesta: '+type(exc).__name__+': '+str(exc)
            self.replies.put({'answer':answer,'message':message,'command':False,'conversation':True})
        threading.Thread(target=work,name='AkiraConversation',daemon=True).start()
    def start_voice(self):
        if self.voice_window is not None:
            try:
                if self.voice_window.winfo_exists():self.voice_window.lift();return
            except tk.TclError:pass
        win=tk.Toplevel(self.root);self.voice_window=win;win.title('AKIRA · Llamada');win.configure(bg=BG)
        apply_window_icon(win,self.folder)
        w,h,mw,mh=fitted_geometry(760,800,win.winfo_screenwidth(),win.winfo_screenheight());win.geometry(f'{min(760,w)}x{h}');win.minsize(min(450,w),min(360,h))
        label(win,'CONVERSAR CON AKIRA',TEXT,18,True).pack(pady=(12,4))
        self.voice_state=label(win,'Detectando dispositivos y voces disponibles...',AMBER,9,wraplength=650);self.voice_state.pack(fill='x',padx=16,pady=4)
        outer,container=neon_card(win,'VOZ Y DISPOSITIVOS',CYAN,padx=10,pady=6);outer.pack(fill='both',expand=True,padx=12,pady=(2,8))
        voice_shell,body=scroll_frame(container,PANEL);voice_shell.pack(fill='both',expand=True)
        self.voice_scroll_canvas=voice_shell._scroll_canvas
        self.voice_avatar=self.avatar(body,200,140);self.voice_avatar.pack(fill='x',pady=(0,6))
        options=self.cfg.get('voice') or {};self.voice_vars={};self.voice_boxes={}
        form=tk.Frame(body,bg=PANEL);form.pack(fill='x');form.columnconfigure(0,weight=1);form.columnconfigure(1,weight=1)
        for key,title,r,c,span in [('voice','Voz',0,0,2),('input','Micrófono',1,0,1),('output','Salida de audio',1,1,1)]:
            field=tk.Frame(form,bg=PANEL);field.grid(row=r,column=c,columnspan=span,sticky='ew',padx=(0,5),pady=4)
            label(field,title,MUTED,9,True,anchor='w').pack(fill='x',pady=(0,3))
            var=tk.StringVar(value='Detectando...');self.voice_vars[key]=var
            box=ttk.Combobox(field,textvariable=var,state='readonly',style='Akira.TCombobox');box.pack(fill='x');self.voice_boxes[key]=box
        self.voice_rate=tk.StringVar(value=str(options.get('rate',180)));self.voice_volume=tk.StringVar(value=str(options.get('volume',.8)))
        row=tk.Frame(body,bg=PANEL);row.pack(fill='x',pady=6)
        for title,var in [('Velocidad',self.voice_rate),('Volumen',self.voice_volume)]:
            label(row,title,MUTED,9).pack(side='left',padx=(0,6))
            tk.Entry(row,textvariable=var,bg=CARD,fg=TEXT,insertbackground=CYAN,width=7,relief='flat').pack(side='left',padx=(0,14),ipady=5)
        button(body,'CONSULTAR CATÁLOGO DE VOCES',lambda:self.load_voice_inventory(True),MUTED).pack(fill='x',pady=(1,4))
        row=tk.Frame(body,bg=PANEL);row.pack(fill='x',pady=(2,5))
        self.download_one_button=button(row,'DESCARGAR VOZ ELEGIDA',self.download_selected_voice,CYAN);self.download_one_button.pack(side='left',fill='x',expand=True,padx=(0,4))
        self.download_all_button=button(row,'DESCARGAR TODAS',self.download_all_voices,BLUE);self.download_all_button.pack(side='left',fill='x',expand=True)
        row=tk.Frame(body,bg=PANEL);row.pack(fill='x',pady=(0,5))
        self.voice_download_cancel=button(row,'CANCELAR DESCARGA',self.cancel_voice_download,AMBER);self.voice_download_cancel.pack(side='left')
        button(row,'ESCUCHAR DEMO',self.preview_voice,GREEN).pack(side='right')
        self.voice_download_status=label(body,'Un clic descarga e instala todo el catálogo. Las voces completas se conservan al reintentar.',MUTED,8,wraplength=650,anchor='w',justify='left');self.voice_download_status.pack(fill='x',pady=(3,4))
        self.voice_download_progress=ttk.Progressbar(body,mode='determinate',maximum=100,style='Cyber.Horizontal.TProgressbar');self.voice_download_progress.pack(fill='x',pady=(0,5))
        label(body,'Elige la voz y los dispositivos para la llamada. El chat escrito permanece silencioso.',MUTED,8,wraplength=650,justify='left',anchor='w').pack(fill='x',pady=3)
        self.voice_transcript=text_box(body,3);self.voice_transcript.pack(fill='x',pady=6)
        row=tk.Frame(body,bg=PANEL);row.pack(fill='x',pady=4)
        self.voice_start_button=button(row,'INICIAR',self.begin_call,GREEN);self.voice_start_button.pack(side='left')
        self.voice_pause_button=button(row,'PAUSAR',self.pause_call,AMBER);self.voice_pause_button.pack(side='left',padx=4)
        button(row,'INTERRUMPIR',self.interrupt_call,BLUE).pack(side='left')
        button(row,'FINALIZAR',self.end_call,RED).pack(side='right')
        row=tk.Frame(body,bg=PANEL);row.pack(fill='x',pady=3)
        button(row,'CANCELAR MENSAJE',self.cancel_voice_message,MUTED).pack(side='left')
        button(row,'ENVIAR TRANSCRIPCIÓN',self.send_voice_transcript,CYAN).pack(side='right')
        def close_voice():
            self.end_call()
            if self.voice_avatar in self.avatars:self.avatars.remove(self.voice_avatar)
            win.destroy();self.voice_window=None
        win.protocol('WM_DELETE_WINDOW',close_voice)
        self._render_voice_download()
        self.load_voice_inventory(False)

    def load_voice_inventory(self,online=False):
        if self.voice_window is None:return
        try:
            if not self.voice_window.winfo_exists():return
        except tk.TclError:return
        self.voice_state.configure(text='Consultando catálogo...' if online else 'Detectando voces y dispositivos...',fg=AMBER)
        def work():
            errors=[]
            try:devices=audio_inventory()
            except Exception as exc:devices={'inputs':[],'outputs':[]};errors.append('Audio: '+str(exc)[:150])
            try:voices=voice_inventory(self.folder,online)
            except Exception as exc:voices=self._voice_catalog;errors.append('Catálogo: '+str(exc)[:150])
            self.replies.put({'voice_inventory':voices,'devices':devices,'voice_setup_error':' · '.join(errors)})
        threading.Thread(target=work,name='AkiraVoiceCatalog',daemon=True).start()

    def _handle_voice_inventory(self,reply):
        prior_id=None
        try:
            index=self.voice_boxes['voice'].current()
            if 0<=index<len(self._voice_catalog):prior_id=self._voice_catalog[index]['id']
        except (AttributeError,tk.TclError):pass
        self._voice_catalog=reply['voice_inventory'];self._voice_devices=reply['devices']
        if self.voice_window is None:return
        try:
            if not self.voice_window.winfo_exists():return
            saved=self.cfg.get('voice') or {}
            names=[v['name']+' ['+('disponible' if v['installed'] else 'descargar')+']' for v in self._voice_catalog]
            self.voice_boxes['voice'].configure(values=names)
            index=next((i for i,v in enumerate(self._voice_catalog) if v['id']==(prior_id or saved.get('voice_id'))),next((i for i,v in enumerate(self._voice_catalog) if v['installed']),0))
            self.voice_vars['voice'].set(names[index] if names else 'Sin voces; consulta catálogo para elegir una voz')
            for key,group in [('input','inputs'),('output','outputs')]:
                values=['Predeterminado']+[str(d['id'])+' · '+d['name'] for d in self._voice_devices[group]]
                self.voice_boxes[key].configure(values=values);device=saved.get(key+'_device',-1)
                self.voice_vars[key].set(next((str(d['id'])+' · '+d['name'] for d in self._voice_devices[group] if d['id']==device),'Predeterminado'))
            self.voice_state.configure(text=reply.get('voice_setup_error') or f'{len(names)} voces en catálogo. Elige voz y dispositivos antes de iniciar.',fg=AMBER if reply.get('voice_setup_error') else GREEN)
        except tk.TclError:pass

    def voice_selection(self,require_installed=True):
        index=self.voice_boxes['voice'].current()
        if index<0 or index>=len(self._voice_catalog):raise ValueError('Selecciona una voz disponible')
        voice=self._voice_catalog[index]
        if require_installed and not voice['installed']:raise ValueError('Instala primero la voz seleccionada y escucha su demostración')
        rate=int(float(self.voice_rate.get()));volume=float(self.voice_volume.get())
        if not 80<=rate<=300 or not 0<=volume<=1:raise ValueError('Velocidad: 80–300. Volumen: 0–1.')
        options={'voice_id':voice['id'],'rate':rate,'volume':volume,'model':self.cfg['assistant'].get('voice_model','tiny'),'language':self.cfg.get('studio',{}).get('language_voice_in','auto') if self.cfg.get('studio',{}).get('language_voice_in','auto')!='auto' else self.cfg['assistant'].get('voice_language','es')}
        for key in ('input','output'):
            raw=self.voice_vars[key].get();options[key+'_device']=None if raw=='Predeterminado' else int(raw.split(' · ')[0])
        return voice,options

    def download_selected_voice(self):
        if getattr(self,'_voice_download_busy',False):return
        try:voice,options=self.voice_selection(False)
        except Exception as exc:self.voice_state.configure(text=str(exc),fg=AMBER);return
        if voice['installed']:
            self.voice_state.configure(text='Esta voz ya está disponible.',fg=GREEN);return
        cancel=threading.Event()
        self._voice_single_cancel=cancel
        self._voice_download_job=None
        self._voice_download_busy=True
        self._voice_download_last={'state':'downloading_one','current':voice['name'],'file_bytes':0,'file_total':0}
        self._render_voice_download()
        def work():
            def notice(filename,done,total):
                self.replies.put({'voice_single_progress':{'state':'downloading_one','current':voice['name']+' · '+filename,
                    'file_bytes':done,'file_total':total}})
            try:
                install_voice(self.folder,voice,lambda msg:self.replies.put({'voice_event':{'kind':'state','text':msg}}),cancel,notice)
                kind='cancelled' if cancel.is_set() else 'installed'
                self.replies.put({'voice_single_done':{'kind':kind,'name':voice['name']}})
            except Exception as exc:
                kind='cancelled' if cancel.is_set() else 'error'
                self.replies.put({'voice_single_done':{'kind':kind,'error':str(exc)[:200]}})
        threading.Thread(target=work,name='AkiraVoiceDownloadSingle',daemon=True).start()

    def handle_voice_single_done(self,event):
        self._voice_single_cancel=None
        self._voice_download_busy=False
        kind=event.get('kind')
        self._voice_download_last={'state':'complete_one' if kind=='installed' else kind,
            'current':event.get('name') or '', 'error':event.get('error') or ''}
        self._render_voice_download()
        if kind=='installed':self.load_voice_inventory(False)

    def download_all_voices(self):
        if self._voice_download_busy:return
        self._voice_download_busy=True
        self._voice_download_job=VoiceDownloadBatch(self.folder,
            lambda event:self.replies.put({'voice_download':event}),self.stop)
        self._voice_download_last={'job_id':self._voice_download_job.job_id,'state':'catalog','current':'Consultando catálogo e iniciando instalación automática...'}
        self._render_voice_download();self._voice_download_job.start()

    def cancel_voice_download(self):
        job=getattr(self,'_voice_download_job',None)
        single=getattr(self,'_voice_single_cancel',None)
        if not self._voice_download_busy:return
        if single is not None:single.set()
        elif job is not None:job.cancel()
        else:return
        self._voice_download_last['state']='cancelling'
        self._render_voice_download()

    def handle_voice_download(self,event):
        if not self._voice_download_job or event.get('job_id')!=self._voice_download_job.job_id:return
        self._voice_download_last=event
        if event.get('finished'):
            self._voice_download_busy=False
            self.load_voice_inventory(False)
        self._render_voice_download()

    def _render_voice_download(self):
        if self.voice_window is None:return
        state=self._voice_download_last;kind=state.get('state');total=state.get('models_total',0);done=state.get('models_done',0)
        try:
            self.download_one_button.configure(state='disabled' if self._voice_download_busy else 'normal')
            self.download_all_button.configure(state='disabled' if self._voice_download_busy else 'normal',
                text='DESCARGANDO VOCES...' if self._voice_download_busy else 'REINTENTAR / COMPLETAR VOCES' if kind in ('partial','error','cancelled','disk_full') else 'DESCARGAR TODAS LAS VOCES')
            self.voice_download_cancel.configure(state='normal' if self._voice_download_busy else 'disabled')
            self.voice_download_progress.configure(value=(state.get('file_bytes',0)/max(1,state.get('file_total',0))*100
                if kind=='downloading_one' and state.get('file_total') else done/total*100 if total else 0))
            if not state:return
            caption={'catalog':'Preparando todo el catálogo...','downloading_one':'Descargando solo la voz seleccionada...','complete_one':'La voz elegida está instalada.','downloading':f'Modelos {done}/{total} · {state.get("voices_total",0)} voces',
                'complete':f'Catálogo instalado · {total} modelos · {state.get("voices_total",0)} voces',
                'partial':f'Instalados {state.get("downloaded",0)} · ya disponibles {state.get("skipped",0)} · fallaron {state.get("failed",0)}. Pulsa reintentar.',
                'cancelled':'Descarga detenida. Las voces completas siguen disponibles; puedes continuar.',
                'cancelling':'Deteniendo la descarga; esperando a que termine la lectura actual...',
                'disk_full':'Descarga detenida por falta de espacio. Libera espacio y pulsa reintentar.',
                'error':state.get('error','No se pudo descargar. Reintenta.'),'empty':'El catálogo no contiene modelos descargables.'}.get(kind,'')
            if kind in ('downloading','downloading_one'):
                size=state.get('file_bytes',0)/1048576;limit=state.get('file_total',0)/1048576
                estimate=state.get('bytes_total',0)/1073741824
                if estimate:caption+=f' · catálogo {estimate:.1f} GB'
                caption+='\n'+str(state.get('current',''))[:85]+(f' · {size:.1f} / {limit:.1f} MB' if limit else '')
            elif kind=='partial' and state.get('errors'):caption+='\n'+str(state['errors'][0]['error'])[:100]
            elif kind=='error':caption+='\n'+str(state.get('error') or '')[:160]
            self.voice_download_status.configure(text=caption,fg=GREEN if kind=='complete' else AMBER if kind in ('partial','error','disk_full') else MUTED)
        except (AttributeError,tk.TclError):pass

    def preview_voice(self):
        if self.voice_call_active:return
        try:voice,options=self.voice_selection()
        except Exception as exc:self.voice_state.configure(text=str(exc),fg=AMBER);return
        if self.voice_session:self.voice_session.stop()
        self.voice_session=VoiceSession(self.folder,lambda e:self.replies.put({'voice_event':e}),{**options,'preview':True},voice)
        self.voice_session.speak('Hola, soy Akira. Esta es una demostración de mi voz. Tú eliges cuándo iniciamos la conversación.')

    def begin_call(self):
        if self.voice_call_active or self.chat_busy:return
        try:
            voice,options=self.voice_selection()
            if not self._voice_devices['inputs']:raise ValueError('No hay micrófono disponible')
            if not messagebox.askyesno('AKIRA · Micrófono','¿Iniciar la llamada usando el micrófono seleccionado?\n\nAKIRA transcribe localmente mientras la llamada esté activa. Puedes silenciar el micrófono, interrumpir la respuesta o finalizar en cualquier momento.',parent=self.voice_window):return
            cfg=copy.deepcopy(self.cfg);cfg['voice']=options;self.cfg.update(save_config(cfg,self.folder/'akira_config.json'))
            if self.voice_session:self.voice_session.stop()
            self.voice_session=VoiceSession(self.folder,lambda e:self.replies.put({'voice_event':e}),options,voice)
            self.voice_call_active=True;self.voice_awaiting=False;self.voice_start_button.configure(state='disabled');self.voice_session.start()
            if getattr(self,'avatar_director',None):self.avatar_director.playback(False)
            for avatar in getattr(self,'avatars',[]):avatar.set_expression('idle')
        except Exception as exc:self.voice_state.configure(text=str(exc),fg=RED)

    def pause_call(self):
        if not self.voice_session or not self.voice_call_active:return
        if self.voice_session.paused.is_set():self.voice_session.resume();self.voice_pause_button.configure(text='PAUSAR')
        else:self.voice_session.pause();self.voice_pause_button.configure(text='REANUDAR')

    def interrupt_call(self):
        if self.voice_session:self.voice_session.interrupt();self.voice_session.resume()
        self.voice_awaiting=False
        if self.chat_busy:self.stop_thinking()
        if getattr(self,'avatar_director',None):self.avatar_director.playback(False)
        for avatar in getattr(self,'avatars',[]):avatar.set_expression('idle')

    def end_call(self):
        self.voice_call_active=False;self.voice_awaiting=False
        if self.voice_session:self.voice_session.stop()
        if getattr(self,'avatar_director',None):self.avatar_director.playback(False)
        for avatar in getattr(self,'avatars',[]):avatar.set_expression('idle')
        try:
            if self.voice_window is not None:self.voice_start_button.configure(state='normal');self.voice_pause_button.configure(text='PAUSAR')
        except tk.TclError:pass

    def cancel_voice_message(self):
        self.voice_awaiting=False
        if self.voice_session:self.voice_session.cancel_message()
        if hasattr(self,'voice_transcript'):replace_text(self.voice_transcript,'')

    def send_voice_transcript(self):
        if self.chat_busy:return
        text=self.voice_transcript.get('1.0','end-1c').strip()
        if text:
            if self.voice_call_active and self.voice_session:self.voice_session.submit_message()
            self.voice_awaiting=self.voice_call_active;self.chat_input.set(text);self.ask()

    def handle_voice_event(self,event):
        session_id=event.get('session_id')
        if session_id and (not self.voice_session or session_id!=self.voice_session.session_id):return
        kind=event.get('kind');text=str(event.get('text',''))
        director=getattr(self,'avatar_director',None)
        if director is not None and kind=='playback_start':director.playback(True);return
        if director is not None and kind=='playback_end':director.playback(False);return
        if director is not None and kind=='playback_level':director.level(event.get('level',0));return
        if getattr(self,'voice_call_active',False) or kind in ('error','download_error'):
            mood=expression_for_voice_event(kind,text)
            for avatar in getattr(self,'avatars',[]):avatar.set_expression(mood,context=str(event))
        if kind=='installed':self._voice_download_busy=False;self.load_voice_inventory(False);return
        if kind=='download_error':self._voice_download_busy=False;kind='error'
        if kind=='final':
            if self.voice_call_active and self.voice_session and not self.voice_session.stop_event.is_set() and not self.chat_busy:
                self.voice_awaiting=True;self.chat_input.set(text);self.ask()
            return
        if kind=='error' and self.voice_session and self.voice_session.stop_event.is_set():self.end_call()
        try:
            if self.voice_window is not None and self.voice_window.winfo_exists():
                if kind=='partial':replace_text(self.voice_transcript,text)
                else:self.voice_state.configure(text=text,fg=RED if kind=='error' else CYAN)
        except tk.TclError:pass

    def request_risk_ack(self):
        def work():self.replies.put({'risk_ack':self.bridge.request({'action':'risk_settings'})})
        threading.Thread(target=work,name='AkiraRiskConfirm',daemon=True).start()

    def ui_callback_error(self,kind,value,tb):
        self.record_ui_error('Evento de interfaz',value,tb)

    def record_ui_error(self,context,error,tb=None):
        pending=getattr(self,'_active_render_errors',None)
        if pending is not None and context not in pending:pending.append(context)
        import traceback
        from notification_center import safe_text
        key=(context,type(error).__name__,str(error));now=time.monotonic()
        if now-self._ui_error_times.get(key,-1000)<60:return
        self._ui_error_times[key]=now
        if len(self._ui_error_times)>100:self._ui_error_times={key:now}
        path=self.folder/'logs'/'INTERFAZ_ERRORES.log'
        trace=safe_text(''.join(traceback.format_exception(type(error),error,tb or error.__traceback__)))
        try:
            path.parent.mkdir(parents=True,exist_ok=True)
            if path.exists() and path.stat().st_size>1_000_000:path.replace(path.with_suffix('.anterior.log'))
            with path.open('a',encoding='utf-8') as stream:stream.write(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())+' '+context+'\n'+trace+'\n')
        except OSError:pass
        cause='Falta el módulo '+str(getattr(error,'name',None) or str(error)) if isinstance(error,ModuleNotFoundError) else type(error).__name__+': '+str(error)
        from akira_version import BUILD_ID
        message=f'{context}: {safe_text(cause)[:240]}. Versión {BUILD_ID}. Este panel no terminó su actualización; detalle en INTERFAZ_ERRORES.log.'
        try:
            self.notice_center.add('AKIRA · error de interfaz',message,'error','system');self.update_notice_badge()
            self.event({'state':'ERROR','symbol':'AKIRA','category':'interface','message':message})
        except Exception:pass

    def refresh_assistant_status(self):
        local=self.assistant.local_ai_status();text=brand_status(local)
        self._assistant_display_status=local
        color=GREEN if local.get('ready') else RED if local.get('phase') in ('FAILED','STALLED') else AMBER
        if getattr(self,'_network_status',{}).get('online') is False:text='AKIRA · SIN INTERNET';color=AMBER
        for widget in (self.sidebar_status,self.brain_label,self.chat_model):widget.configure(text=text,fg=color)
        detail=public_status(local.get('detail') or 'Comprobando el asistente...')
        if local.get('last_reply_error'):
            detail='El último mensaje no terminó: '+public_status(local['last_reply_error'])+'. Puedes reintentar; la disponibilidad del motor no equivale a una respuesta completada.'
        self.assistant_detail.configure(text=detail,fg=color if not local.get('ready') else MUTED)
        short='ACTIVO' if local.get('ready') else text.partition(' · ')[2].upper()
        self.source_status['local'].configure(text=short,fg=color)
        dot,value=self.friendly_source_cards['local'];dot.configure(fg=color);value.configure(text=short.title(),fg=color)
        preparing=local.get('phase') in ('CHECKING','INSTALLING','STARTING','DOWNLOADING','VERIFYING','WAITING','VISION') and not local.get('ready')
        self.assistant_repair_button.configure(state='disabled' if preparing else 'normal')
        self.chat_repair_button.configure(state='disabled' if preparing or local.get('ready') else 'normal')
        previous=getattr(self,'_assistant_last_phase',None)
        phase=local.get('phase')
        if phase!=previous and previous is not None:
            if local.get('ready'):
                self.desktop_toast('AKIRA disponible',detail)
                self.commands.put({'action':'refresh','sources':['local_ai']})
            elif phase in ('FAILED','STALLED'):
                self.desktop_toast('AKIRA · reparación pendiente',detail,severity='warning')
        self._assistant_last_phase=phase


    def poll(self):
        if self._poll_after_id:
            try:self.root.after_cancel(self._poll_after_id)
            except tk.TclError:pass
            self._poll_after_id=None
        try:self._poll_once()
        except Exception as exc:self.record_ui_error('Actualización de interfaz',exc)
        finally:
            if not self.stop.is_set():
                try:self._poll_after_id=self.root.after(self._performance["poll_ms"],self.poll)
                except tk.TclError:pass

    def _poll_once(self):
        if time.monotonic()>=self._assistant_display_due:
            try:self.refresh_assistant_status()
            except Exception as exc:self.record_ui_error('Estado del asistente',exc)
            self._assistant_display_due=time.monotonic()+self._performance["assistant_seconds"]
        latest=None
        try:
            while True:latest=self.messages.get_nowait()
        except queue.Empty:pass
        if latest:
            self.view=latest;self.bridge.connected=bool(latest.get('connected'))
            from connectivity import recently_connected
            if recently_connected(latest):self._network_evidence_at=time.monotonic()
            self._last_snapshot_received=time.monotonic()
            if self.bridge.connected:self.bridge.starting=False
        if time.monotonic()>=self.display_due:
            if self.view:
                try:self.render(self.view)
                except Exception as exc:self.record_ui_error('Paneles de mercado',exc)
            self.display_due=time.monotonic()+self._performance["render_seconds"]
        for _ in range(50):
            try:row=self.events.get_nowait()
            except queue.Empty:break
            event_text=str(row.get('message',row.get('text','')))
            if row.get('operation')=='quality_entry_blocked':
                self.desktop_toast('AKIRA · entrada evitada',str(row.get('symbol',''))+' · '+str(row.get('reason') or event_text),
                    severity='warning',event_key=row.get('event_key'),category='trading')
            if row.get('category')!='interface' and (row.get('state')=='ERROR' or any(word in event_text.lower() for word in ('rechazo mt5','sin confirmación mt5','error inesperado','solicitud incierta','order_check sin respuesta','cuenta diferente','bloqueo de seguridad'))):
                self.notice_center.add('Evento de operaciones',str(row.get('symbol',''))+' · '+event_text,'error','trading');self.update_notice_badge()
            if (self.view.get('markets') or {}).get(row.get('symbol'),{}).get('scheduled_closed'):continue
            self._terminal_pending.append(str(row.get('utc',''))+' '+str(row.get('symbol',''))+' · '+str(row.get('message',row.get('text','')))+'\n')
        if getattr(self,'current_page_index',0)==7 and self._terminal_pending:
            lines=list(self._terminal_pending);self._terminal_pending.clear()
            self.terminal.configure(state='normal');self.terminal.insert('end',''.join(lines));self.terminal_rows+=len(lines)
            if self.terminal_rows>2500:self.terminal.delete('1.0','501.0');self.terminal_rows-=500
            self.terminal.see('end');self.terminal.configure(state='disabled')
        for _ in range(30):
            try:prog=self.chat_progress.get_nowait()
            except queue.Empty:break
            stage=str(prog.get('stage') or 'FUENTES');detail=str(prog.get('detail') or '');url=str(prog.get('url') or '')
            self.chat_stage=stage;self.chat_stage_detail=public_status(detail)[:120]
            source='';low=(stage+' '+detail+' '+url).lower()
            if 'youtube' in low:source='YouTube'
            elif 'coinglass' in low:source='CoinGlass'
            elif 'investing' in low:source='Investing'
            elif 'reuters' in low:source='Reuters/Web'
            elif 'web' in low or url:source='Web'
            elif 'ia' in low or 'modelo' in low:source='AKIRA'
            if source and source not in self.chat_source_names:self.chat_source_names.append(source)
        self._render_chat_progress()
        for _ in range(10):
            try:reply=self.replies.get_nowait()
            except queue.Empty:break
            if self.handle_service_reply(reply):continue
            if 'strategy_export_result' in reply:
                result=reply['strategy_export_result']
                try:self.strategy_export_button.configure(state='normal')
                except (AttributeError,tk.TclError):pass
                self.desktop_toast('Directorio de estrategias',('Guardado en '+result['path']) if result.get('ok') else result.get('error','No se pudo descargar'),severity='info' if result.get('ok') else 'error')
                continue
            if 'voice_download' in reply:
                self.handle_voice_download(reply['voice_download']);continue
            if 'voice_single_progress' in reply:
                if self._voice_download_busy and self._voice_single_cancel is not None:
                    self._voice_download_last=reply['voice_single_progress'];self._render_voice_download()
                continue
            if 'voice_single_done' in reply:
                self.handle_voice_single_done(reply['voice_single_done']);continue
            if 'voice_inventory' in reply:
                self._handle_voice_inventory(reply);continue
            if 'voice_event' in reply:
                self.handle_voice_event(reply['voice_event']);continue
            if 'study_result' in reply:
                try:
                    if reply['study_window'].winfo_exists():
                        result=reply['study_result'];reply['study_button'].configure(state='normal')
                        replace_text(reply['study_box'],result.get('text') or 'No se pudo evaluar: '+result.get('error',''))
                except tk.TclError:pass
                continue
            if 'library_result' in reply:
                try:
                    if reply['library_window'].winfo_exists():replace_text(reply['library_box'],reply['library_result'])
                except tk.TclError:pass
                continue
            if 'cloud_check' in reply:
                if self.use_cloud.get():self.cloud_status.configure(text=reply['cloud_check']['detail'],fg=GREEN if reply['cloud_check'].get('ok') else AMBER)
                continue
            if 'risk_ack' in reply:
                result=reply['risk_ack'];detail=result.get('detail') or result.get('error') or 'Esperando confirmación de MT5. El ajuste quedó guardado para el próximo ciclo.'
                self.map_result_label.configure(text=detail,fg=GREEN if result.get('ok') else AMBER)
                self.desktop_toast('AKIRA · Ajuste de riesgo',detail);continue
            if 'report_ready' in reply or 'report_error' in reply or 'report_saved' in reply:
                self.handle_report_reply(reply);continue
            if 'voice_heard' in reply or 'voice_error' in reply:
                self.voice_listening=False;self.voice_button.configure(text='🎙 HABLAR A AKIRA',state='normal')
                if 'voice_error' in reply:messagebox.showwarning('Micrófono',reply['voice_error'],parent=self.root)
                elif reply['voice_heard']:
                    self.chat_input.set(reply['voice_heard']);self.ask()
                else:self.append_chat('ESTADO','No reconocí palabras. Puedes intentarlo otra vez.')
                continue
            if 'memory' in reply:
                replace_text(self.memory_results,reply['memory']);continue
            if not (reply.get('command') and 'message' in reply and reply.get('message') is None):
                self.append_chat('AKIRA',reply['answer'])
            if 'map_result' in reply:
                self.map_request_busy=False
                result=reply['map_result'];rows=result.get('results') or []
                detail=' | '.join(str(r.get('symbol','?'))+': '+str(r.get('detail','')) for r in rows) or str(result.get('error') or result.get('note') or 'Sin confirmación')
                self.map_result_label.configure(text=detail,fg=GREEN if result.get('ok') else AMBER)
                self.desktop_toast('Resultado BTC + oro',detail[:500]+' · Entry/SL/TP en tabla y chat.')
            if reply.get('conversation'):self.refresh_chat_list()
            if reply.get('command'):
                # SQLite I/O y continuidad también se mantienen fuera de Tk.
                pass  # El resultado ya quedó en continuidad fuera de Tk/modelo.
            elif reply.get('conversation'):
                self.chat_busy=False;self.stop_thinking_btn.configure(state='disabled');self.chat_stage='LISTO';self.chat_stage_detail='';self._render_chat_progress()
            reaction=expression_for_dialogue(getattr(self,'_last_user_question',''),reply.get('answer',''))
            if reaction=='talking' and not self.voice_call_active:reaction='idle'
            for avatar in self.avatars:avatar.set_expression(reaction,context=str(reply.get('answer','')))
            self._avatar_reaction_until=time.monotonic()+8
            if not getattr(self,'voice_call_active',False):self.root.after(8000,self.reset_avatar)
    def remember_command(self,message,answer):
        with self.assistant.lock:self.assistant._remember_turn(message,answer)
    def reset_avatar(self):
        if not self.stop.is_set():
            self._avatar_reaction_until=0
            for avatar in self.avatars:avatar.set_expression('thinking' if self.chat_busy else 'analyzing' if self.view.get('connected') else 'waiting')
    def render(self,row):
        if not self.chat_busy and time.monotonic()>=getattr(self,'_avatar_reaction_until',0) and self.avatars:
            activity='analyzing' if row.get('connected') else 'connecting'
            self.avatars[0].director.publish(activity)
        received=getattr(self,'_last_snapshot_received',None)
        if received is not None:row={**row,'ui_age_seconds':max(0,time.monotonic()-received)}
        self._render_generation=getattr(self,'_render_generation',0)+1
        self._active_render_errors=[]
        # Expensive Tk rendering must be limited to the visible notebook pane.
        # The MT5 actor, risk protection, and notification accounting stay active.
        if not row.get('connected'):
            self.connection.configure(text=public_status(row.get('error','Esperando MT5')),fg=AMBER)
            self.side_connection.configure(text='MT5 · sin conexión',fg=AMBER)
            self.source_status['mt5'].configure(text='SIN CONEXIÓN',fg=AMBER)
            dot,state=self.friendly_source_cards['mt5'];dot.configure(fg=AMBER);state.configure(text='Sin conexión',fg=AMBER)
            self._render_health={'complete':False,'connected':False,'errors':list(self._active_render_errors)}
            self._active_render_errors=None
            return
        markets=row.get('markets') or {}
        closed={symbol for symbol,market in markets.items() if isinstance(market,dict) and market.get('scheduled_closed')}
        page=getattr(self,'current_page_index',0)
        first_render=not getattr(self,'_visible_render_warmed',False)
        self._visible_render_warmed=True
        # Privacy is global: update financial labels even when their tab is hidden.
        # Hidden-pane lazy rendering must never retain unmasked amounts after a
        # privacy preference change (also required by the frozen UI self-check).
        privacy_now=bool(self.cfg['desktop'].get('privacy',True) and not self._account_revealed)
        privacy_previous=getattr(self,'_last_rendered_privacy',None)
        privacy_changed=privacy_previous is not None and privacy_previous!=privacy_now
        self._last_rendered_privacy=privacy_now
        self.render_section('Cuenta',self.render_live_header,row)
        if first_render or page==2:self.render_section('Órdenes',self.render_live_orders,row)
        if first_render or page in (3,4):self.render_section('Fuentes',self.render_source_cards,row)
        if first_render or page in (0,1):self.render_section('Gráficos',self.render_live_charts,row,closed)
        elif privacy_changed:self.render_section('Privacidad gráficos',self.render_dashboard_privacy,row)
        if first_render or page==3:self.render_section('Análisis',self.render_live_analysis,row)
        if first_render or page in (0,1,3):self.render_section('Decisiones',self.render_decisions,row,closed)
        if first_render or page==4:self.render_section('Contexto',self.render_live_context,row)
        if first_render or page in (0,1,2) or privacy_changed:self.render_section('Presupuesto',self.render_account_budget,row)
        if first_render or page==2 or privacy_changed:self.render_section('Seguridad',self.render_account_security,row)
        self.render_section('Avisos',self.maybe_notify,row)
        errors=list(self._active_render_errors)
        self._render_health={'complete':not errors,'connected':True,'generation':self._render_generation,
            'updated':time.monotonic(),'errors':errors}
        self._active_render_errors=None
        if errors:
            self.connection.configure(text=self.connection.cget('text')+' · No se pudo actualizar: '+', '.join(errors),fg=AMBER)

    def render_section(self,name,callback,*args):
        try:callback(*args)
        except Exception as exc:self.record_ui_error(name,exc)

    def render_account_security(self,row):
        if self.cfg['desktop'].get('privacy',True) and not self._account_revealed:
            self.account_safety.configure(text='Datos financieros ocultos. Pulsa el ojo del encabezado para revisar los importes reales.\n\nAKIRA comprueba riesgo por operación, riesgo conjunto, lote mínimo, margen, SL/TP y límites diarios antes del envío. La privacidad solo cambia la visualización.',fg=MUTED)
        else:self.account_safety.configure(text=security_text(row,self.cfg),fg=MUTED)

    def render_live_header(self,row):
        self.paused=bool(row.get('paused'))
        self.toggle.configure(text='REANUDAR GESTIÓN' if self.paused else 'PAUSAR GESTIÓN')
        a=row['account'];ccy=a.get('currency','')
        private=self.cfg['desktop'].get('privacy',True) and not self._account_revealed
        mask='••••••' if os.name=='nt' else '******'
        self.account_label.configure(text='Cuenta MT5: '+(str(a.get('login') or '') if not private else 'OCULTA')+' · '+('Libre '+number(a.get('margin_free'))+' '+ccy if not private else 'Importes ocultos por tu elección'))
        if hasattr(self,'privacy_button'):self.privacy_button.configure(text='MOSTRAR IMPORTES' if private else 'OCULTAR IMPORTES')
        gate=row.get('execution_gate') or {}
        operational=bool(gate.get('execution_allowed')) if gate else (row['mode']=='trade' and not row.get('paused') and not row.get('execution_block') and row.get('network_available',True))
        code=gate.get('code')
        mode={'OFFLINE':'SIN INTERNET · RECONECTANDO','TRADE_ENABLED':'OPERATIVA ACTIVA',
              'OBSERVE':'SOLO ANÁLISIS · NO ENVÍA ÓRDENES',
              'PAUSED':'GESTIÓN PAUSADA','BROKER_BLOCK':'MT5 · EJECUCIÓN BLOQUEADA',
              'PREVIEW':'VISTA PREVIA'}.get(code, 'OPERATIVA ACTIVA' if operational else 'GESTIÓN BLOQUEADA')
        self.connection.configure(text=f"{'VISTA PREVIA · ' if row.get('preview') else ''}{mode} · ciclo {row['cycle_ms']:.0f} ms · {'ESCRITURAS BLOQUEADAS' if row.get('execution_block') else 'MT5 conectado'}",fg=GREEN if operational else AMBER)
        if hasattr(self,'mode_button'):
            self.mode_button.configure(text='SOLO ANÁLISIS' if row['mode']=='trade' else 'ACTIVAR OPERATIVA',state='disabled' if row.get('preview') else 'normal')
        if gate and hasattr(self,'brain_status'):
            self._execution_gate_explanation=gate['reason']+' '+gate['next_action']
        if float(row.get('ui_age_seconds') or 0)>3:self.connection.configure(text=self.connection.cget('text')+' · Estado antiguo: no llega una revisión nueva del motor',fg=AMBER)
        self.metrics['balance'].configure(text=mask if private else number(a.get('balance'))+' '+ccy)
        self.metrics['equity'].configure(text=mask if private else number(a.get('equity'))+' '+ccy)
        self.metrics['floating'].configure(text=mask if private else number(a.get('floating'))+' '+ccy)
        self.metrics['daily'].configure(text=mask if private else 'HISTORIAL PENDIENTE' if a.get('daily_net') is None else number(a.get('daily_net'))+' '+ccy)
        self.metrics['risk'].configure(text=mask if private else number(row.get('reserved_risk'))+' / '+number(row.get('risk_cap')))
        self.metrics['cycle'].configure(text=number(row.get('cycle_ms'),0)+' ms')
        self._fit_metrics()
        self.metrics['daily'].configure(fg=GREEN if float(a.get('daily_net') or 0)>=0 else RED)
        self.metrics['floating'].configure(fg=GREEN if float(a.get('floating') or 0)>=0 else PINK)
        self.side_connection.configure(text='VISTA PREVIA' if row.get('preview') else 'MT5 · conectado',fg=AMBER if row.get('preview') else GREEN)
        if row.get('network_available') is False:self.side_connection.configure(text='SIN INTERNET · reconectando',fg=AMBER)

    def render_account_budget(self,row):
        a=row['account'];ccy=a.get('currency','')
        private=self.cfg['desktop'].get('privacy',True) and not self._account_revealed
        self.budget_value.configure(text=('••••••' if os.name=='nt' else '******') if private else number(row.get('reserved_risk'))+' '+ccy)
        cap=float(row.get('risk_cap') or 0);reserved=float(row.get('reserved_risk') or 0)
        self.budget_bar.configure(value=min(100,reserved/cap*100) if cap and not private else 0)
        ledger=row.get('portfolio_risk') or {}
        if ledger:
            from risk_reservations import ledger_text,reservation_reason
            color=AMBER if ledger['available_usd']<=0 else MUTED
            if hasattr(self,'portfolio_help'):self.portfolio_help.configure(text=ledger_text(ledger),fg=color)
            if hasattr(self,'pending_risk_help'):
                text=reservation_reason(ledger) if ledger['available_usd']<=0 else ledger_text(ledger,limit=0).split('\n')[0]
                self.pending_risk_help.configure(text=text,fg=color)
        if self.cfg['desktop'].get('privacy',True) and not self._account_revealed:
            mask='••••••' if os.name=='nt' else '******'
            self.budget_value.configure(text=mask);self.budget_bar.configure(value=0)
            self.portfolio_help.configure(text='Importes privados. Pulsa el ojo del encabezado para mostrar temporalmente presupuesto, reservas y límites.',fg=MUTED)
        if hasattr(self,'risk_override_help'):
            r=self.cfg.get('risk') or {};eq=float(a.get('equity') or 0);base=min(float(r.get('max_trade_money',0) or 0),eq*float(r.get('max_trade_pct',0) or 0)/100.0) if eq>0 else 0
            over=min(float(r.get('min_lot_structural_override_money_cap',0) or 0),eq*float(r.get('min_lot_structural_override_max_pct',0) or 0)/100.0) if eq>0 else 0
            active=bool(r.get('min_lot_structural_override_enabled',False));cap=max(base,over) if active else base
            self.risk_override_help.configure(text=f"Con patrimonio {number(eq)} {ccy}: cap normal ≈ {number(base)} {ccy}. {'Cobertura activa' if active else 'Cobertura apagada'} → cap por operación ≈ {number(cap)} {ccy}. Si una tesis XAU necesita más que esto, seguirá BLOQUEADA aunque el checkbox esté marcado.",fg=AMBER if active else MUTED)

    def render_decisions(self,row,closed):
        active={symbol:info for symbol,info in row.get('symbols',{}).items() if symbol not in closed}
        decisions=[(symbol,info.get('decision') or {}) for symbol,info in active.items()]
        concise='\n\n'.join(symbol+' · '+str((row.get('status') or {}).get(symbol,{}).get('state','Esperando'))+'\n'+str((row.get('status') or {}).get(symbol,{}).get('detail','')) for symbol in active)
        self.decision_summary.configure(text=concise or 'No hay mercados activos.',fg=MUTED)
        self.terminal_motor.configure(text=('VISTA PREVIA\n\n' if row.get('preview') else '')+'Revisión '+number(row.get('cycle_ms'),0)+' ms\n\n'+concise,fg=MUTED)

    def show_source_reason(self,event=None):
        selection=self.analysis_sources.selection()
        if selection:self.analysis_source_detail.configure(text=self._source_reasons.get(selection[0],''))

    def render_source_cards(self,row):
        research=row.get('research') or {};sources=research.get('sources') or {}
        from cyber_ui import source_presentation
        selected=self.analysis_sources.selection();rows=[]
        self._source_reasons={}
        for name,source in sorted(sources.items()):
            if not isinstance(source,dict):continue
            title,status,detail=source_presentation(name,source)
            age=source.get('age_seconds',source.get('age'))
            rows.append((name,(title,status,number(age,1)+' s' if age is not None else '—',detail),('fresh' if status=='DISPONIBLE' else 'wait',)))
            self._source_reasons[name]=title+' · '+status+'\n'+detail
        from ui_updates import sync_table
        sync_table(self.analysis_sources,rows)
        if selected and selected[0] in self._source_reasons:
            self.analysis_sources.selection_set(selected[0]);self.show_source_reason()
        def src_state(names):
            rows=[sources.get(n,{}) for n in names if sources.get(n)]
            if rows and all(x.get('enabled') is False for x in rows):return ('DESACTIVADO',MUTED)
            if any(x.get('fresh') and x.get('usable',True) for x in rows):return ('ACTIVO',GREEN)
            if any(x.get('inflight') for x in rows):return ('BUSCANDO',AMBER)
            if rows and all(x.get('error') for x in rows):return ('ERROR',RED)
            if rows and all(x.get('usable') is False for x in rows):return ('SIN DATOS',MUTED)
            return ('ESPERA',MUTED)
        if hasattr(self,'source_status'):
            self.source_status['mt5'].configure(text='ACTIVO',fg=GREEN)
            for key,names in (('web',('fed','news')),('youtube',('youtube',)),('coinglass',tuple(k for k in sources if k.startswith('coinglass:') or k.startswith('derivatives:'))),('investing',('news',))):
                textv,color=src_state(names);self.source_status[key].configure(text=textv,fg=color)
        if hasattr(self,'friendly_source_cards'):
            local=self.assistant.local_ai_status()
            groups={
                'mt5':('ACTIVO',GREEN),
                'web':src_state(('fed','news')),
                'venues':src_state(tuple(k for k in sources if k.startswith('venue:') or k.startswith('derivatives:'))),
                'macro':src_state(('macro:FRED',)),
                'global_news':src_state(tuple(k for k in sources if k.startswith('global_news:'))),
                'youtube':src_state(('youtube',)),
                'coinglass':src_state(tuple(k for k in sources if k.startswith('coinglass:') or k.startswith('derivatives:'))),
                'investing':src_state(('news',))}
            for key,(state_text,color) in groups.items():
                if key in self.friendly_source_cards:
                    dot,val=self.friendly_source_cards[key];dot.configure(fg=color);val.configure(text=state_text.title(),fg=color)
            if hasattr(self,'source_refresh_state') and any(isinstance(x,dict) and x.get('inflight') for x in sources.values()):
                self.source_refresh_state.configure(text='BUSCANDO...',fg=AMBER)
            elif hasattr(self,'source_refresh_state'):
                available=sum(1 for x in sources.values() if isinstance(x,dict) and x.get('fresh') and x.get('usable',True) and x.get('enabled') is not False)
                self.source_refresh_state.configure(text=f'{available} FUENTES VIGENTES' if available else 'SIN FUENTES VIGENTES',fg=GREEN if available else AMBER)

    def render_dashboard_privacy(self,row):
        a=row['account'];ccy=a.get('currency','')
        if self.cfg['desktop'].get('privacy',True) and not self._account_revealed:
            self.dashboard_stats.configure(text=f"CAPITAL PRIVADO   |   {len(row['orders'])} PENDIENTES / {len(row['positions'])} POSICIONES")
        else:self.dashboard_stats.configure(text=f"CAPITAL {number(a.get('equity'))} {ccy}   |   DÍA {number(a.get('daily_net'))}   |   FLOTANTE {number(a.get('floating'))}   |   {len(row['orders'])} PENDIENTES / {len(row['positions'])} POSICIONES")

    def render_live_charts(self,row,closed):
        self.render_dashboard_privacy(row)
        self.render_dashboard_activity(row)
        self.render_pending_overview(row)
        for symbol,widgets in self.charts.items():
            try:self.render_dashboard_chart(symbol,widgets,row,closed)
            except Exception as exc:self.record_ui_error('Gráfico '+symbol,exc)
        if hasattr(self,'dashboard_pending'):
            self.dashboard_pending.delete(*self.dashboard_pending.get_children())
            for symbol,info in row.get('symbols',{}).items():
                for p in (info.get('scenario_book') or info.get('pending_book') or [])[:4]:
                    if p.get('confirmed'):state='MT5 #'+str(p.get('ticket'))
                    elif p.get('sendable'):state='LISTA · esperando cupo/confirmación'
                    else:state=str(p.get('scenario_state') or 'BLOQUEADA')+' · '+str(p.get('block_reason') or '')[:80]
                    self.dashboard_pending.insert('','end',values=(symbol,'BUY' if p.get('side')==1 else 'SELL',p.get('kind'),number(p.get('entry'),3),number(p.get('sl'),3),number(p.get('tp'),3),number(p.get('quality_score'),0),number(p.get('activation_score'),0),state))
        for symbol,panel in self.panels.items():
            try:panel.render(row)
            except Exception as exc:self.record_ui_error('Panel '+symbol,exc)

    def render_live_orders(self,row):
        names={0:'BUY',1:'SELL',2:'BUY LIMIT',3:'SELL LIMIT',4:'BUY STOP',5:'SELL STOP'}
        from ui_updates import sync_table
        for tree,records in ((self.orders,row['orders']),(self.positions,row['positions'])):
            sync_table(tree,[(str(p['ticket']),(p['ticket'],p['symbol'],names.get(p['type'],p['type']),p['volume'],number(p['entry'],3),number(p['sl'],3),number(p['tp'],3),number(p.get('profit')),'Akira' if p.get('owned') else 'Manual / otro EA'),()) for p in records])

    def render_live_analysis(self,row):
        frames=[]
        for symbol,info in row.get('symbols',{}).items():
            for tf,f in info.get('frames',{}).items():frames.append((symbol+':'+tf,(symbol,tf,number(f.get('trend')),number(f.get('rsi')),number(f.get('atr')),number(f.get('ema9')),number(f.get('ema21')),number(f.get('ema50')),number(f.get('ema200')),number(f.get('adx')),number(f.get('macd')),number(f.get('vwap')),f.get('regime','')),()))
        from ui_updates import sync_table
        sync_table(self.frames,frames)
        if hasattr(self,'analysis_summary'):
            body='\n\n'.join(analysis_text(row,s) for s in row.get('symbols',{}))
            if replace_text(self.analysis_summary,body):
                for tag in ('section','bull','bear','closed'):self.analysis_summary.tag_remove(tag,'1.0','end')
                for n,line in enumerate(body.splitlines(),1):
                    tag='closed' if 'CERRADO' in line else 'bull' if 'ALCISTA' in line else 'bear' if 'BAJISTA' in line else 'section' if line and (line.isupper() or ' · BTCUSD' in line or ' · XAUUSD' in line) else None
                    if tag:self.analysis_summary.tag_add(tag,f'{n}.0',f'{n}.end')
        audit={'estado':row.get('status'),'uso_de_datos':row.get('analysis'),'evaluacion_de_zonas':row.get('audit'),'solicitudes_sin_confirmar':row.get('unconfirmed')}
        replace_text(self.audit,json.dumps(audit,ensure_ascii=False,indent=2,default=str))

    def render_live_context(self,row):
        ccy=(row.get('account') or {}).get('currency','')
        sources=(row.get('research') or {}).get('sources') or {}
        lines=[];brain=[];friendly=[]
        for symbol,evidence in row.get('analysis',{}).items():
            context=', '.join(evidence['context_sources']) or 'todavía sin contexto externo con peso'
            lines.append(symbol+' · marcos '+', '.join(evidence['timeframes'])+'\n  Contexto integrado: '+context)
            brain.append(symbol+'\n'+str(row['status'].get(symbol,{}).get('detail',''))+'\nFuentes: '+context)
            friendly.append(('ORO' if symbol.startswith('XAU') else 'BITCOIN')+'\n  Mercado técnico: listo' if evidence.get('technical_ready') else ('ORO' if symbol.startswith('XAU') else 'BITCOIN')+'\n  Mercado técnico: preparando')
            friendly[-1]+='\n  Contexto externo usado: '+context
        lines.append('\nFUENTES · edad desde última respuesta correcta')
        for name,s in sorted(row.get('research',{}).get('sources',{}).items()):
            age=number(s.get('age_seconds'),0)+' s' if s.get('age_seconds') is not None else 'sin datos'
            lines.append(name+': '+age+' · '+('vigente' if s.get('fresh') else 'sin peso')+(' · consultando' if s.get('inflight') else '')+'\n  '+str(s.get('error') or s.get('detail') or ''))
        lines.append('\nAPRENDIZAJE DE PENDIENTES · cierres propios completos y costes reales')
        for symbol,m in row.get('learning',{}).items():
            lines.append(f"{symbol}: {m['samples']} cierres · P/L medio {m['expectancy']:+.2f} {ccy} · "+(f"ganadoras históricas {m['win_rate']*100:.1f}%" if m['samples']>=20 else 'muestra insuficiente'))
        research=row.get('research') or {};lines.append('\nMEMORIA Y CONTEXTO\n'+json.dumps({k:research.get(k) for k in ('knowledge','research_state','daily_learning','previous_learning_memory')},ensure_ascii=False,indent=2,default=str))
        for video in research.get('videos',[])[:8]:lines.append('\nYouTube · '+str(video.get('title',''))+'\n'+str(video.get('url',''))+'\n'+str(video.get('summary',''))[:1600])
        if hasattr(self,'sources_summary'):
            inflight=[name for name,s in sources.items() if isinstance(s,dict) and s.get('inflight')]
            state=('Buscando ahora: '+', '.join(inflight[:5])) if inflight else 'Ronda externa en reposo; Akira usa lo último vigente y MT5 en tiempo real.'
            replace_text(self.sources_summary,state+'\n\n'+'\n\n'.join(friendly)+'\n\nCuando una fuente nueva termina, Akira vuelve a comparar el mapa; no espera a Internet para preparar los primeros niveles.')
        gate=row.get('execution_gate') or {}
        if gate:
            brain.insert(0,'MODO EFECTIVO · '+str(gate.get('code',''))+'\n'+str(gate.get('reason',''))+'\n'+str(gate.get('next_action','')))
        replace_text(self.sources,public_status('\n'.join(lines)));replace_text(self.brain_status,public_status('\n\n'.join(brain)))

    def render_dashboard_chart(self,s,widgets,row,closed):
        chart,title,state,tf_var=widgets
        info=row.get('symbols',{}).get(s,{});requested=tf_var.get();tf,bars=available_chart_frame(info,requested)
        if tf!=requested:tf_var.set(tf)
        chart_info=dict(info);chart_info['market_closed']=s in closed;chart_info['indicator']=self.cfg['charts']['indicator'];chart_info['engine_frame']=info.get('frames',{}).get(tf,{});chart_info['timeframe']=tf;chart_info['bars']=bars;chart.update_data(chart_info)
        # If the first render ran before the new dashboard's pane geometry
        # settled, ensure unchanged data still receives its initial drawing.
        if hasattr(chart,'winfo_height') and hasattr(chart,'find_all') and chart.winfo_height() >= 70 and not chart.find_all():
            chart.redraw()
        title.configure(text=s+'   '+number(info.get('bid'))+' / '+number(info.get('ask')))
        status=row['status'].get(s,{});state.configure(text=status.get('state','')+' · '+status.get('detail',''))
        runner=info.get('runner') or {}
        if runner:
            state.configure(text=status.get('state','')+' · '+status.get('detail','')+'\nRUNNER: '+str(runner.get('state',''))+' · '+str(runner.get('detail','')))
        decision=info.get('decision') or {}
        if decision:
            body=status.get('state','')+' · '+status.get('detail','')
            body+=f"\nTécnicas {decision.get('technical_candidates',0)} · enviables {decision.get('currently_sendable',0)} · intentos {decision.get('last_cycle_attempts',0)} · MT5 {decision.get('confirmed_pending_orders',0)}"
            if runner:body+='\nRunner: '+str(runner.get('state',''))+' · '+str(runner.get('detail',''))
            state.configure(text=body)
    def _apply_performance(self):
        self._performance=get_intervals(self.cfg)
        for avatar in self.avatars:
            if hasattr(avatar,'set_refresh_interval'):avatar.set_refresh_interval(self._performance['avatar_ms'])
        self.display_due=0.0;self._assistant_display_due=0.0

    def open_expression_gallery(self):
        from expression_gallery import open_expression_gallery
        return open_expression_gallery(self)

    def open_resource_panel(self):
        from resource_optimizer import config_limits,process_usage,PROFILES,profile_budget
        self.navigate(6);self.settings_notebook.select(self.settings_resources_tab)
        if getattr(self,'_resource_window',None) is not None:
            try:
                if self._resource_window.winfo_exists():
                    self._resource_window.destroy();self._resource_window=None;return
            except tk.TclError:pass
        # Embedded in AJUSTES: no second taskbar window, fixed size, or off-screen dialog.
        win=tk.Frame(self._resource_host,bg=BG,highlightthickness=1,highlightbackground=LINE)
        self._resource_window=win
        win.pack(fill='x',expand=True,pady=(5,12))
        head=tk.Frame(win,bg=PANEL,padx=17,pady=12);head.pack(fill='x')
        label(head,'CONTROL DE RECURSOS',CYAN,12,True,anchor='w',justify='left',wraplength=480).pack(side='left',fill='x',expand=True)
        button(head,'×',lambda:(win.destroy(),setattr(self,'_resource_window',None)),MUTED).pack(side='right')
        values=config_limits(self.cfg)
        shell=tk.Frame(win,bg=BG,padx=14,pady=9);shell.pack(fill='both',expand=True)
        label(shell,'PERFIL DE RENDIMIENTO',MUTED,9,True,anchor='w').pack(fill='x',pady=(4,4))
        mode=tk.StringVar(value=values['performance_profile'])
        ttk.Combobox(shell,textvariable=mode,values=tuple(PROFILES),state='readonly',style='Akira.TCombobox').pack(fill='x',ipady=3,pady=(0,5))
        effective=label(shell,'',CYAN,9,anchor='w',wraplength=389,justify='left')
        effective.pack(fill='x',pady=(0,12))
        effective.bind('<Configure>',lambda e:effective.configure(wraplength=max(220,e.width-10)))
        def preview_profile(*_):
            p=PROFILES.get(mode.get(),PROFILES['Equilibrado'])
            effective.configure(text=(f"Pantalla: {p['target_fps']} FPS objetivo · paneles cada {p['render_seconds']:.2f} s · "
                f"avisos IA cada {p['assistant_seconds']:.1f} s · animación {p['avatar_ms']} ms. "
                'El motor MT5 y sus límites de riesgo NO cambian.'))
        mode.trace_add('write',preview_profile);preview_profile()
        def scale(title,key,low,high,step,unit):
            row=tk.Frame(shell,bg=BG);row.pack(fill='x',pady=(2,0))
            label(row,title,TEXT,9,True,anchor='w',justify='left',wraplength=500).pack(side='left',fill='x',expand=True)
            val=tk.IntVar(value=values[key])
            label(row,textvariable=val,color=CYAN,size=10,bold=True).pack(side='right')
            slider=tk.Scale(shell,from_=low,to=high,resolution=step,orient='horizontal',variable=val,
                bg=BG,fg=CYAN,troughcolor=CARD,activebackground=CYAN,highlightthickness=0,
                showvalue=False,bd=0)
            slider.pack(fill='x',pady=(0,9))
            return val
        memory=scale('PRESUPUESTO DE MEMORIA PARA IA (MB)','memory_budget_mb',512,16384,256,'MB')
        context=scale('CONTEXTO DEL MODELO (TOKENS)','model_context_tokens',1024,16384,1024,'tokens')
        keep=scale('MANTENER MODELO CARGADO (SEGUNDOS)','model_keep_alive_seconds',0,600,15,'s')
        gpu=tk.BooleanVar(value=values['model_use_gpu'])
        tk.Checkbutton(shell,text='Permitir GPU para el modelo local',variable=gpu,bg=BG,fg=TEXT,selectcolor=PANEL,
                       activebackground=BG,activeforeground=CYAN,font=(FONT,10)).pack(anchor='w',pady=2)
        # Selecting a preset must change actual inference settings as well as
        # the visual refresh interval. Sliders remain editable afterwards.
        def update_preset(*_):
            preset=profile_budget(mode.get())
            memory.set(preset['memory_budget_mb'])
            context.set(preset['model_context_tokens'])
            keep.set(preset['model_keep_alive_seconds'])
            gpu.set(preset['model_use_gpu'])
        mode.trace_add('write',update_preset)
        label(shell,'PERFIL: controles visibles y medibles (no una cuota de RAM garantizada). '
            'La memoria indicada es un presupuesto de contexto, no un límite duro de RAM total. '
            'Desactivar GPU traslada inferencia al CPU y puede hacerla más lenta. '
            'Las órdenes y protecciones de MT5 no se ralentizan.',MUTED,9,wraplength=386,justify='left').pack(fill='x',pady=(8,9))
        status=label(shell,'Midiendo uso...',CYAN,9,anchor='w',justify='left',wraplength=600);status.pack(fill='x',pady=4)
        def sample():
            try:
                if not win.winfo_exists():return
                if not getattr(win,'_usage_inflight',False):
                    win._usage_inflight=True
                    def work():
                        try:data=process_usage()
                        except Exception:data={}
                        self.replies.put({'resource_sample':{'window':win,'label':status,'data':data}})
                    threading.Thread(target=work,name='AkiraResourceSample',daemon=True).start()
                win._usage_after=win.after(4000,sample)
            except tk.TclError:pass
        def stop_sampling(event):
            if event.widget is not win:return
            job=getattr(win,'_usage_after',None)
            if job is not None:
                try:win.after_cancel(job)
                except tk.TclError:pass
            win._usage_after=None
        win.bind('<Destroy>',stop_sampling,add='+')
        sample()
        def reveal():
            parent=self._resource_host
            while parent is not None:
                canvas=getattr(parent,'_scroll_canvas',None)
                if canvas is not None:
                    canvas._sync_content();self.root.update_idletasks()
                    offset=self._resource_host.winfo_rooty()-canvas._content.winfo_rooty()
                    height=max(1,canvas._content.winfo_reqheight())
                    canvas.yview_moveto(max(0,offset/height));break
                parent=getattr(parent,'master',None)
        self.root.after_idle(reveal)
        def apply():
            try:
                cfg=copy.deepcopy(self.cfg)
                cfg['desktop'].update(performance_profile=mode.get(),memory_budget_mb=memory.get(),
                    model_context_tokens=context.get(),model_keep_alive_seconds=keep.get(),model_use_gpu=gpu.get())
                # The visible idle slider must also control the managed llama.cpp process.
                cfg['assistant']['local_runtime_idle_seconds']=keep.get()
                from settings_effects import validate_form
                saved=validate_form(cfg);save_config(saved,self.folder/'akira_config.json');self.cfg.update(saved)
                self.assistant._managed_model.settings['local_runtime_idle_seconds']=keep.get()
                self._apply_performance()
                if 'desktop.performance_profile' in self.setting_vars:self.setting_vars['desktop.performance_profile'].set(mode.get())
                self.desktop_toast('Optimizador','Límites aplicados al asistente y a la interfaz. Las operaciones MT5 mantienen sus controles.')
                win.destroy()
            except Exception as exc:status.configure(text='No se pudo aplicar: '+str(exc),fg=RED)
        button(shell,'APLICAR LIMITES',apply,GREEN).pack(fill='x',pady=(7,3))

    def save_settings(self):
        if hasattr(self,'studio_controls'):
            self._studio_avatar=self.studio_controls.staged_avatar()
        saved=self.apply_settings_form()
        # The next UI cycle uses the saved mode. Trading, risk and MT5 remain live.
        if saved is not False:
            self._apply_performance()
            name=self.cfg['studio']['brand_name']
            self.root.title(name+' · 16.3.5 · R8 Studio Rev4')
            self.brand_title.configure(text=name)
            self._activate_user_avatar()
    def _activate_user_avatar(self):
        from akira_studio import UserCatalog
        from akira_expressions import get_catalog
        from akira_live2d import _root as _assets
        item=self.cfg['studio']['avatar']
        catalog=UserCatalog(get_catalog(_assets()),item) if item.get('active') and item.get('entries') else get_catalog(_assets())
        self.root._akira_user_catalog=catalog
        director=getattr(self,'avatar_director',None)
        if director:
            director.catalog=catalog
            for avatar in self.avatars:
                avatar.catalog=catalog
                avatar._photos.clear();avatar._state_images.clear();avatar._visual_key=None
            director.publish('idle','Nuevo avatar',force=True)

    def open_folder(self,name):
        path=self.folder/name;path.mkdir(exist_ok=True)
        if os.name=='nt':os.startfile(path)
    def prepare_local(self):
        result=self.assistant.retry_local_preparation()
        self.desktop_toast('AKIRA · reparación', 'Preparación solicitada. VER MOTIVO Y REGISTRO muestra el resultado y el error.' if result.get('accepted') else public_status(result.get('error') or 'No se pudo solicitar la reparación.'), severity='info' if result.get('accepted') else 'warning')
        self._assistant_display_due=0.0
        self.refresh_assistant_status()
    def search_memory(self):
        query=self.source_query.get()
        def work():
            try:rows=self.assistant.memory.search(query,limit=12);self.replies.put({'memory':json.dumps(rows,ensure_ascii=False,indent=2,default=str)})
            except Exception as exc:self.replies.put({'memory':str(exc)})
        threading.Thread(target=work,daemon=True).start()
    def export_snapshot(self):
        snapshot=copy.deepcopy(self.view)
        def work():
            if self.bridge.connected:
                result=self.bridge.request({'action':'export_diagnostic'})
                if result.get('ok') and result.get('snapshot'):
                    diagnostic=result['snapshot'];diagnostic['runtime']=snapshot.get('runtime',{})
                    snapshot.clear();snapshot.update(diagnostic)
                else:snapshot['diagnostic_export_error']=result.get('error') or result.get('note') or 'El actor no respondió; última vista disponible'
            path=self.assistant._create_local_file({'filename':'estado_akira_'+time.strftime('%Y%m%d_%H%M%S')+'.json','content':json.dumps(snapshot,ensure_ascii=False,indent=2,default=str)})
            self.replies.put({'answer':'Estado exportado: '+path['path'],'command':False})
        threading.Thread(target=work,daemon=True).start()

    def open_report_dialog(self,preferred=None):
        if self.report_window is not None:
            try:
                if self.report_window.winfo_exists():
                    if preferred:self.report_format.set(preferred)
                    self.report_window.lift();return
            except tk.TclError:pass
        win=tk.Toplevel(self.root);self.report_window=win;self.report_generation+=1;self.report_busy=False
        win.protocol('WM_DELETE_WINDOW',self.close_report_dialog)
        win.title('AKIRA · Informe operativo');win.configure(bg=PANEL)
        width,height,_,_=fitted_geometry(960,720,win.winfo_screenwidth(),win.winfo_screenheight())
        win.geometry(f'{width}x{height}');win.minsize(min(760,width),min(580,height))
        label(win,'INFORME OPERATIVO',CYAN,18,True,anchor='w').pack(fill='x',padx=18,pady=(14,5))
        label(win,'Estado de BTC y oro, valoración de pendientes, entradas de runners y gestión de cierres.',MUTED,10,anchor='w',wraplength=900).pack(fill='x',padx=18)
        controls=tk.Frame(win,bg=PANEL);controls.pack(fill='x',padx=18,pady=10)
        label(controls,'Formato:').pack(side='left');self.report_format=tk.StringVar(value=preferred or 'PDF')
        ttk.Combobox(controls,textvariable=self.report_format,values=('PDF','Excel'),state='readonly',width=9,style='Akira.TCombobox').pack(side='left',padx=(6,16))
        label(controls,'Período:').pack(side='left');self.report_period=tk.StringVar(value='Últimas 24 horas')
        ttk.Combobox(controls,textvariable=self.report_period,values=('Últimas 24 horas','Últimos 7 días','Solo estado actual'),state='readonly',width=23,style='Akira.TCombobox').pack(side='left',padx=6)
        self.report_load_button=button(controls,'ACTUALIZAR INFORME',self.request_report,BLUE);self.report_load_button.pack(side='right')
        self.report_status=label(win,'Preparando lectura del motor...',AMBER,10,anchor='w',wraplength=900);self.report_status.pack(fill='x',padx=18,pady=3)
        frame=tk.Frame(win,bg=CARD);frame.pack(fill='both',expand=True,padx=18,pady=8)
        self.report_preview=text_box(frame,20);self.report_preview.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=self.report_preview.yview);scroll.pack(side='right',fill='y');self.report_preview.configure(yscrollcommand=scroll.set)
        bottom=tk.Frame(win,bg=PANEL);bottom.pack(side='bottom',before=frame,fill='x',padx=18,pady=(0,14))
        self.report_support=tk.BooleanVar(value=False)
        label(bottom,'Elige PDF o Excel. La descarga continúa aunque cambies de pestaña.',MUTED,9,anchor='w').pack(side='left')
        self.report_save_button=button(bottom,'DESCARGAR INFORME',self.save_report,AMBER);self.report_save_button.pack(side='right')
        self._report_download=None
        self.report_model=None;self.request_report()

    def close_report_dialog(self):
        # A chosen download owns its worker and destination independently of Tk.
        # Closing the window while reading cancels only its UI queue, never MT5.
        if self.report_window is not None:
            self.report_window.destroy();self.report_window=None
        self.report_generation+=1;self.report_busy=False;self._report_download=None

    def request_report(self):
        if self.report_busy:return
        self.report_busy=True;generation=self.report_generation
        self.report_load_button.configure(state='disabled')
        self.report_status.configure(text='Leyendo el último ciclo y el historial disponible...',fg=AMBER)
        fallback=copy.deepcopy(self.view);hours=(getattr(self,'_report_download',None) or {}).get('hours',{'Últimas 24 horas':24,'Últimos 7 días':168,'Solo estado actual':0}[self.report_period.get()])
        def work():
            try:
                result=self.bridge.request({'action':'export_report_snapshot'}) if self.bridge.connected else {'ok':False}
                snapshot=result.get('snapshot') if result.get('ok') else fallback
                if not snapshot or not (snapshot.get('symbols') or snapshot.get('account')):
                    raise RuntimeError('Todavía no hay datos del motor. Espera a que MT5 conecte y pulsa ACTUALIZAR INFORME.')
                snapshot=copy.deepcopy(snapshot)
                snapshot.setdefault('as_of_utc',snapshot.get('updated') or time.time())
                if not result.get('ok'):
                    snapshot['report_capture_note']='Última captura disponible; el historial de cierres puede estar incompleto. '+str(result.get('error') or '')
                snapshot['runtime']=fallback.get('runtime',{})
                events,truncated=read_recent_events(self.folder/'logs',hours,float(snapshot['as_of_utc']))
                if events:
                    combined=list(snapshot.get('operational_events') or [])+events
                    snapshot['operational_events']=list({(r.get('utc'),r.get('symbol'),r.get('operation')):r for r in combined}.values())
                snapshot['event_log_truncated']=truncated
                from quality_study import QualityStudy
                snapshot['quality_study']={**(snapshot.get('quality_study') or {}),**QualityStudy(self.folder).summary()}
                model=build_report(snapshot,hours)
                self.replies.put({'report_ready':model,'report_generation':generation})
            except Exception as exc:self.replies.put({'report_error':str(exc),'report_generation':generation})
        threading.Thread(target=work,daemon=True,name='AkiraReportReader').start()

    def save_report(self):
        if getattr(self,'_report_download',None):
            self.report_status.configure(text='La descarga ya está en curso. Te avisaré cuando el archivo esté listo.',fg=AMBER);return
        selected={'Últimas 24 horas':24,'Últimos 7 días':168,'Solo estado actual':0}[self.report_period.get()]
        format='pdf' if self.report_format.get()=='PDF' else 'xlsx'
        folder=self.folder/'exports';folder.mkdir(exist_ok=True)
        path=filedialog.asksaveasfilename(parent=self.report_window,title='Guardar informe de Akira',initialdir=str(folder),
            initialfile='Informe_Akira_'+time.strftime('%Y%m%d_%H%M%S')+'.'+format,defaultextension='.'+format,
            filetypes=[('PDF','*.pdf')] if format=='pdf' else [('Excel','*.xlsx')])
        if not path:return
        self._report_download={'path':path,'format':format,'hours':selected,'generation':self.report_generation}
        self.report_save_button.configure(state='disabled')
        if self.report_busy:
            self.report_status.configure(text='Destino elegido. Descargaré el informe al terminar de preparar los datos.',fg=AMBER);return
        if self.report_model is None or selected!=self.report_model['hours']:
            self.request_report();return
        self._perform_report_download()

    def _perform_report_download(self):
        request=getattr(self,'_report_download',None)
        if not request or self.report_model is None:return
        if self.report_model['hours']!=request['hours']:
            self.request_report();return
        path=request['path'];format=request['format']
        self.report_busy=True;self.report_save_button.configure(state='disabled');self.report_load_button.configure(state='disabled')
        self.report_status.configure(text='Descargando '+('PDF' if format=='pdf' else 'Excel')+'... El motor continúa operando.',fg=AMBER)
        model=copy.deepcopy(self.report_model);generation=self.report_generation
        def work():
            try:self.replies.put({'report_saved':export_report(model,path,format,False),'report_generation':generation})
            except Exception as exc:self.replies.put({'report_error':str(exc),'report_generation':generation})
        threading.Thread(target=work,daemon=True,name='AkiraReportExporter').start()

    def handle_report_reply(self,reply):
        if reply.get('report_generation')!=self.report_generation:
            return
        self.report_busy=False
        try:
            if self.report_window is None or not self.report_window.winfo_exists():return
            self.report_load_button.configure(state='normal')
            if 'report_ready' in reply:
                self.report_model=reply['report_ready'];replace_text(self.report_preview,report_text(self.report_model))
                self.report_save_button.configure(state='normal')
                self.report_status.configure(text='Informe listo · captura '+self.report_model['local_time']+' Guatemala · pulsa DESCARGAR INFORME.',fg=GREEN)
                if getattr(self,'_report_download',None):self._perform_report_download()
            elif 'report_error' in reply:
                self._report_download=None
                self.report_status.configure(text='No se pudo generar el informe: '+reply['report_error'],fg=RED)
                self.report_save_button.configure(state='normal')
                messagebox.showerror('Informe de AKIRA',reply['report_error'],parent=self.report_window)
            else:
                self._report_download=None
                saved=reply['report_saved'];self.report_save_button.configure(state='normal')
                self.report_status.configure(text='Guardado: '+saved['path'],fg=GREEN)
                text='Informe guardado en:\n'+saved['path']
                if saved.get('diagnostic_path'):text+='\n\nDatos para soporte:\n'+saved['diagnostic_path']
                messagebox.showinfo('Informe de Akira',text,parent=self.report_window)
        except tk.TclError:pass
    def close(self):
        ambient=getattr(self,'_ambient_wallpaper',None)
        if ambient is not None:ambient.stop()
        studio=getattr(self,'studio_controls',None)
        if studio is not None and studio._preview is not None:studio._preview.stop()
        if hasattr(self,'network_monitor'):self.network_monitor.close()
        self.persist_window_size()
        self.end_call();self.cancel_voice_download();self.knowledge_worker.close();self.layout.save();self.stop.set();self.bridge.connected=False;self.bridge.starting=False
        self.assistant.cancel_current_reply()
        # Inno Setup cannot replace/remove bundled DLLs held by a running model.
        # Never terminate external Ollama or user-owned llama-server processes.
        try:self.assistant._managed_model.shutdown()
        except (AttributeError,OSError,RuntimeError):pass
        try:
            # Cancel the Tcl timer; each child still owns its registered Python
            # callback and will delete it once during normal widget destruction.
            for callback in self.root.tk.call('after','info'):self.root.tk.call('after','cancel',callback)
        except (tk.TclError,AttributeError):pass
        self.root.destroy()

def main(preview=False):
    from windows_identity import application_root,set_identity
    from settings import ensure_user_config
    folder=application_root()
    # A fresh portable build has no user config until its first launch.
    ensure_user_config(folder)
    from akira_studio import activate_style
    import desktop_services, strategy_directory
    config=load_config(folder/'akira_config.json')
    activate_style(config['studio'],(sys.modules[__name__],desktop_services,strategy_directory))
    set_identity();root=tk.Tk()
    percent=config['studio'].get('font_scale',100)
    if int(percent)!=100:
        try:root.tk.call('tk','scaling',float(root.tk.call('tk','scaling'))*int(percent)/100)
        except tk.TclError:pass
    Desktop(root,folder,preview);root.mainloop()
