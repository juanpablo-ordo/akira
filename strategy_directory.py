"""User-facing strategy directory; UI reads cached evidence, never calls MT5."""
import copy,threading,tkinter as tk
from tkinter import ttk,filedialog
from pathlib import Path
from cyber_ui import BG,PANEL,CYAN,BLUE,AMBER,MUTED,TEXT,label,button,text_box
from strategy_lab import definitions,strategy_text,export_html

class StrategyDirectory:
 def open_strategy_directory(self):
  old=getattr(self,'strategy_window',None)
  if old and old.winfo_exists():old.lift();return
  win=self.service_dialog('Directorio de estrategias',1120,760);self.strategy_window=win
  note=label(win,'Generación y evaluación en segundo plano. Las hipótesis nuevas no operan automáticamente.',AMBER,10,wraplength=1050,anchor='w');note.pack(fill='x',padx=15,pady=4)
  controls=tk.Frame(win,bg=BG);controls.pack(fill='x',padx=15,pady=5)
  reference=label(win,'Video compartido: contenido pendiente de recuperar y comprobar.',MUTED,9,anchor='w',wraplength=1050);reference.pack(fill='x',padx=15)
  self.strategy_refresh_button=button(controls,'GENERAR Y EVALUAR AHORA',lambda:self.async_request({'action':'strategy_lab_refresh'},'Solicitada evaluación de estrategias en segundo plano'),CYAN);self.strategy_refresh_button.pack(side='left')
  self.strategy_export_button=button(controls,'DESCARGAR DIRECTORIO',self.download_strategy_directory,BLUE);self.strategy_export_button.pack(side='right')
  button(controls,'VER APRENDIZAJE',self.show_strategy_adaptation,BLUE).pack(side='left',padx=6)
  panes=tk.PanedWindow(win,orient=tk.HORIZONTAL,bg=BG,sashwidth=9,sashrelief=tk.RAISED);panes.pack(fill='both',expand=True,padx=15,pady=8)
  left=tk.Frame(panes,bg=PANEL);right=tk.PanedWindow(panes,orient=tk.VERTICAL,bg=BG,sashwidth=9);panes.add(left,minsize=280);panes.add(right,minsize=380)
  viewport=tk.Frame(left,bg=PANEL);viewport.pack(fill='both',expand=True)
  tree=ttk.Treeview(viewport,columns=('name','symbol','mode','n','state'),show='headings',style='Cyber.Treeview')
  for col,title,width in (('name','Estrategia',245),('symbol','Activo',92),('mode','Uso',90),('n','Cierres reales',95),('state','Evidencia',140)):
   tree.heading(col,text=title);tree.column(col,width=width,minwidth=55,stretch=False)
  bar=ttk.Scrollbar(viewport,orient='vertical',command=tree.yview,style='Akira.Vertical.TScrollbar');bar.pack(side='right',fill='y')
  tree.pack(side='left',fill='both',expand=True)
  horizontal=ttk.Scrollbar(left,orient='horizontal',command=tree.xview,style='Akira.Horizontal.TScrollbar');horizontal.pack(fill='x')
  tree.configure(yscrollcommand=bar.set,xscrollcommand=horizontal.set)
  details=tk.Frame(right,bg=PANEL);chart=tk.Frame(right,bg=PANEL);right.add(details,minsize=190);right.add(chart,minsize=140)
  scroll=ttk.Scrollbar(details,orient='vertical',style='Akira.Vertical.TScrollbar');scroll.pack(side='right',fill='y')
  box=text_box(details,12);box.pack(side='left',fill='both',expand=True);scroll.configure(command=box.yview);box.configure(yscrollcommand=scroll.set)
  image_label=label(chart,'Las imágenes se generan al detectar un caso con velas MT5 y niveles completos.',MUTED,10,wraplength=650)
  image_label.configure(width=1,height=1);image_label.pack(fill='both',expand=True,padx=8,pady=8)
  self.strategy_tree=tree;self.strategy_details=box;self.strategy_image_label=image_label;self._strategy_image_token=None
  rows={};selected=[None]
  resize_job=[None];render_job=[None];image_label._original=None;image_label._size_token=None
  def destroyed(event):
   if event.widget is not win:return
   # Cancel only Tcl timers; widgets own their registered Python callbacks.
   for job in (resize_job,render_job):
    if job[0] is not None:win.tk.call('after','cancel',job[0]);job[0]=None
  win.bind('<Destroy>',destroyed,add='+')
  def fit_image():
   resize_job[0]=None
   if not image_label.winfo_exists() or image_label._original is None:return
   size=(max(1,image_label.winfo_width()-6),max(1,image_label.winfo_height()-6))
   token=(id(image_label._original),size)
   if token==image_label._size_token:return
   from PIL import ImageTk
   im=image_label._original.copy();im.thumbnail(size);photo=ImageTk.PhotoImage(im)
   image_label.configure(image=photo,text='');image_label._photo=photo;image_label._size_token=token
  def resize(event=None):
   if resize_job[0] is not None:image_label.after_cancel(resize_job[0])
   resize_job[0]=image_label.after(60,fit_image)
  image_label.bind('<Configure>',resize)
  def show(event=None):
   choice=tree.selection();pid=choice[0] if choice else selected[0];item=rows.get(pid)
   if not item:return
   selected[0]=pid;row,symbol=item;shown=copy.deepcopy(row)
   if self.cfg.get('desktop',{}).get('privacy') and not self._account_revealed:
    for m in shown.get('symbols',{}).values():
     for k in ('net','expectancy','drawdown'):
      if k in m.get('realized',{}):m['realized'][k]='OCULTO'
   box.configure(state='normal');box.delete('1.0','end');box.insert('end',strategy_text(shown,symbol));box.configure(state='disabled')
   metric=(row.get('symbols') or {}).get(symbol) or {};path=metric.get('image_path');token=(pid,path,Path(path).stat().st_mtime_ns if path and Path(path).is_file() else None)
   if token!=self._strategy_image_token:
    self._strategy_image_token=token
    if path and Path(path).is_file():
     try:
      from PIL import Image
      with Image.open(path) as original:image_label._original=original.copy()
      image_label._size_token=None;resize()
     except OSError:image_label.configure(image='',text='La imagen se está actualizando; se reintentará.');image_label._original=None;self._strategy_image_token=None
    else:image_label.configure(image='',text='Aún no se detectó un ejemplo verificable con velas y Entrada/SL/TP para esta estrategia.');image_label._photo=None;image_label._original=None
  tree.bind('<<TreeviewSelect>>',show)
  def render():
   if not win.winfo_exists():return
   summary=(self.view.get('research') or {}).get('strategy_lab') or {}
   reference.configure(text='Video compartido: '+str(summary.get('reference',{}).get('state','CONTENIDO NO VERIFICADO'))+' · '+str(summary.get('reference',{}).get('note','')))
   note.configure(text=str(summary.get('state','ESPERANDO DATOS'))+' · '+str(summary.get('error') or summary.get('scope') or 'El motor necesita cotizaciones y velas actuales para generar y medir estrategias.'))
   current=summary.get('strategies') or definitions();symbols=list(self.view.get('symbols') or self.cfg['symbols']);chosen=tree.selection();keep=chosen[0] if chosen else selected[0]
   rows.clear();tree.delete(*tree.get_children())
   for row in current:
    for symbol in symbols:
     pid=row['id']+'/'+symbol;metric=(row.get('symbols') or {}).get(symbol) or {};n=(metric.get('realized') or {}).get('n',0)
     rows[pid]=(row,symbol);tree.insert('','end',iid=pid,values=(row['name'],symbol,row['mode'],n,metric.get('state','EN ESTUDIO')))
   if keep in rows:tree.selection_set(keep)
   elif rows:tree.selection_set(next(iter(rows)))
   show();render_job[0]=win.after(2000,render)
  render()
 def show_strategy_adaptation(self):
  from strategy_adaptation import report_text
  summary=((self.view.get('research') or {}).get('strategy_lab') or {}).get('adaptation') or {}
  win=self.service_dialog('Aprendizaje de estrategias',850,640)
  box=text_box(win,20);box.pack(fill='both',expand=True,padx=16,pady=12)
  scroll=ttk.Scrollbar(win,command=box.yview);scroll.pack(side='right',fill='y');box.configure(yscrollcommand=scroll.set)
  box.insert('end',report_text(summary));box.configure(state='disabled')
 def download_strategy_directory(self):
  summary=copy.deepcopy((self.view.get('research') or {}).get('strategy_lab') or {})
  destination=filedialog.askdirectory(parent=self.strategy_window,title='Guardar directorio de estrategias con sus imágenes')
  if not destination:return
  self.strategy_export_button.configure(state='disabled')
  def work():
   try:
    path=export_html(summary,Path(destination)/'Estrategias_AKIRA');self.replies.put({'strategy_export_result':{'ok':True,'path':path}})
   except Exception as exc:self.replies.put({'strategy_export_result':{'ok':False,'error':str(exc)}})
  threading.Thread(target=work,daemon=True,name='AkiraStrategyExport').start()
