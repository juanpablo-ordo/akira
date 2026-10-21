"""Resizable Tk panes, with monitor-independent saved divider positions."""
from pathlib import Path
import json,math,tkinter as tk
from tkinter import ttk

def valid_ratios(value,count):
    if not isinstance(value,(tuple,list)) or len(value)!=max(0,count-1):return None
    if not all(isinstance(x,(int,float)) and math.isfinite(x) and .02<=x<=.98 for x in value):return None
    if any(b-a<.03 for a,b in zip(value,value[1:])):return None
    return tuple(float(x) for x in value)

def fitted_geometry(width,height,screen_width,screen_height):
    """Keep the entire window on screen, including high-DPI laptop displays."""
    usable_w=max(320,int(screen_width)-32);usable_h=max(260,int(screen_height)-80)
    width=max(min(960,usable_w),min(int(width),usable_w))
    height=max(min(600,usable_h),min(int(height),usable_h))
    return width,height,min(900,usable_w),min(580,usable_h)

class PanelLayout:
    def __init__(self,root,path):
        self.root,self.path=root,Path(path);self.saved={};self.widgets={};self.pending=None;self.restore_jobs={};self.dragging=set();self._restoring=set();self._base_minimums={}
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(data,dict) and data.get('schema')==1 and isinstance(data.get('panels'),dict):self.saved=data['panels']
        except (OSError,ValueError):pass

    def pane(self,parent,key,orient=tk.HORIZONTAL,ratios=(.5,)):
        p=tk.PanedWindow(parent,orient=orient,bg='#061022',bd=0,sashwidth=10,sashpad=2,
            showhandle=True,handlesize=8,handlepad=10,opaqueresize=True,
            sashcursor='sb_h_double_arrow' if orient==tk.HORIZONTAL else 'sb_v_double_arrow')
        self.widgets[key]=(p,orient,tuple(ratios));p._layout_key=key
        p.bind('<Map>',lambda event:self.queue_restore(key),add='+')
        # Never restore a saved sash position while the user is dragging it.
        # Reapplying on every Configure caused jitter and panes that fought the mouse.
        p.bind('<Configure>',lambda event:self.queue_restore(key),add='+')
        p.bind('<ButtonPress-1>',lambda event:self.dragging.add(key),add='+')
        p.bind('<ButtonRelease-1>',lambda event:(self.dragging.discard(key),self.changed(key)),add='+')
        return p

    def queue_restore(self,key):
        if self.dragging or key in self._restoring:return
        pane=self.widgets[key][0]
        try:
            size=(pane.winfo_width(),pane.winfo_height(),tuple(map(str,pane.panes())))
        except tk.TclError:return
        if getattr(pane,'_akira_restored_size',None)==size:return
        old=self.restore_jobs.pop(key,None)
        if old is not None:
            try:self.root.after_cancel(old)
            except (tk.TclError,ValueError):pass
        def apply():
            self.restore_jobs.pop(key,None)
            if not self.dragging:self.restore(key)
        self.restore_jobs[key]=self.root.after(170,apply)

    def restore(self,key,defaults=False):
        if key in self._restoring or self.dragging:return
        p,orient,initial=self.widgets[key]
        self._restoring.add(key)
        try:
            count=len(p.panes())
            values=valid_ratios(self.saved.get(key),count) if not defaults else None
            values=values or valid_ratios(initial,count)
            # Detail sections can be toggled; use an even split until all panes
            # are visible instead of retaining an unusable divider count.
            values=values or tuple(i/count for i in range(1,count))
            extent=p.winfo_width() if orient==tk.HORIZONTAL else p.winfo_height()
            if not values or extent<50:return
            # A layout saved on a large monitor must not hide a panel on a
            # laptop. Keep a remembered natural minimum, scaling only when the
            # actual viewport cannot contain their sum.
            try:
                panes=p.panes();minimums=[]
                for pane in panes:
                    identity=(key,str(pane))
                    if identity not in self._base_minimums:
                        self._base_minimums[identity]=max(32,int(p.panecget(pane,'minsize')))
                    minimums.append(self._base_minimums[identity])
                free=max(count,extent-14*(count-1)-4)
                scale=min(1,free/max(1,sum(minimums)))
                fitted=[max(1,int(v*scale)) for v in minimums]
                for pane,minimum in zip(panes,fitted):p.paneconfigure(pane,minsize=minimum)
                positions=constrained_sashes(extent,values,fitted)
            except (AttributeError,TypeError,ValueError,tk.TclError):
                positions=[round(extent*value) for value in values]
            for i,position in enumerate(positions):
                x,y=p.sash_coord(i)
                p.sash_place(i,position if orient==tk.HORIZONTAL else x,
                             position if orient==tk.VERTICAL else y)
        except tk.TclError:pass
        finally:
            try:
                p._akira_restored_size=(p.winfo_width(),p.winfo_height(),tuple(map(str,p.panes())))
            except tk.TclError:pass
            self._restoring.discard(key)

    def changed(self,key):
        p,orient,_=self.widgets[key]
        try:
            extent=p.winfo_width() if orient==tk.HORIZONTAL else p.winfo_height()
            if extent<50:return
            values=[p.sash_coord(i)[0 if orient==tk.HORIZONTAL else 1]/extent for i in range(len(p.panes())-1)]
            if valid_ratios(values,len(p.panes())) is None:return
            self.saved[key]=values
            if self.pending is not None:self.root.after_cancel(self.pending)
            self.pending=self.root.after(350,self.save)
        except tk.TclError:pass

    def save(self):
        if self.pending is not None:
            try:self.root.after_cancel(self.pending)
            except tk.TclError:pass
        self.pending=None
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'schema':1,'panels':self.saved},indent=2)+'\n',encoding='utf-8')
            temporary.replace(self.path)
        except OSError:pass

    def reset(self):
        self.saved={}
        for key in self.widgets:self.restore(key,defaults=True)
        self.save()

def constrained_sashes(extent,ratios,minimums,gap=14):
    """Clamp old proportions so every pane stays reachable after resizing."""
    count=len(minimums);positions=[]
    for index,ratio in enumerate(ratios):
        lower=sum(minimums[:index+1])+gap*index
        upper=extent-sum(minimums[index+1:])-gap*(count-index-2)-gap
        if positions:lower=max(lower,positions[-1]+minimums[index]+gap)
        positions.append(max(lower,min(round(extent*ratio),max(lower,upper))))
    return positions

def scroll_frame(parent,bg):
    shell=tk.Frame(parent,bg=bg);shell.rowconfigure(0,weight=1);shell.columnconfigure(0,weight=1)
    canvas=tk.Canvas(shell,bg=bg,highlightthickness=0,width=210,height=120)
    bar=ttk.Scrollbar(shell,orient='vertical',command=canvas.yview,style='Akira.Vertical.TScrollbar')
    canvas.configure(yscrollcommand=bar.set);canvas.grid(row=0,column=0,sticky='nsew');bar.grid(row=0,column=1,sticky='ns')
    content=tk.Frame(canvas,bg=bg);window=canvas.create_window(0,0,window=content,anchor='nw')
    content._scroll_canvas=canvas;shell._scroll_canvas=canvas
    canvas._sync_pending=None
    def sync():
        pending=canvas._sync_pending
        canvas._sync_pending=None
        if pending is not None:
            try:canvas.after_cancel(pending)
            except tk.TclError:pass
        try:
            width=max(1,canvas.winfo_width());height=max(1,canvas.winfo_height())
            needed=max(height,content.winfo_reqheight())
            top=max(0,canvas.canvasy(0))
            signature=(width,height,needed)
            if getattr(canvas,'_sync_signature',None)==signature:return
            canvas._sync_signature=signature
            # Let Tk report the content's natural height. A fixed canvas-window
            # height suppresses Configure when children shrink and retains an
            # obsolete scroll region (the empty tail seen after reflow).
            if int(float(canvas.itemcget(window,'width') or 0))!=width:
                canvas.itemconfigure(window,width=width)
            canvas.configure(scrollregion=(0,0,width,needed))
            canvas.yview_moveto(min(top,max(0,needed-height))/needed)
            if getattr(canvas,'_wheel_job',None) is None:canvas._wheel_target=canvas.yview()[0]
        except tk.TclError:pass
    def schedule(event=None):
        if getattr(canvas,'_bounds_destroyed',False):return
        try:
            if not canvas.winfo_ismapped():return
        except tk.TclError:return
        # Batch resize requests into the next frame; never refill the same
        # idle pass indefinitely while native labels are still reflowing.
        if canvas._sync_pending is None:canvas._sync_pending=canvas.after(16,sync)
    def destroyed(event):
        if event.widget is not canvas:return
        canvas._bounds_destroyed=True
        for job in (canvas._sync_pending,getattr(canvas,'_wheel_job',None)):
            if job is not None:
                try:canvas.after_cancel(job)
                except tk.TclError:pass
        canvas._sync_pending=None;canvas._wheel_job=None
    content.bind('<Configure>',schedule)
    canvas.bind('<Configure>',schedule)
    canvas.bind('<Map>',schedule)
    canvas.bind('<Destroy>',destroyed,add='+')
    canvas._content=content;canvas._sync_content=sync
    canvas._schedule_sync=schedule
    # Tk mouse-wheel events from a Toplevel dialog never traverse the main
    # root's widget bindings. Bind once at application scope so the pointer
    # scrolls notification cards, settings dialogs, and every nested panel.
    # The wheel handler walks parent widgets and selects the nearest canvas.
    try:
        root=parent._root()  # one Tcl interpreter: avoid duplicate global bindings per Toplevel
        if not getattr(root,'_akira_wheel_dispatch_installed',False):
            root._akira_wheel_dispatch_installed=True
            for sequence in ('<MouseWheel>','<Button-4>','<Button-5>'):
                root.bind_all(sequence,wheel_over_panel,add='+')
    except (AttributeError,tk.TclError):pass
    # A child's requested height can change while the canvas window keeps the
    # same actual size. Observe descendant map/resize/destruction, too.
    try:
        root=parent._root()
        if not getattr(root,'_akira_scroll_bounds_bound',False):
            root._akira_scroll_bounds_bound=True
            def descendant_change(event):
                widget=event.widget
                while widget is not None:
                    owner=getattr(widget,'_scroll_canvas',None)
                    if owner is not None:
                        callback=getattr(owner,'_schedule_sync',None)
                        if callback:callback()
                        break
                    widget=getattr(widget,'master',None)
            for kind in ('<Configure>','<Map>','<Destroy>'):root.bind_all(kind,descendant_change,add='+')
    except (AttributeError,tk.TclError):pass
    return shell,content

def wheel_over_panel(event):
    """Find the nearest scrollable parent; never double-scroll a Text or Treeview."""
    widget=event.widget
    try:
        hovered=widget.winfo_containing(event.x_root,event.y_root)
        if hovered is not None:widget=hovered
    except (AttributeError,tk.TclError):pass
    try:
        if widget.winfo_class() in ('Text','Treeview','Listbox','TCombobox'):return
    except (AttributeError,tk.TclError):pass
    while widget is not None:
        canvas=getattr(widget,'_scroll_canvas',None)
        if canvas is not None:
            sync=getattr(canvas,'_sync_content',None)
            if callable(sync):sync()
            delta=getattr(event,'delta',0);num=getattr(event,'num',0)
            units=-1 if num==4 or delta>0 else 1 if num==5 or delta<0 else 0
            if units:
                amount=units*max(1,min(3,int(abs(delta)/120) or 1))
                if hasattr(canvas,'tk'):
                    try:
                        bounds=tuple(float(v) for v in str(canvas.cget('scrollregion')).split());total=max(1,bounds[-1]-bounds[1]);height=canvas.winfo_height()
                        start=canvas.yview()[0];target=min(max(0,1-height/total),max(0,getattr(canvas,'_wheel_target',start)+amount*max(30,height*.1)/total))
                        pending=getattr(canvas,'_wheel_job',None)
                        if pending is not None:canvas.after_cancel(pending)
                        canvas._wheel_target=target
                        def animate(n=1):
                            try:
                                progress=1-(1-n/7)**3;canvas.yview_moveto(start+(target-start)*progress)
                                canvas._wheel_job=canvas.after(12,lambda:animate(n+1)) if n<7 else None
                            except tk.TclError:pass
                        animate();return 'break'
                    except (AttributeError,IndexError,ValueError,tk.TclError):pass
                canvas.yview_scroll(amount,'units');return 'break'
        widget=getattr(widget,'master',None)


def bind_direct_scroll_subtree(parent, canvas):
    """Wheel support for pop-up cards and their labels (Windows/Linux).

    Tk child widgets may consume an event before the global 'all' bindtag.
    Binding on each newly rendered notification avoids relying on that path.
    Do not attach to Text, Listbox, combobox or other editable scroll widgets.
    Return 'break' so one movement produces only one scroll operation.
    """
    def direct_scroll(event):
        try:
            if not canvas.winfo_exists():
                return 'break'
            direction = (-1 if getattr(event, 'num',None)==4 or getattr(event,'delta',0)>0
                         else 1 if getattr(event,'num',None)==5 or getattr(event,'delta',0)<0 else 0)
            if direction:
                sync=getattr(canvas,'_sync_content',None)
                if callable(sync):sync()
                # No animation: notices must respond immediately and avoid
                # multiple queued GUI callbacks during rapid wheel scrolling.
                delta=abs(int(getattr(event,'delta',0) or 0))
                steps=min(6,max(1,delta//120)) if delta else 1
                canvas.yview_scroll(direction*steps*3,'units')
            return 'break'
        except tk.TclError:
            return 'break'

    def attach(widget):
        try:
            if widget.winfo_class() not in ('Text','Treeview','Listbox','TCombobox','Entry'):
                for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                    widget.bind(event,direct_scroll,add='+')
            for child in widget.winfo_children():
                attach(child)
        except tk.TclError:
            return
    attach(parent)


def add_table_scrollbars(root):
    """Reserve a horizontal rail wherever a table can exceed its panel width."""
    if not hasattr(root,'tk'):return
    for tree in list(_descendants(root)):
        if not isinstance(tree,ttk.Treeview) or tree.cget('xscrollcommand'):continue
        parent=tree.master;manager=tree.winfo_manager()
        if manager=='pack':
            bar=ttk.Scrollbar(parent,orient='horizontal',command=tree.xview)
            bar.pack(side='bottom',fill='x',before=tree)
        elif manager=='grid':
            geometry=tree.grid_info();row=int(geometry.get('row',0));column=int(geometry.get('column',0))
            bar=ttk.Scrollbar(parent,orient='horizontal',command=tree.xview)
            bar.grid(row=row+1,column=column,sticky='ew')
        elif manager=='panedwindow' and isinstance(parent,tk.PanedWindow):
            # Tk permits managing a child inside a descendant of its parent.
            # Keep the Treeview object and selection bindings intact.
            panes=[str(pane) for pane in parent.panes()];index=panes.index(str(tree))
            options={key:parent.panecget(tree,key) for key in ('minsize','stretch')}
            parent.forget(tree);wrapper=tk.Frame(parent,bg=parent.cget('bg'))
            if index<len(parent.panes()):options['before']=parent.panes()[index]
            parent.add(wrapper,**options)
            bar=ttk.Scrollbar(wrapper,orient='horizontal',command=tree.xview)
            bar.pack(side='bottom',fill='x');tree.pack(in_=wrapper,fill='both',expand=True)
        else:continue
        tree.configure(xscrollcommand=bar.set);tree._horizontal_scrollbar=bar


def _descendants(root):
    for child in root.winfo_children():
        yield child
        yield from _descendants(child)
