# AKIRA 16.3.5 R8 — Studio Rev2 / código de revisión

**Entrega de código fuente modificada, NO un instalador `.exe` validado en Windows.**
Mantiene el proyecto AKIRA R8 y su ejecutor financiero anterior. **No conecta a Exness ni opera cuentas reales** durante los controles. La evaluación de rentabilidad, ejecución real y cumplimiento íntegro del documento maestro permanece pendiente.

## Implementación de esta revisión

- Trading/IA: revisiones de pendientes con expiración explícita y resultado final `ERROR` al exceder el plazo, sin aprobar candidatas por timeout; estado visible de verificación obligatoria frente a evidencia de IA opcional; rechazo de respuestas tardías de intentos anteriores incluso si comparten huella de contexto. No se modifican SL, TP, tamaño de lote ni límites por aumentar frecuencia.
- Inicio: panel nativo cyberpunk renovado con actividad real del motor, estado de Akira/MT5/IA/fuentes, alertas, acciones rápidas, mini gráficos BTCUSDm/XAUUSDm y resumen de pendientes. Conserva las áreas existentes, navegación y acceso a informes PDF/Excel. Se ajustaron divisores y dibujo de gráficos después de cambios de ventana.
- Avatar Studio: importa PNG, JPG, WebP, GIF animado y hojas de sprites; admite separación automática de sprites con separaciones transparentes, o filas/columnas definidas por usuario; extrae fotogramas y duración; organiza y genera sugerencias de secuencias, preservando las configuradas manualmente. La inferencia visual de parpadeo/habla mediante diferencias entre fotogramas es heurística y limitada, no reconocimiento universal de emociones.
- Idiomas: admite paquetes JSON personalizados con `locale` y diccionario `translations`; los copia a la carpeta de datos de Studio y los aplica a textos estáticos/etiquetas compatibles. Conserva idiomas integrados de navegación, opciones chat y voz; **no sustituye una traducción completa y auditada de la aplicación ni asegura voces en cualquier idioma**.
- Fondos y aspecto: continúan controles de identidad visible, colores, tipografía, sprites y previsualización local de imágenes/videos con FPS, calidad, recorte y rotación; el fondo predeterminado permanece AKIRA Original. **No hay composición de un wallpaper de video detrás de toda la interfaz Tk ni control duro de uso de GPU por fondo**.
- Guardado/migración: se corrigió la persistencia de `language_pack` en `default_config.json`; la migración conserva y reasigna las rutas de los paquetes de idiomas, avatares y fondos al actualizar con datos preservados.

## Controles

La suite de pytest Linux/Xvfb de la revisión terminó con **1140 casos y 87 subpruebas aprobados**, y la suite `unittest` terminó con **1137 pruebas aprobadas**. La autoinspección de UI en Xvfb comprobó **27 estados** con `FakeMT5` y sin acceso a red. Estos resultados NO sustituyen pruebas de Windows, monitor real, integración MT5 demo con respuestas del servidor, ni la instalación del motor local y voces.

Se incluye `VALIDACION_R8_STUDIO_REV2.json` con la evidencia local y sus limitaciones. `PACKAGE_SHA256.json` controla los archivos de esta entrega y debe verificarse al construir. Los manifiestos de versiones históricas R5-R7 se conservan para trazabilidad y **no** describen la compilación actual.

## Operación segura y próximos trabajos obligatorios

1. Construir en Windows con `.github/workflows/build-windows.yml`, verificar el `.exe` y realizar instalación limpia/actualización/desinstalación. Revisar que todas las dependencias y licencias estén incorporadas.
2. Probar el chat local, OCR/video si aplica, voces e idiomas instalados, animaciones y rendimiento en equipo real.
3. Probar MT5 demo con todos los tipos de pendiente y runners con trazabilidad completa, reconciliación y riesgo conjunto. **No autorizar automáticamente la cuenta real por esta revisión.**
4. Medir latencias, cierres y oportunidades durante al menos seis horas; reproducir OBSERVE, validaciones 6/12 y 7/12, fuentes externas, intervalos de bloqueo, reemplazos y cancelaciones repetidas.
5. Comparar resultados de estrategias en periodos separados, con spread, comisiones, deslizamiento y drawdown. No hay evidencia aquí que garantice ganancias ni superioridad de AKIRA Adaptativa.
6. El diseño exacto de todas las capturas y la cobertura de los 232 requisitos del documento `AKIRA_Instrucciones_Maestras` requieren desarrollo y aceptación adicionales: esta revisión no declara cumplimiento total.

Para prueba local con Python compatible instala `requirements.txt`; ejecuta `python -m pytest -vv tests` y `native_ui_check.run_ui_check(root)` mediante Xvfb en Linux o bajo Windows. Conserva respaldo de todos los datos personales antes de reemplazar una instalación.
