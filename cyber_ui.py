"""Lightweight native components for AKIRA's command interface.

Paint only on resize; no timer, network call, or trading work lives here.
"""
import os,re,tkinter as tk
from tkinter import ttk

BG='#061022';PANEL='#091b2b';CARD='#0b2135';LINE='#204960'
CYAN='#23ddf4';BLUE='#1079c5';PINK='#ed58cc';AMBER='#ffc45a'
GREEN='#44e5b5';RED='#ff6d89';MUTED='#88a9bf';TEXT='#e3effa'
FONT='Bahnschrift' if os.name=='nt' else 'DejaVu Sans'
MONO='Consolas' if os.name=='nt' else 'DejaVu Sans Mono'
STUDIO_GLOW=65
STUDIO_TEXTURE='Neon grid'
STUDIO_FONT_SCALE=100

def brand_status(status):
    if status.get('ready'):return 'AKIRA ACTIVO'
    from assistant_startup import PHASE_LABELS
    phase=status.get('phase')
    if not phase:
        phase='FAILED' if status.get('error') else 'MISSING' if status.get('ok') else 'UNAVAILABLE' if status.get('ok') is False else 'CHECKING'
    text='AKIRA · '+PHASE_LABELS.get(phase,'comprobación pendiente')
    if phase=='DOWNLOADING' and status.get('progress_pct') is not None:
        try:text+=f" · capa {max(0,min(100,float(status['progress_pct']))):.0f}%"
        except (ValueError,TypeError):pass
    return text

def public_status(text):
    """Hide backend identifiers in status UI, without changing stored model IDs."""
    text=re.sub(r'(?i)\bAkira\s+Local\s+Core\b','AKIRA',str(text))
    return re.sub(r'(?i)\b(?:qwen[\w.:-]*|gemma[\w.:-]*|llama(?:\d[\w.:-]*|:[\w.:-]+)|ollama)\b','AKIRA',text)

def source_presentation(name,row):
    names={'local_ai':'AKIRA · revisión de indicadores','pending_ai':'AKIRA · pendiente por pendiente','cloud':'OpenAI opcional','model':'Modelo estadístico',
        'news':'Investing · noticias','fed':'Reserva Federal','youtube':'YouTube · transcripciones','strategy_reference':'Video de estrategia compartido'}
    prefix,_,suffix=name.partition(':')
    title=names.get(name,{'technical':'Análisis web','search':'Noticias web','coinglass':'CoinGlass',
        'derivatives':'Derivados públicos','venue':'Exchange','global_news':'Noticias globales','macro':'Macroeconomía'}.get(prefix,prefix))
    if suffix:title+=' · '+suffix
    if prefix=='local_ai' and suffix:title='AKIRA · '+('Oro' if suffix.startswith('XAU') else 'Bitcoin' if suffix.startswith('BTC') else suffix)
    if prefix=='global_news':title=suffix+' · noticias'
    error=public_status(row.get('error') or '');detail=public_status(row.get('detail') or '')
    code=str(row.get('state') or (row.get('data') or {}).get('state') or '').upper()
    if not code:
        code=next((s for s in ('CERTIFICATE_ERROR','AUTH_REQUIRED','ACCESS_DENIED','CONFIG_REQUIRED','UNSUPPORTED','NO_CAPTIONS','RATE_LIMITED','MISSING_RUNTIME','NETWORK_ERROR','UNAVAILABLE') if s in error.upper()),'')
    messages={'AUTH_REQUIRED':('REQUIERE SESIÓN','Ajustes → FUENTES → IMPORTAR SESIÓN YOUTUBE. No se ha analizado el video.'),
        'CONFIG_REQUIRED':('CLAVE OPCIONAL','Añade tu clave en Ajustes → Fuentes para utilizar CoinGlass. Su ausencia no detiene los cálculos de MT5.'),
        'UNSUPPORTED':('NO APLICA','Esta integración no aporta derivados de oro. Esto no desactiva el análisis de XAUUSDm en MT5.'),
        'NO_CAPTIONS':('SIN TRANSCRIPCIÓN','No se obtuvo una transcripción completa. Prueba otro video o revisa la sesión en Fuentes. El análisis técnico continúa.'),
        'RATE_LIMITED':('ESPERANDO CUOTA','YouTube limita las peticiones. Se reintentará con espera.'),
        'CERTIFICATE_ERROR':('CONEXIÓN SEGURA PENDIENTE','No se pudo verificar el certificado al leer YouTube. Comprueba la fecha y los certificados de Windows. No se ha leído el video.'),
        'NETWORK_ERROR':('CONEXIÓN PENDIENTE','YouTube no respondió. Se reintentará; el análisis técnico y las demás fuentes continúan.'),
        'ACCESS_DENIED':('ACCESO DENEGADO','YouTube denegó el acceso. Prueba otro video o importa tu sesión en Fuentes; no se ha leído este video.'),
        'MISSING_RUNTIME':('FALTA COMPONENTE','Instala el paquete completo de AKIRA, que incluye el componente JavaScript.'),
        'UNAVAILABLE':('NO DISPONIBLE','Video privado, retirado o no disponible para esta sesión.')}
    if row.get('enabled') is not False and code in messages:return title,*messages[code]
    if row.get('enabled') is False:state='DESACTIVADA';detail=detail or 'Desactivada en ajustes; no aporta al análisis.'
    elif row.get('reference_only') and row.get('usable') and not error:state='REFERENCIA EDUCATIVA';detail=detail or 'Material guardado para estudiar; no es una cotización ni una señal actual.'
    elif row.get('fresh') and row.get('usable',True) and not error:state='DISPONIBLE';detail=detail or 'Datos vigentes utilizados como contexto.'
    elif error:
        low=error.lower()
        if any(x in low for x in ('api_key','api key','sin clave','falta clave')):
            state='FALTA CLAVE';detail='El proveedor requiere configuración de una clave; consulta Ajustes.'
        elif 'plan' in low or 'plan_limited' in low:
            state='PLAN LIMITADO';detail='El servicio reconoce la integración, pero el plan no autoriza esta consulta.'
        elif '403' in low or 'forbidden' in low:
            state='ACCESO DENEGADO';detail='El sitio denegó el acceso (403); reintentar de inmediato no lo soluciona.'
        elif any(x in low for x in ('timeouterror','timed out','timeout','tiempo de espera')):
            state='TIEMPO AGOTADO';detail='Esta consulta tardó demasiado. Akira mantiene el análisis técnico y reintentará con espera controlada.'
        else:
            from network_tls import connection_message
            state,detail=connection_message(error)
    elif row.get('inflight'):state='BUSCANDO';detail=detail or 'Consulta en segundo plano; el mapa técnico sigue activo.'
    elif row.get('usable') is False:
        state='SIN NOVEDADES' if prefix=='global_news' else 'SIN RESULTADOS'
        detail=detail or ('Este boletín no tiene publicaciones recientes utilizables. Las demás fuentes y MT5 continúan.' if prefix=='global_news' else 'La consulta no devolvió datos utilizables.')
    elif row.get('age_seconds') is not None:state='DESACTUALIZADA';detail=detail or 'La información anterior ya no se usa como confirmación.'
    else:state='ESPERANDO';detail=detail or 'Todavía no terminó una consulta de esta fuente.'
    if error and row.get('inflight'):detail+=' Nueva consulta en curso.'
    retry=row.get('retry_after_seconds')
    if error and retry:detail+=' Próximo intento en '+str(round(float(retry)))+' s.'
    return title,state,detail

class VerificationStages:
    """One color per real verification stage; no fictitious percent completion."""
    def __init__(self,parent,open_details):
        self.frame=tk.Frame(parent,bg=PANEL);self.cells=[];self.last_cycle=None;self.activity=False
        self.pulse=label(self.frame,'●',MUTED,8);self.pulse.pack(side='left',padx=(0,4))
        for i in range(12):
            cell=tk.Label(self.frame,text=str(i+1),bg=CARD,fg=MUTED,font=(FONT,7,'bold'),padx=1,pady=2,cursor='hand2')
            cell.pack(side='left',fill='x',expand=True,padx=1)
            cell.bind('<Button-1>',lambda e:open_details());self.cells.append(cell)
    def pack(self,**kwargs):self.frame.pack(**kwargs)
    def render(self,check):
        for cell,stage in zip(self.cells,check.get('stages') or []):
            state=stage['state'];color=GREEN if state in ('DISPONIBLE','CALCULADO','COMPROBADO','VALIDADO','CONFIRMADO MT5','RESERVA CALCULADA','YA VIGENTE') else RED if state in ('BLOQUEADO','RECHAZADO','DESACTUALIZADA') else AMBER
            cell.configure(fg=color)
            attach_tooltip(cell,stage['name']+' · '+state+'\n'+stage['detail'])
        cycle=check.get('cycle')
        if cycle is not None and cycle!=self.last_cycle:
            self.activity=not self.activity;self.last_cycle=cycle
            self.pulse.configure(fg=CYAN if self.activity else BLUE)

def label(parent,text='',color=TEXT,size=10,bold=False,**kw):
    wrapped=bool(kw.get('wraplength'))
    widget=tk.Label(parent,text=text,bg=parent.cget('bg'),fg=color,
        font=(FONT,max(7,round(size*STUDIO_FONT_SCALE/100)),'bold' if bold else 'normal'),**kw)
    if wrapped:responsive_wrap(widget)
    return widget

def responsive_wrap(widget,padding=4):
    """Use the granted width, not an old 650px request inside a 200px pane."""
    pending=[None];target=[None];closed=[False]
    def apply():
        pending[0]=None
        if closed[0] or target[0] is None:return
        try:
            if abs(int(float(widget.cget('wraplength') or 0))-target[0])>3:
                widget.configure(wraplength=target[0])
        except tk.TclError:pass
    def fit(event):
        if closed[0] or event.widget is not widget or event.width<30:return
        # Only a layout-constrained label may follow its granted width. A
        # centered label sized by its own text would otherwise shrink itself
        # again on every Configure until only one letter remained visible.
        try:
            manager=widget.winfo_manager()
            if manager=='pack' and widget.pack_info().get('fill') not in ('x','both'):return
            if manager=='grid' and not all(c in widget.grid_info().get('sticky','') for c in 'ew'):return
        except (AttributeError,tk.TclError):return
        target[0]=max(24,event.width-padding)
        # Reflow outside the current native Configure/idle pass. In Win32 an
        # immediate geometry change can continuously refill update()'s queue.
        if pending[0] is None:pending[0]=widget.after(16,apply)
    def destroy(event):
        if event.widget is not widget:return
        closed[0]=True
        if pending[0] is not None:
            try:widget.after_cancel(pending[0])
            except tk.TclError:pass
            pending[0]=None
    widget.bind('<Configure>',fit,add='+')
    widget.bind('<Destroy>',destroy,add='+')
    return widget

def button(parent,text,command,color=CYAN,primary=False):
    primary=primary or color==GREEN or text in ('ENVIAR','ACTUALIZAR AHORA','GUARDAR AJUSTES','INICIAR')
    widget=tk.Button(parent,text=text,command=command,bg=BLUE if primary else CARD,
        fg=TEXT if primary else color,activebackground='#13536e',activeforeground=TEXT,
        disabledforeground=MUTED,font=(FONT,max(8,round(9*STUDIO_FONT_SCALE/100)),'bold'),relief='flat',bd=0,
        highlightthickness=1,highlightbackground=CYAN if primary else LINE,
        highlightcolor=CYAN,padx=13,pady=9,cursor='hand2')
    if text in ('☎','◉','×','⊘','♪') and hasattr(widget,'tk'):
        try:
            from PIL import Image,ImageDraw,ImageTk
            bitmap=Image.new('RGBA',(22,22));draw=ImageDraw.Draw(bitmap);ink=color
            if text=='☎':
                draw.line([(4,3),(3,7),(5,12),(10,17),(15,19),(19,17)],fill=ink,width=3)
                draw.line([(3,3),(7,5)],fill=ink,width=4);draw.line([(16,14),(19,18)],fill=ink,width=4)
            elif text=='◉':draw.ellipse((2,6,20,16),outline=ink,width=2);draw.ellipse((8,8,14,14),fill=ink)
            elif text=='×':draw.line((5,5,17,17),fill=ink,width=2);draw.line((5,17,17,5),fill=ink,width=2)
            elif text=='⊘':draw.ellipse((3,3,19,19),outline=ink,width=2);draw.line((5,17,17,5),fill=ink,width=2)
            else:draw.polygon([(3,9),(7,9),(12,5),(12,17),(7,13),(3,13)],fill=ink);draw.arc((9,5,19,17),-65,65,fill=ink,width=2)
            widget._akira_icon=ImageTk.PhotoImage(bitmap,master=widget);widget.configure(image=widget._akira_icon,compound='none',width=34,height=26)
        except Exception:pass
    attach_tooltip(widget,help_for(text))
    widget.bind('<Enter>',lambda e:widget.configure(bg='#133f58'),add='+')
    widget.bind('<Leave>',lambda e:widget.configure(bg=BLUE if primary else CARD),add='+')
    return widget

def help_for(text):
    text=str(text)
    specific={'GUARDAR AJUSTES':'Valida y aplica los cambios. Confirma cuáles recibieron la interfaz y el motor.',
      'DESCARGAR TODAS LAS VOCES':'Descarga el catálogo completo en segundo plano. Puede ocupar varios GB; permite cancelar y reintentar.',
      'PAUSAR CONTROL':'Suspende nuevas acciones del motor. Las órdenes y sus protecciones existentes siguen en MT5.',
      'REANUDAR GESTIÓN':'Reanuda las acciones autorizadas por la configuración y los límites de riesgo.',
      'BORRAR CACHÉ':'Revisa primero el espacio recuperable. Conserva conversaciones, recuerdos y datos de trading.',
      'VERIFICAR CONEXIÓN':'Comprueba autenticación y lista de modelos. No genera una respuesta API ni verifica saldo.',
      'RESTABLECER PANELES':'Recupera los tamaños iniciales de los paneles; no cambia operaciones ni ajustes financieros.',
      'ELIMINAR':'Envía esta conversación a la papelera para permitir recuperarla.',
      'PAPELERA':'Recupera conversaciones eliminadas.',
      '×':'Cierra este aviso. El mensaje permanece en el centro de notificaciones.',
      '♪':'Silencia el audio de las notificaciones. Puedes reactivarlo en Ajustes.',
      '⊘':'Oculta los avisos emergentes y silencia su audio; el historial permanece disponible.',
      '☎':'Abre la llamada: elige voz, micrófono y salida antes de iniciarla.'}
    specific['VERIFICAR']='Abre la evidencia de la pendiente seleccionada y solicita una revisión de sus niveles exactos, sin enviar ni modificar órdenes.'
    specific['◉']='Muestra u oculta los datos de cuenta. Tu elección se conserva hasta que vuelvas a cambiarla.'
    if text in specific:return specific[text]
    if 'INFORME' in text or text in ('PDF','EXCEL'):return 'Elige período, formato y destino para descargar el informe de datos del motor.'
    if 'MAPA' in text or 'PENDIENTES' in text:return 'Revisa el mapa. Cualquier envío requiere permiso de ejecución, riesgo disponible y confirmación MT5.'
    return text.strip(' +').capitalize()+'.'

def attach_tooltip(widget,text):
    widget._akira_tooltip_text=text
    if getattr(widget,'__dict__',{}).get('_akira_tooltip_bound'):return
    widget._akira_tooltip_bound=True
    pending=[None];window=[None]
    def close(event=None):
        if pending[0] is not None:
            try:widget.after_cancel(pending[0])
            except (AttributeError,tk.TclError):pass
            pending[0]=None
        if window[0] is not None:
            try:window[0].destroy()
            except tk.TclError:pass
            window[0]=None
    def show():
        pending[0]=None
        try:
            win=tk.Toplevel(widget);win.overrideredirect(True);win.configure(bg=LINE);window[0]=win
            label(win,widget._akira_tooltip_text,TEXT,9,wraplength=320,justify='left',padx=10,pady=8).pack(padx=1,pady=1)
            win.update_idletasks();x=min(widget.winfo_rootx(),win.winfo_screenwidth()-win.winfo_reqwidth()-12)
            y=min(widget.winfo_rooty()+widget.winfo_height()+8,win.winfo_screenheight()-win.winfo_reqheight()-45)
            win.geometry('+%d+%d'%(max(6,x),max(6,y)))
        except (AttributeError,tk.TclError):pass
    def enter(event=None):close();pending[0]=widget.after(450,show)
    widget.bind('<Enter>',enter,add='+');widget.bind('<Leave>',close,add='+');widget.bind('<ButtonPress>',close,add='+');widget.bind('<Destroy>',close,add='+')

def confirm_dialog(root,title,text):
    win=tk.Toplevel(root);win.title('AKIRA · '+title);win.configure(bg=BG);win.transient(root)
    from windows_identity import apply_window_icon
    apply_window_icon(win);answer=[False]
    outer,body=neon_card(win,title);outer.pack(fill='both',expand=True,padx=14,pady=14)
    label(body,text,TEXT,10,wraplength=470,justify='left').pack(pady=10)
    bar=tk.Frame(body,bg=PANEL);bar.pack(fill='x',pady=8)
    def accept():answer[0]=True;win.destroy()
    button(bar,'CANCELAR',win.destroy,MUTED).pack(side='left');button(bar,'CONFIRMAR',accept,GREEN).pack(side='right')
    win.grab_set();root.wait_window(win);return answer[0]

def rounded_rect(canvas,x1,y1,x2,y2,r=12,**kw):
    points=(x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,
        x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1)
    return canvas.create_polygon(points,smooth=True,splinesteps=12,**kw)

def neon_card(parent,title='',accent=None,padx=16,pady=12):
    accent=accent or CYAN
    outer=tk.Frame(parent,bg=parent.cget('bg'),bd=0)
    canvas=tk.Canvas(outer,bg=parent.cget('bg'),bd=0,highlightthickness=0)
    canvas.place(x=0,y=0,relwidth=1,relheight=1)
    inner=tk.Frame(outer,bg=PANEL,padx=padx,pady=pady)
    inner.pack(fill='both',expand=True,padx=3,pady=3)
    def paint(event):
        if event.width<8 or event.height<8:return
        size=(event.width,event.height)
        if getattr(canvas,'_painted_size',None)==size:return
        canvas._painted_size=size
        canvas.delete('all')
        rounded_rect(canvas,1,1,event.width-1,event.height-1,12,fill=PANEL,outline=LINE,width=1)
        canvas.create_line(16,2,70,2,fill=accent,width=2)
        # Lightweight futuristic geometry: only rebuilt on actual resize.
        # No video/render timer or GPU shader on the trading hot path.
        if STUDIO_GLOW>=20:
            segment=min(96,max(25,event.width//5))
            canvas.create_line(event.width-segment-17,2,event.width-18,2,fill=accent,width=1)
            canvas.create_line(4,event.height-23,4,event.height-12,fill=accent,width=2)
        if STUDIO_TEXTURE=='Circuit':
            canvas.create_line(event.width-70,4,event.width-58,11,event.width-20,11,fill=LINE,width=1)
            canvas.create_oval(event.width-24,9,event.width-20,13,fill=accent,outline='')
        elif STUDIO_TEXTURE=='Nebula':
            canvas.create_arc(event.width-82,5,event.width+8,90,start=42,extent=110,outline=LINE,style='arc')
        elif STUDIO_TEXTURE=='Neon grid':
            canvas.create_line(12,event.height-4,45,event.height-4,fill=LINE,width=1)
            canvas.create_line(event.width-42,event.height-4,event.width-16,event.height-4,fill=LINE,width=1)
    canvas.bind('<Configure>',paint)
    if title:
        head=tk.Frame(inner,bg=PANEL);head.pack(fill='x',pady=(0,10))
        label(head,title,TEXT,10,True,anchor='w',justify='left',wraplength=400).pack(side='left',fill='x',expand=True)
        tk.Frame(inner,bg=LINE,height=1).pack(fill='x',pady=(0,8))
    return outer,inner

def text_box(parent,height=8):
    return tk.Text(parent,height=height,width=1,bg=PANEL,fg=TEXT,insertbackground=CYAN,
        selectbackground='#123e58',selectforeground=TEXT,highlightthickness=0,bd=0,
        relief='flat',wrap='word',font=(FONT,max(8,round(10*STUDIO_FONT_SCALE/100))),padx=16,pady=12,spacing3=5)

def configure_style(root):
    global FONT,MONO
    try:
        from tkinter import font
        families={f.casefold():f for f in font.families(root)}
        FONT=next((families[f.casefold()] for f in (FONT,'Segoe UI','DejaVu Sans','Helvetica','Arial') if f.casefold() in families),FONT)
        MONO=next((families[f.casefold()] for f in (MONO,'Consolas','DejaVu Sans Mono','Courier') if f.casefold() in families),MONO)
    except (AttributeError,tk.TclError):pass
    def focused(event):
        widget=event.widget;generation=getattr(widget,'_focus_generation',0)+1;widget._focus_generation=generation
        widget._focus_jobs=[]
        for n,color in enumerate(('#244e65','#266e87','#279fb0',CYAN)):
            def paint(c=color,g=generation,w=widget):
                try:
                    if getattr(w,'_focus_generation',None)==g:w.configure(highlightcolor=c)
                except (AttributeError,tk.TclError):pass
            widget._focus_jobs.append(widget.after(n*28,paint))
    def unfocused(event):
        widget=event.widget;widget._focus_generation=getattr(widget,'_focus_generation',0)+1
        for job in getattr(widget,'_focus_jobs',[]):
            try:widget.after_cancel(job)
            except tk.TclError:pass
        widget._focus_jobs=[]
    try:root.bind_class('Entry','<FocusIn>',focused,add='+');root.bind_class('Entry','<FocusOut>',unfocused,add='+');root.bind_class('Entry','<Destroy>',unfocused,add='+')
    except (AttributeError,tk.TclError):pass
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('.',font=(FONT,10),background=PANEL,foreground=TEXT)
    for name in ('Vertical.TScrollbar','Horizontal.TScrollbar','Akira.Vertical.TScrollbar'):
        style.configure(name,background='#1a4a62',troughcolor=BG,bordercolor=BG,
            arrowcolor=MUTED,lightcolor='#1a4a62',darkcolor='#1a4a62',borderwidth=0,width=10)
        style.map(name,background=[('active',BLUE),('pressed',CYAN)])
    style.configure('TNotebook',background=BG,borderwidth=0,tabmargins=(4,4,4,0),bordercolor=BG,lightcolor=BG,darkcolor=BG)
    style.configure('TNotebook.Tab',background=PANEL,foreground=MUTED,
        padding=(14,9),font=(FONT,9,'bold'),borderwidth=0,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE)
    style.map('TNotebook.Tab',background=[('selected','#124361')],foreground=[('selected',TEXT)])
    # Keep the native Notebook API and keyboard navigation; sidebar owns its tabs.
    style.layout('Cyber.TNotebook.Tab',[])
    style.configure('Cyber.TNotebook',background=BG,borderwidth=0,bordercolor=BG,lightcolor=BG,darkcolor=BG)
    try:
        from tkinter import font as tkfont
        row_height=max(34,tkfont.Font(root,family=FONT,size=9).metrics('linespace')+12)
    except (AttributeError,tk.TclError):row_height=34
    style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,
        rowheight=row_height,font=(FONT,9),borderwidth=0,bordercolor=LINE,relief='flat')
    style.configure('Treeview.Heading',background='#102f47',foreground=MUTED,
        font=(FONT,8,'bold'),padding=(6,9),borderwidth=0,relief='flat')
    style.layout('Treeview.Heading',[('Treeheading.cell',{'sticky':'nswe'}),
        ('Treeheading.padding',{'sticky':'nswe','children':[('Treeheading.text',{'sticky':'we'})]})])
    style.map('Treeview',background=[('selected','#14405b')],foreground=[('selected',TEXT)])
    style.layout('Treeview',[('Treeview.treearea',{'sticky':'nswe'})])
    style.map('Treeview.Heading',background=[('active','#164159')])
    style.configure('Akira.TCombobox',fieldbackground=CARD,background=CARD,
        foreground=TEXT,arrowcolor=CYAN,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,
        padding=7,font=(FONT,9),borderwidth=1)
    style.map('Akira.TCombobox',fieldbackground=[('readonly',CARD)],
        foreground=[('readonly',TEXT),('disabled',MUTED)],selectbackground=[('readonly',CARD)],
        selectforeground=[('readonly',TEXT)])
    style.map('Akira.TCombobox',bordercolor=[('focus',CYAN),('active',BLUE)])
    style.configure('TScale',background=PANEL,troughcolor='#173e52',bordercolor=LINE,lightcolor=CYAN,darkcolor=BLUE)
    style.configure('Akira.TCheckbutton',background=PANEL,foreground=TEXT,font=(FONT,10))
    style.configure('Cyber.Horizontal.TProgressbar',troughcolor='#112f43',background=CYAN,
        lightcolor=CYAN,darkcolor=CYAN,bordercolor=PANEL,borderwidth=0,thickness=6)
    for option,value in {'*Entry.background':CARD,'*Entry.foreground':TEXT,
        '*Entry.insertBackground':CYAN,'*Entry.relief':'flat','*Entry.borderWidth':0,
        '*Entry.highlightThickness':1,'*Entry.highlightBackground':LINE,
        '*Entry.highlightColor':CYAN,'*Listbox.borderWidth':0,'*Listbox.highlightThickness':0,
        '*TCombobox*Listbox.background':CARD,'*TCombobox*Listbox.foreground':TEXT,
        '*TCombobox*Listbox.selectBackground':'#14405b','*TCombobox*Listbox.selectForeground':CYAN}.items():
        root.option_add(option,value)
    return FONT,MONO

def toggle(parent,variable,title,hint=''):
    row=tk.Frame(parent,bg=PANEL);row.pack(fill='x',pady=10)
    canvas=tk.Canvas(row,width=46,height=25,bg=PANEL,bd=0,highlightthickness=0,cursor='hand2')
    canvas.pack(side='right',padx=(12,2))
    copy=tk.Frame(row,bg=PANEL);copy.pack(side='left',fill='x',expand=True)
    caption=label(copy,title,TEXT,10,True,anchor='w',justify='left',wraplength=640);caption.pack(fill='x')
    # label() owns the caption's wrap width, including narrow/high-DPI panes.
    if hint:label(copy,hint,MUTED,8,anchor='w',justify='left',wraplength=660).pack(fill='x',pady=(5,0))
    def draw(*args):
        on=bool(variable.get());canvas.delete('all')
        rounded_rect(canvas,1,2,45,24,11,fill='#0d819b' if on else '#294056',outline=LINE)
        x=33 if on else 13;canvas.create_oval(x-8,5,x+8,21,fill='#83f3ff' if on else MUTED,outline='')
    def change(event=None):variable.set(not variable.get());draw()
    canvas.bind('<Button-1>',change);canvas.bind('<space>',change)
    attach_tooltip(canvas,hint or title)
    try:variable.trace_add('write',draw);draw()
    except (AttributeError,tk.TclError):pass
    tk.Frame(parent,bg=LINE,height=1).pack(fill='x',pady=(2,4))
    return row

def ask_text(root,title,prompt,initial='',numeric=False):
    """Branded modal form instead of the default grey Tk simpledialog."""
    from windows_identity import apply_window_icon
    win=tk.Toplevel(root);win.title('AKIRA · '+title);win.configure(bg=BG)
    apply_window_icon(win);win.resizable(False,False);win.transient(root)
    result=[None];outer,body=neon_card(win,title.upper());outer.pack(fill='both',expand=True,padx=14,pady=14)
    label(body,prompt,MUTED,10,anchor='w',wraplength=390,justify='left').pack(fill='x',pady=6)
    value=tk.StringVar(value=str(initial));entry=tk.Entry(body,textvariable=value,font=(FONT,11),width=38)
    entry.pack(fill='x',ipady=9,pady=8);error=label(body,'',RED,9,anchor='w');error.pack(fill='x')
    bar=tk.Frame(body,bg=PANEL);bar.pack(fill='x',pady=(8,0))
    def accept(event=None):
        try:answer=float(value.get().replace(',','.')) if numeric else value.get().strip()
        except ValueError:error.configure(text='Escribe un número válido.');return
        result[0]=answer;win.destroy()
    button(bar,'CANCELAR',win.destroy,MUTED).pack(side='left')
    button(bar,'GUARDAR',accept,GREEN).pack(side='right')
    entry.bind('<Return>',accept);win.bind('<Escape>',lambda e:win.destroy())
    win.update_idletasks();win.geometry('+%d+%d'%(root.winfo_rootx()+max(0,(root.winfo_width()-win.winfo_reqwidth())//2),root.winfo_rooty()+max(0,(root.winfo_height()-win.winfo_reqheight())//2)))
    win.grab_set();entry.focus_set();entry.selection_range(0,'end');root.wait_window(win)
    return result[0]
