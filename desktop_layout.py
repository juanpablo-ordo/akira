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
    usable_w=max(600,int(screen_width)-32);usable_h=max(420,int(screen_height)-80)
    width=max(min(960,usable_w),min(int(width),usable_w))
    height=max(min(600,usable_h),min(int(height),usable_h))
    return width,height,min(900,usable_w),min(580,usable_h)

class PanelLayout:
    def __init__(self,root,path):
        self.root,self.path=root,Path(path);self.saved={};self.widgets={};self.pending=None;self.restore_jobs={};self.dragging=set()
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
        if key in self.dragging:return
        old=self.restore_jobs.pop(key,None)
        if old is not None:
            try:self.root.after_cancel(old)
            except (tk.TclError,ValueError):pass
        def apply():
            self.restore_jobs.pop(key,None)
            if key not in self.dragging:self.restore(key)
        self.restore_jobs[key]=self.root.after(170,apply)

    def restore(self,key,defaults=False):
        p,orient,initial=self.widgets[key]
        try:
            count=len(p.panes())
            values=valid_ratios(self.saved.get(key),count) if not defaults else None
            values=values or valid_ratios(initial,count)
            # Detail sections can be toggled; use an even split until all panes
            # are visible instead of retaining an unusable divider count.
            values=values or tuple(i/count for i in range(1,count))
            extent=p.winfo_width() if orient==tk.HORIZONTAL else p.winfo_height()
            if not values or extent<50:return
            for i,value in enumerate(values):
                x,y=p.sash_coord(i)
                p.sash_place(i,round(extent*value) if orient==tk.HORIZONTAL else x,
                             round(extent*value) if orient==tk.VERTICAL else y)
        except tk.TclError:pass

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

def scroll_frame(parent,bg):
    shell=tk.Frame(parent,bg=bg);shell.rowconfigure(0,weight=1);shell.columnconfigure(0,weight=1)
    canvas=tk.Canvas(shell,bg=bg,highlightthickness=0,width=210,height=120)
    bar=ttk.Scrollbar(shell,orient='vertical',command=canvas.yview,style='Akira.Vertical.TScrollbar')
    canvas.configure(yscrollcommand=bar.set);canvas.grid(row=0,column=0,sticky='nsew');bar.grid(row=0,column=1,sticky='ns')
    content=tk.Frame(canvas,bg=bg);window=canvas.create_window(0,0,window=content,anchor='nw')
    content._scroll_canvas=canvas;shell._scroll_canvas=canvas
    canvas._sync_pending=None
    def sync():
        canvas._sync_pending=None
        try:
            width=max(1,canvas.winfo_width());height=max(1,canvas.winfo_height())
            needed=max(height,content.winfo_reqheight())
            first=canvas.yview()[0]
            # Let Tk report the content's natural height. A fixed canvas-window
            # height suppresses Configure when children shrink and retains an
            # obsolete scroll region (the empty tail seen after reflow).
            canvas.itemconfigure(window,width=width,height=0)
            canvas.configure(scrollregion=(0,0,width,needed))
            canvas.yview_moveto(min(first,max(0,1-height/needed)))
        except tk.TclError:pass
    def schedule(event=None):
        if getattr(canvas,'_bounds_destroyed',False):return
        if canvas._sync_pending is None:canvas._sync_pending=canvas.after_idle(sync)
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
        if widget.winfo_class() in ('Text','Treeview','Listbox','TCombobox'):return
    except (AttributeError,tk.TclError):pass
    while widget is not None:
        canvas=getattr(widget,'_scroll_canvas',None)
        if canvas is not None:
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
