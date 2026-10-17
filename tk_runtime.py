"""Initialize Tcl's library loader before asking the native Tk DLL to load."""
from pathlib import Path
import tkinter as tk


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
    if not present:window.tk.call('source','-encoding','utf-8',str(script))
    if not window.tk.call('info','commands','::tcl_findLibrary'):
        raise RuntimeError('auto.tcl no definió tcl_findLibrary; no iniciar Tk')
    window.loadtk()
    window._akira_tk_bootstrap={'library':str(library),'loader':str(script),
        'already_loaded':present,'tcl':str(window.tk.call('info','patchlevel')),
        'tk':str(window.tk.call('package','provide','Tk'))}
    return window


def create_root(**options):
    if 'useTk' in options:raise TypeError('create_root siempre inicializa Tcl y Tk')
    window=tk.Tk(useTk=False,**options)
    try:return initialize_tk(window)
    except Exception:
        try:
            if window.tk.call('info','commands','destroy'):window.destroy()
        except tk.TclError:pass
        raise
