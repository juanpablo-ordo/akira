# AKIRA 16.4.0 Studio Rev5 · corrección Windows 4

Revisión vigente del bloqueo en pruebas de gráficos: consulta `CORRECCION_WINDOWS_4.md`.

Entrega de código consolidado del 16 de octubre de 2026, sobre el paquete Rev4 y el documento maestro recibidos. La aplicación abre por defecto la nueva interfaz nativa Qt. Este ZIP contiene el programa fuente, sus recursos y la preparación del instalador; el EXE nuevo aún está pendiente de compilar.

## Cambios incluidos

- Ocho pestañas: Trading, Pendientes, Cuenta, Análisis, Fuentes, Chat, Ajustes y Terminal. Tipografía Rajdhani incluida, paneles adaptables, tablas que conservan selección y desplazamiento, privacidad e informes PDF/Excel.
- Análisis, MT5, chat, descargas y dibujo separados. Un responsable del envío y reconciliación. Propuestas y órdenes confirmadas se distinguen; un rechazo ya no aparece como éxito por existir otra operación. La revisión IA obligatoria por candidata se conserva.
- Instalaciones nuevas permiten pendientes y runners normales LONG/SHORT cuando se autoriza operar y se cumplen las condiciones. Una preferencia anterior explícita de solo pendientes se conserva. Los umbrales de riesgo no se han ampliado. El estado inicial es observación, sin cuenta real vinculada.
- Ajustes agrupados y guardado unificado con claves. Claves canónicas protegidas mediante DPAPI en Windows, eliminación explícita persistente y conservación del archivo si falla su lectura. El guardado informa resultados parciales.
- Chat con historial y memoria, cancelación y prioridad sobre trabajos auxiliares. El contexto del modelo gestionado se verifica con su propia plantilla y tokenizador; se limita el historial sin recortar la pregunta actual. Si lo esencial no cabe, se informa antes de inferir. Se conservan corrección de escritura y consulta de fuentes para actualidad.
- Avatar compartido entre pestañas: parpadeo, reacción al puntero, escucha/habla, transición entre expresiones, carga animada y sueño por desconexión. Se elimina el contador de expresiones y el acceso a su galería en la interfaz.
- Personalización de nombre visible, colores, tipografías, idiomas y avatar propio. Importación y orden de sprites, hojas de fotogramas, duraciones y bucles editables. Fondo global de imagen o video con recorte, rotación, desplazamiento, ajuste, calidad, FPS y presupuesto de recursos.
- Recuperación de conexión, conservación de la pausa manual y reconciliación antes de nuevos envíos. Selección de estrategias y registro de su procedencia en revisión y aprendizaje.
- Versión e identidad unificadas a 16.4.0 Studio Rev5. El publicador Rev5 conserva los avisos de espacios de Git en un registro y continúa cuando `git diff --check` devuelve 2 por esos avisos.

## Verificación terminada

**1.211 pruebas pytest y 102 subpruebas aprobadas, cero fallos y cero omisiones.** Además, **1.208 pruebas unittest con la red bloqueada**, sin fallos ni omisiones. Los autocontroles nativos completaron 12 comprobaciones Qt y 27 Tk. Se comprobó el arranque predeterminado mediante `Akira.py` con FakeMT5, sin operar una cuenta real.

Informes actuales: `VALIDACION_STUDIO_REV5.json` y `VERIFICACION_STUDIO_FIX4`. La evidencia original de Rev5 está en `VERIFICACION_STUDIO_REV5`. La medición de fluidez corresponde a una carga sintética de 12,34 segundos en Linux con chat simulado. No mide Windows ni el equipo del propietario. Los informes R6/R7/R8/Rev2/Rev3/Rev4 y las regresiones iniciales son históricos.

## Compilación pendiente

FIX3 está publicado, pero la ejecución 25 terminó con dos fallos: bloqueo del dibujo de alto DPI y falta de tcl_findLibrary al iniciar Tk. Este paquete incorpora la **corrección Windows 4**: ajuste único de etiquetas, reflujo agrupado, prueba adaptada al monitor e inicio explícito del cargador Tcl. La revisión todavía necesita verificarse en Windows. El acceso conectado sigue devolviendo **HTTP 403: Resource not accessible by integration** al escribir, por lo que esta corrección requiere publicarse con Git desde tu computadora y aún no tiene un instalador validado.

Para publicar desde un Windows con Git autenticado: extraer todo el ZIP y ejecutar `PUBLICAR_A_GITHUB_REV5.cmd`. El script usa una copia temporal, crea o actualiza la rama `akira-studio-rev5-20261016` e inicia el workflow con el código nuevo. No sustituye `main`. Los resultados aparecen en https://github.com/juanpablo-ordo/akira/actions.

La ejecución nueva debe identificar **AKIRA 16.4.0 Studio Rev5 · corrección Windows 4**. Solo tras superar regresiones, modelo real, compilación, autocontroles y prueba de instalación se genera el artefacto `AKIRA-16.4.0-Studio-Rev5-IA-fuentes-expresiones-instalador-Windows-IA-INCLUIDA`, con `AKIRA_16_4_0_STUDIO_REV5_IA_INCLUIDA.exe`. Los artefactos de ejecuciones anteriores corresponden a su propio código.

El instalador final empaqueta el modelo y los componentes mediante CI. Este ZIP de código no incluye pesos GGUF/CLIP ni equivale al instalador final. `INSTALAR_AKIRA.cmd` es el instalador heredado desde fuentes; su comprobación Windows tampoco se ha ejecutado en esta revisión.

## Alcance pendiente

La lista de los **232 requisitos y 16 solicitudes adicionales** está en `REQUISITOS_232_ESTADO.json` y `.csv`, con evidencia local y aceptación pendiente. No se declara cumplimiento integral de los 248 puntos.

Falta compilar e instalar en Windows, verificar el modelo local y el clasificador visual dentro del ejecutable, audio físico, DPI y varios monitores, límites efectivos de recursos y una sesión MT5 demo de seis horas. Algunas razones dinámicas continúan en español y los idiomas de voz dependen de los modelos disponibles. El reconocimiento de sprites ofrece sugerencias editables y no garantiza identificar cualquier dibujo. La ejecución Windows anterior sí aprobó la inferencia CPU de origen con un sprite dormido; su margen resultó ambiguo y requiere revisión.

Los límites duros CPU/RAM del fondo se aplican al decodificador propio en Windows y requieren esa validación; no existe un límite duro de GPU ni de toda la aplicación. La estrategia Adaptive es una selección inicial sobre reglas existentes: no demuestra superioridad ni convierte automáticamente todos los videos en estrategias rentables. La rapidez de envío y la rentabilidad con datos reales siguen pendientes de medir.

## Integridad

`PACKAGE_SHA256.json` identifica los archivos inmutables del programa. Se genera después de cerrar esta revisión; la configuración y los datos del usuario quedan fuera. `VALIDACION_STUDIO_REV5.json` registra las huellas de las dos entradas recibidas. Mantén juntos el código, los recursos, las pruebas y los manifiestos.
