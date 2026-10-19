# Aceptación Studio Rev8 — 16.4.3

Esta revisión se basa en las seis capturas recibidas el 19 de octubre. El precio visible de XAU confirma que se reciben datos, pero el historial BTC no permite saber qué impidió una entrada en oro. Se añade evidencia por activo; no se atribuye la ausencia de oro a un bloqueo que las capturas no muestran.

| Observación | Causa o cambio | Comprobación |
| --- | --- | --- |
| Revisión IA agotada y resultado conjunto perdido | Trabajos independientes BTC/XAU, con fechas y errores separados | BTC falla por tiempo; XAU recibe su turno y conserva su resultado |
| Pendientes esperando IA en una laptop lenta | Límite anterior de 30 s y vencimiento fijo de 65 s; cola propia y plazo alineado con cada fase | Contexto pequeño con modelo real; vencimientos no generan aprobación |
| Generación continua si tarda más que el intervalo | Descanso contado al terminar, por activo y perfil | Revisión lenta no vuelve a empezar inmediatamente |
| No se sabe si oro está siendo evaluado | Hora real del actor y motivo de espera, visibles por activo | Estado de XAU sin cotización reciente no bloquea BTC ni provoca un envío XAU |
| YouTube figura sin transcripción ante fallos de conexión | El lector de subtítulos aún no usaba el contexto de certificados incluido; errores absorbidos como ausencia de pistas | HTTPS real, nombre y cadena inválidos rechazados también por el lector público y dentro del EXE |
| Fuente oficial vacía o vídeo educativo marcado viejo | Estados sin novedades y referencia educativa; sin añadir votos de mercado | No se afirman publicaciones, lectura completa ni precios actuales inexistentes |
| Datos BTC dentro de una revisión de oro | Filtro de relevancia y resumen explícito del contexto | Derivados y libros BTC no se envían como evidencia XAU |

Las revisiones generales resumidas no certifican cada valor omitido. El motor técnico conserva los cálculos completos y la vigencia de las cotizaciones, límites, margen y riesgo. Una revisión individual continúa vinculada a sus niveles; no se convierten errores, faltantes ni vencimientos en permiso de envío.

La suite conserva sus comprobaciones de interfaz y ejecución. La prueba antigua de reutilización de subtítulos ahora representa una transcripción completa guardada, y otro caso comprueba que una caché antigua incompleta se vuelve a consultar sin declararla aprendida. La prueba de geometría espera el ajuste asíncrono antes de comprobar el mismo margen de dos píxeles.

Los resultados finales de Windows se incorporan cuando finaliza la instalación. El ensayo del modelo es real; sus datos financieros y noticias son sintéticos. El ensayo de consumo se ejecuta sin generar texto. No se usan credenciales ni cuenta real, y los resultados no sustituyen medir la laptop y la latencia del broker.

La prioridad se comprueba con una revisión obligatoria local sin trabajo opcional en el mismo lote, conservando el resto en cola. El backend externo conserva su caso de lote limitado a dos, con la revisión exigida primero.

El plazo de espera de la cola local tiene en cuenta los trabajos de igual o mayor prioridad que van delante, con un máximo de 500 segundos. El plazo de ejecución se cuenta por separado. Una solicitud no vence sólo porque todavía espera su turno; el vencimiento final sigue siendo un error y nunca una aprobación.
