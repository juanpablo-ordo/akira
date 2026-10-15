# AKIRA 16.3.3 · R6 · 108 expresiones

Esta entrega incluye el código completo actualizado, doce atlas originales y 108 caras seleccionables basadas en las fotos del usuario y su referencia del personaje. Se verificó que los 214 archivos de partida coincidían con el árbol de main que contenía R5.

## Ver las expresiones

Después de descomprimir, abre VER_TODAS_LAS_EXPRESIONES.html. En la aplicación: Ajustes → Interfaz → VER LAS 108 EXPRESIONES. La galería permite ver y elegir cada cara.

El catálogo nuevo se usa en la barra lateral, el centro de operaciones, el chat y la llamada. Hay expresiones de amistad, alegría, curiosidad, pensamiento, escucha, conversación, cariño, sorpresa, descanso, concentración, ánimo y cuidado. Los atlas originales de Imagegen se conservan; se leen sus celdas al mostrarlas. No se dibujan ojos o bocas encima de otras caras. Las proporciones se conservan y la caché de imágenes está acotada.

## Cambios de pantalla

- Encabezado y botones distribuidos para ventanas pequeñas.
- Menos altura ocupada por el encabezado; entrada del chat accesible.
- Títulos y textos ajustados a los paneles; bienvenida del chat adaptable.
- Tablas con desplazamiento horizontal.
- Divisiones que no se restauran mientras se arrastra otro panel.
- Navegación, ajustes, notificaciones y llamada desplazables.
- Optimizador integrado en Ajustes, con controles y textos accesibles.
- Galería paginada estable para las 108 expresiones.
- Marca visible 16.3.3 · R6 / 108 caras para reconocer la versión abierta.

## Obtener el nuevo instalador

Este ZIP es código fuente; no es un instalador EXE. La aplicación instalada no cambia hasta construir e instalar la nueva versión.

1. Copia el contenido descomprimido a la raíz de tu repositorio akira en GitHub Desktop, conservando las carpetas assets, tests, installer y .github. Haz Commit y Push.
2. GitHub → Actions → AKIRA Windows - verificar y compilar → Run workflow.
3. Cuando esa ejecución termine correctamente, descarga AKIRA-16.3.3-R6-108-expresiones-instalador-Windows. Contiene un único AKIRA_16_3_3_R6_108_EXPRESIONES.exe.
4. Cierra AKIRA, ejecuta ese instalador y comprueba la marca R6 en la ventana. Los datos de usuario se conservan al actualizar.

La conexión del asistente a GitHub devolvió 403 Resource not accessible by integration al intentar crear la rama. Esta entrega no se publicó automáticamente.

## Verificación

Los resultados y capturas con datos sintéticos están en VERIFICACION_R6. El constructor de Windows comprueba también que el ejecutable empaquetado incluye al menos 99 expresiones y que sus controles principales se dibujan.

La compilación, instalación y ejecución final en tu Windows requieren una nueva ejecución de Actions; no se presentan como comprobadas en este entorno Linux. Este cambio no modifica estrategias, límites de riesgo ni activa operaciones en una cuenta real.

Generación artística: herramienta Imagegen integrada. El conjunto completo de instrucciones está en assets/expressions/PROMPTS.json.
