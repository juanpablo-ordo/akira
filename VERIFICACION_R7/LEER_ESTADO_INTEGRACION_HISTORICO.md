# AKIRA — integración de fuentes, hipótesis y llamada (14 octubre 2026)

**ESTADO:** proyecto fuente consolidado, NO instalador verificado en Windows.

Cambios reales en esta revisión:
- `strategy_research.py`: múltiples análisis con procedencia y fechas de YouTube/noticias; los resultados nunca se autorizan para live.
- `assistant_akira.py`: almacena descubrimientos, transcripciones, visión y noticias para BTC y oro, diferenciando snippets no verificados de evidencia leída.
- `strategy_lab.py`: presenta resumen de investigación; sus hipótesis experimentales originales permanecen desacopladas del broker.
- `akira_live2d.py`: expresiones sencillas para preguntas y fases de una llamada, sin añadir estados visuales pesados.
- `desktop.py`: cambia el avatar al escuchar, procesar, hablar, pausar, interrumpir y finalizar; evita que el temporizador reemplace el estado durante una llamada.
- Assets: se conservan las expresiones simples basadas en el logo original del perro con huesito.
- Pendientes: conserva la revisión anti-bucle y sus límites de riesgo.

**PRUEBAS:** 96 pasaron, 1 fue omitida en la batería de regresión seleccionada. La batería íntegra se interrumpió al 71% por el tiempo disponible; no hay afirmación de aprobación general.

**FALTANTE CRÍTICO:** Instalador nativo validado en Windows, binarios oficiales llama.cpp y modelo GGUF descargados y ejecutados, build PyInstaller, pruebas Windows/MT5, pruebas de voz con micrófono, rendimiento medido en RTX 5060 Ti.

No se debe activar trading automático real a partir de esta compilación.
