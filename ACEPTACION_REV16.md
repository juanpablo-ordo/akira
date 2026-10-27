# Studio Rev16 · las dos solicitudes

## Riesgo, presupuesto, persistencia y fluidez

La tarjeta principal muestra el límite efectivo por orden, calculado con el dinero y el porcentaje elegidos. El riesgo reservado de órdenes y posiciones aparece debajo. Un uso de cero no se presenta como el límite configurado. Los límites sin cuenta disponible muestran espera, y las barras explican dinero habilitado y dinero en uso.

El botón Ajustar abre la pestaña Riesgo. Su guardado permanece visible mientras se recorre la página. La vista previa explica el límite, el lote admisible, la protección estructural, el margen y el lote mínimo. Se comprueba editar con teclado, guardar con el botón, aplicar al actor y recuperar campos y cifras al cerrar y abrir.

La rueda y el touchpad desplazan la página sobre controles numéricos y selectores. No cambian accidentalmente riesgo, memoria u otros ajustes. Los controles del chat se distribuyen al reducir la ventana; se comprueban 900, 1024 y 1366 píxeles y la posición de lectura mientras llegan mensajes.

## Conversación y actividad

Los temas breves y las peticiones creativas dejan de convertirse por longitud en búsquedas de noticias. Se conservan investigación explícita, hechos actuales y hechos históricos concretos. La prueba del modelo exige las nueve respuestas de Rev15 más seis de temas cortos, seguimiento, simplificación, errores de escritura y una historia.

El estado lateral usa actualizaciones recibidas del motor para mostrar análisis activo de BTC y oro, espera de datos o pausa. El chat activo tiene precedencia. Una avería de la IA permanece visible. El texto de Pensando se retira al responder o terminar. Las explicaciones de fórmulas identifican sus símbolos; la presentación convierte la notación matemática habitual a texto legible sin alterar importes ni enlaces.

## Actualización de una instalación existente

La verificación reconstruye Rev15 desde `6269a70b6373a5f986b7987f5a6c69053cf7e256`. Instala esa versión y actualiza con el nuevo instalador. Se comprueban datos canónicos y un acceso antiguo con `--app-root`, sin borrar sus preferencias. Los accesos existentes se actualizan aunque no se solicite crear otro; escritorio, menú Inicio y ejecución usan la carpeta de datos conservada.

La fuente y el ejecutable deben pasar 24 comprobaciones del recorrido de usuario. El conjunto de aceptación exige 20 informes, 15 respuestas completas de llama.cpp y una instalación limpia, además de la actualización.

Estado: PASSED en Windows. 1551 pruebas y 195 subpruebas aprobadas; cero fallos, errores u omisiones. Los 20 informes exigidos están aprobados. El hardware físico Dell no se ha medido. Las pruebas financieras usan FakeMT5; no certifican rentabilidad. Se usa Qwen3 previamente entrenado y no se afirma entrenamiento de nuevos pesos desde cero.

## Evidencia de esta compilación

Fuente: `101dbfd17ca953758d439bed2ff484b6ef96f590`. Árbol de origen: `d36610521c8803b0cc1cdb4613348936042c807e`. [Ejecución Windows](https://github.com/juanpablo-ordo/akira/actions/runs/40464092340). El manifiesto verificó 450 archivos. El resultado completo y las respuestas sin editar están en [VALIDACION_REV16.json](VALIDACION_REV16.json).

Las 24 comprobaciones de interacción pasaron en código y en el ejecutable: edición real con ratón y teclado, rueda y touchpad, guardado visible, confirmación del motor, cifra principal, reapertura, estado de actividad y ventanas de 900, 1024 y 1366 píxeles. La actualización pasó sus 16 comprobaciones con los datos canónicos y un acceso antiguo con carpeta explícita. La instalación limpia también respondió desde su IA instalada.

Las seis respuestas nuevas proceden del mismo modelo local real, terminaron con `stop` y no quedaron truncadas. La primera respuesta incluye el arranque del proceso:

| Pregunta | Primer texto visible | Respuesta terminada |
|---|---:|---:|
| pintura al óleo | 28.985 s | 45.469 s |
| ¿Me das un ejemplo? | 10.578 s | 32.344 s |
| No te entendi, esplicalo mas facil | 14.156 s | 31.719 s |
| cuéntame algo bonito | 12.093 s | 28.218 s |
| Cuéntame una historia corta de un perro. | 12.500 s | 34.297 s |
| astronomía | 14.360 s | 33.938 s |

Las nueve preguntas anteriores también recibieron una respuesta completa del modelo. Esto comprueba continuidad y finalización; no equivale a certificación factual de cada frase.

## Rendimiento y límites observados

En Windows con política Dell de 8 GB y dos CPU disponibles, la conversación concurrente con el motor sintético mantuvo p95 de interfaz en 30 ms y del ciclo del motor en 28.5 ms. Aplicación y modelo alcanzaron 2768.5 MiB y 66.9% de las dos CPU durante esa carga; la primera respuesta generada comenzó a los 57.157 s. La inferencia local sigue costando recursos y tiempo. La laptop física no se ha medido.

La comparación de interfaz con Rev13 midió la mediana del panel de análisis en 6.439 ms frente a 41.593 ms, y fuentes en 4.907 ms frente a 43.215 ms, con contenido sintético y sin inferencia. El redimensionado p95 fue 92.626 ms frente a 90.25 ms: esta prueba no acredita una mejora al redimensionar. Las mediciones cortas no acreditan ahorro energético físico.

Al revisar la respuesta `euler_explanation` se observó una frase que invierte verbalmente base y exponente. La fórmula escrita y las definiciones de e, i y π sí son correctas. La respuesta íntegra permanece en el informe; no se presenta al modelo como infalible ni esta aceptación como prueba de exactitud matemática universal. Se usa un modelo previamente entrenado.

## Instalador publicado

[Descargar instalador con IA incluida](https://github.com/juanpablo-ordo/akira/actions/runs/40464092340/artifacts/12718016406). ZIP: 2866966291 bytes. SHA-256 del ZIP del artefacto: `c3bccac1a78715223c4ebfa849e5f0d6ad0bea5d9d9ba845df84576b2ca23b79`. Archivo interior: `AKIRA_16_5_1_STUDIO_REV16_IA_INCLUIDA.exe`. Caduca: 2026-11-03T07:46:30Z.

Cierra AKIRA, extrae el ZIP y ejecuta el instalador. La prueba real de actualización conserva ajustes, chats y fondos; no requiere borrar datos ni desinstalar previamente. Los documentos de aceptación se completan después de las pruebas y no modifican el código compilado.
