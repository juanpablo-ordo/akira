# AKIRA 16.4.1 Studio Rev6

Aplicación de Windows con IA local incluida. Esta revisión incorpora las correcciones solicitadas después de probar Studio Rev5: conversación, guardado de ajustes, fuentes, avatar, personalización y gestión del instalador. El código se conserva en GitHub; el instalador aparece únicamente cuando termina correctamente el workflow de Windows.

## Descargar la versión correcta

En la ejecución aprobada de GitHub Actions, descarga el artefacto **AKIRA-16.4.1-Studio-Rev6-IA-fuentes-expresiones-instalador-Windows-IA-INCLUIDA**. Extrae y ejecuta **AKIRA_16_4_1_STUDIO_REV6_IA_INCLUIDA.exe**. Incluye Qwen3-4B Q4_K_M, llama.cpp CPU/Vulkan, reconocimiento visual de sprites y los componentes de YouTube. El ZIP de código y el artefacto de binarios sin modelo no son el instalador principal.

Al abrir: comprueba la versión en Acerca de; guarda tus API en Ajustes > Fuentes; comprueba la IA y conecta tu terminal MT5. Una instalación nueva empieza en observación. Las preferencias existentes de modo, cuenta y riesgo se conservan. Para autorizar envíos se confirma la cuenta desde la aplicación.

## Cambios de Rev6

- Guardado en una cola ordenada. Combina cambios de formularios distintos, conserva el último cambio del mismo campo incluso si vuelves al valor original durante un guardado, y evita que Apariencia restaure un riesgo anterior. API con control para mostrarlas y botón propio de guardado; una clave nueva sustituye la anterior.
- Chat con respuesta visible progresiva, corrección conservadora de faltas, seguimientos y cambios de tema. Las preguntas de actualidad consultan fuentes; Xbox/Gears conserva su tema en las búsquedas. Los enlaces se presentan con el nombre de la fuente. El lector conserva su posición al actualizarse el contenido.
- Reparación explícita de IA con descarga verificada y reemplazo atómico de componentes oficiales cuando falten o estén dañados. Solo anuncia éxito después de generar texto real. Una ruta de modelo personalizado existente se conserva.
- Nuevos 108 fotogramas de expresión y atlas adicional con carga, parpadeo, habla, escucha, reparación y sueño. El círculo forma parte de los sprites; no se superpone un aro externo. Un director de estados comparte las reacciones entre pestañas.
- Informes y paneles con explicaciones, tablas y fuentes con nombre. Presupuesto calculado desde la reserva real, privacidad inicial y ojo para mostrar la cuenta. Avisos filtrables por tipo.
- Revisión IA individual conservada al navegar y priorizada frente al trabajo opcional. Se eliminan los botones de forzar envíos de los paneles. El actor de ejecución continúa decidiendo, reconciliando, modificando y retirando órdenes según las condiciones vigentes.
- Estrategias en Pendientes: siete selecciones de reglas existentes y doce variantes acotadas que aplican filtros comprobables a los planes técnicos. Conservan niveles, riesgo e identidad de versión. Los resultados experimentales y los cierres reales se distinguen; una hipótesis sin resultados no se presenta como superior.
- Idiomas en listas visibles; llamada junto al chat; fuentes TTF/OTF con vista previa; paletas de color y perfiles de tema guardables. Ocho temas, brillo, textura, escala y negrita aplicables.
- Fondos globales de imagen, vídeo y GIF, bucle, FPS y ajuste al refresco. Edición con ratón para desplazamiento, recorte, giro y zoom. El decodificador pertenece a esta instalación y libera el archivo al cerrarse.
- Avatares propios por emoción, orden, duración, animación y repetición persistentes. El reconocimiento ofrece sugerencias editables y requiere revisar dibujos ambiguos.
- Ahorro reduce IA auxiliar, hilos y movimiento, limita el fondo y libera el modelo cuando está inactivo. Los controles financieros mantienen su frecuencia. Los límites del modelo son presupuestos; no se promete un límite duro de toda la GPU.
- La desinstalación cierra únicamente procesos propios bajo la carpeta de esta instalación. No cierra MT5 ni servidores de otras aplicaciones.

## Evidencia y alcance

`ACEPTACION_REV6.md`, `VALIDACION_STUDIO_REV6.json` y `VERIFICACION_STUDIO_REV6` identifican las comprobaciones de esta revisión. El workflow exige regresiones, interfaz de origen y congelada, reconocimiento visual, IA real, conversación por el asistente de producción e instalación con respuesta del modelo instalado. Los diagnósticos y las ocho capturas del ejecutable se adjuntan a esa ejecución.

`REQUISITOS_232_ESTADO.json` y `.csv` conservan los 232 requisitos y 16 adicionales. Los resultados de versiones anteriores son evidencia histórica. Una prueba sintética o un tiempo de ciclo no demuestra rentabilidad ni sustituye una sesión de MT5 demo.

Falta comprobar con hardware físico el audio, varios monitores/DPI, el consumo en tu equipo y una sesión demo prolongada. La traducción de todos los motivos dinámicos no está terminada; las voces dependen de los modelos disponibles. La fidelidad visual de todos los modales y la conversión automática de cualquier estrategia discrecional de un vídeo siguen siendo parciales. La matriz indica estas limitaciones; no se declara cumplimiento integral de los 248 puntos.

`PACKAGE_SHA256.json` identifica archivos inmutables. Configuración, claves, chats, diario y demás datos del usuario quedan fuera del manifiesto.
