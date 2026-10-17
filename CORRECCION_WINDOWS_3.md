# AKIRA Studio Rev5 · corrección Windows 3

La captura corresponde a la ejecución 24, commit `6e6556422940343017746801a1181460a90a2c20`. Su primer intento dejó 91 pruebas terminadas antes de ser cancelado tras 35 minutos. El segundo llevaba más de una hora en el mismo paso. Según el orden de colección, la siguiente es la nueva prueba `ChartViewportTests.test_high_dpi_short_dashboard_keeps_both_real_charts_drawn_and_scrollable`. La IA y el instalador todavía no se habían compilado. El registro antiguo no permite saber en qué llamada interna se detuvo.

## Cambios

- La prueba real con Desktop y FakeMT5 se ejecuta ahora en otro proceso. Su supervisor dispone de un límite externo de 45 segundos, que también funciona si una llamada nativa Tk no devuelve el control. Si vence, detiene el proceso y marca la prueba como fallida.
- Antes de cada intento se elimina cualquier resultado anterior. Un JSON antiguo con PASSED no puede autorizar un proceso nuevo que no terminó su prueba.
- `CHART_VIEWPORT.json` conserva fase, versiones Tcl/Tk, escala, tamaño solicitado y real, altura de gráficos, velas, elementos dibujados y número de ajustes de texto. Los registros conservan trazas Python cada 10 segundos si hay bloqueo. CI publica estos archivos incluso cuando falla.
- El paso de regresiones muestra cada nombre de prueba, vuelca trazas a los 30 segundos y tiene un límite de 15 minutos. El autocontrol gráfico de origen también queda acotado a 90 segundos. Los controles del ejecutable y del instalador siguen siendo obligatorios.
- La decoración de la ventana Windows ya no llama `update_idletasks()` desde su temporizador. Esa llamada vuelve a procesar geometría mientras ya se atiende un evento y puede impedir que un límite interno se cumpla. `winfo_id()` obtiene la ventana nativa sin ese bucle anidado. Se prueba la ruta Win32 con llamadas DWM simuladas.

Se mantienen los requisitos de altura mínima, velas dibujadas, desplazamiento, convergencia del texto y ausencia de envíos al bróker. Se exige además que el tamaño real alcance cada tamaño solicitado; la prueba usa el procesamiento nativo completo de eventos, protegido por el supervisor externo. La prueba aislada también bloquea las conexiones de red. No se modifica el análisis, el riesgo ni el envío de pendientes y runners.

## Lo comprobado y lo pendiente

La prueba específica termina con Tcl/Tk 8.6.14 y 9.0.4 en Linux. Las suites actuales y sus resultados completos están en `VERIFICACION_STUDIO_FIX3`. `WINDOWS_RUN24_OBSERVADO.json` registra lo observado en GitHub. FIX1 aprobó 1.202 pruebas y 102 subpruebas en Windows; ese resultado corresponde al código anterior.

Esta revisión corta la espera indefinida de la prueba nueva y mejora su diagnóstico. No se ha reproducido todavía el punto interno exacto del bloqueo Win32 y no se afirma que desaparezca cualquier problema de distribución. Falta ejecutar FIX3 en Windows, generar el EXE, probar su instalación y la IA real y medir MT5 demo. Ninguna de estas verificaciones demuestra rentabilidad.

## Publicar y comprobar

1. Cancela la ejecución 24 si continúa activa.
2. Extrae el ZIP completo en una carpeta nueva de Windows.
3. Ejecuta `PUBLICAR_A_GITHUB_REV5.cmd` con tu Git autenticado. Publica una corrección normal en la misma rama, sin forzar su historial.
4. Comprueba un commit y una ejecución nuevos con el título **corrección Windows 3**. Reejecutar el intento antiguo no cambia su código.
5. Si hay error, la consola identifica la prueba y el artefacto de diagnósticos conserva `CHART_VIEWPORT.*`. Solo una ejecución con todos los controles aprobados publica el instalador con IA incluida.

La escritura conectada desde aquí sigue sin estar disponible (HTTP 403 observado en las entregas anteriores). El script local conserva la vía que ya permitió publicar FIX1 y FIX2.
