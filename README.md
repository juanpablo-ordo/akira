# AKIRA 16.4.2 · Studio Rev7

[Descargar el instalador de AKIRA 16.4.2 Studio Rev7 con IA incluida](https://github.com/juanpablo-ordo/akira/actions/runs/39152121928/artifacts/12146076612). [Ver las pruebas aprobadas en Windows](https://github.com/juanpablo-ordo/akira/actions/runs/39152121928).

Esta revisión corrige los errores de certificados de noticias, el asistente que seguía figurando como no disponible después de cargar su motor, los recortes que mostraban parte de otra expresión y varias causas de trabajo repetido en la ventana. Ajusta títulos, iconos, actividad, avatar y proporciones a las ocho referencias recuperadas.

## Instalar esta versión

1. Abre el enlace de descarga con tu sesión de GitHub y descarga el artefacto **AKIRA-16.4.2-Studio-Rev7-IA-fuentes-expresiones-instalador-Windows-IA-INCLUIDA**.
2. Extrae el ZIP y ejecuta **AKIRA_16_4_2_STUDIO_REV7_IA_INCLUIDA.exe**.
3. Comprueba **16.4.2 Studio Rev7** en Acerca de. En esta laptop selecciona **Ahorro de energía**.

El paquete incluye Qwen3-4B Q4_K_M, llama.cpp CPU/Vulkan, reconocimiento visual de sprites y el componente JavaScript de YouTube. El artefacto de binarios sin modelo es un paquete distinto. La descarga del instalador es de aproximadamente 2,87 GB y GitHub la conserva hasta el **25 de octubre de 2026**. El código y estos informes permanecen en la rama verificada.

Las instalaciones nuevas empiezan en observación. La actualización conserva los ajustes existentes. Las API se guardan desde Ajustes > Fuentes; una clave válida de CoinGlass y los permisos de servicios externos siguen siendo necesarios cuando se utiliza ese servicio.

## Cambios de Rev7

- HTTPS incorpora las raíces del sistema y Certifi dentro del ejecutable. Conserva la comprobación de certificado y nombre del servidor. Los mensajes distinguen conexión, certificado, clave ausente y permisos del servicio.
- Chat e investigación consultan el estado actual del motor gestionado después de arrancarlo. Un resultado anterior de «sin modelo» deja de bloquear una sesión que ya funciona.
- Los 108 recortes y los 16 estados de movimiento usan límites medidos sobre las figuras. Se conserva una escala y un anclaje comunes; al cambiar de expresión se limpia la anterior. Se corrigen parpadeo y amplitud de boca. Las imágenes originales no se han redibujado.
- La ventana reutiliza datos e imágenes, evita reconstruir tablas iguales y detiene los repintados de páginas minimizadas. El avatar sólo recalcula su resolución al terminar el redimensionado. En ahorro se detiene el movimiento decorativo y se reduce el refresco visual.
- La cola de revisión individual se atiende antes del trabajo auxiliar. En ahorro, las revisiones generales del modelo tienen un intervalo mínimo de diez minutos y usan un resumen de indicadores en todas las temporalidades; el motor técnico conserva sus cálculos completos. El control financiero conserva su frecuencia y sus controles de precios, permisos, margen y riesgo. **Exigir revisión IA** sigue esperando esa revisión cuando se activa.
- Actividad con filas de dos líneas y filtros visibles; títulos claros, menú activo iluminado, avatar más grande y paneles ajustables. Se mantienen las funciones de guardado, temas, fuentes, fondos, avatares propios, estrategias y reparación de Rev6.

## Resultados verificados

| Comprobación | Resultado |
| --- | --- |
| Regresiones Windows | 1.279 pruebas y 120 subpruebas; cero fallos, errores u omisiones |
| Código fuente Linux | 1.279 pruebas y 120 subpruebas; cero omisiones |
| Comprobación sin Internet | 1.276 pruebas aprobadas |
| HTTPS dentro del ejecutable | Conexión válida aceptada; nombre incorrecto y raíz desconocida rechazados |
| Instalación nueva | Modelo y motores presentes; SHA-256 correcto; respuesta de la IA instalada sin descargar reemplazos |
| Conversación con modelo real | Cinco casos aprobados: escritura, seguimiento, cambio de tema, fuentes sintéticas y JSON |
| Revisión IA en ahorro | Ambos activos, 14 temporalidades resumidas, CPU de dos hilos, contexto de 2.048 tokens; 72,4 segundos, incluido arranque |
| Cliente Windows con dos núcleos | Ahorro: 4,0% de CPU, 160,3 MB y demora de interfaz p95 de 14 ms; sin generación de texto |
| Actor con precios simulados en movimiento | 39 ciclos en ocho segundos, todos con precios vigentes; intervalo configurado de 0,2 segundos |

Los datos financieros del ensayo son sintéticos y no se enviaron órdenes a una cuenta real. La cifra de CPU no incluye generación de texto; la inferencia consume recursos y puede tardar en una laptop pequeña. Un ciclo del actor no equivale al tiempo de ejecución del broker. Estas pruebas no certifican rentabilidad ni el cumplimiento integral de los 248 puntos históricos.

Falta medir esta laptop con el modelo cargado, una sesión MT5 demo prolongada, audio y monitores físicos. La correspondencia visual exacta de todos los diálogos y la valoración de naturalidad del avatar requieren aceptación del usuario. La traducción completa de los motivos dinámicos y la conversión automática de cualquier estrategia discrecional de vídeo siguen siendo parciales.

## Evidencia y código

El instalador se construyó del commit `6070db2184476e325b186d71d8dcbddbc7b5a054`. La rama `akira-studio-rev7-verificado-20261018` añade documentación e informes; no modifica el código de aplicación que pasó Windows.

- [Alcance de la corrección](ACEPTACION_REV7.md)
- [Validación y artefacto exactos](VALIDACION_STUDIO_REV7.json)
- [Informes de pruebas](VERIFICACION_STUDIO_REV7/README.md)
- [Matriz histórica de requisitos](REQUISITOS_232_ESTADO.json)
- [Evidencia anterior de Rev6](VALIDACION_STUDIO_REV6.json)

`PACKAGE_SHA256.json` identifica los archivos inmutables del código y las pruebas. Configuración, claves, chats, diario y demás datos del usuario quedan fuera del manifiesto. El workflow puede volver a ejecutarse manualmente desde Actions seleccionando esta rama si caduca el artefacto.
