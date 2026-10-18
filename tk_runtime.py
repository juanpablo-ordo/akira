"""Initialize Tcl's library loader before asking the native Tk DLL to load."""
from pathlib import Path
import tkinter as tk
import gc,os,sys,time

_WINDOWS_BOOTSTRAP=sys.platform=='win32'


def initialize_tk(window):
    """Bootstrap from this interpreter's own library, with no fallback files."""
    library=Path(str(window.tk.call('info','library')))
    script=library/'auto.tcl'
    if not script.is_file():
        raise FileNotFoundError('La biblioteca Tcl seleccionada está incompleta: '+str(script))
    # Tk_Init calls tcl_findLibrary. Relying on a lazy auto_index entry while
    # repeatedly creating native interpreters can leave that command absent.
    # Source the selected Python's actual loader before entering Tk_Init.
    present=bool(window.tk.call('info','commands','::tcl_findLibrary'))
    python_loader=False
    if not present:
        try:window.tk.call('source','-encoding','utf-8',str(script))
        except tk.TclError as error:
            detail=str(error).lower()
            if not (_WINDOWS_BOOTSTRAP and "couldn't read file" in detail and 'no error' in detail and str(script).lower() in detail):raise
            # The native reader sporadically fails although Python can read the
            # same verified file. Evaluate those exact bytes, never substitute a
            # loader from another Tcl installation or suppress a Tcl script error.
            data=script.read_bytes()
            if not 0<len(data)<=2*1024*1024:raise
            window.tk.eval(data.decode('utf-8'));python_loader=True
    if not window.tk.call('info','commands','::tcl_findLibrary'):
        raise RuntimeError('auto.tcl no definió tcl_findLibrary; no iniciar Tk')
    window.loadtk()
    window._akira_tk_bootstrap={'library':str(library),'loader':str(script),
        'already_loaded':present,'loader_via_python':python_loader,'tcl':str(window.tk.call('info','patchlevel')),
        'tk':str(window.tk.call('package','provide','Tk'))}
    return window


def _transient_native_library_read(error):
    """Only retry the observed Windows native read failure for a readable selected library."""
    detail=str(error).lower()
    if not _WINDOWS_BOOTSTRAP or 'init.tcl' not in detail or "couldn't read file" not in detail or 'no error' not in detail:return False
    if any(word in detail for word in ('version conflict','incompatible','syntax error')):return False
    selected=os.environ.get('TCL_LIBRARY') or str(Path(sys.base_prefix)/'tcl'/('tcl'+str(tk.TclVersion)))
    script=Path(selected)/'init.tcl'
    try:return script.is_file() and 0<script.stat().st_size<=2*1024*1024 and bool(script.read_bytes())
    except OSError:return False


def create_interpreter(**options):
    """Initialize native Tcl before loading Tk, with bounded file-read recovery."""
    if 'useTk' in options:raise TypeError('create_interpreter inicializa Tcl sin cargar Tk')
    for attempt in range(3):
        try:window=tk.Tk(useTk=False,**options)
        except tk.TclError as error:
            if attempt==2 or not _transient_native_library_read(error):raise
            gc.collect();time.sleep(.05*(attempt+1));continue
        window._akira_tcl_initialization_attempts=attempt+1
        return window


def create_root(**options):
    if 'useTk' in options:raise TypeError('create_root siempre inicializa Tcl y Tk')
    window=create_interpreter(**options)
    try:
        window=initialize_tk(window)
        window._akira_tk_bootstrap['initialization_attempts']=window._akira_tcl_initialization_attempts
        return window
    except Exception:
        try:
            if window.tk.call('info','commands','destroy'):window.destroy()
        except tk.TclError:pass
        raise
