# Studio Rev18: recuperación, fuentes y conversación

Estado: candidata en validación. Los resultados y el instalador de Rev17 no certifican este código.

## Fallos reproducidos

Una revisión de fondo podía ocupar el modelo sin que hubiera un chat activo. La reparación solicitaba prioridad, pero comprobaba el contador antes de que la revisión cancelada lo liberase y soltaba la prioridad antes de verificar el modelo. Rev18 espera la liberación real, serializa la inferencia y mantiene prioridad durante toda la reparación. El botón puede detener una respuesta anterior y esperar su finalización sin bloquear la interfaz. No reinicia servidores ajenos ni modifica código por inferencia.

Una llamada DNS/HTTP sin retorno podía consumir un trabajador de fuentes indefinidamente. Cada consulta pública tiene ahora un plazo supervisado; una conexión aislada conserva un único trabajador y su resultado tardío se descarta. Las demás fuentes siguen avanzando. Tras tres fallos se abre un circuito de espera. La interfaz identifica alternativas frescas de contexto con su proveedor real; no convierte un boletín o un precio de otro proveedor en el original. El resumen técnico alternativo se etiqueta como tal, no como inferencia neuronal ni evidencia independiente.

YouTube descubría videos mediante API y después perdía esos resultados cuando fallaban sus subtítulos. Se conservan enlaces y metadatos, se informa del acceso de búsqueda y transcripción por separado, se cachea el descubrimiento y se limitan las extracciones. Un cambio de credencial invalida la pausa asociada a la clave anterior. No se eluden límites, se inventan transcripciones ni se afirma haber aprendido un video incompleto. El video de referencia no se sustituye silenciosamente por otro. La documentación oficial distingue la búsqueda de la descarga de subtítulos, que exige autorización adicional: https://developers.google.com/youtube/data/reference/rest/v3/captions/download . Cuota actual: https://developers.google.com/youtube/data/determine_quota_cost .

El mapa táctico podía enviar un grado menor que el requerido para el mapa estructural y usar un R:R inferior al mínimo configurado. La admisión estricta ahora aplica grado, calidad, activación y R:R a todas las pendientes, preserva la base técnica antes del ajuste externo y se repite en Gateway con precios normalizados y costes. Una alternativa no reduce esos mínimos. Las pendientes propias existentes vuelven a pasar la admisión. No se cierran posiciones por dinero ni se altera el SL para hacer caber un lote. Los límites monetarios que el usuario guardó se conservan; configurar 100% sigue permitiendo exposición monetaria alta.

Las LIMIT contra el impulso M15 exigen recuperación M5 cerrada y vigente antes de la entrada. Son comprobaciones causales y no una prueba de mayor rentabilidad. El informe de dos cierres y la captura posterior de tres no constituyen una evaluación fuera de muestra.

## Conversación y diagnóstico

El prompt contempla humor, ironía, sarcasmo y preguntas cotidianas. Las señales explícitas de lenguaje no literal impiden interpretar el texto como autorización de órdenes. El modelo genera las respuestas; las señales de intención no contienen respuestas prefabricadas. Las preguntas de gustos y chistes usan una longitud acotada. Un fallo de chat no oculta la actividad vigente del motor, pero sigue señalado. El diagnóstico exporta el estado del asistente, error, finalización, reparación, ocupación y acceso de YouTube sin claves ni historial del chat.

## Aceptación exigida

Pruebas nuevas de preempción, exclusión, cancelación, reparación con fondo activo, DNS bloqueado, resultado tardío, apertura de circuito, fuentes alternativas, conservación de descubrimiento, cambio de clave, persistencia de pausa de subtítulos, admisión táctica y R:R y ausencia de ejecución ante sarcasmo. Regresión completa, fuente y ejecutable Windows, inferencia real con interfaz y motor simultáneos, instalación limpia y actualización desde Rev17.

La aceptación real de Rev18 exige que una revisión de fondo produzca texto antes de solicitar la reparación; después deben terminar siete respuestas neuronales de gustos, chiste, juego de palabras, sarcasmo, orden sarcástica, conversación cotidiana y cambio de tema. El reporte conserva respuestas, finalización y recursos. No acredita comprensión universal, conciencia, un modelo entrenado desde cero, hardware físico Dell ni rentabilidad. El motor gratuito incluye llama.cpp con Gemma 4 E2B IT Q4, previamente entrenado por Google y convertido por Unsloth. El tamaño, revisión y SHA-256 están fijados en bundled_model.py. Se recomienda un presupuesto orientativo de 4.096 MiB; no es un límite impuesto por Windows. Las preferencias explícitas y GGUF personalizados guardados no se reescriben. El anterior modelo relativo incluido migra en memoria al nuevo.

## Pausa por resultados confirmados

La protección activa añade una pausa de nuevas entradas después de tres pérdidas propias consecutivas entre los dos activos y ambas vías. Dura 24 horas desde el cierre que la activa; los campos de racha y duración son visibles en Ajustes. Los límites monetarios guardados se conservan. Un depósito, otro ciclo o reiniciar no borra los cierres. Gateway vuelve a comprobarla antes de enviar, incluso para solicitudes preparadas y runners. Se retiran solo pendientes propias y se espera la confirmación de MT5; no se cierran posiciones ni se ensanchan sus SL. Una retirada puede cruzarse con una activación del bróker, por lo que nunca se declara completada sin confirmación. La pausa y su motivo aparecen en cuenta, diagnóstico y reportes. Estas medidas no demuestran rentabilidad ni órdenes perfectas.

La plantilla recibe una sola instrucción inicial. El modelo genera las respuestas usando los parámetros de muestreo de su autor y una semilla reproducible; matemáticas con referencia y revisiones de mercado conservan generación determinista. Se comprueba que el sarcasmo reciba respuesta a la pregunta actual y no se trate como autorización financiera. El caso sintético de juego de palabras explicita dos sentidos de «espacio» para evitar ambigüedad entre borrar una agenda y borrar fotografías.
