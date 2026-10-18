# Aceptación Studio Rev7 — 16.4.2

Esta revisión responde a las fotografías y al vídeo del 18 de octubre de 2026. Las ocho referencias originales del 16 de octubre se han recuperado y comparado con la interfaz ejecutable.

| Problema observado | Cambio implementado | Comprobación |
| --- | --- | --- |
| Noticias con CERTIFICATE_VERIFY_FAILED | Contexto HTTPS con certificados del sistema y paquete Certifi incluido; conserva comprobación de cadena y nombre | Servidor TLS real: certificado válido aceptado, nombre incorrecto y raíz desconocida rechazados, también dentro del EXE |
| IA aparece no disponible después de arrancar | La investigación consulta la disponibilidad actual del motor gestionado y descarta el estado anterior almacenado | Reproducción con caché negativa previa al arranque y respuesta estructurada posterior |
| Trozos de otra expresión | Límites medidos sobre el dibujo real, separados en los huecos del atlas | 108 expresiones distintas; límites de una figura por recorte |
| Cara superpuesta y cambios de tamaño | Cambio limpio, anclaje de patas y escala por extensión real; boca por nivel de audio | Renderizado Qt y estados de parpadeo con píxeles distintos |
| Consumo elevado en ahorro | Menos reconstrucciones visuales, copia de instantáneas más ligera, investigación sin reenvíos idénticos, decoración detenida, ventana minimizada sin repintar páginas | Ensayo con afinidad de dos núcleos; actor financiero a 0,2 s; sin cuenta real |
| Diseño alejado de referencias | Actividad con filas de dos líneas y filtros visibles; títulos claros, menú activo iluminado, proporciones de paneles y avatar más grande | Capturas de las ocho páginas y adaptación a pantallas pequeñas |
| Revisiones y pendientes lentas | La cola obligatoria se atiende antes del planificador auxiliar, incluso durante ahorro | Regresiones de prioridad, evidencias y actor; conserva permisos, margen, precios y riesgo |

Los resultados cuantitativos se publican después de la compilación. La prueba de recursos utiliza datos sintéticos y no genera texto con el modelo. No sustituye medir esta laptop con su cuenta demo, noticias reales y modelo cargado. No certifica rentabilidad ni ejecución real, ni reproduce todos los estados dinámicos de las imágenes de referencia.

En ahorro, la IA recibe un resumen de indicadores en todas las temporalidades y una selección de contexto vigente. El motor técnico conserva sus cálculos completos y la revisión se etiqueta expresamente como resumida. Se conserva el contexto elegido de 2.048 tokens; no se aumenta la memoria del modelo para eludir ese límite. La revisión de lenguaje es auxiliar y no sustituye los controles de riesgo.

La compilación también comprueba la recuperación de la lectura de auto.tcl en Windows: evalúa la misma fuente de la biblioteca seleccionada con los saltos de línea normalizados como en Tcl sólo ante el error nativo de lectura identificado; otros errores se propagan.

En el perfil de ahorro las revisiones auxiliares del modelo se programan con un intervalo mínimo de diez minutos. Las solicitudes individuales explícitas conservan prioridad. La frecuencia del actor financiero sigue siendo de 0,2 segundos en el ensayo y no se reduce por esta política.

El chat descarta también el estado negativo almacenado antes de cargar su motor. Durante el redimensionado, el avatar reutiliza su imagen en Qt y sólo recalcula la resolución al terminar; no vuelve a procesar el atlas por cada píxel de movimiento.

La recuperación de inicio gráfico se limita a archivos Tcl que existen, pueden leerse y pertenecen a la biblioteca seleccionada. Si el lector nativo indica erróneamente que faltan, se reinicia solamente el intérprete, con un máximo de tres intentos. Una biblioteca realmente ausente, incompatible o con errores de código sigue deteniendo la comprobación. No se repite ninguna prueba fallida para ocultar su resultado.
