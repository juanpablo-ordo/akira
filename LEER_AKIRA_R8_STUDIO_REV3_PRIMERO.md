# AKIRA 16.3.5 R8 Studio — revisión 3 (código fuente)

**Esta revisión es código fuente actualizado; no contiene un instalador EXE de Windows verificado.** Se basa en el paquete R8 Studio Rev2 y conserva los ejecutores de MT5, posiciones, órdenes, protecciones, el avatar y los ajustes. No se realizaron operaciones reales. No se activó por defecto el modo TRADE, y no se alteraron los límites de capital, lote, SL/TP o margen para incrementar la frecuencia.

## Cambios desarrollados en esta revisión

1. **Diagnóstico de ejecución por causa efectiva.** `operation_health.py` describe por separado observación intencional, pausa manual, desconexión esencial, bloqueo del bróker, modo automático autorizado y vista previa. Los widgets muestran esas causas sin activar la cuenta y sin convertir estado de IA en autorización financiera. La primera instalación continúa en modo observación por seguridad.
2. **Verificación individual finita y auditable.** Las solicitudes manuales de comprobación publican fin, rechazo, datos cambiados, IA no disponible o agotamiento de plazo (125 segundos como límite del trabajo de usuario). Un broker check todavía pendiente no es una comprobación aprobada. Una IA que contesta REVISE/ABSTAIN o devuelve datos incompletos no puede aprobar; nunca se autoriza un envío por haber pasado el tiempo. Las respuestas anteriores quedan ligadas a las huellas y fechas originales.
3. **Panel nativo de Pendientes.** Vista de candidatas por símbolo con entrada, SL, TP, calidad, activación, estado y justificación detallada. Solo se presenta como «CONFIRMADA MT5 #ticket» cuando existen confirmación y ticket en los datos del actor. Seleccionar una candidata no envía órdenes. Los paneles anteriores por símbolo permanecen disponibles.
4. **Supervisión de sesiones sin actividad.** `activity_watchdog.py` distingue candidatas técnicas, señales marcadas viables y tickets propios confirmados. Avisa después de inactividad y reúne a las seis horas motivos rastreables. No ejecuta operaciones ni relaja los límites para aumentar la actividad.
5. **Regresiones.** Se añadieron pruebas de explicación de modo, desconexión, persistencia de decisiones terminales, bróker sin comprobación, abstención de IA, pantalla de pendientes, confirmación de tickets y supervisión de seis horas.

## Alcance y límites de las pruebas

- Las pruebas son locales con Python en Linux, Xvfb y FakeMT5. El archivo `VALIDACION_R8_STUDIO_REV3.json` detalla los controles ejecutados y su resultado.
- **No se compiló el instalador de Windows.** No se ha validado instalación, shaders, consumo gráfico real ni la reproducción de wallpapers tras todos los paneles de Windows.
- **No se conectó a Exness**, por tanto ni latencia externa ni autorización real de pendientes y runners ni rentabilidad futura están demostradas. El directorio de estrategias y el motor conservan los límites y reglas de la versión base.
- La integración visual 1:1 de todas las capturas, la traducción exhaustiva, la detección semántica avanzada de cualquier sprite, la composición global de fondos, el renombrado del instalador y el cierre de los 232 requisitos del documento maestro siguen **pendientes**. R8 Studio Rev3 no debe venderse como versión definitiva.

## Cómo continuar en Windows

Hacer una copia de seguridad de `%LOCALAPPDATA%\\Akira` y demás carpetas de datos originales. Descomprimir esta entrega en el repositorio de fuentes y lanzar la compilación del workflow `.github/workflows/build-windows.yml` en un entorno Windows compatible. Después realizar instalación limpia y migración, pruebas del modelo y las voces incluidas, ejecución con MT5 demo (BUY/SELL LIMIT/STOP y runner con retrocesos), reconexión, recursos durante seis horas y backtesting/forward testing con costes. **No habilitar operaciones reales automáticamente.**

## Archivos nuevos principales

`operation_health.py`, `activity_watchdog.py`, `tests/test_r11_operation_health.py`, `tests/test_r11_pending_ui.py` y `tests/test_r11_activity_watchdog.py`. Los módulos `engine.py` y `desktop.py` incorporan la integración.
