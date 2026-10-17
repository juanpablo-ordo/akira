# AKIRA 16.3.5 R8 Studio — revisión 4

**Tipo de entrega: código fuente actualizado.** Este paquete no incluye un `.exe` instalado y comprobado en Windows y **no constituye la versión definitiva ni autoriza trading real**. El ejecutor financiero, datos históricos, sistema de protecciones y modos autorizados se conservan de la base R8 Rev3. No se cambiaron lotes, límites financieros ni reglas de riesgo con el propósito de aumentar la cantidad de órdenes.

## Cambios integrados sobre Rev3

- **Revisión IA con aceptación estricta.** La comprobación manual ya no trata como aprobación un `COMPLETE` sin dictamen explícito `APPROVE`, un motivo no vacío y una lista de faltantes explícita y vacía. La respuesta incompleta, contradictoria o no válida termina como rechazada. Tampoco permite marcar la comprobación como satisfactoria si hay datos esenciales ausentes. Se mantiene la separación entre IA opcional y requisito obligatorio por pendiente.
- **Supervisión de inactividad.** Reaparecer con un ticket ya visto (por actualización de la interfaz o reconexión) no simula una operación nueva ni reinicia indebidamente el cronómetro de seis horas.
- **Pendientes realmente confirmadas.** El tablero compara ticket y símbolo con el libro actual de órdenes de MT5 antes de decir «CONFIRMADA MT5». Si una tesis dice que había ticket pero este no aparece en la instantánea, muestra «RECONCILIAR CON MT5»; no supone cancelación, activación o éxito sin evidencia.
- **Temas de Studio operativos al iniciar.** Los temas Akira Original (predeterminado), Nebulosa, Océano y Carbono aplican colores de superficies y acentos, brillo, textura y escala tipográfica a los controles nativos de los módulos principales. Los colores HEX personalizados se aplican al siguiente inicio, evitando repintar la ventana durante tareas financieras. No hay un shader ni un compositor global de video en este cambio.
- **Navegación multilingüe.** Títulos y descripciones de las ocho secciones principales se traducen en los nueve idiomas adicionales integrados. Las cadenas de los paneles técnicos y las respuestas de voz no están traducidas por completo; los paquetes JSON siguen permitiendo ampliaciones.
- **Compilación futura.** Se declararon explícitamente en el contrato PyInstaller los módulos adicionales de visualización y seguridad, para evitar omisiones al empaquetar en Windows.
- **Trazabilidad.** `REQUISITOS_232_ESTADO.json` y `.csv` contienen los 232 requisitos de la especificación original y 16 solicitudes complementarias de la conversación, con estado conservador y referencias a evidencia local.

## Qué no se ha completado

1. Aplicar exactamente las capturas a **todas** las pantallas, ventanas emergentes, gráficos, iconografía, luces, tipografía y resoluciones.
2. Implementar traducción integral dinámica y soporte verificado de voz de entrada/salida en cualquier idioma.
3. Detección semántica universal de emociones en sprites arbitrarios, y editor avanzado de todos los estados y transiciones.
4. Fondos de video realmente visibles detrás de **todos** los componentes Tk y presupuestos efectivos, medidos, de GPU/CPU/RAM. El reproductor/preview de Studio no equivale a esa composición global.
5. Concluir los diagnósticos de MT5 **real**, confirmar BUY/SELL LIMIT/STOP, activaciones, reintentos y gestión de runners con controles de riesgo en la cuenta demo autorizada.
6. Medir y comparar el resultado neto de las estrategias —spread, comisiones, slippage, drawdown— con periodos fuera de muestra; no hay base para prometer ganancias.
7. Compilar, instalar, actualizar y desinstalar el ejecutable Windows y probar IA, voces, datos y multi-monitor en una instalación limpia durante al menos seis horas.
8. Cerrar con evidencia de aceptación los 232 requisitos del documento maestro. El archivo de trazabilidad no marca ninguno como completamente validado.

## Reproducir pruebas

En Linux con Xvfb y dependencias instaladas:

```
xvfb-run -a -s '-screen 0 1920x1080x24' python -m pytest -q tests --disable-warnings
```

En Windows, utilizar el workflow `.github/workflows/build-windows.yml`, que obtiene el modelo de IA con hash fijado, compila en Windows y ejecuta autocomprobaciones. Un paso que falle debe dejar el artefacto como **no apto para piloto**. No se ha ejecutado ese workflow sobre esta revisión desde aquí.

## Condición de aprobación

Solo llamar «AKIRA definitivo» al mismo instalador identificado por hash que apruebe instalación limpia, preservación de datos, conversación y voces, navegación/tema/avatares, MT5 demo sin duplicados y la sesión prolongada bajo carga. Las métricas de estrategia se evaluarán por separado de la calidad del código.
