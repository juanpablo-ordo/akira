# AKIRA Studio Rev5 · corrección Windows 5

La ejecución 26 (`39006312418`, commit `32c12cece888f10a44f19f0cb6941bfc2d679377`) aprobó las regresiones y la compilación/autocontrol del EXE en Windows. El modelo real respondió «Hola». Después falló el comprobador con `ModuleNotFoundError: No module named 'akira_local_ai'`. La compilación del instalador y su instalación todavía no se ejecutaron.

## Causa y corrección

Al ejecutar `python installer/smoke_local_ai.py`, Python busca primero en `installer/`. El script importaba `owned_context` antes de añadir la carpeta del proyecto. Se resuelve ahora esa carpeta al iniciar el script y se importan todos los clientes antes de descargar o iniciar el modelo. El comprobador del programa instalado tiene el mismo tratamiento; su validador Studio también se importa al inicio.

El workflow ejecuta todos los módulos del instalador con `python -m installer.…`. Antes de compilar comprueba que los clientes de IA y los validadores de instalación se importan. Las pruebas nuevas ejercitan las cinco entradas tanto por ruta como por módulo. El recorrido aislado del smoke usa el cliente de producción con fixtures HTTP/proceso y comprueba contexto, normalización, respuesta estructurada y cancelación. Una respuesta equivocada continúa provocando un fallo.

El smoke conserva un JSON de fallo y el registro del servidor. El motor debe existir antes de descargar el GGUF. Los controles de modelo real, integridad, compilación e instalación permanecen activos; la prueba del programa instalado sigue utilizando exclusivamente el GGUF instalado, sin descargar otro para ocultar su ausencia.

## Verificación

- Suite completa local: **1.217 pruebas y 118 subpruebas aprobadas**, cero fallos y cero omisiones; Linux con Tcl/Tk 8.6.14 y pantalla de 1024 × 768.
- Suite offline: **1.214 pruebas unittest aprobadas**, red bloqueada, cero fallos y cero omisiones; Linux con Tcl/Tk 9.0.4 y pantalla grande.
- **Inferencia CPU real aprobada** con llama.cpp b10355 y Qwen3-4B-Q4_K_M, SHA-256 oficial verificado. Se ejecutó la ruta del script desde `/tmp`, sin `PYTHONPATH`, y se comprobaron pregunta con faltas usando una fuente grabada, JSON estructurado, cancelación y respuesta posterior. La respuesta a la pregunta factual usa un contexto sintético; no acredita una búsqueda de actualidad.
- La ejecución Windows anterior aprobó 1.210 pruebas y 102 subpruebas; omitió una prueba por falta de pantalla Tk. Aprobó el EXE y las comprobaciones visuales de origen y del ejecutable. Esto corresponde a FIX4.

Los informes están en `VERIFICACION_STUDIO_FIX5`. La inferencia Linux no certifica el instalador Windows. FIX5 todavía necesita un commit y una ejecución Windows nuevos. Se conserva el código financiero, los límites de riesgo y la configuración de FIX4.

## Usar esta corrección

1. Extrae todo el ZIP en una carpeta nueva.
2. Ejecuta `PUBLICAR_A_GITHUB_REV5.cmd` desde esa carpeta.
3. En https://github.com/juanpablo-ordo/akira/actions comprueba una ejecución nueva cuyo título incluya **corrección Windows 5**.

Reejecutar la ejecución 26 conserva el código que falló. El acceso conectado de escritura devolvió otra vez HTTP 403; el script publica con el Git autenticado de tu equipo. El instalador `AKIRA_16_4_0_STUDIO_REV5_IA_INCLUIDA.exe` solo se publica al superar todos los controles, incluida la IA del programa instalado.
