# AKIRA 16.3.5 R8 + Studio — fuente modificada para validar

**NO ES UN INSTALADOR WINDOWS YA COMPILADO.** Se ha modificado el código base original R8 y se entrega con manifiestos de integridad; la compilación, prueba nativa e instalación Windows deben verificarse antes de usarlo. No se ha conectado al servidor real de Exness desde este entorno.

## Cambios implementados en el código

- Las pestañas **IDIOMA Y VOZ**, **PERSONALIZACIÓN** y **AVATAR STUDIO** agregan preferencias persistentes sin sustituir el ejecutor MT5.
- Se pueden editar nombre visible de la aplicación, colores hexadecimales, tema, brillo, tipografía y escala. El diseño **AKIRA Original** queda seleccionado por defecto. La aplicación de algunos ajustes visuales se realiza al reiniciar; no se renombran los identificadores técnicos del ejecutable y del instalador.
- Idiomas: hay diez locales para la **navegación básica y encabezados**; los módulos heredados aún conservan etiquetas sin traducir. El idioma elegido se comunica al motor de chat. El STT puede configurarse para el idioma, y se conservan las preferencias de salida por voz, pero la disponibilidad efectiva de voces e idiomas depende de los modelos instalados. No se ha verificado una traducción universal de todo el programa.
- Sprites: se pueden importar, listar, reordenar mediante botones o arrastre, asignar estados, configurar secuencias y usar el avatar original para los estados faltantes. La detección automática emplea **nombres de archivo**, no un clasificador de emociones por visión: los nombres ambiguos deben corregirse manualmente. Los archivos del usuario se copian a `studio/avatars`.
- Fondos: importar imagen o video, encuadrar, recortar, estirar, desplazar y girar; configurar opacidad, calidad, FPS y presupuestos **orientativos** de CPU/memoria. La vista previa es real con decodificación en un hilo aparte, y se añadió un panel ambiental opcional. **No hay todavía un compositor integrado de wallpaper a pantalla completa ni límites rígidos de recursos del sistema.** Los archivos se copian a `studio/wallpapers`.
- Se conservan los componentes del motor existente de pendientes y runners; los módulos visuales no ejecutan órdenes. La migración/copia de seguridad ahora contempla `studio/` y actualiza rutas internas después de actualizar Akira. Se añaden pruebas de regresión.

## Pendientes explícitos

- Compilación Windows con GitHub Actions, prueba real de `AKIRA.exe`, instalador/desinstalador, voces, video y UI a distintas escalas; verificación de que el diseño coincida *exactamente* con las capturas.
- Prueba MT5 demo de extremo a extremo, supervisión de riesgo y conexiones; no se realizó prueba real de Exness.
- Corrección y aceptación **integral** de los 232 requisitos de `AKIRA_Instrucciones_Maestras`; esta revisión no los certifica como concluidos.
- Evaluación histórica y prospectiva con costes reales para medir la calidad de la estrategia; **no existe garantía ni prueba de ganancias**.

## Cómo preparar instalador en Windows

Usa los archivos en el repositorio de origen conservando sus rutas y ejecuta el workflow `.github/workflows/build-windows.yml`; comprueba el resultado y el artefacto generado antes de instalar. Guarda una copia de seguridad de datos y configuración. Prueba primero con cuenta demo, nunca actives la cuenta real por defecto.

## Dependencias

`requirements.txt` mantiene las dependencias originales y añade `imageio` para las vistas previas de video. Los demás recursos y licencias existentes se conservan. Los archivos suministrados por el usuario no se adjuntan al paquete.
