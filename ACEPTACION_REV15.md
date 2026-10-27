# Studio Rev15 · conversación y actividad

Se reconstruye la coordinación de conversación sobre un modelo Qwen3 previamente entrenado, incluido y ejecutado con llama.cpp. No se afirma haber entrenado nuevos pesos desde cero.

Las preguntas generales de ciencia y matemáticas usan directamente el modelo. Las preguntas actuales y las búsquedas explícitas conservan la verificación de fuentes. Un fallo de generación no se sustituye por titulares ajenos. Los fallos tienen Reintentar; las respuestas cortadas ofrecen Continuar.

El historial conserva un prefijo continuo dentro del contexto disponible. Cambiemos de tema inicia otro contexto sin borrar el chat visible ni los recuerdos guardados. Se excluyen del contexto las respuestas antiguas de error que pegaban noticias irrelevantes.

Cargar, pensar y responder tienen precedencia sobre las comprobaciones de reposo. El avatar refleja esas fases, mantiene el parpadeo y permite una conversación local sin inventar conexión a Internet. El análisis del mercado puede mostrarse activo aunque no exista una orden candidata.

Conservar la IA entre mensajes se ajusta de 0 a 60 segundos; por defecto son 30. No cambia los límites elegidos de riesgo. El motor financiero conserva su frecuencia.

La aceptación exige nueve respuestas completas generadas por el GGUF real, incluidas las preguntas de las capturas y sus seguimientos. Los saludos y las respuestas rápidas de identidad no cuentan como generación del modelo. La comprobación de estados del ejecutable usa un transporte sintético declarado y se informa por separado.

Estado: PASSED. Windows: 1531 pruebas y 173 subpruebas, cero omitidas. Dieciocho informes de verificación completos. Fuente compilada `016ea2c45acaaf72c610ab3f5917ce2c41f5fc13`, árbol `9c949ecf0f1fc9680178e2f3814cf8563a739fba`. [Ejecución verificada](https://github.com/juanpablo-ordo/akira/actions/runs/40429806688). El equipo físico del usuario y una cuenta real no se han probado. No se certifica rentabilidad.

## Conversación real bajo la política de laptop de 8 GB

El runner Windows se restringe a dos CPU lógicas y el modelo utiliza un hilo, sin GPU y contexto de 2048 tokens. Cada respuesta procede de llama.cpp y termina completa; se conserva el mismo proceso entre mensajes. La comprobación del ciclo visual del ejecutable usa un transporte sintético declarado por separado.

| Pregunta | Total (s) | Primer texto (s) |
|---|---:|---:|
| que piensas de la ciencia | 35.078 | 24.203 |
| dime cual es la formula mas elegante de las matematicas | 23.938 | 8.532 |
| Explícame qué significa e^(i*pi)+1=0. | 37.406 | 11.187 |
| ¿Qué representa la i en esa fórmula? | 32.031 | 16.594 |
| Cambiemos de tema: tengo 17 manzanas y regalo 5. ¿Cuántas me quedan? | 8.422 | 3.813 |
| Eso no te pregunté. Quería saber cuántas me quedan, sin hablar de ciencia. | 19.719 | 9.844 |
| Me esplicas la diferncia entre la memroia RAM y el disco de una compuadora? | 27.828 | 17.625 |
| ¿Cuál pierde los datos cuando apago la computadora? | 15.781 | 8.656 |
| Hoy me siento nervioso por una entrevista. ¿Qué puedo hacer para calmarme? | 19.235 | 7.969 |

La ventana y el motor simulado se mantienen activos mientras se genera: demora de interfaz p95 **30 ms**, ciclo financiero p95 **29.5 ms**, pico combinado app/modelo **2765 MiB**. El arranque en frío tiene un coste real; estos tiempos son mediciones del runner, no de la Dell física.

[Instalador completo](https://github.com/juanpablo-ordo/akira/actions/runs/40429806688/artifacts/12703191127) · ZIP con `2866862655` bytes · `sha256:9ee8787bea795218daa69c58c138698a6867ee6850377e1d6467f8cfcb24ec62`. La fecha de caducidad del artefacto es `2026-11-03T01:31:52Z`.

La actualización posterior de README, aceptación y validaciones incorpora la evidencia de la compilación. Esos documentos no modifican el código del instalador ya probado.
