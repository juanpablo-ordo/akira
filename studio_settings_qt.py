"""One settings transaction and native editors for languages, media and sprites."""
from __future__ import annotations
import copy,json
from pathlib import Path
from PySide6.QtCore import Qt,QSize,QTimer
from PySide6.QtGui import QIcon,QPixmap,QColor,QFontDatabase
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QTabWidget,QScrollArea,QLineEdit,QComboBox,QCheckBox,QDoubleSpinBox,QSpinBox,QSlider,QLabel,QFileDialog,QColorDialog,QFontComboBox,QDialog,QDialogButtonBox,QListWidget,QListWidgetItem,QAbstractItemView,QPlainTextEdit
from studio_widgets import Card,label,button,INK,Toggle
from akira_studio import STATES,LOCALES,import_media,import_sprites,suggested_sequences,ordered_entries,import_language_pack


def get(data,path,default=None):
    for key in path.split('.'):
        if not isinstance(data,dict):return default
        data=data.get(key,default)
    return data


def put(data,path,value):
    parts=path.split('.')
    for key in parts[:-1]:data=data.setdefault(key,{})
    data[parts[-1]]=value


class SettingsPanel(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.controller=window.controller;self.tr=window.tr;self.fields={};self.keys={};self.extra={};self.avatar=copy.deepcopy(self.controller.cfg['studio']['avatar'])
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(10)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.categories=[]
        for name in ('OPERACIÓN','RIESGO','IA Y VOZ','FUENTES Y CONEXIONES','APARIENCIA','APLICACIÓN'):
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            body=QWidget();box=QVBoxLayout(body);box.setContentsMargins(8,10,8,10);box.setSpacing(14);scroll.setWidget(body)
            self.tabs.addTab(scroll,self.tr.text(name));self.categories.append((name,box))
        self.operation();self.risk();self.ai_voice();self.sources();self.appearance();self.application()
        for _,box in self.categories:box.addStretch(1)
        footer=QHBoxLayout();self.message=label('','muted');footer.addWidget(self.message,1)
        self.save_button=button('',self.window.save_settings,'primary');self.tr.bind(self.save_button,'GUARDAR AJUSTES');footer.addWidget(self.save_button);layout.addLayout(footer)
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(220);self.preview_timer.timeout.connect(self.preview)

    def card(self,index,title,glyph='settings'):
        card=Card(self.tr.text(title),glyph);self.tr.bind(card.title,title);self.categories[index][1].addWidget(card);return card
    def text(self,source):return self.tr.text(source)
    def field(self,card,path,title,options=None,limits=None,help='',editable=False):
        row=QHBoxLayout();caption=label('');self.tr.bind(caption,title);caption.setWordWrap(True);row.addWidget(caption,1)
        value=get(self.controller.cfg,path)
        if options is not None:
            widget=QComboBox();widget.setEditable(editable)
            for item in options:
                if isinstance(item,tuple):widget.addItem(self.text(item[1]),item[0])
                else:widget.addItem(str(item),str(item))
            index=widget.findData(value)
            if index>=0:widget.setCurrentIndex(index)
            elif editable:widget.setEditText(str(value or ''))
            elif value is not None:widget.addItem(str(value),value);widget.setCurrentIndex(widget.count()-1)
            read=lambda w=widget:w.currentData() if w.currentText()==w.itemText(w.currentIndex()) and w.currentIndex()>=0 else w.currentText().strip()
        elif isinstance(value,bool):
            widget=Toggle();widget.setChecked(value);read=widget.isChecked
        elif path=='expected_login':
            widget=QLineEdit(str(value or 0));read=lambda w=widget:int(w.text().strip() or 0)
        elif isinstance(value,(int,float)) and not isinstance(value,bool):
            widget=QSpinBox() if type(value) is int else QDoubleSpinBox()
            lo,hi=limits or (-1e9,1e9)
            if type(value) is int:widget.setRange(int(lo),int(hi))
            else:widget.setRange(float(lo),float(hi));widget.setDecimals(4)
            widget.setValue(value);read=widget.value
        else:
            widget=QLineEdit(str(value or ''));read=widget.text
        widget.setMinimumWidth(160);widget.setMaximumWidth(420);widget.setSizePolicy(widget.sizePolicy().horizontalPolicy(),widget.sizePolicy().verticalPolicy())
        if help:widget.setToolTip(help);caption.setToolTip(help)
        row.addWidget(widget,1);card.body.addLayout(row);self.fields[path]=(widget,read)
        if path.startswith('studio.'):
            signal=widget.currentTextChanged if isinstance(widget,QComboBox) else widget.toggled if isinstance(widget,QCheckBox) else widget.textChanged if isinstance(widget,QLineEdit) else widget.valueChanged
            signal.connect(self.schedule_preview)
        return widget
    def add_button(self,card,title,callback,kind='',glyph=None):
        widget=button('',callback,kind,glyph);self.tr.bind(widget,title);card.body.addWidget(widget);return widget
    def operation(self):
        card=self.card(0,'OPERACIÓN','bolt')
        self.field(card,'mode','Modo de operación',(('observe','Solo análisis'),('trade','Operativa automática')))
        self.field(card,'terminal_path','Ruta de MetaTrader 5',help='Déjalo vacío para detectar el terminal. Una ruta nueva se utiliza al reconectar.')
        self.field(card,'expected_login','Cuenta autorizada',limits=(0,2147483647),help='La activación comprueba la cuenta conectada; nunca elige una cuenta desconocida.')
        self.field(card,'execution.pending_only','Entradas únicamente mediante pendientes',help='Desmarcado permite runners directos confirmados. Las posiciones activadas desde pendientes pueden gestionarse como runners.')
        self.field(card,'runner.enabled','Gestionar runners normales')
        self.field(card,'lot','Lote base',limits=(.001,100))
        self.field(card,'symbols.BTCUSDm','Bitcoin · BTCUSDm');self.field(card,'symbols.XAUUSDm','Oro · XAUUSDm')
        self.add_button(card,'ACTIVAR OPERATIVA',self.window.activate_execution,'primary','shield')
        card=self.card(0,'ESTRATEGIA','analysis')
        options=(('AKIRA_ADAPTATIVA','Akira Adaptativa'),('PENDIENTE_RETROCESO','Retroceso estructural'),('PENDIENTE_RUPTURA','Ruptura estructural'),('RUNNER_CONTINUACION_M15','Continuación M15'),('RUNNER_RETEST_M5','Retest M5'),('REVERSION_CONFIRMADA','Reversión confirmada'),('RANGO_RECHAZO','Rechazo de rango'))
        self.field(card,'strategy_choice.selected','Estrategia para la sesión',options)
        self.add_button(card,'ESTRATEGIAS',self.window.show_strategies)
    def risk(self):
        card=self.card(1,'PRESUPUESTO Y LÍMITES','shield')
        for path,title in [('risk.max_trade_money','Pérdida máxima por operación (USD)'),('risk.max_trade_pct','Máximo por operación (%)'),('risk.portfolio_money_cap','Límite conjunto (USD; 0 usa porcentaje)'),('risk.portfolio_capital_pct','Presupuesto conjunto (%)'),('risk.daily_loss_money','Pérdida diaria autorizada (USD; 0 desactiva)'),('risk.daily_loss_pct','Pérdida diaria autorizada (%)'),('risk.minimum_margin_level_pct','Nivel mínimo de margen (%)')]:self.field(card,path,title,limits=(0,100 if path.endswith('_pct') and 'margin' not in path else 1e8))
        card=self.card(1,'GESTIÓN DE RUNNERS','analysis')
        for path,title in [('management.breakeven_at_r','Equilibrio a partir de R'),('management.trail_at_r','Trailing a partir de R'),('management.trail_atr','Distancia de trailing (ATR)'),('management.runner_structure_only','Gestión estructural de runners'),('management.pending_fills_as_runners','Gestionar pendientes activadas como runners')]:self.field(card,path,title)
    def ai_voice(self):
        card=self.card(2,'IDIOMAS DEL PROGRAMA','chat')
        for path,title in [('studio.language_ui','Idioma de la interfaz'),('studio.language_chat','Idioma del chat'),('studio.language_voice_in','Idioma de reconocimiento'),('studio.language_voice_out','Idioma de la voz')]:
            self.field(card,path,title,((*LOCALES,'ru','hi','tr','id','vi','nl','pl','uk') if path=='studio.language_ui' else ('auto',*LOCALES,'ru','hi','tr','id','vi','nl','pl','uk')),editable=True)
        self.translation_status=label('','muted');self.translation_status.setWordWrap(True);card.body.addWidget(self.translation_status)
        self.add_button(card,'TRADUCIR TEXTOS RESTANTES',self.window.translate_interface)
        self.add_button(card,'IMPORTAR PAQUETE',self.choose_language)
        card=self.card(2,'IA LOCAL Y CONVERSACIÓN','chat')
        for path,title in [('assistant.enabled','Asistente activado'),('assistant.allow_live_orders','Permitir solicitudes operativas explícitas del chat'),('assistant.local_runtime_enabled','Motor local incluido'),('assistant.cross_chat_memory','Usar memoria de otras conversaciones')]:
            if get(self.controller.cfg,path) is not None:self.field(card,path,title)
        self.add_button(card,'REPARAR ASISTENTE',lambda:self.controller.job('repair_ai',self.controller.assistant.retry_local_preparation,'ai_repair'))
        self.add_button(card,'MOTIVO Y REGISTRO',self.window.show_model_log)
        card=self.card(2,'VOZ Y LLAMADA','sources')
        self.field(card,'voice.model','Modelo de reconocimiento',('tiny','base','small'))
        self.field(card,'voice.rate','Velocidad de voz',limits=(80,300));self.field(card,'voice.volume','Volumen de voz',limits=(0,1))
        self.add_button(card,'LLAMAR',self.window.open_call)
    def sources(self):
        card=self.card(3,'ACCESO A FUENTES','sources')
        from akira_secrets import load_secrets
        saved=load_secrets()
        from akira_secrets import credential_health
        health=credential_health()
        if not health['readable']:
            warning=label(health['detail'],'body',INK['amber']);warning.setWordWrap(True);card.body.addWidget(warning)
        for key,title in [('COINGLASS_API_KEY','Clave CoinGlass (opcional)'),('YOUTUBE_API_KEY','Clave YouTube Data API (opcional)'),('OPENAI_API_KEY','Clave OpenAI (opcional)')]:
            row=QHBoxLayout();caption=label(title);self.tr.bind(caption,title);row.addWidget(caption,1)
            entry=QLineEdit(str(saved.get(key) or ''));entry.setEchoMode(QLineEdit.EchoMode.Password);entry.setPlaceholderText('Guardada' if saved.get(key) else 'Sin configurar');row.addWidget(entry,1);card.body.addLayout(row);self.keys[key]=entry
        note=label('Guardar incluye estas claves. Un campo vacío conserva la clave anterior. Guardar no certifica acceso al proveedor.','muted');note.setWordWrap(True);self.tr.bind(note,note.text());card.body.addWidget(note)
        self.add_button(card,'COMPROBAR FUENTES',self.window.check_sources)
        self.add_button(card,'IMPORTAR SESIÓN YOUTUBE',self.window.import_youtube_session)
        self.add_button(card,'ELIMINAR UNA CLAVE GUARDADA',self.window.delete_key)
        card=self.card(3,'INVESTIGACIÓN Y CONOCIMIENTO','sources')
        for path,title in [('research.enabled','Investigación de mercado'),('research.youtube','Consultar YouTube'),('research.coinglass','Consultar CoinGlass'),('research.global_news','Consultar noticias'),('knowledge.enabled','Actualizar biblioteca de conversación')]:self.field(card,path,title)
        self.field(card,'knowledge.mode','Actualización de conocimiento',(('automatic','Automática'),('request','Solo al solicitarla')))
        self.field(card,'knowledge.interval_hours','Intervalo de biblioteca (horas)',limits=(1,168))
        self.add_button(card,'ACTUALIZAR CONOCIMIENTO',self.window.refresh_knowledge)
    def appearance(self):
        card=self.card(4,'DISEÑO E IDENTIDAD','settings')
        self.field(card,'studio.brand_name','Nombre del programa')
        self.field(card,'studio.theme','Tema',('AKIRA Original','Nebulosa','Océano','Carbono'))
        for path,title in [('studio.accent','Color principal'),('studio.secondary','Color secundario'),('studio.background_color','Color de fondo (vacío usa el tema)')]:
            field=self.field(card,path,title);self.add_button(card,'Elegir '+title.lower(),lambda _=False,p=path:self.choose_color(p))
        row=QHBoxLayout();row.addWidget(label(self.text('Fuente')),1);family=QFontComboBox();family.setCurrentText(get(self.controller.cfg,'studio.font','Rajdhani'));self.fields['studio.font']=(family,family.currentText);family.currentTextChanged.connect(self.schedule_preview);row.addWidget(family,1);card.body.addLayout(row)
        self.add_button(card,'IMPORTAR FUENTE TTF / OTF',self.choose_font)
        self.field(card,'studio.font_scale','Escala tipográfica',limits=(60,160));self.field(card,'studio.glow','Brillo',limits=(0,100))
        self.field(card,'studio.panel_texture','Textura',('Neon grid','Carbon','Flat'))
        self.add_button(card,'RESTAURAR DISEÑO ORIGINAL',self.restore_style)
        card=self.card(4,'FONDO DE LA APLICACIÓN','layers')
        self.field(card,'studio.wallpaper.enabled','Activar fondo personalizado')
        self.field(card,'studio.wallpaper.kind','Tipo de fondo',(('default','Original'),('image','Imagen'),('video','Vídeo')))
        self.media_name=label(Path(get(self.controller.cfg,'studio.wallpaper.file','')).name,'muted');card.body.addWidget(self.media_name)
        self.add_button(card,'ELEGIR IMAGEN',lambda:self.choose_media('image'));self.add_button(card,'ELEGIR VÍDEO',lambda:self.choose_media('video'))
        self.field(card,'studio.wallpaper.fit','Ajuste',(('cover','Rellenar y recortar'),('contain','Encajar completo'),('stretch','Estirar')))
        self.field(card,'studio.wallpaper.rotation','Rotación',[(v,str(v)+'°') for v in (0,90,180,270)])
        fields=[('offset_x','Desplazamiento horizontal',-100,100),('offset_y','Desplazamiento vertical',-100,100),('opacity','Opacidad',0,100),('fps','Fotogramas por segundo',1,144),('quality','Calidad',20,100),('max_memory_mb','Memoria del fondo (MB)',32,512),('max_cpu_percent','CPU máxima del decodificador (%)',1,40),('crop_left','Recorte izquierdo (%)',0,45),('crop_right','Recorte derecho (%)',0,45),('crop_top','Recorte superior (%)',0,45),('crop_bottom','Recorte inferior (%)',0,45)]
        for key,title,low,high in fields:self.field(card,'studio.wallpaper.'+key,title,limits=(low,high))
        self.fields['studio.wallpaper.max_memory_mb'][0].setToolTip('Límite del proceso decodificador en Windows. Los fotogramas de la interfaz tienen un presupuesto adicional acotado; no es un límite de memoria de toda la aplicación.')
        self.wallpaper_status=label('','muted');self.wallpaper_status.setWordWrap(True);card.body.addWidget(self.wallpaper_status)
        card=self.card(4,'AVATAR PERSONALIZADO','chat')
        self.avatar_info=label('','muted');card.body.addWidget(self.avatar_info);self.update_avatar_info()
        self.add_button(card,'EDITAR ESTADOS Y SECUENCIAS',self.edit_avatar)
        self.add_button(card,'USAR AKIRA ORIGINAL',self.original_avatar)
        self.field(card,'studio.reduce_motion','Reducir movimiento')
        card=self.card(4,'RENDIMIENTO','bolt')
        profile=self.field(card,'desktop.performance_profile','Perfil de recursos',('Rendimiento','Equilibrado','Ahorro de energía'))
        for path,title,low,high in [('desktop.memory_budget_mb','Presupuesto del modelo (MB)',512,16384),('desktop.model_context_tokens','Contexto (tokens)',1024,16384),('desktop.model_keep_alive_seconds','Mantener modelo cargado (s)',0,600)]:self.field(card,path,title,limits=(low,high))
        self.field(card,'desktop.model_use_gpu','Usar GPU para el modelo')
        profile.currentTextChanged.connect(self.apply_profile)
        note=label('La interfaz responde por eventos; la frecuencia de datos es independiente de la animación. El fondo tiene un decodificador propio. Los límites del modelo son presupuestos orientativos.','muted');note.setWordWrap(True);self.tr.bind(note,note.text());card.body.addWidget(note)
    def apply_profile(self,name):
        from resource_optimizer import profile_budget
        for key,value in profile_budget(name).items():
            widget=self.fields['desktop.'+key][0]
            widget.setChecked(value) if isinstance(widget,QCheckBox) else widget.setValue(value)
    def application(self):
        card=self.card(5,'APLICACIÓN','settings')
        for path,title in [('desktop.privacy','Ocultar importes al iniciar'),('desktop.notifications','Avisos'),('desktop.notification_popup','Avisos emergentes'),('desktop.notification_sound','Sonido de avisos')]:self.field(card,path,title)
        self.add_button(card,'DESCARGAR DIAGNÓSTICO',self.window.export_diagnostic)
        self.add_button(card,'DESCARGAR INFORME',self.window.export_report)
        self.add_button(card,'GESTIONAR CACHÉ',self.window.manage_cache)
        self.add_button(card,'DESINSTALAR AKIRA',self.window.uninstall_app)
        self.add_button(card,'ACERCA DE',self.window.about)
        card=self.card(5,'PARÁMETROS AVANZADOS DEL MOTOR','shield')
        self.advanced=QPlainTextEdit();self.advanced.setMinimumHeight(200)
        initial={k:copy.deepcopy(v) for k,v in self.controller.cfg.items() if k not in ('studio','desktop','voice','assistant')}
        self.advanced.setPlainText(json.dumps(initial,ensure_ascii=False,indent=2));self.advanced_original=self.advanced.toPlainText();card.body.addWidget(self.advanced)
        note=label('Edición avanzada validada. No cambia órdenes existentes. Los campos del formulario tienen prioridad cuando ambos se editan.','muted');note.setWordWrap(True);self.tr.bind(note,note.text());card.body.addWidget(note)
    def draft(self):
        result=copy.deepcopy(self.controller.cfg)
        if self.advanced.toPlainText()!=self.advanced_original:
            changed=json.loads(self.advanced.toPlainText())
            if not isinstance(changed,dict):raise ValueError('Los parámetros avanzados requieren un objeto JSON.')
            for key,value in changed.items():
                if key in result and key not in ('studio','desktop','voice','assistant'):result[key]=value
        for path,(_,read) in self.fields.items():put(result,path,read())
        for path,value in self.extra.items():put(result,path,value)
        result['studio']['avatar']=copy.deepcopy(self.avatar)
        voice=result['studio']['language_voice_in'];result['voice']['language']=None if voice=='auto' else voice.split('-')[0]
        return result
    def schedule_preview(self,*args):
        if hasattr(self,'preview_timer'):self.preview_timer.start()
    def preview(self):
        try:self.window.apply_visual(self.draft()['studio'])
        except (ValueError,TypeError,KeyError):pass
    def choose_color(self,path):
        color=QColorDialog.getColor(QColor(self.fields[path][1]()),self)
        if color.isValid():self.fields[path][0].setText(color.name())
    def choose_media(self,kind):
        path,_=QFileDialog.getOpenFileName(self,self.text('ELEGIR VÍDEO' if kind=='video' else 'ELEGIR IMAGEN'),'','Video (*.mp4 *.webm *.mov *.mkv)' if kind=='video' else 'Images (*.png *.jpg *.jpeg *.webp *.gif)')
        if path:self.controller.job('import_wallpaper',lambda:{'path':import_media(self.controller.folder,path,kind),'type':kind},'wallpaper_imported')
    def media_imported(self,data):
        self.extra['studio.wallpaper.file']=data['path'];self.media_name.setText(Path(data['path']).name)
        combo=self.fields['studio.wallpaper.kind'][0];combo.setCurrentIndex(combo.findData(data['type']));self.fields['studio.wallpaper.enabled'][0].setChecked(True);self.schedule_preview()
    def choose_language(self):
        path,_=QFileDialog.getOpenFileName(self,self.text('IMPORTAR PAQUETE'),'','JSON (*.json)')
        if path:
            target,locale=import_language_pack(self.controller.folder,path);self.extra['studio.language_pack']=target;self.fields['studio.language_ui'][0].setEditText(locale);self.message.setText(locale)
    def choose_font(self):
        path,_=QFileDialog.getOpenFileName(self,'Fuente','','Fonts (*.ttf *.otf)')
        if not path:return
        def work():
            import hashlib,shutil
            source=Path(path)
            if source.stat().st_size>20*1024*1024:raise ValueError('Fuente demasiado grande.')
            target=self.controller.folder/'studio/fonts'/(hashlib.sha256(source.read_bytes()).hexdigest()[:16]+source.suffix);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);return str(target)
        self.controller.job('import_font',work,'font_imported')
    def font_imported(self,path):
        font_id=QFontDatabase.addApplicationFont(str(path));families=QFontDatabase.applicationFontFamilies(font_id)
        if families:self.fields['studio.font'][0].setCurrentText(families[0])
        else:self.window.show_error('No se pudo leer la fuente.')
    def restore_style(self):
        from akira_studio import DEFAULT
        for key in ('brand_name','theme','accent','secondary','background_color','font','font_scale','glow','panel_texture'):
            field=self.fields['studio.'+key][0];value='Rajdhani' if key=='font' else DEFAULT[key]
            if isinstance(field,QLineEdit):field.setText(str(value))
            elif isinstance(field,QComboBox):field.setCurrentText(str(value))
            else:field.setValue(value)
        self.fields['studio.wallpaper.enabled'][0].setChecked(False);self.original_avatar();self.schedule_preview()
    def edit_avatar(self):
        dialog=SpriteEditor(self.window,self.avatar)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.avatar=dialog.result_avatar();self.update_avatar_info();self.window.set_avatar(self.avatar)
    def original_avatar(self):self.avatar['active']=False;self.update_avatar_info();self.window.set_avatar(self.avatar)
    def update_avatar_info(self):self.avatar_info.setText(('Personalizado' if self.avatar.get('active') else 'Akira original')+' · '+str(len(self.avatar.get('entries',[])))+' sprites propios')
    def retranslate(self):
        for i,(source,_) in enumerate(self.categories):self.tabs.setTabText(i,self.tr.text(source))
        missing=len(self.tr.missing());self.translation_status.setText(self.tr.locale+' · '+str(missing)+' textos disponibles para traducir con la IA local.' if missing else self.tr.locale+' · Traducciones disponibles.')


class SpriteEditor(QDialog):
    def __init__(self,window,avatar):
        super().__init__(window);self.window=window;self.tr=window.tr;self.avatar=copy.deepcopy(avatar);self.setWindowTitle(self.tr.text('AVATAR PERSONALIZADO'));self.resize(940,650)
        layout=QVBoxLayout(self);top=QHBoxLayout();top.addWidget(button(self.tr.text('IMPORTAR SPRITES'),self.import_files,'primary'));self.grid_rows=QSpinBox();self.grid_cols=QSpinBox()
        for widget in (self.grid_rows,self.grid_cols):widget.setRange(0,32);widget.setSpecialValueText('Auto')
        top.addWidget(label('Filas'));top.addWidget(self.grid_rows);top.addWidget(label('Columnas'));top.addWidget(self.grid_cols);top.addStretch();layout.addLayout(top)
        self.status=label('Los nombres y las diferencias visuales sugieren estados. Revisa los casos ambiguos; puedes cambiar orden, estado y duración.','muted');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.list=QListWidget();self.list.setViewMode(QListWidget.ViewMode.IconMode);self.list.setIconSize(QSize(95,95));self.list.setGridSize(QSize(150,145));self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove);self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.list.setMinimumHeight(250);layout.addWidget(self.list,1)
        row=QHBoxLayout();self.state=QComboBox();self.state.addItems(STATES);row.addWidget(label(self.tr.text('Estado reconocido')));row.addWidget(self.state)
        self.duration=QSpinBox();self.duration.setRange(33,2000);self.duration.setValue(180);row.addWidget(label(self.tr.text('Duración (ms)')));row.addWidget(self.duration)
        row.addWidget(button('Asignar a seleccionados',self.assign));row.addWidget(button(self.tr.text('Eliminar'),self.remove));layout.addLayout(row)
        self.loop=QCheckBox('Animar los sprites de cada estado en el orden elegido');self.loop.setChecked(True);layout.addWidget(self.loop)
        self.repeat=QCheckBox('Repetir las secuencias');self.repeat.setChecked(True);layout.addWidget(self.repeat)
        footer=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);footer.accepted.connect(self.accept);footer.rejected.connect(self.reject);layout.addWidget(footer)
        self.populate(self.avatar.get('entries',[]));self.list.itemSelectionChanged.connect(self.selection)
    def populate(self,entries):
        self.list.clear()
        for entry in ordered_entries(entries):
            item=QListWidgetItem(QIcon(QPixmap(entry['path'])),entry['state']+'\n'+Path(entry['path']).stem[:20]);item.setData(Qt.ItemDataRole.UserRole,entry);item.setToolTip(json.dumps({k:entry.get(k) for k in ('detected_by','confidence','recognition_note','visual_recognition') if k in entry},ensure_ascii=False));self.list.addItem(item)
    def entries(self):
        return [{**self.list.item(i).data(Qt.ItemDataRole.UserRole),'order':i} for i in range(self.list.count())]
    def selection(self):
        item=self.list.currentItem()
        if item:
            row=item.data(Qt.ItemDataRole.UserRole);self.state.setCurrentText(row['state']);self.duration.setValue(int(row.get('duration_ms',180)))
    def assign(self):
        for item in self.list.selectedItems():
            row=dict(item.data(Qt.ItemDataRole.UserRole));row.update(state=self.state.currentText(),duration_ms=self.duration.value(),recognition='Asignado por el usuario');item.setData(Qt.ItemDataRole.UserRole,row);item.setText(row['state']+'\n'+Path(row['path']).stem[:20])
    def remove(self):
        for item in self.list.selectedItems():self.list.takeItem(self.list.row(item))
    def import_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,self.tr.text('IMPORTAR SPRITES'),'','Sprites (*.png *.webp *.gif *.jpg *.jpeg)')
        if not paths:return
        self.status.setText('Importando y proponiendo estados en segundo plano…');existing=self.entries();rows=self.grid_rows.value();cols=self.grid_cols.value()
        def work():
            from sprite_recognition import annotate
            return annotate(import_sprites(self.window.controller.folder,paths,current=existing,rows=rows,columns=cols),existing_ids=[row['id'] for row in existing])
        self.window._sprite_dialog=self
        self.window.controller.job('sprite_import',work,'sprites_imported')
    def result_avatar(self):
        entries=self.entries();sequences={}
        if self.loop.isChecked():
            for state in STATES:
                frames=[r for r in entries if r['state']==state]
                if len(frames)>1:sequences[state]={'frames':[r['id'] for r in frames],'durations_ms':[r.get('duration_ms',180) for r in frames],'delay_ms':frames[0].get('duration_ms',180),'loop':self.repeat.isChecked()}
        return {**self.avatar,'active':bool(entries),'entries':entries,'sequences':sequences}
