# Corrección integral posterior al video del 7 de noviembre

Base integrada: `3894d456754b62fca9ee23f9ca444be1f6376a62`, última compilación
Rev21 verificada. Conserva las correcciones de reconocimiento, GPU, ondas y
menú, además de toda la cadena Rev20 y su comprobación de voz instalada.

Alcance autorizado: reparar y publicar instalador; ninguna prueba enviará órdenes
a una cuenta real. Mantener ajustes y cambios existentes. Las comprobaciones de
ejecución usarán el adaptador MT5 simulado y respuestas de bróker controladas.

- [x] Puerto ocupado: servidor HTTP propio probado, sin reutilizar ni cerrar el ajeno.
- [x] Propiedad: PID, fecha de creación, padre, ejecutable, argumentos y modelo.
- [x] GPU: VRAM NVIDIA detectada; perfil de 8 GB y perfil de 16 GB; CPU de respaldo.
- [x] Llamada: error persistente, botones, formato 48 kHz estéreo y cola hasta fin de audio.
- [x] Precarga al iniciar llamada y conservación del modelo mientras está abierta.
- [x] Ondas y menú de Rev21 conservados; horas locales y avisos duplicados corregidos.
- [x] Bloqueos explícitos; un depósito no vuelve a contarse al variar el historial.
- [x] Plan de oro visible en inicio y contexto de conversación, revalidado al abrir.
- [x] Memoria y aprendizaje existentes conservados; aprobación exacta y cierre MT5 verificables.
- [x] Regresiones de reconexión, cambio de cuenta y envío único de candidatas aprobadas.
- [ ] Compilación, instalación y comprobación del paquete publicado.

Pruebas locales: 1.753 casos pasaron en la revisión amplia; las pruebas Tk necesitan
el escritorio de Windows. El fallo del manifiesto durante las ediciones quedó
resuelto al regenerarlo. Después pasaron 97 pruebas enfocadas y 35 subpruebas.
La CI de Windows exige la suite completa, sin omisiones, conversación e inferencia
reales, voz Piper/Whisper y salida simulada de 48 kHz estéreo; comprueba también
instalación y actualización antes de publicar el instalador.

No se certifican rentabilidad, ejecución real en el bróker ni dispositivos físicos
de audio mediante pruebas sintéticas. La generación de lenguaje no se presenta
como entrenamiento de sus pesos; el aprendizaje de operaciones usa cierres
completos confirmados y muestra cuándo faltan muestras para validar un modelo.
