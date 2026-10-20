# AKIRA 16.4.6 Studio Rev11

Estado inicial: PENDIENTE DE REGRESIONES Y VALIDACIÓN WINDOWS. Este archivo describe criterios; no declara resultados.

## Runners y pendientes

- El mapa pendiente se evalúa primero. Por defecto una runner no retira pendientes confirmadas del mismo activo.
- Runners directas: máximo 50% del límite general por operación. El lote se reduce solo si el bróker lo permite; nunca se acerca el SL para hacer caber el riesgo.
- El aumento de lote por puntuación está desactivado por defecto y tiene una opción explícita.
- Pérdida confirmada de runner: pausa de 3600 segundos del mismo activo. Las runners de BTC y oro comparten un presupuesto de pérdidas brutas en 24 horas equivalente a un límite general por operación.
- Las ganancias y un reinicio no borran las pérdidas del período. El cálculo depende de cierres propios completos confirmados por MT5.
- El impulso adverso de dos M1 cerradas también veta entradas directas. Una única vela roja o verde no predice el resultado de una operación.
- No se aumentan límites generales ni se modifican SL/TP de posiciones existentes por esta actualización.

## Conversación

- Identidad, capacidades, presencia y preguntas directas habituales se responden sin búsqueda web ni arranque del modelo.
- Charla personal usa el modelo y el hilo. Se conservan los recuerdos suministrados en el contexto general.
- Actualidad y hechos externos siguen requiriendo evidencia. Las respuestas deterministas no se presentan como una reparación o una inferencia verificada.
- Se prueban faltas, continuidad, tema nuevo y conversación personal con el GGUF real.

## Horas de las órdenes

PDF, Excel y JSON separan solicitud/colocación de apertura de posición. Prioridad a la hora suministrada por MT5, incluyendo milisegundos en datos. Si solo existe la solicitud de Akira, se etiqueta como tal. Sin registro, se muestra su ausencia; no se inventa la hora de captura.

## Recursos

- Detección de RAM y CPUs disponibles; ninguna GPU de 8 GB se presume sin evidencia.
- En un equipo de dos CPUs lógicas, ahorro utiliza un hilo de inferencia y uno de procesamiento de contexto.
- Se limita lote de procesamiento y se desactiva espera activa del motor.
- Ahorro en CPU carga directamente el modelo y limita la caché de contextos a 128 MiB. Comparación Windows con el mismo equipo, preguntas y modelo: pico conjunto 4605.6 → 2934.7 MiB; duración 132.172 → 133.766 s. [Prueba comparativa](https://github.com/juanpablo-ordo/akira/actions/runs/39494977511). La compilación final debe repetir el ensayo y quedar debajo de 3200 MiB.
- Las instrucciones del chat general se acortan para conservar la verificación de fuentes en contextos pequeños y reducir el procesamiento repetido.
- Comprobar el estado en ahorro no despierta el modelo. El sondeo visual se espacia al minimizar y no se reconstruyen gráficos de la página oculta.
- El ciclo financiero conserva su intervalo y sus validaciones.
- Además del benchmark sin inferencia, se mide conversación real, interfaz Qt y BTC/oro sintéticos simultáneos, incluidos CPU y RAM del modelo propio.

## Límites de esta entrega

No se puede asegurar rentabilidad, eliminar toda pérdida ni certificar el rendimiento de un equipo que no se ha medido. Los adjuntos de esta incidencia no estaban accesibles en el entorno de trabajo al preparar los cambios; no se atribuyen causas a operaciones particulares sin leer sus registros.
