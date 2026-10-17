# Hallazgos de los videos y correcciones R8

| Evidencia | Hallazgo | Cambio | Verificación |
|---|---|---|---|
| Video 19-12-04, inicio | Pregunta sobre el presidente de Guatemala respondida con Google Translate y bancos | Relevancia temática obligatoria, lectura de fuente oficial, respuesta o explicación del límite | Pruebas de pregunta, ruido de buscadores, fuente oficial y modelo no disponible; escenarios de modelo real en CI |
| Videos 19-12-04 y 19-21-01 | Encabezado OBSERVE; análisis muestra candidatas sin envíos | Modo explícito, activación con confirmación y cuenta, protección de propiedad antes de escribir | Pruebas de modo, bloqueo de cuenta y primer ciclo válido |
| Video 19-21-01, tabla de datos | Filas cambian de posición y revisión por pendiente muestra error genérico | Actualización estable de filas; formato JSON compatible; error concreto y prioridad del chat | Pruebas de tabla, esquema y cancelación; revisión con motor real obligatoria en CI |
| Video 19-19-54 | Galería y contador de expresiones expuestos | Se retiran los controles públicos; sprites internos por estado y parpadeo | Inspección de widgets, transparencia y animación con doce fases |
| Video 19-19-54 | Ajustes extensos, reflujo y panel de recursos | Ocho secciones con selector, más espacio útil, sincronización de scroll, medición fuera de Tk | Pruebas de cierre y reapertura, categorías, ventanas y capturas con varias escalas |
| Solicitud de claves persistentes | Guardar el formulario general no incluía las claves; campos vacíos podían parecer pérdida de datos | Guardado general de claves, recuperación enmascarada, transacción DPAPI verificada | Reabrir la aplicación tras guardar; pruebas de credenciales |
| Solicitud de desconexión y recuperación | Faltaba una supervisión general separada de errores de proveedores | Monitor con evidencia reciente, aviso, sueño, pausa de entradas y recuperación automática | Pruebas de caída, recuperación, pausa manual, modo observe y protección existente |

La velocidad visible de ciclo en los videos está aproximadamente entre 40 y 60 ms, con algunos picos al abrir ajustes. Ese valor mide el ciclo del motor, no la fluidez de cada dibujo de la ventana. El modo OBSERVE explica los envíos ausentes en la grabación; no demuestra que toda candidata hubiera sido ejecutable con los límites de esa cuenta.

Los videos no contienen el registro completo de la excepción de revisión. Se corrigió una incompatibilidad reproducible del protocolo de esquema y se amplió el diagnóstico; no se atribuye retrospectivamente a esa incompatibilidad cualquier otro fallo que no esté registrado.

Las pruebas de ejecución usan FakeMT5 y datos sintéticos. No son operaciones reales ni una prueba de rentabilidad.
