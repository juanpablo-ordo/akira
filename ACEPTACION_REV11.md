# AKIRA 16.4.6 Studio Rev11

Estado inicial: PENDIENTE DE REGRESIONES Y VALIDACIÓN WINDOWS. Este archivo describe criterios; no declara resultados.

## Runners y pendientes

- El mapa pendiente se evalúa primero. Por defecto una runner no retira pendientes confirmadas del mismo activo.
- Runners directas: máximo 50% del límite general por operación. El lote se reduce solo si el bróker lo permite; nunca se acerca el SL para hacer caber el riesgo.
- El aumento de lote por puntuación está desactivado por defecto y tiene una opción explícita.
- Pérdida confirmada de runner: pausa de 3600 segundos del mismo activo. Las runners de BTC y oro comparten un presupuesto de pérdidas brutas en 24 horas equivalente a un límite general por operación.
- Las ganancias y un reinicio no borran las pérdidas del período. El cálculo depende de cierres propios completos confirmados por MT5.
- El impulso adverso de dos M1 cerradas también veta entradas directas. Una única vela roja o verde no predice el resultado de una operación.
- No se aumentan límites generales. Las posiciones propias abiertas también pueden recibir protección de avance cuando su precio actual alcanza el umbral configurado; nunca se amplía un SL ni se elimina el TP.
- Protección de avance activada por defecto: a partir de `management.breakeven_at_r`, el SL puede cubrir costes estimados aunque falte un pivote M15 posterior. Un pivote solo mejora ese suelo. Se conservan espera mínima, intervalo entre modificaciones y validación stops/freeze del bróker. Puede desactivarse expresamente en Ajustes → Riesgo.
- Se distinguen runners directas de pendientes activadas que usan gestión estructural. Leer un máximo favorable histórico no autoriza a inventar una protección ejecutable después de que el precio haya retrocedido.

## Conversación

- Identidad, capacidades, presencia y preguntas directas habituales se responden sin búsqueda web ni arranque del modelo.
- Charla personal usa el modelo y el hilo. Se conservan los recuerdos suministrados en el contexto general.
- Actualidad y hechos externos siguen requiriendo evidencia. Las respuestas deterministas no se presentan como una reparación o una inferencia verificada.
- Se prueban faltas, continuidad, tema nuevo y conversación personal con el GGUF real.
- La pregunta de capacidades «¿sabes de ciencia?» se contesta directamente. Si falla el modelo en una conversación personal, no se pega una lista de noticias ajenas al tema.
- En Ahorro de energía, el tiempo del chat permite al menos 120 segundos de inferencia para CPU; no se acelera ni se bloquea el ciclo financiero por ese margen. El ensayo usa esta política de producción, sin sobrescribir el tiempo de respuesta desde QA.

## Horas de las órdenes

PDF, Excel y JSON separan solicitud/colocación de apertura de posición. Prioridad a la hora suministrada por MT5, incluyendo milisegundos en datos. Si solo existe la solicitud de Akira, se etiqueta como tal. Sin registro, se muestra su ausencia; no se inventa la hora de captura.

## Recursos

- Detección de RAM y CPUs disponibles; ninguna GPU de 8 GB se presume sin evidencia.
- En un equipo de dos CPUs lógicas, ahorro utiliza un hilo de inferencia y uno de procesamiento de contexto.
- Se limita lote de procesamiento y se desactiva espera activa del motor.
- Ahorro en CPU conserva el GGUF y 2048 tokens, desactiva la caché RAM de prompts y usa Flash Attention con memoria KV q8_0. Se conserva la optimización de pesos, que fue mucho más rápida que desactivarla. Comparación Windows, mismo equipo, siete preguntas, interfaz, componente visual y motor BTC/oro sintético: pico conjunto 2998.4 → 2798.4 MiB; duración 84.563 → 88.953 s. [Comparación reproducible](https://github.com/juanpablo-ordo/akira/actions/runs/39533792740). La compilación final debe repetir el ensayo y quedar debajo de 3200 MiB. El ensayo valida esas preguntas y controles; no demuestra igualdad de todas las respuestas ni rentabilidad.
- Las instrucciones del chat general se acortan para conservar la verificación de fuentes en contextos pequeños y reducir el procesamiento repetido.
- Comprobar el estado en ahorro no despierta el modelo. El sondeo visual se espacia al minimizar y no se reconstruyen gráficos de la página oculta.
- El ciclo financiero conserva su intervalo y sus validaciones.
- Además del benchmark sin inferencia, se mide conversación real, interfaz Qt y BTC/oro sintéticos simultáneos, incluidos CPU y RAM del modelo propio.

## Límites de esta entrega

No se puede asegurar rentabilidad, eliminar toda pérdida ni certificar el rendimiento de un equipo que no se ha medido. Se revisaron localmente el informe JSON, el PDF y las siete capturas aportadas al reanudar esta incidencia. Se identificó la diferencia entre origen pendiente y gestión estructural, y un bloqueo de protección por ausencia de pivote. Los datos privados no se incorporan al repositorio. No se dispone de toda la secuencia histórica de ticks para demostrar qué resultado habría producido la nueva gestión en aquellas operaciones.
