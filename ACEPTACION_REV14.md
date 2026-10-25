# Studio Rev14 · riesgo visible y equipos de pocos recursos

## Entender los importes

El riesgo en uso incluye las reservas calculadas de órdenes y posiciones recibidas de MT5 y las solicitudes que aún esperan confirmación. Estas últimas se identifican como provisionales, incluso si su importe ya se conoce. Si las listas están vacías y no hay solicitudes pendientes puede ser cero aunque hayas elegido límites altos.

Ahora se muestran por separado los topes elegidos, los límites efectivos de la cuenta, el presupuesto habilitado y el presupuesto realmente reservado. El porcentaje del presupuesto habilitado se calcula sobre el capital; el porcentaje en uso aumenta con las reservas. Un límite guardado no se presenta como una orden enviada.

Por orden se aplican el tope en dinero y el porcentaje del patrimonio. El presupuesto conjunto usa el menor entre balance y patrimonio y, si lo has establecido, un tope adicional en dinero. La vista previa explica el importe resultante. Los permisos estructurales adicionales que ya hayas activado se conservan.

## Cambiar y guardar

Pulsa **AJUSTAR** en la tarjeta de riesgo o **Cuenta → Cambiar límites**. Se abre **Ajustes → Riesgo**, con secciones separadas para cada orden, presupuesto conjunto, pérdida del día, margen y runners.

La vista previa cambia mientras editas. **Guardar límites de riesgo** guarda esa sección, actualiza la ventana principal y envía los ajustes al motor. Se muestra si están aplicados, pendientes de actualización o pendientes de conectar MT5. Se conservan las otras ediciones del formulario.

Sin órdenes aparecen el estado de las próximas entradas y **Ver motivos por activo**. Las condiciones del mercado y la aceptación del bróker siguen determinando qué órdenes pueden enviarse.

## Rendimiento

Se evita reconstruir documentos y tablas de pestañas ocultas. El contenido recibido se vuelve a presentar cuando cambia, no por cada cambio de antigüedad. Los gráficos reutilizan su imagen y solo recalculan el dibujo al cambiar las velas, niveles, tamaño o densidad de pantalla. Cambiar riesgo no vuelve a cargar el avatar ni el fondo.

**Ajustes → Apariencia → Rendimiento → Ajustar automáticamente equipos de pocos recursos** está activado inicialmente. En equipos de hasta 8 GB y dos núcleos físicos o cuatro lógicos utiliza ahorro, CPU para el modelo, contexto de 2048 y descarga del modelo al dejar de usarlo. Para el perfil de referencia Dell Latitude 7280 se usa un hilo de inferencia. La configuración efectiva se muestra en pantalla. Puedes desactivar el ajuste automático para aplicar solo tus preferencias manuales.

La frecuencia financiera de 0,2 segundos se conserva. No se modifican los límites de riesgo elegidos para reducir consumo.

## Comprobaciones

Se reproducen los límites altos en una cuenta sintética, su guardado real mediante interfaz, controlador y actor, reservas posteriores en MT5 simulado y reapertura de preferencias. Estas comprobaciones se incluyen también en el ejecutable Windows.

La compilación compara el coste de interfaz contra Rev13 con dos CPU y contenido recibido y prueba la IA real con la política de un equipo de 8 GB y dos núcleos físicos/cuatro lógicos. El procesador y la laptop físicos del usuario no se han medido directamente. No se utiliza una cuenta real ni se certifican ganancias.

Consulta el resultado efectivo y el instalador en VALIDACION_REV14.json.

## Resultado Windows

[1493 pruebas y 172 subpruebas, sin fallos ni omisiones](https://github.com/juanpablo-ordo/akira/actions/runs/40227986286). Pasaron 17 informes, la comparación con Rev13, los 19 escenarios de riesgo y recursos en origen y ejecutable, el modelo real bajo política Dell y una instalación limpia que respondió con su propia IA.

En la misma máquina, el renderizado mediano de Análisis pasó de 39,216 a 3,507 ms (−91,06 %) y el de Fuentes de 40,993 a 4,791 ms (−88,31 %). El coste de redimensionar la ventana se mantuvo similar: mediana de 64,592 a 65,479 ms. No se presenta una mejora de esa medida.

Con política Dell e IA real: retraso de interfaz p95 de 30 ms, 859 ciclos con cotización fresca y pico conjunto de aplicación y modelo de 2758,3 MiB. Las tres respuestas generadas por el modelo tardaron 41–80 s; las cuatro respuestas de identidad/presencia/capacidades usan el flujo directo. La laptop física no se ha medido.

[Descargar instalador con IA incluida](https://github.com/juanpablo-ordo/akira/actions/runs/40227986286/artifacts/12613220332), disponible hasta 2026-11-01 14:26 (Guatemala, UTC-6). Fuente compilada: `aa13f6efd5200f376fc5aa06c9aab1e78484abeb`. Resultados, procedencia y límites de medición en VALIDACION_REV14.json.
