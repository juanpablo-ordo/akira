# AKIRA 16.4.6 · Studio Rev11

[Descargar el instalador Windows con la IA incluida](https://github.com/juanpablo-ordo/akira/actions/runs/39534974903/artifacts/12318093364)

1. Cierra Akira y extrae el ZIP descargado.
2. Ejecuta `AKIRA_16_4_6_STUDIO_REV11_IA_INCLUIDA.exe`.
3. Comprueba que la ventana indique **16.4.6 · Studio Rev11**. Para equipos modestos, elige **Ajustes → Rendimiento → Ahorro de energía**.

El artefacto está disponible hasta el **27/10/2026 21:17 · Guatemala (UTC-6)**. La descarga de instalación es la que termina en **IA-INCLUIDA**; el artefacto «build-no-es-instalador» no es el instalador completo.

## Cambios de esta entrega

- **Entradas y capital:** las runners directas usan, por defecto, hasta el 50 % del límite general por operación. Las pendientes se evalúan primero y una runner no retira su mapa confirmado. Hay una pausa por activo tras una pérdida confirmada y un presupuesto conjunto de pérdidas de runners en 24 horas; las ganancias y reinicios no borran el contador.
- **Protección de avance:** runners directas y pendientes activadas con gestión estructural pueden solicitar un SL que cubra costes estimados al alcanzar el umbral R configurado, aunque aún no haya un pivote M15 nuevo. Conservan el TP, la espera mínima y las restricciones del bróker. Un pivote solo mejora la protección y nunca se amplía el SL. Ajustable en **Ajustes → Riesgo**.
- **Conversación:** preguntas habituales sobre Akira, incluida «¿sabes de ciencia?», tienen respuesta directa. El chat general conserva contexto y recuerdos, tolera faltas y mantiene la investigación de hechos actuales. Un fallo en una charla personal ya no se sustituye por noticias de otro tema.
- **Informes:** PDF, Excel y JSON distinguen solicitud, colocación de la pendiente y apertura de la posición, con prioridad a la hora MT5. Los datos antiguos ausentes se identifican como sin registro.
- **Recursos:** detección real de RAM/CPUs, menos trabajo de interfaz y caché del modelo limitada en Ahorro. En una comparación controlada con el mismo equipo y modelo, el pico conjunto pasó de 2998.4 a 2798.4 MiB, una reducción del 6.7 %.

Los límites, el modo y los datos guardados se conservan al actualizar. Si el lote mínimo no cabe en el presupuesto, no se fuerza una entrada ni se acerca su SL para ocultar el riesgo.

## Comprobaciones

[Windows: 1420 pruebas y 169 subpruebas, sin fallos ni omisiones](https://github.com/juanpablo-ordo/akira/actions/runs/39534974903). Pasaron también el ejecutable y primer inicio, HTTPS, fuentes públicas, reconocimiento de sprites, revisión real BTC/oro, conversación con faltas y continuidad, y una instalación limpia que respondió usando su IA incluida.

En el ensayo de dos CPU lógicas, la conversación utilizó el GGUF real mientras la interfaz de Análisis y el actor de mercado sintético seguían activos: 747 ciclos frescos, retraso de interfaz del percentil 95 de 30 ms y pico conjunto de 2751.3 MiB. **La IA local todavía puede tardar decenas de segundos en CPU y necesita cerca de 3 GB al responder.** Estas cifras no son una medición del portátil del usuario ni una prueba de rentabilidad.

[Detalles y límites](ACEPTACION_REV11.md) · [Evidencia reproducible](VALIDACION_REV11.json) · [Solicitud de integración](https://github.com/juanpablo-ordo/akira/pull/1)

## Código y reconstrucción

Fuente de aplicación compilada: `37e6975ccdfd6d276e80341f893068fe555a9a78`. Los archivos de la aplicación coinciden con esa compilación; solo se añadieron documentación y metadatos de verificación. Para reconstruir en Actions, elige **akira-studio-rev11-20261020**, o **main** cuando incluya esta revisión, en **Run workflow**. La solicitud enlazada indica su estado de integración; el instalador enlazado arriba ya corresponde a Rev11.

No se garantiza recuperar un saldo concreto ni evitar toda pérdida. La protección necesita confirmación del bróker; saltos de precio, costes y deslizamiento siguen siendo posibles.
