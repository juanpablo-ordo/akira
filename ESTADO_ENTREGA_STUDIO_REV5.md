# Studio Rev5 · corrección Windows 4

FIX3 terminó en Windows con dos fallos: bloqueo en el primer dibujo de alto DPI y fallo de tcl_findLibrary al crear Tk. FIX4 modifica el reflujo de etiquetas y paneles, ajusta la prueba al monitor disponible e inicializa explícitamente el cargador Tcl antes de Tk. Las verificaciones actuales están en `VERIFICACION_STUDIO_FIX4`. La revisión necesita un commit nuevo, regresiones Windows, EXE e instalación aprobados. Consulta `CORRECCION_WINDOWS_4.md`.
