# AKIRA 16.3.5 R8

Revisión de los tres videos del 15 de octubre de 2026: respuestas de la IA, retrasos de ventana, ajustes, claves y reacciones del personaje.

En los videos, el encabezado muestra `OBSERVE` y el análisis indica candidatas evaluadas sin envíos. Ese modo prepara escenarios y no coloca órdenes. R8 lo muestra como **SOLO ANÁLISIS · NO ENVÍA ÓRDENES**, con un botón **ACTIVAR OPERATIVA**. Al activarlo confirma la cuenta conectada, conserva los límites elegidos y guarda la selección.

## Crear e instalar esta revisión

1. Copia todo el contenido del ZIP en la raíz de tu repositorio `akira`, junto a `Akira.py`. Incluye `.github`, `assets`, `installer`, `tests` y `third_party`. Acepta combinar las carpetas y reemplazar los archivos.
2. En GitHub Desktop, haz Commit y Push.
3. En Actions → AKIRA Windows - verificar y compilar → Run workflow, inicia una ejecución nueva de `main`. El título debe indicar **AKIRA 16.3.5 R8 · IA incluida**. Una ejecución anterior conserva el código de su commit.
4. Cuando todas las fases terminen correctamente, descarga el artefacto `AKIRA-16.3.5-R8-IA-fuentes-expresiones-instalador-Windows-IA-INCLUIDA` y ejecuta `AKIRA_16_3_5_R8_IA_INCLUIDA.exe`.
5. Comprueba que la ventana muestra **16.3.5 · R8**. Si quieres enviar órdenes, pulsa **ACTIVAR OPERATIVA**, revisa la cuenta y confirma. También puedes cambiar el modo en Ajustes → OPERACIÓN.

La configuración existente se conserva. El ZIP contiene código para compilar; por sí solo no actualiza la aplicación instalada. La compilación y el instalador R8 de Windows quedan pendientes de su propia ejecución de Actions.

## Operación y rapidez

El análisis técnico, riesgo, reconciliación y envío MT5 siguen funcionando fuera de la interfaz y sin esperar a una respuesta del chat o una descarga web. Una candidata válida puede enviarse en el primer ciclo operativo disponible. Una candidata bloqueada muestra su motivo concreto: modo de análisis, pausa, mercado, datos antiguos, estructura, lote mínimo, presupuesto, margen o confirmación pendiente.

Con **Entradas únicamente mediante pendientes** activado, las posiciones que nacen de ellas se gestionan como runners. Para permitir también runners directos de continuación, el control se encuentra en Ajustes → OPERACIÓN. Esas entradas requieren su confirmación M15/M5 y H1, además de las comprobaciones de riesgo y bróker. La revisión conserva los umbrales técnicos y la gestión establecidos; no aumenta automáticamente el presupuesto para forzar una entrada.

Ninguna configuración garantiza cubrir todos los movimientos ni producir beneficios.

## IA y fuentes

- El chat tiene prioridad sobre las revisiones auxiliares del modelo. Una revisión interrumpida se aplaza y mantiene su solicitud para continuar después.
- Se corrige el formato que recibe llama.cpp para las revisiones con esquema JSON. El motor recibe el contenedor de formato y su esquema, y el resultado se valida antes de usarlo.
- La cancelación puede cerrar la conexión mientras espera las cabeceras de la respuesta. También se puede detener la espera de arranque del motor.
- Las preguntas normales usan un contexto y una salida acotados. La disponibilidad del motor y el resultado del último mensaje se muestran por separado.
- Se corrigen errores frecuentes de escritura para interpretar la pregunta, conservando números, parámetros, identificadores, URLs y código. Las órdenes explícitas mantienen su ruta de autorización original.
- La actualidad exige resultados pertinentes. Una coincidencia con el país no convierte un resultado de un banco o de Google Translate en una respuesta sobre su presidente. La consulta de la Presidencia de Guatemala dispone de lectura del dominio oficial estable; el nombre se obtiene del contenido recibido.
- Las búsquedas tienen un presupuesto total y un grupo de trabajadores limitado. Si una consulta no se puede confirmar, se explica. Con una desconexión ya detectada, una pregunta que requiere actualidad no inicia una espera web inútil.

## Ventana, ajustes y claves

- Mover una ventana sin cambiar su tamaño evita repetir la distribución de paneles. Los paneles ocultos reducen su trabajo de dibujo.
- Las tablas de fuentes, órdenes e indicadores actualizan sus filas existentes y conservan selección y desplazamiento.
- Los ajustes se organizan en OPERACIÓN, RIESGO, ESTRATEGIAS, FUENTES, ASISTENTE, RENDIMIENTO, INTERFAZ y MANTENIMIENTO. El selector permite acceder a todas las secciones también con DPI alto. Los importes financieros dejan espacio al chat, ajustes, fuentes y terminal.
- **GUARDAR AJUSTES** incluye las claves introducidas. Al volver a abrir Akira se recuperan en campos enmascarados y se indica que están guardadas. Windows las protege para el mismo usuario mediante DPAPI; se verifica la escritura antes de sustituir el archivo anterior.
- El muestreo de recursos se realiza en segundo plano. La IA gestionada arranca con prioridad de CPU inferior a la normal en Windows para ceder capacidad a MT5 y a la ventana cuando hay carga. Los presupuestos de RAM/GPU siguen siendo orientativos.

## Personaje y conexión

Se conservan las ilustraciones internas y se incorporan ocho sprites de estado. Se retiran de la interfaz el contador de caras y el acceso a la galería. Akira reacciona al escribir, esperar, responder, escuchar y perder o recuperar la conexión. El parpadeo cambia los párpados; el reloj deja de elegir expresiones completas de forma periódica. La espera muestra un círculo con doce fases, dibujado sin generar una imagen nueva por cada fase.

La conectividad se comprueba en segundo plano. Los datos recientes de MT5 o de una fuente remota también sirven como evidencia de conexión, evitando confundir un dominio de comprobación bloqueado con una caída general. Una desconexión confirmada muestra aviso y el sprite dormido, pausa nuevas entradas y reintenta automáticamente. La recuperación conserva la pausa manual y el modo de operación elegido. Las protecciones confirmadas en MT5 se conservan.

## Verificación y alcance

Los informes de esta revisión están en `VERIFICACION_R8`. Incluyen pruebas completas, ejecución con red bloqueada, autocontrol de la interfaz, pantallas y mediciones con datos sintéticos. La comparación de tiempos de interfaz corresponde a Linux, no mide tu PC Windows ni la latencia del bróker.

Actions conserva las fases obligatorias de compilación, autocontrol nativo, IA real CPU e instalación completa. R8 añade comprobaciones del cliente real con pregunta escrita con faltas y una fuente de prueba, revisión JSON y cancelación antes de recibir cabeceras. Los resultados del modelo real se guardan en `diagnostics/LOCAL_AI_SCENARIOS.json`; las regresiones, en `diagnostics/REGRESSION_TESTS.xml`.

Base de código: `109d8b2bbb18da02c86dcc69342ac1732c72caf5`, correspondiente a R7 con la corrección de regresiones Windows y su ejecución 13 aprobada. Los informes de revisiones anteriores son históricos.

Verificación local final: **1,126 pruebas pytest y 87 subpruebas**, **1,123 pruebas unittest con red bloqueada**, sin fallos, errores ni omisiones; autocontrol nativo v8 y 24 combinaciones de pantalla. También se aprobaron 59 pruebas posteriores para los textos de versión y el protocolo. La verificación del modelo real y el instalador R8 de Windows sigue pendiente de Actions.

Los nuevos sprites están en `assets/avatar_states/akira_r8_states.png`; su especificación de generación con ImageGen está en `VERIFICACION_R8/SPRITES_PROMPT.md`.
