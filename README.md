# AKIRA 16.4.9 · Studio Rev14

[Descargar instalador Windows con la IA incluida](https://github.com/juanpablo-ordo/akira/actions/runs/40227986286/artifacts/12613220332)

Cierra Akira, extrae el ZIP y ejecuta `AKIRA_16_4_9_STUDIO_REV14_IA_INCLUIDA.exe`. Comprueba que la ventana indique **16.4.9 · Studio Rev14**. Descarga disponible hasta 2026-11-01 14:26 (Guatemala, UTC-6).

Pulsa **AJUSTAR** en la tarjeta de riesgo o **Cuenta → Cambiar límites**. **Ajustes → Riesgo** muestra la vista previa y **Guardar límites de riesgo** actualiza el motor y la ventana principal, indicando si está aplicado o pendiente. Tus valores guardados se conservan.

En Cuenta se separan el **capital habilitado** y el **presupuesto en uso**. Sin órdenes, posiciones ni solicitudes pendientes, el uso puede ser cero aunque el presupuesto habilitado sea del 100 %. Las reservas sin confirmación de MT5 se identifican como provisionales. **Ver motivos por activo** abre el estado de las próximas entradas.

En **Ajustes → Apariencia → Rendimiento**, la adaptación automática para equipos de 8 GB y dos núcleos físicos reduce efectos y usa CPU, un hilo de IA y contexto pequeño. Puede desactivarse. Se reutilizan gráficos y documentos que no cambiaron y se evita procesar páginas ocultas; se conserva la frecuencia de consulta financiera.

[Windows: 1493 pruebas y 172 subpruebas, sin fallos ni omisiones](https://github.com/juanpablo-ordo/akira/actions/runs/40227986286). Pasaron 17 informes: origen, ejecutable, fuentes, conversación con modelo real, carga con política Dell e instalación limpia con IA incluida.

La comparación con Rev13 redujo el renderizado mediano de Análisis un 91,06 % y de Fuentes un 88,31 %. El coste de redimensionar la ventana fue similar. Con IA activa y política Dell, el retraso de interfaz p95 fue de 30 ms y el pico conjunto de memoria de 2758,3 MiB. **El modelo local todavía tardó 41–80 s en las tres respuestas que generó en CPU**; las cuatro respuestas de identidad/presencia/capacidades usan el flujo directo.

La laptop física del usuario no se ha medido. Las pruebas operativas usan FakeMT5; no certifican rentabilidad. Las condiciones del mercado y la aceptación del bróker siguen determinando las entradas.

[Instrucciones y alcance](ACEPTACION_REV14.md) · [Resultados reproducibles](VALIDACION_REV14.json) · [Cambio de cuentas MT5](ACEPTACION_REV13.md) · [PR #4](https://github.com/juanpablo-ordo/akira/pull/4)

Fuente de aplicación compilada: `aa13f6efd5200f376fc5aa06c9aab1e78484abeb`. Tras integrarla, solo se actualizaron estos documentos y metadatos de verificación.
