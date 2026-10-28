# Studio Rev17 - capital proporcional y conversación de mentor

Estado de publicación: candidata en revisión. No usar los resultados de Rev16 como evidencia de esta compilación. Las pruebas de Windows, instalador y modelo real deben terminar antes de ofrecer un ejecutable nuevo.

## Problema y comportamiento

Un límite personalizado del 100% permitía entradas cuya pérdida estructural representaba una parte importante de una cuenta pequeña. Una pausa por pérdida diaria impedía nuevos envíos, pero dejaba pendientes confirmadas capaces de activarse. Las posiciones de un mismo activo también podían acumular otras entradas en zonas diferentes. Un score técnico alto no protege de estos efectos.

Se añade `capital_protection`, activada por defecto incluso al cargar configuraciones anteriores. Conserva los valores personalizados y aplica el menor límite efectivo. Los controles están en Ajustes > Riesgo y su vista previa explica la protección. Se puede configurar o desactivar explícitamente. Valores iniciales: 2% por orden, 6% de cartera, 3% por símbolo, 6% de pérdida diaria y 15% de caída desde la referencia. No son una optimización de rentabilidad ni límites que el mercado garantice respetar.

La referencia usa balances reconstruidos del historial disponible y patrimonio observado mientras funciona la aplicación. Se conserva por cuenta en el diario. Los movimientos de balance ajustan la referencia; las pérdidas, comisiones y flotante cuentan en el control diario sobre una base estable. No se reconstruye un máximo histórico de patrimonio que no haya sido observado. El historial disponible se consulta de nuevo al arrancar y al enviar si está desactualizado. Las métricas se reutilizan entre candidatas para evitar ordenar el mismo historial cientos de veces.

Las pendientes propias incompatibles con los límites, la pausa diaria o una posición activa se retiran mediante Gateway: comprobar ticket, permisos, freeze, order_check, envío y reconciliación. No se tocan órdenes externas. Una cancelación sin acuse conserva su reserva; otra orden puede activarse mientras el bróker no confirme la retirada. Las posiciones conservan SL/TP y sus comprobaciones de protección; no se liquidan por dinero ni se acerca su invalidación para hacer caber el lote.

En el perfil protegido, las alternativas del mapa conservan el umbral de calidad y grado exigido al mapa principal. La vía de presencia no habilita objetivos estructurales declarados como proyectados sin swing observado. Las tesis pendientes vuelven a pasar los controles M15/H1 aunque todavía no exista una pérdida. Se conservan los controles anteriores de impulso contrario, reentrada después de pérdidas, RR neto y margen. La lista de alternativas puede permanecer sin financiación cuando el lote mínimo sea incompatible con el capital.

## Conversación y herramientas

Se añaden estilos natural, mentor y detallado. La profundidad y el presupuesto de respuesta se adaptan al pedido. Se mantienen memoria, contexto, cancelación y separación del motor financiero. El modelo no se presenta como consciente, infalible ni capaz de asegurar ganancias. La IA usa el motor gratuito llama.cpp ya integrado y pesos previamente entrenados.

El asistente puede consultar cuenta, riesgo, rendimiento y actividad mediante una herramienta de solo lectura que solicita una captura al actor MT5. Se rechazan capturas con más de 15 segundos y se omiten identidad de cuenta, claves y diarios completos. Un diagnóstico de pérdidas cuenta cierres propios confirmados, deduplica posiciones y separa símbolo y vía; no atribuye operaciones a runners si no las hay. Los argumentos de herramientas se validan antes de ejecutar: JSON mal formado, tipos, campos obligatorios, enum y campos adicionales. Los resultados demasiado grandes se notifican como incompletos en vez de recortar JSON y presentarlo como evidencia íntegra.

Se expone el selector de modelo GGUF local. Un modelo personalizado inexistente no se sustituye silenciosamente por otro; el cambio se comunica al supervisor del proceso. El usuario aporta un GGUF compatible y los recursos necesarios. No se descargan pesos desconocidos ni se certifica que un modelo mayor mejore el trading.

## Verificación

Casos nuevos: cuenta pequeña frente a cuenta mayor con el mismo SL, caída persistente al reiniciar, depósitos, comisiones y flotante, historial ausente, retiro de pendientes propias, orden externa intacta, cancelación incierta, una posición por símbolo, reservas conjuntas, calidad revisada sin esperar pérdida, caché de métricas, diagnóstico sin atribuciones inventadas, privacidad, antigüedad de captura, herramientas mal formadas y elección de modelo. El recorrido Qt comprueba activar la protección, vista previa, guardado, confirmación del actor y cifra principal además de las comprobaciones previas.

Los fixtures de transporte y de edición de límites personalizados desactivan explícitamente la protección nueva: prueban ese modo configurable. Las pruebas nuevas la activan y los defaults de producción la incluyen. La regresión de capital mínimo de producción espera ahora el límite efectivo del 2%.

La validación local se registra en `VALIDACION_REV17.json`. La ejecución Windows de la rama incluye los nuevos casos, regresiones, fuente y ejecutable, inferencia real, instalación y actualización. No se ha probado una cuenta real ni el hardware físico Dell. No hay prueba prospectiva o fuera de muestra que certifique una mejora de rentabilidad. El informe de una sola cuenta no permite encontrar ni prometer la estrategia de máxima rentabilidad.

## Revisión tras inferencia real

La primera ejecución Windows (40649761941, commit 4697980) aprobó las regresiones, el ejecutable y las pruebas concurrentes, pero falló al terminar la explicación matemática: el modelo alcanzó el límite de tokens y llamó erróneamente a pi número de Euler. No se publicó un instalador.

Se añade respuesta completa con longitud y tiempo proporcionales al pedido, una sola regeneración dentro del mismo plazo y comprobación de finalización antes de guardar el turno. Un borrador truncado no se considera éxito. Un pequeño glosario de símbolos basado en NIST DLMF 4.2/4.4 aporta definiciones como datos al modelo, sin sustituir su respuesta por plantillas. La aceptación ahora también rechaza la atribución incorrecta detectada. Esto no acredita exactitud universal en matemáticas.
