"""Configurable AKIRA Studio pages; no dependency on MT5 actor."""
import copy,threading,queue,tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
from akira_studio import STATES,LOCALES,UI_LABELS,import_sprites,import_media,detect_expression,ordered_entries,suggested_sequences,import_language_pack,WallpaperPreview
from cyber_ui import BG,PANEL,CARD,CYAN,PINK,RED,GREEN,MUTED,TEXT,FONT,label,button,neon_card

LANG_NAMES={'es':'Español','en':'English','pt':'Português','fr':'Français','de':'Deutsch',
            'it':'Italiano','ja':'日本語','zh':'中文','ko':'한국어','ar':'العربية'}

class StudioControls:
    def __init__(self,app,tab,card,field,check):
        self.app=app;self.tab=tab;self.card=card;self.field=field;self.check=check
        self.asset_rows=copy.deepcopy(app.cfg['studio']['avatar'].get('entries') or [])
        self.sequences=copy.deepcopy(app.cfg['studio']['avatar'].get('sequences') or {})
        self._preview=None
        self.language_tab();self.style_tab();self.avatar_tab()
    def get(self,path):return self.app.setting_vars['studio.'+path].get()
    def set(self,path,value):self.app.setting_vars['studio.'+path].set(value)
    def selector(self,container,path,title,options):
        row=tk.Frame(container,bg=PANEL);row.pack(fill='x',pady=5)
        label(row,title,TEXT,10,True,anchor='w').pack(side='left',fill='x',expand=True)
        var=tk.StringVar(value=self.app.cfg['studio'].get(path,''))
        self.app.setting_vars['studio.'+path]=var;self.app.setting_types['studio.'+path]='str'
        ttk.Combobox(row,textvariable=var,values=options,state='normal' if path=='language_ui' else 'readonly',style='Akira.TCombobox',width=23).pack(side='right')
        return var
    def nested_selector(self,container,path,title,options):
        row=tk.Frame(container,bg=PANEL);row.pack(fill='x',pady=5)
        label(row,title,TEXT,10,True,anchor='w').pack(side='left',fill='x',expand=True)
        var=tk.StringVar(value=self.app.cfg['studio']['wallpaper'].get(path,''))
        self.app.setting_vars['studio.wallpaper.'+path]=var;self.app.setting_types['studio.wallpaper.'+path]='str'
        ttk.Combobox(row,textvariable=var,values=options,state='readonly',style='Akira.TCombobox',width=20).pack(side='right')
        return var
    def language_tab(self):
        t=self.tab('IDIOMA Y VOZ')
        c=self.card(t,'IDIOMAS DEL PROGRAMA',CYAN)
        label(c,'Idiomas incluidos para navegación y encabezados. Las pantallas técnicas heredadas mantienen algunos textos originales hasta completar su traducción.',MUTED,9,anchor='w',wraplength=600,justify='left').pack(fill='x',pady=7)
        for key,title in [('language_ui','Idioma de la interfaz'),('language_chat','Idioma del chat'),('language_voice_in','Idioma de reconocimiento (STT)'),('language_voice_out','Idioma de respuesta hablada (TTS)')]:
            self.selector(c,key,title,('auto',*LOCALES) if key!='language_ui' else LOCALES)
        self.field(c,'studio.language_pack','Paquete de traducción JSON (opcional)','str',
                   'Permite añadir traducciones estáticas para cualquier código de idioma compatible.')
        button(c,'IMPORTAR PAQUETE DE IDIOMA',self.choose_language_pack,CYAN).pack(fill='x',pady=5)
        label(c,'Formato: {"locale":"ru-RU","translations":{"AJUSTES":"Настройки"}}. Cambia al idioma importado al guardar y reiniciar.',MUTED,8,anchor='w',wraplength=620).pack(fill='x',pady=3)
        self.check(c,'studio.translate_input','Solicitar traducción de mensajes entrantes cuando el motor la permita')
        self.check(c,'studio.translate_output','Solicitar respuestas en el idioma elegido cuando el motor la permita')
        label(c,'La disponibilidad real de voz depende de los modelos y voces instalados; cambiar el idioma no instala voces automáticamente.',MUTED,9,anchor='w',wraplength=600,justify='left').pack(fill='x',pady=6)
        c=self.card(t,'IDIOMAS DISPONIBLES',PINK)
        label(c,', '.join(f'{LANG_NAMES[key]} ({key})' for key in LOCALES),TEXT,10,anchor='w',wraplength=620,justify='left').pack(fill='x',pady=5)
        button(c,'ABRIR CATÁLOGO DE VOCES',self.app.start_voice,CYAN).pack(fill='x',pady=8)
    def choose_language_pack(self):
        name=filedialog.askopenfilename(parent=self.app.root,filetypes=[('Paquete JSON','*.json')])
        if not name:return
        try:
            path,locale=import_language_pack(self.app.folder,name)
            self.set('language_pack',path)
            var=self.app.setting_vars['studio.language_ui']
            var.set(locale)
        except Exception as exc:messagebox.showerror('Paquete de idioma',str(exc),parent=self.app.root)

    def style_tab(self):
        t=self.tab('PERSONALIZACIÓN')
        c=self.card(t,'IDENTIDAD Y ESTILO VISUAL',CYAN)
        self.field(c,'studio.brand_name','Nombre visible del programa','str','Cambia la marca de la ventana y navegación, sin cambiar la identidad interna ni el identificador del instalador.')
        self.selector(c,'theme','Tema de paneles',('AKIRA Original','Nebulosa','Océano','Carbono'))
        self.field(c,'studio.accent','Color principal HEX (ej. #23ddf4)','str')
        self.field(c,'studio.secondary','Color secundario HEX (ej. #ed58cc)','str')
        self.field(c,'studio.font','Familia tipográfica instalada','str')
        self.field(c,'studio.font_scale','Escala tipográfica % (60–160)','int')
        self.field(c,'studio.glow','Intensidad de brillo visual (0–100)','int')
        self.selector(c,'panel_texture','Textura de panel',('Neon grid','Minimal','Circuit','Nebula'))
        label(c,'Los colores y fuentes se aplican en el próximo inicio para evitar un redibujado masivo mientras MT5 gestiona posiciones. AKIRA Original es siempre el valor inicial.',MUTED,9,wraplength=620,justify='left').pack(fill='x',pady=8)
        c=self.card(t,'FONDO PERSONALIZADO · IMAGEN / VIDEO',PINK)
        self.check(c,'studio.wallpaper.enabled','Activar fondo personalizado (apagado por defecto)')
        self.nested_selector(c,'kind','Origen',('default','image','video'))
        self.field(c,'studio.wallpaper.file','Archivo importado','str','Se copia a la carpeta privada de Studio al importar.')
        button(c,'IMPORTAR IMAGEN',lambda:self.choose_wallpaper('image'),CYAN).pack(fill='x',pady=4)
        button(c,'IMPORTAR VIDEO',lambda:self.choose_wallpaper('video'),CYAN).pack(fill='x',pady=4)
        self.nested_selector(c,'fit','Ajuste / recorte',('cover','contain','stretch'))
        self.field(c,'studio.wallpaper.rotation','Girar (0, 90, 180 o 270)','int')
        self.field(c,'studio.wallpaper.offset_x','Recorte horizontal (-100 izquierda, +100 derecha)','int')
        self.field(c,'studio.wallpaper.offset_y','Recorte vertical (-100 arriba, +100 abajo)','int')
        self.field(c,'studio.wallpaper.opacity','Visibilidad del fondo %','int')
        self.field(c,'studio.wallpaper.fps','Cuadros por segundo 1–30','int')
        self.field(c,'studio.wallpaper.quality','Calidad de representación 20–100','int')
        self.field(c,'studio.wallpaper.max_memory_mb','Presupuesto orientativo de memoria MB','int')
        self.field(c,'studio.wallpaper.max_cpu_percent','Presupuesto orientativo de CPU %','int')
        self.wallpaper_canvas=tk.Canvas(c,width=480,height=245,bg=BG,bd=0,highlightthickness=1,highlightbackground=CYAN)
        self.wallpaper_canvas.pack(fill='x',pady=7)
        self.wallpaper_canvas.bind('<Destroy>',lambda e:self._preview.stop() if self._preview else None,add='+')
        button(c,'VISTA PREVIA DEL FONDO',self.preview_wallpaper,CYAN).pack(fill='x',pady=4)
        label(c,'Vista previa real de la imagen o el video; el diseño de AKIRA continúa siendo el fondo predeterminado. El video se pausa al ocultar la vista previa.',MUTED,9,wraplength=600,justify='left').pack(fill='x')
    def choose_wallpaper(self,kind):
        types=[('Archivos de imagen','*.png *.jpg *.jpeg *.webp *.gif')] if kind=='image' else [('Archivos de video','*.mp4 *.webm *.mov *.mkv')]
        name=filedialog.askopenfilename(parent=self.app.root,filetypes=types)
        if not name:return
        try:
            target=import_media(self.app.folder,name,kind)
            self.set('wallpaper.file',target);self.set('wallpaper.kind',kind);self.app.setting_vars['studio.wallpaper.enabled'].set(True)
            self.preview_wallpaper()
        except Exception as exc:messagebox.showerror('Importar fondo',str(exc),parent=self.app.root)
    def preview_wallpaper(self):
        keys=('file','fit','rotation','offset_x','offset_y','opacity','fps','quality','kind','max_memory_mb','max_cpu_percent')
        config={k:self.get('wallpaper.'+k) for k in keys}
        if self._preview:self._preview.stop()
        self._preview=WallpaperPreview(self.wallpaper_canvas,config);self._preview.start()
    def avatar_tab(self):
        t=self.tab('AVATAR STUDIO')
        c=self.card(t,'AVATAR PERSONALIZADO · SPRITES',CYAN)
        self.check(c,'studio.avatar.active','Usar sprites del usuario en todas las pantallas')
        label(c,'Importa PNG, WebP, JPEG o GIF. AKIRA reconoce etiquetas del nombre y pistas visuales entre fotogramas; permite corregir el estado, separar hojas, ordenar cuadros y crear secuencias. Estados sin imagen usan el avatar original.',MUTED,9,anchor='w',justify='left',wraplength=620).pack(fill='x',pady=8)
        button(c,'IMPORTAR SPRITES',self.choose_sprites,CYAN).pack(fill='x',pady=5)
        grid_options=tk.Frame(c,bg=PANEL);grid_options.pack(fill='x',pady=4)
        label(grid_options,'Hoja de sprites: filas',MUTED,9).pack(side='left')
        self.sheet_rows=tk.StringVar(value='0')
        tk.Entry(grid_options,textvariable=self.sheet_rows,width=4,bg=CARD,fg=TEXT).pack(side='left',padx=6)
        label(grid_options,'columnas',MUTED,9).pack(side='left')
        self.sheet_cols=tk.StringVar(value='0')
        tk.Entry(grid_options,textvariable=self.sheet_cols,width=4,bg=CARD,fg=TEXT).pack(side='left',padx=6)
        label(c,'0 / 0 = detección automática de casillas separadas por transparencia. Para hojas sin separadores, indica filas y columnas.',MUTED,8,wraplength=610,justify='left').pack(fill='x')
        box=tk.Frame(c,bg=PANEL);box.pack(fill='both',expand=True)
        self.sprite_list=tk.Listbox(box,height=12,bg=CARD,fg=TEXT,selectbackground='#14597a',highlightthickness=0,font=(FONT,10),exportselection=False)
        self.sprite_list.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(box,command=self.sprite_list.yview);scroll.pack(side='right',fill='y');self.sprite_list.config(yscrollcommand=scroll.set)
        self.sprite_list.bind('<<ListboxSelect>>',lambda e:self.sprite_detail())
        self._drag_sprite_index=None
        self.sprite_list.bind('<ButtonPress-1>',lambda e:setattr(self,'_drag_sprite_index',self.sprite_list.nearest(e.y)))
        self.sprite_list.bind('<ButtonRelease-1>',self.drop_sprite)
        self._sprite_refresh()
        tools=tk.Frame(c,bg=PANEL);tools.pack(fill='x',pady=8)
        for title,command in (('SUBIR',lambda:self.shift_sprite(-1)),('BAJAR',lambda:self.shift_sprite(1)),('ELIMINAR',self.delete_sprite)):
            button(tools,title,command,CYAN if title!='ELIMINAR' else RED).pack(side='left',padx=(0,6))
        row=tk.Frame(c,bg=PANEL);row.pack(fill='x')
        label(row,'Estado detectado / asignación',TEXT,10).pack(side='left',padx=(0,8))
        self.sprite_state=tk.StringVar(value='idle')
        state_choice=ttk.Combobox(row,textvariable=self.sprite_state,values=STATES,state='readonly',style='Akira.TCombobox',width=19)
        state_choice.pack(side='left');state_choice.bind('<<ComboboxSelected>>',lambda e:self.assign_state())
        self.sprite_note=label(c,'Selecciona un cuadro para editarlo',MUTED,9,anchor='w',wraplength=620)
        self.sprite_note.pack(fill='x',pady=4)
        c=self.card(t,'SECUENCIAS Y REPRODUCCIÓN',PINK)
        label(c,'Selecciona una expresión; configura la velocidad de su secuencia. Si tiene varios cuadros, el avatar los reproduce mientras permanece en ese estado.',MUTED,9,anchor='w',wraplength=600,justify='left').pack(fill='x',pady=7)
        row=tk.Frame(c,bg=PANEL);row.pack(fill='x',pady=5)
        self.seq_state=tk.StringVar(value='talking')
        ttk.Combobox(row,textvariable=self.seq_state,values=STATES,state='readonly',style='Akira.TCombobox',width=18).pack(side='left')
        label(row,'Duración / cuadro (ms)',TEXT,9).pack(side='left',padx=9)
        self.seq_delay=tk.StringVar(value='180')
        tk.Entry(row,textvariable=self.seq_delay,bg=CARD,fg=TEXT,insertbackground=CYAN,width=8).pack(side='left')
        button(c,'CREAR / ACTUALIZAR SECUENCIA',self.update_sequence,GREEN).pack(fill='x',pady=6)
        self.seq_info=label(c,'Sin cambios pendientes',MUTED,9,anchor='w',wraplength=600);self.seq_info.pack(fill='x')
        c=self.card(t,'PREVISUALIZAR Y RESTABLECER',CYAN)
        self.avatar_preview=tk.Canvas(c,width=300,height=240,bg=CARD,highlightbackground=CYAN,highlightthickness=1)
        self.avatar_preview.pack(fill='x',pady=5)
        self.avatar_preview_image=None
        button(c,'MOSTRAR SPRITE SELECCIONADO',self.show_sprite,CYAN).pack(fill='x',pady=4)
        button(c,'USAR AVATAR ORIGINAL',self.original_avatar,PINK).pack(fill='x',pady=4)
        label(c,'Guardar ajustes conserva los sprites y las secuencias. Los cambios de catálogo se aplican sin alterar posiciones ni órdenes de MT5.',MUTED,9,anchor='w',wraplength=600).pack(fill='x',pady=6)
    def choose_sprites(self):
        if getattr(self,'_sprite_import_busy',False):return
        paths=filedialog.askopenfilenames(parent=self.app.root,filetypes=[('Imágenes','*.png *.jpg *.jpeg *.webp *.gif')])
        if not paths:return
        try:
            rows=int(self.sheet_rows.get());cols=int(self.sheet_cols.get())
        except ValueError:
            messagebox.showerror('Sprites','Filas y columnas deben ser números enteros.',parent=self.app.root);return
        self._sprite_import_busy=True
        self.sprite_note.configure(text='Importando fotogramas sin bloquear la interfaz...')
        results=queue.Queue(maxsize=1)
        folder=self.app.folder;previous=copy.deepcopy(self.asset_rows)
        def read_assets():
            try:results.put((import_sprites(folder,paths,previous,rows=rows,columns=cols),None))
            except Exception as exc:results.put((None,str(exc)))
        threading.Thread(target=read_assets,daemon=True,name='AkiraSpriteImport').start()
        def collect():
            try:values,error=results.get_nowait()
            except queue.Empty:
                try:self.app.root.after(100,collect)
                except tk.TclError:pass
                return
            self._sprite_import_busy=False
            if error:
                messagebox.showerror('Sprites',error,parent=self.app.root);return
            self.asset_rows=values
            self.sequences=suggested_sequences(self.asset_rows,self.sequences)
            self._sprite_refresh()
            self.sprite_note.configure(text=f'{len(values)} fotogramas disponibles. Revisa etiquetas ambiguas y guarda ajustes.')
        self.app.root.after(100,collect)
    def _sprite_refresh(self,select=None):
        if not hasattr(self,'sprite_list'):return
        self.sprite_list.delete(0,'end')
        for n,r in enumerate(self.asset_rows):self.sprite_list.insert('end',f'{n+1:02d}  {r["state"].upper():12s}  {r["source_name"][:38]}')
        if select is not None and 0<=select<len(self.asset_rows):self.sprite_list.selection_set(select)
    def _selected(self):
        sel=self.sprite_list.curselection()
        return int(sel[0]) if sel else None
    def sprite_detail(self):
        idx=self._selected()
        if idx is None:return
        row=self.asset_rows[idx];self.sprite_state.set(row['state']);self.sprite_note.configure(text=f"Clasificación: {row.get('detected_by','manual')} · Confianza inicial: {float(row.get('confidence',0)):.0%}. Puedes corregir el estado.")
    def assign_state(self):
        i=self._selected()
        if i is not None:self.asset_rows[i]['state']=self.sprite_state.get();self.asset_rows[i]['detected_by']='usuario';self._sprite_refresh(i)
    def shift_sprite(self,delta):
        i=self._selected()
        if i is None:return
        j=i+delta
        if 0<=j<len(self.asset_rows):
            self.asset_rows[i],self.asset_rows[j]=self.asset_rows[j],self.asset_rows[i]
            self._sprite_refresh(j)
    def drop_sprite(self,event):
        origin=self._drag_sprite_index;self._drag_sprite_index=None
        if origin is None or not 0<=origin<len(self.asset_rows):return
        target=max(0,min(len(self.asset_rows)-1,self.sprite_list.nearest(event.y)))
        if target!=origin:
            sprite=self.asset_rows.pop(origin);self.asset_rows.insert(target,sprite)
            self._sprite_refresh(target)

    def delete_sprite(self):
        i=self._selected()
        if i is not None:self.asset_rows.pop(i);self._sprite_refresh()
    def show_sprite(self):
        i=self._selected()
        if i is None:return
        from PIL import Image,ImageTk
        with Image.open(self.asset_rows[i]['path']) as im:frame=im.convert('RGBA');frame.thumbnail((285,220))
        self.avatar_preview.delete('all');self.avatar_preview_image=ImageTk.PhotoImage(frame,master=self.avatar_preview)
        self.avatar_preview.create_image(155,120,image=self.avatar_preview_image)
    def original_avatar(self):
        self.app.setting_vars['studio.avatar.active'].set(False)
        self.seq_info.configure(text='Al guardar se restaurará el avatar original.')
    def update_sequence(self):
        state=self.seq_state.get();frames=[r['id'] for r in self.asset_rows if r['state']==state]
        try:delay=int(self.seq_delay.get());assert 80<=delay<=2000
        except (ValueError,AssertionError):self.seq_info.configure(text='Usa entre 80 y 2000 ms por cuadro.',fg=RED);return
        self.sequences[state]={'frames':frames,'delay_ms':delay,'loop':True}
        self.seq_info.configure(text=f'Secuencia {state}: {len(frames)} cuadro(s) · {delay} ms',fg=GREEN)
    def staged_avatar(self):
        rows=copy.deepcopy(self.asset_rows)
        for index,row in enumerate(rows):row['order']=index
        return {'entries':rows,'sequences':copy.deepcopy(self.sequences),'active':bool(self.app.setting_vars['studio.avatar.active'].get()),'profile':'default'}
