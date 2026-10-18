# Aceptación de Studio Rev6

Revisión de las observaciones del propietario del 17–18 de octubre de 2026. Se conservan las ocho pantallas de referencia y las instrucciones maestras. Cada comprobación usa código identificable y datos de prueba explícitos; no se ejecutan operaciones en una cuenta real.

| Solicitud | Implementación y comprobación |
|---|---|
| Ajustes y API que se pierden | `StudioController` combina cambios con la base del formulario y los guarda en orden. Pruebas de dos formularios simultáneos, último valor, reversión mientras llega una confirmación y riesgo cambiado desde otro panel. API canónicas con DPAPI, reemplazo y eliminación persistentes. |
| Chat incoherente y faltas | Contexto de conversación reducido, separación de temas y corrección conservadora. `qa_real_conversation_rev6.py` usa el asistente de producción con Qwen real: RAM/disco con faltas, seguimiento, cambio de tema, ficha sintética de Xbox y JSON estricto. El caso de noticias es ficticio y no acredita búsquedas actuales en vivo. |
| Fuentes feas y scroll forzado | Hipervínculos por nombre y HTML escapado. El desplazamiento solo sigue nuevas entradas si el lector estaba al final. |
| Reparación poco clara | Descarga con SHA256, archivo temporal, conservación del anterior ante fallo e inferencia antes de anunciar éxito. Sticker de Akira feliz tras confirmación. No hay botón Copiar en esos diálogos. |
| Sprites y carga | 108 fotogramas nuevos y atlas de movimiento adicional, misma zona de dibujo. Parpadeo y carga interna, reacciones a estados/puntero, descanso sin conexión y recuperación. Importación propia por emoción, secuencia y duración. |
| Paneles difíciles de comprender | Presentación de presupuesto, seguridad, tesis, fuentes e informes mediante títulos, tablas y explicaciones. Los datos técnicos siguen disponibles en diagnósticos. |
| Exigir IA se desmarca | Estado optimista hasta confirmación del actor, persistencia por cuenta/orden y promoción de una revisión ya en cola a prioridad requerida. |
| Estrategias sin efecto | Selector en Pendientes. Siete familias/selector y doce refinamientos compilados; una selección cambia los filtros reales. No altera niveles o límites para fabricar operaciones. El experimento mantiene resultados prospectivos separados de operaciones confirmadas. |
| Fondo y personalización | GIF/vídeo/imagen, bucle, FPS, refresco, editor con ratón, temas, paletas y fuentes. Pruebas con archivos reales y borrado después del cierre; recursos conservados al navegar. |
| Desinstalar con archivo en uso | Cierre de ventanas y procesos propios bajo la instalación antes de retirar archivos. MT5 y procesos externos excluidos. |
| Rapidez de pendientes y runners | Actor único, análisis técnico independiente de investigación, revisiones requeridas prioritarias, auxiliares con menor frecuencia en Ahorro y retirada del fsync redundante del EA heredado. Las pruebas financieras comprueban solicitudes, rechazo, modificación, invalidación y reconciliación con FakeMT5. La latencia del bróker real queda pendiente de medir. |

El instalador se publica solo después de superar el workflow. No se presenta una tarjeta de estrategia, una prueba de interfaz o un resultado de replay como prueba de ganancias. Permanecen pendientes audio físico, monitores/DPI reales y la sesión demo de seis horas. El mapa completo de requisitos conserva estado parcial donde esa aceptación falta.
