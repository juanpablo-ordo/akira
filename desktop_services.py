"""User-facing services, isolated from the MT5 actor and conversation ownership."""
import copy,json,threading,time,tkinter as tk,webbrowser
from tkinter import ttk
from datetime import datetime
from cyber_ui import BG,PANEL,CARD,CYAN,BLUE,GREEN,RED,AMBER,MUTED,TEXT,FONT,label,button,neon_card,text_box
from desktop_layout import scroll_frame,fitted_geometry,bind_direct_scroll_subtree
from settings import save_config
from settings_effects import changes,validate_form,change_message
from notification_center import NotificationCenter,safe_text
from knowledge_update import KnowledgeUpdater

class DesktopServices:
    def build_source_access(self,parent,card):
        from akira_secrets import get_secret
        panel=card(parent,'ACCESO A FUENTES',CYAN)
        label(panel,'CoinGlass es opcional. YouTube puede solicitar una sesión aunque la búsqueda no requiera clave.',MUTED,9,anchor='w',justify='left',wraplength=620).pack(fill='x',pady=5)
        self.source_key_entries={};self.source_key_labels={}
        for key,title in (('COINGLASS_API_KEY','Clave CoinGlass'),('YOUTUBE_API_KEY','Clave YouTube Data API (opcional)')):
            title_widget=label(panel,title+' · '+('guardada' if get_secret(key) else 'sin configurar'),TEXT,10,True,anchor='w')
            title_widget.pack(fill='x',pady=(9,3));self.source_key_labels[key]=(title_widget,title)
            entry=tk.Entry(panel,bg=CARD,fg=TEXT,insertbackground=CYAN,show='•',font=(FONT,11))
            entry.pack(fill='x',ipady=5);self.source_key_entries[key]=entry
        label(panel,'Deja un campo vacío para conservar la clave guardada. La sesión se importa desde un archivo cookies.txt en formato Netscape elegido por ti.',MUTED,9,anchor='w',justify='left',wraplength=620).pack(fill='x',pady=8)
        self.source_save_button=button(panel,'GUARDAR CLAVES',self.save_source_access,GREEN);self.source_save_button.pack(fill='x',pady=3)
        button(panel,'IMPORTAR SESIÓN YOUTUBE',self.import_youtube_session,CYAN).pack(fill='x',pady=3)
        button(panel,'COMPROBAR FUENTES',self.check_source_access,BLUE).pack(fill='x',pady=3)
        self.source_access_status=label(panel,'Las claves se protegen con tu usuario de Windows. No se leen perfiles de navegadores.',MUTED,9,anchor='w',justify='left',wraplength=620)
        self.source_access_status.pack(fill='x',pady=6)
        panel.bind('<Configure>',lambda e:self.source_access_status.configure(wraplength=max(180,e.width-20)),add='+')

    def save_source_access(self):
        from akira_secrets import save_secrets
        values={k:entry.get().strip() for k,entry in self.source_key_entries.items() if entry.get().strip()}
        try:
            if values:save_secrets(values)
            for entry in self.source_key_entries.values():entry.delete(0,'end')
            from akira_secrets import get_secret
            for key,(widget,title) in self.source_key_labels.items():widget.configure(text=title+' · '+('guardada' if get_secret(key) else 'sin configurar'))
            self.source_access_status.configure(text='Claves guardadas. Los campos vacíos conservan las anteriores.',fg=GREEN)
            self.refresh_configured_sources()
        except Exception as error:self.source_access_status.configure(text='No se pudieron guardar: '+safe_text(error),fg=RED)

    def refresh_configured_sources(self):
        self.assistant._research_cache.clear()
        with self.assistant._source_cache_lock:self.assistant._source_cache.clear()
        from providers import _YT_CACHE,_YT_LOCK,_CG_AUTH_CACHE,_CG_AUTH_LOCK
        with _YT_LOCK:_YT_CACHE.clear()
        with _CG_AUTH_LOCK:_CG_AUTH_CACHE.update(key='',when=0,ok=None,error='')
        if not self.preview:
            threading.Thread(target=lambda:self.bridge.request({'action':'refresh_sources'}),daemon=True,name='AkiraRefreshSources').start()

    def import_youtube_session(self):
        from tkinter import filedialog
        path=filedialog.askopenfilename(parent=self.root,title='Importar sesión de YouTube',filetypes=[('Cookies Netscape','*.txt'),('Todos','*.*')])
        if not path:return
        try:
            from youtube_support import import_session
            import_session(path);self.refresh_configured_sources()
            self.source_access_status.configure(text='Sesión YouTube importada. Pulsa COMPROBAR FUENTES; la sesión puede caducar.',fg=GREEN)
        except Exception as error:self.source_access_status.configure(text='Sesión no importada: '+safe_text(error),fg=RED)

    def check_source_access(self):
        self.source_access_status.configure(text='Comprobando en segundo plano…',fg=AMBER)
        def work():
            from providers import coinglass_auth_probe,youtube_search
            from youtube_support import explained
            lines=[]
            try:
                cg=coinglass_auth_probe(force=True)
                lines.append('CoinGlass: '+('conexión confirmada' if cg.get('ok') else str(cg.get('error') or 'clave opcional sin configurar')))
            except Exception as error:lines.append('CoinGlass: '+safe_text(error))
            try:lines.append('YouTube: '+str(len(youtube_search('Bitcoin technical analysis',cache_seconds=0)))+' resultados de búsqueda; esto no verifica subtítulos.')
            except Exception as error:lines.append(str(explained(error)))
            self.replies.put({'source_access_result':'\n'.join(lines)})
        threading.Thread(target=work,daemon=True,name='AkiraSourceCheck').start()

    def init_services(self):
        self.notice_center=NotificationCenter(self.folder);self.notice_window=None;self._settings_job=0;self._cloud_job=0;self._account_revealed=False
        self._closure_notifications_seen=self.notice_center.event_keys('CLOSE:')
        self.knowledge_worker=KnowledgeUpdater(self.cfg,self.folder,lambda row:self.replies.put({'knowledge_event':row}))
        if not self.preview:
            # Noncritical remote reading should not compete with MT5 and Tk
            # during the initial desktop launch. Manual refresh remains instant.
            self.knowledge_worker.start(initial_delay_seconds=45)
        if not self.preview:
            def protect():
                try:
                    from akira_secrets import protect_existing
                    protect_existing()
                except Exception:self.replies.put({'service_error':'No se pudo proteger la clave guardada con Windows. No se reemplazó el archivo.'})
            threading.Thread(target=protect,daemon=True,name='AkiraCredentialProtection').start()

    def service_dialog(self,title,width=760,height=570):
        from windows_identity import apply_window_icon,apply_dark_titlebar
        win=tk.Toplevel(self.root);win.title('AKIRA · '+title);win.configure(bg=BG);apply_window_icon(win,self.folder)
        win.after(120,lambda:apply_dark_titlebar(win))
        w,h,_,_=fitted_geometry(width,height,win.winfo_screenwidth(),win.winfo_screenheight())
        w=min(width,w);h=min(height,h);win.geometry(f'{w}x{h}');win.minsize(min(450,w),min(340,h))
        label(win,title.upper(),CYAN,17,True,anchor='w').pack(fill='x',padx=18,pady=(16,8))
        return win

    def show_message(self,title,body,error=False):
        self.desktop_toast(title,body,severity='error' if error else 'info')
        self.map_result_label.configure(text=safe_text(body).split('\n')[0][:240],fg=RED if error else GREEN)

    def open_uninstaller(self):
        try:
            from application_management import launch_uninstaller
            launch_uninstaller(self.folder)
            self.show_message('Desinstalar AKIRA','Se abrió el desinstalador de Windows. Puedes elegir conservar los datos de AKIRA.')
            # Close AKIRA after launching its native independent uninstaller, so
            # the application and managed llama-server do not lock installed DLLs.
            try:self.root.after(450,self.close)
            except (AttributeError,tk.TclError):pass
        except Exception as exc:
            self.show_message('Desinstalador no abierto',str(exc),True)

    def persist_window_size(self):
        try:
            if self.root.state()!='normal':return
            w,h=self.root.winfo_width(),self.root.winfo_height()
            if w<600 or h<600:return
            candidate=copy.deepcopy(self.cfg);candidate['desktop'].update(width=w,height=h)
            if changes(self.cfg,candidate):self.cfg.update(save_config(candidate,self.folder/'akira_config.json'))
        except (OSError,ValueError,tk.TclError):pass

    def restore_preferences(self):
        from settings import DEFAULT
        from cyber_ui import confirm_dialog
        if not confirm_dialog(self.root,'Restablecer preferencias','Se restablecen interfaz, gráficos y actualización del conocimiento. Los límites de riesgo, órdenes, voz, claves, chats y memoria se conservan.'):return
        for path,var in self.setting_vars.items():
            if path.split('.')[0] not in ('desktop','knowledge','charts'):continue
            from settings_effects import value_at
            try:value=value_at(DEFAULT,path)
            except KeyError:continue
            var.set(value if self.setting_types.get(path)=='bool' else str(value))
        self.apply_settings_form()

    def open_notifications(self):
        if self.notice_window and self.notice_window.winfo_exists():self.notice_window.lift();return
        win=self.service_dialog('Centro de notificaciones',850,650);self.notice_window=win
        search=tk.StringVar();entry=tk.Entry(win,textvariable=search,font=(FONT,11));entry.pack(fill='x',padx=18,ipady=8,pady=6)
        shell,body=scroll_frame(win,BG);shell.pack(fill='both',expand=True,padx=15,pady=10)
        win._scroll_canvas=shell._scroll_canvas  # rueda en cualquier parte del diálogo
        page_size=25
        page=tk.IntVar(value=page_size)
        def refresh(event=None):
            for child in body.winfo_children():child.destroy()
            rows=self.notice_center.list(search.get(),limit=page.get()+1);self.notice_center.mark_read();self.update_notice_badge()
            more=len(rows)>page.get();rows=rows[:page.get()]
            if not rows:label(body,'No hay avisos que coincidan.',MUTED,11).pack(pady=20)
            for row in rows:
                color=RED if row['severity']=='error' else AMBER if row['severity']=='warning' else CYAN
                outer,card=neon_card(body,datetime.fromtimestamp(row['at']).strftime('%d/%m %H:%M')+' · '+row['title'],color);outer.pack(fill='x',pady=5)
                text=label(card,row['body'],TEXT,10,anchor='w',justify='left',wraplength=650);text.pack(fill='x')
                card.bind('<Configure>',lambda e,w=text:w.configure(wraplength=max(200,e.width-35)))
            if more:button(body,'CARGAR 25 MÁS',lambda:(page.set(page.get()+page_size),refresh()),CYAN).pack(fill='x',pady=10)
            # Reattach after every refresh because every notice card is replaced.
            bind_direct_scroll_subtree(body, shell._scroll_canvas)
            shell._scroll_canvas._schedule_sync()
        def search_changed(event=None):
            page.set(page_size)
            if getattr(win,'_akira_filter_timer',None):win.after_cancel(win._akira_filter_timer)
            win._akira_filter_timer=win.after(260,refresh)
        entry.bind('<KeyRelease>',search_changed);refresh()
        button(win,'ACTUALIZAR',refresh,BLUE).pack(anchor='e',padx=18,pady=(0,12))

    def update_notice_badge(self):
        if hasattr(self,'notice_button'):self.notice_button.configure(text='AVISOS '+str(self.notice_center.unread()))

    def toggle_account_privacy(self):
        private=self.cfg['desktop'].get('privacy',False) and not self._account_revealed
        cfg=copy.deepcopy(self.cfg);cfg['desktop']['privacy']=not private;cfg['desktop']['visibility_preference_saved']=True
        try:self.cfg.update(save_config(cfg,self.folder/'akira_config.json'))
        except Exception as exc:self.show_message('Visibilidad de importes','No se pudo guardar tu elección: '+str(exc),error=True);return
        self._account_revealed=False
        if self.view:self.render(self.view)

    def hide_account(self):
        cfg=copy.deepcopy(self.cfg);cfg['desktop']['privacy']=True;cfg['desktop']['visibility_preference_saved']=True
        self.cfg.update(save_config(cfg,self.folder/'akira_config.json'))
        self._account_revealed=False
        if self.view:self.render(self.view)

    def apply_settings_form(self):
        try:
            candidate=copy.deepcopy(self.cfg)
            for path,var in self.setting_vars.items():
                kind=self.setting_types.get(path,'str');raw=var.get()
                value=bool(raw) if kind=='bool' else int(str(raw)) if kind=='int' else float(str(raw).replace(',','.')) if kind=='float' else str(raw).strip()
                if path=='knowledge.mode':value={'Automática':'automatic','Bajo solicitud':'request'}.get(value,value)
                cursor=candidate;parts=path.split('.')
                for key in parts[:-1]:cursor=cursor[key]
                cursor[parts[-1]]=value
            # The profile selector in Ajustes is a real preset, not a cosmetic
            # label: it applies the same soft model budgets as the GX-like panel.
            if candidate['desktop'].get('performance_profile') != self.cfg['desktop'].get('performance_profile'):
                from resource_optimizer import profile_budget
                candidate['desktop'].update(profile_budget(candidate['desktop']['performance_profile']))
            saved=validate_form(candidate);rows=changes(self.cfg,saved)
            if not rows:self.show_message('Ajustes','No había cambios pendientes.');return
            save_config(saved,self.folder/'akira_config.json');self.cfg.update(saved)
            paths=[r['path'] for r in rows];self._settings_job+=1;job=self._settings_job
            revision=max(time.time_ns(),getattr(self,'_settings_revision',0)+1);self._settings_revision=revision
            if any(p in ('desktop.width','desktop.height') for p in paths):
                w,h,_,_=fitted_geometry(saved['desktop']['width'],saved['desktop']['height'],self.root.winfo_screenwidth(),self.root.winfo_screenheight())
                if self.root.state()=='zoomed':self.root.state('normal')
                self.root.resizable(True,True);self.root.geometry(f'{w}x{h}')
            if any(p.startswith('knowledge.') for p in paths):self.knowledge_worker.next_due=0;self.knowledge_worker.wake.set()
            if any(p.startswith('charts.') for p in paths):
                for chart in self.charts.values():chart._indicator_signature=None;chart.redraw()
            self.use_cloud.set(bool(saved['assistant']['cloud']))
            if 'assistant.cloud' in paths:self.check_cloud() if self.use_cloud.get() else self.cloud_status.configure(text='OpenAI desactivado',fg=MUTED)
            self.map_result_label.configure(text='Aplicando: '+', '.join(paths),fg=AMBER)
            def work():
                reply=self.bridge.request({'action':'apply_settings','config':saved,'changed_paths':paths,'settings_revision':revision})
                self.replies.put({'settings_result':reply,'settings_rows':rows,'settings_job':job})
            threading.Thread(target=work,name='AkiraApplySettings',daemon=True).start()
        except Exception as exc:self.show_message('Ajustes no guardados',safe_text(exc),True)

    def open_knowledge(self):
        win=self.service_dialog('Conocimiento actualizado',820,630)
        label(win,'Fuentes globales indexadas con fecha. La actualización consulta contenido; no cambia el código, los modelos ni el riesgo.',MUTED,10,anchor='w',wraplength=760,justify='left').pack(fill='x',padx=18,pady=8)
        box=text_box(win,12);box.pack(fill='both',expand=True,padx=18,pady=8)
        def render():
            if not win.winfo_exists():return
            state=self.knowledge_worker.read();rows=state['sources']
            text=state['state']+'\nModo: '+self.cfg['knowledge']['mode']+'\n\n'
            from reference_library import CATALOG
            if not rows:rows=[{'name':n,'url':u,'state':'PENDIENTE DE CONSULTA'} for n,u,_ in CATALOG]
            for row in rows:text+=row['name']+' · '+row['state']+'\n'+row['url']+'\n'+('Consulta: '+datetime.fromtimestamp(row['fetched']).isoformat(timespec='seconds') if row.get('fetched') else row.get('error','Sin consulta confirmada'))+'\n\n'
            box.configure(state='normal');box.delete('1.0','end');box.insert('end',text);box.configure(state='disabled');win.after(1500,render)
        bar=tk.Frame(win,bg=BG);bar.pack(side='bottom',fill='x',padx=18,pady=12)
        button(bar,'ACTUALIZAR CONOCIMIENTO',self.knowledge_worker.refresh,GREEN).pack(side='left')
        render()

    def open_cache_cleaner(self):
        from cache_maintenance import candidates,clean
        win=self.service_dialog('Borrar caché',660,420);box=text_box(win,8);box.pack(fill='both',expand=True,padx=18,pady=8)
        action=button(win,'COMPROBANDO…',lambda:None,MUTED);action.configure(state='disabled');action.pack(anchor='e',padx=18,pady=12)
        def preview():
            try:data=candidates(self.folder,self.cfg['knowledge']['cache_days']);self.replies.put({'cache_preview':data,'cache_box':box,'cache_button':action,'cache_window':win})
            except Exception as exc:self.replies.put({'service_error':'No se pudo revisar el caché: '+safe_text(exc)})
        threading.Thread(target=preview,name='AkiraCachePreview',daemon=True).start()

    def clean_cache(self,preview,button_widget):
        from cache_maintenance import clean
        button_widget.configure(state='disabled',text='LIMPIANDO…')
        def work():
            try:
                result=clean(self.folder,preview);self.assistant._research_cache.clear()
                with self.assistant._source_cache_lock:self.assistant._source_cache.clear()
                self.replies.put({'cache_result':result,'cache_button':button_widget})
            except Exception as exc:self.replies.put({'service_error':'No se pudo limpiar el caché: '+safe_text(exc),'cache_button':button_widget})
        threading.Thread(target=work,name='AkiraCacheClean',daemon=True).start()

    def open_verification(self,symbol='ALL',selected_id=None):
        from pending_verification import report_text
        win=self.service_dialog('Verificación pendiente por pendiente',1040,760)
        self.pending_verification_window=win
        bar=tk.Frame(win,bg=BG);bar.pack(side='bottom',fill='x',padx=16,pady=10)
        self.pending_verify_request_button=button(bar,'VERIFICAR LO QUE FALTA',lambda:self.request_pending_verification(symbol,selection(),False),BLUE);self.pending_verify_request_button.pack(side='left',padx=(0,5))
        self.pending_verify_deep_button=button(bar,'EXIGIR REVISIÓN PROFUNDA DE IA',lambda:self.request_pending_verification(symbol,selection(),True),CYAN);self.pending_verify_deep_button.pack(side='left',padx=5)
        self.pending_verify_all_button=button(bar,'REVISAR TODAS',lambda:self.request_pending_verification('ALL',None,True),GREEN);self.pending_verify_all_button.pack(side='right')
        note=label(win,'La barra mide comprobaciones de cada Entry/SL/TP. Revisar no coloca ni modifica órdenes; los datos que falten se muestran expresamente.',MUTED,9,anchor='w',justify='left',wraplength=950);note.pack(fill='x',padx=18,pady=(0,6))
        self.pending_verification_note=note
        self.require_pending_ai=tk.BooleanVar(value=True)
        tk.Checkbutton(win,text='Exigir aprobación IA vigente antes de nuevos envíos o cambios de lo seleccionado',variable=self.require_pending_ai,
            bg=BG,fg=TEXT,selectcolor=CARD,activebackground=BG,font=(FONT,9),bd=0,highlightthickness=0).pack(fill='x',padx=18,pady=(0,5))
        panel=self.layout.pane(win,'pending_verification_dialog',tk.VERTICAL,(.40,));panel.pack(fill='both',expand=True,padx=16,pady=4)
        table=tk.Frame(panel,bg=PANEL);panel.add(table,minsize=100,stretch='always')
        cols=('order','symbol','kind','entry','sl','tp','coverage','state')
        tree=ttk.Treeview(table,columns=cols,show='headings',height=5);self.pending_verification_tree=tree
        for key,title,width in zip(cols,('PENDIENTE','SÍMBOLO','TIPO','ENTRY','SL','TP','REVISIÓN','ESTADO'),(160,100,100,100,100,100,90,195)):
            tree.heading(key,text=title);tree.column(key,width=width,minwidth=65,anchor='w')
        scroll=ttk.Scrollbar(table,orient='vertical',command=tree.yview);scroll.pack(side='right',fill='y')
        horizontal=ttk.Scrollbar(table,orient='horizontal',command=tree.xview);horizontal.pack(side='bottom',fill='x')
        tree.configure(yscrollcommand=scroll.set,xscrollcommand=horizontal.set);tree.pack(fill='both',expand=True)
        details=tk.Frame(panel,bg=PANEL);panel.add(details,minsize=130,stretch='always')
        progress=ttk.Progressbar(details,style='Cyber.Horizontal.TProgressbar',maximum=100);progress.pack(fill='x',padx=8,pady=6);self.pending_verification_progress=progress
        box=text_box(details,12);box.pack(fill='both',expand=True,padx=8,pady=(0,6));self.pending_verification_box=box
        rows={};choice=[selected_id]
        def selection():
            chosen=tree.selection()
            return chosen[0] if chosen else choice[0]
        def show(event=None):
            pid=selection();row=rows.get(pid)
            if row:
                choice[0]=pid;progress.configure(value=row['progress'])
                box.configure(state='normal');box.delete('1.0','end');box.insert('end',report_text(row));box.configure(state='disabled')
        tree.bind('<<TreeviewSelect>>',show)
        def render():
            if not win.winfo_exists():return
            current=self.view.get('pending_verifications') or {};rows.clear();rows.update({pid:r for pid,r in current.items() if symbol=='ALL' or r['symbol']==symbol})
            chosen=selection();tree.delete(*tree.get_children())
            for pid,row in rows.items():
                p=row['levels'];side='BUY' if p.get('side')==1 else 'SELL'
                def price(value):return '—' if value is None else f'{float(value):,.3f}'
                tree.insert('','end',iid=pid,values=('#'+str(row['ticket']) if row.get('ticket') else 'PROPUESTA',row['symbol'],side+' '+str(p.get('kind')),price(p.get('entry')),price(p.get('sl')),price(p.get('tp')),str(row['completed'])+'/'+str(row['total']),row['state']))
            if chosen in rows:tree.selection_set(chosen)
            elif rows:tree.selection_set(next(iter(rows)))
            if rows:show()
            else:
                progress.configure(value=0);box.configure(state='normal');box.delete('1.0','end');box.insert('end','No hay pendientes activas en este ámbito. Esperando escenarios actuales del motor.');box.configure(state='disabled')
            job=(self.view.get('pending_verification_requests') or {}).get(getattr(self,'_pending_verification_job',None))
            if job:
                text=job['phase']+' · tareas procesadas '+str(job['completed'])+'/'+str(job['total'])
                if job.get('changed'):text+=' · Los niveles cambiaron; la revisión anterior no se considera vigente. Exige una revisión nueva.'
                elif job.get('missing'):text+=' · Aún falta: '+', '.join(job['missing'])
                note.configure(text=text,fg=AMBER if job['phase']!='REVISIÓN TERMINADA' or job.get('missing') else CYAN)
                if job['phase'] in ('REVISIÓN TERMINADA','SIN SERVICIO DE IA','DATOS O NIVELES CAMBIADOS'):
                    seen=getattr(self,'_pending_verification_notices',set());self._pending_verification_notices=seen
                    if job['id'] not in seen:self.desktop_toast('Revisión individual',text);seen.add(job['id'])
            win.after(1200,render)
        render()

    def request_pending_verification(self,symbol='ALL',pid=None,deep=True):
        if getattr(self,'_pending_verification_loading',False):return
        self._pending_verification_loading=True
        if hasattr(self,'pending_verification_note'):self.pending_verification_note.configure(text='Solicitando lectura de niveles, riesgos y comprobaciones faltantes…',fg=AMBER)
        command={'action':'verify_pending','symbol':symbol,'deep':bool(deep)}
        if deep and hasattr(self,'require_pending_ai'):command['require']=bool(self.require_pending_ai.get())
        elif hasattr(self,'require_pending_ai') and not self.require_pending_ai.get():command['require']=False
        if pid:command['id']=pid
        def work():
            try:result=self.bridge.request(command)
            except Exception as exc:result={'ok':False,'error':safe_text(exc)}
            self.replies.put({'pending_verification_result':result})
        try:threading.Thread(target=work,name='AkiraPendingVerification',daemon=True).start()
        except RuntimeError as exc:self._pending_verification_loading=False;self.show_message('Verificación',safe_text(exc),True)

    def open_chart_details(self,symbol,tf):
        from analysis_details import INDICATORS
        win=self.service_dialog('Indicadores · '+symbol+' · '+tf,830,600);box=text_box(win,15);box.pack(fill='both',expand=True,padx=18,pady=12)
        info=self.view.get('symbols',{}).get(symbol,{});frame=info.get('frames',{}).get(tf,{})
        text=symbol+' · '+tf+' · fuente MT5\nÚltima vela cerrada: '+str(frame.get('last_bar','sin dato'))+'\n\n'
        text+='VALORES DEL MOTOR\nEstos son los valores publicados que utiliza el análisis. La curva se calcula con la ventana visible y no cambia los filtros de trading.\n\n'
        for key,(name,purpose) in INDICATORS.items():text+=name+': '+str(frame.get(key,'sin dato'))+'\n'+purpose+'\n\n'
        from chart_indicators import indicator_chart
        data=indicator_chart(info.get('bars_by_timeframe',{}).get(tf,[]),tf)
        text+=data.get('parameters','')+'\n'+data['detail']
        box.insert('end',text);box.configure(state='disabled')

    def retry_verification(self):
        self.commands.put({'action':'refresh'});self.commands.put({'action':'reverify'})
        self.show_message('Verificación','Se solicitaron nuevas fuentes y una nueva evaluación del mapa. Las consultas no omiten los límites del Gateway.')

    def open_assistant_diagnostics(self):
        """Read bounded sanitized logs in a worker, preserving any active chat."""
        win=self.service_dialog('AKIRA · motivo y registro',850,600)
        box=text_box(win,16);box.pack(fill='both',expand=True,padx=18,pady=12)
        self.assistant_diagnostic_window=win;self.assistant_diagnostic_box=box
        box.insert('end','Leyendo el estado y los últimos registros…');box.configure(state='disabled')
        status=self.assistant.local_ai_status()
        def work():
            from cyber_ui import public_status
            parts=['ESTADO DE AKIRA\n'+public_status(status.get('detail') or status.get('error') or 'Comprobación pendiente')]
            seen_content=set()
            parts.append('RUTAS DE IA\n'+json.dumps(self.assistant._managed_model.path_resolution,ensure_ascii=False,indent=2))
            paths=[self.folder/'logs/IA_LOCAL.log',self.folder/'logs/ASISTENTE_INICIO.log',self.folder/'logs/ASISTENTE_PROCESO.log',self.assistant.startup.output_log]
            for path in dict.fromkeys(paths):
                try:
                    with path.open('rb') as stream:
                        stream.seek(0,2);end=stream.tell();stream.seek(max(0,end-16000))
                        content=stream.read(16000).decode('utf-8','replace')
                    content=public_status(safe_text(content))
                    if content.strip() and content not in seen_content:parts.append(path.name+'\n'+content);seen_content.add(content)
                except OSError:pass
            if len(parts)==1:parts.append('Todavía no hay salida del proceso. Pulsa REPARAR ASISTENTE y vuelve a abrir este registro.')
            self.replies.put({'assistant_diagnostics':'\n\n'.join(parts),'diagnostic_window':win,'diagnostic_box':box})
        try:threading.Thread(target=work,name='AkiraAssistantDiagnostics',daemon=True).start()
        except RuntimeError as exc:box.configure(state='normal');box.insert('end','\n'+safe_text(exc));box.configure(state='disabled')

    def deep_verification(self):
        self.retry_verification();self.knowledge_worker.refresh()
        if getattr(self,'_deep_verifier_running',False):return
        self._deep_verifier_running=True
        symbols=[s for s in self.view.get('symbols',{}) if not self.view.get('markets',{}).get(s,{}).get('scheduled_closed')]
        def work():
            results=[]
            from concurrent.futures import ThreadPoolExecutor,as_completed
            with ThreadPoolExecutor(max_workers=2,thread_name_prefix='AkiraDeepSource') as pool:
                jobs={pool.submit(self.assistant._source_tool,'research_public_web',{'query':('Bitcoin BTC' if s.startswith('BTC') else 'gold XAUUSD')+' current macroeconomic news liquidity funding market analysis','topic':s,'force':True}):s for s in symbols}
                for future in as_completed(jobs):
                    try:result=future.result();results.append({'symbol':jobs[future],'result':result})
                    except Exception as exc:results.append({'symbol':jobs[future],'error':safe_text(exc)})
            self.replies.put({'deep_verification_result':results})
        threading.Thread(target=work,name='AkiraDeepVerification',daemon=True).start()

    def open_cloud_settings(self):
        from akira_secrets import save_secrets,get_secret
        win=self.service_dialog('OpenAI opcional',750,660)
        label(win,'1. Abre el panel de claves. 2. Crea una clave de proyecto. 3. Pégala aquí y verifica la conexión. La facturación API es independiente de ChatGPT.',MUTED,10,anchor='w',justify='left',wraplength=690).pack(fill='x',padx=18,pady=8)
        button(win,'OBTENER CLAVE API',lambda:webbrowser.open('https://platform.openai.com/api-keys'),BLUE).pack(anchor='w',padx=18,pady=4)
        label(win,'CLAVE API · nunca se muestra la clave guardada',TEXT,10,True,anchor='w').pack(fill='x',padx=18,pady=(14,5))
        value=tk.StringVar();entry=tk.Entry(win,textvariable=value,show='●',font=(FONT,12));entry.pack(fill='x',padx=18,ipady=9)
        state=label(win,'Clave guardada' if get_secret('OPENAI_API_KEY') else 'Sin clave guardada',MUTED,10,anchor='w',justify='left',wraplength=690);state.pack(fill='x',padx=18,pady=12)
        label(win,'La verificación consulta modelos sin generar una respuesta. No confirma saldo ni permisos para todas las herramientas. Chat y síntesis pueden consumir API si el servicio está autorizado; el motor MT5 no espera a OpenAI.',MUTED,9,anchor='w',wraplength=690,justify='left').pack(fill='x',padx=18,pady=5)
        model=tk.StringVar(value=self.cfg['assistant'].get('general_model',''));combo=ttk.Combobox(win,textvariable=model,values=(),style='Akira.TCombobox');combo.pack(fill='x',padx=18,pady=6)
        label(win,'Modelo de conversación y análisis API. La lista se obtiene de tu proyecto al verificar.',MUTED,9,anchor='w').pack(fill='x',padx=18)
        primary=tk.BooleanVar(value=not self.cfg['assistant'].get('local_primary',True))
        from cyber_ui import toggle
        container=tk.Frame(win,bg=PANEL);container.pack(fill='x',padx=18,pady=8)
        enabled=tk.BooleanVar(value=self.cfg['assistant'].get('cloud',False))
        toggle(container,enabled,'Autorizar OpenAI','Permite consultas API. Cada respuesta puede generar costes; el motor MT5 sigue siendo independiente.')
        toggle(container,primary,'Preferir OpenAI cuando esté autorizado','Desactivado: AKIRA utiliza su motor principal y OpenAI como recurso opcional.')
        def save():
            try:
                key=value.get().strip()
                if key:
                    if not key.startswith('sk-'):raise ValueError('Pega una clave API completa; no su representación censurada.')
                    save_secrets({'OPENAI_API_KEY':key});value.set('')
                cfg=copy.deepcopy(self.cfg);cfg['assistant']['local_primary']=not primary.get();cfg['assistant']['cloud']=enabled.get()
                if model.get().strip():cfg['assistant']['general_model']=cfg['assistant']['trading_model']=model.get().strip()
                self.cfg.update(save_config(cfg,self.folder/'akira_config.json'));self.use_cloud.set(enabled.get());state.configure(text='Preferencias guardadas. La clave guardada permanece oculta. Pulsa VERIFICAR CONEXIÓN para comprobar autenticación.',fg=GREEN)
                self.desktop_toast('OpenAI','Se guardó la configuración de la integración; ninguna clave se incluye en este aviso.')
            except Exception as exc:state.configure(text=safe_text(exc),fg=RED)
        bar=tk.Frame(win,bg=BG);bar.pack(fill='x',padx=18,pady=12)
        button(bar,'GUARDAR / REEMPLAZAR',save,GREEN).pack(side='left')
        def verify():
            state.configure(text='Comprobando conexión…',fg=AMBER)
            self._cloud_job+=1;job=self._cloud_job
            def work():
                from cloud_status import verify_cloud
                self.replies.put({'service_cloud':verify_cloud(),'cloud_job':job,'cloud_dialog':win,'cloud_label':state,'cloud_combo':combo})
            threading.Thread(target=work,name='AkiraCloudVerify',daemon=True).start()
        button(bar,'VERIFICAR CONEXIÓN',verify,BLUE).pack(side='right')

    def open_chat_trash(self):
        win=self.service_dialog('Conversaciones eliminadas',650,500);rows=self.assistant.chats.trash();items=tk.Listbox(win,bg=PANEL,fg=TEXT,selectbackground=BLUE,font=(FONT,11));items.pack(fill='both',expand=True,padx=18,pady=10)
        for row in rows:items.insert('end',row['title'])
        def restore():
            if not items.curselection():return
            if self.chat_busy or self.voice_awaiting:self.show_message('Chat','Termina la respuesta activa antes de cambiar de conversación.');return
            cid=rows[items.curselection()[0]]['id'];self.assistant.chats.restore(cid);self.assistant.switch_chat(cid);self.reload_chat();win.destroy()
        button(win,'RECUPERAR CHAT',restore,GREEN).pack(anchor='e',padx=18,pady=12)

    def handle_service_reply(self,reply):
        if 'source_access_result' in reply:
            self.source_access_status.configure(text=reply['source_access_result'],fg=TEXT)
            return True
        if 'pending_verification_result' in reply:
            self._pending_verification_loading=False;r=reply['pending_verification_result']
            if r.get('job'):self._pending_verification_job=r['job']
            message=r.get('detail') or r.get('error') or 'El motor no confirmó la solicitud de revisión.'
            if hasattr(self,'pending_verification_note') and self.pending_verification_note.winfo_exists():self.pending_verification_note.configure(text=message,fg=CYAN if r.get('ok') else RED)
            self.desktop_toast('Verificación de pendientes',message,severity='info' if r.get('ok') else 'warning')
            return True
        if 'assistant_diagnostics' in reply:
            if reply['diagnostic_window'].winfo_exists():
                box=reply['diagnostic_box'];box.configure(state='normal');box.delete('1.0','end')
                box.insert('end',reply['assistant_diagnostics']);box.configure(state='disabled')
            return True
        if 'deep_verification_result' in reply:
            self._deep_verifier_running=False
            win=self.service_dialog('Revisión profunda · fuentes',850,600);box=text_box(win,16);box.pack(fill='both',expand=True,padx=18,pady=12)
            rows=reply['deep_verification_result'];box.insert('end','Las fuentes siguientes aportan contexto. No cambian riesgo ni sustituyen la comprobación MT5.\n\n')
            for row in rows:
                result=row.get('result') or {};box.insert('end',row['symbol']+'\n')
                if row.get('error'):box.insert('end',row['error']+'\n')
                sources=result.get('results') or []
                if not sources:box.insert('end','No se consiguieron fuentes utilizables para esta consulta. Reintenta; esto no equivale a confirmación.\n')
                for index,source in enumerate(sources):
                    box.insert('end',safe_text(source.get('title') or 'Fuente')+'\n')
                    box.insert('end',safe_text(source.get('publisher') or source.get('engine') or 'Web')+' · '+safe_text(source.get('published') or 'Fecha no confirmada')+' · '+safe_text(source.get('read_status') or 'extracto')+'\n')
                    box.insert('end',safe_text(source.get('text') or source.get('snippet') or '')[:1800]+'\n')
                    url=str(source.get('url') or '')
                    if url.startswith(('https://','http://')):
                        tag='deep_source_'+str(time.time_ns())+'_'+str(index)
                        box.insert('end','ABRIR FUENTE\n',tag);box.tag_configure(tag,foreground=CYAN)
                        box.tag_bind(tag,'<Button-1>',lambda event,u=url:webbrowser.open(u))
                    box.insert('end','\n')
            box.configure(state='disabled');return True
        if 'settings_result' in reply:
            if reply['settings_job']!=self._settings_job:return True
            result=reply['settings_result'];rows=reply['settings_rows']
            text=change_message(rows)
            if result.get('ok') and result.get('settings_applied'):
                self.show_message('Ajustes aplicados',text)
                if any(r['path'].startswith(('risk.','sizing.')) or r['path']=='lot' for r in rows):self.request_risk_ack()
            else:self.show_message('Ajustes guardados; aplicación pendiente',text+'\n'+str(result.get('error','Motor no confirmó la aplicación. Se cargarán al reiniciar.')),True)
            return True
        if 'knowledge_event' in reply:
            row=reply['knowledge_event'];self.desktop_toast('Conocimiento · '+row['stage'],row['detail']);return True
        if 'cache_preview' in reply:
            if not reply['cache_window'].winfo_exists():return True
            data=reply['cache_preview'];box=reply['cache_box'];box.configure(state='normal');box.delete('1.0','end');box.insert('end',f"{data['bytes']/1048576:.2f} MB recuperables/reutilizables\n{len(data['files'])} archivos temporales y {len(data['sources'])} consultas antiguas.\nAntigüedad: {data['days']} días.\n\n"+data['scope']);box.configure(state='disabled')
            button_widget=reply['cache_button'];button_widget.configure(text='BORRAR CACHÉ',state='normal',command=lambda:self.clean_cache(data,button_widget));return True
        if 'cache_result' in reply:
            r=reply['cache_result'];self.show_message('Caché limpiado',str(r['files_removed'])+' temporales y '+str(r['source_rows_removed'])+' consultas eliminadas. Los datos importantes se conservaron.')
            if reply['cache_button'].winfo_exists():reply['cache_button'].configure(text='LIMPIEZA COMPLETADA')
            return True
        if 'service_cloud' in reply:
            if reply['cloud_job']!=self._cloud_job:return True
            r=reply['service_cloud'];self.cloud_status.configure(text=r['detail'],fg=GREEN if r['ok'] else RED)
            if reply['cloud_dialog'].winfo_exists():reply['cloud_label'].configure(text=r['detail'],fg=GREEN if r['ok'] else RED);reply['cloud_combo'].configure(values=[m for m in r.get('models',[]) if m.startswith(('gpt-','o1','o3','o4'))])
            self.desktop_toast('OpenAI · verificación',r['detail'],severity='info' if r['ok'] else 'warning');return True
        if 'service_error' in reply:
            if reply.get('cache_button') and reply['cache_button'].winfo_exists():reply['cache_button'].configure(state='normal',text='REINTENTAR')
            self.show_message('Servicio de AKIRA',reply['service_error'],True);return True
        return False
