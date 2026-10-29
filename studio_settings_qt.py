"""One settings transaction and native editors for languages, media and sprites."""
from __future__ import annotations
import copy,json
from pathlib import Path
from PySide6.QtCore import Qt,QSize,QTimer
from PySide6.QtGui import QIcon,QPixmap,QColor,QFontDatabase
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QTabWidget,QScrollArea,QLineEdit,QComboBox,QCheckBox,QDoubleSpinBox,QSpinBox,QSlider,QLabel,QFileDialog,QColorDialog,QFontComboBox,QDialog,QDialogButtonBox,QListWidget,QListWidgetItem,QAbstractItemView,QPlainTextEdit
from studio_editors import ChoiceBox,ColorButton,FontEditor,WallpaperEditor
from studio_widgets import Card,label,button,INK,Toggle
from akira_studio import STATES,LOCALES,import_media,import_sprites,suggested_sequences,ordered_entries,import_language_pack


STATE_TITLES={'idle':'En reposo','blink':'Parpadeo','listening':'Escuchando','talking':'Hablando','thinking':'Pensando','analyzing':'Analizando','happy':'Feliz','alert':'Alerta','sleeping':'Dormido','loading':'Cargando','connecting':'Conectando','waking':'Despertando','bullish':'Alcista','bearish':'Bajista','caring':'Cariñoso','surprised':'Sorprendido'}


class RiskNumber(QDoubleSpinBox):
    def textFromValue(self,value):
        text=super().textFromValue(value);separator=self.locale().decimalPoint()
        return text.rstrip('0'+self.locale().zeroDigit()).rstrip(separator) if separator in text else text

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
        super().__init__();self.window=window;self.controller=window.controller;self.tr=window.tr;self.fields={};self.initial={};self.touched=set();self.keys={};self.extra={};self.avatar=copy.deepcopy(self.controller.cfg['studio']['avatar']);self.avatar_initial=copy.deepcopy(self.avatar);self.avatar_touched=False
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(10)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.categories=[]
        for name in ('OPERACIÓN','RIESGO','IA Y VOZ','FUENTES Y CONEXIONES','APARIENCIA','APLICACIÓN'):
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            body=QWidget();box=QVBoxLayout(body);box.setContentsMargins(8,10,8,10);box.setSpacing(14);scroll.setWidget(body)
            self.tabs.addTab(scroll,self.tr.text(name));self.categories.append((name,box))
        self.operation();self.risk();self.ai_voice();self.sources();self.appearance();self.application()
        for _,box in self.categories:box.addStretch(1)
        footer=QHBoxLayout();self.message=label('','muted');self.message.setWordWrap(True);footer.addWidget(self.message,1)
        self.save_button=button('',self.window.save_settings,'primary');self.tr.bind(self.save_button,'GUARDAR AJUSTES');footer.addWidget(self.save_button);layout.addLayout(footer)
        footer.addWidget(self.risk_save_button)
        def show_save(index):self.risk_save_button.setVisible(index==1);self.save_button.setVisible(index!=1)
        self.tabs.currentChanged.connect(show_save);show_save(self.tabs.currentIndex())
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(220);self.preview_timer.timeout.connect(self.preview)
        self.autosave_timer=QTimer(self);self.autosave_timer.setSingleShot(True);self.autosave_timer.setInterval(800);self.autosave_timer.timeout.connect(self.persist_visual)

    def card(self,index,title,glyph='settings'):
        card=Card(self.tr.text(title),glyph);self.tr.bind(card.title,title);self.categories[index][1].addWidget(card);return card
    def text(self,source):return self.tr.text(source)
    def field(self,card,path,title,options=None,limits=None,help='',editable=False):
        row=QHBoxLayout();caption=label('');self.tr.bind(caption,title);caption.setWordWrap(True);row.addWidget(caption,1)
        value=get(self.controller.cfg,path)
        if path in ('studio.accent','studio.secondary','studio.background_color'):
            widget=ColorButton(str(value or ''));read=widget.value
        elif options is not None:
            widget=ChoiceBox();widget.setEditable(editable)
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
            decimal=path.startswith('risk.') or path in ('runner.max_trade_budget_pct','runner.loss_budget_trades','runner.loss_cooldown_seconds')
            integer=type(value) is int and not decimal
            widget=QSpinBox() if integer else RiskNumber() if path.startswith(('risk.','runner.')) else QDoubleSpinBox()
            lo,hi=limits or (-1e9,1e9)
            if integer:widget.setRange(int(lo),int(hi))
            else:widget.setRange(float(lo),float(hi));widget.setDecimals(4)
            widget.setValue(value);read=widget.value
            if path.startswith('risk.') or path in ('runner.max_trade_budget_pct','runner.loss_cooldown_seconds','runner.loss_budget_trades'):
                widget.setGroupSeparatorShown(True)
                if path.endswith('_pct'):widget.setSuffix(' %')
                elif path.endswith('loss_cooldown_seconds'):widget.setSuffix(' s')
                elif path.endswith('loss_budget_trades'):widget.setSuffix(' ×')
                elif path.startswith('risk.') and 'money' in path:widget.setSuffix(' USD')
        else:
            widget=QLineEdit(str(value or ''));read=widget.text
        widget.setMinimumWidth(160);widget.setMaximumWidth(420);widget.setSizePolicy(widget.sizePolicy().horizontalPolicy(),widget.sizePolicy().verticalPolicy())
        if help:
            note=label(help,'muted');note.setWordWrap(True);card.body.addWidget(note)
        row.addWidget(widget,1);card.body.addLayout(row);self.fields[path]=(widget,read);self.initial[path]=copy.deepcopy(read())
        signal=widget.valueChanged if isinstance(widget,ColorButton) else widget.currentTextChanged if isinstance(widget,QComboBox) else widget.toggled if isinstance(widget,QCheckBox) else widget.textChanged if isinstance(widget,QLineEdit) else widget.valueChanged
        signal.connect(lambda *args,p=path:self.touched.add(p))
        if path.startswith('studio.') or path.startswith('desktop.model_') or path in ('desktop.performance_profile','desktop.memory_budget_mb','desktop.adaptive_resources'):
            signal.connect(self.schedule_preview)
        return widget
    def add_button(self,card,title,callback,kind='',glyph=None):
        widget=button('',callback,kind,glyph);self.tr.bind(widget,title);card.body.addWidget(widget);return widget
    def operation(self):
        card=self.card(0,'OPERACIÓN','bolt')
        self.field(card,'mode','Modo de operación',(('observe','Solo análisis'),('trade','Operativa automática')),help='Solo análisis estudia sin enviar órdenes. Operativa automática envía, edita y retira propuestas válidas tras autorizar la cuenta y respetar los límites de riesgo.')
        self.field(card,'terminal_path','Ruta de MetaTrader 5',help='Es el programa terminal64.exe del MetaTrader que quieres conectar. Puedes seleccionarlo con el botón de abajo. Déjalo vacío para detección automática; Akira recordará el último terminal comprobado.')
        self.add_button(card,'SELECCIONAR METATRADER 5',self.choose_terminal)
        self.use_mt5_button=self.add_button(card,'USAR CUENTA ABIERTA EN MT5',self.use_open_account,'primary','bolt')
        self.field(card,'expected_login','Número de cuenta',limits=(0,2147483647),help='Para cambiar de cuenta: inicia sesión en MT5 y pulsa Usar cuenta abierta en MT5. Akira copiará el número, el servidor y el programa correcto sin pedirte la contraseña. Después pulsa Activar operativa para autorizar esa cuenta.')
        self.field(card,'expected_server','Servidor del bróker',help='Debe ser el mismo servidor que aparece en MT5, por ejemplo el servidor Demo de tu bróker. Usar cuenta abierta en MT5 lo completa automáticamente. Los datos de acceso y la contraseña se guardan en MT5.')
        self.mt5_status=label('Esperando conexión con MT5. Guarda los cambios de cuenta o ruta antes de reconectar.','muted');self.mt5_status.setWordWrap(True);card.body.addWidget(self.mt5_status)
        self.add_button(card,'RECONECTAR MT5',self.controller.reconnect_mt5,'','bolt')
        self.field(card,'execution.pending_only','Entradas únicamente mediante pendientes',help='Desmarcado permite runners directos confirmados. Las posiciones activadas desde pendientes pueden gestionarse como runners.')
        self.field(card,'runner.enabled','Gestionar runners normales')
        self.field(card,'lot','Lote base',limits=(.001,100))
        self.field(card,'symbols.BTCUSDm','Bitcoin · BTCUSDm');self.field(card,'symbols.XAUUSDm','Oro · XAUUSDm')
        self.add_button(card,'ACTIVAR OPERATIVA',self.window.activate_execution,'primary','shield')
        note=label('Selecciona y aplica la estrategia en Pendientes. El motor actúa automáticamente con los límites y la cuenta autorizados.','muted');note.setWordWrap(True);card.body.addWidget(note)

    def choose_terminal(self):
        path,_=QFileDialog.getOpenFileName(self,'Seleccionar MetaTrader 5','','Programas de Windows (*.exe)')
        if path:self.fields['terminal_path'][0].setText(path)
    def use_open_account(self):
        accepted=self.controller.use_open_mt5_account(self.fields['terminal_path'][1]().strip())
        if accepted:
            self.use_mt5_button.setEnabled(False)
            self.mt5_status.setText('Comprobando la cuenta abierta en MT5… La operativa quedará en Solo análisis mientras se guarda.')
    def risk(self):
        before=set(self.fields)
        card=self.card(1,'TUS LÍMITES EN ESTA CUENTA','shield')
        self.risk_preview=label('Conecta MT5 para calcular los límites de tu cuenta.','body');self.risk_preview.setWordWrap(True);card.body.addWidget(self.risk_preview)
        self.risk_save_button=button('',self.window.save_risk_limits,'primary','shield');self.tr.bind(self.risk_save_button,'GUARDAR Y APLICAR RIESGO')
        card=self.card(1,'PROTECCIÓN PROPORCIONAL DEL CAPITAL','shield')
        self.field(card,'capital_protection.enabled','Proteger el capital de esta cuenta',help='Aplica el menor de estos topes y tus límites personalizados. También revisa las pendientes existentes; no cierra posiciones por dinero ni estrecha su SL. Un lote mínimo puede ser incompatible con una cuenta pequeña.')
        for key,title in [('trade_pct','Tope protegido por orden (%)'),('portfolio_pct','Tope protegido conjunto (%)'),('symbol_pct','Tope protegido por símbolo (%)'),('daily_loss_pct','Pérdida diaria protegida (%)'),('max_drawdown_pct','Caída máxima desde la referencia (%)')]:
            self.field(card,'capital_protection.'+key,title,limits=(.1,100))
        self.field(card,'capital_protection.one_position_per_symbol','Una posición por símbolo')
        self.field(card,'capital_protection.strict_pending_quality','Exigir la misma calidad a las alternativas del mapa')
        self.field(card,'capital_protection.loss_streak_limit','Pérdidas propias seguidas antes de pausar entradas')
        self.field(card,'capital_protection.loss_pause_hours','Pausa de nuevas entradas tras la racha (horas)')
        self.field(card,'capital_protection.fomc_pause','Evitar entradas alrededor de anuncios FOMC programados')
        self.field(card,'capital_protection.event_pause_minutes','Minutos antes y después de cada anuncio o conferencia FOMC')
        card=self.card(1,'CUÁNTO PUEDE ARRIESGAR CADA ORDEN','shield')
        self.field(card,'risk.max_trade_money','Tope por orden en dinero',limits=(0,1e8),help='Pérdida máxima estimada si una orden llega a su protección. También se aplica el porcentaje: manda el menor. Con 0 no se habilita riesgo para nuevas órdenes.')
        self.field(card,'risk.max_trade_pct','Tope por orden sobre el patrimonio',limits=(0,100),help='Con 40 USD de patrimonio, 5% equivale a 2 USD. Manda el menor entre este porcentaje y el tope en dinero. Con 0 no se habilita riesgo para nuevas órdenes.')
        card=self.card(1,'PRESUPUESTO PARA TODAS LAS ÓRDENES','wallet')
        self.field(card,'risk.portfolio_capital_pct','Parte del capital disponible para riesgo',limits=(0,100),help='Es el límite conjunto de pendientes y posiciones. Se calcula sobre el menor valor entre balance y patrimonio.')
        self.field(card,'risk.portfolio_money_cap','Tope adicional del presupuesto en dinero',limits=(0,1e8),help='Con 0 se usa solo el porcentaje de arriba. Con otro importe se aplica el menor de ambos. La barra de uso mide las reservas, incluidas las solicitudes provisionales, no cuánto subas este límite.')
        card=self.card(1,'PÉRDIDA DEL DÍA Y MARGEN','shield')
        self.field(card,'risk.daily_loss_money','Pérdida máxima del día en dinero',limits=(0,1e8),help='Al alcanzar este importe se pausan nuevas entradas. Con 0 este tope en dinero queda desactivado; el porcentaje sigue aplicando si es mayor que 0.')
        self.field(card,'risk.daily_loss_pct','Pérdida máxima del día en porcentaje',limits=(0,100),help='Con 0 este tope porcentual queda desactivado. Se conserva la protección de posiciones existentes.')
        self.field(card,'risk.minimum_margin_level_pct','Nivel mínimo de margen',limits=(0,1e8),help='Patrimonio dividido entre margen utilizado. Por ejemplo, 300% exige tres veces el margen estimado. El bróker también comprueba el margen antes de aceptar una orden.')
        card=self.card(1,'ENTRADAS DIRECTAS Y PROTECCIÓN DE CAPITAL','shield')
        self.field(card,'runner.max_trade_budget_pct','Riesgo runner: % del límite por operación',limits=(1,100),help='Con 50%, un límite general de 2 USD deja como máximo 1 USD para una entrada directa. Si el lote mínimo no cabe, se conserva el SL y se espera.')
        self.field(card,'runner.preserve_pending_orders','Dar prioridad a las pendientes confirmadas',help='Activado: una runner no retira pendientes del mismo activo para entrar a mercado. El mapa de pendientes se evalúa primero.')
        self.field(card,'runner.loss_cooldown_seconds','Pausa tras pérdida de runner (segundos)',limits=(60,86400),help='Solo tras un cierre propio confirmado por MT5. La pausa afecta nuevas runners del mismo activo; las pendientes y la protección siguen activas.')
        self.field(card,'runner.loss_budget_trades','Tope de pérdidas runner en 24 h: múltiplo del límite general',limits=(.25,3),help='Con 1 y un límite general de 2 USD, perder 2 USD entre runners de BTC y oro pausa nuevas runners. Las ganancias no borran esas pérdidas del contador.')
        self.field(card,'runner.allow_size_boost','Permitir aumentar lote de runners por puntuación',help='Desactivado por defecto. Una puntuación técnica alta no demuestra una mayor probabilidad de ganar.')
        card=self.card(1,'GESTIÓN DE RUNNERS','analysis')
        self.field(card,'management.protect_progress','Proteger el avance aunque falte un pivote M15',help='Al alcanzar el umbral R configurado, solicita un SL que cubra costes estimados. Afecta runners directas y pendientes activadas gestionadas como runners; conserva el TP. Respeta la espera mínima y los límites del bróker. No garantiza el precio de ejecución ni elimina pérdidas por saltos de precio.')
        for path,title in [('management.breakeven_at_r','Equilibrio a partir de R'),('management.trail_at_r','Trailing a partir de R'),('management.trail_atr','Distancia de trailing (ATR)'),('management.runner_structure_only','Gestión estructural de runners'),('management.pending_fills_as_runners','Gestionar pendientes activadas como runners')]:self.field(card,path,title)
        self.risk_paths=set(self.fields)-before
        for path in self.risk_paths:
            widget=self.fields[path][0];signal=widget.toggled if isinstance(widget,QCheckBox) else widget.valueChanged
            signal.connect(lambda *args:self.refresh_risk_preview(force=True))
        self.tabs.currentChanged.connect(lambda index:self.refresh_risk_preview(force=True) if index==1 else None)
        self.refresh_risk_preview(force=True)

    def risk_draft(self):
        result=copy.deepcopy(self.controller.cfg);result.dirty_paths=set()
        for path in self.risk_paths:
            value=self.fields[path][1]()
            if path in self.touched or value!=self.initial.get(path):
                put(result,path,value);result.dirty_paths.add(path)
        return result

    def refresh_risk_preview(self,force=False):
        if not hasattr(self,'risk_paths') or (not force and not self.risk_preview.isVisible()):return
        from studio_presenter import risk_dashboard
        config={'risk':dict(self.controller.cfg['risk']),'runner':dict(self.controller.cfg['runner']),'capital_protection':dict(self.controller.cfg['capital_protection'])}
        for path in self.risk_paths:put(config,path,self.fields[path][1]())
        data=risk_dashboard(self.controller.view,config,self.window.private)
        text='Vista previa de lo que estás editando\n'+data['configured']
        text+='\n\nEl motor recalcula el lote admisible con estos límites y conserva la protección estructural. El margen disponible y el lote mínimo del bróker también deben permitir la orden.'
        if data['ready'] and not self.window.private:text+='\nCapital usado para el presupuesto: '+format(data['limits']['capital_basis'],',.2f')+' '+data['limits']['currency']
        changed=any(self.fields[p][1]()!=get(self.controller.cfg,p) for p in self.risk_paths)
        text+='\n\nCambios sin guardar. Pulsa Guardar límites de riesgo.' if changed else '\n\n'+data['state']
        self.risk_preview.setText(text)
    def ai_voice(self):
        card=self.card(2,'IDIOMAS DEL PROGRAMA','chat')
        names={'auto':'Automático','es':'Español','en':'English','pt':'Português','fr':'Français','de':'Deutsch','it':'Italiano','ja':'日本語','zh':'中文','ko':'한국어','ar':'العربية','ru':'Русский','hi':'हिन्दी','tr':'Türkçe','id':'Bahasa Indonesia','vi':'Tiếng Việt','nl':'Nederlands','pl':'Polski','uk':'Українська'}
        for path,title in [('studio.language_ui','Idioma de la interfaz'),('studio.language_chat','Idioma del chat'),('studio.language_voice_in','Idioma de reconocimiento'),('studio.language_voice_out','Idioma de la voz')]:self.field(card,path,title,[(k,v) for k,v in names.items() if k!='auto' or path!='studio.language_ui'])
        self.translation_status=label('','muted');self.translation_status.setWordWrap(True);card.body.addWidget(self.translation_status)
        note=label('Importa traducciones en un archivo .json con locale y translations. Ejemplo: {"locale":"es","translations":{"TRADING":"TRADING"}}. Las voces disponibles dependen del idioma.','muted');note.setWordWrap(True);card.body.addWidget(note);self.add_button(card,'IMPORTAR PAQUETE',self.choose_language)
        card=self.card(2,'IA LOCAL Y CONVERSACIÓN','chat')
        self.field(card,'assistant.conversation_style','Estilo de conversación',[('natural','Natural'),('mentor','Guía y mentor'),('detailed','Explicaciones detalladas')])
        self.field(card,'assistant.local_runtime_model','Archivo GGUF local (opcional)')
        self.add_button(card,'ELEGIR MODELO GGUF',self.choose_gguf)
        note=label('El motor gratuito incluido es llama.cpp. Puedes elegir un modelo GGUF compatible más grande si dispones de RAM suficiente; no se descarga ni se activa hasta guardar. Más tamaño no garantiza mejores decisiones de trading.','muted');note.setWordWrap(True);card.body.addWidget(note)
        self.field(card,'assistant.chat_warm_seconds','Conservar la IA entre mensajes (segundos)',limits=(0,60),help='Con 30 evita cargar otra vez el modelo si continúas conversando. Con 0 libera su memoria al terminar. No cambia el riesgo ni la frecuencia del motor.')
        for path,title in [('assistant.enabled','Asistente activado'),('assistant.allow_live_orders','Permitir solicitudes operativas explícitas del chat'),('assistant.local_runtime_enabled','Motor local incluido'),('assistant.cross_chat_memory','Usar memoria de otras conversaciones')]:
            if get(self.controller.cfg,path) is not None:self.field(card,path,title)
        note=label('Reparar comprueba archivos y una respuesta real. Si falta la IA incluida, intenta recuperarla con una descarga verificada de unos 2,5 GB. Espera el resultado antes de cerrar.','muted');note.setWordWrap(True);card.body.addWidget(note)
        self.add_button(card,'REPARAR ASISTENTE',self.controller.repair_ai);self.add_button(card,'MOTIVO Y REGISTRO',self.window.show_model_log)
        card=self.card(2,'PREFERENCIAS DE VOZ','sources');self.field(card,'voice.model','Modelo de reconocimiento',('tiny','base','small'));self.field(card,'voice.rate','Velocidad de voz',limits=(80,300));self.field(card,'voice.volume','Volumen de voz',limits=(0,1))
        note=label('El teléfono junto al envío del chat inicia la llamada y permite seleccionar micrófono, salida y voz.','muted');note.setWordWrap(True);card.body.addWidget(note)

    def choose_gguf(self):
        path,_=QFileDialog.getOpenFileName(self,'Seleccionar modelo local','','Modelo GGUF (*.gguf)')
        if not path:return
        try:
            with Path(path).open('rb') as stream:
                if stream.read(4)!=b'GGUF':raise ValueError('El archivo no tiene cabecera GGUF')
            self.fields['assistant.local_runtime_model'][0].setText(path)
        except (OSError,ValueError) as exc:self.window.show_error(str(exc))

    def sources(self):
        card=self.card(3,'ACCESO A FUENTES','sources')
        from akira_secrets import load_secrets
        saved=load_secrets()
        from akira_secrets import credential_health
        health=credential_health()
        if not health['readable']:
            warning=label(health['detail'],'body',INK['amber']);warning.setWordWrap(True);card.body.addWidget(warning)
        for key,title in [('COINGLASS_API_KEY','Clave CoinGlass (opcional)'),('OPENAI_API_KEY','Clave OpenAI (opcional)')]:
            row=QHBoxLayout();caption=label(title);self.tr.bind(caption,title);row.addWidget(caption,1)
            entry=QLineEdit(str(saved.get(key) or ''));entry.setEchoMode(QLineEdit.EchoMode.Password);entry.setPlaceholderText('Guardada' if saved.get(key) else 'Sin configurar');row.addWidget(entry,1);eye=button('Mostrar',lambda _=False,w=entry:w.setEchoMode(QLineEdit.EchoMode.Normal if w.echoMode()==QLineEdit.EchoMode.Password else QLineEdit.EchoMode.Password),glyph='eye');row.addWidget(eye);card.body.addLayout(row);self.keys[key]=entry
        note=label('Guardar incluye estas claves. Un campo vacío conserva la clave anterior. Guardar no certifica acceso al proveedor.','muted');note.setWordWrap(True);self.tr.bind(note,note.text());card.body.addWidget(note)
        self.add_button(card,'GUARDAR API',lambda:self.controller.save_keys({k:w.text() for k,w in self.keys.items()}),'primary')
        self.add_button(card,'COMPROBAR FUENTES',self.window.check_sources)
        self.add_button(card,'ELIMINAR UNA CLAVE GUARDADA',self.window.delete_key)
        card=self.card(3,'INVESTIGACIÓN Y CONOCIMIENTO','sources')
        self.field(card,'research.derivatives_provider','Datos de derivados BTC',(('public','Públicos sin plan (recomendado)'),('coinglass','CoinGlass opcional con mi plan')),
            help='Públicos consulta OKX, Bybit o Binance sin clave. La cobertura se muestra en Fuentes; no incluye un mapa agregado de liquidaciones. El oro usa sus propios datos MT5 y macro.')
        for path,title in [('research.enabled','Investigación de mercado'),('research.coinglass_public_fallback','Derivados públicos BTC'),('research.global_news','Consultar noticias'),('knowledge.enabled','Actualizar biblioteca de conversación')]:self.field(card,path,title)
        self.field(card,'knowledge.mode','Actualización de conocimiento',(('automatic','Automática'),('request','Solo al solicitarla')))
        self.field(card,'knowledge.interval_hours','Intervalo de biblioteca (horas)',limits=(1,168))
        self.add_button(card,'ACTUALIZAR CONOCIMIENTO',self.window.refresh_knowledge)
    def appearance(self):
        card=self.card(4,'DISEÑO E IDENTIDAD','settings')
        self.field(card,'studio.brand_name','Nombre del programa')
        theme=self.field(card,'studio.theme','Tema',('AKIRA Original','Nebulosa','Océano','Carbono','Aurora','Violeta','Cobre','Noche polar',*self.controller.cfg['studio'].get('theme_profiles',{})));theme.currentTextChanged.connect(self.load_theme)
        for path,title in [('studio.accent','Color principal'),('studio.secondary','Color secundario'),('studio.background_color','Color de fondo')]:self.field(card,path,title)
        self.font_button=button('Tipografía: '+get(self.controller.cfg,'studio.font','Rajdhani'),self.edit_font);card.body.addWidget(self.font_button);self.field(card,'studio.glow','Brillo',limits=(0,100));self.add_button(card,'GUARDAR TEMA PERSONALIZADO',self.save_theme)
        self.field(card,'studio.panel_texture','Textura',('Neon grid','Carbon','Flat'))
        self.add_button(card,'RESTAURAR DISEÑO ORIGINAL',self.restore_style)
        card=self.card(4,'FONDO DE LA APLICACIÓN','layers')
        self.field(card,'studio.wallpaper.enabled','Activar fondo personalizado')
        self.field(card,'studio.wallpaper.kind','Tipo de fondo',(('default','Original'),('image','Imagen'),('video','Vídeo'),('gif','GIF animado')))
        self.media_name=label(Path(get(self.controller.cfg,'studio.wallpaper.file','')).name,'muted');card.body.addWidget(self.media_name)
        self.add_button(card,'ELEGIR IMAGEN',lambda:self.choose_media('image'));self.add_button(card,'ELEGIR VÍDEO',lambda:self.choose_media('video'));self.add_button(card,'ELEGIR GIF',lambda:self.choose_media('gif'));self.add_button(card,'AJUSTAR CON EL RATÓN',self.edit_wallpaper)
        self.field(card,'studio.wallpaper.loop','Reproducir en bucle');self.field(card,'studio.wallpaper.vsync','Adaptar al refresco del monitor',help='Limita los fotogramas al refresco de esta pantalla. La sincronización final de presentación la controla Windows.')
        fps=sorted({12,24,30,60,90,120,144,max(1,round(self.window.screen().refreshRate() or 60))});self.field(card,'studio.wallpaper.fps','Fotogramas por segundo',[(n,str(n)+' FPS') for n in fps])
        for key,title,low,high in [('opacity','Visibilidad del fondo',0,100),('quality','Calidad',20,100),('max_memory_mb','Memoria del fondo (MB)',32,512),('max_cpu_percent','CPU máxima del fondo (%)',1,40)]:self.field(card,'studio.wallpaper.'+key,title,limits=(low,high))
        self.fields['studio.wallpaper.max_memory_mb'][0].setToolTip('Límite del proceso decodificador en Windows. Los fotogramas de la interfaz tienen un presupuesto adicional acotado; no es un límite de memoria de toda la aplicación.')
        self.wallpaper_status=label('','muted');self.wallpaper_status.setWordWrap(True);card.body.addWidget(self.wallpaper_status)
        card=self.card(4,'AVATAR PERSONALIZADO','chat')
        self.avatar_info=label('','muted');card.body.addWidget(self.avatar_info);self.update_avatar_info()
        self.add_button(card,'EDITAR ESTADOS Y SECUENCIAS',self.edit_avatar)
        self.add_button(card,'USAR AKIRA ORIGINAL',self.original_avatar)
        self.field(card,'studio.reduce_motion','Reducir movimiento')
        card=self.card(4,'RENDIMIENTO','bolt')
        self.field(card,'desktop.adaptive_resources','Ajustar automáticamente equipos de pocos recursos',help='En equipos de hasta 8 GB y dos núcleos físicos, Akira usa CPU, un contexto de IA pequeño y menos efectos. Desactívalo para aplicar solo tus preferencias manuales.')
        self.effective_profile=label('','muted');self.effective_profile.setWordWrap(True);card.body.addWidget(self.effective_profile)
        profile=self.field(card,'desktop.performance_profile','Perfil de recursos',('Rendimiento','Equilibrado','Ahorro de energía'))
        for path,title,low,high in [('desktop.memory_budget_mb','Presupuesto del modelo (MB)',512,16384),('desktop.model_context_tokens','Contexto (tokens)',1024,16384),('desktop.model_keep_alive_seconds','Mantener modelo cargado (s)',0,600)]:self.field(card,path,title,limits=(low,high))
        self.field(card,'desktop.model_use_gpu','Usar GPU para el modelo')
        profile.currentTextChanged.connect(self.apply_profile)
        note=label('La IA evalúa Bitcoin y oro por separado. Las revisiones automáticas se espacian diez minutos en ahorro y tres en equilibrio. El resumen general también descansa al terminar. Las revisiones que exijas tienen prioridad. Cotizaciones, órdenes y riesgo mantienen su frecuencia. Los presupuestos del modelo son orientativos.','muted');note.setWordWrap(True);self.tr.bind(note,note.text());card.body.addWidget(note)
    def apply_profile(self,name):
        from resource_optimizer import profile_budget
        for key,value in profile_budget(name).items():
            widget=self.fields['desktop.'+key][0]
            widget.setChecked(value) if isinstance(widget,QCheckBox) else widget.setValue(value)
        self.schedule_preview()
    def application(self):
        region=self.card(5,'PAÍS, REGIÓN Y HORARIO','settings')
        self.field(region,'locale.country','País')
        self.field(region,'locale.region','Departamento / región')
        self.field(region,'locale.timezone','Zona horaria IANA',
            help='Ejemplo: America/Guatemala. Se aplica a la hora de AKIRA y al chat; los registros del bróker continúan en UTC.')
        card=self.card(5,'APLICACIÓN','settings')
        for path,title in [('desktop.privacy','Ocultar importes al iniciar'),('desktop.notifications','Avisos'),('desktop.notification_popup','Avisos emergentes'),('desktop.notification_sound','Sonido de avisos')]:self.field(card,path,title)
        self.add_button(card,'DESCARGAR DIAGNÓSTICO',self.window.export_diagnostic)
        self.add_button(card,'DESCARGAR INFORME',self.window.export_report)
        self.add_button(card,'GESTIONAR CACHÉ',self.window.manage_cache)
        self.add_button(card,'DESINSTALAR AKIRA',self.window.uninstall_app)
        self.add_button(card,'ACERCA DE',self.window.about)
        card=self.card(5,'CÓMO TRABAJA EL MOTOR','shield');note=label('Akira comprueba cotizaciones, estructura, órdenes, margen y riesgo antes de cada cambio. Las fuentes aportan contexto cuando están disponibles. Ahorro reduce efectos e IA auxiliar; no retrasa protecciones ni obliga a abrir operaciones.','muted');note.setWordWrap(True);card.body.addWidget(note)
    def draft(self):
        result=copy.deepcopy(self.controller.cfg)
        for path,(_,read) in self.fields.items():
            value=read()
            if path in self.touched or value!=self.initial.get(path):put(result,path,value)
        for path,value in self.extra.items():put(result,path,copy.deepcopy(value))
        if self.avatar_touched or self.avatar!=self.avatar_initial:result['studio']['avatar']=copy.deepcopy(self.avatar)
        result.dirty_paths=set(self.touched)|set(self.extra)
        if self.avatar_touched or self.avatar!=self.avatar_initial:result.dirty_paths.add('studio.avatar')
        voice=result['studio']['language_voice_in'];result['voice']['language']=None if voice=='auto' else voice.split('-')[0]
        return result

    def saved(self,data):
        submitted=data.get('submitted') or data['config'];current=data['config']
        for path,(widget,read) in self.fields.items():
            value=read()
            adopted=data.get('adopted_mt5_account') and path in ('mode','terminal_path','expected_login','expected_server')
            if adopted or path not in self.touched or value==get(submitted,path):
                target=get(current,path);widget.blockSignals(True)
                try:
                    if isinstance(widget,ColorButton):widget.setValue(target)
                    elif isinstance(widget,QComboBox):widget.setCurrentIndex(widget.findData(target))
                    elif isinstance(widget,QCheckBox):widget.setChecked(target)
                    elif isinstance(widget,QLineEdit):widget.setText(str(target))
                    else:widget.setValue(target)
                finally:widget.blockSignals(False)
                self.initial[path]=copy.deepcopy(read())
                if adopted or value==get(submitted,path):self.touched.discard(path)
        for path in list(self.extra):
            if self.extra[path]==get(submitted,path):self.extra.pop(path)
        if self.avatar==submitted['studio']['avatar']:self.avatar_initial=copy.deepcopy(self.avatar);self.avatar_touched=False
        self.risk_save_button.setEnabled(True);self.refresh_risk_preview(force=True)

    def persist_visual(self):
        if not hasattr(self,'autosave_timer'):return
        self.autosave_timer.stop();draft=self.draft();target=copy.deepcopy(self.controller.cfg);target['studio']=draft['studio']
        for key in ('performance_profile','adaptive_resources','memory_budget_mb','model_context_tokens','model_keep_alive_seconds','model_use_gpu'):target['desktop'][key]=draft['desktop'][key]
        target.dirty_paths={p for p in draft.dirty_paths if p.startswith('studio.') or p in ('desktop.performance_profile','desktop.adaptive_resources','desktop.memory_budget_mb','desktop.model_context_tokens','desktop.model_keep_alive_seconds','desktop.model_use_gpu')}
        if target!=self.controller.cfg or target.dirty_paths:self.controller.save(target)

    def schedule_preview(self,*args):
        if hasattr(self,'preview_timer'):self.preview_timer.start()
        if hasattr(self,'autosave_timer'):self.autosave_timer.start()
    def preview(self):
        try:
            draft=self.draft();self.window.apply_visual(draft['studio'],draft['desktop'])
        except (ValueError,TypeError,KeyError):pass
    def refresh_resources_preview(self,desktop):
        from resource_optimizer import effective_desktop
        actual=effective_desktop(desktop)
        self.effective_profile.setText('Configuración efectiva: '+actual['performance_profile']+' · '+str(actual['model_context_tokens'])+' de contexto · '+('GPU permitida' if actual['model_use_gpu'] else 'CPU, sin GPU del modelo')+'. Con el ajuste automático activo prevalece esta configuración sobre las preferencias manuales. Las cotizaciones y órdenes mantienen su frecuencia.')
    def choose_color(self,path):
        color=QColorDialog.getColor(QColor(self.fields[path][1]()),self)
        if color.isValid():self.fields[path][0].setValue(color.name())
    def choose_media(self,kind):
        path,_=QFileDialog.getOpenFileName(self,self.text('ELEGIR VÍDEO' if kind=='video' else 'ELEGIR IMAGEN'),'','Video (*.mp4 *.webm *.mov *.mkv)' if kind=='video' else 'Images (*.png *.jpg *.jpeg *.webp *.gif)')
        if path:self.controller.job('import_wallpaper',lambda:{'path':import_media(self.controller.folder,path,kind),'type':kind},'wallpaper_imported')
    def media_imported(self,data):
        self.extra['studio.wallpaper.file']=data['path'];self.media_name.setText(Path(data['path']).name)
        combo=self.fields['studio.wallpaper.kind'][0];combo.setCurrentIndex(combo.findData(data['type']));self.fields['studio.wallpaper.enabled'][0].setChecked(True);self.schedule_preview()
    def choose_language(self):
        path,_=QFileDialog.getOpenFileName(self,self.text('IMPORTAR PAQUETE'),'','JSON (*.json)')
        if path:
            target,locale=import_language_pack(self.controller.folder,path);self.extra['studio.language_pack']=target;combo=self.fields['studio.language_ui'][0];combo.addItem(locale,locale);combo.setCurrentIndex(combo.count()-1);self.message.setText(locale)
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
        if families:
            self.extra['studio.font']=families[0];self.font_button.setText('Tipografía: '+families[0]);self.schedule_preview()
            if getattr(self,'_font_dialog',None) and self._font_dialog.isVisible():self._font_dialog.family.setCurrentText(families[0])
        else:self.window.show_error('No se pudo leer la fuente.')
    def restore_style(self):
        from akira_studio import DEFAULT
        for key in ('brand_name','theme','accent','secondary','background_color','font','font_scale','font_bold','glow','panel_texture'):
            value=DEFAULT[key]
            if 'studio.'+key not in self.fields:self.extra['studio.'+key]=value;continue
            field=self.fields['studio.'+key][0]
            if isinstance(field,ColorButton):field.setValue(value)
            elif isinstance(field,QLineEdit):field.setText(str(value))
            elif isinstance(field,QComboBox):field.setCurrentText(str(value))
            elif isinstance(field,QCheckBox):field.setChecked(value)
            else:field.setValue(value)
        self.fields['studio.wallpaper.enabled'][0].setChecked(False);self.original_avatar();self.schedule_preview()

    def edit_font(self):
        dialog=FontEditor(self,self.draft()['studio'],self.choose_font);self._font_dialog=dialog
        if dialog.exec()==QDialog.DialogCode.Accepted:
            for key,value in dialog.values().items():self.extra['studio.'+key]=value
            self.font_button.setText('Tipografía: '+dialog.family.currentText());self.schedule_preview()

    def save_theme(self):
        from PySide6.QtWidgets import QInputDialog
        from akira_studio import normalize_name
        name,ok=QInputDialog.getText(self,'Guardar tema personalizado','Nombre del perfil')
        if not ok:return
        try:name=normalize_name(name)
        except ValueError as error:self.window.show_error(str(error));return
        studio=self.draft()['studio'];keys=('theme','accent','secondary','background_color','font','font_scale','font_bold','glow','panel_texture');profiles=copy.deepcopy(studio.get('theme_profiles') or {});base=(profiles.get(studio['theme']) or {}).get('theme',studio['theme']);profiles[name]={key:studio[key] for key in keys};profiles[name]['theme']=base;self.extra['studio.theme_profiles']=profiles;self.extra['studio.theme_profile_name']=name
        combo=self.fields['studio.theme'][0]
        if combo.findData(name)<0:combo.addItem(name,name)
        combo.setCurrentIndex(combo.findData(name));self.schedule_preview()

    def load_theme(self,name):
        profile=self.draft()['studio'].get('theme_profiles',{}).get(name)
        if not profile:return
        for key,value in profile.items():
            if key=='theme':continue
            if 'studio.'+key not in self.fields:self.extra['studio.'+key]=value;continue
            widget=self.fields['studio.'+key][0]
            if isinstance(widget,ColorButton):widget.setValue(value)
            elif isinstance(widget,QComboBox):widget.setCurrentText(value)
            else:widget.setValue(value)
        self.extra['studio.theme_profile_name']=name;self.schedule_preview()

    def edit_wallpaper(self):
        config=self.draft()['studio']['wallpaper']
        if not Path(config.get('file','')).is_file():self.window.information('Fondo','Elige primero una imagen, vídeo o GIF.');return
        dialog=WallpaperEditor(self,config)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            for key,value in dialog.config.items():
                if 'studio.wallpaper.'+key not in self.fields:self.extra['studio.wallpaper.'+key]=value
            self.schedule_preview()

    def edit_avatar(self):
        dialog=SpriteEditor(self.window,self.avatar)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.avatar=dialog.result_avatar();self.avatar_touched=True;self.update_avatar_info();self.window.set_avatar(self.avatar);self.schedule_preview()
    def original_avatar(self):self.avatar['active']=False;self.avatar_touched=True;self.update_avatar_info();self.window.set_avatar(self.avatar);self.schedule_preview()
    def update_avatar_info(self):self.avatar_info.setText(('Personalizado' if self.avatar.get('active') else 'Akira original')+' · '+str(len(self.avatar.get('entries',[])))+' sprites propios')
    def retranslate(self):
        for i,(source,_) in enumerate(self.categories):self.tabs.setTabText(i,self.tr.text(source))
        self.translation_status.setText('Selecciona un idioma en cada lista. Las voces se eligen y descargan desde el teléfono del chat.')


class SpriteEditor(QDialog):
    def __init__(self,window,avatar):
        super().__init__(window);self.window=window;self.tr=window.tr;self.avatar=copy.deepcopy(avatar);self.setWindowTitle(self.tr.text('AVATAR PERSONALIZADO'));self.resize(940,650)
        layout=QVBoxLayout(self);top=QHBoxLayout();top.addWidget(button(self.tr.text('IMPORTAR SPRITES'),self.import_files,'primary'));self.grid_rows=QSpinBox();self.grid_cols=QSpinBox()
        for widget in (self.grid_rows,self.grid_cols):widget.setRange(0,32);widget.setSpecialValueText('Auto')
        top.addWidget(label('Filas'));top.addWidget(self.grid_rows);top.addWidget(label('Columnas'));top.addWidget(self.grid_cols);top.addStretch();layout.addLayout(top)
        self.profile=ChoiceBox();self.profile.addItem('Todos los perfiles','ALL')
        for state in STATES:self.profile.addItem(STATE_TITLES[state],state)
        self.profile.currentIndexChanged.connect(self.filter_profile);layout.addWidget(self.profile);self.preview_label=QLabel();self.preview_label.setFixedHeight(120);self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.preview_label)
        self.status=label('Los nombres y las diferencias visuales sugieren estados. Revisa los casos ambiguos; puedes cambiar orden, estado y duración.','muted');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.list=QListWidget();self.list.setViewMode(QListWidget.ViewMode.IconMode);self.list.setIconSize(QSize(95,95));self.list.setGridSize(QSize(150,145));self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove);self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.list.setMinimumHeight(250);layout.addWidget(self.list,1)
        row=QHBoxLayout();self.state=ChoiceBox()
        for state in STATES:self.state.addItem(STATE_TITLES[state],state)
        row.addWidget(label(self.tr.text('Estado reconocido')));row.addWidget(self.state)
        self.duration=QSpinBox();self.duration.setRange(33,2000);self.duration.setValue(180);row.addWidget(label(self.tr.text('Duración (ms)')));row.addWidget(self.duration)
        row.addWidget(button('Asignar a seleccionados',self.assign));row.addWidget(button(self.tr.text('Eliminar'),self.remove));layout.addLayout(row)
        self.loop=QCheckBox('Animar los sprites de cada estado en el orden elegido');self.loop.setChecked(self.avatar.get('animate',True));layout.addWidget(self.loop)
        self.repeat=QCheckBox('Repetir las secuencias');self.repeat.setChecked(self.avatar.get('repeat',True));layout.addWidget(self.repeat)
        footer=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);footer.accepted.connect(self.accept);footer.rejected.connect(self.reject);layout.addWidget(footer)
        self.populate(self.avatar.get('entries',[]));self.list.itemSelectionChanged.connect(self.selection)
        self.duration.valueChanged.connect(self.save_duration);self.preview_index=0;self.preview_timer=QTimer(self);self.preview_timer.timeout.connect(self.preview_frame);self.preview_frame();self.finished.connect(lambda _:self.preview_timer.stop())
    def populate(self,entries):
        self.list.clear()
        for entry in ordered_entries(entries):
            item=QListWidgetItem(QIcon(QPixmap(entry['path'])),STATE_TITLES.get(entry['state'],entry['state'])+'\n'+Path(entry['path']).stem[:20]);item.setData(Qt.ItemDataRole.UserRole,entry);item.setToolTip('Arrastra para ordenar. Asigna una emoción y duración a la selección.');self.list.addItem(item)
    def entries(self):
        return [{**self.list.item(i).data(Qt.ItemDataRole.UserRole),'order':i} for i in range(self.list.count())]
    def selection(self):
        item=self.list.currentItem()
        if item:
            row=item.data(Qt.ItemDataRole.UserRole);self.state.setCurrentIndex(self.state.findData(row['state']));self.duration.blockSignals(True);self.duration.setValue(int(row.get('duration_ms',180)));self.duration.blockSignals(False)
    def assign(self):
        for item in self.list.selectedItems():
            row=dict(item.data(Qt.ItemDataRole.UserRole));row.update(state=self.state.currentData(),duration_ms=self.duration.value(),recognition='Asignado por el usuario');item.setData(Qt.ItemDataRole.UserRole,row);item.setText(STATE_TITLES.get(row['state'],row['state'])+'\n'+Path(row['path']).stem[:20])
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
        return {**self.avatar,'active':bool(entries),'entries':entries,'sequences':sequences,'animate':self.loop.isChecked(),'repeat':self.repeat.isChecked()}

    def filter_profile(self,*args):
        state=self.profile.currentData()
        for i in range(self.list.count()):
            item=self.list.item(i);item.setHidden(state!='ALL' and item.data(Qt.ItemDataRole.UserRole)['state']!=state)
        self.preview_index=0
        if hasattr(self,'preview_timer'):self.preview_frame()
    def save_duration(self,value):
        for item in self.list.selectedItems():
            row=dict(item.data(Qt.ItemDataRole.UserRole));row['duration_ms']=value;item.setData(Qt.ItemDataRole.UserRole,row)
    def preview_frame(self):
        frames=[self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count()) if not self.list.item(i).isHidden()]
        if not frames:self.preview_label.clear();self.preview_timer.stop();return
        self.preview_index=min(self.preview_index,len(frames)-1);frame=frames[self.preview_index];self.preview_label.setPixmap(QPixmap(frame['path']).scaled(115,115,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        if self.loop.isChecked():
            if self.preview_index+1>=len(frames) and not self.repeat.isChecked():self.preview_timer.stop();return
            self.preview_index=(self.preview_index+1)%len(frames);self.preview_timer.start(int(frame.get('duration_ms',180)))
        else:self.preview_timer.stop()

